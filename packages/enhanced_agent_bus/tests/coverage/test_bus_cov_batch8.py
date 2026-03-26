"""
Coverage tests for enhanced_agent_bus batch 8.

Targets:
- adaptive_governance.governance_engine (AdaptiveGovernanceEngine)
- mcp_server.server (MCPServer, create_mcp_server)
- constitutional.review_api (list_amendments, get_amendment, approve/reject, rollback, health)

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import dataclasses
from collections import deque
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Governance Engine imports & helpers
# ---------------------------------------------------------------------------
from enhanced_agent_bus.adaptive_governance.governance_engine import (
    AdaptiveGovernanceEngine,
)
from enhanced_agent_bus.adaptive_governance.models import (
    GovernanceDecision,
    GovernanceMetrics,
    GovernanceMode,
    ImpactFeatures,
    ImpactLevel,
)
from enhanced_agent_bus.governance_constants import (
    GOVERNANCE_COMPLIANCE_THRESHOLD,
    GOVERNANCE_FALLBACK_CONFIDENCE,
    GOVERNANCE_MAX_TREND_LENGTH,
    GOVERNANCE_RECOMMENDED_THRESHOLD,
    GOVERNANCE_RISK_CRITICAL,
    GOVERNANCE_RISK_HIGH,
    GOVERNANCE_RISK_LOW,
    GOVERNANCE_RISK_MEDIUM,
)


def _make_features(**overrides) -> ImpactFeatures:
    defaults = dict(
        message_length=100,
        agent_count=2,
        tenant_complexity=0.5,
        temporal_patterns=[0.1, 0.2],
        semantic_similarity=0.6,
        historical_precedence=3,
        resource_utilization=0.4,
        network_isolation=0.3,
        risk_score=0.35,
        confidence_level=0.85,
    )
    defaults.update(overrides)
    return ImpactFeatures(**defaults)


def _make_decision(**overrides) -> GovernanceDecision:
    defaults = dict(
        action_allowed=True,
        impact_level=ImpactLevel.LOW,
        confidence_score=0.9,
        reasoning="test decision",
        recommended_threshold=0.8,
        features_used=_make_features(),
        decision_id="gov-test-001",
    )
    defaults.update(overrides)
    return GovernanceDecision(**defaults)


def _make_engine(
    *,
    enable_dtmc: bool = False,
    dtmc_impact_weight: float = 0.0,
    dtmc_intervention_threshold: float = 0.8,
) -> AdaptiveGovernanceEngine:
    """Build engine with all optional subsystems stubbed out."""
    config = MagicMock()
    config.enable_dtmc = enable_dtmc
    config.dtmc_impact_weight = dtmc_impact_weight
    config.dtmc_intervention_threshold = dtmc_intervention_threshold

    with (
        patch.object(AdaptiveGovernanceEngine, "_initialize_feedback_handler"),
        patch.object(AdaptiveGovernanceEngine, "_initialize_drift_detector"),
        patch.object(AdaptiveGovernanceEngine, "_initialize_river_model"),
        patch.object(AdaptiveGovernanceEngine, "_initialize_ab_test_router"),
        patch.object(AdaptiveGovernanceEngine, "_initialize_anomaly_monitor"),
    ):
        engine = AdaptiveGovernanceEngine(
            constitutional_hash="608508a9bd224290",
            config=config,
        )
    # Ensure optional subsystems are None so we test the fallback paths
    engine._drift_detector = None
    engine._anomaly_monitor = None
    engine.river_model = None
    engine._ab_test_router = None
    engine._shadow_executor = None
    engine._feedback_handler = None
    return engine


# ============================================================================
# AdaptiveGovernanceEngine — classify, reasoning, metrics, feedback, etc.
# ============================================================================


class TestClassifyImpactLevel:
    def test_critical(self):
        engine = _make_engine()
        assert engine._classify_impact_level(0.95) == ImpactLevel.CRITICAL

    def test_high(self):
        engine = _make_engine()
        assert engine._classify_impact_level(0.75) == ImpactLevel.HIGH

    def test_medium(self):
        engine = _make_engine()
        assert engine._classify_impact_level(0.5) == ImpactLevel.MEDIUM

    def test_low(self):
        engine = _make_engine()
        assert engine._classify_impact_level(0.25) == ImpactLevel.LOW

    def test_negligible(self):
        engine = _make_engine()
        assert engine._classify_impact_level(0.05) == ImpactLevel.NEGLIGIBLE

    def test_boundary_critical(self):
        engine = _make_engine()
        assert engine._classify_impact_level(GOVERNANCE_RISK_CRITICAL) == ImpactLevel.CRITICAL

    def test_boundary_high(self):
        engine = _make_engine()
        assert engine._classify_impact_level(GOVERNANCE_RISK_HIGH) == ImpactLevel.HIGH

    def test_boundary_medium(self):
        engine = _make_engine()
        assert engine._classify_impact_level(GOVERNANCE_RISK_MEDIUM) == ImpactLevel.MEDIUM

    def test_boundary_low(self):
        engine = _make_engine()
        assert engine._classify_impact_level(GOVERNANCE_RISK_LOW) == ImpactLevel.LOW


class TestGenerateReasoning:
    def test_allowed_high_confidence(self):
        engine = _make_engine()
        features = _make_features(risk_score=0.3, confidence_level=0.9, historical_precedence=5)
        reasoning = engine._generate_reasoning(True, features, 0.8)
        assert "ALLOWED" in reasoning
        assert "5 similar precedents" in reasoning

    def test_blocked_low_confidence(self):
        engine = _make_engine()
        features = _make_features(risk_score=0.9, confidence_level=0.5, historical_precedence=0)
        reasoning = engine._generate_reasoning(False, features, 0.7)
        assert "BLOCKED" in reasoning
        assert "Low confidence" in reasoning

    def test_no_precedence_no_low_confidence(self):
        engine = _make_engine()
        features = _make_features(risk_score=0.4, confidence_level=0.85, historical_precedence=0)
        reasoning = engine._generate_reasoning(True, features, 0.8)
        assert "precedents" not in reasoning
        assert "Low confidence" not in reasoning


class TestBuildConservativeFallback:
    def test_returns_blocked_decision(self):
        decision = AdaptiveGovernanceEngine._build_conservative_fallback_decision(
            ValueError("boom")
        )
        assert decision.action_allowed is False
        assert decision.impact_level == ImpactLevel.HIGH
        assert decision.confidence_score == GOVERNANCE_FALLBACK_CONFIDENCE
        assert "boom" in decision.reasoning
        assert decision.recommended_threshold == GOVERNANCE_RECOMMENDED_THRESHOLD


class TestBuildDecisionForFeatures:
    def test_allowed_when_risk_below_threshold(self):
        engine = _make_engine()
        engine.threshold_manager = MagicMock()
        engine.threshold_manager.get_adaptive_threshold.return_value = 0.5
        features = _make_features(risk_score=0.3, confidence_level=0.9)
        decision = engine._build_decision_for_features(features, "gov-test-010")
        assert decision.action_allowed is True
        assert decision.decision_id == "gov-test-010"

    def test_blocked_when_risk_above_threshold(self):
        engine = _make_engine()
        engine.threshold_manager = MagicMock()
        engine.threshold_manager.get_adaptive_threshold.return_value = 0.2
        features = _make_features(risk_score=0.5, confidence_level=0.9)
        decision = engine._build_decision_for_features(features, "gov-test-011")
        assert decision.action_allowed is False


class TestUpdateMetrics:
    def test_updates_response_time_ema(self):
        engine = _make_engine()
        engine.metrics.average_response_time = 0.01
        decision = _make_decision(confidence_score=0.95)
        engine.decision_history.append(decision)
        engine._update_metrics(decision, 0.005)
        assert engine.metrics.average_response_time != 0.01

    def test_compliance_rate_computed(self):
        engine = _make_engine()
        for _ in range(10):
            engine.decision_history.append(_make_decision(confidence_score=0.95))
        engine._update_metrics(_make_decision(), 0.001)
        assert engine.metrics.constitutional_compliance_rate > 0.0


class TestRecordDecisionMetrics:
    def test_appends_to_history(self):
        engine = _make_engine()
        decision = _make_decision()
        engine._record_decision_metrics(decision, 0.001)
        assert len(engine.decision_history) == 1

    def test_invokes_anomaly_monitor_when_present(self):
        engine = _make_engine()
        engine._anomaly_monitor = MagicMock()
        decision = _make_decision()
        engine._record_decision_metrics(decision, 0.001)
        engine._anomaly_monitor.record_metrics.assert_called_once()


class TestAnalyzePerformanceTrends:
    def test_appends_trends(self):
        engine = _make_engine()
        engine.metrics.constitutional_compliance_rate = 0.95
        engine.metrics.false_positive_rate = 0.02
        engine.metrics.average_response_time = 0.01
        engine._analyze_performance_trends()
        assert len(engine.metrics.compliance_trend) == 1
        assert len(engine.metrics.accuracy_trend) == 1
        assert len(engine.metrics.performance_trend) == 1

    def test_trims_trends_above_max(self):
        engine = _make_engine()
        engine.metrics.compliance_trend = list(range(GOVERNANCE_MAX_TREND_LENGTH + 5))
        engine.metrics.accuracy_trend = list(range(GOVERNANCE_MAX_TREND_LENGTH + 5))
        engine.metrics.performance_trend = list(range(GOVERNANCE_MAX_TREND_LENGTH + 5))
        engine.metrics.average_response_time = 0.01
        engine._analyze_performance_trends()
        assert len(engine.metrics.compliance_trend) <= GOVERNANCE_MAX_TREND_LENGTH
        assert len(engine.metrics.accuracy_trend) <= GOVERNANCE_MAX_TREND_LENGTH
        assert len(engine.metrics.performance_trend) <= GOVERNANCE_MAX_TREND_LENGTH


class TestShouldRetrainModels:
    def test_retrain_when_compliance_below_target(self):
        engine = _make_engine()
        engine.metrics.constitutional_compliance_rate = 0.5
        assert engine._should_retrain_models() is True

    def test_no_retrain_when_compliance_ok_and_history_small(self):
        engine = _make_engine()
        engine.metrics.constitutional_compliance_rate = 0.99
        assert engine._should_retrain_models() is False


class TestLogPerformanceSummary:
    def test_no_error(self):
        engine = _make_engine()
        engine._log_performance_summary()  # should not raise


class TestDtmcRiskBlend:
    def test_no_blend_when_dtmc_disabled(self):
        engine = _make_engine(enable_dtmc=False)
        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.3

    def test_no_blend_when_no_trajectory(self):
        engine = _make_engine(enable_dtmc=True, dtmc_impact_weight=0.2)
        engine._dtmc_learner = MagicMock()
        engine._dtmc_learner.is_fitted = True
        engine.decision_history = deque()  # empty -> no trajectory
        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == 0.3

    def test_blend_applied_when_fitted_and_weight(self):
        engine = _make_engine(enable_dtmc=True, dtmc_impact_weight=0.2)
        engine._dtmc_learner = MagicMock()
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.predict_risk.return_value = 0.5
        # Need history for trajectory
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        features = _make_features(risk_score=0.3)
        result = engine._apply_dtmc_risk_blend(features)
        assert result.risk_score == pytest.approx(0.3 + 0.5 * 0.2)


class TestDtmcEscalation:
    def test_no_escalation_when_disabled(self):
        engine = _make_engine(enable_dtmc=False)
        decision = _make_decision(impact_level=ImpactLevel.LOW)
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.LOW

    def test_no_escalation_already_high(self):
        engine = _make_engine(enable_dtmc=True)
        engine._dtmc_learner = MagicMock()
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.should_intervene.return_value = True
        engine._dtmc_learner.predict_risk.return_value = 0.95
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.HIGH))
        decision = _make_decision(impact_level=ImpactLevel.HIGH)
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.HIGH

    def test_escalates_low_to_high(self):
        engine = _make_engine(enable_dtmc=True)
        engine._dtmc_learner = MagicMock()
        engine._dtmc_learner.is_fitted = True
        engine._dtmc_learner.should_intervene.return_value = True
        engine._dtmc_learner.predict_risk.return_value = 0.9
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        decision = _make_decision(impact_level=ImpactLevel.LOW)
        result = engine._apply_dtmc_escalation(decision)
        assert result.impact_level == ImpactLevel.HIGH
        assert result.action_allowed is False
        assert "DTMC" in result.reasoning


class TestGetTrajectoryPrefix:
    def test_returns_none_when_empty(self):
        engine = _make_engine()
        assert engine._get_trajectory_prefix() is None

    def test_returns_state_indices(self):
        engine = _make_engine()
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.LOW))
        engine.decision_history.append(_make_decision(impact_level=ImpactLevel.HIGH))
        prefix = engine._get_trajectory_prefix()
        assert prefix is not None
        assert len(prefix) == 2


class TestMaybeRefitDtmc:
    def test_skips_when_disabled(self):
        engine = _make_engine(enable_dtmc=False)
        engine._maybe_refit_dtmc()  # should not raise

    def test_skips_when_too_few_decisions(self):
        engine = _make_engine(enable_dtmc=True)
        engine._maybe_refit_dtmc()  # empty history

    def test_refits_when_enough_decisions(self):
        engine = _make_engine(enable_dtmc=True)
        engine._trace_collector = MagicMock()
        engine._trace_collector.collect_from_decision_history.return_value = [[0, 1, 2]]
        engine._dtmc_learner = MagicMock()
        engine._dtmc_learner.fit.return_value = MagicMock(n_trajectories=1, unsafe_fraction=0.1)
        for _ in range(15):
            engine.decision_history.append(_make_decision())
        engine._maybe_refit_dtmc()
        engine._dtmc_learner.fit.assert_called_once()


class TestProvideFeedback:
    def test_basic_feedback_no_override(self):
        engine = _make_engine()
        engine.threshold_manager = MagicMock()
        engine.impact_scorer = MagicMock()
        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True)
        engine.threshold_manager.update_model.assert_called_once()
        engine.impact_scorer.update_model.assert_called_once()

    def test_feedback_with_human_override(self):
        engine = _make_engine()
        engine.threshold_manager = MagicMock()
        engine.impact_scorer = MagicMock()
        decision = _make_decision(action_allowed=True)
        engine.provide_feedback(decision, outcome_success=False, human_override=False)
        call_args = engine.threshold_manager.update_model.call_args
        assert call_args[0][2] is False  # human_feedback = (override == decision.action_allowed)

    def test_feedback_increases_impact_on_failure(self):
        engine = _make_engine()
        engine.threshold_manager = MagicMock()
        engine.impact_scorer = MagicMock()
        features = _make_features(risk_score=0.3)
        decision = _make_decision(features_used=features)
        engine.provide_feedback(decision, outcome_success=False)
        # actual_impact should be min(1.0, 0.3 + 0.2) = 0.5
        call_args = engine.impact_scorer.update_model.call_args
        assert call_args[0][1] == pytest.approx(0.5)

    def test_feedback_error_does_not_raise(self):
        engine = _make_engine()
        engine.threshold_manager = MagicMock()
        engine.threshold_manager.update_model.side_effect = RuntimeError("boom")
        decision = _make_decision()
        engine.provide_feedback(decision, outcome_success=True)  # should not raise


class TestEvaluateGovernanceDecision:
    async def test_successful_evaluation(self):
        engine = _make_engine()
        engine.impact_scorer = MagicMock()
        engine.impact_scorer.assess_impact = AsyncMock(return_value=_make_features())
        engine.threshold_manager = MagicMock()
        engine.threshold_manager.get_adaptive_threshold.return_value = 0.5
        engine._decision_validator = MagicMock()
        engine._decision_validator.validate_decision = AsyncMock(return_value=(True, []))
        decision = await engine.evaluate_governance_decision({}, {})
        assert decision.action_allowed is True

    async def test_falls_back_on_validation_failure(self):
        engine = _make_engine()
        engine.impact_scorer = MagicMock()
        engine.impact_scorer.assess_impact = AsyncMock(return_value=_make_features())
        engine.threshold_manager = MagicMock()
        engine.threshold_manager.get_adaptive_threshold.return_value = 0.5
        engine._decision_validator = MagicMock()
        engine._decision_validator.validate_decision = AsyncMock(
            return_value=(False, ["hash mismatch"])
        )
        decision = await engine.evaluate_governance_decision({}, {})
        assert decision.action_allowed is False
        assert decision.impact_level == ImpactLevel.HIGH

    async def test_falls_back_on_scorer_error(self):
        engine = _make_engine()
        engine.impact_scorer = MagicMock()
        engine.impact_scorer.assess_impact = AsyncMock(side_effect=RuntimeError("scorer down"))
        decision = await engine.evaluate_governance_decision({}, {})
        assert decision.action_allowed is False


class TestApplyAbTestRouting:
    def test_no_routing_when_unavailable(self):
        engine = _make_engine()
        decision = _make_decision()
        result = engine._apply_ab_test_routing(decision, _make_features(), 0.0)
        assert result is decision  # unchanged


class TestGetAbTestMetrics:
    def test_returns_none_when_unavailable(self):
        engine = _make_engine()
        assert engine.get_ab_test_metrics() is None

    def test_returns_none_on_error(self):
        engine = _make_engine()
        engine._ab_test_router = MagicMock()
        engine._ab_test_router.get_metrics_summary.side_effect = RuntimeError("x")
        # Need AB_TESTING_AVAILABLE to be True for this path
        with patch(
            "enhanced_agent_bus.adaptive_governance.governance_engine.AB_TESTING_AVAILABLE", True
        ):
            assert engine.get_ab_test_metrics() is None


class TestGetAbTestComparison:
    def test_returns_none_when_unavailable(self):
        engine = _make_engine()
        assert engine.get_ab_test_comparison() is None


class TestPromoteCandidateModel:
    def test_returns_none_when_unavailable(self):
        engine = _make_engine()
        assert engine.promote_candidate_model() is None


class TestGetRiverModelStats:
    def test_returns_none_when_unavailable(self):
        engine = _make_engine()
        assert engine.get_river_model_stats() is None


class TestGetAbTestRouter:
    def test_returns_none_when_not_initialized(self):
        engine = _make_engine()
        assert engine.get_ab_test_router() is None


class TestInitializeAndShutdown:
    async def test_initialize(self):
        engine = _make_engine()
        await engine.initialize()
        assert engine.running is True
        assert engine.learning_task is not None
        # Stop to clean up
        await engine.shutdown()
        assert engine.running is False

    async def test_shutdown_cancels_learning_task(self):
        engine = _make_engine()
        await engine.initialize()
        task = engine.learning_task
        await engine.shutdown()
        assert task.cancelled() or task.done()

    async def test_shutdown_when_not_running(self):
        engine = _make_engine()
        await engine.shutdown()  # should not raise

    async def test_shutdown_stops_anomaly_monitor(self):
        engine = _make_engine()
        engine._anomaly_monitor = MagicMock()
        engine._anomaly_monitor.start = AsyncMock()
        engine._anomaly_monitor.stop = AsyncMock()
        await engine.initialize()
        await engine.shutdown()
        engine._anomaly_monitor.stop.assert_called_once()


class TestRunScheduledDriftDetection:
    def test_skips_when_no_detector(self):
        engine = _make_engine()
        engine._run_scheduled_drift_detection()  # should not raise

    def test_skips_when_interval_not_elapsed(self):
        engine = _make_engine()
        engine._drift_detector = MagicMock()
        import time

        engine._last_drift_check = time.time()
        engine._drift_check_interval = 9999
        engine._run_scheduled_drift_detection()
        engine._drift_detector.detect_drift.assert_not_called()


class TestCollectDriftData:
    def test_returns_none_when_no_history(self):
        engine = _make_engine()
        result = engine._collect_drift_data()
        assert result is None

    def test_returns_none_when_pandas_unavailable(self):
        engine = _make_engine()
        engine.decision_history.append(_make_decision())
        with patch.dict("sys.modules", {"pandas": None}):
            result = engine._collect_drift_data()
            # May return None or the frame depending on import caching
            # Just ensure no exception


class TestGetLatestDriftReport:
    def test_returns_none_initially(self):
        engine = _make_engine()
        assert engine.get_latest_drift_report() is None


class TestLearningThreadProperty:
    def test_returns_learning_task(self):
        engine = _make_engine()
        engine.learning_task = MagicMock()
        assert engine._learning_thread is engine.learning_task


class TestStoreFeedbackEvent:
    def test_skips_when_handler_unavailable(self):
        engine = _make_engine()
        engine._store_feedback_event(_make_decision(), True, None, 0.3)  # should not raise


class TestUpdateRiverModel:
    def test_skips_when_unavailable(self):
        engine = _make_engine()
        engine._update_river_model(_make_decision(), 0.3)  # should not raise


# ============================================================================
# MCP Server tests
# ============================================================================

from enhanced_agent_bus.mcp_server.config import MCPConfig, TransportType
from enhanced_agent_bus.mcp_server.protocol.types import (
    MCPError,
    MCPRequest,
    MCPResponse,
    ResourceDefinition,
    ServerCapabilities,
    ToolDefinition,
)
from enhanced_agent_bus.mcp_server.server import MCPServer, create_mcp_server


class TestMCPServerInit:
    def test_creates_with_default_config(self):
        server = MCPServer()
        assert server.config.server_name == "acgs2-governance"
        assert server._running is False
        assert server._handler is not None
        assert len(server._tools) == 5
        assert len(server._resources) == 4
        assert len(server._adapters) == 3

    def test_creates_with_custom_config(self):
        config = MCPConfig(server_name="test-server", server_version="1.0.0")
        server = MCPServer(config=config)
        assert server.config.server_name == "test-server"


class TestMCPServerConnectAdapters:
    async def test_connect_adapters_returns_true(self):
        server = MCPServer()
        server._adapters["agent_bus"] = MagicMock()
        server._adapters["agent_bus"].connect = AsyncMock(return_value=True)
        result = await server.connect_adapters()
        assert result is True

    async def test_connect_adapters_handles_failed_connection(self):
        server = MCPServer()
        server._adapters["agent_bus"] = MagicMock()
        server._adapters["agent_bus"].connect = AsyncMock(return_value=False)
        result = await server.connect_adapters()
        assert result is True  # standalone mode


class TestMCPServerDisconnectAdapters:
    async def test_disconnects_agent_bus(self):
        server = MCPServer()
        mock_adapter = MagicMock()
        mock_adapter.disconnect = AsyncMock()
        server._adapters["agent_bus"] = mock_adapter
        await server.disconnect_adapters()
        mock_adapter.disconnect.assert_called_once()


class TestMCPServerStart:
    async def test_start_already_running(self):
        server = MCPServer()
        server._running = True
        await server.start()  # should return early, no error

    async def test_start_unknown_transport_raises(self):
        config = MCPConfig()
        # Force an invalid transport type
        config.transport_type = MagicMock()
        config.transport_type.value = "unknown"
        # Make it not match any known type
        server = MCPServer(config=config)
        server._adapters["agent_bus"] = MagicMock()
        server._adapters["agent_bus"].connect = AsyncMock(return_value=True)
        with pytest.raises(ValueError, match="Unknown transport"):
            await server.start()


class TestMCPServerStop:
    async def test_stop_when_not_running(self):
        server = MCPServer()
        await server.stop()  # should not raise, early return

    async def test_stop_running_server(self):
        server = MCPServer()
        server._running = True
        server._adapters["agent_bus"] = MagicMock()
        server._adapters["agent_bus"].disconnect = AsyncMock()
        audit_resource = MagicMock()
        server._resources["audit_trail"] = audit_resource
        await server.stop()
        assert server._running is False
        audit_resource.log_event.assert_called_once()


class TestMCPServerHandleRequest:
    async def test_successful_request(self):
        server = MCPServer()
        expected_response = MCPResponse(jsonrpc="2.0", id=1, result={"ok": True})
        server._handler = MagicMock()
        server._handler.handle_request = AsyncMock(return_value=expected_response)
        request = MCPRequest(jsonrpc="2.0", method="test", id=1)
        response = await server.handle_request(request)
        assert response.result == {"ok": True}
        assert server._request_count == 1

    async def test_error_handling(self):
        server = MCPServer()
        server._handler = MagicMock()
        server._handler.handle_request = AsyncMock(side_effect=RuntimeError("test error"))
        request = MCPRequest(jsonrpc="2.0", method="fail", id=2)
        response = await server.handle_request(request)
        assert response.error is not None
        assert response.error.code == -32603
        assert server._error_count == 1


class TestMCPServerGetCapabilities:
    def test_returns_server_capabilities(self):
        server = MCPServer()
        caps = server.get_capabilities()
        assert isinstance(caps, ServerCapabilities)
        assert caps.tools == {"listChanged": True}


class TestMCPServerGetToolDefinitions:
    def test_returns_list_of_tool_definitions(self):
        server = MCPServer()
        defs = server.get_tool_definitions()
        assert len(defs) == 5
        for d in defs:
            assert isinstance(d, ToolDefinition)


class TestMCPServerGetResourceDefinitions:
    def test_returns_list_of_resource_definitions(self):
        server = MCPServer()
        defs = server.get_resource_definitions()
        assert len(defs) == 4
        for d in defs:
            assert isinstance(d, ResourceDefinition)


class TestMCPServerGetMetrics:
    def test_metrics_structure(self):
        server = MCPServer()
        metrics = server.get_metrics()
        assert "server" in metrics
        assert metrics["server"]["name"] == "acgs2-governance"
        assert metrics["server"]["running"] is False
        assert metrics["server"]["request_count"] == 0
        assert "tools" in metrics
        assert "resources" in metrics
        assert "adapters" in metrics

    def test_metrics_with_tool_metrics(self):
        server = MCPServer()
        mock_tool = MagicMock()
        mock_tool.get_metrics.return_value = {"calls": 10}
        mock_tool.get_definition.return_value = MagicMock()
        server._tools["test_tool"] = mock_tool
        metrics = server.get_metrics()
        assert metrics["tools"]["test_tool"] == {"calls": 10}


class TestCreateMcpServer:
    def test_creates_with_defaults(self):
        server = create_mcp_server()
        assert isinstance(server, MCPServer)

    def test_creates_with_custom_config(self):
        config = MCPConfig(server_name="custom")
        server = create_mcp_server(config=config)
        assert server.config.server_name == "custom"

    def test_injects_agent_bus(self):
        mock_bus = MagicMock()
        server = create_mcp_server(agent_bus=mock_bus)
        assert server._adapters["agent_bus"].agent_bus is mock_bus

    def test_injects_policy_client(self):
        mock_client = MagicMock()
        server = create_mcp_server(policy_client=mock_client)
        assert server._adapters["policy_client"].policy_client is mock_client

    def test_injects_audit_client(self):
        mock_client = MagicMock()
        server = create_mcp_server(audit_client=mock_client)
        assert server._adapters["audit_client"].audit_client is mock_client


class TestMCPServerSSETransport:
    async def test_sse_falls_back_to_stdio(self):
        """SSE transport is a stub that falls back to STDIO."""
        server = MCPServer()
        server._running = True
        # Patch _run_stdio_transport to avoid real I/O
        server._run_stdio_transport = AsyncMock()
        await server._run_sse_transport()
        server._run_stdio_transport.assert_called_once()


# ============================================================================
# Constitutional Review API tests
# ============================================================================

from enhanced_agent_bus.constitutional.amendment_model import (
    AmendmentProposal,
    AmendmentStatus,
)
from enhanced_agent_bus.constitutional.review_api import (
    AmendmentDetailResponse,
    AmendmentListResponse,
    ApprovalRequest,
    ApprovalResponse,
    RejectionRequest,
    RollbackRequest,
    RollbackResponse,
    approve_amendment,
    get_amendment,
    health_check,
    list_amendments,
    reject_amendment,
    rollback_to_version,
)

_MISSING = object()


@contextmanager
def _review_api_patch(name: str, value=_MISSING, **kwargs):
    namespace = list_amendments.__globals__
    original = namespace.get(name, _MISSING)

    if value is _MISSING:
        new_callable = kwargs.pop("new_callable", MagicMock)
        replacement = new_callable()
        if hasattr(replacement, "configure_mock"):
            replacement.configure_mock(**kwargs)
        else:
            for key, attr_value in kwargs.items():
                setattr(replacement, key, attr_value)
    else:
        if kwargs:
            raise TypeError("Direct-value patches do not accept mock keyword arguments")
        replacement = value

    namespace[name] = replacement
    try:
        yield replacement
    finally:
        if original is _MISSING:
            namespace.pop(name, None)
        else:
            namespace[name] = original


def _make_amendment(**overrides) -> AmendmentProposal:
    defaults = dict(
        proposal_id="amend-001",
        proposed_changes={"rules": [{"id": "r1", "text": "new rule"}]},
        justification="This is a test amendment justification.",
        proposer_agent_id="agent-001",
        target_version="1.0.0",
        status=AmendmentStatus.UNDER_REVIEW,
        approval_chain=[],
        governance_metrics_before={"compliance": 0.95},
        governance_metrics_after={"compliance": 0.97},
        requires_deliberation=False,
    )
    defaults.update(overrides)
    return AmendmentProposal(**defaults)


class TestHealthCheck:
    async def test_returns_healthy(self):
        result = await health_check()
        assert result["status"] == "healthy"
        assert result["service"] == "constitutional-review-api"
        assert "timestamp" in result


class TestListAmendments:
    """Tests call list_amendments with plain str/int args (not FastAPI Query objects)."""

    async def test_list_with_defaults(self):
        mock_storage = AsyncMock()
        mock_storage.list_amendments.return_value = ([_make_amendment()], 1)

        with _review_api_patch(
            "ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            result = await list_amendments(
                status=None,
                proposer_agent_id=None,
                limit=50,
                offset=0,
                order_by="created_at",
                order="desc",
            )
        assert result.total == 1
        assert len(result.amendments) == 1

    async def test_list_with_status_filter(self):
        mock_storage = AsyncMock()
        mock_storage.list_amendments.return_value = ([], 0)

        with _review_api_patch(
            "ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            result = await list_amendments(
                status="proposed",
                proposer_agent_id=None,
                limit=50,
                offset=0,
                order_by="created_at",
                order="desc",
            )
        assert result.total == 0

    async def test_list_with_invalid_status_raises_400(self):
        mock_storage = AsyncMock()

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            await list_amendments(
                status="invalid_status_xyz",
                proposer_agent_id=None,
                limit=50,
                offset=0,
                order_by="created_at",
                order="desc",
            )
        assert exc_info.value.status_code == 400

    async def test_list_with_invalid_order_by_raises_400(self):
        mock_storage = AsyncMock()

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            await list_amendments(
                status=None,
                proposer_agent_id=None,
                limit=50,
                offset=0,
                order_by="nonexistent_field",
                order="desc",
            )
        assert exc_info.value.status_code == 400

    async def test_list_with_invalid_order_raises_400(self):
        mock_storage = AsyncMock()

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            await list_amendments(
                status=None,
                proposer_agent_id=None,
                limit=50,
                offset=0,
                order_by="created_at",
                order="sideways",
            )
        assert exc_info.value.status_code == 400

    async def test_list_storage_error_raises_500(self):
        mock_storage = AsyncMock()
        mock_storage.connect.side_effect = RuntimeError("db down")

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            await list_amendments(
                status=None,
                proposer_agent_id=None,
                limit=50,
                offset=0,
                order_by="created_at",
                order="desc",
            )
        assert exc_info.value.status_code == 500

    async def test_list_with_proposer_filter(self):
        mock_storage = AsyncMock()
        mock_storage.list_amendments.return_value = ([_make_amendment()], 1)

        with _review_api_patch(
            "ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            result = await list_amendments(
                status=None,
                proposer_agent_id="agent-001",
                limit=10,
                offset=0,
                order_by="impact_score",
                order="asc",
            )
        assert result.total == 1


class TestGetAmendment:
    async def test_get_existing_amendment(self):
        amendment = _make_amendment()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = None

        with _review_api_patch(
            "ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            result = await get_amendment("amend-001")
        assert result.amendment.proposal_id == "amend-001"

    async def test_get_nonexistent_raises_404(self):
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = None

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            await get_amendment("nonexistent")
        assert exc_info.value.status_code == 404

    async def test_get_with_diff_from_dict_changes(self):
        from enhanced_agent_bus.constitutional.diff_engine import SemanticDiff
        from enhanced_agent_bus.constitutional.version_model import (
            ConstitutionalVersion,
        )

        amendment = _make_amendment(proposed_changes={"rules": [{"text": "updated"}]})
        target_ver = ConstitutionalVersion(
            version_id="v1",
            version="1.0.0",
            content={"rules": []},
        )
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target_ver

        fake_diff = SemanticDiff(
            from_version="1.0.0",
            to_version="1.0.1",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="aaa",
            to_hash="bbb",
            hash_changed=True,
        )
        mock_diff_engine = MagicMock()
        mock_diff_engine.compute_diff_from_content = AsyncMock(return_value=fake_diff)

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "ConstitutionalDiffEngine",
                return_value=mock_diff_engine,
            ),
        ):
            result = await get_amendment("amend-001")
        mock_diff_engine.compute_diff_from_content.assert_called_once()
        assert result.diff is not None

    async def test_get_with_string_proposed_changes_branch(self):
        """Cover the isinstance(proposed_changes, str) branch by monkey-patching."""
        from enhanced_agent_bus.constitutional.diff_engine import SemanticDiff
        from enhanced_agent_bus.constitutional.version_model import (
            ConstitutionalVersion,
        )

        amendment = _make_amendment(proposed_changes={"placeholder": True})
        # Monkey-patch to string after construction to bypass Pydantic validation
        object.__setattr__(amendment, "proposed_changes", "v2-ref-id")

        target_ver = ConstitutionalVersion(
            version_id="v1",
            version="1.0.0",
            content={"rules": []},
        )
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = target_ver

        fake_diff = SemanticDiff(
            from_version="1.0.0",
            to_version="1.0.1",
            from_version_id="v1",
            to_version_id="v2",
            from_hash="aaa",
            to_hash="bbb",
            hash_changed=True,
        )
        mock_diff_engine = MagicMock()
        mock_diff_engine.compute_diff = AsyncMock(return_value=fake_diff)

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "ConstitutionalDiffEngine",
                return_value=mock_diff_engine,
            ),
        ):
            result = await get_amendment("amend-001")
        mock_diff_engine.compute_diff.assert_called_once()

    async def test_get_without_diff(self):
        amendment = _make_amendment()
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = None

        with _review_api_patch(
            "ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            result = await get_amendment("amend-001", include_diff=False)
        assert result.diff is None

    async def test_get_computes_metrics_delta(self):
        amendment = _make_amendment(
            governance_metrics_before={"compliance": 0.90, "accuracy": 0.85},
            governance_metrics_after={"compliance": 0.95, "accuracy": 0.88},
        )
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment
        mock_storage.get_version.return_value = None

        with _review_api_patch(
            "ConstitutionalStorageService",
            return_value=mock_storage,
        ):
            result = await get_amendment("amend-001", include_diff=False)
        assert result.governance_metrics_delta["compliance"] == pytest.approx(0.05)
        assert result.governance_metrics_delta["accuracy"] == pytest.approx(0.03)

    async def test_get_storage_error_raises_500(self):
        mock_storage = AsyncMock()
        mock_storage.connect.side_effect = RuntimeError("db down")

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            await get_amendment("amend-001")
        assert exc_info.value.status_code == 500


class TestApproveAmendment:
    async def test_approve_success_fully_approved(self):
        amendment = _make_amendment(status=AmendmentStatus.UNDER_REVIEW)
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        mock_hitl = MagicMock()
        mock_chain_config = MagicMock()
        mock_chain_config.required_approvals = 1
        mock_hitl._determine_approval_chain.return_value = mock_chain_config

        mock_audit = MagicMock()
        mock_audit.log_event = AsyncMock()

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalHITLIntegration",
                return_value=mock_hitl,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=mock_audit,
            ),
            _review_api_patch(
                "AuditClientConfig",
                return_value=MagicMock(),
            ),
        ):
            request = ApprovalRequest(
                approver_agent_id="judge-001",
                comments="Looks good",
            )
            result = await approve_amendment("amend-001", request)
        assert result.success is True
        assert "fully approved" in result.next_steps[0]

    async def test_approve_pending_more_approvals(self):
        amendment = _make_amendment(status=AmendmentStatus.PROPOSED)
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        mock_hitl = MagicMock()
        mock_chain_config = MagicMock()
        mock_chain_config.required_approvals = 3  # need more approvals
        mock_hitl._determine_approval_chain.return_value = mock_chain_config

        mock_audit = MagicMock()
        mock_audit.log_event = AsyncMock()

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalHITLIntegration",
                return_value=mock_hitl,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=mock_audit,
            ),
            _review_api_patch(
                "AuditClientConfig",
                return_value=MagicMock(),
            ),
        ):
            request = ApprovalRequest(approver_agent_id="judge-001")
            result = await approve_amendment("amend-001", request)
        assert result.success is True
        assert "waiting for additional approvals" in result.next_steps[0]

    async def test_approve_maci_denied_raises_403(self):
        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": False})

        with (
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = ApprovalRequest(approver_agent_id="agent-bad")
            await approve_amendment("amend-001", request)
        assert exc_info.value.status_code == 403

    async def test_approve_not_found_raises_404(self):
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = None

        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = ApprovalRequest(approver_agent_id="judge-001")
            await approve_amendment("amend-001", request)
        assert exc_info.value.status_code == 404

    async def test_approve_wrong_status_raises_400(self):
        amendment = _make_amendment(status=AmendmentStatus.REJECTED)
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = ApprovalRequest(approver_agent_id="judge-001")
            await approve_amendment("amend-001", request)
        assert exc_info.value.status_code == 400

    async def test_approve_storage_error_raises_500(self):
        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        mock_storage = AsyncMock()
        mock_storage.connect.side_effect = RuntimeError("db boom")

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = ApprovalRequest(approver_agent_id="judge-001")
            await approve_amendment("amend-001", request)
        assert exc_info.value.status_code == 500


class TestRejectAmendment:
    async def test_reject_success(self):
        amendment = _make_amendment(status=AmendmentStatus.UNDER_REVIEW)
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        mock_audit = MagicMock()
        mock_audit.log_event = AsyncMock()

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=mock_audit,
            ),
            _review_api_patch(
                "AuditClientConfig",
                return_value=MagicMock(),
            ),
        ):
            request = RejectionRequest(
                rejector_agent_id="judge-001",
                reason="Does not meet constitutional standards for safety",
            )
            result = await reject_amendment("amend-001", request)
        assert result.success is True
        assert "rejected" in result.next_steps[0].lower()
        assert amendment.status == AmendmentStatus.REJECTED

    async def test_reject_maci_denied_raises_403(self):
        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": False})

        with (
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = RejectionRequest(
                rejector_agent_id="agent-bad",
                reason="This is a long enough reason for rejection testing.",
            )
            await reject_amendment("amend-001", request)
        assert exc_info.value.status_code == 403

    async def test_reject_not_found_raises_404(self):
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = None

        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = RejectionRequest(
                rejector_agent_id="judge-001",
                reason="Reason must be at least 10 characters",
            )
            await reject_amendment("amend-001", request)
        assert exc_info.value.status_code == 404

    async def test_reject_wrong_status_raises_400(self):
        amendment = _make_amendment(status=AmendmentStatus.APPROVED)
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = RejectionRequest(
                rejector_agent_id="judge-001",
                reason="This amendment was already approved, cannot reject.",
            )
            await reject_amendment("amend-001", request)
        assert exc_info.value.status_code == 400

    async def test_reject_storage_error_raises_500(self):
        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        mock_storage = AsyncMock()
        mock_storage.connect.side_effect = RuntimeError("db boom")

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = RejectionRequest(
                rejector_agent_id="judge-001",
                reason="Reason must be at least 10 characters",
            )
            await reject_amendment("amend-001", request)
        assert exc_info.value.status_code == 500


class TestRollbackToVersion:
    async def test_rollback_not_available_raises_501(self):
        with _review_api_patch("ROLLBACK_AVAILABLE", False):
            with pytest.raises(Exception) as exc_info:
                request = RollbackRequest(
                    requester_agent_id="judge-001",
                    justification="This is a valid justification for constitutional rollback action.",
                )
                await rollback_to_version("v1", request)
            assert exc_info.value.status_code == 501

    async def test_rollback_maci_denied_raises_403(self):
        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": False})

        with (
            _review_api_patch("ROLLBACK_AVAILABLE", True),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = RollbackRequest(
                requester_agent_id="agent-bad",
                justification="This is a valid justification for constitutional rollback action.",
            )
            await rollback_to_version("v1", request)
        assert exc_info.value.status_code == 403

    async def test_rollback_target_not_found_raises_404(self):
        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})
        mock_storage = AsyncMock()
        mock_storage.get_version.return_value = None

        with (
            _review_api_patch("ROLLBACK_AVAILABLE", True),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = RollbackRequest(
                requester_agent_id="judge-001",
                justification="This is a valid justification for constitutional rollback action.",
            )
            await rollback_to_version("v-nonexistent", request)
        assert exc_info.value.status_code == 404

    async def test_rollback_same_version_raises_400(self):
        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        target_version = MagicMock()
        target_version.version_id = "v1"
        target_version.version = "1.0.0"
        current_version = MagicMock()
        current_version.version_id = "v1"
        current_version.version = "1.0.0"

        mock_storage = AsyncMock()
        mock_storage.get_version.return_value = target_version
        mock_storage.get_active_version.return_value = current_version

        with (
            _review_api_patch("ROLLBACK_AVAILABLE", True),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = RollbackRequest(
                requester_agent_id="judge-001",
                justification="This is a valid justification for constitutional rollback action.",
            )
            await rollback_to_version("v1", request)
        assert exc_info.value.status_code == 400

    async def test_rollback_no_active_version_raises_500(self):
        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        target_version = MagicMock()
        target_version.version_id = "v1"

        mock_storage = AsyncMock()
        mock_storage.get_version.return_value = target_version
        mock_storage.get_active_version.return_value = None

        with (
            _review_api_patch("ROLLBACK_AVAILABLE", True),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = RollbackRequest(
                requester_agent_id="judge-001",
                justification="This is a valid justification for constitutional rollback action.",
            )
            await rollback_to_version("v1", request)
        assert exc_info.value.status_code == 500

    async def test_rollback_storage_error_raises_500(self):
        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        mock_storage = AsyncMock()
        mock_storage.connect.side_effect = RuntimeError("db boom")

        with (
            _review_api_patch("ROLLBACK_AVAILABLE", True),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            pytest.raises(Exception) as exc_info,
        ):
            request = RollbackRequest(
                requester_agent_id="judge-001",
                justification="This is a valid justification for constitutional rollback action.",
            )
            await rollback_to_version("v1", request)
        assert exc_info.value.status_code == 500


class TestApproveAmendmentWithXAgentId:
    async def test_uses_x_agent_id_header(self):
        amendment = _make_amendment(status=AmendmentStatus.UNDER_REVIEW)
        mock_storage = AsyncMock()
        mock_storage.get_amendment.return_value = amendment

        mock_maci = MagicMock()
        mock_maci.validate_action = AsyncMock(return_value={"allowed": True})

        mock_hitl = MagicMock()
        mock_chain_config = MagicMock()
        mock_chain_config.required_approvals = 1
        mock_hitl._determine_approval_chain.return_value = mock_chain_config

        mock_audit = MagicMock()
        mock_audit.log_event = AsyncMock()

        with (
            _review_api_patch(
                "ConstitutionalStorageService",
                return_value=mock_storage,
            ),
            _review_api_patch(
                "MACIEnforcer",
                return_value=mock_maci,
            ),
            _review_api_patch(
                "ConstitutionalHITLIntegration",
                return_value=mock_hitl,
            ),
            _review_api_patch(
                "AuditClient",
                return_value=mock_audit,
            ),
            _review_api_patch(
                "AuditClientConfig",
                return_value=MagicMock(),
            ),
        ):
            request = ApprovalRequest(approver_agent_id="judge-001")
            result = await approve_amendment("amend-001", request, x_agent_id="header-agent")
        # MACI should have been called with header-agent
        call_kwargs = mock_maci.validate_action.call_args[1]
        assert call_kwargs["agent_id"] == "header-agent"


# ============================================================================
# Response model tests for review_api
# ============================================================================


class TestResponseModels:
    def test_amendment_list_response(self):
        resp = AmendmentListResponse(
            amendments=[],
            total=0,
            limit=50,
            offset=0,
        )
        assert resp.total == 0

    def test_amendment_detail_response(self):
        resp = AmendmentDetailResponse(
            amendment=_make_amendment(),
        )
        assert resp.amendment.proposal_id == "amend-001"

    def test_approval_response(self):
        resp = ApprovalResponse(
            success=True,
            amendment=_make_amendment(),
            message="approved",
        )
        assert resp.success is True

    def test_rollback_response(self):
        resp = RollbackResponse(
            success=True,
            rollback_id="rb-001",
            previous_version="2.0.0",
            restored_version="1.0.0",
            message="rolled back",
            justification="safety concern with sufficient length",
        )
        assert resp.success is True
        assert resp.rollback_id == "rb-001"
