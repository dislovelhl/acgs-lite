"""Quorum-based multi-agent decision gates for governance.

A ``QuorumGate`` blocks a governance action until at least *N* distinct agents
have cast approval votes.  Vetoes from any agent immediately close the gate as
rejected.  Expired gates (past deadline) auto-close as timed-out.

This complements Condorcet ranked-choice voting (voting.py) by providing a
simpler, threshold-based approval primitive for high-stakes decisions.

Example::

    from acgs_lite.constitution.quorum import QuorumGate, QuorumManager

    manager = QuorumManager()
    gate_id = manager.open(
        action="deploy-model-update",
        required_approvals=3,
        eligible_voters={"alice", "bob", "carol", "dave"},
    )

    manager.vote(gate_id, voter_id="alice", approve=True)
    manager.vote(gate_id, voter_id="bob",   approve=True)
    manager.vote(gate_id, voter_id="carol", approve=True)

    result = manager.status(gate_id)
    assert result.state == "approved"

"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class GateState(str, Enum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


@dataclass
class VoteRecord:
    """A single vote cast on a quorum gate.

    Attributes:
        voter_id: The agent that cast the vote.
        approve: True for approval, False for veto.
        timestamp: UTC ISO-8601 timestamp.
        note: Optional annotation.
    """

    voter_id: str
    approve: bool
    timestamp: str
    note: str = ""


@dataclass
class GateStatus:
    """Current status snapshot for a quorum gate.

    Attributes:
        gate_id: Unique gate identifier.
        action: The action being gated.
        state: One of ``open``, ``approved``, ``rejected``, ``timed_out``.
        required_approvals: Threshold needed for approval.
        approvals: Count of unique approval votes so far.
        vetoes: Count of veto votes so far.
        remaining: Approvals still needed (0 if already approved/rejected).
        deadline: ISO-8601 UTC deadline (empty string if no deadline).
    """

    gate_id: str
    action: str
    state: str
    required_approvals: int
    approvals: int
    vetoes: int
    remaining: int
    deadline: str


class _Gate:
    """Mutable runtime state for a single quorum gate (internal)."""

    __slots__ = (
        "gate_id",
        "action",
        "required_approvals",
        "eligible_voters",
        "deadline",
        "votes",
        "state",
        "metadata",
    )

    def __init__(
        self,
        gate_id: str,
        action: str,
        required_approvals: int,
        eligible_voters: set[str] | None,
        deadline: datetime | None,
        metadata: dict[str, Any],
    ) -> None:
        self.gate_id = gate_id
        self.action = action
        self.required_approvals = required_approvals
        self.eligible_voters: set[str] | None = eligible_voters
        self.deadline: datetime | None = deadline
        self.votes: list[VoteRecord] = []
        self.state: GateState = GateState.OPEN
        self.metadata: dict[str, Any] = metadata

    def _voter_ids(self) -> set[str]:
        return {v.voter_id for v in self.votes}

    def _approval_count(self) -> int:
        seen: set[str] = set()
        count = 0
        for v in self.votes:
            if v.voter_id not in seen and v.approve:
                count += 1
                seen.add(v.voter_id)
        return count

    def _veto_count(self) -> int:
        seen: set[str] = set()
        count = 0
        for v in self.votes:
            if v.voter_id not in seen and not v.approve:
                count += 1
                seen.add(v.voter_id)
        return count

    def check_timeout(self, now: datetime) -> bool:
        if self.deadline and now >= self.deadline and self.state == GateState.OPEN:
            self.state = GateState.TIMED_OUT
            return True
        return False

    def cast(self, voter_id: str, approve: bool, note: str, now: datetime) -> GateStatus:
        if self.state != GateState.OPEN:
            raise ValueError(
                f"Gate '{self.gate_id}' is already {self.state.value} — no further votes accepted"
            )
        self.check_timeout(now)
        if self.state != GateState.OPEN:
            raise ValueError(f"Gate '{self.gate_id}' timed out")

        if self.eligible_voters is not None and voter_id not in self.eligible_voters:
            raise ValueError(
                f"Voter '{voter_id}' is not in the eligible voter set for gate '{self.gate_id}'"
            )

        already_voted = {v.voter_id for v in self.votes}
        if voter_id in already_voted:
            raise ValueError(f"Voter '{voter_id}' has already voted on gate '{self.gate_id}'")

        self.votes.append(
            VoteRecord(voter_id=voter_id, approve=approve, timestamp=now.isoformat(), note=note)
        )

        if not approve:
            self.state = GateState.REJECTED
        elif self._approval_count() >= self.required_approvals:
            self.state = GateState.APPROVED

        return self._status(now)

    def _status(self, now: datetime) -> GateStatus:
        self.check_timeout(now)
        approvals = self._approval_count()
        vetoes = self._veto_count()
        return GateStatus(
            gate_id=self.gate_id,
            action=self.action,
            state=self.state.value,
            required_approvals=self.required_approvals,
            approvals=approvals,
            vetoes=vetoes,
            remaining=max(0, self.required_approvals - approvals),
            deadline=self.deadline.isoformat() if self.deadline else "",
        )


class QuorumManager:
    """Manages quorum gates for multi-agent governance decisions.

    A quorum gate blocks an action until *N* distinct eligible agents approve.
    Any single veto immediately closes the gate as rejected.

    Example::

        manager = QuorumManager()
        gid = manager.open("merge-policy-update", required_approvals=2)
        manager.vote(gid, voter_id="agent-a", approve=True)
        manager.vote(gid, voter_id="agent-b", approve=True)
        assert manager.status(gid).state == "approved"
    """

    def __init__(self) -> None:
        self._gates: dict[str, _Gate] = {}
        self._counter: int = 0

    def open(
        self,
        action: str,
        *,
        required_approvals: int = 1,
        eligible_voters: set[str] | None = None,
        timeout_minutes: float | None = None,
        gate_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        _now: datetime | None = None,
    ) -> str:
        """Open a new quorum gate and return its gate_id.

        Args:
            action: Human-readable description of the action being gated.
            required_approvals: Number of distinct approvals needed.
            eligible_voters: Set of allowed voter IDs (None = any voter allowed).
            timeout_minutes: Auto-close as timed_out after this many minutes.
            gate_id: Override auto-generated ID.
            metadata: Arbitrary key-value metadata.
            _now: Override current time (for testing).

        Raises:
            ValueError: If required_approvals < 1 or gate_id already exists.

        Returns:
            The gate_id string.
        """
        if required_approvals < 1:
            raise ValueError("required_approvals must be ≥ 1")
        now = _now or datetime.now(timezone.utc)
        if gate_id is None:
            self._counter += 1
            gate_id = f"gate-{self._counter:06d}"
        if gate_id in self._gates:
            raise ValueError(f"Gate '{gate_id}' already exists")
        deadline: datetime | None = None
        if timeout_minutes is not None:
            deadline = now + timedelta(minutes=timeout_minutes)
        self._gates[gate_id] = _Gate(
            gate_id=gate_id,
            action=action,
            required_approvals=required_approvals,
            eligible_voters=set(eligible_voters) if eligible_voters else None,
            deadline=deadline,
            metadata=metadata or {},
        )
        return gate_id

    def vote(
        self,
        gate_id: str,
        *,
        voter_id: str,
        approve: bool,
        note: str = "",
        _now: datetime | None = None,
    ) -> GateStatus:
        """Cast a vote on an open gate.

        Args:
            gate_id: The gate to vote on.
            voter_id: The voting agent's ID.
            approve: True for approval, False for veto.
            note: Optional annotation.
            _now: Override current time (for testing).

        Raises:
            KeyError: If gate_id not found.
            ValueError: If gate is not open, voter ineligible, or already voted.

        Returns:
            Updated :class:`GateStatus`.
        """
        if gate_id not in self._gates:
            raise KeyError(f"Gate '{gate_id}' not found")
        now = _now or datetime.now(timezone.utc)
        return self._gates[gate_id].cast(voter_id, approve, note, now)

    def status(self, gate_id: str, *, _now: datetime | None = None) -> GateStatus:
        """Return current status for *gate_id*.

        Raises:
            KeyError: If gate_id not found.
        """
        if gate_id not in self._gates:
            raise KeyError(f"Gate '{gate_id}' not found")
        now = _now or datetime.now(timezone.utc)
        return self._gates[gate_id]._status(now)

    def votes(self, gate_id: str) -> list[VoteRecord]:
        """Return all votes cast on *gate_id*.

        Raises:
            KeyError: If gate_id not found.
        """
        if gate_id not in self._gates:
            raise KeyError(f"Gate '{gate_id}' not found")
        return list(self._gates[gate_id].votes)

    def open_gates(self) -> list[str]:
        """Return IDs of all currently open gates."""
        return [gid for gid, g in self._gates.items() if g.state == GateState.OPEN]

    def list_gates(self) -> list[str]:
        """Return sorted list of all gate IDs."""
        return sorted(self._gates)

    def summary(self) -> dict[str, Any]:
        """Return an aggregate summary of all gates."""
        entries = []
        now = datetime.now(timezone.utc)
        for gid, gate in sorted(self._gates.items()):
            s = gate._status(now)
            entries.append(
                {
                    "gate_id": gid,
                    "action": gate.action,
                    "state": s.state,
                    "approvals": s.approvals,
                    "vetoes": s.vetoes,
                    "remaining": s.remaining,
                    "vote_count": len(gate.votes),
                }
            )
        open_count = sum(1 for e in entries if e["state"] == GateState.OPEN)
        return {
            "gate_count": len(self._gates),
            "open_count": open_count,
            "gates": entries,
        }
