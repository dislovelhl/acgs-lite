"""Dynamic trust scoring for governance agents based on violation history.

Maintains a per-agent trust score (0.0-1.0) that decays on violations and
recovers over time through compliant actions.  Scores gate escalation tiers:
agents with low trust receive stricter review thresholds automatically.

Supports domain-scoped scoring (an agent can be trusted in finance but
restricted in healthcare) and time-based forgiveness (old violations
gradually heal).

Example::

    from acgs_lite.constitution.trust_score import TrustScoreManager, TrustConfig

    manager = TrustScoreManager()
    manager.register("agent:worker-1", TrustConfig(initial_score=1.0))

    # Record a governance decision
    manager.record_decision("agent:worker-1", compliant=True)
    manager.record_decision("agent:worker-1", compliant=False, severity="critical")

    score = manager.score("agent:worker-1")
    tier  = manager.tier("agent:worker-1")   # "trusted" | "monitored" | "restricted"

    # Domain-scoped scoring
    manager.record_decision("agent:worker-1", compliant=False, severity="high", domain="finance")
    fin_score = manager.score("agent:worker-1", domain="finance")
    fin_tier  = manager.tier("agent:worker-1", domain="finance")

    # Time-based forgiveness
    config = TrustConfig(time_decay_rate=0.001)  # recover 0.001/hour passively
    manager.register("agent:worker-2", config)

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Key for the global (non-domain-scoped) trust state
_GLOBAL_DOMAIN = "__global__"


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
        time_decay_rate: Passive score recovery per hour (0.0 = disabled).
            Old violations gradually heal even without active compliant
            decisions.  Applied when :meth:`score` or :meth:`tier` is called.
        minimum_assignment_fraction: Minimum fraction of work routed to this
            agent even when restricted (0.0–1.0, advisory — enforced by the
            orchestrator, not by TrustScoreManager itself).
        metadata: Arbitrary key-value metadata.
    """

    initial_score: float = 1.0
    trusted_threshold: float = 0.8
    monitored_threshold: float = 0.5
    recovery_per_decision: float = _COMPLIANCE_REWARD
    decay_floor: float = 0.0
    time_decay_rate: float = 0.0
    minimum_assignment_fraction: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for attr in (
            "initial_score",
            "trusted_threshold",
            "monitored_threshold",
            "recovery_per_decision",
            "decay_floor",
            "minimum_assignment_fraction",
        ):
            v = getattr(self, attr)
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"{attr} must be in [0.0, 1.0], got {v}")
        if self.time_decay_rate < 0.0:
            raise ValueError(f"time_decay_rate must be ≥ 0.0, got {self.time_decay_rate}")
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
    domain: str = ""


class _DomainTrustState:
    """Trust state for a single domain (or the global aggregate)."""

    __slots__ = ("score", "events", "violation_count", "compliant_count", "last_updated")

    def __init__(self, initial_score: float, now: datetime) -> None:
        self.score: float = initial_score
        self.events: list[TrustEvent] = []
        self.violation_count: int = 0
        self.compliant_count: int = 0
        self.last_updated: datetime = now

    def apply_time_decay(self, config: TrustConfig, now: datetime) -> None:
        """Apply passive time-based recovery since last update."""
        if config.time_decay_rate <= 0 or self.score >= 1.0:
            return
        elapsed_hours = (now - self.last_updated).total_seconds() / 3600.0
        if elapsed_hours <= 0:
            return
        recovery = config.time_decay_rate * elapsed_hours
        self.score = min(1.0, self.score + recovery)
        self.last_updated = now

    def record(
        self,
        agent_id: str,
        config: TrustConfig,
        *,
        compliant: bool,
        severity: str,
        note: str,
        now: datetime,
        domain: str = "",
    ) -> TrustEvent:
        # Apply time decay before recording
        self.apply_time_decay(config, now)

        before = self.score
        if compliant:
            delta = config.recovery_per_decision
            self.score = min(1.0, self.score + delta)
            self.compliant_count += 1
        else:
            penalty = _SEVERITY_PENALTY.get(severity.lower(), _SEVERITY_PENALTY["medium"])
            delta = -penalty
            self.score = max(config.decay_floor, self.score + delta)
            self.violation_count += 1

        self.last_updated = now

        event = TrustEvent(
            agent_id=agent_id,
            compliant=compliant,
            severity=severity if not compliant else "",
            score_before=round(before, 6),
            score_after=round(self.score, 6),
            delta=round(delta, 6),
            timestamp=now.isoformat(),
            note=note,
            domain=domain,
        )
        self.events.append(event)
        return event


class _AgentTrustState:
    __slots__ = ("config", "domains")

    def __init__(self, config: TrustConfig, now: datetime | None = None) -> None:
        self.config = config
        _now = now or datetime.now(timezone.utc)
        # Global domain state is always present
        self.domains: dict[str, _DomainTrustState] = {
            _GLOBAL_DOMAIN: _DomainTrustState(config.initial_score, _now),
        }

    def _get_domain(self, domain: str, now: datetime) -> _DomainTrustState:
        """Get or create a domain-specific trust state."""
        key = domain.lower() if domain else _GLOBAL_DOMAIN
        if key not in self.domains:
            self.domains[key] = _DomainTrustState(self.config.initial_score, now)
        return self.domains[key]

    @property
    def score(self) -> float:
        """Global trust score (backward compat)."""
        return self.domains[_GLOBAL_DOMAIN].score

    @score.setter
    def score(self, value: float) -> None:
        self.domains[_GLOBAL_DOMAIN].score = value

    @property
    def events(self) -> list[TrustEvent]:
        """All events across all domains (backward compat)."""
        all_events: list[TrustEvent] = []
        for ds in self.domains.values():
            all_events.extend(ds.events)
        all_events.sort(key=lambda e: e.timestamp)
        return all_events

    @property
    def violation_count(self) -> int:
        return sum(ds.violation_count for ds in self.domains.values())

    @property
    def compliant_count(self) -> int:
        return sum(ds.compliant_count for ds in self.domains.values())

    def record(
        self,
        agent_id: str,
        *,
        compliant: bool,
        severity: str,
        note: str,
        now: datetime,
        domain: str = "",
    ) -> TrustEvent:
        # Always update global
        global_state = self.domains[_GLOBAL_DOMAIN]
        global_event = global_state.record(
            agent_id,
            self.config,
            compliant=compliant,
            severity=severity,
            note=note,
            now=now,
            domain=domain,
        )

        # If domain-scoped, also update domain-specific state
        if domain:
            domain_state = self._get_domain(domain, now)
            domain_state.record(
                agent_id,
                self.config,
                compliant=compliant,
                severity=severity,
                note=note,
                now=now,
                domain=domain,
            )

        return global_event

    def get_score(self, domain: str = "", now: datetime | None = None) -> float:
        """Get score, optionally for a specific domain, with time decay applied."""
        _now = now or datetime.now(timezone.utc)
        if domain:
            key = domain.lower()
            if key not in self.domains:
                return self.config.initial_score  # no history = initial
            ds = self.domains[key]
            ds.apply_time_decay(self.config, _now)
            return ds.score
        else:
            gs = self.domains[_GLOBAL_DOMAIN]
            gs.apply_time_decay(self.config, _now)
            return gs.score

    def get_tier(self, domain: str = "", now: datetime | None = None) -> str:
        """Get tier, optionally for a specific domain."""
        s = self.get_score(domain, now)
        cfg = self.config
        if s >= cfg.trusted_threshold:
            return TrustTier.TRUSTED
        if s >= cfg.monitored_threshold:
            return TrustTier.MONITORED
        return TrustTier.RESTRICTED

    def domain_history(self, domain: str) -> list[TrustEvent]:
        """Return events for a specific domain."""
        key = domain.lower()
        if key not in self.domains:
            return []
        return list(self.domains[key].events)

    def known_domains(self) -> list[str]:
        """Return list of domains with history (excluding global)."""
        return sorted(k for k in self.domains if k != _GLOBAL_DOMAIN)


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
        domain: str = "",
        _now: datetime | None = None,
    ) -> TrustEvent:
        """Record a governance decision for *agent_id* and update trust score.

        If *agent_id* is not yet registered it is auto-registered with defaults.

        When *domain* is provided, both the global score and the domain-specific
        score are updated. This means a violation in "finance" penalizes the
        agent's finance score AND their global score.

        Args:
            agent_id: The agent making the decision.
            compliant: True if the decision was compliant.
            severity: Violation severity (ignored when compliant=True).
            note: Optional annotation.
            domain: Governance domain (e.g. "finance", "privacy"). Empty = global only.
            _now: Override current time (for testing).

        Returns:
            The :class:`TrustEvent` produced by this call.
        """
        now = _now or datetime.now(timezone.utc)
        if agent_id not in self._states:
            self._states[agent_id] = _AgentTrustState(TrustConfig(), now)
        return self._states[agent_id].record(
            agent_id,
            compliant=compliant,
            severity=severity,
            note=note,
            now=now,
            domain=domain,
        )

    def score(self, agent_id: str, domain: str = "", *, _now: datetime | None = None) -> float:
        """Return current trust score for *agent_id*.

        Args:
            agent_id: Agent identifier.
            domain: Governance domain (empty = global score).
            _now: Override current time (for time decay calculation).

        Raises:
            KeyError: If agent not registered.
        """
        if agent_id not in self._states:
            raise KeyError(f"Agent '{agent_id}' not registered")
        return round(self._states[agent_id].get_score(domain, _now), 6)

    def tier(self, agent_id: str, domain: str = "", *, _now: datetime | None = None) -> str:
        """Return the trust tier for *agent_id*: ``trusted``, ``monitored``, or ``restricted``.

        Args:
            agent_id: Agent identifier.
            domain: Governance domain (empty = global tier).
            _now: Override current time (for time decay calculation).

        Raises:
            KeyError: If agent not registered.
        """
        if agent_id not in self._states:
            raise KeyError(f"Agent '{agent_id}' not registered")
        return self._states[agent_id].get_tier(domain, _now)

    def history(self, agent_id: str, domain: str = "") -> list[TrustEvent]:
        """Return event history for *agent_id*, optionally filtered by domain.

        Args:
            agent_id: Agent identifier.
            domain: If provided, return only events for that domain.

        Raises:
            KeyError: If agent not registered.
        """
        if agent_id not in self._states:
            raise KeyError(f"Agent '{agent_id}' not registered")
        if domain:
            return self._states[agent_id].domain_history(domain)
        return list(self._states[agent_id].events)

    def domains(self, agent_id: str) -> list[str]:
        """Return list of governance domains with history for *agent_id*.

        Raises:
            KeyError: If agent not registered.
        """
        if agent_id not in self._states:
            raise KeyError(f"Agent '{agent_id}' not registered")
        return self._states[agent_id].known_domains()

    def domain_scores(
        self,
        agent_id: str,
        *,
        _now: datetime | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Return scores and tiers for all known domains of *agent_id*.

        Returns:
            dict mapping domain → {"score": float, "tier": str, "events": int}

        Raises:
            KeyError: If agent not registered.
        """
        if agent_id not in self._states:
            raise KeyError(f"Agent '{agent_id}' not registered")
        state = self._states[agent_id]
        result: dict[str, dict[str, Any]] = {}
        for d in state.known_domains():
            result[d] = {
                "score": round(state.get_score(d, _now), 6),
                "tier": state.get_tier(d, _now),
                "violations": state.domains[d.lower()].violation_count,
                "compliant_decisions": state.domains[d.lower()].compliant_count,
                "events": len(state.domains[d.lower()].events),
            }
        return result

    def restricted_agents(self, domain: str = "") -> list[str]:
        """Return IDs of all agents currently in the restricted tier.

        Args:
            domain: If provided, check domain-specific tier instead of global.
        """
        return [aid for aid in self._states if self.tier(aid, domain) == TrustTier.RESTRICTED]

    def list_agents(self) -> list[str]:
        """Return sorted list of registered agent IDs."""
        return sorted(self._states)

    def summary(self, domain: str = "") -> dict[str, Any]:
        """Return an aggregate summary of all agent trust scores.

        Args:
            domain: If provided, summarize domain-specific scores.
        """
        entries = []
        for aid, state in sorted(self._states.items()):
            entries.append(
                {
                    "agent_id": aid,
                    "score": round(state.get_score(domain), 6),
                    "tier": state.get_tier(domain),
                    "violations": state.violation_count,
                    "compliant_decisions": state.compliant_count,
                    "event_count": len(state.events),
                    "domains": state.known_domains(),
                }
            )
        return {
            "agent_count": len(self._states),
            "restricted_count": len(self.restricted_agents(domain)),
            "domain_filter": domain,
            "agents": entries,
        }

    def sync_to_validator_pool(
        self,
        pool: Any,
        domain: str = "",
        *,
        _now: datetime | None = None,
    ) -> int:
        """Push current trust scores into a ValidatorPool.

        Args:
            pool: A :class:`ValidatorPool` instance.
            domain: If provided, use domain-specific scores.
            _now: Override current time.

        Returns:
            Number of validators updated.
        """
        updated = 0
        for aid, state in self._states.items():
            s = state.get_score(domain, _now)
            try:
                pool.update_trust(aid, round(s, 6))
                updated += 1
            except KeyError:
                pass  # agent not in pool, skip
        return updated
