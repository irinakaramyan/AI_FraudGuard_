# System Architecture — FraudGuard AI Detection System

**Project:** FraudGuard AI  
**Version:** 3.0  
**Last Updated:** 2026-05-04  
**Document Type:** System Architecture Document (SAD)

---

## 1. Architecture Overview

FraudGuard AI is a **modular monolith** built on the Flask microframework following the **application factory pattern**. The system integrates a machine learning fraud detection pipeline, rule-based scoring engine, OFAC sanctions screening, real-time monitoring with streaming analytics, a structured data ingestion pipeline, and a RAG-powered AI analyst assistant — all in a single deployable unit.

### 1.1 Architecture Style

| Characteristic | Decision |
|---|---|
| **Pattern** | Modular monolith (Blueprint-based decomposition) |
| **Deployment** | Single-server Flask + Gunicorn |
| **State** | Stateless API (JWT tokens, no server-side sessions) |
| **Database** | Single MySQL instance (relational, ACID) |
| **Background jobs** | In-process APScheduler thread |
| **Frontend** | Single-Page Application (Vanilla JS, no framework) |
| **ML model** | Pre-trained Isolation Forest, loaded from disk at startup |
| **Real-time** | Server-Sent Events (SSE) with in-memory sliding windows |
| **RAG index** | In-memory keyword index (Jaccard similarity) built at startup |

### 1.2 High-Level Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                              CLIENT TIER                               │
│                                                                        │
│  Browser (Chrome / Firefox / Edge)                                     │
│  └── Single-Page Application (Vanilla JS + Chart.js)                  │
│       ├── Dashboard        ├── Transactions    ├── Alerts              │
│       ├── Customers        ├── OFAC / Rules    ├── AI Assistant        │
│       ├── Live Demo        ├── Live Monitor    ├── Reports             │
│       └── Login + 2FA Flow                                             │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │ HTTPS (JWT Bearer token)
                                  │ SSE (text/event-stream for monitor)
                                  ▼
┌────────────────────────────────────────────────────────────────────────┐
│                           APPLICATION TIER                             │
│                                                                        │
│  Nginx (reverse proxy / TLS termination)                               │
│  └── Gunicorn (WSGI server, 4 workers)                                │
│       └── Flask Application (create_app factory)                      │
│            ├── auth_bp         /api/auth/                              │
│            ├── transactions_bp /api/transactions/                      │
│            ├── alerts_bp       /api/alerts/                            │
│            ├── dashboard_bp    /api/dashboard/                         │
│            ├── customers_bp    /api/customers/                         │
│            ├── assistant_bp    /api/assistant/                         │
│            ├── compliance_bp   /api/compliance/                        │
│            ├── reports_bp      /api/reports/                           │
│            ├── ingestion_bp    /api/ingest/        ← NEW              │
│            └── monitoring_bp   /api/monitor/       ← NEW              │
│                                                                        │
│  Background Thread (APScheduler)                                       │
│  └── OFAC SDN refresh at 02:00 UTC daily                              │
│                                                                        │
│  In-Memory State (process-local)                                       │
│  ├── MonitoringService — per-customer sliding window counters          │
│  ├── NetworkAnalyser   — device/IP → customer relationship graph       │
│  └── RAGService        — tokenised document chunk index                │
└──────────────────────┬──────────────────────────┬──────────────────────┘
                       │                          │
                       ▼                          ▼
┌──────────────────────────────┐    ┌────────────────────────────────────┐
│          DATA TIER           │    │          EXTERNAL SERVICES         │
│                              │    │                                    │
│  MySQL 8.0                   │    │  US Treasury OFAC SDN endpoint     │
│  ├── users                   │    │  (daily CSV download)              │
│  ├── transactions            │    │                                    │
│  ├── customers               │    │  Groq API (Llama 3.3 70B)          │
│  ├── fraud_alerts            │    │  (AI assistant — primary)          │
│  ├── risk_scores             │    │                                    │
│  ├── fraud_rules             │    │  Anthropic API (Claude)            │
│  ├── ofac_entries            │    │  (AI assistant — fallback)         │
│  ├── ofac_updates            │    │                                    │
│  ├── audit_logs              │    │  Google Authenticator / Authy      │
│  └── notifications           │    │  (TOTP 2FA — client-side app)      │
└──────────────────────────────┘    └────────────────────────────────────┘
```

---

## 2. Application Layer Architecture

### 2.1 Flask Blueprint Structure

Each API domain is isolated as a Flask Blueprint, enforcing separation of concerns:

```
app/
├── __init__.py              ← Application factory (create_app)
├── api/
│   ├── auth.py              ← Authentication + 2FA (auth_bp)
│   ├── transactions.py      ← Transaction submission + listing (transactions_bp)
│   ├── alerts.py            ← Alert lifecycle management (alerts_bp)
│   ├── dashboard.py         ← KPI aggregations + charts (dashboard_bp)
│   ├── customers.py         ← Customer profiles (customers_bp)
│   ├── assistant.py         ← RAG AI chat interface (assistant_bp)
│   ├── compliance.py        ← OFAC SDN search + detection rules (compliance_bp)
│   ├── reports.py           ← CSV/JSON export + compliance reports (reports_bp)
│   ├── ingestion.py         ← Data ingestion & preprocessing (ingestion_bp)
│   └── monitoring.py        ← Real-time monitoring + SSE stream (monitoring_bp)
├── models/
│   └── models.py            ← All SQLAlchemy ORM models
├── services/
│   ├── fraud_detector.py    ← Core fraud detection orchestrator
│   ├── rule_engine.py       ← Configurable rule-based scorer
│   ├── ml_service.py        ← Isolation Forest ML scorer
│   ├── ofac_service.py      ← OFAC SDN loading + fuzzy matching
│   ├── ingestion_service.py ← PII masking, normalisation, device fingerprinting
│   ├── monitoring_service.py← Sliding windows, threshold engine, network graph
│   ├── rag_service.py       ← Keyword RAG engine (Jaccard similarity retrieval)
│   ├── audit_service.py     ← Append-only audit trail
│   ├── risk_analyzer.py     ← Advanced analytics + portfolio risk
│   └── notification_service.py ← In-app notifications + SLA escalation
├── tasks/
│   └── daily_updater.py     ← APScheduler job definitions
├── utils/
│   └── security.py          ← JWT guards, @admin_required, sanitisers
├── static/
│   ├── js/app.js            ← SPA logic (2,200+ lines)
│   └── js/chart.umd.min.js  ← Chart.js (self-hosted)
└── templates/
    └── index.html           ← SPA shell (Jinja2)
```

### 2.2 Request Lifecycle

```
Browser Request
     │
     ▼
Nginx (TLS termination, static file serving)
     │
     ▼
Gunicorn (WSGI, worker selection)
     │
     ▼
Flask before_request hook
  ├── generate request_id (UUID)
  └── record start_time
     │
     ▼
JWT middleware (Flask-JWT-Extended)
  ├── Valid token → extract identity + role claims
  └── Missing/invalid → 401 Unauthorized
     │
     ▼
Blueprint route handler
  ├── @admin_required check (admin-only endpoints)
  ├── Input validation (utils/security.py)
  ├── Business logic (services/)
  ├── ORM query (SQLAlchemy)
  └── Response serialisation
     │
     ▼
Flask after_request hook
  ├── Attach security headers (CSP, X-Frame-Options, etc.)
  ├── Add X-Request-ID header
  └── Remove Server header
     │
     ▼
HTTP Response → Browser
```

---

## 3. Fraud Detection Pipeline Architecture

The core of FraudGuard AI. Every submitted transaction passes through a deterministic, multi-stage pipeline.

```
POST /api/transactions
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  [Pre-step] Ingestion Preprocessing                       │
│  ├── Field normalisation (uppercase location, trim, etc.) │
│  ├── Structuring detection ($9,500–$9,999 flagging)       │
│  ├── Feature derivation (hour, day_of_week, weekend)      │
│  └── Reject if invalid (returns 422 with quality report)  │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│              FRAUD DETECTION PIPELINE                     │
│                                                           │
│  Stage 0: Compliance Pre-Checks (Fail-Fast)               │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Age Check: DOB known?                               │  │
│  │   Age < 18 or > 100 → BLOCK (skip remaining)       │  │
│  │                                                     │  │
│  │ OFAC Screen: customer name vs SDN list              │  │
│  │   Similarity ≥ 0.80 → BLOCK (skip remaining)       │  │
│  │   Service error → BLOCK (fail-closed)               │  │
│  └─────────────────────────────────────────────────────┘  │
│                       │                                   │
│                       ▼ (if not blocked)                  │
│  Stage 1: Velocity Count                                  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Count transactions for customer in last 1 hour     │  │
│  └─────────────────────────────────────────────────────┘  │
│                       │                                   │
│                       ▼                                   │
│  Stage 2: Rule Engine                                     │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Evaluate active FraudRule records:                  │  │
│  │   HIGH_AMOUNT       (amount > threshold)            │  │
│  │   HIGH_FREQUENCY    (velocity > threshold)          │  │
│  │   HIGH_RISK_COUNTRY (location in risk list)         │  │
│  │   RAPID_SUCCESSION  (< 60s since last tx)           │  │
│  │   NEW_DEVICE        (unrecognised device_id)        │  │
│  │   ROUND_AMOUNT      (amount is a round number)      │  │
│  │                                                     │  │
│  │ rule_score = weighted_sum / total_weight            │  │
│  └─────────────────────────────────────────────────────┘  │
│                       │                                   │
│                       ▼                                   │
│  Stage 3: ML Scoring (Isolation Forest)                   │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 14-feature vector:                                  │  │
│  │   amount, hour, day_of_week, is_weekend             │  │
│  │   velocity_1h, customer_avg_amount                  │  │
│  │   amount_z_score, country_risk_score                │  │
│  │   is_high_risk_country, is_round_amount             │  │
│  │   card_type_encoded, customer_risk_level            │  │
│  │   days_since_last_tx, customer_tx_count             │  │
│  │                                                     │  │
│  │ → ml_score ∈ [0.0, 1.0]                            │  │
│  └─────────────────────────────────────────────────────┘  │
│                       │                                   │
│                       ▼                                   │
│  Stage 4: Score Aggregation                               │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ combined_score = 0.40 × rule_score                  │  │
│  │                + 0.60 × ml_score                    │  │
│  │                                                     │  │
│  │ Risk level:   critical ≥ 0.75                       │  │
│  │               high     ≥ 0.55                       │  │
│  │               medium   ≥ 0.35                       │  │
│  │               low       < 0.35                      │  │
│  └─────────────────────────────────────────────────────┘  │
│                       │                                   │
│                       ▼                                   │
│  Stage 5: Disposition                                     │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ ≥ 0.75 → status = blocked,  is_fraud = true         │  │
│  │ ≥ 0.45 → status = flagged                           │  │
│  │  < 0.45 → status = approved                         │  │
│  └─────────────────────────────────────────────────────┘  │
│                       │                                   │
│                       ▼                                   │
│  Stage 6: Persistence                                     │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Persist: RiskScore, Transaction.status              │  │
│  │ Update:  Customer.risk_level                        │  │
│  │ Create:  FraudAlert (if score ≥ 0.45)               │  │
│  │ Write:   AuditLog entry                             │  │
│  └─────────────────────────────────────────────────────┘  │
│                       │                                   │
│                       ▼                                   │
│  Stage 7: Real-Time Monitoring Feed                       │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ monitoring_service.monitor(tx_data, result)         │  │
│  │   ├── Update per-customer sliding windows           │  │
│  │   ├── Evaluate velocity/score thresholds            │  │
│  │   ├── Update network graph (device/IP)              │  │
│  │   └── Append to monitoring event feed              │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
        │
        ▼
   JSON Response to caller
   (includes monitoring result)
```

---

## 4. Authentication Architecture

### 4.1 Standard Login Flow (Analyst)

```
Browser          Flask /api/auth/login       MySQL
   │                      │                    │
   │── POST {user, pass} ─►│                    │
   │                      │── SELECT user ─────►│
   │                      │◄── user record ─────│
   │                      │                    │
   │                      │ verify password hash│
   │                      │ check lockout       │
   │                      │ update last_login   │
   │                      │                    │
   │◄── {access_token} ───│                    │
```

### 4.2 Admin 2FA Login Flow

```
Browser       Flask /api/auth/login    Flask /api/auth/2fa/verify   MySQL
   │                    │                        │                     │
   │─ POST {user, pass}─►│                        │                     │
   │                    │── SELECT admin ────────────────────────────►│
   │                    │◄── user (totp_enabled=true) ────────────────│
   │                    │                        │                     │
   │                    │ issue temp_token        │                     │
   │                    │ (_2fa_pending=true, 5m) │                     │
   │◄── {requires_2fa,  │                        │                     │
   │     temp_token} ───│                        │                     │
   │                    │                        │                     │
   │ (admin opens authenticator app)             │                     │
   │                    │                        │                     │
   │─ POST {totp_code}  │                        │                     │
   │  Bearer temp_token ──────────────────────►│                     │
   │                    │                        │ validate temp_token │
   │                    │                        │── SELECT user ─────►│
   │                    │                        │◄── totp_secret ─────│
   │                    │                        │ pyotp.verify(code)  │
   │◄────────────────────────── {access_token} ──│                     │
```

### 4.3 Token Architecture

| Token Type | Expiry | Claims | Usage |
|---|---|---|---|
| Access token | 3600 s (1 hour) | `sub`, `role`, `iat`, `exp` | All protected API calls |
| Temp 2FA token | 300 s (5 min) | `sub`, `role`, `_2fa_pending: true` | Only `/api/auth/2fa/verify` |

---

## 5. OFAC Screening Architecture

### 5.1 Daily Refresh Flow

```
APScheduler Thread (02:00 UTC)
        │
        ▼
daily_updater.py → ofac_service.refresh_ofac_list()
        │
        ├── HTTP GET → US Treasury OFAC SDN CSV endpoint
        │                   │
        │                   ├── Success: parse CSV rows
        │                   │    ├── Upsert into ofac_entries table
        │                   │    └── Write OFACUpdate (status=success)
        │                   │
        │                   └── Failure (network/HTTP error):
        │                        ├── Retry × 3 with exponential backoff
        │                        └── Write OFACUpdate (status=error)
        │                             └── Existing data preserved
        ▼
MySQL ofac_entries (last-known-good state always available)
```

### 5.2 Real-Time Screening (Per Transaction)

```
transaction.customer.name
        │
        ▼
normalise: lowercase, remove punctuation, trim
        │
        ▼
SELECT candidate entries FROM ofac_entries
WHERE tokens overlap (DB-level pre-filter)
        │
        ▼
For each candidate:
  compute Levenshtein similarity ∈ [0.0, 1.0]
        │
        ▼
best_score ≥ 0.80?
  ├── Yes → MATCH: block transaction, score=1.0
  │          flag customer.is_ofac_sanctioned=true
  │          create CRITICAL FraudAlert
  └── No  → CLEAR: continue pipeline

Service error → BLOCK (fail-closed policy)
```

---

## 6. AI Assistant Architecture (RAG-Powered)

```
Browser (Analyst)
        │
        ▼
POST /api/assistant/chat
  { message: "...", history: [...] }
        │
        ▼
Input validation (max 500 chars, history cap 20 turns)
        │
        ▼
RAG Retrieval (rag_service.get_context)
  ├── Query tokenised, stop-words removed
  ├── Jaccard similarity scored against all indexed chunks
  ├── Top-3 highest-scoring chunks selected
  └── Formatted context block prepended to user message
        │
        ▼
_detect_provider()
  ├── GROQ_API_KEY set? → use Groq (Llama 3.3 70B)
  ├── ANTHROPIC_API_KEY set? → use Anthropic (Claude)
  └── Neither → return setup instructions
        │
        ▼
Build message array:
  [system_prompt, ...conversation_history, {role:user, content:rag_context + query}]
        │
        ▼
   ┌──────────────────────┐     ┌──────────────────────────┐
   │ Groq API             │  OR │ Anthropic API            │
   │ llama-3.3-70b        │     │ claude-opus-4-6          │
   │ max_tokens: 1024     │     │ max_tokens: 1024         │
   └──────────────────────┘     └──────────────────────────┘
        │
        ▼
Response → JSON { response: "..." }

─── RAG Service Startup ────────────────────────────────────────
_warmup_rag() called in create_app():
  ├── Reads all .md files from docs/ directory
  ├── Splits each file into chunks by heading (##, ###)
  ├── Pre-tokenises each chunk (lowercase, stop-words removed)
  └── Stores as _Chunk(title, content, tokens) objects in memory

Retrieval: Jaccard(query_tokens, chunk_tokens)
  = |intersection| / |union|
  Top-3 chunks by score injected as context.
```

**System Prompt** instructs the model to act as a senior fraud analyst expert, covering AML rules, risk scoring methodology, OFAC compliance, and regulatory requirements (CTR, SAR). It also handles casual greetings.

---

## 7. Data Ingestion Architecture

```
POST /api/ingest/transaction  (or auto-triggered by POST /api/transactions)
        │
        ▼
IngestionService.preprocess_transaction(raw: dict) → PreprocessingResult
        │
        ├── Field normalisation
        │   ├── location: uppercase, trim (e.g. "us" → "US")
        │   ├── currency: uppercase, whitelist check
        │   ├── merchant_name: trim, max 120 chars
        │   └── amounts: float conversion, zero/negative rejection
        │
        ├── Feature derivation
        │   ├── hour_of_day (0–23)
        │   ├── day_of_week (0=Mon, 6=Sun)
        │   ├── is_weekend (bool)
        │   └── amount_magnitude (log10 bucketing)
        │
        ├── Structuring detection
        │   └── $9,500 ≤ amount < $10,000 → flag STRUCTURING_PATTERN
        │
        ├── Device fingerprinting
        │   └── SHA-256(device_id) → stored as hashed identifier (GDPR)
        │
        ├── PII masking (log output only)
        │   ├── email: local-part masked (j***@example.com)
        │   ├── phone: digits replaced with × (×××-×××-1234)
        │   └── IP: last octet zeroed (192.168.1.0)
        │
        └── Validation
            └── Missing required fields or invalid values
                → PreprocessingResult(is_valid=False, rejected_reason=...)

Result:
  ├── is_valid=True  → enriched data dict passed to fraud pipeline
  └── is_valid=False → 422 Unprocessable Entity with quality report
```

### Batch Ingestion Flow

```
POST /api/ingest/batch
  { records: [...up to 500 transactions...] }
        │
        ▼
For each record:
  preprocess_transaction(record)
        │
        ├── Valid → accumulate in processed list
        └── Invalid → accumulate in rejected list (with reason)
        │
        ▼
{ processed: N, rejected: M, errors: [...], quality_report: {...} }
```

---

## 8. Real-Time Monitoring Architecture

### 8.1 Component Overview

```
MonitoringService (singleton, process-local)
├── _customer_windows: Dict[customer_id, WindowSet]
│   └── WindowSet:
│       ├── count_1min  SlidingWindowCounter (60s)
│       ├── count_5min  SlidingWindowCounter (300s)
│       ├── count_1hr   SlidingWindowCounter (3600s)
│       └── amount_1hr  SlidingWindowAmount  (3600s)
│
├── _event_feed: deque(maxlen=500) — recent monitoring events
│
├── _throughput_window: SlidingWindowCounter (60s, system-wide)
│
├── ThresholdEngine — 12 configurable thresholds
│   ├── auto_block_score     (default 0.75)
│   ├── max_tx_per_minute    (default 5)
│   ├── max_tx_per_5min      (default 15)
│   ├── max_tx_per_hour      (default 60)
│   ├── max_amount_per_hour  (default $50,000)
│   ├── single_tx_alert      (default $10,000)
│   ├── max_customers_per_device (default 3)
│   └── max_customers_per_ip     (default 5)
│
└── NetworkAnalyser
    ├── _device_to_customers: Dict[device_id, Set[customer_id]]
    └── _ip_to_customers:     Dict[ip_address, Set[customer_id]]
```

### 8.2 SlidingWindowCounter

```
SlidingWindowCounter(window_seconds)
  ├── _timestamps: deque  — thread-safe with Lock
  └── Methods:
       ├── add()           — append current timestamp
       ├── count()         — evict old entries, return len(deque)
       ├── total()         — (Amount variant) sum of recent values
       └── rate_per_minute()
```

Each `add()` evicts entries outside the window before appending. O(1) amortised.

### 8.3 SSE Stream Flow

```
Browser (GET /api/monitor/stream)
        │
        ▼
Flask Response(generate(), mimetype='text/event-stream')
        │
        ├── Initial:  event: connected\ndata: {"status":"connected"}\n\n
        │
        └── Loop every `interval` seconds (default: 3s):
             data: { throughput, outcomes, system_alerts, network, ... }\n\n
                    │
                    ├── Browser: EventSource.onmessage fires
                    └── _renderMonitorSnapshot(data) updates DOM

Browser disconnect → GeneratorExit → loop breaks cleanly
```

### 8.4 Monitoring Data Flow (Per Transaction)

```
fraud_detector.analyze_transaction()
        │
        │ (after db.session.commit)
        │
        ▼
monitoring_service.monitor(tx_data, fraud_result)
        │
        ├── Update customer sliding windows (count + amount)
        ├── ThresholdEngine.evaluate(tx_data, fraud_result, windows)
        │   └── Returns list of threshold hits
        ├── NetworkAnalyser.update(device_id, ip_address, customer_id)
        │   └── Check for shared device/IP alerts
        ├── Append event to _event_feed
        └── Return monitoring_result dict → attached to API response
```

---

## 9. Authentication & RBAC Architecture

### 9.1 Role-Based Access Control

| Capability | Admin | Analyst |
|---|---|---|
| View dashboard, transactions, alerts | ✓ | ✓ |
| Submit transactions, resolve alerts | ✓ | ✓ |
| Use AI assistant, export reports | ✓ | ✓ |
| Manage detection rules | ✓ | ✗ |
| View compliance report | ✓ | ✗ |
| Update monitoring thresholds | ✓ | ✗ |
| Manage users, reset monitoring | ✓ | ✗ |
| Enable/disable 2FA | ✓ (own) | ✗ |

**Enforcement:**
- Backend: `@admin_required` decorator on all admin endpoints (raises 403 for non-admin JWT)
- Frontend: Admin-only nav items hidden via `showView()` role check; analyst redirected if URL accessed directly

---

## 10. Data Architecture

### 10.1 Entity Relationship Overview

```
users (1) ─────────────── (N) audit_logs
  │
customers (1) ──────────── (N) transactions
                                   │
                              (1) risk_scores
                              (N) fraud_alerts
                                   │
                         fraud_rules (N) ──── (evaluated per tx)

ofac_entries (N) ──── (screened against) ──── customers
ofac_updates  (audit trail for refresh jobs)
notifications (N) ──── (linked to) ──── fraud_alerts
```

### 10.2 Key Tables

| Table | Key Columns | Indexes |
|---|---|---|
| `users` | id, username, password_hash, role, totp_secret | username, email |
| `transactions` | id (UUID), customer_id, amount, status, created_at | customer_id, status, created_at |
| `customers` | id, customer_id, name, country, dob, risk_level | name, country, risk_level |
| `fraud_alerts` | id, transaction_id, type, severity, is_resolved | severity, is_resolved, created_at |
| `risk_scores` | transaction_id, rule_score, ml_score, combined_score | transaction_id |
| `ofac_entries` | id, name, sdn_type, program | name (LIKE queries) |
| `audit_logs` | id, user_id, action, resource_type, ip_address | user_id, action, created_at |

---

## 11. Security Architecture

### 11.1 Defence-in-Depth Layers

```
Layer 1: Network
  └── TLS 1.2+ (Nginx)
  └── CORS whitelist (no wildcard origins)

Layer 2: Transport
  └── Security headers on every response:
       Content-Security-Policy, X-Frame-Options,
       X-XSS-Protection, X-Content-Type-Options,
       Referrer-Policy, Permissions-Policy

Layer 3: Authentication
  └── JWT Bearer tokens (stateless, 1-hour expiry)
  └── TOTP 2FA for admin accounts (RFC 6238)
  └── Account lockout (5 failures → 15 min block)
  └── Generic error messages (no username enumeration)

Layer 4: Authorisation
  └── Role-based access: admin vs analyst
  └── @admin_required decorator on all privileged endpoints
  └── Frontend view-level role enforcement

Layer 5: Input Validation
  └── Request body size limit (2 MB)
  └── Field-level validators (amount, currency, email)
  └── ILIKE search sanitisation (wildcard injection)
  └── Parameterised queries via SQLAlchemy ORM

Layer 6: Privacy (PII)
  └── Device IDs SHA-256 hashed before storage
  └── PII masked in all log output (email, phone, IP)

Layer 7: Output Security
  └── No stack traces in API responses
  └── No internal paths or model names in errors
  └── CSV formula injection prevention (=, +, -, @ prefix)
  └── Server header removed from all responses

Layer 8: Compliance
  └── OFAC fail-closed (service error → block transaction)
  └── Append-only audit log (SOC 2 / ISO 27001)
  └── Password hashing: pbkdf2:sha256 (Werkzeug)
```

### 11.2 Secret Management

| Secret | Storage | Never in |
|---|---|---|
| SECRET_KEY | `.env` file | Source code, logs |
| JWT_SECRET_KEY | `.env` file | Source code, logs |
| MySQL password | `.env` file | Source code, logs |
| GROQ_API_KEY | `.env` file | Source code, git history |
| ANTHROPIC_API_KEY | `.env` file | Source code, git history |
| TOTP secrets | MySQL (per-user column) | Logs, API responses |

---

## 12. Performance Architecture

| Bottleneck | Mitigation |
|---|---|
| Fraud pipeline latency | Fail-fast at Stage 0 (skip ML for blocked transactions) |
| OFAC matching (7,000+ entries) | DB-level token pre-filter + Levenshtein on candidates only |
| Dashboard aggregations | 5 parallel `fetch()` calls in the browser |
| ML model load time | Loaded once at startup, cached in memory |
| Large transaction lists | Paginated (15 rows/page), indexed columns |
| CSV export performance | Row cap at 10,000; streaming response |
| Monitoring counters | In-memory deque, O(1) amortised; no DB write per event |
| SSE connections | Flask streaming response; Nginx `X-Accel-Buffering: no` |

### SLA Targets

| Operation | p95 Target |
|---|---|
| Fraud pipeline (full) | ≤ 3 seconds |
| API endpoints (no ML) | ≤ 500 ms |
| Dashboard load | ≤ 2 seconds |
| OFAC name match | ≤ 500 ms for 10K entries |
| SSE snapshot push | ≤ 3 seconds per event |

---

## 13. Integration Architecture

| System | Type | Protocol | Auth | Error Handling |
|---|---|---|---|---|
| US Treasury OFAC SDN | Outbound pull | HTTPS GET (CSV) | None (public) | 3 retries, fail-preserved |
| Groq API | Outbound push | HTTPS REST | API Key (header) | Return error to user |
| Anthropic API | Outbound push | HTTPS REST | API Key (header) | Return error to user |
| TOTP authenticator apps | Client-side only | RFC 6238 algorithm | QR code setup | ±30s clock tolerance |

### Payment Gateway Integration Point

`POST /api/transactions` is the integration boundary for external payment systems:

```
Payment Gateway
      │  POST /api/transactions
      │  Authorization: Bearer {service_account_jwt}
      │  { customer_id, amount, currency, merchant_name, ... }
      ▼
FraudGuard AI → full fraud pipeline
      │
      │  JSON { status, risk_score, rule_violations, recommendation }
      ▼
Payment Gateway (apply action: approve / flag / block)
```

---

## 14. Deployment Architecture

### 14.1 Single-Server Deployment

```
┌──────────────────────────────────────────────────────────┐
│                    Production Server                     │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Nginx                                          │    │
│  │  ├── TLS termination (Let's Encrypt / CA cert)  │    │
│  │  ├── Static files: /static/* → app/static/      │    │
│  │  └── Reverse proxy: /* → Gunicorn :8000         │    │
│  └─────────────────────────────────────────────────┘    │
│                          │                               │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Gunicorn (WSGI)                                │    │
│  │  └── 4 Flask worker processes                   │    │
│  │       └── APScheduler thread (1 per process)    │    │
│  └─────────────────────────────────────────────────┘    │
│                          │                               │
│  ┌─────────────────────────────────────────────────┐    │
│  │  MySQL 8.0                                      │    │
│  │  └── fraudguard database                        │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │  File system                                    │    │
│  │  ├── ml/fraud_model.pkl  (Isolation Forest)     │    │
│  │  ├── docs/               (RAG source documents) │    │
│  │  └── .env                (configuration secrets)│    │
│  └─────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### 14.2 Configuration Management

| Variable | Description |
|---|---|
| `FLASK_ENV` | `development` or `production` |
| `SECRET_KEY` | Flask signing key (random 64 chars) |
| `JWT_SECRET_KEY` | JWT signing key (separate from SECRET_KEY) |
| `DATABASE_URL` | MySQL connection string |
| `DB_PASSWORD` | MySQL root password |
| `CORS_ORIGINS` | Comma-separated list of allowed origins |
| `GROQ_API_KEY` | Groq API key (AI assistant primary) |
| `ANTHROPIC_API_KEY` | Anthropic API key (AI assistant fallback) |

---

## 15. Scalability Considerations

The current architecture is a **single-server monolith** suitable for the development and diploma demonstration context. The following design decisions make horizontal scaling straightforward:

| Design Decision | Scalability Path |
|---|---|
| Stateless JWT tokens | No sticky sessions — any worker handles any request |
| Blueprint + service layer separation | Each service can be extracted to a microservice |
| APScheduler in separate thread | Can be replaced with Celery + Redis for distributed jobs |
| MySQL with indexed queries | Can scale to read replicas for reporting |
| Pagination on all list endpoints | No unbounded result sets |
| ML model loaded from disk | Can be replaced with MLflow or BentoML model server |
| In-memory sliding windows | Must be replaced with Redis ZADD/ZRANGEBYSCORE for multi-worker scaling |
| RAG in-memory index | Can be replaced with a vector DB (Chroma, Qdrant) for large doc sets |

---

## 16. Architecture Decision Records

| ID | Decision | Rationale |
|---|---|---|
| ADR-01 | Modular monolith over microservices | Simpler deployment, no distributed tracing overhead for v1 |
| ADR-02 | MySQL over PostgreSQL | Wider hosting availability; ACID compliance |
| ADR-03 | JWT-only (no sessions) | Stateless — horizontal scaling without session store |
| ADR-04 | Isolation Forest (unsupervised ML) | No labelled dataset required; detects novel fraud patterns |
| ADR-05 | Fail-closed OFAC policy | Regulatory requirement; false negatives more costly |
| ADR-06 | Self-hosted Chart.js | CDN may be blocked in corporate environments |
| ADR-07 | Groq as primary AI provider | Free tier; avoids credit costs during development |
| ADR-08 | Temp JWT for 2FA flow | Avoids server-side session state while securing 2FA step |
| ADR-09 | APScheduler in-process | No external dependency (Redis/Celery) for single-server |
| ADR-10 | Vanilla JS SPA (no framework) | Zero build toolchain; direct DOM; easier to audit |
| ADR-11 | In-memory sliding windows for monitoring | No Redis dependency in v1; acceptable for single-worker dev |
| ADR-12 | Keyword RAG (Jaccard) over vector embeddings | No GPU/API dependency; fast; deterministic; sufficient for doc QA |
| ADR-13 | SSE over WebSockets for monitoring stream | SSE is simpler (HTTP only), JWT-compatible, and sufficient for 3s push |
| ADR-14 | SHA-256 device fingerprinting | GDPR compliance; irreversible anonymisation of device identifiers |
