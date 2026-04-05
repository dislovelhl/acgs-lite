"""
A/B Testing Framework - Router Promotion Tests
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


class TestABTestRouterPromotion:
    """Tests for model promotion functionality."""

    @pytest.fixture(autouse=True)
    def _mock_mlflow_load(self):
        """Prevent MLflow connection attempts during ABTestRouter init."""
        with patch.object(ABTestRouter, "_ensure_initialized"):
            yield

    @pytest.fixture
    def promotable_router(self):
        """Create router where candidate is ready for promotion."""
        router = ABTestRouter(candidate_split=0.1, min_samples=50)

        # Mock version manager
        router._version_manager = MagicMock()
        router._version_manager.promote_candidate_to_champion = MagicMock(return_value=True)

        # Set models
        router.champion_model = MagicMock()
        router.champion_version = 1
        router.candidate_model = MagicMock()
        router.candidate_version = 2

        # Champion: 80% accuracy
        for i in range(200):
            router._champion_metrics.record_request(
                latency_ms=50.0,
                prediction=1 if i < 160 else 0,
                actual=1,
            )

        # Candidate: 95% accuracy (clearly better)
        for i in range(200):
            router._candidate_metrics.record_request(
                latency_ms=45.0,
                prediction=1 if i < 190 else 0,
                actual=1,
            )

        return router

    def test_promote_candidate_insufficient_data(self):
        """Test promotion blocked due to insufficient data."""
        router = ABTestRouter(min_samples=1000)

        result = router.promote_candidate()

        assert result.status == PromotionStatus.NOT_READY
        assert "Insufficient data" in result.error_message

    def test_promote_candidate_blocked_worse_performance(self):
        """Test promotion blocked when candidate is worse."""
        router = ABTestRouter(min_samples=50)

        # Champion: 95% accuracy
        for i in range(200):
            router._champion_metrics.record_request(
                latency_ms=50.0,
                prediction=1 if i < 190 else 0,
                actual=1,
            )

        # Candidate: 70% accuracy (worse)
        for i in range(200):
            router._candidate_metrics.record_request(
                latency_ms=45.0,
                prediction=1 if i < 140 else 0,
                actual=1,
            )

        result = router.promote_candidate()

        assert result.status == PromotionStatus.BLOCKED
        assert "not better" in result.error_message

    def test_promote_candidate_no_version_manager(self, promotable_router):
        """Test promotion fails without version manager."""
        promotable_router._version_manager = None

        result = promotable_router.promote_candidate()

        assert result.status == PromotionStatus.ERROR
        assert "Version manager not available" in result.error_message

    def test_promote_candidate_force(self):
        """Test forced promotion bypasses validation."""
        router = ABTestRouter(min_samples=1000)

        # Mock version manager
        router._version_manager = MagicMock()
        router._version_manager.promote_candidate_to_champion = MagicMock(return_value=True)
        router.candidate_model = MagicMock()
        router.candidate_version = 2

        result = router.promote_candidate(force=True)

        assert result.status == PromotionStatus.PROMOTED

    def test_promote_candidate_success(self, promotable_router):
        """Test successful promotion."""
        result = promotable_router.promote_candidate()

        assert result.status == PromotionStatus.PROMOTED
        assert result.previous_champion_version == 1
        assert result.new_champion_version == 2
        assert result.promoted_at is not None

        # Verify models swapped
        assert promotable_router.champion_version == 2
        assert promotable_router.candidate_model is None

    def test_reset_metrics_after_promotion(self, promotable_router):
        """Test metrics are reset after promotion."""
        # Record initial state
        initial_champion_requests = promotable_router._champion_metrics.request_count

        assert initial_champion_requests > 0

        promotable_router.promote_candidate()

        # Metrics should be reset
        assert promotable_router._champion_metrics.request_count == 0
        assert promotable_router._candidate_metrics.request_count == 0
