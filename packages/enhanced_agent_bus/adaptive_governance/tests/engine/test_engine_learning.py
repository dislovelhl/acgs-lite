from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH as CONST_HASH
from enhanced_agent_bus.adaptive_governance.governance_engine import (
    AdaptiveGovernanceEngine,
)
from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    GovernanceMode,
    ImpactFeatures,
    ImpactLevel,
)
from enhanced_agent_bus.adaptive_governance.tests.engine.helpers import (
    _make_decision,
    _make_features,
)

_MLFLOW_PATCH = "mlflow.set_tracking_uri"
_IMPACT_MLFLOW = (
    "enhanced_agent_bus.adaptive_governance.impact_scorer.ImpactScorer._initialize_mlflow"
)
_THRESH_MLFLOW = (
    "enhanced_agent_bus.adaptive_governance.threshold_manager.AdaptiveThresholds._initialize_mlflow"  # noqa: E501
)


class TestUpdateRiverModel:
    def test_noop_when_river_unavailable(self, engine):
        engine.river_model = None
        decision = _make_decision()
        engine._update_river_model(decision, 0.5)  # should not raise

    def test_updates_river_model(self, engine):
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.total_samples = 10
        mock_model = MagicMock()
        mock_model.learn_from_feedback = MagicMock(return_value=mock_result)
        mock_model.adapter = MagicMock()
        mock_model.adapter.is_ready = False
        engine.river_model = mock_model

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.ONLINE_LEARNING_AVAILABLE
        try:
            ge_mod.ONLINE_LEARNING_AVAILABLE = True
            decision = _make_decision()
            engine._update_river_model(decision, 0.5)
            mock_model.learn_from_feedback.assert_called_once()
        finally:
            ge_mod.ONLINE_LEARNING_AVAILABLE = orig

    def test_river_adapter_ready_logs(self, engine):
        """Covers branch: adapter.is_ready=True and scorer not yet trained."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.total_samples = 50
        mock_model = MagicMock()
        mock_model.learn_from_feedback = MagicMock(return_value=mock_result)
        mock_model.adapter = MagicMock()
        mock_model.adapter.is_ready = True
        engine.river_model = mock_model
        engine.impact_scorer.model_trained = False

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.ONLINE_LEARNING_AVAILABLE
        try:
            ge_mod.ONLINE_LEARNING_AVAILABLE = True
            engine._update_river_model(_make_decision(), 0.5)
        finally:
            ge_mod.ONLINE_LEARNING_AVAILABLE = orig

    def test_river_update_failure_logged(self, engine):
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "model error"
        mock_model = MagicMock()
        mock_model.learn_from_feedback = MagicMock(return_value=mock_result)
        engine.river_model = mock_model

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.ONLINE_LEARNING_AVAILABLE
        try:
            ge_mod.ONLINE_LEARNING_AVAILABLE = True
            engine._update_river_model(_make_decision(), 0.5)  # should not raise
        finally:
            ge_mod.ONLINE_LEARNING_AVAILABLE = orig

    def test_river_update_exception_swallowed(self, engine):
        mock_model = MagicMock()
        mock_model.learn_from_feedback = MagicMock(side_effect=RuntimeError("fail"))
        engine.river_model = mock_model

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.ONLINE_LEARNING_AVAILABLE
        try:
            ge_mod.ONLINE_LEARNING_AVAILABLE = True
            engine._update_river_model(_make_decision(), 0.5)  # should not raise
        finally:
            ge_mod.ONLINE_LEARNING_AVAILABLE = orig

    def test_temporal_patterns_numpy_path(self, engine):
        """Covers numpy path for temporal_mean and temporal_std."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.total_samples = 5
        mock_model = MagicMock()
        mock_model.learn_from_feedback = MagicMock(return_value=mock_result)
        mock_model.adapter = MagicMock()
        mock_model.adapter.is_ready = False
        engine.river_model = mock_model

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig_ol = ge_mod.ONLINE_LEARNING_AVAILABLE
        orig_np = ge_mod.NUMPY_AVAILABLE
        try:
            ge_mod.ONLINE_LEARNING_AVAILABLE = True
            ge_mod.NUMPY_AVAILABLE = True
            decision = _make_decision()
            engine._update_river_model(decision, 0.5)
        finally:
            ge_mod.ONLINE_LEARNING_AVAILABLE = orig_ol
            ge_mod.NUMPY_AVAILABLE = orig_np


# ---------------------------------------------------------------------------
# 10. get_river_model_stats
# ---------------------------------------------------------------------------


class TestGetRiverModelStats:
    def test_returns_none_when_unavailable(self, engine):
        assert engine.get_river_model_stats() is None

    def test_returns_stats_dict(self, engine):
        mock_stats = MagicMock()
        mock_stats.__dict__ = {"samples": 10, "accuracy": 0.9}
        mock_model = MagicMock()
        mock_model.get_stats = MagicMock(return_value=mock_stats)
        engine.river_model = mock_model

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.ONLINE_LEARNING_AVAILABLE
        try:
            ge_mod.ONLINE_LEARNING_AVAILABLE = True
            result = engine.get_river_model_stats()
            assert result == {"samples": 10, "accuracy": 0.9}
        finally:
            ge_mod.ONLINE_LEARNING_AVAILABLE = orig

    def test_exception_returns_none(self, engine):
        mock_model = MagicMock()
        mock_model.get_stats = MagicMock(side_effect=RuntimeError("fail"))
        engine.river_model = mock_model

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.ONLINE_LEARNING_AVAILABLE
        try:
            ge_mod.ONLINE_LEARNING_AVAILABLE = True
            result = engine.get_river_model_stats()
            assert result is None
        finally:
            ge_mod.ONLINE_LEARNING_AVAILABLE = orig


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
