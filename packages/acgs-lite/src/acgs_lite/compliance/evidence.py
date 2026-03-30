"""Live runtime evidence collection for compliance assessments.

Provides helpers to collect and attach runtime evidence (log excerpts,
metric snapshots, configuration proofs) to compliance checklist items,
separate from the static assessment flow.

Constitutional Hash: 608508a9bd224290

Usage::

    from acgs_lite.compliance.evidence import EvidenceCollector, EvidenceRecord

    collector = EvidenceCollector(system_id="my-system")
    collector.add("GDPR Art.5(2)", "audit_log_hash_chain",
                  data={"chain_length": 1204, "integrity": "verified"})
    collector.add("NIST GOVERN 1.1", "constitution_loaded",
                  data={"rules": 42, "hash": "abc123"})

    records = collector.records
    summary = collector.summary()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class EvidenceRecord:
    """A single piece of runtime evidence supporting compliance.

    Attributes:
        ref: Regulatory reference the evidence supports.
        evidence_type: Category of evidence (e.g. "audit_log_hash_chain").
        data: Arbitrary evidence payload (metrics, hashes, config snapshots).
        collected_at: ISO timestamp of collection.
        system_id: System that produced the evidence.
    """

    ref: str
    evidence_type: str
    data: dict[str, Any]
    collected_at: str
    system_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "evidence_type": self.evidence_type,
            "data": self.data,
            "collected_at": self.collected_at,
            "system_id": self.system_id,
        }


@dataclass
class EvidenceCollector:
    """Collects runtime evidence records for a system.

    Args:
        system_id: Identifier of the system being evidenced.
    """

    system_id: str
    _records: list[EvidenceRecord] = field(default_factory=list, repr=False)

    def add(
        self,
        ref: str,
        evidence_type: str,
        data: dict[str, Any] | None = None,
    ) -> EvidenceRecord:
        """Collect a new evidence record.

        Args:
            ref: Regulatory reference (e.g. "GDPR Art.5(2)").
            evidence_type: Type of evidence (e.g. "audit_log_integrity").
            data: Optional evidence payload.

        Returns:
            The created EvidenceRecord.
        """
        record = EvidenceRecord(
            ref=ref,
            evidence_type=evidence_type,
            data=data or {},
            collected_at=datetime.now(UTC).isoformat(),
            system_id=self.system_id,
        )
        self._records.append(record)
        return record

    @property
    def records(self) -> list[EvidenceRecord]:
        """Return all collected evidence records."""
        return list(self._records)

    def records_for_ref(self, ref: str) -> list[EvidenceRecord]:
        """Return evidence records matching a regulatory reference."""
        return [r for r in self._records if r.ref == ref]

    def summary(self) -> dict[str, Any]:
        """Return a summary of collected evidence."""
        refs = {r.ref for r in self._records}
        types = {r.evidence_type for r in self._records}
        return {
            "system_id": self.system_id,
            "total_records": len(self._records),
            "unique_refs": sorted(refs),
            "evidence_types": sorted(types),
            "collected_at": datetime.now(UTC).isoformat(),
        }

    def clear(self) -> None:
        """Discard all collected records."""
        self._records.clear()
