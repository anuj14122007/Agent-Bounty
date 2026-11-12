"""Human financial governance confirmation component ensuring deliberate human-in-the-loop action."""

from __future__ import annotations

from decimal import Decimal
import streamlit as st


def render_human_identity_disclaimer() -> None:
    """Render mandatory transparency disclaimer regarding human identity in DEMO mode."""
    st.markdown(
        """
        <div class="fintech-callout-info" style="font-size: 0.76rem; border-left-color: #6366F1;">
            <strong>Demo Identity Governance Notice:</strong><br/>
            <code>ActorContext(actor_type="HUMAN")</code> is an application-level role declaration for this demonstration,
            not independent identity authentication. This offline prototype does not authenticate users with passwords,
            MFA, external identity providers (OAuth/SAML), or cryptographic signatures.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_authorization_confirmation_box(
    task_id: str,
    task_title: str,
    worker_name: str,
    amount_usd: Decimal,
    currency: str = "USD",
    operator_id: str = "human_operator_1",
) -> bool:
    """Render an explicit human authorization review box with mandatory acknowledgement checkbox.

    Returns:
        True if the human operator checked the explicit acknowledgement checkbox, False otherwise.
    """
    st.markdown(
        f"""
        <div class="fintech-card" style="border-left: 3px solid #00FFAA;">
            <div style="font-size: 0.78rem; text-transform: uppercase; color: #00FFAA; font-weight: 700; letter-spacing: 0.05em; margin-bottom: 8px;">
                Human Financial Authorization Gate
            </div>
            <div style="font-size: 0.92rem; color: #F9FAFB; margin-bottom: 12px;">
                You are authorizing a financial disbursement for task: <strong>{task_title}</strong>
            </div>
            <table style="width: 100%; font-size: 0.82rem; color: #D1D5DB; margin-bottom: 14px; border-collapse: collapse;">
                <tr>
                    <td style="padding: 4px 0; color: #9CA3AF;">Worker Agent:</td>
                    <td style="padding: 4px 0; font-weight: 600; text-align: right; color: #F3F4F6;">{worker_name}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #9CA3AF;">Verification Status:</td>
                    <td style="padding: 4px 0; font-weight: 600; text-align: right; color: #10B981;">PASSED (100% of machine-checkable criteria passed)</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #9CA3AF;">Disbursement Amount:</td>
                    <td style="padding: 4px 0; font-weight: 700; text-align: right; color: #00FFAA; font-family: monospace; font-size: 1rem;">${amount_usd:.2f} {currency}</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #9CA3AF;">Execution Mode:</td>
                    <td style="padding: 4px 0; font-weight: 600; text-align: right; color: #38BDF8;">SIMULATED (Offline Mock Provider)</td>
                </tr>
                <tr>
                    <td style="padding: 4px 0; color: #9CA3AF;">Authorizing Operator:</td>
                    <td style="padding: 4px 0; font-weight: 600; text-align: right; color: #D1D5DB; font-family: monospace;">{operator_id}</td>
                </tr>
            </table>
            <div style="font-size: 0.78rem; color: #FBBF24; background: rgba(245, 158, 11, 0.1); padding: 8px 12px; border-radius: 6px; margin-bottom: 12px;">
                <strong>Governance Rule:</strong> Autonomous agents (Manager, Worker, System) have ZERO financial authority.
                Only this explicit human decision creates an immutable <code>PaymentAuthorization</code> record.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    chk_key = f"chk_confirm_auth_{task_id}"
    confirmed = st.checkbox(
        f"I explicitly confirm that I have reviewed the deliverable and authorize the payout of exactly ${amount_usd:.2f} {currency}.",
        key=chk_key,
    )

    return confirmed
