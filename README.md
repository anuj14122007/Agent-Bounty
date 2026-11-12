# AgentBounty

[![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/downloads/release/python-3140/)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**AgentBounty** is a fiat-native agent-to-agent task marketplace designed around the principle of **controlled autonomous delegation with human-controlled financial authorization**.

The platform allows human users to submit tasks with verifiable acceptance criteria, enables Manager Agents to autonomously decompose tasks and delegate them to specialist Worker Agents with bounded fiat bounties, independently verifies work deliverables, and requires explicit human authorization before executing payments.

---

## Intended End-to-End Workflow

1. **Task Submission:** A human submits a task along with explicit acceptance criteria.
2. **Autonomous Delegation:** A Manager Agent assesses requirements, selects a qualified Worker Agent from the registry, and assigns a bounded fiat bounty.
3. **Task Execution:** The Worker Agent executes the task and submits structured deliverables (`WorkerResult`).
4. **Independent Verification:** An isolated Verification Engine validates deliverables against criteria without human intervention.
5. **Human Authorization:** A human reviews the task outcome and verification report, explicitly authorizing the disbursement (`PaymentAuthorization`).
6. **Payment Processing:** A payment provider (Mock for offline demo mode or PayPal Sandbox for integration tests) executes the transaction idempotently.
7. **Audit & Ledger:** All state changes, messages, verifications, and financial events are immutably recorded in an append-only audit trail.

---

## Current Implementation Status (Session 3 Completed)

Sessions 1, 2, and 3 are complete and verified:

- [x] **Modular Monolith Foundation:** Clean package structure under `src/agentbounty/`.
- [x] **Validated Configuration:** Pydantic Settings supporting offline `DEMO_MODE`, strict safety limits (`MAX_BOUNTY_USD`), sender country checks, and credential masking.
- [x] **Float-Free Money Handling:** Safe monetary conversion between `Decimal` and integer minor units (cents), strict float rejection, precision enforcement, and currency validation.
- [x] **Persistence Models:** Full SQLAlchemy 2.x ORM models for `Agent`, `Task`, `Bounty`, `AgentMessage`, `WorkerResult`, `Verification`, `PaymentAuthorization`, `PaymentTransaction`, and `AuditEvent`.
- [x] **SQLite & Relational Integrity:** Enforced SQLite foreign keys (`PRAGMA foreign_keys=ON`), unique constraints (1:1 task bounty, payment idempotency), and non-negative money check constraints.
- [x] **Database Migrations:** Configured Alembic environment with initial migration (`001_initial_schema.py`) tested against fresh databases.
- [x] **Append-Only Auditing:** Dedicated `AuditEventRepository` strictly prohibiting in-place edits or deletions.
- [x] **Agent Registry & Specialist Workers:** Deterministic profiles for Creative Writer, Research Assistant (explicitly offline), Data Analyst (exact mathematical computation), and Code Assistant (safe static code drafting, zero arbitrary execution).
- [x] **Manager Agent Delegation:** Capability analysis, deterministic worker selection (match score and lexicographical tie-breaking), and bounty allocation bounded by `MAX_BOUNTY_USD`. Manager authority strictly forbids approving verifications or executing payments.
- [x] **Decoupled Verification Engine:** Independent criteria verification (`contains:`, `not_contains:`, `min_words:`, `max_words:`, `min_chars:`, `max_chars:`, `has_section:`). Ambiguous/unsupported criteria hold task for human review. Workers cannot verify their own results.
- [x] **Task Orchestration & State Machine Enforcement:** End-to-end multi-stage pipeline coordinating task transitions, bounty reservation/award/cancellation, and persistent communication messages.
- [x] **Human Financial Authorization Gate:** Mandatory `HUMAN` role verification (`ActorContext`), exact amount/currency match, budget ceiling validation, rejection and revocation handling. (Note: Application-level role check, not independent identity authentication).
- [x] **Deterministic Offline Mock Payment Provider:** Fully offline DEMO mode, `SIMULATED` execution mode, zero fabricated external IDs (`external_reference is None`), status simulation.
- [x] **Optional PayPal Sandbox Provider:** Fail-closed geographic sender eligibility guard for India (`IN`), OAuth token handling, item-level reconciliation, injected transport for test isolation. (Note: Advisory configuration check, not verified account proof).
- [x] **Payment Execution & Idempotency Boundary:** Database-enforced idempotency key, pre-call state persistence (`SUBMITTED`), provider execution outside DB locks, definitive failure reversion.
- [x] **Payment Status Reconciliation:** Idempotent reconciliation service resolving `PENDING` and `UNKNOWN` states without resubmission.
- [x] **Persistent Transaction Ledger:** Filtered database queries and consolidated task payment histories.
- [x] **Automated Test Suite:** 155 passing pytest unit, schema, and integration tests verifying all Session 1, 2 & 3 requirements.

---

## What Is NOT Implemented Yet

As per the strict scope boundaries:
- Streamlit interactive UI dashboard and human approval panel (Session 4).
- Live real-money transactions (strictly excluded from product scope).

---

## Quickstart & Setup Guide

### 1. Prerequisites
- Linux / macOS / WSL
- Python 3.14 (`Python 3.14.2` recommended)

### 2. Activate Virtual Environment
```bash
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
python -m pip install -r requirements.txt
```

Verify dependency integrity:
```bash
python -m pip check
```

### 4. Configuration
Copy the provided environment template to `.env`:
```bash
cp .env.example .env
```

Default configuration runs in offline `DEMO_MODE` without external API keys:
- `DEMO_MODE=true`
- `PAYMENT_PROVIDER=mock`
- `MAX_BOUNTY_USD=5.00`
- `DATABASE_URL=sqlite:///./data/agentbounty.db`

### 5. Run Database Migrations
Initialize or upgrade the local SQLite database using Alembic:
```bash
alembic upgrade head
```

### 6. Run Test Suite
Execute the test suite with strict warning enforcement:
```bash
python -m pytest -v
```

Run test suite quietly and check bytecode compilation:
```bash
python -m pytest -q
python -m compileall -q src tests
```

---

## Project Structure

```text
Agent-Bounty/
├── src/
│   └── agentbounty/
│       ├── agents/               # Specialist workers, registry, and manager agent
│       ├── config/               # Application settings and environment validation
│       ├── domain/               # Enums, Money value object, Pydantic schemas
│       ├── persistence/          # SQLAlchemy models, SQLite engine, Repositories
│       ├── providers/            # Offline demo generation providers
│       ├── services/             # Orchestration, verification, and communication services
│       └── exceptions.py         # Standardized exception hierarchy
├── migrations/                   # Alembic schema migrations
├── tests/                        # 108 unit, schema, and integration tests
├── docs/                         # Architectural & operational documentation
│   ├── ARCHITECTURE.md           # Modular monolith design and layer contracts
│   ├── PRODUCT_SPEC.md           # Product workflows and safeguards
│   ├── STATE_MACHINES.md         # Lifecycle states and transition gates
│   └── SECURITY.md               # Financial controls, secrets, and idempotency
├── data/                         # Local database storage (.gitkeep only)
├── alembic.ini                   # Alembic configuration
├── pyproject.toml                # Project metadata and test configuration
├── requirements.txt              # Production and test dependencies
├── BUILD_STATUS.md               # Session-by-session audit log
└── README.md
```

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
