"""
Module.

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from enhanced_agent_bus.deliberation_layer.impact_scorer import ImpactScorer


class TestImpactScorerOptimized:
    @pytest.fixture
    def scorer(self):
        return ImpactScorer(use_onnx=False)  # Disable ONNX for unit tests unless mocked

    def test_calculate_impact_score_with_override(self, scorer):
        message = {"content": "test content", "from_agent": "agent1"}
        # Override semantic score to 0.9 (high)
        score = scorer.calculate_impact_score(message, context={"semantic_override": 0.9})
        # High semantic override (0.9) triggers boost to >= 0.75
        assert score >= 0.7
        assert score <= 1.0

    def test_score_batch_placeholder(self, scorer):
        messages = [
            {"content": "critical security breach", "from_agent": "agent1"},
            {"content": "normal message", "from_agent": "agent2"},
        ]
        # Since _bert_enabled is likely False in this test environment without models
        scores = scorer.score_messages_batch(messages)
        assert len(scores) == 2
        assert all(isinstance(s, float) for s in scores)
        assert scores[0] > scores[1]

    def test_model_lazy_loading_mock(self):
        """Test that model lazy loading works when mocked appropriately."""
        # Test the semantic scoring path with mocked embeddings
        with patch(
            "enhanced_agent_bus.deliberation_layer.impact_scorer.ImpactScorer._get_embeddings"
        ) as mock_emb:
            mock_emb.return_value = np.zeros((1, 768))
            scorer = ImpactScorer(use_onnx=False)
            # Manually set flags to simulate model being loaded
            scorer._model_loaded = True
            scorer._bert_enabled = True
            scorer.tokenizer = MagicMock()
            scorer.model = MagicMock()

            score = scorer._calculate_semantic_score({"content": "test"})
            assert isinstance(score, float)

    def test_extract_text_content_variants(self, scorer):
        # Test dict with payload
        msg1 = {"payload": {"message": "hello world"}}
        assert scorer._extract_text_content(msg1) == "hello world"

        # Test dict with string content and payload
        msg2 = {"content": "main content", "payload": {"message": "payload msg"}}
        assert scorer._extract_text_content(msg2) == "main content payload msg"

        # Test dict content gets stringified
        msg2b = {"content": {"text": "main content"}, "payload": {"message": "payload msg"}}
        result = scorer._extract_text_content(msg2b)
        assert "main content" in result
        assert "payload msg" in result

        # Test object with content attribute
        class MockMsg:
            def __init__(self, content):
                self.content = content

        msg3 = MockMsg("obj content")
        assert scorer._extract_text_content(msg3) == "obj content"

    def test_priority_factor_variants(self, scorer):
        assert scorer._calculate_priority_factor({"priority": "critical"}) == 1.0
        assert scorer._calculate_priority_factor({"priority": "high"}) == 0.8
        assert scorer._calculate_priority_factor({"priority": "medium"}) == 0.5
        assert scorer._calculate_priority_factor({"priority": "low"}) == 0.2
        assert scorer._calculate_priority_factor({"priority": "3"}) == 1.0
        assert scorer._calculate_priority_factor({}) == 0.5

    def test_type_factor_variants(self, scorer):
        # Type factors are multipliers: governance/security types get higher values
        assert scorer._calculate_type_factor({"message_type": "governance"}) == 1.5
        assert scorer._calculate_type_factor({"message_type": "constitutional"}) >= 1.0
        assert scorer._calculate_type_factor({"message_type": "command"}) == 1.0
        assert scorer._calculate_type_factor({"message_type": "other"}) == 1.0
        assert scorer._calculate_type_factor({}) == 1.0
