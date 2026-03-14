"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class GovernanceEvent:
    """exp100: Structured governance event for monitoring, alerting, and audit pipelines.

    Immutable record of a governance decision. Downstream systems (SIEM,
    observability dashboards, compliance logs) consume these events via
    ``to_dict()`` for JSON serialization or directly as typed objects.
    """

    event_type: (
        str  # "validation_allow" | "validation_deny" | "validation_escalate" | "maci_violation"
    )
    action: str
    decision: str  # "allow" | "deny" | "escalate"
    timestamp_ns: int  # monotonic nanoseconds for ordering
    rule_ids: tuple[str, ...] = ()
    severity: str = ""
    workflow_action: str = ""
    context_risk_score: float = 0.0
    agent_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON/JSONL output."""
        return {
            "event_type": self.event_type,
            "action": self.action,
            "decision": self.decision,
            "timestamp_ns": self.timestamp_ns,
            "rule_ids": list(self.rule_ids),
            "severity": self.severity,
            "workflow_action": self.workflow_action,
            "context_risk_score": self.context_risk_score,
            "agent_id": self.agent_id,
            "metadata": self.metadata,
        }


def create_governance_event(
    action: str,
    decision: str,
    *,
    rule_ids: Sequence[str] = (),
    severity: str = "",
    workflow_action: str = "",
    context_risk_score: float = 0.0,
    agent_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> GovernanceEvent:
    """exp100: Factory for governance events with auto-populated fields.

    Args:
        action: The action that was validated.
        decision: The governance decision ("allow", "deny", "escalate").
        rule_ids: IDs of rules that triggered (empty for allow).
        severity: Highest severity among triggered rules.
        workflow_action: Recommended workflow action from the triggered rule.
        context_risk_score: Risk score from score_context_risk().
        agent_id: ID of the agent that submitted the action.
        metadata: Additional event metadata.

    Returns:
        Immutable GovernanceEvent ready for publishing.
    """
    event_type = f"validation_{decision}"
    return GovernanceEvent(
        event_type=event_type,
        action=action,
        decision=decision,
        timestamp_ns=time.monotonic_ns(),
        rule_ids=tuple(rule_ids),
        severity=severity,
        workflow_action=workflow_action,
        context_risk_score=context_risk_score,
        agent_id=agent_id,
        metadata=metadata or {},
    )


class GovernanceMetrics:
    """exp104: Lightweight governance statistics collector for observability.

    Tracks allow/deny/escalate counts, rule hit frequencies, and per-decision
    latency stats. Designed for export to Prometheus, OpenTelemetry, or
    custom dashboards. Thread-safe for single-writer use (typical governance
    engine pattern).

    Usage::

        metrics = GovernanceMetrics()
        metrics.record("allow", latency_us=3.2)
        metrics.record("deny", latency_us=5.1, rule_ids=["ACGS-001"])
        print(metrics.snapshot())
    """

    __slots__ = ("_counts", "_rule_hits", "_latencies", "_total")

    def __init__(self) -> None:
        self._counts: dict[str, int] = {"allow": 0, "deny": 0, "escalate": 0}
        self._rule_hits: dict[str, int] = {}
        self._latencies: list[float] = []
        self._total: int = 0

    def record(
        self,
        decision: str,
        *,
        latency_us: float = 0.0,
        rule_ids: Sequence[str] = (),
    ) -> None:
        """Record a governance decision.

        Args:
            decision: "allow", "deny", or "escalate".
            latency_us: Validation latency in microseconds.
            rule_ids: Rule IDs that triggered (for deny/escalate).
        """
        self._counts[decision] = self._counts.get(decision, 0) + 1
        self._total += 1
        if latency_us > 0:
            self._latencies.append(latency_us)
        for rid in rule_ids:
            self._rule_hits[rid] = self._rule_hits.get(rid, 0) + 1

    def snapshot(self) -> dict[str, Any]:
        """Return current metrics snapshot for export.

        Returns:
            dict with keys:
                - ``total_decisions``: total count
                - ``by_decision``: {allow: N, deny: N, escalate: N}
                - ``rule_hit_counts``: {rule_id: hit_count, ...}
                - ``latency``: {p50_us, p99_us, mean_us, count} or empty if no data
                - ``rates``: {allow_rate, deny_rate, escalate_rate} as floats
        """
        rates: dict[str, float] = {}
        if self._total > 0:
            for k, v in self._counts.items():
                rates[f"{k}_rate"] = v / self._total

        latency_stats: dict[str, float] = {}
        if self._latencies:
            sorted_lat = sorted(self._latencies)
            n = len(sorted_lat)
            latency_stats = {
                "p50_us": sorted_lat[n // 2],
                "p99_us": sorted_lat[int(n * 0.99)],
                "mean_us": sum(sorted_lat) / n,
                "count": float(n),
            }

        return {
            "total_decisions": self._total,
            "by_decision": dict(self._counts),
            "rule_hit_counts": dict(
                sorted(self._rule_hits.items(), key=lambda x: x[1], reverse=True)
            ),
            "latency": latency_stats,
            "rates": rates,
        }

    def reset(self) -> None:
        """Reset all counters. Call after exporting metrics."""
        self._counts = {"allow": 0, "deny": 0, "escalate": 0}
        self._rule_hits.clear()
        self._latencies.clear()
        self._total = 0


class GovernanceSession:
    """exp113: Track governance decisions within an agent session.

    Maintains a bounded decision history for a single agent session, enabling:

    - Pattern detection (repeated denials, escalation spikes)
    - Anomaly alerting (deny rate exceeding threshold)
    - Session-level compliance reporting
    - Agent behavior profiling for trust scoring

    Usage::

        session = GovernanceSession("agent-42", max_history=100)
        session.record("allow", action="read customer list")
        session.record("deny", action="delete all records", rule_ids=["ACGS-001"])
        report = session.analyze()
        if report["anomalies"]:
            print("Governance anomaly detected!")
    """

    __slots__ = ("agent_id", "_max_history", "_decisions", "_deny_threshold")

    def __init__(
        self,
        agent_id: str,
        *,
        max_history: int = 200,
        deny_threshold: float = 0.3,
    ) -> None:
        """Initialize a governance session.

        Args:
            agent_id: ID of the agent being tracked.
            max_history: Maximum decisions to retain (FIFO eviction).
            deny_threshold: Deny rate above which an anomaly is flagged (0.0–1.0).
        """
        self.agent_id = agent_id
        self._max_history = max_history
        self._deny_threshold = deny_threshold
        self._decisions: list[dict[str, Any]] = []

    def record(
        self,
        decision: str,
        *,
        action: str = "",
        rule_ids: Sequence[str] = (),
        severity: str = "",
    ) -> None:
        """Record a governance decision in this session.

        Args:
            decision: "allow", "deny", or "escalate".
            action: The action text that was validated.
            rule_ids: Rule IDs that triggered (for deny/escalate).
            severity: Severity of the highest-triggered rule.
        """
        entry = {
            "decision": decision,
            "action": action,
            "rule_ids": list(rule_ids),
            "severity": severity,
            "timestamp_ns": time.monotonic_ns(),
        }
        self._decisions.append(entry)
        if len(self._decisions) > self._max_history:
            self._decisions = self._decisions[-self._max_history:]

    def analyze(self) -> dict[str, Any]:
        """Analyze the session for patterns and anomalies.

        Returns:
            dict with keys:
                - ``agent_id``: the tracked agent ID
                - ``total_decisions``: count of decisions in history
                - ``by_decision``: {allow: N, deny: N, escalate: N}
                - ``deny_rate``: fraction of decisions that were denials
                - ``escalate_rate``: fraction that were escalations
                - ``top_triggered_rules``: most frequently triggered rule IDs
                - ``anomalies``: list of detected anomaly descriptions
                - ``recent_denials``: last 5 denial actions (for investigation)
        """
        total = len(self._decisions)
        if total == 0:
            return {
                "agent_id": self.agent_id,
                "total_decisions": 0,
                "by_decision": {"allow": 0, "deny": 0, "escalate": 0},
                "deny_rate": 0.0,
                "escalate_rate": 0.0,
                "top_triggered_rules": [],
                "anomalies": [],
                "recent_denials": [],
            }

        counts: dict[str, int] = {"allow": 0, "deny": 0, "escalate": 0}
        rule_hits: dict[str, int] = {}
        denials: list[dict[str, Any]] = []

        for d in self._decisions:
            counts[d["decision"]] = counts.get(d["decision"], 0) + 1
            if d["decision"] in ("deny", "escalate"):
                for rid in d["rule_ids"]:
                    rule_hits[rid] = rule_hits.get(rid, 0) + 1
            if d["decision"] == "deny":
                denials.append(d)

        deny_rate = counts.get("deny", 0) / total
        escalate_rate = counts.get("escalate", 0) / total

        top_rules = sorted(rule_hits.items(), key=lambda x: x[1], reverse=True)[:5]

        anomalies: list[str] = []
        if deny_rate > self._deny_threshold:
            anomalies.append(
                f"High deny rate: {deny_rate:.1%} exceeds threshold "
                f"{self._deny_threshold:.1%}"
            )
        if total >= 10 and all(
            d["decision"] == "deny" for d in self._decisions[-5:]
        ):
            anomalies.append("5 consecutive denials detected — possible policy conflict or rogue agent")
        if escalate_rate > 0.5:
            anomalies.append(
                f"Escalation spike: {escalate_rate:.1%} of decisions escalated"
            )

        return {
            "agent_id": self.agent_id,
            "total_decisions": total,
            "by_decision": counts,
            "deny_rate": deny_rate,
            "escalate_rate": escalate_rate,
            "top_triggered_rules": [{"rule_id": r, "hits": h} for r, h in top_rules],
            "anomalies": anomalies,
            "recent_denials": [
                {"action": d["action"], "rule_ids": d["rule_ids"]}
                for d in denials[-5:]
            ],
        }


class RuleEffectiveness:
    """exp114: Track rule fire rates and overrides for governance tuning.

    Monitors how often each rule triggers and how often those triggers lead
    to actual denials vs. overrides. Helps governance operators identify:

    - **Silent rules**: rules that never fire (may be misconfigured or redundant)
    - **Noisy rules**: rules that fire frequently but are often overridden
    - **Effective rules**: high fire rate with low override rate
    - **Tuning candidates**: rules whose severity may need adjustment

    Usage::

        tracker = RuleEffectiveness()
        tracker.record_fire("ACGS-001", overridden=False)
        tracker.record_fire("ACGS-002", overridden=True)
        report = tracker.report(total_validations=100)
    """

    __slots__ = ("_fires", "_overrides")

    def __init__(self) -> None:
        self._fires: dict[str, int] = {}
        self._overrides: dict[str, int] = {}

    def record_fire(self, rule_id: str, *, overridden: bool = False) -> None:
        """Record that a rule fired during validation.

        Args:
            rule_id: The rule that triggered.
            overridden: True if the denial was overridden (e.g., by HITL approval).
        """
        self._fires[rule_id] = self._fires.get(rule_id, 0) + 1
        if overridden:
            self._overrides[rule_id] = self._overrides.get(rule_id, 0) + 1

    def report(self, *, total_validations: int = 0) -> dict[str, Any]:
        """Generate effectiveness report for all tracked rules.

        Args:
            total_validations: Total number of validations run (for fire rate
                calculation). If 0, fire_rate is omitted.

        Returns:
            dict with keys:
                - ``rules``: list of per-rule effectiveness dicts sorted by
                  fire count descending, each with ``rule_id``, ``fires``,
                  ``overrides``, ``override_rate``, and optionally ``fire_rate``
                - ``silent_rules``: rule IDs that were tracked but never fired
                  (empty — tracked rules have at least 1 fire; use with
                  constitution rule IDs to find truly silent rules)
                - ``noisy_rules``: rules with override_rate > 0.5
                - ``effective_rules``: rules with fires > 0 and override_rate < 0.1
                - ``tuning_recommendations``: actionable suggestions
        """
        rules_data: list[dict[str, Any]] = []
        noisy: list[str] = []
        effective: list[str] = []
        recommendations: list[str] = []

        for rid in sorted(self._fires, key=lambda r: self._fires[r], reverse=True):
            fires = self._fires[rid]
            overrides = self._overrides.get(rid, 0)
            override_rate = overrides / fires if fires > 0 else 0.0

            entry: dict[str, Any] = {
                "rule_id": rid,
                "fires": fires,
                "overrides": overrides,
                "override_rate": override_rate,
            }
            if total_validations > 0:
                entry["fire_rate"] = fires / total_validations

            rules_data.append(entry)

            if override_rate > 0.5:
                noisy.append(rid)
                recommendations.append(
                    f"Rule {rid}: override rate {override_rate:.0%} — "
                    "consider lowering severity or refining keywords"
                )
            elif fires > 0 and override_rate < 0.1:
                effective.append(rid)

        return {
            "rules": rules_data,
            "silent_rules": [],
            "noisy_rules": noisy,
            "effective_rules": effective,
            "tuning_recommendations": recommendations,
        }

    def reset(self) -> None:
        """Reset all tracking data."""
        self._fires.clear()
        self._overrides.clear()
