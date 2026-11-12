"""Schemas and domain representations for payment authorization and execution."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from agentbounty.domain.enums import AuthorizationDecision, PaymentStatus
from agentbounty.domain.money import Money
from agentbounty.domain.schemas import (
    AuditEventRead,
    BountyRead,
    PaymentAuthorizationRead,
    PaymentTransactionRead,
    TaskRead,
)


class ActorContext(BaseModel):
    """Execution context and attribution for actors performing financial actions.

    LIMITATION NOTE: In local/demo mode, actor_id represents an attribution identifier,
    not cryptographic proof of identity.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    actor_type: Literal["HUMAN", "MANAGER", "WORKER", "SYSTEM"]
    actor_id: str = Field(..., min_length=1)

    def is_human(self) -> bool:
        """Return True strictly if the actor is explicitly classified as HUMAN."""
        return self.actor_type == "HUMAN"


class AuthorizationRequest(BaseModel):
    """Specification for a human payment authorization decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    bounty_id: str
    authorized_amount: Decimal | Money | int
    currency: str = "USD"
    decision: AuthorizationDecision = AuthorizationDecision.AUTHORIZED
    actor: ActorContext
    reason: str | None = None
    correlation_id: str | None = None


class RevocationRequest(BaseModel):
    """Specification for revoking a previously granted authorization."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    authorization_id: str
    actor: ActorContext
    reason: str = Field(..., min_length=1)
    correlation_id: str | None = None


class PaymentExecutionRequest(BaseModel):
    """Specification for executing payment against an authorized bounty."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    authorization_id: str
    actor: ActorContext
    recipient_info: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class PaymentExecutionResult(BaseModel):
    """Outcome of a payment execution attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transaction: PaymentTransactionRead
    task: TaskRead
    bounty: BountyRead
    status: PaymentStatus
    is_duplicate: bool = False
    correlation_id: str


class PaymentHistoryRead(BaseModel):
    """Consolidated payment, authorization, and audit history for a task."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    authorizations: list[PaymentAuthorizationRead] = Field(default_factory=list)
    transactions: list[PaymentTransactionRead] = Field(default_factory=list)
    audit_events: list[AuditEventRead] = Field(default_factory=list)
