"""Research Assistant specialist worker implementation."""

from __future__ import annotations

from agentbounty.agents.profiles import RESEARCHER_PROFILE
from agentbounty.agents.workers.base import BaseWorker
from agentbounty.domain.enums import AgentStatus
from agentbounty.providers.protocols import AgentProvider


class ResearchAssistantWorker(BaseWorker):
    """Specialist worker focused on research briefs, information synthesis, and evidence analysis.

    In DEMO mode, does not pretend to search live external web or read proprietary literature.
    """

    def __init__(
        self,
        id: str = RESEARCHER_PROFILE.id,
        name: str = RESEARCHER_PROFILE.name,
        description: str = RESEARCHER_PROFILE.description,
        capabilities: list[str] | None = None,
        status: AgentStatus = RESEARCHER_PROFILE.status,
        provider: AgentProvider | None = None,
    ) -> None:
        super().__init__(
            id=id,
            name=name,
            description=description,
            capabilities=capabilities or list(RESEARCHER_PROFILE.capabilities),
            status=status,
            provider=provider,
        )
