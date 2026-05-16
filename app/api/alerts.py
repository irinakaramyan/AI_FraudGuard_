"""
Fraud Alerts API
-----------------
GET /api/alerts              — paginated list with optional filters
GET /api/alerts/<id>         — single alert detail (includes transaction)
PUT /api/alerts/<id>/resolve — resolve an alert
GET /api/alerts/summary      — counts by severity and resolution status
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from app.models.models import db, FraudAlert

alerts_bp = Blueprint('alerts', __name__, url_prefix='/api/alerts')


@alerts_bp.route('', methods=['GET'])
@jwt_required()
def list_alerts():
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    severity = request.args.get('severity')
    is_resolved = request.args.get('is_resolved')
    alert_type = request.args.get('alert_type')

    query = FraudAlert.query

    if severity:
        query = query.filter(FraudAlert.severity == severity)
    if alert_type:
        query = query.filter(FraudAlert.alert_type == alert_type)
    if is_resolved is not None:
        resolved_flag = is_resolved.lower() in ('true', '1', 'yes')
        query = query.filter(FraudAlert.is_resolved == resolved_flag)

    query = query.order_by(FraudAlert.created_at.desc())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'alerts': [a.to_dict() for a in paginated.items],
        'total': paginated.total,
        'pages': paginated.pages,
        'current_page': page,
    }), 200


@alerts_bp.route('/summary', methods=['GET'])
@jwt_required()
def alert_summary():
    total = FraudAlert.query.count()
    unresolved = FraudAlert.query.filter_by(is_resolved=False).count()

    by_severity = {}
    for sev in ('critical', 'high', 'medium', 'low'):
        by_severity[sev] = FraudAlert.query.filter_by(severity=sev).count()

    by_type = {}
    from sqlalchemy import func
    rows = (
        db.session.query(FraudAlert.alert_type, func.count(FraudAlert.id))
        .group_by(FraudAlert.alert_type)
        .all()
    )
    for alert_type, count in rows:
        by_type[alert_type or 'UNKNOWN'] = count

    return jsonify({
        'total': total,
        'unresolved': unresolved,
        'resolved': total - unresolved,
        'by_severity': by_severity,
        'by_type': by_type,
    }), 200


@alerts_bp.route('/<int:alert_id>', methods=['GET'])
@jwt_required()
def get_alert(alert_id):
    alert = FraudAlert.query.get_or_404(alert_id)
    result = alert.to_dict()

    if alert.transaction:
        t = alert.transaction
        result['transaction'] = t.to_dict()
        # Include risk score
        from app.models.models import RiskScore
        rs = RiskScore.query.filter_by(transaction_id=t.id).first()
        if rs:
            result['risk_score'] = rs.to_dict()

    return jsonify(result), 200


@alerts_bp.route('/<int:alert_id>/resolve', methods=['PUT'])
@jwt_required()
def resolve_alert(alert_id):
    alert = FraudAlert.query.get_or_404(alert_id)
    if alert.is_resolved:
        return jsonify({'error': 'Alert is already resolved'}), 409

    data = request.get_json(silent=True) or {}
    user_id = int(get_jwt_identity())

    alert.is_resolved = True
    alert.resolved_by = user_id
    alert.resolved_at = datetime.utcnow()
    alert.resolution_notes = data.get('notes', '').strip()

    db.session.commit()
    return jsonify({'success': True, 'alert': alert.to_dict()}), 200
