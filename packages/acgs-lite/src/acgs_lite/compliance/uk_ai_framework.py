"""UK AI Regulation Framework compliance module.

Implements the UK's pro-innovation approach to AI regulation as set out
in the AI Regulation White Paper (March 2023) and subsequent policy:
- Safety, security, and robustness (PRO-1)
- Transparency and explainability (PRO-2)
- Fairness (PRO-3)
- Accountability and governance (PRO-4)
- Contestability and redress (PRO-5)

Reference: UK DSIT — A pro-innovation approach to AI regulation
    (White Paper, Cm 815, March 2023)
Status: voluntary (regulatory framework; sector regulators interpret)
Enforcement: N/A — sector regulators apply principles to their domains
Penalties: Vary by sector regulator enforcement

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
    # PRO-1: Safety, security, and robustness
    (
        "UK PRO-1.1",
        "AI systems should function in a robust, secure, and safe way "
        "throughout their lifecycle, with risks identified and mitigated.",
        "UK AI White Paper, Principle 1 — Safety",
        "GovernanceEngine — continuous safety validation via constitutional rules",
        True,
    ),
    (
        "UK PRO-1.2",
        "Implement appropriate measures to ensure AI system resilience "
        "against attempts to alter use or performance by malicious actors.",
        "UK AI White Paper, Principle 1 — Security",
        None,
        True,
    ),
    (
        "UK PRO-1.3",
        "Conduct risk assessments proportionate to the level of risk posed "
        "by the AI system, considering potential harms.",
        "UK AI White Paper, Principle 1 — Risk Assessment",
        "RiskClassifier — automated risk classification with harm assessment",
        True,
    ),
    # PRO-2: Transparency and explainability
    (
        "UK PRO-2.1",
        "AI systems should be appropriately transparent and explainable, "
        "with the degree of transparency proportionate to the level of risk.",
        "UK AI White Paper, Principle 2 — Transparency",
        "TransparencyDisclosure — risk-proportionate system documentation",
        True,
    ),
    (
        "UK PRO-2.2",
        "Provide clear and meaningful explanations of AI-driven decisions "
        "to those affected, enabling them to understand the basis of decisions.",
        "UK AI White Paper, Principle 2 — Explainability",
        "TransparencyDisclosure — per-decision explanation with factors",
        True,
    ),
    (
        "UK PRO-2.3",
        "Make information about AI systems available to relevant regulators "
        "and oversight bodies in an accessible form.",
        "UK AI White Paper, Principle 2 — Regulatory Transparency",
        "AuditLog — auditable governance records for regulatory access",
        True,
    ),
    # PRO-3: Fairness
    (
        "UK PRO-3.1",
        "AI systems should not undermine the legal rights of individuals "
        "or organisations, create unfair market outcomes, or be used in "
        "a discriminatory way.",
        "UK AI White Paper, Principle 3 — Fairness",
        None,
        True,
    ),
    (
        "UK PRO-3.2",
        "Consider fairness throughout the AI lifecycle, including design, "
        "training data selection, deployment, and monitoring.",
        "UK AI White Paper, Principle 3 — Lifecycle Fairness",
        None,
        True,
    ),
    # PRO-4: Accountability and governance
    (
        "UK PRO-4.1",
        "Establish clear lines of accountability for AI outcomes, with "
        "appropriate governance measures for oversight and control.",
        "UK AI White Paper, Principle 4 — Accountability",
        "MACIEnforcer — separation-of-powers with clear role accountability",
        True,
    ),
    (
        "UK PRO-4.2",
        "Maintain records and documentation to demonstrate compliance with "
        "applicable regulatory requirements and governance measures.",
        "UK AI White Paper, Principle 4 — Documentation",
        "AuditLog — comprehensive compliance documentation",
        True,
    ),
    (
        "UK PRO-4.3",
        "Implement effective oversight mechanisms including regular review "
        "and monitoring of AI system performance and impacts.",
        "UK AI White Paper, Principle 4 — Oversight",
        "GovernanceEngine — continuous monitoring with real-time enforcement",
        True,
    ),
    # PRO-5: Contestability and redress
    (
        "UK PRO-5.1",
        "Ensure that affected parties can contest AI-driven decisions and "
        "seek appropriate redress through accessible processes.",
        "UK AI White Paper, Principle 5 — Contestability",
        "HumanOversightGateway — contestation and human review pathway",
        True,
    ),
    (
        "UK PRO-5.2",
        "Provide clear routes for individuals to challenge AI decisions "
        "and receive timely and meaningful responses.",
        "UK AI White Paper, Principle 5 — Redress",
        "HumanOversightGateway — structured challenge and review process",
        True,
    ),
]

_ACGS_LITE_MAP: dict[str, str] = {
    "UK PRO-1.1": (
        "acgs-lite GovernanceEngine — continuous safety validation through "
        "constitutional rules enforcement throughout lifecycle"
    ),
    "UK PRO-1.3": (
        "acgs-lite RiskClassifier — automated risk classification with "
        "harm potential assessment"
    ),
    "UK PRO-2.1": (
        "acgs-lite TransparencyDisclosure — generates risk-proportionate "
        "system documentation"
    ),
    "UK PRO-2.2": (
        "acgs-lite TransparencyDisclosure — per-decision explanation with "
        "contributing factors"
    ),
    "UK PRO-2.3": (
        "acgs-lite AuditLog — auditable tamper-evident records accessible "
        "to regulators"
    ),
    "UK PRO-4.1": (
        "acgs-lite MACIEnforcer — enforces separation of powers with clear "
        "accountability roles (proposer/validator/executor)"
    ),
    "UK PRO-4.2": (
        "acgs-lite AuditLog — comprehensive compliance documentation "
        "with cryptographic integrity"
    ),
    "UK PRO-4.3": (
        "acgs-lite GovernanceEngine — continuous real-time monitoring "
        "and enforcement of governance rules"
    ),
    "UK PRO-5.1": (
        "acgs-lite HumanOversightGateway — provides contestation and "
        "human review pathway for affected parties"
    ),
    "UK PRO-5.2": (
        "acgs-lite HumanOversightGateway — structured challenge and "
        "review process with audit trail"
    ),
}


class UKAIFramework:
    """UK AI Regulation Framework compliance assessor.

    Covers the five cross-sectoral principles: safety, transparency,
    fairness, accountability, and contestability.

    Status: Voluntary. Sector regulators apply principles to their domains.
    """

    framework_id: str = "uk_ai_framework"
    framework_name: str = "UK Pro-Innovation AI Regulation Framework"
    jurisdiction: str = "United Kingdom"
    status: str = "voluntary"
    enforcement_date: str | None = None

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
    fw: UKAIFramework, checklist: list[ChecklistItem],
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
            recs.append(f"{i.ref}: Address this UK AI framework principle.")
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
