"""SOC 2 Type II + AI Controls compliance module.

Implements the AICPA Trust Service Criteria with AI-specific control
extensions covering model governance, data lineage, bias testing,
and explainability.

Reference: AICPA Trust Services Criteria (TSC) 2017 + AI Addendum
SOC 2 Type II examinations cover operating effectiveness over a period.

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

_SOC2_ITEMS: list[tuple[str, str, str, str | None, bool]] = [
    # Security (Common Criteria)
    (
        "CC6.1",
        "Implement logical and physical access controls to protect information "
        "assets, including AI model artifacts and training data, against "
        "unauthorized access.",
        "TSC CC6.1 — Logical and Physical Access Controls",
        "GovernanceEngine — action-level access control via constitutional rules",
        True,
    ),
    (
        "CC6.3",
        "Implement role-based access controls to restrict system access to "
        "authorized personnel based on the principle of least privilege.",
        "TSC CC6.3 — Role-Based Access",
        "MACIEnforcer — role-based separation of proposer/validator/executor",
        True,
    ),
    (
        "CC7.2",
        "Monitor system components for anomalies indicative of malicious "
        "acts, natural disasters, and errors, including AI model drift.",
        "TSC CC7.2 — System Monitoring",
        "GovernanceMetrics — real-time monitoring of governance decisions",
        True,
    ),
    (
        "CC8.1",
        "Implement change management controls to authorize, document, and "
        "track changes to system components including AI models.",
        "TSC CC8.1 — Change Management",
        "Constitution — hash-verified change tracking with diff capability",
        True,
    ),
    # Availability
    (
        "A1.2",
        "Establish recovery objectives and implement backup and recovery "
        "procedures for AI system components and model artifacts.",
        "TSC A1.2 — Recovery Procedures",
        None,
        False,
    ),
    # Processing Integrity
    (
        "PI1.1",
        "Define processing integrity objectives for AI system outputs and "
        "validate that processing is complete, valid, accurate, and timely.",
        "TSC PI1.1 — Processing Integrity Objectives",
        "GovernanceEngine — validates processing against constitutional rules",
        True,
    ),
    (
        "PI1.3",
        "Implement error detection and correction mechanisms for AI system "
        "outputs, including confidence thresholds and escalation procedures.",
        "TSC PI1.3 — Error Detection and Correction",
        "GovernanceEngine — severity-based blocking with escalation tiers",
        True,
    ),
    # Confidentiality
    (
        "C1.1",
        "Identify and classify confidential information processed by AI "
        "systems, including training data, model weights, and inference "
        "inputs/outputs.",
        "TSC C1.1 — Confidential Information Classification",
        None,
        True,
    ),
    (
        "C1.2",
        "Dispose of confidential information in accordance with retention "
        "policies, including purging training data and model artifacts.",
        "TSC C1.2 — Confidential Information Disposal",
        None,
        False,
    ),
    # Privacy
    (
        "P6.1",
        "Provide data subjects with notice about the collection and use of "
        "personal information by AI systems, including profiling activities.",
        "TSC P6.1 — Privacy Notice",
        "TransparencyDisclosure — system card with data use documentation",
        True,
    ),
    # AI-Specific Controls
    (
        "AI-GOV.1",
        "Establish an AI model governance framework covering model development, "
        "validation, deployment, and retirement lifecycle stages.",
        "SOC 2 AI Addendum — Model Governance",
        "Constitution + GovernanceEngine — policy-as-code model governance",
        True,
    ),
    (
        "AI-GOV.2",
        "Maintain model inventory documenting all AI/ML models in production "
        "with version, purpose, owner, risk level, and validation status.",
        "SOC 2 AI Addendum — Model Inventory",
        None,
        True,
    ),
    (
        "AI-DATA.1",
        "Implement data lineage tracking for AI training data, including "
        "provenance, transformations, and quality assessments.",
        "SOC 2 AI Addendum — Data Lineage",
        None,
        True,
    ),
    (
        "AI-BIAS.1",
        "Conduct regular bias testing across protected demographic groups "
        "and document results with remediation actions taken.",
        "SOC 2 AI Addendum — Bias Testing",
        None,
        True,
    ),
    (
        "AI-EXPLAIN.1",
        "Provide explanations for AI-assisted decisions commensurate with "
        "the impact on individuals, supporting human oversight and appeals.",
        "SOC 2 AI Addendum — Explainability",
        "HumanOversightGateway — decision explanation with HITL review",
        True,
    ),
    (
        "AI-AUDIT.1",
        "Maintain tamper-evident audit trails of all AI system decisions, "
        "model changes, and governance actions with sufficient retention.",
        "SOC 2 AI Addendum — AI Audit Trail",
        "AuditLog — SHA-256 chained audit trail with tamper detection",
        True,
    ),
]

_ACGS_LITE_MAP: dict[str, str] = {
    "CC6.1": (
        "acgs-lite GovernanceEngine — constitutional rules enforce action-level "
        "access control with severity-based blocking"
    ),
    "CC6.3": (
        "acgs-lite MACIEnforcer — role-based separation of duties across "
        "proposer, validator, and executor roles"
    ),
    "CC7.2": (
        "acgs-lite GovernanceMetrics — real-time monitoring of allow/deny/"
        "escalate rates, rule hit frequencies, latency percentiles"
    ),
    "CC8.1": (
        "acgs-lite Constitution — hash-verified policy versioning with "
        "structured diff tracking for change management"
    ),
    "PI1.1": (
        "acgs-lite GovernanceEngine — validates every agent action against "
        "constitutional rules ensuring processing integrity"
    ),
    "PI1.3": (
        "acgs-lite GovernanceEngine — severity-based blocking (critical/high) "
        "with workflow routing and escalation to human reviewers"
    ),
    "P6.1": (
        "acgs-lite TransparencyDisclosure — Article 13 compliant system card "
        "documenting data collection and processing purposes"
    ),
    "AI-GOV.1": (
        "acgs-lite Constitution + GovernanceEngine — governance policies as "
        "executable code covering the full AI model lifecycle"
    ),
    "AI-EXPLAIN.1": (
        "acgs-lite HumanOversightGateway — human review gates with decision "
        "explanation and contestation support"
    ),
    "AI-AUDIT.1": (
        "acgs-lite AuditLog — tamper-evident SHA-256 chained audit trail "
        "with verify_chain() integrity checks"
    ),
}


class SOC2AIFramework:
    """SOC 2 Type II + AI Controls compliance assessor.

    Covers the five Trust Service Criteria (Security, Availability,
    Processing Integrity, Confidentiality, Privacy) extended with
    AI-specific controls for model governance, data lineage, bias
    testing, and explainability.

    Status: Voluntary but required by many enterprise buyers as a
    procurement prerequisite. Examinations conducted by licensed CPAs.

    Usage::

        from acgs_lite.compliance.soc2_ai import SOC2AIFramework

        framework = SOC2AIFramework()
        assessment = framework.assess({"system_id": "my-system"})
    """

    framework_id: str = "soc2_ai"
    framework_name: str = "SOC 2 Type II + AI Controls"
    jurisdiction: str = "United States"
    status: str = "voluntary"
    enforcement_date: str | None = None

    def get_checklist(self, system_description: dict[str, Any]) -> list[ChecklistItem]:
        """Generate SOC 2 + AI checklist items."""
        return [
            ChecklistItem(
                ref=ref,
                requirement=req,
                acgs_lite_feature=feature,
                blocking=blocking,
                legal_citation=citation,
            )
            for ref, req, citation, feature, blocking in _SOC2_ITEMS
        ]

    def auto_populate_acgs_lite(self, checklist: list[ChecklistItem]) -> None:
        """Mark items that acgs-lite directly satisfies."""
        for item in checklist:
            if item.ref in _ACGS_LITE_MAP:
                item.mark_complete(_ACGS_LITE_MAP[item.ref])

    def assess(self, system_description: dict[str, Any]) -> FrameworkAssessment:
        """Run full SOC 2 + AI assessment."""
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
                recs.append(f"{item.ref}: Address for SOC 2 Type II examination readiness.")

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
