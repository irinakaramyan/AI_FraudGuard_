"""
Rule-Based Fraud Detection Engine
----------------------------------
Evaluates transactions against configurable fraud rules stored in the database.
Each rule returns a violation dict and a risk weight contribution.

Rules included:
  DB-driven  : LARGE_AMOUNT, UNUSUAL_HOURS, HIGH_FREQUENCY,
               INTERNATIONAL_TRANSACTION, ROUND_AMOUNT, AMOUNT_DEVIATION,
               AGE_RESTRICTION, OFAC_SANCTIONS
  Hard-coded : RAPID_TRANSACTIONS, HIGH_RISK_MERCHANT, HIGH_RISK_CUSTOMER
"""
from datetime import datetime, timedelta, date
from app.models.models import Transaction, FraudRule


# High-risk merchant categories
HIGH_RISK_CATEGORIES = {'gambling', 'cryptocurrency', 'money_transfer', 'adult', 'forex'}


class RuleEngine:
    """Evaluates a transaction against all active fraud rules."""

    def evaluate(self, transaction, customer):
        """
        Run all active fraud rules against the given transaction.

        Returns:
            rule_score (float): Aggregate risk score in [0, 1]
            violations (list):  List of violation dicts with rule, description, weight, severity
        """
        violations = []
        total_weight = 0.0

        # Load active rules fresh from DB on every call
        active_rules = FraudRule.query.filter_by(is_active=True).all()

        for rule in active_rules:
            result = self._apply_rule(rule, transaction, customer)
            if result:
                violations.append(result)
                total_weight += rule.weight

        # Extra pattern checks not stored as DB rows
        extra_violations, extra_weight = self._extra_checks(transaction, customer)
        violations.extend(extra_violations)
        total_weight += extra_weight

        rule_score = min(total_weight, 1.0)
        return rule_score, violations

    # ------------------------------------------------------------------
    # Individual rule evaluators
    # ------------------------------------------------------------------

    def _apply_rule(self, rule, transaction, customer):
        """Dispatch to the correct rule handler based on rule_name."""
        handlers = {
            'LARGE_AMOUNT':              self._rule_large_amount,
            'UNUSUAL_HOURS':             self._rule_unusual_hours,
            'HIGH_FREQUENCY':            self._rule_high_frequency,
            'INTERNATIONAL_TRANSACTION': self._rule_international,
            'ROUND_AMOUNT':              self._rule_round_amount,
            'AMOUNT_DEVIATION':          self._rule_amount_deviation,
            'AGE_RESTRICTION':           self._rule_age_restriction,
            'OFAC_SANCTIONS':            self._rule_ofac_sanctions,
        }
        handler = handlers.get(rule.rule_name)
        if handler:
            return handler(rule, transaction, customer)
        return None

    def _rule_large_amount(self, rule, transaction, customer):
        if transaction.amount > rule.threshold:
            multiplier = transaction.amount / rule.threshold
            return {
                'rule': rule.rule_name,
                'description': (
                    f"Transaction ${transaction.amount:,.2f} exceeds large-amount "
                    f"threshold of ${rule.threshold:,.2f} ({multiplier:.1f}x over limit)"
                ),
                'weight': rule.weight,
                'severity': 'critical' if multiplier > 5 else 'high',
            }
        return None

    def _rule_unusual_hours(self, rule, transaction, customer):
        hour = transaction.timestamp.hour
        if 1 <= hour <= 5:
            return {
                'rule': rule.rule_name,
                'description': f"Transaction at unusual hour {hour:02d}:00 (1 AM–5 AM window)",
                'weight': rule.weight,
                'severity': 'low',
            }
        return None

    def _rule_high_frequency(self, rule, transaction, customer):
        one_hour_ago = transaction.timestamp - timedelta(hours=1)
        recent_count = Transaction.query.filter(
            Transaction.customer_id == customer.id,
            Transaction.timestamp >= one_hour_ago,
            Transaction.timestamp < transaction.timestamp,
        ).count()
        if recent_count >= int(rule.threshold):
            return {
                'rule': rule.rule_name,
                'description': (
                    f"Customer made {recent_count} transactions in the last hour "
                    f"(threshold: {int(rule.threshold)})"
                ),
                'weight': rule.weight,
                'severity': 'high',
            }
        return None

    def _rule_international(self, rule, transaction, customer):
        if not transaction.location or not customer.country:
            return None
        tx_loc = transaction.location.upper().strip()
        cust_country = customer.country.upper().strip()
        # Map common equivalents
        us_variants = {'US', 'USA', 'UNITED STATES'}
        if tx_loc in us_variants and cust_country in us_variants:
            return None
        if tx_loc != cust_country:
            return {
                'rule': rule.rule_name,
                'description': (
                    f"Transaction from '{transaction.location}' but customer's "
                    f"home country is '{customer.country}'"
                ),
                'weight': rule.weight,
                'severity': 'medium',
            }
        return None

    def _rule_round_amount(self, rule, transaction, customer):
        if (transaction.amount >= rule.threshold and
                transaction.amount == int(transaction.amount)):
            return {
                'rule': rule.rule_name,
                'description': (
                    f"Suspiciously round transaction amount: ${transaction.amount:,.0f}"
                ),
                'weight': rule.weight,
                'severity': 'low',
            }
        return None

    def _rule_amount_deviation(self, rule, transaction, customer):
        avg = customer.avg_transaction_amount or 500.0
        if avg <= 0:
            return None
        deviation_ratio = abs(transaction.amount - avg) / avg
        if deviation_ratio > rule.threshold:
            return {
                'rule': rule.rule_name,
                'description': (
                    f"Amount ${transaction.amount:,.2f} deviates "
                    f"{deviation_ratio * 100:.0f}% from customer's average "
                    f"${avg:,.2f} (threshold: {rule.threshold * 100:.0f}%)"
                ),
                'weight': rule.weight,
                'severity': 'high' if deviation_ratio > rule.threshold * 2 else 'medium',
            }
        return None

    def _rule_age_restriction(self, rule, transaction, customer):
        """
        Block transactions for customers who are:
          • Under 18  — legally cannot enter financial contracts in most jurisdictions
          • Over 100  — statistically anomalous; likely data error or identity fraud

        If date_of_birth is not set, skip (don't penalise unknown DOB).
        """
        age = customer.age  # uses the @property on the Customer model
        if age is None:
            return None     # DOB unknown — no violation raised

        if age < 18:
            return {
                'rule': rule.rule_name,
                'description': (
                    f"Customer age {age} is below the minimum allowed age of 18. "
                    "Transactions for minors are prohibited under KYC regulations."
                ),
                'weight': rule.weight,
                'severity': 'critical',
                'hard_block': True,     # signal to FraudDetector for immediate block
            }

        if age > 100:
            return {
                'rule': rule.rule_name,
                'description': (
                    f"Customer age {age} exceeds maximum allowed age of 100 years. "
                    "This may indicate identity fraud, a deceased account, or a data error."
                ),
                'weight': rule.weight,
                'severity': 'critical',
                'hard_block': True,
            }

        return None

    def _rule_ofac_sanctions(self, rule, transaction, customer):
        """
        Check the customer name against the OFAC SDN sanctions list.
        A match is a regulatory hard block — the transaction must not proceed.
        """
        try:
            from app.services.ofac_service import check_name
            match = check_name(customer.name)
            if match:
                return {
                    'rule': rule.rule_name,
                    'description': (
                        f"Customer name '{customer.name}' matches OFAC SDN entry "
                        f"'{match['match_name']}' "
                        f"(similarity: {match['similarity']:.0%}, "
                        f"programme: {match['program']}, "
                        f"type: {match['sdn_type']})."
                    ),
                    'weight': rule.weight,
                    'severity': 'critical',
                    'hard_block': True,
                    'ofac_match': match,
                }
        except Exception:
            pass    # OFAC service unavailable — don't crash the detector
        return None

    # ------------------------------------------------------------------
    # Additional hard-coded pattern checks
    # ------------------------------------------------------------------

    def _extra_checks(self, transaction, customer):
        violations = []
        score = 0.0

        # Rapid successive transactions (≥3 in 5 minutes)
        five_min_ago = transaction.timestamp - timedelta(minutes=5)
        rapid_count = Transaction.query.filter(
            Transaction.customer_id == customer.id,
            Transaction.timestamp >= five_min_ago,
            Transaction.timestamp < transaction.timestamp,
        ).count()
        if rapid_count >= 3:
            violations.append({
                'rule': 'RAPID_TRANSACTIONS',
                'description': (
                    f"{rapid_count} transactions within the last 5 minutes — "
                    "velocity pattern typical of account takeover"
                ),
                'weight': 0.30,
                'severity': 'high',
            })
            score += 0.30

        # High-risk merchant category
        cat = (transaction.merchant_category or '').lower()
        if cat in HIGH_RISK_CATEGORIES:
            violations.append({
                'rule': 'HIGH_RISK_MERCHANT',
                'description': (
                    f"Merchant category '{transaction.merchant_category}' is "
                    "classified as high-risk"
                ),
                'weight': 0.20,
                'severity': 'medium',
            })
            score += 0.20

        # Customer already flagged as high-risk
        if customer.risk_level == 'high':
            violations.append({
                'rule': 'HIGH_RISK_CUSTOMER',
                'description': "Customer account is flagged as high-risk based on prior activity",
                'weight': 0.15,
                'severity': 'medium',
            })
            score += 0.15

        return violations, score
