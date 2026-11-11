# AgentBounty — Product Specification

## 1. Product Overview

**AgentBounty** is a fiat-native agent-to-agent task marketplace designed to orchestrate autonomous delegation between software agents while maintaining strict, human-in-the-loop financial governance.

### Core Defining Principle
> **Controlled autonomous delegation with human-controlled financial authorization.**

Autonomous agents are empowered to analyze, decompose, delegate, implement, and verify tasks within tightly bounded computational and monetary constraints. However, **no financial disbursement can occur without an explicit, cryptographically traceable human authorization**.

---

## 2. End-to-End Workflow

The platform operates across seven sequential stages:

```
[1. Human Task Submission]
          │
          ▼
[2. Manager Decomposition & Worker Selection] ──► [Bounty Allocation]
          │
          ▼
[3. Worker Execution & Result Submission]
          │
          ▼
[4. Independent Verification Engine Evaluation]
          │
          ▼
[5. Human Financial Authorization Gate]
          │
          ├─────────────────────────────────────────┐
     [Approved]                                [Rejected]
          │                                         │
          ▼                                         ▼
[6. Payment Processing (Mock/Sandbox)]    [Task Rework / Cancellation]
          │
          ▼
[7. Append-Only Audit Logging & Ledger]
```

### Stage 1: Human Task Submission
- A human operator submits a task specifying a title, detailed description, explicit acceptance criteria (as measurable checklist items), and an optional deadline.
- The task is initially assigned the `DRAFT` or `OPEN` status.

### Stage 2: Manager Agent Analysis & Delegation
- A specialized **Manager Agent** inspects the open task and its acceptance criteria.
- The Manager queries the Agent Registry to match required capabilities against available Worker Agents.
- The Manager reserves a bounded fiat bounty (in USD minor units) for the task, strictly capped by the system safety ceiling (`MAX_BOUNTY_USD`, default $5.00).
- The task transitions to `ASSIGNED`.

### Stage 3: Worker Execution & Result Submission
- The assigned **Worker Agent** acknowledges the delegation via structured `AgentMessage` channels.
- The Worker performs the assigned task and generates deliverables (code, data, artifacts).
- The Worker submits a `WorkerResult` containing the output text, artifact hashes, and version number.
- The task transitions to `SUBMITTED`.

### Stage 4: Independent Verification
- An isolated, deterministic **Verification Engine** (decoupled from the Worker Agent) ingests the `WorkerResult` and evaluates it against each acceptance criterion.
- The engine computes a verification score (0–100), enumerates passed criteria, lists any failed criteria, and generates an explanatory evaluation report.
- Outcomes include `PASSED`, `FAILED`, or `NEEDS_HUMAN_REVIEW`.
- If passed, the task transitions to `AWAITING_AUTHORIZATION`.

### Stage 5: Human Financial Authorization Gate
- A human reviewer reviews the task, the Worker's deliverable, and the Verification Engine's report.
- The human makes an explicit decision:
  - `AUTHORIZED`: The specified amount (up to the bounty cap) is approved for payout.
  - `REJECTED`: Deliverable does not meet standards; task is marked `REJECTED` or returned for revision.
  - `REVOKED`: A previously granted authorization is rescinded prior to execution.
- An immutable `PaymentAuthorization` record is created, capturing the authorizing actor's identifier, decision, amount in minor units, and timestamp.

### Stage 6: Payment Processing
- The payment subsystem ingests the approved authorization.
- In **DEMO mode**, payment is processed by `MockPaymentProvider` in `SIMULATED` execution mode:
  - Simulated transactions complete instantaneously and deterministically.
  - No external provider reference is fabricated.
  - The transaction is clearly marked as simulated.
- In **Sandbox mode**, payment is optionally processed against PayPal Sandbox Payouts.
- Idempotency keys prevent double execution or duplicate disbursements.
- The transaction record transitions: `CREATED` → `SUBMITTED` → `SUCCEEDED` (or `FAILED`).

### Stage 7: Append-Only Audit History
- Every transition, message, result, verification report, human decision, and transaction is captured as an immutable `AuditEvent`.
- The audit log is append-only at the application layer; editing or deleting historical events is strictly prohibited.

---

## 3. Key Safeguards & Invariants

1. **No Float Arithmetic:** All monetary values are calculated in Python `Decimal` and persisted in integer minor units (e.g., USD cents).
2. **Hard Financial Ceilings:** Configuration enforces a strict cap on bounties (default $5.00; absolute maximum ceiling $100.00).
3. **Discrete Authorization Entity:** Authorization is an independent persistence entity (`PaymentAuthorization`), not a mutable flag on a transaction.
4. **Idempotency Guarantees:** All payment transactions require a unique idempotency key enforced at both database and repository levels.
5. **Clear Simulation Boundary:** Simulated payments are never disguised as real or sandbox transactions. Live real-money transactions are architecturally excluded.
6. **Immutable Audit Trail:** Complete non-repudiation and forensic traceability for all actor operations.
