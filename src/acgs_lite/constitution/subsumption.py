"""exp184: CrossConstitutionCompliance — subsumption analysis.

Determines whether one rule set covers (subsumes) another by comparing
keyword coverage, severity alignment, and category gaps. Enables hierarchical
governance validation: does a team-level constitution satisfy org-level requirements?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RuleCoverageResult:
    """Coverage analysis for a single rule from the reference set."""

    rule_id: str
    rule_text: str
    severity: str
    keywords: tuple[str, ...]
    covered_by: tuple[str, ...]
    keyword_coverage: float
    is_covered: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_text": self.rule_text,
            "severity": self.severity,
            "keywords": list(self.keywords),
            "covered_by": list(self.covered_by),
            "keyword_coverage": round(self.keyword_coverage, 4),
            "is_covered": self.is_covered,
        }


@dataclass
class SubsumptionReport:
    """Result of cross-constitution subsumption analysis."""

    reference_name: str
    candidate_name: str
    reference_rule_count: int
    candidate_rule_count: int
    covered_rules: list[RuleCoverageResult]
    uncovered_rules: list[RuleCoverageResult]
    partially_covered: list[RuleCoverageResult]
    severity_gaps: list[dict[str, Any]]
    category_gaps: list[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def coverage_score(self) -> float:
        total = len(self.covered_rules) + len(self.uncovered_rules) + len(self.partially_covered)
        if total == 0:
            return 1.0
        fully = len(self.covered_rules)
        partial = len(self.partially_covered) * 0.5
        return (fully + partial) / total

    @property
    def subsumes(self) -> bool:
        return len(self.uncovered_rules) == 0 and len(self.partially_covered) == 0

    def summary(self) -> str:
        lines = [
            f"Subsumption: {self.candidate_name} vs {self.reference_name}",
            f"  Coverage: {self.coverage_score:.1%}",
            f"  Subsumes: {self.subsumes}",
            f"  Covered: {len(self.covered_rules)}/{self.reference_rule_count}",
            f"  Partially covered: {len(self.partially_covered)}",
            f"  Uncovered: {len(self.uncovered_rules)}",
            f"  Severity gaps: {len(self.severity_gaps)}",
            f"  Category gaps: {len(self.category_gaps)}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_name": self.reference_name,
            "candidate_name": self.candidate_name,
            "reference_rule_count": self.reference_rule_count,
            "candidate_rule_count": self.candidate_rule_count,
            "coverage_score": round(self.coverage_score, 4),
            "subsumes": self.subsumes,
            "covered": [r.to_dict() for r in self.covered_rules],
            "uncovered": [r.to_dict() for r in self.uncovered_rules],
            "partially_covered": [r.to_dict() for r in self.partially_covered],
            "severity_gaps": self.severity_gaps,
            "category_gaps": self.category_gaps,
            "timestamp": self.timestamp.isoformat(),
        }


class CrossConstitutionCompliance:
    """Analyzes whether one constitution's rules subsume another's.

    Used for hierarchical governance validation where child constitutions
    must satisfy parent-level requirements.
    """

    SEVERITY_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    COVERAGE_THRESHOLD: float = 0.7

    __slots__ = ("_history",)

    def __init__(self) -> None:
        self._history: list[SubsumptionReport] = []

    def check_subsumption(
        self,
        reference_rules: list[dict[str, Any]],
        candidate_rules: list[dict[str, Any]],
        reference_name: str = "reference",
        candidate_name: str = "candidate",
        coverage_threshold: float | None = None,
    ) -> SubsumptionReport:
        """Check if candidate_rules subsume reference_rules."""
        threshold = coverage_threshold or self.COVERAGE_THRESHOLD

        candidate_keywords: dict[str, set[str]] = {}
        candidate_severities: dict[str, str] = {}
        candidate_categories: set[str] = set()

        for rule in candidate_rules:
            rid = rule.get("id", "unknown")
            kws = set(rule.get("keywords", []))
            candidate_keywords[rid] = kws
            candidate_severities[rid] = rule.get("severity", "low")
            cat = rule.get("category", "")
            if cat:
                candidate_categories.add(cat)

        all_candidate_kws = set()
        for kws in candidate_keywords.values():
            all_candidate_kws |= kws

        covered: list[RuleCoverageResult] = []
        uncovered: list[RuleCoverageResult] = []
        partially: list[RuleCoverageResult] = []
        severity_gaps: list[dict[str, Any]] = []
        reference_categories: set[str] = set()

        for ref_rule in reference_rules:
            ref_id = ref_rule.get("id", "unknown")
            ref_text = ref_rule.get("text", "")
            ref_severity = ref_rule.get("severity", "low")
            ref_keywords = set(ref_rule.get("keywords", []))
            ref_cat = ref_rule.get("category", "")
            if ref_cat:
                reference_categories.add(ref_cat)

            if not ref_keywords:
                result = RuleCoverageResult(
                    rule_id=ref_id,
                    rule_text=ref_text,
                    severity=ref_severity,
                    keywords=(),
                    covered_by=(),
                    keyword_coverage=0.0,
                    is_covered=False,
                )
                uncovered.append(result)
                continue

            matched_kws = ref_keywords & all_candidate_kws
            kw_coverage = len(matched_kws) / len(ref_keywords) if ref_keywords else 0.0

            covering_rules: list[str] = []
            for cid, ckws in candidate_keywords.items():
                if ckws & ref_keywords:
                    covering_rules.append(cid)
                    c_sev = candidate_severities.get(cid, "low")
                    ref_rank = self.SEVERITY_RANK.get(ref_severity, 0)
                    c_rank = self.SEVERITY_RANK.get(c_sev, 0)
                    if c_rank < ref_rank:
                        severity_gaps.append(
                            {
                                "reference_rule": ref_id,
                                "candidate_rule": cid,
                                "reference_severity": ref_severity,
                                "candidate_severity": c_sev,
                            }
                        )

            result = RuleCoverageResult(
                rule_id=ref_id,
                rule_text=ref_text,
                severity=ref_severity,
                keywords=tuple(sorted(ref_keywords)),
                covered_by=tuple(sorted(covering_rules)),
                keyword_coverage=kw_coverage,
                is_covered=kw_coverage >= threshold,
            )

            if kw_coverage >= threshold:
                covered.append(result)
            elif kw_coverage > 0:
                partially.append(result)
            else:
                uncovered.append(result)

        category_gaps = sorted(reference_categories - candidate_categories)

        report = SubsumptionReport(
            reference_name=reference_name,
            candidate_name=candidate_name,
            reference_rule_count=len(reference_rules),
            candidate_rule_count=len(candidate_rules),
            covered_rules=covered,
            uncovered_rules=uncovered,
            partially_covered=partially,
            severity_gaps=severity_gaps,
            category_gaps=category_gaps,
        )
        self._history.append(report)
        return report

    def find_gaps(
        self,
        reference_rules: list[dict[str, Any]],
        candidate_rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return only the gaps (uncovered + partially covered rules)."""
        report = self.check_subsumption(reference_rules, candidate_rules)
        gaps: list[dict[str, Any]] = []
        for r in report.uncovered_rules:
            gaps.append({"rule_id": r.rule_id, "status": "uncovered", **r.to_dict()})
        for r in report.partially_covered:
            gaps.append({"rule_id": r.rule_id, "status": "partial", **r.to_dict()})
        return gaps

    def history(self) -> list[SubsumptionReport]:
        return list(self._history)
