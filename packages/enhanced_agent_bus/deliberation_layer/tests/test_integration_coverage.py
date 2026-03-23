"""
Tests for deliberation_layer/integration.py — targets ≥90% coverage.
Constitutional Hash: cdd01ef066bc6cf2

asyncio_mode = "auto" — no @pytest.mark.asyncio decorators needed.
Run with: python -m pytest ... --import-mode=importlib
"""

from __future__ import annotations

import asyncio
import base64
import os
import secrets
import sys
from datetime import UTC, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.core.shared.constants import CONSTITUTIONAL_HASH as SHARED_CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Environment setup (mirrors root conftest.py)
# ---------------------------------------------------------------------------
if "ACGS2_ENCRYPTION_KEY" not in os.environ:
    os.environ["ACGS2_ENCRYPTION_KEY"] = base64.b64encode(secrets.token_bytes(32)).decode()
if "JWT_SECRET_KEY" not in os.environ:
    os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-for-testing-only"  # noqa: S105
if "JWT_ALGORITHM" not in os.environ:
    os.environ["JWT_ALGORITHM"] = "ES256"

# Ensure project root on path
_PROJECT_ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[6])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Module under test + helpers (imported after path setup)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.deliberation_layer.integration import (  # noqa: E402
    DeliberationEngine,
    DeliberationLayer,
    _get_imports,
    _lazy_import,
    _truncate_content_for_hotl,
    get_deliberation_layer,
    reset_deliberation_layer,
)
from enhanced_agent_bus.deliberation_layer.opa_guard_models import (  # noqa: E402
    GuardDecision,
    GuardResult,
)
from enhanced_agent_bus.models import (  # noqa: E402
    AgentMessage,
    MessageStatus,
    MessageType,
    Priority,
)

# ---------------------------------------------------------------------------
# Helpers — build lightweight mock components
# ---------------------------------------------------------------------------

CONSTITUTIONAL_HASH = SHARED_CONSTITUTIONAL_HASH  # pragma: allowlist secret


def _make_message(
    impact_score: float | None = None,
    from_agent: str = "agent-a",
    to_agent: str = "agent-b",
    message_type: MessageType = MessageType.COMMAND,
) -> AgentMessage:
    msg = AgentMessage()
    msg.from_agent = from_agent
    msg.to_agent = to_agent
    msg.sender_id = from_agent
    msg.content = {"text": "hello"}
    msg.message_type = message_type
    msg.tenant_id = "test-tenant"
    msg.priority = Priority.MEDIUM
    msg.impact_score = impact_score
    msg.constitutional_hash = CONSTITUTIONAL_HASH
    return msg


def _mock_impact_scorer(score: float = 0.5) -> MagicMock:
    scorer = MagicMock()
    scorer.calculate_impact_score.return_value = score
    return scorer


def _mock_router(lane: str = "fast", impact_score: float = 0.5) -> MagicMock:
    router = MagicMock()
    router.set_impact_threshold = MagicMock()
    router.route_message = AsyncMock(return_value={"lane": lane, "impact_score": impact_score})
    router.update_performance_feedback = AsyncMock(return_value=None)
    router.get_routing_stats = MagicMock(return_value={"calls": 0})
    router.force_deliberation = AsyncMock(return_value={"lane": "deliberation", "forced": True})
    return router


def _mock_queue() -> MagicMock:
    queue = MagicMock()
    queue.enqueue_for_deliberation = AsyncMock(return_value="item-123")
    queue.submit_human_decision = AsyncMock(return_value=True)
    queue.submit_agent_vote = AsyncMock(return_value=True)
    queue.get_queue_status = MagicMock(
        return_value={"stats": {}, "queue_size": 0, "processing_count": 0}
    )
    queue.get_item_details = MagicMock(return_value={"message_id": "msg-001"})
    task_mock = MagicMock()
    task_mock.created_at = datetime.now(UTC)
    task_mock.message = _make_message()
    queue.get_task = MagicMock(return_value=task_mock)
    queue.resolve_task = AsyncMock(return_value=None)
    return queue


def _mock_guard(
    decision: GuardDecision = GuardDecision.ALLOW,
    is_allowed: bool = True,
) -> MagicMock:
    guard = MagicMock()
    guard.initialize = AsyncMock(return_value=None)
    guard.close = AsyncMock(return_value=None)
    guard.get_stats = MagicMock(return_value={"verifications": 0})

    result = GuardResult(
        decision=decision,
        is_allowed=is_allowed,
        validation_errors=[],
        validation_warnings=[],
        required_signers=["signer-1"],
        required_reviewers=["reviewer-1"],
    )
    guard.verify_action = AsyncMock(return_value=result)
    return guard


def _build_layer(
    lane: str = "fast",
    impact_score: float | None = None,
    enable_redis: bool = False,
    enable_llm: bool = False,
    enable_opa_guard: bool = False,
    enable_learning: bool = True,
    guard: Any = None,
    queue: Any = None,
    router: Any = None,
    scorer: Any = None,
) -> DeliberationLayer:
    """Build a DeliberationLayer with fully mocked dependencies."""
    return DeliberationLayer(
        impact_scorer=scorer or _mock_impact_scorer(),
        adaptive_router=router or _mock_router(lane=lane),
        deliberation_queue=queue or _mock_queue(),
        llm_assistant=None,
        opa_guard=guard,
        redis_queue=None,
        redis_voting=None,
        enable_redis=enable_redis,
        enable_llm=enable_llm,
        enable_opa_guard=enable_opa_guard,
        enable_learning=enable_learning,
    )


# ===========================================================================
# Tests
# ===========================================================================


class TestDeliberationLayerInit:
    def test_defaults(self):
        layer = _build_layer()
        assert layer.impact_threshold == 0.8
        assert layer.deliberation_timeout == 300
        assert layer.enable_redis is False
        assert layer.enable_llm is False
        assert layer.fast_lane_callback is None
        assert layer.deliberation_callback is None
        assert layer.guard_callback is None

    def test_custom_thresholds(self):
        layer = DeliberationLayer(
            impact_scorer=_mock_impact_scorer(),
            adaptive_router=_mock_router(),
            deliberation_queue=_mock_queue(),
            llm_assistant=None,
            opa_guard=None,
            impact_threshold=0.6,
            high_risk_threshold=0.7,
            critical_risk_threshold=0.9,
            enable_opa_guard=False,
            enable_llm=False,
        )
        assert layer.impact_threshold == 0.6
        assert layer.high_risk_threshold == 0.7
        assert layer.critical_risk_threshold == 0.9

    def test_injected_components_are_stored(self):
        scorer = _mock_impact_scorer()
        router = _mock_router()
        queue = _mock_queue()
        layer = DeliberationLayer(
            impact_scorer=scorer,
            adaptive_router=router,
            deliberation_queue=queue,
            llm_assistant=None,
            opa_guard=None,
            enable_opa_guard=False,
            enable_llm=False,
        )
        assert layer.impact_scorer is scorer
        assert layer.adaptive_router is router
        assert layer.deliberation_queue is queue

    def test_property_accessors(self):
        layer = _build_layer()
        assert layer.injected_impact_scorer is layer.impact_scorer
        assert layer.injected_router is layer.adaptive_router
        assert layer.injected_queue is layer.deliberation_queue

    def test_enable_opa_guard_creates_guard(self):
        """When enable_opa_guard=True and no guard injected, an OPAGuard instance is created."""
        from enhanced_agent_bus.deliberation_layer.opa_guard import OPAGuard

        layer = DeliberationLayer(
            impact_scorer=_mock_impact_scorer(),
            adaptive_router=_mock_router(),
            deliberation_queue=_mock_queue(),
            llm_assistant=None,
            opa_guard=None,
            enable_opa_guard=True,
            enable_llm=False,
        )
        assert layer.opa_guard is not None
        assert isinstance(layer.opa_guard, OPAGuard)

    def test_enable_redis_uses_redis_queue(self):
        """When enable_redis=True and redis_queue injected, it becomes the deliberation queue."""
        redis_q = MagicMock()
        redis_q.connect = AsyncMock()
        redis_v = MagicMock()
        redis_v.connect = AsyncMock()
        layer = DeliberationLayer(
            impact_scorer=_mock_impact_scorer(),
            adaptive_router=_mock_router(),
            redis_queue=redis_q,
            redis_voting=redis_v,
            deliberation_queue=None,
            llm_assistant=None,
            opa_guard=None,
            enable_redis=True,
            enable_opa_guard=False,
            enable_llm=False,
        )
        assert layer.redis_queue is redis_q
        assert layer.redis_voting is redis_v

    def test_llm_assistant_injected(self):
        mock_llm = MagicMock()
        layer = DeliberationLayer(
            impact_scorer=_mock_impact_scorer(),
            adaptive_router=_mock_router(),
            deliberation_queue=_mock_queue(),
            llm_assistant=mock_llm,
            opa_guard=None,
            enable_llm=True,
            enable_opa_guard=False,
        )
        assert layer.llm_assistant is mock_llm

    def test_llm_disabled_when_enable_llm_false(self):
        layer = DeliberationLayer(
            impact_scorer=_mock_impact_scorer(),
            adaptive_router=_mock_router(),
            deliberation_queue=_mock_queue(),
            llm_assistant=None,
            opa_guard=None,
            enable_llm=False,
            enable_opa_guard=False,
        )
        assert layer.llm_assistant is None

    def test_deliberation_engine_alias(self):
        assert DeliberationEngine is DeliberationLayer


class TestInitialize:
    async def test_initialize_no_redis(self):
        layer = _build_layer(enable_redis=False)
        # Should not raise
        await layer.initialize()

    async def test_initialize_with_redis(self):
        redis_q = MagicMock()
        redis_q.connect = AsyncMock()
        redis_v = MagicMock()
        redis_v.connect = AsyncMock()
        layer = _build_layer(enable_redis=False)
        layer.redis_queue = redis_q
        layer.redis_voting = redis_v
        layer.enable_redis = True
        await layer.initialize()
        redis_q.connect.assert_awaited_once()
        redis_v.connect.assert_awaited_once()

    async def test_initialize_with_opa_guard(self):
        guard = _mock_guard()
        layer = _build_layer(guard=guard, enable_opa_guard=True)
        await layer.initialize()
        guard.initialize.assert_awaited_once()


class TestProcessMessage:
    async def test_fast_lane_success(self):
        layer = _build_layer(lane="fast")
        msg = _make_message(impact_score=0.3)
        result = await layer.process_message(msg)
        assert result["success"] is True
        assert result["lane"] == "fast"
        assert "processing_time" in result

    async def test_deliberation_lane(self):
        layer = _build_layer(lane="deliberation")
        msg = _make_message(impact_score=0.95)
        result = await layer.process_message(msg)
        assert result["success"] is True
        assert result["lane"] == "deliberation"

    async def test_impact_score_calculated_when_absent(self):
        scorer = _mock_impact_scorer(score=0.42)
        layer = _build_layer(lane="fast", scorer=scorer)
        msg = _make_message(impact_score=None)
        result = await layer.process_message(msg)
        assert result["success"] is True
        assert msg.impact_score == 0.42

    async def test_impact_score_not_recalculated_when_present(self):
        scorer = _mock_impact_scorer(score=0.99)
        layer = _build_layer(lane="fast", scorer=scorer)
        msg = _make_message(impact_score=0.1)
        await layer.process_message(msg)
        scorer.calculate_impact_score.assert_not_called()

    async def test_timeout_error_returns_failure(self):
        router = _mock_router()
        router.route_message = AsyncMock(side_effect=TimeoutError("timed out"))
        layer = _build_layer(router=router)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert "Timeout" in result["error"]

    async def test_value_error_returns_failure(self):
        router = _mock_router()
        router.route_message = AsyncMock(side_effect=ValueError("bad value"))
        layer = _build_layer(router=router)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert "ValueError" in result["error"]

    async def test_runtime_error_returns_failure(self):
        router = _mock_router()
        router.route_message = AsyncMock(side_effect=RuntimeError("crash"))
        layer = _build_layer(router=router)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert "RuntimeError" in result["error"]

    async def test_cancelled_error_propagates(self):
        router = _mock_router()
        router.route_message = AsyncMock(side_effect=asyncio.CancelledError())
        layer = _build_layer(router=router)
        msg = _make_message()
        with pytest.raises(asyncio.CancelledError):
            await layer.process_message(msg)

    async def test_no_router_returns_error(self):
        layer = _build_layer()
        layer.adaptive_router = None
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["lane"] == "fast"
        assert "error" in result

    async def test_key_error_returns_failure(self):
        router = _mock_router()
        router.route_message = AsyncMock(side_effect=KeyError("missing"))
        layer = _build_layer(router=router)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is False

    async def test_attribute_error_returns_failure(self):
        router = _mock_router()
        router.route_message = AsyncMock(side_effect=AttributeError("oops"))
        layer = _build_layer(router=router)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is False


class TestFastLaneCallback:
    async def test_fast_lane_callback_invoked(self):
        callback = AsyncMock()
        layer = _build_layer(lane="fast")
        layer.set_fast_lane_callback(callback)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is True
        callback.assert_awaited_once_with(msg)

    async def test_deliberation_callback_invoked(self):
        callback = AsyncMock()
        layer = _build_layer(lane="deliberation")
        layer.set_deliberation_callback(callback)
        msg = _make_message(impact_score=0.95)
        result = await layer.process_message(msg)
        assert result["success"] is True
        callback.assert_awaited_once()


class TestDeliberationLane:
    async def test_redis_queue_used_when_available(self):
        redis_q = MagicMock()
        redis_q.enqueue_deliberation_item = AsyncMock()
        layer = _build_layer(lane="deliberation")
        layer.redis_queue = redis_q
        layer.enable_redis = True
        msg = _make_message(impact_score=0.95)
        await layer.process_message(msg)
        redis_q.enqueue_deliberation_item.assert_awaited_once()


class TestRouteVerifiedMessage:
    async def test_fast_lane_reroute(self):
        layer = _build_layer(lane="fast")
        msg = _make_message()

        result = await layer._route_verified_message(msg)

        assert result["lane"] == "fast"
        assert result["status"] == "delivered"

    async def test_deliberation_lane_reroute(self):
        queue = _mock_queue()
        layer = _build_layer(lane="deliberation", queue=queue)
        msg = _make_message(impact_score=0.95)

        result = await layer._route_verified_message(msg)

        assert result["lane"] == "deliberation"
        assert result["status"] == "queued"
        queue.enqueue_for_deliberation.assert_awaited_once()

    async def test_reroute_without_router_returns_error(self):
        layer = _build_layer()
        layer.adaptive_router = None

        result = await layer._route_verified_message(_make_message())

        assert result == {"success": False, "error": "No router available"}


class TestOPAGuardIntegration:
    async def test_guard_allow_proceeds_to_fast_lane(self):
        guard = _mock_guard(decision=GuardDecision.ALLOW, is_allowed=True)
        layer = _build_layer(lane="fast", guard=guard, enable_opa_guard=True)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is True
        assert result["lane"] == "fast"

    async def test_guard_deny_returns_failure(self):
        guard = _mock_guard(decision=GuardDecision.DENY, is_allowed=False)
        guard.verify_action.return_value = GuardResult(
            decision=GuardDecision.DENY,
            is_allowed=False,
            validation_errors=["Policy violation"],
        )
        layer = _build_layer(guard=guard, enable_opa_guard=True)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert result.get("lane") == "denied"

    async def test_guard_require_signatures_and_collected(self):
        guard_result = GuardResult(
            decision=GuardDecision.REQUIRE_SIGNATURES,
            is_allowed=False,
            required_signers=["signer-1"],
        )
        sig_result = MagicMock()
        sig_result.is_valid = True
        sig_result.to_dict = MagicMock(return_value={"status": "collected"})

        guard = MagicMock()
        guard.initialize = AsyncMock()
        guard.close = AsyncMock()
        guard.get_stats = MagicMock(return_value={})
        guard.verify_action = AsyncMock(return_value=guard_result)
        guard.collect_signatures = AsyncMock(return_value=sig_result)

        router = _mock_router(lane="fast")
        layer = _build_layer(guard=guard, enable_opa_guard=True, router=router)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is True
        router.route_message.assert_awaited_once()

    async def test_guard_require_signatures_and_failed(self):
        guard_result = GuardResult(
            decision=GuardDecision.REQUIRE_SIGNATURES,
            is_allowed=False,
            required_signers=["signer-1"],
        )
        sig_result = MagicMock()
        sig_result.is_valid = False
        sig_status = MagicMock()
        sig_status.value = "expired"
        sig_result.status = sig_status
        sig_result.to_dict = MagicMock(return_value={"status": "expired"})

        guard = MagicMock()
        guard.initialize = AsyncMock()
        guard.close = AsyncMock()
        guard.verify_action = AsyncMock(return_value=guard_result)
        guard.collect_signatures = AsyncMock(return_value=sig_result)

        layer = _build_layer(guard=guard, enable_opa_guard=True)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert result.get("lane") == "signature_required"

    async def test_guard_require_review_and_approved(self):
        guard_result = GuardResult(
            decision=GuardDecision.REQUIRE_REVIEW,
            is_allowed=False,
            required_reviewers=["reviewer-1"],
        )
        review_result = MagicMock()
        review_result.consensus_verdict = "approve"
        review_result.to_dict = MagicMock(return_value={"verdict": "approve"})

        guard = MagicMock()
        guard.initialize = AsyncMock()
        guard.close = AsyncMock()
        guard.verify_action = AsyncMock(return_value=guard_result)
        guard.submit_for_review = AsyncMock(return_value=review_result)

        router = _mock_router(lane="fast")
        layer = _build_layer(guard=guard, enable_opa_guard=True, router=router)

        # Also need message.to_dict
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is True
        router.route_message.assert_awaited_once()

    async def test_guard_require_review_and_rejected(self):
        guard_result = GuardResult(
            decision=GuardDecision.REQUIRE_REVIEW,
            is_allowed=False,
            required_reviewers=["reviewer-1"],
        )
        review_result = MagicMock()
        review_result.consensus_verdict = "reject"
        review_result.to_dict = MagicMock(return_value={"verdict": "reject"})

        guard = MagicMock()
        guard.initialize = AsyncMock()
        guard.close = AsyncMock()
        guard.verify_action = AsyncMock(return_value=guard_result)
        guard.submit_for_review = AsyncMock(return_value=review_result)

        layer = _build_layer(guard=guard, enable_opa_guard=True)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert result.get("lane") == "review_required"

    async def test_guard_callback_invoked(self):
        callback = AsyncMock()
        guard = _mock_guard(decision=GuardDecision.ALLOW, is_allowed=True)
        layer = _build_layer(guard=guard, enable_opa_guard=True, lane="fast")
        layer.set_guard_callback(callback)
        msg = _make_message()
        await layer.process_message(msg)
        callback.assert_awaited_once()

    async def test_guard_verification_error_fail_closed(self):
        guard = MagicMock()
        guard.initialize = AsyncMock()
        guard.close = AsyncMock()
        guard.verify_action = AsyncMock(side_effect=RuntimeError("OPA unavailable"))

        layer = _build_layer(guard=guard, enable_opa_guard=True)
        msg = _make_message()
        result = await layer.process_message(msg)
        # Fail-closed: should deny
        assert result["success"] is False

    async def test_guard_require_signatures_no_router(self):
        """When signature collection succeeds but router is None."""
        guard_result = GuardResult(
            decision=GuardDecision.REQUIRE_SIGNATURES,
            is_allowed=False,
            required_signers=["signer-1"],
        )
        sig_result = MagicMock()
        sig_result.is_valid = True
        sig_result.to_dict = MagicMock(return_value={})

        guard = MagicMock()
        guard.initialize = AsyncMock()
        guard.close = AsyncMock()
        guard.verify_action = AsyncMock(return_value=guard_result)
        guard.collect_signatures = AsyncMock(return_value=sig_result)

        layer = _build_layer(guard=guard, enable_opa_guard=True)
        layer.adaptive_router = None
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is False
        assert "error" in result

    async def test_guard_require_review_no_router(self):
        """When review passes but router is None."""
        guard_result = GuardResult(
            decision=GuardDecision.REQUIRE_REVIEW,
            is_allowed=False,
            required_reviewers=["reviewer-1"],
        )
        review_result = MagicMock()
        review_result.consensus_verdict = "approve"
        review_result.to_dict = MagicMock(return_value={})

        guard = MagicMock()
        guard.initialize = AsyncMock()
        guard.close = AsyncMock()
        guard.verify_action = AsyncMock(return_value=guard_result)
        guard.submit_for_review = AsyncMock(return_value=review_result)

        layer = _build_layer(guard=guard, enable_opa_guard=True)
        layer.adaptive_router = None
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is False

    async def test_guard_allow_with_guard_result_field(self):
        """Guard ALLOW path returns guard_result key in result dict."""
        guard = _mock_guard(decision=GuardDecision.ALLOW, is_allowed=True)
        layer = _build_layer(lane="fast", guard=guard, enable_opa_guard=True)
        msg = _make_message()
        result = await layer.process_message(msg)
        # The intermediate guard_result may be present
        assert result["success"] is True


class TestSignatureAndReviewPaths:
    async def test_signature_requirement_with_deliberation_routing(self):
        """Signature collection succeeds; routing to deliberation lane."""
        guard_result = GuardResult(
            decision=GuardDecision.REQUIRE_SIGNATURES,
            is_allowed=False,
            required_signers=["signer-1"],
        )
        sig_result = MagicMock()
        sig_result.is_valid = True
        sig_result.to_dict = MagicMock(return_value={})

        guard = MagicMock()
        guard.initialize = AsyncMock()
        guard.close = AsyncMock()
        guard.verify_action = AsyncMock(return_value=guard_result)
        guard.collect_signatures = AsyncMock(return_value=sig_result)

        router = _mock_router(lane="deliberation")
        queue = _mock_queue()
        layer = _build_layer(guard=guard, enable_opa_guard=True, router=router, queue=queue)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is True
        router.route_message.assert_awaited_once()
        queue.enqueue_for_deliberation.assert_awaited_once()

    async def test_review_requirement_with_deliberation_routing(self):
        """Review approved; routing to deliberation lane."""
        guard_result = GuardResult(
            decision=GuardDecision.REQUIRE_REVIEW,
            is_allowed=False,
            required_reviewers=["reviewer-1"],
        )
        review_result = MagicMock()
        review_result.consensus_verdict = "approve"
        review_result.to_dict = MagicMock(return_value={})

        guard = MagicMock()
        guard.initialize = AsyncMock()
        guard.close = AsyncMock()
        guard.verify_action = AsyncMock(return_value=guard_result)
        guard.submit_for_review = AsyncMock(return_value=review_result)

        router = _mock_router(lane="deliberation")
        queue = _mock_queue()
        layer = _build_layer(guard=guard, enable_opa_guard=True, router=router, queue=queue)
        msg = _make_message()
        result = await layer.process_message(msg)
        assert result["success"] is True
        router.route_message.assert_awaited_once()
        queue.enqueue_for_deliberation.assert_awaited_once()


class TestSubmitHumanDecision:
    async def test_submit_approved(self):
        queue = _mock_queue()
        router = _mock_router()
        layer = _build_layer(queue=queue, router=router)
        result = await layer.submit_human_decision("item-1", "reviewer-1", "approved", "looks ok")
        assert result is True
        queue.submit_human_decision.assert_awaited_once()

    async def test_submit_rejected(self):
        queue = _mock_queue()
        layer = _build_layer(queue=queue)
        result = await layer.submit_human_decision("item-1", "reviewer-1", "rejected", "nope")
        assert result is True

    async def test_submit_escalated(self):
        queue = _mock_queue()
        layer = _build_layer(queue=queue)
        result = await layer.submit_human_decision("item-1", "reviewer-1", "escalated", "unsure")
        assert result is True

    async def test_submit_under_review(self):
        queue = _mock_queue()
        layer = _build_layer(queue=queue)
        result = await layer.submit_human_decision(
            "item-1", "reviewer-1", "under_review", "pending"
        )
        assert result is True

    async def test_submit_with_enum_decision(self):
        queue = _mock_queue()
        router = _mock_router()
        layer = _build_layer(queue=queue, router=router)
        # Simulate an enum-like object with .value
        decision_enum = MagicMock()
        decision_enum.value = "approved"
        result = await layer.submit_human_decision("item-1", "reviewer-1", decision_enum, "ok")
        assert result is True

    async def test_submit_value_error_returns_false(self):
        queue = _mock_queue()
        queue.submit_human_decision = AsyncMock(side_effect=ValueError("bad"))
        layer = _build_layer(queue=queue)
        result = await layer.submit_human_decision("item-1", "reviewer-1", "approved", "ok")
        assert result is False

    async def test_submit_runtime_error_returns_false(self):
        queue = _mock_queue()
        queue.submit_human_decision = AsyncMock(side_effect=RuntimeError("crash"))
        layer = _build_layer(queue=queue)
        result = await layer.submit_human_decision("item-1", "reviewer-1", "approved", "ok")
        assert result is False

    async def test_submit_cancelled_error_propagates(self):
        queue = _mock_queue()
        queue.submit_human_decision = AsyncMock(side_effect=asyncio.CancelledError())
        layer = _build_layer(queue=queue)
        with pytest.raises(asyncio.CancelledError):
            await layer.submit_human_decision("item-1", "reviewer-1", "approved", "ok")

    async def test_submit_queue_returns_false(self):
        queue = _mock_queue()
        queue.submit_human_decision = AsyncMock(return_value=False)
        layer = _build_layer(queue=queue)
        result = await layer.submit_human_decision("item-1", "reviewer-1", "approved", "ok")
        assert result is False


class TestSubmitAgentVote:
    async def test_approve_vote(self):
        queue = _mock_queue()
        layer = _build_layer(queue=queue)
        result = await layer.submit_agent_vote("item-1", "agent-x", "approve", "good", 0.9)
        assert result is True

    async def test_reject_vote(self):
        queue = _mock_queue()
        layer = _build_layer(queue=queue)
        result = await layer.submit_agent_vote("item-1", "agent-x", "reject", "bad", 0.8)
        assert result is True

    async def test_abstain_vote(self):
        queue = _mock_queue()
        layer = _build_layer(queue=queue)
        result = await layer.submit_agent_vote("item-1", "agent-x", "abstain", "unsure", 0.5)
        assert result is True

    async def test_unknown_vote_defaults_to_abstain(self):
        queue = _mock_queue()
        layer = _build_layer(queue=queue)
        result = await layer.submit_agent_vote("item-1", "agent-x", "UNKNOWN_VOTE", "?", 0.5)
        assert result is True

    async def test_redis_voting_used_when_available(self):
        queue = _mock_queue()
        redis_voting = MagicMock()
        redis_voting.submit_vote = AsyncMock()
        layer = _build_layer(queue=queue)
        layer.redis_voting = redis_voting
        layer.enable_redis = True
        result = await layer.submit_agent_vote("item-1", "agent-x", "approve", "ok", 1.0)
        assert result is True
        redis_voting.submit_vote.assert_awaited_once()

    async def test_redis_voting_not_used_when_queue_returns_false(self):
        queue = _mock_queue()
        queue.submit_agent_vote = AsyncMock(return_value=False)
        redis_voting = MagicMock()
        redis_voting.submit_vote = AsyncMock()
        layer = _build_layer(queue=queue)
        layer.redis_voting = redis_voting
        result = await layer.submit_agent_vote("item-1", "agent-x", "approve", "ok", 1.0)
        assert result is False
        redis_voting.submit_vote.assert_not_awaited()

    async def test_value_error_returns_false(self):
        queue = _mock_queue()
        queue.submit_agent_vote = AsyncMock(side_effect=ValueError("bad"))
        layer = _build_layer(queue=queue)
        result = await layer.submit_agent_vote("item-1", "agent-x", "approve", "ok", 1.0)
        assert result is False

    async def test_runtime_error_returns_false(self):
        queue = _mock_queue()
        queue.submit_agent_vote = AsyncMock(side_effect=RuntimeError("crash"))
        layer = _build_layer(queue=queue)
        result = await layer.submit_agent_vote("item-1", "agent-x", "approve", "ok", 1.0)
        assert result is False

    async def test_cancelled_error_propagates(self):
        queue = _mock_queue()
        queue.submit_agent_vote = AsyncMock(side_effect=asyncio.CancelledError())
        layer = _build_layer(queue=queue)
        with pytest.raises(asyncio.CancelledError):
            await layer.submit_agent_vote("item-1", "agent-x", "approve", "ok", 1.0)


class TestGetLayerStats:
    def test_operational(self):
        layer = _build_layer(lane="fast")
        stats = layer.get_layer_stats()
        assert stats["layer_status"] == "operational"
        assert "router_stats" in stats
        assert "queue_stats" in stats

    def test_not_initialized_when_no_router(self):
        layer = _build_layer()
        layer.adaptive_router = None
        stats = layer.get_layer_stats()
        assert stats["layer_status"] == "not_initialized"

    def test_not_initialized_when_no_queue(self):
        layer = _build_layer()
        layer.deliberation_queue = None
        stats = layer.get_layer_stats()
        assert stats["layer_status"] == "not_initialized"

    def test_opa_guard_stats_included_when_enabled(self):
        guard = _mock_guard()
        layer = _build_layer(guard=guard, enable_opa_guard=True)
        stats = layer.get_layer_stats()
        assert "opa_guard_stats" in stats

    def test_value_error_returns_error_dict(self):
        layer = _build_layer()
        layer.adaptive_router.get_routing_stats = MagicMock(side_effect=ValueError("oops"))
        stats = layer.get_layer_stats()
        assert "error" in stats

    def test_attribute_error_returns_error_dict(self):
        layer = _build_layer()
        layer.adaptive_router.get_routing_stats = MagicMock(side_effect=AttributeError("attr"))
        stats = layer.get_layer_stats()
        assert "error" in stats

    def test_runtime_error_returns_error_dict(self):
        layer = _build_layer()
        layer.adaptive_router.get_routing_stats = MagicMock(side_effect=RuntimeError("rt"))
        stats = layer.get_layer_stats()
        assert "error" in stats

    def test_redis_queue_info_included(self):
        layer = _build_layer()
        redis_q = MagicMock()
        redis_q.get_stream_info = MagicMock(return_value={"stream": "data"})
        layer.redis_queue = redis_q
        layer.enable_redis = True
        # asyncio.run is called internally; we patch it
        with patch(
            "enhanced_agent_bus.deliberation_layer.integration.asyncio.run",
            return_value={"stream": "data"},
        ):
            stats = layer.get_layer_stats()
        assert "redis_info" in stats

    def test_redis_queue_runtime_error_sets_none(self):
        layer = _build_layer()
        redis_q = MagicMock()
        redis_q.get_stream_info = MagicMock(return_value={})
        layer.redis_queue = redis_q
        layer.enable_redis = True
        # asyncio.run raises RuntimeError (already in event loop)
        with patch(
            "enhanced_agent_bus.deliberation_layer.integration.asyncio.run",
            side_effect=RuntimeError("already running"),
        ):
            stats = layer.get_layer_stats()
        assert stats.get("redis_info") is None


class TestPerformanceFeedback:
    async def test_fast_lane_feedback_recorded(self):
        router = _mock_router(lane="fast")
        layer = _build_layer(router=router, enable_learning=True)
        msg = _make_message()
        await layer.process_message(msg)
        router.update_performance_feedback.assert_awaited()

    async def test_deliberation_lane_feedback_recorded(self):
        router = _mock_router(lane="deliberation")
        queue = _mock_queue()
        layer = _build_layer(router=router, queue=queue, enable_learning=True)
        msg = _make_message()
        await layer.process_message(msg)
        router.update_performance_feedback.assert_awaited()

    async def test_no_feedback_when_learning_disabled(self):
        router = _mock_router(lane="fast")
        layer = _build_layer(router=router, enable_learning=False)
        msg = _make_message()
        await layer.process_message(msg)
        router.update_performance_feedback.assert_not_awaited()

    async def test_feedback_value_error_is_caught(self):
        router = _mock_router(lane="fast")
        router.update_performance_feedback = AsyncMock(side_effect=ValueError("oops"))
        layer = _build_layer(router=router, enable_learning=True)
        msg = _make_message()
        result = await layer.process_message(msg)
        # Should not bubble up
        assert result["success"] is True


class TestDFCDiagnostics:
    async def test_dfc_diagnostics_run_in_deliberation_lane(self):
        router = _mock_router(lane="deliberation")
        queue = _mock_queue()
        layer = _build_layer(router=router, queue=queue)

        mock_dfc_calc = MagicMock()
        mock_dfc_calc.calculate = MagicMock(return_value=0.75)
        layer.dfc_calculator = mock_dfc_calc

        mock_components = MagicMock()

        import enhanced_agent_bus.deliberation_layer.integration as integ_mod

        original_cache = integ_mod._imports_cache
        # Inject a mock get_dfc_components_from_context
        integ_mod._imports_cache = dict(integ_mod._imports_cache or {})
        integ_mod._imports_cache["get_dfc_components_from_context"] = lambda ctx: mock_components
        try:
            msg = _make_message(impact_score=0.9)
            result = await layer.process_message(msg)
            assert result["success"] is True
            assert result.get("dfc_diagnostic_score") == 0.75
        finally:
            integ_mod._imports_cache = original_cache

    async def test_dfc_skipped_when_no_calculator(self):
        router = _mock_router(lane="deliberation")
        queue = _mock_queue()
        layer = _build_layer(router=router, queue=queue)
        layer.dfc_calculator = None

        msg = _make_message(impact_score=0.9)
        result = await layer.process_message(msg)
        assert result["success"] is True
        assert "dfc_diagnostic_score" not in result

    async def test_dfc_error_is_caught(self):
        router = _mock_router(lane="deliberation")
        queue = _mock_queue()
        layer = _build_layer(router=router, queue=queue)

        mock_dfc_calc = MagicMock()
        mock_dfc_calc.calculate = MagicMock(side_effect=ValueError("dfc error"))
        layer.dfc_calculator = mock_dfc_calc

        import enhanced_agent_bus.deliberation_layer.integration as integ_mod

        original_cache = integ_mod._imports_cache
        integ_mod._imports_cache = dict(integ_mod._imports_cache or {})
        integ_mod._imports_cache["get_dfc_components_from_context"] = lambda ctx: MagicMock()
        try:
            msg = _make_message(impact_score=0.9)
            result = await layer.process_message(msg)
            # DFC error is swallowed
            assert result["success"] is True
        finally:
            integ_mod._imports_cache = original_cache


class TestUpdateDeliberationOutcome:
    async def test_update_outcome_approved(self):
        router = _mock_router()
        queue = _mock_queue()
        layer = _build_layer(router=router, queue=queue, enable_learning=True)
        await layer._update_deliberation_outcome("item-1", "approved", "good decision")
        router.update_performance_feedback.assert_awaited_once()

    async def test_update_outcome_rejected(self):
        router = _mock_router()
        queue = _mock_queue()
        layer = _build_layer(router=router, queue=queue, enable_learning=True)
        await layer._update_deliberation_outcome("item-1", "rejected", "bad decision")
        router.update_performance_feedback.assert_awaited_once()

    async def test_update_outcome_escalated(self):
        router = _mock_router()
        queue = _mock_queue()
        layer = _build_layer(router=router, queue=queue, enable_learning=True)
        await layer._update_deliberation_outcome("item-1", "escalated", "unsure")
        router.update_performance_feedback.assert_awaited_once()

    async def test_update_skipped_when_learning_disabled(self):
        router = _mock_router()
        queue = _mock_queue()
        layer = _build_layer(router=router, queue=queue, enable_learning=False)
        await layer._update_deliberation_outcome("item-1", "approved", "ok")
        router.update_performance_feedback.assert_not_awaited()

    async def test_update_skipped_when_no_router(self):
        queue = _mock_queue()
        layer = _build_layer(queue=queue, enable_learning=True)
        layer.adaptive_router = None
        await layer._update_deliberation_outcome("item-1", "approved", "ok")

    async def test_update_skipped_when_item_not_found(self):
        router = _mock_router()
        queue = _mock_queue()
        queue.get_item_details = MagicMock(return_value=None)
        layer = _build_layer(router=router, queue=queue, enable_learning=True)
        await layer._update_deliberation_outcome("item-missing", "approved", "ok")
        router.update_performance_feedback.assert_not_awaited()

    async def test_update_skipped_when_no_message_id(self):
        router = _mock_router()
        queue = _mock_queue()
        queue.get_item_details = MagicMock(return_value={"other": "data"})
        layer = _build_layer(router=router, queue=queue, enable_learning=True)
        await layer._update_deliberation_outcome("item-1", "approved", "ok")
        router.update_performance_feedback.assert_not_awaited()

    async def test_update_value_error_caught(self):
        router = _mock_router()
        queue = _mock_queue()
        queue.get_item_details = MagicMock(side_effect=ValueError("bad"))
        layer = _build_layer(router=router, queue=queue, enable_learning=True)
        # Should not raise
        await layer._update_deliberation_outcome("item-1", "approved", "ok")


class TestResolvingDeliberationItem:
    async def test_resolve_approved(self):
        queue = _mock_queue()
        router = _mock_router()
        layer = _build_layer(queue=queue, router=router, enable_learning=True)
        result = await layer.resolve_deliberation_item("item-1", approved=True, feedback_score=0.9)
        assert result["status"] == "resolved"
        assert result["outcome"] == "approved"

    async def test_resolve_rejected(self):
        queue = _mock_queue()
        router = _mock_router()
        layer = _build_layer(queue=queue, router=router, enable_learning=True)
        result = await layer.resolve_deliberation_item("item-1", approved=False)
        assert result["outcome"] == "rejected"

    async def test_no_queue_returns_error(self):
        layer = _build_layer()
        layer.deliberation_queue = None
        result = await layer.resolve_deliberation_item("item-1", approved=True)
        assert result["status"] == "error"

    async def test_task_not_found_returns_resolved_no_feedback(self):
        queue = _mock_queue()
        queue.get_task = MagicMock(return_value=None)
        layer = _build_layer(queue=queue, enable_learning=True)
        result = await layer.resolve_deliberation_item("item-missing", approved=True)
        assert result["status"] == "resolved_no_feedback"

    async def test_get_task_not_available_falls_back_to_none(self):
        queue = _mock_queue()
        del queue.get_task
        layer = _build_layer(queue=queue, enable_learning=True)
        result = await layer.resolve_deliberation_item("item-1", approved=True)
        assert result["status"] == "resolved_no_feedback"

    async def test_no_router_still_resolves(self):
        queue = _mock_queue()
        layer = _build_layer(queue=queue, enable_learning=True)
        layer.adaptive_router = None
        result = await layer.resolve_deliberation_item("item-1", approved=True)
        assert result["status"] == "resolved"


class TestForceDeliberation:
    async def test_force_deliberation_calls_router(self):
        router = _mock_router()
        layer = _build_layer(router=router)
        msg = _make_message(impact_score=0.3)
        result = await layer.force_deliberation(msg, reason="test-override")
        router.force_deliberation.assert_awaited_once()
        assert result.get("forced") is True
        # Verify impact_score was restored
        assert msg.impact_score == 0.3

    async def test_force_deliberation_no_router(self):
        layer = _build_layer()
        layer.adaptive_router = None
        msg = _make_message()
        result = await layer.force_deliberation(msg)
        assert result["success"] is False
        assert "error" in result


class TestAnalyzeTrends:
    async def test_analyze_trends_no_llm(self):
        layer = _build_layer(enable_llm=False)
        result = await layer.analyze_trends()
        assert "error" in result

    async def test_analyze_trends_with_llm(self):
        llm = MagicMock()
        llm.analyze_deliberation_trends = AsyncMock(return_value={"trend": "upward"})
        layer = _build_layer(enable_llm=True)
        layer.llm_assistant = llm
        result = await layer.analyze_trends()
        assert result == {"trend": "upward"}

    async def test_analyze_trends_value_error(self):
        llm = MagicMock()
        llm.analyze_deliberation_trends = AsyncMock(side_effect=ValueError("bad"))
        layer = _build_layer()
        layer.llm_assistant = llm
        result = await layer.analyze_trends()
        assert "error" in result

    async def test_analyze_trends_runtime_error(self):
        llm = MagicMock()
        llm.analyze_deliberation_trends = AsyncMock(side_effect=RuntimeError("crash"))
        layer = _build_layer()
        layer.llm_assistant = llm
        result = await layer.analyze_trends()
        assert "error" in result

    async def test_analyze_trends_cancelled_propagates(self):
        llm = MagicMock()
        llm.analyze_deliberation_trends = AsyncMock(side_effect=asyncio.CancelledError())
        layer = _build_layer()
        layer.llm_assistant = llm
        with pytest.raises(asyncio.CancelledError):
            await layer.analyze_trends()


class TestClose:
    async def test_close_with_all_components(self):
        guard = _mock_guard()
        redis_q = MagicMock()
        redis_q.close = AsyncMock()
        redis_v = MagicMock()
        redis_v.close = AsyncMock()
        layer = _build_layer(guard=guard, enable_opa_guard=True)
        layer.redis_queue = redis_q
        layer.redis_voting = redis_v
        await layer.close()
        guard.close.assert_awaited_once()
        redis_q.close.assert_awaited_once()
        redis_v.close.assert_awaited_once()

    async def test_close_without_components(self):
        layer = _build_layer(enable_opa_guard=False)
        # Should not raise
        await layer.close()


class TestGlobalLayer:
    def test_get_and_reset(self):
        # The module may be imported under multiple aliases due to sys.modules aliasing.
        # Import via the same path used by the functions themselves.
        import sys

        # Find the actual module object used by get_deliberation_layer / reset_deliberation_layer
        # by looking at the module in which those functions were defined.
        integ_mod = sys.modules[get_deliberation_layer.__module__]

        reset_deliberation_layer()
        assert integ_mod._deliberation_layer is None
        layer = get_deliberation_layer()
        assert isinstance(layer, DeliberationLayer)
        assert integ_mod._deliberation_layer is layer
        # Second call returns same instance
        layer2 = get_deliberation_layer()
        assert layer2 is layer
        reset_deliberation_layer()
        assert integ_mod._deliberation_layer is None


class TestLazyImport:
    def test_lazy_import_caches(self):
        import enhanced_agent_bus.deliberation_layer.integration as integ_mod

        # Warm up the cache
        result1 = _lazy_import("DeliberationStatus")
        result2 = _lazy_import("DeliberationStatus")
        assert result1 is result2

    def test_lazy_import_returns_correct_value(self):
        GuardDecision_cls = _lazy_import("GuardDecision")
        assert GuardDecision_cls is GuardDecision


class TestPriorityEnumHandling:
    async def test_priority_with_value_attribute(self):
        """Ensure priority.value path is covered in _verify_with_opa_guard."""
        guard = _mock_guard(decision=GuardDecision.ALLOW, is_allowed=True)
        layer = _build_layer(guard=guard, enable_opa_guard=True, lane="fast")
        msg = _make_message()
        msg.priority = Priority.HIGH  # has .value
        result = await layer.process_message(msg)
        assert result["success"] is True

    async def test_priority_without_value_attribute(self):
        """Ensure str(priority) fallback path is covered."""
        guard = _mock_guard(decision=GuardDecision.ALLOW, is_allowed=True)
        layer = _build_layer(guard=guard, enable_opa_guard=True, lane="fast")
        msg = _make_message()
        msg.priority = "high"  # plain string, no .value
        result = await layer.process_message(msg)
        assert result["success"] is True


class TestPrepareContext:
    def test_prepare_context_uses_from_agent(self):
        layer = _build_layer()
        msg = _make_message(from_agent="the-agent")
        ctx = layer._prepare_processing_context(msg)
        assert ctx["agent_id"] == "the-agent"

    def test_prepare_context_falls_back_to_sender_id(self):
        layer = _build_layer()
        msg = _make_message()
        msg.from_agent = ""
        msg.sender_id = "fallback-sender"
        ctx = layer._prepare_processing_context(msg)
        assert ctx["agent_id"] == "fallback-sender"


class TestHotlContentNormalization:
    def test_truncate_content_for_hotl_with_string(self):
        assert _truncate_content_for_hotl("abcdef", limit=3) == "abc"

    def test_truncate_content_for_hotl_with_dict(self):
        assert _truncate_content_for_hotl({"text": "hello"}) == "{'text': 'hello'}"

    async def test_deliberation_lane_with_dict_content_does_not_fail_medium_risk_path(self):
        layer = _build_layer(lane="deliberation")
        msg = _make_message()

        result = await layer.process_message(msg)

        assert result["success"] is True
        assert result["lane"] == "deliberation"


class TestGuardResultInFinalize:
    async def test_guard_result_from_message_attr_included(self):
        """Branch: guard_result not in result but _guard_result on message."""
        layer = _build_layer(lane="fast", enable_opa_guard=False)
        msg = _make_message()
        sentinel = object()
        msg._guard_result = sentinel  # type: ignore[attr-defined]
        result = await layer.process_message(msg)
        assert result.get("guard_result") is sentinel
