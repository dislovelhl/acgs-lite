"""GDPR automated decision-making compliance module.

Implements GDPR articles relevant to AI/automated decision-making:
- Article 22: Right not to be subject to solely automated decisions
- Articles 13-14: Right to meaningful information about logic involved
- Article 15: Right of access to information about automated decisions
- Article 35: Data Protection Impact Assessment (DPIA)

Reference: Regulation (EU) 2016/679 (General Data Protection Regulation)
Enforcement: Since May 25, 2018. Fines up to 4% of global annual revenue
or EUR 20 million, whichever is higher.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from acgs_lite.compliance.base import (
    ChecklistItem,
    ChecklistStatus,
    FrameworkAssessment,
)

_GDPR_ITEMS: list[tuple[str, str, str, str | None, bool]] = [
    # Article 22: Automated individual decision-making
    (
        "GDPR Art.22(1)",
        "Ensure data subjects have the right not to be subject to a decision "
        "based solely on automated processing which produces legal effects or "
        "similarly significantly affects them.",
        "GDPR Article 22(1)",
        "HumanOversightGateway — ensures human review for high-impact decisions",
        True,
    ),
    (
        "GDPR Art.22(3)",
        "Where automated decisions are permitted under Art.22(2), implement "
        "suitable measures to safeguard data subject rights including the right "
        "to obtain human intervention, express their point of view, and contest.",
        "GDPR Article 22(3)",
        "HumanOversightGateway — provides contestation and human review pathway",
        True,
    ),
    # Articles 13-14: Information obligations
    (
        "GDPR Art.13(2)(f)",
        "Provide meaningful information about the logic involved in automated "
        "decision-making, as well as the significance and envisaged consequences "
        "of such processing for the data subject.",
        "GDPR Article 13(2)(f)",
        "TransparencyDisclosure — generates system cards with logic explanation",
        True,
    ),
    (
        "GDPR Art.14(2)(g)",
        "When personal data is not obtained from the data subject, provide "
        "meaningful information about the logic involved in automated "
        "decision-making and its significance.",
        "GDPR Article 14(2)(g)",
        "TransparencyDisclosure — system card with capabilities and limitations",
        True,
    ),
    # Article 15: Right of access
    (
        "GDPR Art.15(1)(h)",
        "Provide data subjects with access to meaningful information about "
        "the logic involved, significance, and envisaged consequences of "
        "automated decision-making on request.",
        "GDPR Article 15(1)(h)",
        "AuditLog — queryable audit trail for per-subject decision records",
        True,
    ),
    # Article 35: Data Protection Impact Assessment
    (
        "GDPR Art.35(1)",
        "Carry out a Data Protection Impact Assessment (DPIA) where automated "
        "processing, including profiling, is likely to result in a high risk "
        "to the rights and freedoms of natural persons.",
        "GDPR Article 35(1)",
        "RiskClassifier — automated risk classification for DPIA scoping",
        True,
    ),
    (
        "GDPR Art.35(7)(a)",
        "DPIA shall contain a systematic description of the envisaged processing "
        "operations and the purposes of the processing.",
        "GDPR Article 35(7)(a)",
        None,
        True,
    ),
    (
        "GDPR Art.35(7)(b)",
        "DPIA shall include an assessment of the necessity and proportionality "
        "of the processing operations in relation to the purposes.",
        "GDPR Article 35(7)(b)",
        None,
        True,
    ),
    (
        "GDPR Art.35(7)(c)",
        "DPIA shall include an assessment of the risks to the rights and "
        "freedoms of data subjects.",
        "GDPR Article 35(7)(c)",
        "RiskClassifier — risk tier assessment with obligation mapping",
        True,
    ),
    (
        "GDPR Art.35(7)(d)",
        "DPIA shall include the measures envisaged to address the risks, "
        "including safeguards, security measures, and mechanisms to ensure "
        "protection of personal data.",
        "GDPR Article 35(7)(d)",
        "GovernanceEngine — constitutional rules as risk mitigation measures",
        True,
    ),
    # Article 5: Data processing principles
    (
        "GDPR Art.5(1)(a)",
        "Process personal data lawfully, fairly, and in a transparent manner "
        "in relation to the data subject (lawfulness, fairness, transparency).",
        "GDPR Article 5(1)(a)",
        "TransparencyDisclosure — Article 13 compliant system cards",
        True,
    ),
    (
        "GDPR Art.5(2)",
        "The controller shall be responsible for, and be able to demonstrate "
        "compliance with, the data processing principles (accountability).",
        "GDPR Article 5(2)",
        "AuditLog — cryptographic proof of governance compliance",
        True,
    ),
]

_ACGS_LITE_MAP: dict[str, str] = {
    "GDPR Art.22(1)": (
        "acgs-lite HumanOversightGateway — configurable human-in-the-loop "
        "gates ensuring no solely automated high-impact decisions"
    ),
    "GDPR Art.22(3)": (
        "acgs-lite HumanOversightGateway — provides contestation mechanism "
        "and human intervention pathway with audit trail"
    ),
    "GDPR Art.13(2)(f)": (
        "acgs-lite TransparencyDisclosure — generates machine-readable "
        "system cards with logic explanation and decision factors"
    ),
    "GDPR Art.14(2)(g)": (
        "acgs-lite TransparencyDisclosure — system card documenting "
        "capabilities, limitations, and decision logic"
    ),
    "GDPR Art.15(1)(h)": (
        "acgs-lite AuditLog — queryable per-subject audit trail with "
        "full decision records and chain integrity"
    ),
    "GDPR Art.35(1)": (
        "acgs-lite RiskClassifier — automated risk classification to scope DPIA requirements"
    ),
    "GDPR Art.35(7)(c)": (
        "acgs-lite RiskClassifier — risk tier assessment with "
        "obligation mapping for rights impact evaluation"
    ),
    "GDPR Art.35(7)(d)": (
        "acgs-lite GovernanceEngine — constitutional rules serve as "
        "documented risk mitigation safeguards"
    ),
    "GDPR Art.5(1)(a)": (
        "acgs-lite TransparencyDisclosure — Article 13 compliant transparency documentation"
    ),
    "GDPR Art.5(2)": (
        "acgs-lite AuditLog — tamper-evident audit chain demonstrating "
        "accountability and compliance"
    ),
}


class GDPRFramework:
    """GDPR automated decision-making compliance assessor.

    Focuses on GDPR provisions most relevant to AI systems: automated
    decision-making (Art. 22), transparency obligations (Art. 13-15),
    and Data Protection Impact Assessments (Art. 35).

    Penalties: Up to EUR 20 million or 4% of worldwide annual turnover,
    whichever is higher (Art. 83).

    Status: Enacted since May 25, 2018. Enforced by national DPAs.

    Usage::

        from acgs_lite.compliance.gdpr import GDPRFramework

        framework = GDPRFramework()
        assessment = framework.assess({"system_id": "my-system", "processes_pii": True})
    """

    framework_id: str = "gdpr"
    framework_name: str = "EU General Data Protection Regulation (GDPR)"
    jurisdiction: str = "European Union"
    status: str = "enacted"
    enforcement_date: str | None = "2018-05-25"

    def get_checklist(self, system_description: dict[str, Any]) -> list[ChecklistItem]:
        """Generate GDPR AI-relevant checklist items."""
        return [
            ChecklistItem(
                ref=ref,
                requirement=req,
                acgs_lite_feature=feature,
                blocking=blocking,
                legal_citation=citation,
            )
            for ref, req, citation, feature, blocking in _GDPR_ITEMS
        ]

    def auto_populate_acgs_lite(self, checklist: list[ChecklistItem]) -> None:
        """Mark items that acgs-lite directly satisfies."""
        for item in checklist:
            if item.ref in _ACGS_LITE_MAP:
                item.mark_complete(_ACGS_LITE_MAP[item.ref])

    def assess(self, system_description: dict[str, Any]) -> FrameworkAssessment:
        """Run full GDPR automated decision-making assessment."""
        checklist = self.get_checklist(system_description)
        self.auto_populate_acgs_lite(checklist)

        total = len(checklist)
        compliant = sum(
            1
            for item in checklist
            if item.status in (ChecklistStatus.COMPLIANT, ChecklistStatus.NOT_APPLICABLE)
        )
        acgs_covered = sum(1 for item in checklist if item.acgs_lite_feature is not None)
        gaps = tuple(
            f"{item.ref}: {item.requirement[:120]}"
            for item in checklist
            if item.status not in (ChecklistStatus.COMPLIANT, ChecklistStatus.NOT_APPLICABLE)
            and item.blocking
        )

        recs: list[str] = []
        for item in checklist:
            if item.status == ChecklistStatus.PENDING and item.blocking:
                recs.append(
                    f"{item.ref}: Address this requirement. Non-compliance "
                    f"risks fines up to 4% of global annual revenue."
                )

        return FrameworkAssessment(
            framework_id=self.framework_id,
            framework_name=self.framework_name,
            compliance_score=round(compliant / total, 4) if total else 1.0,
            items=tuple(item.to_dict() for item in checklist),
            gaps=gaps,
            acgs_lite_coverage=round(acgs_covered / total, 4) if total else 0.0,
            recommendations=tuple(recs),
            assessed_at=datetime.now(UTC).isoformat(),
        )
