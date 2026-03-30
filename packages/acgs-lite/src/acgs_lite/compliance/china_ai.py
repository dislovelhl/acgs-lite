"""China AI Regulation compliance module.

Implements China's four enacted AI-specific regulations:
1. Algorithm Recommendation Regulation (effective Mar 1, 2022)
2. Deep Synthesis (Deepfake) Regulation (effective Jan 10, 2023)
3. Generative AI Regulation (effective Aug 15, 2023)
4. Global AI Governance Initiative (announced Oct 2023)

Reference:
  - Provisions on the Management of Algorithmic Recommendations
  - Provisions on the Management of Deep Synthesis
  - Interim Measures for the Management of Generative AI Services
  - Global AI Governance Initiative
Status: enacted (4 regulations)
Enforcement: Varies per regulation (2022-2023)
Penalties: Fines, service suspension, criminal liability (per regulation)

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
    # Algorithm Recommendation Regulation (CN-ALG)
    (
        "CN-ALG Art.4",
        "Algorithm recommendation service providers must adhere to laws, "
        "uphold social morality and ethics, and observe business ethics.",
        "Algorithm Recommendation Provisions, Art. 4",
        "GovernanceEngine — constitutional rules encoding ethical constraints",
        True,
    ),
    (
        "CN-ALG Art.6",
        "Implement algorithm management mechanisms including algorithm "
        "security self-assessment, filing, and user complaint handling.",
        "Algorithm Recommendation Provisions, Art. 6",
        None,
        True,
    ),
    (
        "CN-ALG Art.16",
        "Provide users with an option to conveniently turn off algorithmic "
        "recommendation services, and provide a non-personalized option.",
        "Algorithm Recommendation Provisions, Art. 16",
        None,
        True,
    ),
    (
        "CN-ALG Art.17",
        "Inform users of the basic principles, purpose, and main operating "
        "mechanism of the algorithm recommendation service in a prominent way.",
        "Algorithm Recommendation Provisions, Art. 17",
        "TransparencyDisclosure — algorithm information disclosure",
        True,
    ),
    # Deep Synthesis Regulation (CN-DS)
    (
        "CN-DS Art.6",
        "Deep synthesis service providers shall strengthen management of "
        "deep synthesis content, establish and improve management systems, "
        "and maintain technical measures.",
        "Deep Synthesis Provisions, Art. 6",
        "GovernanceEngine — content governance management system",
        True,
    ),
    (
        "CN-DS Art.7",
        "Deep synthesis service providers shall implement real identity "
        "verification of users based on mobile phone numbers, ID documents, "
        "or similar.",
        "Deep Synthesis Provisions, Art. 7",
        None,
        True,
    ),
    (
        "CN-DS Art.12",
        "Add labels to deep synthesis content that could cause public "
        "confusion or misidentification, with labels that cannot be removed.",
        "Deep Synthesis Provisions, Art. 12",
        "TransparencyDisclosure — content labeling for synthetic media",
        True,
    ),
    (
        "CN-DS Art.16",
        "Maintain log records of deep synthesis activities for at least "
        "six months.",
        "Deep Synthesis Provisions, Art. 16",
        "AuditLog — persistent activity logging",
        True,
    ),
    # Generative AI Regulation (CN-GAI)
    (
        "CN-GAI Art.4",
        "Providers of generative AI services shall adhere to socialist core "
        "values and shall not generate content that subverts state power, "
        "incites separatism, or undermines national unity.",
        "Generative AI Interim Measures, Art. 4",
        "GovernanceEngine — content governance rules enforcement",
        True,
    ),
    (
        "CN-GAI Art.7",
        "Take effective measures to improve the quality of training data, "
        "including data annotation quality, and use lawful sources.",
        "Generative AI Interim Measures, Art. 7",
        None,
        True,
    ),
    (
        "CN-GAI Art.8",
        "Conduct security assessments and algorithm filing before providing "
        "generative AI services to the public.",
        "Generative AI Interim Measures, Art. 8",
        "RiskClassifier — security assessment support",
        True,
    ),
    (
        "CN-GAI Art.9",
        "Accept and handle user complaints, promptly deal with personal "
        "information requests, and take measures to prevent discrimination.",
        "Generative AI Interim Measures, Art. 9",
        "HumanOversightGateway — complaint handling and human review",
        True,
    ),
    (
        "CN-GAI Art.17",
        "Providers must clearly mark AI-generated content in a way that "
        "users can identify it, including through metadata labeling.",
        "Generative AI Interim Measures, Art. 17",
        "TransparencyDisclosure — AI content marking and labeling",
        True,
    ),
    # Global AI Governance Initiative (CN-GAIG)
    (
        "CN-GAIG P1",
        "AI technology shall be human-centred and intelligent for good, "
        "developed in a way that is safe, reliable, controllable, and fair.",
        "Global AI Governance Initiative, Principle 1",
        "GovernanceEngine — constitutional safety and fairness constraints",
        False,
    ),
]

# Refs conditional on is_generative_ai
_GENERATIVE_AI_REFS: set[str] = {
    "CN-GAI Art.4", "CN-GAI Art.7", "CN-GAI Art.8", "CN-GAI Art.9",
    "CN-GAI Art.17",
}

_ACGS_LITE_MAP: dict[str, str] = {
    "CN-ALG Art.4": (
        "acgs-lite GovernanceEngine — constitutional rules encoding "
        "ethical and legal constraints"
    ),
    "CN-ALG Art.17": (
        "acgs-lite TransparencyDisclosure — algorithm information "
        "disclosure for users"
    ),
    "CN-DS Art.6": (
        "acgs-lite GovernanceEngine — content governance management "
        "via constitutional rules"
    ),
    "CN-DS Art.12": (
        "acgs-lite TransparencyDisclosure — content labeling for "
        "deep synthesis / synthetic media"
    ),
    "CN-DS Art.16": (
        "acgs-lite AuditLog — persistent JSONL logging of all activities"
    ),
    "CN-GAI Art.4": (
        "acgs-lite GovernanceEngine — content governance rules preventing "
        "generation of prohibited content"
    ),
    "CN-GAI Art.8": (
        "acgs-lite RiskClassifier — security assessment support with "
        "risk classification"
    ),
    "CN-GAI Art.9": (
        "acgs-lite HumanOversightGateway — complaint handling and "
        "human review mechanism"
    ),
    "CN-GAI Art.17": (
        "acgs-lite TransparencyDisclosure — AI content marking "
        "and metadata labeling"
    ),
    "CN-GAIG P1": (
        "acgs-lite GovernanceEngine — constitutional rules for safety, "
        "reliability, controllability, and fairness"
    ),
}


class ChinaAIFramework:
    """China AI Regulation compliance assessor.

    Covers four regulations: Algorithm Recommendation, Deep Synthesis,
    Generative AI, and Global AI Governance Initiative.

    Status: Enacted. Multiple regulations effective 2022-2023.
    """

    framework_id: str = "china_ai"
    framework_name: str = "China AI Regulations (Algorithm/DeepSynth/GenAI/Global)"
    jurisdiction: str = "China"
    status: str = "enacted"
    enforcement_date: str | None = "2022-03-01"

    def get_checklist(self, system_description: dict[str, Any]) -> list[ChecklistItem]:
        is_generative = system_description.get("is_generative_ai", False)

        items: list[ChecklistItem] = []
        for ref, req, citation, feature, blocking in _ITEMS:
            item = ChecklistItem(
                ref=ref, requirement=req, acgs_lite_feature=feature,
                blocking=blocking, legal_citation=citation,
            )
            if ref in _GENERATIVE_AI_REFS and not is_generative:
                item.mark_not_applicable(
                    "Not applicable: system is not a generative AI service."
                )
            items.append(item)
        return items

    def auto_populate_acgs_lite(self, checklist: list[ChecklistItem]) -> None:
        for item in checklist:
            if item.ref in _ACGS_LITE_MAP and item.status != ChecklistStatus.NOT_APPLICABLE:
                item.mark_complete(_ACGS_LITE_MAP[item.ref])

    def assess(self, system_description: dict[str, Any]) -> FrameworkAssessment:
        checklist = self.get_checklist(system_description)
        self.auto_populate_acgs_lite(checklist)
        return _build_assessment(self, checklist)


def _build_assessment(
    fw: ChinaAIFramework, checklist: list[ChecklistItem],
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
                f"{i.ref}: Address this China AI regulation requirement. "
                f"Non-compliance may result in fines, service suspension, "
                f"or criminal liability."
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
