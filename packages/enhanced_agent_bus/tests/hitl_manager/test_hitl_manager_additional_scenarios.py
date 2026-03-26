"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- hitlmanageradditionalscenarios functionality
- Error handling and edge cases
- Integration with related components
"""


class TestHITLManagerAdditionalScenarios:
    """Additional test scenarios for comprehensive coverage."""

    async def test_process_approval_with_various_decisions(self):
        """Test process_approval with different decision types."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        queue = DeliberationQueue()
        manager = HITLManager(queue)

        # Create and enqueue a message
        message = AgentMessage(
            from_agent="test-agent",
            to_agent="recipient",
            message_type=MessageType.COMMAND,
            content={"action": "test_various"},
        )

        item_id = await queue.enqueue_for_deliberation(message)
        await manager.request_approval(item_id)

        # Test with "deny" decision (should map to rejected)
        result = await manager.process_approval(
            item_id=item_id,
            reviewer_id="reviewer-123",
            decision="deny",
            reasoning="Denied for testing",
        )

        assert result is True
        await queue.stop()

    async def test_request_approval_logs_correctly(self, caplog):
        """Test that request_approval logs notification correctly."""
        import logging

        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        with caplog.at_level(logging.INFO):
            queue = DeliberationQueue()
            manager = HITLManager(queue)

            message = AgentMessage(
                from_agent="logging-agent",
                to_agent="recipient",
                message_type=MessageType.COMMAND,
                content={"action": "test_logging"},
                impact_score=0.95,
            )

            item_id = await queue.enqueue_for_deliberation(message)
            await manager.request_approval(item_id)

            # Check that notification was logged
            assert any("Notification sent" in record.message for record in caplog.records)

            await queue.stop()

    async def test_process_approval_logs_decision(self, caplog):
        """Test that process_approval logs the decision."""
        import logging

        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        with caplog.at_level(logging.INFO):
            queue = DeliberationQueue()
            manager = HITLManager(queue)

            message = AgentMessage(
                from_agent="logging-agent",
                to_agent="recipient",
                message_type=MessageType.COMMAND,
                content={"action": "test_decision_logging"},
            )

            item_id = await queue.enqueue_for_deliberation(message)
            await manager.request_approval(item_id)

            await manager.process_approval(
                item_id=item_id,
                reviewer_id="reviewer",
                decision="approve",
                reasoning="Approved for testing",
            )

            # Check that decision was logged
            assert any(
                "Decision for" in record.message and "recorded" in record.message
                for record in caplog.records
            )

            await queue.stop()

    async def test_multiple_sequential_approvals(self):
        """Test handling multiple sequential approval workflows."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        queue = DeliberationQueue()
        manager = HITLManager(queue)

        # Process 3 messages sequentially
        for i in range(3):
            message = AgentMessage(
                from_agent=f"agent-{i}",
                to_agent="recipient",
                message_type=MessageType.COMMAND,
                content={"action": f"test_{i}"},
            )

            item_id = await queue.enqueue_for_deliberation(message)
            await manager.request_approval(item_id)

            decision = "approve" if i % 2 == 0 else "reject"
            result = await manager.process_approval(
                item_id=item_id,
                reviewer_id=f"reviewer-{i}",
                decision=decision,
                reasoning=f"Decision {i}",
            )
            assert result is True

        await queue.stop()
