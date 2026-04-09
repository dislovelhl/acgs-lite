"""Permission ceiling and regulatory mapping helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .constitution import Constitution


def get_permission_ceiling(constitution: Constitution) -> dict[str, Any]:
    """Return the effective permission ceiling for a constitution."""
    ceiling = (constitution.permission_ceiling or "standard").lower().strip()
    if ceiling not in ("strict", "permissive"):
        ceiling = "standard"

    if ceiling == "strict":
        allow_override_critical = False
        require_human_above = "critical"
        max_auto_allow = "high"
        description = "Strict: no critical overrides; human required for critical."
    elif ceiling == "permissive":
        allow_override_critical = True
        require_human_above = "low"
        max_auto_allow = "low"
        description = "Permissive: overrides allowed; human recommended for low+."
    else:
        allow_override_critical = True
        require_human_above = "high"
        max_auto_allow = "medium"
        description = "Standard: human required for high/critical; medium may auto-allow."

    return {
        "ceiling": ceiling,
        "allow_override_critical": allow_override_critical,
        "require_human_above_severity": require_human_above,
        "max_auto_allow_severity": max_auto_allow,
        "description": description,
    }


_TAG_TO_REGULATORY_CLAUSES: dict[str, list[str]] = {
    "gdpr": ["GDPR Art. 5(1)(a) (lawfulness)", "GDPR Art. 32 (security)"],
    "sox": ["SOX 302 (certifications)", "SOX 404 (internal controls)"],
    "pci-dss": ["PCI-DSS Req 3.4 (storage)", "PCI-DSS Req 8.2 (authentication)"],
    "hipaa": ["HIPAA §164.312(a)(1) (access control)", "HIPAA §164.312(e)(1) (transmission)"],
    "soc2": ["SOC2 CC6.1 (logical access)", "SOC2 CC7.1 (system monitoring)"],
    "iso27001": ["ISO/IEC 27001 A.9 (access control)", "ISO/IEC 27001 A.12 (operations)"],
}


def rule_regulatory_clause_map(constitution: Constitution) -> dict[str, Any]:
    """Map rule tags to specific regulatory clauses for audit documentation."""
    by_rule: dict[str, list[str]] = {}
    for rule in constitution.active_rules():
        clauses: list[str] = []
        if isinstance(rule.metadata.get("regulatory_clauses"), list):
            for clause in rule.metadata["regulatory_clauses"]:
                if isinstance(clause, str) and clause.strip():
                    clauses.append(clause.strip())
        for tag in rule.tags or []:
            tag_lower = str(tag).lower().strip()
            if tag_lower in _TAG_TO_REGULATORY_CLAUSES:
                for clause in _TAG_TO_REGULATORY_CLAUSES[tag_lower]:
                    if clause not in clauses:
                        clauses.append(clause)
        if clauses:
            by_rule[rule.id] = clauses

    by_tag = dict(_TAG_TO_REGULATORY_CLAUSES)
    return {
        "by_rule": by_rule,
        "by_tag": by_tag,
        "tag_to_clauses": by_tag,
    }
