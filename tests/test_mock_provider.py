"""Tests for MockPaymentProvider offline semantics."""

from __future__ import annotations

import pytest

from agentbounty.domain.enums import PaymentExecutionMode, PaymentStatus
from agentbounty.exceptions import ProviderTimeoutError
from agentbounty.payments.protocols import PayoutRequest
from agentbounty.payments.providers.mock import MockPaymentProvider


class TestMockPaymentProvider:
    """Test suite verifying MockPaymentProvider invariants."""

    def test_default_simulated_success(self) -> None:
        provider = MockPaymentProvider()
        assert provider.provider_name == "mock"
        assert provider.execution_mode == PaymentExecutionMode.SIMULATED

        req = PayoutRequest(
            task_id="task_123",
            bounty_id="bounty_123",
            authorization_id="auth_123",
            amount_minor_units=350,
            currency="USD",
            idempotency_key="idemp_123",
        )

        res = provider.submit_payout(req)
        assert res.provider_name == "mock"
        assert res.execution_mode == PaymentExecutionMode.SIMULATED
        assert res.status == PaymentStatus.SUCCEEDED
        assert res.external_reference is None  # Never fabricates external reference
        assert res.error_code is None

    def test_simulated_failure(self) -> None:
        provider = MockPaymentProvider(simulate_failure=True)
        req = PayoutRequest(
            task_id="task_123",
            bounty_id="bounty_123",
            authorization_id="auth_123",
            amount_minor_units=350,
            currency="USD",
            idempotency_key="idemp_123",
        )

        res = provider.submit_payout(req)
        assert res.status == PaymentStatus.FAILED
        assert res.error_code == "MOCK_REJECTED"
        assert res.external_reference is None

    def test_simulated_pending(self) -> None:
        provider = MockPaymentProvider(simulate_pending=True)
        req = PayoutRequest(
            task_id="task_123",
            bounty_id="bounty_123",
            authorization_id="auth_123",
            amount_minor_units=350,
            currency="USD",
            idempotency_key="idemp_123",
        )

        res = provider.submit_payout(req)
        assert res.status == PaymentStatus.PENDING
        assert res.provider_status == "SIMULATED_PENDING"

    def test_simulated_timeout_raises_provider_timeout_error(self) -> None:
        provider = MockPaymentProvider(simulate_timeout=True)
        req = PayoutRequest(
            task_id="task_123",
            bounty_id="bounty_123",
            authorization_id="auth_123",
            amount_minor_units=350,
            currency="USD",
            idempotency_key="idemp_123",
        )

        with pytest.raises(ProviderTimeoutError, match="Simulated timeout"):
            provider.submit_payout(req)

    def test_get_payout_status_reconciliation(self) -> None:
        provider = MockPaymentProvider()
        res = provider.get_payout_status(payout_reference="idemp_123")
        assert res.status == PaymentStatus.SUCCEEDED
        assert res.execution_mode == PaymentExecutionMode.SIMULATED
        assert res.external_reference is None
