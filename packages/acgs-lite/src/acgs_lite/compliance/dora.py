"""Digital Operational Resilience Act (DORA) compliance module.

Implements DORA (Regulation (EU) 2022/2554) requirements for ICT risk
management in financial entities, including AI systems used in finance:
- ICT risk management framework (Arts. 5-16)
- ICT-related incident management (Arts. 17-23)
- Digital operational resilience testing (Arts. 24-27)
- Third-party risk management (Arts. 28-44)

Reference: Regulation (EU) 2022/2554 (DORA)
Status: enacted
Enforcement: 2025-01-17
Penalties: Supervisory measures; up to 1% of average daily worldwide
    turnover for critical ICT third-party providers (Art. 35)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from acgs_lite.compliance.base import (
    ChecklistItem,
    ChecklistStatus,
    FrameworkAssessment,
)

_ITEMS: list[tuple[str, str, str, str | None, bool]] = [
    # ICT risk management (Art. 5-6)
    (
        "DORA Art.5(1)",
        "Financial entities shall have in place an internal governance and "
        "control framework that ensures effective and prudent management of "
        "all ICT risks.",
        "DORA Article 5(1)",
        "GovernanceEngine — automated governance control framework",
        True,
    ),
    (
        "DORA Art.6(1)",
        "Financial entities shall have a sound, comprehensive, and "
        "well-documented ICT risk management framework enabling them to "
        "address ICT risk quickly, efficiently, and comprehensively.",
        "DORA Article 6(1)",
        "GovernanceEngine — documented constitutional risk management",
        True,
    ),
    (
        "DORA Art.6(8)",
        "As part of the ICT risk management framework, identify, classify, "
        "and adequately document all ICT-supported business functions and "
        "information assets.",
        "DORA Article 6(8)",
        "RiskClassifier — automated ICT asset risk classification",
        True,
    ),
    # Protection and prevention (Art. 9)
    (
        "DORA Art.9(1)",
        "Financial entities shall use and maintain updated ICT systems that "
        "are designed to minimise ICT risk, including resilience, continuity, "
        "and availability measures.",
        "DORA Article 9(1)",
        None,
        True,
    ),
    (
        "DORA Art.9(4)",
        "Implement ICT security policies, procedures, protocols, and tools "
        "for network security management, data protection, and access control.",
        "DORA Article 9(4)",
        None,
        True,
    ),
    # Detection (Art. 10)
    (
        "DORA Art.10(1)",
        "Have in place mechanisms to promptly detect anomalous activities "
        "including ICT network performance issues and ICT-related incidents.",
        "DORA Article 10(1)",
        "AuditLog — continuous monitoring and anomaly detection trail",
        True,
    ),
    # Response and recovery (Art. 11)
    (
        "DORA Art.11(1)",
        "Establish a comprehensive ICT business continuity policy and "
        "disaster recovery plans as integral parts of the operational "
        "resilience strategy.",
        "DORA Article 11(1)",
        None,
        True,
    ),
    # Incident management (Art. 17)
    (
        "DORA Art.17(1)",
        "Define, establish, and implement an ICT-related incident management "
        "process to detect, manage, and notify ICT-related incidents.",
        "DORA Article 17(1)",
        None,
        True,
    ),
    (
        "DORA Art.17(3)",
        "Classify ICT-related incidents and determine their impact based on "
        "criteria including geographical spread, data losses, criticality "
        "of services, and economic impact.",
        "DORA Article 17(3)",
        "RiskClassifier — incident classification with impact assessment",
        True,
    ),
    # Incident reporting (Art. 19)
    (
        "DORA Art.19(1)",
        "Report major ICT-related incidents to the relevant competent "
        "authority using standardised classification and reporting templates.",
        "DORA Article 19(1)",
        None,
        True,
    ),
    # Digital operational resilience testing (Art. 24-25)
    (
        "DORA Art.24(1)",
        "Establish, maintain, and review a sound and comprehensive digital "
        "operational resilience testing programme as an integral part of "
        "ICT risk management.",
        "DORA Article 24(1)",
        None,
        True,
    ),
    (
        "DORA Art.25(1)",
        "Significant financial entities shall carry out threat-led "
        "penetration testing (TLPT) at least every 3 years.",
        "DORA Article 25(1)",
        None,
        True,
    ),
    # Third-party risk management (Art. 28)
    (
        "DORA Art.28(2)",
        "Manage ICT third-party risk as an integral component of ICT risk "
        "within the ICT risk management framework, including due diligence "
        "and contractual arrangements.",
        "DORA Article 28(2)",
        None,
        True,
    ),
    # Logging (Art. 12)
    (
        "DORA Art.12(1)",
        "Financial entities shall have in place logging policies that record "
        "ICT operations, including ICT access and ICT change management logs.",
        "DORA Article 12(1)",
        "AuditLog — comprehensive tamper-evident logging",
        True,
    ),
]

# Refs conditional on is_significant_entity
_SIGNIFICANT_ENTITY_REFS: set[str] = {"DORA Art.25(1)"}

_ACGS_LITE_MAP: dict[str, str] = {
    "DORA Art.5(1)": (
        "acgs-lite GovernanceEngine — internal governance control framework "
        "with constitutional rules and enforcement"
    ),
    "DORA Art.6(1)": (
        "acgs-lite GovernanceEngine — documented ICT risk management framework "
        "via constitution-as-code"
    ),
    "DORA Art.6(8)": (
        "acgs-lite RiskClassifier — automated classification and documentation "
        "of ICT-supported functions and risk profiles"
    ),
    "DORA Art.10(1)": (
        "acgs-lite AuditLog — continuous event logging enabling anomaly detection"
    ),
    "DORA Art.17(3)": (
        "acgs-lite RiskClassifier — incident impact classification with "
        "severity assessment and obligation mapping"
    ),
    "DORA Art.12(1)": (
        "acgs-lite AuditLog — tamper-evident JSONL logging with SHA-256 "
        "hash chaining for ICT operations"
    ),
}


class DORAFramework:
    """DORA (Digital Operational Resilience Act) compliance assessor.

    Covers ICT risk management, incident management, resilience testing,
    and third-party risk for financial entities using AI systems.

    Penalties: Supervisory measures; up to 1% of average daily worldwide
    turnover for critical ICT third-party providers.

    Status: Enacted. Effective 2025-01-17.
    """

    framework_id: str = "dora"
    framework_name: str = "Digital Operational Resilience Act (DORA)"
    jurisdiction: str = "European Union"
    status: str = "enacted"
    enforcement_date: str | None = "2025-01-17"

    def get_checklist(self, system_description: dict[str, Any]) -> list[ChecklistItem]:
        """Generate DORA checklist, scoping by entity significance."""
        is_significant = system_description.get("is_significant_entity", False)

        items: list[ChecklistItem] = []
        for ref, req, citation, feature, blocking in _ITEMS:
            item = ChecklistItem(
                ref=ref, requirement=req, acgs_lite_feature=feature,
                blocking=blocking, legal_citation=citation,
            )
            if ref in _SIGNIFICANT_ENTITY_REFS and not is_significant:
                item.mark_not_applicable(
                    "Not applicable: entity is not classified as significant."
                )
            items.append(item)
        return items

    def auto_populate_acgs_lite(self, checklist: list[ChecklistItem]) -> None:
        for item in checklist:
            if item.ref in _ACGS_LITE_MAP and item.status != ChecklistStatus.NOT_APPLICABLE:
                item.mark_complete(_ACGS_LITE_MAP[item.ref])

    def assess(self, system_description: dict[str, Any]) -> FrameworkAssessment:
        checklist = self.get_checklist(system_description)
        self.auto_populate_acgs_lite(checklist)
        return _build_assessment(self, checklist)


def _build_assessment(fw: DORAFramework, checklist: list[ChecklistItem]) -> FrameworkAssessment:
    total = len(checklist)
    compliant = sum(
        1 for i in checklist
        if i.status in (ChecklistStatus.COMPLIANT, ChecklistStatus.NOT_APPLICABLE)
    )
    acgs_covered = sum(1 for i in checklist if i.acgs_lite_feature is not None)
    gaps = tuple(
        f"{i.ref}: {i.requirement[:120]}"
        for i in checklist
        if i.status not in (ChecklistStatus.COMPLIANT, ChecklistStatus.NOT_APPLICABLE)
        and i.blocking
    )
    recs: list[str] = []
    for i in checklist:
        if i.status == ChecklistStatus.PENDING and i.blocking:
            recs.append(f"{i.ref}: Address this DORA requirement for operational resilience.")
    return FrameworkAssessment(
        framework_id=fw.framework_id,
        framework_name=fw.framework_name,
        compliance_score=round(compliant / total, 4) if total else 1.0,
        items=tuple(i.to_dict() for i in checklist),
        gaps=gaps,
        acgs_lite_coverage=round(acgs_covered / total, 4) if total else 0.0,
        recommendations=tuple(recs),
        assessed_at=datetime.now(UTC).isoformat(),
    )
