"""
Pro2Guard-inspired execution trace collector for DTMC training.

Mines GovernanceDecision histories and BlockchainLedger audit entries to produce
labelled TrajectoryRecord instances for DTMC transition-matrix learning.

A trajectory is unsafe if:
- any step was explicitly blocked (action_allowed=False), OR
- the trajectory terminates in a HIGH or CRITICAL ImpactLevel state.

Usage::

    collector = TraceCollector()
    records = collector.collect_from_decision_history(engine.decision_history)
    dtmc.fit(records)

Constitutional Hash: cdd01ef066bc6cf2
NIST 800-53 SI-3, AU-9 — System / Information Integrity, Audit Protection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.core.shared.types import JSONDict

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import GovernanceDecision, ImpactLevel

logger = get_logger(__name__)
# ---------------------------------------------------------------------------
# State-space constants
# ---------------------------------------------------------------------------

#: Number of DTMC states (one per ImpactLevel ordinal)
N_STATES: int = 5

#: ImpactLevel → DTMC state index
IMPACT_TO_STATE: dict[ImpactLevel, int] = {
    ImpactLevel.NEGLIGIBLE: 0,
    ImpactLevel.LOW: 1,
    ImpactLevel.MEDIUM: 2,
    ImpactLevel.HIGH: 3,
    ImpactLevel.CRITICAL: 4,
}

#: DTMC state index → ImpactLevel
STATE_TO_IMPACT: dict[int, ImpactLevel] = {v: k for k, v in IMPACT_TO_STATE.items()}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TrajectoryRecord:
    """A single labelled execution trajectory for DTMC training.

    Attributes:
        states: Sequence of ImpactLevel ordinal values (0=NEGLIGIBLE … 4=CRITICAL).
            Must be non-empty; each value must be in [0, N_STATES).
        terminal_unsafe: True if the trajectory ended in a governance block
            or a HIGH/CRITICAL ImpactLevel state.
        session_id: Optional session identifier for grouping trajectories.
        timestamp: ISO 8601 timezone.utc timestamp of the trajectory's last event.
        metadata: Arbitrary key-value diagnostics (source, version, etc.).
    """

    states: list[int]
    terminal_unsafe: bool
    session_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.states:
            raise ValueError("TrajectoryRecord.states must be non-empty")
        for s in self.states:
            if not (0 <= s < N_STATES):
                raise ValueError(
                    f"State value {s!r} out of range [0, {N_STATES - 1}]; "
                    f"use IMPACT_TO_STATE to convert ImpactLevel values"
                )


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


class TraceCollector:
    """Converts governance histories and audit ledger blocks into TrajectoryRecord lists.

    Two collection modes:

    1. **Decision history** (``collect_from_decision_history``): mines a
       ``list[GovernanceDecision]`` from ``AdaptiveGovernanceEngine.decision_history``.
       Sequences of consecutive decisions are grouped; a new trajectory begins
       whenever a HIGH/CRITICAL state is reached (natural session break).

    2. **Blockchain ledger** (``collect_from_ledger_blocks``): mines raw
       ``BlockchainLedger.blocks`` list. The impact state is *inferred* from
       ``allowed`` flag and ``processing_time_ms`` in each audit entry.
    """

    #: ImpactLevel values considered unsafe terminal states
    UNSAFE_TERMINAL_STATES: frozenset[ImpactLevel] = frozenset(
        {ImpactLevel.HIGH, ImpactLevel.CRITICAL}
    )

    # ------------------------------------------------------------------
    # Public collection methods
    # ------------------------------------------------------------------

    def collect_from_decision_history(
        self,
        decisions: list[GovernanceDecision],
        session_id: str | None = None,
        min_length: int = 2,
    ) -> list[TrajectoryRecord]:
        """Convert a flat GovernanceDecision list into trajectory records.

        A trajectory ends (and a new one begins) whenever the current decision
        reaches a HIGH or CRITICAL impact level — mirroring the "unsafe terminal
        event" concept from Pro2Guard.

        Args:
            decisions: Ordered sequence of governance decisions (oldest first).
            session_id: Optional label attached to every produced record.
            min_length: Minimum number of steps required to emit a record.
                Trajectories shorter than this are discarded (noise filter).

        Returns:
            List of labelled TrajectoryRecord instances; empty if insufficient data.
        """
        if len(decisions) < min_length:
            logger.debug(
                "TraceCollector: only %d decisions — below min_length=%d; skipping",
                len(decisions),
                min_length,
            )
            return []

        records: list[TrajectoryRecord] = []
        current: list[GovernanceDecision] = []

        for decision in decisions:
            current.append(decision)

            # Trajectory boundary: flush on unsafe terminal state
            if decision.impact_level in self.UNSAFE_TERMINAL_STATES:
                if len(current) >= min_length:
                    records.append(self._build_record(current, session_id))
                current = []

        # Flush remaining decisions as a (potentially safe) trajectory
        if len(current) >= min_length:
            records.append(self._build_record(current, session_id))

        logger.debug(
            "TraceCollector: extracted %d trajectories from %d decisions",
            len(records),
            len(decisions),
        )
        return records

    def collect_from_ledger_blocks(
        self,
        blocks: list[dict],
        min_length: int = 2,
    ) -> list[TrajectoryRecord]:
        """Extract trajectory records from a BlockchainLedger blocks list.

        Skips the genesis block.  The DTMC state for each audit entry is
        *inferred* from ``allowed``, ``violations``, and ``processing_time_ms``
        via :meth:`_entry_to_state`.

        Args:
            blocks: List of raw ledger block dicts (as returned by
                ``BlockchainLedger.blocks``).
            min_length: Minimum trajectory length to emit.

        Returns:
            List of labelled TrajectoryRecord instances.
        """
        audit_entries = [
            b["data"]
            for b in blocks
            if isinstance(b.get("data"), dict) and b["data"].get("type") != "genesis"
        ]

        if len(audit_entries) < min_length:
            return []

        records: list[TrajectoryRecord] = []
        current_states: list[int] = []

        for entry in audit_entries:
            state = self._entry_to_state(entry)
            current_states.append(state)

            # Flush at unsafe states
            if state >= IMPACT_TO_STATE[ImpactLevel.HIGH]:
                if len(current_states) >= min_length:
                    records.append(
                        TrajectoryRecord(
                            states=current_states[:],
                            terminal_unsafe=True,
                            metadata={"source": "blockchain_ledger"},
                        )
                    )
                current_states = []

        # Flush remaining as safe trajectory
        if len(current_states) >= min_length:
            records.append(
                TrajectoryRecord(
                    states=current_states[:],
                    terminal_unsafe=False,
                    metadata={"source": "blockchain_ledger"},
                )
            )

        logger.debug(
            "TraceCollector: extracted %d trajectories from %d ledger entries",
            len(records),
            len(audit_entries),
        )
        return records

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_record(
        self,
        decisions: list[GovernanceDecision],
        session_id: str | None,
    ) -> TrajectoryRecord:
        """Build a TrajectoryRecord from a sequence of GovernanceDecision objects."""
        states = [IMPACT_TO_STATE[d.impact_level] for d in decisions]
        last = decisions[-1]
        terminal_unsafe = (
            last.impact_level in self.UNSAFE_TERMINAL_STATES or not last.action_allowed
        )
        ts = (
            last.timestamp.isoformat()
            if isinstance(last.timestamp, datetime)
            else str(last.timestamp)
        )
        return TrajectoryRecord(
            states=states,
            terminal_unsafe=terminal_unsafe,
            session_id=session_id,
            timestamp=ts,
        )

    @staticmethod
    def _entry_to_state(entry: dict) -> int:
        """Infer DTMC state (ImpactLevel ordinal) from a blockchain audit entry.

        Heuristic rules (deterministic, O(1)):
        - Blocked with >1 violations → CRITICAL
        - Blocked with ≤1 violations → HIGH
        - Allowed, slow (>5 ms)     → MEDIUM
        - Allowed, moderate (>1 ms) → LOW
        - Allowed, fast (≤1 ms)     → NEGLIGIBLE
        """
        if not entry.get("allowed", True):
            violations = entry.get("violations", [])
            if len(violations) > 1:
                return IMPACT_TO_STATE[ImpactLevel.CRITICAL]
            return IMPACT_TO_STATE[ImpactLevel.HIGH]

        processing_time: float = float(entry.get("processing_time_ms", 0.0))
        if processing_time > 5.0:
            return IMPACT_TO_STATE[ImpactLevel.MEDIUM]
        if processing_time > 1.0:
            return IMPACT_TO_STATE[ImpactLevel.LOW]
        return IMPACT_TO_STATE[ImpactLevel.NEGLIGIBLE]
