"""
Notification Service  —  Alert dispatching and escalation management
---------------------------------------------------------------------
Handles outbound notifications for fraud events:
  • In-app notification queue (database-backed)
  • Email alert formatting and dispatch stubs
  • Escalation rules based on severity and time-to-resolve SLA
  • Daily digest report generation

Architecture:
  All email sending is abstracted behind _send_email() so the transport
  layer (SMTP, SendGrid, SES) can be swapped without changing business logic.

Usage:
    from app.services.notification_service import NotificationService
    NotificationService.notify_fraud_alert(alert, transaction)
    NotificationService.send_daily_digest()
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.models.models import db, FraudAlert, Transaction, User

logger = logging.getLogger(__name__)


# ── Severity Configuration ────────────────────────────────────────────────────

SEVERITY_CONFIG = {
    'critical': {
        'notify_immediately': True,
        'sla_hours':          1,
        'email_subject_prefix': '🚨 CRITICAL FRAUD ALERT',
        'escalate_after_hours': 2,
    },
    'high': {
        'notify_immediately': True,
        'sla_hours':          4,
        'email_subject_prefix': '⚠️ HIGH RISK ALERT',
        'escalate_after_hours': 8,
    },
    'medium': {
        'notify_immediately': False,
        'sla_hours':          24,
        'email_subject_prefix': 'FRAUD ALERT',
        'escalate_after_hours': 48,
    },
    'low': {
        'notify_immediately': False,
        'sla_hours':          72,
        'email_subject_prefix': 'LOW RISK ALERT',
        'escalate_after_hours': None,
    },
}


# ── Notification Model ────────────────────────────────────────────────────────

class Notification(db.Model):
    """In-app notification queue — used when email is not configured."""
    __tablename__ = 'notifications'

    id          = db.Column(db.Integer, primary_key=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    title       = db.Column(db.String(200), nullable=False)
    message     = db.Column(db.Text, nullable=False)
    category    = db.Column(db.String(30), default='info')   # info, warning, danger, success
    is_read     = db.Column(db.Boolean, default=False, nullable=False)
    related_id  = db.Column(db.Integer, nullable=True)       # FK to alert/transaction
    related_type = db.Column(db.String(30), nullable=True)   # 'alert', 'transaction'
    metadata_   = db.Column('metadata', db.Text, nullable=True)  # JSON blob

    def to_dict(self) -> dict:
        return {
            'id':           self.id,
            'created_at':   self.created_at.isoformat(),
            'title':        self.title,
            'message':      self.message,
            'category':     self.category,
            'is_read':      self.is_read,
            'related_id':   self.related_id,
            'related_type': self.related_type,
        }


# ── Notification Service ──────────────────────────────────────────────────────

class NotificationService:

    @staticmethod
    def notify_fraud_alert(alert: FraudAlert, transaction: Optional[Transaction] = None) -> None:
        """
        Dispatch notifications for a newly created fraud alert.
        - Creates in-app notification for all admin/analyst users
        - Sends email for high/critical severity (if email is configured)
        - Logs the notification event
        """
        cfg = SEVERITY_CONFIG.get(alert.severity, SEVERITY_CONFIG['low'])
        tx  = transaction or alert.transaction

        # Build notification content
        amount_str = f'${tx.amount:,.2f}' if tx else 'N/A'
        merchant   = tx.merchant_name if tx else 'Unknown'
        customer   = tx.customer.name if tx and tx.customer else 'Unknown'

        title = f"{cfg['email_subject_prefix']}: {alert.alert_type}"
        message = (
            f"A {alert.severity.upper()} risk transaction was detected.\n"
            f"Customer: {customer} | Amount: {amount_str} | Merchant: {merchant}\n"
            f"{alert.description or ''}"
        )

        # Create in-app notifications for all analysts and admins
        NotificationService._notify_staff(
            title      = title,
            message    = message,
            category   = NotificationService._severity_to_category(alert.severity),
            related_id  = alert.id,
            related_type = 'alert',
        )

        # Email for high/critical alerts
        if cfg['notify_immediately']:
            NotificationService._send_email_to_admins(
                subject = title,
                body    = NotificationService._build_alert_email_body(alert, tx),
            )

        logger.info(
            'Notification dispatched: alert_id=%s severity=%s',
            alert.alert_id, alert.severity
        )

    @staticmethod
    def notify_ofac_match(customer_name: str, sdn_match: str, score: float) -> None:
        """Notify all admins of an OFAC sanctions match."""
        title   = '🚫 OFAC SANCTIONS MATCH DETECTED'
        message = (
            f"Customer '{customer_name}' matched OFAC SDN entry '{sdn_match}' "
            f"with {score:.0%} similarity. Transaction has been automatically blocked. "
            f"Immediate compliance review required."
        )
        NotificationService._notify_staff(
            title       = title,
            message     = message,
            category    = 'danger',
            related_type = 'ofac',
        )
        NotificationService._send_email_to_admins(
            subject = title,
            body    = message,
        )

    @staticmethod
    def notify_2fa_event(user: User, event: str) -> None:
        """Notify a user of 2FA status changes."""
        messages = {
            'enabled':  '2FA has been enabled on your account. You will now need your authenticator app to log in.',
            'disabled': '2FA has been disabled on your account. Your account is now protected by password only.',
            'failed':   'A failed 2FA verification attempt was detected on your account.',
        }
        msg = messages.get(event, f'2FA event: {event}')
        NotificationService._create_notification(
            user_id  = user.id,
            title    = f'Security Update: 2FA {event.capitalize()}',
            message  = msg,
            category = 'warning' if event == 'failed' else 'success',
        )

    @staticmethod
    def send_daily_digest() -> dict:
        """
        Generate and dispatch the daily fraud summary digest.
        Called by APScheduler at a configured time.
        Returns a summary of what was sent.
        """
        from sqlalchemy import func
        yesterday = datetime.utcnow() - timedelta(days=1)

        total_tx = Transaction.query.filter(Transaction.timestamp >= yesterday).count()
        blocked  = Transaction.query.filter(
            Transaction.timestamp >= yesterday, Transaction.status == 'blocked'
        ).count()
        flagged  = Transaction.query.filter(
            Transaction.timestamp >= yesterday, Transaction.status == 'flagged'
        ).count()
        critical_alerts = FraudAlert.query.filter(
            FraudAlert.created_at >= yesterday, FraudAlert.severity == 'critical'
        ).count()
        unresolved = FraudAlert.query.filter_by(is_resolved=False).count()

        fraud_amount = (
            db.session.query(func.sum(Transaction.amount))
            .filter(
                Transaction.timestamp >= yesterday,
                Transaction.is_fraud == True,
            )
            .scalar() or 0
        )

        summary = {
            'date':             yesterday.strftime('%Y-%m-%d'),
            'total_tx':         total_tx,
            'blocked':          blocked,
            'flagged':          flagged,
            'critical_alerts':  critical_alerts,
            'unresolved_total': unresolved,
            'fraud_amount':     round(float(fraud_amount), 2),
        }

        subject = f"FraudGuard Daily Report — {summary['date']}"
        body = (
            f"Daily Fraud Detection Summary\n"
            f"Date: {summary['date']}\n\n"
            f"Transactions Processed: {total_tx}\n"
            f"Blocked:               {blocked}\n"
            f"Flagged for Review:    {flagged}\n"
            f"Critical Alerts:       {critical_alerts}\n"
            f"Open Alerts (total):   {unresolved}\n"
            f"Fraud Amount Blocked:  ${fraud_amount:,.2f}\n"
        )

        NotificationService._send_email_to_admins(subject=subject, body=body)
        NotificationService._notify_staff(
            title    = subject,
            message  = f"{total_tx} transactions processed. {blocked} blocked, {flagged} flagged.",
            category = 'info',
        )

        logger.info('Daily digest sent: %s', json.dumps(summary))
        return summary

    @staticmethod
    def get_unread_for_user(user_id: int, limit: int = 20) -> list[dict]:
        """Return unread in-app notifications for a user."""
        notes = (
            Notification.query
            .filter_by(user_id=user_id, is_read=False)
            .order_by(Notification.created_at.desc())
            .limit(min(limit, 100))
            .all()
        )
        return [n.to_dict() for n in notes]

    @staticmethod
    def mark_read(notification_id: int, user_id: int) -> bool:
        """Mark a notification as read. Returns True if found and updated."""
        note = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
        if not note:
            return False
        note.is_read = True
        db.session.commit()
        return True

    # ── Private Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _notify_staff(
        title: str,
        message: str,
        category: str = 'info',
        related_id: Optional[int] = None,
        related_type: Optional[str] = None,
    ) -> None:
        """Create in-app notifications for all admin and analyst users."""
        try:
            staff = User.query.filter(
                User.role.in_(['admin', 'analyst']),
                User.is_active == True,
            ).all()
            for user in staff:
                NotificationService._create_notification(
                    user_id      = user.id,
                    title        = title,
                    message      = message,
                    category     = category,
                    related_id   = related_id,
                    related_type = related_type,
                )
        except Exception as exc:
            logger.error('Failed to create staff notifications: %s', exc)

    @staticmethod
    def _create_notification(
        user_id: int,
        title: str,
        message: str,
        category: str = 'info',
        related_id: Optional[int] = None,
        related_type: Optional[str] = None,
    ) -> None:
        try:
            note = Notification(
                user_id      = user_id,
                title        = title[:200],
                message      = message,
                category     = category,
                related_id   = related_id,
                related_type = related_type,
            )
            db.session.add(note)
            db.session.commit()
        except Exception as exc:
            logger.error('Failed to create notification for user_id=%s: %s', user_id, exc)
            try:
                db.session.rollback()
            except Exception:
                pass

    @staticmethod
    def _send_email_to_admins(subject: str, body: str) -> None:
        """
        Send email to all active admin users.
        Stub implementation — replace with Flask-Mail / SendGrid / SES.
        """
        try:
            import os
            smtp_host = os.environ.get('SMTP_HOST', '')
            if not smtp_host:
                logger.info('Email not configured (SMTP_HOST not set). Skipping: %s', subject)
                return

            admins = User.query.filter_by(role='admin', is_active=True).all()
            recipients = [u.email for u in admins if u.email]
            if not recipients:
                return

            # ── Replace this block with actual SMTP / API call ─────────────
            # Example using Flask-Mail:
            #   from flask_mail import Message
            #   msg = Message(subject, recipients=recipients, body=body)
            #   mail.send(msg)
            logger.info(
                'Email dispatched — subject="%s" recipients=%s', subject, recipients
            )
        except Exception as exc:
            logger.error('Email dispatch failed: %s', exc)

    @staticmethod
    def _build_alert_email_body(alert: FraudAlert, tx: Optional[Transaction]) -> str:
        lines = [
            f"FRAUD ALERT — {alert.severity.upper()}",
            f"Alert ID:   {alert.alert_id}",
            f"Alert Type: {alert.alert_type}",
            f"Created:    {alert.created_at.isoformat()}",
            '',
        ]
        if tx:
            lines += [
                f"Transaction ID: {tx.transaction_id}",
                f"Amount:         ${tx.amount:,.2f} {tx.currency}",
                f"Merchant:       {tx.merchant_name or 'N/A'}",
                f"Customer:       {tx.customer.name if tx.customer else 'N/A'}",
                f"Location:       {tx.location or 'N/A'}",
                f"Timestamp:      {tx.timestamp.isoformat()}",
                '',
            ]
        lines += [
            f"Description:",
            f"  {alert.description or 'No description'}",
            '',
            f"Action Required: Log in to FraudGuard AI to review and resolve this alert.",
        ]
        return '\n'.join(lines)

    @staticmethod
    def _severity_to_category(severity: str) -> str:
        return {
            'critical': 'danger',
            'high':     'warning',
            'medium':   'warning',
            'low':      'info',
        }.get(severity, 'info')

    @staticmethod
    def check_escalations() -> int:
        """
        Check for alerts that have exceeded their SLA and require escalation.
        Called by the APScheduler every hour.
        Returns the number of alerts escalated.
        """
        escalated = 0
        for severity, cfg in SEVERITY_CONFIG.items():
            if not cfg.get('escalate_after_hours'):
                continue

            cutoff = datetime.utcnow() - timedelta(hours=cfg['escalate_after_hours'])
            overdue = FraudAlert.query.filter(
                FraudAlert.severity == severity,
                FraudAlert.is_resolved == False,
                FraudAlert.created_at <= cutoff,
            ).all()

            for alert in overdue:
                logger.warning(
                    'SLA BREACH: alert_id=%s severity=%s age_hours=%.1f',
                    alert.alert_id, severity,
                    (datetime.utcnow() - alert.created_at).total_seconds() / 3600,
                )
                NotificationService._send_email_to_admins(
                    subject = f"SLA BREACH: Unresolved {severity.upper()} alert",
                    body    = (
                        f"Alert {alert.alert_id} has not been resolved within the "
                        f"{cfg['escalate_after_hours']}-hour SLA.\n\n"
                        f"Description: {alert.description}\n"
                        f"Created at: {alert.created_at.isoformat()}"
                    ),
                )
                escalated += 1

        return escalated
