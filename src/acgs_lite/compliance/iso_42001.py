"""ISO/IEC 42001:2023 AI Management System compliance module.

Implements clauses 4-10 and Annex A controls of ISO/IEC 42001:2023,
the first international standard for AI management systems.

Reference: ISO/IEC 42001:2023 — Information technology — Artificial
intelligence — Management system
Published: December 2023

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

# ISO 42001 requirements: clauses 4-10 + Annex A controls
_ISO_ITEMS: list[tuple[str, str, str, str | None, bool]] = [
    # Clause 4: Context of the organization
    (
        "ISO 4.1",
        "Determine external and internal issues relevant to the organization's "
        "purpose that affect AI management system outcomes.",
        "ISO/IEC 42001:2023, Clause 4.1",
        None,
        True,
    ),
    (
        "ISO 4.2",
        "Determine interested parties and their requirements relevant to "
        "the AI management system, including regulatory obligations.",
        "ISO/IEC 42001:2023, Clause 4.2",
        None,
        True,
    ),
    # Clause 5: Leadership
    (
        "ISO 5.1",
        "Top management shall demonstrate leadership and commitment to the "
        "AI management system, including establishing AI policy.",
        "ISO/IEC 42001:2023, Clause 5.1",
        "Constitution — AI governance policy defined as executable code",
        True,
    ),
    (
        "ISO 5.2",
        "Establish an AI policy appropriate to the organization that includes "
        "commitment to applicable requirements and continual improvement.",
        "ISO/IEC 42001:2023, Clause 5.2",
        "Constitution — version-controlled policy with hash integrity",
        True,
    ),
    (
        "ISO 5.3",
        "Assign roles, responsibilities, and authorities for the AI management "
        "system, ensuring separation of duties where appropriate.",
        "ISO/IEC 42001:2023, Clause 5.3",
        "MACIEnforcer — proposer/validator/executor role separation",
        True,
    ),
    # Clause 6: Planning
    (
        "ISO 6.1",
        "Determine risks and opportunities related to AI systems that need "
        "to be addressed, including impact assessments.",
        "ISO/IEC 42001:2023, Clause 6.1",
        "RiskClassifier — automated risk classification and obligation mapping",
        True,
    ),
    (
        "ISO 6.2",
        "Establish AI management system objectives that are measurable, "
        "monitored, and consistent with the AI policy.",
        "ISO/IEC 42001:2023, Clause 6.2",
        None,
        True,
    ),
    # Clause 7: Support
    (
        "ISO 7.1",
        "Determine and provide resources needed for the establishment, "
        "implementation, maintenance, and improvement of the AI management system.",
        "ISO/IEC 42001:2023, Clause 7.1",
        None,
        False,
    ),
    (
        "ISO 7.5",
        "Maintain documented information required by the AI management system "
        "and retain evidence of conformity.",
        "ISO/IEC 42001:2023, Clause 7.5",
        "AuditLog — tamper-evident documented records with cryptographic integrity",
        True,
    ),
    # Clause 8: Operation
    (
        "ISO 8.1",
        "Plan, implement, and control processes needed to meet AI management "
        "system requirements, including operational controls for AI systems.",
        "ISO/IEC 42001:2023, Clause 8.1",
        "GovernanceEngine — real-time operational control on agent actions",
        True,
    ),
    (
        "ISO 8.2",
        "Conduct AI risk assessment at planned intervals or when significant "
        "changes occur, maintaining records of results.",
        "ISO/IEC 42001:2023, Clause 8.2",
        None,
        True,
    ),
    # Clause 9: Performance evaluation
    (
        "ISO 9.1",
        "Monitor, measure, analyse, and evaluate AI management system "
        "performance, including AI system outputs and impacts.",
        "ISO/IEC 42001:2023, Clause 9.1",
        "GovernanceMetrics — real-time governance performance monitoring",
        True,
    ),
    (
        "ISO 9.2",
        "Conduct internal audits at planned intervals to provide information "
        "on whether the AI management system conforms to requirements.",
        "ISO/IEC 42001:2023, Clause 9.2",
        "AuditLog — audit trail with chain integrity verification",
        True,
    ),
    # Clause 10: Improvement
    (
        "ISO 10.1",
        "Determine opportunities for improvement and implement necessary "
        "changes to the AI management system.",
        "ISO/IEC 42001:2023, Clause 10.1",
        None,
        False,
    ),
    # Annex A controls
    (
        "ISO A.4.2",
        "AI impact assessment: assess the potential impacts of AI systems "
        "on individuals, groups, and society before deployment.",
        "ISO/IEC 42001:2023, Annex A, A.4.2",
        "RiskClassifier — pre-deployment impact classification",
        True,
    ),
    (
        "ISO A.6.2",
        "AI system lifecycle processes: implement processes across the AI "
        "system lifecycle from design through retirement.",
        "ISO/IEC 42001:2023, Annex A, A.6.2",
        None,
        True,
    ),
    (
        "ISO A.8.3",
        "Data management: manage data used in AI systems including data "
        "quality, provenance, and bias assessment.",
        "ISO/IEC 42001:2023, Annex A, A.8.3",
        None,
        True,
    ),
    (
        "ISO A.10.4",
        "Third-party and supplier management: manage risks from third-party "
        "AI components, models, and data sources.",
        "ISO/IEC 42001:2023, Annex A, A.10.4",
        None,
        False,
    ),
]

_ACGS_LITE_MAP: dict[str, str] = {
    "ISO 5.1": (
        "acgs-lite Constitution — AI governance policy defined as executable "
        "code with constitutional hash integrity (608508a9bd224290)"
    ),
    "ISO 5.2": (
        "acgs-lite Constitution — version-controlled governance policy with "
        "cryptographic hash verification and diff tracking"
    ),
    "ISO 5.3": (
        "acgs-lite MACIEnforcer — enforces separation of duties across "
        "proposer, validator, and executor roles"
    ),
    "ISO 6.1": (
        "acgs-lite RiskClassifier — automated risk classification producing "
        "obligation mapping per risk tier"
    ),
    "ISO 7.5": (
        "acgs-lite AuditLog — tamper-evident cryptographic hash chain for "
        "documented information retention"
    ),
    "ISO 8.1": (
        "acgs-lite GovernanceEngine — operational control validating every "
        "agent action against constitutional rules in real time"
    ),
    "ISO 9.1": (
        "acgs-lite GovernanceMetrics — allow/deny/escalate tracking with "
        "latency percentiles and rule hit frequencies"
    ),
    "ISO 9.2": (
        "acgs-lite AuditLog — audit trail with verify_chain() for internal "
        "audit conformity evidence"
    ),
    "ISO A.4.2": (
        "acgs-lite RiskClassifier — pre-deployment AI impact classification "
        "across risk tiers with obligation generation"
    ),
}


class ISO42001Framework:
    """ISO/IEC 42001:2023 AI Management System compliance assessor.

    Covers clauses 4-10 (management system requirements) and Annex A
    controls (AI-specific controls). Certification is available through
    accredited certification bodies.

    Status: Enacted (published December 2023). Certification available.

    Usage::

        from acgs_lite.compliance.iso_42001 import ISO42001Framework

        framework = ISO42001Framework()
        assessment = framework.assess({"system_id": "my-system"})
    """

    framework_id: str = "iso_42001"
    framework_name: str = "ISO/IEC 42001:2023 AI Management System"
    jurisdiction: str = "International"
    status: str = "enacted"
    enforcement_date: str | None = "2023-12-18"

    def get_checklist(self, system_description: dict[str, Any]) -> list[ChecklistItem]:
        """Generate ISO 42001 checklist items."""
        return [
            ChecklistItem(
                ref=ref,
                requirement=req,
                acgs_lite_feature=feature,
                blocking=blocking,
                legal_citation=citation,
            )
            for ref, req, citation, feature, blocking in _ISO_ITEMS
        ]

    def auto_populate_acgs_lite(self, checklist: list[ChecklistItem]) -> None:
        """Mark items that acgs-lite directly satisfies."""
        for item in checklist:
            if item.ref in _ACGS_LITE_MAP:
                item.mark_complete(_ACGS_LITE_MAP[item.ref])

    def assess(self, system_description: dict[str, Any]) -> FrameworkAssessment:
        """Run full ISO 42001 assessment."""
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
                recs.append(f"{item.ref}: Address this requirement for ISO 42001 certification.")

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
