"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- actualhitlmanager functionality
- Error handling and edge cases
- Integration with related components
"""

import pytest


class TestActualHITLManager:
    """Tests for the actual HITLManager implementation."""

    @pytest.fixture
    async def real_queue(self):
        """Create a real DeliberationQueue."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )

        queue = DeliberationQueue()
        yield queue
        await queue.stop()

    @pytest.fixture
    async def real_hitl_manager(self, real_queue):
        """Create a real HITLManager instance."""
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager

        manager = HITLManager(real_queue)
        return manager

    async def test_real_hitl_manager_init(self, real_queue):
        """Test real HITLManager initialization."""
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager

        manager = HITLManager(real_queue)
        assert manager.queue is real_queue
        assert manager.audit_ledger is not None

    async def test_real_request_approval_with_message(self, real_queue, caplog):
        """Test request_approval with a real AgentMessage."""
        import logging

        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        manager = HITLManager(real_queue)

        message = AgentMessage(
            from_agent="test-agent",
            to_agent="recipient",
            message_type=MessageType.COMMAND,
            content={"action": "high-risk-operation"},
            impact_score=0.85,
        )

        item_id = await real_queue.enqueue_for_deliberation(message)

        with caplog.at_level(logging.INFO):
            await manager.request_approval(item_id)

        assert "Notification sent to slack" in caplog.text

        # Verify status changed
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationStatus,
        )

        task = real_queue.get_task(item_id)
        assert task.status.value == DeliberationStatus.UNDER_REVIEW.value

    async def test_real_request_approval_item_not_found(self, real_queue, caplog):
        """Test request_approval when item doesn't exist."""
        import logging

        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager

        manager = HITLManager(real_queue)

        with caplog.at_level(logging.ERROR):
            await manager.request_approval("nonexistent-item")

        assert "not found" in caplog.text

    async def test_real_request_approval_teams_channel(self, real_queue, caplog):
        """Test request_approval with Teams channel."""
        import logging

        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        manager = HITLManager(real_queue)

        message = AgentMessage(
            from_agent="test-agent",
            to_agent="recipient",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )

        item_id = await real_queue.enqueue_for_deliberation(message)

        with caplog.at_level(logging.INFO):
            await manager.request_approval(item_id, channel="teams")

        assert "teams" in caplog.text

    async def test_real_process_approval_approve(self, real_queue, caplog):
        """Test process_approval with approve decision."""
        import logging

        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        manager = HITLManager(real_queue)

        message = AgentMessage(
            from_agent="test-agent",
            to_agent="recipient",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "modify-policy"},
            impact_score=0.9,
        )

        item_id = await real_queue.enqueue_for_deliberation(message)
        await manager.request_approval(item_id)

        with caplog.at_level(logging.INFO):
            result = await manager.process_approval(
                item_id=item_id,
                reviewer_id="reviewer-001",
                decision="approve",
                reasoning="Action is compliant",
            )

        assert result is True
        assert "Decision for" in caplog.text
        assert "recorded" in caplog.text

    async def test_real_process_approval_reject(self, real_queue, caplog):
        """Test process_approval with reject decision."""
        import logging

        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        manager = HITLManager(real_queue)

        message = AgentMessage(
            from_agent="test-agent",
            to_agent="recipient",
            message_type=MessageType.COMMAND,
            content={"action": "risky-operation"},
        )

        item_id = await real_queue.enqueue_for_deliberation(message)
        await manager.request_approval(item_id)

        with caplog.at_level(logging.INFO):
            result = await manager.process_approval(
                item_id=item_id,
                reviewer_id="security-reviewer",
                decision="reject",
                reasoning="Violates security policy",
            )

        assert result is True

    async def test_real_process_approval_invalid_item(self, real_queue):
        """Test process_approval with invalid item_id."""
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager

        manager = HITLManager(real_queue)

        result = await manager.process_approval(
            item_id="invalid-item", reviewer_id="reviewer", decision="approve", reasoning="test"
        )

        assert result is False

    async def test_real_process_approval_not_under_review(self, real_queue):
        """Test process_approval fails if item not under review."""
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        manager = HITLManager(real_queue)

        message = AgentMessage(
            from_agent="test-agent",
            to_agent="recipient",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )

        item_id = await real_queue.enqueue_for_deliberation(message)
        # Don't call request_approval - item is PENDING not UNDER_REVIEW

        result = await manager.process_approval(
            item_id=item_id, reviewer_id="reviewer", decision="approve", reasoning="test"
        )

        assert result is False
