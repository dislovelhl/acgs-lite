"""Singapore Model AI Governance Framework (MAIGF) compliance module.

Implements Singapore's MAIGF (2nd edition, 2020) principles for
responsible AI deployment in ASEAN:
- Principle 1: Internal governance (accountability, oversight)
- Principle 2: Decision-making transparency and explainability
- Principle 3: Operations management (data, robustness, monitoring)
- Principle 4: Stakeholder interaction and communication

Reference: Singapore IMDA — Model Artificial Intelligence Governance
    Framework (2nd Edition, January 2020)
Status: voluntary
Enforcement: N/A (voluntary framework, widely adopted in ASEAN)
Penalties: N/A

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
    # Principle 1: Internal governance structures and measures
    (
        "MAIGF P1.1(a)",
        "Establish clear internal governance structures with defined roles "
        "and responsibilities for AI development and deployment, including "
        "accountability for AI-driven decisions.",
        "MAIGF 2nd Ed., §2.1 — Internal Governance",
        "MACIEnforcer — enforces role separation (proposer/validator/executor)",
        True,
    ),
    (
        "MAIGF P1.1(b)",
        "Implement risk management processes to assess and address the risks "
        "of AI systems, proportionate to the potential impact.",
        "MAIGF 2nd Ed., §2.1 — Risk Management",
        "RiskClassifier — automated risk classification",
        True,
    ),
    (
        "MAIGF P1.2",
        "Adopt a risk assessment framework to determine the level of human "
        "involvement in AI-augmented decision-making based on the severity "
        "and probability of harm.",
        "MAIGF 2nd Ed., §2.2 — Risk Assessment",
        "RiskClassifier — risk tier assessment with human oversight mapping",
        True,
    ),
    (
        "MAIGF P1.3",
        "Implement human-over-the-loop, human-in-the-loop, or human-in-command "
        "oversight proportionate to the risk level of AI decisions.",
        "MAIGF 2nd Ed., §2.3 — Human Oversight",
        "HumanOversightGateway — configurable HITL gates",
        True,
    ),
    # Principle 2: Decision-making transparency and explainability
    (
        "MAIGF P2.1",
        "Provide meaningful explanations of how AI systems make decisions or "
        "predictions, appropriate to the context and audience.",
        "MAIGF 2nd Ed., §3.1 — Explainability",
        "TransparencyDisclosure — system cards with logic explanation",
        True,
    ),
    (
        "MAIGF P2.2",
        "Make available to affected individuals the factors that led to an "
        "AI-driven decision, in a clear and accessible manner.",
        "MAIGF 2nd Ed., §3.2 — Transparency to Individuals",
        "TransparencyDisclosure — per-decision disclosure",
        True,
    ),
    (
        "MAIGF P2.3",
        "Ensure that explanations are provided in a form and language that "
        "the target audience can understand.",
        "MAIGF 2nd Ed., §3.3 — Accessible Communication",
        None,
        False,
    ),
    # Principle 3: Operations management
    (
        "MAIGF P3.1",
        "Implement data management practices that ensure data quality, "
        "relevance, and representativeness for AI training and operations.",
        "MAIGF 2nd Ed., §4.1 — Data Management",
        None,
        True,
    ),
    (
        "MAIGF P3.2",
        "Ensure AI models are robust and reliable through appropriate testing, "
        "validation, and monitoring throughout the lifecycle.",
        "MAIGF 2nd Ed., §4.2 — Model Robustness",
        None,
        True,
    ),
    (
        "MAIGF P3.3",
        "Monitor AI systems in production for performance degradation, drift, "
        "and unintended behaviours, with remediation processes in place.",
        "MAIGF 2nd Ed., §4.3 — Monitoring",
        "AuditLog — continuous event logging for drift detection",
        True,
    ),
    (
        "MAIGF P3.4",
        "Maintain audit trails of AI system operations and decisions to "
        "support accountability and post-hoc review.",
        "MAIGF 2nd Ed., §4.4 — Audit Trails",
        "AuditLog — tamper-evident cryptographic audit chain",
        True,
    ),
    # Principle 4: Stakeholder interaction and communication
    (
        "MAIGF P4.1",
        "Engage with stakeholders including affected communities to understand "
        "concerns and incorporate feedback into AI governance.",
        "MAIGF 2nd Ed., §5.1 — Stakeholder Engagement",
        None,
        False,
    ),
    (
        "MAIGF P4.2",
        "Provide accessible channels for individuals to raise concerns, "
        "seek redress, or contest AI-driven decisions.",
        "MAIGF 2nd Ed., §5.2 — Redress Mechanisms",
        "HumanOversightGateway — contestation and human review pathway",
        True,
    ),
]

_ACGS_LITE_MAP: dict[str, str] = {
    "MAIGF P1.1(a)": (
        "acgs-lite MACIEnforcer — enforces proposer/validator/executor role "
        "separation for AI governance accountability"
    ),
    "MAIGF P1.1(b)": (
        "acgs-lite RiskClassifier — automated risk assessment proportionate "
        "to potential impact"
    ),
    "MAIGF P1.2": (
        "acgs-lite RiskClassifier — risk tier assessment determining "
        "required human oversight level"
    ),
    "MAIGF P1.3": (
        "acgs-lite HumanOversightGateway — configurable HITL, HOTL, and "
        "HIC oversight modes"
    ),
    "MAIGF P2.1": (
        "acgs-lite TransparencyDisclosure — generates machine-readable "
        "system cards with decision logic explanation"
    ),
    "MAIGF P2.2": (
        "acgs-lite TransparencyDisclosure — per-decision factor disclosure "
        "for affected individuals"
    ),
    "MAIGF P3.3": (
        "acgs-lite AuditLog — continuous JSONL event logging for "
        "production monitoring and drift detection"
    ),
    "MAIGF P3.4": (
        "acgs-lite AuditLog — SHA-256 hash chain audit trail supporting "
        "accountability and post-hoc review"
    ),
    "MAIGF P4.2": (
        "acgs-lite HumanOversightGateway — provides contestation and "
        "human review pathway for redress"
    ),
}


class SingaporeMAIGFFramework:
    """Singapore MAIGF (Model AI Governance Framework) compliance assessor.

    Covers the four principles: internal governance, transparency and
    explainability, operations management, and stakeholder interaction.

    Status: Voluntary. Widely adopted in Singapore and ASEAN.
    """

    framework_id: str = "singapore_maigf"
    framework_name: str = "Singapore Model AI Governance Framework (MAIGF)"
    jurisdiction: str = "Singapore"
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
    fw: SingaporeMAIGFFramework, checklist: list[ChecklistItem],
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
            recs.append(f"{i.ref}: Implement this MAIGF recommendation for AI governance.")
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
