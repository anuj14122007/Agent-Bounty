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

## Current Implementation Status (Session 1)

Session 1 establishes the architectural foundation:

- [x] **Modular Monolith Foundation:** Clean package structure under `src/agentbounty/`.
- [x] **Validated Configuration:** Pydantic Settings supporting offline `DEMO_MODE`, strict safety limits (`MAX_BOUNTY_USD`), and credential masking.
- [x] **Float-Free Money Handling:** Safe monetary conversion between `Decimal` and integer minor units (cents), strict float rejection, precision enforcement, and currency validation.
- [x] **Persistence Models:** Full SQLAlchemy 2.x ORM models for `Agent`, `Task`, `Bounty`, `AgentMessage`, `WorkerResult`, `Verification`, `PaymentAuthorization`, `PaymentTransaction`, and `AuditEvent`.
- [x] **SQLite & Relational Integrity:** Enforced SQLite foreign keys (`PRAGMA foreign_keys=ON`), unique constraints (1:1 task bounty, payment idempotency), and non-negative money check constraints.
- [x] **Database Migrations:** Configured Alembic environment with initial migration (`001_initial_schema.py`) tested against fresh databases.
- [x] **Append-Only Auditing:** Dedicated `AuditEventRepository` strictly prohibiting in-place edits or deletions.
- [x] **Architecture Contracts & Documentation:** Full specifications in `docs/ARCHITECTURE.md`, `docs/PRODUCT_SPEC.md`, `docs/STATE_MACHINES.md`, and `docs/SECURITY.md`.
- [x] **Automated Test Suite:** 65 passing pytest unit, schema, and integration tests verifying all acceptance criteria.

---

## What Is NOT Implemented Yet

As per the strict scope boundary of Session 1, the following are intentionally deferred to future sessions:
- Streamlit interactive UI dashboard and human approval panel (Session 3/4).
- Manager Agent autonomous decision logic and LLM orchestration (Session 2).
- Worker Agent execution runtimes and tool invocation (Session 2).
- Automated criteria verification algorithms (Session 2).
- External network integration with PayPal Sandbox REST APIs (Session 3).
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
│       ├── config/               # Application settings and environment validation
│       ├── domain/               # Enums, Money value object, Pydantic schemas
│       ├── persistence/          # SQLAlchemy models, SQLite engine, Repositories
│       └── exceptions.py         # Standardized exception hierarchy
├── migrations/                   # Alembic schema migrations
├── tests/                        # 65 unit, schema, and integration tests
├── docs/                         # Architectural & operational documentation
│   ├── ARCHITECTURE.md           # Modular monolith design and future contracts
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
