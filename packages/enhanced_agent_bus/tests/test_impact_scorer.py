"""Tests for adaptive_governance.impact_scorer module.

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_features(**overrides) -> ImpactFeatures:
    """Create test ImpactFeatures with defaults."""
    defaults = {
        "message_length": 100,
        "agent_count": 2,
        "tenant_complexity": 0.5,
        "temporal_patterns": [0.1, 0.2],
        "semantic_similarity": 0.3,
        "historical_precedence": 1,
        "resource_utilization": 0.2,
        "network_isolation": 0.9,
        "risk_score": 0.0,
        "confidence_level": 0.0,
    }
    return ImpactFeatures(**{**defaults, **overrides})


def _get_scorer_class():
    """Import ImpactScorer (isolates import-time side effects)."""
    from enhanced_agent_bus.adaptive_governance.impact_scorer import ImpactScorer

    return ImpactScorer


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInit:
    def test_creates_scorer(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        assert scorer.constitutional_hash == "test-hash"
        assert scorer.model_trained is False

    def test_feature_weights_sum_roughly_to_one(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        total = sum(scorer.feature_weights.values())
        assert abs(total - 1.0) < 0.01


# ---------------------------------------------------------------------------
# Rule-based scoring
# ---------------------------------------------------------------------------


class TestRuleBasedRiskScore:
    def test_low_risk_features(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        features = _make_features(
            message_length=50,
            agent_count=1,
            tenant_complexity=0.1,
            resource_utilization=0.05,
            semantic_similarity=0.1,
        )
        score = scorer._rule_based_risk_score(features)
        assert 0.0 <= score <= 0.3

    def test_high_risk_features(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        features = _make_features(
            message_length=20000,
            agent_count=15,
            tenant_complexity=0.9,
            resource_utilization=0.9,
            semantic_similarity=0.9,
        )
        score = scorer._rule_based_risk_score(features)
        assert score >= 0.5

    def test_score_capped_at_one(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        features = _make_features(
            message_length=50000,
            agent_count=100,
            tenant_complexity=1.0,
            resource_utilization=1.0,
            semantic_similarity=1.0,
        )
        score = scorer._rule_based_risk_score(features)
        assert score <= 1.0

    def test_medium_message_length(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        features = _make_features(message_length=5000)
        score = scorer._rule_based_risk_score(features)
        # Should get 0.1 for medium message length
        assert score >= 0.1


# ---------------------------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------------------------


class TestCalculateConfidence:
    def test_base_confidence(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        features = _make_features(
            historical_precedence=0,
            temporal_patterns=[],
            semantic_similarity=0.0,
        )
        confidence = scorer._calculate_confidence(features)
        assert confidence == 0.5

    def test_full_confidence_boost(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        features = _make_features(
            historical_precedence=5,
            temporal_patterns=[0.1, 0.2],
            semantic_similarity=0.5,
        )
        confidence = scorer._calculate_confidence(features)
        assert confidence == pytest.approx(0.9)

    def test_confidence_capped_at_one(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        features = _make_features(
            historical_precedence=100,
            temporal_patterns=[0.1] * 50,
            semantic_similarity=1.0,
        )
        confidence = scorer._calculate_confidence(features)
        assert confidence <= 1.0


# ---------------------------------------------------------------------------
# Impact assessment
# ---------------------------------------------------------------------------


class TestAssessImpact:
    @pytest.mark.asyncio
    async def test_assess_impact_rule_based_fallback(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        message = {"content": "hello world", "tenant_id": "t1"}
        context = {"active_agents": ["a1", "a2"]}
        result = await scorer.assess_impact(message, context)
        assert isinstance(result, ImpactFeatures)
        assert result.risk_score >= 0.0
        # Confidence should be fallback value
        from enhanced_agent_bus._compat.config.governance_constants import IMPACT_SCORER_CONFIG

        assert result.confidence_level == IMPACT_SCORER_CONFIG.confidence_fallback

    @pytest.mark.asyncio
    async def test_assess_impact_error_returns_safe_defaults(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        # Pass a message that causes _extract_features to fail
        with patch.object(scorer, "_extract_features", side_effect=RuntimeError("boom")):
            result = await scorer.assess_impact({"content": "test"}, {})
        assert isinstance(result, ImpactFeatures)
        assert result.agent_count == 1
        assert result.confidence_level == 0.5


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


class TestExtractFeatures:
    @pytest.mark.asyncio
    async def test_extract_features_basic(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        message = {"content": "hello", "tenant_id": "t1"}
        context = {"active_agents": ["a1", "a2", "a3"]}
        features = await scorer._extract_features(message, context)
        assert features.message_length == 5
        assert features.agent_count == 3

    @pytest.mark.asyncio
    async def test_extract_features_empty_content(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        message = {}
        context = {}
        features = await scorer._extract_features(message, context)
        assert features.message_length == 0
        assert features.agent_count == 0


# ---------------------------------------------------------------------------
# Model update / retrain
# ---------------------------------------------------------------------------


class TestUpdateModel:
    def test_update_model_adds_sample(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        features = _make_features()
        scorer.update_model(features, 0.5)
        assert len(scorer.training_samples) == 1

    def test_update_model_multiple(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        for i in range(10):
            features = _make_features(message_length=i * 100)
            scorer.update_model(features, i * 0.1)
        assert len(scorer.training_samples) == 10


# ---------------------------------------------------------------------------
# Predict risk score fallback
# ---------------------------------------------------------------------------


class TestPredictRiskScore:
    def test_fallback_when_not_trained(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        features = _make_features()
        score = scorer._predict_risk_score(features)
        # Should fall back to rule-based
        assert 0.0 <= score <= 1.0

    def test_fallback_when_no_classifier(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        scorer.impact_classifier = None
        features = _make_features()
        score = scorer._predict_risk_score(features)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# MHC stability
# ---------------------------------------------------------------------------


class TestMHCStability:
    def test_apply_mhc_stability_noop_when_disabled(self):
        cls = _get_scorer_class()
        scorer = cls("test-hash")
        scorer.use_mhc_stability = False
        original_weights = dict(scorer.feature_weights)
        scorer._apply_mhc_stability()
        assert scorer.feature_weights == original_weights
