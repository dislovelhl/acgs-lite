"""exp187: GovernanceReplay — replay historical decisions against modified rules.

Replays a recorded sequence of governance decisions against a different
rule set to measure the real-world impact of rule changes on historical data.
Unlike counterfactual (hypothetical actions), replay uses actual past decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ReplayedDecision:
    original_action: str
    original_outcome: str
    replayed_outcome: str
    original_violations: tuple[str, ...]
    replayed_violations: tuple[str, ...]
    changed: bool
    change_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.original_action,
            "original_outcome": self.original_outcome,
            "replayed_outcome": self.replayed_outcome,
            "original_violations": list(self.original_violations),
            "replayed_violations": list(self.replayed_violations),
            "changed": self.changed,
            "change_type": self.change_type,
        }


@dataclass
class ReplayReport:
    replay_name: str
    total_decisions: int
    unchanged: int
    newly_blocked: list[ReplayedDecision]
    newly_allowed: list[ReplayedDecision]
    violation_changes: list[ReplayedDecision]
    replayed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_changes(self) -> int:
        return len(self.newly_blocked) + len(self.newly_allowed) + len(self.violation_changes)

    @property
    def change_rate(self) -> float:
        if self.total_decisions == 0:
            return 0.0
        return self.total_changes / self.total_decisions

    @property
    def risk_score(self) -> float:
        if self.total_decisions == 0:
            return 0.0
        blocked_weight = len(self.newly_blocked) * 2.0
        allowed_weight = len(self.newly_allowed) * 3.0
        violation_weight = len(self.violation_changes) * 1.0
        return (blocked_weight + allowed_weight + violation_weight) / self.total_decisions

    def summary(self) -> str:
        lines = [
            f"Replay: {self.replay_name}",
            f"  Total decisions: {self.total_decisions}",
            f"  Unchanged: {self.unchanged}",
            f"  Newly blocked: {len(self.newly_blocked)}",
            f"  Newly allowed: {len(self.newly_allowed)}",
            f"  Violation changes: {len(self.violation_changes)}",
            f"  Change rate: {self.change_rate:.2%}",
            f"  Risk score: {self.risk_score:.4f}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "replay_name": self.replay_name,
            "total_decisions": self.total_decisions,
            "unchanged": self.unchanged,
            "newly_blocked": [d.to_dict() for d in self.newly_blocked],
            "newly_allowed": [d.to_dict() for d in self.newly_allowed],
            "violation_changes": [d.to_dict() for d in self.violation_changes],
            "total_changes": self.total_changes,
            "change_rate": round(self.change_rate, 4),
            "risk_score": round(self.risk_score, 4),
            "replayed_at": self.replayed_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class HistoricalDecision:
    action_text: str
    outcome: str
    violation_ids: list[str] = field(default_factory=list)
    agent_id: str = ""
    timestamp: datetime | None = None


def _evaluate(action_text: str, rules: list[dict[str, Any]]) -> tuple[str, list[str]]:
    action_lower = action_text.lower()
    matched: list[str] = []
    for rule in rules:
        keywords = rule.get("keywords", [])
        if any(kw in action_lower for kw in keywords):
            matched.append(rule.get("id", "unknown"))
    outcome = "deny" if matched else "allow"
    return outcome, matched


class GovernanceReplay:
    """Replays historical governance decisions against a modified rule set.

    Accepts a log of past decisions and re-evaluates each against new rules,
    producing a diff report showing what would have changed. Weights newly-allowed
    actions higher in risk scoring since they represent relaxed enforcement.
    """

    __slots__ = ("_history",)

    def __init__(self) -> None:
        self._history: list[ReplayReport] = []

    def replay(
        self,
        historical: list[HistoricalDecision],
        new_rules: list[dict[str, Any]],
        replay_name: str = "replay",
    ) -> ReplayReport:
        newly_blocked: list[ReplayedDecision] = []
        newly_allowed: list[ReplayedDecision] = []
        violation_changes: list[ReplayedDecision] = []
        unchanged = 0

        for decision in historical:
            new_outcome, new_violations = _evaluate(decision.action_text, new_rules)
            orig_violations = tuple(decision.violation_ids)
            new_violations_tuple = tuple(new_violations)

            if decision.outcome == new_outcome and set(orig_violations) == set(
                new_violations_tuple
            ):
                unchanged += 1
                continue

            if decision.outcome == new_outcome:
                change_type = "violation_set_changed"
            elif decision.outcome == "allow" and new_outcome == "deny":
                change_type = "newly_blocked"
            elif decision.outcome == "deny" and new_outcome == "allow":
                change_type = "newly_allowed"
            else:
                change_type = "outcome_changed"

            replayed = ReplayedDecision(
                original_action=decision.action_text,
                original_outcome=decision.outcome,
                replayed_outcome=new_outcome,
                original_violations=orig_violations,
                replayed_violations=new_violations_tuple,
                changed=True,
                change_type=change_type,
            )

            if change_type == "newly_blocked":
                newly_blocked.append(replayed)
            elif change_type == "newly_allowed":
                newly_allowed.append(replayed)
            else:
                violation_changes.append(replayed)

        report = ReplayReport(
            replay_name=replay_name,
            total_decisions=len(historical),
            unchanged=unchanged,
            newly_blocked=newly_blocked,
            newly_allowed=newly_allowed,
            violation_changes=violation_changes,
            metadata={
                "rule_count": len(new_rules),
                "historical_count": len(historical),
            },
        )
        self._history.append(report)
        return report

    def replay_with_comparison(
        self,
        historical: list[HistoricalDecision],
        rules_a: list[dict[str, Any]],
        rules_b: list[dict[str, Any]],
        name_a: str = "variant_a",
        name_b: str = "variant_b",
    ) -> tuple[ReplayReport, ReplayReport]:
        report_a = self.replay(historical, rules_a, name_a)
        report_b = self.replay(historical, rules_b, name_b)
        return report_a, report_b

    def safest_variant(self) -> ReplayReport | None:
        if not self._history:
            return None
        return min(self._history, key=lambda r: r.risk_score)

    def history(self) -> list[ReplayReport]:
        return list(self._history)
