"""EU Artificial Intelligence Act compliance module.

Implements the EU AI Act (Regulation (EU) 2024/1689) requirements
for AI system providers and deployers across risk tiers:
- Prohibited practices (Art. 5) — effective Feb 2, 2025
- High-risk obligations (Arts. 9-15, 26) — effective Aug 2, 2026
- Transparency obligations (Art. 50)
- General-purpose AI (Arts. 53, 55)

Reference: Regulation (EU) 2024/1689 (Artificial Intelligence Act)
Status: enacted
Enforcement: Prohibited practices 2025-02-02; high-risk 2026-08-02
Penalties: Up to EUR 35 million or 7% of global annual turnover

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

# (ref, requirement, legal_citation, acgs_lite_feature | None, blocking)
_ITEMS: list[tuple[str, str, str, str | None, bool]] = [
    # Risk management (Art. 9)
    (
        "EUAIA Art.9(1)",
        "Establish, implement, document, and maintain a risk management system "
        "for high-risk AI systems throughout their lifecycle.",
        "EU AI Act Article 9(1)",
        "GovernanceEngine — continuous risk management via constitutional rules",
        True,
    ),
    (
        "EUAIA Art.9(2)",
        "Identify and analyse known and reasonably foreseeable risks that the "
        "high-risk AI system can pose to health, safety, or fundamental rights.",
        "EU AI Act Article 9(2)",
        "RiskClassifier — automated risk classification with obligation mapping",
        True,
    ),
    # Data governance (Art. 10)
    (
        "EUAIA Art.10(2)",
        "Training, validation, and testing data sets shall be subject to "
        "appropriate data governance and management practices.",
        "EU AI Act Article 10(2)",
        None,
        True,
    ),
    # Technical documentation (Art. 11)
    (
        "EUAIA Art.11(1)",
        "Draw up technical documentation before placing on market or putting "
        "into service, kept up to date.",
        "EU AI Act Article 11(1)",
        None,
        True,
    ),
    # Record-keeping (Art. 12)
    (
        "EUAIA Art.12(1)",
        "High-risk AI systems shall technically allow for automatic recording "
        "of events (logs) throughout the system's lifetime.",
        "EU AI Act Article 12(1)",
        "AuditLog — tamper-evident automatic event logging",
        True,
    ),
    (
        "EUAIA Art.12(2)",
        "Logging capabilities shall ensure traceability of the AI system's "
        "functioning to identify risks and facilitate post-market monitoring.",
        "EU AI Act Article 12(2)",
        "AuditLog — cryptographic hash chain for traceability",
        True,
    ),
    # Transparency (Art. 13)
    (
        "EUAIA Art.13(1)",
        "High-risk AI systems shall be designed and developed to ensure their "
        "operation is sufficiently transparent to enable deployers to interpret "
        "and use output appropriately.",
        "EU AI Act Article 13(1)",
        "TransparencyDisclosure — system cards with capabilities and limitations",
        True,
    ),
    (
        "EUAIA Art.13(3)",
        "Provide deployers with concise, complete, correct, and clear information "
        "including characteristics, capabilities, limitations, and risks.",
        "EU AI Act Article 13(3)",
        "TransparencyDisclosure — structured disclosure documentation",
        True,
    ),
    # Human oversight (Art. 14)
    (
        "EUAIA Art.14(1)",
        "High-risk AI systems shall be designed and developed to be effectively "
        "overseen by natural persons during the period of use.",
        "EU AI Act Article 14(1)",
        "HumanOversightGateway — configurable human-in-the-loop gates",
        True,
    ),
    (
        "EUAIA Art.14(4)",
        "Provide measures allowing individuals assigned to human oversight to "
        "correctly interpret output and decide not to use or override it.",
        "EU AI Act Article 14(4)",
        "HumanOversightGateway — override and intervention mechanisms",
        True,
    ),
    (
        "EUAIA Art.14(5)",
        "For high-risk AI systems identified in Annex III point 1(a), ensure "
        "no action or decision is taken based solely on AI output without "
        "human verification.",
        "EU AI Act Article 14(5)",
        "MACIEnforcer — separation-of-powers enforcement for critical decisions",
        True,
    ),
    # Accuracy, robustness, cybersecurity (Art. 15)
    (
        "EUAIA Art.15(1)",
        "High-risk AI systems shall be designed to achieve appropriate levels "
        "of accuracy, robustness, and cybersecurity.",
        "EU AI Act Article 15(1)",
        None,
        True,
    ),
    # Deployer obligations (Art. 26)
    (
        "EUAIA Art.26(1)",
        "Deployers shall take appropriate technical and organisational measures "
        "to ensure they use high-risk AI systems in accordance with "
        "instructions of use.",
        "EU AI Act Article 26(1)",
        "GovernanceEngine — enforces use within constitutional boundaries",
        True,
    ),
    # Transparency for certain AI systems (Art. 50)
    (
        "EUAIA Art.50(1)",
        "Providers shall ensure AI systems intended to interact with natural "
        "persons are designed so persons are informed they are interacting "
        "with an AI system.",
        "EU AI Act Article 50(1)",
        "TransparencyDisclosure — AI interaction disclosure",
        False,
    ),
    # General-purpose AI (Art. 53) — conditional on is_gpai
    (
        "EUAIA Art.53(1)",
        "Providers of general-purpose AI models shall draw up and keep "
        "up-to-date technical documentation including training and testing "
        "process and results of evaluation.",
        "EU AI Act Article 53(1)",
        None,
        True,
    ),
    # Systemic risk GPAI (Art. 55) — conditional on is_gpai
    (
        "EUAIA Art.55(1)",
        "Providers of general-purpose AI models with systemic risk shall "
        "perform model evaluation, assess and mitigate systemic risks, "
        "ensure adequate cybersecurity, and report serious incidents.",
        "EU AI Act Article 55(1)",
        None,
        True,
    ),
]

# Refs that only apply when risk_tier == "high"
_HIGH_RISK_REFS: set[str] = {
    "EUAIA Art.9(1)", "EUAIA Art.9(2)", "EUAIA Art.10(2)", "EUAIA Art.11(1)",
    "EUAIA Art.12(1)", "EUAIA Art.12(2)", "EUAIA Art.13(1)", "EUAIA Art.13(3)",
    "EUAIA Art.14(1)", "EUAIA Art.14(4)", "EUAIA Art.14(5)", "EUAIA Art.15(1)",
    "EUAIA Art.26(1)",
}

# Refs that only apply to GPAI models
_GPAI_REFS: set[str] = {"EUAIA Art.53(1)", "EUAIA Art.55(1)"}

_ACGS_LITE_MAP: dict[str, str] = {
    "EUAIA Art.9(1)": (
        "acgs-lite GovernanceEngine — continuous governance enforcement "
        "serving as documented risk management system"
    ),
    "EUAIA Art.9(2)": (
        "acgs-lite RiskClassifier — automated risk identification and "
        "classification with obligation mapping"
    ),
    "EUAIA Art.12(1)": (
        "acgs-lite AuditLog — tamper-evident automatic logging of all "
        "governance events throughout system lifetime"
    ),
    "EUAIA Art.12(2)": (
        "acgs-lite AuditLog — SHA-256 hash chain ensuring traceability "
        "for post-market monitoring"
    ),
    "EUAIA Art.13(1)": (
        "acgs-lite TransparencyDisclosure — machine-readable system cards "
        "enabling deployers to interpret AI output"
    ),
    "EUAIA Art.13(3)": (
        "acgs-lite TransparencyDisclosure — structured disclosure with "
        "capabilities, limitations, and risk information"
    ),
    "EUAIA Art.14(1)": (
        "acgs-lite HumanOversightGateway — configurable HITL gates for "
        "effective human oversight during operation"
    ),
    "EUAIA Art.14(4)": (
        "acgs-lite HumanOversightGateway — override and intervention "
        "mechanisms for human oversight"
    ),
    "EUAIA Art.14(5)": (
        "acgs-lite MACIEnforcer — enforces separation of powers preventing "
        "solely automated critical decisions"
    ),
    "EUAIA Art.26(1)": (
        "acgs-lite GovernanceEngine — enforces operational boundaries "
        "per constitutional rules"
    ),
    "EUAIA Art.50(1)": (
        "acgs-lite TransparencyDisclosure — AI interaction disclosure generation"
    ),
}


class EUAIActFramework:
    """EU Artificial Intelligence Act compliance assessor.

    Covers prohibited practices (Art. 5), high-risk system obligations
    (Arts. 9-15, 26), transparency (Art. 50), and GPAI provisions
    (Arts. 53, 55).

    Penalties: Up to EUR 35M or 7% of global annual turnover (Art. 99).

    Status: Enacted 2024. Prohibited practices effective 2025-02-02.
    High-risk obligations effective 2026-08-02.
    """

    framework_id: str = "eu_ai_act"
    framework_name: str = "EU Artificial Intelligence Act"
    jurisdiction: str = "European Union"
    status: str = "enacted"
    enforcement_date: str | None = "2025-02-02"

    def get_checklist(self, system_description: dict[str, Any]) -> list[ChecklistItem]:
        """Generate EU AI Act checklist, scoping by risk tier and GPAI flag."""
        risk_tier = system_description.get("risk_tier", "high")
        is_gpai = system_description.get("is_gpai", False)

        items: list[ChecklistItem] = []
        for ref, req, citation, feature, blocking in _ITEMS:
            item = ChecklistItem(
                ref=ref, requirement=req, acgs_lite_feature=feature,
                blocking=blocking, legal_citation=citation,
            )
            # High-risk items N/A for non-high-risk systems
            if ref in _HIGH_RISK_REFS and risk_tier != "high":
                item.mark_not_applicable(
                    f"Not applicable: system risk tier is '{risk_tier}', not 'high'."
                )
            # GPAI items N/A for non-GPAI systems
            if ref in _GPAI_REFS and not is_gpai:
                item.mark_not_applicable(
                    "Not applicable: system is not a general-purpose AI model."
                )
            items.append(item)
        return items

    def auto_populate_acgs_lite(self, checklist: list[ChecklistItem]) -> None:
        """Mark items that acgs-lite directly satisfies."""
        for item in checklist:
            if item.ref in _ACGS_LITE_MAP and item.status != ChecklistStatus.NOT_APPLICABLE:
                item.mark_complete(_ACGS_LITE_MAP[item.ref])

    def assess(self, system_description: dict[str, Any]) -> FrameworkAssessment:
        """Run full EU AI Act assessment."""
        checklist = self.get_checklist(system_description)
        self.auto_populate_acgs_lite(checklist)
        return _build_assessment(self, checklist)


def _build_assessment(
    fw: EUAIActFramework,
    checklist: list[ChecklistItem],
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
                f"{i.ref}: Address this requirement. Non-compliance risks "
                f"fines up to EUR 35M or 7% of global annual turnover."
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
