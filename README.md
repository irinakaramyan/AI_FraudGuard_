# FraudGuard AI

> Real-time financial fraud detection platform — ML anomaly scoring, rule engine, OFAC sanctions screening, live monitoring, and RAG-powered AI assistant.

---

## Overview

FraudGuard AI is a modular, production-grade fraud detection system built on a Flask application factory architecture. Every transaction submitted to the platform passes through a four-stage pipeline:

```
Transaction → Compliance Pre-check → Rule Engine → ML Scorer → Disposition
                    (OFAC + age)      (6 rules)   (Isolation      (approved /
                                                    Forest)        flagged /
                                                                   blocked)
```

The combined risk score is a weighted blend of rule-based scoring (40%) and ML anomaly scoring (60%), evaluated against configurable thresholds in under 3 seconds.

---

## Key Capabilities

| Capability | Implementation |
|---|---|
| ML anomaly detection | Isolation Forest · 14-feature vector · unsupervised |
| Rule engine | 6 configurable rules · weighted scoring · runtime-editable |
| Sanctions screening | US Treasury OFAC SDN list · fuzzy Levenshtein matching (≥0.80) |
| Real-time monitoring | Sliding windows (1min/5min/1hr) · SSE push · threshold engine |
| AI assistant | RAG + Groq Llama 3.3 70B · fraud-domain system prompt |
| Authentication | JWT · TOTP 2FA · brute-force lockout · RBAC |
| Data ingestion | PII masking · SHA-256 device fingerprinting · batch (500 records) |
| Reporting | CSV/JSON export · compliance report · append-only audit trail |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          CLIENT TIER                            │
│   Vanilla JS SPA · Chart.js · 10 views · no build step         │
└───────────────────────────┬─────────────────────────────────────┘
                            │  HTTPS — JWT Bearer
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       APPLICATION TIER                          │
│   Flask (create_app) — 10 Blueprints                           │
│                                                                 │
│   /api/auth          JWT login · TOTP 2FA · lockout            │
│   /api/transactions  Submit · query · analyst review           │
│   /api/alerts        Fraud alert lifecycle                      │
│   /api/dashboard     KPI aggregations · chart data             │
│   /api/customers     Risk profiles · transaction history        │
│   /api/assistant     RAG chat — Groq / Anthropic               │
│   /api/compliance    OFAC SDN search · rule management         │
│   /api/reports       CSV/JSON export · compliance metrics       │
│   /api/ingest        Preprocessing · batch ingestion           │
│   /api/monitor       SSE stream · sliding windows · network    │
│                                                                 │
│   APScheduler — OFAC SDN refresh daily at 02:00 UTC           │
└───────────────────────────┬─────────────────────────────────────┘
                            │
              ┌─────────────┴──────────────┐
              ▼                            ▼
   ┌──────────────────┐       ┌────────────────────────┐
   │   MySQL 8.0      │       │   External Services     │
   │   SQLAlchemy ORM │       │   US Treasury OFAC feed │
   │   In-memory      │       │   Groq API (free tier)  │
   │   sliding windows│       │   Anthropic Claude API  │
   └──────────────────┘       └────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vanilla JS (ES2022), HTML5, CSS3 — SPA, no build toolchain |
| Backend | Python 3.11+, Flask 3.0, Flask-JWT-Extended |
| ORM / DB | SQLAlchemy 2.0, PyMySQL, MySQL 8.0 |
| ML | scikit-learn 1.5 (Isolation Forest), NumPy, pandas, joblib |
| AI | Groq SDK (Llama 3.3 70B) · Anthropic SDK · custom Jaccard RAG |
| 2FA | PyOTP (RFC 6238 TOTP), qrcode, Pillow |
| Streaming | Server-Sent Events via Flask `stream_with_context` |
| Scheduler | APScheduler 3.10 |
| Security | Flask-CORS, Flask-Limiter, Werkzeug |
| Charts | Chart.js 4.4 (self-hosted, no CDN) |

---

## Project Structure

```
AI_FD/
├── app/
│   ├── api/                      # REST blueprints
│   │   ├── auth.py               # Login, JWT, TOTP 2FA
│   │   ├── transactions.py       # Transaction CRUD + fraud pipeline trigger
│   │   ├── alerts.py             # Alert lifecycle
│   │   ├── dashboard.py          # KPI + chart aggregations
│   │   ├── customers.py          # Customer profiles
│   │   ├── assistant.py          # RAG AI chat
│   │   ├── compliance.py         # OFAC search + rule CRUD
│   │   ├── reports.py            # CSV/JSON export + compliance report
│   │   ├── ingestion.py          # Ingestion + preprocessing API
│   │   └── monitoring.py         # Real-time monitoring + SSE
│   ├── models/
│   │   └── models.py             # All SQLAlchemy ORM models
│   ├── services/
│   │   ├── fraud_detector.py     # Detection orchestrator
│   │   ├── rule_engine.py        # Configurable rule scorer
│   │   ├── ml_service.py         # Isolation Forest scorer
│   │   ├── ofac_service.py       # SDN loading + fuzzy matching
│   │   ├── ingestion_service.py  # PII masking, normalisation, fingerprinting
│   │   ├── monitoring_service.py # Sliding windows, threshold engine, network graph
│   │   ├── rag_service.py        # Jaccard RAG engine
│   │   ├── audit_service.py      # Append-only audit trail
│   │   ├── risk_analyzer.py      # Portfolio risk analytics
│   │   └── notification_service.py
│   ├── tasks/
│   │   └── daily_updater.py      # APScheduler jobs
│   ├── utils/
│   │   └── security.py           # JWT guards, rate limiter, sanitisers
│   ├── static/
│   │   ├── css/style.css
│   │   ├── js/app.js             # SPA frontend (~2,400 lines)
│   │   └── js/chart.umd.min.js  # Chart.js (self-hosted)
│   ├── templates/
│   │   └── index.html            # SPA shell
│   └── __init__.py               # Application factory
├── ml/                           # Model training scripts
├── docs/                         # Architecture, SRS, use cases, SDLC
├── knowledge/                    # RAG knowledge base
├── .env.example
├── config.py
├── requirements.txt
├── setup_db.py                   # DB init + seed
├── simulate.py                   # Sample data generator
├── simulate_blocked.py           # Hard-block demo script
└── run.py                        # Entry point
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- MySQL 8.0+
- Git

### 1. Clone

```bash
git clone https://github.com/irinakaramyan/AI_FraudGuard_.git
cd AI_FraudGuard_
```

### 2. Virtual environment

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
```

Edit `.env` — minimum required values:

| Variable | How to set |
|---|---|
| `DB_PASSWORD` | Your MySQL root password |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `JWT_SECRET_KEY` | Same method — use a **different** value |
| `GROQ_API_KEY` | Free key from [console.groq.com](https://console.groq.com/) |

### 5. Initialise the database

```bash
python setup_db.py
```

### 6. (Optional) Seed sample data

```bash
python simulate.py
```

### 7. Start the server

```bash
python run.py
```

Navigate to **http://localhost:5000**.

---

## Default Credentials

| Username | Password | Role |
|---|---|---|
| `admin` | `admin123` | Full access — user mgmt, rules, 2FA, monitoring |
| `analyst` | `analyst123` | Analyst — alerts, transactions, reports |

> Change these immediately in any non-development environment.

---

## Detection Pipeline

### Stage 1 — Compliance Pre-check
- **Age verification** — hard-blocks transactions for customers under 18 or over 100
- **OFAC SDN screening** — fuzzy Levenshtein name match against the US Treasury sanctions list (threshold ≥ 0.80); fail-closed — if the list is unavailable, the transaction is blocked

### Stage 2 — Rule Engine
Six configurable rules, evaluated in sequence:

| Rule | Trigger |
|---|---|
| `HIGH_AMOUNT` | Single transaction exceeds configurable threshold |
| `HIGH_FREQUENCY` | Customer exceeds N transactions within the lookback window |
| `HIGH_RISK_COUNTRY` | Merchant country in the high-risk jurisdiction list |
| `RAPID_SUCCESSION` | Multiple transactions within a very short time window |
| `NEW_DEVICE` | Device not previously seen for this customer |
| `ROUND_AMOUNT` | Suspiciously round amounts (structuring indicator) |
| `STRUCTURING` | Amounts in the $9,500–$9,999 range (CTR avoidance) |

### Stage 3 — ML Scorer
Isolation Forest trained on a 14-dimensional feature vector including amount magnitude, hour-of-day, day-of-week, is_weekend, transaction velocity, device novelty, and geographic risk. Returns a normalised anomaly score in [0, 1].

### Stage 4 — Disposition
```
combined_score = (rule_score × 0.40) + (ml_score × 0.60)

≥ 0.75  →  blocked   (automatic, no analyst needed)
≥ 0.45  →  flagged   (queued for analyst review)
< 0.45  →  approved
```

---

## Real-Time Monitoring

The `/api/monitor/stream` endpoint delivers a Server-Sent Events feed — the browser connects once and receives push updates every 3 seconds without polling.

Sliding window counters (per customer, thread-safe `deque`):

| Window | Purpose |
|---|---|
| 1 minute | Burst detection |
| 5 minutes | Velocity spikes |
| 1 hour | Sustained anomaly patterns |

System-wide counters populate the Live Monitor dashboard KPIs (blocked / flagged / approved / volume / TX rate). On server startup, the last hour of database transactions is replayed into the in-memory windows to avoid a cold-start empty display.

---

## AI Assistant

Powered by **Groq Llama 3.3 70B** (free tier — 14,400 requests/day) with automatic fallback to Anthropic Claude.

Setup:
1. Create a free API key at [console.groq.com](https://console.groq.com/)
2. Add `GROQ_API_KEY=gsk_...` to `.env`
3. Restart the server

The RAG engine indexes the `docs/` directory at startup using Jaccard similarity. Relevant document chunks are injected into every chat request, grounding the model in project-specific context. Conversation history is capped at 20 turns.

---

## Two-Factor Authentication

Admin accounts support TOTP 2FA (RFC 6238 — Google Authenticator / Authy compatible):

1. Log in as `admin`
2. Open **Settings** (lock icon, sidebar bottom)
3. Scan the QR code with your authenticator app
4. Enter the 6-digit code to activate
5. All subsequent admin sessions require the TOTP code after password entry

---

## Security

| Control | Implementation |
|---|---|
| Authentication | JWT · 1-hour expiry · refresh on re-login |
| Two-factor auth | TOTP RFC 6238 (admin accounts) |
| Brute-force protection | 5 failed attempts → 15-minute lockout per IP + username |
| Role-based access | `admin` / `analyst` enforced at API and UI layers |
| SQL injection | Parameterised ORM queries · `sanitize_like()` on all ILIKE inputs |
| Security headers | CSP, X-Frame-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy |
| CORS | Strict origin whitelist — wildcard never permitted |
| Error handling | Generic messages only — no stack traces, no username enumeration |
| Input validation | All string inputs truncated and stripped |
| CSV injection | Cells prefixed with `'` when starting with `=`, `+`, `-`, `@` |
| PII masking | Email, phone, IP last octet masked in all log output |
| Device privacy | SHA-256 fingerprinting — raw identifiers never stored |

---

## API Reference

All endpoints require `Authorization: Bearer <JWT>`. Admin-only routes are marked.

### Authentication
| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login` | Password login — returns JWT or 2FA challenge |
| POST | `/api/auth/2fa/verify` | Complete 2FA with TOTP code |
| POST | `/api/auth/2fa/setup` | Generate TOTP secret + QR code |
| POST | `/api/auth/2fa/enable` | Activate 2FA after QR scan |
| POST | `/api/auth/2fa/disable` | Deactivate 2FA |

### Transactions
| Method | Path | Description |
|---|---|---|
| GET | `/api/transactions` | Paginated list with filters |
| POST | `/api/transactions` | Submit — triggers full detection pipeline |
| GET | `/api/transactions/<id>` | Detail + full risk score breakdown |
| PUT | `/api/transactions/<id>/review` | Analyst review — mark legitimate or fraud |

### Alerts
| Method | Path | Description |
|---|---|---|
| GET | `/api/alerts` | Paginated alert list |
| GET | `/api/alerts/<id>` | Alert detail + related transaction |
| PUT | `/api/alerts/<id>/resolve` | Resolve with notes |
| GET | `/api/alerts/summary` | Counts by severity and status |

### Dashboard & Reports
| Method | Path | Description |
|---|---|---|
| GET | `/api/dashboard/stats` | KPI aggregations |
| GET | `/api/dashboard/trend` | 7-day transaction trend |
| GET | `/api/reports/export` | CSV or JSON export (up to 10,000 rows) |
| GET | `/api/reports/compliance` | CTR, SAR, and OFAC compliance metrics |

### Customers
| Method | Path | Description |
|---|---|---|
| GET | `/api/customers` | List with risk-level filter |
| GET | `/api/customers/<id>` | Profile + transaction summary |

### OFAC & Compliance
| Method | Path | Description |
|---|---|---|
| GET | `/api/compliance/ofac/search` | Fuzzy SDN name search |
| GET | `/api/compliance/rules` | Active detection rules |
| PUT | `/api/compliance/rules/<id>` | Update rule threshold or toggle active state |

### Data Ingestion
| Method | Path | Description |
|---|---|---|
| POST | `/api/ingest/transaction` | Preprocess + ingest single transaction |
| POST | `/api/ingest/batch` | Batch ingest (max 500 records) |
| POST | `/api/ingest/customer` | Preprocess + ingest customer record |
| POST | `/api/ingest/device` | Fingerprint + ingest device record |
| POST | `/api/ingest/preview/transaction` | Dry-run validation — no DB write |
| GET | `/api/ingest/stats` | Data quality metrics |

### Real-Time Monitoring
| Method | Path | Description |
|---|---|---|
| GET | `/api/monitor/realtime` | Full snapshot of all monitoring metrics |
| GET | `/api/monitor/stream` | SSE live feed (3-second server push) |
| GET | `/api/monitor/events` | Recent monitoring events |
| GET | `/api/monitor/network` | Device/IP sharing analysis |
| GET | `/api/monitor/thresholds` | Active threshold configuration |
| PUT | `/api/monitor/thresholds` | Update thresholds at runtime |
| GET | `/api/monitor/customer/<id>` | Per-customer velocity stats |
| POST | `/api/monitor/reset` | Reset in-memory windows |

---

## Simulating a Blocked Transaction

```bash
python simulate_blocked.py
```

Submits an $85,000 wire transfer to Russia (`RU`) and prints the full pipeline result — compliance pre-checks, triggered rules, ML score, combined score, disposition, and alert details.

---

## Documentation

Full project documentation is in the `docs/` directory:

| Document | Contents |
|---|---|
| `system_architecture.md` | System Architecture Document (SAD) |
| `requirements.md` | Software Requirements Specification |
| `sdlc.md` | SDLC — Agile Scrum methodology |
| `use_cases.md` | Fully-dressed use cases |
| `user_stories.md` | User stories with acceptance criteria |

---

## License

MIT — free to use for educational and commercial purposes.

---

## Repository

[https://github.com/irinakaramyan/AI_FraudGuard_](https://github.com/irinakaramyan/AI_FraudGuard_)
