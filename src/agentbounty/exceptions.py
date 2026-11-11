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
