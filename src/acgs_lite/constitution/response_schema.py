"""Export constitution rules as constrained-response JSON Schema fragments."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .rule import Rule

if TYPE_CHECKING:
    from .constitution import Constitution

JSONSchema = dict[str, Any]

_SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
_MAX_SKIPPED_RULES = 100


def _unique_preserving_order(values: list[str]) -> list[str]:
    """Return unique non-empty values while preserving the original order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def is_structurally_expressible(rule: Rule) -> bool:
    """Return whether a rule can be projected into JSON Schema constraints."""
    return bool(rule.enabled and not rule.deprecated and (rule.patterns or rule.keywords))


def _skip_reason(rule: Rule) -> str:
    """Classify why a rule cannot be structurally expressed."""
    if not rule.enabled:
        return "disabled"
    if rule.deprecated:
        return "deprecated"
    return "no_structural_constraints"


def rule_to_response_property_schema(rule: Rule) -> JSONSchema | None:
    """Convert one constitution rule into a JSON Schema property definition."""
    if not is_structurally_expressible(rule):
        return None

    schema: JSONSchema = {
        "type": "string",
        "description": rule.text,
        "title": rule.id,
        "x-acgs-category": rule.category,
        "x-acgs-severity": rule.severity.value,
    }

    keywords = _unique_preserving_order(rule.keywords)
    if len(keywords) == 1:
        schema["const"] = keywords[0]
    elif keywords:
        schema["enum"] = keywords

    patterns = _unique_preserving_order(rule.patterns)
    if len(patterns) == 1:
        schema["pattern"] = patterns[0]
    elif patterns:
        schema["allOf"] = [{"pattern": pattern} for pattern in patterns]

    return schema


def constitution_to_response_schema(
    constitution: Constitution,
    *,
    strict: bool = False,
) -> JSONSchema:
    """Build a response schema that captures structurally expressible rules only.

    Args:
        constitution: The constitution to export.
        strict: If ``True``, set ``additionalProperties: false`` to reject any
            fields not derived from constitutional rules.  Defaults to ``False``
            (permissive) so that LLMs can include extra content fields without
            being token-masked into hallucinating schema-compliant garbage.
    """
    properties: JSONSchema = {}
    required: list[str] = []
    skipped: list[JSONSchema] = []

    for rule in constitution.rules:
        if rule.deprecated or not rule.enabled:
            skipped.append({"id": rule.id, "reason": _skip_reason(rule)})
            continue
        property_schema = rule_to_response_property_schema(rule)
        if property_schema is None:
            skipped.append({"id": rule.id, "reason": _skip_reason(rule)})
            continue
        properties[rule.id] = property_schema
        if rule.severity.blocks():
            required.append(rule.id)

    total_skipped = len(skipped)

    return {
        "$schema": _SCHEMA_URI,
        "title": f"{constitution.name} Response Schema",
        "description": (
            "LLM output schema derived from structurally expressible constitutional rules."
        ),
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": not strict,
        "x-acgs-constitution-name": constitution.name,
        "x-acgs-constitution-version": constitution.version,
        "x-acgs-constitutional-hash": constitution.hash,
        "x-acgs-exported-rule-count": len(properties),
        "x-acgs-skipped-rules": skipped[:_MAX_SKIPPED_RULES],
        "x-acgs-skipped-rule-count": total_skipped,
    }


__all__ = [
    "constitution_to_response_schema",
    "is_structurally_expressible",
    "rule_to_response_property_schema",
]
