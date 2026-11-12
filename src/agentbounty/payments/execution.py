"""Payment execution service coordinating human-authorized disbursements and idempotency."""

from __future__ import annotations

import hashlib
from typing import Any
from sqlalchemy.orm import Session

from agentbounty.config.settings import Settings, get_settings
from agentbounty.domain.enums import (
    AuthorizationDecision,
    BountyStatus,
    PaymentStatus,
    TaskStatus,
    VerificationStatus,
)
from agentbounty.domain.schemas import (
    BountyRead,
    PaymentTransactionRead,
    TaskRead,
)
from agentbounty.exceptions import (
    BountyAmountMismatchError,
    CurrencyMismatchError,
    DuplicatePaymentError,
    EntityNotFoundError,
    InvalidAuthorizationError,
    InvalidStateTransitionError,
    ProviderTimeoutError,
    UnauthorizedActorError,
    VerificationNotPassedError,
)
from agentbounty.payments.protocols import PaymentProvider, PayoutRequest, PayoutResult
from agentbounty.payments.providers.mock import MockPaymentProvider
from agentbounty.payments.schemas import PaymentExecutionRequest, PaymentExecutionResult
from agentbounty.persistence.repositories import (
    AuditEventRepository,
    BountyRepository,
    PaymentAuthorizationRepository,
    PaymentTransactionRepository,
    TaskRepository,
    VerificationRepository,
    WorkerResultRepository,
)


class PaymentExecutionService:
    """Service orchestrating financial disbursement following valid human authorization.

    FINANCIAL INVARIANTS:
    - Never executes without a previously persisted, valid HUMAN authorization.
    - Strictly enforces idempotency: same authorization can never double-spend.
    - Transitions to SUBMITTED before provider invocation.
    - Uncertain provider outcomes set status=UNKNOWN without blind retry.
    """

    def __init__(
        self,
        session: Session,
        provider: PaymentProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.provider = provider or MockPaymentProvider()

        # Repositories
        self.task_repo = TaskRepository(session)
        self.bounty_repo = BountyRepository(session)
        self.worker_result_repo = WorkerResultRepository(session)
        self.verification_repo = VerificationRepository(session)
        self.auth_repo = PaymentAuthorizationRepository(session)
        self.tx_repo = PaymentTransactionRepository(session)
        self.audit_repo = AuditEventRepository(session)

    def derive_idempotency_key(self, authorization_id: str, task_id: str) -> str:
        """Derive a stable, deterministic idempotency key for an authorization attempt."""
        raw = f"{task_id}:{authorization_id}"
        return f"idemp_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"

    def execute_payment(self, request: PaymentExecutionRequest) -> PaymentExecutionResult:
        """Execute a human-authorized payout against the configured provider.

        Raises:
            UnauthorizedActorError: If actor attempting execution is not HUMAN.
            EntityNotFoundError: If authorization, task, or bounty is not found.
            InvalidAuthorizationError: If authorization is not AUTHORIZED.
            InvalidStateTransitionError: If task or bounty states are invalid.
            VerificationNotPassedError: If task verification is not PASSED.
            DuplicatePaymentError: If a duplicate attempt is made after a failed transaction.
        """
        corr_id = request.correlation_id or f"corr-exec-{request.authorization_id}"

        # 1. Enforce HUMAN actor authority
        if not request.actor.is_human():
            raise UnauthorizedActorError(
                f"Actor '{request.actor.actor_id}' with role '{request.actor.actor_type}' cannot trigger execution. "
                "Payment execution requires explicit HUMAN operator invocation."
            )

        # 2. Retrieve and revalidate Authorization
        auth = self.auth_repo.get_by_id(request.authorization_id)
        if not auth:
            raise EntityNotFoundError(f"PaymentAuthorization with ID '{request.authorization_id}' not found.")

        if auth.decision != AuthorizationDecision.AUTHORIZED:
            raise InvalidAuthorizationError(
                f"Cannot execute payment: Authorization '{auth.id}' decision is '{auth.decision.value}', "
                "expected 'AUTHORIZED'."
            )

        # 3. Retrieve Task and Bounty
        task = self.task_repo.get_by_id_or_raise(auth.task_id)
        bounty = self.bounty_repo.get_by_task_id(task.id)
        if not bounty:
            raise EntityNotFoundError(f"Bounty for task '{task.id}' not found.")

        # 4. Idempotency & Duplicate Check
        idempotency_key = self.derive_idempotency_key(auth.id, task.id)
        existing_tx = self.tx_repo.get_by_idempotency_key(idempotency_key)

        if existing_tx:
            # If transaction is already processed or in progress, return it idempotently
            if existing_tx.status in (
                PaymentStatus.SUCCEEDED,
                PaymentStatus.PENDING,
                PaymentStatus.SUBMITTED,
                PaymentStatus.UNKNOWN,
                PaymentStatus.CREATED,
            ):
                return PaymentExecutionResult(
                    transaction=PaymentTransactionRead.model_validate(existing_tx),
                    task=TaskRead.model_validate(task),
                    bounty=BountyRead.model_validate(bounty),
                    status=existing_tx.status,
                    is_duplicate=True,
                    correlation_id=corr_id,
                )
            if existing_tx.status == PaymentStatus.FAILED:
                raise DuplicatePaymentError(
                    f"Payment for authorization '{auth.id}' previously reached terminal FAILED state. "
                    "Cannot re-execute under the same authorization."
                )

        # 5. Domain Revalidation
        if task.status not in (TaskStatus.AWAITING_AUTHORIZATION, TaskStatus.PAYMENT_PENDING):
            raise InvalidStateTransitionError(
                f"Task '{task.id}' is in status '{task.status.value}', expected 'AWAITING_AUTHORIZATION'."
            )

        if bounty.status not in (BountyStatus.AWARDED, BountyStatus.PAYMENT_PENDING):
            raise InvalidStateTransitionError(
                f"Bounty '{bounty.id}' is in status '{bounty.status.value}', expected 'AWARDED'."
            )

        # Revalidate Verification status
        worker_results = self.worker_result_repo.list_by_task(task.id)
        if not worker_results:
            raise VerificationNotPassedError(f"Task '{task.id}' has no worker deliverables.")
        verifications = self.verification_repo.list_by_worker_result(worker_results[-1].id)
        if not verifications or verifications[0].status != VerificationStatus.PASSED:
            raise VerificationNotPassedError("Cannot execute payout: Task verification is not PASSED.")

        # Revalidate amount and currency
        if auth.authorized_amount != bounty.amount:
            raise BountyAmountMismatchError(
                f"Authorized amount ({auth.authorized_amount}) does not match bounty amount ({bounty.amount})."
            )
        if auth.currency != bounty.currency:
            raise CurrencyMismatchError(
                f"Authorized currency '{auth.currency}' does not match bounty currency '{bounty.currency}'."
            )

        # 6. Persistence Step A: Create and Submit Transaction Record
        tx = self.tx_repo.create(
            task_id=task.id,
            bounty_id=bounty.id,
            authorization_id=auth.id,
            provider_name=self.provider.provider_name,
            execution_mode=self.provider.execution_mode,
            amount_minor_units=auth.authorized_amount,
            idempotency_key=idempotency_key,
            currency=auth.currency,
        )

        self.audit_repo.append(
            entity_type="payment_transaction",
            entity_id=tx.id,
            event_type="PAYMENT_TRANSACTION_CREATED",
            actor_type="HUMAN",
            actor_id=request.actor.actor_id,
            payload={
                "task_id": task.id,
                "bounty_id": bounty.id,
                "authorization_id": auth.id,
                "amount": tx.amount,
                "currency": tx.currency,
                "provider": tx.provider_name,
                "execution_mode": tx.execution_mode.value,
                "idempotency_key": tx.idempotency_key,
            },
            correlation_id=corr_id,
        )

        # Mark as SUBMITTED before invoking external provider
        self.tx_repo.update_status(tx.id, PaymentStatus.SUBMITTED)
        self.task_repo.update_status(task.id, TaskStatus.PAYMENT_PENDING)
        self.bounty_repo.update_status(bounty.id, BountyStatus.PAYMENT_PENDING)

        self.audit_repo.append(
            entity_type="payment_transaction",
            entity_id=tx.id,
            event_type="PAYMENT_SUBMITTED",
            actor_type="SYSTEM",
            actor_id="orchestrator",
            payload={"status": PaymentStatus.SUBMITTED.value, "provider": self.provider.provider_name},
            correlation_id=corr_id,
        )
        self.session.flush()

        # 7. Provider Invocation (Outside DB transaction lock)
        payout_req = PayoutRequest(
            task_id=task.id,
            bounty_id=bounty.id,
            authorization_id=auth.id,
            amount_minor_units=auth.authorized_amount,
            currency=auth.currency,
            idempotency_key=idempotency_key,
            recipient_info=request.recipient_info,
            metadata={"correlation_id": corr_id},
        )

        payout_result: PayoutResult
        try:
            payout_result = self.provider.submit_payout(payout_req)
        except ProviderTimeoutError as err:
            # Uncertain network outcome: preserve UNKNOWN, do not retry automatically
            payout_result = PayoutResult(
                provider_name=self.provider.provider_name,
                execution_mode=self.provider.execution_mode,
                status=PaymentStatus.UNKNOWN,
                external_reference=None,
                provider_status="TIMEOUT",
                error_code="PROVIDER_TIMEOUT",
                error_message=str(err),
            )
        except Exception as err:
            payout_result = PayoutResult(
                provider_name=self.provider.provider_name,
                execution_mode=self.provider.execution_mode,
                status=PaymentStatus.UNKNOWN,
                external_reference=None,
                provider_status="UNEXPECTED_EXCEPTION",
                error_code="UNEXPECTED_PROVIDER_ERROR",
                error_message=str(err),
            )

        # 8. Persistence Step B: Apply Outcome and Update States
        if payout_result.status == PaymentStatus.SUCCEEDED:
            self.tx_repo.update_status(
                tx.id,
                PaymentStatus.SUCCEEDED,
                external_reference=payout_result.external_reference,
            )
            self.task_repo.update_status(task.id, TaskStatus.COMPLETED)
            self.bounty_repo.update_status(bounty.id, BountyStatus.PAID)

            self.audit_repo.append(
                entity_type="payment_transaction",
                entity_id=tx.id,
                event_type="PAYMENT_SUCCEEDED",
                actor_type="SYSTEM",
                actor_id=self.provider.provider_name,
                payload={
                    "status": PaymentStatus.SUCCEEDED.value,
                    "external_reference": payout_result.external_reference,
                },
                correlation_id=corr_id,
            )
            self.audit_repo.append(
                entity_type="task",
                entity_id=task.id,
                event_type="TASK_COMPLETED",
                actor_type="SYSTEM",
                actor_id="orchestrator",
                payload={"status": TaskStatus.COMPLETED.value},
                correlation_id=corr_id,
            )
            self.audit_repo.append(
                entity_type="bounty",
                entity_id=bounty.id,
                event_type="BOUNTY_PAID",
                actor_type="SYSTEM",
                actor_id="orchestrator",
                payload={"status": BountyStatus.PAID.value},
                correlation_id=corr_id,
            )

        elif payout_result.status == PaymentStatus.PENDING:
            self.tx_repo.update_status(
                tx.id,
                PaymentStatus.PENDING,
                external_reference=payout_result.external_reference,
            )
            self.audit_repo.append(
                entity_type="payment_transaction",
                entity_id=tx.id,
                event_type="PAYMENT_PENDING",
                actor_type="SYSTEM",
                actor_id=self.provider.provider_name,
                payload={"status": PaymentStatus.PENDING.value, "provider_status": payout_result.provider_status},
                correlation_id=corr_id,
            )

        elif payout_result.status == PaymentStatus.UNKNOWN:
            self.tx_repo.update_status(
                tx.id,
                PaymentStatus.UNKNOWN,
                error_code=payout_result.error_code,
                error_message=payout_result.error_message,
            )
            # Task & Bounty remain in PAYMENT_PENDING until reconciled
            self.audit_repo.append(
                entity_type="payment_transaction",
                entity_id=tx.id,
                event_type="PAYMENT_UNKNOWN",
                actor_type="SYSTEM",
                actor_id=self.provider.provider_name,
                payload={
                    "status": PaymentStatus.UNKNOWN.value,
                    "error_code": payout_result.error_code,
                    "error_message": payout_result.error_message,
                },
                correlation_id=corr_id,
            )

        elif payout_result.status == PaymentStatus.FAILED:
            self.tx_repo.update_status(
                tx.id,
                PaymentStatus.FAILED,
                error_code=payout_result.error_code,
                error_message=payout_result.error_message,
            )
            self.task_repo.update_status(task.id, TaskStatus.FAILED)
            # Bounty reverts/remains AWARDED per specification
            self.bounty_repo.update_status(bounty.id, BountyStatus.AWARDED)

            self.audit_repo.append(
                entity_type="payment_transaction",
                entity_id=tx.id,
                event_type="PAYMENT_FAILED",
                actor_type="SYSTEM",
                actor_id=self.provider.provider_name,
                payload={
                    "status": PaymentStatus.FAILED.value,
                    "error_code": payout_result.error_code,
                    "error_message": payout_result.error_message,
                },
                correlation_id=corr_id,
            )
            self.audit_repo.append(
                entity_type="task",
                entity_id=task.id,
                event_type="TASK_FAILED",
                actor_type="SYSTEM",
                actor_id="orchestrator",
                payload={"status": TaskStatus.FAILED.value, "reason": "Payment execution failed."},
                correlation_id=corr_id,
            )

        self.session.flush()

        return PaymentExecutionResult(
            transaction=PaymentTransactionRead.model_validate(tx),
            task=TaskRead.model_validate(task),
            bounty=BountyRead.model_validate(bounty),
            status=tx.status,
            is_duplicate=False,
            correlation_id=corr_id,
        )
