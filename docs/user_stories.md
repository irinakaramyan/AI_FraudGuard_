# User Stories — FraudGuard AI Detection System

**Project:** FraudGuard AI  
**Version:** 3.0  
**Last Updated:** 2026-05-04  
**Format:** As a [role], I want to [action], so that [benefit]

---

## 1. Roles

| Role | Description |
|---|---|
| **Admin** | System administrator — full access, manages users, rules, 2FA, monitoring thresholds |
| **Analyst** | Fraud analyst — reviews alerts, investigates transactions, uses AI assistant, exports reports |
| **System** | Automated processes — background jobs, ML pipeline, monitoring service |

---

## 2. Authentication & Security

### US-01 — Secure Login
**As an** Admin or Analyst,  
**I want to** log in with my username and password,  
**So that** I can securely access the fraud monitoring platform.

**Acceptance Criteria:**
- [ ] Login form accepts username and password
- [ ] Invalid credentials return a generic error (no username enumeration)
- [ ] Account locks after 5 failed attempts for 15 minutes
- [ ] Successful login redirects to the dashboard

**Priority:** Must Have | **Story Points:** 3

---

### US-02 — Two-Factor Authentication (Admin)
**As an** Admin,  
**I want to** enable TOTP-based two-factor authentication on my account,  
**So that** my administrator access is protected even if my password is compromised.

**Acceptance Criteria:**
- [ ] Admin can open 2FA setup from the sidebar lock icon
- [ ] System generates a TOTP secret and displays a QR code
- [ ] Admin scans QR with Google Authenticator or Authy
- [ ] Admin confirms activation by entering a valid 6-digit code
- [ ] Subsequent admin logins prompt for TOTP code after correct password
- [ ] Incorrect TOTP code shows a clear error and does not grant access
- [ ] Admin can disable 2FA by verifying with a valid TOTP code

**Priority:** Must Have | **Story Points:** 8

---

### US-03 — Session Management
**As an** Analyst,  
**I want to** be automatically logged out after 1 hour of inactivity,  
**So that** my session cannot be hijacked if I leave my workstation unattended.

**Acceptance Criteria:**
- [ ] JWT token expires after 3600 seconds
- [ ] Expired token returns 401 and redirects to login
- [ ] User sees "Token has expired. Please log in again."

**Priority:** Must Have | **Story Points:** 2

---

### US-04 — User Management
**As an** Admin,  
**I want to** create and manage user accounts with assigned roles,  
**So that** team members have appropriate access levels.

**Acceptance Criteria:**
- [ ] Admin can create users with roles: admin, analyst
- [ ] Username, email, and password are required
- [ ] Duplicate username or email is rejected with a clear message
- [ ] Admin can list all users with their roles and last login times
- [ ] Analyst cannot access user management (403 Forbidden)
- [ ] Admin-only views (Detection Rules) are hidden from analyst accounts

**Priority:** Must Have | **Story Points:** 5

---

## 3. Transaction Processing

### US-05 — Submit Transaction for Analysis
**As an** Analyst or System,  
**I want to** submit a financial transaction for automated fraud analysis,  
**So that** potentially fraudulent activity is detected and flagged in real time.

**Acceptance Criteria:**
- [ ] System accepts: customer ID, amount, currency, merchant name, location, card type
- [ ] Amount must be positive and not exceed $10,000,000
- [ ] Currency validated against ISO 4217 whitelist
- [ ] Response includes: status (approved/flagged/blocked), risk score breakdown, rule violations
- [ ] Processing completes within 3 seconds under normal load
- [ ] Ingestion preprocessing runs automatically before fraud pipeline

**Priority:** Must Have | **Story Points:** 13

---

### US-06 — View Transaction List
**As an** Analyst,  
**I want to** view a paginated, filterable list of all transactions,  
**So that** I can quickly find and review specific transactions.

**Acceptance Criteria:**
- [ ] Table shows: ID, customer, amount, merchant, status, risk score, risk level, timestamp
- [ ] Filter by status, risk level, amount range, and customer country
- [ ] Search by customer name, merchant name, or transaction ID
- [ ] Clear all filters with one button
- [ ] Pagination with 15 rows per page

**Priority:** Must Have | **Story Points:** 8

---

### US-07 — Transaction Detail View
**As an** Analyst,  
**I want to** click on a transaction to see its full details and risk breakdown,  
**So that** I can understand why it was flagged and make an informed decision.

**Acceptance Criteria:**
- [ ] Modal shows all transaction fields
- [ ] Shows rule score, ML score, and combined score as percentages
- [ ] Lists each rule violation with description
- [ ] Shows related fraud alerts with severity
- [ ] Buttons to mark as legitimate or confirm as fraud

**Priority:** Must Have | **Story Points:** 5

---

### US-08 — Review Transaction
**As an** Analyst,  
**I want to** manually review a flagged transaction and update its status,  
**So that** false positives are cleared and confirmed fraud is escalated.

**Acceptance Criteria:**
- [ ] Analyst can mark a transaction as legitimate (status → approved)
- [ ] Analyst can confirm as fraud (status → blocked, is_fraud = true)
- [ ] Action is logged in the audit trail

**Priority:** Must Have | **Story Points:** 3

---

## 4. Fraud Detection

### US-09 — Automated Rule-Based Detection
**As a** System,  
**I want to** evaluate each transaction against active fraud rules,  
**So that** pattern-based fraud is detected consistently and immediately.

**Acceptance Criteria:**
- [ ] Rules evaluated: HIGH_AMOUNT, HIGH_FREQUENCY, HIGH_RISK_COUNTRY, RAPID_SUCCESSION, NEW_DEVICE, ROUND_AMOUNT
- [ ] Each rule has a configurable threshold and weight
- [ ] Rule score is a weighted average between 0.0 and 1.0
- [ ] All violated rules are returned with descriptions

**Priority:** Must Have | **Story Points:** 8

---

### US-10 — ML Anomaly Detection
**As a** System,  
**I want to** score each transaction using a trained Isolation Forest model,  
**So that** unusual patterns not covered by rules are also detected.

**Acceptance Criteria:**
- [ ] Model engineers 14 features from transaction and customer data
- [ ] Returns anomaly probability between 0.0 and 1.0
- [ ] Model is loaded from disk on startup (not retrained per request)
- [ ] If model is unavailable, rule score is used alone with a warning

**Priority:** Must Have | **Story Points:** 8

---

### US-11 — Combined Risk Scoring
**As a** System,  
**I want to** combine rule and ML scores into a single weighted risk score,  
**So that** the fraud decision uses the best of both detection approaches.

**Acceptance Criteria:**
- [ ] combined_score = 0.40 × rule_score + 0.60 × ml_score
- [ ] Score mapped to risk level: low / medium / high / critical
- [ ] Score ≥ 0.75 → blocked; ≥ 0.45 → flagged; < 0.45 → approved
- [ ] RiskScore record persisted to database

**Priority:** Must Have | **Story Points:** 5

---

### US-12 — Configure Detection Rules (Admin)
**As an** Admin,  
**I want to** view and adjust fraud detection rules without code changes,  
**So that** the detection engine can be tuned to match evolving fraud patterns.

**Acceptance Criteria:**
- [ ] Rules listed with name, type, threshold, weight, and active status
- [ ] Admin can update threshold, weight, and toggle active/inactive
- [ ] Changes take effect on the next transaction submitted
- [ ] Analyst receives 403 Forbidden when attempting to modify rules

**Priority:** Should Have | **Story Points:** 5

---

## 5. Compliance & OFAC

### US-13 — OFAC Sanctions Screening
**As a** System,  
**I want to** screen every customer name against the OFAC SDN list before processing their transaction,  
**So that** the organisation does not facilitate transactions with sanctioned individuals.

**Acceptance Criteria:**
- [ ] Fuzzy name matching with Levenshtein distance ≥ 0.80 triggers a block
- [ ] Matched transactions are immediately blocked (status = blocked, score = 1.0)
- [ ] CRITICAL alert generated for every OFAC match
- [ ] Fail-closed: if OFAC service is unavailable, transaction is blocked
- [ ] Customer flagged with is_ofac_sanctioned = true

**Priority:** Must Have | **Story Points:** 13

---

### US-14 — Search OFAC SDN List
**As an** Analyst,  
**I want to** search the OFAC SDN list by name,  
**So that** I can manually verify whether a person or entity is sanctioned.

**Acceptance Criteria:**
- [ ] Search returns SDN entries with name, type, programme, and match score
- [ ] Full SDN list is paginated and browsable without a search term

**Priority:** Must Have | **Story Points:** 5

---

### US-15 — Daily OFAC List Refresh
**As a** System,  
**I want to** automatically download and refresh the OFAC SDN list daily,  
**So that** newly designated individuals are screened without manual intervention.

**Acceptance Criteria:**
- [ ] Scheduler runs at 02:00 UTC every day
- [ ] Downloads from the US Treasury official source
- [ ] Updates database entries and logs result (success/failure/entry count)
- [ ] Last refresh timestamp visible in the UI

**Priority:** Must Have | **Story Points:** 5

---

### US-16 — Age Restriction Compliance
**As a** System,  
**I want to** block transactions from customers under 18 or over 100 years old,  
**So that** the platform complies with KYC age verification requirements.

**Acceptance Criteria:**
- [ ] Age computed from date_of_birth at transaction time
- [ ] Age < 18 → immediate block with AGE_RESTRICTION violation and CRITICAL alert
- [ ] Age > 100 → immediate block (likely identity fraud or DOB error)
- [ ] Stages 1–5 of the pipeline are skipped when age block fires

**Priority:** Must Have | **Story Points:** 3

---

## 6. Alerts

### US-17 — View and Manage Fraud Alerts
**As an** Analyst,  
**I want to** view all open fraud alerts sorted by severity,  
**So that** the most critical issues are addressed first.

**Acceptance Criteria:**
- [ ] Alert list shows: type, severity, description, transaction, timestamp, resolved status
- [ ] Filter by severity and resolved/open state
- [ ] Click alert to see full detail including risk factors
- [ ] Analyst can resolve an alert with resolution notes

**Priority:** Must Have | **Story Points:** 5

---

### US-18 — Alert Notification Badge
**As an** Analyst,  
**I want to** see a live count of unresolved alerts in the sidebar,  
**So that** I am immediately aware of new alerts without refreshing the page.

**Acceptance Criteria:**
- [ ] Badge shows unresolved alert count in navigation
- [ ] Badge hidden when count is zero
- [ ] Count updates on dashboard refresh

**Priority:** Should Have | **Story Points:** 2

---

## 7. AI Assistant (RAG-Powered)

### US-19 — Ask the AI Fraud Assistant
**As an** Analyst,  
**I want to** ask the AI assistant fraud-related questions in natural language,  
**So that** I can get expert guidance on AML rules, risk scoring, and regulatory requirements without leaving the platform.

**Acceptance Criteria:**
- [ ] Text input accepts questions up to 500 characters
- [ ] AI responds with accurate, domain-specific answers
- [ ] Multi-turn conversation context is maintained within the session (capped at 20 turns)
- [ ] Assistant handles casual greetings gracefully
- [ ] Response displayed with markdown formatting

**Priority:** Should Have | **Story Points:** 8

---

### US-20 — RAG-Grounded AI Responses
**As an** Analyst,  
**I want to** receive AI answers that are grounded in the actual project documentation,  
**So that** the assistant gives accurate, project-specific answers rather than generic ones.

**Acceptance Criteria:**
- [ ] Project docs/ directory is indexed at startup using Jaccard similarity
- [ ] Top-3 most relevant chunks are retrieved for each query
- [ ] Retrieved context is prepended to the LLM prompt before sending
- [ ] If no relevant chunks found, query is sent without RAG context (graceful degradation)
- [ ] Groq used as primary provider; Anthropic as fallback; clear error if neither configured

**Priority:** Should Have | **Story Points:** 5

---

## 8. Dashboard & Analytics

### US-21 — Real-Time Dashboard
**As an** Analyst,  
**I want to** see real-time KPI metrics on the dashboard,  
**So that** I have an immediate overview of the system's fraud detection status.

**Acceptance Criteria:**
- [ ] KPI cards: total transactions, fraud rate, open alerts, total processed amount, customer count, avg risk score
- [ ] Transaction trend chart for the last 7 days
- [ ] Risk distribution donut chart
- [ ] Alert type breakdown chart
- [ ] Dashboard refreshes on demand

**Priority:** Must Have | **Story Points:** 8

---

## 9. Reporting & Export

### US-22 — Export Transaction Report
**As an** Analyst,  
**I want to** export filtered transactions to CSV,  
**So that** I can analyse data in Excel or import it into a compliance reporting tool.

**Acceptance Criteria:**
- [ ] Export respects active filters
- [ ] CSV includes all key fields: ID, customer, amount, merchant, status, scores
- [ ] CSV cells sanitised against formula injection (=, +, -, @ prefix)
- [ ] Maximum 10,000 rows per export

**Priority:** Should Have | **Story Points:** 5

---

### US-23 — Compliance Report (Admin)
**As an** Admin,  
**I want to** generate a compliance metrics report covering CTR thresholds, OFAC flags, and SAR candidates,  
**So that** the organisation can demonstrate regulatory compliance to auditors.

**Acceptance Criteria:**
- [ ] Report shows: transactions ≥ $10,000 (CTR), OFAC-flagged customers, CRITICAL alerts (SAR candidates)
- [ ] Filterable by date range
- [ ] Available as JSON via API
- [ ] Analyst receives 403 Forbidden when attempting to access this endpoint

**Priority:** Should Have | **Story Points:** 5

---

## 10. Customer Management

### US-24 — Customer Risk Profiles
**As an** Analyst,  
**I want to** view customer profiles with risk levels and transaction history,  
**So that** I can understand a customer's fraud risk before or after reviewing their transactions.

**Acceptance Criteria:**
- [ ] Customer list shows: name, email, country, risk level, OFAC flag, transaction count
- [ ] Customer risk level automatically updated after each transaction
- [ ] Customer detail shows transaction history and current risk score

**Priority:** Must Have | **Story Points:** 5

---

## 11. Data Ingestion & Preprocessing

### US-25 — Automated Transaction Preprocessing
**As a** System,  
**I want to** automatically normalise and enrich each transaction before fraud analysis,  
**So that** the fraud pipeline always receives clean, consistent, and compliant data.

**Acceptance Criteria:**
- [ ] Preprocessing runs automatically for every transaction submitted via POST /api/transactions
- [ ] Location normalised to uppercase; strings trimmed; amounts converted to float
- [ ] Additional features derived: hour_of_day, day_of_week, is_weekend, amount_magnitude
- [ ] Rejected records return 422 with rejection reason and data quality report
- [ ] PII (email, phone, IP) masked in all log output

**Priority:** Must Have | **Story Points:** 8

---

### US-26 — Batch Data Ingestion
**As an** Analyst or System,  
**I want to** submit multiple transaction records in a single batch request,  
**So that** historical data can be loaded efficiently without making hundreds of individual API calls.

**Acceptance Criteria:**
- [ ] Batch endpoint accepts up to 500 records per request
- [ ] Each record is validated and preprocessed independently
- [ ] Response includes: processed count, rejected count, per-record error details
- [ ] Dry-run preview endpoint validates payload without writing to the database

**Priority:** Should Have | **Story Points:** 5

---

### US-27 — Structuring Detection in Ingestion
**As a** System,  
**I want to** flag transactions in the $9,500–$9,999 range during preprocessing,  
**So that** potential CTR avoidance (structuring) is identified before the fraud pipeline runs.

**Acceptance Criteria:**
- [ ] Transactions with amount ≥ $9,500 and < $10,000 are flagged with STRUCTURING_PATTERN
- [ ] Flag is included in the preprocessing result and passed to the fraud pipeline
- [ ] Structuring flag does not by itself block the transaction — it is an additional signal

**Priority:** Must Have | **Story Points:** 3

---

## 12. Real-Time Transaction Monitoring

### US-28 — Live Transaction Monitoring Stream
**As an** Analyst,  
**I want to** see a live stream of transaction events with fraud metrics,  
**So that** I can monitor the system's health and detect unusual patterns in real time.

**Acceptance Criteria:**
- [ ] Live Monitor view connects to SSE stream (GET /api/monitor/stream)
- [ ] Snapshot pushed every 3 seconds: tx/min rate, blocked count, flagged count, hourly volume
- [ ] Live event feed shows recent transactions with status, amount, risk score, and timestamp
- [ ] System alerts displayed when any threshold is exceeded (block rate spike, velocity surge)
- [ ] Fallback to polling (GET /api/monitor/realtime) if SSE is unavailable
- [ ] Monitor automatically stops when leaving the view; resumes on return

**Priority:** Must Have | **Story Points:** 13

---

### US-29 — Fraud Ring Network Analysis
**As an** Analyst,  
**I want to** see which devices and IP addresses are shared across multiple customer accounts,  
**So that** I can identify coordinated fraud rings operating across multiple accounts.

**Acceptance Criteria:**
- [ ] Network panel shows count of devices shared by more than 3 customers
- [ ] Network panel shows count of IPs shared by more than 5 customers
- [ ] Top shared devices and IPs listed with customer counts
- [ ] Admin can update sharing thresholds at runtime via PUT /api/monitor/thresholds

**Priority:** Should Have | **Story Points:** 8

---

### US-30 — Per-Customer Velocity Monitoring
**As an** Analyst,  
**I want to** see real-time velocity statistics for any individual customer,  
**So that** I can assess whether a customer is transacting at an unusual rate before deciding to review or block their account.

**Acceptance Criteria:**
- [ ] GET /api/monitor/customer/<id> returns: tx in last 1 min, 5 min, 1 hr; hourly amount
- [ ] Response includes threshold comparison: which limits are exceeded
- [ ] Status field: "alert" if any threshold exceeded, "normal" otherwise

**Priority:** Should Have | **Story Points:** 3

---

## 13. Interactive Live Demo

### US-31 — Interactive Fraud Pipeline Demo
**As an** Analyst or Admin,  
**I want to** run pre-built fraud scenarios through the live system and see the full pipeline output,  
**So that** I can understand how the fraud detection engine works and demonstrate it to stakeholders.

**Acceptance Criteria:**
- [ ] Demo view offers 5 scenarios: High-Amount Wire, OFAC Block, Velocity Burst, Age Restriction, Normal Purchase
- [ ] On page load, real customer IDs are fetched from the database automatically
- [ ] Each scenario pre-fills all form fields with realistic data
- [ ] Analyst can edit any field before running
- [ ] "Run Analysis" submits a real transaction through the full fraud pipeline
- [ ] Result panel shows: status banner, score bars (rule/ML/combined), risk level badge
- [ ] Rule violations listed with descriptions and severity
- [ ] Pipeline visualisation shows which stages ran and which were skipped
- [ ] Loading indicator shown during analysis; button re-enabled after result

**Priority:** Should Have | **Story Points:** 8

---

## 14. Story Map Summary

| Epic | Must Have | Should Have | Total |
|---|---|---|---|
| Authentication & Security | US-01, US-02, US-03, US-04 | — | 4 |
| Transaction Processing | US-05, US-06, US-07, US-08 | — | 4 |
| Fraud Detection | US-09, US-10, US-11 | US-12 | 4 |
| Compliance & OFAC | US-13, US-14, US-15, US-16 | — | 4 |
| Alerts | US-17 | US-18 | 2 |
| AI Assistant (RAG) | — | US-19, US-20 | 2 |
| Dashboard | US-21 | — | 1 |
| Reporting | — | US-22, US-23 | 2 |
| Customer Management | US-24 | — | 1 |
| Data Ingestion | US-25, US-27 | US-26 | 3 |
| Real-Time Monitoring | US-28 | US-29, US-30 | 3 |
| Live Demo | — | US-31 | 1 |
| **Total** | **19** | **12** | **31** |

---

## 15. Total Story Points by Priority

| Priority | Stories | Points |
|---|---|---|
| Must Have | 19 | 114 |
| Should Have | 12 | 73 |
| **Total** | **31** | **187** |
