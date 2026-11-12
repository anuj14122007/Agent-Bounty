"""UI theme, styling system, and dark fintech design specifications for AgentBounty."""

from __future__ import annotations

import streamlit as st

# Fintech Color Palette
COLOR_BG_DARK = "#0B0F19"
COLOR_BG_CARD = "#111827"
COLOR_BG_CARD_HOVER = "#162036"
COLOR_BORDER = "#1F2937"
COLOR_BORDER_ACCENT = "#374151"
COLOR_PRIMARY_ACCENT = "#00FFAA"
COLOR_PRIMARY_ACCENT_DIM = "rgba(0, 255, 170, 0.15)"
COLOR_TEXT_PRIMARY = "#F9FAFB"
COLOR_TEXT_MUTED = "#9CA3AF"
COLOR_TEXT_DIM = "#6B7280"

# Status Colors
COLOR_SUCCESS = "#10B981"
COLOR_SUCCESS_BG = "rgba(16, 185, 129, 0.15)"
COLOR_WARNING = "#F59E0B"
COLOR_WARNING_BG = "rgba(245, 158, 11, 0.15)"
COLOR_DANGER = "#EF4444"
COLOR_DANGER_BG = "rgba(239, 68, 68, 0.15)"
COLOR_INFO = "#3B82F6"
COLOR_INFO_BG = "rgba(59, 130, 246, 0.15)"
COLOR_CYAN = "#06B6D4"
COLOR_CYAN_BG = "rgba(6, 182, 212, 0.15)"
COLOR_PURPLE = "#8B5CF6"
COLOR_PURPLE_BG = "rgba(139, 92, 246, 0.15)"

GLOBAL_CSS = """
<style>
/* Base typography and body reset */
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #F9FAFB;
}

code, pre, .mono-font {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Streamlit Header & Footer Cleanup */
header[data-testid="stHeader"] {
    background: rgba(11, 15, 25, 0.85);
    backdrop-filter: blur(8px);
}

footer {
    visibility: hidden;
}

/* Sidebar styling */
section[data-testid="stSidebar"] {
    background-color: #0d121f;
    border-right: 1px solid #1F2937;
}

/* Demo Mode Global Banner */
.demo-mode-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: linear-gradient(90deg, rgba(0, 255, 170, 0.12) 0%, rgba(6, 182, 212, 0.08) 100%);
    border: 1px solid rgba(0, 255, 170, 0.35);
    border-radius: 8px;
    padding: 10px 18px;
    margin-bottom: 24px;
    color: #00FFAA;
    font-size: 0.82rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    box-shadow: 0 0 15px rgba(0, 255, 170, 0.08);
}

.demo-mode-tag {
    background: #00FFAA;
    color: #0B0F19;
    padding: 3px 8px;
    border-radius: 4px;
    font-weight: 700;
    font-size: 0.72rem;
    margin-right: 8px;
}

/* Metric Card */
.metric-card-container {
    background-color: #111827;
    border: 1px solid #1F2937;
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 12px;
    transition: all 0.2s ease;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
}

.metric-card-container:hover {
    border-color: #374151;
    transform: translateY(-1px);
}

.metric-card-label {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #9CA3AF;
    font-weight: 600;
    margin-bottom: 6px;
}

.metric-card-value {
    font-size: 1.75rem;
    font-weight: 700;
    color: #F9FAFB;
    font-family: 'JetBrains Mono', monospace;
    line-height: 1.2;
}

.metric-card-subtitle {
    font-size: 0.75rem;
    color: #6B7280;
    margin-top: 6px;
}

/* Status Badge */
.status-badge {
    display: inline-flex;
    align-items: center;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    font-family: 'JetBrains Mono', monospace;
    white-space: nowrap;
}

/* Section Card */
.fintech-card {
    background: #111827;
    border: 1px solid #1F2937;
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 20px;
}

.fintech-card-header {
    font-size: 1.05rem;
    font-weight: 600;
    color: #F9FAFB;
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid #1F2937;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

/* Accent Callouts */
.fintech-callout-info {
    background: rgba(59, 130, 246, 0.08);
    border-left: 3px solid #3B82F6;
    padding: 12px 16px;
    border-radius: 0 8px 8px 0;
    margin: 12px 0;
    font-size: 0.88rem;
    color: #D1D5DB;
}

.fintech-callout-warning {
    background: rgba(245, 158, 11, 0.08);
    border-left: 3px solid #F59E0B;
    padding: 12px 16px;
    border-radius: 0 8px 8px 0;
    margin: 12px 0;
    font-size: 0.88rem;
    color: #FDE68A;
}

.fintech-callout-success {
    background: rgba(16, 185, 129, 0.08);
    border-left: 3px solid #10B981;
    padding: 12px 16px;
    border-radius: 0 8px 8px 0;
    margin: 12px 0;
    font-size: 0.88rem;
    color: #A7F3D0;
}

/* Page Header */
.page-title {
    font-size: 1.65rem;
    font-weight: 700;
    color: #F9FAFB;
    letter-spacing: -0.02em;
    margin-bottom: 4px;
}

.page-subtitle {
    font-size: 0.88rem;
    color: #9CA3AF;
    margin-bottom: 20px;
}

/* Custom button tweaks */
div.stButton > button {
    border-radius: 6px;
    font-weight: 600;
    font-size: 0.88rem;
    transition: all 0.15s ease-in-out;
}

div.stButton > button:hover {
    border-color: #00FFAA;
    box-shadow: 0 0 10px rgba(0, 255, 170, 0.2);
}

/* Primary CTA Button override */
div.stButton > button[kind="primary"] {
    background-color: #00FFAA !important;
    color: #0B0F19 !important;
    border: none !important;
    font-weight: 700 !important;
}

div.stButton > button[kind="primary"]:hover {
    background-color: #33FFBB !important;
    box-shadow: 0 0 16px rgba(0, 255, 170, 0.45) !important;
}
</style>
"""


def apply_theme() -> None:
    """Inject global CSS rules into the Streamlit app."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def render_demo_banner() -> None:
    """Render the standard AgentBounty DEMO MODE top banner."""
    st.markdown(
        """
        <div class="demo-mode-banner">
            <div>
                <span class="demo-mode-tag">DEMO MODE</span>
                <span>SIMULATED PAYMENTS — OFFLINE EXECUTION</span>
            </div>
            <div style="font-size: 0.74rem; color: #9CA3AF; text-transform: none; letter-spacing: normal;">
                Bounded Agent Marketplace • Human-Controlled Financial Gate
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str) -> None:
    """Render clean standardized page header."""
    st.markdown(
        f"""
        <div style="margin-bottom: 20px;">
            <div class="page-title">{title}</div>
            <div class="page-subtitle">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
