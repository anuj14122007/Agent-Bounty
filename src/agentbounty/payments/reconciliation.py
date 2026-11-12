"""Payment reconciliation service verifying transaction statuses against providers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from agentbounty.domain.enums import BountyStatus, PaymentStatus, TaskStatus
from agentbounty.domain.schemas import PaymentTransactionRead
from agentbounty.exceptions import EntityNotFoundError, ProviderTimeoutError
from agentbounty.payments.protocols import PaymentProvider, PayoutResult
from agentbounty.payments.providers.mock import MockPaymentProvider
from agentbounty.persistence.repositories import (
    AuditEventRepository,
    BountyRepository,
    PaymentTransactionRepository,
    TaskRepository,
)


class PaymentReconciliationService:
    """Service reconciling payment transaction statuses with provider records.

    INVARIANTS:
    - Never infers success from partial or ambiguous data.
    - Never resends payout disbursements during reconciliation.
    - Strictly idempotent: safe to execute repeatedly without state corruption.
    """

    def __init__(
        self,
        session: Session,
        provider: PaymentProvider | None = None,
    ) -> None:
        self.session = session
        self.provider = provider or MockPaymentProvider()

        # Repositories
        self.tx_repo = PaymentTransactionRepository(session)
        self.task_repo = TaskRepository(session)
        self.bounty_repo = BountyRepository(session)
        self.audit_repo = AuditEventRepository(session)

    def reconcile_transaction(
        self,
        transaction_id: str,
        correlation_id: str | None = None,
    ) -> PaymentTransactionRead:
        """Query provider and update transaction, task, and bounty records accordingly.

        Args:
            transaction_id: Primary key of PaymentTransaction to reconcile.
            correlation_id: Optional tracking correlation identifier.

        Returns:
            Updated PaymentTransactionRead schema.

        Raises:
            EntityNotFoundError: If transaction does not exist.
        """
        corr_id = correlation_id or f"corr-recon-{transaction_id}"

        tx = self.tx_repo.get_by_id(transaction_id)
        if not tx:
            raise EntityNotFoundError(f"PaymentTransaction with ID '{transaction_id}' not found.")

        # Idempotent shortcut: if already succeeded, avoid redundant updates
        if tx.status == PaymentStatus.SUCCEEDED:
            return PaymentTransactionRead.model_validate(tx)

        # Call provider for current status
        reference = tx.external_reference or tx.idempotency_key
        provider_result: PayoutResult
        try:
            provider_result = self.provider.get_payout_status(
                payout_reference=reference,
                idempotency_key=tx.idempotency_key,
            )
        except ProviderTimeoutError as err:
            provider_result = PayoutResult(
                provider_name=self.provider.provider_name,
                execution_mode=self.provider.execution_mode,
                status=PaymentStatus.UNKNOWN,
                external_reference=tx.external_reference,
                provider_status="TIMEOUT",
                error_code="RECONCILIATION_TIMEOUT",
                error_message=str(err),
            )
        except Exception as err:
            provider_result = PayoutResult(
                provider_name=self.provider.provider_name,
                execution_mode=self.provider.execution_mode,
                status=PaymentStatus.UNKNOWN,
                external_reference=tx.external_reference,
                provider_status="ERROR",
                error_code="RECONCILIATION_ERROR",
                error_message=str(err),
            )

        # Apply reconciled status
        if provider_result.status == PaymentStatus.SUCCEEDED:
            self.tx_repo.update_status(
                tx.id,
                PaymentStatus.SUCCEEDED,
                external_reference=provider_result.external_reference or tx.external_reference,
            )
            self.task_repo.update_status(tx.task_id, TaskStatus.COMPLETED)
            self.bounty_repo.update_status(tx.bounty_id, BountyStatus.PAID)

            self.audit_repo.append(
                entity_type="payment_transaction",
                entity_id=tx.id,
                event_type="PAYMENT_RECONCILED",
                actor_type="SYSTEM",
                actor_id=self.provider.provider_name,
                payload={
                    "reconciled_status": PaymentStatus.SUCCEEDED.value,
                    "external_reference": tx.external_reference,
                },
                correlation_id=corr_id,
            )
            self.audit_repo.append(
                entity_type="payment_transaction",
                entity_id=tx.id,
                event_type="PAYMENT_SUCCEEDED",
                actor_type="SYSTEM",
                actor_id=self.provider.provider_name,
                payload={"status": PaymentStatus.SUCCEEDED.value},
                correlation_id=corr_id,
            )
            self.audit_repo.append(
                entity_type="task",
                entity_id=tx.task_id,
                event_type="TASK_COMPLETED",
                actor_type="SYSTEM",
                actor_id="orchestrator",
                payload={"status": TaskStatus.COMPLETED.value},
                correlation_id=corr_id,
            )
            self.audit_repo.append(
                entity_type="bounty",
                entity_id=tx.bounty_id,
                event_type="BOUNTY_PAID",
                actor_type="SYSTEM",
                actor_id="orchestrator",
                payload={"status": BountyStatus.PAID.value},
                correlation_id=corr_id,
            )

        elif provider_result.status == PaymentStatus.FAILED:
            self.tx_repo.update_status(
                tx.id,
                PaymentStatus.FAILED,
                error_code=provider_result.error_code,
                error_message=provider_result.error_message,
            )
            self.task_repo.update_status(tx.task_id, TaskStatus.FAILED)
            # Bounty reverts/remains AWARDED until explicit resolution
            self.bounty_repo.update_status(tx.bounty_id, BountyStatus.AWARDED)

            self.audit_repo.append(
                entity_type="payment_transaction",
                entity_id=tx.id,
                event_type="PAYMENT_RECONCILED",
                actor_type="SYSTEM",
                actor_id=self.provider.provider_name,
                payload={
                    "reconciled_status": PaymentStatus.FAILED.value,
                    "error_code": provider_result.error_code,
                    "error_message": provider_result.error_message,
                },
                correlation_id=corr_id,
            )
            self.audit_repo.append(
                entity_type="payment_transaction",
                entity_id=tx.id,
                event_type="PAYMENT_FAILED",
                actor_type="SYSTEM",
                actor_id=self.provider.provider_name,
                payload={"status": PaymentStatus.FAILED.value},
                correlation_id=corr_id,
            )

        elif provider_result.status == PaymentStatus.PENDING:
            self.tx_repo.update_status(
                tx.id,
                PaymentStatus.PENDING,
                external_reference=provider_result.external_reference or tx.external_reference,
            )
            self.audit_repo.append(
                entity_type="payment_transaction",
                entity_id=tx.id,
                event_type="PAYMENT_RECONCILED",
                actor_type="SYSTEM",
                actor_id=self.provider.provider_name,
                payload={"reconciled_status": PaymentStatus.PENDING.value},
                correlation_id=corr_id,
            )

        elif provider_result.status == PaymentStatus.UNKNOWN:
            # Preserve UNKNOWN status without inventing success
            self.tx_repo.update_status(
                tx.id,
                PaymentStatus.UNKNOWN,
                error_code=provider_result.error_code,
                error_message=provider_result.error_message,
            )
            self.audit_repo.append(
                entity_type="payment_transaction",
                entity_id=tx.id,
                event_type="PAYMENT_RECONCILED",
                actor_type="SYSTEM",
                actor_id=self.provider.provider_name,
                payload={
                    "reconciled_status": PaymentStatus.UNKNOWN.value,
                    "error_code": provider_result.error_code,
                },
                correlation_id=corr_id,
            )

        self.session.flush()
        return PaymentTransactionRead.model_validate(tx)
