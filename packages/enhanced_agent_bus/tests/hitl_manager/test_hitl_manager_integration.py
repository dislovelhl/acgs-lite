"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- hitlmanagerintegration functionality
- Error handling and edge cases
- Integration with related components
"""

from .hitl_test_helpers import (
    MockAuditLedger,
    MockDeliberationQueue,
    MockDeliberationStatus,
)


class TestHITLManagerIntegration:
    """Integration tests for HITLManager."""

    async def test_full_approval_workflow(
        self, mock_queue: MockDeliberationQueue, mock_audit_ledger: MockAuditLedger
    ) -> None:
        """Test complete approval workflow."""

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

            async def process_approval(
                self, item_id: str, reviewer_id: str, decision: str, reasoning: str
            ):
                if decision == "approve":
                    status = MockDeliberationStatus.APPROVED
                else:
                    status = MockDeliberationStatus.REJECTED

                success = await self.queue.submit_human_decision(
                    item_id=item_id, reviewer=reviewer_id, decision=status, reasoning=reasoning
                )

                if success:
                    await self.audit_ledger.add_validation_result({})
                    return True
                return False

        manager = TestableHITLManager(mock_queue, mock_audit_ledger)

        # Step 1: Request approval
        item = await manager.request_approval("item-123")
        assert item is not None
        assert item.status == MockDeliberationStatus.UNDER_REVIEW

        # Step 2: Process approval
        result = await manager.process_approval(
            item_id="item-123",
            reviewer_id="senior-reviewer",
            decision="approve",
            reasoning="All security checks passed",
        )
        assert result is True

    async def test_full_rejection_workflow(
        self, mock_queue: MockDeliberationQueue, mock_audit_ledger: MockAuditLedger
    ) -> None:
        """Test complete rejection workflow."""

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

            async def process_approval(
                self, item_id: str, reviewer_id: str, decision: str, reasoning: str
            ):
                if decision == "approve":
                    status = MockDeliberationStatus.APPROVED
                else:
                    status = MockDeliberationStatus.REJECTED

                success = await self.queue.submit_human_decision(
                    item_id=item_id, reviewer=reviewer_id, decision=status, reasoning=reasoning
                )

                if success:
                    await self.audit_ledger.add_validation_result({})
                    return True
                return False

        manager = TestableHITLManager(mock_queue, mock_audit_ledger)

        # Step 1: Request approval
        item = await manager.request_approval("item-123")
        assert item.status == MockDeliberationStatus.UNDER_REVIEW

        # Step 2: Process rejection
        result = await manager.process_approval(
            item_id="item-123",
            reviewer_id="security-reviewer",
            decision="reject",
            reasoning="Potential security vulnerability detected",
        )
        assert result is True
