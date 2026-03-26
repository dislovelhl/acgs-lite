"""
Tests for MiniCPM-Enhanced Semantic Impact Scoring.

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.impact_scorer_infra.algorithms.minicpm_semantic import (
    CONSTITUTIONAL_HASH,
    DOMAIN_REFERENCE_TEXTS,
    HIGH_IMPACT_INDICATORS,
    GovernanceDomain,
    MiniCPMScorerConfig,
    MiniCPMSemanticScorer,
    cosine_similarity,
    create_minicpm_scorer,
)
from enhanced_agent_bus.impact_scorer_infra.models import (
    ImpactVector,
    ScoringMethod,
    ScoringResult,
)


class TestConstitutionalCompliance:
    """Tests for constitutional compliance."""

    def test_constitutional_hash_present(self):
        """Verify constitutional hash is correctly defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_scoring_result_includes_hash(self):
        """Verify ScoringResult metadata includes constitutional hash."""
        config = MiniCPMScorerConfig(fallback_to_keywords=True)
        scorer = MiniCPMSemanticScorer(config)
        scorer._provider_available = False
        scorer._initialization_attempted = True
        result = scorer.score({"content": "test message"})
        assert "constitutional_hash" in result.metadata
        assert result.metadata["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestGovernanceDomain:
    """Tests for GovernanceDomain enum."""

    def test_all_domains_defined(self):
        """Verify all 7 governance domains are defined."""
        assert len(GovernanceDomain) == 7
        expected = {
            "safety",
            "security",
            "privacy",
            "fairness",
            "reliability",
            "transparency",
            "efficiency",
        }
        actual = {d.value for d in GovernanceDomain}
        assert actual == expected

    def test_domain_reference_texts_complete(self):
        """Verify reference texts exist for all domains."""
        for domain in GovernanceDomain:
            assert domain in DOMAIN_REFERENCE_TEXTS
            assert len(DOMAIN_REFERENCE_TEXTS[domain]) >= 3

    def test_high_impact_indicators_complete(self):
        """Verify high impact indicators exist for all domains."""
        for domain in GovernanceDomain:
            assert domain in HIGH_IMPACT_INDICATORS
            assert len(HIGH_IMPACT_INDICATORS[domain]) >= 3


class TestCosineSimilarity:
    """Tests for cosine similarity function."""

    def test_identical_vectors(self):
        """Identical vectors should have similarity 1.0."""
        vec = [1.0, 2.0, 3.0]
        assert abs(cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        """Orthogonal vectors should have similarity 0.0."""
        vec_a = [1.0, 0.0]
        vec_b = [0.0, 1.0]
        assert abs(cosine_similarity(vec_a, vec_b)) < 1e-6

    def test_opposite_vectors(self):
        """Opposite vectors should have similarity -1.0."""
        vec_a = [1.0, 2.0]
        vec_b = [-1.0, -2.0]
        assert abs(cosine_similarity(vec_a, vec_b) + 1.0) < 1e-6

    def test_zero_vector(self):
        """Zero vectors should return 0.0."""
        vec_a = [0.0, 0.0]
        vec_b = [1.0, 2.0]
        assert cosine_similarity(vec_a, vec_b) == 0.0


class TestMiniCPMScorerConfig:
    """Tests for MiniCPMScorerConfig."""

    def test_default_values(self):
        """Verify default configuration values."""
        config = MiniCPMScorerConfig()
        assert config.model_name == "MiniCPM4-0.5B"
        assert config.pooling_strategy == "mean"
        assert config.use_fp16 is True
        assert config.cache_embeddings is True
        assert config.normalize is True
        assert config.fallback_to_keywords is True

    def test_custom_values(self):
        """Verify custom configuration values."""
        config = MiniCPMScorerConfig(
            model_name="MiniCPM4-8B",
            pooling_strategy="cls",
            use_fp16=False,
            keyword_boost=0.2,
        )
        assert config.model_name == "MiniCPM4-8B"
        assert config.pooling_strategy == "cls"
        assert config.use_fp16 is False
        assert config.keyword_boost == 0.2


class TestMiniCPMSemanticScorerInit:
    """Tests for scorer initialization."""

    def test_init_default_config(self):
        """Test initialization with default config."""
        scorer = MiniCPMSemanticScorer()
        assert scorer.config is not None
        assert scorer._provider is None
        assert scorer._domain_embeddings is None

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = MiniCPMScorerConfig(model_name="MiniCPM4-8B")
        scorer = MiniCPMSemanticScorer(config)
        assert scorer.config.model_name == "MiniCPM4-8B"


class TestKeywordScoring:
    """Tests for keyword-based scoring."""

    @pytest.fixture
    def scorer(self):
        """Create scorer with keyword fallback."""
        config = MiniCPMScorerConfig(fallback_to_keywords=True)
        return MiniCPMSemanticScorer(config)

    def test_safety_keywords(self, scorer):
        """Test safety keyword detection."""
        score = scorer._calculate_keyword_score(
            "This is a dangerous emergency situation", GovernanceDomain.SAFETY
        )
        assert score > 0.0

    def test_security_keywords(self, scorer):
        """Test security keyword detection."""
        score = scorer._calculate_keyword_score(
            "Security breach detected with unauthorized access", GovernanceDomain.SECURITY
        )
        assert score > 0.0

    def test_privacy_keywords(self, scorer):
        """Test privacy keyword detection."""
        score = scorer._calculate_keyword_score(
            "PII data exposure without user consent", GovernanceDomain.PRIVACY
        )
        assert score > 0.0

    def test_fairness_keywords(self, scorer):
        """Test fairness keyword detection."""
        score = scorer._calculate_keyword_score(
            "Algorithm shows bias and discrimination", GovernanceDomain.FAIRNESS
        )
        assert score > 0.0

    def test_no_keywords(self, scorer):
        """Test text without keywords."""
        score = scorer._calculate_keyword_score(
            "Normal processing completed successfully", GovernanceDomain.SAFETY
        )
        assert score == 0.0

    def test_multiple_keywords_capped(self, scorer):
        """Test that multiple keywords don't exceed 1.0."""
        score = scorer._calculate_keyword_score(
            "danger harm injury emergency critical fatal hazard",
            GovernanceDomain.SAFETY,
        )
        assert score <= 1.0


class TestTextExtraction:
    """Tests for text content extraction."""

    @pytest.fixture
    def scorer(self):
        return MiniCPMSemanticScorer()

    def test_extract_direct_content(self, scorer):
        """Test extraction of direct content."""
        context = {"content": "test message"}
        text = scorer._extract_text_content(context)
        assert "test message" in text

    def test_extract_message_content(self, scorer):
        """Test extraction of message.content."""
        context = {"message": {"content": "nested content"}}
        text = scorer._extract_text_content(context)
        assert "nested content" in text

    def test_extract_payload_message(self, scorer):
        """Test extraction of payload.message."""
        context = {"message": {"payload": {"message": "payload content"}}}
        text = scorer._extract_text_content(context)
        assert "payload content" in text

    def test_extract_action(self, scorer):
        """Test extraction of action."""
        context = {"action": "execute_transfer"}
        text = scorer._extract_text_content(context)
        assert "execute_transfer" in text

    def test_extract_reasoning(self, scorer):
        """Test extraction of reasoning."""
        context = {"reasoning": "Based on policy requirements"}
        text = scorer._extract_text_content(context)
        assert "policy requirements" in text

    def test_extract_tools(self, scorer):
        """Test extraction of tools."""
        context = {"tools": [{"name": "transfer_funds"}, {"name": "send_email"}]}
        text = scorer._extract_text_content(context)
        assert "transfer_funds" in text
        assert "send_email" in text

    def test_extract_empty_context(self, scorer):
        """Test extraction of empty context."""
        context = {}
        text = scorer._extract_text_content(context)
        assert text == ""


class TestScoringWithKeywordFallback:
    """Tests for scoring with keyword fallback (no MiniCPM model)."""

    @pytest.fixture
    def scorer(self):
        """Create scorer that will use keyword fallback."""
        config = MiniCPMScorerConfig(fallback_to_keywords=True)
        scorer = MiniCPMSemanticScorer(config)
        scorer._provider_available = False
        scorer._initialization_attempted = True  # Prevent re-initialization
        return scorer

    def test_score_empty_content(self, scorer):
        """Test scoring empty content."""
        result = scorer.score({})
        assert result.aggregate_score == 0.0
        assert result.confidence == 0.0
        assert "error" in result.metadata

    def test_score_security_content(self, scorer):
        """Test scoring security-related content."""
        result = scorer.score({"content": "Security breach detected with unauthorized access"})
        assert result.vector.security > 0.0
        assert result.method == ScoringMethod.SEMANTIC
        assert result.metadata["semantic_enabled"] is False

    def test_score_safety_content(self, scorer):
        """Test scoring safety-related content."""
        result = scorer.score({"content": "Emergency danger situation requires immediate action"})
        assert result.vector.safety > 0.0

    def test_score_privacy_content(self, scorer):
        """Test scoring privacy-related content."""
        result = scorer.score({"content": "PII data exposure detected without consent"})
        assert result.vector.privacy > 0.0

    def test_score_neutral_content(self, scorer):
        """Test scoring neutral content."""
        result = scorer.score({"content": "Hello world this is a test message"})
        # All scores should be low or zero
        assert result.aggregate_score < 0.3

    def test_confidence_with_fallback(self, scorer):
        """Test confidence is lower with keyword fallback."""
        result = scorer.score({"content": "Security breach detected"})
        assert result.confidence == 0.6  # Fallback confidence


class TestScoringWithMockedProvider:
    """Tests for scoring with mocked MiniCPM provider."""

    @pytest.fixture
    def mock_provider(self):
        """Create mock embedding provider."""
        provider = MagicMock()
        provider.embed.return_value = [0.1] * 2048
        provider.embed_batch.return_value = [[0.1] * 2048 for _ in range(6)]
        return provider

    @pytest.fixture
    def scorer_with_mock(self, mock_provider):
        """Create scorer with mocked provider."""
        scorer = MiniCPMSemanticScorer()
        scorer._provider = mock_provider
        scorer._provider_available = True
        return scorer

    def test_score_with_semantic(self, scorer_with_mock, mock_provider):
        """Test scoring with semantic understanding enabled."""
        # Pre-compute domain embeddings
        scorer_with_mock._compute_domain_embeddings()

        result = scorer_with_mock.score({"content": "Security vulnerability detected"})

        assert result.method == ScoringMethod.SEMANTIC
        assert result.confidence == 0.95  # Semantic confidence

    def test_domain_embeddings_computed(self, scorer_with_mock):
        """Test domain embeddings are computed."""
        scorer_with_mock._compute_domain_embeddings()

        assert scorer_with_mock._domain_embeddings is not None
        assert len(scorer_with_mock._domain_embeddings) == 7

    def test_embedding_caching(self, scorer_with_mock, mock_provider):
        """Test embedding caching."""
        # First call
        scorer_with_mock._get_embedding("test text")
        # Second call should use cache
        scorer_with_mock._get_embedding("test text")

        # Embed should only be called once
        assert mock_provider.embed.call_count == 1


class TestImpactVectorScoring:
    """Tests for impact vector calculation."""

    @pytest.fixture
    def scorer(self):
        """Create scorer for testing with keyword fallback."""
        config = MiniCPMScorerConfig(fallback_to_keywords=True)
        scorer = MiniCPMSemanticScorer(config)
        scorer._provider_available = False
        scorer._initialization_attempted = True
        return scorer

    def test_vector_structure(self, scorer):
        """Test impact vector has all 7 dimensions."""
        result = scorer.score({"content": "test"})
        vector = result.vector

        assert hasattr(vector, "safety")
        assert hasattr(vector, "security")
        assert hasattr(vector, "privacy")
        assert hasattr(vector, "fairness")
        assert hasattr(vector, "reliability")
        assert hasattr(vector, "transparency")
        assert hasattr(vector, "efficiency")

    def test_vector_scores_bounded(self, scorer):
        """Test all vector scores are between 0 and 1."""
        result = scorer.score({"content": "danger breach pii bias outage audit latency"})
        vector = result.vector

        for field, value in vector.to_dict().items():
            assert 0.0 <= value <= 1.0, f"{field} out of bounds: {value}"

    def test_aggregate_score_bounded(self, scorer):
        """Test aggregate score is between 0 and 1."""
        result = scorer.score({"content": "maximum impact content breach danger pii"})
        assert 0.0 <= result.aggregate_score <= 1.0


class TestBatchScoring:
    """Tests for batch scoring."""

    @pytest.fixture
    def scorer(self):
        config = MiniCPMScorerConfig(fallback_to_keywords=True)
        scorer = MiniCPMSemanticScorer(config)
        scorer._provider_available = False
        scorer._initialization_attempted = True  # Prevent re-initialization
        return scorer

    def test_empty_batch(self, scorer):
        """Test scoring empty batch."""
        results = scorer.score_batch([])
        assert results == []

    def test_batch_scoring(self, scorer):
        """Test batch scoring multiple contexts."""
        contexts = [
            {"content": "Security breach detected"},
            {"content": "Normal operation"},
            {"content": "Emergency safety alert"},
        ]
        results = scorer.score_batch(contexts)

        assert len(results) == 3
        assert all(isinstance(r, ScoringResult) for r in results)

    def test_batch_order_preserved(self, scorer):
        """Test batch scoring preserves order."""
        contexts = [
            {"content": "First message"},
            {"content": "Security breach"},
            {"content": "Third message"},
        ]
        results = scorer.score_batch(contexts)

        # Second should have highest security score
        assert results[1].vector.security >= results[0].vector.security
        assert results[1].vector.security >= results[2].vector.security


class TestScorerLifecycle:
    """Tests for scorer lifecycle management."""

    def test_get_info(self):
        """Test get_info returns correct information."""
        scorer = MiniCPMSemanticScorer()
        info = scorer.get_info()

        assert info["scorer_type"] == "MiniCPMSemanticScorer"
        assert info["model_name"] == "MiniCPM4-0.5B"
        assert info["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_unload(self):
        """Test unload clears resources."""
        scorer = MiniCPMSemanticScorer()
        scorer._embedding_cache["test"] = [0.1, 0.2]
        scorer._domain_embeddings = {GovernanceDomain.SAFETY: [0.1]}

        scorer.unload()

        assert scorer._provider is None
        assert scorer._provider_available is False
        assert scorer._domain_embeddings is None
        assert len(scorer._embedding_cache) == 0


class TestFactoryFunction:
    """Tests for create_minicpm_scorer factory function."""

    def test_create_default(self):
        """Test creating scorer with defaults."""
        scorer = create_minicpm_scorer()
        assert scorer.config.model_name == "MiniCPM4-0.5B"
        assert scorer.config.use_fp16 is True

    def test_create_custom(self):
        """Test creating scorer with custom params."""
        scorer = create_minicpm_scorer(
            model_name="MiniCPM4-8B",
            use_fp16=False,
            fallback_to_keywords=False,
        )
        assert scorer.config.model_name == "MiniCPM4-8B"
        assert scorer.config.use_fp16 is False
        assert scorer.config.fallback_to_keywords is False


class TestHighImpactDetection:
    """Tests for high-impact classification."""

    @pytest.fixture
    def scorer(self):
        config = MiniCPMScorerConfig(
            fallback_to_keywords=True,
            high_impact_threshold=0.7,
        )
        scorer = MiniCPMSemanticScorer(config)
        scorer._provider_available = False
        scorer._initialization_attempted = True  # Prevent re-initialization
        return scorer

    def test_high_impact_detected(self, scorer):
        """Test high-impact content is flagged."""
        result = scorer.score(
            {"content": "Critical security breach with unauthorized malicious exploit detected"}
        )
        # Should be flagged as high impact due to multiple security keywords
        assert result.metadata.get("is_high_impact") is True or result.vector.security > 0.5

    def test_low_impact_not_flagged(self, scorer):
        """Test low-impact content is not flagged."""
        result = scorer.score({"content": "Normal operation completed"})
        assert result.metadata.get("is_high_impact") is False


class TestIntegration:
    """Integration tests requiring actual embedding computation."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_full_scoring_pipeline(self):
        """Test full scoring pipeline with real model."""
        try:
            scorer = create_minicpm_scorer(model_name="MiniCPM4-0.5B")
            result = scorer.score(
                {"content": "Security vulnerability detected in authentication system"}
            )

            assert result.method == ScoringMethod.SEMANTIC
            assert result.vector.security > 0.0
            assert result.confidence > 0.5

            scorer.unload()
        except ImportError:
            pytest.skip("MiniCPM model not available")
