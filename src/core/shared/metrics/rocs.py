"""
Return on Cognitive Spend (RoCS) — governance efficiency metric.

Constitutional Hash: cdd01ef066bc6cf2
Ref: solveeverything.org — RoCS replaces EBITDA as the primary signal
of solvency in the Intelligence Revolution.

For ACGS-2, RoCS measures governance value delivered per unit of
governance compute cost:

    RoCS = severity_weighted_correct_decisions / governance_compute_seconds

Where:
- Numerator: correct governance decisions weighted by severity
  (CRITICAL=10, HIGH=5, MEDIUM=2, LOW=1, ALLOW=1)
- Denominator: cumulative CPU seconds spent on constitutional
  validation + impact scoring

A higher RoCS means the governance infrastructure delivers more
safety value per unit of compute — the system is both correct and fast.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

# Severity weights for governance decisions
SEVERITY_WEIGHTS: dict[str, float] = {
    "critical": 10.0,
    "high": 5.0,
    "medium": 2.0,
    "low": 1.0,
    "allow": 1.0,  # Correct allow decisions have base value
}


@dataclass
class GovernanceSpend:
    """Cumulative governance compute cost.

    Tracks CPU time consumed by constitutional validation and
    impact scoring. Updated atomically via RoCSTracker.
    """

    validation_ns: int = 0
    scoring_ns: int = 0

    @property
    def total_ns(self) -> int:
        return self.validation_ns + self.scoring_ns

    @property
    def total_seconds(self) -> float:
        return self.total_ns / 1_000_000_000


@dataclass
class GovernanceValue:
    """Cumulative governance value delivered.

    Severity-weighted count of correct governance decisions.
    """

    total_weighted: float = 0.0
    decisions: int = 0
    violations_caught: int = 0


@dataclass
class RoCSSnapshot:
    """Point-in-time RoCS measurement."""

    rocs: float
    spend: GovernanceSpend
    value: GovernanceValue
    timestamp_ns: int = field(default_factory=time.time_ns)


class RoCSTracker:
    """Thread-safe tracker for Return on Cognitive Spend.

    Usage::

        tracker = RoCSTracker()

        # Record a governance decision
        start = time.perf_counter_ns()
        result = engine.validate(action)
        elapsed = time.perf_counter_ns() - start
        tracker.record_validation(elapsed_ns=elapsed, severity="critical", correct=True)

        # Record impact scoring
        start = time.perf_counter_ns()
        score = scorer.calculate_impact_score(msg, ctx)
        elapsed = time.perf_counter_ns() - start
        tracker.record_scoring(elapsed_ns=elapsed)

        # Read current RoCS
        snapshot = tracker.snapshot()
        print(f"RoCS: {snapshot.rocs:.2f} value/sec")
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spend = GovernanceSpend()
        self._value = GovernanceValue()

    def record_validation(
        self,
        elapsed_ns: int,
        severity: str = "allow",
        correct: bool = True,
    ) -> None:
        """Record a constitutional validation decision.

        Args:
            elapsed_ns: CPU nanoseconds consumed by validation.
            severity: Severity of the decision outcome (critical/high/medium/low/allow).
            correct: Whether the decision was correct (not overridden).
        """
        weight = SEVERITY_WEIGHTS.get(severity.lower(), 1.0) if correct else 0.0
        with self._lock:
            self._spend.validation_ns += elapsed_ns
            self._value.decisions += 1
            self._value.total_weighted += weight
            if severity.lower() not in ("allow",) and correct:
                self._value.violations_caught += 1

    def record_scoring(self, elapsed_ns: int) -> None:
        """Record impact scoring compute cost.

        Args:
            elapsed_ns: CPU nanoseconds consumed by impact scoring.
        """
        with self._lock:
            self._spend.scoring_ns += elapsed_ns

    def snapshot(self) -> RoCSSnapshot:
        """Take a point-in-time RoCS measurement.

        Returns:
            RoCSSnapshot with current RoCS ratio, spend, and value.
            RoCS is 0.0 when no compute has been spent.
        """
        with self._lock:
            spend = GovernanceSpend(
                validation_ns=self._spend.validation_ns,
                scoring_ns=self._spend.scoring_ns,
            )
            value = GovernanceValue(
                total_weighted=self._value.total_weighted,
                decisions=self._value.decisions,
                violations_caught=self._value.violations_caught,
            )

        total_s = spend.total_seconds
        rocs = value.total_weighted / total_s if total_s > 0 else 0.0

        return RoCSSnapshot(rocs=rocs, spend=spend, value=value)

    def to_dict(self) -> dict[str, float | int]:
        """Serialize current state for metrics/API exposure."""
        snap = self.snapshot()
        return {
            "rocs": snap.rocs,
            "governance_value_weighted": snap.value.total_weighted,
            "governance_decisions": snap.value.decisions,
            "violations_caught": snap.value.violations_caught,
            "validation_ns": snap.spend.validation_ns,
            "scoring_ns": snap.spend.scoring_ns,
            "total_compute_seconds": snap.spend.total_seconds,
        }

    def reset(self) -> None:
        """Reset all counters. Intended for testing."""
        with self._lock:
            self._spend = GovernanceSpend()
            self._value = GovernanceValue()


# Module-level singleton for process-wide RoCS tracking
_global_tracker: RoCSTracker | None = None
_global_lock = threading.Lock()


def get_rocs_tracker() -> RoCSTracker:
    """Get the process-wide RoCS tracker singleton."""
    global _global_tracker
    if _global_tracker is None:
        with _global_lock:
            if _global_tracker is None:
                _global_tracker = RoCSTracker()
    return _global_tracker


def reset_rocs_tracker() -> None:
    """Reset the global RoCS tracker. Intended for testing."""
    global _global_tracker
    with _global_lock:
        _global_tracker = None
