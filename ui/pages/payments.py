"""Payment execution and AG Grid transaction ledger page."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
import pandas as pd
import streamlit as st
from sqlalchemy import select

from agentbounty.domain.enums import (
    AuthorizationDecision,
    PaymentExecutionMode,
    PaymentStatus,
    TaskStatus,
)
from agentbounty.domain.money import from_minor_units
from agentbounty.exceptions import PaymentError
from agentbounty.payments.schemas import ActorContext, PaymentExecutionRequest
from agentbounty.persistence.models import (
    Bounty,
    PaymentAuthorization,
    PaymentTransaction,
    Task,
)
from agentbounty.persistence.repositories import (
    PaymentAuthorizationRepository,
    PaymentTransactionRepository,
    TaskRepository,
)
from ui.bootstrap import get_app_services, get_db_session
from ui.components.activity_timeline import render_audit_timeline
from ui.components.status_badges import get_badge_html, render_status_badge
from ui.theme import render_page_header

# Try importing AG Grid safely
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

    AG_GRID_AVAILABLE = True
except Exception:
    AG_GRID_AVAILABLE = False


def render_payments_page() -> None:
    """Render the Payment Execution and Transaction Ledger interface."""
    render_page_header(
        title="Settlement Execution & Financial Ledger",
        subtitle="Idempotent payout disbursement and persistent immutable transaction audit ledger",
    )

    tab_exec, tab_ledger = st.tabs(
        ["Execute Authorized Payouts", "Financial Transaction Ledger (AG Grid)"]
    )

    operator_id = st.session_state.get("operator_id", "human_operator_1")

    with get_db_session() as session:
        services = get_app_services(session)
        auth_repo = PaymentAuthorizationRepository(session)
        tx_repo = PaymentTransactionRepository(session)
        task_repo = TaskRepository(session)

        # TAB 1: Payment Execution Page
        with tab_exec:
            st.markdown(
                '<div style="font-size: 1.05rem; font-weight: 600; color: #F9FAFB; margin-bottom: 8px;">Human-Initiated Payment Execution</div>',
                unsafe_allow_html=True,
            )

            st.markdown(
                """
                <div class="fintech-callout-warning" style="border-left-color: #00FFAA;">
                    <strong style="color: #00FFAA;">SIMULATED PAYMENT — NO REAL MONEY IS TRANSFERRED</strong><br/>
                    All disbursements execute through <code>MockPaymentProvider</code> in <code>SIMULATED</code> mode.
                    Verification or authorization does NOT auto-execute payments. Execution requires this deliberate human action.
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Query authorizations that have decision=AUTHORIZED
            stmt = (
                select(PaymentAuthorization)
                .where(PaymentAuthorization.decision == AuthorizationDecision.AUTHORIZED)
                .order_by(PaymentAuthorization.authorized_at.desc())
            )
            all_auths = list(session.scalars(stmt).all())

            # Filter for authorizations that do not yet have a SUCCEEDED transaction
            pending_exec_auths = []
            for a in all_auths:
                existing_tx = session.scalar(
                    select(PaymentTransaction).where(
                        PaymentTransaction.authorization_id == a.id,
                        PaymentTransaction.status == PaymentStatus.SUCCEEDED,
                    )
                )
                if not existing_tx:
                    pending_exec_auths.append(a)

            if not pending_exec_auths:
                st.markdown(
                    """
                    <div style="background: #111827; border: 1px dashed #374151; border-radius: 8px; padding: 24px; text-align: center; color: #9CA3AF; margin-top: 14px;">
                        No authorized disbursements pending execution. Authorize a completed task in "Verification & Approval" to queue it here.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                auth_options = {}
                for a in pending_exec_auths:
                    t = task_repo.get_by_id(a.task_id)
                    amt = from_minor_units(a.authorized_amount, a.currency)
                    label = f"{t.title if t else a.task_id[:8]} — ${amt:.2f} {a.currency} (Auth: {a.id[:8]}...)"
                    auth_options[label] = a

                chosen_label = st.selectbox(
                    "Select Authorized Disbursement to Execute",
                    options=list(auth_options.keys()),
                )
                chosen_auth = auth_options[chosen_label]
                chosen_task = task_repo.get_by_id(chosen_auth.task_id)

                amt_usd = from_minor_units(chosen_auth.authorized_amount, chosen_auth.currency)
                idemp_key = services.exec_service.derive_idempotency_key(
                    chosen_auth.id, chosen_auth.task_id
                )

                st.markdown(
                    f"""
                    <div class="fintech-card" style="border-left: 3px solid #00FFAA;">
                        <div class="fintech-card-header">
                            <span>Settlement Execution Specification</span>
                            <span style="color: #00FFAA; font-family: monospace;">${amt_usd:.2f} {chosen_auth.currency}</span>
                        </div>
                        <table style="width: 100%; font-size: 0.82rem; color: #D1D5DB; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 4px 0; color: #9CA3AF;">Task:</td>
                                <td style="padding: 4px 0; font-weight: 600; text-align: right; color: #F3F4F6;">{chosen_task.title if chosen_task else chosen_auth.task_id}</td>
                            </tr>
                            <tr>
                                <td style="padding: 4px 0; color: #9CA3AF;">Payment Provider:</td>
                                <td style="padding: 4px 0; font-weight: 600; text-align: right; color: #38BDF8;">MockPaymentProvider (DEMO)</td>
                            </tr>
                            <tr>
                                <td style="padding: 4px 0; color: #9CA3AF;">Execution Mode:</td>
                                <td style="padding: 4px 0; font-weight: 600; text-align: right; color: #00FFAA;">SIMULATED (Offline)</td>
                            </tr>
                            <tr>
                                <td style="padding: 4px 0; color: #9CA3AF;">Deterministic Idempotency Key:</td>
                                <td style="padding: 4px 0; font-family: monospace; font-size: 0.75rem; text-align: right; color: #D1D5DB;">{idemp_key}</td>
                            </tr>
                            <tr>
                                <td style="padding: 4px 0; color: #9CA3AF;">Authorizing Human:</td>
                                <td style="padding: 4px 0; font-weight: 600; text-align: right; color: #9CA3AF; font-family: monospace;">{chosen_auth.authorized_by}</td>
                            </tr>
                        </table>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if st.button(
                    f"Execute Simulated Payment (${amt_usd:.2f} {chosen_auth.currency})",
                    type="primary",
                    key=f"btn_exec_{chosen_auth.id}",
                ):
                    try:
                        human_actor = ActorContext(actor_type="HUMAN", actor_id=operator_id)
                        exec_result = services.exec_service.execute_payment(
                            PaymentExecutionRequest(
                                authorization_id=chosen_auth.id,
                                actor=human_actor,
                            )
                        )
                        session.commit()

                        if exec_result.status == PaymentStatus.SUCCEEDED:
                            st.success(
                                f"Simulated Payment Executed Successfully! Status: SUCCEEDED (Transaction ID: {exec_result.transaction.id})"
                            )
                            st.balloons()
                            st.rerun()
                        elif exec_result.status in (PaymentStatus.PENDING, PaymentStatus.UNKNOWN):
                            st.warning(
                                f"Payment submitted with status: {exec_result.status.value}. Use reconciliation below to verify status."
                            )
                        else:
                            st.error(f"Payment execution resulted in status: {exec_result.status.value}")
                    except PaymentError as err:
                        st.error(f"Payment Execution Error: {err}")
                    except Exception as err:
                        st.error(f"Unexpected execution error: {err}")

            # Section for PENDING or UNKNOWN reconciliation
            st.markdown("---")
            st.markdown(
                '<div style="font-size: 0.95rem; font-weight: 600; color: #F9FAFB; margin-bottom: 6px;">Payment Status Reconciliation</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Idempotently reconcile pending or uncertain transactions against the provider without resubmitting payouts."
            )

            uncertain_txs = list(
                session.scalars(
                    select(PaymentTransaction).where(
                        PaymentTransaction.status.in_(
                            [PaymentStatus.PENDING, PaymentStatus.UNKNOWN]
                        )
                    )
                ).all()
            )

            if not uncertain_txs:
                st.caption("No pending or uncertain transactions requiring reconciliation.")
            else:
                for utx in uncertain_txs:
                    uc1, uc2, uc3 = st.columns([2, 1, 1])
                    with uc1:
                        st.markdown(f"Tx: <code>{utx.id[:12]}...</code> ({utx.status.value})", unsafe_allow_html=True)
                    with uc2:
                        render_status_badge(utx.status.value)
                    with uc3:
                        if st.button("Reconcile", key=f"btn_rec_{utx.id}"):
                            try:
                                rec_res = services.recon_service.reconcile_transaction(utx.id)
                                session.commit()
                                st.info(f"Reconciliation completed: Status is {rec_res.status.value}")
                                st.rerun()
                            except Exception as err:
                                st.error(f"Reconciliation failed: {err}")

        # TAB 2: Financial Transaction Ledger (AG Grid)
        with tab_ledger:
            st.markdown(
                '<div style="font-size: 1.05rem; font-weight: 600; color: #F9FAFB; margin-bottom: 8px;">Persistent Settlement Ledger</div>',
                unsafe_allow_html=True,
            )

            # Filter controls
            f_col1, f_col2, f_col3 = st.columns(3)
            with f_col1:
                status_filter = st.selectbox(
                    "Status Filter",
                    options=["ALL", "SUCCEEDED", "FAILED", "PENDING", "UNKNOWN", "SUBMITTED"],
                    index=0,
                )
            with f_col2:
                mode_filter = st.selectbox(
                    "Execution Mode",
                    options=["ALL", "SIMULATED", "SANDBOX"],
                    index=0,
                )
            with f_col3:
                search_query = st.text_input("Search (Tx ID or Task ID)", placeholder="Type ID to filter...")

            # Map filter values
            st_param = (
                PaymentStatus[status_filter] if status_filter != "ALL" else None
            )
            mode_param = (
                PaymentExecutionMode[mode_filter] if mode_filter != "ALL" else None
            )

            # Query transactions using TransactionLedgerService
            tx_records = services.ledger_service.list_transactions(
                status=st_param,
                execution_mode=mode_param,
                limit=100,
            )

            # Client-side filter for search query
            if search_query.strip():
                sq = search_query.strip().lower()
                tx_records = [
                    t for t in tx_records if sq in t.id.lower() or sq in t.task_id.lower()
                ]

            if not tx_records:
                st.markdown(
                    """
                    <div style="background: #111827; border: 1px dashed #374151; border-radius: 8px; padding: 28px; text-align: center; color: #9CA3AF; margin-top: 12px;">
                        No transactions match the specified ledger filter criteria.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                # Prepare table data
                table_rows = []
                for t in tx_records:
                    amt_usd = from_minor_units(t.amount, t.currency)
                    t_task = task_repo.get_by_id(t.task_id)
                    table_rows.append(
                        {
                            "Transaction ID": t.id,
                            "Task Title": t_task.title if t_task else t.task_id[:8],
                            "Task ID": t.task_id,
                            "Amount ($)": float(amt_usd),
                            "Currency": t.currency,
                            "Status": t.status.value,
                            "Mode": t.execution_mode.value,
                            "Provider": t.provider_name,
                            "Authorization ID": t.authorization_id,
                            "Created At": (
                                t.created_at.strftime("%Y-%m-%d %H:%M:%S")
                                if hasattr(t.created_at, "strftime")
                                else str(t.created_at)
                            ),
                        }
                    )
                df = pd.DataFrame(table_rows)

                # Render with AG Grid if available, else DataFrame
                if AG_GRID_AVAILABLE:
                    try:
                        gb = GridOptionsBuilder.from_dataframe(df)
                        gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=15)
                        gb.configure_side_bar()
                        gb.configure_default_column(
                            resizable=True,
                            filterable=True,
                            sortable=True,
                            editable=False,
                        )
                        gb.configure_column(
                            "Status",
                            cellStyle={"fontWeight": "bold"},
                        )
                        gb.configure_column(
                            "Mode",
                            cellStyle={"fontFamily": "monospace"},
                        )
                        gb.configure_selection("single", use_checkbox=True)
                        grid_opts = gb.build()

                        grid_resp = AgGrid(
                            df,
                            gridOptions=grid_opts,
                            theme="balham",
                            update_mode=GridUpdateMode.SELECTION_CHANGED,
                            height=380,
                            allow_unsafe_jscode=True,
                        )
                        selected_rows = grid_resp.get("selected_rows", [])
                    except Exception as err:
                        st.warning(f"AG Grid render fallback: {err}")
                        st.dataframe(df, use_container_width=True)
                        selected_rows = []
                else:
                    st.dataframe(df, use_container_width=True)
                    selected_rows = []

                # Detail view for selected transaction
                st.markdown("---")
                st.markdown(
                    '<div style="font-size: 0.95rem; font-weight: 600; color: #F9FAFB; margin-bottom: 8px;">Transaction Detail & Audit Explorer</div>',
                    unsafe_allow_html=True,
                )

                selected_tx_id = None
                if selected_rows is not None and len(selected_rows) > 0:
                    first_row = selected_rows[0] if isinstance(selected_rows, list) else selected_rows.iloc[0]
                    selected_tx_id = (
                        first_row.get("Transaction ID")
                        if isinstance(first_row, dict)
                        else first_row["Transaction ID"]
                    )

                # Dropdown fallback for transaction selection
                all_tx_ids = [t.id for t in tx_records]
                detail_tx_id = st.selectbox(
                    "Select Transaction for Full Audit Inspection",
                    options=all_tx_ids,
                    index=all_tx_ids.index(selected_tx_id) if selected_tx_id in all_tx_ids else 0,
                )

                if detail_tx_id:
                    detail_tx = services.ledger_service.get_transaction(detail_tx_id)
                    if detail_tx:
                        history = services.ledger_service.get_task_payment_history(
                            detail_tx.task_id
                        )

                        dc1, dc2 = st.columns(2)
                        with dc1:
                            st.markdown(
                                f"""
                                <div style="font-size: 0.82rem; color: #D1D5DB; line-height: 1.6;">
                                    <strong>Idempotency Key:</strong> <code>{detail_tx.idempotency_key}</code><br/>
                                    <strong>Provider:</strong> {detail_tx.provider_name}<br/>
                                    <strong>External Reference:</strong> <code>{detail_tx.external_reference or 'None (SIMULATED offline mock)'}</code><br/>
                                    <strong>Execution Mode:</strong> {detail_tx.execution_mode.value}
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                        with dc2:
                            st.markdown(
                                f"""
                                <div style="font-size: 0.82rem; color: #D1D5DB; line-height: 1.6;">
                                    <strong>Completed At:</strong> {detail_tx.completed_at or 'Pending'}<br/>
                                    <strong>Authorizations on Task:</strong> {len(history.authorizations)}<br/>
                                    <strong>Transactions on Task:</strong> {len(history.transactions)}<br/>
                                    <strong>Audit Trail Entries:</strong> {len(history.audit_events)}
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )

                        with st.expander("Consolidated Task Financial Audit Trail", expanded=False):
                            render_audit_timeline(history.audit_events, max_events=20)
