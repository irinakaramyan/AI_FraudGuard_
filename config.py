"""
Application Configuration
--------------------------
Security-hardened configuration for FraudGuard AI.

All sensitive values MUST be set in the .env file.
The application will refuse to start with weak placeholder secrets
when FLASK_ENV=production.
"""
import os
import secrets
from dotenv import load_dotenv

load_dotenv()

_ENV = os.getenv('FLASK_ENV', 'development')


def _require(key: str, fallback: str | None = None) -> str:
    """
    Return env var value.
    In production, raise if missing or using a known-weak placeholder.
    In development, use fallback (but log a warning).
    """
    value = os.getenv(key, fallback)
    weak_placeholders = {
        'ai-fraud-detection-secret-2024',
        'jwt-fraud-secret-2024',
        'change-in-prod',
        'changeme',
        'secret',
    }
    if _ENV == 'production':
        if not value or any(p in (value or '') for p in weak_placeholders):
            raise RuntimeError(
                f"[SECURITY] Environment variable '{key}' is missing or uses a "
                f"weak placeholder. Set a strong random value in .env before "
                f"running in production. Generate one with: "
                f"python -c \"import secrets; print(secrets.token_hex(32))\""
            )
    return value or fallback or ''


class Config:
    # ── Core security ──────────────────────────────────────────────────────────
    SECRET_KEY  = _require('SECRET_KEY',     secrets.token_hex(32))
    JWT_SECRET_KEY = _require('JWT_SECRET_KEY', secrets.token_hex(32))

    # Token expires in 1 hour (was 24 h — reduced attack window)
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', '3600'))

    # ── Cookie hardening ───────────────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY  = True
    SESSION_COOKIE_SAMESITE  = 'Lax'
    SESSION_COOKIE_SECURE    = (_ENV == 'production')   # HTTPS only in prod

    # ── Request size cap — prevents body-based DoS attacks ────────────────────
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024   # 2 MB

    # ── CORS ───────────────────────────────────────────────────────────────────
    # Set CORS_ORIGINS in .env (comma-separated). Default: localhost only.
    CORS_ORIGINS = [
        o.strip()
        for o in os.getenv('CORS_ORIGINS', 'http://localhost:5000,http://127.0.0.1:5000').split(',')
        if o.strip()
    ]

    # ── Database ───────────────────────────────────────────────────────────────
    DB_HOST     = os.getenv('DB_HOST', 'localhost')
    DB_PORT     = os.getenv('DB_PORT', '3306')
    DB_USER     = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_NAME     = os.getenv('DB_NAME', 'fraud_detection_db')

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping':  True,
        'pool_recycle':   300,
        'pool_timeout':   30,
        'pool_size':      10,
        'max_overflow':   20,
    }

    # ── ML paths ───────────────────────────────────────────────────────────────
    ML_MODEL_DIR = os.path.join(os.path.dirname(__file__), 'ml', 'models')

    # ── Fraud detection thresholds ─────────────────────────────────────────────
    HIGH_AMOUNT_THRESHOLD      = float(os.getenv('HIGH_AMOUNT_THRESHOLD', '10000'))
    FREQ_THRESHOLD             = int(os.getenv('FREQ_THRESHOLD', '5'))
    RISK_SCORE_ALERT_THRESHOLD = float(os.getenv('RISK_SCORE_ALERT_THRESHOLD', '0.5'))


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG              = False
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME  = 'https'


config_map = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'default':     DevelopmentConfig,
}
