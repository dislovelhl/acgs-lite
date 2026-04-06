"""Dependency analysis helpers for constitutions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .constitution import Constitution


def dependency_graph(constitution: Constitution) -> dict[str, Any]:
    """exp99: Return the inter-rule dependency graph.

    Shows which rules depend on or reinforce other rules. Governance
    dashboards and impact analysis tools use this to understand how
    disabling or modifying one rule might affect the overall constitutional
    posture.

    Returns:
        dict with keys:
            - ``edges``: list of (from_id, to_id) dependency pairs
            - ``roots``: rule IDs with no dependencies (foundational rules)
            - ``dependents``: dict mapping rule_id -> list of rules that depend on it
            - ``orphans``: rule IDs that no other rule depends on and have no deps
    """
    all_ids = {r.id for r in constitution.rules}
    edges: list[tuple[str, str]] = []
    has_deps: set[str] = set()
    depended_on: set[str] = set()
    dependents: dict[str, list[str]] = {}

    for r in constitution.rules:
        for dep_id in r.depends_on:
            if dep_id in all_ids:
                edges.append((r.id, dep_id))
                has_deps.add(r.id)
                depended_on.add(dep_id)
                dependents.setdefault(dep_id, []).append(r.id)

    roots = sorted(all_ids - has_deps)
    orphans = sorted((all_ids - has_deps) - depended_on)

    return {
        "edges": edges,
        "roots": roots,
        "dependents": dict(sorted(dependents.items())),
        "orphans": orphans,
    }


def rule_dependencies(constitution: Constitution) -> dict[str, Any]:
    """exp157: Analyze implicit rule dependencies based on content analysis.

    Performs semantic analysis to identify potential dependencies between rules
    based on keyword overlap, severity relationships, and workflow patterns.
    Useful for governance impact analysis when explicit dependencies aren't defined.

    Returns:
        dict with keys:
            - ``semantic_edges``: list of (rule_id, rule_id, confidence) triples
              for potential dependencies
            - ``severity_chains``: rules that form severity escalation chains
            - ``keyword_clusters``: groups of rules that share significant keyword overlap
            - ``workflow_groups``: rules grouped by workflow patterns
    """
    # Semantic dependency analysis based on keyword overlap
    semantic_edges: list[tuple[str, str, float]] = []
    keyword_clusters: dict[str, list[str]] = {}
    workflow_groups: dict[str, list[str]] = {}

    # Group rules by workflow (extracted from keywords/metadata)
    for rule in constitution.rules:
        workflow = rule.metadata.get("workflow", "general")
        workflow_groups.setdefault(workflow, []).append(rule.id)

    # Find keyword clusters (rules sharing >50% keywords)
    rule_keywords = {r.id: set(r.keywords) for r in constitution.rules}

    for i, rule_a in enumerate(constitution.rules):
        cluster_key = f"cluster_{i}"
        cluster = [rule_a.id]

        for rule_b in constitution.rules[i + 1 :]:
            overlap = len(rule_keywords[rule_a.id] & rule_keywords[rule_b.id])
            total = len(rule_keywords[rule_a.id] | rule_keywords[rule_b.id])
            if total > 0 and overlap / total > 0.5:  # >50% overlap
                cluster.append(rule_b.id)
                confidence = overlap / total
                semantic_edges.append((rule_a.id, rule_b.id, confidence))

        if len(cluster) > 1:
            keyword_clusters[cluster_key] = cluster

    # Find severity chains (lower severity rules that might lead to higher severity)
    severity_chains: list[list[str]] = []
    severity_order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

    for rule in constitution.rules:
        chain = [rule.id]
        current_sev = severity_order.get(rule.severity.value, 0)

        # Look for rules that might be prerequisites (lower severity, related keywords)
        for other in constitution.rules:
            if other.id != rule.id:
                other_sev = severity_order.get(other.severity.value, 0)
                if (
                    other_sev < current_sev
                    and len(rule_keywords[rule.id] & rule_keywords[other.id]) > 0
                ):
                    chain.append(other.id)

        if len(chain) > 1:
            severity_chains.append(sorted(chain))

    return {
        "semantic_edges": semantic_edges,
        "severity_chains": severity_chains,
        "keyword_clusters": keyword_clusters,
        "workflow_groups": workflow_groups,
    }


def validate_integrity(constitution: Constitution) -> dict[str, Any]:
    """exp102: Check internal consistency of this constitution.

    Validates structural correctness: unique IDs, valid dependency
    references, no circular dependencies, known workflow_action values,
    and coverage gaps. Governance operators run this before deploying
    a constitution to catch configuration errors early.

    Returns:
        dict with keys:
            - ``valid``: True if no errors found
            - ``errors``: list of error description strings
            - ``warnings``: list of warning description strings
    """
    _KNOWN_WORKFLOW_ACTIONS = frozenset(
        {
            "",
            "block",
            "block_and_notify",
            "require_human_review",
            "escalate_to_senior",
            "warn",
            "halt_and_alert",
        }
    )
    errors: list[str] = []
    warnings: list[str] = []

    # Check unique IDs
    ids = [r.id for r in constitution.rules]
    seen: set[str] = set()
    for rid in ids:
        if rid in seen:
            errors.append(f"Duplicate rule ID: {rid}")
        seen.add(rid)

    # Check dependency references
    valid_ids = set(ids)
    for r in constitution.rules:
        for dep in r.depends_on:
            if dep not in valid_ids:
                errors.append(f"Rule {r.id} depends_on unknown rule: {dep}")
            if dep == r.id:
                errors.append(f"Rule {r.id} depends on itself")

    # Check for circular dependencies (simple DFS)
    adj: dict[str, list[str]] = {r.id: list(r.depends_on) for r in constitution.rules}
    visited: set[str] = set()
    in_stack: set[str] = set()

    def _has_cycle(node: str) -> bool:
        if node in in_stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        in_stack.add(node)
        for dep in adj.get(node, []):
            if _has_cycle(dep):
                return True
        in_stack.discard(node)
        return False

    for rid in valid_ids:
        if _has_cycle(rid):
            errors.append(f"Circular dependency detected involving rule: {rid}")
            break

    # Check workflow_action values
    for r in constitution.rules:
        if r.workflow_action and r.workflow_action not in _KNOWN_WORKFLOW_ACTIONS:
            warnings.append(f"Rule {r.id} has unknown workflow_action: {r.workflow_action}")

    # Coverage warnings
    no_keywords = [r.id for r in constitution.rules if not r.keywords and not r.patterns]
    if no_keywords:
        warnings.append(
            f"Rules with no keywords or patterns (will never match): {', '.join(no_keywords)}"
        )

    no_workflow = [r.id for r in constitution.rules if r.enabled and not r.workflow_action]
    if no_workflow:
        warnings.append(f"Enabled rules without workflow_action: {', '.join(no_workflow)}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def blast_radius(constitution: Constitution, rule_id: str) -> dict[str, Any]:
    """exp152: Impact analysis -- rule IDs affected if this rule is changed or removed.

    Returns dependent rule IDs (rules that list this rule in depends_on) and
    the successor rule ID (replaced_by) if this rule is deprecated. For
    change-impact and rollout planning; zero hot-path overhead.

    Returns:
        dict with keys: dependent_rule_ids (list), successor_rule_id (str or None)
    """
    dependent = [r.id for r in constitution.rules if rule_id in (r.depends_on or [])]
    rule = constitution.get_rule(rule_id)
    successor = (rule.replaced_by or "").strip() or None if rule else None
    return {"dependent_rule_ids": dependent, "successor_rule_id": successor}
