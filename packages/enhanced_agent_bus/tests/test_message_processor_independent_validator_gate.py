"""Tests for independent-validator gate in message processing.

Constitutional Hash: 608508a9bd224290
"""

import pytest

pytest.importorskip("src.core.shared.agent_workflow_metrics")


import pytest
from src.core.shared.agent_workflow_metrics import (
    get_agent_workflow_metrics_collector,
    reset_agent_workflow_metrics_collector,
)

from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.message_processor import MessageProcessor
from enhanced_agent_bus.models import AgentMessage, MessageType


@pytest.fixture
def processor_gate_enabled() -> MessageProcessor:
    reset_agent_workflow_metrics_collector()
    processor = MessageProcessor.__new__(MessageProcessor)
    processor._require_independent_validator = True
    processor._independent_validator_threshold = 0.8
    processor._agent_workflow_metrics = get_agent_workflow_metrics_collector()
    return processor


@pytest.mark.constitutional
def test_gate_allows_low_risk_messages_without_validator(
    processor_gate_enabled: MessageProcessor,
) -> None:
    msg = AgentMessage(
        from_agent="agent-origin",
        message_type=MessageType.COMMAND,
        impact_score=0.2,
    )

    result = processor_gate_enabled._enforce_independent_validator_gate(msg)
    assert result is None


@pytest.mark.constitutional
def test_gate_blocks_high_risk_message_without_validator_metadata(
    processor_gate_enabled: MessageProcessor,
) -> None:
    msg = AgentMessage(
        from_agent="agent-origin",
        message_type=MessageType.COMMAND,
        impact_score=0.95,
    )

    result = processor_gate_enabled._enforce_independent_validator_gate(msg)
    assert result is not None
    assert result.is_valid is False
    assert result.metadata.get("rejection_reason") == "independent_validator_missing"
    summary = processor_gate_enabled._agent_workflow_metrics.snapshot("default")
    assert summary["interventions_total"] == 1
    assert summary["gate_failures_total"] == 1


@pytest.mark.constitutional
def test_gate_blocks_self_validated_message(
    processor_gate_enabled: MessageProcessor,
) -> None:
    msg = AgentMessage(
        from_agent="agent-origin",
        message_type=MessageType.GOVERNANCE_REQUEST,
        metadata={
            "validated_by_agent": "agent-origin",
            "validation_stage": "independent",
        },
    )

    result = processor_gate_enabled._enforce_independent_validator_gate(msg)
    assert result is not None
    assert result.is_valid is False
    assert result.metadata.get("rejection_reason") == "independent_validator_self_validation"


@pytest.mark.constitutional
def test_gate_allows_valid_independent_validator_evidence(
    processor_gate_enabled: MessageProcessor,
) -> None:
    msg = AgentMessage(
        from_agent="agent-origin",
        message_type=MessageType.GOVERNANCE_REQUEST,
        metadata={
            "validated_by_agent": "agent-validator",
            "validation_stage": "independent",
        },
    )

    result = processor_gate_enabled._enforce_independent_validator_gate(msg)
    assert result is None


@pytest.mark.constitutional
def test_processor_reads_gate_defaults_from_configuration() -> None:
    config = BusConfiguration.for_testing()
    config.require_independent_validator = True
    config.independent_validator_threshold = 0.91

    processor = MessageProcessor(
        config=config,
        isolated_mode=True,
        use_rust=False,
        enable_maci=False,  # test-only: MACI off — testing message processor directly
    )

    assert processor._require_independent_validator is True
    assert processor._independent_validator_threshold == 0.91


@pytest.mark.constitutional
def test_processor_reads_policy_fail_closed_from_configuration() -> None:
    config = BusConfiguration.for_testing()
    config.policy_fail_closed = True

    processor = MessageProcessor(
        config=config,
        isolated_mode=True,
        use_rust=False,
        enable_maci=False,  # test-only: MACI off — testing message processor directly
    )

    assert processor._policy_fail_closed is True


@pytest.mark.constitutional
def test_processor_exposes_workflow_telemetry_metrics() -> None:
    reset_agent_workflow_metrics_collector()
    config = BusConfiguration.for_testing()
    processor = MessageProcessor(
        config=config,
        isolated_mode=True,
        use_rust=False,
        enable_maci=False,  # test-only: MACI off — testing message processor directly
    )
    processor._record_agent_workflow_event(
        event_type="autonomous_action",
        msg=AgentMessage(from_agent="agent-origin"),
        reason="test_event",
    )
    metrics = processor.get_metrics()
    assert "workflow_intervention_rate" in metrics
    assert "workflow_gate_failures_total" in metrics
    assert "workflow_rollback_triggers_total" in metrics
    assert "workflow_autonomous_actions_total" in metrics
    assert metrics["workflow_autonomous_actions_total"] >= 1
