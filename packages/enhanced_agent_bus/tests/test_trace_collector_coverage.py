# Constitutional Hash: 608508a9bd224290
"""Comprehensive tests for adaptive_governance/trace_collector.py.

Targets ≥90% coverage on:
- TrajectoryRecord dataclass (validation, __post_init__ error paths)
- TraceCollector.collect_from_decision_history (all branching)
- TraceCollector.collect_from_ledger_blocks (all branching)
- TraceCollector._build_record (timestamp branches)
- TraceCollector._entry_to_state (all heuristic branches)
- Module-level constants (N_STATES, IMPACT_TO_STATE, STATE_TO_IMPACT)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timezone

import pytest

from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    ImpactFeatures,
    ImpactLevel,
)
from enhanced_agent_bus.adaptive_governance.trace_collector import (
    IMPACT_TO_STATE,
    N_STATES,
    STATE_TO_IMPACT,
    TraceCollector,
    TrajectoryRecord,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_features() -> ImpactFeatures:
    return ImpactFeatures(
        message_length=10,
        agent_count=1,
        tenant_complexity=0.1,
        temporal_patterns=[0.1],
        semantic_similarity=0.1,
        historical_precedence=1,
        resource_utilization=0.1,
        network_isolation=0.9,
    )


def _make_decision(
    impact: ImpactLevel,
    allowed: bool = True,
    ts: datetime | None = None,
) -> GovernanceDecision:
    return GovernanceDecision(
        action_allowed=allowed,
        impact_level=impact,
        confidence_score=0.9,
        reasoning="test",
        recommended_threshold=0.5,
        features_used=_make_features(),
        timestamp=ts or datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_n_states(self) -> None:
        assert N_STATES == 5

    def test_impact_to_state_covers_all_levels(self) -> None:
        for level in ImpactLevel:
            assert level in IMPACT_TO_STATE

    def test_impact_to_state_values_in_range(self) -> None:
        for idx in IMPACT_TO_STATE.values():
            assert 0 <= idx < N_STATES

    def test_state_to_impact_is_inverse(self) -> None:
        for level, idx in IMPACT_TO_STATE.items():
            assert STATE_TO_IMPACT[idx] == level

    def test_negligible_is_zero(self) -> None:
        assert IMPACT_TO_STATE[ImpactLevel.NEGLIGIBLE] == 0

    def test_critical_is_four(self) -> None:
        assert IMPACT_TO_STATE[ImpactLevel.CRITICAL] == 4


# ---------------------------------------------------------------------------
# TrajectoryRecord
# ---------------------------------------------------------------------------


class TestTrajectoryRecord:
    def test_valid_single_state(self) -> None:
        rec = TrajectoryRecord(states=[0], terminal_unsafe=False)
        assert rec.states == [0]
        assert rec.terminal_unsafe is False

    def test_valid_multi_state(self) -> None:
        rec = TrajectoryRecord(states=[0, 1, 2, 3, 4], terminal_unsafe=True)
        assert len(rec.states) == 5

    def test_empty_states_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            TrajectoryRecord(states=[], terminal_unsafe=False)

    def test_state_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            TrajectoryRecord(states=[-1], terminal_unsafe=False)

    def test_state_equal_n_states_raises(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            TrajectoryRecord(states=[N_STATES], terminal_unsafe=False)

    def test_state_above_n_states_raises(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            TrajectoryRecord(states=[10], terminal_unsafe=False)

    def test_default_timestamp_is_iso(self) -> None:
        rec = TrajectoryRecord(states=[1], terminal_unsafe=False)
        # Should parse as ISO 8601
        datetime.fromisoformat(rec.timestamp)

    def test_session_id_default_none(self) -> None:
        rec = TrajectoryRecord(states=[1], terminal_unsafe=False)
        assert rec.session_id is None

    def test_session_id_set(self) -> None:
        rec = TrajectoryRecord(states=[1], terminal_unsafe=False, session_id="sess-1")
        assert rec.session_id == "sess-1"

    def test_metadata_default_empty_dict(self) -> None:
        rec = TrajectoryRecord(states=[1], terminal_unsafe=False)
        assert rec.metadata == {}

    def test_metadata_custom(self) -> None:
        rec = TrajectoryRecord(states=[1], terminal_unsafe=False, metadata={"k": "v"})
        assert rec.metadata["k"] == "v"

    def test_boundary_state_zero(self) -> None:
        rec = TrajectoryRecord(states=[0], terminal_unsafe=False)
        assert rec.states[0] == 0

    def test_boundary_state_n_states_minus_one(self) -> None:
        rec = TrajectoryRecord(states=[N_STATES - 1], terminal_unsafe=True)
        assert rec.states[0] == N_STATES - 1


# ---------------------------------------------------------------------------
# TraceCollector._entry_to_state
# ---------------------------------------------------------------------------


class TestEntryToState:
    def setup_method(self) -> None:
        self.collector = TraceCollector()

    def test_blocked_multiple_violations_is_critical(self) -> None:
        entry = {"allowed": False, "violations": ["v1", "v2"]}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.CRITICAL]

    def test_blocked_two_violations_is_critical(self) -> None:
        entry = {"allowed": False, "violations": ["v1", "v2", "v3"]}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.CRITICAL]

    def test_blocked_one_violation_is_high(self) -> None:
        entry = {"allowed": False, "violations": ["v1"]}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.HIGH]

    def test_blocked_zero_violations_is_high(self) -> None:
        entry = {"allowed": False, "violations": []}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.HIGH]

    def test_blocked_no_violations_key_is_high(self) -> None:
        entry = {"allowed": False}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.HIGH]

    def test_allowed_slow_is_medium(self) -> None:
        entry = {"allowed": True, "processing_time_ms": 10.0}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.MEDIUM]

    def test_allowed_exactly_5ms_is_medium(self) -> None:
        # Boundary: >5.0 → MEDIUM, so 5.0 itself should NOT be medium
        entry = {"allowed": True, "processing_time_ms": 5.0}
        # 5.0 > 5.0 is False → falls to > 1.0 check → LOW
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.LOW]

    def test_allowed_just_above_5ms_is_medium(self) -> None:
        entry = {"allowed": True, "processing_time_ms": 5.001}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.MEDIUM]

    def test_allowed_moderate_is_low(self) -> None:
        entry = {"allowed": True, "processing_time_ms": 3.0}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.LOW]

    def test_allowed_just_above_1ms_is_low(self) -> None:
        entry = {"allowed": True, "processing_time_ms": 1.001}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.LOW]

    def test_allowed_exactly_1ms_is_negligible(self) -> None:
        # 1.0 > 1.0 is False → NEGLIGIBLE
        entry = {"allowed": True, "processing_time_ms": 1.0}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.NEGLIGIBLE]

    def test_allowed_fast_is_negligible(self) -> None:
        entry = {"allowed": True, "processing_time_ms": 0.5}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.NEGLIGIBLE]

    def test_allowed_zero_ms_is_negligible(self) -> None:
        entry = {"allowed": True, "processing_time_ms": 0.0}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.NEGLIGIBLE]

    def test_allowed_missing_time_defaults_to_negligible(self) -> None:
        entry = {"allowed": True}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.NEGLIGIBLE]

    def test_missing_allowed_defaults_to_true_path(self) -> None:
        # entry.get("allowed", True) defaults to True when key absent
        entry = {"processing_time_ms": 0.0}
        assert self.collector._entry_to_state(entry) == IMPACT_TO_STATE[ImpactLevel.NEGLIGIBLE]

    def test_static_method_callable_directly(self) -> None:
        result = TraceCollector._entry_to_state({"allowed": False, "violations": ["a", "b"]})
        assert result == IMPACT_TO_STATE[ImpactLevel.CRITICAL]


# ---------------------------------------------------------------------------
# TraceCollector._build_record
# ---------------------------------------------------------------------------


class TestBuildRecord:
    def setup_method(self) -> None:
        self.collector = TraceCollector()

    def test_safe_terminal_allowed(self) -> None:
        decisions = [
            _make_decision(ImpactLevel.NEGLIGIBLE),
            _make_decision(ImpactLevel.LOW),
        ]
        rec = self.collector._build_record(decisions, session_id=None)
        assert rec.terminal_unsafe is False

    def test_unsafe_terminal_high_impact(self) -> None:
        decisions = [
            _make_decision(ImpactLevel.NEGLIGIBLE),
            _make_decision(ImpactLevel.HIGH),
        ]
        rec = self.collector._build_record(decisions, session_id=None)
        assert rec.terminal_unsafe is True

    def test_unsafe_terminal_critical_impact(self) -> None:
        decisions = [
            _make_decision(ImpactLevel.LOW),
            _make_decision(ImpactLevel.CRITICAL),
        ]
        rec = self.collector._build_record(decisions, session_id=None)
        assert rec.terminal_unsafe is True

    def test_unsafe_terminal_not_allowed(self) -> None:
        decisions = [
            _make_decision(ImpactLevel.NEGLIGIBLE),
            _make_decision(ImpactLevel.MEDIUM, allowed=False),
        ]
        rec = self.collector._build_record(decisions, session_id=None)
        assert rec.terminal_unsafe is True

    def test_states_mapped_correctly(self) -> None:
        decisions = [
            _make_decision(ImpactLevel.NEGLIGIBLE),
            _make_decision(ImpactLevel.LOW),
            _make_decision(ImpactLevel.MEDIUM),
        ]
        rec = self.collector._build_record(decisions, session_id=None)
        assert rec.states == [
            IMPACT_TO_STATE[ImpactLevel.NEGLIGIBLE],
            IMPACT_TO_STATE[ImpactLevel.LOW],
            IMPACT_TO_STATE[ImpactLevel.MEDIUM],
        ]

    def test_session_id_passed_through(self) -> None:
        decisions = [_make_decision(ImpactLevel.LOW), _make_decision(ImpactLevel.LOW)]
        rec = self.collector._build_record(decisions, session_id="my-session")
        assert rec.session_id == "my-session"

    def test_timestamp_from_datetime_object(self) -> None:
        ts = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        decisions = [
            _make_decision(ImpactLevel.LOW, ts=ts),
        ]
        rec = self.collector._build_record(decisions, session_id=None)
        assert "2024-06-15" in rec.timestamp

    def test_timestamp_from_non_datetime_string(self) -> None:
        d1 = _make_decision(ImpactLevel.LOW)
        d2 = _make_decision(ImpactLevel.LOW)
        # Force timestamp to be a string (not a datetime)
        d2.timestamp = "2024-06-15T12:00:00+00:00"  # type: ignore[assignment]
        decisions = [d1, d2]
        rec = self.collector._build_record(decisions, session_id=None)
        assert "2024-06-15" in rec.timestamp


# ---------------------------------------------------------------------------
# TraceCollector.collect_from_decision_history
# ---------------------------------------------------------------------------


class TestCollectFromDecisionHistory:
    def setup_method(self) -> None:
        self.collector = TraceCollector()

    def test_empty_list_returns_empty(self) -> None:
        result = self.collector.collect_from_decision_history([])
        assert result == []

    def test_below_min_length_returns_empty(self) -> None:
        decisions = [_make_decision(ImpactLevel.LOW)]
        result = self.collector.collect_from_decision_history(decisions, min_length=2)
        assert result == []

    def test_exactly_min_length_returns_one_record(self) -> None:
        decisions = [_make_decision(ImpactLevel.LOW), _make_decision(ImpactLevel.MEDIUM)]
        result = self.collector.collect_from_decision_history(decisions, min_length=2)
        assert len(result) == 1

    def test_all_safe_produces_single_trajectory(self) -> None:
        decisions = [
            _make_decision(ImpactLevel.NEGLIGIBLE),
            _make_decision(ImpactLevel.LOW),
            _make_decision(ImpactLevel.MEDIUM),
        ]
        result = self.collector.collect_from_decision_history(decisions)
        assert len(result) == 1
        assert result[0].terminal_unsafe is False

    def test_unsafe_boundary_flushes_trajectory(self) -> None:
        decisions = [
            _make_decision(ImpactLevel.NEGLIGIBLE),
            _make_decision(ImpactLevel.LOW),
            _make_decision(ImpactLevel.HIGH),  # unsafe boundary
            _make_decision(ImpactLevel.NEGLIGIBLE),
            _make_decision(ImpactLevel.LOW),
        ]
        result = self.collector.collect_from_decision_history(decisions)
        assert len(result) == 2
        assert result[0].terminal_unsafe is True
        assert result[1].terminal_unsafe is False

    def test_critical_level_flushes_trajectory(self) -> None:
        decisions = [
            _make_decision(ImpactLevel.LOW),
            _make_decision(ImpactLevel.CRITICAL),
            _make_decision(ImpactLevel.LOW),
            _make_decision(ImpactLevel.NEGLIGIBLE),
        ]
        result = self.collector.collect_from_decision_history(decisions)
        assert len(result) == 2
        assert result[0].terminal_unsafe is True

    def test_segment_shorter_than_min_length_discarded(self) -> None:
        # Segment before HIGH has only 1 step → discarded
        decisions = [
            _make_decision(ImpactLevel.LOW),  # only 1 step before HIGH
            _make_decision(ImpactLevel.HIGH),  # unsafe flush
            _make_decision(ImpactLevel.NEGLIGIBLE),
            _make_decision(ImpactLevel.LOW),
        ]
        result = self.collector.collect_from_decision_history(decisions, min_length=2)
        # First segment length=2 (LOW + HIGH) → kept; second (NEG + LOW) → kept
        assert len(result) == 2

    def test_remaining_segment_below_min_length_discarded(self) -> None:
        # After unsafe flush, only 1 remaining step → discarded
        decisions = [
            _make_decision(ImpactLevel.LOW),
            _make_decision(ImpactLevel.MEDIUM),
            _make_decision(ImpactLevel.HIGH),  # flush here
            _make_decision(ImpactLevel.NEGLIGIBLE),  # only 1 remaining
        ]
        result = self.collector.collect_from_decision_history(decisions, min_length=2)
        assert len(result) == 1
        assert result[0].terminal_unsafe is True

    def test_session_id_attached_to_all_records(self) -> None:
        decisions = [
            _make_decision(ImpactLevel.LOW),
            _make_decision(ImpactLevel.MEDIUM),
            _make_decision(ImpactLevel.HIGH),
            _make_decision(ImpactLevel.LOW),
        ]
        result = self.collector.collect_from_decision_history(decisions, session_id="s42")
        for rec in result:
            assert rec.session_id == "s42"

    def test_multiple_unsafe_boundaries_produce_multiple_records(self) -> None:
        decisions = [
            _make_decision(ImpactLevel.LOW),
            _make_decision(ImpactLevel.HIGH),  # flush 1
            _make_decision(ImpactLevel.MEDIUM),
            _make_decision(ImpactLevel.CRITICAL),  # flush 2
            _make_decision(ImpactLevel.LOW),
            _make_decision(ImpactLevel.NEGLIGIBLE),
        ]
        result = self.collector.collect_from_decision_history(decisions, min_length=2)
        assert len(result) == 3

    def test_states_in_record_match_decisions(self) -> None:
        decisions = [
            _make_decision(ImpactLevel.NEGLIGIBLE),
            _make_decision(ImpactLevel.LOW),
            _make_decision(ImpactLevel.MEDIUM),
        ]
        result = self.collector.collect_from_decision_history(decisions)
        rec = result[0]
        assert rec.states == [0, 1, 2]

    def test_custom_min_length_one(self) -> None:
        decisions = [_make_decision(ImpactLevel.LOW)]
        result = self.collector.collect_from_decision_history(decisions, min_length=1)
        assert len(result) == 1

    def test_debug_log_on_short_input(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG):
            self.collector.collect_from_decision_history(
                [_make_decision(ImpactLevel.LOW)], min_length=5
            )
        assert "below min_length" in caplog.text

    def test_debug_log_on_success(self, caplog: pytest.LogCaptureFixture) -> None:
        decisions = [_make_decision(ImpactLevel.LOW), _make_decision(ImpactLevel.MEDIUM)]
        with caplog.at_level(logging.DEBUG):
            self.collector.collect_from_decision_history(decisions)
        assert "trajectories from" in caplog.text


# ---------------------------------------------------------------------------
# TraceCollector.collect_from_ledger_blocks
# ---------------------------------------------------------------------------


def _genesis_block() -> dict:
    return {"data": {"type": "genesis", "block_number": 0}}


def _audit_block(allowed: bool, violations: list | None = None, time_ms: float = 0.0) -> dict:
    return {
        "data": {
            "type": "audit",
            "allowed": allowed,
            "violations": violations or [],
            "processing_time_ms": time_ms,
        }
    }


class TestCollectFromLedgerBlocks:
    def setup_method(self) -> None:
        self.collector = TraceCollector()

    def test_empty_blocks_returns_empty(self) -> None:
        result = self.collector.collect_from_ledger_blocks([])
        assert result == []

    def test_only_genesis_block_returns_empty(self) -> None:
        result = self.collector.collect_from_ledger_blocks([_genesis_block()])
        assert result == []

    def test_below_min_length_returns_empty(self) -> None:
        blocks = [_audit_block(True, time_ms=0.0)]
        result = self.collector.collect_from_ledger_blocks(blocks, min_length=2)
        assert result == []

    def test_genesis_block_skipped(self) -> None:
        blocks = [
            _genesis_block(),
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
        ]
        result = self.collector.collect_from_ledger_blocks(blocks, min_length=2)
        assert len(result) == 1

    def test_non_dict_data_skipped(self) -> None:
        blocks = [
            {"data": "not-a-dict"},
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
        ]
        result = self.collector.collect_from_ledger_blocks(blocks, min_length=2)
        assert len(result) == 1

    def test_missing_data_key_skipped(self) -> None:
        blocks = [
            {"other": "field"},
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
        ]
        result = self.collector.collect_from_ledger_blocks(blocks, min_length=2)
        assert len(result) == 1

    def test_all_safe_entries_one_record(self) -> None:
        blocks = [
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
        ]
        result = self.collector.collect_from_ledger_blocks(blocks)
        assert len(result) == 1
        assert result[0].terminal_unsafe is False

    def test_unsafe_state_flushes_trajectory(self) -> None:
        blocks = [
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
            _audit_block(False, violations=["v1"]),  # HIGH → flush
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
        ]
        result = self.collector.collect_from_ledger_blocks(blocks)
        assert len(result) == 2
        assert result[0].terminal_unsafe is True
        assert result[1].terminal_unsafe is False

    def test_critical_entry_flushes_trajectory(self) -> None:
        blocks = [
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
            _audit_block(False, violations=["v1", "v2"]),  # CRITICAL
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
        ]
        result = self.collector.collect_from_ledger_blocks(blocks)
        assert len(result) == 2
        assert result[0].terminal_unsafe is True

    def test_segment_before_unsafe_too_short_discarded(self) -> None:
        # Only 1 safe entry before HIGH → segment length=2 (NEG + HIGH) → kept
        # Remaining single entry is below min_length=2 → discarded
        blocks = [
            _audit_block(True, time_ms=0.0),  # NEG
            _audit_block(False, violations=["v1"]),  # HIGH flush
            _audit_block(True, time_ms=0.0),
        ]
        result = self.collector.collect_from_ledger_blocks(blocks, min_length=2)
        assert len(result) == 1

    def test_remaining_too_short_discarded(self) -> None:
        # After flush, only 1 entry remains → discarded
        blocks = [
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
            _audit_block(False, violations=["v1"]),  # flush
            _audit_block(True, time_ms=0.0),  # only 1 remaining
        ]
        result = self.collector.collect_from_ledger_blocks(blocks, min_length=2)
        assert len(result) == 1
        assert result[0].terminal_unsafe is True

    def test_metadata_source_is_blockchain_ledger(self) -> None:
        blocks = [_audit_block(True), _audit_block(True)]
        result = self.collector.collect_from_ledger_blocks(blocks)
        assert result[0].metadata == {"source": "blockchain_ledger"}

    def test_states_list_correct(self) -> None:
        blocks = [
            _audit_block(True, time_ms=0.0),  # NEGLIGIBLE → 0
            _audit_block(True, time_ms=3.0),  # LOW → 1
        ]
        result = self.collector.collect_from_ledger_blocks(blocks)
        assert result[0].states == [
            IMPACT_TO_STATE[ImpactLevel.NEGLIGIBLE],
            IMPACT_TO_STATE[ImpactLevel.LOW],
        ]

    def test_multiple_flushes(self) -> None:
        blocks = [
            _audit_block(True, time_ms=0.0),
            _audit_block(False, violations=["v1"]),  # HIGH flush 1
            _audit_block(True, time_ms=0.0),
            _audit_block(False, violations=["a", "b"]),  # CRITICAL flush 2
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
        ]
        result = self.collector.collect_from_ledger_blocks(blocks, min_length=2)
        assert len(result) == 3

    def test_debug_log_on_success(self, caplog: pytest.LogCaptureFixture) -> None:
        blocks = [_audit_block(True), _audit_block(True)]
        with caplog.at_level(logging.DEBUG):
            self.collector.collect_from_ledger_blocks(blocks)
        assert "trajectories from" in caplog.text

    def test_no_data_key_in_block(self) -> None:
        blocks = [
            {},
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
        ]
        result = self.collector.collect_from_ledger_blocks(blocks)
        assert len(result) == 1

    def test_data_is_none_skipped(self) -> None:
        blocks = [
            {"data": None},
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
        ]
        result = self.collector.collect_from_ledger_blocks(blocks)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Integration: round-trip decision history → records
# ---------------------------------------------------------------------------


class TestIntegration:
    def setup_method(self) -> None:
        self.collector = TraceCollector()

    def test_full_decision_history_round_trip(self) -> None:
        decisions = [
            _make_decision(ImpactLevel.NEGLIGIBLE),
            _make_decision(ImpactLevel.LOW),
            _make_decision(ImpactLevel.MEDIUM),
            _make_decision(ImpactLevel.HIGH),  # unsafe flush
            _make_decision(ImpactLevel.NEGLIGIBLE),
            _make_decision(ImpactLevel.LOW),
        ]
        records = self.collector.collect_from_decision_history(decisions)
        assert len(records) == 2
        assert records[0].terminal_unsafe is True
        assert records[1].terminal_unsafe is False
        # All states should be valid
        for rec in records:
            for s in rec.states:
                assert 0 <= s < N_STATES

    def test_full_ledger_round_trip(self) -> None:
        blocks = [
            _genesis_block(),
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=3.0),
            _audit_block(False, violations=["v1", "v2"]),  # CRITICAL flush
            _audit_block(True, time_ms=0.0),
            _audit_block(True, time_ms=0.5),
        ]
        records = self.collector.collect_from_ledger_blocks(blocks)
        assert len(records) == 2
        assert records[0].terminal_unsafe is True
        assert records[1].terminal_unsafe is False

    def test_unsafe_terminal_states_constant(self) -> None:
        assert ImpactLevel.HIGH in TraceCollector.UNSAFE_TERMINAL_STATES
        assert ImpactLevel.CRITICAL in TraceCollector.UNSAFE_TERMINAL_STATES
        assert ImpactLevel.MEDIUM not in TraceCollector.UNSAFE_TERMINAL_STATES
        assert ImpactLevel.LOW not in TraceCollector.UNSAFE_TERMINAL_STATES
        assert ImpactLevel.NEGLIGIBLE not in TraceCollector.UNSAFE_TERMINAL_STATES

    def test_decision_history_single_item_before_unsafe_discarded_by_min_length(self) -> None:
        # Exactly 1 decision before HIGH → segment has length 2 (that 1 + HIGH itself).
        # With min_length=3 that 2-step segment is discarded.
        # Remaining 1-step [LOW] segment is also below min_length=3 → discarded.
        decisions = [
            _make_decision(ImpactLevel.LOW),  # 1 item
            _make_decision(ImpactLevel.HIGH),  # unsafe — segment len=2 < 3 → discarded
            _make_decision(ImpactLevel.LOW),
        ]
        result = self.collector.collect_from_decision_history(decisions, min_length=3)
        assert len(result) == 0

    def test_ledger_single_item_before_unsafe_discarded_by_min_length(self) -> None:
        # Exactly 1 safe entry before HIGH → segment len=2 with HIGH appended.
        # With min_length=3 that segment is discarded.
        # Remaining 1-step [NEG] segment is also below min_length=3 → discarded.
        blocks = [
            _audit_block(True, time_ms=0.0),  # NEG → len=1 before unsafe
            _audit_block(False, violations=["v1"]),  # HIGH flush; segment=[0,3], len=2 < 3
            _audit_block(True, time_ms=0.0),
        ]
        result = self.collector.collect_from_ledger_blocks(blocks, min_length=3)
        assert len(result) == 0
