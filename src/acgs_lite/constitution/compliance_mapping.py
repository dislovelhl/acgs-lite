"""Map constitutional rules to regulatory framework controls.

Enables cross-framework compliance tracking by linking governance rules
to specific regulatory requirements (EU AI Act articles, NIST AI RMF
functions, ISO 42001 clauses, etc.), detecting coverage gaps, and
generating compliance matrices.

Example::

    from acgs_lite.constitution.compliance_mapping import (
        ComplianceMapper, RegulatoryFramework, ControlMapping,
    )

    mapper = ComplianceMapper()
    mapper.register_framework(RegulatoryFramework(
        framework_id="eu_ai_act",
        name="EU AI Act",
        controls=["Art.9-RiskMgmt", "Art.13-Transparency", "Art.14-HumanOversight"],
    ))
    mapper.map_rule("SAFE-001", "eu_ai_act", "Art.9-RiskMgmt", evidence="Blocks risky actions")
    gaps = mapper.coverage_gaps("eu_ai_act")
    matrix = mapper.compliance_matrix("eu_ai_act")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RegulatoryFramework:
    """A regulatory framework with its enumerated controls."""

    framework_id: str
    name: str
    controls: list[str] = field(default_factory=list)
    jurisdiction: str = ""
    version: str = ""


@dataclass
class ControlMapping:
    """Links a governance rule to a regulatory control."""

    rule_id: str
    framework_id: str
    control_id: str
    evidence: str = ""
    coverage_level: str = "full"
    mapped_at: float = field(default_factory=time.time)
    mapped_by: str = "system"


@dataclass
class CoverageGap:
    """A regulatory control with no mapped governance rules."""

    framework_id: str
    control_id: str
    framework_name: str = ""


class ComplianceMapper:
    """Map governance rules to regulatory framework controls.

    Supports multiple frameworks simultaneously, rule-to-control many-to-many
    mappings, coverage gap detection, compliance matrix generation, and
    cross-framework overlap analysis.

    Example::

        mapper = ComplianceMapper()
        mapper.register_framework(RegulatoryFramework(
            framework_id="nist_ai_rmf",
            name="NIST AI RMF",
            controls=["GOVERN-1", "MAP-1", "MEASURE-1", "MANAGE-1"],
        ))
        mapper.map_rule("SAFE-001", "nist_ai_rmf", "GOVERN-1")
        gaps = mapper.coverage_gaps("nist_ai_rmf")
    """

    def __init__(self) -> None:
        self._frameworks: dict[str, RegulatoryFramework] = {}
        self._mappings: list[ControlMapping] = []

    def register_framework(self, framework: RegulatoryFramework) -> None:
        self._frameworks[framework.framework_id] = framework

    def remove_framework(self, framework_id: str) -> bool:
        removed = self._frameworks.pop(framework_id, None)
        if removed is not None:
            self._mappings = [m for m in self._mappings if m.framework_id != framework_id]
            return True
        return False

    def get_framework(self, framework_id: str) -> RegulatoryFramework | None:
        return self._frameworks.get(framework_id)

    def list_frameworks(self) -> list[RegulatoryFramework]:
        return list(self._frameworks.values())

    def map_rule(
        self,
        rule_id: str,
        framework_id: str,
        control_id: str,
        evidence: str = "",
        coverage_level: str = "full",
        mapped_by: str = "system",
    ) -> ControlMapping | None:
        """Create a mapping between a governance rule and a regulatory control."""
        if framework_id not in self._frameworks:
            return None
        fw = self._frameworks[framework_id]
        if control_id not in fw.controls:
            return None
        for existing in self._mappings:
            if (
                existing.rule_id == rule_id
                and existing.framework_id == framework_id
                and existing.control_id == control_id
            ):
                existing.evidence = evidence
                existing.coverage_level = coverage_level
                return existing

        mapping = ControlMapping(
            rule_id=rule_id,
            framework_id=framework_id,
            control_id=control_id,
            evidence=evidence,
            coverage_level=coverage_level,
            mapped_by=mapped_by,
        )
        self._mappings.append(mapping)
        return mapping

    def unmap_rule(self, rule_id: str, framework_id: str, control_id: str) -> bool:
        before = len(self._mappings)
        self._mappings = [
            m
            for m in self._mappings
            if not (
                m.rule_id == rule_id
                and m.framework_id == framework_id
                and m.control_id == control_id
            )
        ]
        return len(self._mappings) < before

    def mappings_for_rule(self, rule_id: str) -> list[ControlMapping]:
        return [m for m in self._mappings if m.rule_id == rule_id]

    def mappings_for_control(self, framework_id: str, control_id: str) -> list[ControlMapping]:
        return [
            m
            for m in self._mappings
            if m.framework_id == framework_id and m.control_id == control_id
        ]

    def mappings_for_framework(self, framework_id: str) -> list[ControlMapping]:
        return [m for m in self._mappings if m.framework_id == framework_id]

    def coverage_gaps(self, framework_id: str) -> list[CoverageGap]:
        """Return controls in *framework_id* with no mapped rules."""
        fw = self._frameworks.get(framework_id)
        if fw is None:
            return []
        covered = {m.control_id for m in self._mappings if m.framework_id == framework_id}
        return [
            CoverageGap(
                framework_id=framework_id,
                control_id=ctrl,
                framework_name=fw.name,
            )
            for ctrl in fw.controls
            if ctrl not in covered
        ]

    def coverage_score(self, framework_id: str) -> float:
        """Fraction of controls covered (0.0-1.0)."""
        fw = self._frameworks.get(framework_id)
        if fw is None or not fw.controls:
            return 0.0
        covered = {m.control_id for m in self._mappings if m.framework_id == framework_id}
        return len(covered & set(fw.controls)) / len(fw.controls)

    def compliance_matrix(self, framework_id: str) -> dict[str, list[str]]:
        """Return {control_id: [rule_ids]} for the framework."""
        fw = self._frameworks.get(framework_id)
        if fw is None:
            return {}
        matrix: dict[str, list[str]] = {ctrl: [] for ctrl in fw.controls}
        for m in self._mappings:
            if m.framework_id == framework_id and m.control_id in matrix:
                matrix[m.control_id].append(m.rule_id)
        return matrix

    def cross_framework_overlap(self, rule_id: str) -> dict[str, list[str]]:
        """Return {framework_id: [control_ids]} for all frameworks a rule maps to."""
        result: dict[str, list[str]] = {}
        for m in self._mappings:
            if m.rule_id == rule_id:
                result.setdefault(m.framework_id, []).append(m.control_id)
        return result

    def summary(self) -> dict[str, object]:
        """Dashboard summary across all frameworks."""
        fw_scores: dict[str, float] = {}
        for fid in self._frameworks:
            fw_scores[fid] = self.coverage_score(fid)
        unique_rules = {m.rule_id for m in self._mappings}
        return {
            "frameworks": len(self._frameworks),
            "total_mappings": len(self._mappings),
            "unique_rules_mapped": len(unique_rules),
            "coverage_scores": fw_scores,
        }
