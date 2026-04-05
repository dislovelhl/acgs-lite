"""
ACGS-2 Temporal Fixtures
Constitutional Hash: 608508a9bd224290

Fixtures for timeline ordering, causal validation, and temporal consistency testing.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

import pytest

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class TemporalViolationType(Enum):
    """Types of temporal violations."""

    CAUSALITY = "causality"  # Effect before cause
    ORDERING = "ordering"  # Out-of-order events
    CLOCK_SKEW = "clock_skew"  # Timestamp inconsistency
    FUTURE_EVENT = "future_event"  # Event in the future


@dataclass
class TemporalEvent:
    """An event with temporal properties for spec testing."""

    id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    causes: set[str] = field(default_factory=set)
    effects: set[str] = field(default_factory=set)
    metadata: JSONDict = field(default_factory=dict)

    def happens_before(self, other: "TemporalEvent") -> bool:
        """Check if this event happens before another."""
        return self.timestamp < other.timestamp

    def is_cause_of(self, other: "TemporalEvent") -> bool:
        """Check if this event is a cause of another."""
        return other.id in self.effects or self.id in other.causes


@dataclass
class TemporalViolation:
    """Record of a temporal violation."""

    violation_type: TemporalViolationType
    event_a: str
    event_b: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


class SpecTimeline:
    """
    Timeline manager for specification testing.

    Provides ordering guarantees and causality validation for events
    in executable specifications.
    """

    def __init__(self):
        self.events: dict[str, TemporalEvent] = {}
        self.order: list[str] = []
        self.violations: list[TemporalViolation] = []
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def record(
        self,
        event_id: str,
        timestamp: datetime | None = None,
        causes: set[str] | None = None,
    ) -> TemporalEvent:
        """
        Record an event in the timeline.

        Args:
            event_id: Unique event identifier
            timestamp: Optional explicit timestamp
            causes: Optional set of event IDs that caused this event

        Returns:
            The recorded TemporalEvent
        """
        event = TemporalEvent(
            id=event_id,
            timestamp=timestamp or datetime.now(UTC),
            causes=causes or set(),
        )

        # Update effects on causal events
        for cause_id in event.causes:
            if cause_id in self.events:
                self.events[cause_id].effects.add(event_id)

        self.events[event_id] = event
        self.order.append(event_id)
        return event

    def get_event(self, event_id: str) -> TemporalEvent | None:
        """Get an event by ID."""
        return self.events.get(event_id)

    def happened_before(self, event_a: str, event_b: str) -> bool:
        """
        Check if event_a happened before event_b.

        Uses Lamport-style ordering based on timestamps.
        """
        a = self.events.get(event_a)
        b = self.events.get(event_b)

        if not a or not b:
            return False

        return a.timestamp < b.timestamp

    def get_order(self) -> list[str]:
        """Get events in recorded order."""
        return self.order.copy()

    def get_sorted_events(self) -> list[TemporalEvent]:
        """Get events sorted by timestamp."""
        return sorted(self.events.values(), key=lambda e: e.timestamp)

    def clear(self) -> None:
        """Clear all events and violations."""
        self.events.clear()
        self.order.clear()
        self.violations.clear()


class CausalValidator:
    """
    Validator for causal relationships in specification testing.

    Ensures cause-effect relationships respect temporal ordering
    and detects causality violations.
    """

    def __init__(self, timeline: SpecTimeline | None = None):
        self.timeline = timeline or SpecTimeline()
        self.violations: list[TemporalViolation] = []
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def validate_causality(
        self,
        cause_id: str,
        effect_id: str,
    ) -> bool:
        """
        Validate that cause happens before effect.

        Args:
            cause_id: ID of the causing event
            effect_id: ID of the effect event

        Returns:
            True if causality is valid, False otherwise
        """
        cause = self.timeline.get_event(cause_id)
        effect = self.timeline.get_event(effect_id)

        if not cause or not effect:
            return False

        # Check temporal ordering
        if not cause.happens_before(effect):
            violation = TemporalViolation(
                violation_type=TemporalViolationType.CAUSALITY,
                event_a=cause_id,
                event_b=effect_id,
                message=f"Cause '{cause_id}' does not precede effect '{effect_id}'",
            )
            self.violations.append(violation)
            self.timeline.violations.append(violation)
            return False

        return True

    def validate_chain(
        self,
        event_ids: list[str],
    ) -> tuple[bool, list[TemporalViolation]]:
        """
        Validate a causal chain of events.

        Args:
            event_ids: List of event IDs in expected causal order

        Returns:
            Tuple of (is_valid, list of violations)
        """
        chain_violations = []

        for i in range(len(event_ids) - 1):
            if not self.validate_causality(event_ids[i], event_ids[i + 1]):
                chain_violations.append(self.violations[-1])

        return len(chain_violations) == 0, chain_violations

    def check_ordering(
        self,
        expected_order: list[str],
    ) -> bool:
        """
        Check if events occurred in expected order.

        Args:
            expected_order: List of event IDs in expected order

        Returns:
            True if order matches, False otherwise
        """
        events = [self.timeline.get_event(e) for e in expected_order]

        if any(e is None for e in events):
            return False

        for i in range(len(events) - 1):
            if not events[i].happens_before(events[i + 1]):
                violation = TemporalViolation(
                    violation_type=TemporalViolationType.ORDERING,
                    event_a=expected_order[i],
                    event_b=expected_order[i + 1],
                    message=f"Event '{expected_order[i]}' should precede '{expected_order[i + 1]}'",
                )
                self.violations.append(violation)
                self.timeline.violations.append(violation)
                return False

        return True

    def detect_future_events(self) -> list[TemporalEvent]:
        """
        Detect events with future timestamps.

        Returns:
            List of events with timestamps in the future
        """
        now = datetime.now(UTC)
        future_events = []

        for event in self.timeline.events.values():
            if event.timestamp > now:
                violation = TemporalViolation(
                    violation_type=TemporalViolationType.FUTURE_EVENT,
                    event_a=event.id,
                    event_b="now",
                    message=f"Event '{event.id}' has future timestamp",
                )
                self.violations.append(violation)
                future_events.append(event)

        return future_events

    def get_violations(self) -> list[TemporalViolation]:
        """Get all detected violations."""
        return self.violations.copy()

    def is_valid(self) -> bool:
        """Check if no violations have been detected."""
        return len(self.violations) == 0

    def reset(self) -> None:
        """Reset validator state."""
        self.violations.clear()


@pytest.fixture
def timeline() -> SpecTimeline:
    """
    Fixture providing a timeline for spec testing.

    Use in tests verifying temporal ordering:
        def test_event_order(timeline):
            timeline.record("A")
            timeline.record("B")
            assert timeline.happened_before("A", "B")
    """
    return SpecTimeline()


@pytest.fixture
def causal_validator(timeline: SpecTimeline) -> CausalValidator:
    """
    Fixture providing a causal validator for spec testing.

    Use in tests verifying causality:
        def test_causality(causal_validator, timeline):
            timeline.record("cause")
            timeline.record("effect", causes={"cause"})
            assert causal_validator.validate_causality("cause", "effect")
    """
    return CausalValidator(timeline)
