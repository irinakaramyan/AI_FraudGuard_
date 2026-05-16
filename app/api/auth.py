"""
Authentication API  —  Security-hardened + TOTP Two-Factor Authentication
--------------------------------------------------------------------------
POST /api/auth/login        — obtain JWT (or 2FA challenge for admin)
GET  /api/auth/me           — current user info
GET  /api/auth/users        — list all users        (admin only)
POST /api/auth/users        — create user           (admin only)

2FA endpoints (admin only):
POST /api/auth/2fa/verify   — complete 2FA login with TOTP code
POST /api/auth/2fa/setup    — generate secret + QR code (stores pending secret)
POST /api/auth/2fa/enable   — confirm TOTP code → activate 2FA
POST /api/auth/2fa/disable  — verify TOTP code → deactivate 2FA
GET  /api/auth/2fa/status   — check if 2FA is enabled for current user

Security controls:
  • Per-IP + per-username brute-force lockout (5 attempts / 15 min)
  • Rate-limited to 5 requests/min per IP
  • Password strength policy enforced on creation
  • Admin-only endpoints strictly role-checked
  • Generic error messages (no username enumeration)
  • TOTP verified with 1-step window tolerance (±30 s clock drift)
  • Temp tokens expire in 5 minutes and carry _2fa_pending claim
"""
import base64
import io
import logging

from datetime import datetime, timedelta

import pyotp

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, jwt_required,
    get_jwt_identity, get_jwt,
)

from app.models.models import db, User
from app.utils.security import (
    LoginThrottle, validate_password, validate_email,
    admin_required, safe_str, VALID_ROLES,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

_2FA_TEMP_MINUTES = 5   # temp token lifetime while awaiting TOTP code


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_qr_b64(uri: str) -> str:
    """Return a base64-encoded PNG of the OTP provisioning URI."""
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=6, border=3)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


def _full_token(user: User) -> dict:
    """Return the standard successful-login payload."""
    user.last_login = datetime.utcnow()
    db.session.commit()
    return {
        'access_token': create_access_token(identity=str(user.id)),
        'token_type':   'Bearer',
        'expires_in':   3600,
        'user':         user.to_dict(),
    }


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------
@auth_bp.route('/login', methods=['POST'])
def login():
    data     = request.get_json(silent=True) or {}
    username = safe_str(data.get('username'), max_length=80)
    password = data.get('password', '')
    ip       = request.remote_addr or '0.0.0.0'

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    # ── Lockout check ─────────────────────────────────────────────────────────
    if LoginThrottle.is_locked(ip, username):
        secs = LoginThrottle.seconds_remaining(ip, username)
        logger.warning('Locked-out login attempt ip=%s username=%s', ip, username)
        return jsonify({
            'error': f'Account temporarily locked due to too many failed attempts. '
                     f'Try again in {secs // 60 + 1} minute(s).'
        }), 429

    # ── Authenticate ──────────────────────────────────────────────────────────
    user     = User.query.filter_by(username=username).first()
    password_ok = user.check_password(password) if user else False

    if not user or not password_ok:
        remaining = LoginThrottle.record_failure(ip, username)
        logger.warning('Failed login ip=%s username=%s remaining=%d', ip, username, remaining)
        return jsonify({'error': 'Invalid username or password'}), 401

    if not user.is_active:
        return jsonify({'error': 'Account is disabled. Contact your administrator.'}), 403

    LoginThrottle.clear(ip, username)
    logger.info('Successful login user_id=%d username=%s ip=%s', user.id, username, ip)

    # ── 2FA challenge for admin accounts that have it enabled ─────────────────
    if user.role == 'admin' and user.totp_enabled and user.totp_secret:
        temp_token = create_access_token(
            identity        = str(user.id),
            expires_delta   = timedelta(minutes=_2FA_TEMP_MINUTES),
            additional_claims={'_2fa_pending': True},
        )
        return jsonify({'requires_2fa': True, 'temp_token': temp_token}), 200

    # ── Normal login (no 2FA required) ────────────────────────────────────────
    return jsonify(_full_token(user)), 200


# ---------------------------------------------------------------------------
# POST /api/auth/2fa/verify  — complete 2FA login
# ---------------------------------------------------------------------------
@auth_bp.route('/2fa/verify', methods=['POST'])
@jwt_required()
def verify_2fa_login():
    claims = get_jwt()
    if not claims.get('_2fa_pending'):
        return jsonify({'error': 'Invalid token type for 2FA verification'}), 401

    user_id = int(get_jwt_identity())
    user    = User.query.get(user_id)
    if not user or not user.is_active:
        return jsonify({'error': 'User not found'}), 404

    code = safe_str((request.get_json(silent=True) or {}).get('code', ''), max_length=8).strip()
    if not code:
        return jsonify({'error': 'Authenticator code is required'}), 400

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code, valid_window=1):
        logger.warning('Failed 2FA verify user_id=%d', user_id)
        return jsonify({'error': 'Invalid authenticator code. Please try again.'}), 401

    logger.info('2FA verified user_id=%d', user_id)
    return jsonify(_full_token(user)), 200


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------
@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    user_id = int(get_jwt_identity())
    user    = User.query.get(user_id)
    if not user or not user.is_active:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(user.to_dict()), 200


# ---------------------------------------------------------------------------
# GET /api/auth/2fa/status
# ---------------------------------------------------------------------------
@auth_bp.route('/2fa/status', methods=['GET'])
@jwt_required()
def twofa_status():
    user_id = int(get_jwt_identity())
    user    = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({'totp_enabled': user.totp_enabled}), 200


# ---------------------------------------------------------------------------
# POST /api/auth/2fa/setup  — generate secret + QR code
# ---------------------------------------------------------------------------
@auth_bp.route('/2fa/setup', methods=['POST'])
@jwt_required()
def setup_2fa():
    user_id = int(get_jwt_identity())
    user    = User.query.get(user_id)
    if not user or user.role != 'admin':
        return jsonify({'error': 'Only admin accounts can enable 2FA'}), 403

    # Generate a new TOTP secret (pending — not yet enabled)
    secret          = pyotp.random_base32()
    user.totp_secret = secret
    user.totp_enabled = False   # remains off until user confirms with a code
    db.session.commit()

    uri    = pyotp.TOTP(secret).provisioning_uri(
        name=user.username, issuer_name='FraudGuard AI'
    )
    try:
        qr_b64 = _make_qr_b64(uri)
    except Exception:
        qr_b64 = None   # qrcode/Pillow not available — user uses manual key

    return jsonify({
        'secret':  secret,
        'uri':     uri,
        'qr_code': f'data:image/png;base64,{qr_b64}' if qr_b64 else None,
    }), 200


# ---------------------------------------------------------------------------
# POST /api/auth/2fa/enable  — confirm TOTP code → activate 2FA
# ---------------------------------------------------------------------------
@auth_bp.route('/2fa/enable', methods=['POST'])
@jwt_required()
def enable_2fa():
    user_id = int(get_jwt_identity())
    user    = User.query.get(user_id)
    if not user or user.role != 'admin':
        return jsonify({'error': 'Only admin accounts can enable 2FA'}), 403

    if not user.totp_secret:
        return jsonify({'error': 'Run /api/auth/2fa/setup first'}), 400

    code = safe_str((request.get_json(silent=True) or {}).get('code', ''), max_length=8).strip()
    if not code:
        return jsonify({'error': 'Authenticator code is required'}), 400

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code, valid_window=1):
        return jsonify({'error': 'Invalid code — make sure your authenticator app is synced'}), 401

    user.totp_enabled = True
    db.session.commit()
    logger.info('2FA enabled user_id=%d', user_id)
    return jsonify({'success': True, 'message': '2FA is now active on your account'}), 200


# ---------------------------------------------------------------------------
# POST /api/auth/2fa/disable  — verify current TOTP → deactivate 2FA
# ---------------------------------------------------------------------------
@auth_bp.route('/2fa/disable', methods=['POST'])
@jwt_required()
def disable_2fa():
    user_id = int(get_jwt_identity())
    user    = User.query.get(user_id)
    if not user or user.role != 'admin':
        return jsonify({'error': 'Only admin accounts can manage 2FA'}), 403

    if not user.totp_enabled:
        return jsonify({'error': '2FA is not currently enabled'}), 400

    code = safe_str((request.get_json(silent=True) or {}).get('code', ''), max_length=8).strip()
    if not code:
        return jsonify({'error': 'Authenticator code is required to disable 2FA'}), 400

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code, valid_window=1):
        return jsonify({'error': 'Invalid authenticator code'}), 401

    user.totp_enabled = False
    user.totp_secret  = None
    db.session.commit()
    logger.info('2FA disabled user_id=%d', user_id)
    return jsonify({'success': True, 'message': '2FA has been disabled'}), 200


# ---------------------------------------------------------------------------
# GET /api/auth/users   (admin only)
# ---------------------------------------------------------------------------
@auth_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([u.to_dict() for u in users]), 200


# ---------------------------------------------------------------------------
# POST /api/auth/users   (admin only)
# ---------------------------------------------------------------------------
@auth_bp.route('/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json(silent=True) or {}

    username = safe_str(data.get('username'), max_length=80)
    email    = safe_str(data.get('email'),    max_length=254)
    password = data.get('password', '')
    role     = safe_str(data.get('role', 'analyst'), max_length=20).lower()

    if not username:
        return jsonify({'error': 'username is required'}), 400
    if not email:
        return jsonify({'error': 'email is required'}), 400
    if not password:
        return jsonify({'error': 'password is required'}), 400

    if not validate_email(email):
        return jsonify({'error': 'Invalid email address format'}), 400

    if role not in VALID_ROLES:
        return jsonify({'error': f"Invalid role '{role}'. Must be one of: {', '.join(sorted(VALID_ROLES))}"}), 400

    pwd_errors = validate_password(password)
    if pwd_errors:
        return jsonify({'error': 'Password does not meet requirements', 'details': pwd_errors}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already taken'}), 409
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already registered'}), 409

    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    logger.info('User created username=%s role=%s by admin_id=%s',
                username, role, get_jwt_identity())
    return jsonify(user.to_dict()), 201
