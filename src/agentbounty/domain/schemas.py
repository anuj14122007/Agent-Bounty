"""Pydantic 2.x schemas for AgentBounty domain representations and data transfer."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentbounty.domain.enums import (
    AgentRole,
    AgentStatus,
    AuthorizationDecision,
    BountyStatus,
    PaymentExecutionMode,
    PaymentStatus,
    SenderType,
    TaskStatus,
    VerificationStatus,
    VerifierType,
)
from agentbounty.domain.money import from_minor_units, to_minor_units, validate_currency
from agentbounty.exceptions import InvalidMoneyError


class DomainSchema(BaseModel):
    """Base schema with standard Pydantic 2.x configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        frozen=True,
        str_strip_whitespace=True,
    )


# --- Agent Schemas ---


class AgentCreate(DomainSchema):
    name: str = Field(..., min_length=1, max_length=100)
    role: AgentRole
    description: str = Field(..., min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.ACTIVE


class AgentRead(DomainSchema):
    id: str
    name: str
    role: AgentRole
    description: str
    capabilities: list[str]
    status: AgentStatus
    created_at: datetime
    updated_at: datetime


# --- Task Schemas ---


class TaskCreate(DomainSchema):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    acceptance_criteria: list[str] = Field(..., min_length=1)
    created_by: str = Field(..., min_length=1, max_length=100)
    deadline: datetime | None = None

    @field_validator("acceptance_criteria")
    @classmethod
    def validate_criteria(cls, criteria: list[str]) -> list[str]:
        cleaned = [c.strip() for c in criteria if c and c.strip()]
        if not cleaned:
            raise ValueError("Task must include at least one non-empty acceptance criterion.")
        return cleaned


class TaskUpdate(DomainSchema):
    title: str | None = None
    description: str | None = None
    acceptance_criteria: list[str] | None = None
    assigned_agent_id: str | None = None
    status: TaskStatus | None = None
    deadline: datetime | None = None


class TaskRead(DomainSchema):
    id: str
    title: str
    description: str
    acceptance_criteria: list[str]
    created_by: str
    assigned_agent_id: str | None = None
    status: TaskStatus
    deadline: datetime | None = None
    created_at: datetime
    updated_at: datetime


# --- Bounty Schemas ---


class BountyCreate(DomainSchema):
    task_id: str
    amount: Decimal = Field(..., gt=Decimal(0))
    currency: str = "USD"

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float_amount(cls, value: object) -> object:
        if isinstance(value, float):
            raise InvalidMoneyError(
                "Floating-point values are strictly forbidden for monetary amounts. Use Decimal or string."
            )
        if isinstance(value, str):
            try:
                return Decimal(value)
            except Exception as err:
                raise InvalidMoneyError(f"Invalid monetary string '{value}'") from err
        return value

    @field_validator("currency")
    @classmethod
    def validate_curr(cls, value: str) -> str:
        return validate_currency(value)

    @model_validator(mode="after")
    def validate_money_precision(self) -> BountyCreate:
        try:
            to_minor_units(self.amount, self.currency)
        except Exception as err:
            raise InvalidMoneyError(f"Invalid monetary precision: {err}") from err
        return self

    @property
    def minor_units(self) -> int:
        return to_minor_units(self.amount, self.currency)


class BountyRead(DomainSchema):
    id: str
    task_id: str
    amount: int  # Stored in minor units
    currency: str
    status: BountyStatus
    created_at: datetime
    updated_at: datetime

    @property
    def amount_decimal(self) -> Decimal:
        return from_minor_units(self.amount, self.currency)


# --- AgentMessage Schemas ---


class AgentMessageCreate(DomainSchema):
    task_id: str
    sender_type: SenderType
    sender_id: str | None = None
    recipient_id: str | None = None
    message_type: str = Field(..., min_length=1, max_length=50)
    content: str = Field(..., min_length=1)
    message_metadata: dict[str, Any] = Field(default_factory=dict)


class AgentMessageRead(DomainSchema):
    id: str
    task_id: str
    sender_type: SenderType
    sender_id: str | None = None
    recipient_id: str | None = None
    message_type: str
    content: str
    message_metadata: dict[str, Any]
    timestamp: datetime


# --- WorkerResult Schemas ---


class WorkerResultCreate(DomainSchema):
    task_id: str
    worker_agent_id: str
    content: str = Field(..., min_length=1)
    artifact_metadata: dict[str, Any] = Field(default_factory=dict)
    submission_version: int = Field(default=1, ge=1)


class WorkerResultRead(DomainSchema):
    id: str
    task_id: str
    worker_agent_id: str
    content: str
    artifact_metadata: dict[str, Any]
    submission_version: int
    submitted_at: datetime


# --- Verification Schemas ---


class VerificationCreate(DomainSchema):
    worker_result_id: str
    status: VerificationStatus
    score: int | None = Field(default=None, ge=0, le=100)
    passed_criteria: list[str] = Field(default_factory=list)
    failed_criteria: list[str] = Field(default_factory=list)
    explanation: str = Field(..., min_length=1)
    verifier_type: VerifierType = VerifierType.AUTOMATED


class VerificationRead(DomainSchema):
    id: str
    worker_result_id: str
    status: VerificationStatus
    score: int | None
    passed_criteria: list[str]
    failed_criteria: list[str]
    explanation: str
    verifier_type: VerifierType
    verified_at: datetime


# --- PaymentAuthorization Schemas ---


class PaymentAuthorizationCreate(DomainSchema):
    task_id: str
    bounty_id: str
    authorized_by: str = Field(..., min_length=1, max_length=100)
    decision: AuthorizationDecision
    authorized_amount: Decimal = Field(..., gt=Decimal(0))
    currency: str = "USD"
    reason: str | None = None

    @field_validator("authorized_amount", mode="before")
    @classmethod
    def reject_float_amount(cls, value: object) -> object:
        if isinstance(value, float):
            raise InvalidMoneyError(
                "Floating-point values are strictly forbidden for monetary amounts."
            )
        if isinstance(value, str):
            try:
                return Decimal(value)
            except Exception as err:
                raise InvalidMoneyError(f"Invalid monetary string '{value}'") from err
        return value

    @field_validator("currency")
    @classmethod
    def validate_curr(cls, value: str) -> str:
        return validate_currency(value)

    @model_validator(mode="after")
    def validate_money_precision(self) -> PaymentAuthorizationCreate:
        try:
            to_minor_units(self.authorized_amount, self.currency)
        except Exception as err:
            raise InvalidMoneyError(f"Invalid monetary precision: {err}") from err
        return self

    @property
    def authorized_amount_minor_units(self) -> int:
        return to_minor_units(self.authorized_amount, self.currency)


class PaymentAuthorizationRead(DomainSchema):
    id: str
    task_id: str
    bounty_id: str
    authorized_by: str
    decision: AuthorizationDecision
    authorized_amount: int  # Minor units
    currency: str
    authorized_at: datetime
    reason: str | None = None

    @property
    def authorized_amount_decimal(self) -> Decimal:
        return from_minor_units(self.authorized_amount, self.currency)


# --- PaymentTransaction Schemas ---


class PaymentTransactionCreate(DomainSchema):
    task_id: str
    bounty_id: str
    authorization_id: str | None = None
    provider_name: str = Field(..., min_length=1, max_length=50)
    execution_mode: PaymentExecutionMode
    amount: Decimal = Field(..., gt=Decimal(0))
    currency: str = "USD"
    idempotency_key: str = Field(..., min_length=8, max_length=128)
    external_reference: str | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def reject_float_amount(cls, value: object) -> object:
        if isinstance(value, float):
            raise InvalidMoneyError(
                "Floating-point values are strictly forbidden for monetary amounts."
            )
        if isinstance(value, str):
            try:
                return Decimal(value)
            except Exception as err:
                raise InvalidMoneyError(f"Invalid monetary string '{value}'") from err
        return value

    @field_validator("currency")
    @classmethod
    def validate_curr(cls, value: str) -> str:
        return validate_currency(value)

    @model_validator(mode="after")
    def validate_transaction_safety(self) -> PaymentTransactionCreate:
        try:
            to_minor_units(self.amount, self.currency)
        except Exception as err:
            raise InvalidMoneyError(f"Invalid monetary precision: {err}") from err

        if self.execution_mode == PaymentExecutionMode.SIMULATED and self.external_reference is not None:
            raise ValueError(
                "Simulated payment transactions cannot contain a fabricated external provider reference."
            )
        return self

    @property
    def minor_units(self) -> int:
        return to_minor_units(self.amount, self.currency)


class PaymentTransactionRead(DomainSchema):
    id: str
    task_id: str
    bounty_id: str
    authorization_id: str | None
    provider_name: str
    execution_mode: PaymentExecutionMode
    amount: int  # Minor units
    currency: str
    status: PaymentStatus
    idempotency_key: str
    external_reference: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @property
    def amount_decimal(self) -> Decimal:
        return from_minor_units(self.amount, self.currency)


# --- AuditEvent Schemas ---


class AuditEventCreate(DomainSchema):
    entity_type: str = Field(..., min_length=1, max_length=50)
    entity_id: str = Field(..., min_length=1, max_length=36)
    event_type: str = Field(..., min_length=1, max_length=100)
    actor_type: str = Field(..., min_length=1, max_length=50)
    actor_id: str = Field(..., min_length=1, max_length=100)
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AuditEventRead(DomainSchema):
    id: str
    entity_type: str
    entity_id: str
    event_type: str
    actor_type: str
    actor_id: str
    timestamp: datetime
    correlation_id: str | None
    payload: dict[str, Any]
