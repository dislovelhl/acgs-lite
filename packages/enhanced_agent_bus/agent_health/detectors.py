"""
Agent Health — Failure and Memory Detectors.
Constitutional Hash: 608508a9bd224290

Pure stateful detector classes with no I/O.  All I/O (Redis writes, metric
emission, healing dispatch) happens in monitor.py and healing_engine.py.

Classes:
    FailureLoopDetector  — sliding-window consecutive-failure counter
    MemoryExhaustionDetector — threshold + hysteresis state machine
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from enhanced_agent_bus.agent_health.models import AgentHealthThresholds


class FailureLoopDetector:
    """Detects continuous failure loops using a sliding time window.

    A loop is detected when the number of recorded failures within
    ``thresholds.failure_window_seconds`` reaches or exceeds
    ``thresholds.failure_count_threshold``.

    Detection is immediate: ``record_failure`` returns ``True`` on the exact
    call that crosses the threshold, contributing to the NFR-002 requirement
    of initiating healing within 10 seconds of the threshold being crossed.

    The detector is stateful but has no I/O; callers supply ``datetime``
    timestamps so the class is fully deterministic in tests.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, thresholds: AgentHealthThresholds) -> None:
        self._thresholds = thresholds
        self._failure_timestamps: deque[datetime] = deque()
        self._loop_detected: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_failure(self, timestamp: datetime) -> bool:
        """Record a failure event at *timestamp* and return True if a loop is now detected.

        Only failures within the configured sliding window are counted;
        older timestamps are pruned before evaluating the threshold.
        """
        self._failure_timestamps.append(timestamp)
        self._prune_window(timestamp)
        if len(self._failure_timestamps) >= self._thresholds.failure_count_threshold:
            self._loop_detected = True
        return self._loop_detected

    def record_success(self) -> None:
        """Record a successful operation, clearing all failure history.

        After a success the consecutive failure streak resets to zero and
        any previously detected loop is cleared.
        """
        self._failure_timestamps.clear()
        self._loop_detected = False

    def is_loop_detected(self) -> bool:
        """Return True if a failure loop was detected in the current window."""
        return self._loop_detected

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prune_window(self, now: datetime) -> None:
        """Remove timestamps that have fallen outside the sliding window."""
        window = timedelta(seconds=self._thresholds.failure_window_seconds)
        cutoff = now - window
        while self._failure_timestamps and self._failure_timestamps[0] <= cutoff:
            self._failure_timestamps.popleft()


class MemoryExhaustionDetector:
    """Detects memory exhaustion with hysteresis to prevent threshold flapping.

    Transitions:
        NOT exhausted  → EXHAUSTED when memory_pct >= exhaustion_threshold
        EXHAUSTED      → NOT exhausted when memory_pct <= (exhaustion_threshold
                         - hysteresis_pct)

    This 10-percentage-point clearance matches common system-level conventions
    and directly implements the edge-case requirement from the spec (edge case 4).

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, thresholds: AgentHealthThresholds) -> None:
        self._thresholds = thresholds
        self._exhausted: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, memory_pct: float) -> bool:
        """Update the detector state with a new memory reading.

        Returns True if the agent is currently considered memory-exhausted.
        """
        if not self._exhausted:
            if memory_pct >= self._thresholds.memory_exhaustion_pct:
                self._exhausted = True
        else:
            clear_threshold = (
                self._thresholds.memory_exhaustion_pct - self._thresholds.memory_hysteresis_pct
            )
            if memory_pct <= clear_threshold:
                self._exhausted = False
        return self._exhausted

    def is_exhausted(self) -> bool:
        """Return True if memory exhaustion is currently detected."""
        return self._exhausted

    def reset(self) -> None:
        """Unconditionally clear the exhausted state (e.g. after agent restart)."""
        self._exhausted = False


__all__ = [
    "FailureLoopDetector",
    "MemoryExhaustionDetector",
]
