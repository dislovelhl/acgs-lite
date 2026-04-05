"""
A/B Testing Framework - Router Prediction Tests
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


class TestABTestRouterPrediction:
    """Tests for prediction functionality."""

    @pytest.fixture(autouse=True)
    def _mock_mlflow_load(self):
        """Prevent MLflow connection attempts during ABTestRouter init."""
        with patch.object(ABTestRouter, "_ensure_initialized"):
            yield

    @pytest.fixture
    def router_with_models(self):
        """Create router with mock models."""
        router = ABTestRouter(candidate_split=0.1)

        # Create mock champion model
        champion = MagicMock()
        champion.predict = MagicMock(return_value=[1])
        champion.predict_proba = MagicMock(return_value=[[0.2, 0.8]])
        champion.classes_ = [0, 1]

        # Create mock candidate model
        candidate = MagicMock()
        candidate.predict = MagicMock(return_value=[0])
        candidate.predict_proba = MagicMock(return_value=[[0.9, 0.1]])
        candidate.classes_ = [0, 1]

        router.set_champion_model(champion, version=1)
        router.set_candidate_model(candidate, version=2)
        router._initialized = True

        return router

    def test_predict_with_routing(self, router_with_models):
        """Test prediction with routing result."""
        routing = router_with_models.route("test-predict")
        result = router_with_models.predict(routing, [1.0, 2.0, 3.0])

        assert result.request_id == "test-predict"
        assert result.cohort in [CohortType.CHAMPION, CohortType.CANDIDATE]
        assert result.latency_ms > 0
        assert result.error is None

    def test_route_and_predict_convenience(self, router_with_models):
        """Test route_and_predict convenience method."""
        result = router_with_models.route_and_predict(
            request_id="test-convenience",
            features=[1.0, 2.0, 3.0],
        )

        assert result.request_id == "test-convenience"
        assert result.prediction is not None
        assert result.latency_ms > 0

    def test_predict_records_latency_metrics(self, router_with_models):
        """Test prediction records latency to cohort metrics."""
        initial_champion = router_with_models._champion_metrics.request_count
        initial_candidate = router_with_models._candidate_metrics.request_count

        # Make several predictions
        for i in range(10):
            router_with_models.route_and_predict(f"latency-test-{i}", [1.0, 2.0])

        total_requests = (
            router_with_models._champion_metrics.request_count
            + router_with_models._candidate_metrics.request_count
        )
        initial_total = initial_champion + initial_candidate

        assert total_requests == initial_total + 10

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="NumPy not installed")
    def test_predict_with_dict_features(self, router_with_models):
        """Test prediction with dictionary features."""
        result = router_with_models.route_and_predict(
            request_id="dict-features",
            features={"f1": 1.0, "f2": 2.0, "f3": 3.0},
        )

        assert result.prediction is not None

    def test_predict_no_model_returns_none_prediction(self):
        """Test prediction returns None when no model available."""
        router = ABTestRouter(candidate_split=0.1)
        router._initialized = True  # Skip model loading

        routing = router.route("no-model-test")
        result = router.predict(routing, [1.0, 2.0])

        assert result.prediction is None
