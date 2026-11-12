# AgentBounty — 3-Minute Hackathon Demonstration Script

This script provides an exact, step-by-step walkthrough to present AgentBounty to hackathon judges and technical evaluators in exactly three minutes.

---

## High-Level Pitch (15 seconds)

> *"Autonomous AI agents are capable of remarkable work, but giving them direct access to financial disbursements creates severe risk of runaway spend and prompt injection exploitation. AgentBounty solves this through a fiat-native marketplace built on a strict principle: **Autonomous agents perform bounded work, independent engines verify deliverables, and only humans control financial authorization.**"*

---

## 3-Minute Demonstration Flow

| Step | Time | Interface Section | Action | Narration / Key Points | Expected Screen State |
|---|---|---|---|---|---|
| **1** | 0:00 – 0:25 | **Command Center** | Start app via `streamlit run app.py` and open landing dashboard. | "Notice the fintech-grade telemetry: zero hardcoded metrics. All stats come directly from SQLite persistence. You can see active agents, state distribution, and the top banner confirming `DEMO MODE — SIMULATED PAYMENTS`." | Real KPI metrics (Total Tasks, Active Tasks, Settled Bounties). Registered fleet of 5 agents shown with active status. |
| **2** | 0:25 – 0:50 | **Create Task** | Click "Create Task" in sidebar. Select template *"Marketing Launch Copy"*. | "Here, a human submits a task with explicit machine-checkable criteria (`contains:AgentBounty`, `min_words:25`, `has_section:Introduction`). We propose a $3.50 USD bounty, bounded by our strict $5.00 safety ceiling." | Pre-populated form with title, description, machine-checkable criteria, and $3.50 USD bounty. |
| **3** | 0:50 – 1:15 | **Create Task** | Click **"Submit Task & Execute Workflow"**. | "Upon submission, the Manager Agent inspects required capabilities, matches them against the fleet, and deterministically selects Creative Writer. The Worker generates structured deliverables offline without hallucinated web access. Then, an isolated Verification Engine deterministically checks the output against every single criterion." | Success banner. Breakdown showing Manager match score (100%), Creative Writer selection, Deliverable preview, and Verification Score (100% PASSED). Task status is `AWAITING_AUTHORIZATION`. |
| **4** | 1:15 – 1:35 | **Agent Activity** | Click "Agent Activity" in sidebar. Open "Communication Feed" and "Deep Task Inspector". | "Every message between Manager and Worker is immutably logged with secrets masked. Notice that verification passing DID NOT trigger a payment. The bounty is only `AWARDED`, awaiting human sign-off." | Chronological agent message logs. Deep inspector showing task criteria, worker output, and verification report. |
| **5** | 1:35 – 2:10 | **Verification & Human Approval** | Click "Verification & Approval" in sidebar. Inspect task. Check the confirmation checkbox, then click **"Authorize $3.50 USD Payout"**. | "This is our core innovation: **The Human Financial Gate**. Even when 100% of machine-checkable criteria pass, agents have ZERO financial authority. Deterministic criteria checks do not establish complete semantic correctness, and only a human operator can authorize monetary disbursement. Non-human calls raise `UnauthorizedActorError`. The human reviews the criteria, checks the explicit acknowledgement box, and clicks Authorize. This writes an immutable `PaymentAuthorization` record." | Detailed review card showing passed criteria (100% of machine-checkable criteria passed). Confirmation checkbox acknowledging exact amount and SIMULATED mode. On click: green banner confirms `Payment Authorization GRANTED`. |
| **6** | 2:10 – 2:40 | **Transaction Ledger** | Click "Proceed to Payment Execution". Review execution details and click **"Execute Simulated Payment ($3.50 USD)"**. | "Authorizing liability does not automatically disburse funds. Execution requires a separate deliberate human action. We enforce deterministic idempotency (`task_id:auth_id`). We click Execute: MockPaymentProvider completes the transaction instantaneously in `SIMULATED` mode with zero fabricated PayPal IDs. Task transitions to `COMPLETED` and Bounty to `PAID`." | Success notification with balloons. Authoritative status transitions to `SUCCEEDED`. Task is marked `COMPLETED`. |
| **7** | 2:40 – 3:00 | **Transaction Ledger** | Switch to the "Financial Transaction Ledger (AG Grid)" tab. Filter by status `SUCCEEDED`. Click on the transaction. | "Finally, our persistent AG Grid financial ledger displays the settled payout with full sorting, pagination, and filtering. Expanding the transaction shows the complete append-only audit trail: from human prompt, through delegation, verification, human approval, to final settlement. Refreshing the browser preserves every record." | AG Grid table showing Transaction ID, Task Title, $3.50 USD, SUCCEEDED, SIMULATED. Expanded view shows consolidated audit trail. |

---

## Safety & Reset Instructions

### Resetting Demo Data Safely
To reset the demonstration environment to a clean initial state without affecting application code:

```bash
# 1. Stop any running Streamlit server (Ctrl+C)
# 2. Re-run Alembic migration to ensure clean state
rm -f data/agentbounty.db
alembic upgrade head

# 3. Synchronize initial fleet agents
python -c '
from ui.bootstrap import get_db_session, sync_registry_agents
with get_db_session() as session:
    sync_registry_agents(session)
print("Database cleanly reset and 5 agents synchronized.")
'
```

### Seeding Sample Records for Evaluation
If judges wish to inspect a pre-populated ledger immediately upon opening:

```bash
python -c '
from decimal import Decimal
from ui.bootstrap import get_app_services, get_db_session
from agentbounty.payments.schemas import ActorContext, AuthorizationRequest, PaymentExecutionRequest
from agentbounty.domain.enums import AuthorizationDecision

with get_db_session() as session:
    services = get_app_services(session)
    wf = services.orchestrator.run_full_workflow(
        title="Compose Product Announcement",
        description="Write an introduction announcement for the AgentBounty marketplace.",
        acceptance_criteria=["contains:AgentBounty", "min_words:20", "has_section:Introduction"],
        created_by="founder_carol",
        proposed_bounty=Decimal("3.50"),
    )
    session.commit()
    actor = ActorContext(actor_type="HUMAN", actor_id="founder_carol")
    auth = services.auth_service.authorize_payment(
        AuthorizationRequest(
            task_id=wf.task.id,
            bounty_id=wf.bounty.id,
            authorized_amount=Decimal("3.50"),
            currency="USD",
            actor=actor,
            decision=AuthorizationDecision.AUTHORIZED,
        )
    )
    services.exec_service.execute_payment(PaymentExecutionRequest(authorization_id=auth.id, actor=actor))
    session.commit()
    print("Seeded 1 verified and settled transaction.")
'
```
