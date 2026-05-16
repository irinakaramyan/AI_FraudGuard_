"""
ML Model Training Script
-------------------------
Generates synthetic transaction data and trains two models:

  1. IsolationForest  — unsupervised anomaly detection
     Trained on normal transactions only; anomaly score ∝ fraud probability.

  2. RandomForestClassifier — supervised fraud classification
     Trained on labelled synthetic data; outputs fraud probability directly.

Both models and the feature scaler are saved to ml/models/.

Feature vector (10 features — must match ml_service.py):
  [0]  amount
  [1]  hour_of_day
  [2]  day_of_week
  [3]  is_international
  [4]  is_unusual_hour   (1–5 AM)
  [5]  recent_count_1h
  [6]  amount_deviation  (amount/avg - 1)
  [7]  is_round_amount
  [8]  is_high_risk_cat
  [9]  customer_risk     (1 = high-risk customer)
"""
import os
import sys
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score
import joblib

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
MODEL_DIR = os.path.join(_SCRIPT_DIR, 'models')

FEATURE_NAMES = [
    'amount', 'hour', 'day_of_week', 'is_international',
    'is_unusual_hour', 'recent_count', 'amount_deviation',
    'is_round_amount', 'is_high_risk_cat', 'customer_risk',
]


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------

def _generate_normal(n: int, rng: np.random.Generator) -> np.ndarray:
    amounts = rng.lognormal(mean=5.5, sigma=0.9, size=n)        # ~$50–$3 000
    hours = rng.integers(6, 23, size=n)
    days = rng.integers(0, 7, size=n)
    intl = rng.choice([0, 1], size=n, p=[0.87, 0.13])
    unusual_h = (hours < 6).astype(float)
    freq = rng.poisson(1.2, size=n)
    amt_dev = rng.normal(0.0, 0.4, size=n)                        # small deviation
    rnd_amt = rng.choice([0, 1], size=n, p=[0.96, 0.04])
    hi_cat = rng.choice([0, 1], size=n, p=[0.93, 0.07])
    cust_risk = rng.choice([0, 1], size=n, p=[0.92, 0.08])
    return np.column_stack([
        amounts, hours, days, intl, unusual_h,
        freq, amt_dev, rnd_amt, hi_cat, cust_risk,
    ])


def _generate_fraud(n: int, rng: np.random.Generator) -> np.ndarray:
    """
    Mix of four fraud archetypes:
      A – large wire / transfer  (high amount, international, unusual hours)
      B – account takeover       (rapid velocity, unusual hours)
      C – high-risk merchant     (crypto / gambling)
      D – identity theft         (international + round amount)
    """
    qa, qb, qc, qd = n // 4, n // 4, n // 4, n - 3 * (n // 4)

    # Archetype A
    A = np.column_stack([
        rng.uniform(8_000, 80_000, qa),    # large amount
        rng.integers(1, 6, qa),            # unusual hours
        rng.integers(0, 7, qa),
        np.ones(qa),                        # international
        np.ones(qa),                        # unusual_hour flag
        rng.poisson(1, qa),
        rng.normal(8.0, 2.0, qa),          # high deviation
        rng.choice([0, 1], qa, p=[0.4, 0.6]),  # round
        np.zeros(qa),
        rng.choice([0, 1], qa, p=[0.5, 0.5]),
    ])

    # Archetype B
    B = np.column_stack([
        rng.lognormal(5.0, 0.6, qb),
        rng.integers(1, 5, qb),
        rng.integers(0, 7, qb),
        rng.choice([0, 1], qb, p=[0.5, 0.5]),
        np.ones(qb),
        rng.poisson(7, qb),                # high frequency
        rng.normal(0.5, 0.3, qb),
        np.zeros(qb),
        np.zeros(qb),
        rng.choice([0, 1], qb, p=[0.4, 0.6]),
    ])

    # Archetype C
    C = np.column_stack([
        rng.lognormal(6.0, 1.0, qc),
        rng.integers(0, 24, qc),
        rng.integers(0, 7, qc),
        rng.choice([0, 1], qc, p=[0.6, 0.4]),
        np.zeros(qc),
        rng.poisson(2, qc),
        rng.normal(1.5, 1.0, qc),
        np.zeros(qc),
        np.ones(qc),                       # high-risk merchant
        rng.choice([0, 1], qc, p=[0.3, 0.7]),
    ])

    # Archetype D
    D = np.column_stack([
        np.array([round(x / 1000) * 1000
                  for x in rng.uniform(2_000, 30_000, qd)], dtype=float),
        rng.integers(0, 24, qd),
        rng.integers(0, 7, qd),
        np.ones(qd),                       # international
        np.zeros(qd),
        rng.poisson(1, qd),
        rng.normal(4.0, 1.5, qd),
        np.ones(qd),                       # round amount
        rng.choice([0, 1], qd, p=[0.7, 0.3]),
        np.ones(qd),                       # high-risk customer
    ])

    return np.vstack([A, B, C, D])


def generate_dataset(n_normal: int = 9_000, n_fraud: int = 600, seed: int = 42):
    rng = np.random.default_rng(seed)
    X_normal = _generate_normal(n_normal, rng)
    X_fraud = _generate_fraud(n_fraud, rng)
    X = np.vstack([X_normal, X_fraud])
    y = np.concatenate([np.zeros(n_normal), np.ones(n_fraud)])
    return X, y


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_models(model_dir: str = MODEL_DIR):
    os.makedirs(model_dir, exist_ok=True)

    print("=" * 60)
    print("AI Fraud Detection — ML Training")
    print("=" * 60)

    print(f"\n[1/5] Generating synthetic data ...")
    X, y = generate_dataset()
    print(f"      Normal:  {int((y == 0).sum()):,}  |  Fraud: {int((y == 1).sum()):,}")

    print("[2/5] Splitting into train / test sets ...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    print("[3/5] Scaling features ...")
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    # ── Isolation Forest ──────────────────────────────────────────────
    print("[4/5] Training Isolation Forest (unsupervised) ...")
    normal_train = X_train_s[y_train == 0]
    iso = IsolationForest(
        n_estimators=200,
        contamination=0.065,
        max_samples='auto',
        random_state=42,
        n_jobs=-1,
    )
    iso.fit(normal_train)

    iso_pred = iso.predict(X_test_s)
    iso_bin = (iso_pred == -1).astype(int)
    iso_scores = -iso.decision_function(X_test_s)           # higher = more anomalous
    try:
        iso_auc = roc_auc_score(y_test, iso_scores)
        print(f"      IsolationForest  AUC-ROC: {iso_auc:.4f}")
    except Exception:
        pass
    print("      Classification report:")
    print(classification_report(y_test, iso_bin, target_names=['Normal', 'Fraud'],
                                 digits=3, zero_division=0))

    # ── Random Forest ─────────────────────────────────────────────────
    print("[4/5] Training Random Forest (supervised) ...")
    rf = RandomForestClassifier(
        n_estimators=150,
        max_depth=12,
        min_samples_leaf=5,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X_train_s, y_train)

    rf_pred = rf.predict(X_test_s)
    rf_proba = rf.predict_proba(X_test_s)[:, 1]
    rf_auc = roc_auc_score(y_test, rf_proba)
    print(f"      RandomForest       AUC-ROC: {rf_auc:.4f}")
    print("      Classification report:")
    print(classification_report(y_test, rf_pred, target_names=['Normal', 'Fraud'],
                                 digits=3, zero_division=0))

    # Feature importance
    importances = sorted(
        zip(FEATURE_NAMES, rf.feature_importances_),
        key=lambda x: x[1], reverse=True,
    )
    print("      Top feature importances:")
    for fname, imp in importances[:5]:
        print(f"        {fname:<25s}  {imp:.4f}")

    # ── Save ─────────────────────────────────────────────────────────
    print("[5/5] Saving models ...")
    joblib.dump(iso,    os.path.join(model_dir, 'fraud_model.pkl'))
    joblib.dump(rf,     os.path.join(model_dir, 'rf_classifier.pkl'))
    joblib.dump(scaler, os.path.join(model_dir, 'scaler.pkl'))

    print(f"\n      Saved to: {model_dir}")
    print("=" * 60)
    print("Training complete!")
    return True


if __name__ == '__main__':
    train_models()
