"""Human financial authorization service enforcing human-in-the-loop control."""

from __future__ import annotations

from decimal import Decimal
from sqlalchemy.orm import Session

from agentbounty.config.settings import Settings, get_settings
from agentbounty.domain.enums import (
    AuthorizationDecision,
    BountyStatus,
    PaymentStatus,
    TaskStatus,
    VerificationStatus,
)
from agentbounty.domain.money import Money, to_minor_units
from agentbounty.domain.schemas import PaymentAuthorizationRead
from agentbounty.exceptions import (
    BountyAmountMismatchError,
    BudgetExceededError,
    CurrencyMismatchError,
    DuplicatePaymentError,
    EntityNotFoundError,
    InvalidAuthorizationError,
    InvalidMoneyError,
    InvalidStateTransitionError,
    UnauthorizedActorError,
    VerificationNotPassedError,
)
from agentbounty.payments.schemas import AuthorizationRequest, RevocationRequest
from agentbounty.persistence.repositories import (
    AuditEventRepository,
    BountyRepository,
    PaymentAuthorizationRepository,
    PaymentTransactionRepository,
    TaskRepository,
    VerificationRepository,
    WorkerResultRepository,
)


class PaymentAuthorizationService:
    """Service enforcing human financial governance over task payouts.

    CORE SECURITY INVARIANT:
    Autonomous agents (Manager, Worker, System) have ZERO financial authority.
    Only an explicit HUMAN actor can authorize, reject, or revoke payouts.
    """

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

        # Repositories
        self.task_repo = TaskRepository(session)
        self.bounty_repo = BountyRepository(session)
        self.worker_result_repo = WorkerResultRepository(session)
        self.verification_repo = VerificationRepository(session)
        self.auth_repo = PaymentAuthorizationRepository(session)
        self.tx_repo = PaymentTransactionRepository(session)
        self.audit_repo = AuditEventRepository(session)

    def authorize_payment(self, request: AuthorizationRequest) -> PaymentAuthorizationRead:
        """Process a human financial authorization or rejection decision.

        Raises:
            UnauthorizedActorError: If the actor is not explicitly classified as HUMAN.
            EntityNotFoundError: If the task or bounty does not exist.
            InvalidAuthorizationError: If task and bounty associations do not match.
            InvalidStateTransitionError: If task or bounty states are invalid.
            VerificationNotPassedError: If the latest verification is not PASSED.
            BountyAmountMismatchError: If the authorized amount differs from the allocated bounty.
            CurrencyMismatchError: If currency does not match the allocated bounty.
            BudgetExceededError: If the authorized amount exceeds MAX_BOUNTY_USD.
            DuplicatePaymentError: If an active transaction already exists for this task.
        """
        corr_id = request.correlation_id or f"corr-auth-{request.task_id}"

        # 1. Enforce HUMAN-only financial authority
        if not request.actor.is_human():
            self.audit_repo.append(
                entity_type="payment_authorization",
                entity_id="unauthorized_attempt",
                event_type="UNAUTHORIZED_AUTHORIZATION_ATTEMPT",
                actor_type=request.actor.actor_type,
                actor_id=request.actor.actor_id,
                payload={"task_id": request.task_id, "reason": "Non-human actor denied payment authority."},
                correlation_id=corr_id,
            )
            self.session.flush()
            raise UnauthorizedActorError(
                f"Actor '{request.actor.actor_id}' with role '{request.actor.actor_type}' cannot authorize payments. "
                "Financial authorization is strictly restricted to HUMAN operators."
            )

        # 2. Retrieve and validate Task
        task = self.task_repo.get_by_id_or_raise(request.task_id)

        # 3. Retrieve and validate Bounty
        bounty = self.bounty_repo.get_by_task_id(task.id)
        if not bounty:
            raise EntityNotFoundError(f"Task '{task.id}' does not have an associated bounty.")
        if bounty.id != request.bounty_id:
            raise InvalidAuthorizationError(
                f"Bounty ID mismatch: Request specified '{request.bounty_id}', but task bounty is '{bounty.id}'."
            )

        # 4. Check for conflicting active or succeeded payment transactions
        existing_txs = self.tx_repo.list_by_task(task.id)
        active_txs = [
            tx for tx in existing_txs
            if tx.status in (PaymentStatus.CREATED, PaymentStatus.SUBMITTED, PaymentStatus.PENDING, PaymentStatus.SUCCEEDED)
        ]
        if active_txs:
            raise DuplicatePaymentError(
                f"Task '{task.id}' already has an active or completed payment transaction ('{active_txs[0].id}')."
            )

        # 5. Handle REJECTED decision
        if request.decision == AuthorizationDecision.REJECTED:
            auth = self.auth_repo.create(
                task_id=task.id,
                bounty_id=bounty.id,
                authorized_by=request.actor.actor_id,
                decision=AuthorizationDecision.REJECTED,
                authorized_amount_minor_units=bounty.amount,
                currency=bounty.currency,
                reason=request.reason or "Human rejected payment authorization.",
            )

            # Transition Task to REJECTED and Bounty to CANCELLED
            self.task_repo.update_status(task.id, TaskStatus.REJECTED)
            self.bounty_repo.update_status(bounty.id, BountyStatus.CANCELLED)

            self.audit_repo.append(
                entity_type="payment_authorization",
                entity_id=auth.id,
                event_type="PAYMENT_REJECTED",
                actor_type="HUMAN",
                actor_id=request.actor.actor_id,
                payload={
                    "task_id": task.id,
                    "bounty_id": bounty.id,
                    "decision": AuthorizationDecision.REJECTED.value,
                    "reason": auth.reason,
                },
                correlation_id=corr_id,
            )
            self.audit_repo.append(
                entity_type="task",
                entity_id=task.id,
                event_type="TASK_REJECTED",
                actor_type="HUMAN",
                actor_id=request.actor.actor_id,
                payload={"status": TaskStatus.REJECTED.value, "reason": auth.reason},
                correlation_id=corr_id,
            )
            self.audit_repo.append(
                entity_type="bounty",
                entity_id=bounty.id,
                event_type="BOUNTY_CANCELLED",
                actor_type="HUMAN",
                actor_id=request.actor.actor_id,
                payload={"status": BountyStatus.CANCELLED.value, "reason": auth.reason},
                correlation_id=corr_id,
            )
            self.session.flush()
            return PaymentAuthorizationRead.model_validate(auth)

        # 6. Validate AUTHORIZED pre-conditions
        if request.decision != AuthorizationDecision.AUTHORIZED:
            raise InvalidAuthorizationError(f"Unsupported authorization decision: {request.decision.value}")

        # Task must be AWAITING_AUTHORIZATION
        if task.status != TaskStatus.AWAITING_AUTHORIZATION:
            raise InvalidStateTransitionError(
                f"Task '{task.id}' cannot be authorized: status is '{task.status.value}', "
                "expected 'AWAITING_AUTHORIZATION'."
            )

        # Bounty must be AWARDED
        if bounty.status != BountyStatus.AWARDED:
            raise InvalidStateTransitionError(
                f"Bounty '{bounty.id}' cannot be authorized: status is '{bounty.status.value}', "
                "expected 'AWARDED'."
            )

        # Independent Verification must be PASSED
        worker_results = self.worker_result_repo.list_by_task(task.id)
        if not worker_results:
            raise VerificationNotPassedError(f"Task '{task.id}' has no worker deliverables submitted.")
        latest_result = worker_results[-1]
        verifications = self.verification_repo.list_by_worker_result(latest_result.id)
        if not verifications or verifications[0].status != VerificationStatus.PASSED:
            ver_status = verifications[0].status.value if verifications else "NONE"
            raise VerificationNotPassedError(
                f"Cannot authorize payout for task '{task.id}': Latest verification status is '{ver_status}', "
                "expected 'PASSED'."
            )

        # 7. Monetary validation
        raw_amount = request.authorized_amount
        if isinstance(raw_amount, float):
            raise InvalidMoneyError("Float monetary values are strictly prohibited for financial authorization.")

        currency = raw_amount.currency.upper() if isinstance(raw_amount, Money) else request.currency.upper()
        if currency != bounty.currency.upper():
            raise CurrencyMismatchError(
                f"Authorized currency '{currency}' does not match bounty currency '{bounty.currency}'."
            )

        if isinstance(raw_amount, Money):
            amount_minor = raw_amount.minor_units
        elif isinstance(raw_amount, Decimal):
            amount_minor = to_minor_units(raw_amount, bounty.currency)
        elif isinstance(raw_amount, int):
            amount_minor = raw_amount
        else:
            raise InvalidMoneyError(f"Unsupported authorized_amount type: {type(raw_amount).__name__}")

        if amount_minor <= 0:
            raise InvalidMoneyError(f"Authorized amount must be positive, got {amount_minor} minor units.")

        # Exact bounty amount match
        if amount_minor != bounty.amount:
            raise BountyAmountMismatchError(
                f"Authorized amount ({amount_minor} minor units) does not match bounty amount ({bounty.amount} minor units)."
            )

        # Safety ceiling check
        max_bounty_minor = to_minor_units(self.settings.max_bounty_usd, "USD")
        if amount_minor > max_bounty_minor:
            raise BudgetExceededError(
                f"Authorized amount ({amount_minor} minor units) exceeds MAX_BOUNTY_USD ceiling ({max_bounty_minor} minor units)."
            )

        # 8. Persist PaymentAuthorization
        auth = self.auth_repo.create(
            task_id=task.id,
            bounty_id=bounty.id,
            authorized_by=request.actor.actor_id,
            decision=AuthorizationDecision.AUTHORIZED,
            authorized_amount_minor_units=amount_minor,
            currency=currency,
            reason=request.reason,
        )

        self.audit_repo.append(
            entity_type="payment_authorization",
            entity_id=auth.id,
            event_type="PAYMENT_AUTHORIZED",
            actor_type="HUMAN",
            actor_id=request.actor.actor_id,
            payload={
                "task_id": task.id,
                "bounty_id": bounty.id,
                "authorized_amount": amount_minor,
                "currency": currency,
                "decision": AuthorizationDecision.AUTHORIZED.value,
                "reason": request.reason,
            },
            correlation_id=corr_id,
        )

        self.session.flush()
        return PaymentAuthorizationRead.model_validate(auth)

    def revoke_authorization(self, request: RevocationRequest) -> PaymentAuthorizationRead:
        """Revoke a previously granted authorization before payment execution commences.

        Raises:
            UnauthorizedActorError: If the actor is not explicitly HUMAN.
            EntityNotFoundError: If the authorization does not exist.
            InvalidStateTransitionError: If payment submission has already started or decision is not AUTHORIZED.
        """
        corr_id = request.correlation_id or f"corr-revoke-{request.authorization_id}"

        if not request.actor.is_human():
            raise UnauthorizedActorError("Only HUMAN actors can revoke financial authorizations.")

        auth = self.auth_repo.get_by_id(request.authorization_id)
        if not auth:
            raise EntityNotFoundError(f"PaymentAuthorization with ID '{request.authorization_id}' not found.")

        if auth.decision != AuthorizationDecision.AUTHORIZED:
            raise InvalidStateTransitionError(
                f"Cannot revoke authorization '{auth.id}': decision is '{auth.decision.value}', expected 'AUTHORIZED'."
            )

        # Check if payment execution has already commenced
        txs = self.tx_repo.list_by_task(auth.task_id)
        submitted_txs = [
            tx for tx in txs
            if tx.authorization_id == auth.id
            and tx.status in (PaymentStatus.SUBMITTED, PaymentStatus.PENDING, PaymentStatus.SUCCEEDED)
        ]
        if submitted_txs:
            raise InvalidStateTransitionError(
                f"Cannot revoke authorization '{auth.id}': Payment submission has already commenced "
                f"(transaction '{submitted_txs[0].id}' status: '{submitted_txs[0].status.value}')."
            )

        # Update decision to REVOKED
        auth.decision = AuthorizationDecision.REVOKED
        auth.reason = f"Revoked: {request.reason}"

        self.audit_repo.append(
            entity_type="payment_authorization",
            entity_id=auth.id,
            event_type="PAYMENT_AUTHORIZATION_REVOKED",
            actor_type="HUMAN",
            actor_id=request.actor.actor_id,
            payload={"authorization_id": auth.id, "reason": request.reason},
            correlation_id=corr_id,
        )

        self.session.flush()
        return PaymentAuthorizationRead.model_validate(auth)
