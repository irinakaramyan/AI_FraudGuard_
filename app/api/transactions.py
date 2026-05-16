"""
Transactions API  —  Security-hardened
---------------------------------------
GET  /api/transactions              — paginated list with optional filters
GET  /api/transactions/<id>         — single transaction with risk detail
POST /api/transactions              — submit new transaction (runs fraud detection)
PUT  /api/transactions/<id>/review  — mark reviewed / correct fraud label
GET  /api/transactions/stats        — quick aggregate stats

Security controls:
  • ILIKE wildcard injection prevented via sanitize_like()
  • Amount bounded: 0 < amount <= $10,000,000
  • Currency validated against whitelist
  • merchant_name length capped at 120 chars
  • Pagination capped at 100 rows
  • All string inputs truncated at safe lengths
"""
import logging
import uuid
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models.models import db, Transaction, Customer, RiskScore
from app.services.fraud_detector import FraudDetector
from app.utils.security import sanitize_like, safe_str, safe_int, VALID_CURRENCIES, MAX_AMOUNT

logger = logging.getLogger(__name__)

transactions_bp = Blueprint('transactions', __name__, url_prefix='/api/transactions')

# Singleton detector — loaded once when the blueprint is first imported
_detector = FraudDetector()

_VALID_STATUSES = {'approved', 'flagged', 'blocked', 'pending'}
_VALID_CARD_TYPES = {'credit', 'debit', 'prepaid'}
_VALID_TX_TYPES = {'purchase', 'transfer', 'withdrawal', 'deposit', 'refund'}


# ---------------------------------------------------------------------------
# GET /api/transactions
# ---------------------------------------------------------------------------
@transactions_bp.route('', methods=['GET'])
@jwt_required()
def list_transactions():
    page       = safe_int(request.args.get('page'),     default=1,  min_val=1, max_val=10_000)
    per_page   = safe_int(request.args.get('per_page'), default=20, min_val=1, max_val=100)
    status     = safe_str(request.args.get('status',     ''), max_length=20)
    risk_level = safe_str(request.args.get('risk_level', ''), max_length=20)
    search     = sanitize_like(safe_str(request.args.get('search',  ''), max_length=100))
    country    = sanitize_like(safe_str(request.args.get('country', ''), max_length=10))
    start_date = safe_str(request.args.get('start_date', ''), max_length=30)
    end_date   = safe_str(request.args.get('end_date',   ''), max_length=30)

    # Amount range — parse safely, ignore non-numeric values
    min_amount = max_amount = None
    try:
        v = request.args.get('min_amount', '').strip()
        if v:
            min_amount = float(v)
    except ValueError:
        pass
    try:
        v = request.args.get('max_amount', '').strip()
        if v:
            max_amount = float(v)
    except ValueError:
        pass

    query = Transaction.query

    if status and status in _VALID_STATUSES:
        query = query.filter(Transaction.status == status)

    # Customer join (needed for name search or country filter) — done once
    need_customer = bool(search or country)
    if need_customer:
        query = query.join(Customer, Transaction.customer_id == Customer.id)
        if search:
            query = query.filter(db.or_(
                Customer.name.ilike(f'%{search}%'),
                Transaction.merchant_name.ilike(f'%{search}%'),
                Transaction.transaction_id.ilike(f'%{search}%'),
            ))
        if country:
            query = query.filter(Customer.country.ilike(f'%{country}%'))

    if min_amount is not None:
        query = query.filter(Transaction.amount >= min_amount)
    if max_amount is not None:
        query = query.filter(Transaction.amount <= max_amount)
    if start_date:
        query = query.filter(Transaction.timestamp >= start_date)
    if end_date:
        query = query.filter(Transaction.timestamp <= end_date)
    if risk_level:
        query = (
            query
            .join(RiskScore, RiskScore.transaction_id == Transaction.id)
            .filter(RiskScore.risk_level == risk_level)
        )

    query     = query.order_by(Transaction.timestamp.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    results = []
    for t in paginated.items:
        t_dict = t.to_dict()
        rs     = RiskScore.query.filter_by(transaction_id=t.id).first()
        t_dict['combined_score'] = round(rs.combined_score, 4) if rs else None
        t_dict['risk_level']     = rs.risk_level if rs else None
        results.append(t_dict)

    return jsonify({
        'transactions': results,
        'total':        paginated.total,
        'pages':        paginated.pages,
        'current_page': page,
        'per_page':     per_page,
    }), 200


# ---------------------------------------------------------------------------
# GET /api/transactions/stats
# ---------------------------------------------------------------------------
@transactions_bp.route('/stats', methods=['GET'])
@jwt_required()
def transaction_stats():
    from sqlalchemy import func
    total        = Transaction.query.count()
    approved     = Transaction.query.filter_by(status='approved').count()
    flagged      = Transaction.query.filter_by(status='flagged').count()
    blocked      = Transaction.query.filter_by(status='blocked').count()
    fraud        = Transaction.query.filter_by(is_fraud=True).count()
    total_amount = db.session.query(func.sum(Transaction.amount)).scalar() or 0
    return jsonify({
        'total':        total,
        'approved':     approved,
        'flagged':      flagged,
        'blocked':      blocked,
        'fraud':        fraud,
        'fraud_rate':   round(fraud / total * 100, 2) if total else 0,
        'total_amount': round(float(total_amount), 2),
    }), 200


# ---------------------------------------------------------------------------
# GET /api/transactions/<id>
# ---------------------------------------------------------------------------
@transactions_bp.route('/<int:transaction_id>', methods=['GET'])
@jwt_required()
def get_transaction(transaction_id):
    t      = Transaction.query.get_or_404(transaction_id)
    result = t.to_dict()
    rs     = RiskScore.query.filter_by(transaction_id=t.id).first()
    result['risk_score_detail'] = rs.to_dict() if rs else None
    result['alerts']            = [a.to_dict() for a in t.alerts]
    return jsonify(result), 200


# ---------------------------------------------------------------------------
# POST /api/transactions
# ---------------------------------------------------------------------------
@transactions_bp.route('', methods=['POST'])
@jwt_required()
def process_transaction():
    """Submit a transaction for fraud detection and persistence."""
    raw_data = request.get_json(silent=True) or {}

    # ── Data Ingestion & Preprocessing ───────────────────────────────────────
    # Run every incoming transaction through the ingestion pipeline:
    # clean, normalise, validate, enrich, and mask PII in logs
    try:
        from app.services.ingestion_service import ingestion_service
        prep = ingestion_service.preprocess_transaction(raw_data)
        if not prep.is_valid:
            return jsonify({
                'error':           prep.rejected_reason,
                'quality_report':  ingestion_service.data_quality_report(prep),
            }), 422
        # Merge preprocessed clean values back; keep any extra keys from raw
        data = {**raw_data, **prep.data}
        if prep.quality_flags:
            logger.info('TX preprocessing warnings for %s: %s',
                        data.get('customer_id'), prep.quality_flags)
    except Exception as exc:
        logger.warning('Ingestion preprocessing skipped (%s) — using raw data', exc)
        data = raw_data

    # ── Required fields ───────────────────────────────────────────────────────
    for field in ('customer_id', 'amount', 'merchant_name'):
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    # ── Amount validation ─────────────────────────────────────────────────────
    try:
        amount = float(data['amount'])
        if amount <= 0:
            raise ValueError('amount must be positive')
        if amount > MAX_AMOUNT:
            return jsonify({
                'error': f'amount exceeds maximum allowed value of {MAX_AMOUNT:,.0f}'
            }), 400
    except (ValueError, TypeError):
        return jsonify({'error': 'amount must be a positive number'}), 400

    # ── Currency validation ───────────────────────────────────────────────────
    currency = safe_str(data.get('currency', 'USD'), max_length=3).upper()
    if currency not in VALID_CURRENCIES:
        return jsonify({'error': f"Unsupported currency '{currency}'"}), 400

    # ── String field sanitisation ─────────────────────────────────────────────
    merchant_name     = safe_str(data.get('merchant_name', ''),     max_length=120)
    merchant_category = safe_str(data.get('merchant_category', 'general'), max_length=60)
    location          = safe_str(data.get('location', ''),          max_length=100)
    device_id         = safe_str(data.get('device_id', 'unknown'),  max_length=80)

    card_type = safe_str(data.get('card_type', 'credit'), max_length=20).lower()
    if card_type not in _VALID_CARD_TYPES:
        card_type = 'credit'

    tx_type = safe_str(data.get('transaction_type', 'purchase'), max_length=20).lower()
    if tx_type not in _VALID_TX_TYPES:
        tx_type = 'purchase'

    if not merchant_name:
        return jsonify({'error': 'merchant_name cannot be empty'}), 400

    # ── Resolve customer ──────────────────────────────────────────────────────
    customer = Customer.query.filter_by(
        customer_id=safe_str(str(data['customer_id']), max_length=50)
    ).first()
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    # ── Build transaction record ──────────────────────────────────────────────
    ip_raw = safe_str(
        data.get('ip_address') or request.remote_addr or '0.0.0.0',
        max_length=45   # max IPv6 length
    )

    transaction = Transaction(
        transaction_id    = str(uuid.uuid4()),
        customer_id       = customer.id,
        amount            = round(amount, 2),
        currency          = currency,
        merchant_name     = merchant_name,
        merchant_category = merchant_category,
        location          = location or customer.country,
        ip_address        = ip_raw,
        device_id         = device_id,
        card_type         = card_type,
        transaction_type  = tx_type,
        timestamp         = datetime.utcnow(),
        status            = 'pending',
    )
    db.session.add(transaction)
    db.session.flush()   # assign transaction.id before fraud analysis

    # ── Run fraud analysis (commits internally) ───────────────────────────────
    analysis = _detector.analyze_transaction(transaction, customer)

    logger.info('Transaction processed tx=%s customer=%s amount=%.2f status=%s',
                transaction.transaction_id, customer.customer_id,
                amount, transaction.status)

    return jsonify({
        'success':        True,
        'transaction':    transaction.to_dict(),
        'fraud_analysis': analysis,
    }), 201


# ---------------------------------------------------------------------------
# PUT /api/transactions/<id>/review   (analyst or admin)
# ---------------------------------------------------------------------------
@transactions_bp.route('/<int:transaction_id>/review', methods=['PUT'])
@jwt_required()
def review_transaction(transaction_id):
    t    = Transaction.query.get_or_404(transaction_id)
    data = request.get_json(silent=True) or {}

    t.is_reviewed = True
    if 'is_fraud' in data:
        t.is_fraud = bool(data['is_fraud'])
    if 'status' in data and data['status'] in _VALID_STATUSES:
        t.status = data['status']

    reviewer_id = int(get_jwt_identity())
    logger.info('Transaction reviewed tx_id=%d reviewer_id=%d new_status=%s',
                transaction_id, reviewer_id, t.status)

    db.session.commit()
    return jsonify({'success': True, 'transaction': t.to_dict()}), 200
