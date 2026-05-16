# Software Development Life Cycle — FraudGuard AI Detection System

**Project:** FraudGuard AI  
**Version:** 3.0  
**Last Updated:** 2026-05-04  
**Methodology:** Agile Scrum (2-week sprints)  
**Team Size:** 1 developer (solo)

---

## 1. Methodology Overview

FraudGuard AI follows an **Agile Scrum** methodology adapted for a solo developer. The iterative approach allows continuous delivery of working software while incorporating feedback at the end of each sprint. Each sprint produces a fully functional, testable increment.

### Why Agile?

| Factor | Rationale |
|---|---|
| Evolving requirements | Fraud detection rules and compliance regulations change frequently |
| Risk mitigation | Short sprints surface integration issues early (ML model, OFAC API) |
| Working software priority | Each sprint delivers runnable features, not just documents |
| Continuous improvement | Retrospectives after each sprint improve code quality and process |

---

## 2. SDLC Phases

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Planning   │───►│ Requirements │───►│   Design     │───►│Implementation│
│  (Sprint 0)  │    │  Analysis    │    │& Architecture│    │  (Sprints    │
│              │    │  (Sprint 0)  │    │  (Sprint 0)  │    │   1–6)       │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
                                                                     │
┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│ Maintenance  │◄───│  Deployment  │◄───│   Testing    │◄────────────┘
│  (Ongoing)   │    │  (Sprint 7)  │    │  (Per Sprint)│
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## 3. Phase 1 — Planning (Sprint 0, Week 1)

### 3.1 Project Scope Definition

**Goal:** Define what FraudGuard AI will and will not do.

**In Scope:**
- Real-time transaction fraud analysis (ML + rule engine)
- OFAC sanctions screening with daily automated refresh
- Fraud alert lifecycle management
- Admin and analyst web interface (SPA)
- Data ingestion, normalisation, and privacy-preserving preprocessing
- Real-time streaming transaction monitoring with velocity analysis and network detection
- Interactive live demo for exploring the fraud pipeline
- RAG-powered AI analyst assistant (Groq/Anthropic)
- CSV/JSON compliance reporting

**Out of Scope (v1):**
- Mobile application
- Real payment gateway integration (simulation only)
- On-premise LLM deployment
- Multi-tenant architecture
- Kubernetes/container orchestration
- Redis-backed distributed monitoring (single-server only)

### 3.2 Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Anthropic API credit exhaustion | High | High | Groq free tier as primary; Anthropic as fallback |
| OFAC SDN download failure | Medium | High | Fail-closed policy; retry with backoff; last-known-good state |
| ML model overfitting on synthetic data | Medium | Medium | Isolation Forest (unsupervised) eliminates label bias |
| MySQL connection failure in production | Low | High | 503 handler; connection pool; SQLAlchemy retry |
| TOTP clock drift causing 2FA lockout | Low | Medium | ±30-second window (1-step tolerance) |
| Chart.js CDN blocked by corporate firewall | Medium | Low | Self-host chart.umd.min.js from Flask static |
| SSE connection dropped by proxy | Medium | Low | Fallback polling endpoint at `/api/monitor/realtime` |
| In-memory monitoring state lost on restart | Medium | Low | Acceptable for v1; Redis migration path documented |

### 3.3 Tools & Technology Selection

| Category | Tool | Rationale |
|---|---|---|
| Backend framework | Flask 3.0 | Lightweight, Pythonic, excellent for REST APIs |
| ORM | SQLAlchemy 2.0 | Type-safe, database-agnostic, mature |
| Database | MySQL 8.0 | ACID-compliant, widely used in fintech |
| ML | scikit-learn | Isolation Forest for unsupervised anomaly detection |
| Authentication | Flask-JWT-Extended | Stateless JWT tokens, 2FA extensions |
| 2FA | PyOTP | RFC 6238-compliant TOTP |
| AI (primary) | Groq (Llama 3.3 70B) | Free tier, low latency |
| AI (fallback) | Anthropic Claude | High quality, paid |
| RAG engine | Custom Jaccard similarity | No external dependency; fast; deterministic |
| Streaming | Flask SSE (Response + stream_with_context) | No WebSocket dependency; HTTP-native |
| Task scheduler | APScheduler | In-process background jobs |
| Frontend | Vanilla JS + Chart.js | No build step, fast, zero dependencies |
| Version control | Git + GitHub | Industry standard |

---

## 4. Phase 2 — Requirements Analysis (Sprint 0, Week 2)

### 4.1 Stakeholder Identification

| Stakeholder | Role | Interest |
|---|---|---|
| Fraud Analyst | Primary user | Real-time alerts, clear risk explanations |
| Compliance Officer | Secondary user | OFAC reports, CTR/SAR identification |
| System Administrator | Secondary user | User management, rule configuration, 2FA |
| Regulatory Bodies | External | OFAC compliance, AML/KYC enforcement |
| Data Engineer | Secondary user | Ingestion quality, PII compliance |

### 4.2 Requirements Elicitation Techniques

| Technique | Output |
|---|---|
| Domain research (FinCEN, OFAC, AML literature) | FR-04, FR-05, NFR-07 |
| Regulatory document analysis (31 CFR 1010, OFAC SDN) | Compliance requirements |
| OWASP Top 10 review | NFR-02 security requirements |
| Prototype walkthroughs | UI/UX requirements (NFR-05) |
| Fraud monitoring pattern research | FR-11 sliding window thresholds |
| GDPR/privacy review | FR-10 PII masking, device fingerprinting |

### 4.3 Requirements Prioritisation (MoSCoW)

| Priority | Count | Examples |
|---|---|---|
| Must Have | 19 user stories | Authentication, fraud detection, OFAC screening, alerts, ingestion pipeline |
| Should Have | 12 user stories | AI assistant (RAG), rule configuration, exports, monitoring, live demo |
| Could Have | 0 user stories | — |
| Won't Have (v1) | — | Mobile app, WebSocket push, multi-tenant, Redis monitoring |

*See `docs/requirements.md` for the full requirements specification.*

---

## 5. Phase 3 — System Design (Sprint 0, Week 2)

### 5.1 Architecture Decision Records

**ADR-01: Application Factory Pattern**
- Decision: Flask `create_app()` factory
- Rationale: Enables testing with different configs; blueprint isolation

**ADR-02: JWT-Only Authentication**
- Decision: Stateless JWT, no server-side sessions
- Rationale: Horizontal scalability; simpler load balancer setup (NFR-06.1)

**ADR-03: Fail-Closed OFAC Policy**
- Decision: OFAC service error → block transaction
- Rationale: Regulatory compliance; false negatives are more costly than false positives

**ADR-04: Two-Phase 2FA via Temp Token**
- Decision: Temp JWT with `_2fa_pending: true` claim (5-min expiry)
- Rationale: Avoids storing server-side session state while securing the 2FA flow

**ADR-05: Unsupervised ML (Isolation Forest)**
- Decision: Isolation Forest over supervised classifiers
- Rationale: No labelled fraud dataset available; detects novel patterns

**ADR-06: Multi-Provider AI**
- Decision: Groq as primary (free), Anthropic as fallback
- Rationale: Zero cost during development; production quality on Anthropic

**ADR-07: Keyword RAG over Vector Embeddings**
- Decision: Jaccard similarity on tokenised markdown chunks
- Rationale: No GPU or embedding API dependency; fast; deterministic; sufficient for doc-level QA

**ADR-08: SSE over WebSockets for Monitoring**
- Decision: Server-Sent Events (HTTP streaming)
- Rationale: SSE is simpler (no upgrade handshake), HTTP-native, and JWT-compatible

**ADR-09: In-Memory Sliding Windows**
- Decision: `collections.deque` with timestamp eviction, protected by `threading.Lock`
- Rationale: No Redis dependency for single-server v1; thread-safe; O(1) amortised

**ADR-10: SHA-256 Device Fingerprinting**
- Decision: Hash raw device IDs before storage
- Rationale: GDPR compliance; irreversible anonymisation; retains fraud correlation value

### 5.2 Database Design

Key entities and relationships:
```
User ──────────────────── AuditLog
  │
  └── Transaction ─── RiskScore
         │         └── FraudAlert
         │
      Customer ────── OFACEntry (screened against)

OFACEntry ──────────── OFACUpdate (refresh audit)
FraudRule              (configurable, admin-managed)
Notification           (in-app alerts)
```

### 5.3 API Design

RESTful API under `/api/` prefix, JWT-protected, with blueprint isolation:
- `/api/auth/` — login, 2FA, token management
- `/api/transactions/` — CRUD + fraud pipeline
- `/api/alerts/` — alert lifecycle
- `/api/dashboard/` — KPI aggregations
- `/api/customers/` — customer profiles
- `/api/assistant/` — RAG AI chat
- `/api/compliance/` — OFAC screening and SDN management
- `/api/reports/` — CSV/JSON exports
- `/api/ingest/` — data ingestion & preprocessing
- `/api/monitor/` — real-time monitoring + SSE stream

*See `docs/system_architecture.md` for full architecture documentation.*

---

## 6. Phase 4 — Implementation (Sprints 1–6)

### Sprint 1 — Foundation (Weeks 1–2)
**Goal:** Runnable application with authentication

| Task | Story | Status |
|---|---|---|
| Flask app factory + config | — | Done |
| SQLAlchemy models (User, Transaction, Customer) | — | Done |
| JWT authentication (login, logout) | US-01 | Done |
| Role-based access control (admin, analyst) | US-04 | Done |
| Account lockout (5 attempts, 15 min) | US-01 | Done |
| Basic SPA scaffold (index.html, app.js) | — | Done |

**Definition of Done:** Analyst can log in and view an empty dashboard.

---

### Sprint 2 — Core Fraud Pipeline (Weeks 3–4)
**Goal:** End-to-end fraud detection working

| Task | Story | Status |
|---|---|---|
| Transaction model + submission API | US-05 | Done |
| Rule engine (6 rule types) | US-09 | Done |
| Isolation Forest ML model integration | US-10 | Done |
| Combined risk scoring (0.40/0.60 weights) | US-11 | Done |
| FraudAlert generation | US-17 | Done |
| Transaction list with pagination | US-06 | Done |
| Transaction detail modal | US-07 | Done |
| Manual review (approve/block) | US-08 | Done |

**Definition of Done:** A submitted transaction is scored, stored, and shown on the UI with risk breakdown.

---

### Sprint 3 — Compliance & OFAC (Weeks 5–6)
**Goal:** Full OFAC integration and compliance pre-checks

| Task | Story | Status |
|---|---|---|
| OFAC SDN list download + parser | US-15 | Done |
| Levenshtein fuzzy matching engine | US-13 | Done |
| OFAC screening integrated into fraud pipeline | US-13 | Done |
| Age restriction checks (< 18, > 100) | US-16 | Done |
| APScheduler daily OFAC refresh at 02:00 UTC | US-15 | Done |
| OFAC SDN search UI | US-14 | Done |
| Fail-closed OFAC error handling | US-13 | Done |

**Definition of Done:** A transaction from a sanctioned customer is automatically blocked before ML scoring.

---

### Sprint 4 — Security Hardening & 2FA (Weeks 7–8)
**Goal:** Production-grade security posture

| Task | Story | Status |
|---|---|---|
| TOTP 2FA for admin accounts | US-02 | Done |
| QR code generation (qrcode + Pillow) | US-02 | Done |
| Temp JWT for 2FA flow (`_2fa_pending` claim) | US-02 | Done |
| Security headers (CSP, X-Frame-Options, etc.) | — | Done |
| CORS whitelist (no wildcard) | — | Done |
| CSV formula injection prevention | US-22 | Done |
| Audit trail (AuditLog service) | US-08 | Done |
| Role-based view restriction (admin vs analyst) | US-04 | Done |
| Stack trace suppression in error responses | — | Done |

**Definition of Done:** Admin 2FA login works end-to-end; all OWASP headers present on every response; analyst cannot access admin-only views.

---

### Sprint 5 — AI Assistant & Analytics (Weeks 9–10)
**Goal:** RAG AI assistant + advanced dashboard + reporting

| Task | Story | Status |
|---|---|---|
| Groq AI provider integration | US-19 | Done |
| Anthropic fallback | US-20 | Done |
| Multi-turn conversation history (capped 20 turns) | US-19 | Done |
| RAG service: docs/ markdown indexing at startup | US-20 | Done |
| RAG retrieval: Jaccard similarity, top-3 chunks | US-20 | Done |
| Dashboard KPI cards + 7-day trend chart | US-21 | Done |
| Chart.js (self-hosted, CDN blocked fix) | — | Done |
| Transaction search/filter (amount, country) | US-06 | Done |
| CSV/JSON export API | US-22 | Done |
| Compliance report (CTR, OFAC, SAR candidates) | US-23 | Done |
| User management (create, list, roles) | US-04 | Done |
| Detection rule configuration UI (admin only) | US-12 | Done |

**Definition of Done:** Analyst can ask the AI assistant a fraud question (RAG context injected), see charts, and export a CSV.

---

### Sprint 6 — Ingestion, Monitoring & Live Demo (Weeks 11–12)
**Goal:** Data pipeline, real-time monitoring stream, and interactive demo

| Task | Story | Status |
|---|---|---|
| IngestionService: normalisation, PII masking, fingerprinting | US-25 | Done |
| Structuring detection ($9,500–$9,999 flag) | US-27 | Done |
| Batch ingestion endpoint (up to 500 records) | US-26 | Done |
| Dry-run preview endpoint | US-26 | Done |
| Auto-preprocessing integrated into transaction submission | US-25 | Done |
| MonitoringService: sliding window counters (1m/5m/1hr) | US-28 | Done |
| ThresholdEngine: 12 configurable thresholds | US-28 | Done |
| NetworkAnalyser: device/IP → customer graph | US-29 | Done |
| SSE stream endpoint (`/api/monitor/stream`) | US-28 | Done |
| Polling fallback endpoint (`/api/monitor/realtime`) | US-28 | Done |
| Admin threshold editor (PUT /api/monitor/thresholds) | US-29 | Done |
| Live Monitor SPA view (real-time KPIs + feed) | US-30 | Done |
| Live Demo SPA view (5 scenarios, pipeline visualiser) | US-31 | Done |
| Demo: auto-load real customer IDs from DB | US-31 | Done |
| Fraud detector feeds monitoring after every analysis | US-28 | Done |

**Definition of Done:** Monitor view shows live transaction feed via SSE; demo page runs all 5 scenarios and displays pipeline stages, score bars, and violations.

---

## 7. Phase 5 — Testing Strategy

### 7.1 Testing Levels

| Level | Scope | Tools | Coverage |
|---|---|---|---|
| Unit | Individual functions, validators, score formulas, sliding windows | pytest | FR-03, FR-05, FR-10, FR-11 |
| Integration | API endpoints with test database | pytest + Flask test client | FR-01–FR-12 |
| Security | Auth bypass, injection, TOTP bypass, RBAC enforcement | Manual + OWASP ZAP | NFR-02 |
| Compliance | OFAC match accuracy, fail-closed, age blocks, structuring detection | pytest | NFR-07 |
| Performance | p95 latency under simulated load, SSE stream stability | locust / wrk | NFR-01 |
| Regression | Full suite on every feature branch | GitHub Actions | All FRs |

### 7.2 Test Data Strategy

- **Synthetic customers:** Generated with known fraud patterns (high velocity, high amount, OFAC name variants, under-18 DOBs)
- **OFAC test cases:** Sample SDN names with deliberate typos to validate fuzzy matching thresholds
- **ML model:** Pre-trained on 10,000 synthetic transactions; loaded from disk at startup
- **Monitoring tests:** Rapid transaction submission to trigger velocity thresholds; shared device/IP tests

### 7.3 Test Case Examples

| ID | Test | Expected Result |
|---|---|---|
| TC-01 | Login with correct credentials | JWT returned, `last_login` updated |
| TC-02 | Login with wrong password (5 times) | 429 on 5th attempt, account locked |
| TC-03 | Submit transaction for OFAC-matched customer | status=blocked, score=1.0, CRITICAL alert |
| TC-04 | Submit transaction with age < 18 | status=blocked, AGE_RESTRICTION violation |
| TC-05 | Submit transaction, ML model unavailable | Falls back to rule score only, warning logged |
| TC-06 | 2FA: valid TOTP code | Full JWT issued |
| TC-07 | 2FA: expired temp token (> 5 min) | 401 "Invalid or malformed token" |
| TC-08 | Export 10,001 rows | Capped at 10,000, no error |
| TC-09 | CSV cell starting with `=` | Cell prefixed with `'` (formula injection prevented) |
| TC-10 | OFAC service unreachable | Transaction blocked (fail-closed) |
| TC-11 | Analyst accesses `/api/compliance/rules` PUT | 403 Forbidden |
| TC-12 | Ingest transaction with missing `amount` | 422 with rejection reason |
| TC-13 | Ingest transaction at $9,750 | STRUCTURING_PATTERN flag in preprocessing result |
| TC-14 | Submit 6 transactions in 1 minute from same customer | Velocity threshold alert in monitoring event |
| TC-15 | Two customers share same device_id | Shared device alert in network analysis |
| TC-16 | Demo page: run High-Amount scenario | Result shows blocked status, score bars filled |
| TC-17 | AI assistant query about OFAC | RAG injects OFAC documentation chunk into prompt |

---

## 8. Phase 6 — Deployment (Sprint 7)

### 8.1 Deployment Architecture

```
Internet → Nginx (reverse proxy, TLS termination)
              │
              └── Gunicorn (WSGI, 4 workers)
                     │
                     ├── Flask Application
                     │      ├── MySQL 8.0 (local or managed)
                     │      ├── APScheduler (in-process thread)
                     │      ├── ML Model (loaded from disk)
                     │      ├── RAG index (built at startup from docs/)
                     │      └── MonitoringService (in-memory)
                     └── SSE connections (long-lived HTTP streams)
```

### 8.2 Environment Configuration

| Environment | Database | Debug | Workers | Scheduler |
|---|---|---|---|---|
| Development | MySQL local | True | 1 (Flask dev server) | Enabled |
| Staging | MySQL remote | False | 2 (Gunicorn) | Enabled |
| Production | MySQL managed | False | 4 (Gunicorn) | Enabled |

All environment-specific values are loaded from `.env` files. No secrets in source code.

### 8.3 Pre-Deployment Checklist

- [ ] `SECRET_KEY` is a cryptographically random 64-character string
- [ ] `JWT_SECRET_KEY` is a separate cryptographically random key
- [ ] `DEBUG=False` in production config
- [ ] CORS origins list updated to production domain
- [ ] `GROQ_API_KEY` or `ANTHROPIC_API_KEY` set in `.env`
- [ ] MySQL database created with correct schema (`python setup_db.py`)
- [ ] OFAC SDN list pre-populated (first run triggers automatic download)
- [ ] `docs/` directory present for RAG indexing at startup
- [ ] Nginx configured with `X-Accel-Buffering: no` for SSE endpoints
- [ ] Nginx TLS certificate provisioned (Let's Encrypt or commercial CA)
- [ ] Gunicorn started with `--workers 4 --timeout 120`
- [ ] Log rotation configured

### 8.4 Rollback Plan

1. Keep the previous release tag in Git (`git tag v1.x`)
2. On failure: `git checkout v1.x && gunicorn restart`
3. Database migrations are additive (no DROP/ALTER of existing columns)
4. OFAC data is preserved across rollbacks (separate table, not truncated)
5. In-memory monitoring state resets on restart (acceptable for v1)

---

## 9. Phase 7 — Maintenance

### 9.1 Operational Monitoring

| Metric | Alert Threshold | Action |
|---|---|---|
| OFAC refresh failure | Any failure | Check OFACUpdate table; manual retry |
| Transaction p95 latency > 3s | Consecutive violations | Investigate ML model, DB query plan |
| Open CRITICAL alerts > 10 | Daily digest | Analyst triage |
| Failed login spike | > 20 in 5 min from same IP | IP block consideration |
| Monitoring block rate alert | > system_block_rate_warn threshold | Ops review |
| SSE stream errors | Repeated stream disconnects | Check Nginx buffering config |

### 9.2 OFAC List Maintenance

- Daily automatic refresh at 02:00 UTC via APScheduler
- Refresh logs available at `GET /api/compliance/ofac/updates`
- Manual refresh available at `POST /api/compliance/ofac/refresh` (admin only)
- Keeps last-known-good data on download failure

### 9.3 ML Model Retraining

**Current policy (v1):** Static model trained on synthetic data, loaded at startup.

**Recommended cadence for production:**
- Retrain monthly with the last 90 days of confirmed fraud/legitimate labels
- Evaluate: F1 score, precision/recall on held-out test set
- Deploy new model by replacing `ml/fraud_model.pkl` (zero downtime if using Gunicorn pre-load)

### 9.4 Monitoring Threshold Tuning

- Review velocity thresholds quarterly against observed transaction patterns
- Use `PUT /api/monitor/thresholds` to update at runtime without restart
- Log threshold change events in audit log for traceability

### 9.5 Dependency Updates

| Dependency | Update Frequency | Risk |
|---|---|---|
| Flask / Flask-JWT-Extended | Quarterly | Medium — check changelog for breaking changes |
| scikit-learn | Semi-annual | Low — retrain model after major version |
| Groq SDK / Anthropic SDK | As needed | Low — API is additive |
| PyOTP | Annual | Low — TOTP algorithm is stable |
| MySQL connector (PyMySQL) | Quarterly | Low |
| APScheduler | Semi-annual | Medium — check job trigger API changes |

---

## 10. Agile Ceremonies (Solo Adaptation)

| Ceremony | Frequency | Duration | Output |
|---|---|---|---|
| Sprint Planning | Start of each sprint | 1 hour | Sprint backlog (GitHub Issues) |
| Daily Standup | Daily | 5 min | Progress journal entry |
| Sprint Review | End of each sprint | 30 min | Demo to stakeholder / self-evaluation |
| Sprint Retrospective | End of each sprint | 20 min | 1 process improvement to implement |
| Backlog Refinement | Mid-sprint | 30 min | Groomed backlog for next sprint |

---

## 11. Definition of Done (Project Level)

A feature is considered complete when:
- [ ] Code is written and passes all existing tests
- [ ] New tests added for the feature (if testable logic)
- [ ] No stack traces visible in API responses
- [ ] OWASP headers present on all new endpoints
- [ ] Feature is accessible from the SPA without full-page reload
- [ ] Code committed to `main` with a descriptive commit message
- [ ] Documentation updated if the feature changes a use case or requirement

---

## 12. Sprint Velocity Summary

| Sprint | Goal | Stories Completed | Story Points |
|---|---|---|---|
| Sprint 0 | Planning + design | — | — |
| Sprint 1 | Foundation + Auth | US-01, US-03, US-04 | 18 |
| Sprint 2 | Fraud Pipeline | US-05, US-06, US-07, US-08, US-09, US-10, US-11 | 47 |
| Sprint 3 | Compliance / OFAC | US-13, US-14, US-15, US-16 | 26 |
| Sprint 4 | Security + 2FA | US-02 + security hardening | 15 |
| Sprint 5 | AI (RAG) + Analytics | US-12, US-17, US-18, US-19, US-20, US-21, US-22, US-23 | 43 |
| Sprint 6 | Ingestion + Monitoring + Demo | US-25, US-26, US-27, US-28, US-29, US-30, US-31 | 38 |
| **Total** | | **30 user stories** | **187** |
