"""India Digital Personal Data Protection Act (DPDP) compliance module.

Implements the DPDP Act, 2023 requirements relevant to AI systems
processing personal data in India:
- Consent and notice (§§4-6)
- Rights of Data Principals (§§8-14)
- Obligations of Data Fiduciaries (§§7-10)
- Significant Data Fiduciary obligations (§16)
- Children's data (§9)

Reference: Digital Personal Data Protection Act, 2023 (Act No. 22 of 2023)
Status: enacted
Enforcement: 2023-08-11 (Royal Assent); sectoral rules TBD
Penalties: Up to INR 250 crore (~USD 30M) per violation (§33)

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
    # Notice and consent (§§4-6)
    (
        "DPDP §4(1)",
        "Process personal data only for a lawful purpose for which the Data "
        "Principal has given consent, or for certain legitimate uses.",
        "DPDP Act §4(1)",
        None,
        True,
    ),
    (
        "DPDP §5(1)",
        "Give the Data Principal a notice containing a description of "
        "personal data sought and the purpose of processing before or "
        "at the time of requesting consent.",
        "DPDP Act §5(1)",
        "TransparencyDisclosure — pre-processing notice generation",
        True,
    ),
    # Data Principal rights (§§8-14)
    (
        "DPDP §8(1)",
        "Data Principal has the right to obtain information about the "
        "processing of their personal data, including a summary of "
        "personal data processed.",
        "DPDP Act §8(1)",
        "AuditLog — queryable per-principal data processing records",
        True,
    ),
    (
        "DPDP §8(3)",
        "Data Principal has the right to correction, completion, updating, "
        "and erasure of their personal data.",
        "DPDP Act §8(3)",
        None,
        True,
    ),
    (
        "DPDP §8(5)",
        "Data Principal has the right of grievance redressal and the right "
        "to nominate another person to exercise rights on their behalf.",
        "DPDP Act §8(5)",
        "HumanOversightGateway — grievance redressal mechanism",
        True,
    ),
    # Data Fiduciary obligations (§§7, 10)
    (
        "DPDP §7(1)",
        "Data Fiduciary shall implement appropriate technical and "
        "organisational measures to ensure compliance with this Act.",
        "DPDP Act §7(1)",
        "GovernanceEngine — technical governance measures for compliance",
        True,
    ),
    (
        "DPDP §7(3)",
        "Protect personal data in its possession or under its control by "
        "taking reasonable security safeguards to prevent personal data breach.",
        "DPDP Act §7(3)",
        None,
        True,
    ),
    (
        "DPDP §10(1)",
        "In the event of a personal data breach, notify the Board and "
        "each affected Data Principal in the prescribed manner.",
        "DPDP Act §10(1)",
        None,
        True,
    ),
    # Children's data (§9) — conditional on processes_children_data
    (
        "DPDP §9(1)",
        "Before processing any personal data of a child, obtain verifiable "
        "consent of the parent or lawful guardian.",
        "DPDP Act §9(1)",
        None,
        True,
    ),
    (
        "DPDP §9(3)",
        "Do not undertake processing of personal data that is likely to "
        "cause any detrimental effect on the well-being of a child.",
        "DPDP Act §9(3)",
        "GovernanceEngine — constitutional rules preventing harmful processing",
        True,
    ),
    # Significant Data Fiduciary (§16) — conditional on is_significant_data_fiduciary
    (
        "DPDP §16(2)",
        "Significant Data Fiduciary shall appoint a Data Protection Officer "
        "based in India who shall represent the Data Fiduciary and be the "
        "point of contact for grievance redressal.",
        "DPDP Act §16(2)",
        None,
        True,
    ),
    (
        "DPDP §16(3)",
        "Significant Data Fiduciary shall appoint an independent data "
        "auditor to evaluate compliance and carry out periodic data "
        "protection impact assessments.",
        "DPDP Act §16(3)",
        None,
        True,
    ),
    (
        "DPDP §16(5)",
        "Significant Data Fiduciary processing personal data for AI "
        "or algorithmic decisions that significantly affect Data Principals "
        "shall ensure transparency and accountability.",
        "DPDP Act §16(5)",
        "TransparencyDisclosure — algorithmic decision transparency",
        True,
    ),
]

# Refs conditional on is_significant_data_fiduciary
_SDF_REFS: set[str] = {"DPDP §16(2)", "DPDP §16(3)", "DPDP §16(5)"}

# Refs conditional on processes_children_data
_CHILDREN_REFS: set[str] = {"DPDP §9(1)", "DPDP §9(3)"}

_ACGS_LITE_MAP: dict[str, str] = {
    "DPDP §5(1)": (
        "acgs-lite TransparencyDisclosure — generates pre-processing "
        "notices describing data and purpose"
    ),
    "DPDP §8(1)": (
        "acgs-lite AuditLog — queryable per-principal audit trail with "
        "processing records"
    ),
    "DPDP §8(5)": (
        "acgs-lite HumanOversightGateway — grievance redressal and "
        "human review mechanism"
    ),
    "DPDP §7(1)": (
        "acgs-lite GovernanceEngine — technical and organisational "
        "governance measures for compliance"
    ),
    "DPDP §9(3)": (
        "acgs-lite GovernanceEngine — constitutional rules preventing "
        "processing detrimental to children"
    ),
    "DPDP §16(5)": (
        "acgs-lite TransparencyDisclosure — algorithmic decision transparency "
        "for significant data fiduciaries"
    ),
}


class IndiaDPDPFramework:
    """India DPDP (Digital Personal Data Protection Act, 2023) compliance assessor.

    Covers consent/notice, Data Principal rights, Data Fiduciary obligations,
    Significant Data Fiduciary obligations, and children's data.

    Penalties: Up to INR 250 crore (~USD 30M) per violation (§33).

    Status: Enacted 2023-08-11. Sectoral rules pending.
    """

    framework_id: str = "india_dpdp"
    framework_name: str = "India Digital Personal Data Protection Act (DPDP), 2023"
    jurisdiction: str = "India"
    status: str = "enacted"
    enforcement_date: str | None = "2023-08-11"

    def get_checklist(self, system_description: dict[str, Any]) -> list[ChecklistItem]:
        is_sdf = system_description.get("is_significant_data_fiduciary", False)
        processes_children = system_description.get("processes_children_data", False)

        items: list[ChecklistItem] = []
        for ref, req, citation, feature, blocking in _ITEMS:
            item = ChecklistItem(
                ref=ref, requirement=req, acgs_lite_feature=feature,
                blocking=blocking, legal_citation=citation,
            )
            if ref in _SDF_REFS and not is_sdf:
                item.mark_not_applicable(
                    "Not applicable: entity is not a Significant Data Fiduciary."
                )
            if ref in _CHILDREN_REFS and not processes_children:
                item.mark_not_applicable(
                    "Not applicable: system does not process children's data."
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


def _build_assessment(
    fw: IndiaDPDPFramework, checklist: list[ChecklistItem],
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
                f"{i.ref}: Address this DPDP requirement. "
                f"Penalties up to INR 250 crore per violation."
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
