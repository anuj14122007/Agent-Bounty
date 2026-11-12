"""Settings and System Configuration Page."""

from __future__ import annotations

import streamlit as st
from sqlalchemy import text

from agentbounty.config.settings import get_settings
from ui.bootstrap import get_db_session
from ui.theme import render_page_header


def render_settings_page() -> None:
    """Render the read-only application settings and security parameter display."""
    render_page_header(
        title="Settings & System Configuration",
        subtitle="Operational parameters, monetary safety ceilings, and compliance transparency",
    )

    settings = get_settings()

    st.markdown(
        """
        <div class="fintech-callout-info">
            <strong>Security Boundary Notice:</strong> All sensitive system parameters and financial constraints are read-only in the UI.
            No live payment switches or credential overrides can be enabled through the interface.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 1. Environment & Mode Parameters
    st.markdown(
        '<div style="font-size: 1.05rem; font-weight: 600; color: #F9FAFB; margin-bottom: 10px;">Application Mode & Environment</div>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"""
            <div class="fintech-card">
                <div style="font-size: 0.78rem; text-transform: uppercase; color: #9CA3AF; font-weight: 600;">Execution Environment</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: #F9FAFB; font-family: monospace; margin: 4px 0;">{settings.app_env.upper()}</div>
                <div style="font-size: 0.75rem; color: #6B7280;">Configured via APP_ENV environment variable</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        demo_color = "#00FFAA" if settings.demo_mode else "#F59E0B"
        st.markdown(
            f"""
            <div class="fintech-card">
                <div style="font-size: 0.78rem; text-transform: uppercase; color: #9CA3AF; font-weight: 600;">Demo Mode State</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: {demo_color}; font-family: monospace; margin: 4px 0;">
                    {'ENABLED (Simulated)' if settings.demo_mode else 'DISABLED'}
                </div>
                <div style="font-size: 0.75rem; color: #6B7280;">Strictly uses offline MockPaymentProvider</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 2. Financial Safety Limits
    st.markdown(
        '<div style="font-size: 1.05rem; font-weight: 600; color: #F9FAFB; margin-top: 14px; margin-bottom: 10px;">Financial Limits & Precision</div>',
        unsafe_allow_html=True,
    )

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        st.markdown(
            f"""
            <div class="fintech-card">
                <div style="font-size: 0.75rem; text-transform: uppercase; color: #9CA3AF; font-weight: 600;">Maximum Bounty Ceiling</div>
                <div style="font-size: 1.4rem; font-weight: 700; color: #00FFAA; font-family: monospace; margin: 4px 0;">${settings.max_bounty_usd:.2f} USD</div>
                <div style="font-size: 0.72rem; color: #6B7280;">Hard programmatic ceiling for tasks</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with fc2:
        st.markdown(
            f"""
            <div class="fintech-card">
                <div style="font-size: 0.75rem; text-transform: uppercase; color: #9CA3AF; font-weight: 600;">Active Payment Provider</div>
                <div style="font-size: 1.4rem; font-weight: 700; color: #38BDF8; font-family: monospace; margin: 4px 0;">{settings.payment_provider.upper()}</div>
                <div style="font-size: 0.72rem; color: #6B7280;">Offline deterministic simulation</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with fc3:
        st.markdown(
            """
            <div class="fintech-card">
                <div style="font-size: 0.75rem; text-transform: uppercase; color: #9CA3AF; font-weight: 600;">Money Precision Format</div>
                <div style="font-size: 1.4rem; font-weight: 700; color: #F9FAFB; font-family: monospace; margin: 4px 0;">Decimal / Cents</div>
                <div style="font-size: 0.72rem; color: #6B7280;">Zero floating-point representations</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 3. Persistence & Database Telemetry
    st.markdown(
        '<div style="font-size: 1.05rem; font-weight: 600; color: #F9FAFB; margin-top: 14px; margin-bottom: 10px;">Database Persistence Status</div>',
        unsafe_allow_html=True,
    )

    db_status = "UNKNOWN"
    table_count = 0
    with get_db_session() as session:
        try:
            # Query SQLite master table count
            tables = session.execute(
                text("SELECT count(*) FROM sqlite_master WHERE type='table'")
            ).scalar()
            table_count = tables or 0
            db_status = "HEALTHY & CONNECTED"
        except Exception as err:
            db_status = f"ERROR: {err}"

    dc1, dc2 = st.columns(2)
    with dc1:
        st.markdown(
            f"""
            <div class="fintech-card">
                <div style="font-size: 0.75rem; text-transform: uppercase; color: #9CA3AF; font-weight: 600;">Database Connection</div>
                <div style="font-size: 1.1rem; font-weight: 700; color: #10B981; font-family: monospace; margin: 4px 0;">{db_status}</div>
                <div style="font-size: 0.72rem; color: #6B7280;">URL: <code>{settings.database_url}</code></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with dc2:
        st.markdown(
            f"""
            <div class="fintech-card">
                <div style="font-size: 0.75rem; text-transform: uppercase; color: #9CA3AF; font-weight: 600;">Schema Tables</div>
                <div style="font-size: 1.1rem; font-weight: 700; color: #38BDF8; font-family: monospace; margin: 4px 0;">{table_count} Tables Verified</div>
                <div style="font-size: 0.72rem; color: #6B7280;">Alembic initial schema active</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 4. Optional PayPal Sandbox Integration Status
    st.markdown(
        '<div style="font-size: 1.05rem; font-weight: 600; color: #F9FAFB; margin-top: 14px; margin-bottom: 10px;">PayPal Sandbox Integration Status</div>',
        unsafe_allow_html=True,
    )

    pp_status = "DISABLED" if not settings.paypal_payouts_enabled else "ENABLED (SANDBOX ONLY)"
    st.markdown(
        f"""
        <div class="fintech-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-weight: 600; color: #F9FAFB;">PayPal Payouts REST API</span>
                <span style="font-family: monospace; font-size: 0.8rem; color: {'#9CA3AF' if not settings.paypal_payouts_enabled else '#F59E0B'};">● {pp_status}</span>
            </div>
            <div style="font-size: 0.82rem; color: #9CA3AF; line-height: 1.5;">
                <strong>Configured Environment:</strong> <code>{settings.paypal_environment}</code><br/>
                <strong>Sender Country Setting:</strong> <code>{settings.paypal_sender_country}</code><br/>
                <strong>Credentials:</strong> [Masked • Securely stored in environment variables]
            </div>
            <div style="font-size: 0.75rem; color: #6B7280; margin-top: 8px; border-top: 1px solid #1F2937; padding-top: 8px;">
                <strong>Advisory Guard Disclaimer:</strong> A self-declared local configuration string (<code>PAYPAL_SENDER_COUNTRY</code>)
                is not proof of the merchant account's registered country or PayPal-verified eligibility.
                Per PayPal documentation, Indian merchant accounts have "Receive and withdraw" capabilities, not "Send, receive, and withdraw".
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 5. Identity Governance Disclaimer
    st.markdown(
        '<div style="font-size: 1.05rem; font-weight: 600; color: #F9FAFB; margin-top: 14px; margin-bottom: 10px;">Identity & Governance Disclaimers</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="fintech-callout-info">
            <strong>Role Check vs. Authentication Boundary:</strong><br/>
            <code>ActorContext(actor_type="HUMAN")</code> is an application-level role check, NOT independent identity authentication.
            The <code>actor_id</code> is supplied by the operator in this hackathon demonstration.
            No external authentication, passwords, or PKI are claimed or implemented in this demo.
        </div>
        """,
        unsafe_allow_html=True,
    )
