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
# 9. _update_river_model
# ---------------------------------------------------------------------------


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
