"""Tests for runtime trajectory monitoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from acgs_lite.trajectory import (
    CumulativeValueRule,
    FrequencyThresholdRule,
    InMemoryTrajectoryStore,
    SensitiveToolSequenceRule,
    TrajectoryMonitor,
    TrajectorySession,
)


def _decision(
    *,
    action_type: str,
    timestamp: datetime,
    amount: int = 0,
    agent_id: str = "agent-1",
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    merged_metadata = {"amount": amount}
    if metadata:
        merged_metadata.update(metadata)
    return {
        "action_type": action_type,
        "agent_id": agent_id,
        "timestamp": timestamp.isoformat(),
        "metadata": merged_metadata,
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
    session.add(_decision(action_type="approve", timestamp=base + timedelta(minutes=4), amount=30))

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


def test_checkpoint_detects_sensitive_tool_sequence_after_untrusted_input() -> None:
    base = datetime(2026, 4, 7, tzinfo=timezone.utc)
    store = InMemoryTrajectoryStore()
    monitor = TrajectoryMonitor(
        rules=[SensitiveToolSequenceRule(sensitive_tools={"shell", "terminal"})],
        store=store,
    )

    precursor_violations = monitor.check_checkpoint(
        session_id="s5",
        agent_id="agent-1",
        decision=_decision(
            action_type="ingest-untrusted-content",
            timestamp=base,
            metadata={
                "checkpoint_kind": "input_analysis",
                "prompt_injection_suspected": True,
            },
        ),
    )
    assert precursor_violations == []

    tool_violations = monitor.check_checkpoint(
        session_id="s5",
        agent_id="agent-1",
        decision=_decision(
            action_type="tool-call",
            timestamp=base + timedelta(seconds=1),
            metadata={
                "checkpoint_kind": "tool_invocation",
                "tool_name": "shell",
            },
        ),
    )

    assert len(tool_violations) == 1
    assert tool_violations[0].rule_id == "TRAJ-TOOLSEQ-001"
    assert "shell" in tool_violations[0].evidence


def test_checkpoint_allows_safe_tool_sequence_without_precursor_flags() -> None:
    base = datetime(2026, 4, 7, tzinfo=timezone.utc)
    monitor = TrajectoryMonitor(
        rules=[SensitiveToolSequenceRule(sensitive_tools={"shell", "terminal"})],
        store=InMemoryTrajectoryStore(),
    )

    violations = monitor.check_checkpoint(
        session_id="s6",
        agent_id="agent-1",
        decision=_decision(
            action_type="tool-call",
            timestamp=base,
            metadata={
                "checkpoint_kind": "tool_invocation",
                "tool_name": "filesystem-read",
            },
        ),
    )

    assert violations == []
