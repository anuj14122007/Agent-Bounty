# AgentBounty — Lifecycle & State Machines

## 1. Task Lifecycle State Machine

The `Task` entity coordinates the progression from initial human prompt to completion or failure.

```mermaid
flowchart TD
    DRAFT -->|Publish| OPEN
    OPEN -->|Manager Assigns Worker| ASSIGNED
    ASSIGNED -->|Worker Starts Execution| IN_PROGRESS
    IN_PROGRESS -->|Worker Submits Deliverable| SUBMITTED
    SUBMITTED -->|Verification Engine Evaluation| IN_REVIEW
    IN_REVIEW -->|Verification Fails| REJECTED
    IN_REVIEW -->|Verification Needs Human Review| IN_REVIEW
    IN_REVIEW -->|Verification Passes| APPROVED
    APPROVED -->|Awaiting Human Review| AWAITING_AUTHORIZATION
    AWAITING_AUTHORIZATION -->|Human Rejects| REJECTED
    AWAITING_AUTHORIZATION -->|Human Authorizes Payout| PAYMENT_PENDING
    PAYMENT_PENDING -->|Payment Confirmed| COMPLETED
    PAYMENT_PENDING -->|Payment Fails| FAILED

    OPEN -->|Human / System Cancels| CANCELLED
    ASSIGNED -->|Human / System Cancels| CANCELLED
    DRAFT -->|Discard| CANCELLED
```

### Transition Gates & Authorities:
| Initial State | Target State | Triggering Event | Gate / Authority |
|---|---|---|---|
| `DRAFT` | `OPEN` | Task published to marketplace | Human Creator |
| `OPEN` | `ASSIGNED` | Worker selected & bounty reserved | Manager Agent |
| `ASSIGNED` | `IN_PROGRESS` | Execution begins | Worker Agent |
| `IN_PROGRESS` | `SUBMITTED` | Deliverable uploaded | Worker Agent |
| `SUBMITTED` | `IN_REVIEW` | Verification begins | Verification Engine |
| `IN_REVIEW` | `REJECTED` | Verification criteria failed | Independent Verification Engine |
| `IN_REVIEW` | `IN_REVIEW` | Verification requires human review | Independent Verification Engine (Ambiguous/Subjective Criteria) |
| `IN_REVIEW` | `APPROVED` | All criteria satisfied (100% / passed) | Independent Verification Engine |
| `APPROVED` | `AWAITING_AUTHORIZATION` | Enters financial review queue | Automated Pipeline Gate |
| `AWAITING_AUTHORIZATION`| `PAYMENT_PENDING` | Payment authorization granted | **Explicit Human Authorization** (Mandatory) |
| `AWAITING_AUTHORIZATION`| `REJECTED` | Authorization rejected by human | **Human Operator Decision** |
| `PAYMENT_PENDING` | `COMPLETED` | Payout confirmed by provider | Payment Provider Callback / Result |
| `PAYMENT_PENDING` | `FAILED` | Provider payout failure | Payment Provider Callback / Result |
| `*` | `CANCELLED` | Explicit cancellation | Human Creator or System Admin |

---

## 2. Bounty Lifecycle State Machine

A task possesses at most one bounty. The bounty coordinates monetary liability.

```mermaid
flowchart LR
    OPEN -->|Task Assigned| RESERVED
    RESERVED -->|Deliverable Verified PASSED| AWARDED
    RESERVED -->|Deliverable FAILED or Cancelled| CANCELLED
    RESERVED -->|Needs Human Review| RESERVED
    AWARDED -->|Human Authorizes| PAYMENT_PENDING
    PAYMENT_PENDING -->|Payout Succeeded| PAID
    OPEN -->|Task Cancelled| CANCELLED
    AWARDED -->|Authorization Denied| CANCELLED
```

### States:
- `OPEN`: Bounty allocated but not yet reserved by a worker.
- `RESERVED`: Manager agent has assigned the task to a worker; funds are set aside.
- `AWARDED`: Independent verification confirmed deliverables met criteria; awaiting financial payout authorization.
- `PAYMENT_PENDING`: Human approved payout; payment provider processing disbursement.
- `PAID`: Funds successfully disbursed to recipient.
- `CANCELLED`: Bounty deallocated due to task rejection or cancellation.

---

## 3. Independent Verification State Machine

Evaluates deliverables submitted by Worker Agents against predefined acceptance criteria.

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PASSED: All Acceptance Criteria Met
    PENDING --> FAILED: Missing / Incomplete Criteria
    PENDING --> NEEDS_HUMAN_REVIEW: Ambiguous or Low Confidence Outcome
    PASSED --> [*]
    FAILED --> [*]
    NEEDS_HUMAN_REVIEW --> [*]
```

### Key Verification Rule:
The Worker Agent **never** verifies its own work. The Verification Engine runs in a separate process or isolated context to ensure objective evaluation.

---

## 4. Payment Authorization State Machine

The `PaymentAuthorization` entity preserves an immutable record of financial authorization decisions.

```mermaid
flowchart LR
    PENDING -->|Human Approves| AUTHORIZED
    PENDING -->|Human Disapproves| REJECTED
    AUTHORIZED -->|Pre-execution Revocation| REVOKED
```

### Rules:
- An authorization record must specify the exact amount in minor units and currency.
- Once created, a `PaymentAuthorization` cannot be deleted or mutated.
- Revocation creates a distinct revocation event / record, ensuring complete forensic traceability.

---

## 5. Payment Transaction State Machine

Payment transactions track the payment execution lifecycle through the chosen provider (`MockPaymentProvider` or `PayPalSandboxProvider`).

```mermaid
flowchart LR
    CREATED -->|Submitted to Provider| SUBMITTED
    SUBMITTED -->|Async Gateway Processing| PENDING
    SUBMITTED -->|Immediate Sync Success| SUCCEEDED
    PENDING -->|Provider Webhook Confirmed| SUCCEEDED
    SUBMITTED -->|Gateway Error / Rejection| FAILED
    PENDING -->|Gateway Timeout / Failure| FAILED
    SUBMITTED -->|Unresolved Network Failure| UNKNOWN
```

### Idempotency Protection:
- Every `PaymentTransaction` requires a unique `idempotency_key`.
- If an operation is retried with an existing key, the transaction repository rejects duplicate processing with `DuplicateEntityError`.
