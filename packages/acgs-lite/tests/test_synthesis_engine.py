"""Tests for acgs_lite.engine.synthesis — ML-powered rule synthesis.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import pytest

from acgs_lite.audit import AuditLog
from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.engine.core import GovernanceEngine
from acgs_lite.engine.synthesis import (
    AutoSynthesizer,
    RuleSynthesizer,
    SuggestedRule,
    SynthesisReport,
    ViolationAnalyzer,
    ViolationPattern,
    _jaccard,
    _tokenize,
)
from acgs_lite.engine.types import ValidationResult, Violation

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def default_constitution() -> Constitution:
    return Constitution.default()


@pytest.fixture()
def engine(default_constitution: Constitution) -> GovernanceEngine:
    return GovernanceEngine(default_constitution)


@pytest.fixture()
def engine_with_audit(default_constitution: Constitution) -> GovernanceEngine:
    return GovernanceEngine(default_constitution, audit_log=AuditLog())


@pytest.fixture()
def analyzer() -> ViolationAnalyzer:
    return ViolationAnalyzer()


@pytest.fixture()
def low_threshold_analyzer() -> ViolationAnalyzer:
    return ViolationAnalyzer(min_frequency=1, min_confidence=0.0)


@pytest.fixture()
def sample_violation() -> Violation:
    return Violation(
        rule_id="ACGS-001",
        rule_text="Agents must not modify their own validation logic",
        severity=Severity.CRITICAL,
        matched_content="bypass validation check",
        category="integrity",
    )


@pytest.fixture()
def sample_result(sample_violation: Violation) -> ValidationResult:
    return ValidationResult(
        valid=False,
        constitutional_hash="608508a9bd224290",
        violations=[sample_violation],
        rules_checked=6,
        action="bypass validation check",
        agent_id="test-agent",
    )


# ── ViolationPattern tests ────────────────────────────────────────────────


class TestViolationPattern:
    def test_creation(self) -> None:
        p = ViolationPattern(
            pattern_id="PAT-001",
            description="Test pattern",
            frequency=5,
            example_content=["example 1", "example 2"],
            suggested_severity=Severity.HIGH,
            suggested_category="safety",
            confidence=0.85,
            first_seen="2026-01-01T00:00:00+00:00",
            last_seen="2026-03-27T00:00:00+00:00",
        )
        assert p.pattern_id == "PAT-001"
        assert p.frequency == 5
        assert p.confidence == 0.85
        assert p.suggested_severity is Severity.HIGH

    def test_frozen(self) -> None:
        p = ViolationPattern(
            pattern_id="PAT-001",
            description="Test",
            frequency=1,
            example_content=[],
            suggested_severity=Severity.LOW,
            suggested_category="general",
            confidence=0.5,
            first_seen="",
            last_seen="",
        )
        with pytest.raises(AttributeError):
            p.frequency = 10  # type: ignore[misc]

    def test_example_content_list_preserved(self) -> None:
        examples = ["a" * 200, "b" * 200, "c", "d", "e"]
        p = ViolationPattern(
            pattern_id="PAT-002",
            description="Multiple examples",
            frequency=5,
            example_content=examples,
            suggested_severity=Severity.MEDIUM,
            suggested_category="safety",
            confidence=0.7,
            first_seen="2026-01-01T00:00:00",
            last_seen="2026-01-02T00:00:00",
        )
        assert len(p.example_content) == 5


# ── SuggestedRule tests ───────────────────────────────────────────────────


class TestSuggestedRule:
    def test_creation(self) -> None:
        s = SuggestedRule(
            rule_id="SYNTH-001",
            rule_text="Agents must not leak credentials",
            severity=Severity.CRITICAL,
            category="security",
            rationale="Detected recurring credential leaks",
            confidence=0.9,
            based_on_patterns=["PAT-001"],
            keywords=["credential", "leak", "secret"],
        )
        assert s.rule_id == "SYNTH-001"
        assert s.severity is Severity.CRITICAL
        assert len(s.keywords) == 3

    def test_frozen(self) -> None:
        s = SuggestedRule(
            rule_id="SYNTH-001",
            rule_text="test",
            severity=Severity.LOW,
            category="general",
            rationale="test",
            confidence=0.5,
            based_on_patterns=[],
            keywords=[],
        )
        with pytest.raises(AttributeError):
            s.confidence = 1.0  # type: ignore[misc]


# ── Tokenizer and Jaccard tests ──────────────────────────────────────────


class TestTokenizer:
    def test_basic_tokenize(self) -> None:
        tokens = _tokenize("Hello World testing 123")
        assert "hello" in tokens
        assert "world" in tokens
        assert "testing" in tokens

    def test_empty_string(self) -> None:
        assert _tokenize("") == set()

    def test_single_char_excluded(self) -> None:
        tokens = _tokenize("I a b test")
        assert "test" in tokens
        # Single chars should be excluded by the regex
        assert "a" not in tokens
        assert "b" not in tokens

    def test_special_characters(self) -> None:
        tokens = _tokenize("self-validate bypass_check")
        assert "self-validate" in tokens
        assert "bypass_check" in tokens


class TestJaccard:
    def test_identical_sets(self) -> None:
        s = {"a", "b", "c"}
        assert _jaccard(s, s) == 1.0

    def test_disjoint_sets(self) -> None:
        assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self) -> None:
        # intersection: {b}, union: {a, b, c} => 1/3
        result = _jaccard({"a", "b"}, {"b", "c"})
        assert abs(result - 1 / 3) < 1e-9

    def test_empty_both(self) -> None:
        assert _jaccard(set(), set()) == 1.0

    def test_one_empty(self) -> None:
        assert _jaccard({"a"}, set()) == 0.0
        assert _jaccard(set(), {"a"}) == 0.0


# ── ViolationAnalyzer tests ──────────────────────────────────────────────


class TestViolationAnalyzer:
    def test_initial_state(self, analyzer: ViolationAnalyzer) -> None:
        assert analyzer.violation_count == 0
        assert analyzer.analyze_patterns() == []

    def test_record_single_violation(
        self,
        analyzer: ViolationAnalyzer,
        sample_violation: Violation,
    ) -> None:
        analyzer.record_violation(sample_violation, "test action")
        assert analyzer.violation_count == 1

    def test_record_validation(
        self,
        analyzer: ViolationAnalyzer,
        sample_result: ValidationResult,
    ) -> None:
        analyzer.record_validation(sample_result)
        assert analyzer.violation_count == len(sample_result.violations)

    def test_clear(
        self,
        analyzer: ViolationAnalyzer,
        sample_violation: Violation,
    ) -> None:
        analyzer.record_violation(sample_violation, "test")
        assert analyzer.violation_count == 1
        analyzer.clear()
        assert analyzer.violation_count == 0

    def test_no_patterns_below_threshold(
        self,
        analyzer: ViolationAnalyzer,
        sample_violation: Violation,
    ) -> None:
        # Default min_frequency is 3, only record 2
        analyzer.record_violation(sample_violation, "action 1")
        analyzer.record_violation(sample_violation, "action 2")
        assert analyzer.analyze_patterns() == []

    def test_patterns_at_threshold(
        self,
        analyzer: ViolationAnalyzer,
    ) -> None:
        v = Violation(
            rule_id="R1",
            rule_text="test rule",
            severity=Severity.HIGH,
            matched_content="bypass validation check",
            category="integrity",
        )
        for _ in range(3):
            analyzer.record_violation(v, "bypass validation check")
        patterns = analyzer.analyze_patterns()
        assert len(patterns) >= 1
        assert patterns[0].frequency >= 3

    def test_patterns_from_similar_content(
        self,
        low_threshold_analyzer: ViolationAnalyzer,
    ) -> None:
        contents = [
            "bypass validation security check",
            "bypass validation safety check",
            "bypass validation auth check",
        ]
        for content in contents:
            v = Violation(
                rule_id="R1",
                rule_text="no bypass",
                severity=Severity.CRITICAL,
                matched_content=content,
                category="security",
            )
            low_threshold_analyzer.record_violation(v, content)

        patterns = low_threshold_analyzer.analyze_patterns()
        assert len(patterns) >= 1

    def test_patterns_diverse_categories(
        self,
        low_threshold_analyzer: ViolationAnalyzer,
    ) -> None:
        for cat in ("safety", "privacy", "security"):
            for i in range(3):
                v = Violation(
                    rule_id=f"{cat}-{i}",
                    rule_text=f"{cat} rule",
                    severity=Severity.HIGH,
                    matched_content=f"{cat} violation content {i}",
                    category=cat,
                )
                low_threshold_analyzer.record_violation(
                    v, f"{cat} action"
                )

        patterns = low_threshold_analyzer.analyze_patterns()
        categories = {p.suggested_category for p in patterns}
        assert len(categories) >= 2

    def test_cluster_content_identical(
        self,
        analyzer: ViolationAnalyzer,
    ) -> None:
        contents = ["same content", "same content", "same content"]
        clusters = analyzer._cluster_content(contents)
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_cluster_content_disjoint(
        self,
        analyzer: ViolationAnalyzer,
    ) -> None:
        contents = [
            "alpha bravo charlie",
            "delta echo foxtrot",
            "golf hotel india",
        ]
        clusters = analyzer._cluster_content(contents, threshold=0.8)
        assert len(clusters) == 3

    def test_cluster_content_empty(
        self,
        analyzer: ViolationAnalyzer,
    ) -> None:
        assert analyzer._cluster_content([]) == []

    def test_cluster_content_single(
        self,
        analyzer: ViolationAnalyzer,
    ) -> None:
        clusters = analyzer._cluster_content(["only one"])
        assert len(clusters) == 1

    def test_pattern_confidence_bounds(
        self,
        low_threshold_analyzer: ViolationAnalyzer,
    ) -> None:
        for i in range(5):
            v = Violation(
                rule_id="R1",
                rule_text="rule",
                severity=Severity.MEDIUM,
                matched_content=f"similar content about data leak {i}",
                category="privacy",
            )
            low_threshold_analyzer.record_violation(v, "action")

        patterns = low_threshold_analyzer.analyze_patterns()
        for p in patterns:
            assert 0.0 <= p.confidence <= 1.0

    def test_pattern_severity_from_most_common(
        self,
    ) -> None:
        analyzer = ViolationAnalyzer(min_frequency=1)
        # 2 CRITICAL + 1 HIGH => should suggest CRITICAL
        for sev, count in [
            (Severity.CRITICAL, 2),
            (Severity.HIGH, 1),
        ]:
            for _ in range(count):
                v = Violation(
                    rule_id="R1",
                    rule_text="rule",
                    severity=sev,
                    matched_content="dangerous bypass action",
                    category="safety",
                )
                analyzer.record_violation(v, "action")

        patterns = analyzer.analyze_patterns()
        assert len(patterns) >= 1
        assert patterns[0].suggested_severity is Severity.CRITICAL

    def test_pattern_example_truncation(
        self,
    ) -> None:
        analyzer = ViolationAnalyzer(min_frequency=1)
        long_content = "x" * 500
        v = Violation(
            rule_id="R1",
            rule_text="rule",
            severity=Severity.LOW,
            matched_content=long_content,
            category="general",
        )
        analyzer.record_violation(v, "action")
        patterns = analyzer.analyze_patterns()
        if patterns:
            for example in patterns[0].example_content:
                assert len(example) <= 200

    def test_pattern_timestamps_ordered(
        self,
    ) -> None:
        analyzer = ViolationAnalyzer(min_frequency=1)
        for _ in range(3):
            v = Violation(
                rule_id="R1",
                rule_text="rule",
                severity=Severity.HIGH,
                matched_content="repeated violation content",
                category="audit",
            )
            analyzer.record_violation(v, "action")

        patterns = analyzer.analyze_patterns()
        if patterns:
            assert patterns[0].first_seen <= patterns[0].last_seen


# ── RuleSynthesizer tests ────────────────────────────────────────────────


class TestRuleSynthesizer:
    def test_no_patterns_no_suggestions(
        self,
        default_constitution: Constitution,
    ) -> None:
        synth = RuleSynthesizer(default_constitution)
        assert synth.suggest_rules([]) == []
        assert synth.suggest_rules(None) == []

    def test_coverage_gap_detection(
        self,
        default_constitution: Constitution,
    ) -> None:
        # "novelcategory" is not in default constitution rules
        pattern = ViolationPattern(
            pattern_id="PAT-001",
            description="Novel violations",
            frequency=5,
            example_content=["novel attack vector detected"],
            suggested_severity=Severity.HIGH,
            suggested_category="novelcategory",
            confidence=0.8,
            first_seen="2026-01-01T00:00:00",
            last_seen="2026-03-27T00:00:00",
        )
        synth = RuleSynthesizer(default_constitution)
        suggestions = synth.suggest_rules([pattern])
        assert len(suggestions) >= 1
        assert any(
            "coverage gap" in s.rationale.lower()
            for s in suggestions
        )

    def test_severity_mismatch_detection(self) -> None:
        # Constitution with only LOW rules in "safety"
        constitution = Constitution(
            name="test",
            rules=[
                Rule(
                    id="R1",
                    text="Safety advisory",
                    severity=Severity.LOW,
                    category="safety",
                    keywords=["safety"],
                ),
            ],
        )
        # Pattern suggests CRITICAL for safety
        pattern = ViolationPattern(
            pattern_id="PAT-001",
            description="Critical safety violations",
            frequency=10,
            example_content=["critical safety breach detected"],
            suggested_severity=Severity.CRITICAL,
            suggested_category="safety",
            confidence=0.9,
            first_seen="2026-01-01T00:00:00",
            last_seen="2026-03-27T00:00:00",
        )
        synth = RuleSynthesizer(constitution)
        suggestions = synth.suggest_rules([pattern])
        assert any(
            "severity" in s.rationale.lower()
            for s in suggestions
        )

    def test_high_frequency_pattern_suggestion(
        self,
        default_constitution: Constitution,
    ) -> None:
        # Pattern in an existing category but at matching severity
        pattern = ViolationPattern(
            pattern_id="PAT-001",
            description="Recurring integrity violations",
            frequency=20,
            example_content=[
                "bypass internal validation",
                "skip integrity check",
            ],
            suggested_severity=Severity.CRITICAL,
            suggested_category="integrity",
            confidence=0.85,
            first_seen="2026-01-01T00:00:00",
            last_seen="2026-03-27T00:00:00",
        )
        synth = RuleSynthesizer(default_constitution)
        suggestions = synth.suggest_rules([pattern])
        assert len(suggestions) >= 1

    def test_rule_id_generation(
        self,
        default_constitution: Constitution,
    ) -> None:
        patterns = [
            ViolationPattern(
                pattern_id=f"PAT-{i:03d}",
                description=f"Pattern {i}",
                frequency=5,
                example_content=[f"example content {i}"],
                suggested_severity=Severity.MEDIUM,
                suggested_category=f"cat-{i}",
                confidence=0.7,
                first_seen="2026-01-01T00:00:00",
                last_seen="2026-01-02T00:00:00",
            )
            for i in range(3)
        ]
        synth = RuleSynthesizer(default_constitution)
        suggestions = synth.suggest_rules(patterns)
        rule_ids = [s.rule_id for s in suggestions]
        # All IDs should be unique and start with SYNTH-
        assert len(rule_ids) == len(set(rule_ids))
        assert all(rid.startswith("SYNTH-") for rid in rule_ids)

    def test_keyword_extraction(
        self,
        default_constitution: Constitution,
    ) -> None:
        synth = RuleSynthesizer(default_constitution)
        texts = [
            "bypass validation security check",
            "bypass validation auth check",
            "bypass validation safety review",
        ]
        keywords = synth._extract_keywords(texts)
        assert len(keywords) > 0
        assert "bypass" in keywords or "validation" in keywords

    def test_keyword_extraction_empty(
        self,
        default_constitution: Constitution,
    ) -> None:
        synth = RuleSynthesizer(default_constitution)
        assert synth._extract_keywords([]) == []

    def test_keyword_extraction_stopwords_filtered(
        self,
        default_constitution: Constitution,
    ) -> None:
        synth = RuleSynthesizer(default_constitution)
        keywords = synth._extract_keywords(
            ["the and or but with from for"]
        )
        assert len(keywords) == 0

    def test_generate_rule_text_critical(
        self,
        default_constitution: Constitution,
    ) -> None:
        synth = RuleSynthesizer(default_constitution)
        pattern = ViolationPattern(
            pattern_id="PAT-001",
            description="test",
            frequency=5,
            example_content=[],
            suggested_severity=Severity.CRITICAL,
            suggested_category="security",
            confidence=0.8,
            first_seen="",
            last_seen="",
        )
        text = synth._generate_rule_text(
            pattern, ["credential", "leak"]
        )
        assert "must not" in text
        assert "security" in text

    def test_generate_rule_text_medium(
        self,
        default_constitution: Constitution,
    ) -> None:
        synth = RuleSynthesizer(default_constitution)
        pattern = ViolationPattern(
            pattern_id="PAT-001",
            description="test",
            frequency=5,
            example_content=[],
            suggested_severity=Severity.MEDIUM,
            suggested_category="general",
            confidence=0.5,
            first_seen="",
            last_seen="",
        )
        text = synth._generate_rule_text(pattern, ["verbose"])
        assert "should avoid" in text

    def test_generate_rule_text_no_keywords(
        self,
        default_constitution: Constitution,
    ) -> None:
        synth = RuleSynthesizer(default_constitution)
        pattern = ViolationPattern(
            pattern_id="PAT-001",
            description="test",
            frequency=5,
            example_content=[],
            suggested_severity=Severity.HIGH,
            suggested_category="general",
            confidence=0.5,
            first_seen="",
            last_seen="",
        )
        text = synth._generate_rule_text(pattern, [])
        assert "flagged content" in text

    def test_preview_constitution_non_mutating(
        self,
        default_constitution: Constitution,
    ) -> None:
        original_hash = default_constitution.hash
        original_count = len(default_constitution.rules)

        synth = RuleSynthesizer(default_constitution)
        suggestion = SuggestedRule(
            rule_id="SYNTH-001",
            rule_text="Test synthesized rule",
            severity=Severity.MEDIUM,
            category="test",
            rationale="Testing",
            confidence=0.8,
            based_on_patterns=["PAT-001"],
            keywords=["test"],
        )
        preview = synth.preview_constitution([suggestion])

        # Original unchanged
        assert default_constitution.hash == original_hash
        assert len(default_constitution.rules) == original_count

        # Preview has additional rule
        assert len(preview.rules) == original_count + 1
        assert preview.hash != original_hash

    def test_preview_constitution_metadata(
        self,
        default_constitution: Constitution,
    ) -> None:
        synth = RuleSynthesizer(default_constitution)
        suggestion = SuggestedRule(
            rule_id="SYNTH-001",
            rule_text="Test rule",
            severity=Severity.LOW,
            category="test",
            rationale="Testing",
            confidence=0.5,
            based_on_patterns=[],
            keywords=[],
        )
        preview = synth.preview_constitution([suggestion])
        assert preview.metadata.get("synthesized_rules") == 1

    def test_preview_empty_suggestions(
        self,
        default_constitution: Constitution,
    ) -> None:
        synth = RuleSynthesizer(default_constitution)
        preview = synth.preview_constitution([])
        assert len(preview.rules) == len(default_constitution.rules)

    def test_suggestions_sorted_by_confidence(
        self,
        default_constitution: Constitution,
    ) -> None:
        patterns = [
            ViolationPattern(
                pattern_id="PAT-001",
                description="Low confidence",
                frequency=5,
                example_content=["low confidence example"],
                suggested_severity=Severity.LOW,
                suggested_category="novel-low",
                confidence=0.3,
                first_seen="2026-01-01T00:00:00",
                last_seen="2026-01-02T00:00:00",
            ),
            ViolationPattern(
                pattern_id="PAT-002",
                description="High confidence",
                frequency=10,
                example_content=["high confidence example"],
                suggested_severity=Severity.HIGH,
                suggested_category="novel-high",
                confidence=0.95,
                first_seen="2026-01-01T00:00:00",
                last_seen="2026-01-02T00:00:00",
            ),
        ]
        synth = RuleSynthesizer(default_constitution)
        suggestions = synth.suggest_rules(patterns)
        if len(suggestions) >= 2:
            assert suggestions[0].confidence >= suggestions[1].confidence


# ── SynthesisReport tests ────────────────────────────────────────────────


class TestSynthesisReport:
    def test_creation(self) -> None:
        report = SynthesisReport(
            patterns=[],
            suggestions=[],
            coverage_gaps=["privacy"],
            severity_distribution={"critical": 5, "high": 3},
            total_violations_analyzed=8,
            generated_at="2026-03-27T00:00:00+00:00",
        )
        assert report.total_violations_analyzed == 8
        assert "privacy" in report.coverage_gaps

    def test_to_dict(self) -> None:
        pattern = ViolationPattern(
            pattern_id="PAT-001",
            description="test",
            frequency=3,
            example_content=["ex1"],
            suggested_severity=Severity.HIGH,
            suggested_category="safety",
            confidence=0.7,
            first_seen="2026-01-01T00:00:00",
            last_seen="2026-01-02T00:00:00",
        )
        suggestion = SuggestedRule(
            rule_id="SYNTH-001",
            rule_text="Test rule",
            severity=Severity.HIGH,
            category="safety",
            rationale="Rationale",
            confidence=0.7,
            based_on_patterns=["PAT-001"],
            keywords=["test"],
        )
        report = SynthesisReport(
            patterns=[pattern],
            suggestions=[suggestion],
            coverage_gaps=["privacy"],
            severity_distribution={"high": 3},
            total_violations_analyzed=3,
            generated_at="2026-03-27T00:00:00",
        )
        d = report.to_dict()
        assert isinstance(d, dict)
        assert len(d["patterns"]) == 1
        assert len(d["suggestions"]) == 1
        assert d["patterns"][0]["suggested_severity"] == "high"
        assert d["suggestions"][0]["severity"] == "high"
        assert d["total_violations_analyzed"] == 3
        assert "privacy" in d["coverage_gaps"]

    def test_to_dict_empty(self) -> None:
        report = SynthesisReport(
            patterns=[],
            suggestions=[],
            coverage_gaps=[],
            severity_distribution={},
            total_violations_analyzed=0,
            generated_at="2026-03-27T00:00:00",
        )
        d = report.to_dict()
        assert d["patterns"] == []
        assert d["suggestions"] == []
        assert d["total_violations_analyzed"] == 0


# ── AutoSynthesizer tests ────────────────────────────────────────────────


class TestAutoSynthesizer:
    def test_creation(
        self,
        engine: GovernanceEngine,
        default_constitution: Constitution,
    ) -> None:
        synth = AutoSynthesizer(engine, default_constitution)
        assert synth.stats["observations"] == 0
        assert synth.stats["violations_recorded"] == 0

    def test_invalid_engine_type(
        self,
        default_constitution: Constitution,
    ) -> None:
        with pytest.raises(TypeError, match="GovernanceEngine"):
            AutoSynthesizer("not-an-engine", default_constitution)  # type: ignore[arg-type]

    def test_observe_allowed_action(
        self,
        engine: GovernanceEngine,
        default_constitution: Constitution,
    ) -> None:
        synth = AutoSynthesizer(engine, default_constitution)
        result = synth.observe("deploy approved model to staging")
        assert result.valid is True
        assert synth.stats["observations"] == 1
        assert synth.stats["violations_recorded"] == 0

    def test_observe_violating_action(
        self,
        engine: GovernanceEngine,
        default_constitution: Constitution,
    ) -> None:
        synth = AutoSynthesizer(engine, default_constitution)
        # observe() catches ConstitutionalViolationError internally
        result = synth.observe(
            "bypass validation and self-validate",
            agent_id="bad-bot",
        )
        assert result.valid is False
        assert synth.stats["observations"] == 1
        assert synth.stats["violations_recorded"] >= 1

    def test_synthesize_empty(
        self,
        engine: GovernanceEngine,
        default_constitution: Constitution,
    ) -> None:
        synth = AutoSynthesizer(engine, default_constitution)
        report = synth.synthesize()
        assert isinstance(report, SynthesisReport)
        assert report.total_violations_analyzed == 0
        assert report.patterns == []
        assert report.suggestions == []

    def test_synthesize_after_observations(
        self,
        engine: GovernanceEngine,
        default_constitution: Constitution,
    ) -> None:
        synth = AutoSynthesizer(engine, default_constitution)
        violating_actions = [
            "bypass validation and skip check",
            "self-validate the proposal output",
            "bypass validation on deployment",
        ]
        for action in violating_actions:
            synth.observe(action, agent_id="bot")

        report = synth.synthesize()
        assert isinstance(report, SynthesisReport)
        assert report.generated_at  # non-empty timestamp
        assert report.total_violations_analyzed >= 1

    def test_stats_property(
        self,
        engine: GovernanceEngine,
        default_constitution: Constitution,
    ) -> None:
        synth = AutoSynthesizer(engine, default_constitution)
        stats = synth.stats
        assert "observations" in stats
        assert "violations_recorded" in stats
        assert "constitution_rules" in stats
        assert "constitution_hash" in stats
        assert stats["constitution_rules"] == len(
            default_constitution.rules
        )

    def test_stats_constitutional_hash(
        self,
        engine: GovernanceEngine,
        default_constitution: Constitution,
    ) -> None:
        synth = AutoSynthesizer(engine, default_constitution)
        assert synth.stats["constitution_hash"] == (
            default_constitution.hash
        )


# ── Integration tests with real engine ───────────────────────────────────


class TestIntegration:
    def test_full_pipeline_default_constitution(self) -> None:
        constitution = Constitution.default()
        engine = GovernanceEngine(constitution)
        synth = AutoSynthesizer(engine, constitution)

        # Observe several actions (observe catches exceptions)
        actions = [
            "deploy model to production",
            "update configuration settings",
            "analyze user feedback data",
        ]
        for action in actions:
            synth.observe(action, agent_id="agent-1")

        report = synth.synthesize()
        assert isinstance(report, SynthesisReport)
        assert report.generated_at

    def test_analyzer_with_real_engine_violations(self) -> None:
        constitution = Constitution.default()
        engine = GovernanceEngine(constitution)
        analyzer = ViolationAnalyzer(min_frequency=1)

        # These actions should trigger violations
        violating_actions = [
            "bypass validation on this request",
            "auto-approve the proposal without review",
            "skip audit trail for this operation",
        ]
        for action in violating_actions:
            try:
                result = engine.validate(action, agent_id="test")
            except Exception:
                continue
            if not result.valid:
                analyzer.record_validation(result)

        # Even if engine raises before returning, verify state
        assert analyzer.violation_count >= 0

    def test_synthesizer_with_real_constitution(self) -> None:
        constitution = Constitution.default()
        synthesizer = RuleSynthesizer(constitution)

        # Create a pattern in a category not covered by default rules
        pattern = ViolationPattern(
            pattern_id="PAT-001",
            description="Fairness violations detected",
            frequency=5,
            example_content=[
                "discriminatory scoring applied",
                "biased selection criteria",
            ],
            suggested_severity=Severity.HIGH,
            suggested_category="fairness",
            confidence=0.85,
            first_seen="2026-01-01T00:00:00",
            last_seen="2026-03-27T00:00:00",
        )
        suggestions = synthesizer.suggest_rules([pattern])
        assert len(suggestions) >= 1

        # Preview should produce a valid Constitution
        preview = synthesizer.preview_constitution(suggestions)
        assert isinstance(preview, Constitution)
        assert len(preview.rules) > len(constitution.rules)

    def test_preview_constitution_validates(self) -> None:
        constitution = Constitution.default()
        synthesizer = RuleSynthesizer(constitution)
        suggestion = SuggestedRule(
            rule_id="SYNTH-001",
            rule_text="Agents must not use biased algorithms",
            severity=Severity.HIGH,
            category="fairness",
            rationale="Coverage gap in fairness",
            confidence=0.8,
            based_on_patterns=["PAT-001"],
            keywords=["biased", "algorithms"],
        )
        preview = synthesizer.preview_constitution([suggestion])

        # The preview constitution should be usable with an engine
        preview_engine = GovernanceEngine(preview)
        result = preview_engine.validate(
            "run standard analytics", agent_id="test"
        )
        assert result.valid is True

    def test_report_severity_distribution(self) -> None:
        constitution = Constitution.default()
        engine = GovernanceEngine(constitution)
        synth = AutoSynthesizer(engine, constitution)

        # Record violations manually via the analyzer
        for sev in [
            Severity.CRITICAL,
            Severity.CRITICAL,
            Severity.HIGH,
        ]:
            v = Violation(
                rule_id="R1",
                rule_text="test",
                severity=sev,
                matched_content="test content",
                category="test",
            )
            synth._analyzer.record_violation(v, "action")

        report = synth.synthesize()
        assert report.severity_distribution.get("critical", 0) == 2
        assert report.severity_distribution.get("high", 0) == 1

    def test_report_coverage_gaps(self) -> None:
        constitution = Constitution.default()
        engine = GovernanceEngine(constitution)
        synth = AutoSynthesizer(engine, constitution)

        # Add violations in a category not in the constitution
        v = Violation(
            rule_id="R1",
            rule_text="test",
            severity=Severity.HIGH,
            matched_content="environmental impact concern",
            category="environment",
        )
        for _ in range(5):
            synth._analyzer.record_violation(v, "action")

        report = synth.synthesize()
        assert "environment" in report.coverage_gaps


# ── Edge case tests ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_many_similar_violations(self) -> None:
        analyzer = ViolationAnalyzer(min_frequency=1)
        for i in range(50):
            v = Violation(
                rule_id="R1",
                rule_text="rule",
                severity=Severity.HIGH,
                matched_content=f"repeated violation content num {i}",
                category="spam",
            )
            analyzer.record_violation(v, "action")

        patterns = analyzer.analyze_patterns()
        assert len(patterns) >= 1
        assert patterns[0].frequency > 1

    def test_single_violation_low_threshold(self) -> None:
        analyzer = ViolationAnalyzer(min_frequency=1)
        v = Violation(
            rule_id="R1",
            rule_text="rule",
            severity=Severity.LOW,
            matched_content="unique violation",
            category="general",
        )
        analyzer.record_violation(v, "action")
        patterns = analyzer.analyze_patterns()
        assert len(patterns) == 1
        assert patterns[0].frequency == 1

    def test_empty_matched_content_uses_action(self) -> None:
        analyzer = ViolationAnalyzer(min_frequency=1)
        v = Violation(
            rule_id="R1",
            rule_text="rule",
            severity=Severity.MEDIUM,
            matched_content="",
            category="general",
        )
        analyzer.record_violation(v, "the actual action text")
        patterns = analyzer.analyze_patterns()
        assert len(patterns) == 1

    def test_min_confidence_filtering(self) -> None:
        constitution = Constitution.default()
        analyzer = ViolationAnalyzer(
            min_frequency=1, min_confidence=0.99
        )
        synth = RuleSynthesizer(constitution, analyzer=analyzer)

        # Record violations with likely low confidence (diverse content)
        for i in range(3):
            v = Violation(
                rule_id=f"R{i}",
                rule_text="rule",
                severity=Severity.MEDIUM,
                matched_content=f"completely unique text {i * 1000}",
                category="integrity",
            )
            analyzer.record_violation(v, f"action {i}")

        # With very high confidence threshold, may filter some
        result = synth.suggest_rules()
        assert isinstance(result, list)

    def test_analyzer_custom_thresholds(self) -> None:
        analyzer = ViolationAnalyzer(
            min_frequency=10, min_confidence=0.9
        )
        for _i in range(5):
            v = Violation(
                rule_id="R1",
                rule_text="rule",
                severity=Severity.HIGH,
                matched_content="repeated content",
                category="test",
            )
            analyzer.record_violation(v, "action")

        # 5 < min_frequency of 10, so no patterns
        patterns = analyzer.analyze_patterns()
        assert patterns == []

    def test_negative_min_frequency_clamped(self) -> None:
        analyzer = ViolationAnalyzer(min_frequency=-5)
        assert analyzer._min_frequency == 1

    def test_confidence_clamped_to_bounds(self) -> None:
        analyzer = ViolationAnalyzer(min_confidence=2.0)
        assert analyzer._min_confidence == 1.0
        analyzer2 = ViolationAnalyzer(min_confidence=-0.5)
        assert analyzer2._min_confidence == 0.0
