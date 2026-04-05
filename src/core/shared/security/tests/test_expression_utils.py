"""
Tests for ACGS-2 Shared Expression Evaluation Utilities

Tests the security of safe_eval_expr() and PII redaction functions.

Constitutional Hash: 608508a9bd224290
"""

import pytest

from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError
from src.core.shared.security.expression_utils import redact_pii, safe_eval_expr


class TestSafeEvalExpr:
    """Test safe expression evaluation with comprehensive edge cases."""

    def test_basic_arithmetic(self):
        """Test basic arithmetic operations."""
        assert safe_eval_expr("2 + 3") == 5.0
        assert safe_eval_expr("10 - 4") == 6.0
        assert safe_eval_expr("3 * 4") == 12.0
        assert safe_eval_expr("8 / 2") == 4.0
        assert safe_eval_expr("2 ** 3") == 8.0

    def test_negative_numbers(self):
        """Test negative numbers and unary minus."""
        assert safe_eval_expr("-5") == -5.0
        assert safe_eval_expr("10 + -3") == 7.0
        assert safe_eval_expr("-2 * 3") == -6.0

    def test_floats(self):
        """Test floating point operations."""
        assert safe_eval_expr("3.5 + 2.1") == 5.6
        assert safe_eval_expr("10.0 / 3.0") == pytest.approx(3.3333333333333335)

    def test_precedence(self):
        """Test operator precedence."""
        assert safe_eval_expr("2 + 3 * 4") == 14.0
        assert safe_eval_expr("(2 + 3) * 4") == 20.0
        assert safe_eval_expr("2 ** 3 + 1") == 9.0

    def test_complex_expressions(self):
        """Test complex but valid expressions."""
        assert safe_eval_expr("2 + 3 * 4 - 6 / 2") == 11.0
        assert safe_eval_expr("(2 + 3) * (4 - 1)") == 15.0

    def test_invalid_syntax(self):
        """Test rejection of invalid syntax."""
        with pytest.raises((ValueError, ACGSValidationError), match="Invalid expression"):
            safe_eval_expr("2 +")

        with pytest.raises((ValueError, ACGSValidationError), match="Invalid expression"):
            safe_eval_expr("2 3")

        with pytest.raises((ValueError, ACGSValidationError), match="Invalid expression"):
            safe_eval_expr("")

    def test_code_injection_attempts(self):
        """Test that code injection attempts are blocked."""
        # Function calls
        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("exec('print(1)')")

        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("eval('2+2')")

        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("__import__('os')")

        # Attribute access
        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("x.__class__")

        # Variable access (not allowed)
        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("x + 1")

        # String operations
        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("'hello' + 'world'")

        # List/dict operations
        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("[1,2,3][0]")

        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("{'a': 1}['a']")

    def test_malformed_expressions(self):
        """Test various malformed expressions."""
        malformed = [
            "2 + (3",
            ")2 + 3(",
            "2 + 3)",
            "(2 + 3",
            "2 + 3,",
            "2 + ;",
            "2 + import os",
            "2 + lambda x: x",
            "2 + def f(): pass",
            "2 + class C: pass",
            "2 + if True: 1 else: 2",
            "2 + for x in []: pass",
            "2 + while True: pass",
            "2 + try: 1 except: 2",
        ]

        for expr in malformed:
            with pytest.raises((ValueError, ACGSValidationError)):
                safe_eval_expr(expr)

    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Very large numbers
        result = safe_eval_expr("999999999999999999999 + 1")
        assert result == 1e21  # 1000000000000000000000 in scientific notation

        # Very small numbers
        assert safe_eval_expr("0.0000000000000001") == 1e-16

        # Zero operations
        assert safe_eval_expr("0 + 0") == 0.0
        assert safe_eval_expr("0 * 5") == 0.0
        assert safe_eval_expr("5 / 1") == 5.0

        # Division by zero (should work as it raises ZeroDivisionError)
        with pytest.raises((ValueError, ACGSValidationError)):  # Our wrapper catches all exceptions
            safe_eval_expr("5 / 0")

    def test_only_numeric_constants(self):
        """Test that only numeric constants are allowed."""
        # Valid numeric constants
        assert safe_eval_expr("42") == 42.0
        assert safe_eval_expr("3.14159") == 3.14159
        assert safe_eval_expr("1e10") == 1e10

        # Invalid non-numeric constants
        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("None")

        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("True")

        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("False")

        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("'string'")

        with pytest.raises((ValueError, ACGSValidationError)):
            safe_eval_expr("b'bytes'")


class TestRedactPII:
    """Test PII redaction functionality."""

    def test_complete_redaction(self):
        """Test complete removal of sensitive fields."""
        payload = {
            "content_preview": "This is sensitive content",
            "content": "Full content here",
            "password": "secret123",
            "api_key": "sk-123456789",
            "token": "bearer-token",
            "secret": "super-secret",
            "safe_field": "this is safe",
        }

        redacted = redact_pii(payload)

        # Sensitive fields should be completely removed
        assert "content_preview" not in redacted
        assert "content" not in redacted
        assert "password" not in redacted
        assert "api_key" not in redacted
        assert "token" not in redacted
        assert "secret" not in redacted

        # Safe fields should remain
        assert redacted["safe_field"] == "this is safe"

    def test_hash_based_redaction(self):
        """Test hash-based redaction for traceability."""
        payload = {
            "metadata": {"user": "john", "session": "abc123"},
            "user_id": "user-123",
            "email": "john@example.com",
            "safe_field": "this is safe",
        }

        redacted = redact_pii(payload)

        # Hash fields should be replaced with hash prefix
        assert redacted["metadata"].startswith("<redacted_hash:")
        assert redacted["user_id"].startswith("<redacted_hash:")
        assert redacted["email"].startswith("<redacted_hash:")

        # Hash should be consistent for same input
        payload2 = {"metadata": {"user": "john", "session": "abc123"}, "user_id": "user-123"}
        redacted2 = redact_pii(payload2)

        assert redacted["metadata"] == redacted2["metadata"]
        assert redacted["user_id"] == redacted2["user_id"]

        # Safe fields should remain
        assert redacted["safe_field"] == "this is safe"

    def test_complex_data_types(self):
        """Test redaction with complex data types."""
        payload = {
            "metadata": ["item1", "item2", {"nested": "value"}],
            "user_id": 12345,  # Non-string
            "email": None,  # None value
            "safe_field": "safe",
        }

        redacted = redact_pii(payload)

        # Complex types should be hashed as JSON
        assert redacted["metadata"].startswith("<redacted_hash:")
        assert redacted["user_id"].startswith("<redacted_hash:")
        assert redacted["email"] is None  # None values should remain None

        assert redacted["safe_field"] == "safe"

    def test_empty_and_none_values(self):
        """Test handling of empty and None values."""
        payload = {
            "metadata": {},
            "user_id": "",
            "email": None,
            "content": None,
            "safe_field": "safe",
        }

        redacted = redact_pii(payload)

        # Empty dict/list should still be hashed
        assert redacted["metadata"].startswith("<redacted_hash:")
        assert redacted["user_id"].startswith("<redacted_hash:")  # Empty string gets hashed
        assert redacted["email"] is None  # None remains None

        # Sensitive None fields get removed
        assert "content" not in redacted

        assert redacted["safe_field"] == "safe"

    def test_no_sensitive_fields(self):
        """Test payload with no sensitive fields."""
        payload = {
            "safe_field1": "value1",
            "safe_field2": {"nested": "data"},
            "safe_field3": ["list", "data"],
        }

        redacted = redact_pii(payload)

        # Should be unchanged
        assert redacted == payload

    def test_all_sensitive_fields(self):
        """Test payload with only sensitive fields."""
        payload = {
            "content_preview": "preview",
            "content": "content",
            "password": "pass",
            "api_key": "key",
            "token": "token",
            "secret": "secret",
            "metadata": "meta",
            "user_id": "user",
            "email": "email",
        }

        redacted = redact_pii(payload)

        # Should only contain hashed fields
        assert len(redacted) == 3  # metadata, user_id, email
        assert all(v.startswith("<redacted_hash:") for v in redacted.values())

    def test_nested_structures(self):
        """Test redaction preserves nested structure."""
        original_payload = {
            "level1": {
                "level2": {
                    "content": "sensitive",
                    "metadata": "also_sensitive",
                    "safe": "preserved",
                }
            },
            "content": "also_sensitive",
        }

        redacted = redact_pii(original_payload)

        # Structure should be preserved
        assert "level1" in redacted
        assert "level2" in redacted["level1"]
        assert "safe" in redacted["level1"]["level2"]

        # Sensitive fields should be removed
        assert "content" not in redacted
        assert "content" not in redacted["level1"]["level2"]

        # Metadata should be hashed
        assert redacted["level1"]["level2"]["metadata"].startswith("<redacted_hash:")


if __name__ == "__main__":
    pytest.main([__file__])
