"""Agent implementations and registry for the AgentBounty marketplace."""

from agentbounty.agents.base import BaseAgent, WorkerExecutionResult
from agentbounty.agents.manager import ManagerAgent, TaskAnalysis, WorkerMatch
from agentbounty.agents.profiles import (
    CODE_ASSISTANT_PROFILE,
    CREATIVE_WRITER_PROFILE,
    DATA_ANALYST_PROFILE,
    MANAGER_PROFILE,
    RESEARCHER_PROFILE,
)
from agentbounty.agents.registry import AgentRegistry
from agentbounty.agents.workers.base import BaseWorker
from agentbounty.agents.workers.code_assistant import CodeAssistantWorker
from agentbounty.agents.workers.creative_writer import CreativeWriterWorker
from agentbounty.agents.workers.data_analyst import DataAnalystWorker
from agentbounty.agents.workers.researcher import ResearchAssistantWorker

__all__ = [
    "BaseAgent",
    "BaseWorker",
    "CodeAssistantWorker",
    "CreativeWriterWorker",
    "DataAnalystWorker",
    "ManagerAgent",
    "ResearchAssistantWorker",
    "TaskAnalysis",
    "WorkerExecutionResult",
    "WorkerMatch",
    "AgentRegistry",
    "MANAGER_PROFILE",
    "CREATIVE_WRITER_PROFILE",
    "RESEARCHER_PROFILE",
    "DATA_ANALYST_PROFILE",
    "CODE_ASSISTANT_PROFILE",
]
