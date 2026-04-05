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


class TestInstantiation:
    def test_basic_creation(self, engine):

        assert engine.constitutional_hash == CONST_HASH
        assert engine.mode == GovernanceMode.ADAPTIVE
        assert len(engine.decision_history) == 0
        assert engine.running is False
        assert engine.learning_task is None

    def test_learning_thread_property(self, engine):
        """_learning_thread property mirrors learning_task."""
        assert engine._learning_thread is engine.learning_task

    def test_feedback_handler_not_available(self, engine):
        assert engine._feedback_handler is None

    def test_drift_detector_not_available(self, engine):
        assert engine._drift_detector is None

    def test_river_model_not_available(self, engine):
        assert engine.river_model is None

    def test_ab_router_not_available(self, engine):
        assert engine._ab_test_router is None
        assert engine._shadow_executor is None

    def test_dtmc_learner_created(self, engine):
        assert engine._dtmc_learner is not None
        assert engine._trace_collector is not None

    def test_with_config(self):
        """Engine accepts a config object that has enable_dtmc."""
        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                False,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            cfg = MagicMock()
            cfg.enable_dtmc = True
            cfg.dtmc_intervention_threshold = 0.75
            cfg.dtmc_impact_weight = 0.2
            eng = AdaptiveGovernanceEngine(CONST_HASH, config=cfg)
            assert eng.config is cfg

    def test_feedback_handler_available_path(self):
        """Branch: FEEDBACK_HANDLER_AVAILABLE=True but get_feedback_handler raises."""
        mock_fh = MagicMock()
        mock_fh.initialize_schema.side_effect = RuntimeError("db unavailable")

        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_feedback_handler",
                return_value=mock_fh,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                False,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            eng = AdaptiveGovernanceEngine(CONST_HASH)
            # initialize_schema raises, handler should be None
            assert eng._feedback_handler is None

    def test_feedback_handler_available_success(self):
        """Branch: FEEDBACK_HANDLER_AVAILABLE=True and handler initialises OK."""
        mock_fh = MagicMock()
        mock_fh.initialize_schema.return_value = None

        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_feedback_handler",
                return_value=mock_fh,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                False,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            eng = AdaptiveGovernanceEngine(CONST_HASH)
            assert eng._feedback_handler is mock_fh

    def test_drift_monitoring_available_path(self):
        """Branch: DRIFT_MONITORING_AVAILABLE=True — load_reference_data returns True."""
        mock_detector = MagicMock()
        mock_detector.load_reference_data.return_value = True

        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_drift_detector",
                return_value=mock_detector,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                False,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            eng = AdaptiveGovernanceEngine(CONST_HASH)
            assert eng._drift_detector is mock_detector

    def test_drift_monitoring_no_reference_data(self):
        """Branch: drift detector available but load_reference_data returns False."""
        mock_detector = MagicMock()
        mock_detector.load_reference_data.return_value = False

        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_drift_detector",
                return_value=mock_detector,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                False,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            eng = AdaptiveGovernanceEngine(CONST_HASH)
            assert eng._drift_detector is mock_detector

    def test_online_learning_available_river_not_available(self):
        """Branch: online learning module available but river library not."""
        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.RIVER_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                False,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            eng = AdaptiveGovernanceEngine(CONST_HASH)
            assert eng.river_model is None

    def test_online_learning_available_river_available(self):
        """Branch: both ONLINE_LEARNING and RIVER available — pipeline created."""
        mock_pipeline = MagicMock()
        mock_pipeline.set_fallback_model = MagicMock()

        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.RIVER_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "get_online_learning_pipeline",
                return_value=mock_pipeline,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.ModelType",
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                False,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            eng = AdaptiveGovernanceEngine(CONST_HASH)
            assert eng.river_model is mock_pipeline

    def test_ab_testing_available_and_init_fails(self):
        """Branch: AB_TESTING_AVAILABLE=True but get_ab_test_router raises."""
        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.get_ab_test_router",
                side_effect=RuntimeError("ab init fail"),
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                False,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            eng = AdaptiveGovernanceEngine(CONST_HASH)
            assert eng._ab_test_router is None

    def test_anomaly_monitor_available_and_init_fails(self):
        """Branch: ANOMALY_MONITORING_AVAILABLE=True but AnomalyMonitor() raises."""
        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AnomalyMonitor",
                side_effect=RuntimeError("monitor fail"),
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            eng = AdaptiveGovernanceEngine(CONST_HASH)
            assert eng._anomaly_monitor is None

    def test_anomaly_monitor_available_success(self):
        """Branch: AnomalyMonitor initialises successfully."""
        mock_monitor = MagicMock()

        with (
            patch(_IMPACT_MLFLOW),
            patch(_THRESH_MLFLOW),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "FEEDBACK_HANDLER_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "DRIFT_MONITORING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ONLINE_LEARNING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE",
                False,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine."
                "ANOMALY_MONITORING_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.adaptive_governance.governance_engine.AnomalyMonitor",
                return_value=mock_monitor,
            ),
        ):
            from enhanced_agent_bus.adaptive_governance.governance_engine import (
                AdaptiveGovernanceEngine,
            )

            eng = AdaptiveGovernanceEngine(CONST_HASH)
            assert eng._anomaly_monitor is mock_monitor


# ---------------------------------------------------------------------------
# 2. initialize / shutdown
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_initialize_starts_learning_task(self, engine):
        mock_anomaly = MagicMock()
        mock_anomaly.start = AsyncMock()
        engine._anomaly_monitor = mock_anomaly

        await engine.initialize()
        assert engine.running is True
        assert engine.learning_task is not None
        # Clean up
        engine.running = False
        engine.learning_task.cancel()
        try:  # noqa: SIM105
            await engine.learning_task
        except asyncio.CancelledError:
            pass

    async def test_shutdown_cancels_task(self, engine):
        await engine.initialize()
        assert engine.learning_task is not None
        await engine.shutdown()
        assert engine.running is False

    async def test_shutdown_with_no_task(self, engine):
        engine.running = False
        engine.learning_task = None
        await engine.shutdown()  # should not raise

    async def test_shutdown_with_anomaly_monitor(self, engine):
        mock_monitor = MagicMock()
        mock_monitor.start = AsyncMock()
        mock_monitor.stop = AsyncMock()
        engine._anomaly_monitor = mock_monitor
        await engine.initialize()
        await engine.shutdown()
        mock_monitor.stop.assert_awaited_once()

    async def test_shutdown_task_already_done(self, engine):
        """If learning task is done before shutdown, no cancel needed."""
        engine.running = True

        async def fast_task():
            pass

        engine.learning_task = asyncio.create_task(fast_task())
        await asyncio.sleep(0)  # let it finish
        await engine.shutdown()
        assert engine.running is False


# ---------------------------------------------------------------------------
# 3. _classify_impact_level
# ---------------------------------------------------------------------------
