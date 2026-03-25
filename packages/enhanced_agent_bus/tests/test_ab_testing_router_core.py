"""
A/B Testing Framework - Core Router Tests
Constitutional Hash: 608508a9bd224290

Part of the A/B testing framework test suite.
Extracted from monolithic test_ab_testing.py for better maintainability.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger

# Add parent directory to path for module imports
enhanced_agent_bus_dir = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)

from ab_testing import (
    AB_TEST_CONFIDENCE_LEVEL,
    AB_TEST_MIN_IMPROVEMENT,
    AB_TEST_MIN_SAMPLES,
    AB_TEST_SPLIT,
    CANDIDATE_ALIAS,
    CHAMPION_ALIAS,
    MODEL_REGISTRY_NAME,
    NUMPY_AVAILABLE,
    ABTestRouter,
    CohortMetrics,
    CohortType,
    ComparisonResult,
    MetricsComparison,
    PredictionResult,
    PromotionResult,
    PromotionStatus,
    RoutingResult,
    compare_models,
    get_ab_test_metrics,
    get_ab_test_router,
    promote_candidate_model,
    route_request,
)

logger = get_logger(__name__)


class TestABTestRouter:
    """Tests for ABTestRouter class."""

    @pytest.fixture(autouse=True)
    def _mock_mlflow_load(self):
        """Prevent MLflow connection attempts during ABTestRouter init."""
        with patch.object(
            ABTestRouter,
            "_ensure_initialized",
        ):
            yield

    @pytest.fixture
    def router(self):
        """Create an ABTestRouter instance for testing."""
        return ABTestRouter(
            candidate_split=0.1,
            min_samples=100,
            confidence_level=0.95,
            min_improvement=0.01,
        )

    @pytest.fixture
    def mock_sklearn_model(self):
        """Create a mock sklearn model."""
        model = MagicMock()
        model.predict = MagicMock(return_value=[1])
        model.predict_proba = MagicMock(return_value=[[0.2, 0.8]])
        model.classes_ = [0, 1]
        return model

    def test_router_initialization(self):
        """Test ABTestRouter initialization with default values."""
        router = ABTestRouter()

        assert router.candidate_split == AB_TEST_SPLIT
        assert router.champion_alias == CHAMPION_ALIAS
        assert router.candidate_alias == CANDIDATE_ALIAS
        assert router.min_samples == AB_TEST_MIN_SAMPLES
        assert router.confidence_level == AB_TEST_CONFIDENCE_LEVEL
        assert router.min_improvement == AB_TEST_MIN_IMPROVEMENT

    def test_router_initialization_custom(self, router):
        """Test ABTestRouter initialization with custom values."""
        assert router.candidate_split == 0.1
        assert router.min_samples == 100
        assert router.confidence_level == 0.95
        assert router.min_improvement == 0.01

    def test_router_invalid_split_raises(self):
        """Test that invalid candidate_split raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            ABTestRouter(candidate_split=1.5)
        assert "candidate_split must be between 0 and 1" in str(exc_info.value)

        with pytest.raises(ValueError):
            ABTestRouter(candidate_split=-0.1)

    def test_router_route_deterministic(self, router):
        """Test that routing is deterministic for same request_id."""
        result1 = router.route("test-request-123")
        result2 = router.route("test-request-123")

        assert result1.cohort == result2.cohort
        assert result1.request_id == result2.request_id

    def test_router_route_returns_valid_cohort(self, router):
        """Test that routing returns valid cohort types."""
        result = router.route("test-request")

        assert result.cohort in [CohortType.CHAMPION, CohortType.CANDIDATE]
        assert result.request_id == "test-request"
        assert isinstance(result, RoutingResult)

    def test_router_compute_hash_value_range(self, router):
        """Test hash value is in valid range [0, 1)."""
        for i in range(100):
            hash_value = router._compute_hash_value(f"request-{i}")
            assert 0.0 <= hash_value < 1.0

    def test_router_compute_hash_value_deterministic(self, router):
        """Test hash value is deterministic."""
        value1 = router._compute_hash_value("same-request")
        value2 = router._compute_hash_value("same-request")

        assert value1 == value2

    def test_router_compute_hash_value_different_inputs(self, router):
        """Test different inputs produce different hash values."""
        value1 = router._compute_hash_value("request-a")
        value2 = router._compute_hash_value("request-b")

        # While collisions are possible, these specific strings should differ
        assert value1 != value2

    def test_router_set_champion_model(self, router, mock_sklearn_model):
        """Test setting champion model directly."""
        router.set_champion_model(mock_sklearn_model, version=5)

        assert router.champion_model is mock_sklearn_model
        assert router.champion_version == 5

    def test_router_set_candidate_model(self, router, mock_sklearn_model):
        """Test setting candidate model directly."""
        router.set_candidate_model(mock_sklearn_model, version=3)

        assert router.candidate_model is mock_sklearn_model
        assert router.candidate_version == 3

    def test_router_set_ab_test_active(self, router):
        """Test enabling/disabling A/B testing."""
        router.set_ab_test_active(False)
        assert router.ab_test_active is False

        router.set_ab_test_active(True)
        assert router.ab_test_active is True

    def test_router_ab_test_disabled_routes_to_champion(self, router):
        """Test all traffic goes to champion when A/B testing disabled."""
        router.set_ab_test_active(False)

        champion_count = 0
        for i in range(100):
            result = router.route(f"request-{i}")
            if result.cohort == CohortType.CHAMPION:
                champion_count += 1

        assert champion_count == 100

    def test_router_get_champion_metrics(self, router):
        """Test getting champion metrics."""
        metrics = router.get_champion_metrics()

        assert isinstance(metrics, CohortMetrics)
        assert metrics.cohort == CohortType.CHAMPION

    def test_router_get_candidate_metrics(self, router):
        """Test getting candidate metrics."""
        metrics = router.get_candidate_metrics()

        assert isinstance(metrics, CohortMetrics)
        assert metrics.cohort == CohortType.CANDIDATE

    def test_router_get_metrics_summary(self, router):
        """Test getting full metrics summary."""
        summary = router.get_metrics_summary()

        assert "ab_test_active" in summary
        assert "candidate_split" in summary
        assert "champion" in summary
        assert "candidate" in summary
        assert "champion_version" in summary
        assert "candidate_version" in summary
        assert "has_champion_model" in summary
        assert "has_candidate_model" in summary

    def test_router_record_outcome(self, router):
        """Test recording outcome for a routed request."""
        # First route a request
        result = router.route("test-outcome")

        # Record outcome
        success = router.record_outcome(
            request_id="test-outcome",
            predicted=1,
            actual=1,
        )

        assert success is True

    def test_router_record_outcome_unknown_request(self, router):
        """Test recording outcome for unknown request returns False."""
        success = router.record_outcome(
            request_id="unknown-request",
            predicted=1,
            actual=1,
        )

        assert success is False
