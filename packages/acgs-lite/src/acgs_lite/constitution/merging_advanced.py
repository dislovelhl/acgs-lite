"""Advanced constitution merging: full merge with conflict resolution and cascade."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from acgs_lite.errors import ConstitutionalViolationError

from .rule import AcknowledgedTension, Rule, Severity

if TYPE_CHECKING:
    from .constitution import Constitution


def merge(
    constitution: Constitution,
    other: Constitution,
    *,
    strategy: str = "keep_higher_severity",
    name: str = "",
    acknowledged_tensions: Sequence[AcknowledgedTension] | None = None,
    allow_hardcoded_override: bool = False,
) -> dict[str, Any]:
    """exp109: Merge two constitutions with conflict detection and resolution.

    Enables layered governance architectures where a base constitution is
    composed with domain-specific overlays. Conflicts (same rule ID in both)
    are resolved according to the specified strategy.

    Args:
        constitution: The base constitution (equivalent to ``self``).
        other: Constitution to merge into the base one.
        strategy: Conflict resolution when both have the same rule ID:
            - ``keep_self``: keep rules from the base constitution
            - ``keep_other``: keep rules from the other constitution
            - ``keep_higher_severity``: keep the rule with higher severity
              (CRITICAL > HIGH > MEDIUM > LOW); ties go to the base
        name: Name for the merged constitution
            (default: ``"merged-{constitution.name}+{other.name}"``).
        acknowledged_tensions: Known conflict IDs that are explicitly
            acknowledged and accepted by governance operators.
        allow_hardcoded_override: If False, overriding any conflicting
            ``Rule.hardcoded=True`` rule raises ``ConstitutionalViolationError``.

    Returns:
        dict with keys:
            - ``constitution``: the merged Constitution object
            - ``conflicts_resolved``: number of rule ID conflicts detected
            - ``conflict_details``: list of dicts describing each resolution
            - ``rules_from_self``: count of rules originating from the base
            - ``rules_from_other``: count of rules originating from other
            - ``total_rules``: total rules in the merged constitution
            - ``unacknowledged_tensions``: conflicting rule IDs that were
              resolved but not explicitly acknowledged
            - ``acknowledged_tensions_applied``: acknowledged tensions that
              were encountered during merge

    Raises:
        ValueError: If strategy is not one of the supported values.

    Example::

        base = Constitution.from_template("security")
        overlay = Constitution.from_template("healthcare")
        result = merge(base, overlay)
        merged = result["constitution"]
        print(f"Merged: {result['total_rules']} rules, "
              f"{result['conflicts_resolved']} conflicts resolved")
    """
    from .constitution import Constitution as _Constitution  # noqa: F811

    _SEVERITY_RANK = {
        Severity.CRITICAL: 4,
        Severity.HIGH: 3,
        Severity.MEDIUM: 2,
        Severity.LOW: 1,
    }
    _VALID_STRATEGIES = frozenset({"keep_self", "keep_other", "keep_higher_severity"})
    if strategy not in _VALID_STRATEGIES:
        raise ValueError(
            f"Unknown merge strategy {strategy!r}; expected one of {sorted(_VALID_STRATEGIES)}"
        )

    merged_name = name or f"merged-{constitution.name}+{other.name}"
    self_rules = {r.id: r for r in constitution.rules}
    other_rules = {r.id: r for r in other.rules}
    acknowledged_ids = {t.rule_id for t in (acknowledged_tensions or [])}

    conflict_ids = set(self_rules) & set(other_rules)
    conflict_details: list[dict[str, str]] = []
    unacknowledged_tensions: list[dict[str, str]] = []
    acknowledged_tensions_applied: list[dict[str, str]] = []
    merged: list[Rule] = []
    from_self = 0
    from_other = 0

    def _record_tension(rule_id: str, kept: str, reason: str = "") -> None:
        rule_self = self_rules[rule_id]
        rule_other = other_rules[rule_id]
        if rule_self.model_dump() == rule_other.model_dump():
            return

        tension_detail = {
            "rule_id": rule_id,
            "kept": kept,
        }
        if reason:
            tension_detail["reason"] = reason

        if rule_id in acknowledged_ids:
            acknowledged_tensions_applied.append(tension_detail)
        else:
            unacknowledged_tensions.append(tension_detail)

    def _guard_hardcoded_override(kept: str, rule: Rule, other_rule: Rule) -> None:
        if allow_hardcoded_override:
            return

        if kept != "self" and rule.hardcoded:
            raise ConstitutionalViolationError(
                f"Cannot override hardcoded rule '{rule.id}' without explicit override",
                rule_id=rule.id,
                severity=rule.severity.value,
            )

        if kept != "other" and other_rule.hardcoded:
            raise ConstitutionalViolationError(
                f"Cannot override hardcoded rule '{other_rule.id}' without explicit override",
                rule_id=other_rule.id,
                severity=other_rule.severity.value,
            )

    # Add all base-constitution rules, resolving conflicts
    for rule in constitution.rules:
        if rule.id in conflict_ids:
            other_rule = other_rules[rule.id]
            if strategy == "keep_self":
                _guard_hardcoded_override("self", rule, other_rule)
                merged.append(rule)
                from_self += 1
                conflict_details.append(
                    {
                        "rule_id": rule.id,
                        "kept": "self",
                        "strategy": strategy,
                    }
                )
                _record_tension(rule.id, "self")
            elif strategy == "keep_other":
                _guard_hardcoded_override("other", rule, other_rule)
                merged.append(other_rule)
                from_other += 1
                conflict_details.append(
                    {
                        "rule_id": rule.id,
                        "kept": "other",
                        "strategy": strategy,
                    }
                )
                _record_tension(rule.id, "other")
            else:  # keep_higher_severity
                self_rank = _SEVERITY_RANK.get(rule.severity, 0)
                other_rank = _SEVERITY_RANK.get(other_rule.severity, 0)
                if other_rank > self_rank:
                    _guard_hardcoded_override("other", rule, other_rule)
                    merged.append(other_rule)
                    from_other += 1
                    reason = f"{other_rule.severity.value} > {rule.severity.value}"
                    conflict_details.append(
                        {
                            "rule_id": rule.id,
                            "kept": "other",
                            "strategy": strategy,
                            "reason": reason,
                        }
                    )
                    _record_tension(rule.id, "other", reason)
                else:
                    _guard_hardcoded_override("self", rule, other_rule)
                    merged.append(rule)
                    from_self += 1
                    reason = f"{rule.severity.value} >= {other_rule.severity.value}"
                    conflict_details.append(
                        {
                            "rule_id": rule.id,
                            "kept": "self",
                            "strategy": strategy,
                            "reason": reason,
                        }
                    )
                    _record_tension(rule.id, "self", reason)
        else:
            merged.append(rule)
            from_self += 1

    # Add non-conflicting rules from other
    for rule in other.rules:
        if rule.id not in conflict_ids:
            merged.append(rule)
            from_other += 1

    merged_constitution = _Constitution(
        name=merged_name,
        version=f"{constitution.version}+{other.version}",
        description=f"Merged: {constitution.name} + {other.name}",
        rules=merged,
        metadata={
            **constitution.metadata,
            **other.metadata,
            "merge_strategy": strategy,
            "merge_sources": [constitution.name, other.name],
        },
    )

    return {
        "constitution": merged_constitution,
        "conflicts_resolved": len(conflict_details),
        "conflict_details": conflict_details,
        "rules_from_self": from_self,
        "rules_from_other": from_other,
        "total_rules": len(merged),
        "unacknowledged_tensions": unacknowledged_tensions,
        "acknowledged_tensions_applied": acknowledged_tensions_applied,
    }


def cascade(constitution: Constitution, child: Constitution, *, name: str = "") -> Constitution:
    """Create a federated constitution where *constitution* is the parent.

    Parent rules marked ``hardcoded=True`` are authoritative and cannot be
    overridden by child rules with the same rule ID.
    """
    from .constitution import Constitution as _Constitution  # noqa: F811

    parent_rules = {rule.id: rule for rule in constitution.rules}
    child_rules = {rule.id: rule for rule in child.rules}

    merged: list[Rule] = []

    for parent_rule in constitution.rules:
        child_rule = child_rules.get(parent_rule.id)
        if child_rule is None:
            merged.append(parent_rule)
            continue
        if parent_rule.hardcoded:
            merged.append(parent_rule)
        else:
            merged.append(child_rule)

    for child_rule in child.rules:
        if child_rule.id not in parent_rules:
            merged.append(child_rule)

    merged_name = name or f"federated-{constitution.name}+{child.name}"
    return _Constitution(
        name=merged_name,
        version=f"{constitution.version}+{child.version}",
        description=f"Federated: parent={constitution.name}, child={child.name}",
        rules=merged,
        metadata={
            **constitution.metadata,
            **child.metadata,
            "federation_parent": constitution.name,
            "federation_child": child.name,
            "federation_mode": "parent_authoritative_hardcoded",
        },
    )
