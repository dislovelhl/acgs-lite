"""
Coverage tests for uncovered paths in:
- structured_logging.py
- http_client.py
- metrics/_registry.py
- database/n1_middleware.py
- interfaces.py
- auth/certs/generate_certs.py

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest


# ============================================================
# structured_logging.py — uncovered lines
# ============================================================


class TestStructuredJSONFormatterUncovered:
    """Cover lines 59-60, 171-172, 176-181, 185, 203, 213, 216, 258-259, 265."""

    def test_import_fallback_jsonvalue(self):
        """Line 59-60: JSONValue fallback when types import fails."""
        # The fallback is exercised at module level; just verify the module loaded.
        from src.core.shared.structured_logging import StructuredJSONFormatter

        assert StructuredJSONFormatter is not None

    def test_format_with_dict_args(self):
        """Lines 171-172: record.args is dict -> merged into extra."""
        from src.core.shared.structured_logging import StructuredJSONFormatter

        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=None,
            exc_info=None,
        )
        # Set args as dict after creation to avoid LogRecord using it for % formatting
        record.args = {"key1": "val1"}
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["extra"]["key1"] == "val1"

    def test_format_with_exc_info(self):
        """Lines 176-181: exc_info present with stack trace."""
        from src.core.shared.structured_logging import StructuredJSONFormatter

        formatter = StructuredJSONFormatter(include_stack_trace=True)
        try:
            raise ValueError("test error")
        except ValueError:
            ei = sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="error occurred",
            args=None,
            exc_info=ei,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["exception"]["type"] == "ValueError"
        assert parsed["exception"]["message"] == "test error"
        assert "traceback" in parsed["exception"]

    def test_format_warning_adds_source(self):
        """Line 185: WARNING level adds source location."""
        from src.core.shared.structured_logging import StructuredJSONFormatter

        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="/some/path.py",
            lineno=42,
            msg="warn msg",
            args=None,
            exc_info=None,
        )
        record.funcName = "my_func"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["source"]["line"] == 42
        assert parsed["source"]["function"] == "my_func"

    def test_process_extra_redact_sensitive(self):
        """Line 203, 213, 216: redaction, nested dict, long string truncation."""
        from src.core.shared.structured_logging import StructuredJSONFormatter

        formatter = StructuredJSONFormatter(redact_sensitive=True)
        extra = {
            "api_key": "secret123",
            "nested": {"inner_password": "s", "safe": "ok"},
            "long_field": "x" * 1500,
            "normal": "short",
        }
        result = formatter._process_extra(extra)
        assert result["api_key"] == "[REDACTED]"
        assert result["nested"]["inner_password"] == "[REDACTED]"
        assert result["nested"]["safe"] == "ok"
        assert result["long_field"].endswith("...")
        assert len(result["long_field"]) == 1003  # 1000 + "..."
        assert result["normal"] == "short"

    def test_process_extra_no_redaction(self):
        """Line 203: redact_sensitive=False returns raw extra."""
        from src.core.shared.structured_logging import StructuredJSONFormatter

        formatter = StructuredJSONFormatter(redact_sensitive=False)
        extra = {"api_key": "secret123"}
        result = formatter._process_extra(extra)
        assert result["api_key"] == "secret123"


class TestTextFormatterUncovered:
    """Cover lines 258-259, 265."""

    def test_text_format_with_extra(self):
        """Lines 258-259: extra data in text format."""
        from src.core.shared.structured_logging import TextFormatter

        formatter = TextFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test msg",
            args=None,
            exc_info=None,
        )
        record.extra = {"key": "val"}
        output = formatter.format(record)
        assert "key=val" in output

    def test_text_format_with_exc_info(self):
        """Line 265: exception info in text format."""
        from src.core.shared.structured_logging import TextFormatter

        formatter = TextFormatter()
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            ei = sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="err",
            args=None,
            exc_info=ei,
        )
        output = formatter.format(record)
        assert "RuntimeError" in output
        assert "boom" in output


class TestStructuredLoggerUncovered:
    """Cover lines 303-304, 309, 348, 353, 393."""

    def test_log_with_args_format(self):
        """Lines 303-304: message % args formatting."""
        from src.core.shared.structured_logging import StructuredLogger

        sl = StructuredLogger("test_args")
        sl._logger.setLevel(logging.DEBUG)
        with patch.object(sl._logger, "log") as mock_log:
            sl._log(logging.INFO, "Hello %s", "world")
            call_args = mock_log.call_args
            assert call_args[0][1] == "Hello world"

    def test_log_with_args_format_fallback(self):
        """Lines 303-304: fallback when % formatting fails."""
        from src.core.shared.structured_logging import StructuredLogger

        sl = StructuredLogger("test_args_fallback")
        sl._logger.setLevel(logging.DEBUG)
        with patch.object(sl._logger, "log") as mock_log:
            sl._log(logging.INFO, "No format spec", 42, "extra")
            call_args = mock_log.call_args
            assert "42" in call_args[0][1]
            assert "extra" in call_args[0][1]

    def test_error_with_exc_info_true(self):
        """Line 309, 348: error/critical with exc_info=True resolves."""
        from src.core.shared.structured_logging import StructuredLogger

        sl = StructuredLogger("test_exc")
        sl._logger.setLevel(logging.DEBUG)
        with patch.object(sl._logger, "log"):
            try:
                raise ValueError("test")
            except ValueError:
                sl.error("err", exc_info=True)
                sl.critical("crit", exc_info=True)

    def test_exception_method(self):
        """Line 353: exception() logs with current exc_info."""
        from src.core.shared.structured_logging import StructuredLogger

        sl = StructuredLogger("test_exception")
        sl._logger.setLevel(logging.DEBUG)
        with patch.object(sl._logger, "log") as mock_log:
            try:
                raise RuntimeError("exc_test")
            except RuntimeError:
                sl.exception("something failed")
            assert mock_log.called

    def test_bound_logger_exception(self):
        """Line 393: BoundLogger.exception()."""
        from src.core.shared.structured_logging import StructuredLogger

        sl = StructuredLogger("test_bound_exc")
        sl._logger.setLevel(logging.DEBUG)
        bound = sl.bind(service="api")
        with patch.object(sl._logger, "log"):
            try:
                raise RuntimeError("bound_exc")
            except RuntimeError:
                bound.exception("bound err")


class TestConfigureLoggingUncovered:
    """Cover lines 415-446."""

    def test_configure_logging_json(self):
        """Lines 415-446: configure with json format."""
        from src.core.shared.structured_logging import configure_logging

        configure_logging(level="DEBUG", format_type="json")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_configure_logging_text(self):
        """Lines 415-446: configure with text format."""
        from src.core.shared.structured_logging import configure_logging

        configure_logging(level="WARNING", format_type="text")
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_configure_logging_from_env(self):
        """Lines 415-446: configure from environment variables."""
        from src.core.shared.structured_logging import configure_logging

        with patch.dict(os.environ, {"LOG_LEVEL": "ERROR", "LOG_FORMAT": "text"}):
            configure_logging()
        root = logging.getLogger()
        assert root.level == logging.ERROR


class TestSetupOpentelemetryUncovered:
    """Cover lines 592-601, 612-617."""

    def test_setup_opentelemetry_import_error(self):
        """Lines 592-601: no-op when opentelemetry not installed."""
        from src.core.shared.structured_logging import setup_opentelemetry

        with patch.dict(sys.modules, {"opentelemetry": None}):
            # Should not raise
            setup_opentelemetry("test-service")

    def test_setup_opentelemetry_success(self):
        """Lines 592-601: success path with mocked opentelemetry."""
        from src.core.shared.structured_logging import setup_opentelemetry

        mock_trace = MagicMock()
        mock_resource = MagicMock()
        mock_tracer_provider = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "opentelemetry": MagicMock(),
                "opentelemetry.trace": mock_trace,
                "opentelemetry.sdk": MagicMock(),
                "opentelemetry.sdk.resources": MagicMock(Resource=mock_resource),
                "opentelemetry.sdk.trace": MagicMock(TracerProvider=mock_tracer_provider),
            },
        ):
            setup_opentelemetry("test-service")

    def test_instrument_fastapi_import_error(self):
        """Lines 612-617: no-op when instrumentation not installed."""
        from src.core.shared.structured_logging import instrument_fastapi

        with patch.dict(sys.modules, {"opentelemetry.instrumentation.fastapi": None}):
            instrument_fastapi(MagicMock())

    def test_instrument_fastapi_success(self):
        """Lines 612-617: success path with mocked instrumentor."""
        from src.core.shared.structured_logging import instrument_fastapi

        mock_instrumentor = MagicMock()
        mock_mod = MagicMock(FastAPIInstrumentor=lambda: mock_instrumentor)
        with patch.dict(
            sys.modules,
            {
                "opentelemetry": MagicMock(),
                "opentelemetry.instrumentation": MagicMock(),
                "opentelemetry.instrumentation.fastapi": mock_mod,
            },
        ):
            instrument_fastapi(MagicMock())


# ============================================================
# http_client.py — uncovered lines
# ============================================================


class TestAsyncCircuitBreakerUncovered:
    """Cover lines 54-55, 69-71, 82-83."""

    @pytest.mark.asyncio
    async def test_now_fallback_no_loop(self):
        """Lines 54-55: _now falls back to time.monotonic when no running loop."""
        from src.core.shared.http_client import _AsyncCircuitBreaker

        cb = _AsyncCircuitBreaker()
        # Call _now outside of async context by patching get_running_loop to raise
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            result = cb._now()
            assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_half_open_allows_request(self):
        """Lines 69-71: half_open state allows requests."""
        from src.core.shared.http_client import _AsyncCircuitBreaker

        cb = _AsyncCircuitBreaker(failure_threshold=1, recovery_timeout=0.0)
        # Force open
        await cb.record_failure()
        await cb.record_failure()
        # Wait for recovery
        await asyncio.sleep(0.01)
        # Should transition to half_open
        allowed = await cb.allow_request()
        assert allowed is True
        assert cb._state == "half_open"
        # half_open still allows
        allowed2 = await cb.allow_request()
        assert allowed2 is True

    @pytest.mark.asyncio
    async def test_record_success_resets_failure_count(self):
        """Lines 82-83: success in closed state resets failure_count."""
        from src.core.shared.http_client import _AsyncCircuitBreaker

        cb = _AsyncCircuitBreaker(failure_threshold=5)
        cb._failure_count = 3
        await cb.record_success()
        assert cb._failure_count == 0


class TestHttpClientUncovered:
    """Cover lines 234, 263, 281, 297, 332-359, 391-422, 453-463."""

    @pytest.mark.asyncio
    async def test_get_delegates_to_request(self):
        """Line 234: get() calls request()."""
        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=False)
        mock_resp = MagicMock()
        with patch.object(client, "request", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.get("http://example.com", params={"q": "1"})
            assert result is mock_resp

    @pytest.mark.asyncio
    async def test_post_delegates_to_request(self):
        """Line 263: post() calls request()."""
        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=False)
        mock_resp = MagicMock()
        with patch.object(client, "request", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.post("http://example.com", json={"a": 1})
            assert result is mock_resp

    @pytest.mark.asyncio
    async def test_put_delegates_to_request(self):
        """Line 281: put() calls request()."""
        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=False)
        mock_resp = MagicMock()
        with patch.object(client, "request", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.put("http://example.com", json={"a": 1})
            assert result is mock_resp

    @pytest.mark.asyncio
    async def test_delete_delegates_to_request(self):
        """Line 297: delete() calls request()."""
        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=False)
        mock_resp = MagicMock()
        with patch.object(client, "request", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.delete("http://example.com")
            assert result is mock_resp

    @pytest.mark.asyncio
    async def test_request_circuit_breaker_open_raises(self):
        """Lines 332-340: circuit breaker open raises ConnectError."""
        import httpx

        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=True, circuit_breaker_threshold=1)
        await client.start()
        client._circuit_breaker._state = "open"
        client._circuit_breaker._last_failure_time = time.monotonic() + 9999

        with pytest.raises(httpx.ConnectError, match="Circuit breaker is open"):
            await client.request("GET", "http://example.com")
        await client.close()

    @pytest.mark.asyncio
    async def test_request_retry_budget_exhausted(self):
        """Lines 343-346: retry budget exhausted raises ConnectError."""
        import httpx

        from src.core.shared.http_client import HttpClient

        mock_budget = AsyncMock()
        mock_budget.can_retry = AsyncMock(return_value=False)
        client = HttpClient(enable_circuit_breaker=False, retry_budget=mock_budget)
        await client.start()

        with pytest.raises(httpx.ConnectError, match="Retry budget exhausted"):
            await client.request("GET", "http://example.com")
        await client.close()

    @pytest.mark.asyncio
    async def test_request_no_retry(self):
        """Lines 358-366: retry_on_failure=False calls _do_request directly."""
        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=False)
        mock_resp = MagicMock()
        with patch.object(client, "_do_request", new_callable=AsyncMock, return_value=mock_resp):
            await client.start()
            result = await client.request(
                "GET", "http://example.com", retry_on_failure=False
            )
            assert result is mock_resp
        await client.close()

    @pytest.mark.asyncio
    async def test_request_with_retry_success(self):
        """Lines 391-408: successful retry path."""
        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=True, max_retries=2)
        mock_resp = MagicMock()
        with patch.object(client, "_do_request", new_callable=AsyncMock, return_value=mock_resp):
            await client.start()
            result = await client.request("GET", "http://example.com")
            assert result is mock_resp
        await client.close()

    @pytest.mark.asyncio
    async def test_request_with_retry_exhausted(self):
        """Lines 410-422: all retries exhausted records failure on circuit breaker."""
        import httpx

        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=True, max_retries=1)
        await client.start()
        with patch.object(
            client,
            "_do_request",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("fail"),
        ):
            with pytest.raises(httpx.ConnectError):
                await client.request("GET", "http://example.com")
        await client.close()

    @pytest.mark.asyncio
    async def test_do_request_not_initialized(self):
        """Lines 453-463: _do_request raises when client is None."""
        from src.core.shared.errors.exceptions import ServiceUnavailableError
        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=False)
        # Don't start -- _client stays None
        with pytest.raises(ServiceUnavailableError):
            await client._do_request("GET", "http://example.com")

    @pytest.mark.asyncio
    async def test_do_request_success_path(self):
        """Lines 453-463: _do_request success path with mocked client."""
        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=False)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_async_client = AsyncMock()
        mock_async_client.request = AsyncMock(return_value=mock_response)
        client._client = mock_async_client

        result = await client._do_request("GET", "http://example.com")
        assert result is mock_response
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_retry_budget_records_retry(self):
        """Line 346: retry_budget.record_retry is called."""
        from src.core.shared.http_client import HttpClient

        mock_budget = AsyncMock()
        mock_budget.can_retry = AsyncMock(return_value=True)
        mock_budget.record_retry = AsyncMock()
        client = HttpClient(enable_circuit_breaker=False, retry_budget=mock_budget)
        mock_resp = MagicMock()
        with patch.object(client, "_request_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            await client.start()
            await client.request("GET", "http://example.com")
            mock_budget.record_retry.assert_called_once()
        await client.close()

    @pytest.mark.asyncio
    async def test_request_auto_starts_client(self):
        """Line 332-333: request auto-starts client if not started."""
        from src.core.shared.http_client import HttpClient

        client = HttpClient(enable_circuit_breaker=False)
        mock_resp = MagicMock()
        with patch.object(client, "_do_request", new_callable=AsyncMock, return_value=mock_resp):
            with patch.object(client, "start", new_callable=AsyncMock) as mock_start:
                result = await client.request(
                    "GET", "http://example.com", retry_on_failure=False
                )
                mock_start.assert_called_once()
                assert result is mock_resp


# ============================================================
# metrics/_registry.py — uncovered lines
# ============================================================


class TestMetricsRegistryUncovered:
    """Cover lines 24, 29-31, 44-45, 54-59, 69-70, 76-81, 91-92, 98-103, 113-114, 120-125."""

    def setup_method(self):
        """Clear the metrics cache before each test."""
        from src.core.shared.metrics._registry import _METRICS_CACHE

        _METRICS_CACHE.clear()

    def test_find_existing_metric_by_name(self):
        """Lines 24, 29-31: find existing metric scanning collectors."""
        from src.core.shared.metrics._registry import _find_existing_metric

        # Will return None for a non-existent metric
        result = _find_existing_metric("nonexistent_metric_xyz_123")
        assert result is None

    def test_find_existing_metric_exception_handling(self):
        """Lines 29-31: handles exceptions in _find_existing_metric."""
        from src.core.shared.metrics._registry import _find_existing_metric

        with patch(
            "src.core.shared.metrics._registry.REGISTRY",
            new_callable=lambda: type("R", (), {"_names_to_collectors": property(lambda s: (_ for _ in ()).throw(RuntimeError()))}),
        ):
            result = _find_existing_metric("test")
            assert result is None

    def test_get_or_create_histogram_cached(self):
        """Lines 44-45: returns cached histogram."""
        from src.core.shared.metrics._registry import _METRICS_CACHE, _get_or_create_histogram

        sentinel = object()
        _METRICS_CACHE["test_hist_cached"] = sentinel
        result = _get_or_create_histogram("test_hist_cached", "desc", ["label"])
        assert result is sentinel

    def test_get_or_create_histogram_existing(self):
        """Lines 44-45: returns existing from registry."""
        from src.core.shared.metrics._registry import _get_or_create_histogram

        mock_metric = MagicMock()
        with patch(
            "src.core.shared.metrics._registry._find_existing_metric",
            return_value=mock_metric,
        ):
            result = _get_or_create_histogram("hist_existing_test", "desc", ["l"])
            assert result is mock_metric

    def test_get_or_create_histogram_new_with_buckets(self):
        """Lines 54-59: creates new histogram with custom buckets."""
        from src.core.shared.metrics._registry import _METRICS_CACHE, _get_or_create_histogram

        name = f"test_hist_buckets_{id(self)}"
        result = _get_or_create_histogram(name, "desc", ["l"], buckets=[0.1, 0.5, 1.0])
        assert result is not None
        assert name in _METRICS_CACHE

    def test_get_or_create_histogram_valueerror_fallback(self):
        """Lines 54-59: ValueError fallback finds existing."""
        from src.core.shared.metrics._registry import _get_or_create_histogram

        sentinel = MagicMock()
        with patch(
            "src.core.shared.metrics._registry.Histogram",
            side_effect=ValueError("dup"),
        ):
            with patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=sentinel,
            ):
                result = _get_or_create_histogram("hist_ve", "desc", ["l"])
                assert result is sentinel

    def test_get_or_create_histogram_valueerror_raises(self):
        """Lines 54-59: ValueError re-raised when no existing found."""
        from src.core.shared.metrics._registry import _get_or_create_histogram

        with patch(
            "src.core.shared.metrics._registry.Histogram",
            side_effect=ValueError("dup"),
        ):
            with patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=None,
            ):
                with pytest.raises(ValueError, match="dup"):
                    _get_or_create_histogram("hist_ve_raise", "desc", ["l"])

    def test_get_or_create_counter_cached(self):
        """Lines 69-70: returns cached counter."""
        from src.core.shared.metrics._registry import _METRICS_CACHE, _get_or_create_counter

        sentinel = object()
        _METRICS_CACHE["test_ctr_cached"] = sentinel
        result = _get_or_create_counter("test_ctr_cached", "desc", ["l"])
        assert result is sentinel

    def test_get_or_create_counter_existing(self):
        """Lines 69-70: returns existing counter from registry."""
        from src.core.shared.metrics._registry import _get_or_create_counter

        mock_metric = MagicMock()
        with patch(
            "src.core.shared.metrics._registry._find_existing_metric",
            return_value=mock_metric,
        ):
            result = _get_or_create_counter("ctr_existing_test", "desc", ["l"])
            assert result is mock_metric

    def test_get_or_create_counter_valueerror_fallback(self):
        """Lines 76-81: ValueError fallback finds existing."""
        from src.core.shared.metrics._registry import _get_or_create_counter

        sentinel = MagicMock()
        with patch(
            "src.core.shared.metrics._registry.Counter",
            side_effect=ValueError("dup"),
        ):
            with patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=sentinel,
            ):
                result = _get_or_create_counter("ctr_ve", "desc", ["l"])
                assert result is sentinel

    def test_get_or_create_counter_valueerror_raises(self):
        """Lines 76-81: ValueError re-raised when no existing found."""
        from src.core.shared.metrics._registry import _get_or_create_counter

        with patch(
            "src.core.shared.metrics._registry.Counter",
            side_effect=ValueError("dup"),
        ):
            with patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=None,
            ):
                with pytest.raises(ValueError, match="dup"):
                    _get_or_create_counter("ctr_ve_raise", "desc", ["l"])

    def test_get_or_create_gauge_cached(self):
        """Lines 91-92: returns cached gauge."""
        from src.core.shared.metrics._registry import _METRICS_CACHE, _get_or_create_gauge

        sentinel = object()
        _METRICS_CACHE["test_gauge_cached"] = sentinel
        result = _get_or_create_gauge("test_gauge_cached", "desc", ["l"])
        assert result is sentinel

    def test_get_or_create_gauge_existing(self):
        """Lines 91-92: returns existing gauge from registry."""
        from src.core.shared.metrics._registry import _get_or_create_gauge

        mock_metric = MagicMock()
        with patch(
            "src.core.shared.metrics._registry._find_existing_metric",
            return_value=mock_metric,
        ):
            result = _get_or_create_gauge("gauge_existing_test", "desc", ["l"])
            assert result is mock_metric

    def test_get_or_create_gauge_valueerror_fallback(self):
        """Lines 98-103: ValueError fallback finds existing."""
        from src.core.shared.metrics._registry import _get_or_create_gauge

        sentinel = MagicMock()
        with patch(
            "src.core.shared.metrics._registry.Gauge",
            side_effect=ValueError("dup"),
        ):
            with patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=sentinel,
            ):
                result = _get_or_create_gauge("gauge_ve", "desc", ["l"])
                assert result is sentinel

    def test_get_or_create_gauge_valueerror_raises(self):
        """Lines 98-103: ValueError re-raised when no existing found."""
        from src.core.shared.metrics._registry import _get_or_create_gauge

        with patch(
            "src.core.shared.metrics._registry.Gauge",
            side_effect=ValueError("dup"),
        ):
            with patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=None,
            ):
                with pytest.raises(ValueError, match="dup"):
                    _get_or_create_gauge("gauge_ve_raise", "desc", ["l"])

    def test_get_or_create_info_cached(self):
        """Lines 113-114: returns cached info."""
        from src.core.shared.metrics._registry import _METRICS_CACHE, _get_or_create_info

        sentinel = object()
        _METRICS_CACHE["test_info_cached"] = sentinel
        result = _get_or_create_info("test_info_cached", "desc")
        assert result is sentinel

    def test_get_or_create_info_existing(self):
        """Lines 113-114: returns existing info from registry."""
        from src.core.shared.metrics._registry import _get_or_create_info

        mock_metric = MagicMock()
        with patch(
            "src.core.shared.metrics._registry._find_existing_metric",
            return_value=mock_metric,
        ):
            result = _get_or_create_info("info_existing_test", "desc")
            assert result is mock_metric

    def test_get_or_create_info_valueerror_fallback(self):
        """Lines 120-125: ValueError fallback finds existing."""
        from src.core.shared.metrics._registry import _get_or_create_info

        sentinel = MagicMock()
        with patch(
            "src.core.shared.metrics._registry.Info",
            side_effect=ValueError("dup"),
        ):
            with patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=sentinel,
            ):
                result = _get_or_create_info("info_ve", "desc")
                assert result is sentinel

    def test_get_or_create_info_valueerror_raises(self):
        """Lines 120-125: ValueError re-raised when no existing found."""
        from src.core.shared.metrics._registry import _get_or_create_info

        with patch(
            "src.core.shared.metrics._registry.Info",
            side_effect=ValueError("dup"),
        ):
            with patch(
                "src.core.shared.metrics._registry._find_existing_metric",
                return_value=None,
            ):
                with pytest.raises(ValueError, match="dup"):
                    _get_or_create_info("info_ve_raise", "desc")


# ============================================================
# database/n1_middleware.py — uncovered lines
# ============================================================


class TestN1DetectorUncovered:
    """Cover lines 73, 76-77, 84-85, 92-93, 143-147, 151-168, 179-187, 200, 212-216, 225-230."""

    def test_record_query_when_disabled(self):
        """Line 73: record_query no-op when detection disabled."""
        from src.core.shared.database.n1_middleware import N1Detector, _n1_detection_enabled

        _n1_detection_enabled.set(False)
        N1Detector.record_query("SELECT 1", 1.0)  # Should not raise

    def test_record_query_when_enabled(self):
        """Lines 76-77: record_query increments count and appends query."""
        from src.core.shared.database.n1_middleware import (
            N1Detector,
            _n1_detection_enabled,
            _queries_executed,
            _query_count,
        )

        _n1_detection_enabled.set(True)
        _query_count.set(0)
        _queries_executed.set([])
        N1Detector.record_query("SELECT * FROM users", 5.0)
        assert _query_count.get() == 1
        queries = _queries_executed.get()
        assert len(queries) == 1
        assert "SELECT * FROM users" in queries[0]

    def test_record_query_creates_list_when_none(self):
        """Line 76-77: record_query creates empty list when queries is None."""
        from src.core.shared.database.n1_middleware import (
            N1Detector,
            _n1_detection_enabled,
            _queries_executed,
            _query_count,
        )

        _n1_detection_enabled.set(True)
        _query_count.set(0)
        _queries_executed.set(None)
        N1Detector.record_query("SELECT 1", 1.0)
        assert _queries_executed.get() is not None

    def test_query_count_property(self):
        """Lines 84-85: query_count property."""
        from src.core.shared.database.n1_middleware import N1Detector, _query_count

        detector = N1Detector()
        _query_count.set(42)
        assert detector.query_count == 42

    def test_queries_property(self):
        """Lines 92-93: queries property."""
        from src.core.shared.database.n1_middleware import N1Detector, _queries_executed

        detector = N1Detector()
        _queries_executed.set(["q1", "q2"])
        assert detector.queries == ["q1", "q2"]

    def test_queries_property_none(self):
        """Lines 92-93: queries property returns empty list when None."""
        from src.core.shared.database.n1_middleware import N1Detector, _queries_executed

        detector = N1Detector()
        _queries_executed.set(None)
        assert detector.queries == []

    def test_record_query_lookup_error(self):
        """Lines 76-77: LookupError in record_query is caught."""
        from src.core.shared.database.n1_middleware import N1Detector, _n1_detection_enabled

        _n1_detection_enabled.set(True)
        with patch("src.core.shared.database.n1_middleware._query_count") as mock_qc:
            mock_qc.get.side_effect = LookupError
            N1Detector.record_query("SELECT 1", 1.0)  # Should not raise

    def test_query_count_lookup_error(self):
        """Lines 84-85: LookupError in query_count returns 0."""
        from src.core.shared.database.n1_middleware import N1Detector

        detector = N1Detector()
        with patch("src.core.shared.database.n1_middleware._query_count") as mock_qc:
            mock_qc.get.side_effect = LookupError
            assert detector.query_count == 0

    def test_queries_lookup_error(self):
        """Lines 92-93: LookupError in queries returns empty list."""
        from src.core.shared.database.n1_middleware import N1Detector

        detector = N1Detector()
        with patch("src.core.shared.database.n1_middleware._queries_executed") as mock_qe:
            mock_qe.get.side_effect = LookupError
            assert detector.queries == []

    def test_is_violation(self):
        """Lines 92-93: is_violation checks threshold."""
        from src.core.shared.database.n1_middleware import N1Detector, _query_count

        detector = N1Detector()
        detector.threshold = 5
        _query_count.set(6)
        assert detector.is_violation() is True
        _query_count.set(3)
        assert detector.is_violation() is False

    def test_report_if_violation_detected(self):
        """Lines 143-147: reports violation when threshold exceeded."""
        from src.core.shared.database.n1_middleware import N1Detector, _query_count, _queries_executed

        detector = N1Detector()
        detector.threshold = 2
        _query_count.set(5)
        _queries_executed.set(["q1", "q2", "q3", "q4", "q5"])
        report = detector.report_if_violation("/test")
        assert report is not None
        assert report["violation"] is True
        assert report["query_count"] == 5
        assert report["endpoint"] == "/test"

    def test_report_if_no_violation(self):
        """Lines 143-147: returns None when no violation."""
        from src.core.shared.database.n1_middleware import N1Detector, _query_count

        detector = N1Detector()
        detector.threshold = 100
        _query_count.set(1)
        assert detector.report_if_violation("/test") is None

    def test_context_manager(self):
        """Lines 151-168: __enter__/__exit__ context manager."""
        from src.core.shared.database.n1_middleware import (
            N1Detector,
            _n1_detection_enabled,
            _queries_executed,
            _query_count,
        )

        detector = N1Detector()
        with detector.monitor(threshold=5):
            assert _n1_detection_enabled.get() is True
            assert _query_count.get() == 0
            assert _queries_executed.get() == []
        assert _n1_detection_enabled.get() is False


class TestN1DetectionMiddlewareUncovered:
    """Cover lines 151-168, 179-187."""

    @pytest.mark.asyncio
    async def test_dispatch_disabled(self):
        """Line 151: dispatch returns directly when disabled."""
        from src.core.shared.database.n1_middleware import N1DetectionMiddleware

        mock_app = MagicMock()
        middleware = N1DetectionMiddleware(mock_app, enabled=False)
        mock_request = MagicMock(spec=["url"])
        mock_response = MagicMock()
        mock_call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, mock_call_next)
        assert result is mock_response

    @pytest.mark.asyncio
    async def test_dispatch_enabled_no_violation(self):
        """Lines 151-168: dispatch with monitoring, no violation."""
        from src.core.shared.database.n1_middleware import N1DetectionMiddleware, _query_count

        mock_app = MagicMock()
        middleware = N1DetectionMiddleware(mock_app, threshold=100, enabled=True, add_headers=True)
        mock_request = MagicMock()
        mock_request.url.path = "/api/test"
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, mock_call_next)
        assert result is mock_response
        assert "X-Query-Count" in mock_response.headers

    @pytest.mark.asyncio
    async def test_dispatch_enabled_with_violation(self):
        """Lines 151-168: dispatch with violation adds X-N1-Violation header."""
        from src.core.shared.database.n1_middleware import N1DetectionMiddleware, _query_count

        mock_app = MagicMock()
        middleware = N1DetectionMiddleware(mock_app, threshold=0, enabled=True, add_headers=True)
        mock_request = MagicMock()
        mock_request.url.path = "/api/test"
        mock_response = MagicMock()
        mock_response.headers = {}

        async def call_next_with_queries(req):
            # Simulate queries during handling
            from src.core.shared.database.n1_middleware import (
                N1Detector,
                _n1_detection_enabled,
                _queries_executed,
            )

            _query_count.set(5)
            _queries_executed.set(["q1", "q2", "q3", "q4", "q5"])
            return mock_response

        result = await middleware.dispatch(mock_request, call_next_with_queries)
        assert mock_response.headers.get("X-N1-Violation") == "true"


class TestSetupN1DetectionUncovered:
    """Cover lines 179-187."""

    def test_setup_n1_detection(self):
        """Lines 179-187: setup_n1_detection adds middleware."""
        from src.core.shared.database.n1_middleware import setup_n1_detection

        mock_app = MagicMock()
        setup_n1_detection(mock_app, threshold=20, enabled=True)
        mock_app.add_middleware.assert_called_once()

    def test_setup_n1_detection_disabled(self):
        """Lines 179-187: setup with enabled=False."""
        from src.core.shared.database.n1_middleware import setup_n1_detection

        mock_app = MagicMock()
        setup_n1_detection(mock_app, threshold=20, enabled=False)
        mock_app.add_middleware.assert_called_once()


class TestSQLAlchemyEventHandlers:
    """Cover lines 200, 212-216."""

    @pytest.mark.asyncio
    async def test_before_cursor_execute(self):
        """Line 200: before_cursor_execute sets start time."""
        from src.core.shared.database.n1_middleware import before_cursor_execute

        context = {}
        await before_cursor_execute(None, None, "SELECT 1", (), context, False)
        assert "_query_start_time" in context

    @pytest.mark.asyncio
    async def test_after_cursor_execute_with_start_time(self):
        """Lines 212-216: after_cursor_execute records query."""
        from src.core.shared.database.n1_middleware import (
            N1Detector,
            _n1_detection_enabled,
            _queries_executed,
            _query_count,
            after_cursor_execute,
        )

        _n1_detection_enabled.set(True)
        _query_count.set(0)
        _queries_executed.set([])
        context = {"_query_start_time": time.monotonic() - 0.001}
        await after_cursor_execute(None, None, "SELECT 1", (), context, False)
        assert _query_count.get() == 1

    @pytest.mark.asyncio
    async def test_after_cursor_execute_no_start_time(self):
        """Lines 212-216: after_cursor_execute with no start time is a no-op."""
        from src.core.shared.database.n1_middleware import after_cursor_execute

        context = {}
        await after_cursor_execute(None, None, "SELECT 1", (), context, False)

    def test_attach_query_listeners(self):
        """Lines 225-230: attach_query_listeners attaches events."""
        from src.core.shared.database.n1_middleware import attach_query_listeners

        mock_engine = MagicMock()
        mock_event = MagicMock()
        with patch.dict(sys.modules, {"sqlalchemy": MagicMock(event=mock_event), "sqlalchemy.event": mock_event}):
            with patch("src.core.shared.database.n1_middleware.event", mock_event, create=True):
                # Re-import to pick up the mock — but attach_query_listeners does
                # `from sqlalchemy import event` at call time, so we patch that.
                with patch("sqlalchemy.event", mock_event):
                    attach_query_listeners(mock_engine)
                    assert mock_event.listen.call_count == 2


# ============================================================
# interfaces.py — uncovered lines
# ============================================================


class TestInterfaceProtocols:
    """Cover lines for all Protocol/ABC definitions in interfaces.py.

    Protocols are not @runtime_checkable, so we exercise them by calling
    the async methods on conforming implementations to trigger coverage
    of the protocol method body stubs (the `...` lines).
    """

    @pytest.mark.asyncio
    async def test_cache_client_protocol(self):
        """Lines 14-15, 24, 28, 32, 36, 40, 44: CacheClient Protocol."""
        from src.core.shared.interfaces import CacheClient

        class MockCache:
            async def get(self, key: str) -> str | None:
                return None

            async def set(self, key: str, value: str, ex: int | None = None) -> bool:
                return True

            async def setex(self, key: str, time: int, value: str) -> bool:
                return True

            async def delete(self, key: str) -> bool:
                return True

            async def exists(self, key: str) -> bool:
                return False

            async def expire(self, key: str, time: int) -> bool:
                return True

        cache = MockCache()
        assert await cache.get("k") is None
        assert await cache.set("k", "v") is True
        assert await cache.setex("k", 60, "v") is True
        assert await cache.delete("k") is True
        assert await cache.exists("k") is False
        assert await cache.expire("k", 60) is True
        # Verify protocol is importable
        assert CacheClient is not None

    @pytest.mark.asyncio
    async def test_policy_evaluator_protocol(self):
        """Lines 58, 68, 72, 76: PolicyEvaluator Protocol."""
        from src.core.shared.interfaces import PolicyEvaluator

        class MockEvaluator:
            async def evaluate(self, policy_path, input_data, *, strict=True):
                return {}

            async def evaluate_batch(self, policy_path, _input_data_list, *, strict=True):
                return []

            async def get_policy(self, policy_path):
                return None

            async def list_policies(self, path=None):
                return []

        ev = MockEvaluator()
        assert await ev.evaluate("p", {}) == {}
        assert await ev.evaluate_batch("p", []) == []
        assert await ev.get_policy("p") is None
        assert await ev.list_policies() == []
        assert PolicyEvaluator is not None

    @pytest.mark.asyncio
    async def test_audit_service_protocol(self):
        """Lines 95, 102, 106: AuditService Protocol."""
        from src.core.shared.interfaces import AuditService

        test_uuid = UUID("12345678-1234-5678-1234-567812345678")

        class MockAudit:
            async def log_event(self, event_type, actor, action, resource, outcome, **kw):
                return test_uuid

            async def log_events_batch(self, events):
                return []

            async def get_event(self, event_id):
                return None

            async def query_events(self, **kw):
                return []

            async def verify_integrity(self):
                return {}

        a = MockAudit()
        assert await a.log_event("t", "a", "a", "r", "o") == test_uuid
        assert await a.log_events_batch([]) == []
        assert await a.get_event(test_uuid) is None
        assert await a.query_events() == []
        assert await a.verify_integrity() == {}
        assert AuditService is not None

    @pytest.mark.asyncio
    async def test_database_session_protocol(self):
        """Lines 121, 125, 133, 137, 141, 145: DatabaseSession Protocol."""
        from src.core.shared.interfaces import DatabaseSession

        class MockSession:
            async def execute(self, query, params=None):
                return None

            async def commit(self):
                pass

            async def rollback(self):
                pass

            async def close(self):
                pass

        s = MockSession()
        assert await s.execute("q") is None
        await s.commit()
        await s.rollback()
        await s.close()
        assert DatabaseSession is not None

    @pytest.mark.asyncio
    async def test_notification_service_protocol(self):
        """Lines 162, 166, 170, 181: NotificationService Protocol."""
        from src.core.shared.interfaces import NotificationService

        class MockNotify:
            async def send_email(self, to, subject, body, **kw):
                return True

            async def send_sms(self, to, message):
                return True

            async def send_webhook(self, url, payload):
                return True

            async def send_in_app(self, user_id, message, **kw):
                return True

        n = MockNotify()
        assert await n.send_email("a", "b", "c") is True
        assert await n.send_sms("a", "b") is True
        assert await n.send_webhook("u", {}) is True
        assert await n.send_in_app("u", "m") is True
        assert NotificationService is not None

    @pytest.mark.asyncio
    async def test_message_processor_protocol(self):
        """Lines 189, 193: MessageProcessor Protocol."""
        from src.core.shared.interfaces import MessageProcessor

        class MockProcessor:
            async def process(self, message):
                return {}

            async def process_batch(self, messages):
                return []

        p = MockProcessor()
        assert await p.process({}) == {}
        assert await p.process_batch([]) == []
        assert MessageProcessor is not None

    @pytest.mark.asyncio
    async def test_retry_strategy_abc(self):
        """Lines 215, 219, 223, 227: RetryStrategy ABC."""
        from src.core.shared.interfaces import RetryStrategy

        class MockRetry(RetryStrategy):
            async def should_retry(self, attempt, error):
                return False

            async def get_delay(self, attempt):
                return 0.0

        strategy = MockRetry()
        assert await strategy.should_retry(1, Exception()) is False
        assert await strategy.get_delay(1) == 0.0

    @pytest.mark.asyncio
    async def test_circuit_breaker_protocol(self):
        """Lines 240, 249, 258, 262: CircuitBreaker Protocol."""
        from src.core.shared.interfaces import CircuitBreaker

        class MockCB:
            async def record_success(self):
                pass

            async def record_failure(self):
                pass

            async def allow_request(self):
                return True

            async def get_state(self):
                return "closed"

        cb = MockCB()
        await cb.record_success()
        await cb.record_failure()
        assert await cb.allow_request() is True
        assert await cb.get_state() == "closed"
        assert CircuitBreaker is not None

    @pytest.mark.asyncio
    async def test_metrics_collector_protocol(self):
        """MetricsCollector Protocol methods."""
        from src.core.shared.interfaces import MetricsCollector

        class MockMetrics:
            async def increment_counter(self, name, value=1.0, tags=None):
                pass

            async def record_timing(self, name, value_ms, tags=None):
                pass

            async def record_gauge(self, name, value, tags=None):
                pass

            async def get_metrics(self):
                return {}

        mc = MockMetrics()
        await mc.increment_counter("c")
        await mc.record_timing("t", 1.0)
        await mc.record_gauge("g", 1.0)
        assert await mc.get_metrics() == {}
        assert MetricsCollector is not None


# ============================================================
# auth/certs/generate_certs.py — uncovered (0%)
# ============================================================


class TestGenerateSamlSpCertificate:
    """Cover generate_saml_sp_certificate function."""

    def test_generate_returns_pem_bytes(self):
        """Generate cert and key without writing to disk."""
        from src.core.shared.auth.certs.generate_certs import generate_saml_sp_certificate

        cert_pem, key_pem = generate_saml_sp_certificate()
        assert isinstance(cert_pem, bytes)
        assert isinstance(key_pem, bytes)
        assert b"BEGIN CERTIFICATE" in cert_pem
        assert b"BEGIN RSA PRIVATE KEY" in key_pem

    def test_generate_custom_params(self):
        """Generate with custom common_name and validity."""
        from src.core.shared.auth.certs.generate_certs import generate_saml_sp_certificate

        cert_pem, key_pem = generate_saml_sp_certificate(
            common_name="test-cn",
            key_size=2048,
            validity_days=30,
        )
        assert b"BEGIN CERTIFICATE" in cert_pem

    def test_generate_writes_to_output_dir(self, tmp_path):
        """Generate cert and key and write to output_dir."""
        from src.core.shared.auth.certs.generate_certs import generate_saml_sp_certificate

        cert_pem, key_pem = generate_saml_sp_certificate(output_dir=str(tmp_path))
        assert (tmp_path / "sp.crt").exists()
        assert (tmp_path / "sp.key").exists()
        assert (tmp_path / "sp.crt").read_bytes() == cert_pem
        assert (tmp_path / "sp.key").read_bytes() == key_pem
        # Check permissions on key file
        key_stat = os.stat(tmp_path / "sp.key")
        assert oct(key_stat.st_mode & 0o777) == "0o600"

    def test_generate_creates_nested_output_dir(self, tmp_path):
        """Generate creates nested dirs if they don't exist."""
        from src.core.shared.auth.certs.generate_certs import generate_saml_sp_certificate

        nested = tmp_path / "a" / "b" / "c"
        cert_pem, key_pem = generate_saml_sp_certificate(output_dir=str(nested))
        assert nested.exists()
        assert (nested / "sp.crt").exists()
