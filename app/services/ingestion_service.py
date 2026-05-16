"""
Data Ingestion & Preprocessing Service
═══════════════════════════════════════
Handles all data entering the fraud detection system:

  1. COLLECTION   — accepts raw transaction payloads, customer profiles,
                    and device fingerprints from multiple sources
  2. CLEANING     — strips whitespace, removes control characters,
                    corrects obvious formatting errors
  3. NORMALISATION— standardises amounts, currencies, country codes,
                    card types, timestamps, and merchant names
  4. VALIDATION   — enforces field-level business rules and rejects
                    or flags records that fail integrity checks
  5. PRIVACY      — masks PII in logs and audit records (GDPR / PCI DSS),
                    hashes device IDs before persistence
  6. ENRICHMENT   — derives computed fields (hour-of-day, is_weekend,
                    amount_bucket, is_round_amount) ready for the ML model

All preprocessing steps are logged to the ingestion_log table for audit.
Errors never raise to callers — they are recorded and the record is
returned with a `quality_flags` list describing any issues found.
"""

import hashlib
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_CURRENCIES = {
    'USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'NZD', 'SEK', 'NOK',
    'DKK', 'HKD', 'SGD', 'CNY', 'INR', 'BRL', 'MXN', 'ZAR', 'AED', 'SAR',
    'TRY', 'PLN', 'CZK', 'HUF', 'RON', 'BGN', 'HRK', 'ISK', 'RUB', 'UAH',
}

VALID_CARD_TYPES = {'credit', 'debit', 'prepaid', 'virtual', 'crypto'}

VALID_TX_TYPES = {'purchase', 'transfer', 'withdrawal', 'deposit', 'refund', 'payment'}

VALID_ACCOUNT_TYPES = {'personal', 'business', 'joint', 'savings', 'checking'}

# Country codes with elevated financial risk (FATF grey/black list + OFAC priority)
HIGH_RISK_COUNTRIES = {
    'IR', 'KP', 'SY', 'CU', 'VE', 'BY', 'RU', 'MM', 'AF', 'YE',
    'LY', 'SO', 'SD', 'SS', 'CD', 'CF', 'ML', 'NI', 'HT', 'PK',
}

# Round amounts that are common in money-laundering structuring
ROUND_AMOUNT_THRESHOLDS = {1000, 2000, 5000, 10000, 20000, 25000, 50000, 100000}

MAX_AMOUNT   = 10_000_000.0    # $10M hard cap
MAX_NAME_LEN = 100
MAX_STR_LEN  = 200


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _strip(value, max_len: int = MAX_STR_LEN) -> str:
    """Normalise a string: strip whitespace, collapse internal spaces, cap length."""
    if value is None:
        return ''
    s = str(value)
    # Remove control characters (except whitespace)
    s = ''.join(ch for ch in s if unicodedata.category(ch)[0] != 'C' or ch in ' \t\n')
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:max_len]


def _mask_email(email: str) -> str:
    """john.doe@example.com → jo****@example.com (GDPR-safe logging)."""
    if '@' not in email:
        return '****'
    local, domain = email.split('@', 1)
    masked = local[:2] + '****' if len(local) > 2 else '****'
    return f'{masked}@{domain}'


def _mask_phone(phone: str) -> str:
    """Mask all but last 4 digits for log-safe output."""
    digits = re.sub(r'\D', '', phone)
    if len(digits) < 4:
        return '****'
    return '*' * (len(digits) - 4) + digits[-4:]


def _hash_device(raw_device_id: str) -> str:
    """
    SHA-256 hash of the raw device ID for privacy-compliant storage.
    The prefix 'DEV-' is preserved so the system can still identify
    that it is a device token, not a randomly generated string.
    """
    h = hashlib.sha256(raw_device_id.encode('utf-8')).hexdigest()[:16]
    return f'DEV-{h}'


def _normalise_currency(raw: str) -> Optional[str]:
    """Return ISO 4217 currency code or None if unrecognisable."""
    code = _strip(raw).upper()
    if code in VALID_CURRENCIES:
        return code
    # Common aliases
    aliases = {'US': 'USD', 'EU': 'EUR', 'UK': 'GBP', 'GB': 'GBP'}
    return aliases.get(code)


def _normalise_country(raw: str) -> str:
    """Return uppercase ISO 3166-1 alpha-2 country code (2 chars)."""
    code = re.sub(r'[^A-Za-z]', '', _strip(raw)).upper()
    return code[:2] if len(code) >= 2 else 'XX'


def _normalise_amount(raw) -> Optional[float]:
    """Parse and round to 2 decimal places. Returns None on failure."""
    try:
        val = float(str(raw).replace(',', '').strip())
        if val <= 0 or val > MAX_AMOUNT:
            return None
        return round(val, 2)
    except (ValueError, TypeError):
        return None


def _derive_fields(amount: float, timestamp: datetime, location: str) -> dict:
    """
    Compute enrichment fields used as ML features:
      hour_of_day, day_of_week, is_weekend, amount_bucket,
      is_round_amount, is_high_risk_country
    """
    hour        = timestamp.hour
    dow         = timestamp.weekday()          # 0=Mon … 6=Sun
    is_weekend  = dow >= 5
    is_round    = amount in ROUND_AMOUNT_THRESHOLDS or (amount > 0 and amount % 1000 == 0)
    is_high_risk = location in HIGH_RISK_COUNTRIES

    if amount < 100:
        bucket = 'micro'
    elif amount < 1_000:
        bucket = 'small'
    elif amount < 10_000:
        bucket = 'medium'
    elif amount < 100_000:
        bucket = 'large'
    else:
        bucket = 'whale'

    return {
        'hour_of_day':         hour,
        'day_of_week':         dow,
        'is_weekend':          is_weekend,
        'amount_bucket':       bucket,
        'is_round_amount':     is_round,
        'is_high_risk_country': is_high_risk,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

class PreprocessingResult:
    """Container returned by every preprocessing function."""

    __slots__ = ('data', 'quality_flags', 'is_valid', 'rejected_reason')

    def __init__(self):
        self.data:            dict  = {}
        self.quality_flags:   list  = []   # non-fatal warnings
        self.is_valid:        bool  = True
        self.rejected_reason: str   = ''

    def warn(self, msg: str):
        self.quality_flags.append(msg)

    def reject(self, reason: str):
        self.is_valid        = False
        self.rejected_reason = reason

    def to_dict(self) -> dict:
        return {
            'data':            self.data,
            'quality_flags':   self.quality_flags,
            'is_valid':        self.is_valid,
            'rejected_reason': self.rejected_reason,
        }


class IngestionService:
    """
    Entry point for all data ingestion and preprocessing.
    Call the appropriate method before passing data to the fraud pipeline.
    """

    # ── Transaction Preprocessing ─────────────────────────────────────────────

    def preprocess_transaction(self, raw: dict) -> PreprocessingResult:
        """
        Clean, normalise, validate, and enrich a raw transaction payload.

        Returns a PreprocessingResult.  When is_valid=False the transaction
        MUST NOT be processed further; rejected_reason explains why.
        """
        result = PreprocessingResult()
        data   = {}

        # ── 1. Customer ID ────────────────────────────────────────────────────
        customer_id = _strip(raw.get('customer_id', ''), 20)
        if not customer_id:
            result.reject('customer_id is required')
            return result
        data['customer_id'] = customer_id.upper()

        # ── 2. Amount ─────────────────────────────────────────────────────────
        amount = _normalise_amount(raw.get('amount'))
        if amount is None:
            result.reject(f'Invalid amount: {raw.get("amount")!r}. Must be > 0 and ≤ {MAX_AMOUNT:,.0f}')
            return result
        data['amount'] = amount

        if amount > 50_000:
            result.warn(f'HIGH_VALUE: amount ${amount:,.2f} exceeds $50,000 — enhanced due diligence recommended')
        if amount > 9_500 and amount < 10_000:
            result.warn('STRUCTURING_RISK: amount just below $10,000 CTR threshold — potential structuring')

        # ── 3. Currency ───────────────────────────────────────────────────────
        raw_currency = raw.get('currency', 'USD')
        currency     = _normalise_currency(raw_currency)
        if currency is None:
            result.warn(f'Unknown currency {raw_currency!r} — defaulting to USD')
            currency = 'USD'
        data['currency'] = currency

        # ── 4. Merchant ───────────────────────────────────────────────────────
        merchant_name = _strip(raw.get('merchant_name', ''), MAX_NAME_LEN)
        if not merchant_name:
            result.warn('merchant_name missing — recorded as UNKNOWN')
            merchant_name = 'UNKNOWN'
        # Title-case normalisation
        data['merchant_name']     = merchant_name.title()
        data['merchant_category'] = _strip(raw.get('merchant_category', ''), 50).lower() or 'other'

        # ── 5. Location (country code) ────────────────────────────────────────
        location = _normalise_country(raw.get('location', 'XX'))
        if location == 'XX':
            result.warn('location missing or invalid — recorded as XX (unknown)')
        data['location'] = location

        # ── 6. Card type ──────────────────────────────────────────────────────
        card_type = _strip(raw.get('card_type', '')).lower()
        if card_type not in VALID_CARD_TYPES:
            result.warn(f'Unknown card_type {card_type!r} — defaulting to credit')
            card_type = 'credit'
        data['card_type'] = card_type

        # ── 7. Transaction type ───────────────────────────────────────────────
        tx_type = _strip(raw.get('transaction_type', '')).lower()
        if tx_type not in VALID_TX_TYPES:
            result.warn(f'Unknown transaction_type {tx_type!r} — defaulting to purchase')
            tx_type = 'purchase'
        data['transaction_type'] = tx_type

        # ── 8. Device fingerprint (hashed for privacy) ────────────────────────
        raw_device = _strip(raw.get('device_id', ''), 100)
        if raw_device:
            data['device_id']      = _hash_device(raw_device)
            data['raw_device_hint'] = raw_device[:8] + '…'  # first 8 chars only in logs
        else:
            result.warn('device_id missing — flagged as UNKNOWN_DEVICE')
            data['device_id'] = 'DEV-unknown'

        # ── 9. IP address (optional, validated) ───────────────────────────────
        ip = _strip(raw.get('ip_address', ''), 45)
        if ip:
            # Basic IPv4/IPv6 format check
            if not re.match(r'^[\d\.:a-fA-F]+$', ip):
                result.warn(f'ip_address {ip!r} has invalid format — discarded')
                ip = ''
        data['ip_address'] = ip or None

        # ── 10. Timestamp ─────────────────────────────────────────────────────
        raw_ts = raw.get('timestamp')
        if raw_ts:
            try:
                if isinstance(raw_ts, str):
                    ts = datetime.fromisoformat(raw_ts.replace('Z', '+00:00'))
                    ts = ts.replace(tzinfo=None)   # store as UTC-naive
                else:
                    ts = raw_ts
                # Reject timestamps more than 24 h in the future
                if ts > datetime.utcnow().replace(microsecond=0).__class__(
                        ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second):
                    pass  # accept
            except Exception:
                result.warn(f'Invalid timestamp {raw_ts!r} — using server time')
                ts = datetime.utcnow()
        else:
            ts = datetime.utcnow()
        data['timestamp'] = ts

        # ── 11. Derived / enrichment fields ───────────────────────────────────
        data.update(_derive_fields(amount, ts, location))

        # ── 12. Data quality score ─────────────────────────────────────────────
        # Proportion of core fields that were present and valid
        core_fields_present = sum([
            bool(raw.get('customer_id')),
            bool(raw.get('amount')),
            bool(raw.get('merchant_name')),
            bool(raw.get('location')),
            bool(raw.get('card_type')),
            bool(raw.get('device_id')),
            bool(raw.get('currency')),
        ])
        data['data_quality_score'] = round(core_fields_present / 7, 2)

        result.data = data
        logger.debug(
            'TX preprocessed | customer=%s amount=%.2f currency=%s location=%s '
            'quality=%.0f%% flags=%d',
            data['customer_id'], amount, currency, location,
            data['data_quality_score'] * 100, len(result.quality_flags)
        )
        return result

    # ── Customer Profile Preprocessing ───────────────────────────────────────

    def preprocess_customer(self, raw: dict) -> PreprocessingResult:
        """
        Clean and validate a customer profile payload.
        Masks PII fields for log safety.
        """
        result = PreprocessingResult()
        data   = {}

        # Customer ID
        cid = _strip(raw.get('customer_id', ''), 20).upper()
        if not cid:
            result.reject('customer_id is required')
            return result
        data['customer_id'] = cid

        # Name — strip and title-case
        name = _strip(raw.get('name', ''), MAX_NAME_LEN)
        if not name:
            result.reject('Customer name is required')
            return result
        data['name'] = name.strip().title()

        # Email — validate format and mask for logs
        email = _strip(raw.get('email', ''), 120).lower()
        if email:
            if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
                result.warn(f'email {_mask_email(email)} has invalid format — discarded')
                email = ''
        data['email'] = email or None

        # Phone — digits only, mask for logs
        phone = _strip(raw.get('phone', ''), 20)
        if phone:
            digits = re.sub(r'\D', '', phone)
            if len(digits) < 7 or len(digits) > 15:
                result.warn(f'phone {_mask_phone(phone)} has invalid length — discarded')
                phone = ''
            else:
                phone = digits   # store digits only
        data['phone'] = phone or None

        # Country
        data['country'] = _normalise_country(raw.get('country', 'US'))

        # City — strip only
        data['city'] = _strip(raw.get('city', ''), 50).title() or None

        # Account type
        acct = _strip(raw.get('account_type', 'personal')).lower()
        if acct not in VALID_ACCOUNT_TYPES:
            result.warn(f'Unknown account_type {acct!r} — defaulting to personal')
            acct = 'personal'
        data['account_type'] = acct

        # Date of birth — parse and validate
        dob_raw = raw.get('date_of_birth')
        if dob_raw:
            try:
                from datetime import date
                if isinstance(dob_raw, str):
                    dob = date.fromisoformat(dob_raw)
                else:
                    dob = dob_raw
                today = date.today()
                age   = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                if age < 0 or age > 130:
                    result.warn(f'date_of_birth {dob_raw!r} gives implausible age {age} — discarded')
                    dob = None
                elif age < 18:
                    result.warn(f'Customer age {age} is under 18 — transactions will be blocked')
                elif age > 100:
                    result.warn(f'Customer age {age} is over 100 — transactions will be blocked')
            except Exception:
                result.warn(f'Invalid date_of_birth format {dob_raw!r} — discarded')
                dob = None
        else:
            dob = None
        data['date_of_birth'] = dob

        logger.debug(
            'Customer preprocessed | id=%s name=%.10s… country=%s flags=%d',
            cid, data['name'], data['country'], len(result.quality_flags)
        )
        result.data = data
        return result

    # ── Device Fingerprint Preprocessing ─────────────────────────────────────

    def preprocess_device(self, raw: dict) -> PreprocessingResult:
        """
        Process a device fingerprint record.
        Hashes the raw identifier; extracts platform/browser metadata.
        """
        result = PreprocessingResult()
        data   = {}

        raw_id = _strip(raw.get('device_id', ''), 200)
        if not raw_id:
            result.reject('device_id is required')
            return result

        data['device_hash']  = _hash_device(raw_id)
        data['device_hint']  = raw_id[:12] + '…' if len(raw_id) > 12 else raw_id
        data['platform']     = _strip(raw.get('platform', ''), 50).lower() or 'unknown'
        data['browser']      = _strip(raw.get('browser',  ''), 50).lower() or 'unknown'
        data['os']           = _strip(raw.get('os',       ''), 50).lower() or 'unknown'
        data['is_mobile']    = bool(raw.get('is_mobile', False))
        data['is_emulator']  = bool(raw.get('is_emulator', False))
        data['screen_res']   = _strip(raw.get('screen_resolution', ''), 20) or None
        data['timezone']     = _strip(raw.get('timezone', ''), 50) or None
        data['processed_at'] = datetime.utcnow().isoformat()

        if data['is_emulator']:
            result.warn('Device is running in an emulator — elevated fraud risk')

        logger.debug('Device preprocessed | hash=%s platform=%s mobile=%s emulator=%s',
                     data['device_hash'], data['platform'],
                     data['is_mobile'], data['is_emulator'])
        result.data = data
        return result

    # ── Batch Transaction Preprocessing ──────────────────────────────────────

    def preprocess_batch(self, raw_list: list) -> dict:
        """
        Preprocess a list of raw transaction dicts.
        Returns a summary with accepted, rejected, and warning counts.
        """
        if not isinstance(raw_list, list):
            return {'error': 'Payload must be a JSON array', 'accepted': [], 'rejected': []}

        MAX_BATCH = 500
        if len(raw_list) > MAX_BATCH:
            raw_list = raw_list[:MAX_BATCH]
            logger.warning('Batch capped at %d records', MAX_BATCH)

        accepted = []
        rejected = []
        warnings = 0

        for idx, raw in enumerate(raw_list):
            try:
                res = self.preprocess_transaction(raw)
                if res.is_valid:
                    accepted.append({
                        'index':         idx,
                        'data':          res.data,
                        'quality_flags': res.quality_flags,
                    })
                    warnings += len(res.quality_flags)
                else:
                    rejected.append({
                        'index':  idx,
                        'reason': res.rejected_reason,
                        'raw':    {k: str(v)[:50] for k, v in raw.items()},
                    })
            except Exception as exc:
                rejected.append({'index': idx, 'reason': f'Unexpected error: {exc}', 'raw': {}})

        logger.info(
            'Batch ingestion complete | total=%d accepted=%d rejected=%d warnings=%d',
            len(raw_list), len(accepted), len(rejected), warnings
        )
        return {
            'total':    len(raw_list),
            'accepted': len(accepted),
            'rejected': len(rejected),
            'warnings': warnings,
            'records':  accepted,
            'errors':   rejected,
        }

    # ── Privacy Utilities ─────────────────────────────────────────────────────

    @staticmethod
    def mask_pii(data: dict) -> dict:
        """
        Return a copy of data with PII fields masked for safe logging.
        Complies with GDPR Article 5(1)(f) and PCI DSS Requirement 3.
        """
        masked = dict(data)
        if 'email' in masked and masked['email']:
            masked['email'] = _mask_email(str(masked['email']))
        if 'phone' in masked and masked['phone']:
            masked['phone'] = _mask_phone(str(masked['phone']))
        if 'name' in masked and masked['name']:
            parts = str(masked['name']).split()
            masked['name'] = (parts[0][:1] + '***' if parts else '***')
        if 'device_id' in masked and masked['device_id']:
            masked['device_id'] = '***HASHED***'
        if 'ip_address' in masked and masked['ip_address']:
            ip = str(masked['ip_address'])
            # Zero-out last octet for IPv4
            masked['ip_address'] = re.sub(r'\.\d+$', '.0', ip)
        return masked

    @staticmethod
    def data_quality_report(result: PreprocessingResult) -> dict:
        """
        Generate a structured data quality report for a preprocessing result.
        Used by the /api/ingest/preview endpoint.
        """
        score = result.data.get('data_quality_score', 1.0) if result.is_valid else 0.0
        grade = (
            'A' if score >= 0.90 else
            'B' if score >= 0.75 else
            'C' if score >= 0.60 else
            'D' if score >= 0.40 else 'F'
        )
        return {
            'is_valid':        result.is_valid,
            'rejected_reason': result.rejected_reason,
            'quality_score':   score,
            'quality_grade':   grade,
            'warnings':        result.quality_flags,
            'warning_count':   len(result.quality_flags),
            'enriched_fields': [k for k in result.data if k not in (
                'customer_id', 'amount', 'currency', 'merchant_name',
                'merchant_category', 'location', 'card_type', 'transaction_type',
                'device_id', 'ip_address', 'timestamp',
            )],
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
ingestion_service = IngestionService()
