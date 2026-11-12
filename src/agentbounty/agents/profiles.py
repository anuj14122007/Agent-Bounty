"""Deterministic profiles and default registrations for AgentBounty agents."""

from __future__ import annotations

import uuid
from typing import NamedTuple

from agentbounty.domain.enums import AgentRole, AgentStatus

# Dedicated UUID namespace for deterministic Agent IDs across restarts
_AGENT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "agentbounty.local")

MANAGER_AGENT_ID = str(uuid.uuid5(_AGENT_NAMESPACE, "manager"))
CREATIVE_WRITER_ID = str(uuid.uuid5(_AGENT_NAMESPACE, "creative_writer"))
RESEARCHER_ID = str(uuid.uuid5(_AGENT_NAMESPACE, "research_assistant"))
DATA_ANALYST_ID = str(uuid.uuid5(_AGENT_NAMESPACE, "data_analyst"))
CODE_ASSISTANT_ID = str(uuid.uuid5(_AGENT_NAMESPACE, "code_assistant"))


class AgentProfile(NamedTuple):
    """Immutable specification for default agent registration."""

    id: str
    name: str
    role: AgentRole
    description: str
    capabilities: list[str]
    status: AgentStatus = AgentStatus.ACTIVE


MANAGER_PROFILE = AgentProfile(
    id=MANAGER_AGENT_ID,
    name="Marketplace Manager",
    role=AgentRole.MANAGER,
    description="Central coordination agent responsible for task analysis, capability matching, and safe bounty delegation.",
    capabilities=[
        "task-decomposition",
        "worker-selection",
        "bounty-allocation",
        "workflow-orchestration",
    ],
    status=AgentStatus.ACTIVE,
)

CREATIVE_WRITER_PROFILE = AgentProfile(
    id=CREATIVE_WRITER_ID,
    name="Creative Writer",
    role=AgentRole.WORKER,
    description="Specialist in copywriting, product introductions, summarization, structured narratives, and editorial formatting.",
    capabilities=[
        "creative-writing",
        "content-generation",
        "summarization",
        "formatting",
        "editing",
        "copywriting",
    ],
    status=AgentStatus.ACTIVE,
)

RESEARCHER_PROFILE = AgentProfile(
    id=RESEARCHER_ID,
    name="Research Assistant",
    role=AgentRole.WORKER,
    description="Specialist in organizing research questions, producing structured briefs, fact organization, and evidence synthesis.",
    capabilities=[
        "research-briefs",
        "information-synthesis",
        "fact-organization",
        "evidence-analysis",
        "source-preservation",
    ],
    status=AgentStatus.ACTIVE,
)

DATA_ANALYST_PROFILE = AgentProfile(
    id=DATA_ANALYST_ID,
    name="Data Analyst",
    role=AgentRole.WORKER,
    description="Specialist in data interpretation, tabular summaries, statistical calculations, and quantitative reporting.",
    capabilities=[
        "data-analysis",
        "statistical-calculation",
        "tabular-summary",
        "structured-reporting",
        "numerical-computation",
    ],
    status=AgentStatus.ACTIVE,
)

CODE_ASSISTANT_PROFILE = AgentProfile(
    id=CODE_ASSISTANT_ID,
    name="Code Assistant",
    role=AgentRole.WORKER,
    description="Specialist in code drafting, algorithmic design, debugging suggestions, and technical architecture documentation.",
    capabilities=[
        "code-drafting",
        "code-explanation",
        "debugging-suggestions",
        "algorithm-design",
        "technical-documentation",
    ],
    status=AgentStatus.ACTIVE,
)

DEFAULT_WORKER_PROFILES: list[AgentProfile] = [
    CREATIVE_WRITER_PROFILE,
    RESEARCHER_PROFILE,
    DATA_ANALYST_PROFILE,
    CODE_ASSISTANT_PROFILE,
]
