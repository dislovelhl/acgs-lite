"""Tests for runtime trajectory monitoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from acgs_lite.trajectory import (
    CumulativeValueRule,
    FrequencyThresholdRule,
    InMemoryTrajectoryStore,
    TrajectoryMonitor,
    TrajectorySession,
)


def _decision(
    *,
    action_type: str,
    timestamp: datetime,
    amount: int = 0,
    agent_id: str = "agent-1",
) -> dict[str, object]:
    return {
        "action_type": action_type,
        "agent_id": agent_id,
        "timestamp": timestamp.isoformat(),
        "metadata": {"amount": amount},
    }


def test_cumulative_value_rule_triggers_above_threshold() -> None:
    base = datetime(2026, 4, 7, tzinfo=timezone.utc)
    session = TrajectorySession(session_id="s1", agent_id="agent-1")
    for index in range(50):
        session.add(
            _decision(
                action_type="payment",
                timestamp=base + timedelta(seconds=index),
                amount=9000,
            )
        )

    monitor = TrajectoryMonitor(
        rules=[CumulativeValueRule(threshold=100000)],
        store=InMemoryTrajectoryStore(),
    )

    violations = monitor.check_trajectory(session)

    assert len(violations) == 1
    assert violations[0].rule_id == "TRAJ-CUMVAL-001"


def test_frequency_threshold_rule_triggers_for_repeated_action_types() -> None:
    base = datetime(2026, 4, 7, tzinfo=timezone.utc)
    session = TrajectorySession(session_id="s2", agent_id="agent-1")
    for index in range(10):
        session.add(
            _decision(
                action_type="approve",
                timestamp=base + timedelta(seconds=index),
            )
        )

    monitor = TrajectoryMonitor(
        rules=[FrequencyThresholdRule(max_count=5, window_seconds=60)],
        store=InMemoryTrajectoryStore(),
    )

    violations = monitor.check_trajectory(session)

    assert len(violations) == 1
    assert violations[0].rule_id == "TRAJ-FREQ-001"


def test_clean_session_produces_zero_violations() -> None:
    base = datetime(2026, 4, 7, tzinfo=timezone.utc)
    session = TrajectorySession(session_id="s3", agent_id="agent-1")
    session.add(_decision(action_type="read", timestamp=base, amount=10))
    session.add(_decision(action_type="write", timestamp=base + timedelta(minutes=2), amount=20))
    session.add(
        _decision(action_type="approve", timestamp=base + timedelta(minutes=4), amount=30)
    )

    monitor = TrajectoryMonitor(
        rules=[
            FrequencyThresholdRule(max_count=5, window_seconds=60),
            CumulativeValueRule(threshold=100000),
        ],
        store=InMemoryTrajectoryStore(),
    )

    assert monitor.check_trajectory(session) == []


def test_trajectory_session_add_is_append_only() -> None:
    session = TrajectorySession(session_id="s4", agent_id="agent-1")
    first = {"action_type": "read", "metadata": {"amount": 1}}
    second = {"action_type": "write", "metadata": {"amount": 2}}

    session.add(first)
    session.add(second)

    assert session.decisions == [first, second]
