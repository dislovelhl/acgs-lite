"""Static regulatory control mappings for generated ACGS rules."""

from __future__ import annotations

EU_AI_ACT_CONTROLS: dict[str, list[str]] = {
    "principles": ["EU AI Act Art.13", "EU AI Act Art.14", "EU AI Act Art.17"],
    "risk": ["EU AI Act Art.9", "EU AI Act Art.17"],
    "data-protection": ["EU AI Act Art.10", "EU AI Act Art.13", "GDPR Art.5", "GDPR Art.32"],
    "compliance": ["EU AI Act Art.13", "EU AI Act Art.17", "GDPR Art.25"],
}

NIST_AI_RMF_CONTROLS: dict[str, list[str]] = {
    "principles": ["NIST AI RMF GOVERN-1", "NIST AI RMF MAP-1"],
    "risk": ["NIST AI RMF MAP-1", "NIST AI RMF MEASURE-2", "NIST AI RMF MANAGE-1"],
    "data-protection": ["NIST AI RMF MAP-1", "NIST AI RMF MEASURE-2"],
    "compliance": ["NIST AI RMF GOVERN-1", "NIST AI RMF MANAGE-1"],
}

ISO_42001_CONTROLS: dict[str, list[str]] = {
    "principles": ["ISO 42001 Clause 6.1", "ISO 42001 Clause 8.4", "ISO 42001 Clause 9.1"],
    "risk": ["ISO 42001 Clause 6.1", "ISO 42001 Clause 9.1"],
    "data-protection": ["ISO 42001 Clause 8.4", "ISO 42001 Clause 9.1"],
    "compliance": ["ISO 42001 Clause 6.1", "ISO 42001 Clause 8.4", "ISO 42001 Clause 9.1"],
}


def map_rule_to_controls(category: str) -> list[str]:
    """Return regulatory controls applicable to a generated rule category."""
    normalized = category.strip().lower()
    controls: list[str] = []
    for table in (EU_AI_ACT_CONTROLS, NIST_AI_RMF_CONTROLS, ISO_42001_CONTROLS):
        controls.extend(table.get(normalized, []))
    return list(dict.fromkeys(controls))
