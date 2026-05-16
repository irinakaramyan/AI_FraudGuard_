"""
Live Transaction Simulator
---------------------------
Submits randomised transactions to the running API to demonstrate real-time
fraud detection.

Usage:
    python simulate.py                  # 20 transactions, 30 % fraud rate
    python simulate.py --count 50       # 50 transactions
    python simulate.py --count 100 --fraud-rate 0.4 --interval 0.3
"""
import argparse
import random
import sys
import time

try:
    import requests
except ImportError:
    print("requests library not found. Run:  pip install requests")
    sys.exit(1)

BASE_URL = 'http://localhost:5000'
TOKEN = None

# ─── Merchants ──────────────────────────────────────────────────────────────
NORMAL_MERCHANTS = [
    ('Amazon',       'retail'),
    ('Walmart',      'retail'),
    ('Target',       'retail'),
    ('Starbucks',    'food'),
    ("McDonald's",   'food'),
    ('Netflix',      'entertainment'),
    ('Shell Gas',    'fuel'),
    ('CVS Pharmacy', 'pharmacy'),
    ('Best Buy',     'electronics'),
    ('Uber',         'transport'),
    ('Airbnb',       'travel'),
    ('Spotify',      'entertainment'),
]

FRAUD_MERCHANTS = [
    ('Crypto Exchange', 'cryptocurrency'),
    ('BetMGM Casino',  'gambling'),
    ('Western Union',  'money_transfer'),
    ('Unnamed ATM',    'withdrawal'),
    ('Online Casino',  'gambling'),
]

LOCATIONS = ['US', 'UK', 'CA', 'AU', 'DE', 'FR', 'NG', 'RU', 'CN', 'BR', 'IN', 'ZA']
CUSTOMER_IDS = [f'CUST{i}' for i in range(1001, 1021)]

STATUS_ICON = {'approved': '✓', 'flagged': '!', 'blocked': '✗'}
SEVERITY_COLOUR = {'critical': '\033[91m', 'high': '\033[93m',
                   'medium': '\033[94m', 'low': '\033[92m', '': ''}
RESET = '\033[0m'


def login(username='admin', password='admin123') -> bool:
    global TOKEN
    try:
        resp = requests.post(
            f'{BASE_URL}/api/auth/login',
            json={'username': username, 'password': password},
            timeout=5,
        )
        if resp.status_code == 200:
            TOKEN = resp.json()['access_token']
            print(f"[✓] Authenticated as {username}")
            return True
        print(f"[✗] Login failed: {resp.json().get('error')}")
    except requests.exceptions.ConnectionError:
        print(f"[✗] Cannot connect to {BASE_URL}. Is the server running? (python run.py)")
    return False


def _headers():
    return {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}


def _normal_tx() -> dict:
    cid = random.choice(CUSTOMER_IDS)
    merchant, cat = random.choice(NORMAL_MERCHANTS)
    amount = round(random.uniform(10, 600), 2)
    return dict(customer_id=cid, amount=amount, merchant_name=merchant,
                merchant_category=cat, location='US',
                card_type=random.choice(['credit', 'debit']),
                transaction_type='purchase')


def _fraud_tx() -> dict:
    cid = random.choice(CUSTOMER_IDS)
    scenario = random.randint(1, 4)

    if scenario == 1:   # large international transfer
        merchant, cat = 'Wire Transfer', 'money_transfer'
        amount = round(random.uniform(15_000, 90_000), 2)
        location = random.choice([l for l in LOCATIONS if l != 'US'])
    elif scenario == 2:  # high-risk merchant (crypto/gambling)
        merchant, cat = random.choice(FRAUD_MERCHANTS)
        amount = round(random.uniform(500, 8_000), 2)
        location = random.choice(LOCATIONS)
    elif scenario == 3:  # suspicious round amount
        amount = float(random.choice([5000, 10000, 25000, 50000]))
        merchant, cat = 'ATM Withdrawal', 'withdrawal'
        location = random.choice(LOCATIONS)
    else:               # normal-looking but international
        merchant, cat = random.choice(NORMAL_MERCHANTS)
        amount = round(random.uniform(300, 3_000), 2)
        location = random.choice([l for l in LOCATIONS if l != 'US'])

    return dict(customer_id=cid, amount=amount, merchant_name=merchant,
                merchant_category=cat, location=location,
                card_type='credit', transaction_type='purchase')


def submit(payload: dict) -> dict | None:
    try:
        resp = requests.post(
            f'{BASE_URL}/api/transactions',
            headers=_headers(),
            json=payload,
            timeout=10,
        )
        if resp.status_code == 201:
            return resp.json()
        print(f"  [ERR] {resp.status_code}: {resp.text[:120]}")
    except Exception as exc:
        print(f"  [ERR] {exc}")
    return None


def run(count: int = 20, fraud_rate: float = 0.30, interval: float = 0.5):
    if not login():
        return

    print(f"\n{'='*62}")
    print(f"  Simulating {count} transactions  |  Fraud rate: {fraud_rate:.0%}  |  Interval: {interval}s")
    print(f"{'='*62}")
    print(f"  {'#':>4}  {'Type':8}  {'Status':8}  {'Score':>7}  {'Amount':>12}  Merchant")
    print(f"  {'-'*58}")

    stats = {'total': 0, 'approved': 0, 'flagged': 0, 'blocked': 0, 'errors': 0}

    for i in range(1, count + 1):
        is_fraud_attempt = random.random() < fraud_rate
        payload = _fraud_tx() if is_fraud_attempt else _normal_tx()
        label = '[FRAUD]' if is_fraud_attempt else '[NORMAL]'

        result = submit(payload)
        if not result:
            stats['errors'] += 1
            print(f"  {i:>4}  {label:8}  ERROR")
            continue

        analysis = result.get('fraud_analysis', {})
        status = analysis.get('status', '?')
        score = analysis.get('risk_score', {}).get('combined_score', 0)
        icon = STATUS_ICON.get(status, '?')
        amount = payload['amount']
        merchant = payload['merchant_name']

        stats['total'] += 1
        stats[status] = stats.get(status, 0) + 1

        # Colour-code by status
        colour = '\033[91m' if status == 'blocked' else '\033[93m' if status == 'flagged' else '\033[92m'
        print(
            f"  {i:>4}  {label:8}  {colour}{icon} {status:6}{RESET}  "
            f"{score:>6.1%}  ${amount:>11,.2f}  {merchant}"
        )

        if interval > 0:
            time.sleep(interval)

    print(f"\n{'='*62}")
    print(f"  Results: {stats['total']} processed  |  "
          f"\033[92m{stats.get('approved',0)} approved\033[0m  |  "
          f"\033[93m{stats.get('flagged',0)} flagged\033[0m  |  "
          f"\033[91m{stats.get('blocked',0)} blocked\033[0m  |  "
          f"{stats.get('errors',0)} errors")
    print(f"{'='*62}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='AI Fraud Detection — Transaction Simulator')
    parser.add_argument('--count',      type=int,   default=20,  help='Number of transactions to submit')
    parser.add_argument('--fraud-rate', type=float, default=0.30, help='Fraction of fraudulent transactions (0–1)')
    parser.add_argument('--interval',   type=float, default=0.50, help='Seconds to pause between submissions')
    args = parser.parse_args()

    run(count=args.count, fraud_rate=args.fraud_rate, interval=args.interval)
