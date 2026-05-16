"""
Database Setup & Seed Script
==============================
Run once before starting the server:

    python setup_db.py

Steps performed:
  1. Create MySQL database (if it doesn't exist)
  2. Create all tables
  3. Create default users (admin / analyst)
  4. Insert fraud rules
  5. Insert sample customers
  6. Train ML models
  7. Generate 200 historical transactions with fraud detection applied
"""
import os
import sys
import random
import uuid
from datetime import datetime, timedelta, date

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# 1.  Create the MySQL database schema (if missing)
# ---------------------------------------------------------------------------
def create_database_if_missing():
    import pymysql
    from config import Config

    cfg = Config()
    try:
        conn = pymysql.connect(
            host=cfg.DB_HOST,
            port=int(cfg.DB_PORT),
            user=cfg.DB_USER,
            password=cfg.DB_PASSWORD,
        )
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{cfg.DB_NAME}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        conn.close()
        print(f"[DB] Database '{cfg.DB_NAME}' ready.")
        return True
    except Exception as exc:
        print(f"\n[ERROR] Cannot connect to MySQL: {exc}")
        print(
            "\nTroubleshooting:\n"
            "  • Make sure MySQL is running (port 3306 by default)\n"
            "  • Check DB_USER / DB_PASSWORD in the .env file\n"
            "  • Default .env has DB_PASSWORD= (empty) for root with no password\n"
        )
        return False


# ---------------------------------------------------------------------------
# 2. Create tables + seed reference data
# ---------------------------------------------------------------------------
def setup_database(app):
    from app.models.models import db, User, Customer, FraudRule
    from sqlalchemy import text

    with app.app_context():
        print("[DB] Creating tables …")
        db.create_all()
        print("[DB] Tables created / verified.")

        # ── Add new columns if they don't exist (idempotent migration) ────────
        new_columns = [
            ("customers", "date_of_birth",      "ALTER TABLE customers ADD COLUMN date_of_birth DATE"),
            ("customers", "is_ofac_sanctioned",  "ALTER TABLE customers ADD COLUMN is_ofac_sanctioned TINYINT(1) NOT NULL DEFAULT 0"),
        ]
        with db.engine.connect() as conn:
            for table, col, sql in new_columns:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                    print(f"[DB] Column '{col}' added to '{table}'.")
                except Exception:
                    pass  # Column already exists — safe to ignore

        # ── Users ────────────────────────────────────────────────────
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@frauddetect.local', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)

            analyst = User(username='analyst', email='analyst@frauddetect.local', role='analyst')
            analyst.set_password('analyst123')
            db.session.add(analyst)

            viewer = User(username='viewer', email='viewer@frauddetect.local', role='viewer')
            viewer.set_password('viewer123')
            db.session.add(viewer)

            db.session.commit()
            print("[DB] Users created  →  admin/admin123  |  analyst/analyst123  |  viewer/viewer123")
        else:
            print("[DB] Users already exist — skipped.")

        # ── Fraud rules ──────────────────────────────────────────────
        if FraudRule.query.count() == 0:
            rules = [
                dict(
                    rule_name='LARGE_AMOUNT',
                    description='Transaction amount exceeds the large-amount threshold',
                    rule_type='threshold',
                    threshold=10_000.0,
                    weight=0.35,
                ),
                dict(
                    rule_name='UNUSUAL_HOURS',
                    description='Transaction placed between 1 AM and 5 AM (local bank time)',
                    rule_type='time',
                    threshold=None,
                    weight=0.20,
                ),
                dict(
                    rule_name='HIGH_FREQUENCY',
                    description='More than N transactions from the same customer within one hour',
                    rule_type='frequency',
                    threshold=5.0,
                    weight=0.30,
                ),
                dict(
                    rule_name='INTERNATIONAL_TRANSACTION',
                    description='Transaction origin differs from customer home country',
                    rule_type='location',
                    threshold=None,
                    weight=0.25,
                ),
                dict(
                    rule_name='ROUND_AMOUNT',
                    description='Transaction amount is a suspiciously round number ≥ threshold',
                    rule_type='pattern',
                    threshold=1_000.0,
                    weight=0.15,
                ),
                dict(
                    rule_name='AMOUNT_DEVIATION',
                    description='Amount deviates more than N x the customer historical average',
                    rule_type='statistical',
                    threshold=3.0,   # 300 % deviation
                    weight=0.25,
                ),
                dict(
                    rule_name='AGE_RESTRICTION',
                    description=(
                        'Blocks transactions for customers under 18 (minors) or '
                        'over 100 years old (likely identity fraud / data error). '
                        'KYC/AML compliance requirement.'
                    ),
                    rule_type='compliance',
                    threshold=None,
                    weight=1.0,       # max weight — immediate hard block
                ),
                dict(
                    rule_name='OFAC_SANCTIONS',
                    description=(
                        'Checks customer name against the OFAC Specially Designated '
                        'Nationals (SDN) list. A match is a mandatory hard block per '
                        'BSA/AML regulations. List is refreshed daily at 02:00.'
                    ),
                    rule_type='compliance',
                    threshold=None,
                    weight=1.0,       # max weight — immediate hard block
                ),
            ]
            for r in rules:
                db.session.add(FraudRule(**r))
            db.session.commit()
            print(f"[DB] Inserted {len(rules)} fraud rules.")
        else:
            print("[DB] Fraud rules already exist — skipped.")

        # ── Customers ─────────────────────────────────────────────────
        if Customer.query.count() == 0:
            # (name, country, city, acc_type, avg_tx, dob)
            # dob=None means unknown DOB — age check is skipped gracefully
            seed_data = [
                ('Alice Johnson',   'US', 'New York',     'personal',  450.0, date(1988, 3, 14)),
                ('Bob Smith',       'US', 'Los Angeles',  'personal',  320.0, date(1975, 7, 22)),
                ('Carol Williams',  'US', 'Chicago',      'business',  680.0, date(1965, 11, 5)),
                ('David Brown',     'US', 'Houston',      'personal',  890.0, date(1990, 1, 30)),
                ('Eve Davis',       'UK', 'London',       'personal',  560.0, date(1982, 9, 18)),
                ('Frank Miller',    'US', 'Phoenix',      'personal',  290.0, date(2000, 6, 12)),  # 24
                ('Grace Wilson',    'CA', 'Toronto',      'business',  720.0, date(1970, 4, 27)),
                ('Henry Moore',     'US', 'San Antonio',  'personal',  410.0, date(1955, 12, 3)),
                ('Iris Taylor',     'AU', 'Sydney',       'personal',  630.0, date(1993, 8, 9)),
                ('Jack Anderson',   'US', 'Dallas',       'business', 1200.0, date(1945, 2, 19)),
                ('Kate Thomas',     'US', 'San Jose',     'business', 1500.0, date(1978, 5, 31)),
                ('Leo Jackson',     'DE', 'Berlin',       'personal',  480.0, date(1995, 10, 7)),
                ('Mia White',       'US', 'Austin',       'personal',  350.0, date(2003, 3, 25)),  # 22
                ('Noah Harris',     'US', 'Jacksonville', 'personal',  270.0, date(1987, 7, 14)),
                ('Olivia Martin',   'FR', 'Paris',        'business',  810.0, date(1960, 1, 8)),
                ('Peter Clark',     'US', 'Columbus',     'personal',  390.0, date(1998, 11, 20)),
                ('Quinn Lewis',     'US', 'Charlotte',    'personal',  510.0, date(1972, 6, 3)),
                ('Rachel Lee',      'SG', 'Singapore',    'business',  960.0, date(1985, 9, 11)),
                ('Sam Walker',      'US', 'Seattle',      'personal',  430.0, date(2008, 4, 15)),  # 16 — MINOR, triggers AGE_RESTRICTION
                ('Tina Hall',       'JP', 'Tokyo',        'personal',  750.0, date(1919, 2, 28)),  # 106 — OVER 100, triggers AGE_RESTRICTION
            ]
            for i, (name, country, city, acc_type, avg, dob) in enumerate(seed_data):
                customer = Customer(
                    customer_id=f'CUST{1001 + i}',
                    name=name,
                    email=f"{name.lower().replace(' ', '.')}@example.com",
                    phone=f"+1-555-{random.randint(1000, 9999)}",
                    country=country,
                    city=city,
                    account_type=acc_type,
                    date_of_birth=dob,
                    avg_transaction_amount=avg,
                    risk_level=random.choice(['low', 'low', 'low', 'medium']),
                )
                db.session.add(customer)
            db.session.commit()
            print(f"[DB] Inserted {len(seed_data)} sample customers (with date_of_birth).")
            print(f"     Note: CUST1019 (Sam Walker, age 16) and CUST1020 (Tina Hall, age 106)")
            print(f"           are intentional test cases for the AGE_RESTRICTION rule.")
        else:
            print("[DB] Customers already exist — skipped.")


# ---------------------------------------------------------------------------
# 3. Seed historical transactions
# ---------------------------------------------------------------------------
def seed_transactions(app):
    from app.models.models import db, Customer, Transaction as Tx
    from app.services.fraud_detector import FraudDetector

    with app.app_context():
        if Tx.query.count() > 0:
            print("[DB] Transactions already exist — skipped.")
            return

        print("[DB] Generating 200 historical transactions …")
        customers = Customer.query.all()
        if not customers:
            print("[DB] No customers found — cannot seed transactions.")
            return

        merchants = [
            ('Amazon',          'retail'),
            ('Walmart',         'retail'),
            ('Target',          'retail'),
            ('Starbucks',       'food'),
            ("McDonald's",      'food'),
            ('Netflix',         'entertainment'),
            ('Shell Gas',       'fuel'),
            ('CVS Pharmacy',    'pharmacy'),
            ('Best Buy',        'electronics'),
            ('Home Depot',      'home'),
            ('Crypto Exchange', 'cryptocurrency'),
            ('BetMGM',          'gambling'),
            ('Western Union',   'money_transfer'),
            ('Casino Royal',    'gambling'),
            ('Uber',            'transport'),
            ('Airbnb',          'travel'),
        ]
        locations = ['US', 'UK', 'CA', 'AU', 'DE', 'FR', 'NG', 'RU', 'CN', 'BR', 'SG']

        detector = FraudDetector()
        success = 0
        errors = 0

        for i in range(200):
            customer = random.choice(customers)
            merchant_name, merchant_cat = random.choice(merchants)

            days_ago = random.randint(0, 30)
            hour = random.randint(0, 23)
            ts = datetime.utcnow() - timedelta(days=days_ago, hours=hour,
                                               minutes=random.randint(0, 59))

            is_fraud_scenario = random.random() < 0.18

            if is_fraud_scenario:
                scenario = random.choice(['large', 'intl', 'unusual_time', 'high_risk'])
                if scenario == 'large':
                    amount = round(random.uniform(12_000, 80_000), 2)
                    location = customer.country
                elif scenario == 'intl':
                    amount = round(customer.avg_transaction_amount * random.uniform(0.8, 2.5), 2)
                    location = random.choice([l for l in locations if l != customer.country])
                elif scenario == 'unusual_time':
                    amount = round(customer.avg_transaction_amount * random.uniform(1.0, 3.0), 2)
                    location = customer.country
                    ts = ts.replace(hour=random.randint(1, 4))
                else:
                    amount = round(random.choice([5000, 10000, 25000]) * 1.0, 2)
                    location = random.choice(locations)
                    merchant_name = 'Crypto Exchange'
                    merchant_cat = 'cryptocurrency'
            else:
                amount = round(customer.avg_transaction_amount * random.uniform(0.2, 1.8), 2)
                location = customer.country if random.random() > 0.08 else random.choice(locations)

            transaction = Tx(
                transaction_id=str(uuid.uuid4()),
                customer_id=customer.id,
                amount=max(0.01, amount),
                currency='USD',
                merchant_name=merchant_name,
                merchant_category=merchant_cat,
                location=location,
                ip_address=f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}",
                device_id=f"DEV-{random.randint(10000, 99999)}",
                card_type=random.choice(['credit', 'debit']),
                transaction_type=random.choice(['purchase', 'transfer', 'withdrawal']),
                timestamp=ts,
                status='pending',
            )
            db.session.add(transaction)
            db.session.flush()

            try:
                detector.analyze_transaction(transaction, customer)
                success += 1
            except Exception as exc:
                print(f"  [WARN] Transaction {i+1} error: {exc}")
                db.session.rollback()
                errors += 1

        print(f"[DB] Historical data seeded — {success} OK, {errors} skipped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print("=" * 60)
    print("  AI Fraud Detection System — Setup")
    print("=" * 60)

    # Step 1: MySQL database creation
    if not create_database_if_missing():
        sys.exit(1)

    # Step 2: Flask app + tables + seed reference data
    from app import create_app
    app = create_app('development')
    setup_database(app)

    # Step 3: Train ML models
    print("\n[ML] Training models …")
    from ml.train_model import train_models
    train_models()

    # Step 4: Seed historical transactions
    print()
    seed_transactions(app)

    print("\n" + "=" * 60)
    print("  Setup complete!")
    print()
    print("  Start the server:  python run.py")
    print("  Open browser:      http://localhost:5000")
    print()
    print("  Credentials:")
    print("    admin    / admin123")
    print("    analyst  / analyst123")
    print("    viewer   / viewer123")
    print("=" * 60)
