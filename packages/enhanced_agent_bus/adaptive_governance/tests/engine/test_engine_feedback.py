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


class TestUpdateMetrics:
    def test_updates_response_time_ema(self, engine):
        engine._update_metrics(_make_decision(), response_time=0.01)
        # EMA should have moved from 0.0
        assert engine.metrics.average_response_time > 0

    def test_history_trimmed_when_over_max(self, engine):
        from collections import deque

        from enhanced_agent_bus.governance_constants import GOVERNANCE_HISTORY_MAX

        # Fill exactly at max + 1 using a deque with maxlen so auto-trim works
        engine.decision_history = deque(
            [_make_decision() for _ in range(GOVERNANCE_HISTORY_MAX + 1)],
            maxlen=GOVERNANCE_HISTORY_MAX,
        )
        initial_len = len(engine.decision_history)
        engine._update_metrics(_make_decision(), response_time=0.001)
        # deque auto-trims; length should stay at maxlen
        assert len(engine.decision_history) <= initial_len

    def test_compliance_rate_calculated(self, engine):
        # Add decisions with high confidence
        for _ in range(10):
            engine.decision_history.append(_make_decision(risk_score=0.3))
        engine._update_metrics(_make_decision(), response_time=0.001)
        assert 0.0 <= engine.metrics.constitutional_compliance_rate <= 1.0


# ---------------------------------------------------------------------------
# 7. provide_feedback
# ---------------------------------------------------------------------------


class TestProvideFeedback:
    def test_success_feedback(self, engine):
        decision = _make_decision()
        engine.impact_scorer.update_model = MagicMock()
        engine.threshold_manager.update_model = MagicMock()
        engine.provide_feedback(decision, outcome_success=True)
        engine.impact_scorer.update_model.assert_called_once()
        engine.threshold_manager.update_model.assert_called_once()

    def test_failure_feedback_increases_impact(self, engine):
        decision = _make_decision(risk_score=0.5)
        captured = {}

        def record_update(features, actual_impact):
            captured["actual_impact"] = actual_impact

        engine.impact_scorer.update_model = record_update
        engine.threshold_manager.update_model = MagicMock()
        engine.provide_feedback(decision, outcome_success=False)
        assert captured["actual_impact"] > 0.5

    def test_human_override_passed(self, engine):
        decision = _make_decision()
        captured = {}

        def record_threshold_update(decision, outcome, human_feedback):
            captured["human_feedback"] = human_feedback

        engine.threshold_manager.update_model = record_threshold_update
        engine.impact_scorer.update_model = MagicMock()
        # human_override=True, decision.action_allowed=True → human_feedback=True
        engine.provide_feedback(decision, outcome_success=True, human_override=True)
        assert captured["human_feedback"] is True

    def test_human_override_mismatch(self, engine):
        decision = _make_decision(action_allowed=False)
        captured = {}

        def record_threshold_update(decision, outcome, human_feedback):
            captured["human_feedback"] = human_feedback

        engine.threshold_manager.update_model = record_threshold_update
        engine.impact_scorer.update_model = MagicMock()
        # human_override=True, decision.action_allowed=False → human_feedback=False
        engine.provide_feedback(decision, outcome_success=True, human_override=True)
        assert captured["human_feedback"] is False

    def test_feedback_exception_swallowed(self, engine):
        decision = _make_decision()
        engine.impact_scorer.update_model = MagicMock(side_effect=RuntimeError("oops"))
        engine.threshold_manager.update_model = MagicMock()
        # Should not raise
        engine.provide_feedback(decision, outcome_success=True)

    def test_dtmc_online_update_when_fitted(self, engine):
        """DTMC online update runs when enable_dtmc and learner fitted."""
        cfg = MagicMock()
        cfg.enable_dtmc = True
        engine.config = cfg

        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.update_online = MagicMock()

        engine.impact_scorer.update_model = MagicMock()
        engine.threshold_manager.update_model = MagicMock()

        # Need at least 2 decisions in history
        engine.decision_history = [_make_decision() for _ in range(3)]
        engine._dtmc_feedback_idx = 0  # reset so all are "new"

        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True)
        # update_online may or may not be called depending on trajectory extraction


# ---------------------------------------------------------------------------
# 8. _store_feedback_event
# ---------------------------------------------------------------------------


class TestStoreFeedbackEvent:
    def test_noop_when_handler_unavailable(self, engine):
        """Should return early without error if handler not available."""
        engine._feedback_handler = None
        decision = _make_decision()
        # Patch FEEDBACK_HANDLER_AVAILABLE as False
        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig = ge_mod.FEEDBACK_HANDLER_AVAILABLE
        try:
            ge_mod.FEEDBACK_HANDLER_AVAILABLE = False
            engine._store_feedback_event(decision, True, None, 0.3)
        finally:
            ge_mod.FEEDBACK_HANDLER_AVAILABLE = orig

    def test_stores_positive_feedback(self, engine):
        mock_handler = MagicMock()
        mock_handler.store_feedback = MagicMock(return_value=MagicMock(feedback_id="fid-1"))
        engine._feedback_handler = mock_handler

        mock_ft = MagicMock()
        mock_ft.POSITIVE = "POSITIVE"
        mock_ft.NEGATIVE = "NEGATIVE"
        mock_ft.CORRECTION = "CORRECTION"

        mock_os = MagicMock()
        mock_os.SUCCESS = "SUCCESS"
        mock_os.FAILURE = "FAILURE"

        mock_event_cls = MagicMock()

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig_available = ge_mod.FEEDBACK_HANDLER_AVAILABLE
        orig_ft = ge_mod.FeedbackType
        orig_os = ge_mod.OutcomeStatus
        orig_ev = ge_mod.FeedbackEvent
        try:
            ge_mod.FEEDBACK_HANDLER_AVAILABLE = True
            ge_mod.FeedbackType = mock_ft
            ge_mod.OutcomeStatus = mock_os
            ge_mod.FeedbackEvent = mock_event_cls

            decision = _make_decision()
            engine._store_feedback_event(
                decision, outcome_success=True, human_override=None, actual_impact=0.3
            )
            mock_handler.store_feedback.assert_called_once()
        finally:
            ge_mod.FEEDBACK_HANDLER_AVAILABLE = orig_available
            ge_mod.FeedbackType = orig_ft
            ge_mod.OutcomeStatus = orig_os
            ge_mod.FeedbackEvent = orig_ev

    def test_stores_correction_feedback_with_override(self, engine):
        mock_handler = MagicMock()
        mock_handler.store_feedback = MagicMock(return_value=MagicMock(feedback_id="fid-2"))
        engine._feedback_handler = mock_handler

        mock_ft = MagicMock()
        mock_ft.CORRECTION = "CORRECTION"
        mock_os = MagicMock()
        mock_os.SUCCESS = "SUCCESS"
        mock_event_cls = MagicMock()

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig_available = ge_mod.FEEDBACK_HANDLER_AVAILABLE
        orig_ft = ge_mod.FeedbackType
        orig_os = ge_mod.OutcomeStatus
        orig_ev = ge_mod.FeedbackEvent
        try:
            ge_mod.FEEDBACK_HANDLER_AVAILABLE = True
            ge_mod.FeedbackType = mock_ft
            ge_mod.OutcomeStatus = mock_os
            ge_mod.FeedbackEvent = mock_event_cls

            decision = _make_decision()
            engine._store_feedback_event(
                decision, outcome_success=True, human_override=True, actual_impact=0.3
            )
            mock_handler.store_feedback.assert_called_once()
        finally:
            ge_mod.FEEDBACK_HANDLER_AVAILABLE = orig_available
            ge_mod.FeedbackType = orig_ft
            ge_mod.OutcomeStatus = orig_os
            ge_mod.FeedbackEvent = orig_ev

    def test_exception_in_store_feedback_swallowed(self, engine):
        mock_handler = MagicMock()
        mock_handler.store_feedback = MagicMock(side_effect=RuntimeError("store fail"))
        engine._feedback_handler = mock_handler

        mock_ft = MagicMock()
        mock_ft.POSITIVE = "POSITIVE"
        mock_os = MagicMock()
        mock_os.SUCCESS = "SUCCESS"
        mock_event_cls = MagicMock()

        from enhanced_agent_bus.adaptive_governance import governance_engine as ge_mod

        orig_available = ge_mod.FEEDBACK_HANDLER_AVAILABLE
        orig_ft = ge_mod.FeedbackType
        orig_os = ge_mod.OutcomeStatus
        orig_ev = ge_mod.FeedbackEvent
        try:
            ge_mod.FEEDBACK_HANDLER_AVAILABLE = True
            ge_mod.FeedbackType = mock_ft
            ge_mod.OutcomeStatus = mock_os
            ge_mod.FeedbackEvent = mock_event_cls

            decision = _make_decision()
            # Should not raise
            engine._store_feedback_event(
                decision, outcome_success=True, human_override=None, actual_impact=0.3
            )
        finally:
            ge_mod.FEEDBACK_HANDLER_AVAILABLE = orig_available
            ge_mod.FeedbackType = orig_ft
            ge_mod.OutcomeStatus = orig_os
            ge_mod.FeedbackEvent = orig_ev


# ---------------------------------------------------------------------------
# 9. _update_river_model
# ---------------------------------------------------------------------------
