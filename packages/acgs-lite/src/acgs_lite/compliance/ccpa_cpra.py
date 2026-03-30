"""California Consumer Privacy Act / California Privacy Rights Act
(CCPA/CPRA) compliance module.

Implements CCPA (as amended by CPRA) requirements relevant to AI
systems processing personal information of California consumers:
- Consumer rights (§§1798.100-125)
- Automated decision-making technology (§§1798.185(a)(16))
- Business obligations (§§1798.100, 130, 135, 140, 145, 150, 155)
- Risk assessments for high-risk processing (CPRA §1798.185(a)(15))

Reference: California Civil Code §§1798.100-1798.199.100 (CCPA/CPRA)
Status: enacted
Enforcement: 2020-07-01 (CCPA); 2023-01-01 (CPRA amendments)
Penalties: Up to USD 7,500 per intentional violation; USD 2,500 per
    unintentional violation (§1798.155)

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
    # Right to know (§1798.100)
    (
        "CCPA §1798.100(a)",
        "Consumers have the right to know what personal information is "
        "collected, used, shared, or sold, and to whom it is disclosed.",
        "Cal. Civ. Code §1798.100(a)",
        "TransparencyDisclosure — data collection and usage disclosure",
        True,
    ),
    # Right to delete (§1798.105)
    (
        "CCPA §1798.105(a)",
        "Consumers have the right to request deletion of their personal "
        "information collected by the business.",
        "Cal. Civ. Code §1798.105(a)",
        None,
        True,
    ),
    # Right to opt out of sale/sharing (§1798.120)
    (
        "CCPA §1798.120(a)",
        "Consumers have the right to opt out of the sale or sharing of "
        "their personal information.",
        "Cal. Civ. Code §1798.120(a)",
        None,
        True,
    ),
    # Right to correct (§1798.106)
    (
        "CCPA §1798.106(a)",
        "Consumers have the right to request correction of inaccurate "
        "personal information maintained by a business.",
        "Cal. Civ. Code §1798.106(a)",
        None,
        True,
    ),
    # Right to limit use of sensitive personal information (§1798.121)
    (
        "CCPA §1798.121(a)",
        "Consumers have the right to limit a business's use and disclosure "
        "of their sensitive personal information.",
        "Cal. Civ. Code §1798.121(a)",
        None,
        True,
    ),
    # Notice obligations (§1798.100(b))
    (
        "CCPA §1798.100(b)",
        "Business shall, at or before the point of collection, inform "
        "consumers of the categories of personal information to be "
        "collected and the purposes for which it will be used.",
        "Cal. Civ. Code §1798.100(b)",
        "TransparencyDisclosure — pre-collection notice generation",
        True,
    ),
    # Automated decision-making (§1798.185(a)(16)) — CPRA
    (
        "CPRA §1798.185(a)(16)(A)",
        "Consumers have the right to opt out of a business's use of "
        "automated decision-making technology, including profiling.",
        "Cal. Civ. Code §1798.185(a)(16)(A)",
        None,
        True,
    ),
    (
        "CPRA §1798.185(a)(16)(B)",
        "Consumers have the right to access information about the logic "
        "involved in automated decision-making processes and a description "
        "of the likely outcome.",
        "Cal. Civ. Code §1798.185(a)(16)(B)",
        "TransparencyDisclosure — automated decision logic disclosure",
        True,
    ),
    # Risk assessments (§1798.185(a)(15)) — CPRA
    (
        "CPRA §1798.185(a)(15)",
        "Businesses processing consumers' personal information presenting "
        "significant risk to consumers' privacy or security shall conduct "
        "cybersecurity and regular risk assessments.",
        "Cal. Civ. Code §1798.185(a)(15)",
        "RiskClassifier — automated risk assessment for privacy impact",
        True,
    ),
    # Security (§1798.150)
    (
        "CCPA §1798.150(a)",
        "Implement and maintain reasonable security procedures and practices "
        "appropriate to the nature of the personal information to protect it.",
        "Cal. Civ. Code §1798.150(a)",
        None,
        True,
    ),
    # Service provider obligations (§1798.140(ag))
    (
        "CCPA §1798.140(ag)",
        "Service providers and contractors shall not retain, use, or disclose "
        "personal information for any purpose other than performing the "
        "services specified in the contract.",
        "Cal. Civ. Code §1798.140(ag)",
        None,
        True,
    ),
    # Record-keeping
    (
        "CCPA §1798.130(a)",
        "Make available two or more designated methods for submitting "
        "consumer requests and maintain records of requests and responses "
        "for 24 months.",
        "Cal. Civ. Code §1798.130(a)",
        "AuditLog — comprehensive request/response record-keeping",
        True,
    ),
]

_ACGS_LITE_MAP: dict[str, str] = {
    "CCPA §1798.100(a)": (
        "acgs-lite TransparencyDisclosure — generates data collection "
        "and usage disclosure documentation"
    ),
    "CCPA §1798.100(b)": (
        "acgs-lite TransparencyDisclosure — pre-collection notice "
        "generation with purpose documentation"
    ),
    "CPRA §1798.185(a)(16)(B)": (
        "acgs-lite TransparencyDisclosure — automated decision logic "
        "disclosure with outcome description"
    ),
    "CPRA §1798.185(a)(15)": (
        "acgs-lite RiskClassifier — automated risk assessment for "
        "privacy and security impact"
    ),
    "CCPA §1798.130(a)": (
        "acgs-lite AuditLog — tamper-evident JSONL records of consumer "
        "requests and responses"
    ),
}


class CCPACPRAFramework:
    """CCPA/CPRA compliance assessor.

    Covers consumer rights, automated decision-making provisions,
    risk assessments, security, and record-keeping.

    Penalties: Up to USD 7,500 per intentional violation.

    Status: Enacted. CCPA effective 2020-07-01; CPRA 2023-01-01.
    """

    framework_id: str = "ccpa_cpra"
    framework_name: str = (
        "California Consumer Privacy Act / California Privacy Rights Act (CCPA/CPRA)"
    )
    jurisdiction: str = "California"
    status: str = "enacted"
    enforcement_date: str | None = "2020-07-01"

    def get_checklist(self, system_description: dict[str, Any]) -> list[ChecklistItem]:
        return [
            ChecklistItem(
                ref=ref, requirement=req, acgs_lite_feature=feature,
                blocking=blocking, legal_citation=citation,
            )
            for ref, req, citation, feature, blocking in _ITEMS
        ]

    def auto_populate_acgs_lite(self, checklist: list[ChecklistItem]) -> None:
        for item in checklist:
            if item.ref in _ACGS_LITE_MAP:
                item.mark_complete(_ACGS_LITE_MAP[item.ref])

    def assess(self, system_description: dict[str, Any]) -> FrameworkAssessment:
        checklist = self.get_checklist(system_description)
        self.auto_populate_acgs_lite(checklist)
        return _build_assessment(self, checklist)


def _build_assessment(
    fw: CCPACPRAFramework, checklist: list[ChecklistItem],
) -> FrameworkAssessment:
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
            recs.append(
                f"{i.ref}: Address this CCPA/CPRA requirement. "
                f"Penalties up to USD 7,500 per intentional violation."
            )
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
