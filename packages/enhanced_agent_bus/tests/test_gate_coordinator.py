"""Direct tests for GateCoordinator."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.gate_coordinator import GateCoordinator
from enhanced_agent_bus.models import AgentMessage, AutonomyTier, MessageType, Priority
from enhanced_agent_bus.processing_context import MessageProcessingContext
from enhanced_agent_bus.validators import ValidationResult


@pytest.fixture
def sample_message() -> AgentMessage:
    return AgentMessage(
        message_id="test-msg-123",
        from_agent="test-agent",
        to_agent="target-agent",
        message_type=MessageType.COMMAND,
        priority=Priority.MEDIUM,
        autonomy_tier=AutonomyTier.BOUNDED,
        tenant_id="test-tenant",
        content="test content",
        metadata={"test": "value"},
    )


def _make_gate_coordinator(
    *,
    require_independent_validator: bool = True,
    independent_validator_threshold: float = 0.8,
    security_scanner: object | None = None,
    record_agent_workflow_event: object | None = None,
    increment_failed_count: object | None = None,
) -> GateCoordinator:
    return GateCoordinator(
        require_independent_validator=require_independent_validator,
        independent_validator_threshold=independent_validator_threshold,
        security_scanner=security_scanner
        or SimpleNamespace(scan=AsyncMock(), detect_prompt_injection=MagicMock()),
        record_agent_workflow_event=record_agent_workflow_event or MagicMock(),
        increment_failed_count=increment_failed_count or MagicMock(),
        advisory_blocked_types=frozenset({"command", "governance_request", "task_request"}),
    )


class TestRequiresIndependentValidation:
    def test_high_impact_score_requires_validation(self, sample_message: AgentMessage) -> None:
        coordinator = _make_gate_coordinator()
        sample_message.impact_score = 0.9

        assert coordinator.requires_independent_validation(sample_message) is True

    def test_low_impact_score_does_not_require_validation(
        self, sample_message: AgentMessage
    ) -> None:
        coordinator = _make_gate_coordinator()
        sample_message.impact_score = 0.5

        assert coordinator.requires_independent_validation(sample_message) is False

    def test_none_impact_score_does_not_require_validation(
        self, sample_message: AgentMessage
    ) -> None:
        coordinator = _make_gate_coordinator()
        sample_message.impact_score = None

        assert coordinator.requires_independent_validation(sample_message) is False

    def test_constitutional_validation_requires_validation(self) -> None:
        coordinator = _make_gate_coordinator()
        message = AgentMessage(impact_score=0.2, message_type=MessageType.CONSTITUTIONAL_VALIDATION)

        assert coordinator.requires_independent_validation(message) is True

    def test_governance_request_requires_validation(self) -> None:
        coordinator = _make_gate_coordinator()
        message = AgentMessage(impact_score=0.2, message_type=MessageType.GOVERNANCE_REQUEST)

        assert coordinator.requires_independent_validation(message) is True


class TestIndependentValidatorGate:
    def test_gate_disabled_returns_none(self, sample_message: AgentMessage) -> None:
        coordinator = _make_gate_coordinator(require_independent_validator=False)

        assert coordinator.enforce_independent_validator_gate(sample_message) is None

    def test_validation_not_required_returns_none(self, sample_message: AgentMessage) -> None:
        coordinator = _make_gate_coordinator(record_agent_workflow_event=MagicMock())
        sample_message.impact_score = 0.2

        assert coordinator.enforce_independent_validator_gate(sample_message) is None

    def test_missing_validator_returns_error(self, sample_message: AgentMessage) -> None:
        record_event = MagicMock()
        coordinator = _make_gate_coordinator(record_agent_workflow_event=record_event)
        sample_message.impact_score = 0.9
        sample_message.metadata = {}

        result = coordinator.enforce_independent_validator_gate(sample_message)

        assert result is not None
        assert result.is_valid is False
        assert result.metadata["rejection_reason"] == "independent_validator_missing"
        record_event.assert_called()

    def test_self_validation_returns_error(self, sample_message: AgentMessage) -> None:
        coordinator = _make_gate_coordinator(record_agent_workflow_event=MagicMock())
        sample_message.impact_score = 0.9
        sample_message.metadata = {
            "validated_by_agent": sample_message.from_agent,
            "validation_stage": "independent",
        }

        result = coordinator.enforce_independent_validator_gate(sample_message)

        assert result is not None
        assert result.is_valid is False
        assert result.metadata["rejection_reason"] == "independent_validator_self_validation"

    def test_invalid_validation_stage_returns_error(self, sample_message: AgentMessage) -> None:
        coordinator = _make_gate_coordinator(record_agent_workflow_event=MagicMock())
        sample_message.impact_score = 0.9
        sample_message.metadata = {
            "validated_by_agent": "different-agent",
            "validation_stage": "preliminary",
        }

        result = coordinator.enforce_independent_validator_gate(sample_message)

        assert result is not None
        assert result.is_valid is False
        assert result.metadata["rejection_reason"] == "independent_validator_invalid_stage"

    def test_valid_validator_returns_none(self, sample_message: AgentMessage) -> None:
        coordinator = _make_gate_coordinator(record_agent_workflow_event=MagicMock())
        sample_message.impact_score = 0.9
        sample_message.metadata = {
            "validated_by_agent": "different-agent",
            "validation_stage": "independent",
        }

        assert coordinator.enforce_independent_validator_gate(sample_message) is None

    def test_independent_validator_id_is_accepted(self, sample_message: AgentMessage) -> None:
        coordinator = _make_gate_coordinator(record_agent_workflow_event=MagicMock())
        sample_message.impact_score = 0.9
        sample_message.metadata = {"independent_validator_id": "different-agent"}

        assert coordinator.enforce_independent_validator_gate(sample_message) is None


class TestAutonomyAndSecurityHelpers:
    @patch("enhanced_agent_bus.gate_coordinator.enforce_autonomy_tier_rules")
    def test_enforce_autonomy_tier_delegates_to_component_helper(
        self,
        mock_enforce_rules: MagicMock,
        sample_message: AgentMessage,
    ) -> None:
        mock_result = ValidationResult(is_valid=True)
        mock_enforce_rules.return_value = mock_result
        coordinator = _make_gate_coordinator()

        result = coordinator.enforce_autonomy_tier(sample_message)

        mock_enforce_rules.assert_called_once()
        assert result == mock_result

    @pytest.mark.asyncio
    async def test_perform_security_scan_increments_failure_for_blocked_result(
        self,
        sample_message: AgentMessage,
    ) -> None:
        blocked_result = ValidationResult(
            is_valid=False,
            errors=["security blocked"],
            metadata={"rejection_reason": "security_violation"},
        )
        increment_failed_count = MagicMock()
        scanner = SimpleNamespace(
            scan=AsyncMock(return_value=blocked_result), detect_prompt_injection=MagicMock()
        )
        coordinator = _make_gate_coordinator(
            security_scanner=scanner,
            increment_failed_count=increment_failed_count,
        )

        result = await coordinator.perform_security_scan(sample_message)

        assert result == blocked_result
        increment_failed_count.assert_called_once_with()

    def test_detect_prompt_injection_delegates_to_security_scanner(
        self,
        sample_message: AgentMessage,
    ) -> None:
        scanner = SimpleNamespace(
            scan=AsyncMock(), detect_prompt_injection=MagicMock(return_value=None)
        )
        coordinator = _make_gate_coordinator(security_scanner=scanner)

        result = coordinator.detect_prompt_injection(sample_message)

        scanner.detect_prompt_injection.assert_called_once_with(sample_message)
        assert result is None

    def test_detect_prompt_injection_returns_validation_result(
        self,
        sample_message: AgentMessage,
    ) -> None:
        blocked = ValidationResult(
            is_valid=False,
            errors=["Prompt injection detected"],
            metadata={"rejection_reason": "prompt_injection"},
        )
        scanner = SimpleNamespace(
            scan=AsyncMock(),
            detect_prompt_injection=MagicMock(return_value=blocked),
        )
        coordinator = _make_gate_coordinator(security_scanner=scanner)

        result = coordinator.detect_prompt_injection(sample_message)

        assert result == blocked


class TestGatePipeline:
    @pytest.mark.asyncio
    async def test_run_calls_governance_runner_when_all_gates_pass(
        self,
        sample_message: AgentMessage,
    ) -> None:
        scanner = SimpleNamespace(
            scan=AsyncMock(return_value=None), detect_prompt_injection=MagicMock(return_value=None)
        )
        coordinator = _make_gate_coordinator(
            security_scanner=scanner,
            record_agent_workflow_event=MagicMock(),
        )
        sample_message.impact_score = 0.2
        context = MessageProcessingContext(message=sample_message, start_time=0.0)
        governance_result = ValidationResult(
            is_valid=False, metadata={"rejection_reason": "governance_failed"}
        )
        governance_runner = AsyncMock(return_value=governance_result)

        result = await coordinator.run(context, governance_runner)

        assert result == governance_result
        governance_runner.assert_awaited_once_with(context)
