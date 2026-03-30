"""Australia AI Ethics Framework compliance module.

Implements Australia's voluntary AI Ethics Principles (2019):
1. Human, societal, and environmental wellbeing
2. Human-centred values
3. Fairness
4. Privacy protection and security
5. Reliability and safety
6. Transparency and explainability
7. Contestability
8. Accountability

Reference: Australian Government — Australia's AI Ethics Principles
    (Department of Industry, Science and Resources, November 2019)
Status: voluntary
Enforcement: N/A (voluntary framework)
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
    # 1. Human, societal, and environmental wellbeing
    (
        "AU-AI P1.1",
        "Throughout the AI lifecycle, assess and address the broader societal "
        "impacts and ensure AI systems benefit individuals, society, and "
        "the environment.",
        "AU AI Ethics Principles, Principle 1",
        None,
        True,
    ),
    # 2. Human-centred values
    (
        "AU-AI P2.1",
        "AI systems should respect human rights, diversity, and the autonomy "
        "of individuals, including respecting people's right to make their "
        "own decisions.",
        "AU AI Ethics Principles, Principle 2",
        "HumanOversightGateway — preserves human autonomy in decisions",
        True,
    ),
    (
        "AU-AI P2.2",
        "AI systems should be designed to augment, complement, and empower "
        "human cognitive, social, and cultural skills.",
        "AU AI Ethics Principles, Principle 2",
        None,
        False,
    ),
    # 3. Fairness
    (
        "AU-AI P3.1",
        "AI systems should be inclusive and accessible, not involve or "
        "result in unfair discrimination against individuals, communities, "
        "or groups.",
        "AU AI Ethics Principles, Principle 3",
        None,
        True,
    ),
    (
        "AU-AI P3.2",
        "Assess and mitigate potential biases in AI systems throughout "
        "the design, development, and deployment lifecycle.",
        "AU AI Ethics Principles, Principle 3 — Bias Mitigation",
        None,
        True,
    ),
    # 4. Privacy protection and security
    (
        "AU-AI P4.1",
        "AI systems should respect and uphold privacy rights and data "
        "protection, with data handled securely and with appropriate "
        "governance.",
        "AU AI Ethics Principles, Principle 4",
        "GovernanceEngine — data governance via constitutional rules",
        True,
    ),
    # 5. Reliability and safety
    (
        "AU-AI P5.1",
        "AI systems should reliably operate in accordance with their "
        "intended purpose throughout their lifecycle.",
        "AU AI Ethics Principles, Principle 5 — Reliability",
        None,
        True,
    ),
    (
        "AU-AI P5.2",
        "Implement robust testing, monitoring, and risk management processes "
        "to ensure AI system safety.",
        "AU AI Ethics Principles, Principle 5 — Safety",
        "RiskClassifier — automated risk assessment for safety",
        True,
    ),
    # 6. Transparency and explainability
    (
        "AU-AI P6.1",
        "There should be transparency and responsible disclosure to ensure "
        "people know when they are being significantly impacted by AI and "
        "can find out when AI is being used.",
        "AU AI Ethics Principles, Principle 6 — Transparency",
        "TransparencyDisclosure — AI usage disclosure",
        True,
    ),
    (
        "AU-AI P6.2",
        "Enable people to understand the output of AI systems and provide "
        "meaningful explanations of how decisions are made.",
        "AU AI Ethics Principles, Principle 6 — Explainability",
        "TransparencyDisclosure — decision explanation generation",
        True,
    ),
    # 7. Contestability
    (
        "AU-AI P7.1",
        "When an AI system significantly impacts a person, community, group "
        "or environment, there should be a timely process to allow people "
        "to challenge the use or output.",
        "AU AI Ethics Principles, Principle 7",
        "HumanOversightGateway — contestation and human review pathway",
        True,
    ),
    # 8. Accountability
    (
        "AU-AI P8.1",
        "Those responsible for AI systems should be identifiable and "
        "accountable for the outcomes, including during design, development, "
        "and deployment.",
        "AU AI Ethics Principles, Principle 8 — Accountability",
        "MACIEnforcer — clear accountability through role separation",
        True,
    ),
    (
        "AU-AI P8.2",
        "Maintain audit trails and records to enable third-party review "
        "and oversight of AI system decisions.",
        "AU AI Ethics Principles, Principle 8 — Auditability",
        "AuditLog — tamper-evident audit trail for third-party review",
        True,
    ),
]

_ACGS_LITE_MAP: dict[str, str] = {
    "AU-AI P2.1": (
        "acgs-lite HumanOversightGateway — preserves human autonomy "
        "through configurable HITL gates"
    ),
    "AU-AI P4.1": (
        "acgs-lite GovernanceEngine — data governance enforcement "
        "via constitutional rules"
    ),
    "AU-AI P5.2": (
        "acgs-lite RiskClassifier — automated risk assessment supporting "
        "safety verification"
    ),
    "AU-AI P6.1": (
        "acgs-lite TransparencyDisclosure — generates AI usage disclosure "
        "documents"
    ),
    "AU-AI P6.2": (
        "acgs-lite TransparencyDisclosure — meaningful decision explanation "
        "generation"
    ),
    "AU-AI P7.1": (
        "acgs-lite HumanOversightGateway — contestation and human review "
        "pathway for affected parties"
    ),
    "AU-AI P8.1": (
        "acgs-lite MACIEnforcer — clear accountability through enforced "
        "role separation (proposer/validator/executor)"
    ),
    "AU-AI P8.2": (
        "acgs-lite AuditLog — tamper-evident JSONL audit trail with "
        "SHA-256 hash chain for third-party review"
    ),
}


class AustraliaAIEthicsFramework:
    """Australia AI Ethics Principles compliance assessor.

    Covers eight principles: wellbeing, human-centred values, fairness,
    privacy, reliability, transparency, contestability, and accountability.

    Status: Voluntary. Widely referenced in Australian government AI procurement.
    """

    framework_id: str = "australia_ai_ethics"
    framework_name: str = "Australia AI Ethics Principles"
    jurisdiction: str = "Australia"
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
    fw: AustraliaAIEthicsFramework, checklist: list[ChecklistItem],
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
            recs.append(f"{i.ref}: Implement this Australian AI Ethics principle.")
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
