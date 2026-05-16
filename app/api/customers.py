"""
Customers API  —  Security-hardened
-------------------------------------
GET /api/customers           — paginated customer list
GET /api/customers/<id>      — customer detail with transaction summary

Security controls:
  • ILIKE wildcard injection prevented via sanitize_like()
  • per_page hard-capped at 50 (was 200 — limits data exfiltration)
  • risk_level validated against whitelist
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func

from app.models.models import db, Customer, Transaction, RiskScore
from app.utils.security import sanitize_like, safe_str, safe_int

customers_bp = Blueprint('customers', __name__, url_prefix='/api/customers')

_VALID_RISK_LEVELS = {'low', 'medium', 'high', 'critical'}


@customers_bp.route('', methods=['GET'])
@jwt_required()
def list_customers():
    page       = safe_int(request.args.get('page'),     default=1,  min_val=1, max_val=10_000)
    per_page   = safe_int(request.args.get('per_page'), default=25, min_val=1, max_val=50)
    risk_level = safe_str(request.args.get('risk_level', ''), max_length=20).lower()
    search     = sanitize_like(safe_str(request.args.get('search', ''), max_length=100))

    query = Customer.query

    if risk_level and risk_level in _VALID_RISK_LEVELS:
        query = query.filter_by(risk_level=risk_level)
    if search:
        query = query.filter(db.or_(
            Customer.name.ilike(f'%{search}%'),
            Customer.customer_id.ilike(f'%{search}%'),
            Customer.email.ilike(f'%{search}%'),
        ))

    query     = query.order_by(Customer.name)
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'customers':    [c.to_dict() for c in paginated.items],
        'total':        paginated.total,
        'pages':        paginated.pages,
        'current_page': page,
    }), 200


@customers_bp.route('/<int:customer_id>', methods=['GET'])
@jwt_required()
def get_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    result   = customer.to_dict()

    # Recent 10 transactions only
    recent = (
        Transaction.query
        .filter_by(customer_id=customer.id)
        .order_by(Transaction.timestamp.desc())
        .limit(10)
        .all()
    )
    result['recent_transactions'] = [t.to_dict() for t in recent]

    # Fraud rate
    total_tx = Transaction.query.filter_by(customer_id=customer.id).count()
    fraud_tx = Transaction.query.filter_by(customer_id=customer.id, is_fraud=True).count()
    result['fraud_rate'] = round(fraud_tx / total_tx * 100, 2) if total_tx else 0

    # Average risk score
    avg_score = (
        db.session.query(func.avg(RiskScore.combined_score))
        .join(Transaction, RiskScore.transaction_id == Transaction.id)
        .filter(Transaction.customer_id == customer.id)
        .scalar()
    )
    result['avg_risk_score'] = round(float(avg_score), 4) if avg_score else 0

    return jsonify(result), 200
