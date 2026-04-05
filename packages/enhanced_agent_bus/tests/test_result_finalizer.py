"""Direct tests for ResultFinalizer."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.models import AgentMessage, AutonomyTier, MessageType, Priority
from enhanced_agent_bus.result_finalizer import ResultFinalizer
from enhanced_agent_bus.validators import ValidationResult


@pytest.fixture
def sample_message() -> AgentMessage:
    return AgentMessage(
        message_id="test-msg-123",
        content="test content",
        from_agent="test-agent",
        to_agent="target-agent",
        message_type=MessageType.COMMAND,
        autonomy_tier=AutonomyTier.BOUNDED,
        tenant_id="test-tenant",
        metadata={"test": "value"},
    )


class TestResultFinalizerPersistenceAndDlq:
    @pytest.mark.asyncio
    async def test_persist_flywheel_decision_event_writes_to_repository(
        self,
        sample_message: AgentMessage,
    ) -> None:
        finalizer = ResultFinalizer()
        repository = AsyncMock()
        result = ValidationResult(is_valid=False, errors=["blocked"], metadata={"latency_ms": 7.5})

        await finalizer.persist_flywheel_decision_event(
            msg=sample_message,
            result=result,
            workflow_repository=repository,
        )

        repository.save_decision_event.assert_awaited_once()
        persisted_event = repository.save_decision_event.await_args.args[0]
        assert persisted_event.decision_id == sample_message.message_id
        assert persisted_event.outcome == "deny"

    @pytest.mark.asyncio
    async def test_send_to_dlq_serializes_entry_to_redis(
        self,
        sample_message: AgentMessage,
    ) -> None:
        finalizer = ResultFinalizer()
        redis_client = AsyncMock()
        result = ValidationResult(is_valid=False, errors=["blocked"], metadata={})

        async def get_dlq_redis() -> object:
            return redis_client

        await finalizer.send_to_dlq(
            msg=sample_message,
            result=result,
            get_dlq_redis=get_dlq_redis,
        )

        redis_client.lpush.assert_awaited_once()
        queue_name, payload = redis_client.lpush.await_args.args
        assert queue_name == "acgs:dlq:messages"
        decoded = json.loads(payload)
        assert decoded["message_id"] == sample_message.message_id
        assert decoded["errors"] == ["blocked"]
        redis_client.ltrim.assert_awaited_once_with("acgs:dlq:messages", 0, 9999)


class TestResultFinalizerFailureHandling:
    @pytest.mark.asyncio
    async def test_handle_failed_processing_sets_stage_and_schedules_dlq(
        self,
        sample_message: AgentMessage,
    ) -> None:
        finalizer = ResultFinalizer()
        result = ValidationResult(is_valid=False, errors=["blocked"], metadata={})
        failed_counter_increment = MagicMock()
        schedule_governance_audit_event = MagicMock()
        persist_flywheel_decision_event = AsyncMock()
        record_agent_workflow_event = MagicMock()
        send_to_dlq = AsyncMock()
        scheduled_background_tasks: list[object] = []

        def schedule_background_task_fn(coroutine: object, background_tasks: set[object]) -> object:
            scheduled_background_tasks.append(coroutine)
            return coroutine

        await finalizer.handle_failed_processing(
            msg=sample_message,
            result=result,
            increment_failed_count=True,
            failed_counter_increment=failed_counter_increment,
            failure_stage="gate",
            extract_rejection_reason=lambda _result: "validation_failed",
            schedule_governance_audit_event=schedule_governance_audit_event,
            persist_flywheel_decision_event=persist_flywheel_decision_event,
            record_agent_workflow_event=record_agent_workflow_event,
            send_to_dlq=send_to_dlq,
            schedule_background_task_fn=schedule_background_task_fn,
            background_tasks=set(),
        )

        assert result.metadata["rejection_stage"] == "gate"
        failed_counter_increment.assert_called_once_with()
        schedule_governance_audit_event.assert_called_once_with(sample_message, result)
        persist_flywheel_decision_event.assert_awaited_once_with(sample_message, result)
        record_agent_workflow_event.assert_called_once_with(
            event_type="gate_failure",
            msg=sample_message,
            reason="validation_failed",
        )
        assert len(scheduled_background_tasks) == 1
        await scheduled_background_tasks[0]
        send_to_dlq.assert_awaited_once_with(sample_message, result)

    @pytest.mark.asyncio
    async def test_handle_failed_processing_records_rollback_for_critical_messages(
        self,
        sample_message: AgentMessage,
    ) -> None:
        finalizer = ResultFinalizer()
        sample_message.priority = Priority.CRITICAL
        result = ValidationResult(is_valid=False, errors=["blocked"], metadata={})
        record_agent_workflow_event = MagicMock()

        await finalizer.handle_failed_processing(
            msg=sample_message,
            result=result,
            increment_failed_count=False,
            failed_counter_increment=MagicMock(),
            failure_stage="gate",
            extract_rejection_reason=lambda _result: "validation_failed",
            schedule_governance_audit_event=MagicMock(),
            persist_flywheel_decision_event=AsyncMock(),
            record_agent_workflow_event=record_agent_workflow_event,
            send_to_dlq=AsyncMock(),
            schedule_background_task_fn=lambda coroutine, _background_tasks: coroutine,
            background_tasks=set(),
        )

        assert record_agent_workflow_event.call_args_list[0].kwargs == {
            "event_type": "gate_failure",
            "msg": sample_message,
            "reason": "validation_failed",
        }
        assert record_agent_workflow_event.call_args_list[1].kwargs == {
            "event_type": "rollback_trigger",
            "msg": sample_message,
            "reason": "critical_message_rejected",
        }
