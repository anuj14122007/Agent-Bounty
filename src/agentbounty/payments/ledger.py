"""Persistent payment transaction ledger service."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from agentbounty.domain.enums import PaymentExecutionMode, PaymentStatus
from agentbounty.domain.schemas import (
    AuditEventRead,
    PaymentAuthorizationRead,
    PaymentTransactionRead,
)
from agentbounty.exceptions import EntityNotFoundError
from agentbounty.payments.schemas import PaymentHistoryRead
from agentbounty.persistence.models import (
    AuditEvent,
    PaymentAuthorization,
    PaymentTransaction,
)
from agentbounty.persistence.repositories import (
    AuditEventRepository,
    PaymentAuthorizationRepository,
    PaymentTransactionRepository,
)


class TransactionLedgerService:
    """Service providing queryable, persistent access to payment transactions and audit logs."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.tx_repo = PaymentTransactionRepository(session)
        self.auth_repo = PaymentAuthorizationRepository(session)
        self.audit_repo = AuditEventRepository(session)

    def get_transaction(self, tx_id: str) -> PaymentTransactionRead | None:
        """Retrieve a payment transaction by primary key."""
        tx = self.tx_repo.get_by_id(tx_id)
        return PaymentTransactionRead.model_validate(tx) if tx else None

    def get_transaction_or_raise(self, tx_id: str) -> PaymentTransactionRead:
        """Retrieve a payment transaction by primary key or raise EntityNotFoundError."""
        tx = self.get_transaction(tx_id)
        if not tx:
            raise EntityNotFoundError(f"PaymentTransaction with ID '{tx_id}' not found in ledger.")
        return tx

    def list_transactions(
        self,
        status: PaymentStatus | None = None,
        provider_name: str | None = None,
        execution_mode: PaymentExecutionMode | None = None,
        task_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PaymentTransactionRead]:
        """Query transactions using indexed database filters without loading the full table."""
        stmt = select(PaymentTransaction)

        if status is not None:
            stmt = stmt.where(PaymentTransaction.status == status)
        if provider_name is not None:
            stmt = stmt.where(PaymentTransaction.provider_name == provider_name)
        if execution_mode is not None:
            stmt = stmt.where(PaymentTransaction.execution_mode == execution_mode)
        if task_id is not None:
            stmt = stmt.where(PaymentTransaction.task_id == task_id)
        if start_time is not None:
            stmt = stmt.where(PaymentTransaction.created_at >= start_time)
        if end_time is not None:
            stmt = stmt.where(PaymentTransaction.created_at <= end_time)

        stmt = stmt.order_by(PaymentTransaction.created_at.desc()).limit(limit).offset(offset)
        records = list(self.session.scalars(stmt).all())
        return [PaymentTransactionRead.model_validate(r) for r in records]

    def get_task_payment_history(self, task_id: str) -> PaymentHistoryRead:
        """Retrieve full financial and audit history associated with a task."""
        # 1. Authorizations
        auths = self.auth_repo.list_by_task(task_id)
        auth_reads = [PaymentAuthorizationRead.model_validate(a) for a in auths]
        auth_ids = {a.id for a in auths}

        # 2. Transactions
        txs = self.tx_repo.list_by_task(task_id)
        tx_reads = [PaymentTransactionRead.model_validate(t) for t in txs]
        tx_ids = {t.id for t in txs}

        # 3. Audit Events related to this task and its financial entities
        entity_ids = {task_id} | auth_ids | tx_ids
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.entity_id.in_(entity_ids))
            .order_by(AuditEvent.timestamp.asc())
        )
        audit_records = list(self.session.scalars(stmt).all())
        audit_reads = [AuditEventRead.model_validate(e) for e in audit_records]

        return PaymentHistoryRead(
            task_id=task_id,
            authorizations=auth_reads,
            transactions=tx_reads,
            audit_events=audit_reads,
        )
