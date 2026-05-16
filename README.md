# FraudGuard AI — Intelligent Fraud Detection System

A full-stack, production-grade financial fraud detection platform combining **machine learning anomaly detection**, a **rule-based engine**, **OFAC sanctions screening**, **real-time transaction monitoring**, and a **RAG-powered AI assistant** — built as a diploma-level capstone project.

---

## Features

### Core Fraud Detection
- **Isolation Forest ML model** — 14-dimensional feature vector, unsupervised anomaly scoring
- **Rule-based engine** — configurable rules: HIGH_AMOUNT, HIGH_FREQUENCY, HIGH_RISK_COUNTRY, RAPID_SUCCESSION, NEW_DEVICE, ROUND_AMOUNT
- **Weighted combined score** — rule score (40%) + ML score (60%)
- **Three-tier disposition** — `approved` / `flagged` / `blocked`
- **Age restriction compliance** — hard-blocks transactions for customers under 18 or over 100

### OFAC Sanctions Screening
- Full US Treasury SDN (Specially Designated Nationals) list integration
- **Fuzzy name matching** using Levenshtein distance (configurable threshold, default ≥ 0.80)
- **Daily automatic refresh** at 02:00 UTC via APScheduler
- **Fail-closed policy** — service unavailable → transaction blocked (never fails open)
- Searchable sanctions list with type, programme, and remarks

### Data Ingestion & Preprocessing
- Structured preprocessing pipeline for transactions, customers, and devices
- **PII masking** — email addresses, phone numbers, and IP last octet masked in logs
- **Device fingerprinting** — SHA-256 hash of raw device identifiers (GDPR-compliant)
- **Structuring detection** — flags transactions in the $9,500–$9,999 range (CTR avoidance)
- Field derivation: hour-of-day, day-of-week, is_weekend, amount_magnitude
- Batch ingestion endpoint (up to 500 records) with per-record validation and error reporting
- Data quality report: field completeness, rejection reasons, normalization stats
- Dry-run preview endpoint — validate payload without touching the database

### Real-Time Transaction Monitoring
- **Sliding window counters** (1-minute, 5-minute, 1-hour) per customer — thread-safe, in-memory
- **Velocity threshold engine** — 12 configurable thresholds evaluated after every transaction
- **Network analysis** — device-to-customer and IP-to-customer relationship graphs for fraud ring detection
- **Server-Sent Events (SSE) stream** — live push to browser every 3 seconds, no polling needed
- **System-wide alerts** — block rate spike, transaction rate surge, shared device/IP detection
- Admin threshold editor — update limits at runtime without restart

### Interactive Live Demo
- Pre-built scenarios: High-Amount Wire, Velocity Burst, OFAC Block, Age Restriction, Normal Purchase
- Loads real customer IDs from the database automatically — no hardcoded test data
- Full pipeline visualization: compliance stage → rule engine → ML scoring → disposition
- Score bars for rule score, ML score, and combined score with colour-coded thresholds
- Shows rule violations with severity and description

### AI Assistant (RAG-Powered)
- Powered by **Groq (Llama 3.3 70B)** — free tier, 14,400 req/day
- Fallback to **Anthropic Claude** (paid)
- **Retrieval-Augmented Generation (RAG)** — project documentation indexed at startup; relevant context injected into every query using Jaccard similarity
- Multi-turn conversation with full context history (capped at 20 turns)
- Expert fraud-domain system prompt: AML, KYC, PCI DSS, SAR thresholds, OFAC procedures

### Security
- **JWT authentication** with 1-hour token expiry
- **TOTP Two-Factor Authentication** for admin accounts (Google Authenticator / Authy compatible)
- **Brute-force lockout** — 5 failed attempts → 15-minute lockout per IP+username
- **Role-based access control** — admin and analyst roles enforced at both API and UI levels
- **SQL injection prevention** via `sanitize_like()` on all ILIKE queries
- **Security headers** on every response: CSP, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy
- **CORS lockdown** — configurable origin whitelist, never wildcard
- **Generic error messages** — no username enumeration, no stack trace leakage
- **Input sanitisation** — all string inputs truncated and stripped
- **CSV formula injection prevention** — cells starting with `=`, `+`, `-`, `@` are prefixed with `'`

### Dashboard & Analytics
- Real-time KPI cards: total transactions, fraud rate, open alerts, revenue at risk, customer count
- 7-day transaction trend chart (Chart.js, self-hosted)
- Risk distribution pie chart
- Alert type breakdown

### Transaction Management
- Advanced search and filter: name, amount range, country, status, risk level
- Click-through transaction detail modal with full risk score breakdown
- Mark transactions as legitimate or confirm fraud (analyst review)
- Paginated, sortable transaction list

### Customer Management
- Customer risk profiles with age verification and OFAC match flag
- Risk level automatically updated after each transaction
- Transaction history per customer with audit trail

### Compliance & Reporting
- CSV and JSON export for transactions and alerts (up to 10,000 rows)
- Compliance metrics report: CTR candidates (≥$10,000), OFAC-flagged accounts, SAR candidates
- Audit log — append-only record of all analyst and admin actions

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Vanilla JS (ES2022), HTML5, CSS3 — SPA architecture, no build step |
| **Backend** | Python 3.11+, Flask 3.0, Flask-JWT-Extended |
| **ORM** | SQLAlchemy 2.0, PyMySQL |
| **Database** | MySQL 8.0 |
| **ML Model** | scikit-learn 1.5 (Isolation Forest), NumPy, pandas, scipy, joblib |
| **2FA** | PyOTP (TOTP/RFC 6238), qrcode + Pillow |
| **AI Assistant** | Groq SDK (Llama 3.3 70B) / Anthropic SDK (Claude) + custom RAG engine |
| **Streaming** | Server-Sent Events (SSE) via Flask `Response(stream_with_context)` |
| **Scheduler** | APScheduler 3.10 |
| **Security** | Flask-CORS, Flask-Limiter, Werkzeug |
| **Charts** | Chart.js 4.4 (self-hosted) |

---

## Architecture

FraudGuard AI is a **modular monolith** using the Flask application factory pattern. It is composed of three tiers:

```
┌────────────────────────────────────────────────────────────────┐
│                         CLIENT TIER                            │
│  Browser SPA (Vanilla JS + Chart.js)                           │
│  Views: Dashboard · Transactions · Alerts · Customers ·        │
│         OFAC · AI Assistant · Live Demo · Live Monitor ·       │
│         Reports · User Mgmt · Detection Rules                  │
└──────────────────────────┬─────────────────────────────────────┘
                           │ HTTPS (JWT Bearer token)
                           ▼
┌────────────────────────────────────────────────────────────────┐
│                      APPLICATION TIER                          │
│  Flask (create_app factory) — 10 Blueprints                    │
│  ├── /api/auth/           Authentication + 2FA                 │
│  ├── /api/transactions/   Transaction CRUD + fraud trigger     │
│  ├── /api/alerts/         Alert lifecycle management           │
│  ├── /api/dashboard/      KPI aggregations + charts            │
│  ├── /api/customers/      Customer profiles                    │
│  ├── /api/assistant/      RAG AI chat                          │
│  ├── /api/compliance/     OFAC SDN search + screening          │
│  ├── /api/reports/        CSV/JSON export + compliance         │
│  ├── /api/ingest/         Data ingestion & preprocessing       │
│  └── /api/monitor/        Real-time monitoring + SSE stream    │
│                                                                │
│  Background Thread (APScheduler)                               │
│  └── OFAC SDN refresh at 02:00 UTC daily                      │
└──────────────────────────┬─────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────┐    ┌──────────────────────────────┐
│        DATA TIER         │    │       EXTERNAL SERVICES      │
│  MySQL 8.0               │    │  US Treasury OFAC SDN feed   │
│  + In-memory sliding     │    │  Groq API (Llama 3.3 70B)    │
│    window counters        │    │  Anthropic API (Claude)      │
│  + In-memory RAG index   │    │  Google Authenticator (TOTP) │
└──────────────────────────┘    └──────────────────────────────┘
```

Full architecture documentation is in [`docs/system_architecture.md`](docs/system_architecture.md).

---

## Project Structure

```
AI_FD/
├── app/
│   ├── api/                      # Flask Blueprints — REST endpoints
│   │   ├── auth.py               # Login, JWT, TOTP 2FA
│   │   ├── transactions.py       # Transaction CRUD + fraud trigger
│   │   ├── alerts.py             # Fraud alert management
│   │   ├── dashboard.py          # KPI aggregations + charts
│   │   ├── customers.py          # Customer profiles
│   │   ├── assistant.py          # RAG AI chat (Groq / Anthropic)
│   │   ├── compliance.py         # Detection rules CRUD + OFAC search
│   │   ├── reports.py            # CSV/JSON exports + compliance report
│   │   ├── ingestion.py          # Data ingestion & preprocessing API
│   │   └── monitoring.py         # Real-time monitoring + SSE stream
│   ├── models/
│   │   └── models.py             # All SQLAlchemy ORM models
│   ├── services/
│   │   ├── fraud_detector.py     # Core fraud detection orchestrator
│   │   ├── rule_engine.py        # Configurable rule-based scorer
│   │   ├── ml_service.py         # Isolation Forest ML scorer
│   │   ├── ofac_service.py       # OFAC SDN loading + fuzzy matching
│   │   ├── ingestion_service.py  # PII masking, normalisation, fingerprinting
│   │   ├── monitoring_service.py # Sliding windows, thresholds, network graph
│   │   ├── rag_service.py        # Keyword RAG engine (Jaccard similarity)
│   │   ├── audit_service.py      # Append-only audit trail
│   │   ├── risk_analyzer.py      # Advanced analytics + portfolio risk
│   │   └── notification_service.py # In-app notifications + SLA escalation
│   ├── tasks/
│   │   └── daily_updater.py      # APScheduler job definitions
│   ├── utils/
│   │   └── security.py           # JWT guards, rate limiter, sanitisers
│   ├── static/
│   │   ├── css/style.css         # Full application stylesheet
│   │   ├── js/app.js             # SPA frontend (2,200+ lines)
│   │   └── js/chart.umd.min.js   # Chart.js (self-hosted)
│   ├── templates/
│   │   └── index.html            # SPA HTML shell (Jinja2)
│   └── __init__.py               # Application factory (create_app)
├── ml/                           # ML model training scripts
├── docs/
│   ├── requirements.md           # Software Requirements Specification (IEEE 830)
│   ├── system_architecture.md    # System Architecture Document (SAD)
│   ├── sdlc.md                   # Software Development Life Cycle (Agile Scrum)
│   ├── use_cases.md              # Fully-Dressed Use Cases (Cockburn Style)
│   └── user_stories.md           # User Stories with acceptance criteria
├── knowledge/                    # Knowledge base files for RAG indexing
├── .env.example                  # Environment variable template
├── config.py                     # Flask configuration classes (dev/prod/test)
├── requirements.txt              # Pinned Python dependencies
├── setup_db.py                   # Database initialisation + seed data
├── simulate.py                   # Sample transaction data generator
├── simulate_blocked.py           # Demonstrates a hard-blocked transaction
└── run.py                        # Application entry point
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- MySQL 8.0+
- Git

### 1. Clone the repository
```bash
git clone https://github.com/irinakaramyan/AI_FraudGuard_.git
cd AI_FraudGuard_
```

### 2. Create virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env with your database credentials and API keys
```

Required values in `.env`:

| Variable | Description |
|---|---|
| `DB_PASSWORD` | Your MySQL root password |
| `SECRET_KEY` | Random 32-byte hex — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `JWT_SECRET_KEY` | Same method — use a **different** value from SECRET_KEY |
| `GROQ_API_KEY` | Free key from [console.groq.com](https://console.groq.com/) |

### 5. Set up the database
```bash
python setup_db.py
```

### 6. (Optional) Load sample data
```bash
python simulate.py
```

### 7. Run the application
```bash
python run.py
```

Open **http://localhost:5000** in your browser.

---

## Default Credentials

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | Full access — user mgmt, rules, 2FA |
| `analyst` | `analyst123` | Analyst — alerts, transactions, reports |

> **Security note:** Change these immediately in any non-development environment.

---

## AI Assistant Setup

The AI Assistant works with a **free** Groq API key — no credit card required:

1. Sign up at [console.groq.com](https://console.groq.com/)
2. Create an API key
3. Add to `.env`: `GROQ_API_KEY=gsk_xxxxxxxxxxxx`
4. Restart the server

The assistant uses **Llama 3.3 70B** with:
- A fraud-domain expert system prompt (AML, KYC, PCI DSS, OFAC)
- RAG context from the `docs/` directory — indexed at startup using Jaccard similarity
- Full multi-turn conversation history (capped at 20 turns to avoid token overflow)

---

## Two-Factor Authentication (Admin)

1. Log in as `admin`
2. Click the **lock icon** in the bottom-left sidebar
3. Scan the QR code with **Google Authenticator** or **Authy**
4. Enter the 6-digit code to activate
5. All subsequent admin logins require the TOTP code after the password

---

## API Overview

All endpoints require `Authorization: Bearer <JWT>` unless noted. Admin-only endpoints are marked with `🔒`.

### Authentication
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/login` | Login — returns JWT or 2FA challenge |
| POST | `/api/auth/2fa/verify` | Complete 2FA login with TOTP code |
| POST | `/api/auth/2fa/setup` | Generate TOTP secret + QR code |
| POST | `/api/auth/2fa/enable` | Activate 2FA after scanning QR |
| POST | `/api/auth/2fa/disable` | Deactivate 2FA |

### Transactions
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/transactions` | List transactions (filterable, paginated) |
| POST | `/api/transactions` | Submit transaction — triggers full fraud pipeline |
| GET | `/api/transactions/<id>` | Transaction detail + risk score breakdown |
| PUT | `/api/transactions/<id>/review` | Analyst review — mark legitimate or fraud |

### Alerts
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/alerts` | List fraud alerts (filterable) |
| PUT | `/api/alerts/<id>/resolve` | Resolve an alert with notes |

### Dashboard & Reports
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/dashboard/stats` | KPI aggregations |
| GET | `/api/dashboard/trend` | 7-day transaction trend |
| GET | `/api/reports/export` | Export CSV or JSON |
| GET | `/api/reports/compliance` | 🔒 Compliance metrics (CTR, SAR, OFAC) |

### Customers
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/customers` | List customers (filterable) |
| GET | `/api/customers/<id>` | Customer detail + transaction summary |

### AI Assistant
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/assistant/chat` | RAG-powered AI chat message |

### Compliance & OFAC
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/compliance/ofac/search` | Search SDN list by name |
| GET | `/api/compliance/rules` | List detection rules |
| PUT | `/api/compliance/rules/<id>` | 🔒 Update rule threshold / active state |

### Data Ingestion
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/ingest/transaction` | Ingest + preprocess a single transaction |
| POST | `/api/ingest/batch` | Ingest + preprocess up to 500 transactions |
| POST | `/api/ingest/customer` | Ingest + preprocess a customer record |
| POST | `/api/ingest/device` | Ingest + fingerprint a device record |
| POST | `/api/ingest/preview/transaction` | Dry-run — validate without writing to DB |
| GET | `/api/ingest/stats` | Data quality metrics |

### Real-Time Monitoring
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/monitor/realtime` | Polling snapshot of all monitoring metrics |
| GET | `/api/monitor/stream` | Server-Sent Events live feed (3-second push) |
| GET | `/api/monitor/events` | Recent monitoring events (last N) |
| GET | `/api/monitor/network` | Device/IP sharing analysis |
| GET | `/api/monitor/thresholds` | Active threshold configuration |
| PUT | `/api/monitor/thresholds` | 🔒 Update thresholds at runtime |
| GET | `/api/monitor/customer/<id>` | Per-customer real-time velocity stats |
| POST | `/api/monitor/reset` | 🔒 Reset in-memory windows (testing only) |

---

## Simulating a Blocked Transaction

Run the standalone script to see a hard-blocked transaction in action:

```bash
python simulate_blocked.py
```

This submits an $85,000 wire transfer to Russia (`RU`) and prints the full fraud analysis result — combined score, triggered rules, compliance pre-checks, and alert details.

---

## License

MIT License — free to use for educational and commercial purposes.

---

## Author

Built as a diploma-level capstone project demonstrating full-stack AI system design, financial compliance integration, real-time streaming analytics, and production-grade security practices.

**Repository:** https://github.com/irinakaramyan/AI_FraudGuard_
