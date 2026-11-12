"""Specialist workers for the AgentBounty marketplace."""

from agentbounty.agents.workers.base import BaseWorker
from agentbounty.agents.workers.code_assistant import CodeAssistantWorker
from agentbounty.agents.workers.creative_writer import CreativeWriterWorker
from agentbounty.agents.workers.data_analyst import DataAnalystWorker
from agentbounty.agents.workers.researcher import ResearchAssistantWorker

__all__ = [
    "BaseWorker",
    "CodeAssistantWorker",
    "CreativeWriterWorker",
    "DataAnalystWorker",
    "ResearchAssistantWorker",
]
