"""
A/B Testing Framework - Router Comparison Tests
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


class TestABTestRouterComparison:
    """Tests for model comparison functionality."""

    @pytest.fixture(autouse=True)
    def _mock_mlflow_load(self):
        """Prevent MLflow connection attempts during ABTestRouter init."""
        with patch.object(ABTestRouter, "_ensure_initialized"):
            yield

    @pytest.fixture
    def router_with_data(self):
        """Create router with sample data in both cohorts."""
        router = ABTestRouter(candidate_split=0.1, min_samples=50)

        # Simulate champion requests (90% accuracy)
        for i in range(100):
            router._champion_metrics.record_request(
                latency_ms=50.0 + i * 0.1,
                prediction=1 if i < 90 else 0,
                actual=1,
            )

        # Simulate candidate requests (85% accuracy)
        for i in range(100):
            router._candidate_metrics.record_request(
                latency_ms=45.0 + i * 0.1,
                prediction=1 if i < 85 else 0,
                actual=1,
            )

        return router

    def test_compare_metrics_insufficient_data(self):
        """Test comparison with insufficient data."""
        router = ABTestRouter(min_samples=1000)

        # Add just a few samples
        for _ in range(10):
            router._champion_metrics.record_request(latency_ms=50.0, prediction=1, actual=1)
            router._candidate_metrics.record_request(latency_ms=45.0, prediction=1, actual=1)

        comparison = router.compare_metrics()

        assert comparison.result == ComparisonResult.INSUFFICIENT_DATA
        assert comparison.is_significant is False
        assert "Need more samples" in comparison.recommendation

    def test_compare_metrics_champion_better(self, router_with_data):
        """Test comparison when champion is better."""
        comparison = router_with_data.compare_metrics()

        # Champion has 90% accuracy, candidate has 85%
        assert comparison.accuracy_delta == pytest.approx(-0.05, rel=0.01)
        assert comparison.champion_metrics.accuracy == pytest.approx(0.90, rel=0.01)
        assert comparison.candidate_metrics.accuracy == pytest.approx(0.85, rel=0.01)

    def test_compare_metrics_candidate_better(self):
        """Test comparison when candidate is better."""
        router = ABTestRouter(candidate_split=0.1, min_samples=50)

        # Champion: 80% accuracy
        for i in range(100):
            router._champion_metrics.record_request(
                latency_ms=50.0,
                prediction=1 if i < 80 else 0,
                actual=1,
            )

        # Candidate: 95% accuracy
        for i in range(100):
            router._candidate_metrics.record_request(
                latency_ms=45.0,
                prediction=1 if i < 95 else 0,
                actual=1,
            )

        comparison = router.compare_metrics()

        assert comparison.accuracy_delta > 0
        assert comparison.candidate_metrics.accuracy > comparison.champion_metrics.accuracy

    def test_compare_metrics_no_difference(self):
        """Test comparison with similar performance."""
        router = ABTestRouter(candidate_split=0.1, min_samples=50)

        # Both at ~90% accuracy
        for i in range(100):
            router._champion_metrics.record_request(
                latency_ms=50.0,
                prediction=1 if i < 90 else 0,
                actual=1,
            )
            router._candidate_metrics.record_request(
                latency_ms=50.0,
                prediction=1 if i < 90 else 0,
                actual=1,
            )

        comparison = router.compare_metrics()

        assert abs(comparison.accuracy_delta) < router.min_improvement
