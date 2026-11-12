"""Protocols and interfaces for agent generation providers."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AgentProvider(Protocol):
    """Protocol for model/agent text and deliverable generation providers."""

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Generate response text for an arbitrary prompt.

        Args:
            prompt: User or instruction prompt.
            system_prompt: Optional system-level instructions or role persona.
            context: Optional contextual parameters.

        Returns:
            Generated text content.
        """
        ...

    def generate_worker_deliverable(
        self,
        worker_name: str,
        task_title: str,
        task_description: str,
        acceptance_criteria: list[str],
        context: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Generate structured deliverable text and artifact metadata for a specialist worker.

        Args:
            worker_name: Name or role identifier of the worker executing the task.
            task_title: Title of the task.
            task_description: Detailed task description.
            acceptance_criteria: Measurable acceptance criteria strings.
            context: Optional contextual variables (e.g. raw data, sources).

        Returns:
            Tuple of (deliverable_content_str, artifact_metadata_dict).
        """
        ...
