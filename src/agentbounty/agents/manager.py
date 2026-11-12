"""Manager agent implementation responsible for task analysis, worker selection, and delegation."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, NamedTuple

from agentbounty.agents.base import BaseAgent
from agentbounty.agents.profiles import MANAGER_PROFILE
from agentbounty.agents.registry import AgentRegistry
from agentbounty.agents.workers.base import BaseWorker
from agentbounty.config.settings import Settings, get_settings
from agentbounty.domain.enums import AgentRole, AgentStatus
from agentbounty.domain.money import Money, to_minor_units
from agentbounty.domain.schemas import TaskRead
from agentbounty.exceptions import BountyLimitExceededError, InvalidMoneyError, NoEligibleWorkerError


class TaskAnalysis(NamedTuple):
    """Analysis produced by the Manager Agent when inspecting a task."""

    task_id: str
    required_capabilities: list[str]
    complexity_assessment: str
    analysis_notes: str


class WorkerMatch(NamedTuple):
    """Match assessment between a worker and task requirements."""

    worker: BaseWorker
    match_count: int
    match_score: float
    matched_capabilities: list[str]


# Keyword mapping to canonical capabilities for automated analysis
_KEYWORD_CAPABILITY_MAP: dict[str, list[str]] = {
    "write": ["creative-writing", "content-generation"],
    "writer": ["creative-writing", "content-generation"],
    "writing": ["creative-writing", "content-generation"],
    "article": ["creative-writing", "content-generation"],
    "introduction": ["creative-writing", "content-generation"],
    "intro": ["creative-writing", "content-generation"],
    "copy": ["copywriting", "content-generation"],
    "copywriting": ["copywriting", "content-generation"],
    "story": ["creative-writing", "content-generation"],
    "summarize": ["summarization", "editing"],
    "summary": ["summarization", "editing"],
    "summarization": ["summarization", "editing"],
    "format": ["formatting", "editing"],
    "formatting": ["formatting", "editing"],
    "edit": ["editing", "formatting"],
    "editing": ["editing", "formatting"],
    "research": ["research-briefs", "information-synthesis"],
    "investigate": ["research-briefs", "evidence-analysis"],
    "brief": ["research-briefs", "information-synthesis"],
    "evidence": ["evidence-analysis", "fact-organization"],
    "fact": ["fact-organization", "information-synthesis"],
    "sources": ["source-preservation", "information-synthesis"],
    "source": ["source-preservation", "information-synthesis"],
    "data": ["data-analysis", "tabular-summary"],
    "analyst": ["data-analysis", "statistical-calculation"],
    "statistics": ["statistical-calculation", "data-analysis"],
    "statistical": ["statistical-calculation", "data-analysis"],
    "calculate": ["statistical-calculation", "numerical-computation"],
    "calculation": ["statistical-calculation", "numerical-computation"],
    "numerical": ["numerical-computation", "statistical-calculation"],
    "tabular": ["tabular-summary", "structured-reporting"],
    "table": ["tabular-summary", "structured-reporting"],
    "metrics": ["data-analysis", "structured-reporting"],
    "numbers": ["numerical-computation", "statistical-calculation"],
    "code": ["code-drafting", "code-explanation"],
    "python": ["code-drafting", "algorithm-design"],
    "script": ["code-drafting", "algorithm-design"],
    "program": ["code-drafting", "algorithm-design"],
    "algorithm": ["algorithm-design", "code-drafting"],
    "debug": ["debugging-suggestions", "code-explanation"],
    "debugging": ["debugging-suggestions", "code-explanation"],
    "developer": ["code-drafting", "technical-documentation"],
    "technical": ["technical-documentation", "code-explanation"],
    "function": ["code-drafting", "algorithm-design"],
}


class ManagerAgent(BaseAgent):
    """Marketplace delegation coordinator.

    SECURITY INVARIANTS:
    - Never approves its own verification.
    - Never changes verification results.
    - Never authorizes or executes payments.
    - Never bypasses task state transitions or limits.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        settings: Settings | None = None,
        id: str = MANAGER_PROFILE.id,
        name: str = MANAGER_PROFILE.name,
        description: str = MANAGER_PROFILE.description,
        capabilities: list[str] | None = None,
        status: AgentStatus = MANAGER_PROFILE.status,
    ) -> None:
        super().__init__(
            id=id,
            name=name,
            role=AgentRole.MANAGER,
            description=description,
            capabilities=capabilities or list(MANAGER_PROFILE.capabilities),
            status=status,
        )
        self.registry = registry
        self.settings = settings or get_settings()

    def analyze_task(self, task: TaskRead, explicit_capabilities: list[str] | None = None) -> TaskAnalysis:
        """Analyze a task to determine required capabilities and execution complexity."""
        if explicit_capabilities:
            required = [c.strip().lower() for c in explicit_capabilities if c and c.strip()]
        else:
            required = self._extract_required_capabilities(task)

        notes = (
            f"Analyzed task '{task.title}'. Identified {len(required)} required capabilities: "
            f"{', '.join(required) if required else 'None'}. "
            f"Acceptance criteria count: {len(task.acceptance_criteria)}."
        )

        return TaskAnalysis(
            task_id=task.id,
            required_capabilities=required,
            complexity_assessment="STANDARD",
            analysis_notes=notes,
        )

    def _extract_required_capabilities(self, task: TaskRead) -> list[str]:
        """Extract matching capabilities from task text using deterministic keyword scanning."""
        combined_text = f"{task.title} {task.description} {' '.join(task.acceptance_criteria)}".lower()
        words = re.findall(r"\b[a-z]{3,}\b", combined_text)

        identified: set[str] = set()
        for word in words:
            if word in _KEYWORD_CAPABILITY_MAP:
                identified.update(_KEYWORD_CAPABILITY_MAP[word])

        return sorted(identified)

    def rank_workers(
        self,
        required_capabilities: list[str],
        active_only: bool = True,
    ) -> list[WorkerMatch]:
        """Rank eligible workers using transparent capability matching and deterministic tie-breaking.

        Tie-breaking rule:
        1. Match score (descending)
        2. Match count (descending)
        3. Worker name (alphabetical ascending)
        4. Worker ID (alphabetical ascending)
        """
        req_clean = [c.strip().lower() for c in required_capabilities if c and c.strip()]
        total_req = len(req_clean) if req_clean else 1

        workers = self.registry.list_workers(active_only=active_only)
        matches: list[WorkerMatch] = []

        for worker in workers:
            matched = worker.match_capabilities(req_clean)
            if matched:
                score = round(len(matched) / total_req, 4)
                matches.append(
                    WorkerMatch(
                        worker=worker,
                        match_count=len(matched),
                        match_score=score,
                        matched_capabilities=matched,
                    )
                )

        # Sort with deterministic tie-breaking
        matches.sort(
            key=lambda m: (-m.match_score, -m.match_count, m.worker.name, m.worker.id)
        )
        return matches

    def select_worker(
        self,
        task: TaskRead,
        required_capabilities: list[str] | None = None,
    ) -> tuple[BaseWorker, WorkerMatch, str]:
        """Select the highest-ranked eligible worker for the task.

        Returns:
            Tuple of (Selected BaseWorker, WorkerMatch details, Explanation string).

        Raises:
            NoEligibleWorkerError: If no active worker possesses any matching capabilities.
        """
        req = required_capabilities if required_capabilities is not None else self._extract_required_capabilities(task)
        if not req:
            raise NoEligibleWorkerError(
                f"Cannot delegate task '{task.id}' ({task.title!r}): No required capabilities could be identified."
            )

        ranked = self.rank_workers(req, active_only=True)
        if not ranked:
            raise NoEligibleWorkerError(
                f"No eligible active worker found satisfying task '{task.id}' requirements: {req}. "
                "Available workers did not match any required capabilities."
            )

        top_match = ranked[0]
        selected_worker = top_match.worker

        explanation = (
            f"Manager selected worker '{selected_worker.name}' (ID: {selected_worker.id}) "
            f"with capability match score {top_match.match_score:.2f} ({top_match.match_count}/{len(req)} matches: "
            f"{', '.join(top_match.matched_capabilities)}). "
            f"Tie-breaking: deterministic lexicographical order."
        )

        return selected_worker, top_match, explanation

    def calculate_bounty(
        self,
        task: TaskRead,
        proposed_amount: Decimal | Money | None = None,
    ) -> Money:
        """Validate and allocate bounty amount respecting the configured safety ceiling.

        FINANCIAL INVARIANTS:
        - Float arithmetic is strictly prohibited.
        - Negative or zero amounts are rejected.
        - Cannot exceed self.settings.max_bounty_usd.
        """
        if isinstance(proposed_amount, float):
            raise InvalidMoneyError("Float amounts are strictly forbidden for bounty calculation.")

        if proposed_amount is None:
            # Default to standard safe demo bounty ($1.00), bounded by max_bounty_usd
            default_amount = min(Decimal("1.00"), self.settings.max_bounty_usd)
            return Money(amount=default_amount, currency="USD")

        if isinstance(proposed_amount, Money):
            amount_decimal = proposed_amount.amount
            currency = proposed_amount.currency
        elif isinstance(proposed_amount, Decimal):
            amount_decimal = proposed_amount
            currency = "USD"
        else:
            raise InvalidMoneyError(f"Unsupported bounty type: {type(proposed_amount).__name__}")

        if amount_decimal <= Decimal(0):
            raise InvalidMoneyError(f"Bounty amount must be strictly greater than zero, got {amount_decimal}.")

        # Enforce maximum safety ceiling
        if amount_decimal > self.settings.max_bounty_usd:
            raise BountyLimitExceededError(
                f"Proposed bounty ${amount_decimal} exceeds configured maximum limit of ${self.settings.max_bounty_usd}."
            )

        # Enforce exact minor unit precision (no sub-cents)
        to_minor_units(amount_decimal, currency)

        return Money(amount=amount_decimal, currency=currency)

    # Explicit enforcement of authority restrictions
    def approve_verification(self, *args: Any, **kwargs: Any) -> None:
        """Manager has zero authority to approve verifications."""
        raise PermissionError("ManagerAgent is strictly prohibited from approving verifications.")

    def authorize_payment(self, *args: Any, **kwargs: Any) -> None:
        """Manager has zero authority to authorize financial disbursements."""
        raise PermissionError("ManagerAgent is strictly prohibited from authorizing payments.")

    def execute_payment(self, *args: Any, **kwargs: Any) -> None:
        """Manager has zero authority to execute financial disbursements."""
        raise PermissionError("ManagerAgent is strictly prohibited from executing payments.")
