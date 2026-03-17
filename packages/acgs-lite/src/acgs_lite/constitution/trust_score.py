"""Dynamic trust scoring for governance agents based on violation history.

Maintains a per-agent trust score (0.0-1.0) that decays on violations and
recovers over time through compliant actions.  Scores gate escalation tiers:
agents with low trust receive stricter review thresholds automatically.

Example::

    from acgs_lite.constitution.trust_score import TrustScoreManager, TrustConfig

    manager = TrustScoreManager()
    manager.register("agent:worker-1", TrustConfig(initial_score=1.0))

    # Record a governance decision
    manager.record_decision("agent:worker-1", compliant=True)
    manager.record_decision("agent:worker-1", compliant=False, severity="critical")

    score = manager.score("agent:worker-1")
    tier  = manager.tier("agent:worker-1")   # "trusted" | "monitored" | "restricted"

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class TrustTier(str):
    TRUSTED = "trusted"
    MONITORED = "monitored"
    RESTRICTED = "restricted"


_SEVERITY_PENALTY: dict[str, float] = {
    "critical": 0.20,
    "high": 0.10,
    "medium": 0.05,
    "low": 0.02,
}

_COMPLIANCE_REWARD: float = 0.01


@dataclass
class TrustConfig:
    """Configuration for an agent's trust scoring behaviour.

    Attributes:
        initial_score: Starting trust score [0.0-1.0].
        trusted_threshold: Score at or above which the agent is "trusted".
        monitored_threshold: Score at or above which the agent is "monitored"
            (below trusted_threshold).
        recovery_per_decision: Score recovery per compliant decision.
        decay_floor: Minimum score after any penalty.
        metadata: Arbitrary key-value metadata.
    """

    initial_score: float = 1.0
    trusted_threshold: float = 0.8
    monitored_threshold: float = 0.5
    recovery_per_decision: float = _COMPLIANCE_REWARD
    decay_floor: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for attr in (
            "initial_score",
            "trusted_threshold",
            "monitored_threshold",
            "recovery_per_decision",
            "decay_floor",
        ):
            v = getattr(self, attr)
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"{attr} must be in [0.0, 1.0], got {v}")
        if self.monitored_threshold > self.trusted_threshold:
            raise ValueError("monitored_threshold must be ≤ trusted_threshold")


@dataclass
class TrustEvent:
    """A single trust event record.

    Attributes:
        agent_id: The agent affected.
        compliant: True if the decision was compliant, False for a violation.
        severity: Violation severity (only meaningful when compliant=False).
        score_before: Trust score before this event.
        score_after: Trust score after this event.
        delta: Score change (positive = recovery, negative = penalty).
        timestamp: UTC ISO-8601 timestamp.
        note: Optional annotation.
    """

    agent_id: str
    compliant: bool
    severity: str
    score_before: float
    score_after: float
    delta: float
    timestamp: str
    note: str = ""


class _AgentTrustState:
    __slots__ = ("config", "score", "events", "violation_count", "compliant_count")

    def __init__(self, config: TrustConfig) -> None:
        self.config = config
        self.score: float = config.initial_score
        self.events: list[TrustEvent] = []
        self.violation_count: int = 0
        self.compliant_count: int = 0

    def record(
        self,
        agent_id: str,
        *,
        compliant: bool,
        severity: str,
        note: str,
        now: datetime,
    ) -> TrustEvent:
        before = self.score
        if compliant:
            delta = self.config.recovery_per_decision
            self.score = min(1.0, self.score + delta)
            self.compliant_count += 1
        else:
            penalty = _SEVERITY_PENALTY.get(severity.lower(), _SEVERITY_PENALTY["medium"])
            delta = -penalty
            self.score = max(self.config.decay_floor, self.score + delta)
            self.violation_count += 1

        event = TrustEvent(
            agent_id=agent_id,
            compliant=compliant,
            severity=severity if not compliant else "",
            score_before=round(before, 6),
            score_after=round(self.score, 6),
            delta=round(delta, 6),
            timestamp=now.isoformat(),
            note=note,
        )
        self.events.append(event)
        return event


class TrustScoreManager:
    """Manages dynamic trust scores for governance agents.

    Agents start at a configurable initial score and are penalised for
    violations (with severity-weighted penalties) and rewarded for compliant
    decisions.  Scores gate three tiers:

    - ``trusted``    — full autonomy
    - ``monitored``  — increased review
    - ``restricted`` — mandatory human-in-the-loop

    Example::

        manager = TrustScoreManager()
        manager.register("agent:a1", TrustConfig(initial_score=1.0))
        manager.record_decision("agent:a1", compliant=False, severity="high")
        assert manager.tier("agent:a1") in ("trusted", "monitored", "restricted")
    """

    def __init__(self) -> None:
        self._states: dict[str, _AgentTrustState] = {}

    def register(
        self,
        agent_id: str,
        config: TrustConfig | None = None,
        *,
        overwrite: bool = False,
    ) -> None:
        """Register an agent for trust tracking.

        Args:
            agent_id: Unique agent identifier.
            config: Trust configuration (defaults to ``TrustConfig()``).
            overwrite: Replace existing state if True.

        Raises:
            ValueError: If agent already registered and overwrite=False.
        """
        if agent_id in self._states and not overwrite:
            raise ValueError(f"Agent '{agent_id}' already registered")
        self._states[agent_id] = _AgentTrustState(config or TrustConfig())

    def record_decision(
        self,
        agent_id: str,
        *,
        compliant: bool,
        severity: str = "medium",
        note: str = "",
        _now: datetime | None = None,
    ) -> TrustEvent:
        """Record a governance decision for *agent_id* and update trust score.

        If *agent_id* is not yet registered it is auto-registered with defaults.

        Args:
            agent_id: The agent making the decision.
            compliant: True if the decision was compliant.
            severity: Violation severity (ignored when compliant=True).
            note: Optional annotation.
            _now: Override current time (for testing).

        Returns:
            The :class:`TrustEvent` produced by this call.
        """
        if agent_id not in self._states:
            self._states[agent_id] = _AgentTrustState(TrustConfig())
        now = _now or datetime.now(timezone.utc)
        return self._states[agent_id].record(
            agent_id, compliant=compliant, severity=severity, note=note, now=now
        )

    def score(self, agent_id: str) -> float:
        """Return current trust score for *agent_id*.

        Raises:
            KeyError: If agent not registered.
        """
        if agent_id not in self._states:
            raise KeyError(f"Agent '{agent_id}' not registered")
        return round(self._states[agent_id].score, 6)

    def tier(self, agent_id: str) -> str:
        """Return the trust tier for *agent_id*: ``trusted``, ``monitored``, or ``restricted``.

        Raises:
            KeyError: If agent not registered.
        """
        if agent_id not in self._states:
            raise KeyError(f"Agent '{agent_id}' not registered")
        state = self._states[agent_id]
        s = state.score
        cfg = state.config
        if s >= cfg.trusted_threshold:
            return TrustTier.TRUSTED
        if s >= cfg.monitored_threshold:
            return TrustTier.MONITORED
        return TrustTier.RESTRICTED

    def history(self, agent_id: str) -> list[TrustEvent]:
        """Return event history for *agent_id*.

        Raises:
            KeyError: If agent not registered.
        """
        if agent_id not in self._states:
            raise KeyError(f"Agent '{agent_id}' not registered")
        return list(self._states[agent_id].events)

    def restricted_agents(self) -> list[str]:
        """Return IDs of all agents currently in the restricted tier."""
        return [aid for aid in self._states if self.tier(aid) == TrustTier.RESTRICTED]

    def list_agents(self) -> list[str]:
        """Return sorted list of registered agent IDs."""
        return sorted(self._states)

    def summary(self) -> dict[str, Any]:
        """Return an aggregate summary of all agent trust scores."""
        entries = []
        for aid, state in sorted(self._states.items()):
            entries.append(
                {
                    "agent_id": aid,
                    "score": round(state.score, 6),
                    "tier": self.tier(aid),
                    "violations": state.violation_count,
                    "compliant_decisions": state.compliant_count,
                    "event_count": len(state.events),
                }
            )
        return {
            "agent_count": len(self._states),
            "restricted_count": len(self.restricted_agents()),
            "agents": entries,
        }
