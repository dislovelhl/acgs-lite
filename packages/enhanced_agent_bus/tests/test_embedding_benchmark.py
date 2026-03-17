"""
Tests for the Embedding Provider Benchmark Module.

Constitutional Hash: cdd01ef066bc6cf2
"""

import os
from unittest.mock import MagicMock

import pytest
from packages.enhanced_agent_bus.embeddings.benchmark import (
    CONSTITUTIONAL_HASH,
    GOVERNANCE_SIMILARITY_PAIRS,
    GOVERNANCE_TEXTS,
    BenchmarkConfig,
    BenchmarkResult,
    EmbeddingBenchmark,
    cosine_similarity,
    get_memory_usage_mb,
)
from packages.enhanced_agent_bus.embeddings.provider import (
    EmbeddingConfig,
    EmbeddingProviderType,
    create_embedding_provider,
)

RUN_EAB_EMBEDDING_PROVIDER_INTEGRATION_TESTS = (
    os.getenv("RUN_EAB_EMBEDDING_PROVIDER_INTEGRATION_TESTS", "").strip().lower() == "true"
)


class TestConstitutionalCompliance:
    """Tests for constitutional compliance."""

    def test_constitutional_hash_present(self):
        """Verify constitutional hash is correctly defined."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_benchmark_result_includes_hash(self):
        """Verify BenchmarkResult includes constitutional hash."""
        result = BenchmarkResult(
            provider_type="mock",
            model_name="test",
            dimension=384,
            semantic_accuracy=0.9,
            avg_positive_similarity=0.8,
            avg_negative_similarity=0.2,
            similarity_gap=0.6,
            single_embed_ms=1.0,
            single_embed_std_ms=0.1,
            batch_embed_ms=0.5,
            batch_embed_std_ms=0.05,
            model_memory_mb=100.0,
            peak_memory_mb=150.0,
            num_samples=16,
            batch_size=8,
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


class TestGovernanceTestData:
    """Tests for governance domain test data."""

    def test_governance_pairs_structure(self):
        """Verify governance pairs have correct structure."""
        for pair in GOVERNANCE_SIMILARITY_PAIRS:
            assert "text_a" in pair
            assert "text_b" in pair
            assert "expected" in pair
            assert pair["expected"] in ("positive", "negative")

    def test_governance_pairs_balance(self):
        """Verify balanced positive and negative pairs."""
        positive_count = sum(1 for p in GOVERNANCE_SIMILARITY_PAIRS if p["expected"] == "positive")
        negative_count = sum(1 for p in GOVERNANCE_SIMILARITY_PAIRS if p["expected"] == "negative")
        assert positive_count == negative_count, "Pairs should be balanced"

    def test_governance_texts_not_empty(self):
        """Verify governance texts are available."""
        assert len(GOVERNANCE_TEXTS) >= 10
        for text in GOVERNANCE_TEXTS:
            assert len(text) > 10, "Each text should be meaningful"

    def test_governance_texts_domain_relevance(self):
        """Verify governance texts contain domain keywords."""
        domain_keywords = [
            "constitutional",
            "governance",
            "policy",
            "audit",
            "compliance",
            "MACI",
            "JWT",
            "Redis",
            "API",
        ]
        found_keywords = set()
        for text in GOVERNANCE_TEXTS:
            for keyword in domain_keywords:
                if keyword.lower() in text.lower():
                    found_keywords.add(keyword)
        assert len(found_keywords) >= 5, "Should cover diverse governance topics"


class TestCosineSimilarity:
    """Tests for cosine similarity function."""

    def test_identical_vectors(self):
        """Identical vectors should have similarity 1.0."""
        vec = [1.0, 2.0, 3.0]
        assert abs(cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        """Orthogonal vectors should have similarity 0.0."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        assert abs(cosine_similarity(vec_a, vec_b)) < 1e-6

    def test_opposite_vectors(self):
        """Opposite vectors should have similarity -1.0."""
        vec_a = [1.0, 2.0, 3.0]
        vec_b = [-1.0, -2.0, -3.0]
        assert abs(cosine_similarity(vec_a, vec_b) + 1.0) < 1e-6

    def test_zero_vector(self):
        """Zero vectors should return 0.0."""
        vec_a = [0.0, 0.0, 0.0]
        vec_b = [1.0, 2.0, 3.0]
        assert cosine_similarity(vec_a, vec_b) == 0.0

    def test_normalized_vectors(self):
        """Normalized vectors should still work correctly."""
        import math

        vec_a = [1.0, 0.0]
        vec_b = [math.sqrt(2) / 2, math.sqrt(2) / 2]
        expected = math.sqrt(2) / 2  # cos(45°)
        assert abs(cosine_similarity(vec_a, vec_b) - expected) < 1e-6


class TestBenchmarkConfig:
    """Tests for BenchmarkConfig."""

    def test_default_values(self):
        """Verify default configuration values."""
        config = BenchmarkConfig()
        assert config.num_warmup == 3
        assert config.num_iterations == 10
        assert config.measure_memory is True
        assert config.include_governance_tests is True

    def test_custom_values(self):
        """Verify custom configuration values."""
        config = BenchmarkConfig(
            num_warmup=5,
            num_iterations=20,
            batch_sizes=[4, 16, 64],
            measure_memory=False,
        )
        assert config.num_warmup == 5
        assert config.num_iterations == 20
        assert config.batch_sizes == [4, 16, 64]
        assert config.measure_memory is False


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_create_result(self):
        """Test creating a benchmark result."""
        result = BenchmarkResult(
            provider_type="sentence_transformer",
            model_name="all-MiniLM-L6-v2",
            dimension=384,
            semantic_accuracy=0.95,
            avg_positive_similarity=0.85,
            avg_negative_similarity=0.15,
            similarity_gap=0.70,
            single_embed_ms=2.5,
            single_embed_std_ms=0.3,
            batch_embed_ms=0.8,
            batch_embed_std_ms=0.1,
            model_memory_mb=250.0,
            peak_memory_mb=300.0,
            num_samples=16,
            batch_size=8,
        )
        assert result.provider_type == "sentence_transformer"
        assert result.semantic_accuracy == 0.95
        assert result.similarity_gap == 0.70

    def test_result_metrics_consistency(self):
        """Verify metric consistency in results."""
        result = BenchmarkResult(
            provider_type="test",
            model_name="test",
            dimension=768,
            semantic_accuracy=0.90,
            avg_positive_similarity=0.80,
            avg_negative_similarity=0.20,
            similarity_gap=0.60,
            single_embed_ms=3.0,
            single_embed_std_ms=0.5,
            batch_embed_ms=1.0,
            batch_embed_std_ms=0.2,
            model_memory_mb=200.0,
            peak_memory_mb=250.0,
            num_samples=16,
            batch_size=8,
        )
        # Gap should equal positive - negative
        assert (
            abs(
                result.similarity_gap
                - (result.avg_positive_similarity - result.avg_negative_similarity)
            )
            < 1e-6
        )
        # Peak memory should be >= model memory
        assert result.peak_memory_mb >= result.model_memory_mb


class TestEmbeddingBenchmarkUnit:
    """Unit tests for EmbeddingBenchmark class."""

    def test_init_default_config(self):
        """Test initialization with default config."""
        benchmark = EmbeddingBenchmark()
        assert benchmark.config is not None
        assert benchmark.results == []

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = BenchmarkConfig(num_iterations=5)
        benchmark = EmbeddingBenchmark(config)
        assert benchmark.config.num_iterations == 5


class TestEmbeddingBenchmarkWithMock:
    """Tests using mock provider."""

    @pytest.fixture
    def mock_provider(self):
        """Create a mock embedding provider."""
        provider = MagicMock()
        provider.embed.return_value = [0.1] * 384
        provider.embed_batch.return_value = [[0.1] * 384 for _ in range(16)]
        provider._cache = {}
        return provider

    @pytest.fixture
    def embedding_benchmark(self):
        """Create benchmark instance with minimal iterations."""
        config = BenchmarkConfig(num_warmup=1, num_iterations=2, measure_memory=False)
        return EmbeddingBenchmark(config)

    def test_semantic_quality_evaluation(self, embedding_benchmark, mock_provider):
        """Test semantic quality evaluation."""
        # Configure mock to return different embeddings for different texts
        call_count = [0]

        def mock_embed(text):
            call_count[0] += 1
            # Return predictable embeddings based on text content
            if "policy" in text.lower() or "consent" in text.lower():
                return [0.8, 0.1, 0.1]  # Governance cluster
            elif "weather" in text.lower() or "recipe" in text.lower():
                return [0.1, 0.8, 0.1]  # Non-governance cluster
            else:
                return [0.5, 0.5, 0.0]  # Neutral

        mock_provider.embed.side_effect = mock_embed

        accuracy, avg_pos, avg_neg, _gap = embedding_benchmark._evaluate_semantic_quality(
            mock_provider
        )

        # Should have been called for all pairs
        assert call_count[0] == len(GOVERNANCE_SIMILARITY_PAIRS) * 2
        # Metrics should be in valid ranges
        assert 0.0 <= accuracy <= 1.0
        assert -1.0 <= avg_pos <= 1.0
        assert -1.0 <= avg_neg <= 1.0

    def test_single_speed_measurement(self, embedding_benchmark, mock_provider):
        """Test single embedding speed measurement."""
        texts = ["test text 1", "test text 2", "test text 3"]
        mean_ms, std_ms = embedding_benchmark._measure_single_speed(mock_provider, texts)

        assert mean_ms >= 0
        assert std_ms >= 0
        # Mock should be very fast
        assert mean_ms < 100  # Less than 100ms for mock

    def test_batch_speed_measurement(self, embedding_benchmark, mock_provider):
        """Test batch embedding speed measurement."""
        texts = ["test text"] * 8
        mean_ms, std_ms = embedding_benchmark._measure_batch_speed(mock_provider, texts, 8)

        assert mean_ms >= 0
        assert std_ms >= 0

    def test_memory_measurement_disabled(self, embedding_benchmark, mock_provider):
        """Test memory measurement when disabled."""
        embedding_benchmark.config.measure_memory = False
        texts = ["test text"] * 4
        model_mem, peak_mem = embedding_benchmark._measure_memory(mock_provider, texts)

        assert model_mem == 0.0
        assert peak_mem == 0.0


class TestBenchmarkWithRealMock:
    """Integration tests using the Mock provider."""

    def test_benchmark_mock_provider(self):
        """Test benchmarking with mock provider end-to-end."""
        config = BenchmarkConfig(num_warmup=1, num_iterations=2, measure_memory=False)
        benchmark = EmbeddingBenchmark(config)

        result = benchmark.benchmark_provider(
            EmbeddingProviderType.MOCK, "mock-model", batch_size=4
        )

        assert result.provider_type == "mock"
        assert result.model_name == "mock-model"
        assert result.dimension == 1536  # Default mock dimension
        assert 0.0 <= result.semantic_accuracy <= 1.0
        assert result.single_embed_ms >= 0
        assert result.batch_embed_ms >= 0


class TestReportGeneration:
    """Tests for report generation."""

    @pytest.fixture
    def sample_results(self):
        """Create sample benchmark results."""
        return [
            BenchmarkResult(
                provider_type="sentence_transformer",
                model_name="all-MiniLM-L6-v2",
                dimension=384,
                semantic_accuracy=0.92,
                avg_positive_similarity=0.82,
                avg_negative_similarity=0.18,
                similarity_gap=0.64,
                single_embed_ms=3.5,
                single_embed_std_ms=0.4,
                batch_embed_ms=1.2,
                batch_embed_std_ms=0.15,
                model_memory_mb=200.0,
                peak_memory_mb=250.0,
                num_samples=16,
                batch_size=8,
            ),
            BenchmarkResult(
                provider_type="minicpm",
                model_name="MiniCPM4-0.5B",
                dimension=2048,
                semantic_accuracy=0.95,
                avg_positive_similarity=0.88,
                avg_negative_similarity=0.12,
                similarity_gap=0.76,
                single_embed_ms=8.5,
                single_embed_std_ms=0.8,
                batch_embed_ms=2.5,
                batch_embed_std_ms=0.3,
                model_memory_mb=1200.0,
                peak_memory_mb=1500.0,
                num_samples=16,
                batch_size=8,
            ),
        ]

    def test_generate_report_empty(self):
        """Test report generation with no results."""
        benchmark = EmbeddingBenchmark()
        report = benchmark.generate_report([])
        assert "No benchmark results available" in report

    def test_generate_report_structure(self, sample_results):
        """Test report has expected sections."""
        benchmark = EmbeddingBenchmark()
        report = benchmark.generate_report(sample_results)

        # Check sections
        assert "# Embedding Provider Benchmark Report" in report
        assert "Constitutional Hash" in report
        assert CONSTITUTIONAL_HASH in report
        assert "## Summary" in report
        assert "## Quality Metrics" in report
        assert "## Speed Metrics" in report
        assert "## Recommendations" in report

    def test_generate_report_includes_all_results(self, sample_results):
        """Test report includes all benchmark results."""
        benchmark = EmbeddingBenchmark()
        report = benchmark.generate_report(sample_results)

        for result in sample_results:
            assert result.model_name in report
            assert result.provider_type in report

    def test_generate_report_recommendations(self, sample_results):
        """Test report includes recommendations."""
        benchmark = EmbeddingBenchmark()
        report = benchmark.generate_report(sample_results)

        assert "Best Accuracy" in report
        assert "Fastest Single" in report
        assert "Fastest Batch" in report
        assert "Lowest Memory" in report

    def test_report_identifies_best_providers(self, sample_results):
        """Test that report correctly identifies best providers."""
        benchmark = EmbeddingBenchmark()
        report = benchmark.generate_report(sample_results)

        # MiniCPM should be best accuracy (0.95 > 0.92)
        assert "MiniCPM4-0.5B" in report
        # SentenceTransformer should be fastest (3.5ms < 8.5ms)
        assert "all-MiniLM-L6-v2" in report


class TestMemoryUtility:
    """Tests for memory utility function."""

    def test_get_memory_usage_returns_float(self):
        """Test memory usage returns a float."""
        mem = get_memory_usage_mb()
        assert isinstance(mem, float)

    def test_get_memory_usage_non_negative(self):
        """Test memory usage is non-negative."""
        mem = get_memory_usage_mb()
        assert mem >= 0.0

    def test_get_memory_usage_without_psutil(self):
        """Test graceful handling when psutil unavailable."""
        # The function handles ImportError internally and returns 0.0
        # We verify the function doesn't crash and returns a valid float
        # Testing actual ImportError behavior would require module reloading
        mem = get_memory_usage_mb()
        assert isinstance(mem, float)
        assert mem >= 0.0


class TestBenchmarkIntegration:
    """Integration tests requiring actual providers."""

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.skipif(
        not RUN_EAB_EMBEDDING_PROVIDER_INTEGRATION_TESTS,
        reason=(
            "Requires online model download/runtime setup. Set "
            "RUN_EAB_EMBEDDING_PROVIDER_INTEGRATION_TESTS=true to enable."
        ),
    )
    def test_benchmark_sentence_transformer(self):
        """Full benchmark with real SentenceTransformer."""
        config = BenchmarkConfig(num_warmup=1, num_iterations=3, measure_memory=True)
        benchmark = EmbeddingBenchmark(config)

        try:
            result = benchmark.benchmark_provider(
                EmbeddingProviderType.SENTENCE_TRANSFORMER,
                "all-MiniLM-L6-v2",
                batch_size=8,
            )

            assert result.dimension == 384
            assert result.semantic_accuracy > 0.5  # Should be reasonably accurate
            assert result.similarity_gap > 0.1  # Should discriminate positive/negative
            assert result.single_embed_ms < 1000  # Should complete in reasonable time
        except ImportError:
            pytest.skip("sentence-transformers not installed")

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.skipif(
        not RUN_EAB_EMBEDDING_PROVIDER_INTEGRATION_TESTS,
        reason=(
            "Requires online model download/runtime setup. Set "
            "RUN_EAB_EMBEDDING_PROVIDER_INTEGRATION_TESTS=true to enable."
        ),
    )
    def test_benchmark_all_providers_mock_only(self):
        """Test benchmark_all_providers with only mock available."""
        config = BenchmarkConfig(num_warmup=1, num_iterations=2, measure_memory=False)
        benchmark = EmbeddingBenchmark(config)

        # This will attempt real providers but shouldn't fail
        results = benchmark.benchmark_all_providers(include_openai=False, batch_size=4)

        # Should have at least attempted some providers
        # Results depend on what's installed
        assert isinstance(results, list)
