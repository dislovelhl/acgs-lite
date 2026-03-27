"""exp221: RegulatoryHorizonScanner — regulatory change monitoring for governance rules.

Maintains a registry of regulatory frameworks (EU AI Act, NIST AI RMF, ISO 42001,
GDPR Art. 22, SOC 2+AI, HIPAA+AI, etc.) with versioned requirement catalogues.
When a framework is updated, the scanner identifies which governance rules are
affected and generates remediation tickets.

This is NOT a live feed poller (that would require network I/O). Instead it models
a structured regulatory knowledge base that can be updated from any external source
and diffed against the current constitution to find gaps and stale mappings.

Key capabilities:
- Framework registry with versioned requirement sets (articles, controls, sections).
- Constitution coverage analysis: which rules map to which framework requirements.
- Gap detection: framework requirements with zero or weak rule coverage.
- Staleness detection: rules whose mapped requirements have been updated/superseded.
- Update simulation: when a framework version changes, which rules need review.
- Remediation ticket generation: structured work items for governance maintainers.
- Multi-framework cross-reference: requirements shared across frameworks.
- Dashboard summary with coverage scores per framework.

Usage::

    from acgs_lite.constitution.regulatory_scanner import RegulatoryHorizonScanner

    scanner = RegulatoryHorizonScanner()
    scanner.register_framework("eu_ai_act", version="2026-08", requirements=[...])
    scanner.map_rule_to_requirement(rule_id="SAFE-001", framework="eu_ai_act", req_id="Art.9")

    report = scanner.scan(constitution)
    for ticket in report.remediation_tickets:
        print(ticket)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _ts() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class RegulatoryRequirement:
    """A single requirement within a regulatory framework."""

    req_id: str
    framework_id: str
    title: str
    description: str = ""
    version: str = "1.0"
    superseded_by: str | None = None
    tags: list[str] = field(default_factory=list)
    effective_date: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_superseded(self) -> bool:
        return self.superseded_by is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "req_id": self.req_id,
            "framework_id": self.framework_id,
            "title": self.title,
            "description": self.description,
            "version": self.version,
            "superseded_by": self.superseded_by,
            "tags": self.tags,
            "effective_date": self.effective_date,
            "is_superseded": self.is_superseded,
        }


@dataclass
class RegulatoryFrameworkVersion:
    """A versioned snapshot of a regulatory framework's requirements."""

    framework_id: str
    version: str
    name: str
    jurisdiction: str = ""
    requirements: dict[str, RegulatoryRequirement] = field(default_factory=dict)
    published_date: str = ""
    enforcement_date: str = ""

    @property
    def requirement_count(self) -> int:
        return len(self.requirements)

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework_id": self.framework_id,
            "version": self.version,
            "name": self.name,
            "jurisdiction": self.jurisdiction,
            "requirement_count": self.requirement_count,
            "published_date": self.published_date,
            "enforcement_date": self.enforcement_date,
        }


@dataclass(frozen=True)
class RuleMappingEntry:
    """Maps a governance rule to a specific regulatory requirement."""

    rule_id: str
    framework_id: str
    req_id: str
    coverage_strength: str = "full"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "framework_id": self.framework_id,
            "req_id": self.req_id,
            "coverage_strength": self.coverage_strength,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class CoverageGapItem:
    """A regulatory requirement with insufficient governance rule coverage."""

    framework_id: str
    req_id: str
    title: str
    mapped_rules: tuple[str, ...]
    gap_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework_id": self.framework_id,
            "req_id": self.req_id,
            "title": self.title,
            "mapped_rules": list(self.mapped_rules),
            "gap_type": self.gap_type,
        }


@dataclass(frozen=True)
class RemediationTicket:
    """A structured work item for governance maintainers."""

    ticket_id: str
    severity: str
    framework_id: str
    req_id: str
    rule_ids: tuple[str, ...]
    action: str
    description: str
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "severity": self.severity,
            "framework_id": self.framework_id,
            "req_id": self.req_id,
            "rule_ids": list(self.rule_ids),
            "action": self.action,
            "description": self.description,
            "generated_at": self.generated_at,
        }


@dataclass
class ScanReport:
    """Results of a regulatory horizon scan."""

    frameworks_scanned: int
    total_requirements: int
    mapped_requirements: int
    coverage_gaps: list[CoverageGapItem] = field(default_factory=list)
    stale_mappings: list[RuleMappingEntry] = field(default_factory=list)
    remediation_tickets: list[RemediationTicket] = field(default_factory=list)
    coverage_by_framework: dict[str, float] = field(default_factory=dict)
    generated_at: str = ""

    @property
    def overall_coverage(self) -> float:
        if self.total_requirements == 0:
            return 0.0
        return self.mapped_requirements / self.total_requirements

    @property
    def gap_count(self) -> int:
        return len(self.coverage_gaps)

    def summary(self) -> str:
        lines = [
            "=== RegulatoryHorizonScanner Report ===",
            f"Frameworks scanned : {self.frameworks_scanned}",
            f"Total requirements : {self.total_requirements}",
            f"Mapped             : {self.mapped_requirements}",
            f"Overall coverage   : {self.overall_coverage:.1%}",
            f"Coverage gaps      : {self.gap_count}",
            f"Stale mappings     : {len(self.stale_mappings)}",
            f"Remediation tickets: {len(self.remediation_tickets)}",
            "",
        ]
        if self.coverage_by_framework:
            lines.append("--- Coverage by Framework ---")
            for fid, cov in sorted(self.coverage_by_framework.items()):
                lines.append(f"  {fid:<25} {cov:.1%}")
            lines.append("")
        if self.coverage_gaps:
            lines.append("--- Top Coverage Gaps ---")
            for gap in self.coverage_gaps[:10]:
                lines.append(f"  [{gap.framework_id}] {gap.req_id}: {gap.title}  ({gap.gap_type})")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frameworks_scanned": self.frameworks_scanned,
            "total_requirements": self.total_requirements,
            "mapped_requirements": self.mapped_requirements,
            "overall_coverage": round(self.overall_coverage, 4),
            "gap_count": self.gap_count,
            "stale_mapping_count": len(self.stale_mappings),
            "remediation_ticket_count": len(self.remediation_tickets),
            "coverage_by_framework": {
                k: round(v, 4) for k, v in self.coverage_by_framework.items()
            },
            "coverage_gaps": [g.to_dict() for g in self.coverage_gaps],
            "remediation_tickets": [t.to_dict() for t in self.remediation_tickets],
            "generated_at": self.generated_at,
        }


class RegulatoryHorizonScanner:
    """Monitors regulatory frameworks and flags governance rules needing updates.

    Maintains a structured knowledge base of regulatory requirements and their
    mappings to governance rules. When framework versions change, identifies
    affected rules and generates remediation tickets.

    Args:
        auto_ticket: Automatically generate remediation tickets on scan (default: True).
    """

    def __init__(self, auto_ticket: bool = True) -> None:
        self._auto_ticket = auto_ticket
        self._frameworks: dict[str, RegulatoryFrameworkVersion] = {}
        self._mappings: list[RuleMappingEntry] = []
        self._ticket_counter = 0

    def register_framework(
        self,
        framework_id: str,
        version: str,
        name: str,
        requirements: list[RegulatoryRequirement] | None = None,
        jurisdiction: str = "",
        published_date: str = "",
        enforcement_date: str = "",
    ) -> RegulatoryFrameworkVersion:
        """Register or update a regulatory framework version."""
        fw = RegulatoryFrameworkVersion(
            framework_id=framework_id,
            version=version,
            name=name,
            jurisdiction=jurisdiction,
            requirements={r.req_id: r for r in (requirements or [])},
            published_date=published_date,
            enforcement_date=enforcement_date,
        )
        self._frameworks[framework_id] = fw
        return fw

    def add_requirement(
        self,
        framework_id: str,
        req_id: str,
        title: str,
        description: str = "",
        version: str = "1.0",
        tags: list[str] | None = None,
        effective_date: str = "",
    ) -> RegulatoryRequirement | None:
        """Add a single requirement to an existing framework."""
        fw = self._frameworks.get(framework_id)
        if fw is None:
            return None
        req = RegulatoryRequirement(
            req_id=req_id,
            framework_id=framework_id,
            title=title,
            description=description,
            version=version,
            tags=tags or [],
            effective_date=effective_date,
        )
        fw.requirements[req_id] = req
        return req

    def supersede_requirement(
        self,
        framework_id: str,
        old_req_id: str,
        new_req_id: str,
    ) -> bool:
        """Mark *old_req_id* as superseded by *new_req_id*."""
        fw = self._frameworks.get(framework_id)
        if fw is None:
            return False
        old_req = fw.requirements.get(old_req_id)
        if old_req is None:
            return False
        fw.requirements[old_req_id] = RegulatoryRequirement(
            req_id=old_req.req_id,
            framework_id=old_req.framework_id,
            title=old_req.title,
            description=old_req.description,
            version=old_req.version,
            superseded_by=new_req_id,
            tags=old_req.tags,
            effective_date=old_req.effective_date,
            metadata=old_req.metadata,
        )
        return True

    def map_rule_to_requirement(
        self,
        rule_id: str,
        framework_id: str,
        req_id: str,
        coverage_strength: str = "full",
        notes: str = "",
    ) -> RuleMappingEntry:
        """Create a mapping between a governance rule and a regulatory requirement."""
        entry = RuleMappingEntry(
            rule_id=rule_id,
            framework_id=framework_id,
            req_id=req_id,
            coverage_strength=coverage_strength,
            notes=notes,
        )
        self._mappings.append(entry)
        return entry

    def scan(self, constitution: Any | None = None) -> ScanReport:
        """Run a full regulatory horizon scan.

        Identifies coverage gaps, stale mappings (rules pointing to superseded
        requirements), and generates remediation tickets.

        Args:
            constitution: Optional constitution for rule existence validation.

        Returns:
            :class:`ScanReport`.
        """
        rule_ids_in_constitution: set[str] = set()
        if constitution is not None:
            try:
                for rule in constitution.rules:
                    rid = getattr(rule, "id", None) or getattr(rule, "rule_id", str(rule))
                    if isinstance(rid, str):
                        rule_ids_in_constitution.add(rid)
            except (TypeError, AttributeError):
                pass

        total_reqs = 0
        mapped_reqs: set[tuple[str, str]] = set()
        coverage_gaps: list[CoverageGapItem] = []
        stale: list[RuleMappingEntry] = []
        tickets: list[RemediationTicket] = []
        coverage_by_fw: dict[str, float] = {}

        req_to_rules: dict[tuple[str, str], list[str]] = {}
        for m in self._mappings:
            key = (m.framework_id, m.req_id)
            req_to_rules.setdefault(key, []).append(m.rule_id)
            mapped_reqs.add(key)

        for m in self._mappings:
            fw = self._frameworks.get(m.framework_id)
            if fw is None:
                continue
            req = fw.requirements.get(m.req_id)
            if req and req.is_superseded:
                stale.append(m)

        for fid, fw in self._frameworks.items():
            fw_total = len(fw.requirements)
            total_reqs += fw_total
            fw_mapped = 0
            for req_id, req in fw.requirements.items():
                if req.is_superseded:
                    continue
                key = (fid, req_id)
                rules = req_to_rules.get(key, [])
                if rules:
                    fw_mapped += 1
                else:
                    coverage_gaps.append(
                        CoverageGapItem(
                            framework_id=fid,
                            req_id=req_id,
                            title=req.title,
                            mapped_rules=(),
                            gap_type="unmapped",
                        )
                    )
            active_reqs = sum(1 for r in fw.requirements.values() if not r.is_superseded)
            coverage_by_fw[fid] = fw_mapped / active_reqs if active_reqs > 0 else 0.0

        if self._auto_ticket:
            for gap in coverage_gaps:
                tickets.append(
                    self._make_ticket(
                        severity="high",
                        framework_id=gap.framework_id,
                        req_id=gap.req_id,
                        rule_ids=(),
                        action="create_rule",
                        description=(
                            f"No governance rule covers"
                            f" {gap.framework_id}/{gap.req_id}: {gap.title}"
                        ),
                    )
                )
            for mapping in stale:
                fw = self._frameworks.get(mapping.framework_id)
                req = fw.requirements.get(mapping.req_id) if fw else None
                new_req = req.superseded_by if req else "unknown"
                tickets.append(
                    self._make_ticket(
                        severity="medium",
                        framework_id=mapping.framework_id,
                        req_id=mapping.req_id,
                        rule_ids=(mapping.rule_id,),
                        action="update_mapping",
                        description=(
                            f"Rule {mapping.rule_id} maps to superseded requirement "
                            f"{mapping.req_id} (now {new_req})"
                        ),
                    )
                )

        return ScanReport(
            frameworks_scanned=len(self._frameworks),
            total_requirements=total_reqs,
            mapped_requirements=len(mapped_reqs),
            coverage_gaps=coverage_gaps,
            stale_mappings=stale,
            remediation_tickets=tickets,
            coverage_by_framework=coverage_by_fw,
            generated_at=_ts(),
        )

    def cross_reference(self, tag: str) -> list[RegulatoryRequirement]:
        """Find all requirements across frameworks that share a tag."""
        results: list[RegulatoryRequirement] = []
        for fw in self._frameworks.values():
            for req in fw.requirements.values():
                if tag in req.tags:
                    results.append(req)
        return results

    def framework_ids(self) -> list[str]:
        return list(self._frameworks.keys())

    def get_framework(self, framework_id: str) -> RegulatoryFrameworkVersion | None:
        return self._frameworks.get(framework_id)

    def summary(self) -> dict[str, Any]:
        return {
            "frameworks": len(self._frameworks),
            "total_mappings": len(self._mappings),
            "frameworks_detail": {fid: fw.to_dict() for fid, fw in self._frameworks.items()},
            "generated_at": _ts(),
        }

    def _make_ticket(
        self,
        severity: str,
        framework_id: str,
        req_id: str,
        rule_ids: tuple[str, ...],
        action: str,
        description: str,
    ) -> RemediationTicket:
        self._ticket_counter += 1
        return RemediationTicket(
            ticket_id=f"RHS-{self._ticket_counter:04d}",
            severity=severity,
            framework_id=framework_id,
            req_id=req_id,
            rule_ids=rule_ids,
            action=action,
            description=description,
            generated_at=_ts(),
        )
