"""Automated compliance evidence collection for governance audits.

Collects structured evidence from the governance engine, audit log, and
constitution to support compliance assessments across SOC2, ISO 27001,
and GDPR frameworks.  Each framework collector examines runtime artifacts
and produces immutable evidence records with status assessments.

Constitutional Hash: 608508a9bd224290

Usage::

    from acgs_lite.audit import AuditLog
    from acgs_lite.compliance.evidence import EvidenceCollector
    from acgs_lite.constitution import Constitution
    from acgs_lite.engine import GovernanceEngine

    constitution = Constitution.default()
    audit_log = AuditLog()
    engine = GovernanceEngine(constitution, audit_log=audit_log)

    collector = EvidenceCollector(engine, audit_log, constitution)
    report = collector.generate_report()
    print(report["summary"]["overall_score"])
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution, Severity
from acgs_lite.engine import GovernanceEngine

# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

_COMPLIANT = "compliant"
_NON_COMPLIANT = "non_compliant"
_PARTIAL = "partial"
_NOT_ASSESSED = "not_assessed"

_VALID_STATUSES = frozenset({_COMPLIANT, _NON_COMPLIANT, _PARTIAL, _NOT_ASSESSED})

_VALID_EVIDENCE_TYPES = frozenset(
    {"audit_trail", "validation_summary", "configuration", "attestation"}
)


@dataclass(frozen=True)
class EvidenceRecord:
    """Immutable record of a single piece of compliance evidence."""

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    framework: str = ""
    control_id: str = ""
    title: str = ""
    evidence_type: str = "attestation"
    collected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    data: dict[str, Any] = field(default_factory=dict)
    status: str = _NOT_ASSESSED

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return asdict(self)


@runtime_checkable
class ComplianceFramework(Protocol):
    """Protocol for pluggable compliance framework collectors."""

    @property
    def framework_id(self) -> str: ...

    def collect_evidence(
        self,
        engine: GovernanceEngine,
        audit_log: AuditLog,
        constitution: Constitution,
    ) -> list[EvidenceRecord]: ...


# ---------------------------------------------------------------------------
# SOC 2 collector
# ---------------------------------------------------------------------------


class SOC2EvidenceCollector:
    """Collect evidence for SOC 2 Trust Service Criteria."""

    @property
    def framework_id(self) -> str:
        return "SOC2"

    def collect_evidence(
        self,
        engine: GovernanceEngine,
        audit_log: AuditLog,
        constitution: Constitution,
    ) -> list[EvidenceRecord]:
        records: list[EvidenceRecord] = []
        records.append(self._cc6_1(engine))
        records.append(self._cc6_6(audit_log))
        records.append(self._cc7_2(engine))
        records.append(self._cc8_1(constitution))
        return records

    # -- CC6.1: Logical access controls --

    def _cc6_1(self, engine: GovernanceEngine) -> EvidenceRecord:
        stats = engine.stats
        total = stats.get("total_validations", 0)
        rules = stats.get("rules_count", 0)
        status = _COMPLIANT if rules > 0 and total >= 0 else _NON_COMPLIANT
        return EvidenceRecord(
            framework="SOC2",
            control_id="CC6.1",
            title="Logical access controls",
            evidence_type="validation_summary",
            data={
                "total_validations": total,
                "rules_count": rules,
                "compliance_rate": stats.get("compliance_rate", 0.0),
                "constitutional_hash": stats.get(
                    "constitutional_hash", ""
                ),
            },
            status=status,
        )

    # -- CC6.6: Security event monitoring --

    def _cc6_6(self, audit_log: AuditLog) -> EvidenceRecord:
        entries = audit_log.entries
        chain_valid = audit_log.verify_chain()
        entry_count = len(entries)
        if entry_count > 0 and chain_valid:
            status = _COMPLIANT
        elif entry_count > 0:
            status = _PARTIAL
        else:
            status = _NOT_ASSESSED
        return EvidenceRecord(
            framework="SOC2",
            control_id="CC6.6",
            title="Security event monitoring",
            evidence_type="audit_trail",
            data={
                "audit_entry_count": entry_count,
                "chain_integrity": chain_valid,
                "compliance_rate": audit_log.compliance_rate,
            },
            status=status,
        )

    # -- CC7.2: System monitoring --

    def _cc7_2(self, engine: GovernanceEngine) -> EvidenceRecord:
        stats = engine.stats
        total = stats.get("total_validations", 0)
        avg_latency = stats.get("avg_latency_ms", 0.0)
        status = _COMPLIANT if total > 0 else _NOT_ASSESSED
        return EvidenceRecord(
            framework="SOC2",
            control_id="CC7.2",
            title="System monitoring",
            evidence_type="validation_summary",
            data={
                "total_validations": total,
                "avg_latency_ms": avg_latency,
                "monitoring_active": total > 0,
            },
            status=status,
        )

    # -- CC8.1: Change management --

    def _cc8_1(self, constitution: Constitution) -> EvidenceRecord:
        c_hash = constitution.hash
        version = constitution.version
        has_hash = bool(c_hash)
        has_version = bool(version)
        if has_hash and has_version:
            status = _COMPLIANT
        elif has_hash or has_version:
            status = _PARTIAL
        else:
            status = _NON_COMPLIANT
        return EvidenceRecord(
            framework="SOC2",
            control_id="CC8.1",
            title="Change management",
            evidence_type="configuration",
            data={
                "constitutional_hash": c_hash,
                "version": version,
                "name": constitution.name,
                "rule_count": len(constitution.rules),
            },
            status=status,
        )


# ---------------------------------------------------------------------------
# ISO 27001 collector
# ---------------------------------------------------------------------------


class ISO27001EvidenceCollector:
    """Collect evidence for ISO 27001 Annex A controls."""

    @property
    def framework_id(self) -> str:
        return "ISO27001"

    def collect_evidence(
        self,
        engine: GovernanceEngine,
        audit_log: AuditLog,
        constitution: Constitution,
    ) -> list[EvidenceRecord]:
        records: list[EvidenceRecord] = []
        records.append(self._a8_2(constitution))
        records.append(self._a12_4(audit_log))
        records.append(self._a14_2(engine))
        records.append(self._a18_1(engine, audit_log, constitution))
        return records

    # -- A.8.2: Information classification --

    def _a8_2(self, constitution: Constitution) -> EvidenceRecord:
        rules = constitution.rules
        severity_dist: dict[str, int] = {}
        for rule in rules:
            sev_val = (
                rule.severity.value
                if isinstance(rule.severity, Severity)
                else str(rule.severity)
            )
            severity_dist[sev_val] = severity_dist.get(sev_val, 0) + 1

        has_critical = severity_dist.get("critical", 0) > 0
        has_high = severity_dist.get("high", 0) > 0
        total_rules = len(rules)

        if total_rules > 0 and (has_critical or has_high):
            status = _COMPLIANT
        elif total_rules > 0:
            status = _PARTIAL
        else:
            status = _NON_COMPLIANT
        return EvidenceRecord(
            framework="ISO27001",
            control_id="A.8.2",
            title="Information classification",
            evidence_type="configuration",
            data={
                "severity_distribution": severity_dist,
                "total_rules": total_rules,
                "has_critical_rules": has_critical,
                "has_high_rules": has_high,
            },
            status=status,
        )

    # -- A.12.4: Logging and monitoring --

    def _a12_4(self, audit_log: AuditLog) -> EvidenceRecord:
        chain_valid = audit_log.verify_chain()
        entry_count = len(audit_log.entries)
        if entry_count > 0 and chain_valid:
            status = _COMPLIANT
        elif entry_count > 0:
            status = _PARTIAL
        else:
            status = _NOT_ASSESSED
        return EvidenceRecord(
            framework="ISO27001",
            control_id="A.12.4",
            title="Logging and monitoring",
            evidence_type="audit_trail",
            data={
                "audit_entry_count": entry_count,
                "chain_integrity": chain_valid,
                "tamper_evident": chain_valid,
            },
            status=status,
        )

    # -- A.14.2: Security in development --

    def _a14_2(self, engine: GovernanceEngine) -> EvidenceRecord:
        stats = engine.stats
        rules_count = stats.get("rules_count", 0)
        total = stats.get("total_validations", 0)
        compliance_rate = stats.get("compliance_rate", 0.0)
        if rules_count > 0 and compliance_rate >= 0.8:
            status = _COMPLIANT
        elif rules_count > 0:
            status = _PARTIAL
        else:
            status = _NON_COMPLIANT
        return EvidenceRecord(
            framework="ISO27001",
            control_id="A.14.2",
            title="Security in development",
            evidence_type="validation_summary",
            data={
                "rules_count": rules_count,
                "total_validations": total,
                "compliance_rate": compliance_rate,
                "validation_active": total > 0,
            },
            status=status,
        )

    # -- A.18.1: Compliance with requirements --

    def _a18_1(
        self,
        engine: GovernanceEngine,
        audit_log: AuditLog,
        constitution: Constitution,
    ) -> EvidenceRecord:
        stats = engine.stats
        compliance_rate = stats.get("compliance_rate", 0.0)
        chain_valid = audit_log.verify_chain()
        has_rules = len(constitution.rules) > 0
        has_hash = bool(constitution.hash)

        checks_passed = sum([
            compliance_rate >= 0.8,
            chain_valid,
            has_rules,
            has_hash,
        ])
        if checks_passed == 4:
            status = _COMPLIANT
        elif checks_passed >= 2:
            status = _PARTIAL
        else:
            status = _NON_COMPLIANT
        return EvidenceRecord(
            framework="ISO27001",
            control_id="A.18.1",
            title="Compliance with requirements",
            evidence_type="attestation",
            data={
                "compliance_rate": compliance_rate,
                "chain_integrity": chain_valid,
                "has_rules": has_rules,
                "has_hash": has_hash,
                "checks_passed": checks_passed,
                "checks_total": 4,
            },
            status=status,
        )


# ---------------------------------------------------------------------------
# GDPR collector
# ---------------------------------------------------------------------------


class GDPREvidenceCollector:
    """Collect evidence for GDPR articles relevant to AI governance."""

    @property
    def framework_id(self) -> str:
        return "GDPR"

    def collect_evidence(
        self,
        engine: GovernanceEngine,
        audit_log: AuditLog,
        constitution: Constitution,
    ) -> list[EvidenceRecord]:
        records: list[EvidenceRecord] = []
        records.append(self._art5(constitution))
        records.append(self._art25(constitution, engine))
        records.append(self._art30(audit_log))
        return records

    # -- Art.5: Data processing principles --

    def _art5(self, constitution: Constitution) -> EvidenceRecord:
        rules = constitution.rules
        data_categories = {"privacy", "data-protection", "compliance"}
        data_rules = [
            r for r in rules if r.category in data_categories
        ]
        data_rule_count = len(data_rules)
        total_rules = len(rules)

        if data_rule_count > 0:
            status = _COMPLIANT
        elif total_rules > 0:
            status = _PARTIAL
        else:
            status = _NON_COMPLIANT
        return EvidenceRecord(
            framework="GDPR",
            control_id="Art.5",
            title="Data processing principles",
            evidence_type="configuration",
            data={
                "data_handling_rules": data_rule_count,
                "total_rules": total_rules,
                "data_rule_ids": [r.id for r in data_rules],
                "coverage_ratio": (
                    data_rule_count / total_rules
                    if total_rules > 0
                    else 0.0
                ),
            },
            status=status,
        )

    # -- Art.25: Data protection by design --

    def _art25(
        self,
        constitution: Constitution,
        engine: GovernanceEngine,
    ) -> EvidenceRecord:
        has_hash = bool(constitution.hash)
        has_rules = len(constitution.rules) > 0
        stats = engine.stats
        has_validation = stats.get("rules_count", 0) > 0

        checks_passed = sum([has_hash, has_rules, has_validation])
        if checks_passed == 3:
            status = _COMPLIANT
        elif checks_passed >= 1:
            status = _PARTIAL
        else:
            status = _NON_COMPLIANT
        return EvidenceRecord(
            framework="GDPR",
            control_id="Art.25",
            title="Data protection by design",
            evidence_type="attestation",
            data={
                "constitutional_hash": constitution.hash,
                "has_rules": has_rules,
                "has_validation_engine": has_validation,
                "design_controls_present": checks_passed,
                "design_controls_total": 3,
            },
            status=status,
        )

    # -- Art.30: Records of processing --

    def _art30(self, audit_log: AuditLog) -> EvidenceRecord:
        entries = audit_log.entries
        entry_count = len(entries)
        chain_valid = audit_log.verify_chain()

        if entry_count > 0 and chain_valid:
            status = _COMPLIANT
        elif entry_count > 0:
            status = _PARTIAL
        else:
            status = _NOT_ASSESSED
        return EvidenceRecord(
            framework="GDPR",
            control_id="Art.30",
            title="Records of processing",
            evidence_type="audit_trail",
            data={
                "audit_entry_count": entry_count,
                "chain_integrity": chain_valid,
                "compliance_rate": audit_log.compliance_rate,
            },
            status=status,
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

_STATUS_SCORES: dict[str, float] = {
    _COMPLIANT: 1.0,
    _PARTIAL: 0.5,
    _NON_COMPLIANT: 0.0,
    _NOT_ASSESSED: 0.0,
}


class EvidenceCollector:
    """Orchestrates evidence collection across compliance frameworks.

    If *frameworks* is ``None`` the three built-in collectors (SOC2,
    ISO 27001, GDPR) are registered automatically.
    """

    def __init__(
        self,
        engine: GovernanceEngine,
        audit_log: AuditLog,
        constitution: Constitution,
        frameworks: list[ComplianceFramework] | None = None,
    ) -> None:
        self._engine = engine
        self._audit_log = audit_log
        self._constitution = constitution
        self._frameworks: dict[str, ComplianceFramework] = {}

        if frameworks is None:
            for fw in (
                SOC2EvidenceCollector(),
                ISO27001EvidenceCollector(),
                GDPREvidenceCollector(),
            ):
                self._frameworks[fw.framework_id] = fw
        else:
            for fw in frameworks:
                self._frameworks[fw.framework_id] = fw

    # -- public API --

    def register_framework(
        self,
        collector: ComplianceFramework,
    ) -> None:
        """Register an additional framework collector."""
        self._frameworks[collector.framework_id] = collector

    def collect_all(self) -> list[EvidenceRecord]:
        """Run all registered framework collectors."""
        records: list[EvidenceRecord] = []
        for fw in self._frameworks.values():
            records.extend(
                fw.collect_evidence(
                    self._engine, self._audit_log, self._constitution
                )
            )
        return records

    def collect_framework(
        self,
        framework_id: str,
    ) -> list[EvidenceRecord]:
        """Run a single framework collector by ID.

        Raises:
            KeyError: If *framework_id* is not registered.
        """
        fw = self._frameworks.get(framework_id)
        if fw is None:
            available = ", ".join(sorted(self._frameworks))
            raise KeyError(
                f"Unknown framework {framework_id!r}. "
                f"Available: {available}"
            )
        return fw.collect_evidence(
            self._engine, self._audit_log, self._constitution
        )

    def compliance_score(
        self,
        framework_id: str | None = None,
    ) -> float:
        """Compute a 0.0--1.0 compliance score.

        If *framework_id* is given, scores only that framework.
        Otherwise scores across all frameworks.
        """
        if framework_id is not None:
            records = self.collect_framework(framework_id)
        else:
            records = self.collect_all()
        if not records:
            return 0.0
        total = sum(
            _STATUS_SCORES.get(r.status, 0.0) for r in records
        )
        return total / len(records)

    def generate_report(self) -> dict[str, Any]:
        """Generate a full compliance report with per-framework detail."""
        all_records = self.collect_all()
        by_framework: dict[str, list[dict[str, Any]]] = {}
        for rec in all_records:
            by_framework.setdefault(rec.framework, []).append(
                rec.to_dict()
            )

        framework_scores: dict[str, float] = {}
        for fw_id in self._frameworks:
            framework_scores[fw_id] = self.compliance_score(fw_id)

        overall = (
            sum(framework_scores.values()) / len(framework_scores)
            if framework_scores
            else 0.0
        )

        status_counts: dict[str, int] = {}
        for rec in all_records:
            status_counts[rec.status] = (
                status_counts.get(rec.status, 0) + 1
            )

        return {
            "summary": {
                "overall_score": overall,
                "framework_scores": framework_scores,
                "total_evidence_records": len(all_records),
                "status_counts": status_counts,
                "frameworks_assessed": list(self._frameworks.keys()),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            },
            "frameworks": by_framework,
        }

    def export_json(self, path: str | None = None) -> str:
        """Export the full report as JSON.

        If *path* is given the JSON is also written to that file.
        Returns the JSON string.
        """
        report = self.generate_report()
        json_str = json.dumps(report, indent=2, default=str)
        if path is not None:
            from pathlib import Path as _P

            p = _P(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json_str, encoding="utf-8")
        return json_str
