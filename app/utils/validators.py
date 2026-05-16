"""
Input Validators  —  Comprehensive validation utilities
-------------------------------------------------------
Centralised validation logic for all domain objects:
transactions, customers, users, date ranges, and API parameters.

All validators return either a validated/coerced value or raise
ValueError with a human-readable message suitable for API error responses.

Design principles:
  • Fail fast — validate at system boundaries, trust internal data
  • Never reveal implementation details in error messages
  • All string inputs bounded and stripped
  • Numeric inputs clamped to safe ranges
"""
import re
from datetime import datetime, date, timedelta
from typing import Any

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_CURRENCIES = frozenset([
    'USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD', 'CHF', 'CNY', 'HKD', 'SGD',
    'NOK', 'SEK', 'DKK', 'NZD', 'MXN', 'BRL', 'ZAR', 'INR', 'KRW', 'TRY',
    'AED', 'SAR', 'QAR', 'KWD', 'BHD', 'OMR', 'JOD', 'EGP', 'PLN', 'CZK',
    'HUF', 'RON', 'BGN', 'HRK', 'ISK', 'ILS', 'THB', 'MYR', 'IDR', 'PHP',
])

VALID_CARD_TYPES   = frozenset(['credit', 'debit', 'prepaid'])
VALID_TX_TYPES     = frozenset(['purchase', 'transfer', 'withdrawal', 'deposit', 'refund'])
VALID_STATUSES     = frozenset(['approved', 'flagged', 'blocked', 'pending'])
VALID_RISK_LEVELS  = frozenset(['low', 'medium', 'high', 'critical'])
VALID_ROLES        = frozenset(['admin', 'analyst', 'viewer'])
VALID_SEVERITIES   = frozenset(['low', 'medium', 'high', 'critical'])

MAX_TRANSACTION_AMOUNT = 10_000_000.0
MIN_TRANSACTION_AMOUNT = 0.01
MAX_STRING_LENGTH      = 500
MAX_DATE_RANGE_DAYS    = 365

_EMAIL_RE     = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
_ISO_DATE_RE  = re.compile(r'^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?$')
_USERNAME_RE  = re.compile(r'^[a-zA-Z0-9_\-\.]{3,80}$')
_COUNTRY_RE   = re.compile(r'^[A-Z]{2,3}$')


# ── Generic Validators ────────────────────────────────────────────────────────

def validate_string(
    value: Any,
    field_name: str,
    required: bool = True,
    max_length: int = MAX_STRING_LENGTH,
    min_length: int = 0,
    strip: bool = True,
) -> str:
    """Validate and coerce a string field."""
    if value is None:
        if required:
            raise ValueError(f"'{field_name}' is required")
        return ''

    s = str(value)
    if strip:
        s = s.strip()

    if required and not s:
        raise ValueError(f"'{field_name}' cannot be empty")

    if len(s) < min_length:
        raise ValueError(f"'{field_name}' must be at least {min_length} characters")

    if len(s) > max_length:
        raise ValueError(f"'{field_name}' must not exceed {max_length} characters")

    return s


def validate_integer(
    value: Any,
    field_name: str,
    required: bool = True,
    min_val: int | None = None,
    max_val: int | None = None,
    default: int | None = None,
) -> int:
    """Validate and coerce an integer field."""
    if value is None:
        if required and default is None:
            raise ValueError(f"'{field_name}' is required")
        return default

    try:
        n = int(value)
    except (ValueError, TypeError):
        raise ValueError(f"'{field_name}' must be a whole number")

    if min_val is not None and n < min_val:
        raise ValueError(f"'{field_name}' must be at least {min_val}")
    if max_val is not None and n > max_val:
        raise ValueError(f"'{field_name}' must not exceed {max_val}")

    return n


def validate_float(
    value: Any,
    field_name: str,
    required: bool = True,
    min_val: float | None = None,
    max_val: float | None = None,
) -> float:
    """Validate and coerce a float field."""
    if value is None:
        if required:
            raise ValueError(f"'{field_name}' is required")
        return 0.0

    try:
        f = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"'{field_name}' must be a number")

    if min_val is not None and f < min_val:
        raise ValueError(f"'{field_name}' must be at least {min_val}")
    if max_val is not None and f > max_val:
        raise ValueError(f"'{field_name}' must not exceed {max_val:,.2f}")

    return f


def validate_choice(value: Any, field_name: str, choices: frozenset, required: bool = True) -> str:
    """Validate that a value is one of an allowed set."""
    if value is None:
        if required:
            raise ValueError(f"'{field_name}' is required")
        return ''

    s = str(value).strip().lower()
    if required and not s:
        raise ValueError(f"'{field_name}' is required")

    if s and s not in choices:
        raise ValueError(f"'{field_name}' must be one of: {', '.join(sorted(choices))}")

    return s


# ── Domain Validators ─────────────────────────────────────────────────────────

def validate_transaction_amount(value: Any) -> float:
    """Validate transaction amount: positive, within system limits."""
    amount = validate_float(value, 'amount', required=True, min_val=MIN_TRANSACTION_AMOUNT)
    if amount > MAX_TRANSACTION_AMOUNT:
        raise ValueError(f"Amount exceeds maximum allowed value of ${MAX_TRANSACTION_AMOUNT:,.0f}")
    return round(amount, 2)


def validate_currency(value: Any) -> str:
    """Validate ISO 4217 currency code."""
    code = validate_string(value, 'currency', required=False, max_length=3) or 'USD'
    code = code.upper()
    if code not in VALID_CURRENCIES:
        raise ValueError(f"Unsupported currency code '{code}'")
    return code


def validate_email(value: Any) -> str:
    """Validate email address format."""
    email = validate_string(value, 'email', required=True, max_length=254)
    if not _EMAIL_RE.match(email):
        raise ValueError("Invalid email address format")
    return email.lower()


def validate_username(value: Any) -> str:
    """Validate username: alphanumeric + underscore/hyphen/dot, 3–80 chars."""
    username = validate_string(value, 'username', required=True, max_length=80, min_length=3)
    if not _USERNAME_RE.match(username):
        raise ValueError("Username may only contain letters, numbers, underscores, hyphens, and dots (3–80 chars)")
    return username


def validate_password_strength(password: str) -> list[str]:
    """
    Check password against security policy.
    Returns a list of error strings (empty list = password is valid).
    """
    errors = []
    if len(password) < 8:
        errors.append("Must be at least 8 characters long")
    if not re.search(r'[A-Z]', password):
        errors.append("Must contain at least one uppercase letter")
    if not re.search(r'[a-z]', password):
        errors.append("Must contain at least one lowercase letter")
    if not re.search(r'\d', password):
        errors.append("Must contain at least one digit")
    if not re.search(r'[^a-zA-Z0-9]', password):
        errors.append("Must contain at least one special character")
    return errors


def validate_country_code(value: Any) -> str:
    """Validate ISO 3166-1 alpha-2 or alpha-3 country code."""
    code = validate_string(value, 'country', required=False, max_length=3) or 'US'
    code = code.upper()
    if not _COUNTRY_RE.match(code):
        raise ValueError("Country must be a 2–3 letter ISO country code (e.g. US, GB, EUR)")
    return code


def validate_date_of_birth(value: Any) -> date | None:
    """
    Validate date of birth.
    Must be a past date and not result in an age over 120.
    """
    if not value:
        return None

    try:
        if isinstance(value, date):
            dob = value
        else:
            dob = date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ValueError("date_of_birth must be in YYYY-MM-DD format")

    today = date.today()
    if dob > today:
        raise ValueError("date_of_birth cannot be in the future")

    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age > 120:
        raise ValueError("date_of_birth results in an implausibly old age (>120 years)")

    return dob


def validate_date_range(
    start_str: str | None,
    end_str: str | None,
    max_days: int = MAX_DATE_RANGE_DAYS,
) -> tuple[datetime, datetime]:
    """
    Parse and validate a start/end date range from string inputs.
    Defaults to the last 30 days. Caps range at max_days.
    Returns (start_dt, end_dt) as UTC datetimes.
    """
    now = datetime.utcnow()

    def _parse(s: str | None, fallback: datetime) -> datetime:
        if not s:
            return fallback
        try:
            return datetime.fromisoformat(s.strip()[:19])
        except ValueError:
            raise ValueError(f"Invalid date format '{s}'. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")

    start = _parse(start_str, now - timedelta(days=30))
    end   = _parse(end_str,   now)

    if end < start:
        start, end = end, start

    if (end - start).days > max_days:
        start = end - timedelta(days=max_days)

    return start, end


def validate_pagination(
    page_str: Any,
    per_page_str: Any,
    max_per_page: int = 100,
) -> tuple[int, int]:
    """Validate and coerce pagination parameters."""
    page     = validate_integer(page_str,     'page',     required=False, min_val=1, max_val=10_000, default=1)
    per_page = validate_integer(per_page_str, 'per_page', required=False, min_val=1, max_val=max_per_page, default=20)
    return page, per_page


def validate_risk_score(value: Any, field_name: str = 'score') -> float:
    """Validate a risk score value is between 0.0 and 1.0."""
    return validate_float(value, field_name, required=True, min_val=0.0, max_val=1.0)


# ── Batch Validator ───────────────────────────────────────────────────────────

def validate_transaction_payload(data: dict) -> dict:
    """
    Validate a full transaction submission payload.
    Returns a cleaned dict or raises ValueError on the first error.
    """
    return {
        'customer_id':        validate_string(data.get('customer_id'), 'customer_id', max_length=50),
        'amount':             validate_transaction_amount(data.get('amount')),
        'currency':           validate_currency(data.get('currency')),
        'merchant_name':      validate_string(data.get('merchant_name'), 'merchant_name', max_length=120),
        'merchant_category':  validate_string(data.get('merchant_category', 'general'), 'merchant_category', required=False, max_length=60) or 'general',
        'location':           validate_string(data.get('location', ''), 'location', required=False, max_length=100),
        'card_type':          validate_choice(data.get('card_type', 'credit'), 'card_type', VALID_CARD_TYPES, required=False) or 'credit',
        'transaction_type':   validate_choice(data.get('transaction_type', 'purchase'), 'transaction_type', VALID_TX_TYPES, required=False) or 'purchase',
        'device_id':          validate_string(data.get('device_id', 'unknown'), 'device_id', required=False, max_length=80) or 'unknown',
    }
