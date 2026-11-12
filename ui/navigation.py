"""Sidebar navigation and page routing for AgentBounty."""

from __future__ import annotations

import streamlit as st

from ui.pages.agent_activity import render_agent_activity_page
from ui.pages.create_task import render_create_task_page
from ui.pages.dashboard import render_dashboard_page
from ui.pages.payments import render_payments_page
from ui.pages.settings import render_settings_page
from ui.pages.verification_review import render_verification_review_page

NAV_PAGES = [
    "Command Center",
    "Create Task",
    "Agent Activity",
    "Verification & Approval",
    "Transaction Ledger",
    "Settings",
]


def render_sidebar() -> str:
    """Render the sidebar branding, navigation controls, and operator attribution."""
    with st.sidebar:
        # Branding
        st.markdown(
            """
            <div style="padding: 10px 0 20px 0; border-bottom: 1px solid #1F2937; margin-bottom: 20px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div style="width: 28px; height: 28px; background: #00FFAA; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: #0B0F19; font-weight: 900; font-size: 16px;">⬡</div>
                    <div style="font-size: 1.25rem; font-weight: 800; letter-spacing: -0.02em; color: #F9FAFB;">AGENT<span style="color: #00FFAA;">BOUNTY</span></div>
                </div>
                <div style="font-size: 0.74rem; color: #9CA3AF; margin-top: 4px; letter-spacing: 0.04em;">
                    Controlled Autonomous Marketplace
                </div>
                <div style="margin-top: 8px;">
                    <span style="background: rgba(0, 255, 170, 0.15); color: #00FFAA; border: 1px solid #00FFAA; font-size: 0.68rem; font-weight: 700; padding: 2px 6px; border-radius: 4px;">DEMO MODE</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Navigation state handling
        current_selection = st.session_state.get("nav_selection", "Command Center")
        if current_selection not in NAV_PAGES:
            current_selection = "Command Center"

        choice = st.radio(
            "Navigation",
            options=NAV_PAGES,
            index=NAV_PAGES.index(current_selection),
            label_visibility="collapsed",
        )
        st.session_state["nav_selection"] = choice

        st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)

        # Operator attribution control
        st.markdown(
            '<div style="font-size: 0.75rem; text-transform: uppercase; color: #6B7280; font-weight: 700; letter-spacing: 0.05em; margin-bottom: 6px;">Operator Identity</div>',
            unsafe_allow_html=True,
        )
        current_op = st.session_state.get("operator_id", "human_operator_1")
        new_op = st.text_input(
            "Operator ID",
            value=current_op,
            label_visibility="collapsed",
            help="Application-level actor identifier for demo audit trail attribution.",
        )
        st.session_state["operator_id"] = new_op.strip() or "human_operator_1"

        st.caption("Role: `HUMAN` (Application-level role declaration for audit logging)")

        # System telemetry footer
        st.markdown(
            """
            <div style="margin-top: 50px; padding-top: 15px; border-top: 1px solid #1F2937; font-size: 0.72rem; color: #6B7280; line-height: 1.5;">
                <div>Engine: <span style="color: #10B981;">SQLite + NullPool</span></div>
                <div>Fleet: <span style="color: #38BDF8;">5 Agents Synced</span></div>
                <div>Settlement: <span style="color: #00FFAA;">Simulated</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    return choice


def route_page(selection: str) -> None:
    """Invoke the corresponding page renderer."""
    if selection == "Command Center":
        render_dashboard_page()
    elif selection == "Create Task":
        render_create_task_page()
    elif selection == "Agent Activity":
        render_agent_activity_page()
    elif selection == "Verification & Approval":
        render_verification_review_page()
    elif selection == "Transaction Ledger":
        render_payments_page()
    elif selection == "Settings":
        render_settings_page()
    else:
        render_dashboard_page()
