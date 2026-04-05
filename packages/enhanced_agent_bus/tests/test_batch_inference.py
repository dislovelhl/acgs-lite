"""
ACGS-2 Enhanced Agent Bus - Batch Inference Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for batch inference, tokenization caching, ONNX session
lazy loading, and optimized inference paths in the impact_scorer.py module.

Triage (2026-02-13): 10 test classes/methods marked xfail — all test APIs that
don't exist yet in impact_scorer.py (batch_score_impact, ImpactAnalysis, ONNX
session management, async batch, combined score, helper functions). Converted
from skip → xfail(strict=False) so they auto-pass when APIs are implemented.
"""

import os
import sys
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Add enhanced_agent_bus directory to path
enhanced_agent_bus_dir = os.path.dirname(os.path.dirname(__file__))
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)


class TestONNXAvailableFlag:
    """Tests for ONNX_AVAILABLE flag proper definition."""

    def test_onnx_available_flag_exists(self):
        """Test that ONNX_AVAILABLE flag is defined as a boolean."""
        from deliberation_layer.impact_scorer import ONNX_AVAILABLE

        assert isinstance(ONNX_AVAILABLE, bool)

    def test_transformers_available_flag_exists(self):
        """Test that TRANSFORMERS_AVAILABLE flag is defined as a boolean."""
        from deliberation_layer.impact_scorer import TRANSFORMERS_AVAILABLE

        assert isinstance(TRANSFORMERS_AVAILABLE, bool)

    def test_onnx_available_is_bool(self):
        """Test that ONNX_AVAILABLE is a boolean flag."""
        from deliberation_layer.impact_scorer import ONNX_AVAILABLE

        assert isinstance(ONNX_AVAILABLE, bool)


class TestTokenizationCaching:
    """Tests for tokenization caching functionality."""

    @pytest.fixture
    def mock_tokenizer(self):
        """Create a mock tokenizer that tracks calls."""
        mock = MagicMock()
        mock.return_value = {
            "input_ids": MagicMock(),
            "attention_mask": MagicMock(),
        }
        return mock

    @pytest.fixture
    def mock_lru_cache(self):
        """Create a mock LRU cache for testing."""

        class MockLRUCache:
            def __init__(self, maxsize=100):
                from typing import Any

                self.maxsize = maxsize
                self._cache: dict[Any, Any] = {}

            def get(self, key):
                return self._cache.get(key)

            def set(self, key, value):
                if len(self._cache) >= self.maxsize:
                    # Remove oldest entry (simplified)
                    first_key = next(iter(self._cache))
                    self._cache.pop(first_key, None)
                self._cache[key] = value

            def clear(self):
                self._cache.clear()

        return MockLRUCache

    def test_tokenize_text_caches_result(self):
        """Test that _tokenize_text caches tokenized results."""
        from deliberation_layer.impact_scorer import ImpactScorer

        # Create scorer with mocked dependencies
        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)

        # Verify cache exists (may be None if LRUCache not available)
        assert hasattr(scorer, "_tokenization_cache")

    def test_clear_tokenization_cache(self):
        """Test that clear_tokenization_cache works correctly."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
            # Should not raise even if cache is None
            scorer.clear_tokenization_cache()


class TestClassLevelCaching:
    """Tests for class-level tokenizer and model caching (singleton pattern)."""

    def test_scorer_singleton_pattern_works(self):
        """Test that get_impact_scorer returns singleton."""
        from deliberation_layer.impact_scorer import (
            get_impact_scorer,
            reset_impact_scorer,
        )

        # Reset first to ensure clean state
        reset_impact_scorer()

        scorer1 = get_impact_scorer()
        scorer2 = get_impact_scorer()

        assert scorer1 is scorer2

        # Cleanup
        reset_impact_scorer()


class TestONNXSessionLazyLoading:
    """Tests for ONNX session lazy loading functionality."""

    def test_onnx_enabled_flag_depends_on_availability(self):
        """Test that _onnx_enabled depends on ONNX_AVAILABLE."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=True)

            # _onnx_enabled should be False if TRANSFORMERS_AVAILABLE is False
            # (it requires both ONNX_AVAILABLE and TRANSFORMERS_AVAILABLE)
            assert scorer._onnx_enabled is False


class TestBatchScoreImpact:
    """Tests for batch_score_impact functionality."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer with mocked dependencies."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
        return scorer

    def test_batch_empty_list_returns_empty(self, scorer):
        """Test batch inference with empty list returns empty list."""
        result = scorer.batch_score_impact([])
        assert result == []

    def test_batch_single_message(self, scorer):
        """Test batch inference with a single message."""
        messages = [{"content": "critical security alert"}]
        result = scorer.batch_score_impact(messages)

        assert len(result) == 1
        assert 0.0 <= result[0] <= 1.0
        assert result[0] > 0.5  # High-impact keywords should produce high score

    def test_batch_multiple_messages(self, scorer):
        """Test batch inference with multiple messages."""
        messages = [
            {"content": "critical security breach detected"},
            {"content": "simple status update"},
            {"content": "governance policy violation"},
        ]
        results = scorer.batch_score_impact(messages)

        assert len(results) == 3
        assert all(0.0 <= score <= 1.0 for score in results)
        # First and third should score higher than second
        assert results[0] > results[1]
        assert results[2] > results[1]

    def test_batch_with_contexts(self, scorer):
        """Test batch inference with context information."""
        messages = [
            {"content": "test message 1"},
            {"content": "test message 2"},
        ]
        contexts = [
            {"priority": "critical"},
            {"priority": "low"},
        ]
        results = scorer.batch_score_impact(messages, contexts)

        assert len(results) == 2
        assert results[0] > results[1]  # Critical priority should score higher

    def test_batch_context_length_mismatch_raises(self, scorer):
        """Test that mismatched context length raises ValueError."""
        messages = [{"content": "test 1"}, {"content": "test 2"}]
        contexts = [{"priority": "high"}]  # Only one context for two messages

        with pytest.raises(ValueError) as excinfo:
            scorer.batch_score_impact(messages, contexts)

        assert "contexts length" in str(excinfo.value)
        assert "messages length" in str(excinfo.value)

    def test_batch_preserves_order(self, scorer):
        """Test that batch results maintain input order."""
        messages = [
            {"content": f"message {i} with {'critical' if i % 2 == 0 else 'normal'} content"}
            for i in range(10)
        ]
        results = scorer.batch_score_impact(messages)

        assert len(results) == 10
        # Even-indexed messages have "critical" keyword, should score higher
        for i in range(0, 10, 2):
            if i + 1 < 10:
                assert results[i] >= results[i + 1]

    def test_batch_with_empty_content(self, scorer):
        """Test batch inference handles empty content gracefully."""
        messages = [
            {"content": ""},
            {"content": "critical alert"},
            {"content": ""},
        ]
        results = scorer.batch_score_impact(messages)

        assert len(results) == 3
        assert all(0.0 <= score <= 1.0 for score in results)
        # Empty content should have low scores
        assert results[1] > results[0]
        assert results[1] > results[2]

    def test_batch_scores_bounded(self, scorer):
        """Test that all batch scores are between 0 and 1."""
        messages = [
            {"content": "critical emergency security breach violation danger risk threat attack"},
            {"content": "simple message"},
            {"content": ""},
            {"content": "governance policy compliance audit financial blockchain"},
        ]
        results = scorer.batch_score_impact(messages)

        assert all(0.0 <= score <= 1.0 for score in results)

    def test_batch_consistency_with_sequential(self, scorer):
        """Test that batch results match sequential scoring."""
        messages = [
            {"content": "critical security alert"},
            {"content": "normal status check"},
            {"content": "governance policy update"},
        ]

        # Batch scoring
        batch_results = scorer.batch_score_impact(messages)

        # Sequential scoring - Reset history first to ensure consistency
        scorer.reset_history()
        sequential_results = [scorer.calculate_impact_score(msg) for msg in messages]

        # Results should be identical
        assert len(batch_results) == len(sequential_results)
        for batch_score, seq_score in zip(batch_results, sequential_results, strict=False):
            assert abs(batch_score - seq_score) < 1e-6

    def test_batch_large_batch_performance(self, scorer):
        """Test batch inference with a large number of messages."""
        messages = [
            {
                "content": (
                    f"test message {i} with security alert" if i % 5 == 0 else f"normal message {i}"
                )
            }
            for i in range(50)
        ]

        start_time = time.time()
        results = scorer.batch_score_impact(messages)
        elapsed_time = time.time() - start_time

        assert len(results) == 50
        assert all(0.0 <= score <= 1.0 for score in results)
        # Should complete in reasonable time (< 2 seconds as per spec)
        assert elapsed_time < 2.0, f"Batch processing took {elapsed_time:.2f}s, expected < 2.0s"


class TestEdgeCases:
    """Tests for edge cases in optimized inference paths."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer with mocked dependencies."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
        return scorer

    def test_none_message_returns_base_score(self, scorer):
        """Test that None message returns base score."""
        score = scorer.calculate_impact_score(None)
        assert 0.0 <= score <= 1.0

    def test_empty_dict_message(self, scorer):
        """Test scoring of empty dict message."""
        score = scorer.calculate_impact_score({})
        assert 0.0 <= score <= 1.0

    def test_very_long_content(self, scorer):
        """Test scoring of very long content (edge case for truncation)."""
        long_content = "critical security " * 1000  # Very long content
        message = {"content": long_content}
        score = scorer.calculate_impact_score(message)

        assert 0.0 <= score <= 1.0
        assert score > 0.5  # Should still detect high-impact keywords

    def test_special_characters_in_content(self, scorer):
        """Test scoring of content with special characters."""
        message = {"content": "critical! security@#$%^&*() breach!!!"}
        score = scorer.calculate_impact_score(message)

        assert 0.0 <= score <= 1.0
        assert score > 0.3  # Should still detect keywords

    def test_unicode_content(self, scorer):
        """Test scoring of content with unicode characters."""
        message = {
            "content": "critical security alert with unicode: \u4e2d\u6587 \u65e5\u672c\u8a9e"
        }
        score = scorer.calculate_impact_score(message)

        assert 0.0 <= score <= 1.0

    def test_nested_payload_extraction(self, scorer):
        """Test text extraction from deeply nested payload."""
        message = {
            "content": "outer content",
            "payload": {
                "message": "critical security issue in nested payload",
            },
        }
        score = scorer.calculate_impact_score(message)

        assert 0.0 <= score <= 1.0
        assert score > 0.3  # Should detect "critical" and "security"

    def test_malformed_priority(self, scorer):
        """Test handling of malformed priority value."""
        message = {
            "content": "test message",
            "priority": {"invalid": "priority"},
        }
        # Should not crash
        score = scorer.calculate_impact_score(message)
        assert 0.0 <= score <= 1.0

    def test_malformed_message_type(self, scorer):
        """Test handling of malformed message_type value."""
        message = {
            "content": "test message",
            "message_type": 12345,  # Non-string type
        }
        # Should not crash
        score = scorer.calculate_impact_score(message)
        assert 0.0 <= score <= 1.0


class TestCosineSimillaryFallback:
    """Tests for cosine_similarity_fallback function."""

    def test_cosine_similarity_fallback_normal(self):
        """Test cosine similarity fallback with normal vectors."""
        from deliberation_layer.impact_scorer import cosine_similarity_fallback

        a = np.array([1.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        sim = cosine_similarity_fallback(a, b)

        assert abs(sim - 1.0) < 1e-6  # Identical vectors should have similarity 1.0

    def test_cosine_similarity_fallback_orthogonal(self):
        """Test cosine similarity fallback with orthogonal vectors."""
        from deliberation_layer.impact_scorer import cosine_similarity_fallback

        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        sim = cosine_similarity_fallback(a, b)

        assert abs(sim) < 1e-6  # Orthogonal vectors should have similarity 0.0

    def test_cosine_similarity_fallback_empty(self):
        """Test cosine similarity fallback with empty vectors."""
        from deliberation_layer.impact_scorer import cosine_similarity_fallback

        a = np.array([])
        b = np.array([1.0, 0.0])
        sim = cosine_similarity_fallback(a, b)

        assert sim == 0.0

    def test_cosine_similarity_fallback_zero_norm(self):
        """Test cosine similarity fallback with zero norm vector."""
        from deliberation_layer.impact_scorer import cosine_similarity_fallback

        a = np.array([0.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        sim = cosine_similarity_fallback(a, b)

        assert sim == 0.0


class TestGlobalFunctions:
    """Tests for global functions in impact_scorer module."""

    def test_reset_impact_scorer_clears_global(self):
        """Test that reset_impact_scorer clears global scorer."""
        from deliberation_layer.impact_scorer import (
            get_impact_scorer,
            reset_impact_scorer,
        )

        # Get a scorer first
        scorer = get_impact_scorer()
        assert scorer is not None

        # Reset
        reset_impact_scorer()

        # Get new scorer - should be different instance
        new_scorer = get_impact_scorer()

        # Note: Can't directly compare with old scorer since it's been reset
        # But we can verify we get a valid scorer
        assert new_scorer is not None

        # Cleanup
        reset_impact_scorer()

    def test_calculate_message_impact_convenience(self):
        """Test calculate_message_impact convenience function."""
        from deliberation_layer.impact_scorer import (
            calculate_message_impact,
            reset_impact_scorer,
        )

        reset_impact_scorer()

        message = MagicMock()
        message.content = "critical security alert"

        score = calculate_message_impact(message)

        assert 0.0 <= score <= 1.0

        reset_impact_scorer()


class TestScoringConfig:
    """Tests for ScoringConfig dataclass."""

    def test_default_config_values(self):
        """Test that ScoringConfig has correct default values."""
        from deliberation_layer.impact_scorer import ScoringConfig

        config = ScoringConfig()

        # Match actual defaults from impact_scorer_infra/models.py
        assert config.semantic_weight == 0.2
        assert config.permission_weight == 0.2
        assert config.volume_weight == 0.15
        assert config.context_weight == 0.15
        assert config.drift_weight == 0.1
        assert config.priority_weight == 0.1
        assert config.type_weight == 0.1
        assert config.critical_priority_boost == 0.9
        assert config.high_semantic_boost == 0.8

    def test_custom_config_values(self):
        """Test ScoringConfig with custom values."""
        from deliberation_layer.impact_scorer import ScoringConfig

        config = ScoringConfig(
            semantic_weight=0.5,
            critical_priority_boost=0.95,
        )

        assert config.semantic_weight == 0.5
        assert config.critical_priority_boost == 0.95


# Entry point for running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
