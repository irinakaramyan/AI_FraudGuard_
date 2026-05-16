"""
ML-Based Fraud Detection Service
----------------------------------
Uses a trained Isolation Forest (unsupervised anomaly detection) combined with
a Random Forest classifier (supervised) for hybrid scoring.

Feature vector (10 features):
  [0]  amount              - raw transaction amount
  [1]  hour               - hour of day (0–23)
  [2]  day_of_week        - weekday (0=Mon … 6=Sun)
  [3]  is_international   - 1 if transaction location differs from customer country
  [4]  is_unusual_hour    - 1 if hour in 1–5 (1 AM–5 AM)
  [5]  recent_count       - # of transactions for this customer in last 60 min
  [6]  amount_deviation   - (amount - avg) / avg  (z-score-like)
  [7]  is_round_amount    - 1 if amount is a whole number ≥ $1 000
  [8]  is_high_risk_cat   - 1 if merchant category is high-risk
  [9]  customer_risk      - 1 if customer is classified high-risk
"""
import os
import numpy as np
import joblib


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODEL_DIR = os.path.join(_BASE_DIR, 'ml', 'models')

HIGH_RISK_CATS = {'gambling', 'cryptocurrency', 'money_transfer', 'adult', 'forex'}


class MLFraudDetector:
    """
    Loads pre-trained Isolation Forest + optional RF classifier and returns
    an ML fraud score in [0, 1] for each transaction.
    """

    def __init__(self):
        self.iso_model = None
        self.rf_model = None
        self.scaler = None
        self.model_loaded = False
        self._load_models()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_models(self):
        iso_path = os.path.join(_MODEL_DIR, 'fraud_model.pkl')
        rf_path = os.path.join(_MODEL_DIR, 'rf_classifier.pkl')
        scaler_path = os.path.join(_MODEL_DIR, 'scaler.pkl')

        if not (os.path.exists(iso_path) and os.path.exists(scaler_path)):
            print(f"[ML] Model files not found in {_MODEL_DIR}. "
                  "Heuristic fallback will be used until models are trained.")
            return

        try:
            self.iso_model = joblib.load(iso_path)
            self.scaler = joblib.load(scaler_path)
            if os.path.exists(rf_path):
                self.rf_model = joblib.load(rf_path)
            self.model_loaded = True
            print("[ML] Fraud detection models loaded successfully.")
        except Exception as exc:
            print(f"[ML] Warning — could not load models: {exc}")
            self.model_loaded = False

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def extract_features(self, transaction, customer, recent_count: int) -> list:
        """Return a 10-element feature vector for the given transaction."""
        hour = transaction.timestamp.hour
        day_of_week = transaction.timestamp.weekday()

        avg = customer.avg_transaction_amount if customer.avg_transaction_amount else 500.0
        amount_deviation = (transaction.amount - avg) / (avg + 1e-9)

        # Internationalness
        is_international = 0
        if transaction.location and customer.country:
            tx_loc = transaction.location.upper().strip()
            cust_country = customer.country.upper().strip()
            us_variants = {'US', 'USA', 'UNITED STATES'}
            if not (tx_loc in us_variants and cust_country in us_variants):
                if tx_loc != cust_country:
                    is_international = 1

        is_unusual_hour = 1 if 1 <= hour <= 5 else 0
        is_round = 1 if (transaction.amount >= 1000 and
                         transaction.amount == int(transaction.amount)) else 0
        cat = (transaction.merchant_category or '').lower()
        is_high_risk_cat = 1 if cat in HIGH_RISK_CATS else 0
        cust_risk = 1 if customer.risk_level == 'high' else 0

        return [
            transaction.amount,       # [0]
            hour,                     # [1]
            day_of_week,              # [2]
            is_international,         # [3]
            is_unusual_hour,          # [4]
            recent_count,             # [5]
            amount_deviation,         # [6]
            is_round,                 # [7]
            is_high_risk_cat,         # [8]
            cust_risk,                # [9]
        ]

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, transaction, customer, recent_count: int = 0):
        """
        Returns:
            ml_score (float): 0.0 = legitimate, 1.0 = highly suspicious
            is_anomaly (bool): True if model classifies as anomaly
        """
        if not self.model_loaded:
            return self._heuristic_score(transaction, customer, recent_count)

        try:
            features = np.array(
                self.extract_features(transaction, customer, recent_count)
            ).reshape(1, -1)
            features_scaled = self.scaler.transform(features)

            # Isolation Forest score: negative = anomaly
            iso_raw = self.iso_model.decision_function(features_scaled)[0]
            # Map to [0,1]: decision_function ≈ [-0.5, 0.5]
            iso_score = float(np.clip((-iso_raw + 0.2) / 0.7, 0.0, 1.0))
            is_anomaly = bool(self.iso_model.predict(features_scaled)[0] == -1)

            if self.rf_model is not None:
                # RF gives probability of fraud class (index 1)
                rf_proba = float(self.rf_model.predict_proba(features_scaled)[0][1])
                ml_score = 0.5 * iso_score + 0.5 * rf_proba
            else:
                ml_score = iso_score

            return float(np.clip(ml_score, 0.0, 1.0)), is_anomaly

        except Exception as exc:
            print(f"[ML] Prediction error: {exc}")
            return self._heuristic_score(transaction, customer, recent_count)

    # ------------------------------------------------------------------
    # Heuristic fallback (no model)
    # ------------------------------------------------------------------

    def _heuristic_score(self, transaction, customer, recent_count: int):
        score = 0.0
        avg = customer.avg_transaction_amount if customer.avg_transaction_amount else 500.0

        if transaction.amount > avg * 10:
            score += 0.50
        elif transaction.amount > avg * 5:
            score += 0.35
        elif transaction.amount > avg * 2:
            score += 0.15

        if recent_count > 8:
            score += 0.35
        elif recent_count > 4:
            score += 0.20
        elif recent_count > 2:
            score += 0.10

        if 1 <= transaction.timestamp.hour <= 5:
            score += 0.20

        cat = (transaction.merchant_category or '').lower()
        if cat in HIGH_RISK_CATS:
            score += 0.20

        if customer.risk_level == 'high':
            score += 0.15

        score = float(np.clip(score, 0.0, 1.0))
        return score, score > 0.5
