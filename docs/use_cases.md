# Use Cases — FraudGuard AI Detection System

**Project:** FraudGuard AI  
**Version:** 3.0  
**Last Updated:** 2026-05-04  
**Format:** Fully Dressed Use Case (Cockburn Style)

---

## Actors

| Actor | Type | Description |
|---|---|---|
| **Analyst** | Primary Human | Fraud analyst who monitors alerts and reviews transactions |
| **Admin** | Primary Human | System administrator who manages users, rules, and security |
| **System Scheduler** | Primary System | APScheduler background job runner |
| **Payment Gateway** | External System | Submits transaction events for analysis |
| **OFAC Source** | External System | US Treasury SDN list — read-only data source |
| **LLM API** | External System | Groq or Anthropic AI language model API |

---

## Use Case Diagram Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FraudGuard AI System                         │
│                                                                     │
│  UC-01 Login                      ◄── Analyst, Admin                │
│  UC-02 Enable / Use 2FA           ◄── Admin                         │
│  UC-03 Submit Transaction         ◄── Analyst, Payment Gateway      │
│  UC-04 Analyse Transaction        ◄── System (triggered by UC-03)   │
│  UC-05 Review Fraud Alert         ◄── Analyst                       │
│  UC-06 Screen OFAC Name           ◄── Analyst, System               │
│  UC-07 Refresh OFAC List          ◄── System Scheduler              │
│  UC-08 Manage Detection Rules     ◄── Admin                         │
│  UC-09 Use AI Assistant (RAG)     ◄── Analyst                       │
│  UC-10 Export Report              ◄── Analyst, Admin                │
│  UC-11 Manage Users               ◄── Admin                         │
│  UC-12 View Dashboard             ◄── Analyst, Admin                │
│  UC-13 Ingest & Preprocess Data   ◄── Analyst, Payment Gateway      │
│  UC-14 Monitor Transactions (Live)◄── Analyst, Admin                │
│  UC-15 Run Live Demo              ◄── Analyst, Admin                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## UC-01 — User Login

| Field | Detail |
|---|---|
| **Use Case ID** | UC-01 |
| **Name** | User Login |
| **Actor** | Analyst, Admin |
| **Preconditions** | User account exists and is active |
| **Postconditions** | User receives a valid JWT token and is redirected to the dashboard |
| **Trigger** | User navigates to the application and submits credentials |

### Main Success Scenario
1. User enters username and password
2. System checks login throttle — not locked
3. System validates credentials against the database
4. *(Admin with 2FA enabled)* System issues a short-lived temp token and shows TOTP screen → **extends UC-02**
5. *(No 2FA)* System issues a full JWT access token (1 hour)
6. System updates `last_login` timestamp
7. User is redirected to the dashboard

### Alternative Flows
**3a. Invalid credentials:**
- System records the failure against IP + username
- If failures < 5: returns generic "Invalid username or password" (401)
- If failures = 5: locks account for 15 minutes (429)

**3b. Account inactive:**
- Returns "Account is disabled. Contact your administrator." (403)

### Exception Flows
**2a. Account locked:**
- System returns remaining lockout time in minutes (429)
- User must wait before retrying

---

## UC-02 — Two-Factor Authentication (Admin)

| Field | Detail |
|---|---|
| **Use Case ID** | UC-02 |
| **Name** | Two-Factor Authentication |
| **Actor** | Admin |
| **Preconditions** | Admin has completed password verification (UC-01 step 3); 2FA is enabled on the account |
| **Postconditions** | Admin receives a full JWT access token |
| **Trigger** | Server returns `requires_2fa: true` during login |

### Main Success Scenario
1. System displays TOTP code entry screen with a 5-minute countdown
2. Admin opens authenticator app and reads the current 6-digit code
3. Admin enters the code and submits
4. System validates the code using PyOTP (±30 second window)
5. System issues a full JWT access token
6. Admin is redirected to the dashboard

### Alternative Flows
**4a. Invalid code:**
- System returns "Invalid authenticator code" (401)
- Admin can retry (main account lockout applies)

**4b. Temp token expired (>5 minutes):**
- System returns 401 "Invalid or malformed token"
- Admin must restart the login process

### Sub-Use Case: Enable 2FA
1. Admin clicks the lock icon in the sidebar
2. System generates a TOTP secret and displays a QR code + manual key
3. Admin scans QR code with Google Authenticator or Authy
4. Admin enters a 6-digit code to confirm the setup
5. System activates 2FA on the account
6. All future admin logins require TOTP verification

---

## UC-03 — Submit Transaction

| Field | Detail |
|---|---|
| **Use Case ID** | UC-03 |
| **Name** | Submit Transaction for Fraud Analysis |
| **Actor** | Analyst (via UI), Payment Gateway (via API) |
| **Preconditions** | Actor is authenticated with a valid JWT; customer exists in the system |
| **Postconditions** | Transaction is persisted; fraud analysis result is returned |
| **Trigger** | POST /api/transactions with transaction payload |

### Main Success Scenario
1. Actor submits: customer_id, amount, currency, merchant_name, location, card_type
2. System runs ingestion preprocessing (normalisation, structuring detection, feature derivation)
3. System validates all input fields (amount, currency, required fields)
4. System resolves the customer record from customer_id
5. System creates a Transaction record (status = pending)
6. System triggers fraud analysis pipeline → **includes UC-04**
7. System feeds result to monitoring service → **includes UC-14**
8. System returns: transaction details, status, risk scores, violations, recommendation

### Alternative Flows
**2a. Preprocessing rejection:**
- Returns 422 with rejection reason and data quality report
- Transaction is not persisted

**4a. Customer not found:**
- Returns 404 "Customer not found"
- Transaction is not persisted

### Exception Flows
**6a. ML model unavailable:**
- Rule score used alone (weighted 100%)
- Warning logged; analysis continues without failing

---

## UC-04 — Analyse Transaction (Fraud Detection Pipeline)

| Field | Detail |
|---|---|
| **Use Case ID** | UC-04 |
| **Name** | Analyse Transaction — Fraud Detection Pipeline |
| **Actor** | System (triggered by UC-03) |
| **Preconditions** | Transaction record exists; customer record loaded |
| **Postconditions** | Transaction has a status (approved/flagged/blocked); RiskScore persisted; alerts generated |
| **Trigger** | FraudDetector.analyze_transaction() called |

### Main Success Scenario

**Stage 0 — Compliance Pre-Checks** *(Fail Fast)*
1. System checks customer age (if date_of_birth known)
   - Age < 18 or Age > 100 → **immediate block** (skip to Stage 6)
2. System screens customer name against OFAC SDN list
   - Similarity ≥ 0.80 → **immediate block** (skip to Stage 6)
   - Service error → **immediate block** (fail-closed)

**Stage 1 — Velocity Count**
3. System counts customer transactions in the last 1 hour

**Stage 2 — Rule Engine**
4. System evaluates all active FraudRule records: HIGH_AMOUNT, HIGH_FREQUENCY, HIGH_RISK_COUNTRY, RAPID_SUCCESSION, NEW_DEVICE, ROUND_AMOUNT
5. System computes weighted rule_score ∈ [0.0, 1.0]

**Stage 3 — ML Scoring**
6. System engineers 14 features from transaction + customer data
7. Isolation Forest model returns anomaly probability → ml_score ∈ [0.0, 1.0]

**Stage 4 — Score Aggregation**
8. combined_score = 0.40 × rule_score + 0.60 × ml_score
9. Risk level mapped: critical (≥0.75), high (≥0.55), medium (≥0.35), low (<0.35)

**Stage 5 — Disposition**
10. combined_score ≥ 0.75 → blocked / combined_score ≥ 0.45 → flagged / else → approved

**Stage 6 — Persistence & Alerts**
11. System persists RiskScore, updates Transaction.status, updates Customer.risk_level
12. If score ≥ 0.45: system creates FraudAlert record

### Alternative Flows
**0a. Compliance block triggered:**
- combined_score forced to 1.0, status = blocked
- RiskScore and CRITICAL FraudAlert created immediately
- Stages 1–5 are skipped

---

## UC-05 — Review Fraud Alert

| Field | Detail |
|---|---|
| **Use Case ID** | UC-05 |
| **Name** | Review and Resolve Fraud Alert |
| **Actor** | Analyst |
| **Preconditions** | Analyst is authenticated; alert exists and is unresolved |
| **Postconditions** | Alert is marked resolved; action logged in audit trail |
| **Trigger** | Analyst opens the Alerts view and selects an alert |

### Main Success Scenario
1. Analyst sees unresolved alerts sorted by severity
2. Analyst opens the alert detail modal
3. Analyst reviews: type, severity, description, risk factors, related transaction
4. Analyst enters resolution notes and clicks "Resolve Alert"
5. System marks alert resolved with `resolved_at` timestamp and `resolved_by` user ID
6. System logs the resolution in the audit trail

### Alternative Flows
**4a. Analyst marks linked transaction as legitimate:**
- Transaction status updated to approved, is_fraud = false

**4b. Analyst confirms linked transaction as fraud:**
- Transaction status updated to blocked, is_fraud = true

---

## UC-06 — Screen Name Against OFAC SDN List

| Field | Detail |
|---|---|
| **Use Case ID** | UC-06 |
| **Name** | Screen Name Against OFAC SDN List |
| **Actor** | Analyst (manual), System (automatic via UC-04) |
| **Preconditions** | OFAC SDN list has been loaded into the database |
| **Postconditions** | Match result returned with score, matched entry, and recommended action |
| **Trigger** | Manual: Analyst enters a name in the OFAC search field. Automatic: called during UC-04 |

### Main Success Scenario
1. Actor provides a name to screen
2. System normalises the name (lowercase, remove punctuation, trim)
3. System queries the database for candidate SDN entries
4. System computes Levenshtein similarity for each candidate
5. If best score ≥ 0.80: match found — returns matched name, SDN type, programme, score
6. If best score < 0.80: no match — returns clear result

### Exception Flows
**Service error (automatic mode):** Fail-closed — transaction blocked, OFAC_SERVICE_ERROR violation logged

---

## UC-07 — Refresh OFAC SDN List

| Field | Detail |
|---|---|
| **Use Case ID** | UC-07 |
| **Name** | Refresh OFAC SDN List |
| **Actor** | System Scheduler |
| **Preconditions** | APScheduler is running; internet connectivity available |
| **Postconditions** | OFACEntry table updated; OFACUpdate audit record written |
| **Trigger** | APScheduler fires at 02:00 UTC daily |

### Main Success Scenario
1. Scheduler triggers the OFAC refresh job
2. System downloads the SDN CSV from the US Treasury endpoint
3. System parses CSV rows into SDN entries
4. System upserts entries into the database
5. System writes OFACUpdate record: status = success, entry count
6. System logs the refresh result

### Exception Flows
**2a. Download fails:**
- System retries up to 3 times with backoff
- If all retries fail: OFACUpdate written with status = error
- Existing SDN data preserved (last known good state)

---

## UC-08 — Manage Detection Rules

| Field | Detail |
|---|---|
| **Use Case ID** | UC-08 |
| **Name** | Manage Fraud Detection Rules |
| **Actor** | Admin |
| **Preconditions** | Admin is authenticated with admin role |
| **Postconditions** | Rule changes persisted; next transaction uses updated rules |
| **Trigger** | Admin navigates to Detection Rules view |

### Main Success Scenario
1. Admin views all fraud rules with current threshold, weight, and active status
2. Admin selects a rule to edit
3. Admin adjusts threshold, weight, or active/inactive toggle
4. System persists the change via PUT /api/compliance/rules/<id>
5. Change takes effect on the next submitted transaction

### Alternative Flows
**Analyst attempts to access rules:** Returns 403 Forbidden (RBAC enforcement)

---

## UC-09 — Use AI Assistant (RAG-Powered)

| Field | Detail |
|---|---|
| **Use Case ID** | UC-09 |
| **Name** | Use RAG-Powered AI Fraud Analysis Assistant |
| **Actor** | Analyst |
| **Preconditions** | Analyst is authenticated; AI provider API key is configured; docs/ indexed at startup |
| **Postconditions** | AI response displayed in the chat window, grounded in project documentation |
| **Trigger** | Analyst types a message and submits |

### Main Success Scenario
1. Analyst opens the AI Assistant view
2. Analyst types a question (or clicks a quick-suggestion button)
3. System validates input (max 500 chars)
4. System retrieves the top-3 most relevant documentation chunks using Jaccard similarity (RAG)
5. System prepends retrieved context to the user query
6. System sends: system prompt + conversation history + augmented query to the LLM API
7. LLM returns a response grounded in both its training and the retrieved documentation
8. Response displayed with markdown formatting in the chat window
9. Response added to conversation history for subsequent turns

### Alternative Flows
**4a. No relevant chunks found:** Query sent to LLM without RAG context (graceful degradation)
**6a. Groq API key set → uses Groq (Llama 3.3 70B, free)**
**6b. Only Anthropic key set → uses Claude**
**6c. No API key configured → chat displays setup instructions**

---

## UC-10 — Export Report

| Field | Detail |
|---|---|
| **Use Case ID** | UC-10 |
| **Name** | Export Compliance or Transaction Report |
| **Actor** | Analyst, Admin |
| **Preconditions** | Actor is authenticated |
| **Postconditions** | CSV or JSON file delivered to the browser |
| **Trigger** | Actor calls the export endpoint with optional filters |

### Main Success Scenario
1. Actor sends export request with optional filters: date range, status, risk level, format
2. System validates parameters (date range, format whitelist)
3. System queries database with applied filters (capped at 10,000 rows)
4. System builds export rows with sanitised values (formula injection prevention)
5. System returns file as a download response

### Alternative Flows
**3a. No records found:** Returns 404 "No data found for the selected filters"
**Compliance report (admin only):** Returns 403 if requested by analyst role

---

## UC-11 — Manage Users

| Field | Detail |
|---|---|
| **Use Case ID** | UC-11 |
| **Name** | Manage System Users |
| **Actor** | Admin |
| **Preconditions** | Admin is authenticated with admin role |
| **Postconditions** | User account created / updated in the database |
| **Trigger** | Admin navigates to the user management section |

### Main Success Scenario
1. Admin views all users with their roles and last login times
2. Admin creates a new user (username, email, password, role)
3. System validates fields including password complexity
4. System checks uniqueness of username and email
5. System creates the user account (password hashed with pbkdf2:sha256)
6. New user can immediately log in

---

## UC-12 — View Dashboard

| Field | Detail |
|---|---|
| **Use Case ID** | UC-12 |
| **Name** | View Fraud Monitoring Dashboard |
| **Actor** | Analyst, Admin |
| **Preconditions** | Actor is authenticated |
| **Postconditions** | Dashboard displays current fraud metrics and charts |
| **Trigger** | Actor navigates to Dashboard view |

### Main Success Scenario
1. Browser renders the Dashboard view
2. System makes 5 parallel API calls: stats, trend, risk-dist, alert-types, top-alerts
3. Dashboard renders KPI cards: total transactions, fraud rate, open alerts, revenue at risk
4. Transaction trend chart rendered (last 7 days, legitimate vs. fraud)
5. Risk distribution donut chart rendered
6. Alert type bar chart rendered
7. Top unresolved alerts listed with severity badges

---

## UC-13 — Ingest & Preprocess Data

| Field | Detail |
|---|---|
| **Use Case ID** | UC-13 |
| **Name** | Ingest and Preprocess Transaction / Customer / Device Data |
| **Actor** | Analyst (via UI), Payment Gateway (via API) |
| **Preconditions** | Actor is authenticated with a valid JWT |
| **Postconditions** | Data is normalised, enriched, and validated; PII masked in logs; device fingerprinted |
| **Trigger** | POST /api/ingest/transaction, /api/ingest/batch, /api/ingest/customer, or /api/ingest/device |

### Main Success Scenario
1. Actor submits raw transaction, customer, or device record(s)
2. System normalises fields: uppercase location, trim strings, convert types
3. System derives additional fields: hour_of_day, day_of_week, is_weekend, amount_magnitude
4. System checks for structuring patterns ($9,500–$9,999 range)
5. System hashes raw device identifier with SHA-256 (GDPR-compliant fingerprinting)
6. System masks PII in all log output (email local-part, phone digits, IP last octet)
7. System validates all fields — rejects with reason if required fields missing or invalid
8. System returns: preprocessed data, quality report, any flags (structuring, etc.)

### Alternative Flows
**7a. Validation failure:**
- Returns 422 with rejection reason and per-field data quality report

**Batch ingestion (up to 500 records):**
- Each record processed independently
- Response includes counts: processed, rejected, per-record errors

**Dry-run preview (POST /api/ingest/preview/transaction):**
- Full preprocessing without writing to the database
- Returns the same result structure as a live ingest

### Exception Flows
**Structuring detected:** Record is accepted but STRUCTURING_PATTERN flag is included in the result for downstream compliance review

---

## UC-14 — Monitor Transactions in Real Time

| Field | Detail |
|---|---|
| **Use Case ID** | UC-14 |
| **Name** | Monitor Transaction Stream in Real Time |
| **Actor** | Analyst, Admin |
| **Preconditions** | Actor is authenticated; monitoring service running (in-memory) |
| **Postconditions** | Actor sees live fraud metrics, velocity stats, network analysis, and event feed |
| **Trigger** | Actor navigates to the Live Monitor view |

### Main Success Scenario
1. Actor opens the Live Monitor view
2. Browser connects to the SSE stream at GET /api/monitor/stream
3. Server pushes monitoring snapshots every 3 seconds
4. Actor sees live KPI tiles: tx/min rate, blocked count, flagged count, hourly volume
5. Actor sees a live event feed: each recent transaction with status, amount, score, timestamp
6. Actor sees system alerts (if any threshold is exceeded)
7. Actor sees network analysis: devices and IPs shared across multiple customer accounts
8. Actor views active threshold configuration

### Alternative Flows
**SSE unavailable (proxy blocks streaming):**
- Browser falls back to polling GET /api/monitor/realtime every 4 seconds

**Admin: update threshold at runtime:**
- Admin sends PUT /api/monitor/thresholds with updated values
- Changes take effect immediately for all subsequent transactions

**Per-customer velocity lookup:**
- Actor calls GET /api/monitor/customer/<id>
- Returns 1-min, 5-min, 1-hr counts and hourly amount vs. threshold comparison

### Exception Flows
**Browser disconnects:** GeneratorExit caught cleanly; SSE generator loop exits; no crash
**Monitoring update fails:** Exception caught and logged as warning; fraud analysis result not affected

---

## UC-15 — Run Live Demo

| Field | Detail |
|---|---|
| **Use Case ID** | UC-15 |
| **Name** | Run Interactive Fraud Pipeline Demo |
| **Actor** | Analyst, Admin |
| **Preconditions** | Actor is authenticated; at least one customer exists in the database |
| **Postconditions** | Fraud analysis result displayed with full pipeline visualisation |
| **Trigger** | Actor navigates to the Live Demo view and clicks "Run Analysis" |

### Main Success Scenario
1. Actor opens the Live Demo view
2. System automatically loads real customer IDs from the database (GET /api/customers)
3. System pre-populates all scenario forms with valid customer IDs
4. Actor selects a fraud scenario from the panel:
   - **High-Amount Wire:** $85,000, location=RU — expected: blocked
   - **OFAC Block:** Sanctioned customer name — expected: blocked (Stage 0)
   - **Velocity Burst:** Repeated transactions — expected: flagged
   - **Age Restriction:** Under-18 customer — expected: blocked (Stage 0)
   - **Normal Purchase:** $42.99 domestic — expected: approved
5. Actor optionally edits any field in the form
6. Actor clicks "Run Analysis"
7. System submits transaction to POST /api/transactions and waits for response
8. System renders the result panel:
   - Status banner (APPROVED / FLAGGED / BLOCKED) with colour coding
   - Score bars for rule score, ML score, combined score
   - Risk level badge
   - Rule violations list with descriptions
   - Pipeline visualisation showing which stages ran and which were skipped

### Alternative Flows
**No customers in database:**
- Form falls back to hardcoded IDs; if those fail, error toast shown with clear message

**Analyst modifies scenario fields:**
- The free-form inputs allow any custom transaction to be tested

### Exception Flows
**API error during analysis:**
- Loading spinner dismissed
- Error toast shown with error message
- "Run Analysis" button re-enabled
