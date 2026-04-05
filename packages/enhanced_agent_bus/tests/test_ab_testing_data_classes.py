"""
A/B Testing Framework - Data Class Tests
Constitutional Hash: 608508a9bd224290

Part of the A/B testing framework test suite.
Extracted from monolithic test_ab_testing.py for better maintainability.
"""

import os
import sys
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock

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


class TestCohortMetrics:
    """Tests for CohortMetrics dataclass."""

    def test_cohort_metrics_defaults(self):
        """Test CohortMetrics with default values."""
        metrics = CohortMetrics(cohort=CohortType.CHAMPION)

        assert metrics.cohort == CohortType.CHAMPION
        assert metrics.request_count == 0
        assert metrics.correct_predictions == 0
        assert metrics.total_predictions == 0
        assert metrics.accuracy == 0.0
        assert metrics.total_latency_ms == 0.0
        assert metrics.min_latency_ms == float("inf")
        assert metrics.max_latency_ms == 0.0
        assert metrics.p50_latency_ms == 0.0
        assert metrics.p95_latency_ms == 0.0
        assert metrics.p99_latency_ms == 0.0
        assert metrics.errors == 0
        assert metrics.first_request_at is None
        assert metrics.last_request_at is None
        assert metrics.latencies == []

    def test_cohort_metrics_record_request(self):
        """Test recording a request updates metrics correctly."""
        metrics = CohortMetrics(cohort=CohortType.CANDIDATE)

        metrics.record_request(latency_ms=50.0, prediction=1, actual=1)

        assert metrics.request_count == 1
        assert metrics.total_latency_ms == 50.0
        assert metrics.min_latency_ms == 50.0
        assert metrics.max_latency_ms == 50.0
        assert metrics.correct_predictions == 1
        assert metrics.total_predictions == 1
        assert metrics.accuracy == 1.0
        assert metrics.first_request_at is not None
        assert metrics.last_request_at is not None
        assert len(metrics.latencies) == 1

    def test_cohort_metrics_record_multiple_requests(self):
        """Test recording multiple requests."""
        metrics = CohortMetrics(cohort=CohortType.CHAMPION)

        metrics.record_request(latency_ms=10.0, prediction=1, actual=1)
        metrics.record_request(latency_ms=20.0, prediction=0, actual=1)
        metrics.record_request(latency_ms=30.0, prediction=1, actual=1)

        assert metrics.request_count == 3
        assert metrics.total_latency_ms == 60.0
        assert metrics.min_latency_ms == 10.0
        assert metrics.max_latency_ms == 30.0
        assert metrics.correct_predictions == 2
        assert metrics.total_predictions == 3
        assert metrics.accuracy == pytest.approx(2 / 3, rel=1e-6)

    def test_cohort_metrics_record_error(self):
        """Test recording an error request."""
        metrics = CohortMetrics(cohort=CohortType.CANDIDATE)

        metrics.record_request(latency_ms=100.0, is_error=True)

        assert metrics.request_count == 1
        assert metrics.errors == 1
        assert metrics.total_predictions == 0  # Errors don't count as predictions
        assert metrics.total_latency_ms == 100.0

    def test_cohort_metrics_avg_latency(self):
        """Test average latency calculation."""
        metrics = CohortMetrics(cohort=CohortType.CHAMPION)

        metrics.record_request(latency_ms=10.0)
        metrics.record_request(latency_ms=20.0)
        metrics.record_request(latency_ms=30.0)

        assert metrics.avg_latency_ms == pytest.approx(20.0, rel=1e-6)

    def test_cohort_metrics_avg_latency_zero_requests(self):
        """Test average latency with no requests."""
        metrics = CohortMetrics(cohort=CohortType.CANDIDATE)

        assert metrics.avg_latency_ms == 0.0

    def test_cohort_metrics_calculate_percentiles(self):
        """Test latency percentile calculation."""
        metrics = CohortMetrics(cohort=CohortType.CHAMPION)

        # Record 100 requests with increasing latency
        for i in range(100):
            metrics.record_request(latency_ms=float(i + 1))

        metrics.calculate_percentiles()

        assert metrics.p50_latency_ms == pytest.approx(50.0, rel=0.1)
        assert metrics.p95_latency_ms == pytest.approx(95.0, rel=0.1)
        assert metrics.p99_latency_ms == pytest.approx(99.0, rel=0.1)

    def test_cohort_metrics_calculate_percentiles_empty(self):
        """Test percentile calculation with no latencies."""
        metrics = CohortMetrics(cohort=CohortType.CANDIDATE)

        metrics.calculate_percentiles()

        assert metrics.p50_latency_ms == 0.0
        assert metrics.p95_latency_ms == 0.0
        assert metrics.p99_latency_ms == 0.0

    def test_cohort_metrics_to_dict(self):
        """Test serialization to dictionary."""
        metrics = CohortMetrics(cohort=CohortType.CHAMPION)
        metrics.record_request(latency_ms=50.0, prediction=1, actual=1)
        metrics.record_request(latency_ms=75.0, prediction=0, actual=0)

        result = metrics.to_dict()

        assert result["cohort"] == "champion"
        assert result["request_count"] == 2
        assert result["accuracy"] == 1.0
        assert result["avg_latency_ms"] == pytest.approx(62.5, rel=1e-6)
        assert result["min_latency_ms"] == 50.0
        assert result["max_latency_ms"] == 75.0
        assert "first_request_at" in result
        assert "last_request_at" in result
        assert "error_rate" in result


class TestRoutingResult:
    """Tests for RoutingResult dataclass."""

    def test_routing_result_creation(self):
        """Test creating RoutingResult."""
        result = RoutingResult(
            cohort=CohortType.CHAMPION,
            request_id="req-123",
            model_version=5,
        )

        assert result.cohort == CohortType.CHAMPION
        assert result.request_id == "req-123"
        assert result.model_version == 5
        assert result.routed_at is not None

    def test_routing_result_default_timestamp(self):
        """Test RoutingResult has default timestamp."""
        result = RoutingResult(
            cohort=CohortType.CANDIDATE,
            request_id="req-456",
        )

        assert isinstance(result.routed_at, datetime)
        assert result.model_version is None


class TestPredictionResult:
    """Tests for PredictionResult dataclass."""

    def test_prediction_result_minimal(self):
        """Test PredictionResult with minimal fields."""
        result = PredictionResult(
            prediction=1,
            cohort=CohortType.CHAMPION,
            request_id="req-123",
            latency_ms=50.0,
        )

        assert result.prediction == 1
        assert result.cohort == CohortType.CHAMPION
        assert result.request_id == "req-123"
        assert result.latency_ms == 50.0
        assert result.model_version is None
        assert result.confidence is None
        assert result.probabilities is None
        assert result.error is None

    def test_prediction_result_full(self):
        """Test PredictionResult with all fields."""
        result = PredictionResult(
            prediction=0,
            cohort=CohortType.CANDIDATE,
            request_id="req-789",
            latency_ms=75.0,
            model_version=3,
            confidence=0.95,
            probabilities={0: 0.95, 1: 0.05},
            error=None,
        )

        assert result.prediction == 0
        assert result.model_version == 3
        assert result.confidence == 0.95
        assert result.probabilities[0] == 0.95

    def test_prediction_result_with_error(self):
        """Test PredictionResult with error."""
        result = PredictionResult(
            prediction=None,
            cohort=CohortType.CHAMPION,
            request_id="req-err",
            latency_ms=100.0,
            error="Model not loaded",
        )

        assert result.prediction is None
        assert result.error == "Model not loaded"


class TestMetricsComparison:
    """Tests for MetricsComparison dataclass."""

    @pytest.fixture
    def champion_metrics(self):
        """Create champion cohort metrics."""
        metrics = CohortMetrics(cohort=CohortType.CHAMPION)
        for i in range(100):
            metrics.record_request(
                latency_ms=50.0 + i * 0.1,
                prediction=i % 2,
                actual=i % 2,  # 100% accuracy
            )
        return metrics

    @pytest.fixture
    def candidate_metrics(self):
        """Create candidate cohort metrics."""
        metrics = CohortMetrics(cohort=CohortType.CANDIDATE)
        for i in range(50):
            metrics.record_request(
                latency_ms=40.0 + i * 0.1,
                prediction=i % 2,
                actual=i % 2,  # 100% accuracy
            )
        return metrics

    def test_metrics_comparison_creation(self, champion_metrics, candidate_metrics):
        """Test MetricsComparison creation."""
        comparison = MetricsComparison(
            champion_metrics=champion_metrics,
            candidate_metrics=candidate_metrics,
            result=ComparisonResult.NO_DIFFERENCE,
            accuracy_delta=0.0,
            latency_delta_ms=-10.0,
            sample_size_champion=100,
            sample_size_candidate=50,
            is_significant=False,
            candidate_is_better=False,
            recommendation="Continue testing",
        )

        assert comparison.result == ComparisonResult.NO_DIFFERENCE
        assert comparison.accuracy_delta == 0.0
        assert comparison.latency_delta_ms == -10.0
        assert comparison.sample_size_champion == 100
        assert comparison.sample_size_candidate == 50
        assert comparison.is_significant is False
        assert comparison.candidate_is_better is False

    def test_metrics_comparison_to_dict(self, champion_metrics, candidate_metrics):
        """Test MetricsComparison serialization."""
        comparison = MetricsComparison(
            champion_metrics=champion_metrics,
            candidate_metrics=candidate_metrics,
            result=ComparisonResult.CANDIDATE_BETTER,
            accuracy_delta=0.05,
            latency_delta_ms=-5.0,
            sample_size_champion=100,
            sample_size_candidate=50,
            is_significant=True,
            candidate_is_better=True,
            recommendation="Promote candidate",
        )

        result = comparison.to_dict()

        assert result["result"] == "candidate_better"
        assert result["accuracy_delta"] == 0.05
        assert result["latency_delta_ms"] == -5.0
        assert result["is_significant"] is True
        assert result["candidate_is_better"] is True
        assert "champion_metrics" in result
        assert "candidate_metrics" in result
        assert "compared_at" in result


class TestPromotionResult:
    """Tests for PromotionResult dataclass."""

    def test_promotion_result_success(self):
        """Test PromotionResult for successful promotion."""
        result = PromotionResult(
            status=PromotionStatus.PROMOTED,
            previous_champion_version=2,
            new_champion_version=3,
            promoted_at=datetime.now(UTC),
        )

        assert result.status == PromotionStatus.PROMOTED
        assert result.previous_champion_version == 2
        assert result.new_champion_version == 3
        assert result.promoted_at is not None
        assert result.error_message is None

    def test_promotion_result_blocked(self):
        """Test PromotionResult for blocked promotion."""
        result = PromotionResult(
            status=PromotionStatus.BLOCKED,
            error_message="Candidate performance is worse",
        )

        assert result.status == PromotionStatus.BLOCKED
        assert result.error_message is not None
        assert result.new_champion_version is None

    def test_promotion_result_not_ready(self):
        """Test PromotionResult for not ready state."""
        result = PromotionResult(
            status=PromotionStatus.NOT_READY,
            error_message="Insufficient samples",
        )

        assert result.status == PromotionStatus.NOT_READY
