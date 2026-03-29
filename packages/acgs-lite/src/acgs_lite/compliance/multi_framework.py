"""Multi-framework compliance orchestrator.

Runs compliance assessment across all applicable regulatory frameworks
and produces a unified MultiFrameworkReport with cross-framework gap
analysis, overall scoring, and prioritized recommendations.

Constitutional Hash: 608508a9bd224290

Usage::

    from acgs_lite.compliance import MultiFrameworkAssessor

    assessor = MultiFrameworkAssessor()
    report = assessor.assess({"system_id": "my-system", "domain": "healthcare"})

    print(report.overall_score)          # 0.65
    print(report.frameworks_assessed)    # ("gdpr", "hipaa_ai", "nist_ai_rmf", ...)
    print(report.cross_framework_gaps)   # Common gaps across frameworks
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from acgs_lite.compliance.base import (
    ComplianceFramework,
    FrameworkAssessment,
    MultiFrameworkReport,
)
from acgs_lite.compliance.australia_ai_ethics import AustraliaAIEthicsFramework
from acgs_lite.compliance.brazil_lgpd import BrazilLGPDFramework
from acgs_lite.compliance.canada_aida import CanadaAIDAFramework
from acgs_lite.compliance.ccpa_cpra import CCPACPRAFramework
from acgs_lite.compliance.china_ai import ChinaAIFramework
from acgs_lite.compliance.dora import DORAFramework
from acgs_lite.compliance.eu_ai_act import EUAIActFramework
from acgs_lite.compliance.gdpr import GDPRFramework
from acgs_lite.compliance.hipaa_ai import HIPAAAIFramework
from acgs_lite.compliance.india_dpdp import IndiaDPDPFramework
from acgs_lite.compliance.iso_42001 import ISO42001Framework
from acgs_lite.compliance.nist_ai_rmf import NISTAIRMFFramework
from acgs_lite.compliance.nyc_ll144 import NYCLL144Framework
from acgs_lite.compliance.oecd_ai import OECDAIFramework
from acgs_lite.compliance.singapore_maigf import SingaporeMAIGFFramework
from acgs_lite.compliance.soc2_ai import SOC2AIFramework
from acgs_lite.compliance.uk_ai_framework import UKAIFramework
from acgs_lite.compliance.us_fair_lending import USFairLendingFramework

# Registry of all available compliance frameworks
_FRAMEWORK_REGISTRY: dict[str, type] = {
    # Original 8
    "nist_ai_rmf": NISTAIRMFFramework,
    "iso_42001": ISO42001Framework,
    "gdpr": GDPRFramework,
    "soc2_ai": SOC2AIFramework,
    "hipaa_ai": HIPAAAIFramework,
    "us_fair_lending": USFairLendingFramework,
    "nyc_ll144": NYCLL144Framework,
    "oecd_ai": OECDAIFramework,
    # Round 2: +5
    "eu_ai_act": EUAIActFramework,
    "dora": DORAFramework,
    "canada_aida": CanadaAIDAFramework,
    "singapore_maigf": SingaporeMAIGFFramework,
    "uk_ai_framework": UKAIFramework,
    # Round 3: +5
    "india_dpdp": IndiaDPDPFramework,
    "australia_ai_ethics": AustraliaAIEthicsFramework,
    "brazil_lgpd": BrazilLGPDFramework,
    "china_ai": ChinaAIFramework,
    "ccpa_cpra": CCPACPRAFramework,
}

# Jurisdiction -> frameworks that apply
_JURISDICTION_MAP: dict[str, list[str]] = {
    "united_states": ["nist_ai_rmf", "soc2_ai", "oecd_ai", "ccpa_cpra"],
    "european_union": ["gdpr", "eu_ai_act", "iso_42001", "oecd_ai"],
    "international": ["iso_42001", "oecd_ai"],
    "new_york_city": ["nist_ai_rmf", "soc2_ai", "nyc_ll144", "oecd_ai"],
    "canada": ["canada_aida", "nist_ai_rmf", "oecd_ai"],
    "united_kingdom": ["uk_ai_framework", "iso_42001", "oecd_ai"],
    "singapore": ["singapore_maigf", "iso_42001", "oecd_ai"],
    "asean": ["singapore_maigf", "oecd_ai"],
    "india": ["india_dpdp", "oecd_ai"],
    "australia": ["australia_ai_ethics", "oecd_ai"],
    "brazil": ["brazil_lgpd", "oecd_ai"],
    "china": ["china_ai"],
    "california": ["ccpa_cpra", "nist_ai_rmf"],
}

# Domain -> additional frameworks
_DOMAIN_MAP: dict[str, list[str]] = {
    "healthcare": ["hipaa_ai"],
    "medical": ["hipaa_ai"],
    "lending": ["us_fair_lending"],
    "credit": ["us_fair_lending"],
    "credit_scoring": ["us_fair_lending"],
    "financial": ["us_fair_lending", "soc2_ai", "dora"],
    "finance": ["us_fair_lending", "soc2_ai", "dora"],
    "fintech": ["dora", "soc2_ai"],
    "banking": ["dora", "us_fair_lending", "soc2_ai"],
    "insurance": ["dora", "soc2_ai"],
    "employment": ["nyc_ll144"],
    "hiring": ["nyc_ll144"],
    "general_purpose_ai": ["eu_ai_act"],
    "gpai": ["eu_ai_act"],
}

# Gap categories that appear across multiple frameworks
_CROSS_FRAMEWORK_THEMES: dict[str, list[str]] = {
    "bias_testing": [
        "bias",
        "fairness",
        "discrimination",
        "disparate",
        "demographic",
    ],
    "data_governance": [
        "data governance",
        "data lineage",
        "training data",
        "data quality",
    ],
    "incident_response": [
        "incident",
        "breach",
        "notification",
        "response",
    ],
    "model_documentation": [
        "documentation",
        "technical documentation",
        "model inventory",
    ],
    "stakeholder_engagement": [
        "stakeholder",
        "affected",
        "community",
        "engagement",
    ],
}


class MultiFrameworkAssessor:
    """Run compliance assessment across multiple regulatory frameworks.

    Accepts a list of framework IDs to assess, or determines applicable
    frameworks automatically based on jurisdiction and domain.

    Args:
        frameworks: List of framework IDs to assess. If None, determines
            applicable frameworks based on system_description.

    Usage::

        # Explicit framework selection
        assessor = MultiFrameworkAssessor(frameworks=["gdpr", "nist_ai_rmf"])
        report = assessor.assess({"system_id": "my-system"})

        # Automatic framework selection
        assessor = MultiFrameworkAssessor()
        report = assessor.assess({
            "system_id": "my-system",
            "jurisdiction": "european_union",
            "domain": "healthcare",
        })
    """

    def __init__(self, frameworks: list[str] | None = None) -> None:
        """Initialize with an optional list of framework IDs to assess."""
        self._requested_frameworks = frameworks
        self._instances: dict[str, ComplianceFramework] = {}

    def _resolve_frameworks(
        self,
        system_description: dict[str, Any],
    ) -> list[str]:
        """Determine which frameworks to run."""
        if self._requested_frameworks is not None:
            return [fid for fid in self._requested_frameworks if fid in _FRAMEWORK_REGISTRY]

        jurisdiction = system_description.get("jurisdiction", "").lower().replace(" ", "_")
        domain = system_description.get("domain", "").lower().replace(" ", "_")

        fw_ids: set[str] = set()

        # Add jurisdiction-based frameworks
        if jurisdiction in _JURISDICTION_MAP:
            fw_ids.update(_JURISDICTION_MAP[jurisdiction])

        # Add domain-based frameworks
        if domain in _DOMAIN_MAP:
            fw_ids.update(_DOMAIN_MAP[domain])

        # If nothing matched, run all
        if not fw_ids:
            fw_ids = set(_FRAMEWORK_REGISTRY.keys())

        return sorted(fw_ids)

    def _get_instance(self, framework_id: str) -> ComplianceFramework:
        """Get or create a framework instance."""
        if framework_id not in self._instances:
            cls = _FRAMEWORK_REGISTRY[framework_id]
            self._instances[framework_id] = cls()
        return self._instances[framework_id]

    def applicable_frameworks(
        self,
        jurisdiction: str,
        domain: str,
    ) -> list[str]:
        """Determine which frameworks apply based on jurisdiction and domain.

        Args:
            jurisdiction: Jurisdiction string (e.g. "european_union", "united_states").
            domain: Application domain (e.g. "healthcare", "lending").

        Returns:
            Sorted list of applicable framework IDs.

        """
        desc = {"jurisdiction": jurisdiction, "domain": domain}
        return self._resolve_frameworks(desc)

    def assess(self, system_description: dict[str, Any]) -> MultiFrameworkReport:
        """Run all applicable frameworks and return a unified report.

        Args:
            system_description: Dict describing the AI system. Expected keys:
                - system_id: str (required)
                - jurisdiction: str (optional, for auto-selection)
                - domain: str (optional, for auto-selection)
                - purpose: str (optional)
                - Additional framework-specific keys.

        Returns:
            Frozen MultiFrameworkReport with per-framework and cross-framework results.

        """
        system_id = system_description.get("system_id", "unknown")
        fw_ids = self._resolve_frameworks(system_description)

        by_framework: dict[str, FrameworkAssessment] = {}
        for fid in fw_ids:
            fw = self._get_instance(fid)
            by_framework[fid] = fw.assess(system_description)

        overall_score = _compute_overall_score(by_framework)
        acgs_total = _compute_acgs_coverage(by_framework)
        cross_gaps = _identify_cross_framework_gaps(by_framework)
        recommendations = _generate_prioritized_recommendations(by_framework, cross_gaps)

        return MultiFrameworkReport(
            system_id=system_id,
            frameworks_assessed=tuple(fw_ids),
            overall_score=overall_score,
            by_framework=by_framework,
            cross_framework_gaps=cross_gaps,
            acgs_lite_total_coverage=acgs_total,
            recommendations=recommendations,
            assessed_at=datetime.now(UTC).isoformat(),
        )

    @staticmethod
    def available_frameworks() -> dict[str, str]:
        """Return all registered framework IDs and names.

        Returns:
            Dict mapping framework_id to framework_name.

        """
        result: dict[str, str] = {}
        for fid, cls in sorted(_FRAMEWORK_REGISTRY.items()):
            instance = cls()
            result[fid] = instance.framework_name
        return result


def _compute_overall_score(
    by_framework: dict[str, FrameworkAssessment],
) -> float:
    """Compute weighted average compliance score across frameworks."""
    if not by_framework:
        return 0.0
    total = sum(a.compliance_score for a in by_framework.values())
    return round(total / len(by_framework), 4)


def _compute_acgs_coverage(
    by_framework: dict[str, FrameworkAssessment],
) -> float:
    """Compute average acgs-lite coverage across frameworks."""
    if not by_framework:
        return 0.0
    total = sum(a.acgs_lite_coverage for a in by_framework.values())
    return round(total / len(by_framework), 4)


def _identify_cross_framework_gaps(
    by_framework: dict[str, FrameworkAssessment],
) -> tuple[str, ...]:
    """Identify gap themes that appear across multiple frameworks."""
    # Collect all gap texts
    all_gaps: list[str] = []
    for assessment in by_framework.values():
        all_gaps.extend(assessment.gaps)

    if not all_gaps:
        return ()

    # Count theme occurrences across frameworks
    theme_counts: Counter[str] = Counter()
    all_gap_text = " ".join(g.lower() for g in all_gaps)

    for theme, keywords in _CROSS_FRAMEWORK_THEMES.items():
        for kw in keywords:
            if kw in all_gap_text:
                theme_counts[theme] += 1
                break

    # Report themes found in gaps
    cross_gaps: list[str] = []
    theme_descriptions = {
        "bias_testing": (
            "Bias testing and fairness assessment: required by multiple frameworks "
            "but not yet addressed."
        ),
        "data_governance": (
            "Data governance and lineage: training data quality and provenance "
            "requirements appear across frameworks."
        ),
        "incident_response": (
            "Incident response procedures: breach notification and failure "
            "response required by multiple regulations."
        ),
        "model_documentation": (
            "Model documentation: comprehensive AI system documentation "
            "required across multiple frameworks."
        ),
        "stakeholder_engagement": (
            "Stakeholder engagement: requirements to involve affected "
            "populations appear in multiple frameworks."
        ),
    }

    for theme, _count in theme_counts.most_common():
        if theme in theme_descriptions:
            cross_gaps.append(theme_descriptions[theme])

    return tuple(cross_gaps)


def _generate_prioritized_recommendations(
    by_framework: dict[str, FrameworkAssessment],
    cross_gaps: tuple[str, ...],
) -> tuple[str, ...]:
    """Generate prioritized recommendations from all frameworks."""
    recs: list[str] = []

    # Cross-framework gaps are highest priority
    if cross_gaps:
        recs.append(
            "PRIORITY: Address cross-framework gaps first, as they close "
            "compliance requirements across multiple regulations simultaneously."
        )

    # Count which acgs-lite features are used most
    feature_refs: Counter[str] = Counter()
    for assessment in by_framework.values():
        for item in assessment.items:
            feat = item.get("acgs_lite_feature")
            if feat and item.get("status") == "compliant":
                feature_refs[feat] += 1

    if feature_refs:
        top_feature = feature_refs.most_common(1)[0]
        recs.append(
            f"STRENGTH: '{top_feature[0]}' satisfies requirements across "
            f"{top_feature[1]} frameworks. Leverage this capability further."
        )

    # Add framework-specific recommendations (up to 3 per framework)
    for fid, assessment in sorted(by_framework.items()):
        for rec in assessment.recommendations[:3]:
            recs.append(f"[{fid}] {rec}")

    return tuple(recs)
