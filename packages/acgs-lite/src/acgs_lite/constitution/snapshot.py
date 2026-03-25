"""exp116: Governance state snapshot for compliance archival.

Captures the complete governance state (constitution rules, metrics,
session summaries, routing config) as a single immutable record for
compliance archival, audit trails, and point-in-time governance review.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConstitutionSnapshot:
    """exp116: Immutable point-in-time capture of governance state.

    Captures everything a compliance reviewer needs to understand the
    governance posture at a specific moment: the constitution rules,
    their configuration, active metrics, and routing setup.

    Usage::

        from acgs_lite.constitution import Constitution, GovernanceMetrics
        from acgs_lite.constitution.snapshot import capture_snapshot

        constitution = Constitution.default()
        metrics = GovernanceMetrics()
        # ... after some governance activity ...
        snapshot = capture_snapshot(
            constitution=constitution,
            metrics=metrics,
            reason="Pre-deployment audit Q1 2026",
        )
        archive = snapshot.to_dict()  # serialize for storage
    """

    constitution_name: str
    constitution_version: str
    constitution_hash: str
    rule_count: int
    active_rule_count: int
    rules_summary: tuple[dict[str, Any], ...]
    governance_summary: dict[str, Any]
    integrity_report: dict[str, Any]
    metrics_snapshot: dict[str, Any]
    routing_summary: dict[str, Any]
    timestamp_ns: int
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage or API response."""
        return {
            "constitution_name": self.constitution_name,
            "constitution_version": self.constitution_version,
            "constitution_hash": self.constitution_hash,
            "rule_count": self.rule_count,
            "active_rule_count": self.active_rule_count,
            "rules_summary": list(self.rules_summary),
            "governance_summary": self.governance_summary,
            "integrity_report": self.integrity_report,
            "metrics_snapshot": self.metrics_snapshot,
            "routing_summary": self.routing_summary,
            "timestamp_ns": self.timestamp_ns,
            "reason": self.reason,
            "metadata": self.metadata,
        }


def capture_snapshot(
    constitution: Any,
    *,
    metrics: Any | None = None,
    router: Any | None = None,
    reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> ConstitutionSnapshot:
    """Capture a point-in-time governance snapshot.

    Args:
        constitution: The Constitution to snapshot.
        metrics: Optional GovernanceMetrics for current statistics.
        router: Optional GovernanceRouter for routing configuration.
        reason: Reason for the snapshot (e.g., "Pre-deployment audit").
        metadata: Additional metadata to include.

    Returns:
        Immutable ConstitutionSnapshot.
    """
    rules_summary = tuple(
        {
            "id": r.id,
            "severity": r.severity.value,
            "category": r.category,
            "enabled": r.enabled,
            "workflow_action": r.workflow_action,
        }
        for r in constitution.rules
    )

    governance_summary = constitution.governance_summary()
    integrity_report = constitution.validate_integrity()
    metrics_snapshot = metrics.snapshot() if metrics else {}
    routing_summary = router.summary() if router else {}

    return ConstitutionSnapshot(
        constitution_name=constitution.name,
        constitution_version=constitution.version,
        constitution_hash=constitution.hash,
        rule_count=len(constitution.rules),
        active_rule_count=len(constitution.active_rules()),
        rules_summary=rules_summary,
        governance_summary=governance_summary,
        integrity_report=integrity_report,
        metrics_snapshot=metrics_snapshot,
        routing_summary=routing_summary,
        timestamp_ns=time.monotonic_ns(),
        reason=reason,
        metadata=metadata or {},
    )
