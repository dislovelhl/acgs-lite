"""Brazil Lei Geral de Proteção de Dados (LGPD) compliance module.

Implements LGPD (Law No. 13,709/2018) requirements relevant to AI
systems processing personal data in Brazil:
- Legal bases for processing (Arts. 7, 11)
- Data subject rights (Arts. 17-22)
- Automated decision-making (Art. 20)
- Data protection impact assessment (Art. 38)
- Security measures and governance (Arts. 46-50)

Reference: Lei nº 13.709/2018 (Lei Geral de Proteção de Dados Pessoais)
Status: enacted
Enforcement: 2021-08-01 (sanctions became enforceable)
Penalties: Up to 2% of revenue in Brazil, capped at BRL 50 million
    per infraction (Art. 52)

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
    # Automated decision-making (Art. 20)
    (
        "LGPD Art.20(1)",
        "The data subject has the right to request a review of decisions "
        "taken solely on the basis of automated processing of personal data "
        "that affect their interests.",
        "LGPD Article 20(1)",
        "HumanOversightGateway — human review pathway for automated decisions",
        True,
    ),
    (
        "LGPD Art.20(2)",
        "The controller shall provide clear and adequate information "
        "regarding the criteria and procedures used for the automated "
        "decision, subject to trade secrets.",
        "LGPD Article 20(2)",
        "TransparencyDisclosure — system cards with decision criteria",
        True,
    ),
    # Data subject rights (Arts. 17-19)
    (
        "LGPD Art.18(1)",
        "The data subject has the right to obtain from the controller "
        "confirmation of the existence of processing, access to data, "
        "correction, anonymization, and portability.",
        "LGPD Article 18(1)",
        None,
        True,
    ),
    (
        "LGPD Art.18(8)",
        "The data subject has the right to petition the national authority "
        "against the controller regarding their personal data.",
        "LGPD Article 18(8)",
        None,
        False,
    ),
    # Legal bases and consent (Art. 7)
    (
        "LGPD Art.7",
        "Processing of personal data shall only be carried out with a "
        "valid legal basis: consent, legal obligation, public policy, "
        "research, contract, legitimate interest, or health protection.",
        "LGPD Article 7",
        None,
        True,
    ),
    # Transparency (Art. 6 — principles)
    (
        "LGPD Art.6(IV)",
        "Processing shall observe the principle of free access: "
        "guarantee data subjects easy and free consultation regarding "
        "the form and duration of processing and the integrity of data.",
        "LGPD Article 6(IV)",
        "AuditLog — queryable records for data subject access",
        True,
    ),
    (
        "LGPD Art.6(VI)",
        "Processing shall observe the principle of transparency: "
        "guarantee data subjects clear and easily accessible information "
        "about the processing and its agents.",
        "LGPD Article 6(VI)",
        "TransparencyDisclosure — clear processing information disclosure",
        True,
    ),
    # Security (Art. 46)
    (
        "LGPD Art.46(1)",
        "Processing agents shall adopt security, technical, and "
        "administrative measures to protect personal data from "
        "unauthorized access and accidental or unlawful destruction.",
        "LGPD Article 46(1)",
        None,
        True,
    ),
    # Governance (Art. 50)
    (
        "LGPD Art.50(1)",
        "Controllers and processors may formulate rules of good practice "
        "and governance that establish conditions of organization, "
        "complaint handling, and applicable rules.",
        "LGPD Article 50(1)",
        "GovernanceEngine — governance rules as documented best practices",
        True,
    ),
    (
        "LGPD Art.50(2)(I)(d)",
        "Governance programme shall include mechanisms for internal and "
        "external supervision and auditing.",
        "LGPD Article 50(2)(I)(d)",
        "AuditLog — tamper-evident audit chain for supervision",
        True,
    ),
    # Data protection impact assessment (Art. 38)
    (
        "LGPD Art.38(1)",
        "The national authority may determine that the controller prepare "
        "a data protection impact assessment, including description of "
        "processes, safeguards, and risk analysis.",
        "LGPD Article 38(1)",
        "RiskClassifier — risk analysis supporting impact assessment",
        True,
    ),
    # Incident notification (Art. 48)
    (
        "LGPD Art.48(1)",
        "The controller must communicate to the national authority and "
        "the data subject the occurrence of a security incident that "
        "may cause risk or relevant damage.",
        "LGPD Article 48(1)",
        None,
        True,
    ),
]

_ACGS_LITE_MAP: dict[str, str] = {
    "LGPD Art.20(1)": (
        "acgs-lite HumanOversightGateway — human review pathway for "
        "data subjects to contest automated decisions"
    ),
    "LGPD Art.20(2)": (
        "acgs-lite TransparencyDisclosure — system cards documenting "
        "criteria and procedures for automated decisions"
    ),
    "LGPD Art.6(IV)": (
        "acgs-lite AuditLog — queryable per-subject records enabling "
        "free access to processing information"
    ),
    "LGPD Art.6(VI)": (
        "acgs-lite TransparencyDisclosure — clear and accessible "
        "processing information disclosure"
    ),
    "LGPD Art.50(1)": (
        "acgs-lite GovernanceEngine — governance rules and organization "
        "documented as constitutional code"
    ),
    "LGPD Art.50(2)(I)(d)": (
        "acgs-lite AuditLog — tamper-evident JSONL with SHA-256 chain "
        "for supervision and auditing"
    ),
    "LGPD Art.38(1)": (
        "acgs-lite RiskClassifier — automated risk analysis supporting "
        "data protection impact assessment"
    ),
}


class BrazilLGPDFramework:
    """Brazil LGPD compliance assessor.

    Covers automated decision-making rights, data subject rights,
    governance, security, and impact assessments.

    Penalties: Up to 2% of revenue in Brazil, capped at BRL 50M.

    Status: Enacted. Sanctions enforceable since 2021-08-01.
    """

    framework_id: str = "brazil_lgpd"
    framework_name: str = "Brazil Lei Geral de Proteção de Dados (LGPD)"
    jurisdiction: str = "Brazil"
    status: str = "enacted"
    enforcement_date: str | None = "2021-08-01"

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
    fw: BrazilLGPDFramework, checklist: list[ChecklistItem],
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
                f"{i.ref}: Address this LGPD requirement. "
                f"Penalties up to 2% of Brazil revenue (BRL 50M cap)."
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
