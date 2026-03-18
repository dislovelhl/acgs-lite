"""Coverage analysis helpers for constitutional domains."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .constitution import Constitution


def semantic_rule_clusters(
    constitution: Constitution,
    expected_domains: Sequence[str] | None = None,
) -> dict[str, list[str]]:
    """Group rules into governance domains using category and keyword signals."""
    domains = list(expected_domains or ("safety", "privacy", "transparency"))
    clusters: dict[str, list[str]] = {domain: [] for domain in domains}

    for rule in constitution.active_rules():
        rule_fields = " ".join(
            (
                rule.category.lower(),
                rule.subcategory.lower(),
                rule.text.lower(),
                " ".join(k.lower() for k in rule.keywords),
            )
        )
        for domain in domains:
            signal = constitution._DOMAIN_SIGNAL_MAP.get(
                domain.lower(),
                {"categories": {domain.lower()}, "keywords": {domain.lower()}},
            )
            categories = signal["categories"]
            keywords = signal["keywords"]
            has_category_signal = any(cat in rule_fields for cat in categories)
            has_keyword_signal = any(kw in rule_fields for kw in keywords)
            if has_category_signal or has_keyword_signal:
                clusters[domain].append(rule.id)

    return {domain: sorted(set(rule_ids)) for domain, rule_ids in clusters.items()}


def analyze_coverage_gaps(
    constitution: Constitution,
    expected_domains: Sequence[str] | None = None,
    *,
    weak_threshold: int = 1,
) -> dict[str, Any]:
    """Identify weak or missing governance-domain coverage."""
    if weak_threshold < 1:
        raise ValueError("weak_threshold must be >= 1")

    domains = list(expected_domains or ("safety", "privacy", "transparency"))
    clusters = semantic_rule_clusters(constitution, domains)

    coverage: dict[str, dict[str, Any]] = {}
    weak_domains: list[str] = []
    missing_domains: list[str] = []
    recommendations: list[str] = []

    for domain in domains:
        rule_ids = clusters.get(domain, [])
        rule_count = len(rule_ids)
        if rule_count == 0:
            status = "missing"
            missing_domains.append(domain)
            weak_domains.append(domain)
            recommendations.append(
                f"Add at least {weak_threshold} rule(s) covering '{domain}' controls."
            )
        elif rule_count <= weak_threshold:
            status = "weak"
            weak_domains.append(domain)
            recommendations.append(
                f"Expand '{domain}' coverage beyond {rule_count} clustered rule(s)."
            )
        else:
            status = "covered"

        coverage[domain] = {
            "status": status,
            "rule_count": rule_count,
            "rule_ids": rule_ids,
        }

    return {
        "expected_domains": domains,
        "semantic_clusters": clusters,
        "domain_coverage": coverage,
        "weak_domains": weak_domains,
        "missing_domains": missing_domains,
        "recommendations": recommendations,
    }
