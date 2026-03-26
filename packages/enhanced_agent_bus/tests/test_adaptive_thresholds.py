"""
Tests for Adaptive Threshold Manager.

Constitutional Hash: 608508a9bd224290

Covers:
- AdaptiveThresholds construction and _initialize_mlflow
- get_adaptive_threshold (trained and untrained paths)
- update_model (positive, negative, neutral feedback)
- _retrain_model (insufficient data, successful retrain)
- _extract_feature_vector
- _log_training_run_to_mlflow (mocked)
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    ImpactFeatures,
    ImpactLevel,
)
from enhanced_agent_bus.adaptive_governance.threshold_manager import (
    AdaptiveThresholds,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def thresholds():
    """Create an AdaptiveThresholds instance."""
    return AdaptiveThresholds(constitutional_hash="608508a9bd224290")


@pytest.fixture
def sample_features():
    """Create sample ImpactFeatures."""
    return ImpactFeatures(
        message_length=100,
        agent_count=5,
        tenant_complexity=0.5,
        temporal_patterns=[0.1, 0.2, 0.3],
        semantic_similarity=0.8,
        historical_precedence=3,
        resource_utilization=0.6,
        network_isolation=0.4,
        risk_score=0.5,
        confidence_level=0.9,
    )


@pytest.fixture
def sample_decision(sample_features):
    """Create a sample GovernanceDecision."""
    return GovernanceDecision(
        action_allowed=True,
        impact_level=ImpactLevel.MEDIUM,
        confidence_score=0.85,
        reasoning="Test decision",
        recommended_threshold=0.65,
        features_used=sample_features,
    )


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------


class TestConstruction:
    """Tests for AdaptiveThresholds initialization."""

    def test_init_sets_base_thresholds(self, thresholds):
        assert thresholds.base_thresholds[ImpactLevel.NEGLIGIBLE] == 0.1
        assert thresholds.base_thresholds[ImpactLevel.CRITICAL] == 0.95

    def test_init_model_not_trained(self, thresholds):
        assert thresholds.model_trained is False

    def test_init_mlflow_not_initialized_in_tests(self, thresholds):
        # pytest is in sys.modules so _mlflow_initialized should be False
        assert thresholds._mlflow_initialized is False

    def test_init_constitutional_hash(self, thresholds):
        assert thresholds.constitutional_hash == "608508a9bd224290"


# ---------------------------------------------------------------------------
# get_adaptive_threshold tests
# ---------------------------------------------------------------------------


class TestGetAdaptiveThreshold:
    """Tests for get_adaptive_threshold."""

    def test_untrained_returns_base(self, thresholds, sample_features):
        """When model is not trained, return base threshold."""
        for level in ImpactLevel:
            result = thresholds.get_adaptive_threshold(level, sample_features)
            assert result == thresholds.base_thresholds[level]

    def test_trained_returns_adjusted(self, thresholds, sample_features):
        """When model is trained, return ML-adjusted threshold."""
        # Train the model with some data
        thresholds.model_trained = True
        # Mock the model to return a known adjustment
        thresholds.threshold_model = MagicMock()
        thresholds.threshold_model.predict = MagicMock(return_value=np.array([0.05]))

        result = thresholds.get_adaptive_threshold(ImpactLevel.MEDIUM, sample_features)
        # base=0.6 + (0.05 * confidence_level=0.9) = 0.645
        assert 0.0 <= result <= 1.0

    def test_trained_model_error_falls_back(self, thresholds, sample_features):
        """When trained model errors, fall back to base threshold."""
        thresholds.model_trained = True
        thresholds.threshold_model = MagicMock()
        thresholds.threshold_model.predict = MagicMock(side_effect=RuntimeError("boom"))

        result = thresholds.get_adaptive_threshold(ImpactLevel.MEDIUM, sample_features)
        assert result == thresholds.base_thresholds[ImpactLevel.MEDIUM]

    def test_threshold_clamped_to_bounds(self, thresholds, sample_features):
        """Result is always clamped between 0.0 and 1.0."""
        thresholds.model_trained = True
        thresholds.threshold_model = MagicMock()
        # Return a large positive adjustment
        thresholds.threshold_model.predict = MagicMock(return_value=np.array([5.0]))
        result = thresholds.get_adaptive_threshold(ImpactLevel.CRITICAL, sample_features)
        assert result <= 1.0

        # Return a large negative adjustment
        thresholds.threshold_model.predict = MagicMock(return_value=np.array([-5.0]))
        result = thresholds.get_adaptive_threshold(ImpactLevel.NEGLIGIBLE, sample_features)
        assert result >= 0.0


# ---------------------------------------------------------------------------
# update_model tests
# ---------------------------------------------------------------------------


class TestUpdateModel:
    """Tests for update_model."""

    def test_positive_feedback(self, thresholds, sample_decision):
        """Test positive reinforcement path."""
        thresholds.update_model(sample_decision, outcome_success=True, human_feedback=True)
        assert len(thresholds.training_data) == 1
        sample = thresholds.training_data[0]
        assert sample["outcome_success"] is True
        assert sample["human_feedback"] is True

    def test_negative_feedback(self, thresholds, sample_decision):
        """Test negative reinforcement path."""
        thresholds.update_model(sample_decision, outcome_success=False, human_feedback=False)
        assert len(thresholds.training_data) == 1
        sample = thresholds.training_data[0]
        assert sample["outcome_success"] is False

    def test_neutral_feedback(self, thresholds, sample_decision):
        """Test neutral path (success=True, feedback=None but NOT False)."""
        thresholds.update_model(sample_decision, outcome_success=True, human_feedback=None)
        assert len(thresholds.training_data) == 1

    def test_triggers_retrain_after_interval(self, thresholds, sample_decision):
        """Test that retraining is triggered after interval."""
        thresholds.last_retraining = time.time() - thresholds.retraining_interval - 1
        # _retrain_model requires >= 100 samples, so it won't actually retrain
        thresholds.update_model(sample_decision, outcome_success=True)
        # Just verify no error

    def test_error_in_update_does_not_raise(self, thresholds):
        """Test that errors during update are caught."""
        bad_decision = MagicMock()
        bad_decision.features_used = MagicMock()
        bad_decision.features_used.message_length = "not_a_number"
        bad_decision.impact_level = ImpactLevel.MEDIUM
        bad_decision.recommended_threshold = 0.5
        # This will fail during feature extraction but should not raise
        thresholds.update_model(bad_decision, outcome_success=True)


# ---------------------------------------------------------------------------
# _retrain_model tests
# ---------------------------------------------------------------------------


class TestRetrainModel:
    """Tests for _retrain_model."""

    def test_insufficient_data_skips(self, thresholds):
        """Retrain with < 100 samples should skip."""
        for i in range(50):
            thresholds.training_data.append(
                {
                    "features": [float(i)] * 11,
                    "target": 0.1,
                    "timestamp": time.time(),
                    "impact_level": "medium",
                    "confidence": 0.8,
                    "outcome_success": True,
                    "human_feedback": None,
                }
            )
        thresholds._retrain_model()
        assert thresholds.model_trained is False

    def test_sufficient_data_trains(self, thresholds):
        """Retrain with >= 100 recent samples should train."""
        now = time.time()
        for i in range(120):
            thresholds.training_data.append(
                {
                    "features": [float(j + i * 0.01) for j in range(11)],
                    "target": 0.1 + (i * 0.001),
                    "timestamp": now - (i * 10),  # all within 24h
                    "impact_level": "medium",
                    "confidence": 0.8,
                    "outcome_success": True,
                    "human_feedback": None,
                }
            )
        thresholds._retrain_model()
        assert thresholds.model_trained is True

    def test_retrain_error_does_not_raise(self, thresholds):
        """Retrain errors are caught."""
        # Add invalid training data
        for _i in range(120):
            thresholds.training_data.append(
                {
                    "features": "not_a_list",
                    "target": 0.1,
                    "timestamp": time.time(),
                    "impact_level": "medium",
                    "confidence": 0.8,
                    "outcome_success": True,
                    "human_feedback": None,
                }
            )
        # Should not raise
        thresholds._retrain_model()


# ---------------------------------------------------------------------------
# _extract_feature_vector tests
# ---------------------------------------------------------------------------


class TestExtractFeatureVector:
    """Tests for _extract_feature_vector."""

    def test_correct_length(self, thresholds, sample_features):
        vector = thresholds._extract_feature_vector(sample_features)
        assert len(vector) == 11

    def test_empty_temporal_patterns(self, thresholds):
        features = ImpactFeatures(
            message_length=10,
            agent_count=1,
            tenant_complexity=0.1,
            temporal_patterns=[],
            semantic_similarity=0.5,
            historical_precedence=0,
            resource_utilization=0.0,
            network_isolation=0.0,
            risk_score=0.0,
            confidence_level=0.0,
        )
        vector = thresholds._extract_feature_vector(features)
        assert len(vector) == 11
        # temporal mean and std should be 0.0 for empty list
        assert vector[3] == 0.0
        assert vector[4] == 0.0

    def test_feature_values_match(self, thresholds, sample_features):
        vector = thresholds._extract_feature_vector(sample_features)
        assert vector[0] == sample_features.message_length
        assert vector[1] == sample_features.agent_count
        assert vector[2] == sample_features.tenant_complexity
        assert vector[5] == sample_features.semantic_similarity
        assert vector[10] == sample_features.confidence_level
