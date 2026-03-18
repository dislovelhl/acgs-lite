"""Workflow analytics helpers for constitutions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .constitution import Constitution


def analyze_workflow_distribution(constitution: Constitution) -> dict[str, Any]:
    """Return governance posture summary for dashboards and introspection."""
    active = constitution.active_rules()
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_subcategory: dict[str, int] = {}
    by_workflow: dict[str, int] = {}
    by_tag: dict[str, int] = {}

    for rule in active:
        severity = rule.severity.value
        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_category[rule.category] = by_category.get(rule.category, 0) + 1
        if rule.subcategory:
            by_subcategory[rule.subcategory] = by_subcategory.get(rule.subcategory, 0) + 1
        workflow = rule.workflow_action or "unspecified"
        by_workflow[workflow] = by_workflow.get(workflow, 0) + 1
        for tag in rule.tags:
            by_tag[tag] = by_tag.get(tag, 0) + 1

    has_keywords = sum(1 for rule in active if rule.keywords)
    has_patterns = sum(1 for rule in active if rule.patterns)
    has_workflow = sum(1 for rule in active if rule.workflow_action)
    has_subcategory = sum(1 for rule in active if rule.subcategory)
    has_tags = sum(1 for rule in active if rule.tags)

    return {
        "total_rules": len(constitution.rules),
        "active_rules": len(active),
        "by_severity": by_severity,
        "by_category": by_category,
        "by_subcategory": by_subcategory,
        "by_workflow_action": by_workflow,
        "by_tag": by_tag,
        "coverage": {
            "keyword_rules": has_keywords,
            "pattern_rules": has_patterns,
            "workflow_routed": has_workflow,
            "subcategorized": has_subcategory,
            "tagged": has_tags,
            "blocking_rules": sum(1 for rule in active if rule.severity.blocks()),
        },
    }


def changelog_summary(constitution: Constitution) -> dict[str, Any]:
    """Summarise the constitution-level change log."""
    total = len(constitution.changelog)
    by_op: dict[str, int] = {}
    affected: set[str] = set()
    for entry in constitution.changelog:
        op = entry.get("operation", "unknown")
        by_op[op] = by_op.get(op, 0) + 1
        rule_id = entry.get("rule_id", "")
        if rule_id:
            affected.add(rule_id)

    recent = list(reversed(constitution.changelog[-5:])) if constitution.changelog else []

    return {
        "total_changes": total,
        "by_operation": by_op,
        "recent": recent,
        "affected_rules": sorted(affected),
    }


governance_summary = analyze_workflow_distribution
