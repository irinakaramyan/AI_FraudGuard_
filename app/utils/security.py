"""
Security Utilities
==================
Centralised security helpers used across all API blueprints.

  • admin_required          — decorator: JWT + admin-role check
  • analyst_or_admin        — decorator: JWT + analyst|admin check
  • sanitize_like           — escapes SQL ILIKE wildcards
  • LoginThrottle           — in-memory per-IP/username brute-force protection
  • validate_password       — enforce minimum password strength
  • safe_str / safe_int     — sanitised, bounded input helpers
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from functools import wraps
from threading import Lock

from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
LOCKOUT_ATTEMPTS  = 5          # consecutive failures before lockout
LOCKOUT_WINDOW_S  = 900        # 15-minute window
LOCKOUT_DURATION_S = 900       # 15-minute lockout
MAX_AMOUNT        = 10_000_000 # $10M hard cap per transaction
VALID_ROLES       = {'admin', 'analyst', 'viewer'}
VALID_CURRENCIES  = {'USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'CHF', 'CNY',
                     'HKD', 'SGD', 'MXN', 'BRL', 'INR', 'KRW', 'TRY', 'RUB',
                     'SAR', 'AED', 'ZAR', 'SEK', 'NOK', 'DKK', 'PLN', 'CZK'}


# ── Role-based access decorators ──────────────────────────────────────────────
def admin_required(fn):
    """Require a valid JWT token AND the 'admin' role."""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        from app.models.models import User
        try:
            user_id = int(get_jwt_identity())
            user    = User.query.get(user_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid token identity'}), 401

        if not user or not user.is_active:
            return jsonify({'error': 'User not found or disabled'}), 401
        if user.role != 'admin':
            logger.warning('Admin-required access denied for user_id=%s role=%s path=<%s>',
                           user_id, getattr(user, 'role', '?'),
                           __import__('flask').request.path)
            return jsonify({'error': 'Administrator privileges required'}), 403
        return fn(*args, **kwargs)
    return wrapper


def analyst_or_admin(fn):
    """Require a valid JWT token AND the 'analyst' or 'admin' role."""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        from app.models.models import User
        try:
            user_id = int(get_jwt_identity())
            user    = User.query.get(user_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid token identity'}), 401

        if not user or not user.is_active:
            return jsonify({'error': 'User not found or disabled'}), 401
        if user.role not in ('admin', 'analyst'):
            return jsonify({'error': 'Insufficient privileges'}), 403
        return fn(*args, **kwargs)
    return wrapper


# ── SQL ILIKE wildcard sanitiser ──────────────────────────────────────────────
def sanitize_like(value: str, max_length: int = 100) -> str:
    """
    Escape SQL ILIKE wildcard characters (% and _) in user-supplied search
    strings to prevent wildcard injection attacks.

    Also truncates to max_length to prevent DoS via very long search strings.
    """
    if not value:
        return ''
    # Truncate first, then escape
    value = value[:max_length]
    value = value.replace('\\', '\\\\')   # escape backslash first
    value = value.replace('%', r'\%')      # escape percent
    value = value.replace('_', r'\_')      # escape underscore
    return value


# ── Brute-force login protection ──────────────────────────────────────────────
class _LoginThrottle:
    """
    Thread-safe per-key (IP + username) failed-login counter with lockout.

    After LOCKOUT_ATTEMPTS failures within LOCKOUT_WINDOW_S seconds, the key
    is locked for LOCKOUT_DURATION_S seconds.
    """

    def __init__(self):
        self._lock    = Lock()
        self._records = defaultdict(list)  # key → [timestamp, ...]
        self._locked  = {}                 # key → lockout_expiry_ts

    def _key(self, ip: str, username: str) -> str:
        return f'{ip}|{username.lower()}'

    def is_locked(self, ip: str, username: str) -> bool:
        key = self._key(ip, username)
        with self._lock:
            expiry = self._locked.get(key)
            if expiry and time.time() < expiry:
                return True
            # Expired lockout — clean up
            if expiry:
                del self._locked[key]
                self._records.pop(key, None)
            return False

    def record_failure(self, ip: str, username: str) -> int:
        """Record a failed attempt. Returns remaining attempts before lockout."""
        key = self._key(ip, username)
        now = time.time()
        with self._lock:
            # Keep only attempts within the sliding window
            self._records[key] = [
                ts for ts in self._records[key]
                if now - ts < LOCKOUT_WINDOW_S
            ]
            self._records[key].append(now)
            count = len(self._records[key])

            if count >= LOCKOUT_ATTEMPTS:
                self._locked[key] = now + LOCKOUT_DURATION_S
                logger.warning(
                    'LOGIN LOCKOUT: ip=%s username=%s attempts=%d', ip, username, count
                )

            return max(0, LOCKOUT_ATTEMPTS - count)

    def clear(self, ip: str, username: str) -> None:
        """Clear failure record on successful login."""
        key = self._key(ip, username)
        with self._lock:
            self._records.pop(key, None)
            self._locked.pop(key, None)

    def seconds_remaining(self, ip: str, username: str) -> int:
        key = self._key(ip, username)
        with self._lock:
            expiry = self._locked.get(key)
            if expiry:
                return max(0, int(expiry - time.time()))
        return 0


# Module-level singleton
LoginThrottle = _LoginThrottle()


# ── Password strength validator ───────────────────────────────────────────────
def validate_password(password: str) -> list[str]:
    """
    Return a list of error messages.  Empty list = password is acceptable.

    Requirements (NIST SP 800-63B aligned):
      • At least 10 characters
      • At least 1 uppercase letter
      • At least 1 lowercase letter
      • At least 1 digit
      • At least 1 special character
    """
    errors = []
    if len(password) < 10:
        errors.append('Password must be at least 10 characters long.')
    if not re.search(r'[A-Z]', password):
        errors.append('Password must contain at least one uppercase letter.')
    if not re.search(r'[a-z]', password):
        errors.append('Password must contain at least one lowercase letter.')
    if not re.search(r'\d', password):
        errors.append('Password must contain at least one digit.')
    if not re.search(r'[^A-Za-z0-9]', password):
        errors.append('Password must contain at least one special character.')
    return errors


# ── Safe input helpers ────────────────────────────────────────────────────────
def safe_str(value, max_length: int = 255, default: str = '') -> str:
    """Coerce to string, strip whitespace, truncate."""
    if value is None:
        return default
    return str(value).strip()[:max_length]


def safe_int(value, default: int = 1, min_val: int = 1, max_val: int = 10_000) -> int:
    """Parse integer from user input with bounds."""
    try:
        n = int(value)
        return max(min_val, min(max_val, n))
    except (TypeError, ValueError):
        return default


def validate_email(email: str) -> bool:
    """Basic email format check."""
    return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email))
