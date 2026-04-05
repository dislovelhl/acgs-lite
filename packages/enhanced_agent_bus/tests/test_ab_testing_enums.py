"""
A/B Testing Framework - Enum Tests
Constitutional Hash: 608508a9bd224290

Part of the A/B testing framework test suite.
Extracted from monolithic test_ab_testing.py for better maintainability.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

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


class TestCohortType:
    """Tests for CohortType enum."""

    def test_cohort_type_values(self):
        """Test all CohortType enum values."""
        assert CohortType.CHAMPION.value == "champion"
        assert CohortType.CANDIDATE.value == "candidate"

    def test_cohort_type_is_string_enum(self):
        """Test that CohortType inherits from str."""
        assert isinstance(CohortType.CHAMPION, str)
        assert CohortType.CHAMPION == "champion"
        assert CohortType.CANDIDATE == "candidate"

    def test_cohort_type_count(self):
        """Test all expected cohort types exist."""
        cohort_values = [c.value for c in CohortType]
        assert len(cohort_values) == 2
        assert "champion" in cohort_values
        assert "candidate" in cohort_values


class TestPromotionStatus:
    """Tests for PromotionStatus enum."""

    def test_promotion_status_values(self):
        """Test all PromotionStatus enum values."""
        assert PromotionStatus.READY.value == "ready"
        assert PromotionStatus.NOT_READY.value == "not_ready"
        assert PromotionStatus.BLOCKED.value == "blocked"
        assert PromotionStatus.PROMOTED.value == "promoted"
        assert PromotionStatus.ERROR.value == "error"

    def test_promotion_status_is_string_enum(self):
        """Test that PromotionStatus inherits from str."""
        assert isinstance(PromotionStatus.READY, str)
        assert PromotionStatus.PROMOTED == "promoted"

    def test_promotion_status_count(self):
        """Test all expected promotion status values exist."""
        status_values = [s.value for s in PromotionStatus]
        assert len(status_values) == 5
        assert "ready" in status_values
        assert "error" in status_values


class TestComparisonResult:
    """Tests for ComparisonResult enum."""

    def test_comparison_result_values(self):
        """Test all ComparisonResult enum values."""
        assert ComparisonResult.CANDIDATE_BETTER.value == "candidate_better"
        assert ComparisonResult.CHAMPION_BETTER.value == "champion_better"
        assert ComparisonResult.NO_DIFFERENCE.value == "no_difference"
        assert ComparisonResult.INSUFFICIENT_DATA.value == "insufficient_data"

    def test_comparison_result_is_string_enum(self):
        """Test that ComparisonResult inherits from str."""
        assert isinstance(ComparisonResult.CANDIDATE_BETTER, str)
        assert ComparisonResult.NO_DIFFERENCE == "no_difference"

    def test_comparison_result_count(self):
        """Test all expected comparison results exist."""
        result_values = [r.value for r in ComparisonResult]
        assert len(result_values) == 4
        assert "candidate_better" in result_values
        assert "insufficient_data" in result_values
