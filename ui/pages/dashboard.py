"""Command Center / Main Dashboard page displaying authoritative metrics, workflow states, and agent overview."""

from __future__ import annotations

from typing import Any
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentbounty.agents.profiles import (
    CODE_ASSISTANT_ID,
    CREATIVE_WRITER_ID,
    DATA_ANALYST_ID,
    MANAGER_AGENT_ID,
    RESEARCHER_ID,
)
from agentbounty.domain.enums import (
    AgentRole,
    AgentStatus,
    PaymentExecutionMode,
    PaymentStatus,
    TaskStatus,
)
from agentbounty.domain.money import from_minor_units
from agentbounty.persistence.models import (
    Agent,
    AuditEvent,
    Bounty,
    PaymentTransaction,
    Task,
)
from agentbounty.persistence.repositories import AgentRepository, TaskRepository
from ui.bootstrap import get_db_session
from ui.components.activity_timeline import render_audit_timeline
from ui.components.metric_cards import render_metric_row
from ui.components.status_badges import render_status_badge
from ui.theme import render_page_header


def get_dashboard_metrics(session: Session) -> dict[str, Any]:
    """Query authoritative real metrics directly from persistent database records."""
    # 1. Total tasks
    total_tasks = session.scalar(select(func.count(Task.id))) or 0

    # 2. Active tasks
    active_statuses = [
        TaskStatus.OPEN,
        TaskStatus.ASSIGNED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.SUBMITTED,
        TaskStatus.IN_REVIEW,
        TaskStatus.APPROVED,
        TaskStatus.AWAITING_AUTHORIZATION,
        TaskStatus.PAYMENT_PENDING,
    ]
    active_tasks = (
        session.scalar(select(func.count(Task.id)).where(Task.status.in_(active_statuses))) or 0
    )

    # 3. Completed tasks
    completed_tasks = (
        session.scalar(select(func.count(Task.id)).where(Task.status == TaskStatus.COMPLETED)) or 0
    )

    # 4. Total bounty volume
    total_bounty_cents = session.scalar(select(func.coalesce(func.sum(Bounty.amount), 0))) or 0
    total_bounty_usd = from_minor_units(total_bounty_cents, "USD")

    # 5. Pending human authorizations
    pending_auth = (
        session.scalar(
            select(func.count(Task.id)).where(Task.status == TaskStatus.AWAITING_AUTHORIZATION)
        )
        or 0
    )

    # 6. Successful simulated payments
    successful_payments = (
        session.scalar(
            select(func.count(PaymentTransaction.id)).where(
                PaymentTransaction.status == PaymentStatus.SUCCEEDED,
                PaymentTransaction.execution_mode == PaymentExecutionMode.SIMULATED,
            )
        )
        or 0
    )

    return {
        "total_tasks": total_tasks,
        "active_tasks": active_tasks,
        "completed_tasks": completed_tasks,
        "total_bounty_usd": total_bounty_usd,
        "pending_authorizations": pending_auth,
        "successful_payments": successful_payments,
    }


def get_task_lifecycle_counts(session: Session) -> dict[str, int]:
    """Retrieve count of tasks in each lifecycle state."""
    lifecycle_keys = [
        TaskStatus.OPEN.value,
        TaskStatus.ASSIGNED.value,
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.SUBMITTED.value,
        TaskStatus.IN_REVIEW.value,
        TaskStatus.AWAITING_AUTHORIZATION.value,
        TaskStatus.PAYMENT_PENDING.value,
        TaskStatus.COMPLETED.value,
        TaskStatus.REJECTED.value,
        TaskStatus.FAILED.value,
    ]
    counts = {k: 0 for k in lifecycle_keys}

    stmt = select(Task.status, func.count(Task.id)).group_by(Task.status)
    rows = session.execute(stmt).all()
    for status_enum, count in rows:
        val = status_enum.value if hasattr(status_enum, "value") else str(status_enum)
        counts[val] = count

    return counts


def render_dashboard_page() -> None:
    """Render Command Center dashboard with live persistent database metrics."""
    render_page_header(
        title="Command Center",
        subtitle="Real-time agent marketplace telemetry, human governance queue & financial settlement ledger",
    )

    with get_db_session() as session:
        metrics = get_dashboard_metrics(session)

        # Top section KPI row
        render_metric_row(
            [
                {
                    "label": "Total Tasks",
                    "value": str(metrics["total_tasks"]),
                    "subtitle": "Marketplace volume",
                },
                {
                    "label": "Active Tasks",
                    "value": str(metrics["active_tasks"]),
                    "subtitle": "In flight",
                    "accent_color": "#38BDF8",
                },
                {
                    "label": "Completed Tasks",
                    "value": str(metrics["completed_tasks"]),
                    "subtitle": "Settled & verified",
                    "accent_color": "#10B981",
                },
                {
                    "label": "Total Bounty Value",
                    "value": f"${metrics['total_bounty_usd']:.2f}",
                    "subtitle": "Cumulative USD",
                    "accent_color": "#00FFAA",
                },
                {
                    "label": "Pending Approvals",
                    "value": str(metrics["pending_authorizations"]),
                    "subtitle": "Requires human action",
                    "accent_color": (
                        "#F59E0B" if metrics["pending_authorizations"] > 0 else "#9CA3AF"
                    ),
                },
                {
                    "label": "Simulated Payments",
                    "value": str(metrics["successful_payments"]),
                    "subtitle": "Settled transactions",
                    "accent_color": "#00FFAA",
                },
            ]
        )

        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

        col_left, col_right = st.columns([1.5, 1.0])

        with col_left:
            st.markdown(
                '<div style="font-size: 1rem; font-weight: 600; color: #F9FAFB; margin-bottom: 10px;">Workflow Lifecycle Distribution</div>',
                unsafe_allow_html=True,
            )
            state_counts = get_task_lifecycle_counts(session)

            # Build a Plotly horizontal bar chart with fintech styling
            categories = list(reversed(list(state_counts.keys())))
            values = [state_counts[cat] for cat in categories]

            # Colors for each category
            colors = []
            for cat in categories:
                if cat in ("COMPLETED", "APPROVED"):
                    colors.append("#10B981")
                elif cat in ("AWAITING_AUTHORIZATION",):
                    colors.append("#00FFAA")
                elif cat in ("REJECTED", "FAILED"):
                    colors.append("#EF4444")
                elif cat in ("IN_REVIEW", "ASSIGNED"):
                    colors.append("#F59E0B")
                else:
                    colors.append("#38BDF8")

            fig = go.Figure(
                go.Bar(
                    x=values,
                    y=[cat.replace("_", " ") for cat in categories],
                    orientation="h",
                    marker=dict(color=colors, line=dict(color="#1F2937", width=1)),
                    text=values,
                    textposition="auto",
                )
            )

            fig.update_layout(
                plot_bgcolor="#111827",
                paper_bgcolor="#111827",
                margin=dict(l=10, r=10, t=10, b=10),
                height=280,
                xaxis=dict(
                    showgrid=True,
                    gridcolor="#1F2937",
                    color="#9CA3AF",
                    tickfont=dict(size=10),
                    dtick=1 if max(values, default=0) < 10 else None,
                ),
                yaxis=dict(
                    color="#D1D5DB",
                    tickfont=dict(size=11, family="monospace"),
                ),
                font=dict(family="Inter, sans-serif"),
            )

            st.plotly_chart(fig, use_container_width=True)

            # Tasks Awaiting Review section
            st.markdown(
                '<div style="font-size: 1rem; font-weight: 600; color: #F9FAFB; margin-top: 14px; margin-bottom: 8px;">'
                "Tasks Awaiting Human Action"
                "</div>",
                unsafe_allow_html=True,
            )

            review_tasks = (
                session.scalars(
                    select(Task)
                    .where(
                        Task.status.in_(
                            [TaskStatus.AWAITING_AUTHORIZATION, TaskStatus.IN_REVIEW]
                        )
                    )
                    .order_by(Task.created_at.desc())
                    .limit(5)
                ).all()
            )

            if not review_tasks:
                st.markdown(
                    """
                    <div style="background: #111827; border: 1px dashed #374151; border-radius: 8px; padding: 20px; text-align: center; color: #9CA3AF; font-size: 0.85rem;">
                        No tasks currently require human authorization. All verification pipelines are settled.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                for t in review_tasks:
                    c1, c2, c3 = st.columns([2.5, 1.2, 1.0])
                    with c1:
                        st.markdown(
                            f"<div style='font-size: 0.88rem; font-weight: 600; color: #F3F4F6;'>{t.title}</div>"
                            f"<div style='font-size: 0.75rem; color: #9CA3AF;'>Task ID: <code>{t.id[:8]}...</code></div>",
                            unsafe_allow_html=True,
                        )
                    with c2:
                        render_status_badge(t.status.value)
                    with c3:
                        if st.button("Review", key=f"btn_dash_rev_{t.id}", use_container_width=True):
                            st.session_state["nav_selection"] = "Verification & Approval"
                            st.session_state["selected_review_task_id"] = t.id
                            st.rerun()

        with col_right:
            st.markdown(
                '<div style="font-size: 1rem; font-weight: 600; color: #F9FAFB; margin-bottom: 10px;">Marketplace Agent Fleet</div>',
                unsafe_allow_html=True,
            )

            # Display all 5 registered agents with live task stats
            agent_repo = AgentRepository(session)
            agents = agent_repo.list_all()

            for ag in agents:
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

                role_tag = (
                    '<span style="color: #38BDF8; font-size: 0.72rem; font-weight: 600;">[MANAGER]</span>'
                    if ag.role == AgentRole.MANAGER
                    else '<span style="color: #A78BFA; font-size: 0.72rem; font-weight: 600;">[SPECIALIST]</span>'
                )

                st.markdown(
                    f"""
                    <div style="background: #111827; border: 1px solid #1F2937; border-radius: 8px; padding: 12px 14px; margin-bottom: 8px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <span style="font-weight: 600; color: #F9FAFB; font-size: 0.88rem;">{ag.name}</span>
                                <span style="margin-left: 6px;">{role_tag}</span>
                            </div>
                            <span style="color: #10B981; font-size: 0.72rem; font-family: monospace;">● ACTIVE</span>
                        </div>
                        <div style="font-size: 0.75rem; color: #9CA3AF; margin-top: 4px; display: flex; justify-content: space-between;">
                            <span>Assigned: <strong style="color: #F3F4F6;">{assigned_count}</strong></span>
                            <span>Completed: <strong style="color: #00FFAA;">{completed_count}</strong></span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

        # Recent Activity Timeline section
        st.markdown(
            '<div style="font-size: 1rem; font-weight: 600; color: #F9FAFB; margin-bottom: 10px;">Recent Audit & Governance Events</div>',
            unsafe_allow_html=True,
        )
        recent_events = (
            session.scalars(
                select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(8)
            ).all()
        )
        render_audit_timeline(list(recent_events), max_events=8)
