"""
Unit tests for agent_health Pydantic models and enums.
Constitutional Hash: 608508a9bd224290

Tests are written RED-first (before models.py exists) per TDD workflow.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.agent_health.models import (
    AgentHealthRecord,
    AgentHealthThresholds,
    AutonomyTier,
    HealingAction,
    HealingActionType,
    HealingOverride,
    HealingTrigger,
    HealthState,
    OverrideMode,
)

# These imports will fail (RED) until models.py is implemented


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestHealthState:
    def test_values(self) -> None:
        assert HealthState.HEALTHY == "HEALTHY"
        assert HealthState.DEGRADED == "DEGRADED"
        assert HealthState.QUARANTINED == "QUARANTINED"
        assert HealthState.RESTARTING == "RESTARTING"

    def test_all_four_members(self) -> None:
        assert len(HealthState) == 4


class TestAutonomyTier:
    def test_values(self) -> None:
        assert AutonomyTier.ADVISORY == "ADVISORY"
        assert AutonomyTier.BOUNDED == "BOUNDED"
        assert AutonomyTier.HUMAN_APPROVED == "HUMAN_APPROVED"

    def test_all_three_members(self) -> None:
        assert len(AutonomyTier) == 3


class TestHealingTrigger:
    def test_values(self) -> None:
        assert HealingTrigger.FAILURE_LOOP == "FAILURE_LOOP"
        assert HealingTrigger.MEMORY_EXHAUSTION == "MEMORY_EXHAUSTION"
        assert HealingTrigger.MANUAL == "MANUAL"

    def test_all_three_members(self) -> None:
        assert len(HealingTrigger) == 3


class TestHealingActionType:
    def test_values(self) -> None:
        assert HealingActionType.GRACEFUL_RESTART == "GRACEFUL_RESTART"
        assert HealingActionType.QUARANTINE == "QUARANTINE"
        assert HealingActionType.SUPERVISOR_NOTIFY == "SUPERVISOR_NOTIFY"
        assert HealingActionType.HITL_REQUEST == "HITL_REQUEST"

    def test_all_four_members(self) -> None:
        assert len(HealingActionType) == 4


class TestOverrideMode:
    def test_values(self) -> None:
        assert OverrideMode.SUPPRESS_HEALING == "SUPPRESS_HEALING"
        assert OverrideMode.FORCE_RESTART == "FORCE_RESTART"
        assert OverrideMode.FORCE_QUARANTINE == "FORCE_QUARANTINE"

    def test_all_three_members(self) -> None:
        assert len(OverrideMode) == 3


# ---------------------------------------------------------------------------
# AgentHealthRecord tests
# ---------------------------------------------------------------------------


class TestAgentHealthRecord:
    def _make_record(self, **kwargs: object) -> AgentHealthRecord:
        defaults: dict = {
            "agent_id": "agent-abc",
            "health_state": HealthState.HEALTHY,
            "consecutive_failure_count": 0,
            "memory_usage_pct": 45.0,
            "last_event_at": datetime.now(UTC),
            "autonomy_tier": AutonomyTier.ADVISORY,
        }
        defaults.update(kwargs)
        return AgentHealthRecord(**defaults)

    def test_happy_path(self) -> None:
        record = self._make_record()
        assert record.agent_id == "agent-abc"
        assert record.health_state == HealthState.HEALTHY
        assert record.consecutive_failure_count == 0
        assert record.memory_usage_pct == 45.0
        assert record.last_error_type is None
        assert record.healing_override_id is None

    def test_agent_id_max_255_chars(self) -> None:
        long_id = "a" * 255
        record = self._make_record(agent_id=long_id)
        assert len(record.agent_id) == 255

    def test_agent_id_too_long_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make_record(agent_id="a" * 256)

    def test_agent_id_empty_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make_record(agent_id="")

    def test_memory_usage_pct_lower_bound(self) -> None:
        record = self._make_record(memory_usage_pct=0.0)
        assert record.memory_usage_pct == 0.0

    def test_memory_usage_pct_upper_bound(self) -> None:
        record = self._make_record(memory_usage_pct=100.0)
        assert record.memory_usage_pct == 100.0

    def test_memory_usage_pct_below_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make_record(memory_usage_pct=-0.1)

    def test_memory_usage_pct_above_100_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make_record(memory_usage_pct=100.1)

    def test_consecutive_failure_count_zero_allowed(self) -> None:
        record = self._make_record(consecutive_failure_count=0)
        assert record.consecutive_failure_count == 0

    def test_consecutive_failure_count_negative_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make_record(consecutive_failure_count=-1)

    def test_optional_fields_default_none(self) -> None:
        record = self._make_record()
        assert record.last_error_type is None
        assert record.healing_override_id is None

    def test_last_error_type_max_128_chars(self) -> None:
        record = self._make_record(last_error_type="x" * 128)
        assert len(record.last_error_type) == 128  # type: ignore[arg-type]

    def test_last_error_type_too_long_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make_record(last_error_type="x" * 129)


# ---------------------------------------------------------------------------
# HealingAction tests
# ---------------------------------------------------------------------------


class TestHealingAction:
    def _make_action(self, **kwargs: object) -> HealingAction:
        defaults: dict = {
            "agent_id": "agent-xyz",
            "trigger": HealingTrigger.FAILURE_LOOP,
            "action_type": HealingActionType.GRACEFUL_RESTART,
            "tier_determined_by": AutonomyTier.HUMAN_APPROVED,
            "initiated_at": datetime.now(UTC),
            "audit_event_id": "audit-001",
        }
        defaults.update(kwargs)
        return HealingAction(**defaults)

    def test_action_id_auto_generated_uuid(self) -> None:
        action = self._make_action()
        # Should be a valid UUID
        parsed = uuid.UUID(action.action_id)
        assert parsed.version == 4

    def test_constitutional_hash_fixed(self) -> None:
        action = self._make_action()
        assert action.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_wrong_value_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make_action(constitutional_hash="deadbeef")

    def test_completed_at_defaults_none(self) -> None:
        action = self._make_action()
        assert action.completed_at is None

    def test_completed_at_can_be_set(self) -> None:
        now = datetime.now(UTC)
        action = self._make_action(completed_at=now)
        assert action.completed_at == now

    def test_all_required_fields_present(self) -> None:
        action = self._make_action()
        assert action.agent_id == "agent-xyz"
        assert action.trigger == HealingTrigger.FAILURE_LOOP
        assert action.action_type == HealingActionType.GRACEFUL_RESTART
        assert action.tier_determined_by == AutonomyTier.HUMAN_APPROVED
        assert action.audit_event_id == "audit-001"


# ---------------------------------------------------------------------------
# HealingOverride tests
# ---------------------------------------------------------------------------


class TestHealingOverride:
    def _make_override(self, **kwargs: object) -> HealingOverride:
        now = datetime.now(UTC)
        defaults: dict = {
            "agent_id": "agent-foo",
            "mode": OverrideMode.SUPPRESS_HEALING,
            "reason": "Investigating failure pattern",
            "issued_by": "operator@example.com",
            "issued_at": now,
        }
        defaults.update(kwargs)
        return HealingOverride(**defaults)

    def test_override_id_auto_generated_uuid(self) -> None:
        override = self._make_override()
        parsed = uuid.UUID(override.override_id)
        assert parsed.version == 4

    def test_reason_max_1000_chars(self) -> None:
        override = self._make_override(reason="x" * 1000)
        assert len(override.reason) == 1000

    def test_reason_too_long_raises(self) -> None:
        with pytest.raises(ValidationError):
            self._make_override(reason="x" * 1001)

    def test_expires_at_defaults_none(self) -> None:
        override = self._make_override()
        assert override.expires_at is None

    def test_expires_at_after_issued_at_allowed(self) -> None:
        now = datetime.now(UTC)
        override = self._make_override(
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )
        assert override.expires_at is not None

    def test_expires_at_before_issued_at_raises(self) -> None:
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            self._make_override(
                issued_at=now,
                expires_at=now - timedelta(seconds=1),
            )


# ---------------------------------------------------------------------------
# AgentHealthThresholds tests
# ---------------------------------------------------------------------------


class TestAgentHealthThresholds:
    def test_defaults(self) -> None:
        t = AgentHealthThresholds()
        assert t.failure_count_threshold == 5
        assert t.failure_window_seconds == 60
        assert t.memory_exhaustion_pct == 85.0
        assert t.memory_hysteresis_pct == 10.0
        assert t.drain_timeout_seconds == 30
        assert t.metric_emit_interval_seconds == 30

    def test_agent_id_optional(self) -> None:
        t = AgentHealthThresholds()
        assert t.agent_id is None

    def test_agent_id_can_be_set(self) -> None:
        t = AgentHealthThresholds(agent_id="agent-123")
        assert t.agent_id == "agent-123"

    def test_failure_count_threshold_min_1(self) -> None:
        t = AgentHealthThresholds(failure_count_threshold=1)
        assert t.failure_count_threshold == 1

    def test_failure_count_threshold_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            AgentHealthThresholds(failure_count_threshold=0)

    def test_failure_window_seconds_min_10(self) -> None:
        t = AgentHealthThresholds(failure_window_seconds=10)
        assert t.failure_window_seconds == 10

    def test_failure_window_seconds_below_10_raises(self) -> None:
        with pytest.raises(ValidationError):
            AgentHealthThresholds(failure_window_seconds=9)

    def test_memory_exhaustion_pct_bounds(self) -> None:
        t_low = AgentHealthThresholds(memory_exhaustion_pct=50.0)
        t_high = AgentHealthThresholds(memory_exhaustion_pct=99.0)
        assert t_low.memory_exhaustion_pct == 50.0
        assert t_high.memory_exhaustion_pct == 99.0

    def test_memory_exhaustion_pct_out_of_bounds_raises(self) -> None:
        with pytest.raises(ValidationError):
            AgentHealthThresholds(memory_exhaustion_pct=49.9)
        with pytest.raises(ValidationError):
            AgentHealthThresholds(memory_exhaustion_pct=99.1)

    def test_drain_timeout_seconds_min_5(self) -> None:
        t = AgentHealthThresholds(drain_timeout_seconds=5)
        assert t.drain_timeout_seconds == 5

    def test_drain_timeout_seconds_below_5_raises(self) -> None:
        with pytest.raises(ValidationError):
            AgentHealthThresholds(drain_timeout_seconds=4)

    def test_metric_emit_interval_seconds_min_5(self) -> None:
        t = AgentHealthThresholds(metric_emit_interval_seconds=5)
        assert t.metric_emit_interval_seconds == 5

    def test_metric_emit_interval_seconds_below_5_raises(self) -> None:
        with pytest.raises(ValidationError):
            AgentHealthThresholds(metric_emit_interval_seconds=4)
