"""Validated application configuration using Pydantic Settings."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agentbounty.domain.money import to_minor_units
from agentbounty.exceptions import ConfigurationError


class Settings(BaseSettings):
    """Application configuration and security settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application environment
    app_env: Literal["development", "test", "production"] = "development"

    # DEMO Mode: fully offline, zero external dependencies or API keys required
    demo_mode: bool = True

    # Payment provider selection: 'mock' is required in demo mode; 'paypal' only for sandbox testing
    payment_provider: Literal["mock", "paypal"] = "mock"

    # PayPal payouts integration toggle
    paypal_payouts_enabled: bool = False

    # PayPal environment must strictly be 'sandbox'. Real/live mode is completely prohibited.
    paypal_environment: Literal["sandbox"] = "sandbox"

    # Optional PayPal Sandbox credentials
    paypal_client_id: str | None = None
    paypal_client_secret: str | None = None

    # Maximum allowed bounty per task (USD Decimal). Default: $5.00
    max_bounty_usd: Decimal = Field(default=Decimal("5.00"))

    # Database connection URL
    database_url: str = "sqlite:///./data/agentbounty.db"

    @field_validator("max_bounty_usd", mode="before")
    @classmethod
    def validate_max_bounty_not_float(cls, value: object) -> object:
        """Reject float values to prevent precision loss before Pydantic parsing."""
        if isinstance(value, float):
            raise ConfigurationError(
                "MAX_BOUNTY_USD must be specified as a Decimal string (e.g. '5.00'), not a float."
            )
        if isinstance(value, str):
            try:
                return Decimal(value)
            except Exception as err:
                raise ConfigurationError(f"Invalid MAX_BOUNTY_USD value '{value}': {err}") from err
        return value

    @field_validator("max_bounty_usd")
    @classmethod
    def validate_max_bounty_bounds(cls, value: Decimal) -> Decimal:
        """Enforce positive value, correct decimal precision, and safety ceiling."""
        if value <= Decimal(0):
            raise ConfigurationError(f"MAX_BOUNTY_USD must be greater than zero, got {value}")

        # Check precision and ceiling
        try:
            to_minor_units(value, "USD")
        except Exception as err:
            raise ConfigurationError(f"MAX_BOUNTY_USD has invalid precision: {err}") from err

        # Safety ceiling for the hackathon application
        if value > Decimal("100.00"):
            raise ConfigurationError(
                f"MAX_BOUNTY_USD ({value}) exceeds maximum allowable safety ceiling ($100.00)."
            )
        return value

    @model_validator(mode="after")
    def validate_provider_and_environment_safety(self) -> Settings:
        """Validate safety invariants across interrelated settings."""
        # DEMO_MODE must always use the mock payment provider
        if self.demo_mode and self.payment_provider != "mock":
            raise ConfigurationError(
                f"Invalid configuration: DEMO_MODE=true requires PAYMENT_PROVIDER='mock', "
                f"got '{self.payment_provider}'."
            )

        if self.demo_mode and self.paypal_payouts_enabled:
            raise ConfigurationError(
                "Invalid configuration: DEMO_MODE=true prohibits PAYPAL_PAYOUTS_ENABLED=true."
            )

        # Non-sandbox PayPal environment is prohibited
        if self.paypal_environment != "sandbox":
            raise ConfigurationError(
                "Security violation: Live PayPal payouts are not supported in AgentBounty. "
                "Only 'sandbox' is permitted."
            )

        # If PayPal is selected, PayPal payouts must be explicitly enabled
        if self.payment_provider == "paypal" and not self.paypal_payouts_enabled:
            raise ConfigurationError(
                "PAYMENT_PROVIDER='paypal' requires PAYPAL_PAYOUTS_ENABLED=true."
            )

        return self

    def __repr__(self) -> str:
        """Safe representation hiding credentials."""
        secret_masked = "***" if self.paypal_client_secret else None
        return (
            f"Settings(app_env={self.app_env!r}, demo_mode={self.demo_mode}, "
            f"payment_provider={self.payment_provider!r}, "
            f"paypal_payouts_enabled={self.paypal_payouts_enabled}, "
            f"paypal_environment={self.paypal_environment!r}, "
            f"max_bounty_usd={self.max_bounty_usd}, database_url={self.database_url!r}, "
            f"paypal_client_id={self.paypal_client_id!r}, paypal_client_secret={secret_masked!r})"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
