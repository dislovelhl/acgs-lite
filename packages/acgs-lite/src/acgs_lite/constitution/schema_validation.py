"""Schema and rule validation helpers."""

from __future__ import annotations

from typing import Any


def validate_yaml_schema(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a constitution dict against the JSON Schema."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return {"valid": False, "errors": ["Root must be an object"], "warnings": []}

    rules = data.get("rules")
    if not rules:
        errors.append("'rules' is required and must be non-empty")
    elif not isinstance(rules, list):
        errors.append("'rules' must be an array")
    else:
        valid_severities = {"critical", "high", "medium", "low"}
        valid_workflows = {
            "",
            "block",
            "block_and_notify",
            "require_human_review",
            "escalate_to_senior",
            "warn",
        }
        seen_ids: set[str] = set()

        for i, rule in enumerate(rules):
            prefix = f"rules[{i}]"
            if not isinstance(rule, dict):
                errors.append(f"{prefix}: must be an object")
                continue

            rid = rule.get("id")
            if not rid or not isinstance(rid, str):
                errors.append(f"{prefix}: 'id' is required and must be a non-empty string")
            elif rid in seen_ids:
                errors.append(f"{prefix}: duplicate rule id '{rid}'")
            else:
                seen_ids.add(rid)

            if not rule.get("text") or not isinstance(rule.get("text"), str):
                errors.append(f"{prefix}: 'text' is required and must be a non-empty string")

            severity = rule.get("severity", "high")
            if isinstance(severity, str) and severity.lower() not in valid_severities:
                errors.append(f"{prefix}: invalid severity '{severity}'")

            workflow_action = rule.get("workflow_action", "")
            if isinstance(workflow_action, str) and workflow_action not in valid_workflows:
                errors.append(f"{prefix}: invalid workflow_action '{workflow_action}'")

            if not rule.get("keywords") and not rule.get("patterns"):
                warnings.append(f"{prefix}: rule has no keywords or patterns (will never match)")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_rules(constitution: Any) -> list[str]:
    """Validate rule syntax and semantics for a constitution."""
    errors: list[str] = []

    rule_ids = [r.id for r in constitution.rules]
    duplicates = [rid for rid in rule_ids if rule_ids.count(rid) > 1]
    for duplicate in set(duplicates):
        errors.append(f"Duplicate rule ID: {duplicate}")

    for rule in constitution.rules:
        if not rule.text or not rule.text.strip():
            errors.append(f"Rule {rule.id}: empty text")
        if len(rule.text) > 1000:
            errors.append(f"Rule {rule.id}: text too long (>1000 chars)")

        if len(rule.keywords) > 50:
            errors.append(f"Rule {rule.id}: too many keywords (>50)")

        if rule.severity.value not in ["info", "low", "medium", "high", "critical"]:
            errors.append(f"Rule {rule.id}: invalid severity {rule.severity.value}")

        for dep_id in rule.depends_on:
            if dep_id not in rule_ids:
                errors.append(f"Rule {rule.id}: depends_on references non-existent rule {dep_id}")

    return errors
