"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- hitlmanagerwithcustomauditledger functionality
- Error handling and edge cases
- Integration with related components
"""

import pytest


class TestHITLManagerWithCustomAuditLedger:
    """Tests for HITLManager with custom audit ledger."""

    @pytest.fixture
    async def custom_audit_ledger(self):
        """Create a custom audit ledger that tracks calls."""

        class TrackingAuditLedger:
            def __init__(self):
                self.results = []

            async def add_validation_result(self, result):
                self.results.append(result)
                return f"audit_hash_{len(self.results)}"

        return TrackingAuditLedger()

    async def test_custom_audit_ledger_receives_results(self, custom_audit_ledger):
        """Test that custom audit ledger receives validation results."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import AgentMessage, MessageType

        queue = DeliberationQueue()
        manager = HITLManager(queue, audit_ledger=custom_audit_ledger)

        message = AgentMessage(
            from_agent="test-agent",
            to_agent="recipient",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )

        item_id = await queue.enqueue_for_deliberation(message)
        await manager.request_approval(item_id)

        await manager.process_approval(
            item_id=item_id, reviewer_id="reviewer", decision="approve", reasoning="Approved"
        )

        assert len(custom_audit_ledger.results) == 1
        audit = custom_audit_ledger.results[0]
        assert audit.is_valid is True
        assert audit.metadata["reviewer"] == "reviewer"
        assert audit.metadata["decision"] == "approve"

        await queue.stop()

    async def test_audit_records_constitutional_hash(self, custom_audit_ledger):
        """Test that audit records include constitutional hash."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import (
            CONSTITUTIONAL_HASH,
            AgentMessage,
            MessageType,
        )

        queue = DeliberationQueue()
        manager = HITLManager(queue, audit_ledger=custom_audit_ledger)

        message = AgentMessage(
            from_agent="test-agent",
            to_agent="recipient",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )

        item_id = await queue.enqueue_for_deliberation(message)
        await manager.request_approval(item_id)

        await manager.process_approval(
            item_id=item_id, reviewer_id="reviewer", decision="approve", reasoning="Test"
        )

        audit = custom_audit_ledger.results[0]
        assert audit.constitutional_hash == CONSTITUTIONAL_HASH

        await queue.stop()
