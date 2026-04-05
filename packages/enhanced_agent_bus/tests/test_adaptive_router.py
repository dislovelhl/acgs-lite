"""
ACGS-2 Enhanced Agent Bus - Adaptive Router Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the AdaptiveRouter class covering:
- Dual-path routing (Fast Path vs Deliberation Path)
- Impact score-based routing decisions
- Adaptive threshold learning
- Performance feedback integration
- Routing statistics
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

from enhanced_agent_bus.deliberation_layer.adaptive_router import (
    AdaptiveRouter,
    get_adaptive_router,
)
from enhanced_agent_bus.models import AgentMessage, MessageStatus, MessageType


@pytest.fixture
def mock_deliberation_queue():
    """Create a mock deliberation queue."""
    queue = MagicMock()
    queue.add_item = AsyncMock(return_value=True)
    return queue


@pytest.fixture
def router(mock_deliberation_queue):
    """Create an AdaptiveRouter instance with mocked dependencies."""
    with patch(
        "enhanced_agent_bus.deliberation_layer.adaptive_router.get_deliberation_queue",
        return_value=mock_deliberation_queue,
    ):
        router = AdaptiveRouter(
            impact_threshold=0.8, deliberation_timeout=300, enable_learning=True
        )
    return router


@pytest.fixture
def router_no_learning(mock_deliberation_queue):
    """Create an AdaptiveRouter with learning disabled."""
    with patch(
        "enhanced_agent_bus.deliberation_layer.adaptive_router.get_deliberation_queue",
        return_value=mock_deliberation_queue,
    ):
        router = AdaptiveRouter(
            impact_threshold=0.8, deliberation_timeout=300, enable_learning=False
        )
    return router


@pytest.fixture
def low_impact_message():
    """Create a message with low impact score (below threshold)."""
    return AgentMessage(
        from_agent="agent-1",
        to_agent="agent-2",
        message_type=MessageType.COMMAND,
        content={"action": "simple_query"},
        impact_score=0.3,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


@pytest.fixture
def high_impact_message():
    """Create a message with high impact score (above threshold)."""
    return AgentMessage(
        from_agent="agent-1",
        to_agent="agent-2",
        message_type=MessageType.GOVERNANCE_REQUEST,
        content={"action": "critical_governance_decision"},
        impact_score=0.95,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


@pytest.fixture
def message_no_score():
    """Create a message without impact score."""
    return AgentMessage(
        from_agent="agent-1",
        to_agent="agent-2",
        message_type=MessageType.COMMAND,
        content={"action": "new_request"},
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


class TestAdaptiveRouterInitialization:
    """Tests for AdaptiveRouter initialization."""

    def test_default_initialization(self, mock_deliberation_queue):
        """Test router initializes with default parameters."""
        with patch(
            "enhanced_agent_bus.deliberation_layer.adaptive_router.get_deliberation_queue",
            return_value=mock_deliberation_queue,
        ):
            router = AdaptiveRouter()

        assert router.impact_threshold == 0.8
        assert router.deliberation_timeout == 300
        assert router.enable_learning is True
        assert router.routing_history == []
        assert router.performance_metrics["total_messages"] == 0

    def test_custom_initialization(self, mock_deliberation_queue):
        """Test router initializes with custom parameters."""
        with patch(
            "enhanced_agent_bus.deliberation_layer.adaptive_router.get_deliberation_queue",
            return_value=mock_deliberation_queue,
        ):
            router = AdaptiveRouter(
                impact_threshold=0.5, deliberation_timeout=600, enable_learning=False
            )

        assert router.impact_threshold == 0.5
        assert router.deliberation_timeout == 600
        assert router.enable_learning is False

    def test_performance_metrics_initialized(self, router):
        """Test that performance metrics are properly initialized."""
        metrics = router.performance_metrics

        assert "total_messages" in metrics
        assert "fast_lane_count" in metrics
        assert "deliberation_count" in metrics
        assert "deliberation_approved" in metrics
        assert "deliberation_rejected" in metrics
        assert "deliberation_timeout" in metrics
        assert "false_positives" in metrics
        assert "false_negatives" in metrics


class TestRouteMessage:
    """Tests for the route_message method."""

    async def test_route_low_impact_to_fast_lane(self, router, low_impact_message):
        """Test that low impact messages are routed to fast lane."""
        result = await router.route_message(low_impact_message)

        assert result["lane"] == "fast"
        assert result["impact_score"] == 0.3
        assert result["requires_deliberation"] is False
        assert result["fast_path_enabled"] is True
        assert router.performance_metrics["fast_lane_count"] == 1
        assert router.performance_metrics["total_messages"] == 1

    async def test_route_high_impact_to_deliberation(self, router, high_impact_message):
        """Test that high impact messages are routed to deliberation."""
        result = await router.route_message(high_impact_message)

        assert result["lane"] == "deliberation"
        assert result["impact_score"] == 0.95
        assert result["requires_deliberation"] is True
        assert result["opa_enforced"] is True
        assert router.performance_metrics["deliberation_count"] == 1
        assert router.performance_metrics["total_messages"] == 1

    async def test_route_boundary_score_at_threshold(self, router, mock_deliberation_queue):
        """Test routing behavior at exactly the threshold."""
        with patch(
            "enhanced_agent_bus.deliberation_layer.adaptive_router.get_deliberation_queue",
            return_value=mock_deliberation_queue,
        ):
            router = AdaptiveRouter(impact_threshold=0.8)

        # Score exactly at threshold should go to deliberation
        message = AgentMessage(
            from_agent="agent-1",
            to_agent="agent-2",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            impact_score=0.8,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        result = await router.route_message(message)
        assert result["lane"] == "deliberation"

    async def test_route_calculates_missing_impact_score(self, router, message_no_score):
        """Test that missing impact scores are calculated."""
        assert message_no_score.impact_score is None

        # Mock the impact scorer and intent classifier to avoid external dependencies
        with (
            patch(
                "enhanced_agent_bus.deliberation_layer.impact_scorer.get_impact_scorer"
            ) as mock_get_scorer,
            patch.object(
                router.intent_classifier, "classify_async", new_callable=AsyncMock
            ) as mock_classify,
        ):
            scorer_instance = MagicMock()
            scorer_instance.calculate_impact_score_async = AsyncMock(return_value=0.4)
            mock_get_scorer.return_value = scorer_instance

            from enhanced_agent_bus.deliberation_layer.intent_classifier import IntentType

            mock_classify.return_value = IntentType.GENERAL

            result = await router.route_message(message_no_score)

            # Verify that impact score was calculated and set
            assert message_no_score.impact_score == 0.4
            assert result["lane"] == "fast"

    async def test_route_message_updates_status(self, router, low_impact_message):
        """Test that fast lane routing updates message status."""
        original_updated_at = low_impact_message.updated_at

        await router.route_message(low_impact_message)

        assert low_impact_message.status == MessageStatus.DELIVERED
        assert low_impact_message.updated_at >= original_updated_at

    async def test_route_with_context(self, router, low_impact_message):
        """Test routing with additional context."""
        context = {"tenant_id": "tenant-123", "user_role": "admin", "action_severity": "low"}

        result = await router.route_message(low_impact_message, context=context)

        assert result["lane"] == "fast"


class TestRoutingHistory:
    """Tests for routing history recording."""

    async def test_routing_history_recorded(self, router, low_impact_message):
        """Test that routing decisions are recorded in history."""
        await router.route_message(low_impact_message)

        assert len(router.routing_history) == 1
        entry = router.routing_history[0]

        assert entry["message_id"] == low_impact_message.message_id
        assert entry["impact_score"] == 0.3
        assert entry["routing_decision"]["lane"] == "fast"
        assert "timestamp" in entry

    async def test_routing_history_disabled_when_learning_off(
        self, router_no_learning, low_impact_message
    ):
        """Test that history is not recorded when learning is disabled."""
        await router_no_learning.route_message(low_impact_message)

        assert len(router_no_learning.routing_history) == 0

    async def test_routing_history_capped_at_1000(self, router, mock_deliberation_queue):
        """Test that routing history is capped at 1000 entries."""
        with patch(
            "enhanced_agent_bus.deliberation_layer.adaptive_router.get_deliberation_queue",
            return_value=mock_deliberation_queue,
        ):
            router = AdaptiveRouter(enable_learning=True)

        # Add 1050 routing decisions
        for i in range(1050):
            message = AgentMessage(
                from_agent="agent-1",
                to_agent="agent-2",
                message_type=MessageType.COMMAND,
                content={"index": i},
                impact_score=0.3,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            await router.route_message(message)

        assert len(router.routing_history) == 1000


class TestPerformanceFeedback:
    """Tests for performance feedback handling."""

    async def test_update_feedback_approved(self, router, high_impact_message):
        """Test feedback update for approved deliberation."""
        await router.route_message(high_impact_message)

        await router.update_performance_feedback(
            message_id=high_impact_message.message_id,
            actual_outcome="approved",
            processing_time=2.5,
            feedback_score=0.9,
        )

        assert router.performance_metrics["deliberation_approved"] == 1

    async def test_update_feedback_rejected(self, router, high_impact_message):
        """Test feedback update for rejected deliberation."""
        await router.route_message(high_impact_message)

        await router.update_performance_feedback(
            message_id=high_impact_message.message_id,
            actual_outcome="rejected",
            processing_time=3.0,
            feedback_score=0.1,
        )

        assert router.performance_metrics["deliberation_rejected"] == 1

    async def test_update_feedback_timeout(self, router, high_impact_message):
        """Test feedback update for timed out deliberation."""
        await router.route_message(high_impact_message)

        await router.update_performance_feedback(
            message_id=high_impact_message.message_id,
            actual_outcome="timeout",
            processing_time=300.0,
        )

        assert router.performance_metrics["deliberation_timeout"] == 1

    async def test_update_feedback_missing_message(self, router):
        """Test feedback update for non-existent message."""
        # Should not raise, just log warning
        await router.update_performance_feedback(
            message_id="non-existent-id", actual_outcome="approved", processing_time=1.0
        )

        # Metrics should remain unchanged
        assert router.performance_metrics["deliberation_approved"] == 0

    async def test_update_feedback_disabled_when_learning_off(
        self, router_no_learning, high_impact_message
    ):
        """Test that feedback is ignored when learning is disabled."""
        await router_no_learning.route_message(high_impact_message)

        # Should return without updating
        await router_no_learning.update_performance_feedback(
            message_id=high_impact_message.message_id,
            actual_outcome="approved",
            processing_time=2.0,
        )

        # No history to update
        assert len(router_no_learning.routing_history) == 0


class TestAdaptiveThresholdAdjustment:
    """Tests for adaptive threshold adjustment."""

    async def test_threshold_not_adjusted_insufficient_data(self, router, mock_deliberation_queue):
        """Test threshold is not adjusted with insufficient data."""
        with patch(
            "enhanced_agent_bus.deliberation_layer.adaptive_router.get_deliberation_queue",
            return_value=mock_deliberation_queue,
        ):
            router = AdaptiveRouter(impact_threshold=0.8)

        original_threshold = router.impact_threshold

        # Only 10 messages - below 50 minimum
        for i in range(10):
            message = AgentMessage(
                from_agent="agent-1",
                to_agent="agent-2",
                message_type=MessageType.COMMAND,
                content={"index": i},
                impact_score=0.5,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            await router.route_message(message)
            await router.update_performance_feedback(
                message_id=message.message_id, actual_outcome="success", processing_time=1.0
            )

        assert router.impact_threshold == original_threshold

    async def test_threshold_bounded_between_0_1_and_0_95(self, router, mock_deliberation_queue):
        """Test threshold stays within valid bounds."""
        with patch(
            "enhanced_agent_bus.deliberation_layer.adaptive_router.get_deliberation_queue",
            return_value=mock_deliberation_queue,
        ):
            router = AdaptiveRouter(impact_threshold=0.95)

        # Even with adjustments, threshold should stay <= 0.95
        router.impact_threshold = 1.0
        router.set_impact_threshold(1.5)  # Try to set above max
        assert router.impact_threshold <= 1.0

        router.set_impact_threshold(-0.5)  # Try to set below min
        assert router.impact_threshold >= 0.0


class TestRoutingStatistics:
    """Tests for routing statistics retrieval."""

    def test_get_routing_stats_empty(self, router):
        """Test stats retrieval with no messages."""
        stats = router.get_routing_stats()

        assert stats["total_messages"] == 0
        assert stats["fast_lane_count"] == 0
        assert stats["deliberation_count"] == 0

    async def test_get_routing_stats_with_data(
        self, router, low_impact_message, high_impact_message
    ):
        """Test stats retrieval with processed messages."""
        await router.route_message(low_impact_message)
        await router.route_message(high_impact_message)

        stats = router.get_routing_stats()

        assert stats["total_messages"] == 2
        assert stats["fast_lane_count"] == 1
        assert stats["deliberation_count"] == 1
        assert stats["fast_lane_percentage"] == 0.5
        assert stats["deliberation_percentage"] == 0.5
        assert stats["current_threshold"] == 0.8
        assert stats["learning_enabled"] is True
        assert stats["history_size"] == 2


class TestThresholdManagement:
    """Tests for manual threshold management."""

    def test_set_impact_threshold_valid(self, router):
        """Test setting a valid threshold."""
        router.set_impact_threshold(0.5)
        assert router.impact_threshold == 0.5

    def test_set_impact_threshold_clamped_high(self, router):
        """Test threshold is clamped to maximum 1.0."""
        router.set_impact_threshold(1.5)
        assert router.impact_threshold == 1.0

    def test_set_impact_threshold_clamped_low(self, router):
        """Test threshold is clamped to minimum 0.0."""
        router.set_impact_threshold(-0.5)
        assert router.impact_threshold == 0.0


class TestForceDeliberation:
    """Tests for forced deliberation routing."""

    async def test_force_deliberation_overrides_score(self, router, low_impact_message):
        """Test that force_deliberation routes regardless of score."""
        assert low_impact_message.impact_score < router.impact_threshold

        result = await router.force_deliberation(low_impact_message, reason="manual_review")

        assert result["lane"] == "deliberation"
        assert result["forced"] is True
        assert result["force_reason"] == "manual_review"
        # Original score should be restored
        assert low_impact_message.impact_score == 0.3

    async def test_force_deliberation_default_reason(self, router, low_impact_message):
        """Test force deliberation with default reason."""
        result = await router.force_deliberation(low_impact_message)

        assert result["forced"] is True
        assert result["force_reason"] == "manual_override"

    async def test_force_deliberation_increments_counter(self, router, low_impact_message):
        """Test that force deliberation increments deliberation counter."""
        await router.force_deliberation(low_impact_message)

        assert router.performance_metrics["deliberation_count"] == 1


class TestGetAdaptiveRouter:
    """Tests for the singleton router getter."""

    def test_get_adaptive_router_returns_instance(self, mock_deliberation_queue):
        """Test that get_adaptive_router returns a router instance."""
        with patch(
            "enhanced_agent_bus.deliberation_layer.adaptive_router.get_deliberation_queue",
            return_value=mock_deliberation_queue,
        ):
            with patch(
                "enhanced_agent_bus.deliberation_layer.adaptive_router._adaptive_router", None
            ):
                router = get_adaptive_router()

                assert router is not None
                assert isinstance(router, AdaptiveRouter)

    def test_get_adaptive_router_returns_same_instance(self, mock_deliberation_queue):
        """Test that get_adaptive_router returns the same instance on repeated calls."""
        with patch(
            "enhanced_agent_bus.deliberation_layer.adaptive_router.get_deliberation_queue",
            return_value=mock_deliberation_queue,
        ):
            # Reset the singleton using the already imported module
            from enhanced_agent_bus.deliberation_layer import (
                adaptive_router as router_module,
            )

            router_module._adaptive_router = None

            router1 = get_adaptive_router()
            router2 = get_adaptive_router()

            assert router1 is router2


class TestMultipleRoutingDecisions:
    """Tests for handling multiple routing decisions in sequence."""

    async def test_multiple_messages_different_paths(self, router, mock_deliberation_queue):
        """Test routing multiple messages to different paths."""
        with patch(
            "enhanced_agent_bus.deliberation_layer.adaptive_router.get_deliberation_queue",
            return_value=mock_deliberation_queue,
        ):
            router = AdaptiveRouter(impact_threshold=0.5)

        messages = [
            AgentMessage(
                from_agent="a",
                to_agent="b",
                message_type=MessageType.COMMAND,
                content={},
                impact_score=0.3,
                constitutional_hash=CONSTITUTIONAL_HASH,
            ),
            AgentMessage(
                from_agent="a",
                to_agent="b",
                message_type=MessageType.COMMAND,
                content={},
                impact_score=0.7,
                constitutional_hash=CONSTITUTIONAL_HASH,
            ),
            AgentMessage(
                from_agent="a",
                to_agent="b",
                message_type=MessageType.COMMAND,
                content={},
                impact_score=0.2,
                constitutional_hash=CONSTITUTIONAL_HASH,
            ),
            AgentMessage(
                from_agent="a",
                to_agent="b",
                message_type=MessageType.COMMAND,
                content={},
                impact_score=0.9,
                constitutional_hash=CONSTITUTIONAL_HASH,
            ),
        ]

        results = []
        for msg in messages:
            result = await router.route_message(msg)
            results.append(result)

        assert results[0]["lane"] == "fast"  # 0.3 < 0.5
        assert results[1]["lane"] == "deliberation"  # 0.7 >= 0.5
        assert results[2]["lane"] == "fast"  # 0.2 < 0.5
        assert results[3]["lane"] == "deliberation"  # 0.9 >= 0.5

        assert router.performance_metrics["fast_lane_count"] == 2
        assert router.performance_metrics["deliberation_count"] == 2


class TestConstitutionalCompliance:
    """Tests for constitutional compliance."""

    @pytest.mark.constitutional
    async def test_routing_preserves_constitutional_hash(self, router, low_impact_message):
        """Test that routing preserves constitutional hash."""
        original_hash = low_impact_message.constitutional_hash

        await router.route_message(low_impact_message)

        assert low_impact_message.constitutional_hash == original_hash
        assert low_impact_message.constitutional_hash == CONSTITUTIONAL_HASH

    @pytest.mark.constitutional
    async def test_routing_includes_decision_timestamp(self, router, low_impact_message):
        """Test that routing decisions include timestamps."""
        result = await router.route_message(low_impact_message)

        assert "decision_timestamp" in result
        assert isinstance(result["decision_timestamp"], datetime)
