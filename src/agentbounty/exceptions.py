"""Domain and application exceptions for AgentBounty."""


class AgentBountyError(Exception):
    """Base exception for all AgentBounty domain and operational errors."""


class ConfigurationError(AgentBountyError):
    """Raised when application configuration or environment settings are invalid."""


class InvalidMoneyError(AgentBountyError):
    """Raised when monetary amounts, precision, or currency codes violate safety rules."""


class EntityNotFoundError(AgentBountyError):
    """Raised when an entity with the specified identifier is not found in persistence."""


class DuplicateEntityError(AgentBountyError):
    """Raised when a unique constraint or idempotency key is violated."""


class InvalidStateTransitionError(AgentBountyError):
    """Raised when an illegal lifecycle transition is attempted on an entity."""


class AppendOnlyViolationError(AgentBountyError):
    """Raised when an operation attempts to modify or delete append-only historical records."""


class NoEligibleWorkerError(AgentBountyError):
    """Raised when no active worker agent satisfies the required task capabilities."""


class BountyLimitExceededError(AgentBountyError):
    """Raised when a proposed bounty violates the maximum allowed bounty limit."""


class WorkerExecutionError(AgentBountyError):
    """Raised when an error occurs during worker task execution."""


class VerificationEngineError(AgentBountyError):
    """Raised when an error occurs during acceptance criteria verification."""
