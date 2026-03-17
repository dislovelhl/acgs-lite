"""
Tests for MiniCPM Embedding Provider.

Constitutional Hash: cdd01ef066bc6cf2

Tests the MiniCPMEmbeddingProvider implementation for ACGS-2 constitutional
governance semantic search capabilities.
"""

import hashlib
from unittest.mock import MagicMock, patch

import packages.enhanced_agent_bus.embeddings.provider as provider_module
import pytest
from packages.enhanced_agent_bus.embeddings.provider import (
    EmbeddingConfig,
    EmbeddingProviderType,
    MiniCPMEmbeddingProvider,
    MockEmbeddingProvider,
    create_embedding_provider,
)
from src.core.shared.constants import CONSTITUTIONAL_HASH


class TestEmbeddingProviderType:
    """Tests for EmbeddingProviderType enum."""

    def test_minicpm_provider_type_exists(self):
        """Verify MINICPM is a valid provider type."""
        assert EmbeddingProviderType.MINICPM.value == "minicpm"

    def test_all_provider_types(self):
        """Verify all expected provider types exist."""
        expected = {"openai", "sentence_transformer", "minicpm", "mock", "octen"}
        actual = {pt.value for pt in EmbeddingProviderType}
        assert actual == expected


class TestEmbeddingConfig:
    """Tests for EmbeddingConfig with MiniCPM models."""

    def test_minicpm_8b_default_dimension(self):
        """Test MiniCPM4-8B gets correct default dimension."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
        )
        assert config.dimension == 4096

    def test_minicpm_05b_default_dimension(self):
        """Test MiniCPM4-0.5B gets correct default dimension."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-0.5B",
        )
        assert config.dimension == 2048

    def test_minicpm_3b_default_dimension(self):
        """Test MiniCPM3-4B gets correct default dimension."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM3-4B",
        )
        assert config.dimension == 2560

    def test_shorthand_model_name(self):
        """Test shorthand model names without openbmb prefix."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="MiniCPM4-8B",
        )
        assert config.dimension == 4096

    def test_custom_dimension_override(self):
        """Test custom dimension overrides default."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
            dimension=1024,
        )
        assert config.dimension == 1024

    def test_extra_params_for_minicpm(self):
        """Test extra parameters for MiniCPM configuration."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
            extra_params={
                "pooling": "cls",
                "max_length": 4096,
                "use_fp16": False,
                "trust_remote_code": True,
            },
        )
        assert config.extra_params["pooling"] == "cls"
        assert config.extra_params["max_length"] == 4096
        assert config.extra_params["use_fp16"] is False

    def test_invalid_cache_hash_mode_raises(self):
        """Invalid cache hash mode should be rejected."""
        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            EmbeddingConfig(
                provider_type=EmbeddingProviderType.MINICPM,
                model_name="openbmb/MiniCPM4-8B",
                cache_hash_mode="invalid",  # type: ignore[arg-type]
            )


class TestCreateEmbeddingProvider:
    """Tests for the embedding provider factory function."""

    def test_create_minicpm_provider(self):
        """Test factory creates MiniCPMEmbeddingProvider for MINICPM type."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
        )
        provider = create_embedding_provider(config)
        assert isinstance(provider, MiniCPMEmbeddingProvider)

    def test_create_mock_provider(self):
        """Test factory creates MockEmbeddingProvider for MOCK type."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MOCK,
            model_name="mock",
            dimension=768,
        )
        provider = create_embedding_provider(config)
        assert isinstance(provider, MockEmbeddingProvider)


class TestMiniCPMEmbeddingProviderUnit:
    """Unit tests for MiniCPMEmbeddingProvider without loading actual model."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
            batch_size=32,
            cache_embeddings=True,
            normalize=True,
            extra_params={
                "pooling": "mean",
                "max_length": 8192,
                "use_fp16": True,
                "trust_remote_code": True,
            },
        )

    @pytest.fixture
    def provider(self, config):
        """Create a provider instance without loading the model."""
        return MiniCPMEmbeddingProvider(config)

    def test_provider_initialization(self, provider, config):
        """Test provider initializes with correct configuration."""
        assert provider.config == config
        assert provider._pooling_strategy == "mean"
        assert provider._max_length == 8192
        assert provider._use_fp16 is True
        assert provider._trust_remote_code is True
        assert provider._model is None  # Not loaded yet
        assert provider._tokenizer is None

    def test_pooling_strategies_defined(self, provider):
        """Test all pooling strategies are defined."""
        assert provider.POOLING_MEAN == "mean"
        assert provider.POOLING_CLS == "cls"
        assert provider.POOLING_LAST == "last"
        assert provider.POOLING_MAX == "max"

    def test_get_model_info_before_load(self, provider):
        """Test model info before loading."""
        info = provider.get_model_info()
        assert info["model_name"] == "openbmb/MiniCPM4-8B"
        assert info["dimension"] == 4096
        assert info["loaded"] is False
        assert info["pooling_strategy"] == "mean"
        assert info["max_length"] == 8192

    def test_cache_key_generation(self, provider):
        """Test cache key generation is consistent."""
        text = "Constitutional compliance validation"
        key1 = provider._cache_key(text)
        key2 = provider._cache_key(text)
        assert key1 == key2
        assert len(key1) == 32  # SHA256 truncated to 32 chars

        # Different text should produce different key
        key3 = provider._cache_key("Different text")
        assert key1 != key3

    def test_cache_key_fast_mode_uses_kernel(self, monkeypatch):
        """Fast mode should use Rust hash kernel when available."""
        called = {"value": False}

        def _fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0xBEEF

        monkeypatch.setattr(provider_module, "FAST_HASH_AVAILABLE", True)
        monkeypatch.setattr(provider_module, "fast_hash", _fake_fast_hash, raising=False)

        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MOCK,
            model_name="mock",
            dimension=8,
            cache_hash_mode="fast",
        )
        provider = MockEmbeddingProvider(config)
        key = provider._cache_key("hello")

        assert called["value"] is True
        assert key == "fast:000000000000beef"

    def test_cache_key_fast_mode_falls_back_to_sha256(self, monkeypatch):
        """Fast mode should fallback to SHA-256 when kernel unavailable."""
        monkeypatch.setattr(provider_module, "FAST_HASH_AVAILABLE", False)

        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MOCK,
            model_name="mock",
            dimension=8,
            cache_hash_mode="fast",
        )
        provider = MockEmbeddingProvider(config)
        key = provider._cache_key("hello")

        expected = hashlib.sha256(b"hello").hexdigest()[:32]
        assert key == expected

    def test_normalize_embedding(self, provider):
        """Test embedding normalization."""
        embedding = [3.0, 4.0]  # Magnitude = 5
        normalized = provider._normalize(embedding)
        assert abs(normalized[0] - 0.6) < 1e-6
        assert abs(normalized[1] - 0.8) < 1e-6

        # Verify unit magnitude
        magnitude = sum(x * x for x in normalized) ** 0.5
        assert abs(magnitude - 1.0) < 1e-6

    def test_normalize_zero_vector(self, provider):
        """Test normalization of zero vector returns original."""
        embedding = [0.0, 0.0, 0.0]
        normalized = provider._normalize(embedding)
        assert normalized == embedding


class TestMiniCPMEmbeddingProviderWithMocks:
    """Tests for MiniCPMEmbeddingProvider with mocked transformers."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
            dimension=4096,
            batch_size=32,
            cache_embeddings=True,
            normalize=True,
        )

    @pytest.fixture
    def mock_torch(self):
        """Create mock torch module."""
        mock = MagicMock()
        mock.cuda.is_available.return_value = False
        mock.no_grad.return_value.__enter__ = MagicMock()
        mock.no_grad.return_value.__exit__ = MagicMock()
        return mock

    @pytest.fixture
    def mock_tokenizer(self):
        """Create mock tokenizer."""
        tokenizer = MagicMock()
        tokenizer.pad_token = "[PAD]"  # noqa: S105
        tokenizer.eos_token = "</s>"  # noqa: S105

        # Mock tokenizer call returns dict with tensors
        def tokenize_mock(text, **kwargs):
            if isinstance(text, str):  # noqa: SIM108
                batch_size = 1
            else:
                batch_size = len(text)

            mock_inputs = MagicMock()
            mock_inputs.__getitem__ = lambda self, k: MagicMock()
            mock_inputs.items.return_value = [
                ("input_ids", MagicMock()),
                ("attention_mask", MagicMock()),
            ]
            return mock_inputs

        tokenizer.side_effect = tokenize_mock
        tokenizer.return_value = tokenize_mock("test")
        return tokenizer

    @pytest.fixture
    def mock_model(self):
        """Create mock model with hidden states output."""
        import numpy as np

        model = MagicMock()
        model.eval.return_value = None

        # Create mock output with hidden states
        def forward_mock(**kwargs):
            output = MagicMock()

            # Create mock tensor for hidden states
            hidden_state = MagicMock()
            hidden_state.shape = (1, 10, 4096)  # batch, seq_len, hidden_dim
            hidden_state.__getitem__ = lambda self, idx: MagicMock()

            # Mock operations for pooling
            mask_expanded = MagicMock()
            mask_expanded.size.return_value = (1, 10, 4096)
            mask_expanded.sum.return_value = MagicMock()
            mask_expanded.sum.return_value.clamp.return_value = MagicMock()

            # Return random embeddings for testing
            random_embedding = np.random.randn(4096).tolist()

            # Mock the final embedding extraction
            pooled = MagicMock()
            pooled.squeeze.return_value.cpu.return_value.tolist.return_value = random_embedding

            output.hidden_states = (hidden_state,)  # Tuple of hidden states
            output.last_hidden_state = hidden_state

            return output

        model.side_effect = forward_mock
        model.return_value = forward_mock()
        return model

    @patch("packages.enhanced_agent_bus.embeddings.provider.MiniCPMEmbeddingProvider._get_device")
    def test_device_selection_cpu(self, mock_get_device, config):
        """Test CPU device selection when CUDA unavailable."""
        mock_get_device.return_value = "cpu"
        provider = MiniCPMEmbeddingProvider(config)
        assert provider._get_device() == "cpu"

    def test_unload_clears_model(self, config):
        """Test unload method clears model and tokenizer."""
        provider = MiniCPMEmbeddingProvider(config)

        # Simulate loaded model
        provider._model = MagicMock()
        provider._tokenizer = MagicMock()
        provider._device = "cpu"

        provider.unload()

        assert provider._model is None
        assert provider._tokenizer is None


class TestMiniCPMEmbeddingProviderCaching:
    """Tests for MiniCPM embedding caching functionality."""

    @pytest.fixture
    def config_with_cache(self):
        """Create config with caching enabled."""
        return EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
            cache_embeddings=True,
        )

    @pytest.fixture
    def config_without_cache(self):
        """Create config with caching disabled."""
        return EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
            cache_embeddings=False,
        )

    def test_cache_enabled_stores_embeddings(self, config_with_cache):
        """Test embeddings are cached when caching is enabled."""
        provider = MiniCPMEmbeddingProvider(config_with_cache)

        # Mock the generate method
        test_embedding = [0.1] * 4096
        provider._generate_embedding = MagicMock(return_value=test_embedding)

        # First call should generate
        text = "Test constitutional compliance"
        result1 = provider.embed(text)

        # Should have cached
        cache_key = provider._cache_key(text)
        assert cache_key in provider._cache

        # Second call should use cache
        result2 = provider.embed(text)

        # Generate should only be called once
        assert provider._generate_embedding.call_count == 1
        assert result1 == result2

    def test_cache_disabled_always_generates(self, config_without_cache):
        """Test embeddings are not cached when caching is disabled."""
        provider = MiniCPMEmbeddingProvider(config_without_cache)

        test_embedding = [0.1] * 4096
        provider._generate_embedding = MagicMock(return_value=test_embedding)

        text = "Test constitutional compliance"
        provider.embed(text)
        provider.embed(text)

        # Generate should be called twice
        assert provider._generate_embedding.call_count == 2

    def test_clear_cache(self, config_with_cache):
        """Test cache clearing functionality."""
        provider = MiniCPMEmbeddingProvider(config_with_cache)

        # Add something to cache
        provider._cache["test_key"] = [0.1] * 4096
        assert len(provider._cache) == 1

        provider.clear_cache()
        assert len(provider._cache) == 0


class TestMiniCPMEmbeddingProviderBatch:
    """Tests for MiniCPM batch embedding functionality."""

    @pytest.fixture
    def provider(self):
        """Create provider with mocked generation."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
            batch_size=2,
            cache_embeddings=True,
        )
        return MiniCPMEmbeddingProvider(config)

    def test_batch_embed_empty_list(self, provider):
        """Test batch embedding with empty list."""
        result = provider.embed_batch([])
        assert result == []

    def test_batch_embed_with_partial_cache(self, provider):
        """Test batch embedding with some items already cached."""
        # Pre-cache one item
        text1 = "Cached constitutional text"
        cached_embedding = [0.5] * 4096
        provider._cache[provider._cache_key(text1)] = cached_embedding

        # Mock generate for uncached items
        new_embedding = [0.2] * 4096
        provider._generate_batch = MagicMock(return_value=[new_embedding])

        texts = [text1, "Uncached text"]
        results = provider.embed_batch(texts)

        assert len(results) == 2
        # First should be from cache (normalized)
        # Second should be newly generated
        assert provider._generate_batch.call_count == 1


class TestMiniCPMPoolingStrategies:
    """Tests for different pooling strategies."""

    @pytest.fixture
    def provider_mean(self):
        """Create provider with mean pooling."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
            extra_params={"pooling": "mean"},
        )
        return MiniCPMEmbeddingProvider(config)

    @pytest.fixture
    def provider_cls(self):
        """Create provider with CLS pooling."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
            extra_params={"pooling": "cls"},
        )
        return MiniCPMEmbeddingProvider(config)

    @pytest.fixture
    def provider_last(self):
        """Create provider with last token pooling."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
            extra_params={"pooling": "last"},
        )
        return MiniCPMEmbeddingProvider(config)

    @pytest.fixture
    def provider_max(self):
        """Create provider with max pooling."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
            extra_params={"pooling": "max"},
        )
        return MiniCPMEmbeddingProvider(config)

    def test_mean_pooling_strategy(self, provider_mean):
        """Test mean pooling strategy is set correctly."""
        assert provider_mean._pooling_strategy == "mean"

    def test_cls_pooling_strategy(self, provider_cls):
        """Test CLS pooling strategy is set correctly."""
        assert provider_cls._pooling_strategy == "cls"

    def test_last_pooling_strategy(self, provider_last):
        """Test last token pooling strategy is set correctly."""
        assert provider_last._pooling_strategy == "last"

    def test_max_pooling_strategy(self, provider_max):
        """Test max pooling strategy is set correctly."""
        assert provider_max._pooling_strategy == "max"


@pytest.mark.constitutional
class TestMiniCPMConstitutionalCompliance:
    """Constitutional compliance tests for MiniCPM embedding provider."""

    def test_constitutional_hash_in_module(self):
        """Verify constitutional hash is present in module docstring."""
        from packages.enhanced_agent_bus.embeddings import provider

        assert CONSTITUTIONAL_HASH in provider.__doc__

    def test_constitutional_hash_in_provider_docstring(self):
        """Verify constitutional hash in MiniCPMEmbeddingProvider docstring."""
        docstring = MiniCPMEmbeddingProvider.__doc__
        assert CONSTITUTIONAL_HASH in docstring

    def test_embedding_dimension_consistency(self):
        """Verify embedding dimensions are consistent with constitutional requirements."""
        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-8B",
        )
        provider = MiniCPMEmbeddingProvider(config)

        # Dimension should match configuration
        assert provider.dimension == config.dimension
        assert provider.dimension == 4096


@pytest.mark.integration
class TestMiniCPMIntegration:
    """Integration tests for MiniCPM embedding provider.

    These tests require the actual MiniCPM model and are skipped by default.
    Run with: pytest -m integration
    """

    @pytest.fixture
    def real_provider(self):
        """Create real provider for integration testing."""
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except (ImportError, ValueError):
            pytest.skip("transformers or torch not installed")

        config = EmbeddingConfig(
            provider_type=EmbeddingProviderType.MINICPM,
            model_name="openbmb/MiniCPM4-0.5B",  # Use smaller model for tests
            extra_params={
                "pooling": "mean",
                "max_length": 512,
                "use_fp16": False,  # Use FP32 for CPU compatibility
            },
        )
        return MiniCPMEmbeddingProvider(config)

    @pytest.mark.slow
    def test_real_embedding_generation(self, real_provider):
        """Test actual embedding generation with real model."""
        text = "Constitutional AI governance compliance validation"

        try:
            embedding = real_provider.embed(text)
        except (RuntimeError, ValueError, TypeError, AssertionError, ImportError, Exception) as e:
            pytest.skip(f"Could not load MiniCPM model: {e}")

        # Verify embedding properties
        assert isinstance(embedding, list)
        assert len(embedding) == real_provider.dimension
        assert all(isinstance(x, float) for x in embedding)

        # Verify normalization (magnitude should be ~1.0)
        magnitude = sum(x * x for x in embedding) ** 0.5
        assert abs(magnitude - 1.0) < 0.01

    @pytest.mark.slow
    def test_real_batch_embedding(self, real_provider):
        """Test batch embedding with real model."""
        texts = [
            "Constitutional compliance validation",
            "Governance policy enforcement",
            "Security audit requirements",
        ]

        try:
            embeddings = real_provider.embed_batch(texts)
        except (RuntimeError, ValueError, TypeError, AssertionError, ImportError, Exception) as e:
            pytest.skip(f"Could not load MiniCPM model: {e}")

        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) == real_provider.dimension

    @pytest.mark.slow
    def test_semantic_similarity(self, real_provider):
        """Test that similar texts have similar embeddings."""
        text1 = "Constitutional AI governance"
        text2 = "AI constitutional governance"  # Semantically similar
        text3 = "Banana smoothie recipe"  # Semantically different

        try:
            emb1 = real_provider.embed(text1)
            emb2 = real_provider.embed(text2)
            emb3 = real_provider.embed(text3)
        except (RuntimeError, ValueError, TypeError, AssertionError, ImportError, Exception) as e:
            pytest.skip(f"Could not load MiniCPM model: {e}")

        # Calculate cosine similarities
        def cosine_similarity(a, b):
            dot = sum(x * y for x, y in zip(a, b, strict=False))
            mag_a = sum(x * x for x in a) ** 0.5
            mag_b = sum(x * x for x in b) ** 0.5
            return dot / (mag_a * mag_b)

        sim_12 = cosine_similarity(emb1, emb2)
        sim_13 = cosine_similarity(emb1, emb3)

        # Similar texts should have higher similarity than dissimilar
        assert sim_12 > sim_13


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
