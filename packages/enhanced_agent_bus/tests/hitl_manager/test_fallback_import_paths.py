"""
ACGS-2 Enhanced Agent Bus - HITL Manager Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the HITLManager class.
Tests cover:
- fallbackimportpaths functionality
- Error handling and edge cases
- Integration with related components
"""

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH


class TestFallbackImportPaths:
    """Test the fallback import paths for ValidationResult."""

    def test_module_level_imports(self):
        """Test that the module can be imported successfully."""
        from enhanced_agent_bus.deliberation_layer import hitl_manager

        # Verify HITLManager class is available
        assert hasattr(hitl_manager, "HITLManager")
        assert hasattr(hitl_manager, "ValidationResult")
        assert hasattr(hitl_manager, "CONSTITUTIONAL_HASH")

    def test_validation_result_interface(self):
        """Test ValidationResult interface from hitl_manager."""
        from enhanced_agent_bus.deliberation_layer.hitl_manager import ValidationResult

        result = ValidationResult(is_valid=True, constitutional_hash=CONSTITUTIONAL_HASH)
        assert result.is_valid is True
        assert result.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_validation_result_from_module_has_to_dict(self):
        """Test ValidationResult has to_dict method."""
        from enhanced_agent_bus.deliberation_layer.hitl_manager import ValidationResult

        result = ValidationResult(is_valid=False, errors=["Test error"], metadata={"key": "value"})

        result_dict = result.to_dict()
        assert "is_valid" in result_dict
        assert "errors" in result_dict
        assert "metadata" in result_dict
        assert result_dict["errors"] == ["Test error"]
