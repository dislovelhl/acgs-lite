"""
A/B Testing Framework - Configuration Tests
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


class TestConfigurationConstants:
    """Tests for configuration constants."""

    def test_ab_test_split_from_env(self):
        """Test AB_TEST_SPLIT uses environment variable."""
        expected = float(os.getenv("AB_TEST_SPLIT", "0.1"))
        assert AB_TEST_SPLIT == expected

    def test_champion_alias_from_env(self):
        """Test CHAMPION_ALIAS uses environment variable."""
        expected = os.getenv("CHAMPION_ALIAS", "champion")
        assert CHAMPION_ALIAS == expected

    def test_candidate_alias_from_env(self):
        """Test CANDIDATE_ALIAS uses environment variable."""
        expected = os.getenv("CANDIDATE_ALIAS", "candidate")
        assert CANDIDATE_ALIAS == expected

    def test_ab_test_min_samples_from_env(self):
        """Test AB_TEST_MIN_SAMPLES uses environment variable."""
        expected = int(os.getenv("AB_TEST_MIN_SAMPLES", "1000"))
        assert AB_TEST_MIN_SAMPLES == expected

    def test_ab_test_confidence_level_from_env(self):
        """Test AB_TEST_CONFIDENCE_LEVEL uses environment variable."""
        expected = float(os.getenv("AB_TEST_CONFIDENCE_LEVEL", "0.95"))
        assert AB_TEST_CONFIDENCE_LEVEL == expected

    def test_ab_test_min_improvement_from_env(self):
        """Test AB_TEST_MIN_IMPROVEMENT uses environment variable."""
        expected = float(os.getenv("AB_TEST_MIN_IMPROVEMENT", "0.01"))
        assert AB_TEST_MIN_IMPROVEMENT == expected

    def test_model_registry_name_from_env(self):
        """Test MODEL_REGISTRY_NAME uses environment variable."""
        expected = os.getenv("MODEL_REGISTRY_NAME", "governance_impact_scorer")
        assert MODEL_REGISTRY_NAME == expected


class TestAvailabilityFlags:
    """Tests for availability flag exports."""

    def test_numpy_available_flag(self):
        """Test NUMPY_AVAILABLE flag is exported."""
        assert isinstance(NUMPY_AVAILABLE, bool)
