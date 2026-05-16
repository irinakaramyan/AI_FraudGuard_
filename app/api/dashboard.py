"""
Dashboard API
--------------
GET /api/dashboard/stats           — headline KPI metrics
GET /api/dashboard/trend           — transaction counts per day (last N days)
GET /api/dashboard/risk-dist       — risk score distribution buckets
GET /api/dashboard/alert-types     — alert counts grouped by rule type
GET /api/dashboard/top-alerts      — 10 most recent unresolved alerts
GET /api/dashboard/hourly-heatmap  — transactions per hour (fraud vs. legit)
GET /api/dashboard/rules           — list and manage fraud rules
PUT /api/dashboard/rules/<id>      — update a rule threshold / weight / active state
"""
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import func

from app.models.models import db, Transaction, FraudAlert, Customer, RiskScore, FraudRule
from app.utils.security import admin_required

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')


# ---------------------------------------------------------------------------
# KPI stats
# ---------------------------------------------------------------------------
@dashboard_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_stats():
    total_tx = Transaction.query.count()
    flagged = Transaction.query.filter_by(status='flagged').count()
    blocked = Transaction.query.filter_by(status='blocked').count()
    fraud = Transaction.query.filter_by(is_fraud=True).count()
    approved = Transaction.query.filter_by(status='approved').count()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_tx = Transaction.query.filter(Transaction.timestamp >= today_start).count()
    today_fraud = Transaction.query.filter(
        Transaction.timestamp >= today_start, Transaction.is_fraud == True
    ).count()

    total_alerts = FraudAlert.query.count()
    unresolved = FraudAlert.query.filter_by(is_resolved=False).count()

    total_customers = Customer.query.count()
    high_risk_cust = Customer.query.filter_by(risk_level='high').count()

    total_amount = db.session.query(func.sum(Transaction.amount)).scalar() or 0
    fraud_amount = (
        db.session.query(func.sum(Transaction.amount))
        .filter(Transaction.is_fraud == True)
        .scalar() or 0
    )

    avg_risk = db.session.query(func.avg(RiskScore.combined_score)).scalar() or 0

    return jsonify({
        'transactions': {
            'total': total_tx,
            'today': today_tx,
            'today_fraud': today_fraud,
            'approved': approved,
            'flagged': flagged,
            'blocked': blocked,
            'fraud': fraud,
            'fraud_rate': round(fraud / total_tx * 100, 2) if total_tx else 0,
        },
        'alerts': {
            'total': total_alerts,
            'unresolved': unresolved,
            'resolved': total_alerts - unresolved,
        },
        'customers': {
            'total': total_customers,
            'high_risk': high_risk_cust,
        },
        'financial': {
            'total_amount': round(float(total_amount), 2),
            'fraud_amount': round(float(fraud_amount), 2),
            'avg_risk_score': round(float(avg_risk), 4),
        },
    }), 200


# ---------------------------------------------------------------------------
# Transaction trend (last N days)
# ---------------------------------------------------------------------------
@dashboard_bp.route('/trend', methods=['GET'])
@jwt_required()
def transaction_trend():
    days = max(1, min(request.args.get('days', 7, type=int), 90))
    data = []
    for i in range(days - 1, -1, -1):
        date = (datetime.utcnow() - timedelta(days=i)).date()
        day_start = datetime.combine(date, datetime.min.time())
        day_end = datetime.combine(date, datetime.max.time())

        total = Transaction.query.filter(
            Transaction.timestamp >= day_start,
            Transaction.timestamp <= day_end,
        ).count()
        fraud = Transaction.query.filter(
            Transaction.timestamp >= day_start,
            Transaction.timestamp <= day_end,
            Transaction.is_fraud == True,
        ).count()
        data.append({
            'date': date.strftime('%Y-%m-%d'),
            'label': date.strftime('%b %d'),
            'total': total,
            'fraud': fraud,
            'legitimate': total - fraud,
        })
    return jsonify(data), 200


# ---------------------------------------------------------------------------
# Risk score distribution
# ---------------------------------------------------------------------------
@dashboard_bp.route('/risk-dist', methods=['GET'])
@jwt_required()
def risk_distribution():
    buckets = {
        'low':      RiskScore.query.filter(RiskScore.combined_score < 0.35).count(),
        'medium':   RiskScore.query.filter(
                        RiskScore.combined_score >= 0.35,
                        RiskScore.combined_score < 0.55,
                    ).count(),
        'high':     RiskScore.query.filter(
                        RiskScore.combined_score >= 0.55,
                        RiskScore.combined_score < 0.75,
                    ).count(),
        'critical': RiskScore.query.filter(RiskScore.combined_score >= 0.75).count(),
    }
    return jsonify(buckets), 200


# ---------------------------------------------------------------------------
# Alert type breakdown
# ---------------------------------------------------------------------------
@dashboard_bp.route('/alert-types', methods=['GET'])
@jwt_required()
def alert_types():
    rows = (
        db.session.query(FraudAlert.alert_type, func.count(FraudAlert.id).label('count'))
        .group_by(FraudAlert.alert_type)
        .order_by(func.count(FraudAlert.id).desc())
        .all()
    )
    return jsonify([{'type': r.alert_type or 'UNKNOWN', 'count': r.count} for r in rows]), 200


# ---------------------------------------------------------------------------
# Top 10 unresolved alerts (for dashboard widget)
# ---------------------------------------------------------------------------
@dashboard_bp.route('/top-alerts', methods=['GET'])
@jwt_required()
def top_alerts():
    alerts = (
        FraudAlert.query
        .filter_by(is_resolved=False)
        .order_by(FraudAlert.created_at.desc())
        .limit(10)
        .all()
    )
    result = []
    for a in alerts:
        d = a.to_dict()
        if a.transaction:
            d['transaction'] = {
                'transaction_id': a.transaction.transaction_id,
                'amount': a.transaction.amount,
                'currency': a.transaction.currency,
                'merchant_name': a.transaction.merchant_name,
                'customer_name': a.transaction.customer.name if a.transaction.customer else None,
                'timestamp': a.transaction.timestamp.isoformat(),
            }
        result.append(d)
    return jsonify(result), 200


# ---------------------------------------------------------------------------
# Hourly heatmap (fraud vs. legit per hour of day)
# ---------------------------------------------------------------------------
@dashboard_bp.route('/hourly-heatmap', methods=['GET'])
@jwt_required()
def hourly_heatmap():
    rows = (
        db.session.query(
            func.hour(Transaction.timestamp).label('hour'),
            func.sum(func.if_(Transaction.is_fraud == True, 1, 0)).label('fraud'),
            func.count(Transaction.id).label('total'),
        )
        .group_by(func.hour(Transaction.timestamp))
        .order_by('hour')
        .all()
    )
    data = [
        {
            'hour': r.hour,
            'label': f"{r.hour:02d}:00",
            'total': r.total,
            'fraud': int(r.fraud or 0),
            'legitimate': r.total - int(r.fraud or 0),
        }
        for r in rows
    ]
    return jsonify(data), 200


# ---------------------------------------------------------------------------
# Fraud rules management
# ---------------------------------------------------------------------------
@dashboard_bp.route('/rules', methods=['GET'])
@jwt_required()
def list_rules():
    rules = FraudRule.query.order_by(FraudRule.id).all()
    return jsonify([r.to_dict() for r in rules]), 200


@dashboard_bp.route('/rules/<int:rule_id>', methods=['PUT'])
@admin_required
def update_rule(rule_id):
    rule = FraudRule.query.get_or_404(rule_id)
    data = request.get_json(silent=True) or {}

    if 'threshold' in data and data['threshold'] is not None:
        rule.threshold = float(data['threshold'])
    if 'weight' in data:
        rule.weight = max(0.0, min(float(data['weight']), 1.0))
    if 'is_active' in data:
        rule.is_active = bool(data['is_active'])

    db.session.commit()
    return jsonify({'success': True, 'rule': rule.to_dict()}), 200
