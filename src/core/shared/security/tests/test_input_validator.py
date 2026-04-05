"""
Tests for ACGS-2 Input Validation Framework

Constitutional Hash: 608508a9bd224290
"""

import pytest
from fastapi import HTTPException

from src.core.shared.security.input_validator import InputValidator, _contains_injection


class TestInputValidator:
    """Test the InputValidator's sanitization and injection detection."""

    def test_sanitize_string(self):
        """Test basic string sanitization."""
        assert InputValidator.sanitize_string("  hello  ") == "hello"
        assert InputValidator.sanitize_string("hello\x00world") == "helloworld"
        assert InputValidator.sanitize_string(123) == 123  # Non-string returned as is

    def test_sql_injection_detection(self):
        """Test detection of SQL injection patterns."""
        injections = [
            "SELECT * FROM users",
            "UNION SELECT password FROM users",
            "INSERT INTO logs VALUES ('a')",
            "UPDATE config SET value='1'",
            "DELETE FROM sessions",
            "DROP TABLE audit_trail",
            "admin' OR '1'='1'",
        ]
        for payload in injections:
            assert InputValidator.check_injection(payload) is True

    def test_nosql_injection_detection(self):
        """Test detection of NoSQL injection patterns."""
        injections = [
            '{"$gt": ""}',
            '{"$ne": null}',
            '{"$or": []}',
        ]
        for payload in injections:
            assert InputValidator.check_injection(payload) is True

    def test_xss_detection(self):
        """Test detection of XSS patterns."""
        injections = [
            "<script>alert(1)</script>",
            "<IMG SRC=javascript:alert('XSS')>",
            "<body onload=alert('XSS')>",
        ]
        for payload in injections:
            assert InputValidator.check_injection(payload) is True

    def test_clean_input(self):
        """Test that clean inputs are not flagged."""
        clean_inputs = [
            "How do I use the AI agent?",
            "The weather is nice today.",
            "Normal text without special commands.",
            "12345",
        ]
        for text in clean_inputs:
            assert InputValidator.check_injection(text) is False

    def test_validate_path(self):
        """Test path traversal protection."""
        base_dir = "/tmp/safe"

        # Safe path
        InputValidator.validate_path("/tmp/safe/file.txt", base_dir)

        # Traversal attempt
        with pytest.raises(HTTPException) as exc:
            InputValidator.validate_path("/etc/passwd", base_dir)
        assert exc.value.status_code == 400

    def test_contains_injection_recursive(self):
        """Test recursive injection checking in dicts and lists."""
        payload = {"query": "safe", "metadata": {"user": "john", "attempt": "DROP TABLE users"}}
        assert _contains_injection(payload) is True

        payload_list = ["safe", ["nested", "SELECT * FROM secrets"]]
        assert _contains_injection(payload_list) is True
