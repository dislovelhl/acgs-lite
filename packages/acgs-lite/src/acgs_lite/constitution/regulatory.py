"""Regulatory mapping helpers for constitutional analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import permission_ceiling

if TYPE_CHECKING:
    from .constitution import Constitution


_REGULATORY_FRAMEWORKS: dict[str, dict[str, list[dict[str, str | list[str]]]]] = {
    "soc2": {
        "controls": [
            {
                "name": "CC1 - Control Environment",
                "categories": ["transparency", "audit"],
                "keywords": ["transparency", "oversight", "governance", "audit"],
            },
            {
                "name": "CC2 - Communication",
                "categories": ["transparency"],
                "keywords": ["disclose", "explain", "report", "document"],
            },
            {
                "name": "CC6 - Logical Access",
                "categories": ["security", "privacy"],
                "keywords": ["access", "credential", "authentication", "authorization"],
            },
            {
                "name": "CC7 - System Operations",
                "categories": ["operations", "safety"],
                "keywords": ["monitor", "deploy", "operate", "maintain"],
            },
            {
                "name": "CC9 - Risk Mitigation",
                "categories": ["compliance", "regulatory", "safety"],
                "keywords": ["risk", "incident", "remediat", "mitigat"],
            },
        ],
    },
    "hipaa": {
        "controls": [
            {
                "name": "§164.308 Administrative Safeguards",
                "categories": ["privacy", "compliance"],
                "keywords": ["policy", "procedure", "workforce", "training"],
            },
            {
                "name": "§164.312 Technical Safeguards",
                "categories": ["security", "privacy"],
                "keywords": ["encrypt", "access", "audit", "integrity"],
            },
            {
                "name": "§164.514 PHI De-identification",
                "categories": ["privacy", "data-protection"],
                "keywords": ["phi", "pii", "personal", "deidentif", "anonymi"],
            },
            {
                "name": "§164.524 Access Rights",
                "categories": ["privacy"],
                "keywords": ["access", "request", "consent", "right"],
            },
        ],
    },
    "gdpr": {
        "controls": [
            {
                "name": "Art.5 Data Principles",
                "categories": ["privacy", "data-protection"],
                "keywords": ["privacy", "personal", "data", "gdpr", "purpose"],
            },
            {
                "name": "Art.6 Lawful Basis",
                "categories": ["privacy", "compliance"],
                "keywords": ["consent", "lawful", "legitimate", "contract"],
            },
            {
                "name": "Art.17 Right to Erasure",
                "categories": ["privacy"],
                "keywords": ["delete", "erase", "remov", "forget"],
            },
            {
                "name": "Art.25 Data by Design",
                "categories": ["privacy", "security"],
                "keywords": ["by design", "default", "privacy", "minimal"],
            },
            {
                "name": "Art.32 Security Measures",
                "categories": ["security", "privacy"],
                "keywords": ["encrypt", "integrity", "confidential", "breach"],
            },
        ],
    },
    "iso27001": {
        "controls": [
            {
                "name": "A.5 Information Security Policies",
                "categories": ["compliance", "audit"],
                "keywords": ["policy", "security", "governance", "framework"],
            },
            {
                "name": "A.9 Access Control",
                "categories": ["security", "privacy"],
                "keywords": ["access", "credential", "privilege", "authenticat"],
            },
            {
                "name": "A.12 Operations Security",
                "categories": ["operations", "security"],
                "keywords": ["monitor", "log", "backup", "change", "vulnerabilit"],
            },
            {
                "name": "A.18 Compliance",
                "categories": ["compliance", "regulatory"],
                "keywords": ["compliance", "legal", "regulat", "audit", "review"],
            },
        ],
    },
}


def regulatory_alignment(
    constitution: Constitution,
    framework: str = "soc2",
) -> dict[str, Any]:
    """Report how well the constitution aligns to a regulatory framework."""
    fw_key = framework.lower()
    if fw_key not in _REGULATORY_FRAMEWORKS:
        available = ", ".join(sorted(_REGULATORY_FRAMEWORKS))
        raise ValueError(f"Unknown framework {framework!r}. Available: {available}")

    controls = _REGULATORY_FRAMEWORKS[fw_key]["controls"]
    active = constitution.active_rules()

    covered: list[str] = []
    uncovered: list[str] = []
    control_detail: dict[str, Any] = {}

    for control in controls:
        control_name = str(control["name"])
        control_categories: list[str] = list(control.get("categories", []))
        control_keywords: list[str] = list(control.get("keywords", []))

        matched: list[str] = []
        for rule in active:
            category_hit = rule.category in control_categories
            keyword_hit = any(
                keyword in " ".join(rule.keywords).lower() for keyword in control_keywords
            )
            if category_hit or keyword_hit:
                matched.append(rule.id)

        is_covered = bool(matched)
        control_detail[control_name] = {
            "covered": is_covered,
            "matched_rules": matched,
        }
        (covered if is_covered else uncovered).append(control_name)

    total = len(controls)
    alignment_score = len(covered) / total if total > 0 else 0.0

    return {
        "framework": fw_key,
        "alignment_score": round(alignment_score, 4),
        "covered_controls": covered,
        "uncovered_controls": uncovered,
        "control_detail": control_detail,
        "total_controls": total,
    }


def rule_regulatory_clause_map(constitution: Constitution) -> dict[str, Any]:
    """Map rule tags to specific regulatory clauses for audit documentation."""
    return permission_ceiling.rule_regulatory_clause_map(constitution)
