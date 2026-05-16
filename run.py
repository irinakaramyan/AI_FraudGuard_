"""
Application Entry Point
------------------------
Run:  python run.py

Environment variables (set in .env):
  FLASK_ENV   — 'development' (default) or 'production'
  PORT        — port to listen on (default 5000)
  HOST        — host to bind to (default 127.0.0.1)
"""
import os
import logging
from app import create_app

log = logging.getLogger(__name__)

config_name = os.getenv('FLASK_ENV', 'development')
app = create_app(config_name)

if __name__ == '__main__':
    debug = config_name == 'development'
    host  = os.getenv('HOST', '127.0.0.1')   # bind localhost by default (not 0.0.0.0)
    port  = int(os.getenv('PORT', '5000'))

    print("=" * 55)
    print("  FraudGuard AI — Fraud Detection System")
    print(f"  http://{host}:{port}")
    print(f"  Environment : {config_name}")
    print(f"  Debug mode  : {debug}")
    print("=" * 55)

    if debug:
        log.warning("Running in DEVELOPMENT mode — not for production use")

    app.run(
        host        = host,
        port        = port,
        debug       = debug,
        use_reloader= debug,
    )
