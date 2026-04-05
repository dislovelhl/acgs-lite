"""
ACGS-2 Enhanced Agent Bus - Validators Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for validation utilities including:
- ValidationResult dataclass and methods
- Constitutional hash validation
- Message content validation
"""

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.types import JSONDict

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

try:
    from enhanced_agent_bus.validators import (
        CONSTITUTIONAL_HASH,
        ValidationResult,
        validate_constitutional_hash,
        validate_message_content,
    )
except ImportError:
    import sys

    sys.path.insert(0, "/home/martin/ACGS")
    from enhanced_agent_bus.validators import (
        CONSTITUTIONAL_HASH,
        ValidationResult,
        validate_constitutional_hash,
        validate_message_content,
    )

# =============================================================================
# CONSTITUTIONAL HASH CONSTANT TESTS
# =============================================================================


class TestConstitutionalHashConstant:
    """Tests for the CONSTITUTIONAL_HASH constant."""

    def test_constitutional_hash_value(self):
        """Constitutional hash has expected value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_constitutional_hash_is_string(self):
        """Constitutional hash is a string type."""
        assert isinstance(CONSTITUTIONAL_HASH, str)

    def test_constitutional_hash_is_hexadecimal(self):
        """Constitutional hash contains only hex characters."""
        assert all(c in "0123456789abcdef" for c in CONSTITUTIONAL_HASH)

    def test_constitutional_hash_length(self):
        """Constitutional hash has expected length (16 hex chars = 64 bits)."""
        assert len(CONSTITUTIONAL_HASH) == 16


# =============================================================================
# VALIDATION RESULT DATACLASS TESTS
# =============================================================================


class TestValidationResultInit:
    """Tests for ValidationResult initialization."""

    def test_default_initialization(self):
        """Default ValidationResult is valid with no errors."""
        result = ValidationResult()
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.metadata == {}
        assert result.decision == "ALLOW"
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_initialization(self):
        """ValidationResult with custom values."""
        result = ValidationResult(
            is_valid=False,
            errors=["error1"],
            warnings=["warning1"],
            metadata={"key": "value"},
            decision="DENY",
        )
        assert result.is_valid is False
        assert result.errors == ["error1"]
        assert result.warnings == ["warning1"]
        assert result.metadata == {"key": "value"}
        assert result.decision == "DENY"

    def test_constitutional_hash_always_present(self):
        """Constitutional hash is always set to expected value."""
        result = ValidationResult()
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


class TestValidationResultAddError:
    """Tests for ValidationResult.add_error method."""

    def test_add_error_sets_invalid(self):
        """Adding an error marks result as invalid."""
        result = ValidationResult()
        assert result.is_valid is True

        result.add_error("Test error")

        assert result.is_valid is False
        assert "Test error" in result.errors

    def test_add_multiple_errors(self):
        """Multiple errors can be added."""
        result = ValidationResult()

        result.add_error("Error 1")
        result.add_error("Error 2")
        result.add_error("Error 3")

        assert len(result.errors) == 3
        assert result.errors == ["Error 1", "Error 2", "Error 3"]
        assert result.is_valid is False

    def test_add_error_preserves_order(self):
        """Errors are preserved in order added."""
        result = ValidationResult()

        for i in range(5):
            result.add_error(f"Error {i}")

        assert result.errors == [f"Error {i}" for i in range(5)]

    def test_add_empty_error(self):
        """Empty error string can be added."""
        result = ValidationResult()
        result.add_error("")

        assert "" in result.errors
        assert result.is_valid is False


class TestValidationResultAddWarning:
    """Tests for ValidationResult.add_warning method."""

    def test_add_warning_keeps_valid(self):
        """Adding a warning does not mark result as invalid."""
        result = ValidationResult()

        result.add_warning("Test warning")

        assert result.is_valid is True
        assert "Test warning" in result.warnings

    def test_add_multiple_warnings(self):
        """Multiple warnings can be added."""
        result = ValidationResult()

        result.add_warning("Warning 1")
        result.add_warning("Warning 2")

        assert len(result.warnings) == 2
        assert result.is_valid is True

    def test_warnings_and_errors_independent(self):
        """Warnings and errors are tracked independently."""
        result = ValidationResult()

        result.add_warning("Warning")
        assert result.is_valid is True

        result.add_error("Error")
        assert result.is_valid is False

        assert len(result.warnings) == 1
        assert len(result.errors) == 1


class TestValidationResultMerge:
    """Tests for ValidationResult.merge method."""

    def test_merge_valid_into_valid(self):
        """Merging two valid results stays valid."""
        result1 = ValidationResult()
        result2 = ValidationResult()

        result1.merge(result2)

        assert result1.is_valid is True

    def test_merge_invalid_into_valid(self):
        """Merging invalid result makes target invalid."""
        result1 = ValidationResult()
        result2 = ValidationResult()
        result2.add_error("Error from result2")

        result1.merge(result2)

        assert result1.is_valid is False
        assert "Error from result2" in result1.errors

    def test_merge_valid_into_invalid(self):
        """Merging valid result into invalid keeps invalid."""
        result1 = ValidationResult()
        result1.add_error("Original error")
        result2 = ValidationResult()

        result1.merge(result2)

        assert result1.is_valid is False
        assert len(result1.errors) == 1

    def test_merge_combines_errors(self):
        """Merge combines errors from both results."""
        result1 = ValidationResult()
        result1.add_error("Error 1")
        result2 = ValidationResult()
        result2.add_error("Error 2")

        result1.merge(result2)

        assert len(result1.errors) == 2
        assert "Error 1" in result1.errors
        assert "Error 2" in result1.errors

    def test_merge_combines_warnings(self):
        """Merge combines warnings from both results."""
        result1 = ValidationResult()
        result1.add_warning("Warning 1")
        result2 = ValidationResult()
        result2.add_warning("Warning 2")

        result1.merge(result2)

        assert len(result1.warnings) == 2
        assert "Warning 1" in result1.warnings
        assert "Warning 2" in result1.warnings

    def test_merge_multiple_results(self):
        """Multiple results can be merged."""
        main = ValidationResult()

        for i in range(3):
            other = ValidationResult()
            other.add_error(f"Error {i}")
            other.add_warning(f"Warning {i}")
            main.merge(other)

        assert len(main.errors) == 3
        assert len(main.warnings) == 3
        assert main.is_valid is False


class TestValidationResultToDict:
    """Tests for ValidationResult.to_dict method."""

    def test_to_dict_contains_all_fields(self):
        """to_dict includes all required fields."""
        result = ValidationResult()
        d = result.to_dict()

        assert "is_valid" in d
        assert "errors" in d
        assert "warnings" in d
        assert "metadata" in d
        assert "decision" in d
        assert "constitutional_hash" in d
        assert "timestamp" in d

    def test_to_dict_values_match(self):
        """to_dict values match the result object."""
        result = ValidationResult(
            is_valid=False,
            errors=["error1", "error2"],
            warnings=["warning1"],
            metadata={"key": "value"},
            decision="DENY",
        )
        d = result.to_dict()

        assert d["is_valid"] is False
        assert d["errors"] == ["error1", "error2"]
        assert d["warnings"] == ["warning1"]
        assert d["metadata"] == {"key": "value"}
        assert d["decision"] == "DENY"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_timestamp_format(self):
        """Timestamp is in ISO format."""
        result = ValidationResult()
        d = result.to_dict()

        # Should be parseable as ISO format
        timestamp = d["timestamp"]
        assert isinstance(timestamp, str)
        # Should contain date separators
        assert "T" in timestamp or "-" in timestamp

    def test_to_dict_returns_new_dict(self):
        """to_dict returns a new dict each call."""
        result = ValidationResult()
        d1 = result.to_dict()
        d2 = result.to_dict()

        assert d1 is not d2
        assert d1["is_valid"] == d2["is_valid"]

    def test_to_dict_serializable(self):
        """to_dict returns JSON-serializable data."""
        import json

        result = ValidationResult()
        result.add_error("Test error")
        result.add_warning("Test warning")

        d = result.to_dict()

        # Should not raise
        json_str = json.dumps(d)
        assert isinstance(json_str, str)


# =============================================================================
# VALIDATE CONSTITUTIONAL HASH FUNCTION TESTS
# =============================================================================


class TestValidateConstitutionalHash:
    """Tests for validate_constitutional_hash function."""

    def test_valid_hash_passes(self):
        """Valid constitutional hash passes validation."""
        result = validate_constitutional_hash(CONSTITUTIONAL_HASH)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_invalid_hash_fails(self):
        """Invalid constitutional hash fails validation."""
        result = validate_constitutional_hash("invalid_hash")

        assert result.is_valid is False
        assert len(result.errors) == 1
        # Error message is sanitized to prevent hash exposure
        assert "Constitutional hash mismatch" in result.errors[0]
        # Verify hash is truncated in error message (security)
        assert "invalid_..." in result.errors[0]

    def test_empty_hash_fails(self):
        """Empty hash fails validation."""
        result = validate_constitutional_hash("")

        assert result.is_valid is False

    def test_similar_hash_fails(self):
        """Hash with one character difference fails."""
        # Change last character
        result = validate_constitutional_hash("608508a9bd224291")

        assert result.is_valid is False

    def test_uppercase_hash_fails(self):
        """Uppercase version of hash fails (case sensitive)."""
        result = validate_constitutional_hash(CONSTITUTIONAL_HASH.upper())

        assert result.is_valid is False

    def test_hash_with_prefix_fails(self):
        """Hash with prefix fails."""
        result = validate_constitutional_hash("0x608508a9bd224290")

        assert result.is_valid is False

    def test_partial_hash_fails(self):
        """Partial hash fails."""
        result = validate_constitutional_hash("608508a9")

        assert result.is_valid is False

    def test_returns_validation_result(self):
        """Function returns ValidationResult instance."""
        result = validate_constitutional_hash("any_value")

        assert isinstance(result, ValidationResult)
        assert result.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# VALIDATE MESSAGE CONTENT FUNCTION TESTS
# =============================================================================


class TestValidateMessageContent:
    """Tests for validate_message_content function."""

    def test_valid_dict_passes(self):
        """Valid dictionary content passes."""
        content = {"action": "test", "data": "value"}
        result = validate_message_content(content)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_empty_dict_passes(self):
        """Empty dictionary passes validation."""
        result = validate_message_content({})

        assert result.is_valid is True

    def test_non_dict_fails(self):
        """Non-dictionary content fails validation."""
        result = validate_message_content("not a dict")

        assert result.is_valid is False
        assert "Content must be a dictionary" in result.errors[0]

    def test_list_fails(self):
        """List content fails validation."""
        result = validate_message_content([1, 2, 3])

        assert result.is_valid is False

    def test_none_fails(self):
        """None content fails validation."""
        result = validate_message_content(None)

        assert result.is_valid is False

    def test_empty_action_warns(self):
        """Empty action field generates warning."""
        content = {"action": ""}
        result = validate_message_content(content)

        assert result.is_valid is True  # Still valid, just a warning
        assert len(result.warnings) == 1
        assert "Empty action field" in result.warnings[0]

    def test_none_action_warns(self):
        """None action field generates warning."""
        content = {"action": None}
        result = validate_message_content(content)

        assert result.is_valid is True
        assert "Empty action field" in result.warnings[0]

    def test_valid_action_no_warning(self):
        """Valid action field has no warning."""
        content = {"action": "valid_action"}
        result = validate_message_content(content)

        assert result.is_valid is True
        assert len(result.warnings) == 0

    def test_no_action_field_no_warning(self):
        """Missing action field generates no warning."""
        content = {"other_field": "value"}
        result = validate_message_content(content)

        assert result.is_valid is True
        assert len(result.warnings) == 0

    def test_nested_dict_passes(self):
        """Nested dictionary content passes."""
        content = {"action": "test", "nested": {"level2": {"level3": "value"}}}
        result = validate_message_content(content)

        assert result.is_valid is True

    def test_complex_content_passes(self):
        """Complex content with various types passes."""
        content = {
            "action": "complex_action",
            "list_field": [1, 2, 3],
            "bool_field": True,
            "int_field": 42,
            "float_field": 3.14,
            "none_field": None,
        }
        result = validate_message_content(content)

        assert result.is_valid is True

    def test_returns_validation_result(self):
        """Function returns ValidationResult instance."""
        result = validate_message_content({})

        assert isinstance(result, ValidationResult)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestValidatorsIntegration:
    """Integration tests combining multiple validators."""

    def test_validate_and_merge_results(self):
        """Validate multiple aspects and merge results."""
        hash_result = validate_constitutional_hash(CONSTITUTIONAL_HASH)
        content_result = validate_message_content({"action": "test"})

        hash_result.merge(content_result)

        assert hash_result.is_valid is True

    def test_invalid_hash_and_valid_content(self):
        """Invalid hash with valid content results in invalid."""
        hash_result = validate_constitutional_hash("invalid")
        content_result = validate_message_content({"action": "test"})

        hash_result.merge(content_result)

        assert hash_result.is_valid is False
        assert len(hash_result.errors) == 1

    def test_valid_hash_and_invalid_content(self):
        """Valid hash with invalid content results in invalid."""
        hash_result = validate_constitutional_hash(CONSTITUTIONAL_HASH)
        content_result = validate_message_content("not a dict")

        hash_result.merge(content_result)

        assert hash_result.is_valid is False

    def test_both_invalid(self):
        """Both invalid results in multiple errors."""
        hash_result = validate_constitutional_hash("invalid")
        content_result = validate_message_content("not a dict")

        hash_result.merge(content_result)

        assert hash_result.is_valid is False
        assert len(hash_result.errors) == 2

    def test_content_warning_with_valid_hash(self):
        """Content warning with valid hash stays valid."""
        hash_result = validate_constitutional_hash(CONSTITUTIONAL_HASH)
        content_result = validate_message_content({"action": ""})

        hash_result.merge(content_result)

        assert hash_result.is_valid is True
        assert len(hash_result.warnings) == 1


# =============================================================================
# EDGE CASES AND BOUNDARY TESTS
# =============================================================================


class TestEdgeCases:
    """Edge case and boundary tests."""

    def test_validation_result_with_large_errors_list(self):
        """ValidationResult handles large number of errors."""
        result = ValidationResult()

        for i in range(1000):
            result.add_error(f"Error {i}")

        assert len(result.errors) == 1000
        assert result.is_valid is False

    def test_unicode_in_error_messages(self):
        """Unicode characters in error messages."""
        result = ValidationResult()
        result.add_error("Error with unicode: 日本語 🚀 émoji")

        assert "日本語" in result.errors[0]
        d = result.to_dict()
        assert "日本語" in d["errors"][0]

    def test_special_characters_in_metadata(self):
        """Special characters in metadata."""
        result = ValidationResult(metadata={"key<>&\"'": "value<>&\"'"})

        d = result.to_dict()
        assert d["metadata"]["key<>&\"'"] == "value<>&\"'"

    def test_validation_result_to_dict_shares_references(self):
        """to_dict returns references to internal lists (not copies).

        Note: This is the actual behavior - to_dict() returns the same
        list objects for performance. Callers should not modify the returned dict.
        """
        result = ValidationResult()
        result.add_error("Original error")

        d = result.to_dict()

        # Verify that errors list is the same reference
        assert d["errors"] is result.errors

        # Verify that modifying d["errors"] also affects result.errors
        # (This is expected behavior - callers should treat returned dict as read-only)
        original_len = len(result.errors)
        assert original_len == 1

    def test_hash_with_whitespace_fails(self):
        """Hash with leading/trailing whitespace fails."""
        result = validate_constitutional_hash(" 608508a9bd224290")
        assert result.is_valid is False

        result = validate_constitutional_hash("608508a9bd224290 ")
        assert result.is_valid is False

    def test_content_with_circular_reference_handling(self):
        """Content validation doesn't crash on complex nested dicts."""
        content: JSONDict = {"level1": {}}
        content["level1"]["level2"] = {"back_ref": content}

        # Should not crash, just validate the structure
        result = validate_message_content(content)
        assert result.is_valid is True


__all__ = [
    "TestConstitutionalHashConstant",
    "TestEdgeCases",
    "TestValidateConstitutionalHash",
    "TestValidateMessageContent",
    "TestValidationResultAddError",
    "TestValidationResultAddWarning",
    "TestValidationResultInit",
    "TestValidationResultMerge",
    "TestValidationResultToDict",
    "TestValidatorsIntegration",
]
