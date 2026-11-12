"""Deterministic offline Mock Payment Provider for DEMO mode."""

from __future__ import annotations

from agentbounty.domain.enums import PaymentExecutionMode, PaymentStatus
from agentbounty.exceptions import ProviderTimeoutError
from agentbounty.payments.protocols import PaymentProvider, PayoutRequest, PayoutResult
from agentbounty.persistence.base import utc_now


class MockPaymentProvider(PaymentProvider):
    """Offline, deterministic payment provider requiring zero external credentials or network access.

    FINANCIAL SAFETY INVARIANTS:
    - Always marks execution_mode as SIMULATED.
    - Never fabricates external provider references (external_reference is always None).
    - Never executes network requests or transfers real funds.
    - Database unique constraints remain authoritative for idempotency; mock provider does not
      rely on fragile in-memory state as the sole protection.
    """

    def __init__(
        self,
        default_status: PaymentStatus = PaymentStatus.SUCCEEDED,
        simulate_timeout: bool = False,
        simulate_failure: bool = False,
        simulate_pending: bool = False,
    ) -> None:
        self._default_status = default_status
        self.simulate_timeout = simulate_timeout
        self.simulate_failure = simulate_failure
        self.simulate_pending = simulate_pending
        self.submission_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def execution_mode(self) -> PaymentExecutionMode:
        return PaymentExecutionMode.SIMULATED

    def submit_payout(self, request: PayoutRequest) -> PayoutResult:
        """Deterministically simulate payout submission without external calls."""
        self.submission_count += 1
        now = utc_now()

        # 1. Simulate network timeout / ambiguous outcome if requested
        if self.simulate_timeout:
            raise ProviderTimeoutError(
                f"Simulated timeout during mock payout submission for task '{request.task_id}'. "
                "Disbursement outcome is uncertain."
            )

        # 2. Simulate definitive provider failure if requested
        if self.simulate_failure:
            return PayoutResult(
                provider_name=self.provider_name,
                execution_mode=self.execution_mode,
                status=PaymentStatus.FAILED,
                external_reference=None,
                provider_status="SIMULATED_REJECTED",
                error_code="MOCK_REJECTED",
                error_message="Simulated mock disbursement rejection.",
                timestamp=now,
            )

        # 3. Simulate pending asynchronous processing if requested
        if self.simulate_pending:
            return PayoutResult(
                provider_name=self.provider_name,
                execution_mode=self.execution_mode,
                status=PaymentStatus.PENDING,
                external_reference=None,
                provider_status="SIMULATED_PENDING",
                error_code=None,
                error_message=None,
                timestamp=now,
            )

        # 4. Standard DEMO path: Immediate deterministic simulated success
        return PayoutResult(
            provider_name=self.provider_name,
            execution_mode=self.execution_mode,
            status=self._default_status,
            external_reference=None,
            provider_status="SIMULATED_SUCCESS",
            error_code=None,
            error_message=None,
            timestamp=now,
        )

    def get_payout_status(
        self,
        payout_reference: str,
        idempotency_key: str | None = None,
    ) -> PayoutResult:
        """Retrieve current status during mock reconciliation."""
        now = utc_now()

        if self.simulate_timeout:
            raise ProviderTimeoutError(
                f"Simulated timeout during mock status check for reference '{payout_reference}'."
            )

        if self.simulate_failure:
            return PayoutResult(
                provider_name=self.provider_name,
                execution_mode=self.execution_mode,
                status=PaymentStatus.FAILED,
                external_reference=None,
                provider_status="SIMULATED_REJECTED",
                error_code="MOCK_REJECTED",
                error_message="Simulated mock disbursement rejection.",
                timestamp=now,
            )

        if self.simulate_pending:
            return PayoutResult(
                provider_name=self.provider_name,
                execution_mode=self.execution_mode,
                status=PaymentStatus.PENDING,
                external_reference=None,
                provider_status="SIMULATED_PENDING",
                error_code=None,
                error_message=None,
                timestamp=now,
            )

        return PayoutResult(
            provider_name=self.provider_name,
            execution_mode=self.execution_mode,
            status=self._default_status,
            external_reference=None,
            provider_status="SIMULATED_SUCCESS",
            error_code=None,
            error_message=None,
            timestamp=now,
        )
