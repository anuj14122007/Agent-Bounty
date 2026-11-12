"""Creative Writer specialist worker implementation."""

from __future__ import annotations

from agentbounty.agents.profiles import CREATIVE_WRITER_PROFILE
from agentbounty.agents.workers.base import BaseWorker
from agentbounty.domain.enums import AgentStatus
from agentbounty.providers.protocols import AgentProvider


class CreativeWriterWorker(BaseWorker):
    """Specialist worker focused on high quality writing, editing, and content formatting."""

    def __init__(
        self,
        id: str = CREATIVE_WRITER_PROFILE.id,
        name: str = CREATIVE_WRITER_PROFILE.name,
        description: str = CREATIVE_WRITER_PROFILE.description,
        capabilities: list[str] | None = None,
        status: AgentStatus = CREATIVE_WRITER_PROFILE.status,
        provider: AgentProvider | None = None,
    ) -> None:
        super().__init__(
            id=id,
            name=name,
            description=description,
            capabilities=capabilities or list(CREATIVE_WRITER_PROFILE.capabilities),
            status=status,
            provider=provider,
        )
