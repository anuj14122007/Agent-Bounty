"""Persistent agent-to-agent and system communication service."""

from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session

from agentbounty.domain.enums import SenderType
from agentbounty.domain.schemas import AgentMessageRead
from agentbounty.persistence.repositories import AgentMessageRepository


class AgentCommunicationService:
    """Service managing persistent communication between marketplace actors.

    All messages are persisted to the database in chronological order.
    Never persists raw secrets or unmasked credentials.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AgentMessageRepository(session)

    def record_message(
        self,
        task_id: str,
        sender_type: SenderType,
        message_type: str,
        content: str,
        sender_id: str | None = None,
        recipient_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessageRead:
        """Create and persist an AgentMessage record."""
        # Sanitize metadata to prevent accidental credential leakage
        safe_meta = dict(metadata or {})
        for key in list(safe_meta.keys()):
            if "secret" in key.lower() or "password" in key.lower() or "token" in key.lower():
                safe_meta[key] = "***"

        msg = self.repository.create(
            task_id=task_id,
            sender_type=sender_type,
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_type=message_type,
            content=content.strip(),
            metadata=safe_meta,
        )
        return AgentMessageRead.model_validate(msg)

    def list_task_messages(
        self,
        task_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentMessageRead]:
        """Retrieve chronological message history for a task."""
        messages = self.repository.list_by_task(task_id, limit=limit, offset=offset)
        return [AgentMessageRead.model_validate(m) for m in messages]

    # --- Structured Notification Helpers ---

    def notify_task_received(self, task_id: str, created_by: str, title: str) -> AgentMessageRead:
        return self.record_message(
            task_id=task_id,
            sender_type=SenderType.USER,
            sender_id=created_by,
            message_type="TASK_RECEIVED",
            content=f"Task '{title}' has been submitted and registered in marketplace.",
            metadata={"title": title, "created_by": created_by},
        )

    def notify_task_analysis(
        self,
        task_id: str,
        manager_id: str,
        required_capabilities: list[str],
        analysis_notes: str,
    ) -> AgentMessageRead:
        return self.record_message(
            task_id=task_id,
            sender_type=SenderType.MANAGER,
            sender_id=manager_id,
            message_type="TASK_ANALYSIS",
            content=analysis_notes,
            metadata={"required_capabilities": required_capabilities},
        )

    def notify_worker_selected(
        self,
        task_id: str,
        manager_id: str,
        worker_id: str,
        explanation: str,
    ) -> AgentMessageRead:
        return self.record_message(
            task_id=task_id,
            sender_type=SenderType.MANAGER,
            sender_id=manager_id,
            recipient_id=worker_id,
            message_type="WORKER_SELECTED",
            content=explanation,
            metadata={"selected_worker_id": worker_id},
        )

    def notify_task_delegated(
        self,
        task_id: str,
        manager_id: str,
        worker_id: str,
        bounty_amount_str: str,
    ) -> AgentMessageRead:
        return self.record_message(
            task_id=task_id,
            sender_type=SenderType.MANAGER,
            sender_id=manager_id,
            recipient_id=worker_id,
            message_type="TASK_DELEGATED",
            content=f"Delegated task '{task_id}' to worker '{worker_id}' with bounty {bounty_amount_str}.",
            metadata={"bounty": bounty_amount_str, "worker_id": worker_id},
        )

    def notify_work_started(self, task_id: str, worker_id: str) -> AgentMessageRead:
        return self.record_message(
            task_id=task_id,
            sender_type=SenderType.WORKER,
            sender_id=worker_id,
            message_type="WORK_STARTED",
            content=f"Worker '{worker_id}' has commenced task execution.",
            metadata={"worker_id": worker_id},
        )

    def notify_result_submitted(
        self,
        task_id: str,
        worker_id: str,
        submission_version: int,
        content_preview: str,
    ) -> AgentMessageRead:
        preview = (content_preview[:200] + "...") if len(content_preview) > 200 else content_preview
        return self.record_message(
            task_id=task_id,
            sender_type=SenderType.WORKER,
            sender_id=worker_id,
            message_type="RESULT_SUBMITTED",
            content=f"Worker '{worker_id}' submitted deliverable version {submission_version}: {preview}",
            metadata={"submission_version": submission_version},
        )

    def notify_verification_started(
        self,
        task_id: str,
        worker_result_id: str,
        criteria_count: int,
    ) -> AgentMessageRead:
        return self.record_message(
            task_id=task_id,
            sender_type=SenderType.SYSTEM,
            sender_id="verification_engine",
            message_type="VERIFICATION_STARTED",
            content=f"Independent verification started for worker result '{worker_result_id}' ({criteria_count} criteria).",
            metadata={"worker_result_id": worker_result_id, "criteria_count": criteria_count},
        )

    def notify_verification_completed(
        self,
        task_id: str,
        worker_result_id: str,
        status: str,
        score: int | None,
        explanation: str,
    ) -> AgentMessageRead:
        return self.record_message(
            task_id=task_id,
            sender_type=SenderType.SYSTEM,
            sender_id="verification_engine",
            message_type="VERIFICATION_COMPLETED",
            content=f"Verification completed: status={status}, score={score}. {explanation}",
            metadata={"worker_result_id": worker_result_id, "status": status, "score": score},
        )

    def notify_error(
        self,
        task_id: str,
        sender_type: SenderType,
        sender_id: str | None,
        error_message: str,
    ) -> AgentMessageRead:
        return self.record_message(
            task_id=task_id,
            sender_type=sender_type,
            sender_id=sender_id,
            message_type="ERROR",
            content=f"Workflow error: {error_message}",
            metadata={"error": error_message},
        )
