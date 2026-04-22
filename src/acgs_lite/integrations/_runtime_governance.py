"""Shared runtime-governance helpers used across integrations."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, cast

from acgs_lite.constitution.experience_library import GovernanceExperienceLibrary
from acgs_lite.constitution.semantic_search import EmbeddingProvider

_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def derive_precedent_decision(result: Any) -> str:
    """Map a validation result to a stable precedent decision label."""
    action_taken = getattr(result, "action_taken", None)
    if action_taken is not None:
        action_value = action_taken.value
        if action_value == "warn":
            return "warn"
        if action_value in {"require_human_review", "escalate_to_senior", "halt_and_alert"}:
            return "escalate"
        if action_value in {"block", "block_and_notify"}:
            return "deny"

    if getattr(result, "warnings", None):
        return "warn"
    return "allow" if getattr(result, "valid", False) else "deny"


def highest_violation(result: Any) -> Any | None:
    """Return the highest-severity blocking violation, if any."""
    violations = list(getattr(result, "violations", []))
    if not violations:
        return None
    return max(violations, key=lambda violation: _SEVERITY_RANK.get(violation.severity.value, 0))


def derive_precedent_rationale(result: Any, decision: str) -> str:
    """Generate a concise rationale from the finished validation result."""
    violations = list(getattr(result, "violations", []))
    if violations:
        rule_ids = ", ".join(violation.rule_id for violation in violations)
        prefix = "Escalated" if decision == "escalate" else "Blocked"
        return f"{prefix} by rules: {rule_ids}."

    warnings = list(getattr(result, "warnings", []))
    if warnings:
        rule_ids = ", ".join(warning.rule_id for warning in warnings)
        return f"Warning from rules: {rule_ids}."

    return "Validated without violations."


def record_validation_precedent(
    *,
    experience_library: GovernanceExperienceLibrary | None,
    embedding_provider: EmbeddingProvider | None,
    action: str,
    result: Any,
    context: dict[str, Any],
) -> None:
    """Persist a validation outcome into the experience library when configured."""
    if experience_library is None:
        return

    decision = derive_precedent_decision(result)
    top_violation = highest_violation(result)
    embedding: list[float] = []
    if embedding_provider is not None:
        embeddings = embedding_provider.embed([action])
        if embeddings:
            embedding = list(embeddings[0])

    experience_library.record(
        action=action,
        decision=decision,
        triggered_rules=[violation.rule_id for violation in getattr(result, "violations", [])],
        context=dict(context),
        rationale=derive_precedent_rationale(result, decision),
        category=top_violation.category if top_violation is not None else "general",
        severity=top_violation.severity.value if top_violation is not None else "none",
        embedding=embedding,
    )


def _struct_to_dict(value: Any) -> dict[str, Any]:
    """Convert dataclass-like or object-like values into plain dictionaries."""
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(cast(Any, value))
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {}


def _compact_rule_hit(hit: Any) -> dict[str, Any]:
    """Return a compact, serializable semantic-rule hit."""
    data = _struct_to_dict(hit)
    compact = {
        "rule_id": data.get("rule_id", ""),
        "score": round(float(data.get("score", 0.0)), 4),
        "category": data.get("category", ""),
        "severity": data.get("severity", ""),
    }
    tags = data.get("tags")
    if isinstance(tags, list) and tags:
        compact["tags"] = list(tags)
    return compact


def _compact_precedent_hit(hit: Any) -> dict[str, Any]:
    """Return a compact, serializable governance-precedent hit."""
    data = _struct_to_dict(hit)
    compact = {
        "precedent_id": data.get("precedent_id", ""),
        "score": round(float(data.get("score", 0.0)), 4),
        "decision": data.get("decision", ""),
        "category": data.get("category", ""),
        "severity": data.get("severity", ""),
    }
    triggered_rules = data.get("triggered_rules")
    if isinstance(triggered_rules, list):
        compact["triggered_rules"] = list(triggered_rules)
    return compact


def _compact_trajectory_violation(violation: Any) -> dict[str, Any]:
    """Return a compact, serializable trajectory-violation record."""
    data = _struct_to_dict(violation) if not isinstance(violation, dict) else dict(violation)
    return {
        "rule_id": data.get("rule_id", ""),
        "severity": data.get("severity", ""),
        "evidence": data.get("evidence", ""),
    }


def build_runtime_governance_observability(
    *,
    governance_memory_report: Any | None = None,
    tool_risk: dict[str, Any] | None = None,
    trajectory_violations: list[Any] | None = None,
    tool_name: str | None = None,
    session_id: str | None = None,
    checkpoint_kind: str | None = None,
) -> dict[str, Any]:
    """Build a compact, structured runtime-governance observability payload."""
    payload: dict[str, Any] = {}

    if tool_name:
        payload["tool_name"] = tool_name
    if session_id:
        payload["session_id"] = session_id
    if checkpoint_kind:
        payload["checkpoint_kind"] = checkpoint_kind

    if tool_risk is not None:
        payload["tool_risk"] = dict(tool_risk)

    if governance_memory_report is not None:
        payload["retrieved_rules"] = [
            _compact_rule_hit(hit) for hit in getattr(governance_memory_report, "rule_hits", [])
        ]
        payload["retrieved_precedents"] = [
            _compact_precedent_hit(hit)
            for hit in getattr(governance_memory_report, "precedent_hits", [])
        ]
        payload["governance_memory_summary"] = _struct_to_dict(
            getattr(governance_memory_report, "summary", {})
        )

    if trajectory_violations is not None:
        payload["trajectory_violations"] = [
            _compact_trajectory_violation(violation) for violation in trajectory_violations
        ]

    return payload
