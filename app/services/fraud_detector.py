"""
Fraud Detection Orchestrator
------------------------------
Combines rule-based and ML-based signals into a single combined risk score,
determines transaction status, stores risk score records, and generates alerts.

Combined score = 0.40 * rule_score + 0.60 * ml_score
"""
import json
import uuid
from datetime import datetime, timedelta

from app.models.models import db, Transaction, FraudAlert, RiskScore
from app.services.rule_engine import RuleEngine
from app.services.ml_service import MLFraudDetector

# Weights for combining rule and ML scores
RULE_WEIGHT = 0.40
ML_WEIGHT = 0.60

# Thresholds
ALERT_THRESHOLD = 0.45    # above this → generate alert
FLAG_THRESHOLD = 0.45     # flagged
BLOCK_THRESHOLD = 0.75    # blocked (high confidence fraud)
FRAUD_THRESHOLD = 0.65    # mark is_fraud = True


def get_risk_level(score: float) -> str:
    if score >= 0.75:
        return 'critical'
    elif score >= 0.55:
        return 'high'
    elif score >= 0.35:
        return 'medium'
    return 'low'


# Module-level singletons — safe because neither __init__ uses app context
_rule_engine = RuleEngine()
_ml_detector = MLFraudDetector()


class FraudDetector:
    """
    Main entry point for fraud analysis.
    Call analyze_transaction() within an active Flask app / DB session context.
    """

    def analyze_transaction(self, transaction, customer) -> dict:
        """
        Perform full fraud analysis on *transaction*.

        Step 0: Compliance pre-checks (AGE + OFAC) — hard block immediately.
        Steps 1–9: Standard rule + ML pipeline.

        Writes RiskScore and optional FraudAlert to the DB session (caller must commit).
        Also updates transaction.status, transaction.is_fraud, and customer stats.

        Returns a result dict suitable for JSON serialisation.
        """
        # ── 0. Compliance pre-checks — age and OFAC sanctions ─────────
        compliance_block = self._compliance_precheck(transaction, customer)
        if compliance_block:
            return compliance_block

        # ── 1. Count recent transactions for velocity checks ──────────
        one_hour_ago = transaction.timestamp - timedelta(hours=1)
        recent_count = Transaction.query.filter(
            Transaction.customer_id == customer.id,
            Transaction.timestamp >= one_hour_ago,
            Transaction.timestamp < transaction.timestamp,
        ).count()

        # ── 2. Rule-based evaluation ────────────────────────────────────
        rule_score, rule_violations = _rule_engine.evaluate(transaction, customer)

        # ── 3. ML-based evaluation ──────────────────────────────────────
        ml_score, is_anomaly = _ml_detector.predict(transaction, customer, recent_count)

        # ── 4. Combined score ───────────────────────────────────────────
        combined_score = min(RULE_WEIGHT * rule_score + ML_WEIGHT * ml_score, 1.0)
        risk_level = get_risk_level(combined_score)

        # ── 5. Transaction disposition ──────────────────────────────────
        if combined_score >= BLOCK_THRESHOLD:
            status = 'blocked'
        elif combined_score >= FLAG_THRESHOLD:
            status = 'flagged'
        else:
            status = 'approved'

        is_fraud = combined_score >= FRAUD_THRESHOLD

        # ── 6. Persist RiskScore record ─────────────────────────────────
        ml_features = {
            'recent_count_1h': recent_count,
            'is_anomaly_iso': is_anomaly,
            'amount_vs_avg_ratio': round(
                transaction.amount / max(customer.avg_transaction_amount or 500.0, 1), 3
            ),
        }
        risk_record = RiskScore(
            transaction_id=transaction.id,
            rule_score=rule_score,
            ml_score=ml_score,
            combined_score=combined_score,
            risk_level=risk_level,
            rule_violations=json.dumps(rule_violations),
            ml_features=json.dumps(ml_features),
        )
        db.session.add(risk_record)

        # ── 7. Generate fraud alert if threshold exceeded ───────────────
        alert_generated = False
        if combined_score >= ALERT_THRESHOLD:
            self._create_alert(transaction, combined_score, risk_level, rule_violations)
            alert_generated = True

        # ── 8. Update transaction ───────────────────────────────────────
        transaction.status = status
        transaction.is_fraud = is_fraud

        # ── 9. Update customer stats and risk level ─────────────────────
        customer.total_transactions = (customer.total_transactions or 0) + 1
        self._update_customer_risk(customer, combined_score)

        db.session.commit()

        result = {
            'transaction_id': transaction.transaction_id,
            'status': status,
            'is_fraud': is_fraud,
            'risk_score': {
                'rule_score': round(rule_score, 4),
                'ml_score': round(ml_score, 4),
                'combined_score': round(combined_score, 4),
                'risk_level': risk_level,
            },
            'rule_violations': rule_violations,
            'ml_analysis': {
                'recent_count_1h': recent_count,
                'is_anomaly': is_anomaly,
                'model_active': _ml_detector.model_loaded,
            },
            'alert_generated': alert_generated,
            'recommendation': self._recommendation(status, combined_score),
        }

        # ── Real-Time Monitoring ────────────────────────────────────────────
        # Feed every completed analysis into the monitoring service for
        # streaming analytics, threshold evaluation, and network analysis.
        try:
            from app.services.monitoring_service import monitoring_service
            tx_data = {
                'customer_id': transaction.customer_id,
                'amount':      transaction.amount,
                'device_id':   transaction.device_id,
                'ip_address':  transaction.ip_address,
                'location':    transaction.location,
            }
            monitoring_result = monitoring_service.monitor(tx_data, result)
            result['monitoring'] = monitoring_result
        except Exception as mon_err:
            import logging as _log
            _log.getLogger(__name__).warning('Monitoring update failed: %s', mon_err)

        return result

    # ------------------------------------------------------------------
    # Compliance Pre-Check (Age + OFAC) — runs BEFORE rule/ML pipeline
    # ------------------------------------------------------------------

    def _compliance_precheck(self, transaction, customer) -> dict | None:
        """
        Perform regulatory compliance checks that result in an IMMEDIATE hard block:
          1. Age restriction  — under 18 or over 100
          2. OFAC sanctions   — customer name on the SDN list

        If a violation is found:
          • Transaction is blocked immediately (status = 'blocked')
          • RiskScore is recorded at 1.0 (maximum)
          • A CRITICAL alert is generated
          • A result dict is returned (short-circuiting the ML pipeline)

        Returns None if compliance passes (caller continues with normal pipeline).
        """
        violations = []

        # ── Age check ─────────────────────────────────────────────────
        age = customer.age
        if age is not None:
            if age < 18:
                violations.append({
                    'rule':       'AGE_RESTRICTION',
                    'description': (
                        f"COMPLIANCE BLOCK: Customer age {age} is below the legal minimum "
                        f"of 18. Minor cannot enter financial contracts (KYC requirement)."
                    ),
                    'weight':     1.0,
                    'severity':   'critical',
                    'hard_block': True,
                })
            elif age > 100:
                violations.append({
                    'rule':       'AGE_RESTRICTION',
                    'description': (
                        f"COMPLIANCE BLOCK: Customer age {age} exceeds 100 years. "
                        f"Likely identity fraud, deceased account, or date-of-birth error."
                    ),
                    'weight':     1.0,
                    'severity':   'critical',
                    'hard_block': True,
                })

        # ── OFAC sanctions check ─────────────────────────────────────
        try:
            from app.services.ofac_service import check_name
            ofac_match = check_name(customer.name)
            if ofac_match:
                violations.append({
                    'rule':       'OFAC_SANCTIONS',
                    'description': (
                        f"COMPLIANCE BLOCK: Customer '{customer.name}' matched OFAC SDN entry "
                        f"'{ofac_match['match_name']}' "
                        f"({ofac_match['similarity']:.0%} similarity, "
                        f"programme: {ofac_match['program']})."
                    ),
                    'weight':     1.0,
                    'severity':   'critical',
                    'hard_block': True,
                    'ofac_match': ofac_match,
                })
                # Mark the customer account as OFAC-flagged
                customer.is_ofac_sanctioned = True
        except Exception as ofac_err:
            # Fail-closed: if OFAC service is unavailable, block the transaction
            # and require manual compliance review. Never silently skip.
            import logging as _logging
            _logging.getLogger(__name__).error(
                'OFAC check FAILED for customer %s — blocking transaction pending review: %s',
                customer.name, ofac_err, exc_info=True
            )
            violations.append({
                'rule':        'OFAC_SERVICE_ERROR',
                'description': (
                    "COMPLIANCE BLOCK: OFAC sanctions screening service is temporarily "
                    "unavailable. Transaction blocked pending manual compliance review."
                ),
                'weight':      1.0,
                'severity':    'critical',
                'hard_block':  True,
            })

        if not violations:
            return None  # All compliance checks passed

        # ── Issue hard block ──────────────────────────────────────────
        risk_record = RiskScore(
            transaction_id = transaction.id,
            rule_score     = 1.0,
            ml_score       = 1.0,
            combined_score = 1.0,
            risk_level     = 'critical',
            rule_violations= json.dumps(violations),
            ml_features    = json.dumps({'compliance_block': True}),
        )
        db.session.add(risk_record)

        transaction.status   = 'blocked'
        transaction.is_fraud = True
        customer.total_transactions = (customer.total_transactions or 0) + 1
        customer.risk_level = 'high'

        self._create_alert(transaction, 1.0, 'critical', violations)
        db.session.commit()

        reason = violations[0]['rule']
        return {
            'transaction_id':  transaction.transaction_id,
            'status':          'blocked',
            'is_fraud':        True,
            'compliance_block': True,
            'block_reason':    reason,
            'risk_score': {
                'rule_score':    1.0,
                'ml_score':      1.0,
                'combined_score': 1.0,
                'risk_level':    'critical',
            },
            'rule_violations': violations,
            'ml_analysis': {
                'recent_count_1h': 0,
                'is_anomaly':      True,
                'model_active':    False,
                'skipped_reason':  'compliance_block',
            },
            'alert_generated': True,
            'recommendation': (
                f"⛔ COMPLIANCE BLOCK ({reason}): Transaction blocked by regulatory "
                f"compliance rule. Immediate escalation to Compliance Officer required. "
                f"Do NOT process this transaction."
            ),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_alert(self, transaction, score, risk_level, violations):
        """Create and persist a FraudAlert record."""
        severity_map = {
            'critical': 'critical',
            'high': 'high',
            'medium': 'medium',
            'low': 'low',
        }
        alert_type = violations[0]['rule'] if violations else 'ML_ANOMALY'

        description = (
            f"Suspicious transaction detected — combined risk score: "
            f"{score:.1%}.  "
        )
        if violations:
            description += f"Primary trigger: {violations[0]['description']}"

        alert = FraudAlert(
            alert_id=str(uuid.uuid4()),
            transaction_id=transaction.id,
            alert_type=alert_type,
            severity=severity_map.get(risk_level, 'medium'),
            description=description,
            risk_factors=json.dumps([v['description'] for v in violations]),
            is_resolved=False,
        )
        db.session.add(alert)

    def _update_customer_risk(self, customer, combined_score):
        """Escalate customer risk level based on latest transaction score."""
        if combined_score >= FRAUD_THRESHOLD:
            customer.risk_level = 'high'
        elif combined_score >= ALERT_THRESHOLD and customer.risk_level == 'low':
            customer.risk_level = 'medium'

    @staticmethod
    def _recommendation(status: str, score: float) -> str:
        msgs = {
            'blocked': 'Transaction blocked automatically. Immediate manual review required.',
            'flagged': (
                'Transaction flagged for review. '
                'Contact customer to verify legitimacy before approving.'
            ),
            'approved': 'Transaction approved. No immediate action required.',
        }
        return msgs.get(status, 'Review required.')
