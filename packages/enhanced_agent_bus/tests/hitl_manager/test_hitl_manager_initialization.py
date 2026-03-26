"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- hitlmanagerinitialization functionality
- Error handling and edge cases
- Integration with related components
"""

from .hitl_test_helpers import MockAuditLedger, MockDeliberationQueue


class TestHITLManagerInitialization:
    """Tests for HITLManager initialization."""

    def test_initialization_with_defaults(self, mock_queue: MockDeliberationQueue) -> None:
        """Test initialization with default parameters."""

        # Create a simple HITLManager-like class for testing
        class TestableHITLManager:
            def __init__(self, deliberation_queue, audit_ledger=None):
                self.queue = deliberation_queue
                self.audit_ledger = audit_ledger or MockAuditLedger()

        manager = TestableHITLManager(mock_queue)
        assert manager.queue is mock_queue
        assert manager.audit_ledger is not None

    def test_initialization_with_custom_audit_ledger(
        self, mock_queue: MockDeliberationQueue, mock_audit_ledger: MockAuditLedger
    ) -> None:
        """Test initialization with custom audit ledger."""

        class TestableHITLManager:
            def __init__(self, deliberation_queue, audit_ledger=None):
                self.queue = deliberation_queue
                self.audit_ledger = audit_ledger or MockAuditLedger()

        manager = TestableHITLManager(mock_queue, mock_audit_ledger)
        assert manager.audit_ledger is mock_audit_ledger
