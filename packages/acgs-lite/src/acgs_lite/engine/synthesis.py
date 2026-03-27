"""ML-powered rule synthesis from violation pattern analysis.

Analyzes recorded violations to detect recurring patterns, cluster similar
content using Jaccard word-overlap similarity, and suggest new constitutional
rules to close governance gaps.

Constitutional Hash: 608508a9bd224290

Usage::

    from acgs_lite.constitution import Constitution
    from acgs_lite.engine.core import GovernanceEngine
    from acgs_lite.engine.synthesis import AutoSynthesizer

    constitution = Constitution.default()
    engine = GovernanceEngine(constitution)
    synth = AutoSynthesizer(engine, constitution)

    # Observe actions (validates + records violations)
    synth.observe("bypass validation and self-approve", agent_id="bot-1")
    synth.observe("auto-approve merge without review", agent_id="bot-2")
    synth.observe("skip audit trail for deployment", agent_id="bot-3")

    # Synthesize new rules from observed patterns
    report = synth.synthesize()
    for suggestion in report.suggestions:
        print(f"{suggestion.rule_id}: {suggestion.rule_text}")
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.errors import ConstitutionalViolationError

from .types import ValidationResult, Violation

if TYPE_CHECKING:
    from .core import GovernanceEngine

# ── Stopwords for keyword extraction ──────────────────────────────────────

_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "is", "it", "its", "be",
    "was", "were", "been", "being", "have", "has", "had", "do",
    "does", "did", "will", "would", "shall", "should", "may",
    "might", "can", "could", "must", "not", "no", "nor", "so",
    "if", "then", "than", "that", "this", "these", "those",
    "which", "what", "who", "whom", "where", "when", "how",
    "all", "each", "every", "both", "few", "more", "most",
    "other", "some", "such", "only", "own", "same", "too",
    "very", "just", "about", "above", "after", "again",
    "also", "any", "are", "as", "because", "before",
    "between", "during", "into", "out", "over", "under",
    "up", "down", "here", "there", "through", "while",
})

_WORD_RE = re.compile(r"[a-z][a-z0-9_-]{1,}")


# ── Data Classes ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ViolationPattern:
    """A detected pattern across multiple violations."""

    pattern_id: str
    description: str
    frequency: int
    example_content: list[str]
    suggested_severity: Severity
    suggested_category: str
    confidence: float
    first_seen: str
    last_seen: str


@dataclass(frozen=True)
class SuggestedRule:
    """A synthesized rule recommendation based on violation patterns."""

    rule_id: str
    rule_text: str
    severity: Severity
    category: str
    rationale: str
    confidence: float
    based_on_patterns: list[str]
    keywords: list[str]


@dataclass
class SynthesisReport:
    """Complete synthesis analysis report."""

    patterns: list[ViolationPattern]
    suggestions: list[SuggestedRule]
    coverage_gaps: list[str]
    severity_distribution: dict[str, int]
    total_violations_analyzed: int
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report to a plain dictionary."""
        return {
            "patterns": [
                {
                    "pattern_id": p.pattern_id,
                    "description": p.description,
                    "frequency": p.frequency,
                    "example_content": list(p.example_content),
                    "suggested_severity": p.suggested_severity.value,
                    "suggested_category": p.suggested_category,
                    "confidence": p.confidence,
                    "first_seen": p.first_seen,
                    "last_seen": p.last_seen,
                }
                for p in self.patterns
            ],
            "suggestions": [
                {
                    "rule_id": s.rule_id,
                    "rule_text": s.rule_text,
                    "severity": s.severity.value,
                    "category": s.category,
                    "rationale": s.rationale,
                    "confidence": s.confidence,
                    "based_on_patterns": list(s.based_on_patterns),
                    "keywords": list(s.keywords),
                }
                for s in self.suggestions
            ],
            "coverage_gaps": list(self.coverage_gaps),
            "severity_distribution": dict(self.severity_distribution),
            "total_violations_analyzed": self.total_violations_analyzed,
            "generated_at": self.generated_at,
        }


# ── Violation Analyzer ────────────────────────────────────────────────────


def _tokenize(text: str) -> set[str]:
    """Extract a set of lowercase word tokens from text."""
    return set(_WORD_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity coefficient between two token sets."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class _ViolationRecord:
    """Internal record of a single observed violation."""

    rule_id: str
    rule_text: str
    severity: Severity
    matched_content: str
    category: str
    action: str
    timestamp: str


class ViolationAnalyzer:
    """Analyzes recorded violations to extract recurring patterns.

    Uses Jaccard word-overlap similarity to cluster similar violation
    content, then identifies patterns that exceed the minimum frequency
    and confidence thresholds.
    """

    def __init__(
        self,
        *,
        min_frequency: int = 3,
        min_confidence: float = 0.5,
    ) -> None:
        self._min_frequency = max(1, min_frequency)
        self._min_confidence = max(0.0, min(1.0, min_confidence))
        self._records: list[_ViolationRecord] = []

    @property
    def violation_count(self) -> int:
        """Number of violations recorded so far."""
        return len(self._records)

    def clear(self) -> None:
        """Discard all recorded violations."""
        self._records = []

    def record_violation(self, violation: Violation, action: str) -> None:
        """Record a single violation for later pattern analysis."""
        now = datetime.now(timezone.utc).isoformat()
        self._records.append(
            _ViolationRecord(
                rule_id=violation.rule_id,
                rule_text=violation.rule_text,
                severity=violation.severity,
                matched_content=violation.matched_content,
                category=violation.category,
                action=action,
                timestamp=now,
            )
        )

    def record_validation(self, result: ValidationResult) -> None:
        """Bulk-record all violations from a validation result."""
        for v in result.violations:
            self.record_violation(v, result.action)

    def _cluster_content(
        self,
        contents: list[str],
        threshold: float = 0.6,
    ) -> list[list[str]]:
        """Group similar strings by Jaccard word-overlap similarity.

        Single-pass greedy clustering: each new string is added to the
        first cluster whose centroid exceeds the similarity threshold,
        or starts a new cluster otherwise.
        """
        if not contents:
            return []

        token_sets = [_tokenize(c) for c in contents]
        clusters: list[list[int]] = []
        centroids: list[set[str]] = []

        for i, tokens in enumerate(token_sets):
            placed = False
            for ci, centroid in enumerate(centroids):
                if _jaccard(tokens, centroid) >= threshold:
                    clusters[ci].append(i)
                    # Update centroid: intersection of existing and new
                    # keeps words common to the cluster members.
                    centroids[ci] = centroid & tokens
                    placed = True
                    break
            if not placed:
                clusters.append([i])
                centroids.append(set(tokens))

        return [[contents[i] for i in cluster] for cluster in clusters]

    def analyze_patterns(self) -> list[ViolationPattern]:
        """Cluster violations by content similarity and extract patterns.

        Returns patterns that meet the minimum frequency threshold,
        sorted by frequency (highest first).
        """
        if not self._records:
            return []

        # Group by category first, then cluster within each category
        by_category: dict[str, list[_ViolationRecord]] = defaultdict(list)
        for rec in self._records:
            by_category[rec.category].append(rec)

        patterns: list[ViolationPattern] = []
        pattern_counter = 0

        for category, records in sorted(by_category.items()):
            contents = [r.matched_content or r.action for r in records]
            clusters = self._cluster_content(contents)

            for cluster_items in clusters:
                freq = len(cluster_items)
                if freq < self._min_frequency:
                    continue

                pattern_counter += 1
                pid = f"PAT-{pattern_counter:03d}"

                # Find matching records for this cluster
                cluster_set = set(cluster_items)
                matching_records = [
                    r for r in records
                    if (r.matched_content or r.action) in cluster_set
                ]

                # Determine suggested severity: use the most common
                sev_counts: Counter[Severity] = Counter(
                    r.severity for r in matching_records
                )
                suggested_severity = sev_counts.most_common(1)[0][0]

                # Collect truncated examples (max 5, 200 chars each)
                examples = [
                    item[:200] for item in dict.fromkeys(cluster_items)
                ][:5]

                # Confidence: based on cluster cohesion and frequency
                tokens_list = [_tokenize(item) for item in cluster_items]
                if len(tokens_list) >= 2:
                    pair_sims = []
                    for i in range(min(len(tokens_list), 10)):
                        for j in range(i + 1, min(len(tokens_list), 10)):
                            pair_sims.append(
                                _jaccard(tokens_list[i], tokens_list[j])
                            )
                    avg_sim = (
                        sum(pair_sims) / len(pair_sims)
                        if pair_sims
                        else 0.0
                    )
                else:
                    avg_sim = 1.0

                freq_factor = min(1.0, freq / 10.0)
                confidence = round(
                    0.4 * avg_sim + 0.6 * freq_factor, 3
                )

                # Timestamps
                timestamps = sorted(r.timestamp for r in matching_records)
                first_seen = timestamps[0] if timestamps else ""
                last_seen = timestamps[-1] if timestamps else ""

                # Generate description from common words
                all_tokens = _tokenize(" ".join(cluster_items))
                common_words = sorted(
                    all_tokens - _STOPWORDS, key=lambda w: -len(w)
                )[:5]
                desc = (
                    f"Recurring {category} violations involving: "
                    f"{', '.join(common_words)}"
                    if common_words
                    else f"Recurring {category} violations"
                )

                patterns.append(ViolationPattern(
                    pattern_id=pid,
                    description=desc,
                    frequency=freq,
                    example_content=examples,
                    suggested_severity=suggested_severity,
                    suggested_category=category,
                    confidence=confidence,
                    first_seen=first_seen,
                    last_seen=last_seen,
                ))

        return sorted(patterns, key=lambda p: -p.frequency)


# ── Rule Synthesizer ──────────────────────────────────────────────────────


class RuleSynthesizer:
    """Generates rule suggestions from violation patterns.

    Analyzes coverage gaps (categories with violations but no rules)
    and severity mismatches, then produces concrete rule suggestions
    with rationale.
    """

    def __init__(
        self,
        constitution: Constitution,
        *,
        analyzer: ViolationAnalyzer | None = None,
    ) -> None:
        self._constitution = constitution
        self._analyzer = analyzer or ViolationAnalyzer()
        self._rule_counter = 0

    def _next_rule_id(self) -> str:
        """Generate the next sequential rule ID."""
        self._rule_counter += 1
        return f"SYNTH-{self._rule_counter:03d}"

    def _extract_keywords(
        self,
        texts: list[str],
        *,
        max_keywords: int = 8,
    ) -> list[str]:
        """Extract common significant words from violation texts.

        Filters stopwords and returns the most frequent non-trivial
        words across all provided texts.
        """
        word_counts: Counter[str] = Counter()
        for text in texts:
            tokens = _tokenize(text)
            significant = tokens - _STOPWORDS
            word_counts.update(significant)

        return [
            word
            for word, _ in word_counts.most_common(max_keywords)
            if len(word) > 2
        ]

    def _generate_rule_text(
        self,
        pattern: ViolationPattern,
        keywords: list[str],
    ) -> str:
        """Generate a human-readable rule from a violation pattern."""
        kw_str = ", ".join(keywords[:5]) if keywords else "flagged content"
        category = pattern.suggested_category

        if pattern.suggested_severity in (Severity.CRITICAL, Severity.HIGH):
            verb = "must not"
        else:
            verb = "should avoid"

        return (
            f"Agents {verb} produce content involving "
            f"{kw_str} in the {category} domain"
        )

    def _find_coverage_gaps(
        self,
        patterns: list[ViolationPattern],
    ) -> list[str]:
        """Identify categories with violation patterns but no rules."""
        rule_categories = {
            r.category for r in self._constitution.rules
        }
        pattern_categories = {p.suggested_category for p in patterns}
        return sorted(pattern_categories - rule_categories)

    def _find_severity_mismatches(
        self,
        patterns: list[ViolationPattern],
    ) -> list[tuple[ViolationPattern, Severity]]:
        """Find patterns whose severity exceeds existing rules.

        Returns (pattern, existing_rule_severity) pairs where the
        pattern's suggested severity is higher than the maximum
        severity of rules in the same category.
        """
        severity_order = {
            Severity.LOW: 0,
            Severity.MEDIUM: 1,
            Severity.HIGH: 2,
            Severity.CRITICAL: 3,
        }

        category_max_severity: dict[str, Severity] = {}
        for rule in self._constitution.rules:
            cat = rule.category
            if (
                cat not in category_max_severity
                or severity_order.get(rule.severity, 0)
                > severity_order.get(category_max_severity[cat], 0)
            ):
                category_max_severity[cat] = rule.severity

        mismatches: list[tuple[ViolationPattern, Severity]] = []
        for pattern in patterns:
            cat = pattern.suggested_category
            if cat in category_max_severity:
                existing = category_max_severity[cat]
                if severity_order.get(
                    pattern.suggested_severity, 0
                ) > severity_order.get(existing, 0):
                    mismatches.append((pattern, existing))
        return mismatches

    def suggest_rules(
        self,
        patterns: list[ViolationPattern] | None = None,
    ) -> list[SuggestedRule]:
        """Generate rule suggestions from violation patterns.

        If no patterns are provided, runs the internal analyzer to
        detect them. Suggestions are generated for:
        - Coverage gaps: categories with violations but no rules
        - Severity mismatches: violations at higher severity than rules
        - High-frequency patterns: recurring violation clusters
        """
        if patterns is None:
            patterns = self._analyzer.analyze_patterns()

        if not patterns:
            return []

        suggestions: list[SuggestedRule] = []

        # Coverage gap suggestions
        coverage_gaps = self._find_coverage_gaps(patterns)
        gap_patterns = [
            p for p in patterns
            if p.suggested_category in coverage_gaps
        ]
        for pattern in gap_patterns:
            keywords = self._extract_keywords(pattern.example_content)
            rule_text = self._generate_rule_text(pattern, keywords)
            suggestions.append(SuggestedRule(
                rule_id=self._next_rule_id(),
                rule_text=rule_text,
                severity=pattern.suggested_severity,
                category=pattern.suggested_category,
                rationale=(
                    f"Coverage gap: no existing rules cover the "
                    f"'{pattern.suggested_category}' category, but "
                    f"{pattern.frequency} violations were observed"
                ),
                confidence=pattern.confidence,
                based_on_patterns=[pattern.pattern_id],
                keywords=keywords,
            ))

        # Severity mismatch suggestions
        mismatches = self._find_severity_mismatches(patterns)
        for pattern, existing_sev in mismatches:
            keywords = self._extract_keywords(pattern.example_content)
            rule_text = self._generate_rule_text(pattern, keywords)
            suggestions.append(SuggestedRule(
                rule_id=self._next_rule_id(),
                rule_text=rule_text,
                severity=pattern.suggested_severity,
                category=pattern.suggested_category,
                rationale=(
                    f"Severity escalation: violations at "
                    f"{pattern.suggested_severity.value} level but "
                    f"existing rules max at {existing_sev.value} "
                    f"in '{pattern.suggested_category}' category"
                ),
                confidence=pattern.confidence,
                based_on_patterns=[pattern.pattern_id],
                keywords=keywords,
            ))

        # General high-frequency pattern suggestions (not already covered)
        covered_pattern_ids = {
            pid
            for s in suggestions
            for pid in s.based_on_patterns
        }
        for pattern in patterns:
            if pattern.pattern_id in covered_pattern_ids:
                continue
            if pattern.confidence < self._analyzer._min_confidence:
                continue

            keywords = self._extract_keywords(pattern.example_content)
            rule_text = self._generate_rule_text(pattern, keywords)
            suggestions.append(SuggestedRule(
                rule_id=self._next_rule_id(),
                rule_text=rule_text,
                severity=pattern.suggested_severity,
                category=pattern.suggested_category,
                rationale=(
                    f"Recurring pattern: {pattern.frequency} similar "
                    f"violations detected with {pattern.confidence:.0%} "
                    f"confidence"
                ),
                confidence=pattern.confidence,
                based_on_patterns=[pattern.pattern_id],
                keywords=keywords,
            ))

        return sorted(suggestions, key=lambda s: -s.confidence)

    def preview_constitution(
        self,
        suggestions: list[SuggestedRule],
    ) -> Constitution:
        """Return a new Constitution with suggested rules added.

        Non-mutating: the original constitution is not modified.
        """
        new_rules = list(self._constitution.rules)
        for suggestion in suggestions:
            new_rules.append(Rule(
                id=suggestion.rule_id,
                text=suggestion.rule_text,
                severity=suggestion.severity,
                category=suggestion.category,
                keywords=list(suggestion.keywords),
                tags=["synthesized"],
            ))
        return Constitution(
            name=self._constitution.name,
            version=self._constitution.version,
            rules=new_rules,
            description=self._constitution.description,
            metadata={
                **self._constitution.metadata,
                "synthesized_rules": len(suggestions),
            },
        )


# ── Auto Synthesizer ──────────────────────────────────────────────────────


class AutoSynthesizer:
    """Convenience wrapper: observe actions and synthesize rules.

    Combines a GovernanceEngine for validation with a ViolationAnalyzer
    and RuleSynthesizer for pattern detection and rule suggestion.
    """

    def __init__(
        self,
        engine: GovernanceEngine,
        constitution: Constitution,
    ) -> None:
        # Avoid circular import at module level
        from .core import GovernanceEngine as _GE

        if not isinstance(engine, _GE):
            raise TypeError(
                f"engine must be a GovernanceEngine, got {type(engine)}"
            )
        self._engine = engine
        self._constitution = constitution
        self._analyzer = ViolationAnalyzer()
        self._synthesizer = RuleSynthesizer(
            constitution, analyzer=self._analyzer
        )
        self._observations = 0

    def observe(
        self,
        text: str,
        agent_id: str = "anonymous",
    ) -> ValidationResult:
        """Validate text and auto-record any violations for analysis.

        If the engine raises ConstitutionalViolationError (strict mode
        with CRITICAL violations), the error is caught and a synthetic
        ValidationResult is returned so the violation is still recorded.
        """
        try:
            result = self._engine.validate(text, agent_id=agent_id)
        except ConstitutionalViolationError as exc:
            # Engine raises on CRITICAL violations in strict mode.
            # Build a result from the exception so we can still record.
            violation = Violation(
                rule_id=exc.rule_id or "UNKNOWN",
                rule_text=str(exc),
                severity=Severity(exc.severity),
                matched_content=text[:200],
                category="",
            )
            result = ValidationResult(
                valid=False,
                constitutional_hash=self._constitution.hash,
                violations=[violation],
                rules_checked=len(self._constitution.rules),
                action=text,
                agent_id=agent_id,
            )
        self._observations += 1
        if result.violations:
            self._analyzer.record_validation(result)
        return result

    def synthesize(self) -> SynthesisReport:
        """Analyze recorded violations and generate a full report."""
        patterns = self._analyzer.analyze_patterns()
        suggestions = self._synthesizer.suggest_rules(patterns)

        # Coverage gaps
        rule_categories = {
            r.category for r in self._constitution.rules
        }
        pattern_categories = {p.suggested_category for p in patterns}
        coverage_gaps = sorted(pattern_categories - rule_categories)

        # Severity distribution
        severity_dist: dict[str, int] = {}
        for rec in self._analyzer._records:
            key = rec.severity.value
            severity_dist[key] = severity_dist.get(key, 0) + 1

        return SynthesisReport(
            patterns=patterns,
            suggestions=suggestions,
            coverage_gaps=coverage_gaps,
            severity_distribution=severity_dist,
            total_violations_analyzed=self._analyzer.violation_count,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    @property
    def stats(self) -> dict[str, Any]:
        """Current observation and analysis statistics."""
        return {
            "observations": self._observations,
            "violations_recorded": self._analyzer.violation_count,
            "constitution_rules": len(self._constitution.rules),
            "constitution_hash": self._constitution.hash,
        }
