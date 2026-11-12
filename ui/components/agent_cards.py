"""Agent profile and roster presentation cards."""

from __future__ import annotations

import streamlit as st

from agentbounty.agents.base import BaseAgent
from ui.components.status_badges import get_badge_html


def render_agent_card(
    agent: BaseAgent,
    tasks_assigned: int = 0,
    tasks_completed: int = 0,
) -> None:
    """Render a clean dark fintech profile card for an agent."""
    role_badge = get_badge_html(agent.role.value)
    status_badge = get_badge_html(agent.status.value)

    caps_html = " ".join(
        f'<span style="background: rgba(55, 65, 81, 0.4); border: 1px solid #374151; '
        f'color: #D1D5DB; padding: 2px 8px; border-radius: 4px; font-size: 0.72rem; '
        f'margin-right: 4px; margin-bottom: 4px; display: inline-block; font-family: monospace;">'
        f'{cap}</span>'
        for cap in agent.capabilities
    )

    st.markdown(
        f"""
        <div class="fintech-card">
            <div class="fintech-card-header">
                <div>
                    <span style="font-size: 1.1rem; font-weight: 700; color: #F9FAFB;">{agent.name}</span>
                    <span style="margin-left: 8px;">{role_badge}</span>
                </div>
                {status_badge}
            </div>
            <div style="font-size: 0.82rem; color: #9CA3AF; margin-bottom: 12px; line-height: 1.4;">
                {agent.description}
            </div>
            <div style="margin-bottom: 12px;">
                <div style="font-size: 0.72rem; color: #6B7280; text-transform: uppercase; font-weight: 600; margin-bottom: 6px;">
                    Declared Capabilities
                </div>
                <div>{caps_html}</div>
            </div>
            <div style="display: flex; gap: 20px; border-top: 1px solid #1F2937; padding-top: 10px; font-size: 0.78rem; color: #9CA3AF;">
                <div>Assigned: <strong style="color: #F9FAFB; font-family: monospace;">{tasks_assigned}</strong></div>
                <div>Completed: <strong style="color: #00FFAA; font-family: monospace;">{tasks_completed}</strong></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
