"""EU AI Act compliance module for acgs-lite.

Provides Article 12 (Record-Keeping), Article 13 (Transparency),
Article 14 (Human Oversight), and risk classification helpers
for high-risk AI system compliance.

**Deadline: EU AI Act high-risk provisions take effect 2026-08-02.**

Constitutional Hash: cdd01ef066bc6cf2

License Requirements
--------------------
- **PRO+**: Article12Logger, RiskClassifier, ComplianceChecklist
- **TEAM+**: TransparencyDisclosure, HumanOversightGateway
- **ENTERPRISE**: Custom constitutional rules, priority support

Quick Start::

    import acgs_lite
    acgs_lite.set_license("ACGS-PRO-...")

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
    # result.requires_article12_logging == True

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

from typing import Any

import acgs_lite.eu_ai_act.article12 as _a12
import acgs_lite.eu_ai_act.compliance_checklist as _cc
import acgs_lite.eu_ai_act.human_oversight as _ho
import acgs_lite.eu_ai_act.risk_classification as _rc
import acgs_lite.eu_ai_act.transparency as _tr
from acgs_lite.licensing import LicenseError, LicenseManager, Tier

# ---------------------------------------------------------------------------
# Tier-gating helper
# ---------------------------------------------------------------------------


def _gated(tier: Tier, original_cls: type, feature: str = "") -> type:
    """Return a subclass whose __init__ checks the license tier first."""

    class _Gated(original_cls):  # type: ignore[misc]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            # Always resolve the current singleton so test resets work correctly
            LicenseManager().require(tier, feature or original_cls.__name__)
            super().__init__(*args, **kwargs)

    _Gated.__name__ = original_cls.__name__
    _Gated.__qualname__ = original_cls.__qualname__
    _Gated.__doc__ = original_cls.__doc__
    _Gated.__module__ = original_cls.__module__
    return _Gated


# ---------------------------------------------------------------------------
# PRO-gated classes (Article 12 + risk classification + compliance checklist)
# ---------------------------------------------------------------------------

Article12Logger: type = _gated(Tier.PRO, _a12.Article12Logger, "Article 12 logging")
Article12Record = _a12.Article12Record  # data class, no gate needed

RiskClassifier: type = _gated(Tier.PRO, _rc.RiskClassifier, "Risk classification")
ClassificationResult = _rc.ClassificationResult  # data class
RiskLevel = _rc.RiskLevel  # enum
SystemDescription = _rc.SystemDescription  # data class

ComplianceChecklist: type = _gated(Tier.PRO, _cc.ComplianceChecklist, "Compliance checklist")
ChecklistItem = _cc.ChecklistItem  # data class
ChecklistStatus = _cc.ChecklistStatus  # enum

# ---------------------------------------------------------------------------
# TEAM-gated classes (Article 13 transparency + Article 14 human oversight)
# ---------------------------------------------------------------------------

TransparencyDisclosure: type = _gated(
    Tier.TEAM, _tr.TransparencyDisclosure, "Article 13 transparency"
)

HumanOversightGateway: type = _gated(
    Tier.TEAM, _ho.HumanOversightGateway, "Article 14 human oversight"
)
OversightDecision = _ho.OversightDecision  # data class
OversightOutcome = _ho.OversightOutcome  # enum

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def check_license() -> dict[str, Any]:
    """Return current license tier and available EU AI Act features.

    Returns a dict with keys: tier, expiry, pro_features, team_features.
    """
    info = LicenseManager().load()
    return {
        "tier": info.tier.name,
        "expiry": info.expiry_date,
        "pro_features": info.has_tier(Tier.PRO),
        "team_features": info.has_tier(Tier.TEAM),
        "enterprise_features": info.has_tier(Tier.ENTERPRISE),
        "available_classes": [
            cls
            for cls, tier in [
                ("Article12Logger", Tier.PRO),
                ("RiskClassifier", Tier.PRO),
                ("ComplianceChecklist", Tier.PRO),
                ("TransparencyDisclosure", Tier.TEAM),
                ("HumanOversightGateway", Tier.TEAM),
            ]
            if info.has_tier(tier)
        ],
    }


__all__ = [
    # Article 12 — Record-Keeping (PRO+)
    "Article12Logger",
    "Article12Record",
    # Article 13 — Transparency (TEAM+)
    "TransparencyDisclosure",
    # Article 14 — Human Oversight (TEAM+)
    "HumanOversightGateway",
    "OversightDecision",
    "OversightOutcome",
    # Risk Classification — Article 6 + Annex III (PRO+)
    "RiskClassifier",
    "RiskLevel",
    "SystemDescription",
    "ClassificationResult",
    # Compliance Checklist (PRO+)
    "ComplianceChecklist",
    "ChecklistItem",
    "ChecklistStatus",
    # Helpers
    "LicenseError",
    "check_license",
]

EU_AI_ACT_HIGH_RISK_DEADLINE = "2026-08-02"
