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

1. **Discrete Entity:** Authorizations are tracked as independent persistence entities (`PaymentAuthorization`), not simple boolean flags on a task or transaction.
2. **Immutable Traceability:** Every authorization records:
   - Authorizing actor identity (e.g., human operator ID).
   - Timestamp in UTC.
   - Exact authorized amount in minor units and currency.
   - Associated task and bounty foreign keys.
3. **Pre-condition for Execution:** The payment subsystem will refuse execution if no valid `PaymentAuthorization` with `decision == AUTHORIZED` exists.

---

## 4. Idempotency & Replay Prevention

1. **Unique Idempotency Keys:** Every `PaymentTransaction` must possess a unique `idempotency_key` (e.g. UUIDv4 or SHA-256 hash derived from task ID + authorization ID).
2. **Database Constraint:** A unique database index on `payment_transactions.idempotency_key` guarantees that the database engine rejects duplicate transactions even under race conditions.
3. **Application Defense:** The `PaymentTransactionRepository` checks for existing keys before insertion and raises `DuplicateEntityError`.

---

## 5. Simulation vs. Sandbox vs. Live Execution

| Property | SIMULATED Mode | SANDBOX Mode | LIVE Mode |
|---|---|---|---|
| **Primary Use** | Local development, CI/CD, offline demos | Integration testing against PayPal Sandbox | Real money payouts |
| **Allowed in DEMO_MODE?** | **YES** (Default) | NO | **FORBIDDEN** |
| **External API Calls?** | NONE (100% offline) | PayPal Sandbox REST API | N/A |
| **External Reference** | `None` (Never fabricated) | Real PayPal Payout Batch ID | N/A |
| **Configuration Guard** | Default | `PAYPAL_PAYOUTS_ENABLED=true`, `PAYPAL_ENVIRONMENT=sandbox` | **Strictly blocked at startup** |

### Critical Invariant:
A simulated transaction is explicitly recorded with `execution_mode = SIMULATED`. The system **never** fabricates a synthetic PayPal transaction ID or pretends a mock payment went through an external processor.

---

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
