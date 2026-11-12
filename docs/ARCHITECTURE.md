# AgentBounty — Architecture Documentation

## 1. Architectural Philosophy: The Modular Monolith

AgentBounty is designed as a **clean, maintainable modular monolith**, intentionally avoiding distributed microservices, message queues (Celery/RabbitMQ), external caches (Redis), or containerized service clusters at this stage.

### Why a Modular Monolith?
- **Transactional Consistency:** Relational integrity, foreign keys, and idempotency guarantees can be enforced atomically within the persistence layer without distributed saga coordination.
- **Low Operational Overhead:** The application runs locally or in containerized evaluation environments with zero external infrastructure dependencies in `DEMO_MODE`.
- **Fast Developer Ergonomics:** Clean in-memory and local SQLite persistence allows instant test runs (<2 seconds) and rapid iteration during development sessions.
- **Clean Boundaries for Evolution:** Explicit module boundaries and strict dependency rules ensure individual subsystems can be decomposed into independent services in the future if scale warrants it.

---

## 2. Layered Architecture & Dependency Direction

The codebase strictly adheres to unidirectional dependency flow:

```
[Presentation / UI Layer]  (e.g., Streamlit Dashboard - Future Session)
           │
           ▼
[Application Services Layer] (TaskService, VerificationService, PaymentService)
           │
           ├──────────────────────────────┐
           ▼                              ▼
    [Domain Layer]               [Persistence Layer]
(Entities, Value Objects,        (SQLAlchemy Models, Base,
 Enums, Money, Schemas)           Database, Repositories)
```

### Dependency Rules:
1. **Domain Layer has zero outward dependencies:** It depends only on Python standard libraries (e.g., `decimal`, `enum`, `datetime`, `uuid`) and Pydantic for validation schemas. It contains no persistence or UI logic.
2. **Persistence Layer depends on Domain:** Models and repositories reference domain enums, exceptions, and money converters.
3. **Application Services depend on Domain and Persistence:** Business logic orchestrates transactions through repositories and validates against domain invariants.
4. **UI Layer depends strictly on Application Services:** Presentation components (e.g. Streamlit widgets) must never query database connections directly or mutate ORM objects outside application service transactions.
5. **Agent & Payment implementations must not bypass rules:** Specialist agents and payment adapters interact via defined application service contracts and persistence repositories.

---

## 3. Package Layout

```text
Agent-Bounty/
├── src/
│   └── agentbounty/
│       ├── __init__.py
│       ├── agents/               # Specialist workers, registry, and manager agent
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── manager.py
│       │   ├── profiles.py
│       │   ├── registry.py
│       │   └── workers/
│       │       ├── __init__.py
│       │       ├── base.py
│       │       ├── code_assistant.py
│       │       ├── creative_writer.py
│       │       ├── data_analyst.py
│       │       └── researcher.py
│       ├── config/               # Pydantic Settings & environment validation
│       │   ├── __init__.py
│       │   └── settings.py
│       ├── domain/               # Core business rules, enums, money, and schemas
│       │   ├── __init__.py
│       │   ├── enums.py
│       │   ├── money.py
│       │   └── schemas.py
│       ├── persistence/          # Persistence models, DB engine, and repositories
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── models.py
│       │   ├── database.py
│       │   └── repositories.py
│       ├── payments/             # Payment infrastructure, authorization gate, providers & ledger
│       │   ├── __init__.py
│       │   ├── authorization.py
│       │   ├── execution.py
│       │   ├── ledger.py
│       │   ├── protocols.py
│       │   ├── reconciliation.py
│       │   ├── schemas.py
│       │   └── providers/
│       │       ├── __init__.py
│       │       ├── mock.py
│       │       └── paypal_sandbox.py
│       ├── providers/            # Generation providers & protocols
│       │   ├── __init__.py
│       │   ├── demo_provider.py
│       │   └── protocols.py
│       ├── services/             # Application orchestration & communication services
│       │   ├── __init__.py
│       │   ├── agent_communication.py
│       │   ├── task_orchestration.py
│       │   └── verification.py
│       └── exceptions.py         # Standardized application exception hierarchy
├── migrations/                   # Alembic database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 001_initial_schema.py
├── tests/                        # Automated unit and integration tests (155 tests)
│   ├── conftest.py
│   ├── test_agents.py
│   ├── test_communication.py
│   ├── test_config.py
│   ├── test_database.py
│   ├── test_enums.py
│   ├── test_mock_provider.py
│   ├── test_models.py
│   ├── test_money.py
│   ├── test_orchestration.py
│   ├── test_payment_authorization.py
│   ├── test_payment_execution.py
│   ├── test_payment_ledger.py
│   ├── test_payment_reconciliation.py
│   ├── test_payment_workflow.py
│   ├── test_paypal_sandbox_provider.py
│   ├── test_repositories.py
│   ├── test_schemas.py
│   └── test_verification.py
├── docs/                         # Architecture, product specs, state machines, security
│   ├── ARCHITECTURE.md
│   ├── PRODUCT_SPEC.md
│   ├── STATE_MACHINES.md
│   └── SECURITY.md
├── data/                         # Local database folder (.gitignore protected)
│   └── .gitkeep
├── .env.example                  # Safe configuration template
├── .gitignore
├── alembic.ini                   # Migration runner configuration
├── pyproject.toml                # Project packaging & pytest config
├── requirements.txt              # Pinned/compatible requirements
├── README.md                     # Project overview and setup guide
└── BUILD_STATUS.md               # Session-by-session build audit log
```

---

## 4. Subsystem Contracts for Future Sessions

To prevent interface drift during subsequent sessions, the boundaries and contracts for future modules are established below:

### 4.1. Agent Subsystem
- **Manager Agent:**
  - *Responsibilities:* Ingests open tasks, assesses requirements against worker capabilities, selects worker agent, assigns bounty within `MAX_BOUNTY_USD`, and issues delegation message.
  - *Expected Input:* `TaskRead`
  - *Expected Output:* `TaskUpdate(assigned_agent_id=..., status=TaskStatus.ASSIGNED)` and `BountyCreate`.
- **Worker Agent Registry:**
  - *Responsibilities:* In-memory or database catalog of worker agents, their capabilities (e.g. `['python', 'data-scraping', 'text-summarization']`), and current availability (`ACTIVE`, `BUSY`).
- **Worker Agent:**
  - *Responsibilities:* Receives delegated task instructions, executes autonomous actions, compiles deliverable text and artifact metadata.
  - *Expected Output:* `WorkerResultCreate(content=..., artifact_metadata=...)`.
- **Independent Verification Engine:**
  - *Responsibilities:* Evaluates a `WorkerResult` against acceptance criteria independently from the Worker.
  - *Expected Input:* `(TaskRead, WorkerResultRead)`
  - *Expected Output:* `VerificationCreate(status=..., score=..., passed_criteria=..., failed_criteria=..., explanation=...)`.

### 4.2. Payment Subsystem
- **PaymentProvider Protocol (`agentbounty.payments.protocols`):**
  ```python
  class PaymentProvider(Protocol):
      @property
      def provider_name(self) -> str: ...
      @property
      def execution_mode(self) -> PaymentExecutionMode: ...
      def submit_payout(self, request: PayoutRequest) -> PayoutResult: ...
      def check_payout_status(self, payout_id: str, idempotency_key: str) -> PayoutResult: ...
  ```
- **MockPaymentProvider (`agentbounty.payments.providers.mock`):**
  - Fully offline, deterministic payout execution for `DEMO_MODE=true`.
  - Sets `execution_mode = PaymentExecutionMode.SIMULATED`.
  - Invariant: `external_reference is None` (never fabricates external transaction IDs or fake PayPal hashes).
  - Configurable simulation parameters for testing timeout, pending, or failure scenarios.
- **PayPalSandboxProvider (`agentbounty.payments.providers.paypal_sandbox`):**
  - Communicates exclusively with PayPal REST Sandbox endpoint (`https://api-m.sandbox.paypal.com/v1/payments/payouts`).
  - Sets `execution_mode = PaymentExecutionMode.SANDBOX`.
  - Captures PayPal batch payout ID in `external_reference`.
  - Prohibited in `DEMO_MODE=true` or when `PAYPAL_PAYOUTS_ENABLED=false`.
  - Fails closed with `IneligibleSenderCountryError` if `paypal_sender_country == "IN"` per PayPal Payouts documentation.
  - Supports dependency-injected `HttpTransport` for test isolation with zero live network calls.
- **PaymentAuthorizationService (`agentbounty.payments.authorization`):**
  - Enforces mandatory `HUMAN` actor verification for all authorization decisions.
  - Validates preconditions: Task must be `AWAITING_AUTHORIZATION`, Bounty `AWARDED`, Verification `PASSED`.
  - Enforces exact amount match, currency match, and configuration ceiling (`MAX_BOUNTY_USD`).
  - Supports authorization `AUTHORIZED`, `REJECTED`, and pre-submission `REVOKED`.
- **PaymentExecutionService (`agentbounty.payments.execution`):**
  - Enforces mandatory `HUMAN` actor context.
  - Computes deterministic SHA-256 idempotency key: `task_id:authorization_id`.
  - Returns existing authoritative transaction without re-calling provider if already submitted/processed (`is_duplicate=True`).
  - Persists `CREATED -> SUBMITTED` boundary and task/bounty `PAYMENT_PENDING` before invoking payment provider.
  - Transitions to `SUCCEEDED` (Task `COMPLETED`, Bounty `PAID`), `FAILED` (Task `FAILED`, Bounty `AWARDED`), or `UNKNOWN`.
- **PaymentReconciliationService (`agentbounty.payments.reconciliation`):**
  - Idempotent status resolution for `PENDING` and `UNKNOWN` transactions.
- **TransactionLedgerService (`agentbounty.payments.ledger`):**
  - Indexed queries across payment transactions and consolidated task payment histories.

### 4.3. UI / Presentation Subsystem (Streamlit)
- **Human Approval Panel:**
  - Displays pending tasks awaiting authorization (`AWAITING_AUTHORIZATION`).
  - Shows task details, Worker submission, and Verification report with side-by-side criteria breakdown.
  - Form with explicit "Authorize Payout" or "Reject / Request Revision" buttons requiring explicit human confirmation.
- **Audit & Transaction Ledger:**
  - Real-time read-only view of `PaymentTransaction` and `AuditEvent` streams.
