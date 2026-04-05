"""Processor integration tests for independent-validator configuration and workflow telemetry."""

from __future__ import annotations

import pytest

pytest.importorskip("src.core.shared.agent_workflow_metrics")

from enhanced_agent_bus._compat.agent_workflow_metrics import (
    reset_agent_workflow_metrics_collector,
)
from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.message_processor import MessageProcessor
from enhanced_agent_bus.models import AgentMessage


@pytest.mark.constitutional
def test_processor_reads_gate_defaults_from_configuration() -> None:
    config = BusConfiguration.for_testing()
    config.require_independent_validator = True
    config.independent_validator_threshold = 0.91

    processor = MessageProcessor(
        config=config,
        isolated_mode=True,
        use_rust=False,
        enable_maci=False,
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
        enable_maci=False,
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
        enable_maci=False,
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
