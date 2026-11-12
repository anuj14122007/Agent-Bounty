"""Optional PayPal Sandbox payment provider adapter with country and security restrictions."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, NamedTuple, Protocol
from pydantic import BaseModel, ConfigDict

from agentbounty.config.settings import Settings, get_settings
from agentbounty.domain.enums import PaymentExecutionMode, PaymentStatus
from agentbounty.exceptions import (
    IneligibleSenderCountryError,
    InvalidProviderConfigurationError,
    InvalidProviderResponseError,
    ProviderAuthenticationError,
    ProviderRejectionError,
    ProviderTimeoutError,
)
from agentbounty.payments.protocols import PaymentProvider, PayoutRequest, PayoutResult
from agentbounty.persistence.base import utc_now


class HttpResponse(NamedTuple):
    """Simple HTTP response container."""

    status_code: int
    headers: dict[str, str]
    body: str

    def json(self) -> dict[str, Any]:
        try:
            return json.loads(self.body)
        except Exception as err:
            raise InvalidProviderResponseError(f"Malformed JSON response from provider: {err}") from err


class HttpTransport(Protocol):
    """Protocol for pluggable HTTP clients, enabling testing without network calls."""

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None = None,
        timeout: float = 10.0,
    ) -> HttpResponse:
        ...


class UrllibHttpTransport:
    """Default HTTP transport using standard library urllib."""

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None = None,
        timeout: float = 10.0,
    ) -> HttpResponse:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_body = resp.read().decode("utf-8")
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                return HttpResponse(status_code=resp.status, headers=resp_headers, body=resp_body)
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8")
            err_headers = {k.lower(): v for k, v in err.headers.items()}
            return HttpResponse(status_code=err.code, headers=err_headers, body=err_body)
        except (urllib.error.URLError, TimeoutError) as err:
            raise ProviderTimeoutError(f"HTTP request to PayPal Sandbox timed out or failed: {err}") from err


class PayPalSandboxProvider(PaymentProvider):
    """Optional PayPal Sandbox adapter.

    CRITICAL BOUNDARIES:
    - Never enabled by default; prohibited in DEMO mode.
    - Uses Sandbox endpoints only: https://api-m.sandbox.paypal.com
    - Fails closed for ineligible merchant countries (e.g. India / 'IN').
    - Injected transport ensures zero network access during unit tests.
    """

    SANDBOX_BASE_URL = "https://api-m.sandbox.paypal.com"

    def __init__(
        self,
        settings: Settings | None = None,
        transport: HttpTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.transport = transport or UrllibHttpTransport()
        self._cached_token: str | None = None
        self._token_expires_at: datetime | None = None

        # Validate configuration invariants
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        """Enforce strict startup guards and country eligibility."""
        if self.settings.demo_mode:
            raise InvalidProviderConfigurationError(
                "PayPal provider cannot be initialized in DEMO_MODE=true. Use MockPaymentProvider."
            )

        if self.settings.payment_provider != "paypal" or not self.settings.paypal_payouts_enabled:
            raise InvalidProviderConfigurationError(
                "PayPal provider requires PAYMENT_PROVIDER='paypal' and PAYPAL_PAYOUTS_ENABLED=true."
            )

        if self.settings.paypal_environment != "sandbox":
            raise InvalidProviderConfigurationError(
                "Security violation: Live PayPal environment is strictly forbidden."
            )

        # Country restriction: India ('IN') is restricted to 'Receive and withdraw'
        sender_country = (self.settings.paypal_sender_country or "US").strip().upper()
        if sender_country == "IN":
            raise IneligibleSenderCountryError(
                "Merchants registered in India ('IN') are restricted to 'Receive and withdraw' "
                "under PayPal policy and cannot send payouts through the PayPal Payouts API."
            )

        # Ensure credentials are provided
        if not self.settings.paypal_client_id or not self.settings.paypal_client_id.strip():
            raise InvalidProviderConfigurationError(
                "PayPal Sandbox requires a non-empty PAYPAL_CLIENT_ID."
            )
        if not self.settings.paypal_client_secret or not self.settings.paypal_client_secret.strip():
            raise InvalidProviderConfigurationError(
                "PayPal Sandbox requires a non-empty PAYPAL_CLIENT_SECRET."
            )

    @property
    def provider_name(self) -> str:
        return "paypal"

    @property
    def execution_mode(self) -> PaymentExecutionMode:
        return PaymentExecutionMode.SANDBOX

    def _get_access_token(self) -> str:
        """Obtain OAuth 2.0 Bearer access token using client credentials."""
        now = utc_now()
        if self._cached_token and self._token_expires_at and now < self._token_expires_at:
            return self._cached_token

        client_id = self.settings.paypal_client_id or ""
        client_secret = self.settings.paypal_client_secret or ""
        creds = f"{client_id}:{client_secret}".encode("utf-8")
        basic_auth = base64.b64encode(creds).decode("utf-8")

        headers = {
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        body = b"grant_type=client_credentials"

        url = f"{self.SANDBOX_BASE_URL}/v1/oauth2/token"
        resp = self.transport.request(
            method="POST",
            url=url,
            headers=headers,
            body=body,
            timeout=self.settings.paypal_timeout_seconds,
        )

        if resp.status_code != 200:
            raise ProviderAuthenticationError(
                f"PayPal Sandbox OAuth authentication failed with HTTP {resp.status_code}: {resp.body}"
            )

        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise ProviderAuthenticationError("PayPal OAuth response missing 'access_token'.")

        self._cached_token = token
        expires_in = int(data.get("expires_in", 3600))
        # Buffer expiration by 60 seconds
        self._token_expires_at = datetime.fromtimestamp(now.timestamp() + max(expires_in - 60, 60), tz=timezone.utc)
        return token

    def submit_payout(self, request: PayoutRequest) -> PayoutResult:
        """Submit single payout batch to PayPal Sandbox."""
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Format amount to 2 decimal places (e.g. 350 cents -> '3.50')
        dollars_str = f"{request.amount_minor_units / 100:.2f}"
        receiver_email = request.recipient_info.get("email", f"worker_{request.task_id[:8]}@example.com")

        # Stable sender_batch_id derived from idempotency_key to prevent duplicate submissions
        sender_batch_id = f"batch_{request.idempotency_key}"[:64]

        payload = {
            "sender_batch_header": {
                "sender_batch_id": sender_batch_id,
                "email_subject": f"Bounty Award for Task {request.task_id[:8]}",
                "email_message": "Thank you for completing work on AgentBounty.",
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "amount": {"value": dollars_str, "currency": request.currency.upper()},
                    "note": f"AgentBounty Payout - Task {request.task_id}",
                    "sender_item_id": f"item_{request.idempotency_key}"[:64],
                    "receiver": receiver_email,
                }
            ],
        }

        url = f"{self.SANDBOX_BASE_URL}/v1/payments/payouts"
        resp = self.transport.request(
            method="POST",
            url=url,
            headers=headers,
            body=json.dumps(payload).encode("utf-8"),
            timeout=self.settings.paypal_timeout_seconds,
        )

        now = utc_now()

        # Handle HTTP 201 Created
        if resp.status_code == 201:
            data = resp.json()
            batch_header = data.get("batch_header", {})
            payout_batch_id = batch_header.get("payout_batch_id")
            raw_status = (batch_header.get("batch_status") or "PENDING").upper()

            # Map PayPal batch status to domain PaymentStatus
            if raw_status in ("SUCCESS", "COMPLETED"):
                status = PaymentStatus.SUCCEEDED
            elif raw_status in ("PENDING", "PROCESSING"):
                status = PaymentStatus.PENDING
            elif raw_status in ("DENIED", "CANCELED"):
                status = PaymentStatus.FAILED
            else:
                status = PaymentStatus.UNKNOWN

            return PayoutResult(
                provider_name=self.provider_name,
                execution_mode=self.execution_mode,
                status=status,
                external_reference=payout_batch_id,
                provider_status=raw_status,
                timestamp=now,
            )

        # Handle Duplicate Submission / Conflict (HTTP 400 or 409)
        data = resp.json() if resp.body.startswith("{") else {}
        name = data.get("name") or ""
        message = data.get("message") or resp.body

        if resp.status_code in (400, 409) and "DUPLICATE" in (name + message).upper():
            return PayoutResult(
                provider_name=self.provider_name,
                execution_mode=self.execution_mode,
                status=PaymentStatus.UNKNOWN,
                external_reference=None,
                provider_status="DUPLICATE_SENDER_BATCH_ID",
                error_code="DUPLICATE_BATCH_ID",
                error_message=f"PayPal rejected duplicate batch ID: {message}",
                timestamp=now,
            )

        # Handle Definitive Failure / Rejection
        raise ProviderRejectionError(
            f"PayPal Sandbox rejected payout with HTTP {resp.status_code} ({name}): {message}"
        )

    def get_payout_status(
        self,
        payout_reference: str,
        idempotency_key: str | None = None,
    ) -> PayoutResult:
        """Reconcile payout status against PayPal Sandbox details endpoint."""
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        url = f"{self.SANDBOX_BASE_URL}/v1/payments/payouts/{payout_reference}"
        resp = self.transport.request(
            method="GET",
            url=url,
            headers=headers,
            timeout=self.settings.paypal_timeout_seconds,
        )

        now = utc_now()

        if resp.status_code != 200:
            raise InvalidProviderResponseError(
                f"Failed to query PayPal payout status for '{payout_reference}': HTTP {resp.status_code}"
            )

        data = resp.json()
        batch_header = data.get("batch_header", {})
        raw_batch_status = (batch_header.get("batch_status") or "UNKNOWN").upper()
        items = data.get("items", [])

        # Inspect both batch header and individual item status
        if raw_batch_status in ("DENIED", "CANCELED"):
            status = PaymentStatus.FAILED
            item_status = raw_batch_status
        elif items:
            # Individual item status is authoritative over batch header
            item_status = (items[0].get("transaction_status") or "").upper()
            if item_status == "SUCCESS":
                status = PaymentStatus.SUCCEEDED
            elif item_status in ("FAILED", "BLOCKED", "RETURNED"):
                status = PaymentStatus.FAILED
            elif item_status in ("PENDING", "UNCLAIMED", "ONHOLD", "PROCESSING"):
                status = PaymentStatus.PENDING
            else:
                status = PaymentStatus.UNKNOWN
        else:
            # When items array is omitted, a successful batch header is NOT proof of item delivery
            item_status = f"batch_only_{raw_batch_status}"
            if raw_batch_status in ("SUCCESS", "COMPLETED", "PENDING", "PROCESSING"):
                status = PaymentStatus.PENDING
            else:
                status = PaymentStatus.UNKNOWN

        return PayoutResult(
            provider_name=self.provider_name,
            execution_mode=self.execution_mode,
            status=status,
            external_reference=payout_reference,
            provider_status=f"batch={raw_batch_status}, item={item_status}",
            timestamp=now,
        )
