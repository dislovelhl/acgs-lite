"""NIST AI Risk Management Framework (AI RMF 1.0) compliance module.

Implements the four core functions of the NIST AI RMF:
- GOVERN: Policies, roles, and organizational governance
- MAP: Context and risk identification
- MEASURE: Quantitative and qualitative assessment
- MANAGE: Risk treatment and monitoring

Reference: https://www.nist.gov/artificial-intelligence/ai-risk-management-framework
Published: January 2023 (NIST AI 100-1)

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

# NIST AI RMF 1.0 requirements organized by core function
_NIST_ITEMS: list[tuple[str, str, str, str | None, bool]] = [
    # GOVERN function — organizational policies and oversight
    (
        "GOVERN 1.1",
        "Establish policies for AI risk management aligned with organizational "
        "risk tolerance and applicable legal requirements.",
        "NIST AI 100-1, Section 3 (GOVERN)",
        "Constitution — defines organizational AI governance policies as code",
        True,
    ),
    (
        "GOVERN 1.2",
        "Define roles and responsibilities for AI risk management across "
        "the organization, including accountability structures.",
        "NIST AI 100-1, Section 3 (GOVERN)",
        "MACIEnforcer — enforces role separation (proposer/validator/executor)",
        True,
    ),
    (
        "GOVERN 1.3",
        "Establish processes for ongoing monitoring and periodic review "
        "of AI system risks throughout the lifecycle.",
        "NIST AI 100-1, Section 3 (GOVERN)",
        "GovernanceEngine — continuous validation on every agent action",
        True,
    ),
    (
        "GOVERN 1.4",
        "Maintain organizational AI inventory and documentation of AI "
        "systems, their purposes, and risk profiles.",
        "NIST AI 100-1, Section 3 (GOVERN)",
        None,
        False,
    ),
    # MAP function — context identification and risk framing
    (
        "MAP 1.1",
        "Identify and document the intended purpose, context of use, "
        "and intended users or affected populations for each AI system.",
        "NIST AI 100-1, Section 4 (MAP)",
        None,
        True,
    ),
    (
        "MAP 1.2",
        "Identify and assess potential risks including bias, fairness, "
        "safety, security, privacy, and environmental impacts.",
        "NIST AI 100-1, Section 4 (MAP)",
        "RiskClassifier — automated risk level classification",
        True,
    ),
    (
        "MAP 1.3",
        "Document assumptions, limitations, and known failure modes of "
        "the AI system, including conditions where it should not be used.",
        "NIST AI 100-1, Section 4 (MAP)",
        None,
        True,
    ),
    (
        "MAP 1.4",
        "Engage relevant stakeholders (including affected communities) "
        "in identifying risks and defining acceptable risk thresholds.",
        "NIST AI 100-1, Section 4 (MAP)",
        None,
        False,
    ),
    # MEASURE function — quantitative and qualitative assessment
    (
        "MEASURE 1.1",
        "Establish metrics and methods for evaluating AI system performance, "
        "including accuracy, fairness, reliability, and robustness metrics.",
        "NIST AI 100-1, Section 5 (MEASURE)",
        None,
        True,
    ),
    (
        "MEASURE 1.2",
        "Conduct regular testing, including bias testing, adversarial "
        "testing, and performance evaluation across demographic groups.",
        "NIST AI 100-1, Section 5 (MEASURE)",
        None,
        True,
    ),
    (
        "MEASURE 1.3",
        "Maintain audit trails of AI system decisions, inputs, outputs, "
        "and operational parameters for post-hoc analysis.",
        "NIST AI 100-1, Section 5 (MEASURE)",
        "AuditLog — tamper-evident cryptographic audit chain",
        True,
    ),
    (
        "MEASURE 1.4",
        "Monitor AI system performance in production and detect drift, "
        "degradation, or anomalous behavior over time.",
        "NIST AI 100-1, Section 5 (MEASURE)",
        None,
        False,
    ),
    # MANAGE function — risk treatment and response
    (
        "MANAGE 1.1",
        "Implement risk treatment actions proportionate to assessed risk "
        "levels, including human oversight for high-risk decisions.",
        "NIST AI 100-1, Section 6 (MANAGE)",
        "GovernanceEngine — severity-based blocking with escalation tiers",
        True,
    ),
    (
        "MANAGE 1.2",
        "Establish incident response procedures for AI system failures, "
        "including escalation paths and rollback capabilities.",
        "NIST AI 100-1, Section 6 (MANAGE)",
        None,
        True,
    ),
    (
        "MANAGE 1.3",
        "Provide mechanisms for affected individuals to contest or appeal "
        "AI-assisted decisions and obtain human review.",
        "NIST AI 100-1, Section 6 (MANAGE)",
        "HumanOversightGateway — configurable HITL approval gates",
        True,
    ),
    (
        "MANAGE 1.4",
        "Regularly update risk management practices based on new information, "
        "incidents, and evolving organizational and regulatory context.",
        "NIST AI 100-1, Section 6 (MANAGE)",
        None,
        False,
    ),
]

# acgs-lite auto-population map: ref -> evidence string
_ACGS_LITE_MAP: dict[str, str] = {
    "GOVERN 1.1": (
        "acgs-lite Constitution — governance policies defined as code with "
        "constitutional hash integrity verification"
    ),
    "GOVERN 1.2": (
        "acgs-lite MACIEnforcer — enforces proposer/validator/executor role "
        "separation (Multi-Agent Constitutional Integrity)"
    ),
    "GOVERN 1.3": (
        "acgs-lite GovernanceEngine — validates every agent action against "
        "constitutional rules in real time"
    ),
    "MAP 1.2": (
        "acgs-lite RiskClassifier — classifies system risk level and generates obligation mapping"
    ),
    "MEASURE 1.3": (
        "acgs-lite AuditLog — tamper-evident JSONL logging with SHA-256 cryptographic hash chaining"
    ),
    "MANAGE 1.1": (
        "acgs-lite GovernanceEngine — severity-based action blocking with "
        "configurable escalation tiers and workflow routing"
    ),
    "MANAGE 1.3": (
        "acgs-lite HumanOversightGateway — configurable human-in-the-loop "
        "approval gates with full audit trail"
    ),
}


class NISTAIRMFFramework:
    """NIST AI Risk Management Framework (AI RMF 1.0) compliance assessor.

    Implements the ComplianceFramework protocol for the NIST AI RMF,
    covering all four core functions (GOVERN, MAP, MEASURE, MANAGE)
    with 16 sub-function requirements.

    Status: Voluntary but widely adopted; referenced in US federal
    procurement (EO 14110) and state AI legislation.

    Usage::

        from acgs_lite.compliance.nist_ai_rmf import NISTAIRMFFramework

        framework = NISTAIRMFFramework()
        checklist = framework.get_checklist({"system_id": "my-system"})
        framework.auto_populate_acgs_lite(checklist)
        assessment = framework.assess({"system_id": "my-system"})
    """

    framework_id: str = "nist_ai_rmf"
    framework_name: str = "NIST AI Risk Management Framework (AI RMF 1.0)"
    jurisdiction: str = "United States"
    status: str = "voluntary"
    enforcement_date: str | None = None  # Voluntary framework

    def get_checklist(self, system_description: dict[str, Any]) -> list[ChecklistItem]:
        """Generate NIST AI RMF checklist items."""
        return [
            ChecklistItem(
                ref=ref,
                requirement=req,
                acgs_lite_feature=feature,
                blocking=blocking,
                legal_citation=citation,
            )
            for ref, req, citation, feature, blocking in _NIST_ITEMS
        ]

    def auto_populate_acgs_lite(self, checklist: list[ChecklistItem]) -> None:
        """Mark items that acgs-lite directly satisfies."""
        for item in checklist:
            if item.ref in _ACGS_LITE_MAP:
                item.mark_complete(_ACGS_LITE_MAP[item.ref])

    def assess(self, system_description: dict[str, Any]) -> FrameworkAssessment:
        """Run full NIST AI RMF assessment."""
        checklist = self.get_checklist(system_description)
        self.auto_populate_acgs_lite(checklist)
        return _build_assessment(self, checklist)


def _build_assessment(
    fw: NISTAIRMFFramework,
    checklist: list[ChecklistItem],
) -> FrameworkAssessment:
    """Shared assessment builder."""
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
    """Generate actionable recommendations for non-compliant items."""
    recs: list[str] = []
    for item in checklist:
        if item.status == ChecklistStatus.PENDING and item.blocking:
            if "MAP" in item.ref:
                recs.append(
                    f"{item.ref}: Document system context, risks, and "
                    f"stakeholder engagement per NIST AI RMF MAP function."
                )
            elif "MEASURE" in item.ref:
                recs.append(
                    f"{item.ref}: Establish metrics and testing procedures "
                    f"per NIST AI RMF MEASURE function."
                )
            elif "MANAGE" in item.ref:
                recs.append(
                    f"{item.ref}: Implement incident response and risk "
                    f"treatment per NIST AI RMF MANAGE function."
                )
    return tuple(recs)
