# Requirements Specification — FraudGuard AI Detection System

**Project:** FraudGuard AI  
**Version:** 3.0  
**Last Updated:** 2026-05-04  
**Document Type:** Software Requirements Specification (SRS)  
**Standard:** IEEE 830 / ISO/IEC 29148

---

## 1. Introduction

### 1.1 Purpose
This document defines the complete functional and non-functional requirements for FraudGuard AI — a real-time, AI-powered financial fraud detection platform combining machine learning anomaly detection, rule-based fraud rules, OFAC sanctions screening, real-time transaction monitoring with streaming analytics, a structured data ingestion pipeline, an interactive live demo, and a Retrieval-Augmented Generation (RAG) AI assistant.

### 1.2 Scope
The system covers:
- Real-time transaction fraud analysis (ML + rules)
- Regulatory compliance screening (OFAC, age restrictions, AML thresholds)
- Fraud alert lifecycle management
- Data ingestion, normalisation, and privacy-preserving preprocessing
- Real-time streaming monitoring with velocity thresholds and network analysis
- Interactive live demo for exploring the fraud pipeline
- Administrative and analyst web interface (SPA)
- RAG-powered AI assistant grounded in project documentation
- Data export and compliance reporting

### 1.3 Definitions

| Term | Definition |
|---|---|
| **SDN** | Specially Designated Nationals — OFAC's list of blocked persons and entities |
| **CTR** | Currency Transaction Report — required by FinCEN for transactions ≥ $10,000 |
| **SAR** | Suspicious Activity Report — filed for transactions ≥ $5,000 with fraud indicators |
| **AML** | Anti-Money Laundering |
| **KYC** | Know Your Customer — identity verification process |
| **TOTP** | Time-based One-Time Password — algorithm for 2FA codes (RFC 6238) |
| **JWT** | JSON Web Token — stateless authentication mechanism |
| **ML** | Machine Learning |
| **SLA** | Service Level Agreement |
| **SSE** | Server-Sent Events — HTTP-based unidirectional push from server to browser |
| **RAG** | Retrieval-Augmented Generation — LLM augmented with retrieved document context |
| **PII** | Personally Identifiable Information |
| **Structuring** | Intentionally splitting transactions to stay below CTR reporting thresholds |
| **Velocity** | The rate of transactions within a time window (per customer) |

---

## 2. Functional Requirements

### FR-01 — Authentication & Authorisation

| ID | Requirement | Priority |
|---|---|---|
| FR-01.1 | The system SHALL authenticate users with username and password | Must |
| FR-01.2 | The system SHALL support role-based access control: admin and analyst | Must |
| FR-01.3 | The system SHALL lock accounts after 5 consecutive failed login attempts for 15 minutes | Must |
| FR-01.4 | The system SHALL issue JWT tokens valid for 3600 seconds (1 hour) | Must |
| FR-01.5 | The system SHALL support TOTP two-factor authentication for admin accounts | Must |
| FR-01.6 | The system SHALL generate QR codes compatible with Google Authenticator and Authy | Must |
| FR-01.7 | The system SHALL validate TOTP codes with a ±30-second clock tolerance (1-step window) | Must |
| FR-01.8 | Admin SHALL be able to enable, disable, and verify 2FA via dedicated API endpoints | Must |
| FR-01.9 | The system SHALL never reveal in error messages whether a username exists | Must |
| FR-01.10 | The system SHALL enforce role-based view restrictions at both the API and UI level | Must |

---

### FR-02 — Transaction Processing

| ID | Requirement | Priority |
|---|---|---|
| FR-02.1 | The system SHALL accept transactions with: customer_id, amount, currency, merchant_name | Must |
| FR-02.2 | The system SHALL validate amounts: must be positive, maximum $10,000,000 | Must |
| FR-02.3 | The system SHALL validate currency codes against the ISO 4217 whitelist (50+ currencies) | Must |
| FR-02.4 | The system SHALL assign each transaction a UUID at submission time | Must |
| FR-02.5 | The system SHALL return a fraud analysis result within 3 seconds for 95% of transactions | Must |
| FR-02.6 | The system SHALL record transaction status: pending, approved, flagged, blocked | Must |
| FR-02.7 | The system SHALL allow analysts to manually review and override a transaction's status | Must |
| FR-02.8 | The system SHALL provide a paginated transaction list with filtering by status, risk level, amount range, country, and search term | Must |

---

### FR-03 — Fraud Detection Pipeline

| ID | Requirement | Priority |
|---|---|---|
| FR-03.1 | The system SHALL execute compliance pre-checks (OFAC + age) BEFORE the ML pipeline | Must |
| FR-03.2 | The system SHALL evaluate all active fraud rules and compute a weighted rule score | Must |
| FR-03.3 | The system SHALL score each transaction using a trained Isolation Forest ML model | Must |
| FR-03.4 | The system SHALL compute combined_score = 0.40 × rule_score + 0.60 × ml_score | Must |
| FR-03.5 | combined_score ≥ 0.75 SHALL result in status = blocked | Must |
| FR-03.6 | combined_score ≥ 0.45 SHALL result in status = flagged | Must |
| FR-03.7 | combined_score < 0.45 SHALL result in status = approved | Must |
| FR-03.8 | The system SHALL persist a RiskScore record for every analysed transaction | Must |
| FR-03.9 | The system SHALL generate FraudAlert records for transactions exceeding the alert threshold (0.45) | Must |
| FR-03.10 | The system SHALL support at minimum 6 configurable rule types: HIGH_AMOUNT, HIGH_FREQUENCY, HIGH_RISK_COUNTRY, RAPID_SUCCESSION, NEW_DEVICE, ROUND_AMOUNT | Must |
| FR-03.11 | Admins SHALL be able to toggle rules active/inactive and adjust thresholds without code changes | Should |

---

### FR-04 — OFAC Sanctions Compliance

| ID | Requirement | Priority |
|---|---|---|
| FR-04.1 | The system SHALL screen every customer name against the US Treasury OFAC SDN list before processing | Must |
| FR-04.2 | The system SHALL use fuzzy name matching (Levenshtein distance) with a configurable threshold (default ≥ 0.80) | Must |
| FR-04.3 | An OFAC match SHALL immediately block the transaction with combined_score = 1.0 | Must |
| FR-04.4 | The system SHALL be fail-closed: if the OFAC service is unavailable, transactions SHALL be blocked pending manual review | Must |
| FR-04.5 | The system SHALL automatically refresh the OFAC SDN list daily at 02:00 UTC | Must |
| FR-04.6 | The system SHALL log every OFAC refresh attempt with status, entry count, and timestamp | Must |
| FR-04.7 | The system SHALL flag customers with is_ofac_sanctioned = true when an OFAC match is detected | Must |
| FR-04.8 | Analysts SHALL be able to search the SDN list by name and view full SDN entry details | Must |

---

### FR-05 — Age Restriction Compliance

| ID | Requirement | Priority |
|---|---|---|
| FR-05.1 | The system SHALL block transactions from customers whose age is below 18 years | Must |
| FR-05.2 | The system SHALL block transactions from customers whose age exceeds 100 years | Must |
| FR-05.3 | The system SHALL compute age from date_of_birth at the time of each transaction | Must |
| FR-05.4 | Age violations SHALL generate a CRITICAL severity fraud alert | Must |
| FR-05.5 | If date_of_birth is unknown, the age check SHALL be skipped (not blocked) | Must |

---

### FR-06 — Alert Management

| ID | Requirement | Priority |
|---|---|---|
| FR-06.1 | The system SHALL create FraudAlert records with: type, severity, description, risk factors | Must |
| FR-06.2 | Alert severity SHALL be mapped from risk level: low → low, medium → medium, high → high, critical → critical | Must |
| FR-06.3 | Analysts SHALL be able to resolve alerts with resolution notes | Must |
| FR-06.4 | The system SHALL provide a filterable, paginated alert list | Must |
| FR-06.5 | The dashboard SHALL display the count of unresolved alerts | Should |

---

### FR-07 — AI Assistant (RAG-Powered)

| ID | Requirement | Priority |
|---|---|---|
| FR-07.1 | The system SHALL provide a conversational AI assistant powered by an external LLM API | Should |
| FR-07.2 | The assistant SHALL support multi-turn conversations with full context history | Should |
| FR-07.3 | The assistant SHALL use Groq (free) as the primary provider, with Anthropic as fallback | Should |
| FR-07.4 | User queries SHALL be limited to 500 characters | Must |
| FR-07.5 | Conversation history SHALL be capped at 20 turns to prevent token overflows | Must |
| FR-07.6 | The system SHALL implement RAG: index project documentation (markdown files) at startup | Should |
| FR-07.7 | RAG retrieval SHALL use Jaccard similarity on tokenised content with stop-word removal | Should |
| FR-07.8 | The top-3 most relevant documentation chunks SHALL be injected into each LLM prompt | Should |
| FR-07.9 | The assistant SHALL respond to casual greetings as well as technical fraud questions | Should |

---

### FR-08 — Dashboard & Reporting

| ID | Requirement | Priority |
|---|---|---|
| FR-08.1 | The dashboard SHALL display: total transactions, fraud rate, open alerts, total amount, customer count, avg risk score | Must |
| FR-08.2 | The dashboard SHALL display a 7-day transaction trend chart | Must |
| FR-08.3 | The dashboard SHALL display a risk distribution chart | Must |
| FR-08.4 | The system SHALL support CSV and JSON export for transactions and alerts | Should |
| FR-08.5 | Exports SHALL sanitise cells against formula injection (=, +, -, @ prefixes) | Must |
| FR-08.6 | The system SHALL provide a compliance metrics report covering CTR thresholds, OFAC flags, and SAR candidates | Should |
| FR-08.7 | Export row count SHALL be capped at 10,000 records per request | Must |

---

### FR-09 — Customer Management

| ID | Requirement | Priority |
|---|---|---|
| FR-09.1 | The system SHALL maintain customer profiles with: name, email, country, DOB, risk level, OFAC flag | Must |
| FR-09.2 | The system SHALL compute and store a customer risk level (low/medium/high) based on transaction history | Must |
| FR-09.3 | Customer risk level SHALL be automatically updated after each transaction analysis | Must |

---

### FR-10 — Data Ingestion & Preprocessing

| ID | Requirement | Priority |
|---|---|---|
| FR-10.1 | The system SHALL provide a dedicated ingestion API that validates and normalises transaction, customer, and device records | Must |
| FR-10.2 | The system SHALL mask PII in all logs: email domains shown, local-parts masked; phone digits replaced with ×; IP last octet replaced with 0 | Must |
| FR-10.3 | The system SHALL hash raw device identifiers using SHA-256 before storage (GDPR-compliant fingerprinting) | Must |
| FR-10.4 | The system SHALL detect structuring patterns: transactions in the $9,500–$9,999 range flagged as potential CTR avoidance | Must |
| FR-10.5 | The system SHALL derive additional features from raw input: hour_of_day, day_of_week, is_weekend, amount_magnitude | Must |
| FR-10.6 | The system SHALL support batch ingestion of up to 500 records per request with per-record validation and error reporting | Should |
| FR-10.7 | The system SHALL provide a dry-run preview endpoint that validates a payload without writing to the database | Should |
| FR-10.8 | The system SHALL report data quality metrics: field completeness, rejection rate, and per-field normalization stats | Should |
| FR-10.9 | The ingestion pipeline SHALL be integrated into the main transaction submission endpoint (auto-preprocessing) | Must |
| FR-10.10 | Rejected records SHALL include a rejection reason and a data quality report | Must |

---

### FR-11 — Real-Time Transaction Monitoring

| ID | Requirement | Priority |
|---|---|---|
| FR-11.1 | The system SHALL maintain per-customer sliding window counters for 1-minute, 5-minute, and 1-hour transaction counts | Must |
| FR-11.2 | The system SHALL maintain per-customer sliding window totals for hourly transaction amounts | Must |
| FR-11.3 | The system SHALL evaluate 12 configurable velocity and score thresholds after every transaction | Must |
| FR-11.4 | The system SHALL provide a Server-Sent Events (SSE) stream endpoint that pushes monitoring snapshots to connected browsers every 3 seconds | Must |
| FR-11.5 | The system SHALL provide a polling REST endpoint as a fallback for environments where SSE is unavailable | Must |
| FR-11.6 | The system SHALL maintain a network graph mapping device IDs and IP addresses to customer accounts | Must |
| FR-11.7 | The system SHALL detect devices shared across more than a configurable number of accounts (default: 3) and generate a fraud ring alert | Must |
| FR-11.8 | The system SHALL detect IP addresses shared across more than a configurable number of accounts (default: 5) | Must |
| FR-11.9 | Admins SHALL be able to update threshold values at runtime via the PUT /api/monitor/thresholds endpoint without restarting the server | Should |
| FR-11.10 | The system SHALL provide per-customer real-time velocity stats and threshold comparison via a dedicated endpoint | Should |
| FR-11.11 | The monitoring service SHALL be thread-safe: all sliding windows SHALL use locking to prevent race conditions | Must |
| FR-11.12 | The system SHALL emit system-level alerts for: block rate spike above threshold, transaction rate surge | Should |

---

### FR-12 — Interactive Live Demo

| ID | Requirement | Priority |
|---|---|---|
| FR-12.1 | The system SHALL provide an interactive demo page that lets users submit pre-built fraud scenarios | Should |
| FR-12.2 | The demo SHALL include at minimum 5 scenarios: High-Amount Wire, OFAC Block, Velocity Burst, Age Restriction, Normal Purchase | Should |
| FR-12.3 | The demo SHALL automatically load real customer IDs from the database so scenarios always use valid data | Must |
| FR-12.4 | The demo SHALL display a real-time pipeline visualisation showing which stages were executed and which were skipped | Should |
| FR-12.5 | The demo SHALL display score bars for rule score, ML score, and combined score with colour-coded thresholds | Should |
| FR-12.6 | The demo SHALL list triggered rule violations with severity and description | Should |
| FR-12.7 | The demo form SHALL allow users to edit any scenario field before running it | Should |

---

## 3. Non-Functional Requirements

### NFR-01 — Performance

| ID | Requirement | Target |
|---|---|---|
| NFR-01.1 | Fraud analysis pipeline latency (p95) | ≤ 3 seconds |
| NFR-01.2 | API endpoint response time (p95, excluding ML) | ≤ 500 ms |
| NFR-01.3 | Dashboard load time (cold) | ≤ 2 seconds |
| NFR-01.4 | Maximum concurrent users (development) | 50 |
| NFR-01.5 | Database query time (p99) | ≤ 200 ms |
| NFR-01.6 | OFAC name match query | ≤ 500 ms for 10,000 entries |
| NFR-01.7 | SSE stream push interval | ≤ 3 seconds per snapshot |
| NFR-01.8 | Sliding window counter update | ≤ 1 ms (in-memory, O(1) amortised) |

---

### NFR-02 — Security

| ID | Requirement | Standard/Reference |
|---|---|---|
| NFR-02.1 | All endpoints SHALL require a valid JWT Bearer token (except /login) | RFC 7519 |
| NFR-02.2 | All HTTP responses SHALL include security headers: CSP, X-Frame-Options, X-XSS-Protection, X-Content-Type-Options, Referrer-Policy, Permissions-Policy | OWASP |
| NFR-02.3 | CORS SHALL be restricted to explicitly configured origin whitelist | OWASP |
| NFR-02.4 | All database queries using user input SHALL use parameterised queries or ORM-level escaping | OWASP A03 |
| NFR-02.5 | ILIKE search terms SHALL be sanitised to prevent wildcard injection | OWASP A03 |
| NFR-02.6 | Passwords SHALL be stored as pbkdf2:sha256 hashes (Werkzeug default) | NIST SP 800-63B |
| NFR-02.7 | Stack traces and internal error details SHALL never be returned in API responses | OWASP A05 |
| NFR-02.8 | The OFAC screening service SHALL be fail-closed (error → block) | Regulatory |
| NFR-02.9 | All audit-relevant actions SHALL be recorded in an immutable append-only audit log | SOC 2 |
| NFR-02.10 | Brute-force protection SHALL be enforced on the login endpoint | OWASP A07 |
| NFR-02.11 | CSV exports SHALL sanitise against formula injection attacks | OWASP |
| NFR-02.12 | PII (email, phone, IP) SHALL be masked in all log output | GDPR / Privacy |
| NFR-02.13 | Device identifiers SHALL be SHA-256 hashed before storage | GDPR / Privacy |
| NFR-02.14 | Admin-only API endpoints SHALL be protected by the @admin_required decorator | RBAC |

---

### NFR-03 — Reliability & Availability

| ID | Requirement | Target |
|---|---|---|
| NFR-03.1 | System availability (development) | ≥ 99% |
| NFR-03.2 | OFAC refresh SHALL retry on failure with exponential backoff | 3 retries |
| NFR-03.3 | ML model unavailability SHALL not crash the system; rule score used alone | Graceful degradation |
| NFR-03.4 | Database connection failures SHALL return 503 with a generic message | Fail safe |
| NFR-03.5 | Audit log failures SHALL never interrupt the primary request flow | Non-blocking |
| NFR-03.6 | Monitoring service failures SHALL not interrupt fraud analysis | Non-blocking |
| NFR-03.7 | SSE stream SHALL handle GeneratorExit cleanly when the browser disconnects | Must |

---

### NFR-04 — Maintainability

| ID | Requirement |
|---|---|
| NFR-04.1 | The codebase SHALL follow the Flask application factory pattern |
| NFR-04.2 | Each API domain SHALL be implemented as a separate Flask Blueprint |
| NFR-04.3 | Business logic SHALL be separated from API controllers into service classes |
| NFR-04.4 | Database models SHALL be defined in a single ORM module using SQLAlchemy |
| NFR-04.5 | All environment-specific configuration SHALL be loaded from .env files |
| NFR-04.6 | No secrets, credentials, or .env files SHALL be committed to version control |
| NFR-04.7 | Service singletons SHALL be instantiated at module level for thread-safety |

---

### NFR-05 — Usability

| ID | Requirement |
|---|---|
| NFR-05.1 | The web interface SHALL be a single-page application (SPA) with no full-page reloads |
| NFR-05.2 | The interface SHALL display a loading indicator during data fetches |
| NFR-05.3 | All error messages shown to users SHALL be actionable and in plain language |
| NFR-05.4 | The system SHALL display toast notifications for all user actions |
| NFR-05.5 | The system SHALL function on Chrome, Firefox, and Edge (latest 2 versions) |
| NFR-05.6 | The logo/brand icon SHALL navigate back to the login/home page when clicked |
| NFR-05.7 | Admin-only navigation items (Detection Rules) SHALL be hidden from analyst users |

---

### NFR-06 — Scalability

| ID | Requirement |
|---|---|
| NFR-06.1 | The API SHALL be stateless to allow horizontal scaling behind a load balancer |
| NFR-06.2 | Database queries SHALL use indexed columns for all filter/search operations |
| NFR-06.3 | Pagination SHALL be enforced on all list endpoints (max 50–100 rows per page) |
| NFR-06.4 | Background jobs SHALL run in a separate APScheduler thread, not blocking the web server |
| NFR-06.5 | In-memory sliding windows are acceptable for single-server deployments; Redis SHALL be used for multi-server scaling |

---

### NFR-07 — Compliance & Regulatory

| ID | Requirement | Regulation |
|---|---|---|
| NFR-07.1 | The system SHALL flag all transactions ≥ $10,000 for potential CTR filing | FinCEN 31 CFR 1010.311 |
| NFR-07.2 | The system SHALL identify CRITICAL alerts as potential SAR candidates | FinCEN 31 CFR 1020.320 |
| NFR-07.3 | All customer names SHALL be screened against the OFAC SDN list before transaction approval | OFAC / 31 CFR 500–598 |
| NFR-07.4 | Customers under 18 SHALL be prevented from completing financial transactions | KYC / AML Directive |
| NFR-07.5 | The audit log SHALL be append-only with no update or delete operations | SOC 2 / ISO 27001 |
| NFR-07.6 | Transactions in the $9,500–$9,999 range SHALL be flagged for structuring detection | FinCEN / BSA |

---

### NFR-08 — Data Integrity

| ID | Requirement |
|---|---|
| NFR-08.1 | All monetary amounts SHALL be stored with 2 decimal places precision |
| NFR-08.2 | Transaction IDs SHALL be globally unique UUIDs (RFC 4122) |
| NFR-08.3 | All timestamps SHALL be stored in UTC |
| NFR-08.4 | Foreign key constraints SHALL be enforced at the database level |
| NFR-08.5 | Database sessions SHALL be rolled back on exception to prevent partial writes |

---

## 4. Constraints

| Constraint | Description |
|---|---|
| **Language** | Python 3.11+ backend; Vanilla JS frontend (no framework) |
| **Database** | MySQL 8.0 (no NoSQL, no SQLite in production) |
| **ML Framework** | scikit-learn only (no TensorFlow / PyTorch) |
| **Authentication** | JWT-only (no session cookies) |
| **AI Provider** | Groq or Anthropic external API (no on-premise LLM) |
| **Deployment** | Single-server Flask + Gunicorn (no Kubernetes in v1) |
| **Monitoring State** | In-memory sliding windows (no Redis in v1) |

---

## 5. Requirements Traceability Matrix

| Requirement Group | User Stories | Test Type |
|---|---|---|
| FR-01 (Auth & RBAC) | US-01, US-02, US-03, US-04 | Integration, Security |
| FR-02 (Transactions) | US-05, US-06, US-07, US-08 | Integration, Unit |
| FR-03 (Fraud Pipeline) | US-09, US-10, US-11, US-12 | Unit, Integration |
| FR-04 (OFAC) | US-13, US-14, US-15 | Integration, Compliance |
| FR-05 (Age Restriction) | US-16 | Unit, Compliance |
| FR-06 (Alerts) | US-17, US-18 | Integration |
| FR-07 (AI + RAG) | US-19, US-20 | Integration |
| FR-08 (Dashboard & Reports) | US-21, US-22, US-23 | Integration, E2E |
| FR-09 (Customers) | US-24 | Integration |
| FR-10 (Data Ingestion) | US-25, US-26, US-27 | Unit, Integration |
| FR-11 (Real-Time Monitoring) | US-28, US-29, US-30 | Integration, Performance |
| FR-12 (Live Demo) | US-31 | E2E, UI |
| NFR-02 (Security) | US-01, US-02 | Security, Penetration |
| NFR-07 (Compliance) | US-13, US-15, US-16, US-23, US-27 | Compliance |
