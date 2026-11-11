"""Domain enumerations for AgentBounty workflows, roles, and lifecycles."""

from enum import StrEnum


class TaskStatus(StrEnum):
    """Lifecycle states for a delegable task."""

    DRAFT = "DRAFT"
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AWAITING_AUTHORIZATION = "AWAITING_AUTHORIZATION"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BountyStatus(StrEnum):
    """Lifecycle states for a task bounty."""

    OPEN = "OPEN"
    RESERVED = "RESERVED"
    AWARDED = "AWARDED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class VerificationStatus(StrEnum):
    """Evaluation outcomes from the independent verification engine."""

    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class PaymentStatus(StrEnum):
    """States of a payment transaction."""

    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class AuthorizationDecision(StrEnum):
    """Human or designated actor financial authorization decision."""

    AUTHORIZED = "AUTHORIZED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class AgentRole(StrEnum):
    """Functional role of an agent in the marketplace."""

    MANAGER = "MANAGER"
    WORKER = "WORKER"


class AgentStatus(StrEnum):
    """Operational availability status of an agent."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BUSY = "BUSY"


class PaymentExecutionMode(StrEnum):
    """Execution modality of payment transactions. Live real-money mode is strictly excluded."""

    SIMULATED = "SIMULATED"
    SANDBOX = "SANDBOX"


class VerifierType(StrEnum):
    """Classification of the verification engine running criteria checks."""

    AUTOMATED = "AUTOMATED"
    DETERMINISTIC = "DETERMINISTIC"
    LLM = "LLM"
    HUMAN = "HUMAN"


class SenderType(StrEnum):
    """Originator classification for agent messages."""

    USER = "USER"
    MANAGER = "MANAGER"
    WORKER = "WORKER"
    SYSTEM = "SYSTEM"
