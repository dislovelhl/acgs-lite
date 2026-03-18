"""Constitution merging helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .rule import Rule, Severity

if TYPE_CHECKING:
    from .constitution import Constitution


def inherit(
    parent: Constitution,
    child: Constitution,
    *,
    override_strategy: str = "child_wins",
) -> Constitution:
    """Create a child constitution that inherits parent rules."""
    sev_rank = {
        Severity.CRITICAL: 4,
        Severity.HIGH: 3,
        Severity.MEDIUM: 2,
        Severity.LOW: 1,
    }

    child_by_id = {r.id: r for r in child.rules}
    merged: list[Rule] = []
    seen_ids: set[str] = set()

    for rule in parent.rules:
        if rule.id in child_by_id:
            child_rule = child_by_id[rule.id]
            if override_strategy == "child_wins":
                merged.append(child_rule)
            elif override_strategy == "parent_wins":
                merged.append(rule)
            elif override_strategy == "higher_severity":
                p_rank = sev_rank.get(rule.severity, 0)
                c_rank = sev_rank.get(child_rule.severity, 0)
                merged.append(child_rule if c_rank >= p_rank else rule)
            else:
                merged.append(child_rule)
        else:
            merged.append(rule)
        seen_ids.add(rule.id)

    for rule in child.rules:
        if rule.id not in seen_ids:
            merged.append(rule)

    inherited_meta = dict(parent.metadata)
    inherited_meta.update(child.metadata)
    inherited_meta["_inherited_from"] = parent.name
    inherited_meta["_override_strategy"] = override_strategy

    return child.__class__(
        name=child.name,
        version=child.version,
        description=child.description or parent.description,
        rules=merged,
        metadata=inherited_meta,
    )


def merge_constitutions(
    constitution: Constitution,
    other: Constitution,
    strategy: str = "union",
) -> Constitution:
    """Merge two constitutions with conflict resolution."""
    self_rules = {r.id: r for r in constitution.rules}
    other_rules = {r.id: r for r in other.rules}
    merged_rules: list[Rule] = []

    for rule_id in set(self_rules) & set(other_rules):
        self_rule = self_rules[rule_id]
        other_rule = other_rules[rule_id]

        if self_rule == other_rule:
            merged_rules.append(self_rule)
        elif strategy == "replace":
            merged_rules.append(other_rule)
        elif strategy == "union":
            sev_order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
            self_sev = sev_order.get(self_rule.severity.value, 0)
            other_sev = sev_order.get(other_rule.severity.value, 0)
            merged_rules.append(other_rule if other_sev > self_sev else self_rule)
        elif strategy == "strict":
            raise ValueError(f"Conflicting rule {rule_id} in strict merge mode")
        else:
            merged_rules.append(self_rule)

    for rule_id in set(self_rules) - set(other_rules):
        merged_rules.append(self_rules[rule_id])

    if strategy != "conservative":
        for rule_id in set(other_rules) - set(self_rules):
            merged_rules.append(other_rules[rule_id])

    merged_metadata = {**constitution.metadata, **other.metadata}
    merged_description = (
        f"{constitution.description} + {other.description}"
        if constitution.description and other.description
        else (constitution.description or other.description or "")
    )

    return constitution.__class__(
        name=f"{constitution.name}-merged-{other.name}",
        version=max(
            constitution.version,
            other.version,
            key=lambda v: [int(x) for x in v.split(".")],
        ),
        rules=merged_rules,
        description=merged_description,
        metadata=merged_metadata,
        permission_ceiling=constitution.permission_ceiling,
        version_name=constitution.version_name or other.version_name,
    )


def apply_amendments(
    constitution: Constitution,
    amendments: Sequence[Any],
) -> Constitution:
    """Apply amendment-like payloads to a constitution."""
    current = constitution
    if not amendments:
        return current

    for amendment in amendments:
        if isinstance(amendment, dict):
            payload = amendment
        else:
            payload = {
                "amendment_type": getattr(amendment, "amendment_type", ""),
                "changes": getattr(amendment, "changes", {}),
                "title": getattr(amendment, "title", ""),
                "description": getattr(amendment, "description", ""),
            }

        amd_type = payload.get("amendment_type", "")
        if hasattr(amd_type, "value"):
            amd_type = amd_type.value
        amd_type = str(amd_type)
        changes = dict(payload.get("changes") or {})
        reason = str(
            payload.get("title") or payload.get("reason") or payload.get("description") or ""
        )

        if amd_type == "modify_rule":
            rule_id = str(changes.get("rule_id", ""))
            update_fields = {k: v for k, v in changes.items() if k != "rule_id"}
            current = current.update_rule(rule_id, change_reason=reason, **update_fields)
            continue

        if amd_type == "modify_severity":
            rule_id = str(changes.get("rule_id", ""))
            current = current.update_rule(
                rule_id,
                severity=changes.get("severity", ""),
                change_reason=reason,
            )
            continue

        if amd_type == "modify_workflow":
            rule_id = str(changes.get("rule_id", ""))
            current = current.update_rule(
                rule_id,
                workflow_action=changes.get("workflow_action", ""),
                change_reason=reason,
            )
            continue

        if amd_type == "add_rule":
            rule_data = changes.get("rule", {})
            if isinstance(rule_data, Rule):
                new_rule = rule_data
            elif isinstance(rule_data, dict):
                new_rule = Rule(**rule_data)
            else:
                raise TypeError("add_rule amendments require a Rule or mapping payload")

            current = current.__class__(
                name=current.name,
                version=current.version,
                description=current.description,
                rules=[*current.rules, new_rule],
                metadata=dict(current.metadata),
                rule_history=dict(current.rule_history),
                changelog=[
                    *current.changelog,
                    {
                        "operation": "apply_amendment",
                        "amendment_type": amd_type,
                        "reason": reason,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                ],
                permission_ceiling=current.permission_ceiling,
                version_name=current.version_name,
            )
            continue

        if amd_type == "remove_rule":
            rule_id = str(changes.get("rule_id", ""))
            current = current.__class__(
                name=current.name,
                version=current.version,
                description=current.description,
                rules=[r for r in current.rules if r.id != rule_id],
                metadata=dict(current.metadata),
                rule_history=dict(current.rule_history),
                changelog=[
                    *current.changelog,
                    {
                        "operation": "apply_amendment",
                        "amendment_type": amd_type,
                        "rule_id": rule_id,
                        "reason": reason,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                ],
                permission_ceiling=current.permission_ceiling,
                version_name=current.version_name,
            )
            continue

    return current
