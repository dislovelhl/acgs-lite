"""Data sensitivity classification and handling rules for governance artifacts.

Provides a labeling system that tags governance data (rules, audit entries,
decisions, consent records) with sensitivity levels and prescribes handling
constraints — retention ceilings, encryption requirements, access tiers,
and cross-border transfer restrictions.

Example::

    from acgs_lite.constitution.data_classification import (
        DataClassifier, SensitivityLevel, HandlingRequirement,
    )

    classifier = DataClassifier()
    classifier.add_policy(
        label="pii",
        level=SensitivityLevel.CONFIDENTIAL,
        handling=HandlingRequirement(
            encrypt_at_rest=True,
            max_retention_days=365,
            cross_border_allowed=False,
        ),
    )

    result = classifier.classify("user-consent-record-42", labels=["pii"])
    assert result.level == SensitivityLevel.CONFIDENTIAL
    assert result.handling.encrypt_at_rest is True

    report = classifier.compliance_report()
    assert report["total_classified"] >= 1
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field


class SensitivityLevel(enum.IntEnum):
    """Data sensitivity tiers, ordered by restriction severity."""

    PUBLIC = 0
    INTERNAL = 1
    CONFIDENTIAL = 2
    RESTRICTED = 3
    TOP_SECRET = 4


@dataclass(frozen=True)
class HandlingRequirement:
    """Prescriptive handling constraints for a sensitivity label."""

    encrypt_at_rest: bool = False
    encrypt_in_transit: bool = True
    max_retention_days: int | None = None
    cross_border_allowed: bool = True
    require_access_log: bool = False
    allowed_roles: frozenset[str] = field(default_factory=frozenset)
    redact_in_logs: bool = False


@dataclass
class ClassificationPolicy:
    """Maps a label string to sensitivity level and handling rules."""

    label: str
    level: SensitivityLevel
    handling: HandlingRequirement
    description: str = ""


@dataclass
class ClassificationResult:
    """Outcome of classifying a single data artifact."""

    artifact_id: str
    labels: list[str]
    level: SensitivityLevel
    handling: HandlingRequirement
    classified_at: float = field(default_factory=time.time)


@dataclass
class ClassificationAuditEntry:
    """Audit record for a classification action."""

    artifact_id: str
    labels: list[str]
    level: SensitivityLevel
    actor: str
    timestamp: float


class DataClassifier:
    """Classify governance artifacts by sensitivity and prescribe handling.

    Supports multiple labels per artifact with highest-level-wins semantics,
    merged handling requirements (most restrictive wins), queryable audit log,
    bulk classification, and compliance reporting.

    Example::

        dc = DataClassifier()
        dc.add_policy("pii", SensitivityLevel.CONFIDENTIAL,
                       HandlingRequirement(encrypt_at_rest=True, max_retention_days=90))
        dc.add_policy("financial", SensitivityLevel.RESTRICTED,
                       HandlingRequirement(cross_border_allowed=False))

        r = dc.classify("record-1", labels=["pii", "financial"], actor="agent-a")
        assert r.level == SensitivityLevel.RESTRICTED  # highest wins
        assert r.handling.encrypt_at_rest is True       # merged
        assert r.handling.cross_border_allowed is False  # most restrictive
    """

    def __init__(self) -> None:
        self._policies: dict[str, ClassificationPolicy] = {}
        self._classifications: dict[str, ClassificationResult] = {}
        self._audit: list[ClassificationAuditEntry] = []

    def add_policy(
        self,
        label: str,
        level: SensitivityLevel,
        handling: HandlingRequirement | None = None,
        description: str = "",
    ) -> ClassificationPolicy:
        """Register a classification policy for *label*."""
        policy = ClassificationPolicy(
            label=label,
            level=level,
            handling=handling or HandlingRequirement(),
            description=description,
        )
        self._policies[label] = policy
        return policy

    def remove_policy(self, label: str) -> bool:
        """Remove a classification policy. Returns True if it existed."""
        return self._policies.pop(label, None) is not None

    def get_policy(self, label: str) -> ClassificationPolicy | None:
        return self._policies.get(label)

    def list_policies(self) -> list[ClassificationPolicy]:
        return list(self._policies.values())

    def classify(
        self,
        artifact_id: str,
        labels: list[str] | None = None,
        actor: str = "system",
    ) -> ClassificationResult:
        """Classify an artifact. Multiple labels merge with highest-level-wins."""
        applied_labels = labels or []
        matched_policies = [self._policies[lb] for lb in applied_labels if lb in self._policies]

        if not matched_policies:
            level = SensitivityLevel.PUBLIC
            handling = HandlingRequirement()
        else:
            level = max(p.level for p in matched_policies)
            handling = self._merge_handling([p.handling for p in matched_policies])

        result = ClassificationResult(
            artifact_id=artifact_id,
            labels=applied_labels,
            level=level,
            handling=handling,
        )
        self._classifications[artifact_id] = result
        self._audit.append(
            ClassificationAuditEntry(
                artifact_id=artifact_id,
                labels=applied_labels,
                level=level,
                actor=actor,
                timestamp=result.classified_at,
            )
        )
        return result

    def classify_batch(
        self,
        items: list[tuple[str, list[str]]],
        actor: str = "system",
    ) -> list[ClassificationResult]:
        """Classify multiple artifacts in one call."""
        return [self.classify(aid, labels, actor) for aid, labels in items]

    def get_classification(self, artifact_id: str) -> ClassificationResult | None:
        return self._classifications.get(artifact_id)

    def query_by_level(self, min_level: SensitivityLevel) -> list[ClassificationResult]:
        """Return artifacts at or above *min_level*."""
        return [r for r in self._classifications.values() if r.level >= min_level]

    def query_by_label(self, label: str) -> list[ClassificationResult]:
        return [r for r in self._classifications.values() if label in r.labels]

    def reclassify(
        self,
        artifact_id: str,
        labels: list[str],
        actor: str = "system",
    ) -> ClassificationResult | None:
        """Re-classify an already-classified artifact with new labels."""
        if artifact_id not in self._classifications:
            return None
        return self.classify(artifact_id, labels, actor)

    def declassify(self, artifact_id: str, actor: str = "system") -> bool:
        """Remove classification from an artifact."""
        removed = self._classifications.pop(artifact_id, None)
        if removed is not None:
            self._audit.append(
                ClassificationAuditEntry(
                    artifact_id=artifact_id,
                    labels=[],
                    level=SensitivityLevel.PUBLIC,
                    actor=actor,
                    timestamp=time.time(),
                )
            )
            return True
        return False

    def audit_log(self, artifact_id: str | None = None) -> list[ClassificationAuditEntry]:
        if artifact_id is None:
            return list(self._audit)
        return [e for e in self._audit if e.artifact_id == artifact_id]

    def compliance_report(self) -> dict[str, object]:
        """Summary statistics for compliance dashboards."""
        by_level: dict[str, int] = {}
        for r in self._classifications.values():
            key = r.level.name
            by_level[key] = by_level.get(key, 0) + 1

        encrypted_count = sum(
            1 for r in self._classifications.values() if r.handling.encrypt_at_rest
        )
        restricted_border = sum(
            1 for r in self._classifications.values() if not r.handling.cross_border_allowed
        )

        return {
            "total_classified": len(self._classifications),
            "by_level": by_level,
            "encrypted_at_rest": encrypted_count,
            "cross_border_restricted": restricted_border,
            "total_audit_entries": len(self._audit),
        }

    @staticmethod
    def _merge_handling(items: list[HandlingRequirement]) -> HandlingRequirement:
        """Merge multiple handling requirements — most restrictive wins."""
        if not items:
            return HandlingRequirement()
        encrypt_rest = any(h.encrypt_at_rest for h in items)
        encrypt_transit = any(h.encrypt_in_transit for h in items)
        retentions = [h.max_retention_days for h in items if h.max_retention_days is not None]
        max_ret = min(retentions) if retentions else None
        cross_border = all(h.cross_border_allowed for h in items)
        access_log = any(h.require_access_log for h in items)
        roles: frozenset[str] = frozenset()
        role_sets = [h.allowed_roles for h in items if h.allowed_roles]
        if role_sets:
            roles = role_sets[0]
            for rs in role_sets[1:]:
                roles = roles & rs
        redact = any(h.redact_in_logs for h in items)

        return HandlingRequirement(
            encrypt_at_rest=encrypt_rest,
            encrypt_in_transit=encrypt_transit,
            max_retention_days=max_ret,
            cross_border_allowed=cross_border,
            require_access_log=access_log,
            allowed_roles=roles,
            redact_in_logs=redact,
        )
