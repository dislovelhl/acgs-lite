"""
Unit tests for FailureLoopDetector and MemoryExhaustionDetector.
Constitutional Hash: 608508a9bd224290

TDD RED: These tests are written before detectors.py is implemented.
All tests fail (RED) until detectors.py provides the implementation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from enhanced_agent_bus.agent_health.detectors import (
    FailureLoopDetector,
    MemoryExhaustionDetector,
)
from enhanced_agent_bus.agent_health.models import AgentHealthThresholds

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _thresholds(
    failure_count_threshold: int = 5,
    failure_window_seconds: int = 60,
    memory_exhaustion_pct: float = 85.0,
    memory_hysteresis_pct: float = 10.0,
) -> AgentHealthThresholds:
    return AgentHealthThresholds(
        failure_count_threshold=failure_count_threshold,
        failure_window_seconds=failure_window_seconds,
        memory_exhaustion_pct=memory_exhaustion_pct,
        memory_hysteresis_pct=memory_hysteresis_pct,
    )


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# FailureLoopDetector
# ---------------------------------------------------------------------------


class TestFailureLoopDetectorBelowThreshold:
    """Tests verify FailureLoopDetector does not trigger when failure count < threshold."""

    def test_no_failures_not_detected(self) -> None:
        detector = FailureLoopDetector(_thresholds(failure_count_threshold=5))
        assert not detector.is_loop_detected()

    def test_one_below_threshold_not_detected(self) -> None:
        detector = FailureLoopDetector(_thresholds(failure_count_threshold=5))
        now = _now()
        for i in range(4):
            result = detector.record_failure(now + timedelta(seconds=i))
            assert not result, f"Should not detect loop after {i + 1} failure(s)"
        assert not detector.is_loop_detected()

    @pytest.mark.parametrize("threshold", [1, 5, 10])
    def test_threshold_minus_one_not_detected(self, threshold: int) -> None:
        detector = FailureLoopDetector(_thresholds(failure_count_threshold=threshold))
        now = _now()
        for i in range(threshold - 1):
            result = detector.record_failure(now + timedelta(seconds=i))
            assert not result
        assert not detector.is_loop_detected()


@pytest.mark.constitutional
class TestFailureLoopDetectorThresholdCrossing:
    """Tests verify FailureLoopDetector triggers exactly at the configured threshold."""

    @pytest.mark.parametrize("threshold", [1, 5, 10])
    def test_triggers_exactly_at_threshold(self, threshold: int) -> None:
        detector = FailureLoopDetector(_thresholds(failure_count_threshold=threshold))
        now = _now()
        # Record threshold - 1 failures: not triggered
        for i in range(threshold - 1):
            result = detector.record_failure(now + timedelta(seconds=i))
            assert not result, f"Should not trigger before threshold ({i + 1}/{threshold})"
        # Record the threshold-th failure: triggers
        result = detector.record_failure(now + timedelta(seconds=threshold))
        assert result, "Should trigger exactly at threshold"
        assert detector.is_loop_detected()

    def test_default_threshold_five_within_window(self) -> None:
        """Default threshold (5) triggers inside the default 60-second window."""
        detector = FailureLoopDetector(_thresholds())
        now = _now()
        for i in range(4):
            detector.record_failure(now + timedelta(seconds=i * 5))
        result = detector.record_failure(now + timedelta(seconds=25))
        assert result
        assert detector.is_loop_detected()

    def test_detection_is_immediate_on_threshold_crossing(self) -> None:
        """record_failure returns True on the exact call that crosses the threshold.

        This verifies NFR-002: detection happens within the same polling cycle
        (no additional delay in the detector itself), contributing to the
        <10-second total pipeline requirement.
        """
        detector = FailureLoopDetector(_thresholds(failure_count_threshold=3))
        t = _now()
        assert not detector.record_failure(t)
        assert not detector.record_failure(t + timedelta(seconds=1))
        assert detector.record_failure(t + timedelta(seconds=2))  # triggers immediately


@pytest.mark.constitutional
class TestFailureLoopDetectorSuccessReset:
    """Tests verify failure counter resets to 0 when a success is recorded."""

    def test_success_clears_failure_history(self) -> None:
        detector = FailureLoopDetector(_thresholds(failure_count_threshold=5))
        now = _now()
        for i in range(4):
            detector.record_failure(now + timedelta(seconds=i))
        detector.record_success()
        assert not detector.is_loop_detected()

    def test_success_after_loop_detected_clears_state(self) -> None:
        detector = FailureLoopDetector(_thresholds(failure_count_threshold=3))
        now = _now()
        for i in range(3):
            detector.record_failure(now + timedelta(seconds=i))
        assert detector.is_loop_detected()
        detector.record_success()
        assert not detector.is_loop_detected()

    def test_failure_after_success_starts_fresh_count(self) -> None:
        detector = FailureLoopDetector(_thresholds(failure_count_threshold=3))
        now = _now()
        # First burst: reach threshold
        for i in range(3):
            detector.record_failure(now + timedelta(seconds=i))
        assert detector.is_loop_detected()
        # Success clears
        detector.record_success()
        # Second burst: 2 failures — should not trigger again
        t2 = now + timedelta(seconds=10)
        result = detector.record_failure(t2)
        assert not result
        result = detector.record_failure(t2 + timedelta(seconds=1))
        assert not result
        assert not detector.is_loop_detected()


@pytest.mark.constitutional
class TestFailureLoopDetectorSlidingWindow:
    """Tests verify failures outside the time window do not count toward the threshold."""

    def test_old_failures_outside_window_excluded(self) -> None:
        detector = FailureLoopDetector(
            _thresholds(failure_count_threshold=3, failure_window_seconds=30)
        )
        base = _now()
        # Record 2 failures that will expire
        detector.record_failure(base)
        detector.record_failure(base + timedelta(seconds=1))
        # Advance time past the window
        recent = base + timedelta(seconds=35)
        # Record 2 more within the new window — still below threshold (3)
        result1 = detector.record_failure(recent)
        result2 = detector.record_failure(recent + timedelta(seconds=1))
        assert not result1, "Old failures expired; 1 in-window failure should not trigger"
        assert not result2, "Old failures expired; 2 in-window failures should not trigger"

    def test_window_boundary_failure_counts(self) -> None:
        """Failures exactly AT the boundary edge are excluded (strictly older)."""
        detector = FailureLoopDetector(
            _thresholds(failure_count_threshold=2, failure_window_seconds=60)
        )
        base = _now()
        # First failure: will be exactly at window boundary
        detector.record_failure(base)
        # Advance 60 seconds: the first failure is now at the boundary edge
        at_boundary = base + timedelta(seconds=60)
        # Second failure at boundary — first failure should be pruned (>= 60s old)
        result = detector.record_failure(at_boundary)
        assert not result, "Failure at exact boundary edge should be excluded"

    def test_failures_within_window_accumulate(self) -> None:
        detector = FailureLoopDetector(
            _thresholds(failure_count_threshold=3, failure_window_seconds=60)
        )
        base = _now()
        detector.record_failure(base)
        detector.record_failure(base + timedelta(seconds=20))
        result = detector.record_failure(base + timedelta(seconds=40))
        assert result, "3 failures within 60s window should trigger"

    def test_mixed_in_and_out_of_window(self) -> None:
        """Only failures within the sliding window count."""
        detector = FailureLoopDetector(
            _thresholds(failure_count_threshold=3, failure_window_seconds=30)
        )
        base = _now()
        # 2 stale failures (will expire)
        detector.record_failure(base)
        detector.record_failure(base + timedelta(seconds=1))
        # Jump forward: stale failures fall outside window
        t_new = base + timedelta(seconds=40)
        detector.record_failure(t_new)
        detector.record_failure(t_new + timedelta(seconds=1))
        # Only 2 in-window — threshold not crossed
        assert not detector.is_loop_detected()
        # Third in-window failure — threshold crossed
        result = detector.record_failure(t_new + timedelta(seconds=2))
        assert result


# ---------------------------------------------------------------------------
# MemoryExhaustionDetector
# ---------------------------------------------------------------------------


@pytest.mark.constitutional
class TestMemoryExhaustionDetectorTrigger:
    def test_below_threshold_not_exhausted(self) -> None:
        detector = MemoryExhaustionDetector(_thresholds(memory_exhaustion_pct=85.0))
        assert not detector.update(84.9)
        assert not detector.is_exhausted()

    def test_at_threshold_triggers(self) -> None:
        detector = MemoryExhaustionDetector(_thresholds(memory_exhaustion_pct=85.0))
        assert detector.update(85.0)
        assert detector.is_exhausted()

    def test_above_threshold_triggers(self) -> None:
        detector = MemoryExhaustionDetector(_thresholds(memory_exhaustion_pct=85.0))
        assert detector.update(90.0)
        assert detector.is_exhausted()

    def test_initial_state_not_exhausted(self) -> None:
        detector = MemoryExhaustionDetector(_thresholds())
        assert not detector.is_exhausted()


@pytest.mark.constitutional
class TestMemoryExhaustionDetectorHysteresis:
    """Hysteresis: clears only when memory drops threshold - hysteresis_pct below."""

    def test_drops_to_just_above_clear_threshold_stays_exhausted(self) -> None:
        # threshold=85, hysteresis=10 → clear_threshold=75
        detector = MemoryExhaustionDetector(
            _thresholds(memory_exhaustion_pct=85.0, memory_hysteresis_pct=10.0)
        )
        detector.update(85.0)
        assert detector.is_exhausted()
        # Drop to 75.1 — still above clear threshold
        detector.update(75.1)
        assert detector.is_exhausted()

    def test_drops_to_clear_threshold_clears(self) -> None:
        # threshold=85, hysteresis=10 → clear_threshold=75
        detector = MemoryExhaustionDetector(
            _thresholds(memory_exhaustion_pct=85.0, memory_hysteresis_pct=10.0)
        )
        detector.update(85.0)
        assert detector.is_exhausted()
        # Drop to exactly 75.0 — should clear
        result = detector.update(75.0)
        assert not result
        assert not detector.is_exhausted()

    def test_drops_below_clear_threshold_clears(self) -> None:
        detector = MemoryExhaustionDetector(
            _thresholds(memory_exhaustion_pct=85.0, memory_hysteresis_pct=10.0)
        )
        detector.update(90.0)
        result = detector.update(60.0)
        assert not result
        assert not detector.is_exhausted()

    def test_oscillation_around_trigger_threshold_does_not_flap(self) -> None:
        """Memory oscillating around the trigger threshold should NOT flap.

        Once exhausted, the clear requires dropping to (threshold - hysteresis).
        """
        detector = MemoryExhaustionDetector(
            _thresholds(memory_exhaustion_pct=85.0, memory_hysteresis_pct=10.0)
        )
        # Trigger
        detector.update(86.0)
        assert detector.is_exhausted()
        # Drops slightly below trigger but above clear threshold — stays exhausted
        detector.update(84.5)
        assert detector.is_exhausted()
        # Rises again — still exhausted
        detector.update(86.0)
        assert detector.is_exhausted()

    def test_clears_then_retriggers(self) -> None:
        detector = MemoryExhaustionDetector(
            _thresholds(memory_exhaustion_pct=85.0, memory_hysteresis_pct=10.0)
        )
        detector.update(90.0)
        assert detector.is_exhausted()
        # Clear via hysteresis
        detector.update(70.0)
        assert not detector.is_exhausted()
        # Re-trigger
        result = detector.update(85.0)
        assert result
        assert detector.is_exhausted()


@pytest.mark.constitutional
class TestMemoryExhaustionDetectorReset:
    def test_reset_clears_exhausted_state(self) -> None:
        detector = MemoryExhaustionDetector(_thresholds(memory_exhaustion_pct=85.0))
        detector.update(90.0)
        assert detector.is_exhausted()
        detector.reset()
        assert not detector.is_exhausted()

    def test_reset_on_non_exhausted_is_noop(self) -> None:
        detector = MemoryExhaustionDetector(_thresholds())
        detector.reset()
        assert not detector.is_exhausted()
