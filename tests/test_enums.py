"""Tests for domain workflow enums and string serialization."""

import json

from agentbounty.domain.enums import (
    AgentRole,
    AgentStatus,
    AuthorizationDecision,
    BountyStatus,
    PaymentExecutionMode,
    PaymentStatus,
    SenderType,
    TaskStatus,
    VerificationStatus,
    VerifierType,
)


def test_task_status_values() -> None:
    """Verify all required TaskStatus enum values exist and serialize."""
    expected = {
        "DRAFT",
        "OPEN",
        "ASSIGNED",
        "IN_PROGRESS",
        "SUBMITTED",
        "IN_REVIEW",
        "APPROVED",
        "REJECTED",
        "AWAITING_AUTHORIZATION",
        "PAYMENT_PENDING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }
    actual = {s.value for s in TaskStatus}
    assert actual == expected
    for status in TaskStatus:
        assert json.dumps({"status": status}) == f'{{"status": "{status.value}"}}'


def test_bounty_status_values() -> None:
    """Verify all required BountyStatus enum values exist."""
    expected = {
        "OPEN",
        "RESERVED",
        "AWARDED",
        "PAYMENT_PENDING",
        "PAID",
        "CANCELLED",
    }
    actual = {s.value for s in BountyStatus}
    assert actual == expected


def test_verification_status_values() -> None:
    """Verify all required VerificationStatus enum values exist."""
    expected = {
        "PENDING",
        "PASSED",
        "FAILED",
        "NEEDS_HUMAN_REVIEW",
    }
    actual = {s.value for s in VerificationStatus}
    assert actual == expected


def test_payment_status_values() -> None:
    """Verify all required PaymentStatus enum values exist."""
    expected = {
        "CREATED",
        "SUBMITTED",
        "PENDING",
        "SUCCEEDED",
        "FAILED",
        "UNKNOWN",
    }
    actual = {s.value for s in PaymentStatus}
    assert actual == expected


def test_authorization_decision_values() -> None:
    """Verify all required AuthorizationDecision enum values exist."""
    expected = {
        "AUTHORIZED",
        "REJECTED",
        "REVOKED",
    }
    actual = {d.value for d in AuthorizationDecision}
    assert actual == expected


def test_other_enums() -> None:
    """Verify agent roles, statuses, execution modes, verifier types, and sender types."""
    assert {r.value for r in AgentRole} == {"MANAGER", "WORKER"}
    assert {s.value for s in AgentStatus} == {"ACTIVE", "INACTIVE", "BUSY"}
    assert {m.value for m in PaymentExecutionMode} == {"SIMULATED", "SANDBOX"}
    assert {v.value for v in VerifierType} == {"AUTOMATED", "DETERMINISTIC", "LLM", "HUMAN"}
    assert {st.value for st in SenderType} == {"USER", "MANAGER", "WORKER", "SYSTEM"}
