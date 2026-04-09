"""Policy-as-Code export: Rego/OPA policy generation from a Constitution.

exp141: Enables external enforcement integration (OPA, Gatekeeper, etc.) by
exporting constitutional rules as a Rego policy. Input contract: ``input.action``
(string) and optional ``input.context``. Output: ``allow``, ``deny``,
``violations`` (array of {rule_id, severity, category}).

Semantic subset: Rego export uses keyword and regex pattern matching only.
Positive-verb exclusions and negation-aware matching from the engine are not
replicated; use the engine for full ACGS-Lite semantics.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import Constitution, Rule


def _rego_escape(s: str) -> str:
    """Escape a string for use inside a Rego double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")


def _rule_to_rego_conditions(rule: Rule) -> list[str]:
    """Build Rego conditions that are true when this rule matches the action.

    Uses keyword substring match (case-insensitive via regex) and optional
    regex patterns. Caller must only pass enabled, non-deprecated rules.
    """
    conditions: list[str] = []
    action_var = "input.action"
    # OPA Rego: regex.match("(?i)keyword", s) for case-insensitive substring
    for kw in rule.keywords:
        if not kw.strip():
            continue
        # Escape for Rego string literal and for regex literal (keyword = literal substring)
        pattern_re = "(?i)" + re.escape(kw.strip())
        escaped = _rego_escape(pattern_re)
        conditions.append(f'regex.match("{escaped}", {action_var})')
    for pat in rule.patterns:
        if not pat.strip():
            continue
        try:
            re.compile(pat)
        except re.error:
            continue
        escaped = _rego_escape(pat.strip())
        conditions.append(f'regex.match("{escaped}", {action_var})')
    return conditions


def constitution_to_rego(constitution: Constitution, package_name: str = "acgs.governance") -> str:
    """Generate a Rego policy string from a Constitution.

    Exports enabled, non-deprecated rules only. Each rule becomes a Rego
    rule that pushes a violation when any of its keywords or patterns
    match ``input.action``.

    Args:
        constitution: The constitution to export.
        package_name: Rego package name (e.g. ``acgs.governance``).

    Returns:
        Full Rego policy string (package, import, default allow/deny/violations,
        per-rule match rules, and aggregation of violations).
    """
    # Use active_rules equivalent: enabled and not deprecated
    rules = [r for r in constitution.rules if r.enabled and not getattr(r, "deprecated", False)]
    lines: list[str] = [
        f"package {package_name.replace('-', '_')}",
        "",
        "import future.keywords.if",
        "import future.keywords.in",
        "import regex",
        "",
        "default allow := true",
        "default deny := false",
        "default violations := []",
        "",
        "deny if count(violations) > 0",
        "allow := not deny",
        "",
        "violations[v] if {",
        "    some rule_id in matched_rule_ids",
        '    v := {"rule_id": rule_id, "severity": severity_by_id[rule_id],'
        ' "category": category_by_id[rule_id]}',
        "}",
        "",
    ]

    # severity_by_id and category_by_id: one entry per rule
    for r in rules:
        sev = r.severity.value if hasattr(r.severity, "value") else str(r.severity)
        rid_esc = _rego_escape(r.id)
        sev_esc = _rego_escape(sev)
        cat_esc = _rego_escape(r.category)
        lines.append(f'severity_by_id["{rid_esc}"] := "{sev_esc}"')
        lines.append(f'category_by_id["{rid_esc}"] := "{cat_esc}"')
    lines.append("")

    # matched_rule_ids: set of rule IDs that matched
    for r in rules:
        conds = _rule_to_rego_conditions(r)
        if not conds:
            continue
        rule_id_esc = _rego_escape(r.id)
        # One of the conditions must be true
        cond_expr = " or ".join(conds)
        lines.append(f'matched_rule_ids["{rule_id_esc}"] if {{')
        lines.append(f"    {cond_expr}")
        lines.append("}")
        lines.append("")

    return "\n".join(lines).strip()


def constitution_to_rego_bundle(
    constitution: Constitution,
    package_name: str = "acgs.governance",
) -> dict[str, Any]:
    """Export Constitution as an OPA bundle-ready dict.

    Returns a dict with ``policy.rego`` (string) and optional ``data.json``
    (constitution metadata) for use with OPA's bundle API or file-based load.

    Args:
        constitution: The constitution to export.
        package_name: Rego package name.

    Returns:
        Dict with keys: ``policy`` (Rego string), ``metadata`` (name, version,
        hash, rule_count).
    """
    policy = constitution_to_rego(constitution, package_name=package_name)
    rules = [r for r in constitution.rules if r.enabled and not getattr(r, "deprecated", False)]
    return {
        "policy": policy,
        "metadata": {
            "name": constitution.name,
            "version": constitution.version,
            "hash": constitution.hash,
            "rule_count": len(rules),
        },
    }
