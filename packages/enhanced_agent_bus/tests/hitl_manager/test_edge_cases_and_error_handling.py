"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- edgecasesanderrorhandling functionality
- Error handling and edge cases
- Integration with related components
"""


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling in HITLManager."""

    async def test_empty_content_message(self):
        """Test handling of message with empty content."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
            DeliberationStatus,
        )
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        queue = DeliberationQueue()
        manager = HITLManager(queue)

        message = AgentMessage(
            from_agent="test-agent",
            to_agent="recipient",
            message_type=MessageType.COMMAND,
            content={},  # Empty content
        )

        item_id = await queue.enqueue_for_deliberation(message)
        await manager.request_approval(item_id)

        task = queue.get_task(item_id)
        assert task.status.value == DeliberationStatus.UNDER_REVIEW.value

        await queue.stop()

    async def test_special_characters_in_reasoning(self):
        """Test special characters in reasoning field."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        class TrackingLedger:
            def __init__(self):
                self.results = []

            async def add_validation_result(self, result):
                self.results.append(result)
                return "hash"

        queue = DeliberationQueue()
        ledger = TrackingLedger()
        manager = HITLManager(queue, audit_ledger=ledger)

        message = AgentMessage(
            from_agent="test-agent",
            to_agent="recipient",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )

        item_id = await queue.enqueue_for_deliberation(message)
        await manager.request_approval(item_id)

        special_reasoning = "<script>alert('xss')</script> & 'quotes' \"double\" emoji: 🚨"

        result = await manager.process_approval(
            item_id=item_id, reviewer_id="reviewer", decision="approve", reasoning=special_reasoning
        )

        assert result is True
        assert ledger.results[0].metadata["reasoning"] == special_reasoning

        await queue.stop()

    async def test_concurrent_approval_requests(self):
        """Test concurrent approval requests don't interfere."""
        import asyncio

        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
            DeliberationStatus,
        )
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        queue = DeliberationQueue()
        manager = HITLManager(queue)

        # Create multiple items
        item_ids = []
        for i in range(5):
            message = AgentMessage(
                from_agent=f"agent-{i}",
                to_agent="recipient",
                message_type=MessageType.COMMAND,
                content={"action": f"action-{i}"},
            )
            item_id = await queue.enqueue_for_deliberation(message)
            item_ids.append(item_id)

        # Request approvals concurrently
        await asyncio.gather(*[manager.request_approval(item_id) for item_id in item_ids])

        # Verify all items are under review
        for item_id in item_ids:
            task = queue.get_task(item_id)
            assert task.status.value == DeliberationStatus.UNDER_REVIEW.value

        await queue.stop()

    async def test_long_content_truncation(self, caplog):
        """Test that long content is truncated in notification."""
        import logging

        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        queue = DeliberationQueue()
        manager = HITLManager(queue)

        # Create message with very long content
        long_content = "A" * 500
        message = AgentMessage(
            from_agent="test-agent",
            to_agent="recipient",
            message_type=MessageType.COMMAND,
            content=long_content,
        )

        item_id = await queue.enqueue_for_deliberation(message)

        with caplog.at_level(logging.INFO):
            await manager.request_approval(item_id)

        # Content should be truncated (100 chars + "...")
        assert "..." in caplog.text

        await queue.stop()
