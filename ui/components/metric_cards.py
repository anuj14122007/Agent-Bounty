"""Metric card presentation components for fintech KPI display."""

from __future__ import annotations

import streamlit as st


def render_metric_card(
    label: str,
    value: str | int | float,
    subtitle: str | None = None,
    accent_color: str | None = None,
) -> None:
    """Render a single high-contrast dark fintech KPI metric card."""
    border_style = f"border-top: 3px solid {accent_color};" if accent_color else ""
    sub_html = f'<div class="metric-card-subtitle">{subtitle}</div>' if subtitle else ""

    st.markdown(
        f"""
        <div class="metric-card-container" style="{border_style}">
            <div class="metric-card-label">{label}</div>
            <div class="metric-card-value" style="color: {accent_color or '#F9FAFB'};">{value}</div>
            {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_row(metrics: list[dict[str, str | int | float | None]]) -> None:
    """Render a row of responsive metric cards."""
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        with col:
            render_metric_card(
                label=str(m.get("label", "")),
                value=m.get("value", "-"),
                subtitle=m.get("subtitle") if isinstance(m.get("subtitle"), str) else None,
                accent_color=(
                    m.get("accent_color") if isinstance(m.get("accent_color"), str) else None
                ),
            )
