"""
Coverage tests for:
  - enhanced_agent_bus.deliberation_layer.integration (DeliberationLayer)
  - enhanced_agent_bus.deliberation_layer.tensorrt_optimizer (TensorRTOptimizer)
  - enhanced_agent_bus.mcp.pool (MCPClientPool)

Targets missing branches and lines to push coverage above 80%.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Integration: DeliberationLayer
# ---------------------------------------------------------------------------
from enhanced_agent_bus.deliberation_layer.integration import (
    DeliberationLayer,
    _lazy_import,
    _truncate_content_for_hotl,
    get_deliberation_layer,
    reset_deliberation_layer,
)

# ---------------------------------------------------------------------------
# Helpers for building mocks
# ---------------------------------------------------------------------------


def _make_mock_message(**overrides: Any) -> MagicMock:
    """Build a mock AgentMessage with sensible defaults."""
    msg = MagicMock()
    msg.message_id = overrides.get("message_id", "msg-001")
    msg.from_agent = overrides.get("from_agent", "agent-a")
    msg.to_agent = overrides.get("to_agent", "agent-b")
    msg.sender_id = overrides.get("sender_id", "agent-a")
    msg.tenant_id = overrides.get("tenant_id", "tenant-1")
    msg.content = overrides.get("content", "test content")
    msg.impact_score = overrides.get("impact_score", None)
    msg.priority = overrides.get("priority", "normal")
    msg.message_type = overrides.get("message_type", MagicMock(value="command"))
    msg.constitutional_hash = overrides.get("constitutional_hash", "608508a9bd224290")
    msg.status = overrides.get("status", "pending")
    msg.to_dict = MagicMock(return_value={"id": msg.message_id})
    return msg


def _make_guard_result(*, is_allowed: bool, decision: str, **extra: Any) -> MagicMock:
    gr = MagicMock()
    gr.is_allowed = is_allowed
    gr.decision = decision
    gr.validation_errors = extra.get("validation_errors", [])
    gr.validation_warnings = extra.get("validation_warnings", [])
    gr.required_signers = extra.get("required_signers", ["signer-1"])
    gr.required_reviewers = extra.get("required_reviewers", ["critic-1"])
    gr.to_dict = MagicMock(return_value={"decision": decision, "is_allowed": is_allowed})
    return gr


def _build_layer(**overrides: Any) -> DeliberationLayer:
    """Build a DeliberationLayer with all components injected as mocks."""
    impact_scorer = overrides.get("impact_scorer", MagicMock())
    impact_scorer.calculate_impact_score = MagicMock(return_value=0.5)

    adaptive_router = overrides.get("adaptive_router", MagicMock())
    adaptive_router.route_message = AsyncMock(return_value={"lane": "fast"})
    adaptive_router.update_performance_feedback = AsyncMock()
    adaptive_router.get_routing_stats = MagicMock(return_value={"total": 10})
    adaptive_router.force_deliberation = AsyncMock(
        return_value={"forced": True, "lane": "deliberation"}
    )

    delib_queue = overrides.get("deliberation_queue", MagicMock())
    delib_queue.enqueue_for_deliberation = AsyncMock(return_value="item-001")
    delib_queue.submit_human_decision = AsyncMock(return_value=True)
    delib_queue.submit_agent_vote = AsyncMock(return_value=True)
    delib_queue.get_queue_status = MagicMock(
        return_value={"stats": {}, "queue_size": 0, "processing_count": 0}
    )
    delib_queue.get_item_details = MagicMock(return_value={"message_id": "msg-001"})
    delib_queue.resolve_task = AsyncMock()
    delib_queue.get_task = MagicMock(
        return_value=SimpleNamespace(
            created_at=datetime.now(UTC),
            message=_make_mock_message(),
        )
    )

    opa_guard = overrides.get("opa_guard", None)
    llm_assistant = overrides.get("llm_assistant", None)

    layer = DeliberationLayer(
        enable_opa_guard=False,
        enable_llm=False,
        enable_redis=overrides.get("enable_redis", False),
        enable_learning=overrides.get("enable_learning", True),
        impact_scorer=impact_scorer,
        adaptive_router=adaptive_router,
        deliberation_queue=delib_queue,
        opa_guard=opa_guard,
        llm_assistant=llm_assistant,
    )
    return layer


# ===========================================================================
# _truncate_content_for_hotl
# ===========================================================================


class TestTruncateContentForHotl:
    def test_string_under_limit(self):
        assert _truncate_content_for_hotl("short", limit=500) == "short"

    def test_string_over_limit(self):
        result = _truncate_content_for_hotl("a" * 1000, limit=10)
        assert len(result) == 10

    def test_none_returns_empty(self):
        assert _truncate_content_for_hotl(None) == ""

    def test_non_string_object(self):
        result = _truncate_content_for_hotl({"key": "value"}, limit=10)
        assert isinstance(result, str)
        assert len(result) <= 10


# ===========================================================================
# Global layer singleton
# ===========================================================================


class TestGlobalLayerSingleton:
    def teardown_method(self):
        reset_deliberation_layer()

    def test_get_deliberation_layer_creates_singleton(self):
        layer = get_deliberation_layer()
        assert isinstance(layer, DeliberationLayer)

    def test_get_deliberation_layer_returns_same_instance(self):
        a = get_deliberation_layer()
        b = get_deliberation_layer()
        assert a is b

    def test_reset_deliberation_layer_clears_singleton(self):
        a = get_deliberation_layer()
        reset_deliberation_layer()
        b = get_deliberation_layer()
        assert a is not b


# ===========================================================================
# DeliberationLayer.__init__ branches
# ===========================================================================


class TestDeliberationLayerInit:
    def test_default_init_with_injected_components(self):
        layer = _build_layer()
        assert layer.impact_threshold == 0.8
        assert layer.enable_redis is False
        assert layer.enable_learning is True

    def test_init_with_redis_enabled(self):
        redis_queue = MagicMock()
        redis_voting = MagicMock()
        layer = _build_layer(
            enable_redis=True,
        )
        # Redis is enabled but no injection => lazy-import defaults attempted
        assert layer.enable_redis is True

    def test_init_with_injected_opa_guard(self):
        guard = MagicMock()
        layer = _build_layer(opa_guard=guard)
        assert layer.opa_guard is guard

    def test_init_with_injected_llm_assistant(self):
        llm = MagicMock()
        layer = _build_layer(llm_assistant=llm)
        assert layer.llm_assistant is llm

    def test_redis_disabled_ignores_redis_components(self):
        layer = _build_layer(enable_redis=False)
        assert layer.redis_queue is None
        assert layer.redis_voting is None

    def test_property_accessors(self):
        layer = _build_layer()
        assert layer.injected_impact_scorer is layer.impact_scorer
        assert layer.injected_router is layer.adaptive_router
        assert layer.injected_queue is layer.deliberation_queue


# ===========================================================================
# DeliberationLayer.initialize
# ===========================================================================


class TestDeliberationLayerInitialize:
    @pytest.mark.asyncio
    async def test_initialize_without_redis(self):
        layer = _build_layer()
        await layer.initialize()
        # Should not raise

    @pytest.mark.asyncio
    async def test_initialize_with_opa_guard(self):
        guard = MagicMock()
        guard.initialize = AsyncMock()
        layer = _build_layer(opa_guard=guard)
        await layer.initialize()
        guard.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_with_redis(self):
        layer = _build_layer(enable_redis=True)
        # Manually inject redis mocks after construction
        layer.redis_queue = MagicMock()
        layer.redis_queue.connect = AsyncMock()
        layer.redis_voting = MagicMock()
        layer.redis_voting.connect = AsyncMock()
        await layer.initialize()
        layer.redis_queue.connect.assert_awaited_once()
        layer.redis_voting.connect.assert_awaited_once()


# ===========================================================================
# DeliberationLayer.process_message
# ===========================================================================


class TestProcessMessage:
    @pytest.mark.asyncio
    async def test_process_fast_lane(self):
        layer = _build_layer()
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert result["success"] is True
        assert result["lane"] == "fast"

    @pytest.mark.asyncio
    async def test_process_fast_lane_with_callback(self):
        layer = _build_layer()
        cb = AsyncMock()
        layer.set_fast_lane_callback(cb)
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert result["lane"] == "fast"
        cb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_deliberation_lane(self):
        layer = _build_layer()
        layer.adaptive_router.route_message = AsyncMock(
            return_value={"lane": "deliberation", "impact_score": 0.85}
        )
        msg = _make_mock_message(impact_score=0.85)
        result = await layer.process_message(msg)
        assert result["success"] is True
        assert result["lane"] == "deliberation"

    @pytest.mark.asyncio
    async def test_process_deliberation_with_redis(self):
        layer = _build_layer(enable_redis=True)
        layer.redis_queue = MagicMock()
        layer.redis_queue.enqueue_deliberation_item = AsyncMock()
        layer.adaptive_router.route_message = AsyncMock(
            return_value={"lane": "deliberation", "impact_score": 0.85}
        )
        msg = _make_mock_message(impact_score=0.85)
        result = await layer.process_message(msg)
        assert result["lane"] == "deliberation"
        layer.redis_queue.enqueue_deliberation_item.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_deliberation_with_callback(self):
        layer = _build_layer()
        layer.adaptive_router.route_message = AsyncMock(
            return_value={"lane": "deliberation", "impact_score": 0.85}
        )
        cb = AsyncMock()
        layer.set_deliberation_callback(cb)
        msg = _make_mock_message(impact_score=0.85)
        result = await layer.process_message(msg)
        assert result["lane"] == "deliberation"
        cb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_with_impact_score_calculation(self):
        layer = _build_layer()
        msg = _make_mock_message(impact_score=None)
        await layer.process_message(msg)
        layer.impact_scorer.calculate_impact_score.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_timeout_error(self):
        layer = _build_layer()
        layer.adaptive_router.route_message = AsyncMock(side_effect=TimeoutError("timed out"))
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert "Timeout" in result["error"]

    @pytest.mark.asyncio
    async def test_process_value_error(self):
        layer = _build_layer()
        layer.adaptive_router.route_message = AsyncMock(side_effect=ValueError("bad value"))
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert "ValueError" in result["error"]

    @pytest.mark.asyncio
    async def test_process_runtime_error(self):
        layer = _build_layer()
        layer.adaptive_router.route_message = AsyncMock(side_effect=RuntimeError("boom"))
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert "RuntimeError" in result["error"]

    @pytest.mark.asyncio
    async def test_process_cancelled_error_propagates(self):
        layer = _build_layer()
        layer.adaptive_router.route_message = AsyncMock(side_effect=asyncio.CancelledError())
        msg = _make_mock_message()
        with pytest.raises(asyncio.CancelledError):
            await layer.process_message(msg)

    @pytest.mark.asyncio
    async def test_process_with_no_router(self):
        layer = _build_layer()
        layer.adaptive_router = None
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert result.get("lane") == "fast"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_process_with_graphrag_enricher(self):
        enricher = MagicMock()
        enricher.enrich = AsyncMock(return_value={"policy": "data"})
        layer = _build_layer()
        layer._graphrag_enricher = enricher
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert result["success"] is True
        enricher.enrich.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_with_graphrag_enricher_returns_none(self):
        enricher = MagicMock()
        enricher.enrich = AsyncMock(return_value=None)
        layer = _build_layer()
        layer._graphrag_enricher = enricher
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert result["success"] is True


# ===========================================================================
# OPA Guard evaluation paths
# ===========================================================================


class TestOPAGuardEvaluation:
    @pytest.mark.asyncio
    async def test_guard_allows_message(self):
        guard = MagicMock()
        gr = _make_guard_result(is_allowed=True, decision="ALLOW")
        guard.verify_action = AsyncMock(return_value=gr)
        guard.initialize = AsyncMock()
        guard.get_stats = MagicMock(return_value={})

        layer = _build_layer(opa_guard=guard)
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_guard_denies_message(self):
        guard = MagicMock()
        guard_decision_deny = _lazy_import("GuardDecision").DENY
        gr = _make_guard_result(
            is_allowed=False,
            decision=guard_decision_deny,
            validation_errors=["policy violation"],
        )
        guard.verify_action = AsyncMock(return_value=gr)
        guard.initialize = AsyncMock()

        layer = _build_layer(opa_guard=guard)
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert result["lane"] == "denied"

    @pytest.mark.asyncio
    async def test_guard_requires_signatures_success(self):
        guard = MagicMock()
        guard_decision_sig = _lazy_import("GuardDecision").REQUIRE_SIGNATURES
        gr = _make_guard_result(
            is_allowed=False,
            decision=guard_decision_sig,
            required_signers=["signer-1"],
        )
        guard.verify_action = AsyncMock(return_value=gr)
        guard.initialize = AsyncMock()

        sig_result = MagicMock()
        sig_result.is_valid = True
        sig_result.to_dict = MagicMock(return_value={"valid": True})
        guard.collect_signatures = AsyncMock(return_value=sig_result)

        layer = _build_layer(opa_guard=guard)
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        # After signatures collected, it routes the verified message
        assert "signature_result" in result

    @pytest.mark.asyncio
    async def test_guard_requires_signatures_failure(self):
        guard = MagicMock()
        guard_decision_sig = _lazy_import("GuardDecision").REQUIRE_SIGNATURES
        gr = _make_guard_result(
            is_allowed=False,
            decision=guard_decision_sig,
        )
        guard.verify_action = AsyncMock(return_value=gr)
        guard.initialize = AsyncMock()

        sig_result = MagicMock()
        sig_result.is_valid = False
        sig_result.status = MagicMock(value="failed")
        sig_result.to_dict = MagicMock(return_value={"valid": False})
        guard.collect_signatures = AsyncMock(return_value=sig_result)

        layer = _build_layer(opa_guard=guard)
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert result["lane"] == "signature_required"

    @pytest.mark.asyncio
    async def test_guard_requires_review_approved(self):
        guard = MagicMock()
        guard_decision_review = _lazy_import("GuardDecision").REQUIRE_REVIEW
        gr = _make_guard_result(
            is_allowed=False,
            decision=guard_decision_review,
            required_reviewers=["critic-1"],
        )
        guard.verify_action = AsyncMock(return_value=gr)
        guard.initialize = AsyncMock()

        review_result = MagicMock()
        review_result.consensus_verdict = "approve"
        review_result.to_dict = MagicMock(return_value={"verdict": "approve"})
        guard.submit_for_review = AsyncMock(return_value=review_result)

        layer = _build_layer(opa_guard=guard)
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert "review_result" in result

    @pytest.mark.asyncio
    async def test_guard_requires_review_rejected(self):
        guard = MagicMock()
        guard_decision_review = _lazy_import("GuardDecision").REQUIRE_REVIEW
        gr = _make_guard_result(
            is_allowed=False,
            decision=guard_decision_review,
            required_reviewers=["critic-1"],
        )
        guard.verify_action = AsyncMock(return_value=gr)
        guard.initialize = AsyncMock()

        review_result = MagicMock()
        review_result.consensus_verdict = "reject"
        review_result.to_dict = MagicMock(return_value={"verdict": "reject"})
        guard.submit_for_review = AsyncMock(return_value=review_result)

        layer = _build_layer(opa_guard=guard)
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert result["lane"] == "review_required"

    @pytest.mark.asyncio
    async def test_guard_verification_error_fails_closed(self):
        guard = MagicMock()
        guard.verify_action = AsyncMock(side_effect=RuntimeError("OPA down"))
        guard.initialize = AsyncMock()

        layer = _build_layer(opa_guard=guard)
        msg = _make_mock_message()
        result = await layer.process_message(msg)
        # Fail-closed => denied
        assert result["success"] is False
        assert result["lane"] == "denied"

    @pytest.mark.asyncio
    async def test_guard_callback_invoked(self):
        guard = MagicMock()
        gr = _make_guard_result(is_allowed=True, decision="ALLOW")
        guard.verify_action = AsyncMock(return_value=gr)
        guard.initialize = AsyncMock()

        cb = AsyncMock()
        layer = _build_layer(opa_guard=guard)
        layer.set_guard_callback(cb)
        msg = _make_mock_message()
        await layer.process_message(msg)
        cb.assert_awaited_once()


# ===========================================================================
# submit_human_decision / submit_agent_vote
# ===========================================================================


class TestSubmitDecisions:
    @pytest.mark.asyncio
    async def test_submit_human_decision_approved(self):
        layer = _build_layer()
        ok = await layer.submit_human_decision("item-1", "reviewer-1", "approved", "looks good")
        assert ok is True

    @pytest.mark.asyncio
    async def test_submit_human_decision_rejected(self):
        layer = _build_layer()
        ok = await layer.submit_human_decision("item-1", "reviewer-1", "rejected", "nope")
        assert ok is True

    @pytest.mark.asyncio
    async def test_submit_human_decision_escalated(self):
        layer = _build_layer()
        ok = await layer.submit_human_decision("item-1", "reviewer-1", "escalated", "need help")
        assert ok is True

    @pytest.mark.asyncio
    async def test_submit_human_decision_with_enum_value(self):
        layer = _build_layer()
        decision_enum = MagicMock()
        decision_enum.value = "approved"
        ok = await layer.submit_human_decision("item-1", "reviewer-1", decision_enum, "ok")
        assert ok is True

    @pytest.mark.asyncio
    async def test_submit_human_decision_value_error(self):
        layer = _build_layer()
        layer.deliberation_queue.submit_human_decision = AsyncMock(side_effect=ValueError("bad"))
        ok = await layer.submit_human_decision("item-1", "reviewer-1", "approved", "ok")
        assert ok is False

    @pytest.mark.asyncio
    async def test_submit_human_decision_runtime_error(self):
        layer = _build_layer()
        layer.deliberation_queue.submit_human_decision = AsyncMock(
            side_effect=RuntimeError("broken")
        )
        ok = await layer.submit_human_decision("item-1", "reviewer-1", "approved", "ok")
        assert ok is False

    @pytest.mark.asyncio
    async def test_submit_agent_vote_approve(self):
        layer = _build_layer()
        ok = await layer.submit_agent_vote("item-1", "agent-1", "approve", "agreed")
        assert ok is True

    @pytest.mark.asyncio
    async def test_submit_agent_vote_reject(self):
        layer = _build_layer()
        ok = await layer.submit_agent_vote("item-1", "agent-1", "reject", "disagree")
        assert ok is True

    @pytest.mark.asyncio
    async def test_submit_agent_vote_abstain(self):
        layer = _build_layer()
        ok = await layer.submit_agent_vote("item-1", "agent-1", "abstain", "no opinion")
        assert ok is True

    @pytest.mark.asyncio
    async def test_submit_agent_vote_with_redis(self):
        layer = _build_layer(enable_redis=True)
        layer.redis_voting = MagicMock()
        layer.redis_voting.submit_vote = AsyncMock()
        ok = await layer.submit_agent_vote("item-1", "agent-1", "approve", "ok")
        assert ok is True
        layer.redis_voting.submit_vote.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_submit_agent_vote_value_error(self):
        layer = _build_layer()
        layer.deliberation_queue.submit_agent_vote = AsyncMock(side_effect=ValueError("bad"))
        ok = await layer.submit_agent_vote("item-1", "agent-1", "approve", "ok")
        assert ok is False

    @pytest.mark.asyncio
    async def test_submit_agent_vote_runtime_error(self):
        layer = _build_layer()
        layer.deliberation_queue.submit_agent_vote = AsyncMock(side_effect=RuntimeError("broken"))
        ok = await layer.submit_agent_vote("item-1", "agent-1", "approve", "ok")
        assert ok is False


# ===========================================================================
# _update_deliberation_outcome
# ===========================================================================


class TestUpdateDeliberationOutcome:
    @pytest.mark.asyncio
    async def test_outcome_approved(self):
        layer = _build_layer()
        await layer._update_deliberation_outcome("item-1", "approved", "good")
        layer.adaptive_router.update_performance_feedback.assert_awaited()

    @pytest.mark.asyncio
    async def test_outcome_rejected(self):
        layer = _build_layer()
        await layer._update_deliberation_outcome("item-1", "rejected", "bad")
        layer.adaptive_router.update_performance_feedback.assert_awaited()

    @pytest.mark.asyncio
    async def test_outcome_escalated(self):
        layer = _build_layer()
        await layer._update_deliberation_outcome("item-1", "escalated", "need help")

    @pytest.mark.asyncio
    async def test_outcome_learning_disabled(self):
        layer = _build_layer(enable_learning=False)
        await layer._update_deliberation_outcome("item-1", "approved", "ok")
        layer.adaptive_router.update_performance_feedback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_outcome_no_queue(self):
        layer = _build_layer()
        layer.deliberation_queue = None
        await layer._update_deliberation_outcome("item-1", "approved", "ok")
        # Should return early without error

    @pytest.mark.asyncio
    async def test_outcome_no_item_details(self):
        layer = _build_layer()
        layer.deliberation_queue.get_item_details = MagicMock(return_value=None)
        await layer._update_deliberation_outcome("item-1", "approved", "ok")

    @pytest.mark.asyncio
    async def test_outcome_no_message_id_in_details(self):
        layer = _build_layer()
        layer.deliberation_queue.get_item_details = MagicMock(return_value={"other": "data"})
        await layer._update_deliberation_outcome("item-1", "approved", "ok")

    @pytest.mark.asyncio
    async def test_outcome_error_caught(self):
        layer = _build_layer()
        layer.adaptive_router.update_performance_feedback = AsyncMock(
            side_effect=AttributeError("nope")
        )
        await layer._update_deliberation_outcome("item-1", "approved", "ok")
        # Should not raise


# ===========================================================================
# get_layer_stats
# ===========================================================================


class TestGetLayerStats:
    def test_stats_operational(self):
        layer = _build_layer()
        stats = layer.get_layer_stats()
        assert stats["layer_status"] == "operational"
        assert "router_stats" in stats
        assert "features" in stats

    def test_stats_with_opa_guard(self):
        guard = MagicMock()
        guard.get_stats = MagicMock(return_value={"checked": 10})
        guard.initialize = AsyncMock()
        layer = _build_layer(opa_guard=guard)
        stats = layer.get_layer_stats()
        assert "opa_guard_stats" in stats

    def test_stats_not_initialized(self):
        layer = _build_layer()
        layer.adaptive_router = None
        stats = layer.get_layer_stats()
        assert stats["layer_status"] == "not_initialized"

    def test_stats_not_initialized_no_queue(self):
        layer = _build_layer()
        layer.deliberation_queue = None
        stats = layer.get_layer_stats()
        assert stats["layer_status"] == "not_initialized"

    def test_stats_value_error(self):
        layer = _build_layer()
        layer.adaptive_router.get_routing_stats = MagicMock(side_effect=ValueError("bad"))
        stats = layer.get_layer_stats()
        assert "error" in stats

    def test_stats_runtime_error(self):
        layer = _build_layer()
        layer.adaptive_router.get_routing_stats = MagicMock(side_effect=RuntimeError("boom"))
        stats = layer.get_layer_stats()
        assert "error" in stats

    def test_stats_with_redis_in_async_context(self):
        layer = _build_layer(enable_redis=True)
        layer.redis_queue = MagicMock()
        layer.redis_queue.get_stream_info = AsyncMock(return_value={"streams": 1})
        stats = layer.get_layer_stats()
        # In sync context, should set redis_info=None (running loop check)
        assert "redis_info" in stats or "error" not in stats


# ===========================================================================
# analyze_trends / force_deliberation / resolve_deliberation_item
# ===========================================================================


class TestMiscMethods:
    @pytest.mark.asyncio
    async def test_analyze_trends_no_llm(self):
        layer = _build_layer()
        result = await layer.analyze_trends()
        assert "error" in result
        assert "LLM" in result["error"]

    @pytest.mark.asyncio
    async def test_analyze_trends_with_llm(self):
        llm = MagicMock()
        llm.analyze_deliberation_trends = AsyncMock(return_value={"trends": ["improving"]})
        layer = _build_layer(llm_assistant=llm)
        result = await layer.analyze_trends()
        assert result == {"trends": ["improving"]}

    @pytest.mark.asyncio
    async def test_analyze_trends_value_error(self):
        llm = MagicMock()
        llm.analyze_deliberation_trends = AsyncMock(side_effect=ValueError("bad"))
        layer = _build_layer(llm_assistant=llm)
        result = await layer.analyze_trends()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_analyze_trends_runtime_error(self):
        llm = MagicMock()
        llm.analyze_deliberation_trends = AsyncMock(side_effect=RuntimeError("boom"))
        layer = _build_layer(llm_assistant=llm)
        result = await layer.analyze_trends()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_force_deliberation(self):
        layer = _build_layer()
        msg = _make_mock_message(impact_score=0.3)
        result = await layer.force_deliberation(msg, reason="testing")
        assert result.get("forced") is True
        # Score should be restored
        assert msg.impact_score == 0.3

    @pytest.mark.asyncio
    async def test_force_deliberation_no_router(self):
        layer = _build_layer()
        layer.adaptive_router = None
        msg = _make_mock_message()
        result = await layer.force_deliberation(msg)
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_resolve_deliberation_item_approved(self):
        layer = _build_layer()
        result = await layer.resolve_deliberation_item("item-1", approved=True)
        assert result["status"] == "resolved"
        assert result["outcome"] == "approved"

    @pytest.mark.asyncio
    async def test_resolve_deliberation_item_rejected(self):
        layer = _build_layer()
        result = await layer.resolve_deliberation_item("item-1", approved=False)
        assert result["status"] == "resolved"
        assert result["outcome"] == "rejected"

    @pytest.mark.asyncio
    async def test_resolve_deliberation_item_no_queue(self):
        layer = _build_layer()
        layer.deliberation_queue = None
        result = await layer.resolve_deliberation_item("item-1", approved=True)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_resolve_deliberation_item_no_task(self):
        layer = _build_layer()
        layer.deliberation_queue.get_task = MagicMock(return_value=None)
        result = await layer.resolve_deliberation_item("item-1", approved=True)
        assert result["status"] == "resolved_no_feedback"

    @pytest.mark.asyncio
    async def test_resolve_deliberation_item_no_get_task_attr(self):
        layer = _build_layer()
        del layer.deliberation_queue.get_task
        result = await layer.resolve_deliberation_item("item-1", approved=True)
        assert result["status"] == "resolved_no_feedback"


# ===========================================================================
# close
# ===========================================================================


class TestClose:
    @pytest.mark.asyncio
    async def test_close_with_opa_guard(self):
        guard = MagicMock()
        guard.close = AsyncMock()
        guard.initialize = AsyncMock()
        layer = _build_layer(opa_guard=guard)
        await layer.close()
        guard.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_with_redis(self):
        layer = _build_layer(enable_redis=True)
        layer.redis_queue = MagicMock()
        layer.redis_queue.close = AsyncMock()
        layer.redis_voting = MagicMock()
        layer.redis_voting.close = AsyncMock()
        await layer.close()
        layer.redis_queue.close.assert_awaited_once()
        layer.redis_voting.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_minimal(self):
        layer = _build_layer()
        await layer.close()
        # No error expected


# ===========================================================================
# _record_performance_feedback
# ===========================================================================


class TestRecordPerformanceFeedback:
    @pytest.mark.asyncio
    async def test_feedback_fast_lane_success(self):
        layer = _build_layer()
        msg = _make_mock_message()
        result = {"lane": "fast", "success": True}
        await layer._record_performance_feedback(msg, result, 0.5)
        layer.adaptive_router.update_performance_feedback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_feedback_fast_lane_failure(self):
        layer = _build_layer()
        msg = _make_mock_message()
        result = {"lane": "fast", "success": False}
        await layer._record_performance_feedback(msg, result, 0.5)

    @pytest.mark.asyncio
    async def test_feedback_deliberation(self):
        layer = _build_layer()
        msg = _make_mock_message()
        result = {"lane": "deliberation"}
        await layer._record_performance_feedback(msg, result, 1.0)

    @pytest.mark.asyncio
    async def test_feedback_learning_disabled(self):
        layer = _build_layer(enable_learning=False)
        msg = _make_mock_message()
        await layer._record_performance_feedback(msg, {}, 0.5)
        layer.adaptive_router.update_performance_feedback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_feedback_error_caught(self):
        layer = _build_layer()
        layer.adaptive_router.update_performance_feedback = AsyncMock(
            side_effect=AttributeError("nope")
        )
        msg = _make_mock_message()
        await layer._record_performance_feedback(msg, {"lane": "fast"}, 0.5)
        # Should not raise


# ===========================================================================
# _run_dfc_diagnostics
# ===========================================================================


class TestDFCDiagnostics:
    @pytest.mark.asyncio
    async def test_dfc_runs_when_calculator_available(self):
        layer = _build_layer()
        layer.dfc_calculator = MagicMock()
        layer.dfc_calculator.calculate = MagicMock(return_value=0.85)
        msg = _make_mock_message(impact_score=0.5)
        result: dict[str, Any] = {"lane": "deliberation"}
        await layer._run_dfc_diagnostics(msg, result)
        assert "dfc_diagnostic_score" in result

    @pytest.mark.asyncio
    async def test_dfc_skipped_when_no_calculator(self):
        layer = _build_layer()
        layer.dfc_calculator = None
        msg = _make_mock_message()
        result: dict[str, Any] = {"lane": "deliberation"}
        await layer._run_dfc_diagnostics(msg, result)
        assert "dfc_diagnostic_score" not in result

    @pytest.mark.asyncio
    async def test_dfc_error_caught(self):
        layer = _build_layer()
        layer.dfc_calculator = MagicMock()
        layer.dfc_calculator.calculate = MagicMock(side_effect=ValueError("bad"))
        msg = _make_mock_message()
        result: dict[str, Any] = {"lane": "deliberation"}
        await layer._run_dfc_diagnostics(msg, result)
        # Should not raise


# ===========================================================================
# _route_verified_message
# ===========================================================================


class TestRouteVerifiedMessage:
    @pytest.mark.asyncio
    async def test_route_to_fast_lane(self):
        layer = _build_layer()
        layer.adaptive_router.route_message = AsyncMock(return_value={"lane": "fast"})
        msg = _make_mock_message()
        result = await layer._route_verified_message(msg)
        assert result["lane"] == "fast"

    @pytest.mark.asyncio
    async def test_route_to_deliberation(self):
        layer = _build_layer()
        layer.adaptive_router.route_message = AsyncMock(
            return_value={"lane": "deliberation", "impact_score": 0.9}
        )
        msg = _make_mock_message()
        result = await layer._route_verified_message(msg)
        assert result["lane"] == "deliberation"

    @pytest.mark.asyncio
    async def test_route_no_router(self):
        layer = _build_layer()
        layer.adaptive_router = None
        msg = _make_mock_message()
        result = await layer._route_verified_message(msg)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# TensorRT Optimizer
# ---------------------------------------------------------------------------

from enhanced_agent_bus.deliberation_layer.tensorrt_optimizer import (
    NUMPY_AVAILABLE,
    ONNX_AVAILABLE,
    TENSORRT_AVAILABLE,
    TORCH_AVAILABLE,
    TensorRTOptimizer,
    get_optimization_status,
    optimize_distilbert,
)


class TestTensorRTOptimizerInit:
    def test_default_init(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.model_name == "distilbert-base-uncased"
        assert opt.max_seq_length == 128
        assert opt.use_fp16 is True
        assert opt.cache_dir == tmp_path

    def test_custom_init(self, tmp_path: Path):
        opt = TensorRTOptimizer(
            model_name="bert-base-uncased",
            max_seq_length=256,
            use_fp16=False,
            cache_dir=tmp_path,
        )
        assert opt.model_name == "bert-base-uncased"
        assert opt.max_seq_length == 256
        assert opt.use_fp16 is False

    def test_model_id_generation(self, tmp_path: Path):
        opt = TensorRTOptimizer(model_name="some/model-name", cache_dir=tmp_path)
        assert opt.model_id == "some_model_name"

    def test_paths_set_correctly(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.onnx_path == tmp_path / "distilbert_base_uncased.onnx"
        assert opt.trt_path == tmp_path / "distilbert_base_uncased.trt"


class TestTensorRTOptimizerStatus:
    def test_status_property(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        status = opt.status
        assert "torch_available" in status
        assert "onnx_available" in status
        assert "tensorrt_available" in status
        assert status["model_name"] == "distilbert-base-uncased"
        assert status["max_seq_length"] == 128
        assert status["use_fp16"] is True
        assert status["active_backend"] == "none"


class TestTensorRTOptimizerExportOnnx:
    def test_export_onnx_requires_torch(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        if not TORCH_AVAILABLE:
            with pytest.raises(RuntimeError, match="PyTorch required"):
                opt.export_onnx()

    def test_export_onnx_cached(self, tmp_path: Path):
        # Create a fake onnx file
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.onnx_path.write_bytes(b"fake_onnx")
        result = opt.export_onnx(force=False)
        assert result == opt.onnx_path
        assert opt._optimization_status["onnx_exported"] is True


class TestTensorRTOptimizerConvertToTensorRT:
    def test_convert_no_tensorrt(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        if not TENSORRT_AVAILABLE:
            result = opt.convert_to_tensorrt()
            assert result is None

    def test_convert_cached(self, tmp_path: Path):
        if not TENSORRT_AVAILABLE:
            pytest.skip("TensorRT not available")
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt.trt_path.write_bytes(b"fake_trt")
        result = opt.convert_to_tensorrt(force=False)
        assert result == opt.trt_path


class TestTensorRTOptimizerLoadEngine:
    def test_load_tensorrt_engine_no_trt(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        if not TENSORRT_AVAILABLE:
            assert opt.load_tensorrt_engine() is False

    def test_load_tensorrt_engine_no_file(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        if TENSORRT_AVAILABLE:
            assert opt.load_tensorrt_engine() is False

    def test_load_onnx_runtime_no_onnx(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        if not ONNX_AVAILABLE:
            assert opt.load_onnx_runtime() is False
        else:
            # ONNX available but no model file
            assert opt.load_onnx_runtime() is False


class TestTensorRTOptimizerValidateEngine:
    def test_validate_nonexistent_file(self, tmp_path: Path):
        opt = TensorRTOptimizer(cache_dir=tmp_path)
        assert opt.validate_engine(tmp_path / "nonexistent.trt") is False

    def test_validate_no_tensorrt(self, tmp_path: Path):
        if not TENSORRT_AVAILABLE:
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            fake_file = tmp_path / "fake.trt"
            fake_file.write_bytes(b"x" * 2 * 1024 * 1024)
            assert opt.validate_engine(fake_file) is False

    def test_validate_small_file(self, tmp_path: Path):
        if TENSORRT_AVAILABLE:
            opt = TensorRTOptimizer(cache_dir=tmp_path)
            small_file = tmp_path / "small.trt"
            small_file.write_bytes(b"small")
            assert opt.validate_engine(small_file) is False


class TestTensorRTOptimizerInfer:
    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="numpy not available")
    def test_infer_calls_infer_batch(self, tmp_path: Path):
        import numpy as np

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        fake_result = np.zeros((1, 768), dtype=np.float32)
        opt.infer_batch = MagicMock(return_value=fake_result)
        result = opt.infer("test text")
        opt.infer_batch.assert_called_once_with(["test text"])
        assert result.shape == (768,)

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="numpy not available")
    def test_generate_fallback_embeddings(self, tmp_path: Path):
        import numpy as np

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        result = opt._generate_fallback_embeddings(3)
        assert result.shape == (3, 768)
        assert (result == 0).all()

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="numpy not available")
    def test_infer_batch_fallback_on_error(self, tmp_path: Path):
        import numpy as np

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        # Mock tokenizer
        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.ones((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }
        opt._tokenizer_cache[opt.model_name] = mock_tokenizer
        # No backend loaded, _infer_torch will fail
        opt._load_torch_model = MagicMock(side_effect=RuntimeError("no model"))

        result = opt.infer_batch(["test"])
        assert result.shape == (1, 768)
        assert (result == 0).all()

    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="numpy not available")
    def test_infer_batch_timeout_fallback(self, tmp_path: Path):
        import numpy as np

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        opt._latency_threshold_ms = 0.0  # Force immediate timeout

        mock_tokenizer = MagicMock()
        mock_tokenizer.return_value = {
            "input_ids": np.ones((1, 128), dtype=np.int64),
            "attention_mask": np.ones((1, 128), dtype=np.int64),
        }
        opt._tokenizer_cache[opt.model_name] = mock_tokenizer

        result = opt.infer_batch(["test"])
        assert result.shape == (1, 768)
        assert (result == 0).all()


class TestTensorRTOptimizerInferOnnx:
    @pytest.mark.skipif(not NUMPY_AVAILABLE, reason="numpy not available")
    def test_infer_onnx_no_session(self, tmp_path: Path):
        import numpy as np

        opt = TensorRTOptimizer(cache_dir=tmp_path)
        with pytest.raises(RuntimeError, match="ONNX session not loaded"):
            opt._infer_onnx(
                {
                    "input_ids": np.ones((1, 128), dtype=np.int64),
                    "attention_mask": np.ones((1, 128), dtype=np.int64),
                }
            )


class TestTensorRTModuleFunctions:
    def test_get_optimization_status(self, tmp_path: Path):
        status = get_optimization_status()
        assert isinstance(status, dict)
        assert "model_name" in status
        assert "active_backend" in status

    def test_optimize_distilbert_no_torch(self, tmp_path: Path):
        if not TORCH_AVAILABLE:
            result = optimize_distilbert(force=False)
            # Should get an onnx_error since torch is unavailable
            assert "onnx_error" in result or "steps_completed" in result


# ---------------------------------------------------------------------------
# MCP Pool
# ---------------------------------------------------------------------------

from enhanced_agent_bus.mcp.pool import (
    MCPClientPool,
    MCPPoolDuplicateClientError,
    MCPPoolError,
    MCPToolNotFoundError,
    create_mcp_pool,
)


def _make_mock_client(
    server_id: str = "srv-1",
    is_connected: bool = True,
    tools: list | None = None,
) -> MagicMock:
    """Create a mock MCPClient."""
    from enhanced_agent_bus.mcp.client import MCPClientState
    from enhanced_agent_bus.mcp.types import MCPTool, MCPToolResult, MCPToolStatus

    client = MagicMock()
    client.server_id = server_id
    client.is_connected = is_connected
    client.state = MCPClientState.CONNECTED if is_connected else MCPClientState.DISCONNECTED
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()

    if tools is None:
        tools = [
            MCPTool(
                name=f"tool_{server_id}", description="a tool", input_schema={}, server_id=server_id
            ),
        ]
    client.list_tools = AsyncMock(return_value=tools)
    client.call_tool = AsyncMock(
        return_value=MCPToolResult.success(
            tool_name="test",
            content={"result": "ok"},
            agent_id="agent-1",
        )
    )
    return client


class TestMCPPoolExceptions:
    def test_pool_error_has_hash(self):
        err = MCPPoolError("test error")
        assert err.constitutional_hash

    def test_duplicate_client_error(self):
        err = MCPPoolDuplicateClientError("dup")
        assert isinstance(err, MCPPoolError)

    def test_tool_not_found_error(self):
        err = MCPToolNotFoundError("not found")
        assert isinstance(err, MCPPoolError)


class TestMCPPoolRegistration:
    def test_register_client(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a")
        pool.register_client(client)
        assert pool.client_count == 1

    def test_register_duplicate_raises(self):
        pool = MCPClientPool()
        client_a = _make_mock_client("srv-a")
        pool.register_client(client_a)
        client_b = _make_mock_client("srv-a")
        with pytest.raises(MCPPoolDuplicateClientError):
            pool.register_client(client_b)

    def test_register_multiple_clients(self):
        pool = MCPClientPool()
        pool.register_client(_make_mock_client("srv-a"))
        pool.register_client(_make_mock_client("srv-b"))
        assert pool.client_count == 2


class TestMCPPoolIntrospection:
    def test_client_count(self):
        pool = MCPClientPool()
        assert pool.client_count == 0
        pool.register_client(_make_mock_client("srv-a"))
        assert pool.client_count == 1

    def test_tool_count(self):
        pool = MCPClientPool()
        assert pool.tool_count == 0

    def test_server_ids(self):
        pool = MCPClientPool()
        pool.register_client(_make_mock_client("srv-a"))
        pool.register_client(_make_mock_client("srv-b"))
        assert pool.server_ids() == ["srv-a", "srv-b"]

    def test_repr(self):
        pool = MCPClientPool()
        r = repr(pool)
        assert "MCPClientPool" in r
        assert "clients=0" in r
        assert "tools=0" in r


class TestMCPPoolConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_all_no_clients(self):
        pool = MCPClientPool()
        await pool.connect_all()
        # Logs warning, no error

    @pytest.mark.asyncio
    async def test_connect_all_success(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a", is_connected=False)

        # After connect is called, simulate the client becoming connected
        async def fake_connect():
            client.is_connected = True

        client.connect = AsyncMock(side_effect=fake_connect)
        pool.register_client(client)
        await pool.connect_all()
        client.connect.assert_awaited_once()
        assert pool.tool_count >= 1

    @pytest.mark.asyncio
    async def test_connect_all_with_failure(self):
        pool = MCPClientPool()
        good = _make_mock_client("srv-good", is_connected=False)

        async def good_connect():
            good.is_connected = True

        good.connect = AsyncMock(side_effect=good_connect)

        bad = _make_mock_client("srv-bad", is_connected=False)
        bad.connect = AsyncMock(side_effect=ConnectionError("refused"))
        bad.is_connected = False

        pool.register_client(good)
        pool.register_client(bad)
        await pool.connect_all()
        # Good client connected, bad did not
        assert pool.tool_count >= 1

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a")
        pool.register_client(client)
        await pool.connect_all()
        await pool.disconnect_all()
        client.disconnect.assert_awaited_once()
        assert pool.tool_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_all_with_error(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a")
        client.disconnect = AsyncMock(side_effect=OSError("socket error"))
        pool.register_client(client)
        await pool.disconnect_all()
        # Should not raise

    @pytest.mark.asyncio
    async def test_context_manager(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a", is_connected=False)

        async def fake_connect():
            client.is_connected = True

        client.connect = AsyncMock(side_effect=fake_connect)
        pool.register_client(client)
        async with pool as p:
            assert p is pool
            assert pool.tool_count >= 1
        client.disconnect.assert_awaited_once()


class TestMCPPoolListTools:
    @pytest.mark.asyncio
    async def test_list_tools_no_filter(self):
        from enhanced_agent_bus.mcp.types import MCPTool

        pool = MCPClientPool()
        client = _make_mock_client(
            "srv-a",
            tools=[
                MCPTool(name="search_docs", description="search", input_schema={}),
                MCPTool(name="execute_cmd", description="exec", input_schema={}),
            ],
        )

        async def fake_connect():
            client.is_connected = True

        client.connect = AsyncMock(side_effect=fake_connect)
        pool.register_client(client)
        await pool.connect_all()

        tools = await pool.list_tools()
        assert len(tools) == 2

    @pytest.mark.asyncio
    async def test_list_tools_with_maci_role(self):
        from enhanced_agent_bus.mcp.types import MCPTool

        pool = MCPClientPool()
        client = _make_mock_client(
            "srv-a",
            tools=[
                MCPTool(name="search_docs", description="search", input_schema={}),
                MCPTool(name="execute_cmd", description="exec", input_schema={}),
            ],
        )

        async def fake_connect():
            client.is_connected = True

        client.connect = AsyncMock(side_effect=fake_connect)
        pool.register_client(client)
        await pool.connect_all()

        # judicial role should not see execute_ tools
        tools = await pool.list_tools(maci_role="judicial")
        tool_names = [t.name for t in tools]
        assert "execute_cmd" not in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_empty_role(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a")

        async def fake_connect():
            client.is_connected = True

        client.connect = AsyncMock(side_effect=fake_connect)
        pool.register_client(client)
        await pool.connect_all()

        tools = await pool.list_tools(maci_role="")
        assert tools == []

    @pytest.mark.asyncio
    async def test_list_tools_unknown_role(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a")

        async def fake_connect():
            client.is_connected = True

        client.connect = AsyncMock(side_effect=fake_connect)
        pool.register_client(client)
        await pool.connect_all()

        tools = await pool.list_tools(maci_role="unknown_role")
        assert tools == []


class TestMCPPoolCallTool:
    @pytest.mark.asyncio
    async def test_call_existing_tool(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a")

        async def fake_connect():
            client.is_connected = True

        client.connect = AsyncMock(side_effect=fake_connect)
        pool.register_client(client)
        await pool.connect_all()

        tool_name = "tool_srv-a"
        result = await pool.call_tool(tool_name, arguments={"q": "test"}, agent_id="a1")
        assert result.is_success

    @pytest.mark.asyncio
    async def test_call_nonexistent_tool(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a")

        async def fake_connect():
            client.is_connected = True

        client.connect = AsyncMock(side_effect=fake_connect)
        pool.register_client(client)
        await pool.connect_all()

        result = await pool.call_tool("nonexistent_tool", agent_id="a1", agent_role="exec")
        assert not result.is_success
        assert "not available" in (result.error or "")


class TestMCPPoolHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_all_connected(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a", is_connected=True)
        pool.register_client(client)
        health = await pool.health_check()
        assert health == {"srv-a": True}

    @pytest.mark.asyncio
    async def test_health_check_reconnects_disconnected(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a", is_connected=False)

        async def fake_connect():
            client.is_connected = True

        client.connect = AsyncMock(side_effect=fake_connect)
        pool.register_client(client)
        health = await pool.health_check()
        assert health == {"srv-a": True}
        client.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_check_reconnect_fails(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a", is_connected=False)
        client.connect = AsyncMock(side_effect=ConnectionError("refused"))
        pool.register_client(client)
        health = await pool.health_check()
        assert health == {"srv-a": False}

    @pytest.mark.asyncio
    async def test_health_check_mixed(self):
        pool = MCPClientPool()
        good = _make_mock_client("srv-good", is_connected=True)
        bad = _make_mock_client("srv-bad", is_connected=False)
        bad.connect = AsyncMock(side_effect=ConnectionError("refused"))
        pool.register_client(good)
        pool.register_client(bad)
        health = await pool.health_check()
        assert health["srv-good"] is True
        assert health["srv-bad"] is False


class TestMCPPoolToolConflict:
    @pytest.mark.asyncio
    async def test_tool_conflict_first_wins(self):
        from enhanced_agent_bus.mcp.types import MCPTool

        pool = MCPClientPool()
        client_a = _make_mock_client(
            "srv-a",
            tools=[
                MCPTool(
                    name="shared_tool", description="from a", input_schema={}, server_id="srv-a"
                ),
            ],
        )
        client_b = _make_mock_client(
            "srv-b",
            tools=[
                MCPTool(
                    name="shared_tool", description="from b", input_schema={}, server_id="srv-b"
                ),
            ],
        )

        async def connect_a():
            client_a.is_connected = True

        async def connect_b():
            client_b.is_connected = True

        client_a.connect = AsyncMock(side_effect=connect_a)
        client_b.connect = AsyncMock(side_effect=connect_b)

        pool.register_client(client_a)
        pool.register_client(client_b)
        await pool.connect_all()

        # Should have one tool, from srv-a
        tools = await pool.list_tools()
        assert len(tools) == 1
        assert tools[0].server_id == "srv-a"

    @pytest.mark.asyncio
    async def test_incremental_index_conflict(self):
        from enhanced_agent_bus.mcp.types import MCPTool

        pool = MCPClientPool()
        client_a = _make_mock_client(
            "srv-a",
            tools=[
                MCPTool(
                    name="shared_tool", description="from a", input_schema={}, server_id="srv-a"
                ),
            ],
        )

        async def connect_a():
            client_a.is_connected = True

        client_a.connect = AsyncMock(side_effect=connect_a)
        pool.register_client(client_a)
        await pool.connect_all()

        # Now simulate incremental index from another client with conflicting tool
        client_b = _make_mock_client(
            "srv-b",
            tools=[
                MCPTool(
                    name="shared_tool", description="from b", input_schema={}, server_id="srv-b"
                ),
            ],
        )
        client_b.is_connected = True
        await pool._index_client_tools(client_b)

        # Should still have srv-a's tool
        tools = await pool.list_tools()
        assert len(tools) == 1
        assert tools[0].server_id == "srv-a"


class TestMCPPoolCollectClientToolsError:
    @pytest.mark.asyncio
    async def test_list_tools_exception_handled(self):
        pool = MCPClientPool()
        client = _make_mock_client("srv-a")
        client.list_tools = AsyncMock(side_effect=RuntimeError("protocol error"))
        client.is_connected = True

        async def connect():
            client.is_connected = True

        client.connect = AsyncMock(side_effect=connect)
        pool.register_client(client)
        await pool.connect_all()
        # Should have zero tools but no crash
        assert pool.tool_count == 0


class TestMCPPoolToolServerIdStamp:
    @pytest.mark.asyncio
    async def test_server_id_stamped_on_tool(self):
        from enhanced_agent_bus.mcp.types import MCPTool

        pool = MCPClientPool()
        # Tool with empty server_id
        tool_no_id = MCPTool(name="my_tool", description="test", input_schema={}, server_id="")
        client = _make_mock_client("srv-a", tools=[tool_no_id])

        async def connect():
            client.is_connected = True

        client.connect = AsyncMock(side_effect=connect)
        pool.register_client(client)
        await pool.connect_all()

        tools = await pool.list_tools()
        assert len(tools) == 1
        assert tools[0].server_id == "srv-a"


class TestCreateMCPPool:
    def test_create_empty_pool(self):
        pool = create_mcp_pool()
        assert pool.client_count == 0

    def test_create_pool_with_clients(self):
        a = _make_mock_client("srv-a")
        b = _make_mock_client("srv-b")
        pool = create_mcp_pool(a, b)
        assert pool.client_count == 2
        assert pool.server_ids() == ["srv-a", "srv-b"]


class TestMCPPoolRebuildIndex:
    @pytest.mark.asyncio
    async def test_rebuild_skips_disconnected(self):
        pool = MCPClientPool()
        connected = _make_mock_client("srv-a", is_connected=True)
        disconnected = _make_mock_client("srv-b", is_connected=False)
        pool._clients = [connected, disconnected]
        await pool._rebuild_tool_index()
        assert pool.tool_count >= 1  # Only from connected client
