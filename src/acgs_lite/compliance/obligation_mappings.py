"""Article-ref to runtime obligation mappings.

Static mapping from framework article references to RuntimeObligation instances.
Extensible via ``register_obligation()`` without modifying this file.

Constitutional Hash: 608508a9bd224290

Usage::

    from acgs_lite.compliance.obligation_mappings import get_obligations_for_refs

    refs = ["EU-AIA Art.14(1)", "HIPAA §164.502"]
    obligations = get_obligations_for_refs(refs)
"""

from __future__ import annotations

from acgs_lite.compliance.runtime_obligations import (
    ObligationType,
    RuntimeObligation,
    make_obligation,
)

# ---------------------------------------------------------------------------
# Static mapping: article_ref → RuntimeObligation
# ---------------------------------------------------------------------------
# Keys must match the `legal_citation` (or ref) values used by each framework
# module's ChecklistItem.  New entries should follow the naming convention
# already established in eu_ai_act.py, hipaa_ai.py, gdpr.py, etc.

_OBLIGATION_MAP: dict[str, RuntimeObligation] = {
    # ── EU AI Act ────────────────────────────────────────────────────────────
    "EU-AIA Art.14(1)": make_obligation(
        ObligationType.HITL_REQUIRED,
        "eu_ai_act",
        "EU-AIA Art.14(1)",
        "High-risk AI system must have human oversight measures enabling humans "
        "to understand, monitor, and intervene in the AI output.",
    ),
    "EU-AIA Art.14(4)": make_obligation(
        ObligationType.HITL_REQUIRED,
        "eu_ai_act",
        "EU-AIA Art.14(4)",
        "Natural persons assigned to human oversight must have authority and "
        "competence to intervene or halt AI system operation.",
    ),
    "EU-AIA Art.14(5)": make_obligation(
        ObligationType.HITL_REQUIRED,
        "eu_ai_act",
        "EU-AIA Art.14(5)",
        "Providers must design high-risk AI to allow human override of automated "
        "decisions where technically feasible.",
    ),
    "EU-AIA Art.13(1)": make_obligation(
        ObligationType.EXPLAINABILITY,
        "eu_ai_act",
        "EU-AIA Art.13(1)",
        "High-risk AI systems must be transparent and provide sufficient "
        "information to deployers to interpret outputs and use appropriately.",
    ),
    "EU-AIA Art.13(3)": make_obligation(
        ObligationType.EXPLAINABILITY,
        "eu_ai_act",
        "EU-AIA Art.13(3)",
        "Instructions for use must include purpose, performance limitations, "
        "human oversight requirements, and technical measures.",
    ),
    "EU-AIA Art.9(1)": make_obligation(
        ObligationType.AUDIT_REQUIRED,
        "eu_ai_act",
        "EU-AIA Art.9(1)",
        "Providers must establish and maintain a risk management system for "
        "high-risk AI systems throughout their lifecycle.",
    ),
    "EU-AIA Art.12(1)": make_obligation(
        ObligationType.AUDIT_REQUIRED,
        "eu_ai_act",
        "EU-AIA Art.12(1)",
        "High-risk AI systems must automatically log events to enable post-market "
        "monitoring and traceability.",
    ),
    "EU-AIA Art.10(2)": make_obligation(
        ObligationType.BIAS_CHECK,
        "eu_ai_act",
        "EU-AIA Art.10(2)",
        "Training data must be subject to data governance practices including "
        "bias assessment and data quality examination.",
    ),
    "EU-AIA Art.15(1)": make_obligation(
        ObligationType.BIAS_CHECK,
        "eu_ai_act",
        "EU-AIA Art.15(1)",
        "High-risk AI systems must achieve appropriate levels of accuracy, "
        "robustness, and cybersecurity throughout their lifecycle.",
    ),
    # ── HIPAA ────────────────────────────────────────────────────────────────
    "HIPAA §164.502": make_obligation(
        ObligationType.PHI_GUARD,
        "hipaa_ai",
        "HIPAA §164.502",
        "Protected health information (PHI) may not be used or disclosed except "
        "as permitted by the Privacy Rule. AI must not expose PHI in outputs.",
    ),
    "HIPAA §164.312": make_obligation(
        ObligationType.PHI_GUARD,
        "hipaa_ai",
        "HIPAA §164.312",
        "Technical safeguards must control access to PHI. AI outputs must not "
        "contain or reconstruct individually identifiable health information.",
    ),
    "HIPAA §164.530": make_obligation(
        ObligationType.AUDIT_REQUIRED,
        "hipaa_ai",
        "HIPAA §164.530",
        "Covered entities must document policies, procedures, and activities "
        "relating to PHI use and disclosure by AI systems.",
    ),
    # ── GDPR ─────────────────────────────────────────────────────────────────
    "GDPR Art.22(1)": make_obligation(
        ObligationType.HITL_REQUIRED,
        "gdpr",
        "GDPR Art.22(1)",
        "Data subjects have the right not to be subject to solely automated "
        "decisions with significant effects. Human review must be available.",
    ),
    "GDPR Art.22(3)": make_obligation(
        ObligationType.HITL_REQUIRED,
        "gdpr",
        "GDPR Art.22(3)",
        "Where automated decisions are permitted, the controller must implement "
        "suitable measures including human intervention and contestation.",
    ),
    "GDPR Art.6(1)": make_obligation(
        ObligationType.CONSENT_CHECK,
        "gdpr",
        "GDPR Art.6(1)",
        "Personal data processing requires a lawful basis. AI that processes "
        "personal data must verify consent or another legal ground.",
    ),
    "GDPR Art.13(2)(f)": make_obligation(
        ObligationType.EXPLAINABILITY,
        "gdpr",
        "GDPR Art.13(2)(f)",
        "Privacy notices must include meaningful information about automated "
        "decision-making logic, significance, and envisaged consequences.",
    ),
    "GDPR Art.35(1)": make_obligation(
        ObligationType.AUDIT_REQUIRED,
        "gdpr",
        "GDPR Art.35(1)",
        "A Data Protection Impact Assessment (DPIA) is required for high-risk "
        "AI processing of personal data.",
    ),
    # ── SOC 2 ────────────────────────────────────────────────────────────────
    "SOC2 CC7.1": make_obligation(
        ObligationType.AUDIT_REQUIRED,
        "soc2_ai",
        "SOC2 CC7.1",
        "The organization detects and monitors for system anomalies, threats, "
        "and failures. AI decisions must generate auditable log events.",
    ),
    "SOC2 CC6.1": make_obligation(
        ObligationType.AUDIT_REQUIRED,
        "soc2_ai",
        "SOC2 CC6.1",
        "Logical and physical access controls must restrict AI system access "
        "to authorized users and verify access based on least privilege.",
    ),
    # ── DORA (financial resilience) ──────────────────────────────────────────
    "DORA Art.6": make_obligation(
        ObligationType.AUDIT_REQUIRED,
        "dora",
        "DORA Art.6",
        "Financial entities must have ICT risk management frameworks that "
        "include monitoring and logging of AI-driven decisions.",
    ),
    # ── iGaming (UKGC LCCP) ──────────────────────────────────────────────────
    "IGAMING-RG-1.1": make_obligation(
        ObligationType.COOL_OFF,
        "igaming",
        "IGAMING-RG-1.1",
        "Self-exclusion must be enforced immediately and AI must not target self-excluded players.",
    ),
    "IGAMING-RG-1.2": make_obligation(
        ObligationType.COOL_OFF,
        "igaming",
        "IGAMING-RG-1.2",
        "Cool-off period (minimum 24 hours) must be enforced before player can resume.",
    ),
    "IGAMING-RG-1.3": make_obligation(
        ObligationType.SPEND_LIMIT,
        "igaming",
        "IGAMING-RG-1.3",
        "Deposit limit must be enforced by AI before processing any deposit action.",
    ),
    "IGAMING-KYC-2.1": make_obligation(
        ObligationType.CONSENT_CHECK,
        "igaming",
        "IGAMING-KYC-2.1",
        "Age verification (18+) must be completed before any deposit or gameplay.",
    ),
    "IGAMING-AI-4.1": make_obligation(
        ObligationType.HITL_REQUIRED,
        "igaming",
        "IGAMING-AI-4.1",
        "AI-driven personalized offers must be reviewed against constitutional rules before delivery.",
    ),
    "IGAMING-AI-4.3": make_obligation(
        ObligationType.HITL_REQUIRED,
        "igaming",
        "IGAMING-AI-4.3",
        "AI must not target vulnerable or self-excluded players. Constitutional rule verification required.",
    ),
}

# ---------------------------------------------------------------------------
# Extension registry — populated by register_obligation()
# ---------------------------------------------------------------------------
_CUSTOM_OBLIGATIONS: dict[str, RuntimeObligation] = {}


def register_obligation(article_ref: str, obligation: RuntimeObligation) -> None:
    """Register a custom article_ref → obligation mapping at runtime.

    Useful for tenant-specific extensions or vertical-specific frameworks
    (e.g. iGaming LCCP) without modifying this module.

    Args:
        article_ref: The article reference string (must be unique).
        obligation: The RuntimeObligation to attach when this ref is present.
    """
    _CUSTOM_OBLIGATIONS[article_ref] = obligation


def get_obligations_for_refs(
    article_refs: list[str],
) -> list[RuntimeObligation]:
    """Look up runtime obligations for a list of article references.

    Checks both the static map and the custom extension registry.
    Unknown refs are silently skipped (not every ref maps to a runtime obligation).

    Args:
        article_refs: List of article reference strings from checklist items.

    Returns:
        Deduplicated list of RuntimeObligation instances (unsatisfied).
    """
    seen: set[str] = set()
    obligations: list[RuntimeObligation] = []

    for ref in article_refs:
        if ref in seen:
            continue
        seen.add(ref)

        obligation = _CUSTOM_OBLIGATIONS.get(ref) or _OBLIGATION_MAP.get(ref)
        if obligation is not None:
            obligations.append(obligation)

    return obligations


def get_all_article_refs() -> list[str]:
    """Return all known article refs (static + custom). Useful for introspection."""
    return sorted({**_OBLIGATION_MAP, **_CUSTOM_OBLIGATIONS}.keys())
