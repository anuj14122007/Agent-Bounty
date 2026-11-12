"""Base worker implementation extending the common agent contract."""

from __future__ import annotations

from typing import Any

from agentbounty.agents.base import BaseAgent, WorkerExecutionResult
from agentbounty.domain.enums import AgentRole, AgentStatus
from agentbounty.domain.schemas import TaskRead
from agentbounty.exceptions import WorkerExecutionError
from agentbounty.providers.demo_provider import DemoAgentProvider
from agentbounty.providers.protocols import AgentProvider


class BaseWorker(BaseAgent):
    """Abstract base worker capable of executing assigned tasks."""

    def __init__(
        self,
        id: str,
        name: str,
        description: str,
        capabilities: list[str] | None = None,
        status: AgentStatus = AgentStatus.ACTIVE,
        provider: AgentProvider | None = None,
    ) -> None:
        super().__init__(
            id=id,
            name=name,
            role=AgentRole.WORKER,
            description=description,
            capabilities=capabilities,
            status=status,
        )
        self.provider = provider or DemoAgentProvider()

    def execute(
        self,
        task: TaskRead,
        context: dict[str, Any] | None = None,
        submission_version: int = 1,
    ) -> WorkerExecutionResult:
        """Execute delegated task and return a structured WorkerExecutionResult.

        Args:
            task: Task to be executed.
            context: Additional contextual variables.
            submission_version: Submission version counter (default 1).

        Returns:
            WorkerExecutionResult containing generated deliverable and metadata.

        Raises:
            WorkerExecutionError: If execution fails or returns empty content.
        """
        if not self.is_active:
            raise WorkerExecutionError(
                f"Worker '{self.name}' ({self.id}) is not active (status: {self.status.value}) and cannot execute tasks."
            )

        try:
            content, metadata = self.provider.generate_worker_deliverable(
                worker_name=self.name,
                task_title=task.title,
                task_description=task.description,
                acceptance_criteria=task.acceptance_criteria,
                context=context or {},
            )
        except Exception as err:
            raise WorkerExecutionError(f"Worker '{self.name}' encountered execution failure: {err}") from err

        if not content or not content.strip():
            raise WorkerExecutionError(f"Worker '{self.name}' produced an empty deliverable for task '{task.id}'.")

        # Enrich metadata with worker execution provenance
        metadata_enriched = dict(metadata)
        metadata_enriched.update(
            {
                "executed_by_agent_id": self.id,
                "executed_by_agent_name": self.name,
                "submission_version": submission_version,
            }
        )

        return WorkerExecutionResult(
            worker_agent_id=self.id,
            content=content.strip(),
            artifact_metadata=metadata_enriched,
            submission_version=submission_version,
        )
