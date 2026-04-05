"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- constitutionalcompliance functionality
- Error handling and edge cases
- Integration with related components
"""

from datetime import datetime

import pytest


class TestConstitutionalCompliance:
    """Test constitutional compliance in HITL operations."""

    @pytest.mark.constitutional
    async def test_constitutional_hash_in_audit_trail(self):
        """Verify constitutional hash is maintained in audit trail."""
        from enhanced_agent_bus.deliberation_layer.deliberation_queue import (
            DeliberationQueue,
        )
        from enhanced_agent_bus.deliberation_layer.hitl_manager import HITLManager
        from enhanced_agent_bus.models import (
            CONSTITUTIONAL_HASH,
            AgentMessage,
            MessageType,
        )

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
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        item_id = await queue.enqueue_for_deliberation(message)
        await manager.request_approval(item_id)

        await manager.process_approval(
            item_id=item_id,
            reviewer_id="reviewer",
            decision="approve",
            reasoning="Compliant with constitutional principles",
        )

        # Verify constitutional hash in audit
        audit_result = ledger.results[0]
        assert audit_result.constitutional_hash == CONSTITUTIONAL_HASH

        await queue.stop()

    @pytest.mark.constitutional
    async def test_all_decisions_include_timestamp(self):
        """Verify all decisions include proper timestamps."""

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

        await manager.process_approval(
            item_id=item_id, reviewer_id="reviewer", decision="approve", reasoning="test"
        )

        audit_result = ledger.results[0]
        assert "timestamp" in audit_result.metadata
        # Verify timestamp is valid ISO format
        timestamp = audit_result.metadata["timestamp"]
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        await queue.stop()
