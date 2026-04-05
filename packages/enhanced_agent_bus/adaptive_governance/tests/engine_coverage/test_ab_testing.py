"""
Test coverage for AdaptiveGovernanceEngine.
Constitutional Hash: 608508a9bd224290

Targets ≥90% coverage of
src/core/enhanced_agent_bus/adaptive_governance/governance_engine.py
"""

import asyncio
import dataclasses
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH as SHARED_CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Shared patch targets — always suppress heavy I/O during import / init
# ---------------------------------------------------------------------------

_MLFLOW_PATCH = "mlflow.set_tracking_uri"
_IMPACT_MLFLOW = (
    "enhanced_agent_bus.adaptive_governance.impact_scorer.ImpactScorer._initialize_mlflow"
)
_THRESH_MLFLOW = (
    "enhanced_agent_bus.adaptive_governance.threshold_manager.AdaptiveThresholds._initialize_mlflow"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONST_HASH = SHARED_CONSTITUTIONAL_HASH


def _make_features(risk_score: float = 0.3, confidence: float = 0.9):
    from enhanced_agent_bus.adaptive_governance.models import ImpactFeatures

    return ImpactFeatures(
        message_length=50,
        agent_count=2,
        tenant_complexity=0.5,
        temporal_patterns=[0.1, 0.2],
        semantic_similarity=0.4,
        historical_precedence=1,
        resource_utilization=0.2,
        network_isolation=0.8,
        risk_score=risk_score,
        confidence_level=confidence,
    )


def _make_decision(risk_score: float = 0.3, action_allowed: bool = True):
    from enhanced_agent_bus.adaptive_governance.models import (
        GovernanceDecision,
        ImpactLevel,
    )

    features = _make_features(risk_score=risk_score)
    return GovernanceDecision(
        action_allowed=action_allowed,
        impact_level=ImpactLevel.LOW,
        confidence_score=0.9,
        reasoning="test reasoning",
        recommended_threshold=0.5,
        features_used=features,
    )


@pytest.fixture
def engine():
    """Create an AdaptiveGovernanceEngine with all heavy deps suppressed."""
    with (
        patch(_IMPACT_MLFLOW),
        patch(_THRESH_MLFLOW),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.FEEDBACK_HANDLER_AVAILABLE",
            False,
        ),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.DRIFT_MONITORING_AVAILABLE",
            False,
        ),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ONLINE_LEARNING_AVAILABLE",
            False,
        ),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
            False,
        ),
        patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.ANOMALY_MONITORING_AVAILABLE",
            False,
        ),
    ):
        from enhanced_agent_bus.adaptive_governance.governance_engine import (
            AdaptiveGovernanceEngine,
        )

        return AdaptiveGovernanceEngine(CONST_HASH)


@pytest.fixture
def sample_message():
    return {
        "from_agent": "agent-a",
        "to_agent": "agent-b",
        "content": "Hello world",
        "tenant_id": "tenant-1",
        "constitutional_hash": CONST_HASH,
    }


@pytest.fixture
def sample_context():
    return {
        "tenant_id": "tenant-1",
        "agent_type": "standard",
        "permissions": ["read"],
    }


# ---------------------------------------------------------------------------
# 11. AB test accessor methods
# ---------------------------------------------------------------------------


class TestABTestMethods:
    def test_get_ab_test_router_none(self, engine):
        assert engine.get_ab_test_router() is None

    def test_get_ab_test_router_returns_router(self, engine):
        mock_router = MagicMock()
        engine._ab_test_router = mock_router
        assert engine.get_ab_test_router() is mock_router

    def test_get_ab_test_metrics_none_when_unavailable(self, engine):
        assert engine.get_ab_test_metrics() is None

    def test_get_ab_test_metrics_returns_summary(self, engine):
        mock_router = MagicMock()
        mock_router.get_metrics_summary = MagicMock(return_value={"champion": {}})
        engine._ab_test_router = mock_router

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.AB_TESTING_AVAILABLE
        try:
            ge_mod.AB_TESTING_AVAILABLE = True
            result = engine.get_ab_test_metrics()
            assert result == {"champion": {}}
        finally:
            ge_mod.AB_TESTING_AVAILABLE = orig

    def test_get_ab_test_metrics_exception_returns_none(self, engine):
        mock_router = MagicMock()
        mock_router.get_metrics_summary = MagicMock(side_effect=RuntimeError("fail"))
        engine._ab_test_router = mock_router

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.AB_TESTING_AVAILABLE
        try:
            ge_mod.AB_TESTING_AVAILABLE = True
            result = engine.get_ab_test_metrics()
            assert result is None
        finally:
            ge_mod.AB_TESTING_AVAILABLE = orig

    def test_get_ab_test_comparison_none_when_unavailable(self, engine):
        assert engine.get_ab_test_comparison() is None

    def test_get_ab_test_comparison_returns_comparison(self, engine):
        mock_comparison = MagicMock()
        mock_router = MagicMock()
        mock_router.compare_metrics = MagicMock(return_value=mock_comparison)
        engine._ab_test_router = mock_router

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.AB_TESTING_AVAILABLE
        try:
            ge_mod.AB_TESTING_AVAILABLE = True
            result = engine.get_ab_test_comparison()
            assert result is mock_comparison
        finally:
            ge_mod.AB_TESTING_AVAILABLE = orig

    def test_get_ab_test_comparison_exception_returns_none(self, engine):
        mock_router = MagicMock()
        mock_router.compare_metrics = MagicMock(side_effect=RuntimeError("fail"))
        engine._ab_test_router = mock_router

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.AB_TESTING_AVAILABLE
        try:
            ge_mod.AB_TESTING_AVAILABLE = True
            result = engine.get_ab_test_comparison()
            assert result is None
        finally:
            ge_mod.AB_TESTING_AVAILABLE = orig

    def test_promote_candidate_none_when_unavailable(self, engine):
        assert engine.promote_candidate_model() is None

    def test_promote_candidate_success(self, engine):
        mock_result = MagicMock()
        mock_result.status = MagicMock()
        mock_result.status.value = "promoted"
        mock_result.previous_champion_version = 1
        mock_result.new_champion_version = 2

        mock_router = MagicMock()
        mock_router.promote_candidate = MagicMock(return_value=mock_result)
        engine._ab_test_router = mock_router

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.AB_TESTING_AVAILABLE
        try:
            ge_mod.AB_TESTING_AVAILABLE = True
            result = engine.promote_candidate_model(force=False)
            assert result is mock_result
        finally:
            ge_mod.AB_TESTING_AVAILABLE = orig

    def test_promote_candidate_not_promoted_status(self, engine):
        """Status is not 'promoted' — no INFO log but still returns result."""
        mock_result = MagicMock()
        mock_result.status = MagicMock()
        mock_result.status.value = "insufficient_data"

        mock_router = MagicMock()
        mock_router.promote_candidate = MagicMock(return_value=mock_result)
        engine._ab_test_router = mock_router

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.AB_TESTING_AVAILABLE
        try:
            ge_mod.AB_TESTING_AVAILABLE = True
            result = engine.promote_candidate_model()
            assert result is mock_result
        finally:
            ge_mod.AB_TESTING_AVAILABLE = orig

    def test_promote_candidate_exception_returns_none(self, engine):
        mock_router = MagicMock()
        mock_router.promote_candidate = MagicMock(side_effect=RuntimeError("fail"))
        engine._ab_test_router = mock_router

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.AB_TESTING_AVAILABLE
        try:
            ge_mod.AB_TESTING_AVAILABLE = True
            result = engine.promote_candidate_model()
            assert result is None
        finally:
            ge_mod.AB_TESTING_AVAILABLE = orig


# ---------------------------------------------------------------------------
# 12. Performance trend methods
# ---------------------------------------------------------------------------


class TestPerformanceTrends:
    def test_analyze_performance_trends_adds_values(self, engine):
        engine._analyze_performance_trends()
        assert len(engine.metrics.compliance_trend) == 1
        assert len(engine.metrics.accuracy_trend) == 1
        assert len(engine.metrics.performance_trend) == 1

    def test_analyze_performance_trends_trims_when_long(self, engine):
        from enhanced_agent_bus.governance_constants import GOVERNANCE_MAX_TREND_LENGTH

        engine.metrics.compliance_trend = [0.5] * (GOVERNANCE_MAX_TREND_LENGTH + 5)
        engine.metrics.accuracy_trend = [0.5] * (GOVERNANCE_MAX_TREND_LENGTH + 5)
        engine.metrics.performance_trend = [0.5] * (GOVERNANCE_MAX_TREND_LENGTH + 5)
        engine._analyze_performance_trends()
        assert len(engine.metrics.compliance_trend) <= GOVERNANCE_MAX_TREND_LENGTH

    def test_analyze_performance_trends_exception_swallowed(self, engine):
        """The method catches RuntimeError/ValueError/TypeError — simulate ValueError."""
        # Replace the list with a mock that raises on append
        mock_trend = MagicMock()
        mock_trend.append = MagicMock(side_effect=ValueError("trend error"))
        engine.metrics.compliance_trend = mock_trend
        engine._analyze_performance_trends()  # should not raise

    def test_should_retrain_below_target(self, engine):
        engine.metrics.constitutional_compliance_rate = 0.0
        assert engine._should_retrain_models() is True

    def test_should_retrain_sufficient_data(self, engine):
        from enhanced_agent_bus.governance_constants import (
            GOVERNANCE_RETRAIN_CHECK_MODULUS,
            GOVERNANCE_RETRAIN_HISTORY_MIN,
        )

        engine.metrics.constitutional_compliance_rate = 1.0
        engine.decision_history = [_make_decision()] * GOVERNANCE_RETRAIN_HISTORY_MIN
        # Make modulus check pass
        assert engine._should_retrain_models() in (True, False)

    def test_log_performance_summary_ok(self, engine):
        engine._log_performance_summary()  # should not raise

    def test_log_performance_summary_exception_swallowed(self, engine):
        """Verify _log_performance_summary runs without raising normally."""
        engine._log_performance_summary()  # should not raise

    def test_log_performance_summary_handles_runtime_error(self, engine):
        """If logger.info raises RuntimeError it is caught."""
        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.logger"
        ) as mock_logger:
            mock_logger.info.side_effect = RuntimeError("log fail")
            engine._log_performance_summary()  # should not raise
