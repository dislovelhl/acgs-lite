"""Constitution filtering helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .rule import Rule, Severity

if TYPE_CHECKING:
    from .constitution import Constitution


_SEV_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
}


def filter(
    constitution: Constitution,
    *,
    severity: str | Severity | None = None,
    min_severity: str | Severity | None = None,
    category: str | None = None,
    workflow_action: str | None = None,
    tag: str | None = None,
    enabled_only: bool = True,
) -> Constitution:
    """Return a new constitution containing only matching rules."""
    if severity is not None and isinstance(severity, str):
        severity = Severity(severity)
    if min_severity is not None and isinstance(min_severity, str):
        min_severity = Severity(min_severity)

    min_rank = _SEV_RANK.get(min_severity, 0) if min_severity else 0

    filtered: list[Rule] = []
    for rule in constitution.rules:
        if enabled_only and not rule.enabled:
            continue
        if severity is not None and rule.severity != severity:
            continue
        if min_severity is not None and _SEV_RANK.get(rule.severity, 0) < min_rank:
            continue
        if category is not None and rule.category != category:
            continue
        if workflow_action is not None and rule.workflow_action != workflow_action:
            continue
        if tag is not None and tag not in rule.tags:
            continue
        filtered.append(rule)

    if not filtered:
        raise ValueError(
            "Filter produced an empty constitution — at least one rule must match the criteria"
        )

    return constitution.__class__(
        name=constitution.name,
        version=constitution.version,
        description=constitution.description,
        rules=filtered,
        metadata={**constitution.metadata, "filtered": True},
    )
