"""US Fair Lending AI compliance module.

Implements ECOA, FCRA, and fair lending requirements for AI systems
used in credit decisions, lending, and financial services:
- ECOA: Equal Credit Opportunity Act (no discrimination)
- FCRA: Fair Credit Reporting Act (accuracy, disputes, adverse actions)
- Fair lending: Disparate impact analysis and adverse action requirements

Reference: 15 U.S.C. 1691 (ECOA), 15 U.S.C. 1681 (FCRA),
Regulation B (12 CFR 1002), Regulation V (12 CFR 1022).
Enforced by CFPB, FTC, OCC, Federal Reserve, FDIC.

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

_FAIR_LENDING_ITEMS: list[tuple[str, str, str, str | None, bool]] = [
    # ECOA — Equal Credit Opportunity Act
    (
        "ECOA 1691(a)",
        "Ensure AI credit decision models do not discriminate on the basis "
        "of race, color, religion, national origin, sex, marital status, "
        "age, or receipt of public assistance.",
        "15 U.S.C. 1691(a); Regulation B, 12 CFR 1002.4",
        "GovernanceEngine — anti-discrimination rules in constitution",
        True,
    ),
    (
        "ECOA 1691(d)",
        "Provide specific reasons for adverse credit actions taken with AI "
        "assistance. Generic statements are insufficient; each applicant must "
        "receive the principal reason(s) for the action taken.",
        "15 U.S.C. 1691(d); 12 CFR 1002.9",
        "AuditLog — per-decision audit trail documenting action reasons",
        True,
    ),
    (
        "ECOA-AI.1",
        "Validate that AI model features do not serve as proxies for "
        "prohibited bases (disparate impact analysis). Test model outputs "
        "across protected classes.",
        "Regulation B, 12 CFR 1002.6; CFPB Circular 2022-03",
        None,
        True,
    ),
    # FCRA — Fair Credit Reporting Act
    (
        "FCRA 1681e(b)",
        "Follow reasonable procedures to assure maximum possible accuracy "
        "of information furnished to and used by AI credit decision systems.",
        "15 U.S.C. 1681e(b)",
        None,
        True,
    ),
    (
        "FCRA 1681g",
        "Upon request, disclose to the consumer all information in their "
        "file including the sources of information used by the AI system "
        "for credit decisions.",
        "15 U.S.C. 1681g",
        "AuditLog — queryable per-subject decision records",
        True,
    ),
    (
        "FCRA 1681m(a)",
        "Provide adverse action notices when AI-assisted decisions result in "
        "denial or unfavorable terms. Notice must include the specific reasons "
        "and the consumer's right to a free credit report.",
        "15 U.S.C. 1681m(a); 12 CFR 1022.72",
        "TransparencyDisclosure — adverse action documentation template",
        True,
    ),
    (
        "FCRA 1681i",
        "Investigate disputed information within 30 days when a consumer "
        "challenges AI-generated credit assessments or scores.",
        "15 U.S.C. 1681i",
        None,
        True,
    ),
    # Fair Lending — Disparate Impact
    (
        "FL-DI.1",
        "Conduct disparate impact testing on AI lending models across "
        "protected classes (race, sex, age, national origin). Document "
        "testing methodology and results.",
        "CFPB Circular 2022-03; ECOA Regulation B",
        None,
        True,
    ),
    (
        "FL-DI.2",
        "Where disparate impact is identified, demonstrate that the AI model "
        "serves a legitimate business necessity and that no less discriminatory "
        "alternative achieves the same objective.",
        "Regulation B; Texas Dept. of Housing v. Inclusive Communities (2015)",
        None,
        True,
    ),
    # Model Risk Management
    (
        "FL-MRM.1",
        "Implement model risk management per SR 11-7 / OCC 2011-12 for AI "
        "credit models: independent validation, ongoing monitoring, and "
        "documentation of model limitations.",
        "OCC 2011-12; FRB SR 11-7 — Model Risk Management",
        "GovernanceEngine — independent validation via MACI separation",
        True,
    ),
    (
        "FL-MRM.2",
        "Maintain complete model documentation including development data, "
        "feature selection rationale, performance metrics, and known limitations.",
        "OCC 2011-12; FRB SR 11-7",
        None,
        True,
    ),
    # CFPB AI Guidance
    (
        "CFPB-AI.1",
        "Ensure that AI-generated adverse action reasons are specific and "
        "accurate per CFPB guidance. Vague reasons like 'the model determined' "
        "do not satisfy ECOA/FCRA notice requirements.",
        "CFPB Circular 2022-03 — Adverse Action Notification",
        "HumanOversightGateway — human review of adverse actions",
        True,
    ),
]

_ACGS_LITE_MAP: dict[str, str] = {
    "ECOA 1691(a)": (
        "acgs-lite GovernanceEngine — constitutional rules can encode "
        "anti-discrimination policies as enforceable governance constraints"
    ),
    "ECOA 1691(d)": (
        "acgs-lite AuditLog — per-decision audit trail captures "
        "specific reasons for each credit action for ECOA compliance"
    ),
    "FCRA 1681g": (
        "acgs-lite AuditLog — queryable per-subject records support "
        "consumer file disclosure requirements"
    ),
    "FCRA 1681m(a)": (
        "acgs-lite TransparencyDisclosure — generates adverse action "
        "documentation with required consumer notifications"
    ),
    "FL-MRM.1": (
        "acgs-lite GovernanceEngine + MACIEnforcer — independent model "
        "validation via MACI role separation (proposer != validator)"
    ),
    "CFPB-AI.1": (
        "acgs-lite HumanOversightGateway — human review gate for "
        "AI-assisted adverse credit actions before delivery"
    ),
}


class USFairLendingFramework:
    """US Fair Lending AI compliance assessor.

    Covers ECOA (anti-discrimination), FCRA (accuracy, disputes,
    adverse actions), fair lending disparate impact requirements,
    and federal model risk management guidance for AI credit models.

    Enforced by CFPB, FTC, OCC, Federal Reserve, FDIC. Violations
    can result in regulatory actions, fines, and private litigation.

    Status: Enacted. Multiple overlapping federal statutes.

    Usage::

        from acgs_lite.compliance.us_fair_lending import USFairLendingFramework

        framework = USFairLendingFramework()
        assessment = framework.assess({
            "system_id": "credit-scoring-v2",
            "domain": "lending",
        })
    """

    framework_id: str = "us_fair_lending"
    framework_name: str = "US Fair Lending (ECOA + FCRA + Fair Lending)"
    jurisdiction: str = "United States"
    status: str = "enacted"
    enforcement_date: str | None = "1974-10-28"  # ECOA enactment

    def get_checklist(self, system_description: dict[str, Any]) -> list[ChecklistItem]:
        """Generate fair lending AI checklist items."""
        return [
            ChecklistItem(
                ref=ref,
                requirement=req,
                acgs_lite_feature=feature,
                blocking=blocking,
                legal_citation=citation,
            )
            for ref, req, citation, feature, blocking in _FAIR_LENDING_ITEMS
        ]

    def auto_populate_acgs_lite(self, checklist: list[ChecklistItem]) -> None:
        """Mark items that acgs-lite directly satisfies."""
        for item in checklist:
            if item.ref in _ACGS_LITE_MAP:
                item.mark_complete(_ACGS_LITE_MAP[item.ref])

    def assess(self, system_description: dict[str, Any]) -> FrameworkAssessment:
        """Run full US Fair Lending assessment."""
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
                recs.append(
                    f"{item.ref}: Address for fair lending compliance. "
                    f"CFPB enforcement actions carry significant penalties."
                )

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
