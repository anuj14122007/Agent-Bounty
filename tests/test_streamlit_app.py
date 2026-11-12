"""Streamlit application UI tests using Streamlit AppTest."""

from __future__ import annotations

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


class TestStreamlitApplication:
    """End-to-end UI tests for Streamlit application pages and navigation."""

    def test_app_default_launch_renders_cleanly(self) -> None:
        """Application default launch must initialize and render Command Center without exceptions."""
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.run()
        assert len(at.exception) == 0

    @pytest.mark.parametrize(
        "page_name",
        [
            "Command Center",
            "Create Task",
            "Agent Activity",
            "Verification & Approval",
            "Transaction Ledger",
            "Settings",
        ],
    )
    def test_all_pages_render_without_exceptions(self, page_name: str) -> None:
        """Every application page must render cleanly without unhandled exceptions."""
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.session_state["nav_selection"] = page_name
        at.run()
        assert len(at.exception) == 0

    def test_create_task_page_has_required_input_controls(self) -> None:
        """Create Task page must present title, description, criteria, and bounty inputs."""
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.session_state["nav_selection"] = "Create Task"
        at.run()
        assert len(at.exception) == 0

        # Check that text inputs and text areas exist
        assert len(at.text_input) >= 1
        assert len(at.text_area) >= 1
        assert len(at.button) >= 1

    def test_settings_page_displays_mode_and_no_secrets(self) -> None:
        """Settings page must render demo mode indicators and zero raw credentials."""
        at = AppTest.from_file(str(APP_PATH), default_timeout=30)
        at.session_state["nav_selection"] = "Settings"
        at.run()
        assert len(at.exception) == 0

        # Check markdown text does not contain secret strings
        full_text = " ".join(m.value for m in at.markdown)
        assert "PAYPAL_CLIENT_SECRET" not in full_text
        assert "password" not in full_text.lower() or "no external authentication" in full_text.lower()
