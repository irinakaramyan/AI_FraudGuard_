from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import json

db = SQLAlchemy()


class User(db.Model):
    """System users (analysts, admins, viewers)"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='analyst')  # admin, analyst, viewer
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    # Two-Factor Authentication (TOTP)
    totp_secret = db.Column(db.String(64), nullable=True)
    totp_enabled = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'totp_enabled': self.totp_enabled,
        }


class Customer(db.Model):
    """Bank customers whose transactions are monitored"""
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    country = db.Column(db.String(10), default='US')
    city = db.Column(db.String(50))
    account_type = db.Column(db.String(20), default='personal')  # personal, business
    date_of_birth = db.Column(db.Date, nullable=True)           # for age verification
    avg_transaction_amount = db.Column(db.Float, default=500.0)
    total_transactions = db.Column(db.Integer, default=0)
    risk_level = db.Column(db.String(10), default='low')        # low, medium, high
    is_ofac_sanctioned = db.Column(db.Boolean, default=False)   # OFAC match flag
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    transactions = db.relationship('Transaction', backref='customer', lazy=True)

    @property
    def age(self) -> int | None:
        """Calculate customer age from date_of_birth. Returns None if unknown."""
        if not self.date_of_birth:
            return None
        today = date.today()
        dob   = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    def to_dict(self):
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'country': self.country,
            'city': self.city,
            'account_type': self.account_type,
            'date_of_birth': self.date_of_birth.isoformat() if self.date_of_birth else None,
            'age': self.age,
            'avg_transaction_amount': self.avg_transaction_amount,
            'total_transactions': self.total_transactions,
            'risk_level': self.risk_level,
            'is_ofac_sanctioned': self.is_ofac_sanctioned,
        }


class Transaction(db.Model):
    """Financial transactions submitted for fraud analysis"""
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(36), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD')
    merchant_name = db.Column(db.String(100))
    merchant_category = db.Column(db.String(50))
    location = db.Column(db.String(50))
    ip_address = db.Column(db.String(45))
    device_id = db.Column(db.String(100))
    card_type = db.Column(db.String(20))
    transaction_type = db.Column(db.String(20))  # purchase, transfer, withdrawal
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    status = db.Column(db.String(20), default='pending')  # pending, approved, flagged, blocked
    is_fraud = db.Column(db.Boolean, default=False)
    is_reviewed = db.Column(db.Boolean, default=False)

    risk_scores = db.relationship('RiskScore', backref='transaction', lazy=True)
    alerts = db.relationship('FraudAlert', backref='transaction', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'customer_id': self.customer_id,
            'customer_name': self.customer.name if self.customer else None,
            'customer_code': self.customer.customer_id if self.customer else None,
            'amount': self.amount,
            'currency': self.currency,
            'merchant_name': self.merchant_name,
            'merchant_category': self.merchant_category,
            'location': self.location,
            'card_type': self.card_type,
            'transaction_type': self.transaction_type,
            'timestamp': self.timestamp.isoformat(),
            'status': self.status,
            'is_fraud': self.is_fraud,
            'is_reviewed': self.is_reviewed,
        }


class FraudAlert(db.Model):
    """Alerts generated when suspicious transactions are detected"""
    __tablename__ = 'fraud_alerts'

    id = db.Column(db.Integer, primary_key=True)
    alert_id = db.Column(db.String(36), unique=True, nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=False)
    alert_type = db.Column(db.String(50))
    severity = db.Column(db.String(10))  # low, medium, high, critical
    description = db.Column(db.Text)
    risk_factors = db.Column(db.Text)  # JSON list of violation descriptions
    is_resolved = db.Column(db.Boolean, default=False)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolution_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'alert_id': self.alert_id,
            'transaction_id': self.transaction_id,
            'alert_type': self.alert_type,
            'severity': self.severity,
            'description': self.description,
            'risk_factors': json.loads(self.risk_factors) if self.risk_factors else [],
            'is_resolved': self.is_resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'resolution_notes': self.resolution_notes,
            'created_at': self.created_at.isoformat(),
        }


class RiskScore(db.Model):
    """Risk score breakdown stored for each analyzed transaction"""
    __tablename__ = 'risk_scores'

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=False)
    rule_score = db.Column(db.Float, default=0.0)
    ml_score = db.Column(db.Float, default=0.0)
    combined_score = db.Column(db.Float, default=0.0)
    risk_level = db.Column(db.String(10))  # low, medium, high, critical
    rule_violations = db.Column(db.Text)   # JSON list of violation dicts
    ml_features = db.Column(db.Text)       # JSON dict of feature values used
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'transaction_id': self.transaction_id,
            'rule_score': round(self.rule_score, 4),
            'ml_score': round(self.ml_score, 4),
            'combined_score': round(self.combined_score, 4),
            'risk_level': self.risk_level,
            'rule_violations': json.loads(self.rule_violations) if self.rule_violations else [],
            'ml_features': json.loads(self.ml_features) if self.ml_features else {},
            'created_at': self.created_at.isoformat(),
        }


class FraudRule(db.Model):
    """Configurable rule definitions for rule-based fraud detection"""
    __tablename__ = 'fraud_rules'

    id = db.Column(db.Integer, primary_key=True)
    rule_name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)
    rule_type = db.Column(db.String(30))   # threshold, time, frequency, location, pattern, statistical
    threshold = db.Column(db.Float, nullable=True)
    weight = db.Column(db.Float, default=0.1)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'rule_name': self.rule_name,
            'description': self.description,
            'rule_type': self.rule_type,
            'threshold': self.threshold,
            'weight': self.weight,
            'is_active': self.is_active,
        }


class OFACEntry(db.Model):
    """
    OFAC Specially Designated Nationals (SDN) list entry.
    Populated and refreshed daily by the background scheduler.
    """
    __tablename__ = 'ofac_entries'

    id            = db.Column(db.Integer, primary_key=True)
    sdn_name      = db.Column(db.String(300), nullable=False)
    sdn_name_norm = db.Column(db.String(300), nullable=False, index=True)  # normalised for fast search
    sdn_type      = db.Column(db.String(30))    # individual, entity, vessel, aircraft
    program       = db.Column(db.String(200))   # sanctions programme identifiers
    remarks       = db.Column(db.String(500))
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':       self.id,
            'name':     self.sdn_name,
            'type':     self.sdn_type,
            'program':  self.program,
            'remarks':  self.remarks,
        }


class OFACUpdate(db.Model):
    """
    Audit log for each OFAC list refresh attempt.
    Tracks download status, entry counts, and timestamps.
    """
    __tablename__ = 'ofac_updates'

    id            = db.Column(db.Integer, primary_key=True)
    status        = db.Column(db.String(20), default='running')   # running, success, error
    entries_added = db.Column(db.Integer, default=0)
    entries_total = db.Column(db.Integer, default=0)
    error_message = db.Column(db.String(500))
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':            self.id,
            'status':        self.status,
            'entries_added': self.entries_added,
            'entries_total': self.entries_total,
            'error_message': self.error_message,
            'updated_at':    self.updated_at.isoformat() if self.updated_at else None,
        }
