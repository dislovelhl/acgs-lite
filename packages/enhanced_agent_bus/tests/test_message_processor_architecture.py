"""Architecture hardening regressions for MessageProcessor."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.message_processor import MessageProcessor
from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage, AutonomyTier, MessageType
from enhanced_agent_bus.validators import ValidationResult


async def _drain_background_tasks(processor: MessageProcessor) -> None:
    if processor._background_tasks:
        await asyncio.gather(*processor._background_tasks, return_exceptions=True)


def _message(
    *,
    content: str = "safe collaborative planning update",
    metadata: dict[str, object] | None = None,
    impact_score: float | None = None,
    message_type: MessageType = MessageType.COMMAND,
) -> AgentMessage:
    return AgentMessage(
        content=content,
        from_agent="agent-producer",
        to_agent="agent-receiver",
        metadata=metadata or {},
        impact_score=impact_score,
        constitutional_hash=CONSTITUTIONAL_HASH,
        message_type=message_type,
        autonomy_tier=AutonomyTier.BOUNDED,
    )


@pytest.mark.asyncio
async def test_process_keeps_governance_artifacts_off_message_object() -> None:
    strategy = MagicMock()
    strategy.process = AsyncMock(return_value=ValidationResult(is_valid=True, metadata={}))
    strategy.get_name = MagicMock(return_value="mock_strategy")

    processor = MessageProcessor(isolated_mode=True, processing_strategy=strategy)

    msg = _message()
    result = await processor.process(msg)

    assert result.is_valid is True
    assert isinstance(result.metadata["governance_decision"], dict)
    assert isinstance(result.metadata["governance_receipt"], dict)
    assert not hasattr(msg, "_governance_decision")
    assert not hasattr(msg, "_governance_receipt")
    assert not hasattr(msg, "_governance_shadow_metadata")


@pytest.mark.asyncio
async def test_gate_failure_uses_common_failure_sinks_and_audit() -> None:
    audit_client = AsyncMock()
    processor = MessageProcessor(
        isolated_mode=True,
        audit_client=audit_client,
        require_independent_validator=True,
        independent_validator_threshold=0.8,
    )
    processor._result_finalizer.persist_flywheel_decision_event = AsyncMock()
    processor._result_finalizer.send_to_dlq = AsyncMock()

    result = await processor.process(_message(impact_score=0.95))
    await _drain_background_tasks(processor)

    assert result.is_valid is False
    assert result.metadata["rejection_reason"] == "independent_validator_missing"
    assert result.metadata["rejection_stage"] == "gate"
    processor._result_finalizer.persist_flywheel_decision_event.assert_awaited_once()
    processor._result_finalizer.send_to_dlq.assert_awaited_once()
    audit_client.log_event.assert_awaited_once()
    details = audit_client.log_event.call_args.kwargs["details"]
    assert details["result_valid"] is False
    assert details["rejection_stage"] == "gate"
    assert details["governance_decision"] is None
    assert details["governance_receipt"] is None


@pytest.mark.asyncio
async def test_main_pipeline_bypasses_legacy_session_and_verification_wrappers() -> None:
    processor = MessageProcessor(isolated_mode=True)
    msg = _message()
    expected_result = ValidationResult(is_valid=True, metadata={})

    processor._attach_session_context = AsyncMock(
        side_effect=AssertionError("legacy session wrapper should not be used")
    )
    processor._session_coordinator.attach_session_context = AsyncMock()
    processor._gate_coordinator.run = AsyncMock(return_value=None)
    processor._verification_coordinator.execute = AsyncMock(return_value=expected_result)

    result = await processor._do_process(msg)

    assert result is expected_result
    processor._session_coordinator.attach_session_context.assert_awaited_once()
    processor._gate_coordinator.run.assert_awaited_once()
    processor._verification_coordinator.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_pipeline_bypasses_legacy_success_sink_wrappers() -> None:
    strategy = MagicMock()
    strategy.process = AsyncMock(return_value=ValidationResult(is_valid=True, metadata={}))
    strategy.get_name = MagicMock(return_value="mock_strategy")
    processor = MessageProcessor(isolated_mode=True, processing_strategy=strategy)

    processor._requires_independent_validation = MagicMock(
        side_effect=AssertionError("legacy validation wrapper should not be used")
    )
    processor._result_finalizer.persist_flywheel_decision_event = AsyncMock()

    result = await processor.process(_message())
    await _drain_background_tasks(processor)

    assert result.is_valid is True
    processor._result_finalizer.persist_flywheel_decision_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_pqc_failure_uses_common_failure_sinks_without_strategy_execution() -> None:
    strategy = MagicMock()
    strategy.process = AsyncMock(return_value=ValidationResult(is_valid=True, metadata={}))
    strategy.get_name = MagicMock(return_value="mock_strategy")
    verification_orchestrator = SimpleNamespace(
        verify=AsyncMock(
            return_value=SimpleNamespace(
                sdpc_metadata={},
                pqc_metadata={},
                pqc_result=ValidationResult(
                    is_valid=False,
                    errors=["PQC rejected message"],
                    metadata={"rejection_reason": "pqc_failed"},
                ),
            )
        )
    )

    processor = MessageProcessor(
        isolated_mode=True,
        processing_strategy=strategy,
        verification_orchestrator=verification_orchestrator,
    )
    processor._result_finalizer.persist_flywheel_decision_event = AsyncMock()
    processor._result_finalizer.send_to_dlq = AsyncMock()

    result = await processor.process(_message())
    await _drain_background_tasks(processor)

    assert result.is_valid is False
    assert result.metadata["rejection_reason"] == "pqc_failed"
    assert result.metadata["rejection_stage"] == "verification"
    strategy.process.assert_not_called()
    processor._result_finalizer.persist_flywheel_decision_event.assert_awaited_once()
    processor._result_finalizer.send_to_dlq.assert_awaited_once()


@pytest.mark.asyncio
async def test_main_pipeline_bypasses_legacy_failure_sink_wrappers() -> None:
    processor = MessageProcessor(
        isolated_mode=True,
        require_independent_validator=True,
        independent_validator_threshold=0.8,
    )
    processor._send_to_dlq = AsyncMock(
        side_effect=AssertionError("legacy DLQ wrapper should not be used")
    )
    processor._result_finalizer.persist_flywheel_decision_event = AsyncMock()
    processor._result_finalizer.send_to_dlq = AsyncMock()

    result = await processor.process(_message(impact_score=0.95))
    await _drain_background_tasks(processor)

    assert result.is_valid is False
    assert result.metadata["rejection_reason"] == "independent_validator_missing"
    processor._result_finalizer.persist_flywheel_decision_event.assert_awaited_once()
    processor._result_finalizer.send_to_dlq.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_isolated_by_session_context() -> None:
    strategy = MagicMock()

    async def _process(msg: AgentMessage, _handlers: dict[str, object]) -> ValidationResult:
        session_id = getattr(getattr(msg, "session_context", None), "session_id", "missing")
        return ValidationResult(is_valid=True, metadata={"session_seen": session_id})

    strategy.process = AsyncMock(side_effect=_process)
    strategy.get_name = MagicMock(return_value="mock_strategy")

    verification_orchestrator = SimpleNamespace(
        verify=AsyncMock(
            return_value=SimpleNamespace(sdpc_metadata={}, pqc_metadata={}, pqc_result=None)
        )
    )

    processor = MessageProcessor(
        isolated_mode=True,
        processing_strategy=strategy,
        verification_orchestrator=verification_orchestrator,
    )

    async def _attach(context: object) -> None:
        msg = context.message
        session_context = SimpleNamespace(session_id=msg.session_id)
        context.session_context = session_context
        msg.session_context = session_context

    processor._session_coordinator.attach_session_context = AsyncMock(side_effect=_attach)
    processor._gate_coordinator.run = AsyncMock(return_value=None)

    first_msg = _message()
    first_msg.session_id = "session-a"
    first = await processor.process(first_msg)
    await _drain_background_tasks(processor)

    second_msg = _message()
    second_msg.session_id = "session-b"
    second = await processor.process(second_msg)
    await _drain_background_tasks(processor)

    assert strategy.process.await_count == 2
    assert first.metadata["session_seen"] == "session-a"
    assert second.metadata["session_seen"] == "session-b"


@pytest.mark.asyncio
async def test_shutdown_cancels_background_tasks() -> None:
    processor = MessageProcessor(isolated_mode=True)
    started = asyncio.Event()

    async def _pending_task() -> None:
        started.set()
        await asyncio.sleep(100)

    task = asyncio.create_task(_pending_task())
    processor._background_tasks.add(task)
    task.add_done_callback(processor._background_tasks.discard)
    await started.wait()

    await processor.shutdown()

    assert task.done() is True
    assert len(processor._background_tasks) == 0
