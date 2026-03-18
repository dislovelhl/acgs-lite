"""Conflict detection and resolution helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .rule import _cosine_sim

if TYPE_CHECKING:
    from .constitution import Constitution


def resolve_conflicts(
    constitution: Constitution,
    conflicts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Resolve conflicts using severity, specificity, and hardcoded precedence."""
    resolutions: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    policy_applied: list[str] = []

    severity_order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

    for conflict in conflicts:
        rule_a_id = conflict["rule_a"]
        rule_b_id = conflict["rule_b"]

        rule_a = next((r for r in constitution.rules if r.id == rule_a_id), None)
        rule_b = next((r for r in constitution.rules if r.id == rule_b_id), None)

        if not rule_a or not rule_b:
            unresolved.append(conflict)
            continue

        sev_a = severity_order.get(rule_a.severity.value, 0)
        sev_b = severity_order.get(rule_b.severity.value, 0)

        if sev_a != sev_b:
            winner = rule_a_id if sev_a > sev_b else rule_b_id
            loser = rule_b_id if sev_a > sev_b else rule_a_id
            resolutions.append(
                {
                    "action": "prioritize",
                    "winner": winner,
                    "loser": loser,
                    "reason": "severity_precedence",
                    "conflict": conflict,
                }
            )
            policy_applied.append("severity_precedence")
            continue

        spec_a = len(rule_a.keywords)
        spec_b = len(rule_b.keywords)
        if spec_a != spec_b:
            winner = rule_a_id if spec_a > spec_b else rule_b_id
            loser = rule_b_id if spec_a > spec_b else rule_a_id
            resolutions.append(
                {
                    "action": "prioritize",
                    "winner": winner,
                    "loser": loser,
                    "reason": "specificity",
                    "conflict": conflict,
                }
            )
            policy_applied.append("specificity")
            continue

        if rule_a.hardcoded != rule_b.hardcoded:
            winner = rule_a_id if rule_a.hardcoded else rule_b_id
            loser = rule_b_id if rule_a.hardcoded else rule_a_id
            resolutions.append(
                {
                    "action": "prioritize",
                    "winner": winner,
                    "loser": loser,
                    "reason": "hardcoded_precedence",
                    "conflict": conflict,
                }
            )
            policy_applied.append("hardcoded_precedence")
            continue

        unresolved.append(conflict)

    return {
        "resolutions": resolutions,
        "unresolved": unresolved,
        "policy_applied": list(set(policy_applied)),
    }


def detect_semantic_conflicts(
    constitution: Constitution,
    threshold: float = 0.8,
) -> dict[str, Any]:
    """Detect semantically similar rules with conflicting governance."""
    active = constitution.active_rules()
    rules_with_emb = [r for r in active if r.embedding]
    if len(rules_with_emb) < 2:
        return {
            "has_conflicts": False,
            "conflicts": [],
            "conflict_count": 0,
            "rules_with_embeddings": len(rules_with_emb),
            "recommendation": (
                "Need at least 2 rules with embeddings for semantic conflict detection."
            ),
        }

    conflicts: list[dict[str, Any]] = []
    checked: set[tuple[str, str]] = set()

    for i, ra in enumerate(rules_with_emb):
        for rb in rules_with_emb[i + 1 :]:
            pair = (min(ra.id, rb.id), max(ra.id, rb.id))
            if pair in checked:
                continue
            checked.add(pair)

            sim = _cosine_sim(ra.embedding, rb.embedding)
            if sim is None or sim < threshold:
                continue

            sev_conflict = ra.severity != rb.severity
            wf_conflict = (
                ra.workflow_action != rb.workflow_action
                and ra.workflow_action != ""
                and rb.workflow_action != ""
            )

            if sev_conflict or wf_conflict:
                conflict_entry: dict[str, Any] = {
                    "rule_a": ra.id,
                    "rule_b": rb.id,
                    "similarity": round(float(sim), 3),
                    "severity_conflict": sev_conflict,
                    "workflow_conflict": wf_conflict,
                }
                if sev_conflict:
                    conflict_entry["severity_a"] = ra.severity.value
                    conflict_entry["severity_b"] = rb.severity.value
                if wf_conflict:
                    conflict_entry["workflow_a"] = ra.workflow_action
                    conflict_entry["workflow_b"] = rb.workflow_action
                conflicts.append(conflict_entry)

    recommendation = ""
    if conflicts:
        recommendation = (
            f"Found {len(conflicts)} semantic conflict(s) among "
            f"{len(rules_with_emb)} rules with embeddings. "
            "Review similar rules and align severity/workflow_action."
        )
    else:
        recommendation = (
            f"No semantic conflicts detected among {len(rules_with_emb)} "
            f"rules with embeddings (threshold={threshold})."
        )

    return {
        "has_conflicts": len(conflicts) > 0,
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
        "rules_with_embeddings": len(rules_with_emb),
        "recommendation": recommendation,
    }
