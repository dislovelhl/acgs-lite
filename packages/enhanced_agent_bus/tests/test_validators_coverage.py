# Constitutional Hash: 608508a9bd224290
"""
ACGS-2 Validators Coverage Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests to achieve ≥95% coverage of validators.py (58 statements).
"""

import hmac
from unittest.mock import MagicMock, patch

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

from enhanced_agent_bus.models import MessageStatus
from enhanced_agent_bus.validators import (
    CONSTITUTIONAL_HASH,
    ValidationResult,
    validate_constitutional_hash,
    validate_message_content,
)


class TestValidationResultExtended:
    """Extended tests for ValidationResult dataclass."""

    def test_default_values(self):
        """ValidationResult has correct defaults."""
        result = ValidationResult()
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.metadata == {}
        assert result.decision == "ALLOW"
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_add_error_makes_invalid(self):
        """Adding an error sets is_valid to False."""
        result = ValidationResult()
        assert result.is_valid is True
        result.add_error("test error")
        assert result.is_valid is False
        assert "test error" in result.errors

    def test_add_multiple_errors(self):
        """Multiple errors can be added."""
        result = ValidationResult()
        result.add_error("error 1")
        result.add_error("error 2")
        assert len(result.errors) == 2
        assert result.is_valid is False

    def test_add_warning_preserves_validity(self):
        """Adding warning does not change is_valid."""
        result = ValidationResult()
        result.add_warning("test warning")
        assert result.is_valid is True
        assert "test warning" in result.warnings

    def test_merge_combines_results(self):
        """Merge combines errors and warnings."""
        result1 = ValidationResult()
        result1.add_warning("warning 1")

        result2 = ValidationResult()
        result2.add_error("error from 2")
        result2.add_warning("warning 2")

        result1.merge(result2)
        assert result1.is_valid is False
        assert "error from 2" in result1.errors
        assert "warning 1" in result1.warnings
        assert "warning 2" in result1.warnings

    def test_merge_preserves_validity_when_both_valid(self):
        """Merge keeps valid if both are valid."""
        result1 = ValidationResult()
        result2 = ValidationResult()
        result1.merge(result2)
        assert result1.is_valid is True

    def test_to_dict_structure(self):
        """to_dict returns correct structure."""
        result = ValidationResult()
        result.add_error("test error")
        result.add_warning("test warning")
        result.metadata["key"] = "value"

        d = result.to_dict()
        assert d["is_valid"] is False
        assert d["errors"] == ["test error"]
        assert d["warnings"] == ["test warning"]
        assert d["metadata"] == {"key": "value"}
        assert d["decision"] == "ALLOW"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "timestamp" in d


class TestValidateConstitutionalHash:
    """Tests for validate_constitutional_hash function."""

    def test_valid_hash(self):
        """Valid constitutional hash passes."""
        result = validate_constitutional_hash(CONSTITUTIONAL_HASH)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_invalid_hash_string(self):
        """Invalid hash string fails with error."""
        result = validate_constitutional_hash("wrong_hash_value")
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "mismatch" in result.errors[0].lower()

    def test_non_string_hash(self):
        """Non-string hash type fails."""
        result = validate_constitutional_hash(12345)
        assert result.is_valid is False
        assert "string" in result.errors[0].lower()

    def test_none_hash(self):
        """None hash fails."""
        result = validate_constitutional_hash(None)
        assert result.is_valid is False

    def test_empty_string_hash(self):
        """Empty string hash fails."""
        result = validate_constitutional_hash("")
        assert result.is_valid is False

    def test_partial_hash_sanitized(self):
        """Error message shows only partial hash for security."""
        result = validate_constitutional_hash("1234567890abcdef")  # pragma: allowlist secret
        assert result.is_valid is False
        # Should only show first 8 chars + ...
        error_msg = result.errors[0]
        assert "12345678..." in error_msg


class TestValidateMessageContent:
    """Tests for validate_message_content function."""

    def test_valid_content(self):
        """Valid dict content passes."""
        result = validate_message_content({"action": "test"})
        assert result.is_valid is True

    def test_non_dict_content(self):
        """Non-dict content fails."""
        result = validate_message_content("string content")
        assert result.is_valid is False
        assert "dictionary" in result.errors[0].lower()

    def test_empty_action_warning(self):
        """Empty action field generates warning."""
        result = validate_message_content({"action": ""})
        assert result.is_valid is True  # Still valid, just warning
        assert len(result.warnings) == 1
        assert "action" in result.warnings[0].lower()

    def test_none_action_warning(self):
        """None action field generates warning."""
        result = validate_message_content({"action": None})
        assert result.is_valid is True
        assert len(result.warnings) == 1

    def test_content_without_action(self):
        """Content without action field passes."""
        result = validate_message_content({"data": "value"})
        assert result.is_valid is True
        assert len(result.warnings) == 0

    def test_list_content_fails(self):
        """List content fails validation."""
        result = validate_message_content([1, 2, 3])
        assert result.is_valid is False

    def test_empty_dict_passes(self):
        """Empty dict passes validation."""
        result = validate_message_content({})
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# ValidationResult — default field independence (mutable defaults)
# ---------------------------------------------------------------------------


class TestValidationResultFieldIndependence:
    def test_errors_list_not_shared_across_instances(self):
        r1 = ValidationResult()
        r2 = ValidationResult()
        r1.errors.append("x")
        assert r2.errors == []

    def test_warnings_list_not_shared_across_instances(self):
        r1 = ValidationResult()
        r2 = ValidationResult()
        r1.warnings.append("w")
        assert r2.warnings == []

    def test_metadata_dict_not_shared_across_instances(self):
        r1 = ValidationResult()
        r2 = ValidationResult()
        r1.metadata["k"] = "v"
        assert r2.metadata == {}

    def test_default_status_is_validated(self):
        result = ValidationResult()
        assert result.status == MessageStatus.VALIDATED

    def test_default_pqc_metadata_is_none(self):
        result = ValidationResult()
        assert result.pqc_metadata is None


# ---------------------------------------------------------------------------
# ValidationResult.to_dict — additional branches
# ---------------------------------------------------------------------------


class TestValidationResultToDictExtra:
    def test_to_dict_no_pqc_metadata_key_when_none(self):
        """pqc_metadata key must be absent when pqc_metadata is None."""
        result = ValidationResult()
        d = result.to_dict()
        assert "pqc_metadata" not in d

    def test_to_dict_includes_pqc_metadata_when_present(self):
        """pqc_metadata key is included when pqc_metadata is set."""
        pqc_mock = MagicMock()
        pqc_mock.to_dict.return_value = {"algorithm": "CRYSTALS-Kyber"}
        result = ValidationResult(pqc_metadata=pqc_mock)
        d = result.to_dict()
        assert "pqc_metadata" in d
        assert d["pqc_metadata"] == {"algorithm": "CRYSTALS-Kyber"}

    def test_to_dict_calls_pqc_metadata_to_dict(self):
        pqc_mock = MagicMock()
        pqc_mock.to_dict.return_value = {}
        result = ValidationResult(pqc_metadata=pqc_mock)
        result.to_dict()
        pqc_mock.to_dict.assert_called_once()

    def test_to_dict_timestamp_is_iso_string(self):
        from datetime import datetime, timezone

        result = ValidationResult()
        d = result.to_dict()
        # Should parse without raising
        datetime.fromisoformat(d["timestamp"])

    def test_to_dict_with_custom_metadata(self):
        result = ValidationResult(metadata={"foo": "bar"})
        d = result.to_dict()
        assert d["metadata"] == {"foo": "bar"}

    def test_to_dict_after_error_shows_invalid(self):
        result = ValidationResult()
        result.add_error("bad input")
        d = result.to_dict()
        assert d["is_valid"] is False
        assert "bad input" in d["errors"]

    def test_to_dict_after_warning_shows_warning(self):
        result = ValidationResult()
        result.add_warning("watch out")
        d = result.to_dict()
        assert "watch out" in d["warnings"]


# ---------------------------------------------------------------------------
# ValidationResult.merge — additional branches
# ---------------------------------------------------------------------------


class TestValidationResultMergeExtra:
    def test_merge_invalid_into_valid_sets_invalid(self):
        base = ValidationResult()
        other = ValidationResult()
        other.add_error("problem")
        base.merge(other)
        assert base.is_valid is False

    def test_merge_copies_errors_to_base(self):
        base = ValidationResult()
        other = ValidationResult()
        other.add_error("remote error")
        base.merge(other)
        assert "remote error" in base.errors

    def test_merge_accumulates_existing_base_errors(self):
        base = ValidationResult()
        base.add_error("local error")
        other = ValidationResult()
        other.add_error("remote error")
        base.merge(other)
        assert len(base.errors) == 2

    def test_merge_valid_other_preserves_base_invalid(self):
        base = ValidationResult()
        base.add_error("base error")
        other = ValidationResult()  # valid
        base.merge(other)
        assert base.is_valid is False

    def test_merge_multiple_warnings_accumulate(self):
        base = ValidationResult()
        base.add_warning("w1")
        other = ValidationResult()
        other.add_warning("w2")
        other.add_warning("w3")
        base.merge(other)
        assert len(base.warnings) == 3


# ---------------------------------------------------------------------------
# validate_constitutional_hash — additional branches
# ---------------------------------------------------------------------------


class TestValidateConstitutionalHashExtra:
    def test_correct_hash_returns_validation_result(self):
        result = validate_constitutional_hash(CONSTITUTIONAL_HASH)
        assert isinstance(result, ValidationResult)

    def test_exactly_8_char_hash_not_truncated_in_error(self):
        """Hashes of length ≤8 are shown in full (no ellipsis)."""
        result = validate_constitutional_hash("12345678")
        assert result.is_valid is False
        error = result.errors[0]
        # len "12345678" == 8, so condition `len > 8` is False → no truncation
        assert "..." not in error
        assert "12345678" in error

    def test_9_char_hash_truncated_in_error(self):
        """Hashes longer than 8 chars are truncated."""
        result = validate_constitutional_hash("123456789")
        error = result.errors[0]
        assert "12345678..." in error

    def test_uppercase_hash_is_invalid(self):
        result = validate_constitutional_hash(CONSTITUTIONAL_HASH.upper())
        assert result.is_valid is False

    def test_close_but_wrong_hash_is_invalid(self):
        wrong = CONSTITUTIONAL_HASH[:-1] + "X"
        result = validate_constitutional_hash(wrong)
        assert result.is_valid is False

    def test_list_input_is_invalid(self):
        result = validate_constitutional_hash([CONSTITUTIONAL_HASH])
        assert result.is_valid is False
        assert any("string" in e.lower() for e in result.errors)

    def test_dict_input_is_invalid(self):
        result = validate_constitutional_hash({"hash": CONSTITUTIONAL_HASH})
        assert result.is_valid is False

    def test_unicode_encode_error_treated_as_mismatch(self):
        """When hmac.compare_digest raises UnicodeEncodeError, result is invalid."""
        with patch(
            "hmac.compare_digest",
            side_effect=UnicodeEncodeError("utf-8", "", 0, 1, "bad char"),
        ):
            result = validate_constitutional_hash(CONSTITUTIONAL_HASH)
        assert result.is_valid is False


# ---------------------------------------------------------------------------
# validate_message_content — additional branches
# ---------------------------------------------------------------------------


class TestValidateMessageContentExtra:
    def test_integer_input_is_invalid(self):
        result = validate_message_content(42)
        assert result.is_valid is False
        assert any("dictionary" in e.lower() for e in result.errors)

    def test_bool_input_is_invalid(self):
        result = validate_message_content(True)
        assert result.is_valid is False

    def test_zero_as_action_generates_warning(self):
        """Falsy integer action values trigger empty-action warning."""
        result = validate_message_content({"action": 0})
        assert len(result.warnings) == 1

    def test_false_as_action_generates_warning(self):
        result = validate_message_content({"action": False})
        assert len(result.warnings) == 1

    def test_non_dict_returns_early_no_warnings(self):
        """Non-dict input returns immediately; no warnings added."""
        result = validate_message_content(42)
        assert result.warnings == []

    def test_dict_with_nested_values_is_valid(self):
        result = validate_message_content({"nested": {"a": 1}})
        assert result.is_valid is True

    def test_dict_without_action_key_no_warning(self):
        result = validate_message_content({"other_key": "value"})
        assert result.warnings == []

    def test_non_empty_action_no_warning(self):
        result = validate_message_content({"action": "do_something"})
        assert result.warnings == []
        assert result.is_valid is True


# ---------------------------------------------------------------------------
# Module __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_constitutional_hash_exported(self):
        import enhanced_agent_bus.validators as mod

        assert "CONSTITUTIONAL_HASH" in mod.__all__
        assert mod.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_validation_result_exported(self):
        import enhanced_agent_bus.validators as mod

        assert "ValidationResult" in mod.__all__

    def test_validate_constitutional_hash_exported(self):
        import enhanced_agent_bus.validators as mod

        assert "validate_constitutional_hash" in mod.__all__
        assert callable(mod.validate_constitutional_hash)

    def test_validate_message_content_exported(self):
        import enhanced_agent_bus.validators as mod

        assert "validate_message_content" in mod.__all__
        assert callable(mod.validate_message_content)

    def test_all_names_resolvable(self):
        import enhanced_agent_bus.validators as mod

        for name in mod.__all__:
            assert hasattr(mod, name), f"__all__ lists missing attribute: {name}"
