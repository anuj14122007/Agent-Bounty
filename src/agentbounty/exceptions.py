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


# --- Payment & Financial Exceptions ---


class PaymentError(AgentBountyError):
    """Base exception for all payment, authorization, and financial operations."""


class InvalidAuthorizationError(PaymentError):
    """Raised when an authorization record is invalid, missing, or in an incorrect state."""


class UnauthorizedActorError(PaymentError):
    """Raised when an actor without financial authority attempts to authorize or disburse payments."""


class VerificationNotPassedError(PaymentError):
    """Raised when a payment is attempted for a task whose verification is not PASSED."""


class BountyAmountMismatchError(PaymentError):
    """Raised when an authorized or executed payment amount does not match the allocated bounty."""


class BudgetExceededError(PaymentError):
    """Raised when a payment amount exceeds configured maximum safety limits."""


class CurrencyMismatchError(PaymentError):
    """Raised when the currency of an authorization or payment does not match the bounty currency."""


class DuplicatePaymentError(PaymentError):
    """Raised when a duplicate payment attempt is detected for an authorization or task."""


class InvalidProviderConfigurationError(PaymentError):
    """Raised when a payment provider configuration violates safety or environment rules."""


class ProviderUnavailableError(PaymentError):
    """Raised when an external payment provider is offline or unreachable."""


class ProviderAuthenticationError(PaymentError):
    """Raised when authentication against a payment provider fails."""


class ProviderRejectionError(PaymentError):
    """Raised when a payment provider explicitly rejects a payout submission."""


class ProviderTimeoutError(PaymentError):
    """Raised when an external payment provider call times out with uncertain outcome."""


class UncertainPaymentResultError(PaymentError):
    """Raised when a provider outcome is ambiguous and cannot be confirmed as succeeded or failed."""


class InvalidProviderResponseError(PaymentError):
    """Raised when a provider returns a malformed, invalid, or unrecognized response."""


class ReconciliationError(PaymentError):
    """Raised when payment status reconciliation fails or cannot determine true state."""


class IneligibleSenderCountryError(PaymentError):
    """Raised when the sender account country is ineligible for sending payouts under provider rules."""
