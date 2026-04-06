"""EU AI Act compliance module for acgs-lite.

Provides Article 12 (Record-Keeping), Article 13 (Transparency),
Article 14 (Human Oversight), and risk classification helpers
for high-risk AI system compliance.

**Deadline: EU AI Act high-risk provisions take effect 2026-08-02.**

Constitutional Hash: 608508a9bd224290

Quick Start::

    from acgs_lite.eu_ai_act import (
        Article12Logger,
        RiskClassifier,
        SystemDescription,
        ComplianceChecklist,
        TransparencyDisclosure,
        HumanOversightGateway,
    )

    # 1. Classify your system
    classifier = RiskClassifier()
    result = classifier.classify(SystemDescription(
        system_id="my-system",
        purpose="Screening job applications",
        domain="employment",
        autonomy_level=3,
        human_oversight=True,
        employment=True,
    ))
    # result.level == RiskLevel.HIGH_RISK

    # 2. Add Article 12 logging to every LLM call
    logger = Article12Logger(system_id="my-system")
    response = logger.log_call(
        operation="screen_candidate",
        call=lambda: llm.complete(prompt),
        input_text=prompt,
    )

    # 3. Human oversight for high-impact decisions
    gateway = HumanOversightGateway(system_id="my-system")
    decision = gateway.submit("final_reject", output, impact_score=0.9)

    # 4. Transparency disclosure (Article 13)
    disclosure = TransparencyDisclosure(
        system_id="my-system",
        system_name="Job Application Screener",
        provider="Acme Corp",
        intended_purpose="Automated first-pass CV screening",
        capabilities=["Text classification", "Ranking"],
        limitations=["English only", "Not validated for creative roles"],
        human_oversight_measures=["All rejections reviewed by HR"],
        contact_email="ai-compliance@acme.com",
    )

    # 5. Compliance checklist (Annex IV documentation)
    checklist = ComplianceChecklist(system_id="my-system")
    checklist.auto_populate_acgs_lite()
    print(checklist.is_gate_clear)     # True (once remaining items done)
    print(checklist.compliance_score)  # 0.55 (items auto-populated by acgs-lite)
"""

from __future__ import annotations

import acgs_lite.eu_ai_act.article12 as _a12
import acgs_lite.eu_ai_act.compliance_checklist as _cc
import acgs_lite.eu_ai_act.human_oversight as _ho
import acgs_lite.eu_ai_act.risk_classification as _rc
import acgs_lite.eu_ai_act.transparency as _tr

# ---------------------------------------------------------------------------
# Article 12 — Record-Keeping
# ---------------------------------------------------------------------------

Article12Logger = _a12.Article12Logger
Article12Record = _a12.Article12Record

# ---------------------------------------------------------------------------
# Risk Classification — Article 6 + Annex III
# ---------------------------------------------------------------------------

RiskClassifier = _rc.RiskClassifier
ClassificationResult = _rc.ClassificationResult
RiskLevel = _rc.RiskLevel
SystemDescription = _rc.SystemDescription

# ---------------------------------------------------------------------------
# Compliance Checklist
# ---------------------------------------------------------------------------

ComplianceChecklist = _cc.ComplianceChecklist
ChecklistItem = _cc.ChecklistItem
ChecklistStatus = _cc.ChecklistStatus

# ---------------------------------------------------------------------------
# Article 13 — Transparency
# ---------------------------------------------------------------------------

TransparencyDisclosure = _tr.TransparencyDisclosure

# ---------------------------------------------------------------------------
# Article 14 — Human Oversight
# ---------------------------------------------------------------------------

HumanOversightGateway = _ho.HumanOversightGateway
OversightDecision = _ho.OversightDecision
OversightOutcome = _ho.OversightOutcome

# ---------------------------------------------------------------------------

__all__ = [
    # Article 12 — Record-Keeping
    "Article12Logger",
    "Article12Record",
    # Article 13 — Transparency
    "TransparencyDisclosure",
    # Article 14 — Human Oversight
    "HumanOversightGateway",
    "OversightDecision",
    "OversightOutcome",
    # Risk Classification — Article 6 + Annex III
    "RiskClassifier",
    "RiskLevel",
    "SystemDescription",
    "ClassificationResult",
    # Compliance Checklist
    "ComplianceChecklist",
    "ChecklistItem",
    "ChecklistStatus",
    # License check
    "check_license",
]

EU_AI_ACT_HIGH_RISK_DEADLINE = "2026-08-02"


def check_license() -> dict[str, object]:
    """Return a summary of EU AI Act features included with the current license tier."""
    from acgs_lite.licensing import LicenseManager, Tier

    mgr = LicenseManager()
    info = mgr.load()

    pro_ok = info.has_tier(Tier.PRO)
    team_ok = info.has_tier(Tier.TEAM)

    available: list[str] = []
    if pro_ok:
        available.extend(["Article12Logger", "RiskClassifier", "ComplianceChecklist"])
    if team_ok:
        available.extend(["TransparencyDisclosure", "HumanOversightGateway"])

    return {
        "tier": info.tier.name,
        "pro_features": pro_ok,
        "team_features": team_ok,
        "available_classes": available,
    }
