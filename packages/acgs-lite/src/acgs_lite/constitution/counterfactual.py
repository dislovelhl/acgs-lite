"""exp183: CounterfactualGovernance — what-if scenario simulation.

Test governance rule changes before applying them. Evaluates a batch of actions
against both the current constitution and a hypothetical modified version,
producing a diff report of changed decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DecisionDelta:
    """A single action whose governance outcome changed between baseline and variant."""

    action_text: str
    baseline_outcome: str
    variant_outcome: str
    baseline_violations: tuple[str, ...]
    variant_violations: tuple[str, ...]
    severity_change: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_text": self.action_text,
            "baseline_outcome": self.baseline_outcome,
            "variant_outcome": self.variant_outcome,
            "baseline_violations": list(self.baseline_violations),
            "variant_violations": list(self.variant_violations),
            "severity_change": self.severity_change,
        }


@dataclass
class CounterfactualReport:
    """Result of a counterfactual governance analysis."""

    scenario_name: str
    actions_tested: int
    unchanged: int
    newly_blocked: list[DecisionDelta]
    newly_allowed: list[DecisionDelta]
    severity_changed: list[DecisionDelta]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_changes(self) -> int:
        return len(self.newly_blocked) + len(self.newly_allowed) + len(self.severity_changed)

    @property
    def impact_score(self) -> float:
        if self.actions_tested == 0:
            return 0.0
        return self.total_changes / self.actions_tested

    def summary(self) -> str:
        lines = [
            f"Counterfactual: {self.scenario_name}",
            f"  Actions tested: {self.actions_tested}",
            f"  Unchanged: {self.unchanged}",
            f"  Newly blocked: {len(self.newly_blocked)}",
            f"  Newly allowed: {len(self.newly_allowed)}",
            f"  Severity changed: {len(self.severity_changed)}",
            f"  Impact score: {self.impact_score:.2%}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "actions_tested": self.actions_tested,
            "unchanged": self.unchanged,
            "newly_blocked": [d.to_dict() for d in self.newly_blocked],
            "newly_allowed": [d.to_dict() for d in self.newly_allowed],
            "severity_changed": [d.to_dict() for d in self.severity_changed],
            "total_changes": self.total_changes,
            "impact_score": self.impact_score,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


def _evaluate_action(
    action_text: str,
    rules: list[dict[str, Any]],
) -> tuple[str, list[str], str]:
    """Evaluate an action against a rule set. Returns (outcome, violation_ids, max_severity)."""
    action_lower = action_text.lower()
    matched: list[str] = []
    severity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    max_severity = "low"

    for rule in rules:
        keywords = rule.get("keywords", [])
        if any(kw in action_lower for kw in keywords):
            matched.append(rule.get("id", "unknown"))
            rule_sev = rule.get("severity", "low")
            if severity_rank.get(rule_sev, 0) > severity_rank.get(max_severity, 0):
                max_severity = rule_sev

    outcome = "deny" if matched else "allow"
    return outcome, matched, max_severity


class CounterfactualGovernance:
    """Simulate governance rule changes without modifying the live constitution.

    Compares baseline rules against a variant (rules added, removed, or modified)
    to predict the impact on a set of test actions.
    """

    __slots__ = ("_baseline_rules", "_history")

    def __init__(self, baseline_rules: list[dict[str, Any]]) -> None:
        self._baseline_rules = list(baseline_rules)
        self._history: list[CounterfactualReport] = []

    def what_if_add_rules(
        self,
        new_rules: list[dict[str, Any]],
        test_actions: list[str],
        scenario_name: str = "add_rules",
    ) -> CounterfactualReport:
        variant_rules = self._baseline_rules + new_rules
        return self._compare(self._baseline_rules, variant_rules, test_actions, scenario_name)

    def what_if_remove_rules(
        self,
        rule_ids_to_remove: set[str],
        test_actions: list[str],
        scenario_name: str = "remove_rules",
    ) -> CounterfactualReport:
        variant_rules = [r for r in self._baseline_rules if r.get("id") not in rule_ids_to_remove]
        return self._compare(self._baseline_rules, variant_rules, test_actions, scenario_name)

    def what_if_modify_rules(
        self,
        modifications: dict[str, dict[str, Any]],
        test_actions: list[str],
        scenario_name: str = "modify_rules",
    ) -> CounterfactualReport:
        variant_rules = []
        for rule in self._baseline_rules:
            rid = rule.get("id", "")
            if rid in modifications:
                modified = {**rule, **modifications[rid]}
                variant_rules.append(modified)
            else:
                variant_rules.append(rule)
        return self._compare(self._baseline_rules, variant_rules, test_actions, scenario_name)

    def what_if_replace_all(
        self,
        variant_rules: list[dict[str, Any]],
        test_actions: list[str],
        scenario_name: str = "replace_all",
    ) -> CounterfactualReport:
        return self._compare(self._baseline_rules, variant_rules, test_actions, scenario_name)

    def _compare(
        self,
        baseline: list[dict[str, Any]],
        variant: list[dict[str, Any]],
        test_actions: list[str],
        scenario_name: str,
    ) -> CounterfactualReport:
        newly_blocked: list[DecisionDelta] = []
        newly_allowed: list[DecisionDelta] = []
        severity_changed: list[DecisionDelta] = []
        unchanged = 0

        for action in test_actions:
            b_outcome, b_violations, b_severity = _evaluate_action(action, baseline)
            v_outcome, v_violations, v_severity = _evaluate_action(action, variant)

            if b_outcome == v_outcome and b_severity == v_severity:
                unchanged += 1
                continue

            delta = DecisionDelta(
                action_text=action,
                baseline_outcome=b_outcome,
                variant_outcome=v_outcome,
                baseline_violations=tuple(b_violations),
                variant_violations=tuple(v_violations),
                severity_change=f"{b_severity}->{v_severity}"
                if b_severity != v_severity
                else "none",
            )

            if b_outcome == "allow" and v_outcome == "deny":
                newly_blocked.append(delta)
            elif b_outcome == "deny" and v_outcome == "allow":
                newly_allowed.append(delta)
            elif b_severity != v_severity:
                severity_changed.append(delta)

        report = CounterfactualReport(
            scenario_name=scenario_name,
            actions_tested=len(test_actions),
            unchanged=unchanged,
            newly_blocked=newly_blocked,
            newly_allowed=newly_allowed,
            severity_changed=severity_changed,
            metadata={
                "baseline_rule_count": len(baseline),
                "variant_rule_count": len(variant),
            },
        )
        self._history.append(report)
        return report

    def history(self) -> list[CounterfactualReport]:
        return list(self._history)

    def highest_impact(self) -> CounterfactualReport | None:
        if not self._history:
            return None
        return max(self._history, key=lambda r: r.impact_score)
