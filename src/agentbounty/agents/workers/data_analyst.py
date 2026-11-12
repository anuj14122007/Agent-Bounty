"""Data Analyst specialist worker implementation."""

from __future__ import annotations

from agentbounty.agents.profiles import DATA_ANALYST_PROFILE
from agentbounty.agents.workers.base import BaseWorker
from agentbounty.domain.enums import AgentStatus
from agentbounty.providers.protocols import AgentProvider


class DataAnalystWorker(BaseWorker):
    """Specialist worker focused on quantitative interpretation, statistics, and tabular summaries.

    Uses actual mathematical computation when numerical input is provided. Never fabricates datasets.
    """

    def __init__(
        self,
        id: str = DATA_ANALYST_PROFILE.id,
        name: str = DATA_ANALYST_PROFILE.name,
        description: str = DATA_ANALYST_PROFILE.description,
        capabilities: list[str] | None = None,
        status: AgentStatus = DATA_ANALYST_PROFILE.status,
        provider: AgentProvider | None = None,
    ) -> None:
        super().__init__(
            id=id,
            name=name,
            description=description,
            capabilities=capabilities or list(DATA_ANALYST_PROFILE.capabilities),
            status=status,
            provider=provider,
        )
