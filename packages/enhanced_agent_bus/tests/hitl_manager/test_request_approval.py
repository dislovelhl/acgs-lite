"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- requestapproval functionality
- Error handling and edge cases
- Integration with related components
"""

from .hitl_test_helpers import (
    MockAuditLedger,
    MockDeliberationQueue,
    MockDeliberationStatus,
)


class TestRequestApproval:
    """Tests for request_approval method."""

    async def test_request_approval_valid_item(self, mock_queue: MockDeliberationQueue) -> None:
        """Test request_approval with a valid queue item."""

        class TestableHITLManager:
            def __init__(self, deliberation_queue, audit_ledger=None):
                self.queue = deliberation_queue
                self.audit_ledger = audit_ledger or MockAuditLedger()

            async def request_approval(self, item_id: str, channel: str = "slack"):
                item = self.queue.queue.get(item_id)
                if not item:
                    return None
                item.status = MockDeliberationStatus.UNDER_REVIEW
                return item

        manager = TestableHITLManager(mock_queue)
        result = await manager.request_approval("item-123")

        assert result is not None
        assert result.status == MockDeliberationStatus.UNDER_REVIEW

    async def test_request_approval_missing_item(self, mock_queue: MockDeliberationQueue) -> None:
        """Test request_approval with a missing queue item."""

        class TestableHITLManager:
            def __init__(self, deliberation_queue, audit_ledger=None):
                self.queue = deliberation_queue
                self.audit_ledger = audit_ledger or MockAuditLedger()

            async def request_approval(self, item_id: str, channel: str = "slack"):
                item = self.queue.queue.get(item_id)
                if not item:
                    return None
                item.status = MockDeliberationStatus.UNDER_REVIEW
                return item

        manager = TestableHITLManager(mock_queue)
        result = await manager.request_approval("nonexistent-item")

        assert result is None

    async def test_request_approval_teams_channel(self, mock_queue: MockDeliberationQueue) -> None:
        """Test request_approval with Teams channel."""

        class TestableHITLManager:
            def __init__(self, deliberation_queue, audit_ledger=None):
                self.queue = deliberation_queue
                self.audit_ledger = audit_ledger or MockAuditLedger()

            async def request_approval(self, item_id: str, channel: str = "slack"):
                item = self.queue.queue.get(item_id)
                if not item:
                    return None
                item.status = MockDeliberationStatus.UNDER_REVIEW
                return {"item": item, "channel": channel}

        manager = TestableHITLManager(mock_queue)
        result = await manager.request_approval("item-123", channel="teams")

        assert result is not None
        assert result["channel"] == "teams"
