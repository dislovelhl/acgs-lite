"""Data and audit retention policies with auto-purge for governance artifacts.

Manages retention lifecycles — configurable per-category retention windows,
automatic expiry detection, legal-hold overrides that freeze purging, bulk
purge execution, and retention compliance reporting.

Example::

    from acgs_lite.constitution.retention import (
        RetentionManager, RetentionPolicy, RetentionCategory,
    )

    mgr = RetentionManager()
    mgr.add_policy(RetentionPolicy(
        category=RetentionCategory.AUDIT_LOG,
        max_retention_days=730,
        description="Keep audit logs for 2 years",
    ))
    mgr.ingest("audit-001", category=RetentionCategory.AUDIT_LOG)
    expired = mgr.scan_expired()
    purged = mgr.purge_expired()
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field


class RetentionCategory(str, enum.Enum):
    """Categories of governance data subject to retention rules."""

    AUDIT_LOG = "audit_log"
    DECISION_RECORD = "decision_record"
    CONSENT_DATA = "consent_data"
    POLICY_SNAPSHOT = "policy_snapshot"
    INCIDENT_REPORT = "incident_report"
    CLASSIFICATION_RECORD = "classification_record"
    GENERAL = "general"


class RetentionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    PURGED = "purged"
    LEGAL_HOLD = "legal_hold"


@dataclass
class RetentionPolicy:
    """Retention rules for a data category."""

    category: RetentionCategory
    max_retention_days: int
    description: str = ""
    auto_purge: bool = True
    archive_before_purge: bool = False


@dataclass
class RetainedArtifact:
    """A tracked artifact under retention management."""

    artifact_id: str
    category: RetentionCategory
    ingested_at: float = field(default_factory=time.time)
    status: RetentionStatus = RetentionStatus.ACTIVE
    legal_hold: bool = False
    hold_reason: str = ""
    purged_at: float | None = None
    archived: bool = False


@dataclass
class PurgeRecord:
    """Audit entry for a purge action."""

    artifact_id: str
    category: RetentionCategory
    purged_at: float
    reason: str
    archived: bool


class RetentionManager:
    """Manage retention lifecycles for governance artifacts.

    Supports per-category retention policies, legal holds that freeze
    purging, bulk expiry scanning, purge execution with optional archival,
    and compliance reporting for retention audits.

    Example::

        mgr = RetentionManager()
        mgr.add_policy(RetentionPolicy(
            category=RetentionCategory.AUDIT_LOG,
            max_retention_days=365,
        ))
        mgr.ingest("log-1", RetentionCategory.AUDIT_LOG)

        # Simulate passage of time for expiry scanning
        expired = mgr.scan_expired()
    """

    def __init__(self) -> None:
        self._policies: dict[RetentionCategory, RetentionPolicy] = {}
        self._artifacts: dict[str, RetainedArtifact] = {}
        self._purge_log: list[PurgeRecord] = []

    def add_policy(self, policy: RetentionPolicy) -> None:
        self._policies[policy.category] = policy

    def remove_policy(self, category: RetentionCategory) -> bool:
        return self._policies.pop(category, None) is not None

    def get_policy(self, category: RetentionCategory) -> RetentionPolicy | None:
        return self._policies.get(category)

    def list_policies(self) -> list[RetentionPolicy]:
        return list(self._policies.values())

    def ingest(
        self,
        artifact_id: str,
        category: RetentionCategory,
        timestamp: float | None = None,
    ) -> RetainedArtifact:
        """Register an artifact for retention tracking."""
        artifact = RetainedArtifact(
            artifact_id=artifact_id,
            category=category,
            ingested_at=timestamp if timestamp is not None else time.time(),
        )
        self._artifacts[artifact_id] = artifact
        return artifact

    def ingest_batch(
        self,
        items: list[tuple[str, RetentionCategory]],
        timestamp: float | None = None,
    ) -> list[RetainedArtifact]:
        return [self.ingest(aid, cat, timestamp) for aid, cat in items]

    def get_artifact(self, artifact_id: str) -> RetainedArtifact | None:
        return self._artifacts.get(artifact_id)

    def place_legal_hold(self, artifact_id: str, reason: str = "") -> bool:
        """Freeze an artifact — prevents purging regardless of expiry."""
        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            return False
        artifact.legal_hold = True
        artifact.hold_reason = reason
        artifact.status = RetentionStatus.LEGAL_HOLD
        return True

    def release_legal_hold(self, artifact_id: str) -> bool:
        artifact = self._artifacts.get(artifact_id)
        if artifact is None or not artifact.legal_hold:
            return False
        artifact.legal_hold = False
        artifact.hold_reason = ""
        artifact.status = RetentionStatus.ACTIVE
        return True

    def scan_expired(self, now: float | None = None) -> list[RetainedArtifact]:
        """Return artifacts past their retention window (excluding legal holds)."""
        current = now if now is not None else time.time()
        expired: list[RetainedArtifact] = []
        for artifact in self._artifacts.values():
            if artifact.status in (RetentionStatus.PURGED, RetentionStatus.LEGAL_HOLD):
                continue
            policy = self._policies.get(artifact.category)
            if policy is None:
                continue
            cutoff = artifact.ingested_at + (policy.max_retention_days * 86400)
            if current >= cutoff:
                artifact.status = RetentionStatus.EXPIRED
                expired.append(artifact)
        return expired

    def purge_expired(self, now: float | None = None) -> list[PurgeRecord]:
        """Purge all expired artifacts (respecting legal holds and auto_purge flags)."""
        expired = self.scan_expired(now)
        current = now if now is not None else time.time()
        records: list[PurgeRecord] = []
        for artifact in expired:
            if artifact.legal_hold:
                continue
            policy = self._policies.get(artifact.category)
            if policy and not policy.auto_purge:
                continue
            archived = False
            if policy and policy.archive_before_purge:
                archived = True
                artifact.archived = True
            artifact.status = RetentionStatus.PURGED
            artifact.purged_at = current
            record = PurgeRecord(
                artifact_id=artifact.artifact_id,
                category=artifact.category,
                purged_at=current,
                reason="retention_expired",
                archived=archived,
            )
            self._purge_log.append(record)
            records.append(record)
        return records

    def purge_single(self, artifact_id: str, reason: str = "manual") -> PurgeRecord | None:
        """Manually purge a specific artifact (legal holds still block)."""
        artifact = self._artifacts.get(artifact_id)
        if artifact is None or artifact.legal_hold:
            return None
        if artifact.status == RetentionStatus.PURGED:
            return None
        artifact.status = RetentionStatus.PURGED
        artifact.purged_at = time.time()
        record = PurgeRecord(
            artifact_id=artifact.artifact_id,
            category=artifact.category,
            purged_at=artifact.purged_at,
            reason=reason,
            archived=False,
        )
        self._purge_log.append(record)
        return record

    def purge_log(self) -> list[PurgeRecord]:
        return list(self._purge_log)

    def query_by_category(self, category: RetentionCategory) -> list[RetainedArtifact]:
        return [a for a in self._artifacts.values() if a.category == category]

    def query_by_status(self, status: RetentionStatus) -> list[RetainedArtifact]:
        return [a for a in self._artifacts.values() if a.status == status]

    def compliance_report(self, now: float | None = None) -> dict[str, object]:
        """Retention compliance summary for audits."""
        current = now if now is not None else time.time()
        total = len(self._artifacts)
        by_status: dict[str, int] = {}
        overdue: list[str] = []
        for artifact in self._artifacts.values():
            by_status[artifact.status.value] = by_status.get(artifact.status.value, 0) + 1
            if artifact.status == RetentionStatus.ACTIVE:
                policy = self._policies.get(artifact.category)
                if policy:
                    cutoff = artifact.ingested_at + (policy.max_retention_days * 86400)
                    if current >= cutoff:
                        overdue.append(artifact.artifact_id)

        holds = sum(1 for a in self._artifacts.values() if a.legal_hold)
        categories_covered = set(self._policies.keys())
        categories_used = {a.category for a in self._artifacts.values()}
        uncovered = categories_used - categories_covered

        return {
            "total_tracked": total,
            "by_status": by_status,
            "overdue_count": len(overdue),
            "overdue_artifact_ids": overdue,
            "legal_holds": holds,
            "total_purged": len(self._purge_log),
            "uncovered_categories": [c.value for c in uncovered],
        }
