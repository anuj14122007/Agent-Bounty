"""Common base agent contracts and execution abstractions."""

from __future__ import annotations

from abc import ABC
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from agentbounty.domain.enums import AgentRole, AgentStatus


class WorkerExecutionResult(BaseModel):
    """Structured deliverable produced by a worker execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_agent_id: str
    content: str = Field(..., min_length=1)
    artifact_metadata: dict[str, Any] = Field(default_factory=dict)
    submission_version: int = Field(default=1, ge=1)


class BaseAgent(ABC):
    """Common contract for all AgentBounty agents."""

    def __init__(
        self,
        id: str,
        name: str,
        role: AgentRole,
        description: str,
        capabilities: list[str] | None = None,
        status: AgentStatus = AgentStatus.ACTIVE,
    ) -> None:
        if not id or not id.strip():
            raise ValueError("Agent ID cannot be empty.")
        if not name or not name.strip():
            raise ValueError("Agent name cannot be empty.")

        self.id = id.strip()
        self.name = name.strip()
        self.role = role
        self.description = description.strip()
        self.capabilities = [c.strip().lower() for c in (capabilities or []) if c and c.strip()]
        self.status = status

    def has_capability(self, capability: str) -> bool:
        """Check if agent possesses a specific capability (case-insensitive)."""
        target = capability.strip().lower()
        return target in self.capabilities

    def match_capabilities(self, required_capabilities: list[str]) -> list[str]:
        """Return subset of required capabilities matched by this agent."""
        req = [c.strip().lower() for c in required_capabilities if c and c.strip()]
        return [c for c in req if c in self.capabilities]

    @property
    def is_active(self) -> bool:
        """Return whether agent is active and eligible for task assignment."""
        return self.status == AgentStatus.ACTIVE

    def to_dict(self) -> dict[str, Any]:
        """Serialize agent state to a standard dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role.value,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "status": self.status.value,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id!r}, name={self.name!r}, role={self.role.value!r}, status={self.status.value!r})"
