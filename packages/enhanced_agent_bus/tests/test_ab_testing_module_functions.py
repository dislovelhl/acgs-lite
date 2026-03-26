"""
A/B Testing Framework - Module Function Tests
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


class TestModuleLevelFunctions:
    """Tests for module-level convenience functions."""

    @pytest.fixture(autouse=True)
    def _mock_mlflow_load(self):
        """Prevent MLflow connection attempts during ABTestRouter init."""
        with patch.object(ABTestRouter, "_ensure_initialized"):
            yield

    @pytest.fixture(autouse=True)
    def reset_global_router(self):
        """Reset the global A/B test router before each test."""
        import ab_testing

        ab_testing._ab_test_router = None
        yield
        ab_testing._ab_test_router = None

    def test_get_ab_test_router_creates_singleton(self):
        """Test get_ab_test_router creates a singleton."""
        router1 = get_ab_test_router()
        router2 = get_ab_test_router()

        assert router1 is router2

    def test_get_ab_test_router_with_custom_params(self):
        """Test get_ab_test_router with custom parameters."""
        router = get_ab_test_router(
            candidate_split=0.2,
            min_samples=500,
        )

        assert router.candidate_split == 0.2
        assert router.min_samples == 500

    def test_route_request_function(self):
        """Test module-level route_request function."""
        result = route_request("module-level-test")

        assert isinstance(result, RoutingResult)
        assert result.request_id == "module-level-test"

    def test_get_ab_test_metrics_function(self):
        """Test module-level get_ab_test_metrics function."""
        metrics = get_ab_test_metrics()

        assert "ab_test_active" in metrics
        assert "champion" in metrics
        assert "candidate" in metrics

    def test_compare_models_function(self):
        """Test module-level compare_models function."""
        comparison = compare_models()

        assert isinstance(comparison, MetricsComparison)
        assert comparison.result in list(ComparisonResult)

    def test_promote_candidate_model_function(self):
        """Test module-level promote_candidate_model function."""
        result = promote_candidate_model()

        assert isinstance(result, PromotionResult)
        # Should return NOT_READY or ERROR since we don't have setup
        assert result.status in [
            PromotionStatus.NOT_READY,
            PromotionStatus.ERROR,
        ]
