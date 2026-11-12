"""Tests for Agent base contracts, specialist workers, registry, and ManagerAgent."""

from __future__ import annotations

from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from agentbounty.agents.base import BaseAgent, WorkerExecutionResult
from agentbounty.agents.manager import ManagerAgent, TaskAnalysis
from agentbounty.agents.profiles import (
    CODE_ASSISTANT_PROFILE,
    CREATIVE_WRITER_PROFILE,
    DATA_ANALYST_PROFILE,
    MANAGER_PROFILE,
    RESEARCHER_PROFILE,
)
from agentbounty.agents.registry import AgentRegistry
from agentbounty.agents.workers.code_assistant import CodeAssistantWorker
from agentbounty.agents.workers.creative_writer import CreativeWriterWorker
from agentbounty.agents.workers.data_analyst import DataAnalystWorker
from agentbounty.agents.workers.researcher import ResearchAssistantWorker
from agentbounty.config.settings import Settings
from agentbounty.domain.enums import AgentRole, AgentStatus, TaskStatus
from agentbounty.domain.money import Money
from agentbounty.domain.schemas import TaskRead
from agentbounty.exceptions import (
    BountyLimitExceededError,
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidMoneyError,
    NoEligibleWorkerError,
    WorkerExecutionError,
)
from agentbounty.persistence.repositories import AgentRepository
from agentbounty.persistence.base import utc_now


def _make_dummy_task(
    title: str = "Test Task",
    description: str = "Please write a comprehensive summary article.",
    criteria: list[str] | None = None,
    task_id: str = "task-1234",
) -> TaskRead:
    now = utc_now()
    return TaskRead(
        id=task_id,
        title=title,
        description=description,
        acceptance_criteria=criteria or ["contains:summary", "min_words:20"],
        created_by="human_tester",
        status=TaskStatus.OPEN,
        created_at=now,
        updated_at=now,
    )


class TestAgentRegistry:
    """Tests covering AgentRegistry registration, filtering, and DB synchronization."""

    def test_default_workers_registered(self) -> None:
        registry = AgentRegistry()
        workers = registry.list_workers(active_only=False)
        assert len(workers) == 4
        worker_ids = {w.id for w in workers}
        assert CREATIVE_WRITER_PROFILE.id in worker_ids
        assert RESEARCHER_PROFILE.id in worker_ids
        assert DATA_ANALYST_PROFILE.id in worker_ids
        assert CODE_ASSISTANT_PROFILE.id in worker_ids

    def test_manager_not_in_workers_list(self) -> None:
        registry = AgentRegistry()
        manager = ManagerAgent(registry=registry)
        registry.register(manager)

        all_agents = registry.list_agents()
        assert any(a.role == AgentRole.MANAGER for a in all_agents)

        workers = registry.list_workers()
        assert not any(w.role == AgentRole.MANAGER for w in workers)
        assert not any(w.id == manager.id for w in workers)

    def test_retrieve_by_id_and_raises(self) -> None:
        registry = AgentRegistry()
        writer = registry.get_or_raise(CREATIVE_WRITER_PROFILE.id)
        assert writer.name == CREATIVE_WRITER_PROFILE.name

        with pytest.raises(EntityNotFoundError, match="not found in registry"):
            registry.get_or_raise("non-existent-id")

    def test_duplicate_registration_rejected(self) -> None:
        registry = AgentRegistry()
        duplicate_worker = CreativeWriterWorker(id=CREATIVE_WRITER_PROFILE.id)
        with pytest.raises(DuplicateEntityError, match="already registered"):
            registry.register(duplicate_worker, allow_replace=False)

    def test_filter_by_capabilities(self) -> None:
        registry = AgentRegistry()
        matches = registry.filter_by_capabilities(["statistical-calculation"])
        assert len(matches) == 1
        assert matches[0].name == "Data Analyst"

        code_matches = registry.filter_by_capabilities(["code-drafting", "debugging-suggestions"])
        assert len(code_matches) == 1
        assert code_matches[0].name == "Code Assistant"

    def test_inactive_worker_excluded_from_active_list(self) -> None:
        registry = AgentRegistry()
        writer = registry.get_worker_or_raise(CREATIVE_WRITER_PROFILE.id)
        writer.status = AgentStatus.INACTIVE

        active_workers = registry.list_workers(active_only=True)
        assert not any(w.id == writer.id for w in active_workers)

        all_workers = registry.list_workers(active_only=False)
        assert any(w.id == writer.id for w in all_workers)

    def test_sync_with_db_creates_records_and_avoids_duplicates(self, session: Session) -> None:
        registry = AgentRegistry()
        manager = ManagerAgent(registry=registry)

        # First sync: creates records
        registry.sync_with_db(session, include_agents=[manager])

        agent_repo = AgentRepository(session)
        db_agents = agent_repo.list_all()
        assert len(db_agents) == 5  # 4 workers + 1 manager

        # Second sync: should not create duplicates
        registry.sync_with_db(session, include_agents=[manager])
        db_agents_after = agent_repo.list_all()
        assert len(db_agents_after) == 5


class TestSpecialistWorkers:
    """Tests covering the 4 specialist workers and their demo execution."""

    def test_creative_writer_execution(self) -> None:
        writer = CreativeWriterWorker()
        task = _make_dummy_task(
            title="Professional Introduction",
            description="Write a 300-word introduction for AgentBounty.",
            criteria=["contains:AgentBounty", "has_section:Introduction"],
        )
        result = writer.execute(task)
        assert isinstance(result, WorkerExecutionResult)
        assert result.worker_agent_id == writer.id
        assert "AgentBounty" in result.content
        assert "Introduction" in result.content
        assert result.artifact_metadata["worker_type"] == "creative_writer"

    def test_research_assistant_does_not_claim_live_search(self) -> None:
        researcher = ResearchAssistantWorker()
        task = _make_dummy_task(
            title="Decentralized Task Systems",
            description="Research literature on multi-agent consensus.",
            criteria=["contains:Domain Context"],
        )
        result = researcher.execute(task, context={"sources": ["https://example.com/source1"]})
        assert result.artifact_metadata["external_search_performed"] is False
        assert "Simulated" in result.content or "NOTICE" in result.content
        assert "https://example.com/source1" in result.content

    def test_data_analyst_performs_actual_calculations(self) -> None:
        analyst = DataAnalystWorker()
        task = _make_dummy_task(
            title="Sample Metric Analysis",
            description="Analyze data samples: 10, 20, 30, 40",
            criteria=["contains:Arithmetic Mean"],
        )
        result = analyst.execute(task, context={"data": [10, 20, 30, 40]})
        meta = result.artifact_metadata
        assert "calculated_stats" in meta
        assert meta["calculated_stats"]["sum"] == 100.0
        assert meta["calculated_stats"]["mean"] == 25.0
        assert meta["calculated_stats"]["count"] == 4
        assert "25.0" in result.content

    def test_code_assistant_does_not_execute_code(self) -> None:
        coder = CodeAssistantWorker()
        task = _make_dummy_task(
            title="Parse JSON Manifest",
            description="Create a python function to parse structured json payload.",
            criteria=["contains:def parse_json_manifest"],
        )
        result = coder.execute(task)
        assert result.artifact_metadata["arbitrary_execution_prevented"] is True
        assert "```python" in result.content
        assert "SECURITY NOTICE" in result.content

    def test_inactive_worker_cannot_execute(self) -> None:
        writer = CreativeWriterWorker(status=AgentStatus.INACTIVE)
        task = _make_dummy_task()
        with pytest.raises(WorkerExecutionError, match="is not active"):
            writer.execute(task)


class TestManagerAgent:
    """Tests covering ManagerAgent analysis, worker selection, bounty enforcement, and authority limits."""

    def test_task_analysis_extracts_capabilities(self) -> None:
        registry = AgentRegistry()
        manager = ManagerAgent(registry=registry)

        task = _make_dummy_task(
            title="Write Product Copy",
            description="Please write and format an article.",
            criteria=["contains:product"],
        )
        analysis = manager.analyze_task(task)
        assert isinstance(analysis, TaskAnalysis)
        assert "creative-writing" in analysis.required_capabilities
        assert "content-generation" in analysis.required_capabilities

    def test_worker_selection_matching_and_tie_breaking(self) -> None:
        registry = AgentRegistry()
        manager = ManagerAgent(registry=registry)

        task = _make_dummy_task(
            title="Python Algorithm Design",
            description="Draft a python script for graph search.",
            criteria=["contains:python"],
        )
        selected, match, explanation = manager.select_worker(task)
        assert selected.name == "Code Assistant"
        assert match.match_score > 0
        assert "Manager selected worker 'Code Assistant'" in explanation

    def test_no_eligible_worker_raises_domain_error(self) -> None:
        registry = AgentRegistry()
        manager = ManagerAgent(registry=registry)

        task = _make_dummy_task(
            title="Quantum Teleportation Calibration",
            description="Unrelated extraterrestrial task with zero known capabilities.",
            criteria=["min_words:10"],
        )
        with pytest.raises(NoEligibleWorkerError):
            manager.select_worker(task)

    def test_bounty_ceiling_enforced(self, test_settings: Settings) -> None:
        registry = AgentRegistry()
        manager = ManagerAgent(registry=registry, settings=test_settings)
        task = _make_dummy_task()

        # Valid bounty within $5.00 limit
        bounty = manager.calculate_bounty(task, proposed_amount=Decimal("4.50"))
        assert bounty.amount == Decimal("4.50")

        # Exceeds $5.00 limit
        with pytest.raises(BountyLimitExceededError, match="exceeds configured maximum"):
            manager.calculate_bounty(task, proposed_amount=Decimal("15.00"))

        # Rejects float
        with pytest.raises(InvalidMoneyError, match="Float amounts are strictly forbidden"):
            manager.calculate_bounty(task, proposed_amount=5.0)  # type: ignore

        # Rejects negative amount
        with pytest.raises(InvalidMoneyError, match="greater than zero"):
            manager.calculate_bounty(task, proposed_amount=Decimal("-1.00"))

    def test_manager_authority_restrictions(self) -> None:
        registry = AgentRegistry()
        manager = ManagerAgent(registry=registry)

        with pytest.raises(PermissionError, match="strictly prohibited from approving verifications"):
            manager.approve_verification()

        with pytest.raises(PermissionError, match="strictly prohibited from authorizing payments"):
            manager.authorize_payment()

        with pytest.raises(PermissionError, match="strictly prohibited from executing payments"):
            manager.execute_payment()
