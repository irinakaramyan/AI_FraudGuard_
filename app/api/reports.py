"""
Reports API  —  CSV & JSON export for compliance and audit purposes
--------------------------------------------------------------------
GET  /api/reports/transactions   — export transactions as CSV or JSON
GET  /api/reports/alerts         — export fraud alerts as CSV or JSON
GET  /api/reports/risk-summary   — risk score summary report
GET  /api/reports/compliance     — AML compliance metrics report
GET  /api/reports/customer/<id>  — full customer risk report

All endpoints require JWT authentication.
Admin-only exports are restricted via @admin_required.

Security controls:
  • Date range capped at 365 days to prevent memory exhaustion
  • Row limit capped at 10,000 per export
  • CSV output escapes formula injection (cells starting with =, +, -, @)
  • All string inputs sanitised via safe_str()
"""
import csv
import io
import logging
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import jwt_required

from app.models.models import (
    db, Transaction, FraudAlert, Customer, RiskScore,
)
from app.utils.security import safe_str, safe_int, admin_required

logger = logging.getLogger(__name__)

reports_bp = Blueprint('reports', __name__, url_prefix='/api/reports')

_MAX_ROWS       = 10_000
_MAX_DATE_RANGE = 365   # days


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sanitise_csv_cell(value) -> str:
    """Prevent CSV formula injection (Excel / Google Sheets attack vector)."""
    s = str(value) if value is not None else ''
    if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
        s = "'" + s   # prefix with single-quote to neutralise
    return s


def _csv_response(rows: list[dict], filename: str) -> Response:
    """Stream a list of dicts as a CSV download response."""
    if not rows:
        return jsonify({'error': 'No data found for the selected filters'}), 404

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys(), lineterminator='\r\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _sanitise_csv_cell(v) for k, v in row.items()})

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'X-Content-Type-Options': 'nosniff',
        },
    )


def _parse_date_range(request_args: dict) -> tuple[datetime, datetime]:
    """
    Parse start_date / end_date from query params.
    Defaults: last 30 days.
    Enforces maximum range of _MAX_DATE_RANGE days.
    """
    now = datetime.utcnow()
    try:
        start = datetime.fromisoformat(request_args.get('start_date', ''))
    except ValueError:
        start = now - timedelta(days=30)
    try:
        end = datetime.fromisoformat(request_args.get('end_date', ''))
    except ValueError:
        end = now

    if end < start:
        start, end = end, start

    if (end - start).days > _MAX_DATE_RANGE:
        start = end - timedelta(days=_MAX_DATE_RANGE)

    return start, end


# ── GET /api/reports/transactions ─────────────────────────────────────────────
@reports_bp.route('/transactions', methods=['GET'])
@jwt_required()
def export_transactions():
    """Export filtered transactions as CSV or JSON."""
    fmt        = safe_str(request.args.get('format', 'csv'), max_length=4).lower()
    status     = safe_str(request.args.get('status', ''),   max_length=20)
    risk_level = safe_str(request.args.get('risk_level', ''), max_length=20)
    start, end = _parse_date_range(request.args)

    query = (
        Transaction.query
        .filter(Transaction.timestamp >= start, Transaction.timestamp <= end)
        .order_by(Transaction.timestamp.desc())
        .limit(_MAX_ROWS)
    )
    if status in ('approved', 'flagged', 'blocked', 'pending'):
        query = query.filter(Transaction.status == status)

    transactions = query.all()

    rows = []
    for t in transactions:
        rs = RiskScore.query.filter_by(transaction_id=t.id).first()
        rows.append({
            'transaction_id':    t.transaction_id,
            'timestamp':         t.timestamp.isoformat(),
            'customer_name':     t.customer.name if t.customer else '',
            'customer_code':     t.customer.customer_id if t.customer else '',
            'amount':            round(t.amount, 2),
            'currency':          t.currency,
            'merchant_name':     t.merchant_name or '',
            'merchant_category': t.merchant_category or '',
            'location':          t.location or '',
            'card_type':         t.card_type or '',
            'transaction_type':  t.transaction_type or '',
            'status':            t.status,
            'is_fraud':          t.is_fraud,
            'rule_score':        round(rs.rule_score, 4) if rs else '',
            'ml_score':          round(rs.ml_score, 4) if rs else '',
            'combined_score':    round(rs.combined_score, 4) if rs else '',
            'risk_level':        rs.risk_level if rs else '',
        })

    if not rows:
        return jsonify({'error': 'No transactions found for the selected filters'}), 404

    if fmt == 'json':
        return jsonify({'count': len(rows), 'transactions': rows}), 200

    fname = f"transactions_{start.date()}_{end.date()}.csv"
    logger.info('Transaction export: %d rows, format=%s', len(rows), fmt)
    return _csv_response(rows, fname)


# ── GET /api/reports/alerts ───────────────────────────────────────────────────
@reports_bp.route('/alerts', methods=['GET'])
@jwt_required()
def export_alerts():
    """Export fraud alerts as CSV or JSON."""
    fmt        = safe_str(request.args.get('format', 'csv'), max_length=4).lower()
    severity   = safe_str(request.args.get('severity', ''), max_length=10)
    resolved   = request.args.get('resolved', '')
    start, end = _parse_date_range(request.args)

    query = (
        FraudAlert.query
        .filter(FraudAlert.created_at >= start, FraudAlert.created_at <= end)
        .order_by(FraudAlert.created_at.desc())
        .limit(_MAX_ROWS)
    )
    if severity in ('low', 'medium', 'high', 'critical'):
        query = query.filter(FraudAlert.severity == severity)
    if resolved == 'true':
        query = query.filter(FraudAlert.is_resolved == True)
    elif resolved == 'false':
        query = query.filter(FraudAlert.is_resolved == False)

    alerts = query.all()
    rows = []
    for a in alerts:
        tx = a.transaction
        rows.append({
            'alert_id':       a.alert_id,
            'created_at':     a.created_at.isoformat(),
            'alert_type':     a.alert_type or '',
            'severity':       a.severity,
            'description':    a.description or '',
            'is_resolved':    a.is_resolved,
            'resolved_at':    a.resolved_at.isoformat() if a.resolved_at else '',
            'transaction_id': tx.transaction_id if tx else '',
            'amount':         round(tx.amount, 2) if tx else '',
            'merchant':       tx.merchant_name if tx else '',
            'customer':       tx.customer.name if tx and tx.customer else '',
        })

    if not rows:
        return jsonify({'error': 'No alerts found for the selected filters'}), 404

    if fmt == 'json':
        return jsonify({'count': len(rows), 'alerts': rows}), 200

    fname = f"fraud_alerts_{start.date()}_{end.date()}.csv"
    logger.info('Alert export: %d rows, format=%s', len(rows), fmt)
    return _csv_response(rows, fname)


# ── GET /api/reports/risk-summary ─────────────────────────────────────────────
@reports_bp.route('/risk-summary', methods=['GET'])
@jwt_required()
def risk_summary():
    """Aggregated risk score statistics for a date range."""
    from sqlalchemy import func
    start, end = _parse_date_range(request.args)

    scores = (
        db.session.query(
            func.count(RiskScore.id).label('total'),
            func.avg(RiskScore.combined_score).label('avg_score'),
            func.max(RiskScore.combined_score).label('max_score'),
            func.min(RiskScore.combined_score).label('min_score'),
            func.avg(RiskScore.rule_score).label('avg_rule'),
            func.avg(RiskScore.ml_score).label('avg_ml'),
        )
        .join(Transaction, RiskScore.transaction_id == Transaction.id)
        .filter(Transaction.timestamp >= start, Transaction.timestamp <= end)
        .first()
    )

    distribution = {
        level: RiskScore.query
        .join(Transaction, RiskScore.transaction_id == Transaction.id)
        .filter(
            Transaction.timestamp >= start,
            Transaction.timestamp <= end,
            RiskScore.risk_level == level,
        ).count()
        for level in ('low', 'medium', 'high', 'critical')
    }

    return jsonify({
        'period':       {'start': start.isoformat(), 'end': end.isoformat()},
        'totals':       {'scored_transactions': scores.total or 0},
        'scores': {
            'average_combined': round(float(scores.avg_score or 0), 4),
            'average_rule':     round(float(scores.avg_rule  or 0), 4),
            'average_ml':       round(float(scores.avg_ml    or 0), 4),
            'max_combined':     round(float(scores.max_score or 0), 4),
            'min_combined':     round(float(scores.min_score or 0), 4),
        },
        'distribution': distribution,
    }), 200


# ── GET /api/reports/compliance ───────────────────────────────────────────────
@reports_bp.route('/compliance', methods=['GET'])
@admin_required
def compliance_report():
    """
    AML / regulatory compliance metrics report.
    Includes CTR threshold breaches, high-risk customer stats,
    OFAC flagged accounts, and SAR-relevant transaction volumes.
    """
    from sqlalchemy import func
    start, end = _parse_date_range(request.args)

    # Transactions over $10,000 (CTR threshold — FinCEN requirement)
    ctr_threshold = 10_000
    ctr_count = Transaction.query.filter(
        Transaction.timestamp >= start,
        Transaction.timestamp <= end,
        Transaction.amount >= ctr_threshold,
    ).count()

    ctr_amount = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.timestamp >= start,
        Transaction.timestamp <= end,
        Transaction.amount >= ctr_threshold,
    ).scalar() or 0

    # OFAC-flagged customers
    ofac_count = Customer.query.filter_by(is_ofac_sanctioned=True).count()

    # High-risk customer breakdown
    risk_dist = {
        level: Customer.query.filter_by(risk_level=level).count()
        for level in ('low', 'medium', 'high')
    }

    # Fraud blocked/flagged in period
    blocked = Transaction.query.filter(
        Transaction.timestamp >= start,
        Transaction.timestamp <= end,
        Transaction.status == 'blocked',
    ).count()

    flagged = Transaction.query.filter(
        Transaction.timestamp >= start,
        Transaction.timestamp <= end,
        Transaction.status == 'flagged',
    ).count()

    # Critical alerts in period (potential SAR triggers)
    critical_alerts = FraudAlert.query.filter(
        FraudAlert.created_at >= start,
        FraudAlert.created_at <= end,
        FraudAlert.severity == 'critical',
    ).count()

    return jsonify({
        'report_period':     {'start': start.isoformat(), 'end': end.isoformat()},
        'generated_at':      datetime.utcnow().isoformat(),
        'ctr_reporting': {
            'threshold':          ctr_threshold,
            'transactions_count': ctr_count,
            'total_amount':       round(float(ctr_amount), 2),
            'note':               'Transactions at or above $10,000 may require CTR filing under FinCEN rules.',
        },
        'ofac_screening': {
            'flagged_customers':  ofac_count,
            'note':               'Customers matched against US Treasury SDN list.',
        },
        'customer_risk': {
            'distribution':       risk_dist,
            'total':              sum(risk_dist.values()),
        },
        'fraud_actions': {
            'blocked':            blocked,
            'flagged':            flagged,
            'critical_alerts':    critical_alerts,
            'sar_candidates':     critical_alerts,
            'note':               'Critical alerts may meet the $5,000 threshold for SAR filing under FinCEN guidance.',
        },
    }), 200


# ── GET /api/reports/customer/<id> ────────────────────────────────────────────
@reports_bp.route('/customer/<int:customer_id>', methods=['GET'])
@jwt_required()
def customer_report(customer_id):
    """Full risk report for a single customer."""
    from sqlalchemy import func
    customer = Customer.query.get_or_404(customer_id)

    transactions = (
        Transaction.query
        .filter_by(customer_id=customer.id)
        .order_by(Transaction.timestamp.desc())
        .limit(100)
        .all()
    )

    tx_stats = db.session.query(
        func.count(Transaction.id).label('total'),
        func.sum(Transaction.amount).label('total_amount'),
        func.avg(Transaction.amount).label('avg_amount'),
        func.max(Transaction.amount).label('max_amount'),
        func.sum(db.cast(Transaction.is_fraud, db.Integer)).label('fraud_count'),
    ).filter(Transaction.customer_id == customer.id).first()

    alert_count = (
        FraudAlert.query
        .join(Transaction, FraudAlert.transaction_id == Transaction.id)
        .filter(Transaction.customer_id == customer.id)
        .count()
    )

    avg_risk = (
        db.session.query(func.avg(RiskScore.combined_score))
        .join(Transaction, RiskScore.transaction_id == Transaction.id)
        .filter(Transaction.customer_id == customer.id)
        .scalar() or 0
    )

    return jsonify({
        'customer':  customer.to_dict(),
        'statistics': {
            'total_transactions': tx_stats.total or 0,
            'total_amount':       round(float(tx_stats.total_amount or 0), 2),
            'average_amount':     round(float(tx_stats.avg_amount  or 0), 2),
            'max_amount':         round(float(tx_stats.max_amount  or 0), 2),
            'fraud_count':        int(tx_stats.fraud_count or 0),
            'fraud_rate':         round(int(tx_stats.fraud_count or 0) / max(tx_stats.total or 1, 1) * 100, 2),
            'total_alerts':       alert_count,
            'average_risk_score': round(float(avg_risk), 4),
        },
        'recent_transactions': [t.to_dict() for t in transactions[:20]],
        'generated_at': datetime.utcnow().isoformat(),
    }), 200
