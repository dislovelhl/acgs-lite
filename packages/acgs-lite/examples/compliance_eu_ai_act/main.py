"""
Example: EU AI Act Compliance Assessment
==========================================
Assess any AI system against the EU AI Act (Regulation 2024/1689).
Risk tier is inferred automatically from the domain — no manual classification needed.

Run:
    python examples/compliance_eu_ai_act/main.py
"""

from acgs_lite.compliance import (
    EUAIActFramework,
    MultiFrameworkAssessor,
    infer_risk_tier,
)
from acgs_lite.compliance.base import ChecklistStatus


def demo_tier_inference() -> None:
    """Show automatic risk-tier inference from domain."""
    print("\n── 1. Automatic Risk-Tier Inference ──────────────────────────")
    cases = [
        {"domain": "medical_device", "description": "Clinical decision support"},
        {"domain": "hr_recruitment", "description": "CV screening tool"},
        {"domain": "chatbot", "description": "Customer service bot"},
        {"domain": "spam_filter", "description": "Email spam detection"},
    ]
    for desc in cases:
        tier = infer_risk_tier(desc)
        print(f"  {desc['domain']:20s} → tier: {tier}")


def demo_single_framework() -> None:
    """Run a single-framework EU AI Act assessment."""
    print("\n── 2. Single-Framework Assessment ────────────────────────────")

    fw = EUAIActFramework()
    system = {
        "system_id": "cv-screener-v1",
        "domain": "hr_recruitment",      # infers risk_tier="high"
        "has_human_oversight": True,
        "has_audit_log": True,
        "has_risk_management": False,    # gap
        "has_data_governance": False,    # gap
    }

    assessment = fw.assess(system)
    print(f"  Framework   : {assessment.framework_name}")
    print(f"  Score       : {assessment.compliance_score:.0%}")
    print(f"  ACGS coverage: {assessment.acgs_lite_coverage:.0%}")

    if assessment.gaps:
        print(f"  Gaps ({len(assessment.gaps)}):")
        for gap in assessment.gaps[:3]:
            print(f"    • {gap[:80]}")

    # Count items by status
    statuses: dict[str, int] = {}
    for item in assessment.items:
        statuses[item["status"]] = statuses.get(item["status"], 0) + 1
    print(f"  Item counts : {statuses}")


def demo_checklist_by_tier() -> None:
    """Compare checklist sizes across risk tiers."""
    print("\n── 3. Checklist Size by Risk Tier ────────────────────────────")
    fw = EUAIActFramework()
    for tier in ("unacceptable", "limited", "high"):
        items = fw.get_checklist({"risk_tier": tier})
        applicable = [i for i in items if i.status != ChecklistStatus.NOT_APPLICABLE]
        print(f"  {tier:14s}: {len(applicable):2d} applicable items")


def demo_multi_framework() -> None:
    """Run a multi-framework global assessment."""
    print("\n── 4. Multi-Framework Assessment ─────────────────────────────")

    assessor = MultiFrameworkAssessor(frameworks=["eu_ai_act", "gdpr", "nist_ai_rmf"])
    results = assessor.assess({
        "system_id": "medical-ai-v2",
        "domain": "medical_device",
        "has_human_oversight": True,
        "has_audit_log": True,
        "has_risk_management": True,
        "processes_personal_data": True,
        "has_data_governance": True,
    })

    print(f"  Overall score: {results.overall_score:.0%}")
    for fw_id, fw_result in results.by_framework.items():
        bar = "█" * int(fw_result.compliance_score * 20)
        print(f"  {fw_id:15s} {bar:<20s} {fw_result.compliance_score:.0%}")


if __name__ == "__main__":
    print("=" * 55)
    print("  EU AI Act Compliance Assessment Demo")
    print("=" * 55)

    demo_tier_inference()
    demo_single_framework()
    demo_checklist_by_tier()
    demo_multi_framework()

    print("\nDone. No API keys required — all assessments run offline.")
