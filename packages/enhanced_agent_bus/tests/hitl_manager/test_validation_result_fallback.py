"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class and validationresultfallback.
Tests cover:
- validationresultfallback functionality
- Error handling and edge cases
- Integration with related components
"""

from datetime import UTC, datetime


class TestValidationResultFallback:
    """Test the fallback ValidationResult class defined in hitl_manager."""

    def test_validation_result_creation(self):
        """Test ValidationResult creation with defaults."""
        from enhanced_agent_bus.deliberation_layer.hitl_manager import ValidationResult

        result = ValidationResult()
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.metadata == {}
        assert result.decision == "ALLOW"

    def test_validation_result_add_error(self):
        """Test add_error sets is_valid to False."""
        from enhanced_agent_bus.deliberation_layer.hitl_manager import ValidationResult

        result = ValidationResult()
        result.add_error("Test error")

        assert result.is_valid is False
        assert "Test error" in result.errors

    def test_validation_result_to_dict(self):
        """Test to_dict serialization."""
        from enhanced_agent_bus.deliberation_layer.hitl_manager import ValidationResult

        result = ValidationResult(
            is_valid=False,
            errors=["error1", "error2"],
            warnings=["warning1"],
            metadata={"key": "value"},
            decision="DENY",
        )

        d = result.to_dict()

        assert d["is_valid"] is False
        assert len(d["errors"]) == 2
        assert d["warnings"] == ["warning1"]
        assert d["metadata"] == {"key": "value"}
        assert d["decision"] == "DENY"

    def test_validation_result_with_custom_metadata(self):
        """Test ValidationResult with custom metadata."""

        from enhanced_agent_bus.deliberation_layer.hitl_manager import ValidationResult

        metadata = {
            "item_id": "item-123",
            "reviewer": "admin",
            "decision": "approve",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        result = ValidationResult(
            is_valid=True,
            metadata=metadata,
        )

        assert result.metadata["item_id"] == "item-123"
        assert result.metadata["reviewer"] == "admin"
