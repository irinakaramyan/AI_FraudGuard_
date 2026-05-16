"""
FraudGuard AI — Application Factory
─────────────────────────────────────
Creates and configures the Flask application with:
  • SQLAlchemy ORM
  • JWT authentication
  • CORS (restricted to configured origins)
  • Security headers on every response
  • RAG assistant (lazy-loaded on first request)
  • APScheduler background jobs (OFAC daily update at 02:00)
  • All API blueprints registered under /api/
"""

import logging
import time
import uuid
from flask import Flask, render_template, jsonify, request, g
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from config import config_map

# ── Shared extension instances ────────────────────────────────────────────────
jwt = JWTManager()

logging.basicConfig(
    level   = logging.INFO,
    format  = '%(asctime)s  %(levelname)-8s  %(name)s — %(message)s',
    datefmt = '%H:%M:%S',
)

_log = logging.getLogger(__name__)


def create_app(config_name: str = 'default') -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_map[config_name])

    # ── Core extensions ───────────────────────────────────────────────────────
    from app.models.models import db
    db.init_app(app)
    jwt.init_app(app)

    # CORS: only allow configured origins (never wildcard in any environment)
    CORS(app, resources={r'/api/*': {
        'origins':        app.config.get('CORS_ORIGINS', ['http://localhost:5000']),
        'methods':        ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
        'allow_headers':  ['Content-Type', 'Authorization'],
        'expose_headers': ['X-Request-ID', 'X-Response-Time'],
        'max_age':        600,
    }})

    # ── Security: request ID + security headers on every response ────────────
    @app.before_request
    def _before():
        g.request_id = str(uuid.uuid4())
        g.start_time = time.perf_counter()

    @app.after_request
    def _after(response):
        response.headers['X-Content-Type-Options']  = 'nosniff'
        response.headers['X-Frame-Options']          = 'DENY'
        response.headers['X-XSS-Protection']         = '1; mode=block'
        response.headers['Referrer-Policy']          = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy']       = 'camera=(), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy']  = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self'; connect-src 'self'; frame-ancestors 'none';"
        )
        response.headers['X-Request-ID'] = getattr(g, 'request_id', '—')
        response.headers.pop('Server', None)
        return response

    # ── Register API Blueprints ────────────────────────────────────────────────
    from app.api.auth         import auth_bp
    from app.api.transactions import transactions_bp
    from app.api.alerts       import alerts_bp
    from app.api.dashboard    import dashboard_bp
    from app.api.customers    import customers_bp
    from app.api.assistant    import assistant_bp
    from app.api.compliance   import compliance_bp
    from app.api.reports      import reports_bp
    from app.api.ingestion    import ingestion_bp
    from app.api.monitoring   import monitoring_bp

    for bp in (auth_bp, transactions_bp, alerts_bp, dashboard_bp,
               customers_bp, assistant_bp, compliance_bp, reports_bp,
               ingestion_bp, monitoring_bp):
        app.register_blueprint(bp)

    # ── Frontend Route ────────────────────────────────────────────────────────
    @app.route('/')
    def index():
        return render_template('index.html')

    # ── Generic error handlers (no stack-trace leakage) ──────────────────────
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({'error': 'Bad request'}), 400

    @app.errorhandler(404)
    def not_found(e):
        # Only return JSON for API paths; render HTML for frontend routes
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Endpoint not found'}), 404
        return render_template('index.html'), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({'error': 'Method not allowed'}), 405

    @app.errorhandler(413)
    def request_too_large(e):
        return jsonify({'error': 'Request body too large (max 2 MB)'}), 413

    @app.errorhandler(500)
    def internal_error(e):
        _log.error('Unhandled 500 error: %s', e, exc_info=True)
        return jsonify({'error': 'An internal error occurred. Please try again.'}), 500

    # ── JWT Error Handlers ────────────────────────────────────────────────────
    @jwt.unauthorized_loader
    def unauthorized_callback(reason):
        return jsonify({'error': 'Authorization required'}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(reason):
        return jsonify({'error': 'Invalid or malformed token'}), 422

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return jsonify({'error': 'Token has expired. Please log in again.'}), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        return jsonify({'error': 'Token has been revoked. Please log in again.'}), 401

    # ── DB migration + startup checks ─────────────────────────────────────────
    with app.app_context():
        _migrate_db()
        _warmup_rag()
        _seed_monitoring()

    # ── Start background scheduler (OFAC daily update, etc.) ─────────────────
    _start_scheduler(app)

    return app


def _migrate_db() -> None:
    """Add new columns to existing tables without dropping data (idempotent)."""
    from app.models.models import db
    from sqlalchemy import text
    log = logging.getLogger(__name__)
    migrations = [
        "ALTER TABLE users ADD COLUMN totp_secret VARCHAR(64) DEFAULT NULL",
        "ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT FALSE",
    ]
    for sql in migrations:
        try:
            db.session.execute(text(sql))
            db.session.commit()
            log.info('DB migration applied: %s', sql[:60])
        except Exception:
            db.session.rollback()  # column already exists — safe to ignore


def _warmup_rag() -> None:
    """Load project documentation into the RAG service and validate AI key."""
    import os
    log = logging.getLogger(__name__)

    # ── Load docs into RAG ────────────────────────────────────────────────────
    try:
        from app.services.rag_service import rag_service
        import pathlib
        # docs/ sits one level above the app/ package directory
        docs_dir = str(pathlib.Path(__file__).parent.parent / 'docs')
        rag_service.load(docs_dir)
        log.info('RAG: ready — %d chunks indexed from docs/', rag_service.chunk_count)
    except Exception as exc:
        log.warning('RAG: failed to load docs — %s', exc)

    # ── AI provider check ─────────────────────────────────────────────────────
    groq_key = os.environ.get('GROQ_API_KEY', '').strip()
    ant_key  = os.environ.get('ANTHROPIC_API_KEY', '').strip()

    if groq_key and groq_key != 'your-groq-api-key-here':
        log.info('AI Assistant: Groq API key detected (model=llama-3.3-70b-versatile, free)')
    elif ant_key and ant_key != 'your-anthropic-api-key-here':
        log.info('AI Assistant: Anthropic API key detected (model=claude-opus-4-6)')
    else:
        log.warning(
            'No AI API key set — AI Assistant will not work. '
            'Add GROQ_API_KEY (free) or ANTHROPIC_API_KEY to your .env file.'
        )


def _seed_monitoring() -> None:
    """
    Pre-populate the in-memory MonitoringService with the last hour of
    transactions from the database so the Live Monitor is not empty on restart.
    Runs once at startup inside the app context — failures are non-fatal.
    """
    from app.models.models import Transaction
    from app.services.monitoring_service import monitoring_service
    from datetime import datetime, timedelta
    log = logging.getLogger(__name__)
    try:
        cutoff = datetime.utcnow() - timedelta(hours=1)
        txs = (Transaction.query
               .filter(Transaction.timestamp >= cutoff)
               .order_by(Transaction.timestamp.asc())
               .all())
        for tx in txs:
            # Mirror the dict shape that fraud_detector.py passes to monitor()
            cust_code = tx.customer.customer_id if tx.customer else str(tx.customer_id)
            tx_data = {
                'customer_id': cust_code,
                'amount':      tx.amount,
                'device_id':   tx.device_id or 'unknown',
                'ip_address':  tx.ip_address or '0.0.0.0',
            }
            # Use the most recent RiskScore row if available
            combined = 0.0
            if tx.risk_scores:
                combined = float(tx.risk_scores[-1].combined_score or 0.0)
            fraud_result = {
                'status':     tx.status or 'approved',
                'risk_score': {'combined_score': combined},
            }
            monitoring_service.monitor(tx_data, fraud_result)
        log.info('Monitoring: seeded %d transaction(s) from the last hour', len(txs))
    except Exception as exc:
        log.warning('Monitoring seed skipped (non-fatal): %s', exc)


def _start_scheduler(app) -> None:
    """Start the APScheduler background scheduler for periodic tasks."""
    try:
        from app.tasks.daily_updater import start_scheduler
        start_scheduler(app)
    except Exception as e:
        logging.getLogger(__name__).warning('Scheduler start skipped: %s', e)
