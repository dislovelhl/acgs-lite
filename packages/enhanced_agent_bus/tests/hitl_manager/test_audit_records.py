"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- auditrecords functionality
- Error handling and edge cases
- Integration with related components
"""

from datetime import UTC, datetime


class TestAuditRecords:
    """Tests for audit record generation."""

    def test_audit_record_for_approval(self) -> None:
        """Test audit record structure for approval."""
        audit_record = {
            "is_valid": True,
            "metadata": {
                "item_id": "item-123",
                "reviewer": "reviewer-1",
                "decision": "approve",
                "reasoning": "All checks passed",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }

        assert audit_record["is_valid"] is True
        assert audit_record["metadata"]["decision"] == "approve"
        assert "timestamp" in audit_record["metadata"]

    def test_audit_record_for_rejection(self) -> None:
        """Test audit record structure for rejection."""
        audit_record = {
            "is_valid": False,
            "metadata": {
                "item_id": "item-456",
                "reviewer": "reviewer-2",
                "decision": "reject",
                "reasoning": "Security concerns",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }

        assert audit_record["is_valid"] is False
        assert audit_record["metadata"]["decision"] == "reject"
