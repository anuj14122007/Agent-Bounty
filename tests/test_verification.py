"""Tests for Independent Verification Engine and deterministic acceptance criteria rules."""

from __future__ import annotations

import pytest

from agentbounty.domain.enums import TaskStatus, VerificationStatus, VerifierType
from agentbounty.domain.schemas import TaskRead, WorkerResultRead
from agentbounty.exceptions import VerificationEngineError
from agentbounty.persistence.base import utc_now
from agentbounty.services.verification import VerificationEngine


def _make_task_and_result(
    criteria: list[str],
    content: str,
    worker_agent_id: str = "worker-001",
) -> tuple[TaskRead, WorkerResultRead]:
    now = utc_now()
    task = TaskRead(
        id="task-eval-1",
        title="Verification Test Task",
        description="Task used to test acceptance criteria verification.",
        acceptance_criteria=criteria,
        created_by="tester",
        status=TaskStatus.SUBMITTED,
        created_at=now,
        updated_at=now,
    )
    result = WorkerResultRead(
        id="result-eval-1",
        task_id="task-eval-1",
        worker_agent_id=worker_agent_id,
        content=content,
        artifact_metadata={},
        submission_version=1,
        submitted_at=now,
    )
    return task, result


class TestVerificationEngine:
    """Tests covering criteria parsing, verification scoring, and edge cases."""

    def test_contains_criterion(self) -> None:
        engine = VerificationEngine()
        task, result = _make_task_and_result(
            criteria=["contains:AgentBounty"],
            content="Welcome to the AgentBounty marketplace for autonomous workflows.",
        )
        report = engine.verify(task, result)
        assert report.status == VerificationStatus.PASSED
        assert report.score == 100
        assert "contains:AgentBounty" in report.passed_criteria

        # Negative case
        task_fail, result_fail = _make_task_and_result(
            criteria=["contains:Ethereum"],
            content="This is a pure fiat platform.",
        )
        report_fail = engine.verify(task_fail, result_fail)
        assert report_fail.status == VerificationStatus.FAILED
        assert "contains:Ethereum" in report_fail.failed_criteria

    def test_not_contains_criterion(self) -> None:
        engine = VerificationEngine()
        task, result = _make_task_and_result(
            criteria=["not_contains:forbidden_word"],
            content="This deliverable contains entirely benign terminology.",
        )
        report = engine.verify(task, result)
        assert report.status == VerificationStatus.PASSED

        # Negative case
        task_fail, result_fail = _make_task_and_result(
            criteria=["not_contains:forbidden_word"],
            content="Accidental forbidden_word included.",
        )
        report_fail = engine.verify(task_fail, result_fail)
        assert report_fail.status == VerificationStatus.FAILED
        assert "not_contains:forbidden_word" in report_fail.failed_criteria

    def test_min_and_max_words_criteria(self) -> None:
        engine = VerificationEngine()
        text_10_words = "one two three four five six seven eight nine ten"

        task, result = _make_task_and_result(
            criteria=["min_words:5", "max_words:15"],
            content=text_10_words,
        )
        report = engine.verify(task, result)
        assert report.status == VerificationStatus.PASSED
        assert report.score == 100

        # Min words fail
        task_min_fail, result_min = _make_task_and_result(
            criteria=["min_words:20"],
            content=text_10_words,
        )
        report_min_fail = engine.verify(task_min_fail, result_min)
        assert report_min_fail.status == VerificationStatus.FAILED

        # Max words fail
        task_max_fail, result_max = _make_task_and_result(
            criteria=["max_words:5"],
            content=text_10_words,
        )
        report_max_fail = engine.verify(task_max_fail, result_max)
        assert report_max_fail.status == VerificationStatus.FAILED

    def test_min_and_max_chars_criteria(self) -> None:
        engine = VerificationEngine()
        text = "1234567890"  # 10 chars

        task, result = _make_task_and_result(
            criteria=["min_chars:5", "max_chars:20"],
            content=text,
        )
        report = engine.verify(task, result)
        assert report.status == VerificationStatus.PASSED

        task_fail, result_fail = _make_task_and_result(
            criteria=["min_chars:50"],
            content=text,
        )
        report_fail = engine.verify(task_fail, result_fail)
        assert report_fail.status == VerificationStatus.FAILED

    def test_has_section_criterion(self) -> None:
        engine = VerificationEngine()
        content = "# Overview\nSome body text\n\n## Conclusion\nFinal closing statement."

        task, result = _make_task_and_result(
            criteria=["has_section:Overview", "has_section:Conclusion"],
            content=content,
        )
        report = engine.verify(task, result)
        assert report.status == VerificationStatus.PASSED

        task_fail, result_fail = _make_task_and_result(
            criteria=["has_section:Financial Methodology"],
            content=content,
        )
        report_fail = engine.verify(task_fail, result_fail)
        assert report_fail.status == VerificationStatus.FAILED
        assert "has_section:Financial Methodology" in report_fail.failed_criteria

    def test_ambiguous_criterion_triggers_needs_human_review(self) -> None:
        engine = VerificationEngine()
        task, result = _make_task_and_result(
            criteria=[
                "contains:AgentBounty",
                "The tone must be delightfully inspiring and philosophical",
            ],
            content="AgentBounty is a premier platform for autonomous delegation.",
        )
        report = engine.verify(task, result)
        assert report.status == VerificationStatus.NEEDS_HUMAN_REVIEW
        assert report.score == 50  # 1 out of 2 passed deterministically
        assert "contains:AgentBounty" in report.passed_criteria
        assert "The tone must be delightfully inspiring and philosophical" in report.failed_criteria
        assert "HUMAN REVIEW" in report.explanation

    def test_worker_cannot_verify_own_work(self) -> None:
        engine = VerificationEngine()
        task, result = _make_task_and_result(
            criteria=["min_words:5"],
            content="Valid deliverable text here.",
            worker_agent_id="worker-rogue",
        )
        with pytest.raises(VerificationEngineError, match="cannot verify its own result"):
            engine.verify(task, result, verifier_id="worker-rogue")

    def test_empty_content_fails_criteria(self) -> None:
        engine = VerificationEngine()
        task, result = _make_task_and_result(
            criteria=["min_words:10", "contains:Required"],
            content="",
        )
        report = engine.verify(task, result)
        assert report.status == VerificationStatus.FAILED
        assert report.score == 0
