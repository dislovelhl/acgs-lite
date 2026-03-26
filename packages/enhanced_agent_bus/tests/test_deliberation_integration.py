"""Tests for enhanced_agent_bus.deliberation_layer.integration — coverage boost.

Constitutional Hash: 608508a9bd224290

Tests the DeliberationLayer class, _truncate_content_for_hotl helper,
and internal methods for impact scoring, routing, and processing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.deliberation_layer.integration import (
    DeliberationLayer,
    _truncate_content_for_hotl,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(**overrides):
    """Create a minimal AgentMessage-like mock."""
    from enhanced_agent_bus.models import AgentMessage

    defaults = {
        "message_id": "msg-001",
        "content": "test message content",
        "from_agent": "agent-a",
        "to_agent": "agent-b",
        "sender_id": "agent-a",
        "tenant_id": "tenant-1",
        "priority": "normal",
        "message_type": "request",
        "constitutional_hash": "608508a9bd224290",
        "impact_score": None,
        "status": "pending",
    }
    defaults.update(overrides)
    msg = MagicMock(spec=AgentMessage)
    for k, v in defaults.items():
        setattr(msg, k, v)
    return msg


def _mock_imports():
    """Return a mock imports dict for _get_imports."""
    return {
        "get_impact_scorer": lambda: MagicMock(),
        "get_adaptive_router": lambda: MagicMock(),
        "get_deliberation_queue": lambda: MagicMock(),
        "get_llm_assistant": lambda: MagicMock(),
        "OPAGuard": lambda **kw: MagicMock(),
        "DFCCalculator": None,
        "DFCComponents": None,
        "get_dfc_components_from_context": lambda _: None,
        "AdaptiveRouterProtocol": object,
        "DeliberationQueueProtocol": object,
        "DeliberationStatus": object,
        "GuardDecision": object,
        "GuardResult": object,
        "ImpactScorerProtocol": object,
        "LLMAssistantProtocol": object,
        "OPAGuardProtocol": object,
        "RedisQueueProtocol": object,
        "RedisVotingProtocol": object,
        "VoteType": object,
        "get_redis_deliberation_queue": lambda: MagicMock(),
        "get_redis_voting_system": lambda: MagicMock(),
    }


def _build_layer(**overrides):
    """Build a DeliberationLayer with all imports mocked."""
    defaults = {
        "enable_redis": False,
        "enable_llm": False,
        "enable_opa_guard": False,
    }
    defaults.update(overrides)

    with patch(
        "enhanced_agent_bus.deliberation_layer.integration._get_imports",
        return_value=_mock_imports(),
    ):
        return DeliberationLayer(**defaults)


# ---------------------------------------------------------------------------
# _truncate_content_for_hotl
# ---------------------------------------------------------------------------


class TestTruncateContentForHotl:
    def test_string_input(self):
        assert _truncate_content_for_hotl("hello") == "hello"

    def test_long_string_truncated(self):
        long_str = "a" * 1000
        result = _truncate_content_for_hotl(long_str, limit=500)
        assert len(result) == 500

    def test_none_input(self):
        assert _truncate_content_for_hotl(None) == ""

    def test_non_string_input(self):
        result = _truncate_content_for_hotl(12345)
        assert result == "12345"

    def test_custom_limit(self):
        result = _truncate_content_for_hotl("hello world", limit=5)
        assert result == "hello"

    def test_empty_string(self):
        assert _truncate_content_for_hotl("") == ""


# ---------------------------------------------------------------------------
# DeliberationLayer — construction
# ---------------------------------------------------------------------------


class TestDeliberationLayerConstruction:
    def test_default_construction(self):
        layer = _build_layer()
        assert layer.impact_threshold == 0.8
        assert layer.enable_redis is False

    def test_custom_thresholds(self):
        layer = _build_layer(
            impact_threshold=0.5,
            high_risk_threshold=0.7,
            critical_risk_threshold=0.9,
        )
        assert layer.impact_threshold == 0.5
        assert layer.high_risk_threshold == 0.7
        assert layer.critical_risk_threshold == 0.9

    def test_injected_dependencies(self):
        scorer = MagicMock()
        router = MagicMock()
        queue = MagicMock()
        llm = MagicMock()
        opa = MagicMock()

        layer = _build_layer(
            impact_scorer=scorer,
            adaptive_router=router,
            deliberation_queue=queue,
            llm_assistant=llm,
            opa_guard=opa,
        )
        assert layer.impact_scorer is scorer
        assert layer.adaptive_router is router
        assert layer.deliberation_queue is queue
        assert layer.llm_assistant is llm
        assert layer.opa_guard is opa

    def test_redis_disabled_ignores_injected_redis(self):
        redis_q = MagicMock()
        redis_v = MagicMock()
        layer = _build_layer(
            enable_redis=False,
            redis_queue=redis_q,
            redis_voting=redis_v,
        )
        # When enable_redis=False, redis components should be None
        assert layer.redis_queue is None
        assert layer.redis_voting is None

    def test_graphrag_enricher_stored(self):
        enricher = MagicMock()
        layer = _build_layer(graphrag_enricher=enricher)
        assert layer._graphrag_enricher is enricher


# ---------------------------------------------------------------------------
# DeliberationLayer — properties
# ---------------------------------------------------------------------------


class TestDeliberationLayerProperties:
    def test_injected_impact_scorer(self):
        scorer = MagicMock()
        layer = _build_layer(impact_scorer=scorer)
        assert layer.injected_impact_scorer is scorer

    def test_injected_router(self):
        router = MagicMock()
        layer = _build_layer(adaptive_router=router)
        assert layer.injected_router is router

    def test_injected_queue(self):
        queue = MagicMock()
        layer = _build_layer(deliberation_queue=queue)
        assert layer.injected_queue is queue


# ---------------------------------------------------------------------------
# _prepare_processing_context
# ---------------------------------------------------------------------------


class TestPrepareProcessingContext:
    def test_returns_context_dict(self):
        layer = _build_layer()
        msg = _make_message()
        ctx = layer._prepare_processing_context(msg)
        assert ctx["agent_id"] == "agent-a"
        assert ctx["tenant_id"] == "tenant-1"
        assert ctx["constitutional_hash"] == "608508a9bd224290"

    def test_uses_sender_id_fallback(self):
        layer = _build_layer()
        msg = _make_message(from_agent=None, sender_id="sender-x")
        ctx = layer._prepare_processing_context(msg)
        # from_agent is None, so agent_id should be None (Python truthy check)
        # The implementation does `message.from_agent or message.sender_id`
        assert ctx["agent_id"] == "sender-x"


# ---------------------------------------------------------------------------
# _ensure_impact_score
# ---------------------------------------------------------------------------


class TestEnsureImpactScore:
    def test_calculates_when_none(self):
        scorer = MagicMock()
        scorer.calculate_impact_score.return_value = 0.5
        layer = _build_layer(impact_scorer=scorer)
        msg = _make_message(impact_score=None)

        layer._ensure_impact_score(msg, {"key": "val"})
        scorer.calculate_impact_score.assert_called_once()
        assert msg.impact_score == 0.5

    def test_skips_when_already_set(self):
        scorer = MagicMock()
        layer = _build_layer(impact_scorer=scorer)
        msg = _make_message(impact_score=0.9)

        layer._ensure_impact_score(msg, {})
        scorer.calculate_impact_score.assert_not_called()

    def test_skips_when_no_scorer(self):
        layer = _build_layer()
        layer.impact_scorer = None
        msg = _make_message(impact_score=None)
        layer._ensure_impact_score(msg, {})
        assert msg.impact_score is None


# ---------------------------------------------------------------------------
# _evaluate_opa_guard
# ---------------------------------------------------------------------------


class TestEvaluateOpaGuard:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_guard(self):
        layer = _build_layer()
        layer.opa_guard = None
        msg = _make_message()
        result = await layer._evaluate_opa_guard(msg, datetime.now(UTC))
        assert result is None


# ---------------------------------------------------------------------------
# _execute_routing
# ---------------------------------------------------------------------------


class TestExecuteRouting:
    @pytest.mark.asyncio
    async def test_returns_error_when_no_router(self):
        layer = _build_layer()
        layer.adaptive_router = None
        msg = _make_message()
        result = await layer._execute_routing(msg, {})
        assert result["lane"] == "fast"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_fast_lane_routing(self):
        router = MagicMock()
        router.set_impact_threshold = MagicMock()
        router.route_message = AsyncMock(return_value={"lane": "fast"})
        layer = _build_layer(adaptive_router=router)
        msg = _make_message(impact_score=0.1)
        layer._process_fast_lane = AsyncMock(return_value={"lane": "fast", "status": "delivered"})

        result = await layer._execute_routing(msg, {})
        assert result["lane"] == "fast"


# ---------------------------------------------------------------------------
# _process_fast_lane
# ---------------------------------------------------------------------------


class TestProcessFastLane:
    @pytest.mark.asyncio
    async def test_basic(self):
        layer = _build_layer()
        msg = _make_message(impact_score=0.1)
        result = await layer._process_fast_lane(msg, {"lane": "fast"})
        assert result["lane"] == "fast"
        assert result["status"] == "delivered"

    @pytest.mark.asyncio
    async def test_with_callback(self):
        layer = _build_layer()
        callback = AsyncMock()
        layer.fast_lane_callback = callback
        msg = _make_message(impact_score=0.1)

        await layer._process_fast_lane(msg, {"lane": "fast"})
        callback.assert_awaited_once_with(msg)


# ---------------------------------------------------------------------------
# _finalize_processing
# ---------------------------------------------------------------------------


class TestFinalizeProcessing:
    @pytest.mark.asyncio
    async def test_adds_processing_time_and_success(self):
        layer = _build_layer()
        layer._record_performance_feedback = AsyncMock()
        layer._run_dfc_diagnostics = AsyncMock()

        msg = _make_message()
        start = datetime.now(UTC)
        result = await layer._finalize_processing(msg, {"lane": "fast"}, start)

        assert "processing_time" in result
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_includes_guard_result_from_message(self):
        layer = _build_layer()
        layer._record_performance_feedback = AsyncMock()
        layer._run_dfc_diagnostics = AsyncMock()

        msg = _make_message()
        msg._guard_result = {"decision": "allow"}
        start = datetime.now(UTC)
        result = await layer._finalize_processing(msg, {"lane": "fast"}, start)
        assert result["guard_result"] == {"decision": "allow"}

    @pytest.mark.asyncio
    async def test_deliberation_lane_runs_dfc(self):
        layer = _build_layer()
        layer._record_performance_feedback = AsyncMock()
        layer._run_dfc_diagnostics = AsyncMock()

        msg = _make_message()
        start = datetime.now(UTC)
        await layer._finalize_processing(msg, {"lane": "deliberation"}, start)
        layer._run_dfc_diagnostics.assert_awaited_once()


# ---------------------------------------------------------------------------
# _record_performance_feedback
# ---------------------------------------------------------------------------


class TestRecordPerformanceFeedback:
    @pytest.mark.asyncio
    async def test_skips_when_learning_disabled(self):
        layer = _build_layer(enable_learning=False)
        msg = _make_message()
        await layer._record_performance_feedback(msg, {"lane": "fast"}, 1.0)

    @pytest.mark.asyncio
    async def test_skips_when_no_router(self):
        layer = _build_layer(enable_learning=True)
        layer.adaptive_router = None
        msg = _make_message()
        await layer._record_performance_feedback(msg, {"lane": "fast"}, 1.0)


# ---------------------------------------------------------------------------
# Callbacks initialization
# ---------------------------------------------------------------------------


class TestCallbacksInit:
    def test_callbacks_initialized_to_none(self):
        layer = _build_layer()
        assert layer.fast_lane_callback is None
        assert layer.deliberation_callback is None
        assert layer.guard_callback is None


# ---------------------------------------------------------------------------
# initialize (async)
# ---------------------------------------------------------------------------


class TestInitializeAsync:
    @pytest.mark.asyncio
    async def test_initialize_without_redis(self):
        layer = _build_layer(enable_redis=False)
        layer.opa_guard = None
        await layer.initialize()

    @pytest.mark.asyncio
    async def test_initialize_with_opa_guard(self):
        mock_guard = AsyncMock()
        mock_guard.initialize = AsyncMock()
        layer = _build_layer()
        layer.opa_guard = mock_guard

        await layer.initialize()
        mock_guard.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_with_redis(self):
        redis_q = AsyncMock()
        redis_q.connect = AsyncMock()
        redis_v = AsyncMock()
        redis_v.connect = AsyncMock()

        with patch(
            "enhanced_agent_bus.deliberation_layer.integration._get_imports",
            return_value=_mock_imports(),
        ):
            layer = DeliberationLayer(
                enable_redis=True,
                enable_llm=False,
                enable_opa_guard=False,
                redis_queue=redis_q,
                redis_voting=redis_v,
            )

        layer.opa_guard = None
        await layer.initialize()
        redis_q.connect.assert_awaited_once()
        redis_v.connect.assert_awaited_once()


# ---------------------------------------------------------------------------
# Basic config params
# ---------------------------------------------------------------------------


class TestBasicConfig:
    def test_deliberation_timeout(self):
        layer = _build_layer(deliberation_timeout=600)
        assert layer.deliberation_timeout == 600

    def test_enable_learning_default(self):
        layer = _build_layer()
        assert layer.enable_learning is True
