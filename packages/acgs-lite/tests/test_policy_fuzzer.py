"""Tests for acgs_lite.constitution.policy_fuzzer module.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import pytest

from acgs_lite.constitution.policy_fuzzer import (
    _STRATEGIES,
    FuzzCase,
    FuzzReport,
    GovernancePolicyFuzzer,
    RuleCoverage,
    _apply_homoglyph,
    _apply_leetspeak,
    _apply_strategy,
    _insert_whitespace,
    _mixed_case,
    _normalize_unicode,
    _synonym_replace,
)

# ---------------------------------------------------------------------------
# Helpers: mock constitution
# ---------------------------------------------------------------------------

@dataclass
class MockRule:
    id: str
    keywords: list[str]


@dataclass
class MockViolation:
    rule_id: str


@dataclass
class MockResult:
    outcome: str
    violations: list[MockViolation]


class MockConstitution:
    """A simple mock constitution for testing the fuzzer."""

    def __init__(self, deny_keywords: list[str] | None = None):
        self._deny_keywords = [kw.lower() for kw in (deny_keywords or ["delete", "hack", "kill"])]
        self.rules = [
            MockRule(id="rule-1", keywords=["delete", "remove"]),
            MockRule(id="rule-2", keywords=["hack", "exploit"]),
            MockRule(id="rule-3", keywords=["kill", "terminate"]),
        ]
        self.constitutional_hash = "608508a9bd224290"

    def validate(self, action: str, context: dict | None = None) -> MockResult:
        action_lower = action.lower()
        violations = []
        for kw in self._deny_keywords:
            if kw in action_lower:
                violations.append(MockViolation(rule_id=f"rule-{kw}"))
        outcome = "deny" if violations else "allow"
        return MockResult(outcome=outcome, violations=violations)


# ---------------------------------------------------------------------------
# Tests: Mutation helpers
# ---------------------------------------------------------------------------

class TestInsertWhitespace:

    def test_inserts_something(self):
        rng = random.Random(42)
        result = _insert_whitespace("hello", rng)
        assert len(result) > len("hello")

    def test_empty_string(self):
        rng = random.Random(42)
        result = _insert_whitespace("", rng)
        assert result == ""

    def test_single_char(self):
        rng = random.Random(42)
        result = _insert_whitespace("a", rng)
        # Should insert at position 0
        assert len(result) == 2


class TestApplyHomoglyph:

    def test_replaces_character(self):
        rng = random.Random(42)
        result = _apply_homoglyph("hello", rng)
        # Should differ from original (most of the time with this seed)
        assert isinstance(result, str)
        assert len(result) == len("hello")

    def test_no_candidates(self):
        rng = random.Random(42)
        result = _apply_homoglyph("12345", rng)
        assert result == "12345"

    def test_empty_string(self):
        rng = random.Random(42)
        result = _apply_homoglyph("", rng)
        assert result == ""


class TestApplyLeetspeak:

    def test_converts(self):
        result = _apply_leetspeak("test")
        # 't'->7, 'e'->3, 's'->5, 't'->7
        assert result == "7357"

    def test_preserves_unmapped(self):
        result = _apply_leetspeak("xyz")
        assert result == "xyz"

    def test_empty(self):
        assert _apply_leetspeak("") == ""


class TestMixedCase:

    def test_changes_case(self):
        rng = random.Random(42)
        result = _mixed_case("hello", rng)
        assert result.lower() == "hello"
        assert len(result) == 5

    def test_empty(self):
        rng = random.Random(42)
        assert _mixed_case("", rng) == ""


class TestSynonymReplace:

    def test_replaces_known_word(self):
        rng = random.Random(42)
        result = _synonym_replace("delete the data", rng)
        # "delete" should be replaced by a synonym
        assert "delete" not in result.lower() or result != "delete the data"

    def test_no_known_words(self):
        rng = random.Random(42)
        result = _synonym_replace("hello world", rng)
        assert result == "hello world"

    def test_empty(self):
        rng = random.Random(42)
        assert _synonym_replace("", rng) == ""


class TestNormalizeUnicode:

    def test_normalizes(self):
        # Composed vs decomposed
        result = _normalize_unicode("\u00e9")  # e with acute
        assert result == "\u00e9"

    def test_ascii_passthrough(self):
        assert _normalize_unicode("hello") == "hello"


# ---------------------------------------------------------------------------
# Tests: _apply_strategy
# ---------------------------------------------------------------------------

class TestApplyStrategy:

    def test_all_strategies_produce_output(self):
        rng = random.Random(42)
        base = "delete the data"
        for strategy in _STRATEGIES:
            result = _apply_strategy(base, strategy, rng)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_prefix_strategy(self):
        rng = random.Random(42)
        result = _apply_strategy("test", "prefix", rng)
        assert result.endswith("test")
        assert len(result) > len("test")

    def test_suffix_strategy(self):
        rng = random.Random(42)
        result = _apply_strategy("test", "suffix", rng)
        assert result.startswith("test")
        assert len(result) > len("test")

    def test_negation_wrap_strategy(self):
        rng = random.Random(42)
        result = _apply_strategy("test", "negation_wrap", rng)
        assert result.endswith("test")

    def test_double_strategy(self):
        rng = random.Random(42)
        result = _apply_strategy("test", "double", rng)
        assert result == "test test"

    def test_context_strip_strategy(self):
        rng = random.Random(42)
        result = _apply_strategy("please do this", "context_strip", rng)
        assert "please" not in result

    def test_unknown_strategy_returns_input(self):
        rng = random.Random(42)
        result = _apply_strategy("test", "nonexistent_strategy", rng)
        assert result == "test"


# ---------------------------------------------------------------------------
# Tests: FuzzCase dataclass
# ---------------------------------------------------------------------------

class TestFuzzCase:

    def test_default_values(self):
        case = FuzzCase(action="test", strategy="homoglyph", seed_action="test", rule_id=None)
        assert case.outcome == "unknown"
        assert case.violations == ()
        assert case.is_suspected_bypass is False
        assert case.metadata == {}

    def test_to_dict(self):
        case = FuzzCase(
            action="mutated",
            strategy="leetspeak",
            seed_action="original",
            rule_id="rule-1",
            outcome="deny",
            violations=("rule-1",),
            is_suspected_bypass=False,
        )
        d = case.to_dict()
        assert d["action"] == "mutated"
        assert d["strategy"] == "leetspeak"
        assert d["violations"] == ["rule-1"]
        assert d["is_suspected_bypass"] is False

    def test_frozen(self):
        case = FuzzCase(action="test", strategy="s", seed_action="s", rule_id=None)
        with pytest.raises(AttributeError):
            case.action = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: RuleCoverage
# ---------------------------------------------------------------------------

class TestRuleCoverage:

    def test_trigger_rate_zero_cases(self):
        cov = RuleCoverage(rule_id="r1")
        assert cov.trigger_rate == 0.0

    def test_trigger_rate(self):
        cov = RuleCoverage(rule_id="r1", triggered_count=5, fuzz_cases_targeting=10)
        assert cov.trigger_rate == pytest.approx(0.5)

    def test_bypass_rate_zero_cases(self):
        cov = RuleCoverage(rule_id="r1")
        assert cov.bypass_rate == 0.0

    def test_bypass_rate(self):
        cov = RuleCoverage(rule_id="r1", bypasses_found=2, fuzz_cases_targeting=10)
        assert cov.bypass_rate == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Tests: FuzzReport
# ---------------------------------------------------------------------------

class TestFuzzReport:

    def _make_report(self, cases=None, rule_coverage=None):
        return FuzzReport(
            constitution_hash="608508a9bd224290",
            seed=42,
            n_cases=len(cases or []),
            started_at="2025-01-01T00:00:00Z",
            finished_at="2025-01-01T00:01:00Z",
            cases=cases or [],
            rule_coverage=rule_coverage or {},
        )

    def test_suspected_bypasses_empty(self):
        report = self._make_report()
        assert report.suspected_bypasses == []
        assert report.bypass_count == 0

    def test_suspected_bypasses(self):
        cases = [
            FuzzCase(action="a", strategy="s", seed_action="b", rule_id=None, is_suspected_bypass=True),
            FuzzCase(action="c", strategy="s", seed_action="d", rule_id=None, is_suspected_bypass=False),
        ]
        report = self._make_report(cases=cases)
        assert report.bypass_count == 1
        assert report.suspected_bypasses[0].action == "a"

    def test_rules_never_triggered(self):
        coverage = {
            "r1": RuleCoverage(rule_id="r1", triggered_count=5, fuzz_cases_targeting=10),
            "r2": RuleCoverage(rule_id="r2", triggered_count=0, fuzz_cases_targeting=10),
        }
        report = self._make_report(rule_coverage=coverage)
        assert "r2" in report.rules_never_triggered
        assert "r1" not in report.rules_never_triggered

    def test_coverage_rate_empty(self):
        report = self._make_report()
        assert report.coverage_rate == 0.0

    def test_coverage_rate(self):
        coverage = {
            "r1": RuleCoverage(rule_id="r1", triggered_count=1),
            "r2": RuleCoverage(rule_id="r2", triggered_count=0),
        }
        report = self._make_report(rule_coverage=coverage)
        assert report.coverage_rate == pytest.approx(0.5)

    def test_summary_contains_key_info(self):
        report = self._make_report()
        summary = report.summary()
        assert "GovernancePolicyFuzzer Report" in summary
        assert "608508a9bd224290" in summary
        assert "42" in summary

    def test_to_dict(self):
        report = self._make_report()
        d = report.to_dict()
        assert d["constitution_hash"] == "608508a9bd224290"
        assert d["seed"] == 42
        assert d["bypass_count"] == 0
        assert isinstance(d["cases"], list)


# ---------------------------------------------------------------------------
# Tests: GovernancePolicyFuzzer
# ---------------------------------------------------------------------------

class TestGovernancePolicyFuzzer:

    def test_init_defaults(self):
        fuzzer = GovernancePolicyFuzzer()
        assert fuzzer._seed == 0
        assert fuzzer._benign_ratio == 0.15

    def test_init_custom_seed(self):
        fuzzer = GovernancePolicyFuzzer(seed=42)
        assert fuzzer._seed == 42

    def test_init_extra_seed_actions(self):
        fuzzer = GovernancePolicyFuzzer(extra_seed_actions=["custom action"])
        assert "custom action" in fuzzer._seed_actions

    def test_init_benign_ratio_clamped(self):
        fuzzer = GovernancePolicyFuzzer(benign_ratio=2.0)
        assert fuzzer._benign_ratio == 1.0

        fuzzer2 = GovernancePolicyFuzzer(benign_ratio=-0.5)
        assert fuzzer2._benign_ratio == 0.0

    def test_generate_cases(self):
        fuzzer = GovernancePolicyFuzzer(seed=42)
        cases = fuzzer.generate_cases(n=10)
        assert len(cases) == 10
        assert all(isinstance(c, str) for c in cases)

    def test_generate_cases_with_keywords(self):
        fuzzer = GovernancePolicyFuzzer(seed=42)
        cases = fuzzer.generate_cases(n=5, target_keywords=["exploit"])
        assert len(cases) == 5

    def test_boundary_probe(self):
        fuzzer = GovernancePolicyFuzzer(seed=42)
        probes = fuzzer.boundary_probe("delete", n_per_strategy=2)
        # 10 strategies * 2 per strategy = 20
        assert len(probes) == len(_STRATEGIES) * 2
        assert all(isinstance(p, str) for p in probes)

    def test_exhaustive_keyword_probe(self):
        fuzzer = GovernancePolicyFuzzer(seed=42)
        probes = fuzzer.exhaustive_keyword_probe(["delete", "hack"], max_combos=10)
        assert len(probes) <= 10
        assert all(isinstance(p, str) for p in probes)

    def test_exhaustive_keyword_probe_custom_prefixes(self):
        fuzzer = GovernancePolicyFuzzer(seed=42)
        probes = fuzzer.exhaustive_keyword_probe(
            ["test"],
            prefixes=["run", "execute"],
            max_combos=5,
        )
        assert len(probes) <= 5


class TestFuzzCampaign:

    def test_fuzz_with_mock_constitution(self):
        fuzzer = GovernancePolicyFuzzer(seed=42)
        constitution = MockConstitution()

        report = fuzzer.fuzz(constitution, n_cases=20)

        assert isinstance(report, FuzzReport)
        assert report.n_cases == 20
        assert report.seed == 42
        assert report.constitution_hash == "608508a9bd224290"
        assert len(report.cases) == 20

    def test_fuzz_produces_rule_coverage(self):
        fuzzer = GovernancePolicyFuzzer(seed=42)
        constitution = MockConstitution()

        report = fuzzer.fuzz(constitution, n_cases=50)

        assert len(report.rule_coverage) > 0

    def test_fuzz_benign_cases_included(self):
        fuzzer = GovernancePolicyFuzzer(seed=42, benign_ratio=0.5)
        constitution = MockConstitution()

        report = fuzzer.fuzz(constitution, n_cases=20)
        benign_cases = [c for c in report.cases if c.strategy == "benign_control"]
        assert len(benign_cases) == 10  # 50% of 20

    def test_fuzz_callable_constitution(self):
        """Test that fuzz works with a callable instead of an object with .validate()."""

        def simple_validator(action, ctx):
            if "bad" in action.lower():
                return ("deny", ["rule-bad"])
            return ("allow", [])

        fuzzer = GovernancePolicyFuzzer(seed=42)
        report = fuzzer.fuzz(simple_validator, n_cases=10)

        assert report.n_cases == 10
        assert report.constitution_hash == ""  # callable has no constitutional_hash

    def test_fuzz_constitution_without_rules(self):
        """Test fuzzer handles constitution without .rules attribute."""

        class MinimalConstitution:
            def validate(self, action, context=None):
                return MockResult(outcome="allow", violations=[])

        fuzzer = GovernancePolicyFuzzer(seed=42)
        report = fuzzer.fuzz(MinimalConstitution(), n_cases=5)
        assert report.n_cases == 5

    def test_fuzz_error_in_validate(self):
        """Test fuzzer handles exceptions from validate gracefully."""

        class BrokenConstitution:
            rules = [MockRule(id="r1", keywords=["test"])]
            constitutional_hash = "608508a9bd224290"

            def validate(self, action, context=None):
                raise RuntimeError("boom")

        fuzzer = GovernancePolicyFuzzer(seed=42)
        report = fuzzer.fuzz(BrokenConstitution(), n_cases=5)

        # All cases should have outcome="error"
        for case in report.cases:
            assert case.outcome == "error"


class TestConstitutionHash:

    def test_hash_from_attribute(self):
        constitution = MockConstitution()
        h = GovernancePolicyFuzzer._constitution_hash(constitution)
        assert h == "608508a9bd224290"

    def test_hash_none_returns_empty(self):
        """When constitutional_hash is None, returns empty string."""

        class NoHash:
            constitutional_hash = None
            rules = [MockRule(id="r1", keywords=["a"])]

        h = GovernancePolicyFuzzer._constitution_hash(NoHash())
        # str(None or "")[:16] = ""
        assert h == ""

    def test_hash_no_attr_returns_empty(self):
        h = GovernancePolicyFuzzer._constitution_hash(42)  # no attrs
        # getattr(42, "constitutional_hash", None) is None => ""
        assert h == ""

    def test_hash_with_value(self):
        class WithHash:
            constitutional_hash = "abcdef0123456789extra"

        h = GovernancePolicyFuzzer._constitution_hash(WithHash())
        assert h == "abcdef0123456789"  # truncated to 16
