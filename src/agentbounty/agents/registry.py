"""Agent registry managing in-memory and persistent agent lifecycles."""

from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session

from agentbounty.agents.base import BaseAgent
from agentbounty.agents.profiles import (
    CODE_ASSISTANT_PROFILE,
    CREATIVE_WRITER_PROFILE,
    DATA_ANALYST_PROFILE,
    RESEARCHER_PROFILE,
)
from agentbounty.agents.workers.base import BaseWorker
from agentbounty.agents.workers.code_assistant import CodeAssistantWorker
from agentbounty.agents.workers.creative_writer import CreativeWriterWorker
from agentbounty.agents.workers.data_analyst import DataAnalystWorker
from agentbounty.agents.workers.researcher import ResearchAssistantWorker
from agentbounty.domain.enums import AgentRole, AgentStatus
from agentbounty.exceptions import DuplicateEntityError, EntityNotFoundError
from agentbounty.persistence.repositories import AgentRepository
from agentbounty.providers.protocols import AgentProvider


class AgentRegistry:
    """Registry maintaining active agents and synchronizing with persistence.

    Ensures deterministic agent IDs across restarts and prevents duplicate records.
    """

    def __init__(self, provider: AgentProvider | None = None, auto_register_defaults: bool = True) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self.provider = provider
        if auto_register_defaults:
            self.register_default_specialists(provider=self.provider)

    def register_default_specialists(self, provider: AgentProvider | None = None) -> None:
        """Register the four canonical specialist workers with deterministic identities."""
        self.register(CreativeWriterWorker(provider=provider), allow_replace=True)
        self.register(ResearchAssistantWorker(provider=provider), allow_replace=True)
        self.register(DataAnalystWorker(provider=provider), allow_replace=True)
        self.register(CodeAssistantWorker(provider=provider), allow_replace=True)

    def register(self, agent: BaseAgent, allow_replace: bool = False) -> None:
        """Register an agent instance in the registry.

        Args:
            agent: The agent instance to register.
            allow_replace: Whether to allow overwriting an existing registration.

        Raises:
            DuplicateEntityError: If agent ID is already registered and allow_replace is False.
        """
        if agent.id in self._agents and not allow_replace:
            raise DuplicateEntityError(
                f"Agent with ID '{agent.id}' ({agent.name}) is already registered in registry."
            )
        self._agents[agent.id] = agent

    def get(self, agent_id: str) -> BaseAgent | None:
        """Retrieve an agent by its ID, returning None if not found."""
        return self._agents.get(agent_id)

    def get_or_raise(self, agent_id: str) -> BaseAgent:
        """Retrieve an agent by its ID or raise EntityNotFoundError."""
        agent = self.get(agent_id)
        if not agent:
            raise EntityNotFoundError(f"Agent with ID '{agent_id}' not found in registry.")
        return agent

    def get_worker(self, worker_id: str) -> BaseWorker | None:
        """Retrieve a specialist worker by ID, returning None if not found or not a worker."""
        agent = self.get(worker_id)
        if agent and isinstance(agent, BaseWorker) and agent.role == AgentRole.WORKER:
            return agent
        return None

    def get_worker_or_raise(self, worker_id: str) -> BaseWorker:
        """Retrieve a specialist worker by ID or raise EntityNotFoundError."""
        worker = self.get_worker(worker_id)
        if not worker:
            raise EntityNotFoundError(f"Worker with ID '{worker_id}' not found in registry.")
        return worker

    def list_agents(
        self,
        role: AgentRole | None = None,
        status: AgentStatus | None = None,
    ) -> list[BaseAgent]:
        """List registered agents with optional role and status filters."""
        result: list[BaseAgent] = []
        for agent in self._agents.values():
            if role is not None and agent.role != role:
                continue
            if status is not None and agent.status != status:
                continue
            result.append(agent)
        return result

    def list_workers(self, active_only: bool = True) -> list[BaseWorker]:
        """List specialist workers in the registry. Excludes Manager agents."""
        workers: list[BaseWorker] = []
        for agent in self._agents.values():
            if isinstance(agent, BaseWorker) and agent.role == AgentRole.WORKER:
                if active_only and not agent.is_active:
                    continue
                workers.append(agent)
        return workers

    def filter_by_capabilities(
        self,
        required_capabilities: list[str],
        active_only: bool = True,
    ) -> list[BaseWorker]:
        """Filter eligible workers who possess at least one required capability."""
        req_clean = [c.strip().lower() for c in required_capabilities if c and c.strip()]
        eligible: list[BaseWorker] = []
        for worker in self.list_workers(active_only=active_only):
            if any(worker.has_capability(c) for c in req_clean):
                eligible.append(worker)
        return eligible

    def sync_with_db(
        self,
        session: Session,
        include_agents: list[BaseAgent] | None = None,
    ) -> None:
        """Synchronize in-memory registered agents with the persistence layer.

        Prevents duplicate records across restarts by querying by stable agent ID.
        """
        repo = AgentRepository(session)
        all_to_sync = list(self._agents.values())
        if include_agents:
            all_to_sync.extend(include_agents)

        for agent in all_to_sync:
            existing = repo.get_by_id(agent.id)
            if existing is None:
                repo.create(
                    id=agent.id,
                    name=agent.name,
                    role=agent.role,
                    description=agent.description,
                    capabilities=list(agent.capabilities),
                    status=agent.status,
                )
            else:
                # Update status and capabilities if changed in code
                existing.status = agent.status
                existing.capabilities = list(agent.capabilities)
                existing.description = agent.description
                existing.name = agent.name
        session.flush()
