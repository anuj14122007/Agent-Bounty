"""Code Assistant specialist worker implementation."""

from __future__ import annotations

from agentbounty.agents.profiles import CODE_ASSISTANT_PROFILE
from agentbounty.agents.workers.base import BaseWorker
from agentbounty.domain.enums import AgentStatus
from agentbounty.providers.protocols import AgentProvider


class CodeAssistantWorker(BaseWorker):
    """Specialist worker focused on code drafting, explanation, debugging suggestions, and technical documentation.

    SECURITY INVARIANT:
    Generates text deliverables only. Never executes arbitrary shell commands, subprocesses,
    Python evaluations, or filesystem mutations.
    """

    def __init__(
        self,
        id: str = CODE_ASSISTANT_PROFILE.id,
        name: str = CODE_ASSISTANT_PROFILE.name,
        description: str = CODE_ASSISTANT_PROFILE.description,
        capabilities: list[str] | None = None,
        status: AgentStatus = CODE_ASSISTANT_PROFILE.status,
        provider: AgentProvider | None = None,
    ) -> None:
        super().__init__(
            id=id,
            name=name,
            description=description,
            capabilities=capabilities or list(CODE_ASSISTANT_PROFILE.capabilities),
            status=status,
            provider=provider,
        )
