"""exp225: Rule deduplication — detect and collapse redundant constitutional rules.

Large constitutions accumulated over time often contain duplicate or near-duplicate
rules: identical keyword sets under different IDs, rules subsumed by broader rules,
or split rules that should be merged back.  This module provides analysis and
safe deduplication with full audit trail.

Duplication types detected:

- **Exact**: identical normalised keyword sets AND same severity AND same category
- **Subset**: rule A's keywords are a strict subset of rule B's (A is redundant if
  they share severity + category — B already catches everything A catches)
- **Near-duplicate**: Jaccard similarity of keyword sets above a configurable
  threshold (default 0.85)

Deduplication is always **non-destructive** — the original constitution is never
modified.  A new Constitution is returned with duplicates removed/merged, plus a
``DuplicationReport`` explaining every decision.

Usage::

    from acgs_lite.constitution import Constitution
    from acgs_lite.constitution.deduplication import find_duplicates, deduplicate

    c = Constitution.from_yaml("policy.yaml")

    report = find_duplicates(c)
    print(f"Found {len(report.exact_groups)} exact duplicates")
    print(f"Found {len(report.subset_pairs)} subset redundancies")
    print(f"Found {len(report.near_duplicate_pairs)} near-duplicates (>85% similarity)")

    c2, dedup_report = deduplicate(c, strategy="keep_highest_severity")
    print(f"Reduced from {len(c.rules)} to {len(c2.rules)} rules")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import Constitution, Rule


def _kw_set(rule: Rule) -> frozenset[str]:
    """Return normalised lowercase keyword frozenset for a rule."""
    return frozenset(k.lower().strip() for k in rule.keywords if k.strip())


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity coefficient for two sets.

    Returns 0.0 for empty sets to avoid division by zero.
    """
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


@dataclass(frozen=True)
class ExactDuplicateGroup:
    """A set of rules with identical normalised keyword sets, same severity and category."""

    rule_ids: tuple[str, ...]
    keywords: frozenset[str]
    severity: str
    category: str
    recommended_keep: str  # rule_id of the rule to keep

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "exact",
            "rule_ids": list(self.rule_ids),
            "keywords": sorted(self.keywords),
            "severity": self.severity,
            "category": self.category,
            "recommended_keep": self.recommended_keep,
        }


@dataclass(frozen=True)
class SubsetRedundancy:
    """Rule *subset_id* is made redundant by *superset_id* (subset keywords ⊂ superset keywords)."""

    subset_id: str
    superset_id: str
    subset_keywords: frozenset[str]
    superset_keywords: frozenset[str]
    shared_severity: bool
    shared_category: bool

    @property
    def is_strictly_redundant(self) -> bool:
        """True only when severity AND category also match (safe to remove)."""
        return self.shared_severity and self.shared_category

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "subset",
            "subset_id": self.subset_id,
            "superset_id": self.superset_id,
            "subset_keywords": sorted(self.subset_keywords),
            "superset_keywords": sorted(self.superset_keywords),
            "shared_severity": self.shared_severity,
            "shared_category": self.shared_category,
            "strictly_redundant": self.is_strictly_redundant,
        }


@dataclass(frozen=True)
class NearDuplicatePair:
    """Two rules with high Jaccard keyword similarity above threshold."""

    rule_id_a: str
    rule_id_b: str
    similarity: float
    shared_keywords: frozenset[str]
    unique_to_a: frozenset[str]
    unique_to_b: frozenset[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "near_duplicate",
            "rule_id_a": self.rule_id_a,
            "rule_id_b": self.rule_id_b,
            "similarity": round(self.similarity, 4),
            "shared_keywords": sorted(self.shared_keywords),
            "unique_to_a": sorted(self.unique_to_a),
            "unique_to_b": sorted(self.unique_to_b),
        }


@dataclass
class DuplicationReport:
    """Full deduplication analysis for a constitution."""

    rule_count: int
    exact_groups: list[ExactDuplicateGroup] = field(default_factory=list)
    subset_pairs: list[SubsetRedundancy] = field(default_factory=list)
    near_duplicate_pairs: list[NearDuplicatePair] = field(default_factory=list)
    near_duplicate_threshold: float = 0.85

    @property
    def has_duplicates(self) -> bool:
        """Return True if any duplicate or near-duplicate rules were found."""
        return bool(self.exact_groups or self.subset_pairs or self.near_duplicate_pairs)

    @property
    def strictly_redundant_ids(self) -> list[str]:
        """Rule IDs that are safe to remove (exact or strict-subset duplicates)."""
        ids: list[str] = []
        for grp in self.exact_groups:
            # Keep the recommended one, remove the rest
            ids.extend(rid for rid in grp.rule_ids if rid != grp.recommended_keep)
        for sub in self.subset_pairs:
            if sub.is_strictly_redundant:
                ids.append(sub.subset_id)
        # Deduplicate while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for rid in ids:
            if rid not in seen:
                seen.add(rid)
                result.append(rid)
        return result

    def summary(self) -> dict[str, Any]:
        return {
            "rule_count": self.rule_count,
            "exact_duplicate_groups": len(self.exact_groups),
            "subset_redundancies": len(self.subset_pairs),
            "strictly_redundant_count": len(self.strictly_redundant_ids),
            "near_duplicate_pairs": len(self.near_duplicate_pairs),
            "near_duplicate_threshold": self.near_duplicate_threshold,
            "has_duplicates": self.has_duplicates,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "exact_groups": [g.to_dict() for g in self.exact_groups],
            "subset_pairs": [s.to_dict() for s in self.subset_pairs],
            "near_duplicate_pairs": [p.to_dict() for p in self.near_duplicate_pairs],
            "strictly_redundant_ids": self.strictly_redundant_ids,
        }

    def render_text(self) -> str:
        """Human-readable summary for CLI/logging output."""
        lines: list[str] = [
            f"Duplication Report — {self.rule_count} rules analysed",
            "=" * 50,
        ]
        if self.exact_groups:
            lines.append(f"\nExact Duplicates ({len(self.exact_groups)} groups):")
            for g in self.exact_groups:
                lines.append(
                    f"  {' = '.join(g.rule_ids)} [severity={g.severity}, keep={g.recommended_keep}]"
                )
        if self.subset_pairs:
            lines.append(f"\nSubset Redundancies ({len(self.subset_pairs)} pairs):")
            for s in self.subset_pairs:
                flag = " [SAFE TO REMOVE]" if s.is_strictly_redundant else ""
                lines.append(f"  {s.subset_id} ⊂ {s.superset_id}{flag}")
        if self.near_duplicate_pairs:
            lines.append(
                f"\nNear-Duplicates >{self.near_duplicate_threshold:.0%} "
                f"similarity ({len(self.near_duplicate_pairs)} pairs):"
            )
            for p in self.near_duplicate_pairs:
                lines.append(
                    f"  {p.rule_id_a} ~ {p.rule_id_b} "
                    f"(Jaccard={p.similarity:.2f}, shared={sorted(p.shared_keywords)})"
                )
        if not self.has_duplicates:
            lines.append("\nNo duplicates found.")
        lines.append(f"\nStrictly redundant IDs: {self.strictly_redundant_ids or 'none'}")
        return "\n".join(lines)


def find_duplicates(
    constitution: Constitution,
    *,
    near_threshold: float = 0.85,
    min_keywords: int = 1,
) -> DuplicationReport:
    """Analyse *constitution* for exact, subset, and near-duplicate rules.

    Only considers **enabled, non-deprecated** rules to avoid false positives
    from intentionally retired rules.

    Args:
        constitution: The constitution to analyse.
        near_threshold: Jaccard similarity threshold for near-duplicate detection
            (default 0.85 — rules sharing 85%+ of keywords).
        min_keywords: Minimum keyword count for a rule to be considered
            (rules with fewer keywords are skipped — too broad to classify).

    Returns:
        :class:`DuplicationReport` with all findings.
    """
    active = [r for r in constitution.rules if r.enabled and not r.deprecated]
    report = DuplicationReport(
        rule_count=len(active),
        near_duplicate_threshold=near_threshold,
    )

    # Build (rule_id, kw_set, severity, category) index
    index = [
        (r.id, _kw_set(r), r.severity.value, r.category)
        for r in active
        if len(r.keywords) >= min_keywords
    ]

    # ── exact duplicates ────────────────────────────────────────────────────
    # Group by (kw_set, severity, category)
    from collections import defaultdict

    exact_buckets: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    for rule_id, kws, sev, cat in index:
        bucket_key = (kws, sev, cat)
        exact_buckets[bucket_key].append(rule_id)

    for (kws, sev, cat), ids in exact_buckets.items():
        if len(ids) > 1:
            # Keep the rule with the shortest (most specific) ID, then alphabetical
            keep = min(ids, key=lambda x: (len(x), x))
            report.exact_groups.append(
                ExactDuplicateGroup(
                    rule_ids=tuple(ids),
                    keywords=kws,
                    severity=sev,
                    category=cat,
                    recommended_keep=keep,
                )
            )

    # Track IDs already flagged as exact duplicates (skip subset/near checks)
    # Keep only the recommended representative from each group for further analysis
    exact_non_keepers: set[str] = {
        rid for grp in report.exact_groups for rid in grp.rule_ids if rid != grp.recommended_keep
    }

    # ── subset redundancies ─────────────────────────────────────────────────
    non_exact = [
        (rid, kws, sev, cat) for rid, kws, sev, cat in index if rid not in exact_non_keepers
    ]

    for i, (id_a, kws_a, sev_a, cat_a) in enumerate(non_exact):
        for id_b, kws_b, sev_b, cat_b in non_exact[i + 1 :]:
            if kws_a < kws_b:  # A is strict subset of B
                report.subset_pairs.append(
                    SubsetRedundancy(
                        subset_id=id_a,
                        superset_id=id_b,
                        subset_keywords=kws_a,
                        superset_keywords=kws_b,
                        shared_severity=(sev_a == sev_b),
                        shared_category=(cat_a == cat_b),
                    )
                )
            elif kws_b < kws_a:  # B is strict subset of A
                report.subset_pairs.append(
                    SubsetRedundancy(
                        subset_id=id_b,
                        superset_id=id_a,
                        subset_keywords=kws_b,
                        superset_keywords=kws_a,
                        shared_severity=(sev_a == sev_b),
                        shared_category=(cat_a == cat_b),
                    )
                )

    # ── near-duplicates ─────────────────────────────────────────────────────
    subset_flagged = {s.subset_id for s in report.subset_pairs}
    candidates = [(rid, kws) for rid, kws, _, _ in non_exact if rid not in subset_flagged]

    for i, (id_a, kws_a) in enumerate(candidates):
        for id_b, kws_b in candidates[i + 1 :]:
            sim = _jaccard(kws_a, kws_b)
            if sim >= near_threshold:
                report.near_duplicate_pairs.append(
                    NearDuplicatePair(
                        rule_id_a=id_a,
                        rule_id_b=id_b,
                        similarity=sim,
                        shared_keywords=kws_a & kws_b,
                        unique_to_a=kws_a - kws_b,
                        unique_to_b=kws_b - kws_a,
                    )
                )

    return report


def deduplicate(
    constitution: Constitution,
    *,
    strategy: str = "keep_highest_severity",
    near_threshold: float = 0.85,
) -> tuple[Constitution, DuplicationReport]:
    """Return a new constitution with strictly redundant rules removed.

    Only removes rules that are **provably safe** to remove:

    - Exact duplicates (keep one per group, per *strategy*)
    - Strict subset redundancies (same severity + category)

    Near-duplicates are reported but **never automatically removed** — they
    require human review.

    Args:
        constitution: The source constitution.
        strategy: How to pick the keeper from an exact duplicate group:
            - ``"keep_highest_severity"``: keep the rule with highest severity
            - ``"keep_oldest"`` (alphabetically smallest ID): stable, reproducible
            - ``"keep_most_keywords"``: keep the rule with most keywords
        near_threshold: Threshold for near-duplicate reporting (not removal).

    Returns:
        Tuple of (new_constitution, DuplicationReport).
    """
    report = find_duplicates(constitution, near_threshold=near_threshold)
    remove_ids = set(report.strictly_redundant_ids)

    if not remove_ids:
        return constitution, report

    # Apply strategy to refine which exact-duplicate to keep
    if strategy in {"keep_highest_severity", "keep_most_keywords"}:
        from .rule import Severity

        _SEV_RANK = {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
        }
        rule_by_id = {r.id: r for r in constitution.rules}

        for grp in report.exact_groups:
            if strategy == "keep_highest_severity":
                keeper = max(
                    grp.rule_ids,
                    key=lambda rid: _SEV_RANK.get(rule_by_id[rid].severity, 0),
                )
            else:  # keep_most_keywords
                keeper = max(grp.rule_ids, key=lambda rid: len(rule_by_id[rid].keywords))

            # Swap the kept rule if strategy differs from default
            for rid in grp.rule_ids:
                if rid == keeper:
                    remove_ids.discard(rid)
                else:
                    remove_ids.add(rid)

    new_rules = [r for r in constitution.rules if r.id not in remove_ids]
    new_constitution = constitution.model_copy(update={"rules": new_rules})
    return new_constitution, report
