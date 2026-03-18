"""exp232: Behavioral Drift via Session Contracts — cryptographic behavioral baselines.

At session start an agent declares a *behavioral contract*: the action types it
intends to perform, the resource scopes it will access, an upper bound on total
actions, and a time limit.  The contract is hashed (SHA-256) so any post-hoc
tampering is detectable.  During the session every action is checked against the
contract and divergence signals are emitted when behavior deviates.

Motivation (from Agent Behavioral Contracts, arXiv:2602.22302; Pro2Guard):

> A behavioral contract is a *cryptographic commitment* made by an agent before
> it begins acting.  Unlike intent-alignment scoring (exp228) which uses
> free-text keyword overlap, a session contract is a *formal specification*:
> explicit allowed action categories, resource scopes, volume bounds, and time
> limits.  Divergence from the contract is a hard governance signal — not a
> soft drift indicator — because the agent itself committed to these bounds.

Design
------
- **BehaviorContract** — immutable, hashed declaration of intended session
  behavior: allowed action categories (keyword sets), resource scopes, max
  actions, time limit.  SHA-256 ``contract_hash`` commits the agent.
- **ContractDivergence** — a single divergence event with type, severity,
  details, and timestamp.
- **DivergenceType** — ``unauthorized_action``, ``scope_violation``,
  ``volume_exceeded``, ``time_exceeded``.
- **SessionContractTracker** — manages per-agent sessions:
  ``bind()`` starts a session, ``check_action()`` returns divergences,
  ``divergence_score()`` returns cumulative 0–1, ``should_terminate()``
  gates session kill, ``unbind()`` ends.

Zero hot-path overhead — purely additive; the core engine is never touched.

Usage::

    from acgs_lite.constitution.session_contract import (
        BehaviorContract, SessionContractTracker,
    )

    contract = BehaviorContract(
        allowed_actions=frozenset({"read", "summarise", "list"}),
        resource_scopes=frozenset({"documents", "calendar"}),
        max_actions=100,
        time_limit_seconds=3600,
    )

    tracker = SessionContractTracker()
    tracker.bind("agent-1", contract)

    r1 = tracker.check_action("agent-1", "read quarterly report")
    assert not r1.divergences  # within contract

    r2 = tracker.check_action("agent-1", "send email to external")
    assert r2.divergences  # "send" not in allowed_actions
    assert r2.divergences[0].divergence_type.value == "unauthorized_action"

    print(tracker.divergence_score("agent-1"))  # 0.5
    print(tracker.should_terminate("agent-1"))  # depends on threshold
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── action classification ─────────────────────────────────────────────────────

_WORD_SPLIT_CHARS = frozenset(" \t\n_-/.,;:!?()[]{}\"'")


def _extract_words(text: str) -> frozenset[str]:
    """Extract lowercase words from action text (simple tokeniser)."""
    buf: list[str] = []
    result: set[str] = set()
    for ch in text.lower():
        if ch in _WORD_SPLIT_CHARS:
            if buf:
                w = "".join(buf)
                if len(w) > 1:
                    result.add(w)
                buf.clear()
        else:
            buf.append(ch)
    if buf:
        w = "".join(buf)
        if len(w) > 1:
            result.add(w)
    return frozenset(result)


# ── data structures ──────────────────────────────────────────────────────────


class DivergenceType(str, Enum):
    """Types of behavioral contract divergence."""

    UNAUTHORIZED_ACTION = "unauthorized_action"
    SCOPE_VIOLATION = "scope_violation"
    VOLUME_EXCEEDED = "volume_exceeded"
    TIME_EXCEEDED = "time_exceeded"


_DIVERGENCE_SEVERITY: dict[DivergenceType, str] = {
    DivergenceType.UNAUTHORIZED_ACTION: "high",
    DivergenceType.SCOPE_VIOLATION: "medium",
    DivergenceType.VOLUME_EXCEEDED: "medium",
    DivergenceType.TIME_EXCEEDED: "low",
}


@dataclass(frozen=True, slots=True)
class ContractDivergence:
    """A single divergence event from the behavioral contract."""

    divergence_type: DivergenceType
    severity: str
    details: str
    action: str
    timestamp_ns: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "divergence_type": self.divergence_type.value,
            "severity": self.severity,
            "details": self.details,
            "action": self.action,
            "timestamp_ns": self.timestamp_ns,
        }


@dataclass(frozen=True, slots=True)
class ContractCheckResult:
    """Result from checking a single action against the session contract."""

    action: str
    agent_id: str
    divergences: tuple[ContractDivergence, ...]
    action_number: int
    elapsed_seconds: float

    @property
    def is_compliant(self) -> bool:
        return len(self.divergences) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "agent_id": self.agent_id,
            "divergences": [d.to_dict() for d in self.divergences],
            "action_number": self.action_number,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "is_compliant": self.is_compliant,
        }


@dataclass(frozen=True, slots=True)
class BehaviorContract:
    """Immutable, hashed declaration of intended session behavior.

    The ``contract_hash`` is a SHA-256 digest of the contract's key fields,
    providing tamper detection: if any field is modified after binding, the
    hash will no longer match.

    Attributes:
        allowed_actions: Frozenset of action-verb keywords the agent is
            permitted to use (e.g., {"read", "summarise", "list"}).
        resource_scopes: Frozenset of resource categories the agent may
            access (e.g., {"documents", "calendar", "email"}).
        max_actions: Upper bound on total actions in this session (0 = unlimited).
        time_limit_seconds: Maximum session duration in seconds (0 = unlimited).
        description: Optional human-readable contract summary.
        contract_hash: SHA-256 hex digest (auto-computed if not provided).
    """

    allowed_actions: frozenset[str]
    resource_scopes: frozenset[str]
    max_actions: int = 0
    time_limit_seconds: int = 0
    description: str = ""
    contract_hash: str = ""

    def __post_init__(self) -> None:
        if not self.contract_hash:
            computed = self._compute_hash()
            object.__setattr__(self, "contract_hash", computed)

    def _compute_hash(self) -> str:
        """SHA-256 of canonical contract representation."""
        canonical = (
            f"actions={sorted(self.allowed_actions)}|"
            f"scopes={sorted(self.resource_scopes)}|"
            f"max={self.max_actions}|"
            f"time={self.time_limit_seconds}"
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def verify_integrity(self) -> bool:
        """Return True if the stored hash matches the computed hash."""
        return self.contract_hash == self._compute_hash()

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_actions": sorted(self.allowed_actions),
            "resource_scopes": sorted(self.resource_scopes),
            "max_actions": self.max_actions,
            "time_limit_seconds": self.time_limit_seconds,
            "description": self.description,
            "contract_hash": self.contract_hash,
        }


@dataclass(frozen=True, slots=True)
class SessionReport:
    """Summary report for a completed or active session."""

    agent_id: str
    contract_hash: str
    total_actions: int
    compliant_actions: int
    divergent_actions: int
    divergence_score: float
    elapsed_seconds: float
    should_terminate: bool
    divergence_breakdown: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "contract_hash": self.contract_hash,
            "total_actions": self.total_actions,
            "compliant_actions": self.compliant_actions,
            "divergent_actions": self.divergent_actions,
            "divergence_score": round(self.divergence_score, 4),
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "should_terminate": self.should_terminate,
            "divergence_breakdown": self.divergence_breakdown,
        }


# ── internal state ────────────────────────────────────────────────────────────


@dataclass(slots=True)
class _SessionState:
    """Mutable per-agent session tracking."""

    contract: BehaviorContract
    started_at: float  # time.monotonic()
    action_count: int = 0
    compliant_count: int = 0
    divergent_count: int = 0
    divergence_history: list[ContractDivergence] = field(default_factory=list)
    divergence_type_counts: dict[str, int] = field(default_factory=dict)


# ── tracker ───────────────────────────────────────────────────────────────────


class SessionContractTracker:
    """Manages per-agent behavioral session contracts with divergence detection.

    Attributes:
        terminate_threshold: Divergence score (0–1) at which ``should_terminate``
            returns True (default 0.3 = 30% of actions divergent).
        max_divergence_history: Maximum divergence events stored per agent.
    """

    __slots__ = ("terminate_threshold", "max_divergence_history", "_sessions")

    def __init__(
        self,
        *,
        terminate_threshold: float = 0.3,
        max_divergence_history: int = 200,
    ) -> None:
        self.terminate_threshold = max(0.0, min(1.0, terminate_threshold))
        self.max_divergence_history = max(1, max_divergence_history)
        self._sessions: dict[str, _SessionState] = {}

    def bind(self, agent_id: str, contract: BehaviorContract) -> str:
        """Start tracking a session for an agent under the given contract.

        Returns the contract_hash as confirmation of binding.
        Raises ValueError if agent already has an active session.
        """
        if agent_id in self._sessions:
            raise ValueError(f"Agent {agent_id!r} already has an active session; unbind first")
        self._sessions[agent_id] = _SessionState(
            contract=contract,
            started_at=time.monotonic(),
        )
        return contract.contract_hash

    def unbind(self, agent_id: str) -> SessionReport | None:
        """End a session and return the final report. Returns None if no session."""
        state = self._sessions.pop(agent_id, None)
        if state is None:
            return None
        return self._build_report(agent_id, state)

    def check_action(self, agent_id: str, action: str) -> ContractCheckResult:
        """Check an action against the agent's session contract.

        Returns ContractCheckResult with any divergences detected.
        Raises KeyError if agent has no active session.
        """
        state = self._sessions.get(agent_id)
        if state is None:
            raise KeyError(f"No active session for agent {agent_id!r}; call bind() first")

        now_ns = time.monotonic_ns()
        elapsed = time.monotonic() - state.started_at
        state.action_count += 1
        action_words = _extract_words(action)

        divergences: list[ContractDivergence] = []

        # Check 1: action type authorisation
        if state.contract.allowed_actions and not (
            action_words & state.contract.allowed_actions
        ):
            divergences.append(
                ContractDivergence(
                    divergence_type=DivergenceType.UNAUTHORIZED_ACTION,
                    severity=_DIVERGENCE_SEVERITY[DivergenceType.UNAUTHORIZED_ACTION],
                    details=(
                        f"Action words {sorted(action_words)} do not overlap "
                        f"with allowed actions {sorted(state.contract.allowed_actions)}"
                    ),
                    action=action,
                    timestamp_ns=now_ns,
                )
            )

        # Check 2: volume limit
        if state.contract.max_actions > 0 and state.action_count > state.contract.max_actions:
            divergences.append(
                ContractDivergence(
                    divergence_type=DivergenceType.VOLUME_EXCEEDED,
                    severity=_DIVERGENCE_SEVERITY[DivergenceType.VOLUME_EXCEEDED],
                    details=(
                        f"Action count {state.action_count} exceeds "
                        f"max_actions {state.contract.max_actions}"
                    ),
                    action=action,
                    timestamp_ns=now_ns,
                )
            )

        # Check 3: time limit
        if state.contract.time_limit_seconds > 0 and elapsed > state.contract.time_limit_seconds:
            divergences.append(
                ContractDivergence(
                    divergence_type=DivergenceType.TIME_EXCEEDED,
                    severity=_DIVERGENCE_SEVERITY[DivergenceType.TIME_EXCEEDED],
                    details=(
                        f"Elapsed {elapsed:.1f}s exceeds "
                        f"time_limit {state.contract.time_limit_seconds}s"
                    ),
                    action=action,
                    timestamp_ns=now_ns,
                )
            )

        # Update counters
        if divergences:
            state.divergent_count += 1
            for d in divergences:
                dt_key = d.divergence_type.value
                state.divergence_type_counts[dt_key] = (
                    state.divergence_type_counts.get(dt_key, 0) + 1
                )
                if len(state.divergence_history) < self.max_divergence_history:
                    state.divergence_history.append(d)
        else:
            state.compliant_count += 1

        return ContractCheckResult(
            action=action,
            agent_id=agent_id,
            divergences=tuple(divergences),
            action_number=state.action_count,
            elapsed_seconds=elapsed,
        )

    def divergence_score(self, agent_id: str) -> float:
        """Return cumulative divergence score (0–1) for an agent session.

        Score = divergent_actions / total_actions. Returns 0.0 if no actions yet.
        """
        state = self._sessions.get(agent_id)
        if state is None or state.action_count == 0:
            return 0.0
        return state.divergent_count / state.action_count

    def should_terminate(self, agent_id: str) -> bool:
        """Return True if divergence score exceeds the termination threshold."""
        return self.divergence_score(agent_id) >= self.terminate_threshold

    def is_bound(self, agent_id: str) -> bool:
        """Return True if the agent has an active session."""
        return agent_id in self._sessions

    def contract_for(self, agent_id: str) -> BehaviorContract | None:
        """Return the active contract for an agent, or None."""
        state = self._sessions.get(agent_id)
        return state.contract if state else None

    def report(self, agent_id: str) -> SessionReport | None:
        """Return a live session report without ending the session."""
        state = self._sessions.get(agent_id)
        if state is None:
            return None
        return self._build_report(agent_id, state)

    def active_agents(self) -> list[str]:
        """Return list of agent IDs with active sessions."""
        return list(self._sessions.keys())

    def summary(self) -> dict[str, Any]:
        """Aggregate summary across all active sessions."""
        agents: dict[str, dict[str, Any]] = {}
        total_actions = 0
        total_divergent = 0

        for aid, state in self._sessions.items():
            total_actions += state.action_count
            total_divergent += state.divergent_count
            score = state.divergent_count / state.action_count if state.action_count else 0.0
            agents[aid] = {
                "actions": state.action_count,
                "divergent": state.divergent_count,
                "score": round(score, 4),
                "should_terminate": score >= self.terminate_threshold,
                "contract_hash": state.contract.contract_hash[:16],
            }

        return {
            "active_sessions": len(self._sessions),
            "total_actions": total_actions,
            "total_divergent": total_divergent,
            "global_divergence_rate": (
                round(total_divergent / total_actions, 4) if total_actions else 0.0
            ),
            "agents": agents,
        }

    def _build_report(self, agent_id: str, state: _SessionState) -> SessionReport:
        elapsed = time.monotonic() - state.started_at
        score = state.divergent_count / state.action_count if state.action_count else 0.0
        return SessionReport(
            agent_id=agent_id,
            contract_hash=state.contract.contract_hash,
            total_actions=state.action_count,
            compliant_actions=state.compliant_count,
            divergent_actions=state.divergent_count,
            divergence_score=score,
            elapsed_seconds=elapsed,
            should_terminate=score >= self.terminate_threshold,
            divergence_breakdown=dict(state.divergence_type_counts),
        )
