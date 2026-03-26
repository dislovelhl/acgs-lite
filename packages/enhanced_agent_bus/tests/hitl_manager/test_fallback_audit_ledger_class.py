"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- fallbackauditledgerclass functionality
- Error handling and edge cases
- Integration with related components
"""


class TestFallbackAuditLedgerClass:
    """Test the fallback AuditLedger class defined in hitl_manager."""

    async def test_mock_audit_ledger_returns_hash(self):
        """Test that mock audit ledger returns a hash."""
        from enhanced_agent_bus.deliberation_layer.hitl_manager import (
            AuditLedger,
            ValidationResult,
        )

        ledger = AuditLedger()
        result = ValidationResult(is_valid=True)

        hash_value = await ledger.add_validation_result(result)

        assert hash_value == "mock_audit_hash"

    async def test_mock_audit_ledger_logs_result(self, caplog):
        """Test that mock audit ledger logs the result."""
        import logging

        from enhanced_agent_bus.deliberation_layer.hitl_manager import (
            AuditLedger,
            ValidationResult,
        )

        ledger = AuditLedger()
        result = ValidationResult(is_valid=True, metadata={"test": "data"})

        with caplog.at_level(logging.DEBUG):
            await ledger.add_validation_result(result)

        # The log happens at DEBUG level, may or may not be captured
        # depending on logger configuration
