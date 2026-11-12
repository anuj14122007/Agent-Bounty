"""Task creation and autonomous orchestration page."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
import streamlit as st

from agentbounty.config.settings import get_settings
from agentbounty.domain.enums import TaskStatus, VerificationStatus
from agentbounty.domain.money import from_minor_units
from agentbounty.exceptions import (
    BountyLimitExceededError,
    InvalidMoneyError,
    NoEligibleWorkerError,
)
from agentbounty.persistence.repositories import AgentRepository
from ui.bootstrap import get_app_services, get_db_session
from ui.components.status_badges import render_status_badge
from ui.theme import render_page_header

# Predefined quick templates for hackathon demos
PRESET_TEMPLATES: dict[str, dict[str, Any]] = {
    "Custom / Blank": {
        "title": "",
        "description": "",
        "criteria": "contains:AgentBounty\nmin_words:20\nhas_section:Introduction",
        "bounty": "3.50",
    },
    "Marketing Launch Copy (Creative Writer)": {
        "title": "Compose Product Launch Overview",
        "description": "Write a launch announcement and product introduction explaining the AgentBounty autonomous agent marketplace.",
        "criteria": "contains:AgentBounty\nmin_words:25\nhas_section:Introduction\nnot_contains:placeholder",
        "bounty": "3.50",
    },
    "Algorithm Optimization Draft (Code Assistant)": {
        "title": "Draft Python Rate Limiter Function",
        "description": "Develop a static Python implementation draft of an in-memory token bucket rate limiter.",
        "criteria": "contains:def \ncontains:class \nmin_words:15\nnot_contains:exec(",
        "bounty": "4.00",
    },
    "Dataset Summary Brief (Data Analyst)": {
        "title": "Calculate Descriptive Statistics from Metrics",
        "description": "Compute statistical calculations and descriptive summary metrics from numerical dataset.",
        "criteria": "contains:Statistics\nmin_words:15",
        "bounty": "2.50",
    },
    "AI Safety Evidence Brief (Research Assistant)": {
        "title": "Synthesize AI Alignment Literature",
        "description": "Investigate key literature on autonomous agent delegation safeguards and evidence synthesis.",
        "criteria": "contains:Synthesis\nmin_words:20\nnot_contains:hallucination",
        "bounty": "3.00",
    },
}


def render_create_task_page() -> None:
    """Render the Task Submission and Orchestration interface."""
    render_page_header(
        title="Create & Delegate Task",
        subtitle="Submit a task with explicit acceptance criteria; Manager Agent matches capabilities and allocates a bounded bounty",
    )

    settings = get_settings()
    max_bounty = settings.max_bounty_usd

    st.markdown(
        f"""
        <div class="fintech-callout-info">
            <strong>System Financial Ceiling:</strong> Maximum allowed bounty per task is 
            <strong style="color: #00FFAA; font-family: monospace;">${max_bounty:.2f} USD</strong>. 
            All financial inputs are evaluated as exact Decimals without floating-point arithmetic.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Preset Template Selector
    preset_choice = st.selectbox(
        "Choose a Task Template (Optional)",
        options=list(PRESET_TEMPLATES.keys()),
        index=1,  # Default to Marketing Launch Copy
        help="Pre-fills task parameters demonstrating deterministic specialist routing.",
    )

    preset = PRESET_TEMPLATES[preset_choice]

    with st.form("create_task_form"):
        title_input = st.text_input(
            "Task Title",
            value=preset["title"],
            placeholder="e.g., Compose Product Launch Overview",
            max_chars=200,
        )

        desc_input = st.text_area(
            "Task Description & Objectives",
            value=preset["description"],
            placeholder="Describe the requested work in detail for the Manager Agent to analyze...",
            height=110,
        )

        col_crit, col_bounty = st.columns([1.8, 1.0])

        with col_crit:
            st.markdown(
                '<div style="font-size: 0.82rem; font-weight: 600; color: #D1D5DB; margin-bottom: 4px;">'
                "Acceptance Criteria (One per line)"
                "</div>",
                unsafe_allow_html=True,
            )
            criteria_input = st.text_area(
                "Acceptance Criteria",
                value=preset["criteria"],
                height=130,
                label_visibility="collapsed",
                help=(
                    "Supported machine-checkable prefixes:\n"
                    "- contains:<text>\n"
                    "- not_contains:<text>\n"
                    "- min_words:<count>\n"
                    "- max_words:<count>\n"
                    "- has_section:<heading>\n"
                    "Unsupported criteria will flag task for human review."
                ),
            )
            st.caption(
                "Machine-checkable examples: `contains:AgentBounty`, `min_words:25`, `has_section:Introduction`, `not_contains:placeholder`"
            )

        with col_bounty:
            bounty_input = st.text_input(
                "Proposed Bounty (USD)",
                value=preset["bounty"],
                help=f"Must be a positive monetary value <= ${max_bounty:.2f} USD.",
            )
            operator_id = st.session_state.get("operator_id", "human_operator_1")
            st.text_input(
                "Submitting Operator",
                value=operator_id,
                disabled=True,
                help="Actor identifier for demo audit trail attribution.",
            )

        submitted = st.form_submit_button(
            "Submit Task & Execute Workflow",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        # 1. Validation
        title_clean = title_input.strip()
        desc_clean = desc_input.strip()
        criteria_list = [c.strip() for c in criteria_input.splitlines() if c.strip()]

        if not title_clean:
            st.error("Task title cannot be empty.")
            return

        if not desc_clean:
            st.error("Task description cannot be empty.")
            return

        if not criteria_list:
            st.error("At least one acceptance criterion is required.")
            return

        try:
            bounty_decimal = Decimal(bounty_input.strip())
            if bounty_decimal <= 0:
                st.error("Bounty must be strictly greater than $0.00.")
                return
            if bounty_decimal > max_bounty:
                st.error(
                    f"Bounty ${bounty_decimal:.2f} exceeds configured maximum limit of ${max_bounty:.2f} USD."
                )
                return
        except (InvalidOperation, ValueError):
            st.error("Invalid bounty format. Please enter a valid decimal number (e.g. 3.50).")
            return

        # 2. Execute full backend workflow
        with st.spinner("Manager Agent analyzing requirements and delegating to specialist worker..."):
            with get_db_session() as session:
                services = get_app_services(session)
                try:
                    res = services.orchestrator.run_full_workflow(
                        title=title_clean,
                        description=desc_clean,
                        acceptance_criteria=criteria_list,
                        created_by=operator_id,
                        proposed_bounty=bounty_decimal,
                    )
                    session.commit()

                    st.session_state["latest_workflow_result"] = {
                        "task_id": res.task.id,
                        "bounty_id": res.bounty.id,
                        "worker_id": res.worker_result.worker_agent_id,
                        "task_status": res.task.status.value,
                        "bounty_status": res.bounty.status.value,
                        "verification_status": res.verification.status.value,
                        "verification_score": res.verification.score,
                    }
                    st.success("Workflow executed and persisted successfully!")

                except BountyLimitExceededError as err:
                    st.error(f"Bounty Allocation Rejected: {err}")
                    return
                except NoEligibleWorkerError as err:
                    st.error(f"Worker Delegation Failed: {err}")
                    return
                except Exception as err:
                    st.error(f"Workflow execution failed: {err}")
                    return

    # Display results if a recent execution exists
    if "latest_workflow_result" in st.session_state:
        last = st.session_state["latest_workflow_result"]
        with get_db_session() as session:
            services = get_app_services(session)
            db_task = services.orchestrator.task_repo.get_by_id(last["task_id"])
            db_bounty = services.orchestrator.bounty_repo.get_by_task_id(last["task_id"])
            worker_results = services.orchestrator.worker_result_repo.list_by_task(last["task_id"])
            db_result = worker_results[-1] if worker_results else None
            db_verif = None
            if db_result:
                verifs = services.orchestrator.verification_repo.list_by_worker_result(db_result.id)
                db_verif = verifs[-1] if verifs else None
            agent_repo = AgentRepository(session)
            worker = agent_repo.get_by_id(last["worker_id"]) if last.get("worker_id") else None

            if db_task and db_verif:
                st.markdown("---")
                st.markdown(
                    '<div style="font-size: 1.15rem; font-weight: 700; color: #F9FAFB; margin-bottom: 12px;">'
                    "Autonomous Workflow Execution Output"
                    "</div>",
                    unsafe_allow_html=True,
                )

                # Summary columns
                r1, r2, r3, r4 = st.columns(4)
                with r1:
                    st.markdown("<div style='font-size: 0.75rem; color: #9CA3AF;'>Task Status</div>", unsafe_allow_html=True)
                    render_status_badge(db_task.status.value)
                with r2:
                    st.markdown("<div style='font-size: 0.75rem; color: #9CA3AF;'>Selected Worker</div>", unsafe_allow_html=True)
                    st.markdown(f"<strong style='color: #A78BFA;'>{worker.name if worker else 'Specialist'}</strong>", unsafe_allow_html=True)
                with r3:
                    st.markdown("<div style='font-size: 0.75rem; color: #9CA3AF;'>Allocated Bounty</div>", unsafe_allow_html=True)
                    if db_bounty:
                        st.markdown(
                            f"<strong style='color: #00FFAA; font-family: monospace;'>${from_minor_units(db_bounty.amount, db_bounty.currency):.2f} {db_bounty.currency}</strong>",
                            unsafe_allow_html=True,
                        )
                with r4:
                    st.markdown("<div style='font-size: 0.75rem; color: #9CA3AF;'>Verification Result</div>", unsafe_allow_html=True)
                    render_status_badge(db_verif.status.value)

                # Deliverable preview
                if db_result:
                    with st.expander("Worker Deliverable Output", expanded=True):
                        st.markdown(db_result.content)

                # Verification evaluation breakdown
                with st.expander(f"Independent Verification Details (Score: {db_verif.score}%)", expanded=True):
                    st.markdown(f"**Explanation:** {db_verif.explanation}")
                    vc1, vc2 = st.columns(2)
                    with vc1:
                        st.markdown("**Passed Criteria:**")
                        for pc in db_verif.passed_criteria:
                            st.markdown(f"- ✅ `{pc}`")
                        if not db_verif.passed_criteria:
                            st.caption("None passed.")
                    with vc2:
                        st.markdown("**Failed Criteria:**")
                        for fc in db_verif.failed_criteria:
                            st.markdown(f"- ❌ `{fc}`")
                        if not db_verif.failed_criteria:
                            st.caption("None failed.")

                # Action button if awaiting authorization
                if db_task.status == TaskStatus.AWAITING_AUTHORIZATION:
                    st.markdown(
                        """
                        <div class="fintech-callout-success">
                            <strong>Independent Verification Passed!</strong> This task is eligible for human financial review and bounty authorization.
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if st.button("Proceed to Human Authorization Panel", type="primary", use_container_width=True):
                        st.session_state["nav_selection"] = "Verification & Approval"
                        st.session_state["selected_review_task_id"] = db_task.id
                        st.rerun()
