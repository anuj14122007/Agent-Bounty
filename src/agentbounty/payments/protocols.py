"""Payment provider protocols and core transaction data contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, ConfigDict, Field

from agentbounty.domain.enums import PaymentExecutionMode, PaymentStatus
from agentbounty.persistence.base import utc_now


class PayoutRequest(BaseModel):
    """Specification for a payout submission to a payment provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    bounty_id: str
    authorization_id: str
    amount_minor_units: int = Field(..., gt=0)
    currency: str = "USD"
    idempotency_key: str
    recipient_info: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PayoutResult(BaseModel):
    """Structured result returned by a payment provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_name: str
    execution_mode: PaymentExecutionMode
    status: PaymentStatus
    external_reference: str | None = None
    provider_status: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)


@runtime_checkable
class PaymentProvider(Protocol):
    """Protocol defining the required interface for all AgentBounty payment adapters."""

    @property
    def provider_name(self) -> str:
        """Identifier of the payment provider (e.g. 'mock', 'paypal')."""
        ...

    @property
    def execution_mode(self) -> PaymentExecutionMode:
        """Execution modality: SIMULATED (offline mock) or SANDBOX (PayPal sandbox)."""
        ...

    def submit_payout(self, request: PayoutRequest) -> PayoutResult:
        """Submit a payout disbursement request to the provider.

        Args:
            request: Typed specification of the payout to execute.

        Returns:
            Structured PayoutResult containing status and provider metadata.
        """
        ...

    def get_payout_status(
        self,
        payout_reference: str,
        idempotency_key: str | None = None,
    ) -> PayoutResult:
        """Retrieve current reconciliation status of a previously submitted payout.

        Args:
            payout_reference: External reference (for sandbox) or idempotency key.
            idempotency_key: Optional idempotency key for fallback lookup.

        Returns:
            Structured PayoutResult containing reconciled status and provider metadata.
        """
        ...
