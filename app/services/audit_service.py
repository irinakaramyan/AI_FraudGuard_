"""
Audit Service  —  Immutable audit trail for all system actions
--------------------------------------------------------------
Every significant action in the system (login, transaction submit,
alert resolution, rule change, 2FA event, OFAC refresh, export)
is logged to an append-only audit table.

The AuditLog model uses created_at with no update path — records
are never modified or deleted (compliant with SOC 2 / ISO 27001).

Usage:
    from app.services.audit_service import AuditService
    AuditService.log(action='LOGIN_SUCCESS', user_id=1, details={'ip': '...'})
"""
import json
import logging
from datetime import datetime, timedelta
from enum import Enum

from flask import request as flask_request
from sqlalchemy import func

from app.models.models import db

logger = logging.getLogger(__name__)


# ── Audit Action Constants ─────────────────────────────────────────────────────

class AuditAction(str, Enum):
    # Authentication
    LOGIN_SUCCESS       = 'LOGIN_SUCCESS'
    LOGIN_FAILED        = 'LOGIN_FAILED'
    LOGIN_LOCKED        = 'LOGIN_LOCKED'
    LOGOUT              = 'LOGOUT'
    TOKEN_EXPIRED       = 'TOKEN_EXPIRED'

    # Two-Factor Authentication
    TOTP_SETUP          = 'TOTP_SETUP'
    TOTP_ENABLED        = 'TOTP_ENABLED'
    TOTP_DISABLED       = 'TOTP_DISABLED'
    TOTP_VERIFY_SUCCESS = 'TOTP_VERIFY_SUCCESS'
    TOTP_VERIFY_FAILED  = 'TOTP_VERIFY_FAILED'

    # Transactions
    TRANSACTION_SUBMITTED = 'TRANSACTION_SUBMITTED'
    TRANSACTION_BLOCKED   = 'TRANSACTION_BLOCKED'
    TRANSACTION_FLAGGED   = 'TRANSACTION_FLAGGED'
    TRANSACTION_APPROVED  = 'TRANSACTION_APPROVED'
    TRANSACTION_REVIEWED  = 'TRANSACTION_REVIEWED'

    # Alerts
    ALERT_CREATED   = 'ALERT_CREATED'
    ALERT_RESOLVED  = 'ALERT_RESOLVED'

    # User Management
    USER_CREATED    = 'USER_CREATED'
    USER_UPDATED    = 'USER_UPDATED'
    USER_DEACTIVATED = 'USER_DEACTIVATED'

    # Rules
    RULE_UPDATED    = 'RULE_UPDATED'
    RULE_TOGGLED    = 'RULE_TOGGLED'

    # OFAC
    OFAC_REFRESH_STARTED   = 'OFAC_REFRESH_STARTED'
    OFAC_REFRESH_SUCCESS   = 'OFAC_REFRESH_SUCCESS'
    OFAC_REFRESH_FAILED    = 'OFAC_REFRESH_FAILED'
    OFAC_MATCH_FOUND       = 'OFAC_MATCH_FOUND'

    # Exports / Reports
    REPORT_EXPORTED = 'REPORT_EXPORTED'


# ── Audit Log SQLAlchemy Model ─────────────────────────────────────────────────

class AuditLog(db.Model):
    """
    Append-only audit log table.
    Never update or delete rows — only insert.
    """
    __tablename__ = 'audit_logs'

    id         = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    action     = db.Column(db.String(60),  nullable=False, index=True)
    user_id    = db.Column(db.Integer,     nullable=True,  index=True)
    username   = db.Column(db.String(80),  nullable=True)
    ip_address = db.Column(db.String(45),  nullable=True)
    resource   = db.Column(db.String(120), nullable=True)   # e.g. "transaction:abc-123"
    details    = db.Column(db.Text,        nullable=True)   # JSON blob
    success    = db.Column(db.Boolean,     default=True, nullable=False)

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'created_at': self.created_at.isoformat(),
            'action':     self.action,
            'user_id':    self.user_id,
            'username':   self.username,
            'ip_address': self.ip_address,
            'resource':   self.resource,
            'details':    json.loads(self.details) if self.details else {},
            'success':    self.success,
        }


# ── Audit Service ──────────────────────────────────────────────────────────────

class AuditService:
    """
    Static helper that writes AuditLog entries.
    Designed to be called anywhere within a Flask request context.
    Failures are logged but never re-raised (audit must not break main flow).
    """

    @staticmethod
    def log(
        action:   str | AuditAction,
        user_id:  int  | None = None,
        username: str  | None = None,
        resource: str  | None = None,
        details:  dict | None = None,
        success:  bool        = True,
        ip:       str  | None = None,
    ) -> None:
        """
        Write one audit record.

        Parameters
        ----------
        action   : AuditAction constant or free-form string
        user_id  : authenticated user performing the action (None for system)
        username : username string (de-normalised for fast querying)
        resource : target of the action, e.g. 'transaction:abc-123'
        details  : arbitrary dict of extra context (stored as JSON)
        success  : True if the action completed successfully
        ip       : source IP — auto-detected from Flask request if omitted
        """
        try:
            # Auto-detect IP from Flask request context if available
            if ip is None:
                try:
                    ip = flask_request.remote_addr
                except RuntimeError:
                    ip = None   # called outside request context (e.g. scheduler)

            entry = AuditLog(
                action     = str(action),
                user_id    = user_id,
                username   = username,
                ip_address = ip,
                resource   = resource,
                details    = json.dumps(details) if details else None,
                success    = success,
            )
            db.session.add(entry)
            db.session.commit()

        except Exception as exc:
            # Never let audit failure break the main request
            logger.error('AuditService.log failed: %s', exc, exc_info=True)
            try:
                db.session.rollback()
            except Exception:
                pass

    @staticmethod
    def get_recent(limit: int = 100) -> list[dict]:
        """Return the most recent audit entries."""
        entries = (
            AuditLog.query
            .order_by(AuditLog.created_at.desc())
            .limit(min(limit, 500))
            .all()
        )
        return [e.to_dict() for e in entries]

    @staticmethod
    def get_by_user(user_id: int, limit: int = 50) -> list[dict]:
        """Return recent audit entries for a specific user."""
        entries = (
            AuditLog.query
            .filter_by(user_id=user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(min(limit, 200))
            .all()
        )
        return [e.to_dict() for e in entries]

    @staticmethod
    def get_by_action(action: str, days: int = 7) -> list[dict]:
        """Return audit entries matching a specific action within the last N days."""
        since = datetime.utcnow() - timedelta(days=min(days, 90))
        entries = (
            AuditLog.query
            .filter(AuditLog.action == action, AuditLog.created_at >= since)
            .order_by(AuditLog.created_at.desc())
            .limit(500)
            .all()
        )
        return [e.to_dict() for e in entries]

    @staticmethod
    def security_summary(days: int = 7) -> dict:
        """
        Aggregate security-relevant audit counts for a dashboard widget.
        Returns counts of login failures, lockouts, 2FA events, etc.
        """
        since = datetime.utcnow() - timedelta(days=min(days, 90))

        def _count(action_val: str) -> int:
            return (
                AuditLog.query
                .filter(AuditLog.action == action_val, AuditLog.created_at >= since)
                .count()
            )

        return {
            'period_days':          days,
            'login_success':        _count(AuditAction.LOGIN_SUCCESS),
            'login_failed':         _count(AuditAction.LOGIN_FAILED),
            'login_locked':         _count(AuditAction.LOGIN_LOCKED),
            'totp_verify_failed':   _count(AuditAction.TOTP_VERIFY_FAILED),
            'totp_enabled':         _count(AuditAction.TOTP_ENABLED),
            'transactions_blocked': _count(AuditAction.TRANSACTION_BLOCKED),
            'alerts_resolved':      _count(AuditAction.ALERT_RESOLVED),
            'reports_exported':     _count(AuditAction.REPORT_EXPORTED),
            'ofac_matches':         _count(AuditAction.OFAC_MATCH_FOUND),
        }
