"""
A/B Testing Framework - Traffic Split Tests
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


class TestABTestRouterTrafficSplit:
    """
    Critical tests for traffic split verification.

    Per spec: Traffic split within ±2% variance over 1000 requests.
    """

    @pytest.fixture(autouse=True)
    def _mock_mlflow(self):
        """Prevent MLflow connection attempts during tests."""
        with patch.object(
            ABTestRouter,
            "_ensure_initialized",
        ):
            yield

    @pytest.fixture
    def router_10_percent_split(self):
        """Create router with 10% candidate split."""
        return ABTestRouter(candidate_split=0.1)

    @pytest.fixture
    def router_20_percent_split(self):
        """Create router with 20% candidate split."""
        return ABTestRouter(candidate_split=0.2)

    @pytest.fixture
    def router_50_percent_split(self):
        """Create router with 50% candidate split."""
        return ABTestRouter(candidate_split=0.5)

    def test_traffic_split_10_percent_within_tolerance(self, router_10_percent_split):
        """
        CRITICAL TEST: Verify 10% candidate split within ±2% variance.

        Expected: ~10% requests to candidate (80-120 out of 1000)
        Tolerance: ±2% means 8-12% acceptable (80-120 out of 1000)
        """
        distribution = router_10_percent_split.get_traffic_distribution(n_requests=1000)

        expected_candidate_split = 0.1
        actual_candidate_split = distribution["actual_candidate_split"]
        variance = distribution["variance"]

        # Verify within tolerance
        assert variance < 0.02, (
            f"Traffic split variance {variance:.4f} exceeds ±2% tolerance. "
            f"Expected ~{expected_candidate_split:.0%}, "
            f"got {actual_candidate_split:.2%}"
        )

        # Additional sanity checks
        assert distribution["n_requests"] == 1000
        assert distribution["champion_count"] + distribution["candidate_count"] == 1000
        assert distribution["within_tolerance"] is True

    def test_traffic_split_10_percent_extended(self, router_10_percent_split):
        """Test 10% split with more requests for statistical confidence."""
        distribution = router_10_percent_split.get_traffic_distribution(n_requests=5000)

        variance = distribution["variance"]

        # With more samples, variance should be even smaller
        assert variance < 0.015, f"Extended test variance {variance:.4f} too high"
        assert distribution["within_tolerance"] is True

    def test_traffic_split_20_percent_within_tolerance(self, router_20_percent_split):
        """Verify 20% candidate split within ±2% variance."""
        distribution = router_20_percent_split.get_traffic_distribution(n_requests=1000)

        variance = distribution["variance"]
        actual_split = distribution["actual_candidate_split"]

        assert variance < 0.02, (
            f"Traffic split variance {variance:.4f} exceeds ±2% tolerance for 20% split. "
            f"Got {actual_split:.2%}"
        )

    def test_traffic_split_50_percent_within_tolerance(self, router_50_percent_split):
        """Verify 50% candidate split within ±2% variance."""
        distribution = router_50_percent_split.get_traffic_distribution(n_requests=1000)

        variance = distribution["variance"]
        actual_split = distribution["actual_candidate_split"]

        assert variance < 0.02, (
            f"Traffic split variance {variance:.4f} exceeds ±2% tolerance for 50% split. "
            f"Got {actual_split:.2%}"
        )

    def test_traffic_distribution_structure(self, router_10_percent_split):
        """Test traffic distribution returns complete structure."""
        distribution = router_10_percent_split.get_traffic_distribution(n_requests=100)

        assert "n_requests" in distribution
        assert "champion_count" in distribution
        assert "candidate_count" in distribution
        assert "actual_champion_split" in distribution
        assert "actual_candidate_split" in distribution
        assert "expected_candidate_split" in distribution
        assert "variance" in distribution
        assert "within_tolerance" in distribution

    def test_traffic_split_reproducible(self, router_10_percent_split):
        """Test traffic split is reproducible with same request IDs."""
        dist1 = router_10_percent_split.get_traffic_distribution(n_requests=100)
        dist2 = router_10_percent_split.get_traffic_distribution(n_requests=100)

        # Same request IDs should produce same distribution
        assert dist1["champion_count"] == dist2["champion_count"]
        assert dist1["candidate_count"] == dist2["candidate_count"]

    def test_traffic_split_manual_verification(self):
        """Manually verify traffic split by routing individual requests."""
        router = ABTestRouter(candidate_split=0.1)

        champion_count = 0
        candidate_count = 0

        for i in range(1000):
            result = router.route(f"manual-test-{i}")
            if result.cohort == CohortType.CHAMPION:
                champion_count += 1
            else:
                candidate_count += 1

        actual_candidate_split = candidate_count / 1000
        variance = abs(actual_candidate_split - 0.1)

        assert variance < 0.02, (
            f"Manual traffic split variance {variance:.4f} exceeds ±2% tolerance. "
            f"Champion: {champion_count}, Candidate: {candidate_count}"
        )

    def test_different_request_ids_vary(self):
        """Test that different request patterns produce varying but consistent routing."""
        router = ABTestRouter(candidate_split=0.1)

        # Route requests with different ID patterns
        patterns = [
            [f"alpha-{i}" for i in range(1000)],
            [f"beta-{i}" for i in range(1000)],
            [f"gamma-{i}" for i in range(1000)],
        ]

        variances = []
        for pattern in patterns:
            candidate_count = sum(
                1 for req_id in pattern if router.route(req_id).cohort == CohortType.CANDIDATE
            )
            variance = abs(candidate_count / 1000 - 0.1)
            variances.append(variance)
            # Clean up tracking
            for req_id in pattern:
                router._request_cohorts.pop(req_id, None)

        # All patterns should be within tolerance
        for i, variance in enumerate(variances):
            assert variance < 0.02, f"Pattern {i} variance {variance:.4f} exceeds ±2% tolerance"
