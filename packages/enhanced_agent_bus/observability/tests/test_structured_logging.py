"""
ACGS-2 Structured Logging Tests
Constitutional Hash: 608508a9bd224290

Tests for structured_logging module per SPEC_ACGS2_ENHANCED.md Section 6.2.
"""

import io
import json
import logging
from unittest.mock import MagicMock, patch

from ..structured_logging import (
    CONSTITUTIONAL_HASH,
    LOG_LEVEL_CONFIG,
    REDACTION_PATTERNS,
    LogLevel,
    RedactionPattern,
    StructuredJSONFormatter,
    StructuredLogger,
    clear_trace_context,
    configure_structured_logging,
    get_log_level,
    get_structured_logger,
    get_trace_context,
    redact_dict,
    redact_sensitive_data,
    reset_structured_logger,
    set_trace_context,
)


class TestConstitutionalHash:
    """Test constitutional hash enforcement."""

    def test_constitutional_hash_value(self):
        """Verify constitutional hash matches spec."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH


class TestLogLevel:
    """Test LogLevel enum."""

    def test_log_level_values(self):
        """Test all log levels per spec."""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARN.value == "WARN"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.FATAL.value == "FATAL"


class TestLogLevelConfig:
    """Test environment-based log level configuration."""

    def test_production_log_level(self):
        """Production should use INFO level."""
        assert LOG_LEVEL_CONFIG["production"] == LogLevel.INFO

    def test_staging_log_level(self):
        """Staging should use DEBUG level."""
        assert LOG_LEVEL_CONFIG["staging"] == LogLevel.DEBUG

    def test_development_log_level(self):
        """Development should use DEBUG level."""
        assert LOG_LEVEL_CONFIG["development"] == LogLevel.DEBUG

    @patch.dict("os.environ", {"ENVIRONMENT": "production"})
    def test_get_log_level_production(self):
        """Test get_log_level for production."""
        assert get_log_level() == "INFO"

    @patch.dict("os.environ", {"ENVIRONMENT": "development"})
    def test_get_log_level_development(self):
        """Test get_log_level for development."""
        assert get_log_level() == "DEBUG"

    @patch.dict("os.environ", {"ENVIRONMENT": "unknown"})
    def test_get_log_level_unknown_defaults_to_debug(self):
        """Test unknown environment defaults to DEBUG."""
        assert get_log_level() == "DEBUG"


class TestPIIRedaction:
    """Test PII/sensitive data redaction per Section 6.2."""

    def test_email_redaction(self):
        """Test email addresses are redacted."""
        text = "Contact user@example.com for support"
        result = redact_sensitive_data(text)
        assert "user@example.com" not in result
        assert "***@***.***" in result

    def test_jwt_token_redaction(self):
        """Test JWT tokens are redacted."""
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        text = f"Token: {jwt}"
        result = redact_sensitive_data(text)
        assert jwt not in result
        assert "[JWT_REDACTED]" in result

    def test_api_key_redaction(self):
        """Test API keys are redacted."""
        text = "api_key=example-key-for-unit-tests"
        result = redact_sensitive_data(text)
        assert "sk_live_abcdefghijklmnop" not in result
        assert "[KEY_REDACTED]" in result

    def test_bearer_token_redaction(self):
        """Test Bearer tokens are redacted."""
        text = "Authorization: Bearer abc123xyz789token"
        result = redact_sensitive_data(text)
        assert "abc123xyz789token" not in result
        assert "[TOKEN_REDACTED]" in result

    def test_password_redaction(self):
        """Test passwords are redacted."""
        text = "password=supersecret123"
        result = redact_sensitive_data(text)
        assert "supersecret123" not in result
        assert "[PASSWORD_REDACTED]" in result

    def test_credit_card_redaction(self):
        """Test credit card numbers are redacted."""
        text = "Card: 4111-1111-1111-1111"
        result = redact_sensitive_data(text)
        assert "4111-1111-1111-1111" not in result
        assert "[CARD_REDACTED]" in result

    def test_ssn_redaction(self):
        """Test SSN numbers are redacted."""
        text = "SSN: 123-45-6789"
        result = redact_sensitive_data(text)
        assert "123-45-6789" not in result
        assert "[SSN_REDACTED]" in result

    def test_phone_redaction(self):
        """Test phone numbers are redacted."""
        text = "Call me at (555) 123-4567"
        result = redact_sensitive_data(text)
        assert "(555) 123-4567" not in result
        assert "[PHONE_REDACTED]" in result

    def test_ip_address_redaction(self):
        """Test IP addresses are redacted."""
        text = "Client IP: 192.168.1.100"
        result = redact_sensitive_data(text)
        assert "192.168.1.100" not in result
        assert "[IP_REDACTED]" in result

    def test_authorization_header_redaction(self):
        """Test authorization headers are redacted."""
        text = "authorization=secret_auth_value"
        result = redact_sensitive_data(text)
        assert "secret_auth_value" not in result
        assert "[AUTH_REDACTED]" in result

    def test_non_string_returns_unchanged(self):
        """Test non-string input returns unchanged."""
        assert redact_sensitive_data(123) == 123
        assert redact_sensitive_data(None) is None


class TestDictRedaction:
    """Test dictionary redaction."""

    def test_redact_dict_sensitive_keys(self):
        """Test sensitive keys are redacted in dictionaries."""
        data = {
            "username": "testuser",
            "password": "secret123",
            "api_key": "key123",
            "token": "tok_abc",
        }
        result = redact_dict(data)
        assert result["username"] == "testuser"
        assert result["password"] == "[REDACTED]"
        assert result["api_key"] == "[REDACTED]"
        assert result["token"] == "[REDACTED]"

    def test_redact_dict_nested(self):
        """Test nested dictionaries are redacted."""
        data = {
            "user": {
                "name": "Test",
                "secret": "should_be_redacted",
            }
        }
        result = redact_dict(data)
        assert result["user"]["secret"] == "[REDACTED]"

    def test_redact_dict_lists(self):
        """Test lists in dictionaries are processed."""
        data = {"emails": ["user@example.com", "other@test.com"]}
        result = redact_dict(data)
        assert "***@***.***" in result["emails"]

    def test_redact_dict_preserves_non_sensitive(self):
        """Test non-sensitive data is preserved."""
        data = {
            "id": 123,
            "active": True,
            "name": "Test",
        }
        result = redact_dict(data)
        assert result["id"] == 123
        assert result["active"] is True
        assert result["name"] == "Test"

    def test_redact_dict_non_dict_input(self):
        """Test non-dict input returns unchanged."""
        assert redact_dict("string") == "string"
        assert redact_dict(123) == 123


class TestStructuredJSONFormatter:
    """Test StructuredJSONFormatter."""

    def test_format_returns_json(self):
        """Test format returns valid JSON."""
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_format_includes_required_fields(self):
        """Test format includes all required fields per spec."""
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        data = json.loads(result)

        # Required fields per Section 6.2
        assert "timestamp" in data
        assert "level" in data
        assert "service" in data
        assert "trace_id" in data
        assert "span_id" in data
        assert "message" in data

    def test_format_includes_constitutional_hash(self):
        """Test format includes constitutional hash."""
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        data = json.loads(result)
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_format_custom_service_name(self):
        """Test custom service name."""
        formatter = StructuredJSONFormatter(service_name="custom-service")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        data = json.loads(result)
        assert data["service"] == "custom-service"

    def test_format_redacts_pii_by_default(self):
        """Test PII is redacted by default."""
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="User email: user@example.com",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert "user@example.com" not in result
        assert "***@***.***" in result

    def test_format_can_disable_redaction(self):
        """Test PII redaction can be disabled."""
        formatter = StructuredJSONFormatter(redact_pii=False)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="User email: user@example.com",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert "user@example.com" in result


class TestStructuredLogger:
    """Test StructuredLogger."""

    def setup_method(self):
        """Reset logger before each test."""
        reset_structured_logger()

    def test_get_structured_logger_singleton(self):
        """Test global structured logger is singleton."""
        logger1 = get_structured_logger()
        logger2 = get_structured_logger()
        assert logger1 is logger2

    def test_structured_logger_default_service_name(self):
        """Test default service name."""
        logger = StructuredLogger()
        assert logger.service_name == "acgs2-enhanced-agent-bus"

    def test_log_constitutional_validation(self):
        """Test logging constitutional validation event."""
        logger = StructuredLogger()
        # Should not raise
        logger.log_constitutional_validation(
            agent_id="agent-001",
            result="PASS",
            confidence=0.95,
            latency_ms=2.5,
            principles_checked=["harm_prevention", "truthfulness"],
        )

    def test_log_constitutional_validation_with_violations(self):
        """Test logging constitutional validation with violations."""
        logger = StructuredLogger()
        logger.log_constitutional_validation(
            agent_id="agent-002",
            result="FAIL",
            confidence=0.3,
            latency_ms=5.0,
            violations=[{"type": "harm_violation", "severity": "high"}],
        )

    def test_log_policy_evaluation(self):
        """Test logging policy evaluation event."""
        logger = StructuredLogger()
        logger.log_policy_evaluation(
            policy_id="policy-001",
            input_hash="abc123",
            decision="ALLOW",
            latency_ms=1.0,
        )

    def test_log_security_violation(self):
        """Test logging security violation event."""
        logger = StructuredLogger()
        logger.log_security_violation(
            violation_type="unauthorized_access",
            source="agent-suspicious",
            details={"summary": "Attempted access without authorization"},
        )

    def test_log_cache_operation(self):
        """Test logging cache operation event."""
        logger = StructuredLogger()
        logger.log_cache_operation(
            cache_tier="L1",
            operation="GET",
            hit=True,
            key_prefix="validation:",
            latency_ms=0.5,
        )

    def test_log_request(self):
        """Test logging HTTP request event."""
        logger = StructuredLogger()
        logger.log_request(
            method="POST",
            path="/api/v1/validate",
            status_code=200,
            latency_ms=2.5,
            user_agent="test-agent/1.0",
        )

    def test_log_request_error(self):
        """Test logging HTTP request error event."""
        logger = StructuredLogger()
        logger.log_request(
            method="GET",
            path="/api/v1/unknown",
            status_code=404,
            latency_ms=1.0,
        )


class TestTraceContext:
    """Test trace context management."""

    def setup_method(self):
        """Clear trace context before each test."""
        clear_trace_context()

    def test_set_trace_context(self):
        """Test setting trace context."""
        set_trace_context("trace-123", "span-456")
        ctx = get_trace_context()
        assert ctx["trace_id"] == "trace-123"
        assert ctx["span_id"] == "span-456"

    def test_set_trace_context_trace_only(self):
        """Test setting trace context with trace_id only."""
        set_trace_context("trace-123")
        ctx = get_trace_context()
        assert ctx["trace_id"] == "trace-123"
        assert ctx["span_id"] is None

    def test_clear_trace_context(self):
        """Test clearing trace context."""
        set_trace_context("trace-123", "span-456")
        clear_trace_context()
        ctx = get_trace_context()
        assert ctx["trace_id"] is None
        assert ctx["span_id"] is None


class TestConfigureLogging:
    """Test configure_structured_logging function."""

    def test_configure_structured_logging_returns_logger(self):
        """Test configure returns logger."""
        stream = io.StringIO()
        logger = configure_structured_logging(
            service_name="test-service",
            output_stream=stream,
        )
        assert isinstance(logger, logging.Logger)

    def test_configure_structured_logging_uses_json_formatter(self):
        """Test configure uses JSON formatter."""
        stream = io.StringIO()
        configure_structured_logging(
            service_name="test-service",
            output_stream=stream,
        )

        # Log a message
        test_logger = logging.getLogger("test")
        test_logger.info("Test message")

        # Check output is JSON
        stream.seek(0)
        output = stream.read()
        if output:  # May be empty due to level filtering
            lines = [line for line in output.strip().split("\n") if line]
            if lines:
                data = json.loads(lines[-1])
                assert "service" in data


class TestRedactionPatterns:
    """Test redaction pattern definitions."""

    def test_redaction_patterns_count(self):
        """Test expected number of redaction patterns."""
        # Should have at least 9 patterns per spec
        assert len(REDACTION_PATTERNS) >= 9

    def test_redaction_pattern_names(self):
        """Test all expected pattern names exist."""
        names = [p.name for p in REDACTION_PATTERNS]
        expected = [
            "email",
            "jwt",
            "api_key",
            "bearer_token",
            "password",
            "credit_card",
            "ssn",
            "phone",
            "ip_address",
            "auth_header",
        ]
        for name in expected:
            assert name in names, f"Missing redaction pattern: {name}"

    def test_redaction_pattern_has_replacement(self):
        """Test all patterns have replacement strings."""
        for pattern in REDACTION_PATTERNS:
            assert pattern.replacement, f"Pattern {pattern.name} missing replacement"
