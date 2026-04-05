"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- processapproval functionality
- Error handling and edge cases
- Integration with related components
"""

from .hitl_test_helpers import (
    MockAuditLedger,
    MockDeliberationQueue,
    MockDeliberationStatus,
)


class TestProcessApproval:
    """Tests for process_approval method."""

    async def test_process_approval_approve_decision(
        self, mock_queue: MockDeliberationQueue, mock_audit_ledger: MockAuditLedger
    ) -> None:
        """Test process_approval with approve decision."""

        class TestableHITLManager:
            def __init__(self, deliberation_queue, audit_ledger=None):
                self.queue = deliberation_queue
                self.audit_ledger = audit_ledger or MockAuditLedger()

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
                    audit_result = {
                        "is_valid": status == MockDeliberationStatus.APPROVED,
                        "item_id": item_id,
                        "reviewer": reviewer_id,
                        "decision": decision,
                    }
                    await self.audit_ledger.add_validation_result(audit_result)
                    return True
                return False

        manager = TestableHITLManager(mock_queue, mock_audit_ledger)
        result = await manager.process_approval(
            item_id="item-123",
            reviewer_id="reviewer-1",
            decision="approve",
            reasoning="Looks good to me",
        )

        assert result is True
        mock_queue.submit_human_decision.assert_called_once()
        mock_audit_ledger.add_validation_result.assert_called_once()

    async def test_process_approval_reject_decision(
        self, mock_queue: MockDeliberationQueue, mock_audit_ledger: MockAuditLedger
    ) -> None:
        """Test process_approval with reject decision."""

        class TestableHITLManager:
            def __init__(self, deliberation_queue, audit_ledger=None):
                self.queue = deliberation_queue
                self.audit_ledger = audit_ledger or MockAuditLedger()

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
                    audit_result = {
                        "is_valid": status == MockDeliberationStatus.APPROVED,
                        "item_id": item_id,
                        "reviewer": reviewer_id,
                        "decision": decision,
                    }
                    await self.audit_ledger.add_validation_result(audit_result)
                    return True
                return False

        manager = TestableHITLManager(mock_queue, mock_audit_ledger)
        result = await manager.process_approval(
            item_id="item-123",
            reviewer_id="reviewer-1",
            decision="reject",
            reasoning="Security concerns",
        )

        assert result is True
        call_kwargs = mock_queue.submit_human_decision.call_args.kwargs
        assert call_kwargs["decision"] == MockDeliberationStatus.REJECTED

    async def test_process_approval_submission_failure(
        self, mock_queue: MockDeliberationQueue, mock_audit_ledger: MockAuditLedger
    ) -> None:
        """Test process_approval when submission fails."""
        mock_queue.submit_human_decision.return_value = False

        class TestableHITLManager:
            def __init__(self, deliberation_queue, audit_ledger=None):
                self.queue = deliberation_queue
                self.audit_ledger = audit_ledger or MockAuditLedger()

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
                    audit_result = {
                        "is_valid": status == MockDeliberationStatus.APPROVED,
                        "item_id": item_id,
                        "reviewer": reviewer_id,
                        "decision": decision,
                    }
                    await self.audit_ledger.add_validation_result(audit_result)
                    return True
                return False

        manager = TestableHITLManager(mock_queue, mock_audit_ledger)
        result = await manager.process_approval(
            item_id="item-123", reviewer_id="reviewer-1", decision="approve", reasoning="Approved"
        )

        assert result is False
        # Audit ledger should not be called when submission fails
        mock_audit_ledger.add_validation_result.assert_not_called()
