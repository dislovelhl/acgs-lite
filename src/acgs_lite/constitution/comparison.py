"""Constitution comparison helpers — diff, compare, subsumes, counterfactual."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from .rule import Severity

if TYPE_CHECKING:
    from .constitution import Constitution


def diff(constitution: Constitution, other: Constitution) -> dict[str, Any]:
    """exp98: Compare two constitutions and report changes.

    Essential for governance auditing and change management. Returns
    a structured diff showing added, removed, and modified rules so
    compliance teams can review constitutional changes before deployment.

    Args:
        constitution: The baseline constitution.
        other: The constitution to compare against (typically the newer version).

    Returns:
        dict with keys:
            - ``hash_changed``: bool
            - ``old_hash``: this constitution's hash
            - ``new_hash``: other constitution's hash
            - ``added``: list of rule IDs present in other but not constitution
            - ``removed``: list of rule IDs present in constitution but not other
            - ``modified``: list of dicts describing per-rule changes
            - ``severity_changes``: list of rules where severity changed
            - ``summary``: human-readable change summary string
    """
    self_rules = {r.id: r for r in constitution.rules}
    other_rules = {r.id: r for r in other.rules}

    self_ids = set(self_rules)
    other_ids = set(other_rules)

    added = sorted(other_ids - self_ids)
    removed = sorted(self_ids - other_ids)

    modified: list[dict[str, Any]] = []
    severity_changes: list[dict[str, str]] = []

    for rid in sorted(self_ids & other_ids):
        old_r = self_rules[rid]
        new_r = other_rules[rid]
        changes: dict[str, tuple[str, str]] = {}

        if old_r.text != new_r.text:
            changes["text"] = (old_r.text, new_r.text)
        if old_r.severity != new_r.severity:
            changes["severity"] = (old_r.severity.value, new_r.severity.value)
            severity_changes.append(
                {"rule_id": rid, "old": old_r.severity.value, "new": new_r.severity.value}
            )
        if old_r.category != new_r.category:
            changes["category"] = (old_r.category, new_r.category)
        if old_r.subcategory != new_r.subcategory:
            changes["subcategory"] = (old_r.subcategory, new_r.subcategory)
        if old_r.workflow_action != new_r.workflow_action:
            changes["workflow_action"] = (old_r.workflow_action, new_r.workflow_action)
        if old_r.enabled != new_r.enabled:
            changes["enabled"] = (str(old_r.enabled), str(new_r.enabled))
        if old_r.hardcoded != new_r.hardcoded:
            changes["hardcoded"] = (str(old_r.hardcoded), str(new_r.hardcoded))
        if sorted(old_r.keywords) != sorted(new_r.keywords):
            changes["keywords"] = (
                ",".join(sorted(old_r.keywords)),
                ",".join(sorted(new_r.keywords)),
            )
        if old_r.priority != new_r.priority:
            changes["priority"] = (str(old_r.priority), str(new_r.priority))

        if changes:
            modified.append({"rule_id": rid, "changes": changes})

    parts: list[str] = []
    if added:
        parts.append(f"+{len(added)} rules")
    if removed:
        parts.append(f"-{len(removed)} rules")
    if modified:
        parts.append(f"~{len(modified)} modified")
    if severity_changes:
        parts.append(f"{len(severity_changes)} severity changes")
    summary = ", ".join(parts) if parts else "no changes"

    return {
        "hash_changed": constitution.hash != other.hash,
        "old_hash": constitution.hash,
        "new_hash": other.hash,
        "added": added,
        "removed": removed,
        "modified": modified,
        "severity_changes": severity_changes,
        "summary": summary,
    }


def compare(
    before: Constitution,
    after: Constitution,
) -> dict[str, Any]:
    """exp122: Compare two constitutions and return structured differences.

    Unlike ``diff``, this function takes both constitutions as parameters,
    making the temporal relationship explicit.  Useful for deployment gates,
    CI/CD checks, and audit trails where neither constitution is privileged
    as "current".

    Args:
        before: The baseline constitution.
        after: The updated constitution.

    Returns:
        dict with keys:
            - ``added``: list of rule IDs only in *after*
            - ``removed``: list of rule IDs only in *before*
            - ``modified``: list of dicts describing changed rules
            - ``unchanged``: count of rules present in both with no changes
            - ``summary``: human-readable change summary
    """
    before_map = {r.id: r for r in before.rules}
    after_map = {r.id: r for r in after.rules}

    before_ids = set(before_map)
    after_ids = set(after_map)

    added = sorted(after_ids - before_ids)
    removed = sorted(before_ids - after_ids)
    common_ids = before_ids & after_ids

    modified: list[dict[str, Any]] = []
    unchanged = 0

    for rid in sorted(common_ids):
        b_rule = before_map[rid]
        a_rule = after_map[rid]
        changes: list[str] = []

        if b_rule.severity != a_rule.severity:
            changes.append(f"severity: {b_rule.severity.value} -> {a_rule.severity.value}")
        if b_rule.text != a_rule.text:
            changes.append("text changed")
        if set(b_rule.keywords) != set(a_rule.keywords):
            changes.append(f"keywords: {len(b_rule.keywords)} -> {len(a_rule.keywords)}")
        if set(b_rule.patterns) != set(a_rule.patterns):
            changes.append(f"patterns: {len(b_rule.patterns)} -> {len(a_rule.patterns)}")
        if b_rule.workflow_action != a_rule.workflow_action:
            changes.append(
                f"workflow_action: {b_rule.workflow_action or '(none)'}"
                f" -> {a_rule.workflow_action or '(none)'}"
            )
        if b_rule.enabled != a_rule.enabled:
            changes.append(f"enabled: {b_rule.enabled} -> {a_rule.enabled}")
        if set(b_rule.tags) != set(a_rule.tags):
            changes.append(f"tags: {b_rule.tags} -> {a_rule.tags}")
        if b_rule.category != a_rule.category:
            changes.append(f"category: {b_rule.category} -> {a_rule.category}")
        if b_rule.priority != a_rule.priority:
            changes.append(f"priority: {b_rule.priority} -> {a_rule.priority}")

        if changes:
            modified.append({"rule_id": rid, "changes": changes})
        else:
            unchanged += 1

    parts = []
    if added:
        parts.append(f"{len(added)} added")
    if removed:
        parts.append(f"{len(removed)} removed")
    if modified:
        parts.append(f"{len(modified)} modified")
    if unchanged:
        parts.append(f"{unchanged} unchanged")
    summary = ", ".join(parts) if parts else "No differences"

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged,
        "summary": summary,
    }


def subsumes(
    superset: Constitution,
    subset: Constitution,
) -> dict[str, Any]:
    """exp144: Check whether one constitution subsumes another.

    A constitution *superset* is said to subsume *subset* if every rule in
    *subset* is present in *superset* with severity and blocking power that
    are at least as strong, and with compatible workflow actions. This is a
    static, offline analysis intended for CI/CD gates and cross-tenant
    policy comparison — it never runs on the hot validation path.

    Args:
        superset: Candidate stronger/wider constitution.
        subset: Constitution that must be covered by ``superset``.

    Returns:
        dict with keys:
            - ``subsumes``: bool indicating if superset fully subsumes subset
            - ``missing_rules``: rule IDs present only in subset
            - ``weaker_rules``: rule IDs where superset has weaker severity
            - ``incompatible_workflow``: rule IDs with conflicting workflow_action
            - ``details``: per-rule comparison records for diagnostics
    """
    _SEV_RANK = {
        Severity.CRITICAL: 4,
        Severity.HIGH: 3,
        Severity.MEDIUM: 2,
        Severity.LOW: 1,
    }

    super_map = {r.id: r for r in superset.rules}
    sub_map = {r.id: r for r in subset.rules}

    missing: list[str] = []
    weaker: list[str] = []
    incompatible: list[str] = []
    details: list[dict[str, Any]] = []

    for rid, s_rule in sorted(sub_map.items()):
        super_rule = super_map.get(rid)
        if super_rule is None:
            missing.append(rid)
            details.append(
                {
                    "rule_id": rid,
                    "status": "missing",
                    "subset_severity": s_rule.severity.value,
                    "superset_severity": None,
                }
            )
            continue

        sev_sub = _SEV_RANK.get(s_rule.severity, 0)
        sev_super = _SEV_RANK.get(super_rule.severity, 0)
        workflow_sub = s_rule.workflow_action or ""
        workflow_super = super_rule.workflow_action or ""

        is_weaker = sev_super < sev_sub
        # Treat stricter workflow actions as compatible; only flag if
        # superset is more permissive than subset for the same rule.
        workflow_weaker = workflow_sub in {
            "block",
            "block_and_notify",
            "require_human_review",
        } and workflow_super in {"", "warn"}

        status = "ok"
        if is_weaker:
            weaker.append(rid)
            status = "weaker_severity"
        elif workflow_weaker:
            incompatible.append(rid)
            status = "weaker_workflow"

        details.append(
            {
                "rule_id": rid,
                "status": status,
                "subset_severity": s_rule.severity.value,
                "superset_severity": super_rule.severity.value,
                "subset_workflow": workflow_sub or "(none)",
                "superset_workflow": workflow_super or "(none)",
            }
        )

    subsumes_all = not missing and not weaker and not incompatible

    return {
        "subsumes": subsumes_all,
        "missing_rules": missing,
        "weaker_rules": weaker,
        "incompatible_workflow": incompatible,
        "details": details,
    }


def counterfactual(
    constitution: Constitution,
    action: str,
    *,
    remove_rules: Sequence[str] | None = None,
    context: dict[str, Any] | None = None,
    agent_id: str = "counterfactual",
) -> dict[str, Any]:
    """exp143: Evaluate how removing rules would change a decision.

    Runs a baseline validation against this constitution, then a
    counterfactual validation against a copy with the specified rules
    removed. Useful for A/B testing proposed rule changes, tuning
    dependencies, and explaining the practical impact of individual rules.

    This helper is intentionally off the hot path: it builds a fresh
    GovernanceEngine instance and performs two validations on demand. It
    is never called from the benchmark harness and has zero impact on
    latency or throughput metrics.

    Args:
        constitution: The constitution to evaluate against.
        action: Free-text description of the action to validate.
        remove_rules: Iterable of rule IDs to virtually remove.
        context: Optional context dict passed through to validation.
        agent_id: Logical agent identifier for audit and stats.

    Returns:
        dict with keys:
            - ``removed_rules``: sorted list of rule IDs removed
            - ``baseline``: ValidationResult.to_dict() under current rules
            - ``counterfactual``: ValidationResult.to_dict() with rules removed
            - ``changed``: bool indicating whether decision/violations differ
    """
    # Local import to avoid creating a hard dependency at module import
    # time; keeps core engine wiring flexible for alternative runtimes.
    from acgs_lite.engine.core import GovernanceEngine

    # Lazy import to access Constitution class at runtime without circular deps.
    from .constitution import Constitution as _Constitution

    remove_set = {rid for rid in (remove_rules or []) if rid}

    # Baseline: validate against the current constitution without raising
    # on blocking violations so we can compare outcomes structurally.
    baseline_engine = GovernanceEngine(constitution, strict=False)
    baseline_result = baseline_engine.validate(
        action,
        agent_id=agent_id,
        context=context or {},
    )

    if not remove_set:
        baseline_dict = baseline_result.to_dict()
        return {
            "removed_rules": [],
            "baseline": baseline_dict,
            "counterfactual": baseline_dict,
            "changed": False,
        }

    # Build a counterfactual constitution with the specified rules removed.
    cf_rules = [r for r in constitution.rules if r.id not in remove_set]
    if not cf_rules:
        raise ValueError("Counterfactual would remove all rules; at least one rule must remain")

    cf_constitution = _Constitution(
        name=f"{constitution.name}-counterfactual",
        version=constitution.version,
        description=constitution.description,
        rules=cf_rules,
        metadata={
            **constitution.metadata,
            "counterfactual": True,
            "removed_rules": sorted(remove_set),
        },
    )
    cf_engine = GovernanceEngine(cf_constitution, strict=False)
    cf_result = cf_engine.validate(
        action,
        agent_id=agent_id,
        context=context or {},
    )

    baseline_dict = baseline_result.to_dict()
    cf_dict = cf_result.to_dict()

    baseline_ids = [v["rule_id"] for v in baseline_dict.get("violations", [])]
    cf_ids = [v["rule_id"] for v in cf_dict.get("violations", [])]
    changed = baseline_dict.get("valid") != cf_dict.get("valid") or baseline_ids != cf_ids

    return {
        "removed_rules": sorted(remove_set),
        "baseline": baseline_dict,
        "counterfactual": cf_dict,
        "changed": changed,
    }
