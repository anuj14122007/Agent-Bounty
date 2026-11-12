# AgentBounty — Security & Financial Controls

## 1. Threat Model & Security Posture

AgentBounty operates in an environment where autonomous software agents delegate work and propose monetary disbursements. The core threat model addresses:
1. **Agent Overspending / Rogue Allocations:** An autonomous agent assigning excessive or unauthorized bounties.
2. **Double Payouts / Replay Attacks:** Repeated payout requests against a single task deliverable.
3. **Deceptive Simulation:** Presenting simulated transactions as real payments or falsifying provider confirmations.
4. **Credential Leakage:** Exposing API secrets in logs, repositories, or error traces.
5. **Audit History Tampering:** Modifying or deleting audit records to conceal illicit activity.

---

## 2. Financial Controls & Money Safety

### 2.1. Strict Prohibition of Floating-Point Types
Floating-point arithmetic (IEEE 754 `float`) introduces binary rounding artifacts (e.g. `0.1 + 0.2 = 0.30000000000000004`) which corrupt financial totals.
- **Application Calculations:** Restricted strictly to `decimal.Decimal`.
- **Database Persistence:** Stored exclusively as signed 64-bit integers representing minor units (cents for USD: `$5.00` → `500`).
- **Validation:** Float inputs to money functions, Pydantic schemas, or Settings are immediately rejected with `InvalidMoneyError` or `ConfigurationError`.
- **Rounding:** Silent rounding of sub-cent amounts is strictly prohibited. Any fractional minor unit raises an error.

### 2.2. Safety Ceilings
- Per-task bounty allocations are validated against `MAX_BOUNTY_USD` (default `$5.00`).
- An absolute maximum safety ceiling (`$100.00`) is enforced at the configuration layer to prevent accidental high-value commitments during testing.

---

## 3. Human Financial Authorization Gate

Autonomous agents (Manager or Worker) have **zero authority to disburse funds**.

1. **Role Check vs. Identity Authentication (Important Boundary):**
   - The application enforces that only `ActorContext.actor_type == "HUMAN"` may authorize, reject, or revoke payouts.
   - **Crucial Distinction:** This is an application-layer role check, **NOT independent identity authentication**. The `actor_id` (e.g. `"operator"`, `"founder"`) is supplied by the caller or UI; there is no cryptographic PKI, OAuth session, password authentication, or identity proofing in this demo architecture.
   - In Session 4, the Streamlit user interface must require an explicit, un-automated human confirmation action (button click) to submit an authorization.
2. **Discrete Entity:** Authorizations are tracked as independent persistence entities (`PaymentAuthorization`), not simple boolean flags on a task or transaction.
3. **Immutable Traceability:** Every authorization records:
   - Authorizing actor attribution identifier (`actor_id`).
   - Timestamp in UTC.
   - Exact authorized amount in minor units and currency.
   - Associated task and bounty foreign keys.
4. **Pre-condition for Execution:** The payment subsystem will refuse execution if no valid `PaymentAuthorization` with `decision == AUTHORIZED` exists. Any attempt by `MANAGER`, `WORKER`, or `SYSTEM` actors raises `UnauthorizedActorError`.

---

## 4. Idempotency & Replay Prevention

1. **Deterministic Idempotency Keys:** Every `PaymentTransaction` derives a deterministic `idempotency_key` via SHA-256 hash of `f"{task_id}:{authorization_id}"`.
2. **Database Constraint:** A unique database index on `payment_transactions.idempotency_key` guarantees that the database engine rejects duplicate transactions even under concurrent requests.
3. **Application Defense:** The `PaymentExecutionService` checks for existing transactions before invoking providers:
   - Transactions in `SUCCEEDED`, `PENDING`, `SUBMITTED`, `UNKNOWN`, or `CREATED` return the authoritative record with `is_duplicate=True` without duplicate provider execution.
   - Terminal `FAILED` transactions cannot be re-executed under the same authorization (`DuplicatePaymentError`), requiring human review and explicit re-authorization.

---

## 5. Simulation vs. Sandbox vs. Live Execution

| Property | SIMULATED Mode | SANDBOX Mode | LIVE Mode |
|---|---|---|---|
| **Primary Use** | Local development, CI/CD, offline demos | Integration testing against PayPal Sandbox | Real money payouts |
| **Allowed in DEMO_MODE?** | **YES** (Default) | NO | **FORBIDDEN** |
| **External API Calls?** | NONE (100% offline) | PayPal Sandbox REST API (Mocked in tests) | N/A |
| **External Reference** | `None` (Never fabricated) | Real PayPal Payout Batch ID | N/A |
| **Configuration Guard** | Default | `PAYPAL_PAYOUTS_ENABLED=true`, `PAYPAL_ENVIRONMENT=sandbox` | **Strictly blocked at startup** |

### Critical Invariants:
1. **No Fabricated References:** A simulated transaction is explicitly recorded with `execution_mode = SIMULATED`. The system **never** fabricates synthetic PayPal transaction IDs or pretends a mock payment went through an external processor.
2. **PayPal Sender Country Limitation:** Under PayPal Payouts documentation, accounts registered in India (`IN`) are limited to "Receive and withdraw" and cannot send payouts. The `paypal_sender_country` setting provides an advisory fail-closed check that rejects `IN`.
   - **Limitation Notice:** A self-declared environment variable (`PAYPAL_SENDER_COUNTRY`) is not proof of the merchant account's actual registered country or PayPal-verified eligibility. Server-side account eligibility is determined solely by PayPal's backend.
3. **No Live Payments:** Live endpoints, real funds, and live credentials are fundamentally excluded from the architecture.

## 6. Secrets Management

1. **No Hardcoded Credentials:** No credentials exist in the source code.
2. **Safe Template:** `.env.example` contains only non-sensitive placeholder variables.
3. **Git Protection:** `.gitignore` excludes `.env`, `.env.*`, and `.streamlit/secrets.toml`.
4. **Log Masking:** The `Settings` model implements custom `__repr__` masking to ensure `paypal_client_secret` is masked with `***` and never leaked in log output or diagnostic dumps.

---

## 7. Append-Only Audit Integrity

1. **No In-Place Modifications:** The `AuditEvent` table captures all domain events chronologically.
2. **Repository Safeguards:** `AuditEventRepository` exposes only `append` and query operations. Attempting to call `update` or `delete` raises `AppendOnlyViolationError`.
3. **Correlation Tracking:** Events accept an optional `correlation_id` to trace end-to-end distributed agent workflows back to the originating human command.
