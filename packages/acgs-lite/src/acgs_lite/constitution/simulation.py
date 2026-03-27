"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """exp130: Decision delta for one action in a constitution simulation."""

    action: str
    before_decision: str
    after_decision: str
    changed: bool


@dataclass(frozen=True, slots=True)
class SimulationReport:
    """exp130: Aggregate report for constitution change simulation."""

    results: tuple[SimulationResult, ...]
    total: int
    changed: int
    unchanged: int
    change_rate: float
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize report to a JSON-compatible dict."""
        return {
            "results": [
                {
                    "action": r.action,
                    "before_decision": r.before_decision,
                    "after_decision": r.after_decision,
                    "changed": r.changed,
                }
                for r in self.results
            ],
            "total": self.total,
            "changed": self.changed,
            "unchanged": self.unchanged,
            "change_rate": self.change_rate,
            "summary": self.summary,
        }


def _safe_decision(constitution: Any, action: str) -> str:
    from acgs_lite.engine import GovernanceEngine

    engine = GovernanceEngine(constitution, strict=False)
    try:
        result = engine.validate(action)
    except (ValueError, TypeError, RuntimeError, AttributeError):
        return "deny"
    if result.valid:
        return "allow"
    if result.violations:
        sev = getattr(result.violations[0], "severity", None)
        blocks = getattr(sev, "blocks", lambda: True)
        if callable(blocks) and blocks():
            return "deny"
        return "escalate"
    return "allow"


def simulate_constitution_change(
    constitution: Any,
    actions: Sequence[str],
    rule_changes: dict[str, Any],
) -> SimulationReport:
    """exp130: Simulate decision impact of proposed constitution mutations."""
    bundle = constitution.to_bundle()
    rules = list(bundle.get("rules", []))

    remove_ids = set(rule_changes.get("remove", []))
    if remove_ids:
        rules = [r for r in rules if str(r.get("id", "")) not in remove_ids]

    updates = dict(rule_changes.get("update", {}))
    if updates:
        updated_rules: list[dict[str, Any]] = []
        for rule in rules:
            rid = str(rule.get("id", ""))
            patch = updates.get(rid)
            if patch is not None:
                merged = dict(rule)
                merged.update(patch)
                updated_rules.append(merged)
            else:
                updated_rules.append(rule)
        rules = updated_rules

    additions = list(rule_changes.get("add", []))
    if additions:
        rules.extend(dict(r) for r in additions)

    bundle["rules"] = rules
    modified = constitution.__class__.from_bundle(bundle)

    results: list[SimulationResult] = []
    transition_counts: dict[str, int] = {}

    for action in actions:
        before_decision = _safe_decision(constitution, action)
        after_decision = _safe_decision(modified, action)
        changed = before_decision != after_decision
        results.append(
            SimulationResult(
                action=action,
                before_decision=before_decision,
                after_decision=after_decision,
                changed=changed,
            )
        )
        transition_key = f"{before_decision}->{after_decision}"
        transition_counts[transition_key] = transition_counts.get(transition_key, 0) + 1

    total = len(results)
    changed_count = sum(1 for r in results if r.changed)
    unchanged = total - changed_count
    change_rate = (changed_count / total) if total > 0 else 0.0

    summary = {
        "total_actions": total,
        "changed_actions": changed_count,
        "unchanged_actions": unchanged,
        "transitions": transition_counts,
        "rule_changes": {
            "added": len(additions),
            "removed": len(remove_ids),
            "updated": len(updates),
        },
    }

    return SimulationReport(
        results=tuple(results),
        total=total,
        changed=changed_count,
        unchanged=unchanged,
        change_rate=change_rate,
        summary=summary,
    )
