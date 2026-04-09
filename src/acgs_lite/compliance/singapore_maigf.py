"""Singapore Model AI Governance Framework v2 (MAIGF) compliance module.

Implements the four principles and twelve practices of Singapore's Model AI
Governance Framework, Second Edition (2020), published by the Personal Data
Protection Commission (PDPC) and Infocomm Media Development Authority (IMDA).

Principles and practices covered:
- P1 Internal Governance Structures and Measures
  P1.1 Establish internal governance structures and oversight
  P1.2 Define AI decision-making model (human vs. machine)
  P1.3 Ensure human oversight for significant decisions
- P2 Determining the Level of Human Involvement in AI-Augmented Decision-Making
  P2.1 Determine appropriate human involvement based on risk
  P2.2 Classify risk level using probability × impact framework
- P3 Operations Management
  P3.1 Ensure model robustness and reproducibility
  P3.2 Data governance for training and inference data
  P3.3 Vendor/third-party risk management
  P3.4 Establish incident and anomaly response procedures
- P4 Stakeholder Interaction and Communication
  P4.1 Communicate AI involvement to customers and users
  P4.2 Establish feedback, review, and redress mechanisms
  P4.3 Conduct human oversight for decisions disputed by customers

The MAIGF is a voluntary framework but is referenced in MAS (Monetary
Authority of Singapore) guidance, Singapore courts, and ASEAN AI governance
frameworks.

Reference: Personal Data Protection Commission Singapore — Model AI
Governance Framework, Second Edition (2020).

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

# ---------------------------------------------------------------------------
# Checklist: (ref, requirement, legal_citation, acgs_lite_feature, blocking)
# ---------------------------------------------------------------------------
_MAIGF_ITEMS: list[tuple[str, str, str, str | None, bool]] = [
    # Principle 1 — Internal Governance
    (
        "MAIGF P1.1(a)",
        "Establish clear roles and responsibilities for AI governance, "
        "including a designated senior accountable person (AI owner or "
        "equivalent) and defined escalation paths.",
        "PDPC MAIGF v2, Principle 1.1(a)",
        "MACIEnforcer — role separation (proposer/validator/executor) with accountability",
        True,
    ),
    (
        "MAIGF P1.1(b)",
        "Document AI governance policies covering model selection, testing, "
        "deployment, monitoring, and decommissioning, with board/senior "
        "management sign-off.",
        "PDPC MAIGF v2, Principle 1.1(b)",
        "Constitution — board-approved governance policies as version-controlled code",
        True,
    ),
    (
        "MAIGF P1.1(c)",
        "Conduct staff training on AI ethics, data governance, and the "
        "organisation's AI governance policies.",
        "PDPC MAIGF v2, Principle 1.1(c)",
        None,
        False,
    ),
    (
        "MAIGF P1.2",
        "Define and document how AI systems interact with human decision-makers: "
        "fully automated, human-in-the-loop (advisory), or human-on-the-loop "
        "(override-only) models.",
        "PDPC MAIGF v2, Principle 1.2",
        "HumanOversightGateway — configurable HITL/human-on-the-loop with documented modes",
        True,
    ),
    (
        "MAIGF P1.3",
        "For decisions that significantly affect individuals, ensure that a "
        "human with appropriate authority reviews AI output before action is "
        "taken or within a defined correction window.",
        "PDPC MAIGF v2, Principle 1.3",
        "HumanOversightGateway — mandatory human review gate for high-impact actions",
        True,
    ),
    # Principle 2 — Human Involvement in AI Decision-Making
    (
        "MAIGF P2.1",
        "Determine the appropriate degree of human involvement based on "
        "quantitative risk assessment: consider probability of error, impact "
        "on individuals, reversibility, and recourse available.",
        "PDPC MAIGF v2, Principle 2.1",
        "RiskClassifier — probability × impact scoring determines required oversight level",
        True,
    ),
    (
        "MAIGF P2.2(a)",
        "Classify the AI decision scenario into a risk level (high / medium / "
        "low) based on the product of decision error probability and impact "
        "severity on individuals.",
        "PDPC MAIGF v2, Principle 2.2(a)",
        "RiskClassifier — automated risk tier classification with configurable thresholds",
        True,
    ),
    (
        "MAIGF P2.2(b)",
        "Apply minimum human oversight requirements commensurate with risk "
        "level: high-risk decisions require human approval; medium-risk "
        "require human review within defined window.",
        "PDPC MAIGF v2, Principle 2.2(b)",
        "GovernanceEngine — severity-based escalation with configurable approval gates",
        True,
    ),
    # Principle 3 — Operations Management
    (
        "MAIGF P3.1(a)",
        "Test AI models for performance, accuracy, and fairness before "
        "deployment, including testing across demographic sub-groups where "
        "relevant.",
        "PDPC MAIGF v2, Principle 3.1(a)",
        None,
        True,
    ),
    (
        "MAIGF P3.1(b)",
        "Implement version control for AI models and training data to enable "
        "reproducibility and rollback to known-good states.",
        "PDPC MAIGF v2, Principle 3.1(b)",
        "AuditLog — versioned audit chain supports model lineage and rollback",
        True,
    ),
    (
        "MAIGF P3.1(c)",
        "Monitor AI model performance on an ongoing basis in production, "
        "including detecting drift, degradation, and changes in input data "
        "distributions.",
        "PDPC MAIGF v2, Principle 3.1(c)",
        "GovernanceEngine — continuous monitoring detects performance anomalies",
        True,
    ),
    (
        "MAIGF P3.2(a)",
        "Establish data governance practices covering data collection consent "
        "or legal basis, data quality, data lineage, and documentation of "
        "training data sources.",
        "PDPC MAIGF v2, Principle 3.2(a)",
        None,
        True,
    ),
    (
        "MAIGF P3.2(b)",
        "Implement data lifecycle management including secure deletion of "
        "training data when no longer needed and appropriate controls for "
        "personal data used in AI.",
        "PDPC MAIGF v2, Principle 3.2(b)",
        None,
        True,
    ),
    (
        "MAIGF P3.3",
        "Assess and manage risks from AI vendors and third-party models "
        "used in the system, including review of vendor governance practices "
        "and data handling.",
        "PDPC MAIGF v2, Principle 3.3",
        None,
        True,
    ),
    (
        "MAIGF P3.4",
        "Establish documented procedures for detecting, responding to, and "
        "recovering from AI system incidents, anomalies, and errors, with "
        "defined escalation paths.",
        "PDPC MAIGF v2, Principle 3.4",
        "GovernanceEngine — incident escalation with anomaly detection and audit trail",
        True,
    ),
    # Principle 4 — Stakeholder Interaction
    (
        "MAIGF P4.1(a)",
        "Inform customers and users that an AI system is involved in "
        "decisions that affect them, in plain language and in advance.",
        "PDPC MAIGF v2, Principle 4.1(a)",
        "TransparencyDisclosure — AI system identification and plain-language notice",
        True,
    ),
    (
        "MAIGF P4.1(b)",
        "Provide customers with meaningful information about the factors "
        "the AI system considers and how these influence the outcome, "
        "at the level of specificity appropriate to the risk.",
        "PDPC MAIGF v2, Principle 4.1(b)",
        "TransparencyDisclosure — system card with decision factors and logic",
        True,
    ),
    (
        "MAIGF P4.2",
        "Establish accessible feedback and complaint mechanisms for "
        "customers affected by AI decisions, with defined response "
        "and resolution timeframes.",
        "PDPC MAIGF v2, Principle 4.2",
        "HumanOversightGateway — contestation pathway with human review",
        True,
    ),
    (
        "MAIGF P4.3",
        "For decisions disputed by customers, ensure human review is "
        "available with authority to overturn AI-assisted decisions "
        "and correct any harm caused.",
        "PDPC MAIGF v2, Principle 4.3",
        "HumanOversightGateway — override controls with authority delegation",
        True,
    ),
]

# ---------------------------------------------------------------------------
# acgs-lite auto-population map
# ---------------------------------------------------------------------------
_ACGS_LITE_MAP: dict[str, str] = {
    "MAIGF P1.1(a)": (
        "acgs-lite MACIEnforcer — enforces proposer/validator/executor role "
        "separation with clear accountability and escalation paths"
    ),
    "MAIGF P1.1(b)": (
        "acgs-lite Constitution — version-controlled governance policies "
        "with hash integrity and audit trail"
    ),
    "MAIGF P1.2": (
        "acgs-lite HumanOversightGateway — configurable HITL and human-on-the-loop "
        "modes with documented decision flow"
    ),
    "MAIGF P1.3": (
        "acgs-lite HumanOversightGateway — mandatory human review gate for "
        "high-impact actions with authority delegation"
    ),
    "MAIGF P2.1": (
        "acgs-lite RiskClassifier — probability × impact scoring used to "
        "determine required oversight level"
    ),
    "MAIGF P2.2(a)": (
        "acgs-lite RiskClassifier — automated risk tier classification with "
        "configurable probability × impact thresholds"
    ),
    "MAIGF P2.2(b)": (
        "acgs-lite GovernanceEngine — severity-based escalation with "
        "configurable human approval gates by risk level"
    ),
    "MAIGF P3.1(b)": (
        "acgs-lite AuditLog — versioned audit chain with model lineage "
        "records supports reproducibility and rollback"
    ),
    "MAIGF P3.1(c)": (
        "acgs-lite GovernanceEngine — continuous monitoring detects "
        "performance anomalies and drift in production"
    ),
    "MAIGF P3.4": (
        "acgs-lite GovernanceEngine — incident escalation with anomaly "
        "detection, halt controls, and full audit trail"
    ),
    "MAIGF P4.1(a)": (
        "acgs-lite TransparencyDisclosure — AI system identification with "
        "plain-language notice in system card"
    ),
    "MAIGF P4.1(b)": (
        "acgs-lite TransparencyDisclosure — system card includes decision "
        "factors and logic explanation at appropriate specificity"
    ),
    "MAIGF P4.2": (
        "acgs-lite HumanOversightGateway — contestation pathway and "
        "human review channel with defined response flow"
    ),
    "MAIGF P4.3": (
        "acgs-lite HumanOversightGateway — override controls with authority "
        "delegation enable overturn of disputed AI decisions"
    ),
}


class SingaporeMAIGFFramework:
    """Singapore Model AI Governance Framework v2 (MAIGF) compliance assessor.

    Covers internal governance, risk-proportionate human oversight,
    operations management, and stakeholder communication across all
    four MAIGF principles (P1-P4).

    Status: Voluntary framework; referenced in MAS guidance and ASEAN
    regional AI governance network.

    Usage::

        from acgs_lite.compliance.singapore_maigf import SingaporeMAIGFFramework

        framework = SingaporeMAIGFFramework()
        assessment = framework.assess({
            "system_id": "my-system",
            "jurisdiction": "singapore",
        })
    """

    framework_id: str = "singapore_maigf"
    framework_name: str = "Singapore Model AI Governance Framework v2 (MAIGF)"
    jurisdiction: str = "Singapore"
    status: str = "voluntary"
    enforcement_date: str | None = None

    def get_checklist(self, system_description: dict[str, Any]) -> list[ChecklistItem]:
        """Generate Singapore MAIGF checklist items."""
        return [
            ChecklistItem(
                ref=ref,
                requirement=req,
                acgs_lite_feature=feature,
                blocking=blocking,
                legal_citation=citation,
            )
            for ref, req, citation, feature, blocking in _MAIGF_ITEMS
        ]

    def auto_populate_acgs_lite(self, checklist: list[ChecklistItem]) -> None:
        """Mark items that acgs-lite directly satisfies."""
        for item in checklist:
            if item.ref in _ACGS_LITE_MAP:
                item.mark_complete(_ACGS_LITE_MAP[item.ref])

    def assess(self, system_description: dict[str, Any]) -> FrameworkAssessment:
        """Run full Singapore MAIGF compliance assessment."""
        checklist = self.get_checklist(system_description)
        self.auto_populate_acgs_lite(checklist)
        return _build_assessment(self, checklist)


def _build_assessment(
    fw: SingaporeMAIGFFramework,
    checklist: list[ChecklistItem],
) -> FrameworkAssessment:
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
    recommendations = _generate_recommendations(checklist)
    return FrameworkAssessment(
        framework_id=fw.framework_id,
        framework_name=fw.framework_name,
        compliance_score=round(compliant / total, 4) if total else 1.0,
        items=tuple(item.to_dict() for item in checklist),
        gaps=gaps,
        acgs_lite_coverage=round(acgs_covered / total, 4) if total else 0.0,
        recommendations=recommendations,
        assessed_at=datetime.now(UTC).isoformat(),
    )


def _generate_recommendations(checklist: list[ChecklistItem]) -> tuple[str, ...]:
    recs: list[str] = []
    for item in checklist:
        if item.status == ChecklistStatus.PENDING and item.blocking:
            if "P1" in item.ref:
                recs.append(
                    f"{item.ref}: Establish internal governance structures "
                    f"and document AI policies per MAIGF Principle 1."
                )
            elif "P2" in item.ref:
                recs.append(
                    f"{item.ref}: Conduct risk classification and define "
                    f"human oversight requirements per MAIGF Principle 2."
                )
            elif "P3" in item.ref:
                recs.append(
                    f"{item.ref}: Implement operational controls including "
                    f"testing, data governance, and incident response per MAIGF P3."
                )
            elif "P4" in item.ref:
                recs.append(
                    f"{item.ref}: Establish stakeholder communication and "
                    f"feedback mechanisms per MAIGF Principle 4."
                )
    return tuple(recs)
