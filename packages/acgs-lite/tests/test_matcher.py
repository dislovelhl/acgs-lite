"""Tests for acgs_lite.matcher — ConstitutionMatcher and helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from acgs_lite.matcher import (
    _HAS_AHO,
    _NEGATIVE_PHRASES,
    _POSITIVE_VERBS,
    ConstitutionMatcher,
    _BloomFilter,
    _CompiledRuleIndex,
)

# ---------------------------------------------------------------------------
# Minimal Rule stub — matches the fields the matcher reads
# ---------------------------------------------------------------------------


@dataclass
class _FakeRule:
    id: str
    text: str = ""
    keywords: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    enabled: bool = True
    severity: str = "high"
    category: str = "general"


# ---------------------------------------------------------------------------
# _BloomFilter
# ---------------------------------------------------------------------------


class TestBloomFilter:
    def test_definitely_not_present(self) -> None:
        bf = _BloomFilter(["alpha", "beta", "gamma"])
        # "zzzzzzz" is very unlikely to match
        assert bf.might_contain("zzzzzzz") is False

    def test_present_items_detected(self) -> None:
        items = ["alpha", "beta", "gamma"]
        bf = _BloomFilter(items)
        for item in items:
            assert bf.might_contain(item) is True

    def test_empty_items(self) -> None:
        bf = _BloomFilter([])
        assert bf.might_contain("anything") is False

    def test_custom_fp_rate(self) -> None:
        bf = _BloomFilter(["a", "b", "c"], fp_rate=0.5)
        # Should still create a valid filter
        assert bf._size > 0
        assert bf._num_hashes >= 1


# ---------------------------------------------------------------------------
# _CompiledRuleIndex
# ---------------------------------------------------------------------------


class TestCompiledRuleIndex:
    def test_finds_keyword(self) -> None:
        rule = _FakeRule(id="r1", keywords=["password"])
        index = _CompiledRuleIndex([rule])  # type: ignore[arg-type]
        results = index.search("store the password in plaintext")
        assert len(results) == 1
        assert results[0].rule.id == "r1"

    def test_no_match(self) -> None:
        rule = _FakeRule(id="r1", keywords=["password"])
        index = _CompiledRuleIndex([rule])  # type: ignore[arg-type]
        results = index.search("store the secret in vault")
        assert results == []

    def test_case_insensitive(self) -> None:
        rule = _FakeRule(id="r1", keywords=["Password"])
        index = _CompiledRuleIndex([rule])  # type: ignore[arg-type]
        results = index.search("Enter PASSWORD here")
        assert len(results) == 1

    def test_skips_disabled_rules(self) -> None:
        rule = _FakeRule(id="r1", keywords=["test"], enabled=False)
        index = _CompiledRuleIndex([rule])  # type: ignore[arg-type]
        results = index.search("this is a test")
        assert results == []

    def test_deduplicates_rules(self) -> None:
        rule = _FakeRule(id="r1", keywords=["alpha", "beta"])
        index = _CompiledRuleIndex([rule])  # type: ignore[arg-type]
        results = index.search("alpha and beta together")
        # Should appear only once despite two keyword matches
        assert len(results) == 1


# ---------------------------------------------------------------------------
# ConstitutionMatcher
# ---------------------------------------------------------------------------


class TestConstitutionMatcher:
    def test_match_keyword(self) -> None:
        rule = _FakeRule(id="r1", keywords=["bypass"])
        matcher = ConstitutionMatcher([rule])  # type: ignore[arg-type]
        results = matcher.match("bypass the security check")
        assert len(results) == 1
        assert results[0].keyword == "bypass"

    def test_match_no_rules(self) -> None:
        matcher = ConstitutionMatcher([])
        results = matcher.match("anything")
        assert results == []

    def test_match_regex_pattern(self) -> None:
        rule = _FakeRule(id="r1", keywords=[], patterns=[r"SSN-\d{3}-\d{2}-\d{4}"])
        matcher = ConstitutionMatcher([rule])  # type: ignore[arg-type]
        results = matcher.match("found SSN-123-45-6789 in logs")
        assert len(results) == 1
        assert results[0].keyword.startswith("regex:")

    def test_regex_no_match(self) -> None:
        rule = _FakeRule(id="r1", keywords=[], patterns=[r"SSN-\d{3}"])
        matcher = ConstitutionMatcher([rule])  # type: ignore[arg-type]
        results = matcher.match("no social security numbers here")
        assert results == []

    def test_context_filter_positive_action_filters_general(self) -> None:
        """Positive verbs + no negative signal -> general keywords filtered out."""
        rule = _FakeRule(id="r1", keywords=["security"])
        matcher = ConstitutionMatcher([rule])  # type: ignore[arg-type]
        # "run" is a positive verb, "security" is a general keyword
        results = matcher.match("run security assessment on the system")
        assert results == []

    def test_context_filter_negative_signal_keeps_all(self) -> None:
        """Negative signal present -> all matches kept."""
        rule = _FakeRule(id="r1", keywords=["security"])
        matcher = ConstitutionMatcher([rule])  # type: ignore[arg-type]
        results = matcher.match("bypass security check without authorization")
        assert len(results) == 1

    def test_context_filter_keeps_negative_keywords(self) -> None:
        """Even in positive context, keywords with negative markers are kept."""
        rule = _FakeRule(id="r1", keywords=["bypass authentication"])
        matcher = ConstitutionMatcher([rule])  # type: ignore[arg-type]
        results = matcher.match("run bypass authentication on the server")
        assert len(results) == 1

    def test_no_positive_no_negative_keeps_all(self) -> None:
        """No strong signals either way -> keep all matches."""
        rule = _FakeRule(id="r1", keywords=["data"])
        matcher = ConstitutionMatcher([rule])  # type: ignore[arg-type]
        results = matcher.match("the data is stored somewhere")
        assert len(results) == 1

    def test_bloom_filter_fast_path(self) -> None:
        """When bloom says definitely no keywords, only regex checked."""
        rule_kw = _FakeRule(id="r1", keywords=["xyzspecialword"])
        rule_rx = _FakeRule(id="r2", patterns=[r"PATTERN\d+"])
        matcher = ConstitutionMatcher([rule_kw, rule_rx])  # type: ignore[arg-type]
        # Text has no keyword words, but matches regex
        results = matcher.match("found PATTERN42 here")
        # r2 should match via regex, r1 should not
        matched_ids = {r.rule.id for r in results}
        assert "r2" in matched_ids

    def test_has_aho_corasick_property(self) -> None:
        matcher = ConstitutionMatcher([])
        # Should match the availability of the library
        assert matcher.has_aho_corasick == _HAS_AHO

    def test_multiple_rules_multiple_keywords(self) -> None:
        r1 = _FakeRule(id="r1", keywords=["delete"])
        r2 = _FakeRule(id="r2", keywords=["override"])
        matcher = ConstitutionMatcher([r1, r2])  # type: ignore[arg-type]
        results = matcher.match("delete and override the config")
        matched_ids = {r.rule.id for r in results}
        assert "r1" in matched_ids
        assert "r2" in matched_ids

    def test_keyword_and_regex_dedup(self) -> None:
        """If a rule matches by keyword, regex does not add it again."""
        rule = _FakeRule(id="r1", keywords=["bypass"], patterns=[r"bypass"])
        matcher = ConstitutionMatcher([rule])  # type: ignore[arg-type]
        results = matcher.match("bypass the gate")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


class TestConstants:
    def test_positive_verbs_non_empty(self) -> None:
        assert len(_POSITIVE_VERBS) > 10

    def test_negative_phrases_non_empty(self) -> None:
        assert len(_NEGATIVE_PHRASES) > 5

    def test_positive_verbs_are_lowercase(self) -> None:
        for verb in _POSITIVE_VERBS:
            assert verb == verb.lower()
