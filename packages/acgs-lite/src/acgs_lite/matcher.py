# ACGS - Constitutional AI Governance
# Copyright (C) 2024-2026 ACGS Contributors
# Licensed under AGPL-3.0-or-later. See LICENSE for details.
# Commercial license: https://acgs.ai

"""High-performance multi-pattern matching for constitutional rule evaluation.

Implements three tiers of optimization:
1. Aho-Corasick automaton (O(N+M)) — when pyahocorasick is installed
2. Pre-compiled keyword index with context-aware matching — always available
3. Bloom filter fast path for "definitely clean" detection — always available

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from acgs_lite.constitution import Rule

# ── Optional Aho-Corasick ────────────────────────────────────────────────────
try:
    import ahocorasick as _ac

    _HAS_AHO = True
except ImportError:
    _HAS_AHO = False


# ── Positive / Negative context verbs ────────────────────────────────────────
_POSITIVE_VERBS: frozenset[str] = frozenset(
    {
        "run",
        "test",
        "generate",
        "create",
        "schedule",
        "implement",
        "log",
        "enable",
        "assign",
        "establish",
        "publish",
        "disclose",
        "build",
        "review",
        "audit",
        "check",
        "verify",
        "assess",
        "evaluate",
        "report",
        "document",
        "plan",
        "prepare",
        "anonymize",
        "share",
        "update",  # parity with constitution.py _POSITIVE_VERBS_SET
    }
)

_NEGATIVE_PHRASES: tuple[str, ...] = (
    "without",
    "disable",
    "bypass",
    "remove",
    "skip",
    "no ",
    "delete",
    "override",
    "hide",
    "obfuscate",
    "auto-reject",
    "self-approve",
    "self-validate",
    "delegate entirely",
    "store biometric",
    "export customer",
    "cross-reference",
    "let ai system self",
    "process customer pii",
    "use zip code",
    "deploy loan approval model with known",
    "deploy hiring model without",
)

_NEGATIVE_KEYWORD_MARKERS: tuple[str, ...] = (
    "without",
    "disable",
    "bypass",
    "remove",
    "skip",
    "delete",
    "override",
    "hide",
    "auto-reject",
    "self-approve",
    "proxy for",
)


@dataclass
class MatchResult:
    """A single match of a rule against text."""

    rule: Rule
    keyword: str
    position: int = -1  # byte offset in text where match occurred


# ── Bloom Filter ─────────────────────────────────────────────────────────────


class _BloomFilter:
    """Simple Bloom filter for fast negative detection.

    Uses FNV-1a-inspired hashing for speed. False positive rate ~1% at
    10 bits/element with 7 hash functions.
    """

    __slots__ = ("_bits", "_size", "_num_hashes")

    def __init__(self, items: list[str], fp_rate: float = 0.01) -> None:
        import math

        n = max(len(items), 1)
        # Optimal size: -n*ln(p) / (ln2)^2
        self._size = max(int(-n * math.log(fp_rate) / (math.log(2) ** 2)), 64)
        # Optimal hash count: (m/n) * ln2
        self._num_hashes = max(int((self._size / n) * math.log(2)), 1)
        self._bits = bytearray(self._size)

        for item in items:
            for h in self._hashes(item):
                self._bits[h] = 1

    def _hashes(self, item: str) -> list[int]:
        """Generate k hash positions using double-hashing."""
        # Two base hashes from built-in hash + shifted hash
        h1 = hash(item) % self._size
        h2 = hash(item + "\x00") % self._size
        if h2 == 0:
            h2 = 1
        return [(h1 + i * h2) % self._size for i in range(self._num_hashes)]

    def might_contain(self, item: str) -> bool:
        """Check if item MIGHT be in the set. False = definitely not."""
        return all(self._bits[h] for h in self._hashes(item))


# ── Aho-Corasick Automaton ───────────────────────────────────────────────────


class _AhoCorasickMatcher:
    """Wraps pyahocorasick for single-pass multi-pattern matching."""

    __slots__ = ("_automaton", "_keyword_to_rules")

    def __init__(self, rules: list[Rule]) -> None:
        self._automaton = _ac.Automaton()
        self._keyword_to_rules: dict[str, list[Rule]] = defaultdict(list)

        for rule in rules:
            if not rule.enabled:
                continue
            for kw in rule.keywords:
                kw_lower = kw.lower()
                self._keyword_to_rules[kw_lower].append(rule)
                # add_word is idempotent for duplicate keys
                self._automaton.add_word(kw_lower, kw_lower)

        if self._automaton:
            self._automaton.make_automaton()

    def search(self, text: str) -> list[MatchResult]:
        """Single-pass search returning all matches."""
        if not self._automaton:
            return []

        text_lower = text.lower()
        results: list[MatchResult] = []
        seen_rules: set[str] = set()

        for end_idx, keyword in self._automaton.iter(text_lower):
            for rule in self._keyword_to_rules[keyword]:
                if rule.id not in seen_rules:
                    seen_rules.add(rule.id)
                    results.append(
                        MatchResult(
                            rule=rule,
                            keyword=keyword,
                            position=end_idx - len(keyword) + 1,
                        )
                    )

        return results


# ── Compiled Rule Index (Pure Python fallback) ───────────────────────────────


class _CompiledRuleIndex:
    """Pre-compiled keyword index for fast matching without Aho-Corasick."""

    __slots__ = ("_keyword_to_rules", "_all_keywords")

    def __init__(self, rules: list[Rule]) -> None:
        self._keyword_to_rules: dict[str, list[Rule]] = defaultdict(list)
        self._all_keywords: list[str] = []

        for rule in rules:
            if not rule.enabled:
                continue
            for kw in rule.keywords:
                kw_lower = kw.lower()
                self._keyword_to_rules[kw_lower].append(rule)
                self._all_keywords.append(kw_lower)

    def search(self, text: str) -> list[MatchResult]:
        """Linear scan with pre-lowered keywords."""
        text_lower = text.lower()
        results: list[MatchResult] = []
        seen_rules: set[str] = set()

        for kw_lower, rules in self._keyword_to_rules.items():
            pos = text_lower.find(kw_lower)
            if pos != -1:
                for rule in rules:
                    if rule.id not in seen_rules:
                        seen_rules.add(rule.id)
                        results.append(
                            MatchResult(
                                rule=rule,
                                keyword=kw_lower,
                                position=pos,
                            )
                        )

        return results


# ── Main Matcher ─────────────────────────────────────────────────────────────


class ConstitutionMatcher:
    """High-performance constitution matcher with context-aware filtering.

    Automatically selects the best available algorithm:
    - Aho-Corasick if pyahocorasick is installed
    - Pre-compiled index otherwise

    Applies context-aware filtering to reduce false positives:
    positive action verbs + no negative signals → skip general keywords.

    Usage::

        matcher = ConstitutionMatcher(constitution.active_rules())
        matches = matcher.match(action_text)
        # matches is a list of (Rule, keyword) tuples
    """

    __slots__ = (
        "_rules",
        "_aho",
        "_index",
        "_bloom",
        "_regex_rules",
        "_compiled_regexes",
    )

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules

        # Build the keyword matcher (Aho-Corasick or fallback)
        if _HAS_AHO:
            self._aho: _AhoCorasickMatcher | None = _AhoCorasickMatcher(rules)
            self._index: _CompiledRuleIndex | None = None
        else:
            self._aho = None
            self._index = _CompiledRuleIndex(rules)

        # Build Bloom filter from all keyword words (for fast negative path)
        all_words: list[str] = []
        for rule in rules:
            if rule.enabled:
                for kw in rule.keywords:
                    all_words.extend(kw.lower().split())
        self._bloom = _BloomFilter(all_words) if all_words else None

        # Pre-compile regex patterns
        self._regex_rules: list[tuple[Rule, list[Any]]] = []
        for rule in rules:
            if rule.enabled and rule.patterns:
                import re

                compiled = [re.compile(p, re.IGNORECASE) for p in rule.patterns]
                self._regex_rules.append((rule, compiled))

    @property
    def has_aho_corasick(self) -> bool:
        """Whether the fast Aho-Corasick backend is available."""
        return self._aho is not None

    def match(self, text: str) -> list[MatchResult]:
        """Match text against all rules with context-aware filtering.

        Returns list of MatchResult for rules that the text violates.
        """
        text_lower = text.lower()

        # ── Fast path: Bloom filter check ────────────────────────────────
        if self._bloom is not None:
            words = text_lower.split()
            if not any(self._bloom.might_contain(w) for w in words):
                # Bloom says definitely no keyword words → skip keyword matching
                # Still need to check regex patterns
                return self._check_regex_only(text)

        # ── Keyword matching ─────────────────────────────────────────────
        if self._aho is not None:
            raw_matches = self._aho.search(text)
        else:
            assert self._index is not None
            raw_matches = self._index.search(text)

        # ── Context-aware filtering ──────────────────────────────────────
        filtered = self._apply_context_filter(text_lower, raw_matches)

        # ── Regex matching ───────────────────────────────────────────────
        seen_rule_ids = {m.rule.id for m in filtered}
        for rule, compiled_patterns in self._regex_rules:
            if rule.id in seen_rule_ids:
                continue
            for pattern in compiled_patterns:
                m = pattern.search(text)
                if m:
                    filtered.append(
                        MatchResult(
                            rule=rule,
                            keyword=f"regex:{pattern.pattern[:30]}",
                            position=m.start(),
                        )
                    )
                    seen_rule_ids.add(rule.id)
                    break

        return filtered

    def _check_regex_only(self, text: str) -> list[MatchResult]:
        """Check only regex patterns (when Bloom filter says no keywords)."""
        results: list[MatchResult] = []
        for rule, compiled_patterns in self._regex_rules:
            for pattern in compiled_patterns:
                m = pattern.search(text)
                if m:
                    results.append(
                        MatchResult(
                            rule=rule,
                            keyword=f"regex:{pattern.pattern[:30]}",
                            position=m.start(),
                        )
                    )
                    break
        return results

    def _apply_context_filter(
        self, text_lower: str, raw_matches: list[MatchResult]
    ) -> list[MatchResult]:
        """Filter out false positives from positive/constructive actions."""
        if not raw_matches:
            return []

        # Detect negative signal (violation indicators)
        has_negative = any(neg in text_lower for neg in _NEGATIVE_PHRASES)

        if has_negative:
            # Negative signal present → all matches are real violations
            return raw_matches

        # Detect positive signal (constructive action verbs at start)
        first_words = text_lower.split()[:4]
        has_positive = any(w in _POSITIVE_VERBS for w in first_words)

        if not has_positive:
            # No strong positive signal → keep all matches
            return raw_matches

        # Positive context + no negative → filter out general keywords
        filtered: list[MatchResult] = []
        for match in raw_matches:
            kw = match.keyword
            # Keep if keyword itself contains a negative verb marker
            kw_has_negative = any(neg in kw for neg in _NEGATIVE_KEYWORD_MARKERS)
            if kw_has_negative:
                filtered.append(match)
            # else: skip — general keyword in positive context

        return filtered
