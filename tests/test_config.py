"""Tests for application settings and configuration validation."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from agentbounty.config.settings import Settings
from agentbounty.exceptions import ConfigurationError


def test_default_demo_settings() -> None:
    """Verify default settings match required DEMO configuration."""
    settings = Settings()
    assert settings.app_env == "development"
    assert settings.demo_mode is True
    assert settings.payment_provider == "mock"
    assert settings.paypal_payouts_enabled is False
    assert settings.paypal_environment == "sandbox"
    assert settings.max_bounty_usd == Decimal("5.00")
    assert settings.database_url == "sqlite:///./data/agentbounty.db"


def test_reject_float_max_bounty() -> None:
    """Float monetary inputs must be strictly rejected in settings."""
    with pytest.raises((ConfigurationError, ValidationError)):
        Settings(max_bounty_usd=5.0)


def test_reject_zero_or_negative_max_bounty() -> None:
    """Zero and negative maximum bounties must be rejected."""
    with pytest.raises((ConfigurationError, ValidationError)):
        Settings(max_bounty_usd=Decimal("0.00"))

    with pytest.raises((ConfigurationError, ValidationError)):
        Settings(max_bounty_usd=Decimal("-5.00"))


def test_reject_invalid_precision_max_bounty() -> None:
    """Sub-cent precision amounts must be rejected without rounding."""
    with pytest.raises((ConfigurationError, ValidationError)):
        Settings(max_bounty_usd=Decimal("5.005"))


def test_reject_excessive_max_bounty() -> None:
    """Values exceeding safety ceiling ($100.00) must be rejected."""
    with pytest.raises((ConfigurationError, ValidationError)):
        Settings(max_bounty_usd=Decimal("150.00"))


def test_reject_paypal_in_demo_mode() -> None:
    """DEMO_MODE=true prohibits non-mock payment providers."""
    with pytest.raises((ConfigurationError, ValidationError)):
        Settings(demo_mode=True, payment_provider="paypal", paypal_payouts_enabled=True)


def test_reject_paypal_payouts_enabled_in_demo_mode() -> None:
    """DEMO_MODE=true prohibits paypal_payouts_enabled=true."""
    with pytest.raises((ConfigurationError, ValidationError)):
        Settings(demo_mode=True, payment_provider="mock", paypal_payouts_enabled=True)


def test_reject_live_paypal_environment() -> None:
    """Live PayPal environment is forbidden across the entire application."""
    with pytest.raises((ConfigurationError, ValidationError)):
        Settings.model_validate({
            "demo_mode": False,
            "payment_provider": "paypal",
            "paypal_payouts_enabled": True,
            "paypal_environment": "live",
        })


def test_reject_paypal_provider_without_payouts_enabled() -> None:
    """Selecting paypal requires paypal_payouts_enabled=true."""
    with pytest.raises((ConfigurationError, ValidationError)):
        Settings(demo_mode=False, payment_provider="paypal", paypal_payouts_enabled=False)


def test_safe_repr_masks_secrets() -> None:
    """String representation of Settings must never print raw client secrets."""
    settings = Settings(paypal_client_secret="super-secret-key-12345")
    repr_str = repr(settings)
    assert "super-secret-key-12345" not in repr_str
    assert "***" in repr_str
