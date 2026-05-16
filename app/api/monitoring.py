"""
Real-Time Transaction Monitoring API
═════════════════════════════════════
Routes
──────
GET  /api/monitor/realtime          Current streaming analytics snapshot
GET  /api/monitor/stream            Server-Sent Events live feed (SSE)
GET  /api/monitor/events            Recent monitoring events (last N)
GET  /api/monitor/network           Network analysis (device/IP sharing)
GET  /api/monitor/thresholds        Active threshold configuration
PUT  /api/monitor/thresholds        Update thresholds (admin only)
GET  /api/monitor/customer/<id>     Per-customer real-time velocity stats
POST /api/monitor/reset             Reset in-memory windows (admin, testing)
"""

import json
import logging
import time

from flask import Blueprint, request, jsonify, Response, stream_with_context
from flask_jwt_extended import jwt_required

from app.services.monitoring_service import monitoring_service
from app.utils.security import admin_required, safe_int, safe_str

logger = logging.getLogger(__name__)

monitoring_bp = Blueprint('monitoring', __name__, url_prefix='/api/monitor')


# ── GET /api/monitor/realtime ─────────────────────────────────────────────────
@monitoring_bp.route('/realtime', methods=['GET'])
@jwt_required()
def realtime_stats():
    """
    Polling endpoint: returns a full snapshot of real-time monitoring metrics.
    Suitable as a fallback when SSE is not available.
    """
    return jsonify(monitoring_service.get_realtime_stats()), 200


# ── GET /api/monitor/stream (Server-Sent Events) ──────────────────────────────
@monitoring_bp.route('/stream', methods=['GET'])
@jwt_required()
def event_stream():
    """
    SSE (Server-Sent Events) endpoint — pushes real-time monitoring snapshots
    to the browser every 3 seconds.  No polling needed on the client side.

    The browser connects once; updates arrive as a continuous stream.
    Each event is a JSON snapshot of current system metrics.

    Client usage:
        const es = new EventSource('/api/monitor/stream?token=<jwt>');
        es.onmessage = e => { const data = JSON.parse(e.data); ... };
    """
    interval = safe_int(request.args.get('interval', 3), min_val=1, max_val=30, default=3)

    @stream_with_context
    def generate():
        # Send initial connection event
        yield f'event: connected\ndata: {{"status":"connected","interval":{interval}}}\n\n'

        tick = 0
        while True:
            try:
                snapshot = monitoring_service.get_realtime_stats()
                snapshot['tick'] = tick
                payload = json.dumps(snapshot, default=str)
                yield f'data: {payload}\n\n'
                tick += 1
                time.sleep(interval)
            except GeneratorExit:
                break
            except Exception as exc:
                logger.warning('SSE stream error: %s', exc)
                yield f'event: error\ndata: {{"error":"{exc}"}}\n\n'
                break

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control':     'no-cache',
            'X-Accel-Buffering': 'no',        # disable Nginx buffering
            'Connection':        'keep-alive',
        }
    )


# ── GET /api/monitor/events ───────────────────────────────────────────────────
@monitoring_bp.route('/events', methods=['GET'])
@jwt_required()
def recent_events():
    """Return the most recent N monitoring events from the in-memory feed."""
    limit = safe_int(request.args.get('limit', 50), min_val=1, max_val=200, default=50)
    events = monitoring_service.get_recent_events(limit=limit)
    return jsonify({
        'count':  len(events),
        'events': list(reversed(events)),   # newest first
    }), 200


# ── GET /api/monitor/network ──────────────────────────────────────────────────
@monitoring_bp.route('/network', methods=['GET'])
@jwt_required()
def network_analysis():
    """
    Network-level fraud ring detection.
    Shows devices and IP addresses shared across multiple customer accounts.
    """
    stats = monitoring_service.get_realtime_stats()
    return jsonify({
        'network_summary': stats.get('network', {}),
        'description': {
            'shared_devices': 'Devices used by more than one customer account — possible account takeover or fraud ring',
            'shared_ips':     'IP addresses used by multiple customers — possible proxy, VPN, or coordinated attack',
        },
        'thresholds': {
            'max_customers_per_device': monitoring_service.get_thresholds()['max_customers_per_device'],
            'max_customers_per_ip':     monitoring_service.get_thresholds()['max_customers_per_ip'],
        }
    }), 200


# ── GET /api/monitor/thresholds ───────────────────────────────────────────────
@monitoring_bp.route('/thresholds', methods=['GET'])
@jwt_required()
def get_thresholds():
    """Return the active threshold configuration with descriptions."""
    th = monitoring_service.get_thresholds()
    described = {
        'score_thresholds': {
            'auto_block_score':     {'value': th['auto_block_score'],     'description': 'Combined score ≥ this → automatic block'},
            'auto_flag_score':      {'value': th['auto_flag_score'],      'description': 'Combined score ≥ this → flagged for review'},
            'critical_alert_score': {'value': th['critical_alert_score'], 'description': 'Generate CRITICAL alert'},
        },
        'velocity_thresholds': {
            'max_tx_per_minute':    {'value': th['max_tx_per_minute'],    'description': 'Max transactions per minute (per customer)'},
            'max_tx_per_5min':      {'value': th['max_tx_per_5min'],      'description': 'Max transactions in 5 minutes (per customer)'},
            'max_tx_per_hour':      {'value': th['max_tx_per_hour'],      'description': 'Max transactions per hour (per customer)'},
            'max_amount_per_hour':  {'value': th['max_amount_per_hour'],  'description': 'Max total spend per hour in USD (per customer)'},
            'single_tx_alert':      {'value': th['single_tx_alert'],      'description': 'Single transaction value that triggers an alert'},
        },
        'network_thresholds': {
            'max_customers_per_device': {'value': th['max_customers_per_device'], 'description': 'Max unique customers sharing one device before ring alert'},
            'max_customers_per_ip':     {'value': th['max_customers_per_ip'],     'description': 'Max unique customers from one IP before clustering alert'},
        },
        'system_thresholds': {
            'system_block_rate_warn': {'value': th['system_block_rate_warn'], 'description': 'System-wide block rate that triggers an ops alert'},
            'system_tx_rate_warn':    {'value': th['system_tx_rate_warn'],    'description': 'Transactions per minute that triggers a capacity alert'},
        },
    }
    return jsonify(described), 200


# ── PUT /api/monitor/thresholds (admin only) ──────────────────────────────────
@monitoring_bp.route('/thresholds', methods=['PUT'])
@admin_required
def update_thresholds():
    """
    Update one or more threshold values at runtime — no restart required.
    Only recognised threshold keys are accepted.

    Example body:
        { "auto_block_score": 0.80, "max_tx_per_minute": 8 }
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'error': 'Request body must be a JSON object'}), 400

    changed = monitoring_service.update_thresholds(data)
    if not changed:
        return jsonify({'error': 'No recognised threshold keys in request'}), 400

    return jsonify({
        'updated': changed,
        'current': monitoring_service.get_thresholds(),
    }), 200


# ── GET /api/monitor/customer/<id> ────────────────────────────────────────────
@monitoring_bp.route('/customer/<customer_id>', methods=['GET'])
@jwt_required()
def customer_velocity(customer_id):
    """
    Return real-time velocity stats for a specific customer.
    Pulls from sliding window counters and the DB for historical context.
    """
    cid = safe_str(customer_id, max_length=20)

    # Live in-memory windows
    windows = monitoring_service._get_or_create_windows(cid)
    live = {
        'tx_last_1min':    windows['count_1min'].count(),
        'tx_last_5min':    windows['count_5min'].count(),
        'tx_last_1hr':     windows['count_1hr'].count(),
        'amount_last_1hr': round(windows['amount_1hr'].total(), 2),
        'rate_per_min':    windows['count_1min'].rate_per_minute(),
    }

    # Threshold comparison
    th = monitoring_service.get_thresholds()
    alerts = []
    if live['tx_last_1min']  > th['max_tx_per_minute']:
        alerts.append(f"Burst rate: {live['tx_last_1min']}/min (limit {th['max_tx_per_minute']})")
    if live['tx_last_5min']  > th['max_tx_per_5min']:
        alerts.append(f"5-min velocity: {live['tx_last_5min']} (limit {th['max_tx_per_5min']})")
    if live['tx_last_1hr']   > th['max_tx_per_hour']:
        alerts.append(f"Hourly velocity: {live['tx_last_1hr']} (limit {th['max_tx_per_hour']})")
    if live['amount_last_1hr'] > th['max_amount_per_hour']:
        alerts.append(f"Hourly spend: ${live['amount_last_1hr']:,.2f} (limit ${th['max_amount_per_hour']:,.0f})")

    return jsonify({
        'customer_id':  cid,
        'live_velocity': live,
        'threshold_alerts': alerts,
        'status': 'alert' if alerts else 'normal',
    }), 200


# ── POST /api/monitor/reset (admin only) ─────────────────────────────────────
@monitoring_bp.route('/reset', methods=['POST'])
@admin_required
def reset_windows():
    """
    Reset all in-memory sliding windows and network graph.
    Use only in testing/staging — production data will be lost.
    """
    from app.services.monitoring_service import MonitoringService
    global monitoring_service
    from app.services import monitoring_service as ms_module
    ms_module.monitoring_service.__init__()
    return jsonify({'status': 'reset', 'message': 'All monitoring windows cleared'}), 200
