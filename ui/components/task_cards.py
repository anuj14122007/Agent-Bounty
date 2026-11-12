"""Task card components for displaying marketplace tasks and verification summaries."""

from __future__ import annotations

import streamlit as st

from agentbounty.domain.money import from_minor_units
from agentbounty.persistence.models import Bounty, Task
from ui.components.status_badges import get_badge_html


def render_task_card(
    task: Task,
    bounty: Bounty | None = None,
    worker_name: str | None = None,
    show_criteria: bool = True,
) -> None:
    """Render a structured dark fintech card for a task."""
    status_html = get_badge_html(task.status.value)
    bounty_text = (
        f"${from_minor_units(bounty.amount, bounty.currency):.2f} {bounty.currency}"
        if bounty
        else "No Bounty"
    )
    worker_text = worker_name or (
        task.assigned_agent_id[:8] + "..." if task.assigned_agent_id else "Unassigned"
    )

    criteria_html = ""
    if show_criteria and task.acceptance_criteria:
        crit_items = "".join(
            f'<li style="color: #9CA3AF; font-size: 0.8rem; margin-bottom: 2px;"><code>{c}</code></li>'
            for c in task.acceptance_criteria[:4]
        )
        if len(task.acceptance_criteria) > 4:
            crit_items += (
                f'<li style="color: #6B7280; font-size: 0.75rem;">+{len(task.acceptance_criteria)-4} more...</li>'
            )
        criteria_html = f"""
        <div style="margin-top: 10px; border-top: 1px solid #1F2937; padding-top: 8px;">
            <div style="font-size: 0.72rem; color: #6B7280; text-transform: uppercase; font-weight: 600; margin-bottom: 4px;">Acceptance Criteria</div>
            <ul style="padding-left: 18px; margin: 0;">{crit_items}</ul>
        </div>
        """

    st.markdown(
        f"""
        <div class="fintech-card">
            <div class="fintech-card-header">
                <span style="font-size: 1.05rem; font-weight: 600;">{task.title}</span>
                {status_html}
            </div>
            <div style="font-size: 0.85rem; color: #D1D5DB; margin-bottom: 12px; line-height: 1.4;">
                {task.description}
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; color: #9CA3AF; padding-top: 6px;">
                <div>Worker: <strong style="color: #F3F4F6;">{worker_text}</strong></div>
                <div>Bounty: <strong style="color: #00FFAA; font-family: monospace;">{bounty_text}</strong></div>
            </div>
            {criteria_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
