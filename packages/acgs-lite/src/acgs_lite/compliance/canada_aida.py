"""Canada Artificial Intelligence and Data Act (AIDA) compliance module.

Implements AIDA (Part 3 of Bill C-27) requirements for high-impact AI
systems in Canada:
- Responsible AI measures (§§5-7)
- Assessment and mitigation (§§8-9)
- Transparency and explanation (§§10-11)
- Record-keeping and registration (§§12-14)

Reference: Bill C-27, Part 3 — Artificial Intelligence and Data Act
Status: proposed (passed House; pending Senate as of 2024)
Enforcement: TBD upon Royal Assent + regulation
Penalties: Up to CAD 10 million or 3% of gross global revenue for
    non-compliance; CAD 25 million or 5% for reckless/knowing harm

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
    (
        "AIDA §5(1)",
        "Persons responsible for a high-impact AI system must establish "
        "measures to identify, assess, and mitigate risks of harm or "
        "biased output.",
        "AIDA §5(1)",
        "GovernanceEngine — constitutional rules as risk mitigation measures",
        True,
    ),
    (
        "AIDA §6(1)",
        "Assess whether an AI system is a high-impact system, considering "
        "prescribed criteria including potential for harm.",
        "AIDA §6(1)",
        "RiskClassifier — automated high-impact classification",
        True,
    ),
    (
        "AIDA §7(1)",
        "Establish measures to monitor compliance with mitigation measures "
        "and the effectiveness of those measures on an ongoing basis.",
        "AIDA §7(1)",
        "GovernanceEngine — continuous compliance monitoring",
        True,
    ),
    (
        "AIDA §8(1)",
        "Assess the potential impacts of the high-impact AI system, "
        "including impacts on individuals and communities.",
        "AIDA §8(1)",
        None,
        True,
    ),
    (
        "AIDA §9(1)",
        "Take reasonable measures to mitigate risks of harm and biased "
        "output identified in the assessment.",
        "AIDA §9(1)",
        "GovernanceEngine — severity-based blocking and escalation",
        True,
    ),
    (
        "AIDA §10(1)",
        "Publish on a publicly available website a plain-language "
        "description of the system, how it is used, the types of content "
        "it generates, and the mitigation measures in place.",
        "AIDA §10(1)",
        "TransparencyDisclosure — public system card generation",
        True,
    ),
    (
        "AIDA §11(1)",
        "Provide a meaningful explanation to any individual affected by "
        "a decision made or informed by the high-impact AI system.",
        "AIDA §11(1)",
        "TransparencyDisclosure — per-decision explanation capability",
        True,
    ),
    (
        "AIDA §12(1)",
        "Keep records of the measures taken to comply with this Act, "
        "including records of assessments, monitoring, and mitigation.",
        "AIDA §12(1)",
        "AuditLog — comprehensive compliance record-keeping",
        True,
    ),
    (
        "AIDA §13(1)",
        "Notify the Minister if use of the AI system results in, or is "
        "likely to result in, material harm to an individual.",
        "AIDA §13(1)",
        None,
        True,
    ),
    (
        "AIDA §14(1)",
        "Register the high-impact AI system in the public registry "
        "maintained by the Minister.",
        "AIDA §14(1)",
        None,
        False,
    ),
]

_ACGS_LITE_MAP: dict[str, str] = {
    "AIDA §5(1)": (
        "acgs-lite GovernanceEngine — constitutional governance rules "
        "serve as documented risk mitigation measures"
    ),
    "AIDA §6(1)": (
        "acgs-lite RiskClassifier — automated risk tier classification "
        "determining high-impact status"
    ),
    "AIDA §7(1)": (
        "acgs-lite GovernanceEngine — real-time monitoring of every agent "
        "action against constitutional rules"
    ),
    "AIDA §9(1)": (
        "acgs-lite GovernanceEngine — severity-based action blocking with "
        "escalation tiers as mitigation"
    ),
    "AIDA §10(1)": (
        "acgs-lite TransparencyDisclosure — generates public-facing "
        "system cards with capabilities, limitations, and safeguards"
    ),
    "AIDA §11(1)": (
        "acgs-lite TransparencyDisclosure — per-decision explanation with "
        "contributing factors and governance context"
    ),
    "AIDA §12(1)": (
        "acgs-lite AuditLog — tamper-evident JSONL with SHA-256 hash "
        "chain preserving compliance records"
    ),
}


class CanadaAIDAFramework:
    """Canada AIDA (Artificial Intelligence and Data Act) compliance assessor.

    Covers high-impact AI system obligations: risk assessment, mitigation,
    transparency, explanation, record-keeping, and registration.

    Penalties: Up to CAD 25M or 5% of gross global revenue.

    Status: Proposed (Bill C-27, Part 3). Pending Senate.
    """

    framework_id: str = "canada_aida"
    framework_name: str = "Canada Artificial Intelligence and Data Act (AIDA)"
    jurisdiction: str = "Canada"
    status: str = "proposed"
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
    fw: CanadaAIDAFramework, checklist: list[ChecklistItem],
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
            recs.append(f"{i.ref}: Address this AIDA requirement before enforcement begins.")
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
