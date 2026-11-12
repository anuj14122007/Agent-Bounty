"""Tests for persistent AgentCommunicationService."""

from __future__ import annotations

from sqlalchemy.orm import Session

from agentbounty.domain.enums import SenderType
from agentbounty.persistence.repositories import TaskRepository
from agentbounty.services.agent_communication import AgentCommunicationService


def _create_db_task(session: Session, task_id: str = "task-comm-1") -> str:
    repo = TaskRepository(session)
    t = repo.create(
        title="Communication Test Task",
        description="Testing persistent message flow.",
        acceptance_criteria=["min_words:5"],
        created_by="tester",
    )
    return t.id


class TestAgentCommunicationService:
    """Tests covering message persistence, ordering, and sanitization."""

    def test_record_and_retrieve_messages_chronologically(self, session: Session) -> None:
        task_id = _create_db_task(session)
        service = AgentCommunicationService(session)

        m1 = service.notify_task_received(task_id, created_by="alice", title="Sample")
        m2 = service.notify_work_started(task_id, worker_id="worker-01")
        m3 = service.notify_result_submitted(task_id, worker_id="worker-01", submission_version=1, content_preview="Done")

        messages = service.list_task_messages(task_id)
        assert len(messages) == 3
        assert messages[0].id == m1.id
        assert messages[0].message_type == "TASK_RECEIVED"
        assert messages[1].id == m2.id
        assert messages[1].message_type == "WORK_STARTED"
        assert messages[2].id == m3.id
        assert messages[2].message_type == "RESULT_SUBMITTED"

    def test_sender_and_recipient_preserved(self, session: Session) -> None:
        task_id = _create_db_task(session)
        service = AgentCommunicationService(session)

        msg = service.record_message(
            task_id=task_id,
            sender_type=SenderType.MANAGER,
            message_type="TASK_DELEGATED",
            content="Delegating work to you.",
            sender_id="manager-001",
            recipient_id="worker-002",
            metadata={"priority": "high"},
        )
        assert msg.sender_id == "manager-001"
        assert msg.recipient_id == "worker-002"
        assert msg.sender_type == SenderType.MANAGER
        assert msg.message_metadata["priority"] == "high"

    def test_secrets_masked_in_metadata(self, session: Session) -> None:
        task_id = _create_db_task(session)
        service = AgentCommunicationService(session)

        msg = service.record_message(
            task_id=task_id,
            sender_type=SenderType.SYSTEM,
            message_type="CONFIG",
            content="System configuration info.",
            metadata={
                "safe_param": "visible",
                "api_secret": "super_secret_12345",
                "auth_token": "token_abc_xyz",
            },
        )
        assert msg.message_metadata["safe_param"] == "visible"
        assert msg.message_metadata["api_secret"] == "***"
        assert msg.message_metadata["auth_token"] == "***"

    def test_notification_helpers(self, session: Session) -> None:
        task_id = _create_db_task(session)
        service = AgentCommunicationService(session)

        m_analysis = service.notify_task_analysis(task_id, "mgr", ["cap1"], "Notes")
        assert m_analysis.message_type == "TASK_ANALYSIS"

        m_worker = service.notify_worker_selected(task_id, "mgr", "wrk", "Chosen because best")
        assert m_worker.message_type == "WORKER_SELECTED"

        m_verif = service.notify_verification_completed(task_id, "wrk_res", "PASSED", 100, "All criteria satisfied")
        assert m_verif.message_type == "VERIFICATION_COMPLETED"

        m_err = service.notify_error(task_id, SenderType.SYSTEM, "orchestrator", "Unexpected timeout")
        assert m_err.message_type == "ERROR"
