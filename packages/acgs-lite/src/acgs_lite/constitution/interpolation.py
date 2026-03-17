"""exp223: Contextual variable interpolation for constitutional rules.

Allows rule text, descriptions, and condition values to embed ``${key.subkey}``
placeholders that are resolved against a runtime context dict at evaluation time.

This is **display-only** — interpolation never touches the keyword/pattern
matching hot path. It enriches audit logs, explain() output, and governance
reports by showing what values actually applied in a specific context.

Examples::

    rule = Rule(
        id="DATA-001",
        text="Agent ${agent.id} must not access ${resource.classification} data without consent.",
        severity=Severity.HIGH,
        keywords=["access", "data"],
    )
    rendered = render_text(rule.text, {"agent": {"id": "alpha"}, "resource": {"classification": "PII"}})
    # "Agent alpha must not access PII data without consent."

    # Unresolved placeholders are preserved unchanged:
    render_text("Hello ${unknown.key}", {})
    # "Hello ${unknown.key}"
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import Constitution, Rule

# Matches ${key}, ${key.subkey}, ${key.sub.nested} — letters, digits, underscores, dots
_PLACEHOLDER_RE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")


def _resolve_path(context: dict[str, Any], path: str) -> str | None:
    """Resolve a dot-notation path against a nested context dict.

    Returns the string representation of the resolved value, or ``None`` if
    any segment is missing or the context is not a dict at that level.

    Examples::

        _resolve_path({"agent": {"id": "alpha"}}, "agent.id")  # "alpha"
        _resolve_path({"agent": {"id": "alpha"}}, "agent.missing")  # None
        _resolve_path({}, "anything")  # None
    """
    parts = path.split(".")
    node: Any = context
    for part in parts:
        if not isinstance(node, dict):
            return None
        if part not in node:
            return None
        node = node[part]
    return str(node)


def render_text(text: str, context: dict[str, Any]) -> str:
    """Resolve ``${key.subkey}`` placeholders in *text* using *context*.

    Unresolved placeholders are preserved unchanged so callers can detect
    what was missing without raising an exception.

    Args:
        text: Template string potentially containing ``${...}`` placeholders.
        context: Nested dict of runtime values (e.g., ``{"agent": {"id": "x"}}``).

    Returns:
        Text with all resolvable placeholders replaced by their context values.
        Unresolvable placeholders are left as-is (``${key}`` unchanged).

    Examples::

        render_text("Agent ${agent.id} denied", {"agent": {"id": "alpha"}})
        # "Agent alpha denied"

        render_text("Agent ${agent.id} denied", {})
        # "Agent ${agent.id} denied"  -- preserved unchanged
    """
    if not context or "${" not in text:
        return text

    def _replacer(match: re.Match[str]) -> str:
        resolved = _resolve_path(context, match.group(1))
        return resolved if resolved is not None else match.group(0)

    return _PLACEHOLDER_RE.sub(_replacer, text)


def extract_placeholders(text: str) -> list[str]:
    """Return all placeholder paths found in *text*.

    Useful for validating that a rule template will resolve correctly
    given a specific context schema.

    Args:
        text: Template string to scan.

    Returns:
        List of placeholder paths in order of appearance (may contain duplicates).

    Examples::

        extract_placeholders("Agent ${agent.id} accessed ${resource.type}")
        # ["agent.id", "resource.type"]
    """
    return _PLACEHOLDER_RE.findall(text)


def render_rule(rule: Rule, context: dict[str, Any]) -> Rule:
    """Return a copy of *rule* with ``${...}`` placeholders resolved in its text.

    The original rule is never modified (immutable pattern). The returned rule
    has the same id, severity, keywords, and all other fields — only ``text``
    is interpolated. This makes the rendered rule suitable for display in audit
    logs and explain() output.

    Note: Keyword and pattern matching always uses the original rule's ``text``
    field. This function is for display/reporting only.

    Args:
        rule: Source rule to render.
        context: Runtime context dict for placeholder resolution.

    Returns:
        New Rule with interpolated text. If no placeholders exist or context
        is empty, returns the original rule unchanged (no copy overhead).
    """
    if not context or "${" not in rule.text:
        return rule
    rendered = render_text(rule.text, context)
    if rendered == rule.text:
        return rule
    return rule.model_copy(update={"text": rendered})


def render_constitution(constitution: Constitution, context: dict[str, Any]) -> Constitution:
    """Return a copy of *constitution* with all rule texts interpolated.

    Only rules whose texts contain ``${...}`` placeholders are copied; others
    are reused as-is to minimise allocation.

    Args:
        constitution: Source constitution to render.
        context: Runtime context dict for placeholder resolution.

    Returns:
        New Constitution with rendered rule texts. If no rules have placeholders,
        returns the original constitution unchanged.
    """
    if not context:
        return constitution

    rendered_rules = []
    any_changed = False
    for rule in constitution.rules:
        rendered = render_rule(rule, context)
        rendered_rules.append(rendered)
        if rendered is not rule:
            any_changed = True

    if not any_changed:
        return constitution

    return constitution.model_copy(update={"rules": rendered_rules})


def context_coverage(rules: list[Rule]) -> dict[str, list[str]]:
    """Report which context paths each rule depends on.

    Scans all rule texts for ``${...}`` placeholders and returns a mapping
    of rule ID to list of required context paths. Useful for validating
    that a context dict will fully resolve all rule templates before a
    governance session starts.

    Args:
        rules: List of rules to analyse.

    Returns:
        Dict mapping rule_id -> list of placeholder paths. Rules with no
        placeholders are omitted.

    Examples::

        context_coverage([rule_with_agent_id, rule_without_placeholders])
        # {"DATA-001": ["agent.id", "resource.classification"]}
    """
    result: dict[str, list[str]] = {}
    for rule in rules:
        paths = extract_placeholders(rule.text)
        if paths:
            result[rule.id] = paths
    return result


def validate_context_schema(
    rules: list[Rule],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Check that *context* can resolve all placeholders in *rules*.

    Returns a report of resolved and unresolved placeholders, allowing
    callers to detect missing context keys before governance evaluation.

    Args:
        rules: Rules whose texts may contain ``${...}`` placeholders.
        context: Runtime context dict to validate against.

    Returns:
        Dict with keys:

        - ``"resolved"``: list of (rule_id, path) tuples that resolved OK
        - ``"unresolved"``: list of (rule_id, path) tuples that could not resolve
        - ``"complete"``: bool, True if all placeholders resolved
        - ``"coverage_pct"``: float, fraction of placeholders that resolved (0-100)

    Examples::

        report = validate_context_schema(constitution.rules, {"agent": {"id": "x"}})
        if not report["complete"]:
            print("Missing context:", report["unresolved"])
    """
    resolved: list[tuple[str, str]] = []
    unresolved: list[tuple[str, str]] = []

    for rule in rules:
        for path in extract_placeholders(rule.text):
            if _resolve_path(context, path) is not None:
                resolved.append((rule.id, path))
            else:
                unresolved.append((rule.id, path))

    total = len(resolved) + len(unresolved)
    coverage_pct = (len(resolved) / total * 100.0) if total > 0 else 100.0

    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "complete": len(unresolved) == 0,
        "coverage_pct": round(coverage_pct, 1),
    }
