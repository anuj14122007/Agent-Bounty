"""Independent, deterministic verification engine for evaluating worker results."""

from __future__ import annotations

import re
from typing import Any, NamedTuple

from agentbounty.domain.enums import VerificationStatus, VerifierType
from agentbounty.domain.schemas import TaskRead, VerificationCreate, WorkerResultRead
from agentbounty.exceptions import VerificationEngineError


class CriterionEvaluation(NamedTuple):
    """Result of evaluating a single acceptance criterion."""

    criterion: str
    is_supported: bool
    passed: bool
    evidence: str
    criterion_type: str


class VerificationEngine:
    """Independent verification engine decoupled from workers and managers.

    Evaluates WorkerResult against explicit machine-checkable acceptance criteria:
    - contains:<required phrase>
    - not_contains:<forbidden phrase>
    - min_words:<int>
    - max_words:<int>
    - min_chars:<int>
    - max_chars:<int>
    - has_section:<heading title>

    Ambiguous or non-machine-checkable criteria trigger NEEDS_HUMAN_REVIEW status.
    """

    SUPPORTED_PREFIXES = (
        "contains:",
        "not_contains:",
        "min_words:",
        "max_words:",
        "min_chars:",
        "max_chars:",
        "has_section:",
    )

    def verify(
        self,
        task: TaskRead,
        worker_result: WorkerResultRead,
        context: dict[str, Any] | None = None,
        verifier_id: str = "verification_engine_v1",
    ) -> VerificationCreate:
        """Evaluate a worker deliverable against task acceptance criteria.

        Args:
            task: The original task specification and criteria.
            worker_result: The submitted worker result to evaluate.
            context: Optional contextual parameters.
            verifier_id: Identifier of the evaluating component.

        Returns:
            VerificationCreate schema containing status, score, passed/failed lists, and explanation.

        Raises:
            VerificationEngineError: If self-verification is attempted or input is invalid.
        """
        # INVARIANT: Worker can never verify its own work
        if verifier_id == worker_result.worker_agent_id:
            raise VerificationEngineError(
                f"Security violation: Worker '{worker_result.worker_agent_id}' cannot verify its own result."
            )

        content = worker_result.content or ""
        criteria = task.acceptance_criteria

        if not criteria:
            raise VerificationEngineError(f"Task '{task.id}' does not specify any acceptance criteria.")

        evaluations: list[CriterionEvaluation] = []
        for crit in criteria:
            ev = self._evaluate_single_criterion(crit, content)
            evaluations.append(ev)

        passed_list: list[str] = []
        failed_list: list[str] = []
        ambiguous_list: list[str] = []

        for ev in evaluations:
            if not ev.is_supported:
                ambiguous_list.append(ev.criterion)
            elif ev.passed:
                passed_list.append(ev.criterion)
            else:
                failed_list.append(ev.criterion)

        total_criteria = len(criteria)
        passed_count = len(passed_list)

        # Determine outcome status
        if failed_list:
            status = VerificationStatus.FAILED
            score = int(round((passed_count / total_criteria) * 100))
            explanation_lines = [
                f"Verification FAILED ({passed_count}/{total_criteria} criteria met, score: {score}/100).",
                f"Failed criteria ({len(failed_list)}):",
            ]
            for ev in evaluations:
                if ev.is_supported and not ev.passed:
                    explanation_lines.append(f"  - [FAIL] {ev.criterion}: {ev.evidence}")
            if ambiguous_list:
                explanation_lines.append(f"Ambiguous / unsupported criteria requiring review ({len(ambiguous_list)}):")
                for crit in ambiguous_list:
                    explanation_lines.append(f"  - [UNVERIFIED] {crit}")

        elif ambiguous_list:
            # All supported criteria passed, but subjective / unsupported criteria remain
            status = VerificationStatus.NEEDS_HUMAN_REVIEW
            score = int(round((passed_count / total_criteria) * 100))
            explanation_lines = [
                f"Verification requires HUMAN REVIEW ({passed_count}/{total_criteria} deterministic criteria verified).",
                f"Ambiguous or subjective criteria requiring human evaluation ({len(ambiguous_list)}):",
            ]
            for ev in evaluations:
                if not ev.is_supported:
                    explanation_lines.append(f"  - [NEEDS REVIEW] {ev.criterion}: {ev.evidence}")
            if passed_list:
                explanation_lines.append(f"Deterministic criteria satisfied ({len(passed_list)}):")
                for ev in evaluations:
                    if ev.passed:
                        explanation_lines.append(f"  - [PASS] {ev.criterion}: {ev.evidence}")

        else:
            # All criteria are supported and all passed
            status = VerificationStatus.PASSED
            score = 100
            explanation_lines = [
                f"Verification PASSED (100% - all {total_criteria} acceptance criteria satisfied).",
                "Evaluated criteria:",
            ]
            for ev in evaluations:
                explanation_lines.append(f"  - [PASS] {ev.criterion}: {ev.evidence}")

        explanation = "\n".join(explanation_lines)

        return VerificationCreate(
            worker_result_id=worker_result.id,
            status=status,
            score=score,
            passed_criteria=passed_list,
            failed_criteria=failed_list + (ambiguous_list if status == VerificationStatus.NEEDS_HUMAN_REVIEW else []),
            explanation=explanation,
            verifier_type=VerifierType.DETERMINISTIC,
        )

    def _evaluate_single_criterion(self, criterion: str, content: str) -> CriterionEvaluation:
        """Parse and evaluate an individual criterion string."""
        crit_clean = criterion.strip()
        lower_crit = crit_clean.lower()

        # Check for min_words
        if lower_crit.startswith("min_words:"):
            target_str = crit_clean[len("min_words:") :].strip()
            try:
                min_words = int(target_str)
                actual_words = len(content.split())
                passed = actual_words >= min_words
                evidence = f"Deliverable contains {actual_words} words (minimum required: {min_words})"
                return CriterionEvaluation(criterion, True, passed, evidence, "min_words")
            except ValueError:
                return CriterionEvaluation(
                    criterion, False, False, f"Invalid min_words argument: '{target_str}'", "invalid_syntax"
                )

        # Check for max_words
        if lower_crit.startswith("max_words:"):
            target_str = crit_clean[len("max_words:") :].strip()
            try:
                max_words = int(target_str)
                actual_words = len(content.split())
                passed = actual_words <= max_words
                evidence = f"Deliverable contains {actual_words} words (maximum allowed: {max_words})"
                return CriterionEvaluation(criterion, True, passed, evidence, "max_words")
            except ValueError:
                return CriterionEvaluation(
                    criterion, False, False, f"Invalid max_words argument: '{target_str}'", "invalid_syntax"
                )

        # Check for min_chars
        if lower_crit.startswith("min_chars:"):
            target_str = crit_clean[len("min_chars:") :].strip()
            try:
                min_chars = int(target_str)
                actual_chars = len(content)
                passed = actual_chars >= min_chars
                evidence = f"Deliverable contains {actual_chars} characters (minimum required: {min_chars})"
                return CriterionEvaluation(criterion, True, passed, evidence, "min_chars")
            except ValueError:
                return CriterionEvaluation(
                    criterion, False, False, f"Invalid min_chars argument: '{target_str}'", "invalid_syntax"
                )

        # Check for max_chars
        if lower_crit.startswith("max_chars:"):
            target_str = crit_clean[len("max_chars:") :].strip()
            try:
                max_chars = int(target_str)
                actual_chars = len(content)
                passed = actual_chars <= max_chars
                evidence = f"Deliverable contains {actual_chars} characters (maximum allowed: {max_chars})"
                return CriterionEvaluation(criterion, True, passed, evidence, "max_chars")
            except ValueError:
                return CriterionEvaluation(
                    criterion, False, False, f"Invalid max_chars argument: '{target_str}'", "invalid_syntax"
                )

        # Check for contains
        if lower_crit.startswith("contains:"):
            phrase = crit_clean[len("contains:") :].strip()
            if not phrase:
                return CriterionEvaluation(criterion, False, False, "Empty contains target", "invalid_syntax")
            passed = phrase.lower() in content.lower()
            evidence = (
                f"Found phrase '{phrase}' in content"
                if passed
                else f"Missing required phrase '{phrase}' in content"
            )
            return CriterionEvaluation(criterion, True, passed, evidence, "contains")

        # Check for not_contains
        if lower_crit.startswith("not_contains:"):
            phrase = crit_clean[len("not_contains:") :].strip()
            if not phrase:
                return CriterionEvaluation(criterion, False, False, "Empty not_contains target", "invalid_syntax")
            passed = phrase.lower() not in content.lower()
            evidence = (
                f"Phrase '{phrase}' absent from content as required"
                if passed
                else f"Forbidden phrase '{phrase}' detected in content"
            )
            return CriterionEvaluation(criterion, True, passed, evidence, "not_contains")

        # Check for has_section
        if lower_crit.startswith("has_section:"):
            section_title = crit_clean[len("has_section:") :].strip()
            if not section_title:
                return CriterionEvaluation(criterion, False, False, "Empty has_section target", "invalid_syntax")

            escaped = re.escape(section_title)
            # Match markdown headings e.g. # Title, ## Title, or **Title**, or Title:
            pattern = rf"(?:^|\n)\s*(?:#+\s*|\*\*\s*|){escaped}(?:\s*\*+|\s*:|\s*(?:\r?\n|$))"
            matched = bool(re.search(pattern, content, re.IGNORECASE | re.MULTILINE))
            evidence = (
                f"Section header matching '{section_title}' detected"
                if matched
                else f"Required section header '{section_title}' not found in content"
            )
            return CriterionEvaluation(criterion, True, matched, evidence, "has_section")

        # Fallback: unsupported / ambiguous natural language criterion
        return CriterionEvaluation(
            criterion=criterion,
            is_supported=False,
            passed=False,
            evidence="Criterion does not use deterministic syntax (contains:, not_contains:, min_words:, max_words:, min_chars:, has_section:). Cannot be objectively verified by deterministic DEMO engine.",
            criterion_type="ambiguous_natural_language",
        )
