"""Reusable status badge component with color-coded dark fintech styling."""

from __future__ import annotations

import streamlit as st

from agentbounty.domain.enums import (
    AgentRole,
    AgentStatus,
    AuthorizationDecision,
    BountyStatus,
    PaymentExecutionMode,
    PaymentStatus,
    TaskStatus,
    VerificationStatus,
)

# Badge color mappings (text_color, background_color, border_color)
_BADGE_STYLE_MAP: dict[str, tuple[str, str, str]] = {
    # Task Statuses
    TaskStatus.DRAFT.value: ("#9CA3AF", "rgba(156, 163, 175, 0.12)", "#4B5563"),
    TaskStatus.OPEN.value: ("#60A5FA", "rgba(96, 165, 250, 0.12)", "#2563EB"),
    TaskStatus.ASSIGNED.value: ("#38BDF8", "rgba(56, 189, 248, 0.12)", "#0284C7"),
    TaskStatus.IN_PROGRESS.value: ("#C084FC", "rgba(192, 132, 252, 0.12)", "#9333EA"),
    TaskStatus.SUBMITTED.value: ("#A78BFA", "rgba(167, 139, 250, 0.12)", "#7C3AED"),
    TaskStatus.IN_REVIEW.value: ("#FBBF24", "rgba(251, 191, 36, 0.12)", "#D97706"),
    TaskStatus.APPROVED.value: ("#34D399", "rgba(52, 211, 153, 0.12)", "#059669"),
    TaskStatus.AWAITING_AUTHORIZATION.value: (
        "#00FFAA",
        "rgba(0, 255, 170, 0.15)",
        "#00FFAA",
    ),
    TaskStatus.PAYMENT_PENDING.value: ("#38BDF8", "rgba(56, 189, 248, 0.12)", "#0284C7"),
    TaskStatus.COMPLETED.value: ("#10B981", "rgba(16, 185, 129, 0.15)", "#10B981"),
    TaskStatus.REJECTED.value: ("#F87171", "rgba(248, 113, 113, 0.12)", "#DC2626"),
    TaskStatus.FAILED.value: ("#EF4444", "rgba(239, 68, 68, 0.15)", "#B91C1C"),
    TaskStatus.CANCELLED.value: ("#9CA3AF", "rgba(156, 163, 175, 0.12)", "#4B5563"),
    # Bounty Statuses
    BountyStatus.OPEN.value: ("#60A5FA", "rgba(96, 165, 250, 0.12)", "#2563EB"),
    BountyStatus.RESERVED.value: ("#FBBF24", "rgba(251, 191, 36, 0.12)", "#D97706"),
    BountyStatus.AWARDED.value: ("#34D399", "rgba(52, 211, 153, 0.12)", "#059669"),
    BountyStatus.PAID.value: ("#00FFAA", "rgba(0, 255, 170, 0.15)", "#00FFAA"),
    # Verification Statuses
    VerificationStatus.PENDING.value: ("#60A5FA", "rgba(96, 165, 250, 0.12)", "#2563EB"),
    VerificationStatus.PASSED.value: ("#10B981", "rgba(16, 185, 129, 0.15)", "#10B981"),
    VerificationStatus.FAILED.value: ("#EF4444", "rgba(239, 68, 68, 0.15)", "#DC2626"),
    VerificationStatus.NEEDS_HUMAN_REVIEW.value: (
        "#F59E0B",
        "rgba(245, 158, 11, 0.15)",
        "#F59E0B",
    ),
    # Payment Statuses
    PaymentStatus.CREATED.value: ("#9CA3AF", "rgba(156, 163, 175, 0.12)", "#4B5563"),
    PaymentStatus.SUBMITTED.value: ("#38BDF8", "rgba(56, 189, 248, 0.12)", "#0284C7"),
    PaymentStatus.PENDING.value: ("#FBBF24", "rgba(251, 191, 36, 0.12)", "#D97706"),
    PaymentStatus.SUCCEEDED.value: ("#00FFAA", "rgba(0, 255, 170, 0.15)", "#00FFAA"),
    PaymentStatus.UNKNOWN.value: ("#F59E0B", "rgba(245, 158, 11, 0.18)", "#D97706"),
    # Authorization Decisions
    AuthorizationDecision.AUTHORIZED.value: (
        "#10B981",
        "rgba(16, 185, 129, 0.15)",
        "#10B981",
    ),
    AuthorizationDecision.REJECTED.value: (
        "#EF4444",
        "rgba(239, 68, 68, 0.15)",
        "#DC2626",
    ),
    AuthorizationDecision.REVOKED.value: (
        "#F59E0B",
        "rgba(245, 158, 11, 0.15)",
        "#D97706",
    ),
    # Execution Modes
    PaymentExecutionMode.SIMULATED.value: (
        "#00FFAA",
        "rgba(0, 255, 170, 0.12)",
        "rgba(0, 255, 170, 0.5)",
    ),
    PaymentExecutionMode.SANDBOX.value: (
        "#F59E0B",
        "rgba(245, 158, 11, 0.12)",
        "rgba(245, 158, 11, 0.5)",
    ),
    # Agent Roles & Status
    AgentRole.MANAGER.value: ("#38BDF8", "rgba(56, 189, 248, 0.15)", "#0284C7"),
    AgentRole.WORKER.value: ("#A78BFA", "rgba(167, 139, 250, 0.15)", "#7C3AED"),
    AgentStatus.ACTIVE.value: ("#10B981", "rgba(16, 185, 129, 0.12)", "#059669"),
    AgentStatus.BUSY.value: ("#F59E0B", "rgba(245, 158, 11, 0.12)", "#D97706"),
    AgentStatus.INACTIVE.value: ("#6B7280", "rgba(107, 114, 128, 0.12)", "#4B5563"),
}


def get_badge_html(status_val: str, label: str | None = None) -> str:
    """Generate HTML string for a styled status badge."""
    clean_val = str(status_val).upper()
    display_label = label or clean_val.replace("_", " ")
    text_color, bg_color, border_color = _BADGE_STYLE_MAP.get(
        clean_val, ("#D1D5DB", "rgba(209, 213, 219, 0.1)", "#4B5563")
    )
    return (
        f'<span class="status-badge" style="color: {text_color}; background-color: {bg_color}; '
        f'border: 1px solid {border_color};">{display_label}</span>'
    )


def render_status_badge(status_val: str, label: str | None = None) -> None:
    """Render a styled status badge directly to the Streamlit page."""
    st.markdown(get_badge_html(status_val, label=label), unsafe_allow_html=True)
