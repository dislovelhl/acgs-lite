"""
A/B Testing Framework - Edge Case Tests
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


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture(autouse=True)
    def _mock_mlflow_load(self):
        """Prevent MLflow connection attempts during ABTestRouter init."""
        with patch.object(ABTestRouter, "_ensure_initialized"):
            yield

    def test_router_with_zero_candidate_split(self):
        """Test router with 0% candidate split."""
        router = ABTestRouter(candidate_split=0.0)

        # All requests should go to champion
        for i in range(100):
            result = router.route(f"zero-split-{i}")
            assert result.cohort == CohortType.CHAMPION

    def test_router_with_full_candidate_split(self):
        """Test router with 100% candidate split."""
        router = ABTestRouter(candidate_split=1.0)

        # All requests should go to candidate
        for i in range(100):
            result = router.route(f"full-split-{i}")
            assert result.cohort == CohortType.CANDIDATE

    def test_cohort_metrics_very_high_latency(self):
        """Test metrics handle very high latency values."""
        metrics = CohortMetrics(cohort=CohortType.CHAMPION)

        metrics.record_request(latency_ms=100000.0)  # 100 seconds

        assert metrics.max_latency_ms == 100000.0
        assert metrics.avg_latency_ms == 100000.0

    def test_cohort_metrics_very_low_latency(self):
        """Test metrics handle very low latency values."""
        metrics = CohortMetrics(cohort=CohortType.CHAMPION)

        metrics.record_request(latency_ms=0.001)  # 1 microsecond

        assert metrics.min_latency_ms == 0.001

    def test_router_prediction_error_handling(self):
        """Test router handles prediction errors gracefully."""
        router = ABTestRouter(candidate_split=0.1)
        router._initialized = True

        # Create model that raises error
        bad_model = MagicMock()
        bad_model.predict = MagicMock(side_effect=ValueError("Model failed"))

        router.set_champion_model(bad_model, version=1)

        routing = router.route("error-test")
        result = router.predict(routing, [1.0, 2.0])

        assert result.error is not None
        assert "Model failed" in result.error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
