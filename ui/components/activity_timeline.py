"""Activity timeline component for immutable audit trail and agent communications."""

from __future__ import annotations

import json
from typing import Any
import streamlit as st

from agentbounty.persistence.models import AuditEvent


def render_audit_timeline(events: list[AuditEvent], max_events: int = 15) -> None:
    """Render a chronological audit event log."""
    if not events:
        st.markdown(
            '<div style="color: #6B7280; font-size: 0.85rem; font-style: italic; padding: 12px 0;">'
            "No audit events recorded yet."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    for evt in events[:max_events]:
        ts_str = (
            evt.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(evt.timestamp, "strftime")
            else str(evt.timestamp)
        )
        actor_label = f"{evt.actor_type}: {evt.actor_id}" if evt.actor_id else evt.actor_type

        # Color code based on event severity or type
        accent_color = "#38BDF8"  # Blue/cyan default
        if "PAYMENT" in evt.event_type:
            accent_color = "#00FFAA"  # Neon green for payments
        elif "FAIL" in evt.event_type or "REJECT" in evt.event_type:
            accent_color = "#EF4444"  # Red for failures/rejections
        elif "VERIF" in evt.event_type:
            accent_color = "#F59E0B"  # Amber for verifications

        st.markdown(
            f"""
            <div style="display: flex; gap: 14px; margin-bottom: 12px; font-size: 0.82rem; border-left: 2px solid {accent_color}; padding-left: 12px;">
                <div style="color: #6B7280; font-family: monospace; white-space: nowrap;">{ts_str}</div>
                <div style="flex-grow: 1;">
                    <span style="font-weight: 600; color: {accent_color}; font-family: monospace;">{evt.event_type}</span>
                    <span style="color: #9CA3AF; margin-left: 8px;">({evt.entity_type}: <code style="color: #D1D5DB;">{evt.entity_id[:12]}...</code>)</span>
                    <div style="color: #D1D5DB; margin-top: 2px;">Actor: <span style="color: #F3F4F6;">{actor_label}</span></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Show payload in an expander if available
        if evt.payload:
            with st.expander(f"Details: {evt.event_type} ({evt.entity_id[:8]})", expanded=False):
                st.json(evt.payload)
