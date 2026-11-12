"""AgentBounty — Full Product Interface, Human Command Center & Financial Ledger.

Main Streamlit Application Entrypoint.
"""

from __future__ import annotations

import streamlit as st

from ui.bootstrap import bootstrap_application
from ui.navigation import render_sidebar, route_page
from ui.theme import apply_theme, render_demo_banner


def main() -> None:
    """Initialize and run the AgentBounty product application."""
    # 1. Page Configuration
    st.set_page_config(
        page_title="AgentBounty — Autonomous Marketplace & Financial Governance",
        page_icon="⬡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 2. Inject Dark Fintech Styling
    apply_theme()

    # 3. Safe Application Bootstrap
    boot_ok, boot_msg = bootstrap_application()
    if not boot_ok:
        st.error(f"Application Bootstrap Error: {boot_msg}")
        st.info("Check database connectivity, file permissions, and environment configuration.")
        st.stop()

    # 4. Global Top Demo Mode Banner
    render_demo_banner()

    # 5. Sidebar Navigation & Page Routing
    selection = render_sidebar()
    route_page(selection)


if __name__ == "__main__":
    main()
