"""Agent activity monitoring, communication timeline, and deep task inspection page."""

from __future__ import annotations

import streamlit as st
from sqlalchemy import func, select

from agentbounty.domain.enums import AgentRole, TaskStatus
from agentbounty.persistence.models import (
    Agent,
    AgentMessage,
    AuditEvent,
    Bounty,
    Task,
    Verification,
    WorkerResult,
)
from agentbounty.persistence.repositories import (
    AgentMessageRepository,
    AgentRepository,
    TaskRepository,
)
from ui.bootstrap import get_db_session
from ui.components.agent_cards import render_agent_card
from ui.components.status_badges import render_status_badge
from ui.theme import render_page_header


def render_agent_activity_page() -> None:
    """Render the Agent Activity monitoring interface."""
    render_page_header(
        title="Agent Fleet & Telemetry",
        subtitle="Inspect autonomous agents, capability profiles, message channels, and task execution history",
    )

    tab_agents, tab_comms, tab_inspect = st.tabs(
        ["Agent Fleet Roster", "Communication Channel Feed", "Deep Task Inspector"]
    )

    with get_db_session() as session:
        agent_repo = AgentRepository(session)
        task_repo = TaskRepository(session)
        msg_repo = AgentMessageRepository(session)

        # TAB 1: Agent Fleet Roster
        with tab_agents:
            st.markdown(
                '<div style="font-size: 1.05rem; font-weight: 600; color: #F9FAFB; margin-bottom: 12px;">Registered Marketplace Agents</div>',
                unsafe_allow_html=True,
            )
            agents = agent_repo.list_all()

            # Render in 2 columns
            c1, c2 = st.columns(2)
            for idx, ag in enumerate(agents):
                assigned_count = (
                    session.scalar(
                        select(func.count(Task.id)).where(Task.assigned_agent_id == ag.id)
                    )
                    or 0
                )
                completed_count = (
                    session.scalar(
                        select(func.count(Task.id)).where(
                            Task.assigned_agent_id == ag.id, Task.status == TaskStatus.COMPLETED
                        )
                    )
                    or 0
                )

                col = c1 if idx % 2 == 0 else c2
                with col:
                    render_agent_card(
                        ag,
                        tasks_assigned=assigned_count,
                        tasks_completed=completed_count,
                    )

        # TAB 2: Communication Feed
        with tab_comms:
            st.markdown(
                '<div style="font-size: 1.05rem; font-weight: 600; color: #F9FAFB; margin-bottom: 8px;">Persistent Inter-Agent Communications</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Chronological messages exchanged between Manager Agent and specialist Workers during delegation and execution."
            )

            # Query all tasks for filter dropdown
            tasks = task_repo.list_tasks(limit=100)
            task_options = {"All Tasks": None}
            for t in tasks:
                task_options[f"{t.title} ({t.id[:8]})"] = t.id

            col_filt1, col_filt2 = st.columns([2, 1])
            with col_filt1:
                selected_task_label = st.selectbox(
                    "Filter by Associated Task",
                    options=list(task_options.keys()),
                )
            selected_task_id = task_options[selected_task_label]

            # Query messages
            stmt = select(AgentMessage)
            if selected_task_id:
                stmt = stmt.where(AgentMessage.task_id == selected_task_id)
            stmt = stmt.order_by(AgentMessage.timestamp.desc()).limit(50)
            messages = session.scalars(stmt).all()

            if not messages:
                st.markdown(
                    """
                    <div style="background: #111827; border: 1px dashed #374151; border-radius: 8px; padding: 24px; text-align: center; color: #9CA3AF; font-size: 0.85rem;">
                        No communication messages found. Submit a task in "Create Task" to watch agents communicate.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                for msg in messages:
                    ts_str = (
                        msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                        if hasattr(msg.timestamp, "strftime")
                        else str(msg.timestamp)
                    )
                    sender_label = (
                        f"{msg.sender_type.value}: {msg.sender_id[:8]}"
                        if msg.sender_id
                        else msg.sender_type.value
                    )
                    recipient_label = (
                        f"Recipient: {msg.recipient_id[:8]}" if msg.recipient_id else "Broadcast"
                    )

                    st.markdown(
                        f"""
                        <div style="background: #111827; border: 1px solid #1F2937; border-left: 3px solid #8B5CF6; border-radius: 6px; padding: 12px; margin-bottom: 10px;">
                            <div style="display: flex; justify-content: space-between; font-size: 0.76rem; color: #9CA3AF; margin-bottom: 4px;">
                                <span style="font-family: monospace; color: #C084FC; font-weight: 600;">{msg.message_type}</span>
                                <span style="font-family: monospace;">{ts_str}</span>
                            </div>
                            <div style="font-size: 0.84rem; color: #F3F4F6; margin-bottom: 6px; line-height: 1.4;">
                                {msg.content}
                            </div>
                            <div style="font-size: 0.72rem; color: #6B7280; display: flex; justify-content: space-between;">
                                <span>Sender: <code>{sender_label}</code></span>
                                <span>{recipient_label} • Task: <code>{msg.task_id[:8]}...</code></span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if msg.message_metadata:
                        with st.expander(f"Metadata ({msg.message_type})", expanded=False):
                            st.json(msg.message_metadata)

        # TAB 3: Deep Task Inspector
        with tab_inspect:
            st.markdown(
                '<div style="font-size: 1.05rem; font-weight: 600; color: #F9FAFB; margin-bottom: 8px;">Detailed Task Lifecycle Inspection</div>',
                unsafe_allow_html=True,
            )

            all_tasks = task_repo.list_tasks(limit=100)
            if not all_tasks:
                st.markdown(
                    """
                    <div style="background: #111827; border: 1px dashed #374151; border-radius: 8px; padding: 24px; text-align: center; color: #9CA3AF; font-size: 0.85rem;">
                        No tasks in marketplace database yet.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                task_map = {f"{t.title} [{t.status.value}] ({t.id[:8]})": t for t in all_tasks}
                chosen_label = st.selectbox("Select Task to Inspect", options=list(task_map.keys()))
                inspected_task = task_map[chosen_label]

                # Fetch associated entities
                bounty = session.scalar(select(Bounty).where(Bounty.task_id == inspected_task.id))
                worker_results = list(
                    session.scalars(
                        select(WorkerResult)
                        .where(WorkerResult.task_id == inspected_task.id)
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

                worker_agent = (
                    agent_repo.get_by_id(inspected_task.assigned_agent_id)
                    if inspected_task.assigned_agent_id
                    else None
                )

                st.markdown(
                    f"""
                    <div class="fintech-card">
                        <div class="fintech-card-header">
                            <div>
                                <span style="font-size: 1.15rem; font-weight: 700;">{inspected_task.title}</span>
                                <div style="font-size: 0.74rem; color: #9CA3AF; font-family: monospace;">ID: {inspected_task.id}</div>
                            </div>
                        </div>
                        <div style="font-size: 0.88rem; color: #E5E7EB; margin-bottom: 12px;">{inspected_task.description}</div>
                        <div style="display: flex; gap: 20px; font-size: 0.82rem; color: #9CA3AF; border-top: 1px solid #1F2937; padding-top: 10px;">
                            <div>Created by: <strong style="color: #F3F4F6;">{inspected_task.created_by}</strong></div>
                            <div>Assigned Worker: <strong style="color: #A78BFA;">{worker_agent.name if worker_agent else 'None'}</strong></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Acceptance Criteria
                st.markdown("**Configured Acceptance Criteria:**")
                for crit in inspected_task.acceptance_criteria:
                    st.markdown(f"- `<code>{crit}</code>`", unsafe_allow_html=True)

                # Worker Deliverable Result
                if worker_result:
                    with st.expander("Worker Deliverable Output", expanded=True):
                        st.markdown(worker_result.content)
                        if worker_result.artifact_metadata:
                            st.caption(f"Metadata: `{worker_result.artifact_metadata}`")

                # Verification Evaluation
                if verification:
                    with st.expander(f"Independent Verification Report (Score: {verification.score}%)", expanded=True):
                        st.markdown(f"**Status:** `{verification.status.value}`")
                        st.markdown(f"**Explanation:** {verification.explanation}")
                        v_col1, v_col2 = st.columns(2)
                        with v_col1:
                            st.markdown("**Passed Criteria:**")
                            for p in verification.passed_criteria:
                                st.markdown(f"- ✅ `{p}`")
                        with v_col2:
                            st.markdown("**Failed Criteria:**")
                            for f in verification.failed_criteria:
                                st.markdown(f"- ❌ `{f}`")

                # Audit History for Task
                with st.expander("Associated Immutable Audit Trail", expanded=False):
                    events = session.scalars(
                        select(AuditEvent)
                        .where(AuditEvent.entity_id == inspected_task.id)
                        .order_by(AuditEvent.timestamp.asc())
                    ).all()
                    for ev in events:
                        st.markdown(
                            f"- `{ev.timestamp}` **{ev.event_type}** by `{ev.actor_type}:{ev.actor_id}`"
                        )
