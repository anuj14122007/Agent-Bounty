"""Unit tests for PayPal Sandbox adapter with fake transport and country restriction."""

from __future__ import annotations

import json
from decimal import Decimal
import pytest

from agentbounty.config.settings import Settings
from agentbounty.domain.enums import PaymentExecutionMode, PaymentStatus
from agentbounty.exceptions import (
    IneligibleSenderCountryError,
    InvalidProviderConfigurationError,
    ProviderAuthenticationError,
    ProviderRejectionError,
    ProviderTimeoutError,
)
from agentbounty.payments.protocols import PayoutRequest
from agentbounty.payments.providers.paypal_sandbox import (
    HttpResponse,
    HttpTransport,
    PayPalSandboxProvider,
)


class FakeHttpTransport(HttpTransport):
    """In-memory test double intercepting HTTP requests."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.oauth_status_code = 200
        self.oauth_response_body = json.dumps({"access_token": "fake_access_token_123", "expires_in": 3600})
        self.payout_status_code = 201
        self.payout_response_body = json.dumps({
            "batch_header": {
                "payout_batch_id": "PAYOUT_BATCH_999",
                "batch_status": "SUCCESS",
            }
        })
        self.get_status_code = 200
        self.get_response_body = json.dumps({
            "batch_header": {"payout_batch_id": "PAYOUT_BATCH_999", "batch_status": "SUCCESS"},
            "items": [{"transaction_status": "SUCCESS"}],
        })
        self.raise_timeout = False

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None = None,
        timeout: float = 10.0,
    ) -> HttpResponse:
        if self.raise_timeout:
            raise ProviderTimeoutError("Simulated PayPal connection timeout.")

        self.requests.append({
            "method": method,
            "url": url,
            "headers": headers,
            "body": body.decode("utf-8") if body else None,
        })

        if "oauth2/token" in url:
            return HttpResponse(status_code=self.oauth_status_code, headers={}, body=self.oauth_response_body)
        elif method == "POST" and "payments/payouts" in url:
            return HttpResponse(status_code=self.payout_status_code, headers={}, body=self.payout_response_body)
        elif method == "GET" and "payments/payouts" in url:
            return HttpResponse(status_code=self.get_status_code, headers={}, body=self.get_response_body)

        return HttpResponse(status_code=404, headers={}, body="Not Found")


class TestPayPalSandboxProvider:
    """Test suite for optional PayPal Sandbox adapter."""

    def test_rejection_in_demo_mode(self) -> None:
        settings = Settings(demo_mode=True)
        with pytest.raises(InvalidProviderConfigurationError, match="DEMO_MODE=true"):
            PayPalSandboxProvider(settings=settings)

    def test_rejection_when_payouts_disabled(self) -> None:
        settings = Settings(
            demo_mode=False,
            payment_provider="mock",
            paypal_payouts_enabled=False,
        )
        with pytest.raises(InvalidProviderConfigurationError):
            PayPalSandboxProvider(settings=settings)

    def test_rejection_for_indian_merchant_country(self) -> None:
        """Indian PayPal accounts cannot send payouts under official PayPal policy."""
        settings = Settings(
            demo_mode=False,
            payment_provider="paypal",
            paypal_payouts_enabled=True,
            paypal_environment="sandbox",
            paypal_client_id="id123",
            paypal_client_secret="secret123",
            paypal_sender_country="IN",  # India
        )
        with pytest.raises(IneligibleSenderCountryError, match="India \\('IN'\\) are restricted to 'Receive and withdraw'"):
            PayPalSandboxProvider(settings=settings)

    def test_rejection_for_missing_credentials(self) -> None:
        settings = Settings(
            demo_mode=False,
            payment_provider="paypal",
            paypal_payouts_enabled=True,
            paypal_environment="sandbox",
            paypal_client_id="",
            paypal_client_secret="",
            paypal_sender_country="US",
        )
        with pytest.raises(InvalidProviderConfigurationError, match="non-empty PAYPAL_CLIENT_ID"):
            PayPalSandboxProvider(settings=settings)

    def test_successful_sandbox_payout_with_fake_transport(self) -> None:
        settings = Settings(
            demo_mode=False,
            payment_provider="paypal",
            paypal_payouts_enabled=True,
            paypal_environment="sandbox",
            paypal_client_id="client_id_test",
            paypal_client_secret="client_secret_test",
            paypal_sender_country="US",
        )
        transport = FakeHttpTransport()
        provider = PayPalSandboxProvider(settings=settings, transport=transport)

        assert provider.provider_name == "paypal"
        assert provider.execution_mode == PaymentExecutionMode.SANDBOX

        req = PayoutRequest(
            task_id="task_12345",
            bounty_id="bounty_12345",
            authorization_id="auth_12345",
            amount_minor_units=350,
            currency="USD",
            idempotency_key="idemp_abc123",
            recipient_info={"email": "worker@example.com"},
        )

        res = provider.submit_payout(req)
        assert res.status == PaymentStatus.SUCCEEDED
        assert res.external_reference == "PAYOUT_BATCH_999"
        assert res.execution_mode == PaymentExecutionMode.SANDBOX

        # Verify requests recorded
        assert len(transport.requests) == 2  # OAuth token + Payout submission
        oauth_req = transport.requests[0]
        assert "oauth2/token" in oauth_req["url"]
        assert oauth_req["headers"]["Authorization"].startswith("Basic ")

        payout_req = transport.requests[1]
        assert "payments/payouts" in payout_req["url"]
        assert payout_req["headers"]["Authorization"] == "Bearer fake_access_token_123"
        payload = json.loads(payout_req["body"])
        assert payload["items"][0]["amount"]["value"] == "3.50"
        assert payload["items"][0]["receiver"] == "worker@example.com"

    def test_duplicate_batch_id_maps_to_unknown_with_provider_error(self) -> None:
        settings = Settings(
            demo_mode=False,
            payment_provider="paypal",
            paypal_payouts_enabled=True,
            paypal_environment="sandbox",
            paypal_client_id="id",
            paypal_client_secret="secret",
            paypal_sender_country="US",
        )
        transport = FakeHttpTransport()
        transport.payout_status_code = 400
        transport.payout_response_body = json.dumps({
            "name": "DUPLICATE_SENDER_BATCH_ID",
            "message": "The sender_batch_id was previously used within 30 days.",
        })
        provider = PayPalSandboxProvider(settings=settings, transport=transport)

        req = PayoutRequest(
            task_id="task_12345",
            bounty_id="bounty_12345",
            authorization_id="auth_12345",
            amount_minor_units=350,
            currency="USD",
            idempotency_key="idemp_abc123",
        )

        res = provider.submit_payout(req)
        assert res.status == PaymentStatus.UNKNOWN
        assert res.error_code == "DUPLICATE_BATCH_ID"

    def test_provider_rejection_raises_provider_rejection_error(self) -> None:
        settings = Settings(
            demo_mode=False,
            payment_provider="paypal",
            paypal_payouts_enabled=True,
            paypal_environment="sandbox",
            paypal_client_id="id",
            paypal_client_secret="secret",
            paypal_sender_country="US",
        )
        transport = FakeHttpTransport()
        transport.payout_status_code = 403
        transport.payout_response_body = json.dumps({
            "name": "INSUFFICIENT_FUNDS",
            "message": "Account balance insufficient for payout.",
        })
        provider = PayPalSandboxProvider(settings=settings, transport=transport)

        req = PayoutRequest(
            task_id="task_12345",
            bounty_id="bounty_12345",
            authorization_id="auth_12345",
            amount_minor_units=350,
            currency="USD",
            idempotency_key="idemp_abc123",
        )

        with pytest.raises(ProviderRejectionError, match="INSUFFICIENT_FUNDS"):
            provider.submit_payout(req)

    def test_sandbox_reconciliation(self) -> None:
        settings = Settings(
            demo_mode=False,
            payment_provider="paypal",
            paypal_payouts_enabled=True,
            paypal_environment="sandbox",
            paypal_client_id="id",
            paypal_client_secret="secret",
            paypal_sender_country="US",
        )
        transport = FakeHttpTransport()
        transport.get_response_body = json.dumps({
            "batch_header": {"payout_batch_id": "BATCH_111", "batch_status": "SUCCESS"},
            "items": [{"transaction_status": "SUCCESS"}],
        })
        provider = PayPalSandboxProvider(settings=settings, transport=transport)

        res = provider.get_payout_status("BATCH_111")
        assert res.status == PaymentStatus.SUCCEEDED
        assert res.external_reference == "BATCH_111"

    def test_sandbox_reconciliation_item_failure_overrides_batch_success(self) -> None:
        settings = Settings(
            demo_mode=False,
            payment_provider="paypal",
            paypal_payouts_enabled=True,
            paypal_environment="sandbox",
            paypal_client_id="id",
            paypal_client_secret="secret",
            paypal_sender_country="US",
        )
        transport = FakeHttpTransport()
        # PayPal batch completed, but individual item failed (e.g. invalid receiver email)
        transport.get_response_body = json.dumps({
            "batch_header": {"payout_batch_id": "BATCH_222", "batch_status": "SUCCESS"},
            "items": [{"transaction_status": "FAILED"}],
        })
        provider = PayPalSandboxProvider(settings=settings, transport=transport)

        res = provider.get_payout_status("BATCH_222")
        assert res.status == PaymentStatus.FAILED

    def test_sandbox_reconciliation_omitted_items_does_not_assume_success(self) -> None:
        settings = Settings(
            demo_mode=False,
            payment_provider="paypal",
            paypal_payouts_enabled=True,
            paypal_environment="sandbox",
            paypal_client_id="id",
            paypal_client_secret="secret",
            paypal_sender_country="US",
        )
        transport = FakeHttpTransport()
        # Batch header reports SUCCESS, but items array is missing from response
        transport.get_response_body = json.dumps({
            "batch_header": {"payout_batch_id": "BATCH_333", "batch_status": "SUCCESS"},
            "items": [],
        })
        provider = PayPalSandboxProvider(settings=settings, transport=transport)

        res = provider.get_payout_status("BATCH_333")
        assert res.status == PaymentStatus.PENDING
