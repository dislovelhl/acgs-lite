"""
Coverage batch 15 — observability/structured_logging, enterprise_sso/middleware,
cb_kafka_producer, collaboration/permissions, constitutional/version_history,
online_learning_infra/adapter, ai_assistant/integration.

Target: 864+ newly covered lines across 8 modules.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. observability/structured_logging (105 missing lines)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.observability.structured_logging import (
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
    span_id_var,
    trace_id_var,
)


class TestLogLevel:
    def test_enum_values(self) -> None:
        assert LogLevel.DEBUG == "DEBUG"
        assert LogLevel.INFO == "INFO"
        assert LogLevel.WARN == "WARN"
        assert LogLevel.ERROR == "ERROR"
        assert LogLevel.FATAL == "FATAL"


class TestGetLogLevel:
    def test_default_development(self) -> None:
        with patch.dict("os.environ", {"ENVIRONMENT": "development"}):
            assert get_log_level() == "DEBUG"

    def test_production(self) -> None:
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            assert get_log_level() == "INFO"

    def test_staging(self) -> None:
        with patch.dict("os.environ", {"ENVIRONMENT": "staging"}):
            assert get_log_level() == "DEBUG"

    def test_unknown_env(self) -> None:
        with patch.dict("os.environ", {"ENVIRONMENT": "custom"}):
            assert get_log_level() == "DEBUG"


class TestRedactSensitiveData:
    def test_email_redaction(self) -> None:
        result = redact_sensitive_data("Contact user@example.com for info")
        assert "user@example.com" not in result
        assert "***@***.***" in result

    def test_jwt_redaction(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = redact_sensitive_data(f"Token: {jwt}")
        assert "[JWT_REDACTED]" in result

    def test_bearer_token_redaction(self) -> None:
        result = redact_sensitive_data("Authorization: Bearer abc123def456")
        assert "[TOKEN_REDACTED]" in result

    def test_password_redaction(self) -> None:
        result = redact_sensitive_data("password=mysecretpass123")
        assert "[PASSWORD_REDACTED]" in result

    def test_ssn_redaction(self) -> None:
        result = redact_sensitive_data("SSN: 123-45-6789")
        assert "[SSN_REDACTED]" in result

    def test_credit_card_redaction(self) -> None:
        result = redact_sensitive_data("Card: 4111-1111-1111-1111")
        assert "[CARD_REDACTED]" in result

    def test_phone_redaction(self) -> None:
        result = redact_sensitive_data("Call (555) 123-4567 for help")
        assert "[PHONE_REDACTED]" in result

    def test_ip_redaction(self) -> None:
        result = redact_sensitive_data("Server at 192.168.1.100")
        assert "[IP_REDACTED]" in result

    def test_non_string_passthrough(self) -> None:
        assert redact_sensitive_data(42) == 42  # type: ignore[arg-type]

    def test_no_sensitive_data(self) -> None:
        text = "This is a normal message."
        assert redact_sensitive_data(text) == text


class TestRedactDict:
    def test_sensitive_keys_redacted(self) -> None:
        data = {"password": "secret123", "name": "John"}
        result = redact_dict(data)
        assert result["password"] == "[REDACTED]"
        assert result["name"] == "John"

    def test_nested_dict(self) -> None:
        data = {"config": {"api_key": "abc123", "host": "localhost"}}
        result = redact_dict(data)
        assert result["config"]["api_key"] == "[REDACTED]"
        assert result["config"]["host"] == "localhost"

    def test_list_values(self) -> None:
        data = {"items": [{"secret": "x"}, "user@test.com"]}
        result = redact_dict(data)
        assert result["items"][0]["secret"] == "[REDACTED]"
        assert "***@***.***" in result["items"][1]

    def test_string_value_redaction(self) -> None:
        data = {"message": "Contact user@test.com"}
        result = redact_dict(data)
        assert "***@***.***" in result["message"]

    def test_non_dict_passthrough(self) -> None:
        assert redact_dict("not a dict") == "not a dict"  # type: ignore[arg-type]

    def test_numeric_values_preserved(self) -> None:
        data = {"count": 42, "ratio": 3.14}
        result = redact_dict(data)
        assert result["count"] == 42
        assert result["ratio"] == 3.14

    def test_list_with_non_string_non_dict(self) -> None:
        data = {"nums": [1, 2, 3]}
        result = redact_dict(data)
        assert result["nums"] == [1, 2, 3]

    def test_token_key_redacted(self) -> None:
        data = {"access_token": "abc123xyz"}
        result = redact_dict(data)
        assert result["access_token"] == "[REDACTED]"

    def test_authorization_key(self) -> None:
        data = {"authorization": "Bearer xyz"}
        result = redact_dict(data)
        assert result["authorization"] == "[REDACTED]"


class TestStructuredJSONFormatter:
    def test_format_basic(self) -> None:
        formatter = StructuredJSONFormatter(service_name="test-svc", redact_pii=False)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["service"] == "test-svc"
        assert "Test message" in parsed["message"]

    def test_format_with_exception(self) -> None:
        formatter = StructuredJSONFormatter(redact_pii=False)
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Error",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed

    def test_format_with_extra(self) -> None:
        formatter = StructuredJSONFormatter(include_extra=True, redact_pii=False)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.custom_field = "custom_value"  # type: ignore[attr-defined]
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "extra" in parsed

    def test_format_without_extra(self) -> None:
        formatter = StructuredJSONFormatter(include_extra=False, redact_pii=False)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "extra" not in parsed

    def test_format_with_pii_redaction(self) -> None:
        formatter = StructuredJSONFormatter(redact_pii=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Email: user@test.com",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "user@test.com" not in output


class TestStructuredLogger:
    def test_creation(self) -> None:
        sl = StructuredLogger(service_name="test")
        assert sl.service_name == "test"
        assert sl.logger is not None

    def test_log_constitutional_validation(self) -> None:
        sl = StructuredLogger()
        sl.log_constitutional_validation(
            agent_id="agent-1",
            result="pass",
            confidence=0.95,
            latency_ms=1.5,
            principles_checked=["safety", "fairness"],
            violations=[],
        )

    def test_log_constitutional_validation_with_violations(self) -> None:
        sl = StructuredLogger()
        sl.log_constitutional_validation(
            agent_id="agent-1",
            result="fail",
            confidence=0.3,
            latency_ms=2.0,
            violations=[{"rule": "safety", "detail": "violation"}],
        )

    def test_log_policy_evaluation(self) -> None:
        sl = StructuredLogger()
        sl.log_policy_evaluation(
            policy_id="pol-1",
            input_hash="abc123",
            decision="allow",
            latency_ms=0.5,
        )

    def test_log_policy_evaluation_no_latency(self) -> None:
        sl = StructuredLogger()
        sl.log_policy_evaluation(
            policy_id="pol-1",
            input_hash="abc123",
            decision="deny",
        )

    def test_log_security_violation(self) -> None:
        sl = StructuredLogger()
        sl.log_security_violation(
            violation_type="injection",
            source="api",
            details={"summary": "SQL injection attempt"},
        )

    def test_log_cache_operation(self) -> None:
        sl = StructuredLogger()
        sl.log_cache_operation(
            cache_tier="l1",
            operation="get",
            hit=True,
            key_prefix="msg:",
            latency_ms=0.1,
        )

    def test_log_cache_operation_minimal(self) -> None:
        sl = StructuredLogger()
        sl.log_cache_operation(cache_tier="l2", operation="set", hit=False)

    def test_log_request_success(self) -> None:
        sl = StructuredLogger()
        sl.log_request(
            method="GET",
            path="/api/v1/health",
            status_code=200,
            latency_ms=5.0,
            user_agent="test-agent/1.0",
        )

    def test_log_request_error(self) -> None:
        sl = StructuredLogger()
        sl.log_request(
            method="POST",
            path="/api/v1/resource",
            status_code=500,
            latency_ms=100.0,
        )

    def test_log_with_pii_redaction(self) -> None:
        sl = StructuredLogger(redact_pii=True)
        sl.log_security_violation(
            violation_type="leak",
            source="handler",
            details={"email": "user@test.com"},
        )


class TestTraceContext:
    def test_set_and_get(self) -> None:
        set_trace_context("trace-123", "span-456")
        ctx = get_trace_context()
        assert ctx["trace_id"] == "trace-123"
        assert ctx["span_id"] == "span-456"
        clear_trace_context()

    def test_clear(self) -> None:
        set_trace_context("t1", "s1")
        clear_trace_context()
        ctx = get_trace_context()
        assert ctx["trace_id"] is None
        assert ctx["span_id"] is None

    def test_set_without_span(self) -> None:
        set_trace_context("trace-only")
        ctx = get_trace_context()
        assert ctx["trace_id"] == "trace-only"
        clear_trace_context()


class TestGlobalStructuredLogger:
    def test_get_singleton(self) -> None:
        reset_structured_logger()
        sl1 = get_structured_logger()
        sl2 = get_structured_logger()
        assert sl1 is sl2
        reset_structured_logger()

    def test_reset(self) -> None:
        sl1 = get_structured_logger()
        reset_structured_logger()
        sl2 = get_structured_logger()
        assert sl1 is not sl2
        reset_structured_logger()


class TestConfigureStructuredLogging:
    def test_configure_default(self) -> None:
        output = io.StringIO()
        logger = configure_structured_logging(
            service_name="test-config",
            log_level="DEBUG",
            output_stream=output,
        )
        assert isinstance(logger, logging.Logger)

    def test_configure_no_redact(self) -> None:
        output = io.StringIO()
        configure_structured_logging(
            service_name="test",
            log_level="INFO",
            output_stream=output,
            redact_pii=False,
        )


# ---------------------------------------------------------------------------
# 2. enterprise_sso/middleware (116 missing lines)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.enterprise_sso.middleware import (
    SSOMiddlewareConfig,
    SSOSessionContext,
    clear_sso_session,
    get_current_sso_session,
    require_sso_authentication,
    set_sso_session,
)


def _make_session(**overrides: Any) -> SSOSessionContext:
    defaults: dict[str, Any] = {
        "session_id": "sess-1",
        "user_id": "user-1",
        "tenant_id": "tenant-1",
        "email": "user@example.com",
        "display_name": "Test User",
        "maci_roles": ["ADMIN", "OPERATOR"],
        "idp_groups": ["engineering"],
        "attributes": {},
        "authenticated_at": datetime.now(UTC),
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
    }
    defaults.update(overrides)
    return SSOSessionContext(**defaults)


class TestSSOSessionContext:
    def test_is_expired_false(self) -> None:
        session = _make_session(expires_at=datetime.now(UTC) + timedelta(hours=1))
        assert session.is_expired is False

    def test_is_expired_true(self) -> None:
        session = _make_session(expires_at=datetime.now(UTC) - timedelta(hours=1))
        assert session.is_expired is True

    def test_time_until_expiry(self) -> None:
        session = _make_session(expires_at=datetime.now(UTC) + timedelta(seconds=60))
        assert session.time_until_expiry > 0

    def test_time_until_expiry_expired(self) -> None:
        session = _make_session(expires_at=datetime.now(UTC) - timedelta(seconds=60))
        assert session.time_until_expiry == 0.0

    def test_has_role(self) -> None:
        session = _make_session(maci_roles=["ADMIN", "VIEWER"])
        assert session.has_role("admin") is True
        assert session.has_role("ADMIN") is True
        assert session.has_role("OPERATOR") is False

    def test_has_any_role(self) -> None:
        session = _make_session(maci_roles=["ADMIN"])
        assert session.has_any_role(["admin", "viewer"]) is True
        assert session.has_any_role(["operator"]) is False

    def test_has_all_roles(self) -> None:
        session = _make_session(maci_roles=["ADMIN", "OPERATOR"])
        assert session.has_all_roles(["admin", "operator"]) is True
        assert session.has_all_roles(["admin", "viewer"]) is False

    def test_to_dict(self) -> None:
        session = _make_session()
        d = session.to_dict()
        assert d["session_id"] == "sess-1"
        assert d["user_id"] == "user-1"
        assert "authenticated_at" in d
        assert "expires_at" in d


class TestSSOContextVars:
    def test_set_and_get(self) -> None:
        session = _make_session()
        set_sso_session(session)
        assert get_current_sso_session() is session
        clear_sso_session()
        assert get_current_sso_session() is None

    def test_clear(self) -> None:
        set_sso_session(_make_session())
        clear_sso_session()
        assert get_current_sso_session() is None


class TestSSOMiddlewareConfig:
    def test_defaults(self) -> None:
        config = SSOMiddlewareConfig()
        assert "/health" in config.excluded_paths
        assert config.require_authentication is True
        assert config.auto_refresh_sessions is True


class TestRequireSSOAuthentication:
    @pytest.mark.asyncio
    async def test_async_no_session_raises(self) -> None:
        clear_sso_session()

        @require_sso_authentication()
        async def protected() -> str:
            return "ok"

        with pytest.raises((PermissionError, Exception)):
            await protected()

    @pytest.mark.asyncio
    async def test_async_with_session(self) -> None:
        session = _make_session()
        set_sso_session(session)
        try:

            @require_sso_authentication()
            async def protected() -> str:
                return "ok"

            result = await protected()
            assert result == "ok"
        finally:
            clear_sso_session()

    @pytest.mark.asyncio
    async def test_async_expired_session_raises(self) -> None:
        session = _make_session(expires_at=datetime.now(UTC) - timedelta(hours=1))
        set_sso_session(session)
        try:

            @require_sso_authentication(allow_expired=False)
            async def protected() -> str:
                return "ok"

            with pytest.raises((PermissionError, Exception)):
                await protected()
        finally:
            clear_sso_session()

    @pytest.mark.asyncio
    async def test_async_expired_session_allowed(self) -> None:
        session = _make_session(expires_at=datetime.now(UTC) - timedelta(hours=1))
        set_sso_session(session)
        try:

            @require_sso_authentication(allow_expired=True)
            async def protected() -> str:
                return "ok"

            result = await protected()
            assert result == "ok"
        finally:
            clear_sso_session()

    @pytest.mark.asyncio
    async def test_async_role_check_any(self) -> None:
        session = _make_session(maci_roles=["VIEWER"])
        set_sso_session(session)
        try:

            @require_sso_authentication(roles=["ADMIN", "OPERATOR"], any_role=True)
            async def protected() -> str:
                return "ok"

            with pytest.raises((PermissionError, Exception)):
                await protected()
        finally:
            clear_sso_session()

    @pytest.mark.asyncio
    async def test_async_role_check_all(self) -> None:
        session = _make_session(maci_roles=["ADMIN"])
        set_sso_session(session)
        try:

            @require_sso_authentication(roles=["ADMIN", "OPERATOR"], any_role=False)
            async def protected() -> str:
                return "ok"

            with pytest.raises((PermissionError, Exception)):
                await protected()
        finally:
            clear_sso_session()

    def test_sync_no_session_raises(self) -> None:
        clear_sso_session()

        @require_sso_authentication()
        def protected() -> str:
            return "ok"

        with pytest.raises(PermissionError):
            protected()

    def test_sync_with_session(self) -> None:
        session = _make_session()
        set_sso_session(session)
        try:

            @require_sso_authentication()
            def protected() -> str:
                return "ok"

            assert protected() == "ok"
        finally:
            clear_sso_session()

    def test_sync_expired_raises(self) -> None:
        session = _make_session(expires_at=datetime.now(UTC) - timedelta(hours=1))
        set_sso_session(session)
        try:

            @require_sso_authentication()
            def protected() -> str:
                return "ok"

            with pytest.raises(PermissionError, match="expired"):
                protected()
        finally:
            clear_sso_session()

    def test_sync_role_check(self) -> None:
        session = _make_session(maci_roles=["VIEWER"])
        set_sso_session(session)
        try:

            @require_sso_authentication(roles=["ADMIN"], any_role=True)
            def protected() -> str:
                return "ok"

            with pytest.raises(PermissionError, match="Requires one of"):
                protected()
        finally:
            clear_sso_session()

    def test_sync_role_check_all_fail(self) -> None:
        session = _make_session(maci_roles=["ADMIN"])
        set_sso_session(session)
        try:

            @require_sso_authentication(roles=["ADMIN", "OPERATOR"], any_role=False)
            def protected() -> str:
                return "ok"

            with pytest.raises(PermissionError, match="Requires all"):
                protected()
        finally:
            clear_sso_session()


# ---------------------------------------------------------------------------
# 3. cb_kafka_producer (112 missing lines)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.cb_kafka_producer import CircuitBreakerKafkaProducer


class TestCircuitBreakerKafkaProducer:
    def test_init_defaults(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        assert producer.bootstrap_servers == "localhost:9092"
        assert producer._initialized is False
        assert producer._running is False

    @pytest.mark.asyncio
    async def test_initialize_no_aiokafka(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        with patch.dict("sys.modules", {"aiokafka": None}):
            with patch(
                "enhanced_agent_bus.cb_kafka_producer.CircuitBreakerKafkaProducer._retry_loop",
                new_callable=lambda: lambda self: asyncio.sleep(0),
            ):
                # Mock get_service_circuit_breaker
                mock_cb = AsyncMock()
                mock_cb.state = MagicMock()
                with patch(
                    "enhanced_agent_bus.cb_kafka_producer.get_service_circuit_breaker",
                    return_value=mock_cb,
                ):
                    await producer.initialize()
                    assert producer._initialized is True
                    producer._running = False
                    if producer._retry_task:
                        producer._retry_task.cancel()
                        try:
                            await producer._retry_task
                        except (asyncio.CancelledError, Exception):
                            pass

    @pytest.mark.asyncio
    async def test_close_without_init(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        await producer.close()
        assert producer._initialized is False

    @pytest.mark.asyncio
    async def test_close_with_producer(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        mock_prod = AsyncMock()
        producer._producer = mock_prod
        producer._initialized = True
        producer._running = True
        producer._retry_task = None
        await producer.close()
        mock_prod.flush.assert_awaited_once()
        mock_prod.stop.assert_awaited_once()
        assert producer._producer is None

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        with patch.object(producer, "initialize", new_callable=AsyncMock):
            with patch.object(producer, "close", new_callable=AsyncMock):
                async with producer as p:
                    assert p is producer

    @pytest.mark.asyncio
    async def test_send_buffers_when_circuit_open(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        producer._initialized = True

        mock_cb = AsyncMock()
        mock_cb.can_execute = AsyncMock(return_value=False)
        mock_cb.record_rejection = AsyncMock()
        producer._circuit_breaker = mock_cb
        producer._producer = AsyncMock()

        result = await producer.send("topic", {"data": "test"}, "key1")
        assert result is False
        mock_cb.record_rejection.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_no_producer_buffers(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        producer._initialized = True

        mock_cb = AsyncMock()
        mock_cb.can_execute = AsyncMock(return_value=True)
        producer._circuit_breaker = mock_cb
        producer._producer = None

        result = await producer.send("topic", {"data": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        producer._initialized = True

        mock_cb = AsyncMock()
        mock_cb.can_execute = AsyncMock(return_value=True)
        mock_cb.record_success = AsyncMock()
        producer._circuit_breaker = mock_cb

        mock_prod = AsyncMock()
        producer._producer = mock_prod

        result = await producer.send("topic", {"data": "test"}, "key1")
        assert result is True
        mock_cb.record_success.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_failure_buffers(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        producer._initialized = True

        mock_cb = AsyncMock()
        mock_cb.can_execute = AsyncMock(return_value=True)
        mock_cb.record_failure = AsyncMock()
        producer._circuit_breaker = mock_cb

        mock_prod = AsyncMock()
        mock_prod.send_and_wait = AsyncMock(side_effect=RuntimeError("send failed"))
        producer._producer = mock_prod

        result = await producer.send("topic", {"data": "test"})
        assert result is False
        mock_cb.record_failure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_batch(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        producer._initialized = True

        mock_cb = AsyncMock()
        mock_cb.can_execute = AsyncMock(return_value=True)
        mock_cb.record_success = AsyncMock()
        producer._circuit_breaker = mock_cb

        mock_prod = AsyncMock()
        producer._producer = mock_prod

        messages = [
            ("topic1", {"a": 1}, "k1"),
            ("topic2", {"b": 2}, None),
        ]
        result = await producer.send_batch(messages)
        assert result["sent"] == 2
        assert result["buffered"] == 0

    @pytest.mark.asyncio
    async def test_flush_buffer_no_producer(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        producer._producer = None
        result = await producer.flush_buffer()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_health_check_no_producer(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        producer._circuit_breaker = None
        health = await producer.health_check()
        assert health["service"] == "kafka_producer"
        assert health["kafka_status"] == "not_connected"

    @pytest.mark.asyncio
    async def test_health_check_with_producer(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        producer._producer = MagicMock()

        class FakeMetrics:
            failures = 0
            successes = 5

        mock_cb = MagicMock()
        mock_cb.state = MagicMock(value="closed")
        mock_cb.metrics = FakeMetrics()
        producer._circuit_breaker = mock_cb
        health = await producer.health_check()
        assert health["healthy"] is True

    def test_get_circuit_status_not_init(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        status = producer.get_circuit_status()
        assert "error" in status

    def test_get_circuit_status(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        mock_cb = MagicMock()
        mock_cb.get_status.return_value = {"state": "closed"}
        producer._circuit_breaker = mock_cb
        status = producer.get_circuit_status()
        assert "state" in status
        assert "buffer_metrics" in status

    @pytest.mark.asyncio
    async def test_send_raw_no_producer(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        producer._producer = None
        with pytest.raises(RuntimeError, match="not available"):
            await producer._send_raw("topic", {"x": 1}, None)

    @pytest.mark.asyncio
    async def test_send_raw_with_producer(self) -> None:
        producer = CircuitBreakerKafkaProducer()
        mock_prod = AsyncMock()
        producer._producer = mock_prod
        await producer._send_raw("topic", {"x": 1}, b"key")
        mock_prod.send_and_wait.assert_awaited_once()


# ---------------------------------------------------------------------------
# 4. collaboration/permissions (110 missing lines)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.collaboration.models import (
    CollaborationSession,
    DocumentType,
    PermissionDeniedError,
    UserPermissions,
)
from enhanced_agent_bus.collaboration.permissions import PermissionController


class TestPermissionController:
    @pytest.mark.asyncio
    async def test_default_read_permission(self) -> None:
        pc = PermissionController()
        # Default permission is READ, so requesting READ should succeed
        result = await pc.check_permission("user1", "doc1", UserPermissions.READ)
        assert result is True

    @pytest.mark.asyncio
    async def test_write_denied_for_default_user(self) -> None:
        pc = PermissionController()
        with pytest.raises(PermissionDeniedError):
            await pc.check_permission("user1", "doc1", UserPermissions.WRITE)

    @pytest.mark.asyncio
    async def test_set_and_check_permission(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.WRITE, "admin1")
        result = await pc.check_permission("user1", "doc1", UserPermissions.WRITE)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_permission_upgrade(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.READ, "admin1")
        await pc.set_permission("doc1", "user1", UserPermissions.ADMIN, "admin1")
        result = await pc.check_permission("user1", "doc1", UserPermissions.ADMIN)
        assert result is True

    @pytest.mark.asyncio
    async def test_can_edit_true(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.WRITE, "admin1")
        assert await pc.can_edit("user1", "doc1") is True

    @pytest.mark.asyncio
    async def test_can_edit_false(self) -> None:
        pc = PermissionController()
        assert await pc.can_edit("user1", "doc1") is False

    @pytest.mark.asyncio
    async def test_can_admin_true(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.ADMIN, "admin1")
        assert await pc.can_admin("user1", "doc1") is True

    @pytest.mark.asyncio
    async def test_can_admin_false(self) -> None:
        pc = PermissionController()
        assert await pc.can_admin("user1", "doc1") is False

    @pytest.mark.asyncio
    async def test_require_edit_permission(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.WRITE, "admin1")
        await pc.require_edit_permission("user1", "doc1")  # Should not raise

    @pytest.mark.asyncio
    async def test_require_edit_permission_denied(self) -> None:
        pc = PermissionController()
        with pytest.raises(PermissionDeniedError):
            await pc.require_edit_permission("user1", "doc1")

    @pytest.mark.asyncio
    async def test_require_admin_permission(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.ADMIN, "admin1")
        await pc.require_admin_permission("user1", "doc1")

    @pytest.mark.asyncio
    async def test_lock_document(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.ADMIN, "admin1")
        session = CollaborationSession(
            document_id="doc1",
            document_type=DocumentType.POLICY,
            tenant_id="t1",
        )
        result = await pc.lock_document("doc1", "user1", session)
        assert result is True
        assert session.is_locked is True
        assert session.locked_by == "user1"

    @pytest.mark.asyncio
    async def test_lock_document_already_locked(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.ADMIN, "admin1")
        await pc.set_permission("doc1", "user2", UserPermissions.ADMIN, "admin1")
        session = CollaborationSession(
            document_id="doc1",
            document_type=DocumentType.POLICY,
            tenant_id="t1",
            is_locked=True,
            locked_by="user2",
        )
        result = await pc.lock_document("doc1", "user1", session)
        assert result is False

    @pytest.mark.asyncio
    async def test_unlock_document(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.ADMIN, "admin1")
        session = CollaborationSession(
            document_id="doc1",
            document_type=DocumentType.POLICY,
            tenant_id="t1",
            is_locked=True,
            locked_by="user1",
        )
        result = await pc.unlock_document("doc1", "user1", session)
        assert result is True
        assert session.is_locked is False

    @pytest.mark.asyncio
    async def test_unlock_document_not_locked(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.ADMIN, "admin1")
        session = CollaborationSession(
            document_id="doc1",
            document_type=DocumentType.POLICY,
            tenant_id="t1",
        )
        result = await pc.unlock_document("doc1", "user1", session)
        assert result is True

    @pytest.mark.asyncio
    async def test_request_edit_approval(self) -> None:
        pc = PermissionController()
        approval_id = await pc.request_edit_approval("doc1", "user1")
        assert "approval:" in approval_id
        assert await pc.is_edit_approved("doc1", "user1") is False

    @pytest.mark.asyncio
    async def test_approve_edit(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "admin1", UserPermissions.ADMIN, "admin1")
        await pc.request_edit_approval("doc1", "user1")
        result = await pc.approve_edit("doc1", "user1", "admin1")
        assert result is True
        assert await pc.is_edit_approved("doc1", "user1") is True

    @pytest.mark.asyncio
    async def test_is_edit_approved_no_doc(self) -> None:
        pc = PermissionController()
        assert await pc.is_edit_approved("no-doc", "user1") is False

    @pytest.mark.asyncio
    async def test_validate_operation_write(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.WRITE, "admin1")
        result = await pc.validate_operation("user1", "doc1", "insert", {"text": "hello"})
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_operation_delete_needs_admin(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.WRITE, "admin1")
        with pytest.raises(PermissionDeniedError):
            await pc.validate_operation("user1", "doc1", "delete", {})

    @pytest.mark.asyncio
    async def test_validate_operation_delete_admin(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.ADMIN, "admin1")
        result = await pc.validate_operation("user1", "doc1", "delete", {})
        assert result is True

    def test_get_document_permissions(self) -> None:
        pc = PermissionController()
        pc._document_permissions["doc1"] = {"user1": UserPermissions.WRITE}
        perms = pc.get_document_permissions("doc1")
        assert perms == {"user1": UserPermissions.WRITE}

    def test_get_document_permissions_empty(self) -> None:
        pc = PermissionController()
        perms = pc.get_document_permissions("unknown")
        assert perms == {}

    @pytest.mark.asyncio
    async def test_remove_user_permissions(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.WRITE, "admin1")
        await pc.remove_user_permissions("doc1", "user1")
        assert await pc.can_edit("user1", "doc1") is False

    @pytest.mark.asyncio
    async def test_audit_client_logging(self) -> None:
        audit_client = AsyncMock()
        pc = PermissionController(audit_client=audit_client)
        await pc.set_permission("doc1", "user1", UserPermissions.WRITE, "admin1")
        await pc.check_permission("user1", "doc1", UserPermissions.WRITE)
        assert audit_client.log_event.await_count >= 1

    @pytest.mark.asyncio
    async def test_audit_client_error_handling(self) -> None:
        audit_client = AsyncMock()
        audit_client.log_event = AsyncMock(side_effect=RuntimeError("audit down"))
        pc = PermissionController(audit_client=audit_client)
        await pc.set_permission("doc1", "user1", UserPermissions.WRITE, "admin1")
        # Should not raise despite audit failure
        result = await pc.check_permission("user1", "doc1", UserPermissions.WRITE)
        assert result is True

    @pytest.mark.asyncio
    async def test_lock_document_denied_non_admin(self) -> None:
        pc = PermissionController()
        session = CollaborationSession(
            document_id="doc1",
            document_type=DocumentType.POLICY,
            tenant_id="t1",
        )
        with pytest.raises(PermissionDeniedError):
            await pc.lock_document("doc1", "user1", session)

    @pytest.mark.asyncio
    async def test_unlock_by_different_admin(self) -> None:
        pc = PermissionController()
        await pc.set_permission("doc1", "user1", UserPermissions.ADMIN, "admin1")
        await pc.set_permission("doc1", "user2", UserPermissions.ADMIN, "admin1")
        session = CollaborationSession(
            document_id="doc1",
            document_type=DocumentType.POLICY,
            tenant_id="t1",
            is_locked=True,
            locked_by="user1",
        )
        result = await pc.unlock_document("doc1", "user2", session)
        assert result is True


# ---------------------------------------------------------------------------
# 5. constitutional/version_history (108 missing lines)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.constitutional.version_history import (
    VersionHistoryQuery,
    VersionHistoryService,
    VersionHistorySummary,
)
from enhanced_agent_bus.constitutional.version_model import (
    ConstitutionalStatus,
    ConstitutionalVersion,
)


def _make_version(
    version: str = "1.0.0",
    status: ConstitutionalStatus = ConstitutionalStatus.ACTIVE,
    predecessor: str | None = None,
    activated_at: datetime | None = None,
    deactivated_at: datetime | None = None,
    **kwargs: Any,
) -> ConstitutionalVersion:
    return ConstitutionalVersion(
        version=version,
        content={"rules": []},
        constitutional_hash="608508a9bd224290",
        status=status,
        predecessor_version=predecessor,
        activated_at=activated_at,
        deactivated_at=deactivated_at,
        **kwargs,
    )


class TestVersionHistoryQuery:
    def test_defaults(self) -> None:
        q = VersionHistoryQuery()
        assert q.limit == 50
        assert q.offset == 0
        assert q.sort_order == "desc"


class TestVersionHistorySummary:
    def test_defaults(self) -> None:
        s = VersionHistorySummary()
        assert s.total_versions == 0
        assert s.rollback_count == 0


class TestVersionHistoryService:
    def _make_service(
        self, versions: list[ConstitutionalVersion] | None = None
    ) -> VersionHistoryService:
        storage = AsyncMock()
        vlist = versions or []
        storage.list_versions = AsyncMock(return_value=vlist)
        storage.get_version = AsyncMock(
            side_effect=lambda vid: next((v for v in vlist if v.version_id == vid), None)
        )
        return VersionHistoryService(storage=storage)

    @pytest.mark.asyncio
    async def test_list_versions_default(self) -> None:
        v1 = _make_version("1.0.0")
        v2 = _make_version("2.0.0")
        svc = self._make_service([v1, v2])
        result = await svc.list_versions()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_versions_with_query(self) -> None:
        v1 = _make_version("1.0.0")
        svc = self._make_service([v1])
        q = VersionHistoryQuery(limit=10, offset=0, sort_order="asc")
        result = await svc.list_versions(q)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_versions_date_filter(self) -> None:
        v1 = _make_version("1.0.0")
        svc = self._make_service([v1])
        future = datetime.now(UTC) + timedelta(days=1)
        q = VersionHistoryQuery(from_date=future)
        result = await svc.list_versions(q)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_versions_to_date_filter(self) -> None:
        v1 = _make_version("1.0.0")
        svc = self._make_service([v1])
        past = datetime.now(UTC) - timedelta(days=1)
        q = VersionHistoryQuery(to_date=past)
        result = await svc.list_versions(q)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_versions_exclude_metadata(self) -> None:
        v1 = _make_version("1.0.0", metadata={"author": "test"})
        svc = self._make_service([v1])
        q = VersionHistoryQuery(include_metadata=False)
        result = await svc.list_versions(q)
        assert result[0].metadata == {}

    @pytest.mark.asyncio
    async def test_get_version_lineage(self) -> None:
        v1 = _make_version("1.0.0")
        v2 = _make_version("2.0.0", predecessor=v1.version_id)
        svc = self._make_service([v1, v2])
        lineage = await svc.get_version_lineage(v2.version_id)
        assert len(lineage) == 2

    @pytest.mark.asyncio
    async def test_get_version_lineage_missing(self) -> None:
        svc = self._make_service([])
        lineage = await svc.get_version_lineage("nonexistent")
        assert len(lineage) == 0

    @pytest.mark.asyncio
    async def test_get_summary(self) -> None:
        v1 = _make_version("1.0.0", status=ConstitutionalStatus.ACTIVE)
        v2 = _make_version("2.0.0", status=ConstitutionalStatus.ROLLED_BACK)
        v3 = _make_version("3.0.0", status=ConstitutionalStatus.REJECTED)
        svc = self._make_service([v1, v2, v3])
        summary = await svc.get_summary()
        assert summary.total_versions == 3
        assert summary.rollback_count == 1
        assert summary.rejection_count == 1
        assert summary.active_version == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_summary_cached(self) -> None:
        v1 = _make_version("1.0.0")
        svc = self._make_service([v1])
        s1 = await svc.get_summary()
        s2 = await svc.get_summary()  # Should use cache
        assert s1.total_versions == s2.total_versions

    @pytest.mark.asyncio
    async def test_export_json(self) -> None:
        v1 = _make_version("1.0.0", activated_at=datetime.now(UTC))
        svc = self._make_service([v1])
        exported = await svc.export_audit_trail(format="json")
        assert "constitutional_hash" in exported
        assert "1.0.0" in exported

    @pytest.mark.asyncio
    async def test_export_csv(self) -> None:
        v1 = _make_version("1.0.0")
        svc = self._make_service([v1])
        exported = await svc.export_audit_trail(format="csv")
        reader = csv.reader(io.StringIO(exported))
        rows = list(reader)
        assert len(rows) == 2  # header + 1 data row
        assert "version_id" in rows[0]

    @pytest.mark.asyncio
    async def test_export_invalid_format(self) -> None:
        svc = self._make_service([])
        with pytest.raises(ValueError, match="Unsupported"):
            await svc.export_audit_trail(format="xml")

    @pytest.mark.asyncio
    async def test_get_version_by_semver(self) -> None:
        v1 = _make_version("1.0.0")
        v2 = _make_version("2.0.0")
        svc = self._make_service([v1, v2])
        found = await svc.get_version_by_semver("2.0.0")
        assert found is not None
        assert found.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_get_version_by_semver_not_found(self) -> None:
        svc = self._make_service([])
        found = await svc.get_version_by_semver("99.0.0")
        assert found is None

    @pytest.mark.asyncio
    async def test_get_transition_history(self) -> None:
        v1 = _make_version(
            "1.0.0",
            activated_at=datetime.now(UTC) - timedelta(days=2),
            deactivated_at=datetime.now(UTC) - timedelta(days=1),
            status=ConstitutionalStatus.SUPERSEDED,
        )
        v2 = _make_version(
            "2.0.0",
            activated_at=datetime.now(UTC),
        )
        svc = self._make_service([v1, v2])
        transitions = await svc.get_transition_history()
        assert len(transitions) >= 2
        events = [t["event"] for t in transitions]
        assert "activated" in events

    @pytest.mark.asyncio
    async def test_get_transition_history_empty(self) -> None:
        svc = self._make_service([])
        transitions = await svc.get_transition_history()
        assert transitions == []

    def test_is_cache_valid_no_key(self) -> None:
        svc = self._make_service([])
        assert svc._is_cache_valid("missing") is False

    def test_is_cache_valid_no_update(self) -> None:
        svc = self._make_service([])
        svc._cache["key"] = "val"
        assert svc._is_cache_valid("key") is False

    def test_is_cache_valid_expired(self) -> None:
        svc = self._make_service([])
        svc._cache["key"] = "val"
        svc._last_cache_update = datetime.now(UTC) - timedelta(seconds=600)
        assert svc._is_cache_valid("key") is False

    def test_clear_cache(self) -> None:
        svc = self._make_service([])
        svc._cache["x"] = 1
        svc._last_cache_update = datetime.now(UTC)
        svc.clear_cache()
        assert svc._cache == {}
        assert svc._last_cache_update is None

    @pytest.mark.asyncio
    async def test_export_csv_with_deactivated(self) -> None:
        v1 = _make_version(
            "1.0.0",
            activated_at=datetime.now(UTC),
            deactivated_at=datetime.now(UTC),
        )
        svc = self._make_service([v1])
        exported = await svc.export_audit_trail(format="csv")
        assert "1.0.0" in exported


# ---------------------------------------------------------------------------
# 6. online_learning_infra/adapter (109 missing lines)
# ---------------------------------------------------------------------------

# We need to mock river and numpy before importing the adapter
_mock_forest = MagicMock()
_mock_metrics = MagicMock()
_mock_accuracy = MagicMock()
_mock_accuracy.get.return_value = 0.85
_mock_accuracy.update = MagicMock()
_mock_metrics.Accuracy.return_value = _mock_accuracy

_mock_classifier = MagicMock()
_mock_classifier.predict_one.return_value = 1
_mock_classifier.learn_one = MagicMock()
_mock_classifier.predict_proba_one.return_value = {0: 0.3, 1: 0.7}
_mock_forest.ARFClassifier.return_value = _mock_classifier

_mock_regressor = MagicMock()
_mock_regressor.predict_one.return_value = 0.5
_mock_regressor.learn_one = MagicMock()
_mock_forest.ARFRegressor.return_value = _mock_regressor


class TestRiverSklearnAdapter:
    @pytest.fixture(autouse=True)
    def _patch_deps(self):
        with patch.dict(
            "sys.modules",
            {
                "river": MagicMock(),
                "river.forest": _mock_forest,
                "river.metrics": _mock_metrics,
            },
        ):
            with patch(
                "enhanced_agent_bus.online_learning_infra.adapter.river_forest", _mock_forest
            ):
                with patch(
                    "enhanced_agent_bus.online_learning_infra.adapter.river_metrics", _mock_metrics
                ):
                    with patch(
                        "enhanced_agent_bus.online_learning_infra.adapter.RIVER_AVAILABLE", True
                    ):
                        with patch(
                            "enhanced_agent_bus.online_learning_infra.adapter.NUMPY_AVAILABLE", True
                        ):
                            yield

    def _make_adapter(self, **kwargs):
        from enhanced_agent_bus.online_learning_infra.adapter import RiverSklearnAdapter
        from enhanced_agent_bus.online_learning_infra.config import ModelType

        # Patch _check_dependencies to skip actual import checks
        with patch.object(RiverSklearnAdapter, "_check_dependencies"):
            return RiverSklearnAdapter(**kwargs)

    def test_init_default(self) -> None:
        adapter = self._make_adapter()
        assert adapter._samples_learned == 0
        assert adapter.model is not None

    def test_learn_one_dict(self) -> None:
        adapter = self._make_adapter()
        adapter.learn_one({"f1": 1.0, "f2": 2.0}, 1)
        assert adapter._samples_learned == 1
        assert adapter._last_update is not None

    def test_learn_one_list(self) -> None:
        adapter = self._make_adapter(feature_names=["a", "b"])
        adapter.learn_one([1.0, 2.0], 0)
        assert adapter._samples_learned == 1

    def test_learn_one_list_no_names(self) -> None:
        adapter = self._make_adapter()
        adapter.learn_one([1.0, 2.0, 3.0], 1)
        assert adapter._samples_learned == 1

    def test_learn_batch(self) -> None:
        adapter = self._make_adapter()
        X = [[1.0, 2.0], [3.0, 4.0]]
        y = [0, 1]
        result = adapter.learn_batch(X, y)
        assert result.success is True
        assert result.samples_learned == 2

    def test_learn_batch_error(self) -> None:
        adapter = self._make_adapter()
        adapter.model.learn_one.side_effect = ValueError("bad data")
        result = adapter.learn_batch([[1.0]], [0])
        assert result.success is False
        adapter.model.learn_one.side_effect = None

    def test_predict_one(self) -> None:
        adapter = self._make_adapter()
        result = adapter.predict_one({"f1": 1.0})
        assert result is not None
        assert adapter._total_predictions == 1

    def test_predict(self) -> None:
        adapter = self._make_adapter()
        results = adapter.predict([[1.0, 2.0], [3.0, 4.0]])
        assert len(results) == 2

    def test_predict_proba_one(self) -> None:
        adapter = self._make_adapter()
        result = adapter.predict_proba_one({"f1": 1.0})
        assert isinstance(result, dict)

    def test_predict_proba_one_regressor_raises(self) -> None:
        from enhanced_agent_bus.online_learning_infra.config import ModelType

        adapter = self._make_adapter(model_type=ModelType.REGRESSOR)
        with pytest.raises(ValueError, match="only available for classifiers"):
            adapter.predict_proba_one({"f1": 1.0})

    def test_predict_proba(self) -> None:
        adapter = self._make_adapter()
        results = adapter.predict_proba([[1.0], [2.0]])
        assert len(results) == 2

    def test_get_stats_cold_start(self) -> None:
        adapter = self._make_adapter()
        stats = adapter.get_stats()
        assert stats.status.value == "cold_start"

    def test_get_stats_ready(self) -> None:
        adapter = self._make_adapter()
        # Simulate enough samples
        from enhanced_agent_bus.online_learning_infra.config import MIN_SAMPLES_FOR_PREDICTION

        adapter._samples_learned = MIN_SAMPLES_FOR_PREDICTION + 1
        stats = adapter.get_stats()
        assert stats.status.value == "ready"

    def test_get_stats_warming_up(self) -> None:
        adapter = self._make_adapter()
        from enhanced_agent_bus.online_learning_infra.config import MIN_SAMPLES_FOR_PREDICTION

        adapter._samples_learned = MIN_SAMPLES_FOR_PREDICTION // 2 + 1
        stats = adapter.get_stats()
        assert stats.status.value == "warming_up"

    def test_is_ready(self) -> None:
        adapter = self._make_adapter()
        assert adapter.is_ready is False
        from enhanced_agent_bus.online_learning_infra.config import MIN_SAMPLES_FOR_PREDICTION

        adapter._samples_learned = MIN_SAMPLES_FOR_PREDICTION
        assert adapter.is_ready is True

    def test_accuracy_property(self) -> None:
        adapter = self._make_adapter()
        acc = adapter.accuracy
        assert isinstance(acc, float)

    def test_samples_learned_property(self) -> None:
        adapter = self._make_adapter()
        assert adapter.samples_learned == 0

    def test_reset(self) -> None:
        adapter = self._make_adapter()
        adapter._samples_learned = 100
        adapter._total_predictions = 50
        adapter.reset()
        assert adapter._samples_learned == 0
        assert adapter._total_predictions == 0
        assert adapter._last_update is None

    def test_to_dict_hashing_trick(self) -> None:
        adapter = self._make_adapter(use_hashing_trick=True, n_features=16)
        result = adapter._to_dict({"feature_a": 1.0, "feature_b": 2.0})
        assert isinstance(result, dict)
        assert all(isinstance(k, int) for k in result.keys())

    def test_to_dict_list_hashing_trick(self) -> None:
        adapter = self._make_adapter(use_hashing_trick=True, n_features=16)
        result = adapter._to_dict([1.0, 2.0, 3.0])
        assert isinstance(result, dict)

    def test_to_dict_list_with_names_hashing_trick(self) -> None:
        adapter = self._make_adapter(
            feature_names=["a", "b"],
            use_hashing_trick=True,
            n_features=16,
        )
        result = adapter._to_dict([1.0, 2.0])
        assert isinstance(result, dict)

    def test_to_dict_list_with_names_no_hashing(self) -> None:
        adapter = self._make_adapter(feature_names=["x", "y"])
        result = adapter._to_dict([10.0, 20.0])
        assert result == {"x": 10.0, "y": 20.0}

    def test_feature_stats_bounded(self) -> None:
        adapter = self._make_adapter()
        adapter._max_feature_stats = 2
        adapter.learn_one({"f1": 1.0}, 0)
        adapter.learn_one({"f2": 2.0}, 1)
        adapter.learn_one({"f3": 3.0}, 0)  # Should not add new feature stats
        assert len(adapter._feature_stats) <= 2

    def test_feature_stats_updates(self) -> None:
        adapter = self._make_adapter()
        adapter.learn_one({"f1": 1.0}, 0)
        adapter.learn_one({"f1": 3.0}, 1)
        stats = adapter._feature_stats["f1"]
        assert stats["min"] == 1.0
        assert stats["max"] == 3.0
        assert stats["count"] == 2

    def test_regressor_model(self) -> None:
        from enhanced_agent_bus.online_learning_infra.config import ModelType

        adapter = self._make_adapter(model_type=ModelType.REGRESSOR)
        assert adapter.model is not None


# ---------------------------------------------------------------------------
# 7. ai_assistant/integration (109 missing lines)
# ---------------------------------------------------------------------------


class TestAgentBusIntegration:
    @pytest.fixture
    def _mock_imports(self):
        """Patch imports needed by ai_assistant.integration."""
        with patch.dict(
            "sys.modules",
            {
                "src.core.shared.policy": MagicMock(),
                "src.core.shared.policy.models": MagicMock(),
                "src.core.shared.policy.unified_generator": MagicMock(),
            },
        ):
            yield

    def _make_integration(self, agent_bus=None):
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        config = IntegrationConfig(agent_id="test_agent", enable_governance=False)
        return AgentBusIntegration(config=config, agent_bus=agent_bus)

    @pytest.mark.asyncio
    async def test_initialize_no_bus(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        integration = AgentBusIntegration(config=IntegrationConfig())
        result = await integration.initialize()
        assert result is False

    @pytest.mark.asyncio
    async def test_initialize_with_bus(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        bus = MagicMock()
        integration = AgentBusIntegration(config=IntegrationConfig(), agent_bus=bus)
        result = await integration.initialize()
        assert result is True

    def test_register_handler(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()

        def handler(msg):
            return msg

        integration.register_handler("command", handler)
        assert "command" in integration.handlers

    def test_governance_decision_to_dict(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import GovernanceDecision

        gd = GovernanceDecision(
            is_allowed=True,
            reason="test",
            policy_id="pol-1",
            confidence=0.95,
        )
        d = gd.to_dict()
        assert d["is_allowed"] is True
        assert d["confidence"] == 0.95
        assert "timestamp" in d

    def test_integration_config_defaults(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import IntegrationConfig

        config = IntegrationConfig()
        assert config.agent_id == "ai_assistant"
        assert config.enable_governance is True

    @pytest.mark.asyncio
    async def test_shutdown(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()
        await integration.shutdown()  # Should not raise

    @pytest.mark.asyncio
    async def test_send_message_no_bus(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        integration = AgentBusIntegration(config=IntegrationConfig(enable_governance=False))
        result = await integration.send_message("target", "hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_handle_incoming_with_handler(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "608508a9bd224290"
        mock_msg.message_type = MagicMock(value="command")

        response_msg = MagicMock()
        handler = AsyncMock(return_value=response_msg)
        integration.register_handler("command", handler)

        result = await integration.handle_incoming_message(mock_msg)
        assert result is response_msg

    @pytest.mark.asyncio
    async def test_handle_incoming_no_handler(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "608508a9bd224290"
        mock_msg.message_type = MagicMock(value="unknown_type")

        result = await integration.handle_incoming_message(mock_msg)
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_user_message(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "608508a9bd224290"
        mock_msg.content = {"text": "Hello there, this is a test message."}

        mock_context = MagicMock()
        mock_context.session_id = "s1"
        mock_context.user_id = "u1"

        result = await integration.validate_user_message(mock_msg, mock_context)
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_validate_user_message_empty(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "608508a9bd224290"
        mock_msg.content = {"text": ""}

        result = await integration.validate_user_message(mock_msg, MagicMock())
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_validate_user_message_too_long(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "608508a9bd224290"
        mock_msg.content = {"text": "x" * 20000}

        result = await integration.validate_user_message(mock_msg, MagicMock())
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_validate_user_message_string_content(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()

        mock_msg = MagicMock()
        mock_msg.constitutional_hash = "608508a9bd224290"
        mock_msg.content = "A plain string message for testing."

        result = await integration.validate_user_message(mock_msg, MagicMock())
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_process_nlu_result_governance_disabled(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        integration = AgentBusIntegration(config=IntegrationConfig(enable_governance=False))

        mock_nlu = MagicMock()
        mock_nlu.primary_intent = MagicMock(name="help")
        mock_context = MagicMock()

        result = await integration.process_nlu_result(mock_nlu, mock_context)
        assert result.action_type is not None

    @pytest.mark.asyncio
    async def test_process_nlu_help_intent(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        integration = AgentBusIntegration(config=IntegrationConfig(enable_governance=False))

        mock_nlu = MagicMock()
        mock_nlu.primary_intent = MagicMock()
        mock_nlu.primary_intent.name = "help"
        mock_context = MagicMock()

        result = await integration.process_nlu_result(mock_nlu, mock_context)
        assert "help" in result.response_template.lower()

    @pytest.mark.asyncio
    async def test_process_nlu_default_intent(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        integration = AgentBusIntegration(config=IntegrationConfig(enable_governance=False))

        mock_nlu = MagicMock()
        mock_nlu.primary_intent = MagicMock()
        mock_nlu.primary_intent.name = "something_else"
        mock_context = MagicMock()

        result = await integration.process_nlu_result(mock_nlu, mock_context)
        assert "processing" in result.response_template.lower()

    @pytest.mark.asyncio
    async def test_check_governance_disabled(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import (
            AgentBusIntegration,
            IntegrationConfig,
        )

        integration = AgentBusIntegration(config=IntegrationConfig(enable_governance=False))

        result = await integration._check_governance(MagicMock(), MagicMock())
        assert result["is_allowed"] is True

    @pytest.mark.asyncio
    async def test_execute_task_no_handler(self) -> None:
        from enhanced_agent_bus.ai_assistant.integration import AgentBusIntegration

        integration = AgentBusIntegration()

        result = await integration.execute_task("test_task", {"param": "value"})
        # No handler for task_executor, so should fail gracefully
        assert isinstance(result, dict)
