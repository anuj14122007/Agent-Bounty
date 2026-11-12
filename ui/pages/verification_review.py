"""Verification and Human Financial Authorization Page."""

from __future__ import annotations

from decimal import Decimal
import streamlit as st
from sqlalchemy import select

from agentbounty.domain.enums import (
    AuthorizationDecision,
    BountyStatus,
    PaymentExecutionMode,
    TaskStatus,
    VerificationStatus,
)
from agentbounty.domain.money import from_minor_units
from agentbounty.exceptions import (
    PaymentError,
    UnauthorizedActorError,
    VerificationNotPassedError,
)
from agentbounty.payments.schemas import ActorContext, AuthorizationRequest
from agentbounty.persistence.models import (
    Agent,
    Bounty,
    PaymentAuthorization,
    Task,
    Verification,
    WorkerResult,
)
from agentbounty.persistence.repositories import (
    AgentRepository,
    BountyRepository,
    TaskRepository,
)
from ui.bootstrap import get_app_services, get_db_session
from ui.components.confirmation import (
    render_authorization_confirmation_box,
    render_human_identity_disclaimer,
)
from ui.components.status_badges import render_status_badge
from ui.theme import render_page_header


def render_verification_review_page() -> None:
    """Render the Verification Review and Human Financial Governance Panel."""
    render_page_header(
        title="Verification Review & Human Approval Gate",
        subtitle="Controlled human-in-the-loop governance: AI agents perform bounded work; humans control financial authorization",
    )

    render_human_identity_disclaimer()

    operator_id = st.session_state.get("operator_id", "human_operator_1")

    with get_db_session() as session:
        task_repo = TaskRepository(session)
        agent_repo = AgentRepository(session)
        bounty_repo = BountyRepository(session)
        services = get_app_services(session)

        # 1. Query tasks in AWAITING_AUTHORIZATION or IN_REVIEW (NEEDS_HUMAN_REVIEW)
        stmt = (
            select(Task)
            .where(
                Task.status.in_(
                    [TaskStatus.AWAITING_AUTHORIZATION, TaskStatus.IN_REVIEW]
                )
            )
            .order_by(Task.created_at.desc())
        )
        review_tasks = list(session.scalars(stmt).all())

        if not review_tasks:
            st.markdown(
                """
                <div style="background: #111827; border: 1px dashed #374151; border-radius: 8px; padding: 30px; text-align: center; color: #9CA3AF; margin-top: 20px;">
                    <div style="font-size: 1.1rem; font-weight: 600; color: #F9FAFB; margin-bottom: 6px;">No Tasks Awaiting Review</div>
                    <div style="font-size: 0.85rem;">All tasks are currently settled, completed, or in active delegation.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return

        # Selection of task to review
        task_labels = [
            f"{t.title} [{t.status.value}] (${from_minor_units(session.scalar(select(Bounty.amount).where(Bounty.task_id == t.id)) or 0, 'USD'):.2f}) - ID: {t.id[:8]}"
            for t in review_tasks
        ]

        # Check if pre-selected via navigation
        default_idx = 0
        preselected_id = st.session_state.get("selected_review_task_id")
        if preselected_id:
            for idx, t in enumerate(review_tasks):
                if t.id == preselected_id:
                    default_idx = idx
                    break

        selected_label = st.selectbox(
            "Select Task for Human Financial Governance Decision",
            options=task_labels,
            index=default_idx,
        )
        selected_task = review_tasks[task_labels.index(selected_label)]

        # Load related entities
        bounty = bounty_repo.get_by_task_id(selected_task.id)
        worker_results = list(
            session.scalars(
                select(WorkerResult)
                .where(WorkerResult.task_id == selected_task.id)
                .order_by(WorkerResult.submission_version.desc())
            ).all()
        )
        worker_result = worker_results[0] if worker_results else None

        verification = None
        if worker_result:
            verifs = list(
                session.scalars(
                    select(Verification)
                    .where(Verification.worker_result_id == worker_result.id)
                    .order_by(Verification.verified_at.desc())
                ).all()
            )
            verification = verifs[0] if verifs else None

        worker = (
            agent_repo.get_by_id(selected_task.assigned_agent_id)
            if selected_task.assigned_agent_id
            else None
        )
        bounty_amount_usd = (
            from_minor_units(bounty.amount, bounty.currency) if bounty else Decimal("0.00")
        )

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        # Overview Card
        st.markdown(
            f"""
            <div class="fintech-card">
                <div class="fintech-card-header">
                    <div>
                        <span style="font-size: 1.15rem; font-weight: 700; color: #F9FAFB;">{selected_task.title}</span>
                        <div style="font-size: 0.74rem; color: #9CA3AF; font-family: monospace;">Task ID: {selected_task.id}</div>
                    </div>
                </div>
                <div style="font-size: 0.88rem; color: #E5E7EB; margin-bottom: 14px; line-height: 1.4;">
                    {selected_task.description}
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #1F2937; padding-top: 10px; font-size: 0.82rem; color: #9CA3AF;">
                    <div>Assigned Specialist Worker: <strong style="color: #A78BFA;">{worker.name if worker else 'Unassigned'}</strong></div>
                    <div>Allocated Bounty: <strong style="color: #00FFAA; font-family: monospace; font-size: 0.95rem;">${bounty_amount_usd:.2f} {bounty.currency if bounty else 'USD'}</strong></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Delivered Result
        if worker_result:
            with st.expander("Worker Deliverable Output", expanded=True):
                st.markdown(worker_result.content)
                if worker_result.artifact_metadata:
                    st.caption(f"Metadata: `{worker_result.artifact_metadata}`")
        else:
            st.warning("No worker deliverable uploaded yet.")

        # Verification Evaluation Report
        if verification:
            st.markdown(
                f"""
                <div class="fintech-card">
                    <div class="fintech-card-header">
                        <span>Independent Verification Engine Report</span>
                    </div>
                    <div style="font-size: 0.85rem; color: #D1D5DB; margin-bottom: 12px;">
                        <strong>Explanation:</strong> {verification.explanation}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            vcol1, vcol2 = st.columns(2)
            with vcol1:
                st.markdown("**Passed Criteria:**")
                for p in verification.passed_criteria:
                    st.markdown(f"- ✅ `{p}`")
                if not verification.passed_criteria:
                    st.caption("No criteria passed.")

            with vcol2:
                st.markdown("**Failed Criteria:**")
                for f in verification.failed_criteria:
                    st.markdown(f"- ❌ `{f}`")
                if not verification.failed_criteria:
                    st.caption("No criteria failed.")

            # Check for ambiguous / unsupported criteria
            unsupported_criteria = [
                c
                for c in selected_task.acceptance_criteria
                if not any(
                    c.lower().startswith(p)
                    for p in [
                        "contains:",
                        "not_contains:",
                        "min_words:",
                        "max_words:",
                        "min_chars:",
                        "max_chars:",
                        "has_section:",
                    ]
                )
            ]
            if unsupported_criteria:
                st.markdown(
                    """
                    <div class="fintech-callout-warning">
                        <strong>Subjective / Unsupported Criteria Detected:</strong><br/>
                        The following criteria could not be deterministically evaluated by machine verification and require manual human inspection:
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                for uc in unsupported_criteria:
                    st.markdown(f"- ⚠️ `<code>{uc}</code>`", unsafe_allow_html=True)

        # HUMAN GOVERNANCE ACTIONS
        st.markdown("---")
        st.markdown(
            '<div style="font-size: 1.15rem; font-weight: 700; color: #F9FAFB; margin-bottom: 12px;">Human Governance Decision</div>',
            unsafe_allow_html=True,
        )

        # Check eligibility:
        # Payout authorization is ONLY permitted if verification PASSED and task is AWAITING_AUTHORIZATION
        can_authorize = (
            selected_task.status == TaskStatus.AWAITING_AUTHORIZATION
            and verification is not None
            and verification.status == VerificationStatus.PASSED
            and bounty is not None
            and bounty.status == BountyStatus.AWARDED
        )

        if not can_authorize:
            if selected_task.status == TaskStatus.IN_REVIEW:
                st.markdown(
                    """
                    <div class="fintech-callout-warning">
                        <strong>Verification Not Passed:</strong> This task requires human inspection because machine verification was inconclusive (<code>NEEDS_HUMAN_REVIEW</code>).
                        In accordance with the product safety specification, payment authorization cannot be granted for unverified work. You may reject the task below.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div class="fintech-callout-warning">
                        <strong>Task Not Eligible for Financial Authorization:</strong> Current task status is <code>{selected_task.status.value}</code>.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        col_auth, col_reject = st.columns([1.5, 1.0])

        with col_auth:
            if can_authorize:
                confirmed = render_authorization_confirmation_box(
                    task_id=selected_task.id,
                    task_title=selected_task.title,
                    worker_name=worker.name if worker else "Specialist Worker",
                    amount_usd=bounty_amount_usd,
                    currency=bounty.currency if bounty else "USD",
                    operator_id=operator_id,
                )

                if st.button(
                    f"Authorize ${bounty_amount_usd:.2f} {bounty.currency} Payout",
                    type="primary",
                    disabled=not confirmed,
                    use_container_width=True,
                    key=f"btn_auth_{selected_task.id}",
                ):
                    try:
                        human_actor = ActorContext(actor_type="HUMAN", actor_id=operator_id)
                        auth_read = services.auth_service.authorize_payment(
                            AuthorizationRequest(
                                task_id=selected_task.id,
                                bounty_id=bounty.id,
                                authorized_amount=bounty_amount_usd,
                                currency=bounty.currency,
                                actor=human_actor,
                                decision=AuthorizationDecision.AUTHORIZED,
                                reason=f"Human review completed by {operator_id}; quality verified and accepted.",
                            )
                        )
                        session.commit()

                        st.success(
                            f"Payment Authorization GRANTED! (Auth ID: {auth_read.id[:12]}...)"
                        )
                        st.markdown(
                            """
                            <div class="fintech-callout-success">
                                <strong>Authorization Recorded:</strong> The payout has been legally authorized by a human operator.
                                Now proceed to the <strong>Payment Execution</strong> page to execute the simulated disbursement.
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if st.button("Proceed to Payment Execution", type="primary"):
                            st.session_state["nav_selection"] = "Transaction Ledger"
                            st.session_state["active_ledger_tab"] = "Execute Payouts"
                            st.session_state["selected_auth_id"] = auth_read.id
                            st.rerun()

                    except PaymentError as err:
                        st.error(f"Authorization Error: {err}")
                    except Exception as err:
                        st.error(f"Unexpected authorization failure: {err}")

        with col_reject:
            st.markdown(
                """
                <div class="fintech-card" style="border-left: 3px solid #EF4444;">
                    <div style="font-size: 0.78rem; text-transform: uppercase; color: #EF4444; font-weight: 700; margin-bottom: 8px;">
                        Human Rejection Action
                    </div>
                    <div style="font-size: 0.82rem; color: #9CA3AF; margin-bottom: 8px;">
                        Reject the deliverable and cancel the reserved bounty. This action transitions task to REJECTED.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            rejection_reason = st.text_area(
                "Reason for Rejection",
                placeholder="Explain why the deliverable failed human review...",
                key=f"txt_reject_{selected_task.id}",
                height=80,
            )

            if st.button(
                "Reject Task & Cancel Bounty",
                type="secondary",
                use_container_width=True,
                key=f"btn_reject_{selected_task.id}",
            ):
                if not rejection_reason.strip():
                    st.error("A reason is mandatory for human rejection.")
                else:
                    try:
                        human_actor = ActorContext(actor_type="HUMAN", actor_id=operator_id)
                        services.auth_service.authorize_payment(
                            AuthorizationRequest(
                                task_id=selected_task.id,
                                bounty_id=bounty.id,
                                authorized_amount=bounty_amount_usd,
                                currency=bounty.currency,
                                actor=human_actor,
                                decision=AuthorizationDecision.REJECTED,
                                reason=rejection_reason.strip(),
                            )
                        )
                        session.commit()
                        st.warning("Task REJECTED and Bounty CANCELLED.")
                        st.rerun()
                    except PaymentError as err:
                        st.error(f"Rejection Error: {err}")
                    except Exception as err:
                        st.error(f"Failed to record rejection: {err}")
