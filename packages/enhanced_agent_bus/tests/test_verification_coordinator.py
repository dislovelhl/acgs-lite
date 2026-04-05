"""Direct tests for VerificationCoordinator."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.models import AgentMessage, AutonomyTier, MessageType
from enhanced_agent_bus.processing_context import MessageProcessingContext
from enhanced_agent_bus.validators import ValidationResult
from enhanced_agent_bus.verification_coordinator import VerificationCoordinator


@pytest.fixture
def sample_message() -> AgentMessage:
    return AgentMessage(
        content="test content",
        from_agent="test-agent",
        to_agent="target-agent",
        message_type=MessageType.COMMAND,
        autonomy_tier=AutonomyTier.BOUNDED,
        tenant_id="test-tenant",
        metadata={"test": "value"},
    )


def _coordinator(
    *,
    verification_orchestrator: object,
    processing_strategy: object,
    attach_governance_metadata: object | None = None,
    increment_failed_count: object | None = None,
    handle_successful_processing: object | None = None,
    handle_failed_processing: object | None = None,
) -> VerificationCoordinator:
    return VerificationCoordinator(
        verification_orchestrator=verification_orchestrator,
        processing_strategy=processing_strategy,
        handlers={},
        attach_governance_metadata=attach_governance_metadata or MagicMock(),
        increment_failed_count=increment_failed_count or MagicMock(),
        handle_successful_processing=handle_successful_processing or AsyncMock(),
        handle_failed_processing=handle_failed_processing or AsyncMock(),
    )


class TestVerificationCoordinatorExecute:
    @pytest.mark.asyncio
    async def test_execute_passes_normalized_content_to_verification_orchestrator(
        self,
        sample_message: AgentMessage,
    ) -> None:
        sample_message.content = {"nested": [1, 2, 3]}
        verification_result = SimpleNamespace(sdpc_metadata={}, pqc_metadata={}, pqc_result=None)
        verification_orchestrator = SimpleNamespace(
            verify=AsyncMock(return_value=verification_result)
        )
        processing_strategy = SimpleNamespace(
            process=AsyncMock(return_value=ValidationResult(is_valid=True, metadata={}))
        )
        coordinator = _coordinator(
            verification_orchestrator=verification_orchestrator,
            processing_strategy=processing_strategy,
        )

        await coordinator.execute(
            MessageProcessingContext(message=sample_message, start_time=0.0, cache_key="cache-key")
        )

        verification_orchestrator.verify.assert_awaited_once_with(
            sample_message,
            str({"nested": [1, 2, 3]}),
        )

    @pytest.mark.asyncio
    async def test_execute_applies_merged_metadata_and_latency(
        self,
        sample_message: AgentMessage,
    ) -> None:
        verification_result = SimpleNamespace(
            sdpc_metadata={"sdpc": "ok", "shared": "sdpc"},
            pqc_metadata={"pqc": "ok", "shared": "pqc"},
            pqc_result=None,
        )
        process_result = ValidationResult(is_valid=True, metadata={})
        verification_orchestrator = SimpleNamespace(
            verify=AsyncMock(return_value=verification_result)
        )
        handle_successful_processing = AsyncMock()
        coordinator = _coordinator(
            verification_orchestrator=verification_orchestrator,
            processing_strategy=SimpleNamespace(process=AsyncMock(return_value=process_result)),
            handle_successful_processing=handle_successful_processing,
        )

        result = await coordinator.execute(
            MessageProcessingContext(message=sample_message, start_time=0.0, cache_key="cache-key")
        )

        assert result.metadata["sdpc"] == "ok"
        assert result.metadata["pqc"] == "ok"
        assert result.metadata["shared"] == "pqc"
        assert isinstance(result.metadata["latency_ms"], float)
        handle_successful_processing.assert_awaited_once()
        assert handle_successful_processing.await_args.args[3] == result.metadata["latency_ms"]

    @pytest.mark.asyncio
    async def test_execute_returns_pqc_failure_and_skips_strategy(
        self,
        sample_message: AgentMessage,
    ) -> None:
        pqc_failure = ValidationResult(is_valid=False, errors=["pqc failed"], metadata={})
        verification_result = SimpleNamespace(
            sdpc_metadata={"sdpc": "ok"},
            pqc_metadata={"pqc": "meta"},
            pqc_result=pqc_failure,
        )
        processing_strategy = SimpleNamespace(process=AsyncMock())
        increment_failed_count = MagicMock()
        handle_failed_processing = AsyncMock()
        coordinator = _coordinator(
            verification_orchestrator=SimpleNamespace(
                verify=AsyncMock(return_value=verification_result)
            ),
            processing_strategy=processing_strategy,
            increment_failed_count=increment_failed_count,
            handle_failed_processing=handle_failed_processing,
        )

        result = await coordinator.execute(
            MessageProcessingContext(message=sample_message, start_time=0.0, cache_key="cache-key")
        )

        assert result is pqc_failure
        processing_strategy.process.assert_not_awaited()
        increment_failed_count.assert_called_once_with()
        handle_failed_processing.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_routes_strategy_failure_to_failure_handler(
        self,
        sample_message: AgentMessage,
    ) -> None:
        verification_result = SimpleNamespace(sdpc_metadata={}, pqc_metadata={}, pqc_result=None)
        strategy_result = ValidationResult(
            is_valid=False,
            errors=["strategy rejected"],
            metadata={"rejection_reason": "strategy_failed"},
        )
        handle_failed_processing = AsyncMock()
        coordinator = _coordinator(
            verification_orchestrator=SimpleNamespace(
                verify=AsyncMock(return_value=verification_result)
            ),
            processing_strategy=SimpleNamespace(process=AsyncMock(return_value=strategy_result)),
            handle_failed_processing=handle_failed_processing,
        )

        result = await coordinator.execute(
            MessageProcessingContext(message=sample_message, start_time=0.0, cache_key="cache-key")
        )

        assert result is strategy_result
        handle_failed_processing.assert_awaited_once_with(
            sample_message,
            strategy_result,
            failure_stage="strategy",
        )
