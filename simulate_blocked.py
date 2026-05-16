"""
Blocked Transaction Demo
─────────────────────────
Submits one carefully crafted transaction that will be BLOCKED
by FraudGuard AI, then prints the full fraud analysis result.

The transaction triggers multiple red flags:
  • HIGH_AMOUNT      — $85,000 wire transfer
  • ROUND_AMOUNT     — exact round number
  • HIGH_RISK_COUNTRY — origin: Russia (RU)
  • Combined score will exceed 0.75 → status = BLOCKED

Run:
    python simulate_blocked.py
    (server must be running:  python run.py)
"""

import sys
try:
    import requests
except ImportError:
    print("requests not installed. Run: pip install requests")
    sys.exit(1)

BASE_URL  = 'http://localhost:5000'
USERNAME  = 'admin'
PASSWORD  = 'admin123'

# ─── The suspicious transaction ───────────────────────────────────────────────
BLOCKED_TRANSACTION = {
    'customer_id':        'CUST1001',
    'amount':             85000.00,        # HIGH_AMOUNT (> $10,000)
    'currency':           'USD',
    'merchant_name':      'Wire Transfer Corp',
    'merchant_category':  'money_transfer',
    'location':           'RU',            # HIGH_RISK_COUNTRY
    'card_type':          'credit',
    'transaction_type':   'transfer',
    'device_id':          'UNKNOWN-DEVICE-9x8f',  # NEW_DEVICE
}


def colour(text, code):
    return f'\033[{code}m{text}\033[0m'

red    = lambda t: colour(t, 91)
yellow = lambda t: colour(t, 93)
green  = lambda t: colour(t, 92)
cyan   = lambda t: colour(t, 96)
bold   = lambda t: colour(t, 1)


def login():
    print(bold('\n[1/3] Authenticating with FraudGuard AI...'))
    try:
        resp = requests.post(
            f'{BASE_URL}/api/auth/login',
            json={'username': USERNAME, 'password': PASSWORD},
            timeout=5,
        )
    except requests.exceptions.ConnectionError:
        print(red(f'  ERROR: Cannot connect to {BASE_URL}'))
        print('  Make sure the server is running:  python run.py')
        sys.exit(1)

    if resp.status_code == 200:
        data = resp.json()
        # Handle 2FA if enabled on admin account
        if data.get('requires_2fa'):
            print(yellow('  2FA is enabled on admin — using analyst account'))
            resp2 = requests.post(
                f'{BASE_URL}/api/auth/login',
                json={'username': 'analyst', 'password': 'analyst123'},
                timeout=5,
            )
            if resp2.status_code == 200:
                token = resp2.json()['access_token']
                print(green('  Authenticated as analyst'))
                return token
            print(red('  Login failed. Create an analyst account in the UI first.'))
            sys.exit(1)
        token = data['access_token']
        print(green(f'  Authenticated as {USERNAME}'))
        return token

    print(red(f'  Login failed: {resp.json().get("error")}'))
    sys.exit(1)


def submit_transaction(token):
    print(bold('\n[2/3] Submitting suspicious transaction...'))
    print(f'  Customer  :  {BLOCKED_TRANSACTION["customer_id"]}')
    print(f'  Amount    :  ${BLOCKED_TRANSACTION["amount"]:,.2f}')
    print(f'  Merchant  :  {BLOCKED_TRANSACTION["merchant_name"]}')
    print(f'  Location  :  {BLOCKED_TRANSACTION["location"]}  ← high-risk country')
    print(f'  Device    :  {BLOCKED_TRANSACTION["device_id"]}  ← unknown device')

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type':  'application/json',
    }
    resp = requests.post(
        f'{BASE_URL}/api/transactions',
        headers=headers,
        json=BLOCKED_TRANSACTION,
        timeout=15,
    )

    if resp.status_code not in (200, 201):
        print(red(f'  Submission failed ({resp.status_code}): {resp.text[:200]}'))
        sys.exit(1)

    return resp.json()


def display_result(result):
    print(bold('\n[3/3] Fraud Analysis Result'))
    print('─' * 56)

    analysis = result.get('fraud_analysis', result)
    status   = analysis.get('status', '?').upper()
    tx_id    = result.get('transaction_id') or result.get('id', '—')

    # Status banner
    if status == 'BLOCKED':
        print(red(f'  STATUS : ██ BLOCKED ██'))
    elif status == 'FLAGGED':
        print(yellow(f'  STATUS : ▲ FLAGGED'))
    else:
        print(green(f'  STATUS : ✓ APPROVED'))

    print(f'  TX ID  : {tx_id}')

    # Risk scores
    scores = analysis.get('risk_score', {})
    if scores:
        rule_score = scores.get('rule_score', 0)
        ml_score   = scores.get('ml_score', 0)
        combined   = scores.get('combined_score', 0)
        risk_level = scores.get('risk_level', '?').upper()

        print()
        print(bold('  Risk Scores:'))
        print(f'    Rule score   : {rule_score:.1%}  (40% weight)')
        print(f'    ML score     : {ml_score:.1%}  (60% weight)')
        bar = '█' * int(combined * 30)
        colour_fn = red if combined >= 0.75 else yellow if combined >= 0.45 else green
        print(f'    Combined     : {colour_fn(f"{combined:.1%}")}  {colour_fn(bar)}')
        print(f'    Risk level   : {red(risk_level) if risk_level == "CRITICAL" else yellow(risk_level)}')

    # Rule violations
    violations = analysis.get('violations', [])
    if violations:
        print()
        print(bold('  Rules Triggered:'))
        for v in violations:
            rule = v.get('rule') or v.get('type', '?')
            desc = v.get('description') or v.get('message', '')
            print(f'    {red("✗")} {rule}: {desc}')

    # Recommendation
    recommendation = analysis.get('recommendation', '')
    if recommendation:
        print()
        print(bold('  Recommendation:'))
        print(f'    {recommendation}')

    print()
    print('─' * 56)

    if status == 'BLOCKED':
        print(red(bold('  Transaction BLOCKED by FraudGuard AI.')))
        print('  A CRITICAL alert has been created in the alerts panel.')
        print('  Log in to the dashboard to review the full details.')
    print()


if __name__ == '__main__':
    print(bold(cyan('\n  FraudGuard AI — Blocked Transaction Demo')))
    print(cyan('  =========================================='))

    token  = login()
    result = submit_transaction(token)
    display_result(result)
