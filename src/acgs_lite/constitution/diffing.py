"""Structured constitution diffs and amendment review artifacts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from . import provenance

if TYPE_CHECKING:
    from .constitution import Constitution
    from .rule import Rule


_TRACKED_FIELDS = (
    "text",
    "severity",
    "workflow_action",
    "keywords",
    "patterns",
    "category",
    "tags",
    "enabled",
    "priority",
    "condition",
    "deprecated",
    "valid_from",
    "valid_until",
)


def _normalize(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    return value


def _rule_snapshot(rule: Rule) -> dict[str, Any]:
    snapshot = {
        "id": rule.id,
        "text": rule.text,
        "severity": _normalize(rule.severity),
        "workflow_action": _normalize(rule.workflow_action),
        "keywords": sorted(rule.keywords),
        "patterns": list(rule.patterns),
        "category": rule.category,
        "tags": sorted(rule.tags),
        "enabled": rule.enabled,
        "priority": rule.priority,
        "condition": _normalize(rule.condition),
        "deprecated": rule.deprecated,
        "valid_from": rule.valid_from,
        "valid_until": rule.valid_until,
    }
    return snapshot


def _field_change_descriptions(field_changes: dict[str, dict[str, Any]]) -> list[str]:
    descriptions: list[str] = []
    for field_name, change in field_changes.items():
        if field_name == "text":
            descriptions.append("text changed")
        elif field_name in {"keywords", "patterns"}:
            descriptions.append(f"{field_name}: {len(change['before'])} -> {len(change['after'])}")
        else:
            descriptions.append(f"{field_name}: {change['before']} -> {change['after']}")
    return descriptions


def _build_lineage(before: Constitution, after: Constitution) -> dict[str, Any]:
    return {
        "hash_transition": [before.hash, after.hash],
        "before": {
            "name": before.name,
            "version": before.version,
            "version_name": before.version_name,
            "constitutional_hash": before.hash,
        },
        "after": {
            "name": after.name,
            "version": after.version,
            "version_name": after.version_name,
            "constitutional_hash": after.hash,
        },
        "rule_provenance": provenance.rule_provenance_graph(after),
    }


def _coerce_amendment_metadata(amendments: list[Any]) -> list[dict[str, Any]]:
    metadata: list[dict[str, Any]] = []
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
        amendment_type = payload.get("amendment_type", "")
        if hasattr(amendment_type, "value"):
            amendment_type = amendment_type.value
        metadata.append(
            {
                "amendment_type": str(amendment_type),
                "title": str(payload.get("title", "")),
                "description": str(payload.get("description", "")),
                "changes": payload.get("changes", {}),
            }
        )
    return metadata


@dataclass(frozen=True, slots=True)
class RuleDiff:
    """Rule-level diff artifact with field-by-field changes."""

    rule_id: str
    change_type: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    field_changes: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "change_type": self.change_type,
            "before": self.before,
            "after": self.after,
            "field_changes": self.field_changes,
            "changes": _field_change_descriptions(self.field_changes),
        }


@dataclass(frozen=True, slots=True)
class ConstitutionDiff:
    """Structured constitution diff for review and reporting."""

    before_hash: str
    after_hash: str
    added_rules: list[RuleDiff] = field(default_factory=list)
    removed_rules: list[RuleDiff] = field(default_factory=list)
    modified_rules: list[RuleDiff] = field(default_factory=list)
    unchanged: int = 0
    lineage: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        parts: list[str] = []
        if self.added_rules:
            parts.append(f"{len(self.added_rules)} added")
        if self.removed_rules:
            parts.append(f"{len(self.removed_rules)} removed")
        if self.modified_rules:
            parts.append(f"{len(self.modified_rules)} modified")
        if self.unchanged:
            parts.append(f"{self.unchanged} unchanged")
        return ", ".join(parts) if parts else "No differences"

    def to_dict(self) -> dict[str, Any]:
        return {
            "hash_changed": self.before_hash != self.after_hash,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "old_hash": self.before_hash,
            "new_hash": self.after_hash,
            "added": [rule.rule_id for rule in self.added_rules],
            "removed": [rule.rule_id for rule in self.removed_rules],
            "modified": [rule.to_dict() for rule in self.modified_rules],
            "unchanged": self.unchanged,
            "lineage": self.lineage,
            "added_rules": [rule.to_dict() for rule in self.added_rules],
            "removed_rules": [rule.to_dict() for rule in self.removed_rules],
            "modified_rules": [rule.to_dict() for rule in self.modified_rules],
            "summary": self.summary(),
        }


@dataclass(frozen=True, slots=True)
class AmendmentReviewReport:
    """Review artifact returned when amendments are applied."""

    before_hash: str
    after_hash: str
    diff: ConstitutionDiff
    amendment_metadata: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        titles = [item["title"] for item in self.amendment_metadata if item.get("title")]
        prefix = f"{len(self.amendment_metadata)} amendment(s) applied"
        if titles:
            prefix += f": {', '.join(titles)}"
        return f"{prefix} | {self.diff.summary()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "diff": self.diff.to_dict(),
            "amendment_metadata": self.amendment_metadata,
            "lineage": self.diff.lineage,
            "summary": self.summary(),
        }


def compare_constitutions(before: Constitution, after: Constitution) -> ConstitutionDiff:
    """Build a structured diff between two constitutions."""
    before_rules = {rule.id: rule for rule in before.rules}
    after_rules = {rule.id: rule for rule in after.rules}

    before_ids = set(before_rules)
    after_ids = set(after_rules)

    added_rules = [
        RuleDiff(
            rule_id=rule_id,
            change_type="added",
            before=None,
            after=_rule_snapshot(after_rules[rule_id]),
        )
        for rule_id in sorted(after_ids - before_ids)
    ]
    removed_rules = [
        RuleDiff(
            rule_id=rule_id,
            change_type="removed",
            before=_rule_snapshot(before_rules[rule_id]),
            after=None,
        )
        for rule_id in sorted(before_ids - after_ids)
    ]

    modified_rules: list[RuleDiff] = []
    unchanged = 0
    for rule_id in sorted(before_ids & after_ids):
        before_snapshot = _rule_snapshot(before_rules[rule_id])
        after_snapshot = _rule_snapshot(after_rules[rule_id])
        field_changes: dict[str, dict[str, Any]] = {}
        for field_name in _TRACKED_FIELDS:
            if before_snapshot[field_name] != after_snapshot[field_name]:
                field_changes[field_name] = {
                    "before": before_snapshot[field_name],
                    "after": after_snapshot[field_name],
                }
        if field_changes:
            modified_rules.append(
                RuleDiff(
                    rule_id=rule_id,
                    change_type="modified",
                    before=before_snapshot,
                    after=after_snapshot,
                    field_changes=field_changes,
                )
            )
        else:
            unchanged += 1

    return ConstitutionDiff(
        before_hash=before.hash,
        after_hash=after.hash,
        added_rules=added_rules,
        removed_rules=removed_rules,
        modified_rules=modified_rules,
        unchanged=unchanged,
        lineage=_build_lineage(before, after),
    )


def compare(before: Constitution, after: Constitution) -> dict[str, Any]:
    """Compatibility wrapper returning dict-shaped structured compare output."""
    return compare_constitutions(before, after).to_dict()


def diff_summary(before: Constitution, after: Constitution) -> str:
    """Return a concise human-readable diff summary."""
    return compare_constitutions(before, after).summary()


def amendment_review_report(
    before: Constitution,
    after: Constitution,
    amendments: list[Any],
) -> AmendmentReviewReport:
    """Build a review artifact for an amendment application."""
    diff = compare_constitutions(before, after)
    return AmendmentReviewReport(
        before_hash=before.hash,
        after_hash=after.hash,
        diff=diff,
        amendment_metadata=_coerce_amendment_metadata(amendments),
    )


__all__ = [
    "AmendmentReviewReport",
    "ConstitutionDiff",
    "RuleDiff",
    "amendment_review_report",
    "compare",
    "compare_constitutions",
    "diff_summary",
]
