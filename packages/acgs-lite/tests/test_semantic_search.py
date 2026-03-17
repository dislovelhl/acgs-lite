"""Tests for exp230: Semantic rule search — embedding-based retrieval."""

from __future__ import annotations

from acgs_lite.constitution.rule import Rule, Severity
from acgs_lite.constitution.semantic_search import (
    SearchReport,
    SearchResult,
    SemanticRuleSearch,
    _cosine_similarity,
    _embedding_fingerprint,
    embed_rules,
    embedding_coverage_report,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_rule(
    rule_id: str,
    text: str,
    *,
    embedding: list[float] | None = None,
    category: str = "general",
    severity: Severity = Severity.HIGH,
    tags: list[str] | None = None,
    enabled: bool = True,
) -> Rule:
    return Rule(
        id=rule_id,
        text=text,
        severity=severity,
        keywords=[w for w in text.lower().split()[:3]],
        category=category,
        tags=tags or [],
        embedding=embedding or [],
        enabled=enabled,
    )


def _make_constitution(rules: list[Rule]):
    """Minimal Constitution-like object for testing."""

    class FakeConstitution:
        def __init__(self, rules: list[Rule]):
            self.rules = rules

        def model_copy(self, *, update: dict):
            return FakeConstitution(update.get("rules", self.rules))

    return FakeConstitution(rules)


# ── Unit: cosine similarity ─────────────────────────────────────────────────


class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert _cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == 1.0

    def test_orthogonal_vectors(self):
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_opposite_vectors(self):
        result = _cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert abs(result - (-1.0)) < 1e-10

    def test_empty_vectors(self):
        assert _cosine_similarity([], [1.0]) == 0.0
        assert _cosine_similarity([1.0], []) == 0.0

    def test_mismatched_lengths(self):
        assert _cosine_similarity([1.0, 2.0], [1.0]) == 0.0

    def test_zero_magnitude(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_similar_vectors(self):
        result = _cosine_similarity([0.9, 0.1], [0.8, 0.2])
        assert result > 0.95  # highly similar


# ── Unit: embedding fingerprint ──────────────────────────────────────────────


class TestEmbeddingFingerprint:
    def test_stable_across_calls(self):
        rules = [_make_rule("R1", "test rule", embedding=[1.0, 2.0])]
        fp1 = _embedding_fingerprint(rules)
        fp2 = _embedding_fingerprint(rules)
        assert fp1 == fp2

    def test_changes_with_text(self):
        r1 = [_make_rule("R1", "original text", embedding=[1.0])]
        r2 = [_make_rule("R1", "modified text", embedding=[1.0])]
        assert _embedding_fingerprint(r1) != _embedding_fingerprint(r2)

    def test_changes_with_embedding_presence(self):
        r1 = [_make_rule("R1", "test", embedding=[1.0])]
        r2 = [_make_rule("R1", "test")]
        assert _embedding_fingerprint(r1) != _embedding_fingerprint(r2)

    def test_order_independent(self):
        r1 = _make_rule("A", "rule a", embedding=[1.0])
        r2 = _make_rule("B", "rule b", embedding=[2.0])
        fp_ab = _embedding_fingerprint([r1, r2])
        fp_ba = _embedding_fingerprint([r2, r1])
        assert fp_ab == fp_ba  # sorted by ID internally


# ── Unit: SearchResult / SearchReport ────────────────────────────────────────


class TestSearchDataclasses:
    def test_search_result_creation(self):
        sr = SearchResult(
            rule_id="R1",
            score=0.95,
            rule_text="No PII exposure",
            category="privacy",
            severity="critical",
            tags=["gdpr"],
        )
        assert sr.rule_id == "R1"
        assert sr.score == 0.95
        assert sr.tags == ["gdpr"]

    def test_search_report_creation(self):
        report = SearchReport(
            query="data retention",
            results=[],
            total_rules_searched=10,
            rules_with_embeddings=5,
        )
        assert report.query == "data retention"
        assert report.total_rules_searched == 10
        assert not report.cache_hit


# ── Integration: SemanticRuleSearch ──────────────────────────────────────────


class TestSemanticRuleSearch:
    def _setup_search(self):
        rules = [
            _make_rule(
                "PRIV-001",
                "No personal data exposure",
                embedding=[0.9, 0.1, 0.0],
                category="privacy",
            ),
            _make_rule(
                "PRIV-002",
                "Encrypt sensitive information",
                embedding=[0.8, 0.2, 0.1],
                category="privacy",
            ),
            _make_rule(
                "SEC-001",
                "No hardcoded credentials",
                embedding=[0.1, 0.9, 0.0],
                category="security",
            ),
            _make_rule(
                "SEC-002", "Validate all user input", embedding=[0.2, 0.8, 0.1], category="security"
            ),
            _make_rule(
                "GEN-001", "Log all decisions", embedding=[0.0, 0.1, 0.9], category="general"
            ),
            _make_rule("NO-EMB", "Rule without embedding"),  # no embedding
            _make_rule("DISABLED", "Disabled rule", embedding=[0.5, 0.5, 0.0], enabled=False),
        ]
        constitution = _make_constitution(rules)
        return SemanticRuleSearch(constitution), constitution

    def test_find_relevant_returns_report(self):
        search, _ = self._setup_search()

        class MockProvider:
            def embed(self, texts):
                return [[0.85, 0.15, 0.0]]  # similar to PRIV-001

        search._provider = MockProvider()
        report = search.find_relevant("user privacy data")

        assert isinstance(report, SearchReport)
        assert report.query == "user privacy data"
        assert report.total_rules_searched == 7
        assert report.rules_with_embeddings == 5  # excludes NO-EMB and DISABLED

    def test_find_relevant_ranks_by_similarity(self):
        search, _ = self._setup_search()

        class MockProvider:
            def embed(self, texts):
                return [[0.85, 0.15, 0.05]]  # close to privacy rules

        search._provider = MockProvider()
        report = search.find_relevant("personal data protection", top_k=3)

        assert len(report.results) <= 3
        if report.results:
            # Should rank privacy rules higher
            assert report.results[0].category == "privacy"
            # Scores should be descending
            scores = [r.score for r in report.results]
            assert scores == sorted(scores, reverse=True)

    def test_find_relevant_respects_min_similarity(self):
        search, _ = self._setup_search()

        class MockProvider:
            def embed(self, texts):
                return [[0.0, 0.0, 1.0]]  # similar to GEN-001 only

        search._provider = MockProvider()
        report = search.find_relevant("audit logging", min_similarity=0.95)

        # Only GEN-001 should pass high threshold
        for r in report.results:
            assert r.score >= 0.95

    def test_find_relevant_category_filter(self):
        search, _ = self._setup_search()

        class MockProvider:
            def embed(self, texts):
                return [[0.5, 0.5, 0.0]]

        search._provider = MockProvider()
        report = search.find_relevant("something", category="security")

        for r in report.results:
            assert r.category == "security"

    def test_find_relevant_tag_filter(self):
        rules = [
            _make_rule("R1", "GDPR compliance", embedding=[1.0, 0.0], tags=["gdpr"]),
            _make_rule("R2", "SOX compliance", embedding=[0.9, 0.1], tags=["sox"]),
            _make_rule("R3", "General rule", embedding=[0.5, 0.5]),
        ]
        search = SemanticRuleSearch(_make_constitution(rules))

        class MockProvider:
            def embed(self, texts):
                return [[0.95, 0.05]]

        search._provider = MockProvider()
        report = search.find_relevant("compliance", tags=["gdpr"])

        rule_ids = [r.rule_id for r in report.results]
        assert "R1" in rule_ids
        assert "R3" not in rule_ids  # no gdpr tag

    def test_find_relevant_no_provider(self):
        search, _ = self._setup_search()
        report = search.find_relevant("test query")
        # Without provider, should return empty results
        assert report.results == []

    def test_find_relevant_no_embeddings(self):
        rules = [_make_rule("R1", "rule without embedding")]
        search = SemanticRuleSearch(_make_constitution(rules))
        report = search.find_relevant("test")
        assert report.rules_with_embeddings == 0
        assert report.results == []

    def test_excludes_disabled_rules(self):
        search, _ = self._setup_search()

        class MockProvider:
            def embed(self, texts):
                return [[0.5, 0.5, 0.0]]

        search._provider = MockProvider()
        report = search.find_relevant("test", top_k=10)

        rule_ids = [r.rule_id for r in report.results]
        assert "DISABLED" not in rule_ids


class TestFindSimilarRules:
    def test_find_similar_basic(self):
        rules = [
            _make_rule("R1", "protect user data", embedding=[0.9, 0.1, 0.0]),
            _make_rule("R2", "safeguard personal info", embedding=[0.85, 0.15, 0.0]),
            _make_rule("R3", "audit all access", embedding=[0.0, 0.1, 0.9]),
        ]
        search = SemanticRuleSearch(_make_constitution(rules))
        report = search.find_similar_rules("R1", top_k=2)

        assert report.query == "similar_to:R1"
        rule_ids = [r.rule_id for r in report.results]
        assert "R1" not in rule_ids  # excludes self
        if report.results:
            assert report.results[0].rule_id == "R2"  # most similar

    def test_find_similar_unknown_rule(self):
        rules = [_make_rule("R1", "test", embedding=[1.0, 0.0])]
        search = SemanticRuleSearch(_make_constitution(rules))
        report = search.find_similar_rules("NONEXISTENT")
        assert report.results == []

    def test_find_similar_respects_min_similarity(self):
        rules = [
            _make_rule("R1", "rule a", embedding=[1.0, 0.0]),
            _make_rule("R2", "rule b", embedding=[0.0, 1.0]),  # orthogonal
        ]
        search = SemanticRuleSearch(_make_constitution(rules))
        report = search.find_similar_rules("R1", min_similarity=0.5)
        assert report.results == []  # R2 is orthogonal (sim=0.0)


class TestCoverage:
    def test_full_coverage(self):
        rules = [
            _make_rule("R1", "a", embedding=[1.0]),
            _make_rule("R2", "b", embedding=[2.0]),
        ]
        search = SemanticRuleSearch(_make_constitution(rules))
        assert search.coverage == 1.0

    def test_partial_coverage(self):
        rules = [
            _make_rule("R1", "a", embedding=[1.0]),
            _make_rule("R2", "b"),  # no embedding
        ]
        search = SemanticRuleSearch(_make_constitution(rules))
        assert search.coverage == 0.5

    def test_zero_coverage(self):
        rules = [_make_rule("R1", "a")]
        search = SemanticRuleSearch(_make_constitution(rules))
        assert search.coverage == 0.0

    def test_empty_constitution(self):
        search = SemanticRuleSearch(_make_constitution([]))
        assert search.coverage == 0.0


# ── Integration: embed_rules ─────────────────────────────────────────────────


class TestEmbedRules:
    def test_embeds_rules_without_embeddings(self):
        rules = [
            _make_rule("R1", "protect privacy"),
            _make_rule("R2", "validate input"),
            _make_rule("R3", "already embedded", embedding=[1.0, 2.0, 3.0]),
        ]
        constitution = _make_constitution(rules)

        class MockProvider:
            def embed(self, texts):
                return [[float(i)] * 3 for i in range(len(texts))]

        result = embed_rules(constitution, MockProvider())
        embedded_rules = result.rules

        # R1 and R2 should now have embeddings
        r1 = next(r for r in embedded_rules if r.id == "R1")
        r2 = next(r for r in embedded_rules if r.id == "R2")
        r3 = next(r for r in embedded_rules if r.id == "R3")

        assert r1.embedding  # now has embedding
        assert r2.embedding
        assert r3.embedding == [1.0, 2.0, 3.0]  # unchanged

    def test_skips_already_embedded(self):
        rules = [_make_rule("R1", "test", embedding=[1.0])]
        constitution = _make_constitution(rules)

        class MockProvider:
            call_count = 0

            def embed(self, texts):
                MockProvider.call_count += 1
                return [[9.0]]

        result = embed_rules(constitution, MockProvider())
        assert MockProvider.call_count == 0  # no API calls needed
        assert result.rules[0].embedding == [1.0]  # unchanged

    def test_includes_metadata_in_embedding_text(self):
        rules = [_make_rule("R1", "protect data", category="privacy", tags=["gdpr"])]
        constitution = _make_constitution(rules)

        captured_texts: list[list[str]] = []

        class CapturingProvider:
            def embed(self, texts):
                captured_texts.append(texts)
                return [[1.0] * len(texts)]

        embed_rules(constitution, CapturingProvider(), include_metadata=True)

        assert captured_texts
        text = captured_texts[0][0]
        assert "privacy" in text
        assert "gdpr" in text

    def test_batch_processing(self):
        rules = [_make_rule(f"R{i}", f"rule {i}") for i in range(10)]
        constitution = _make_constitution(rules)

        batch_sizes: list[int] = []

        class BatchTracker:
            def embed(self, texts):
                batch_sizes.append(len(texts))
                return [[1.0] for _ in texts]

        embed_rules(constitution, BatchTracker(), batch_size=3)

        # 10 rules / batch_size 3 = 4 batches (3, 3, 3, 1)
        assert len(batch_sizes) == 4
        assert sum(batch_sizes) == 10


# ── Integration: embedding_coverage_report ───────────────────────────────────


class TestEmbeddingCoverageReport:
    def test_basic_report(self):
        rules = [
            _make_rule("R1", "a", embedding=[1.0], category="privacy", severity=Severity.CRITICAL),
            _make_rule("R2", "b", category="security", severity=Severity.HIGH),
            _make_rule("R3", "c", embedding=[2.0], category="privacy", severity=Severity.MEDIUM),
        ]
        report = embedding_coverage_report(_make_constitution(rules))

        assert report["total_rules"] == 3
        assert report["active_rules"] == 3
        assert report["embedded_rules"] == 2
        assert abs(report["coverage"] - 2.0 / 3.0) < 0.01

        assert report["by_category"]["privacy"]["total"] == 2
        assert report["by_category"]["privacy"]["embedded"] == 2
        assert report["by_category"]["security"]["embedded"] == 0

    def test_empty_constitution(self):
        report = embedding_coverage_report(_make_constitution([]))
        assert report["total_rules"] == 0
        assert report["coverage"] == 0.0
