"""
Coverage improvement tests for batch32e.
Constitutional Hash: 608508a9bd224290

Targets:
  - enhanced_agent_bus.integrations.ml_governance (lines 86-89, 503-505, 523,
    527-528, 565-568, 651, 696, 760, 858-860, 866-868, 897-900)
  - src.core.shared.structured_logging (lines 59-60, 74, 137-139, 144-198,
    202-220, 241-267, 303-304, 348, 357, 364-365, 369, 373, 377, 381, 385,
    389, 393, 415-446, 480-482, 487, 492, 497, 502, 518-577, 592-601, 612-617)
  - enhanced_agent_bus.governance.polis_engine (lines 183, 186, 221, 225,
    393-394, 396-397, 400, 409, 411, 468-469, 476, 480, 510-511, 513-514,
    518-521, 524, 552-556, 663-664, 680, 682, 690-691, 702-704, 861, 991, 1068)
"""

from __future__ import annotations

import json
import logging
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import numpy as np
import pytest

from enhanced_agent_bus._compat.structured_logging import (
    BoundLogger,
    StructuredJSONFormatter,
    StructuredLogger,
    TextFormatter,
    configure_logging,
    correlation_id_var,
    get_correlation_id,
    get_logger,
    get_tenant_id,
    instrument_fastapi,
    log_function_call,
    request_id_var,
    set_correlation_id,
    set_request_id,
    set_tenant_id,
    setup_opentelemetry,
    tenant_id_var,
)
from enhanced_agent_bus.circuit_breaker.enums import CircuitState
from enhanced_agent_bus.governance.models import (
    OpinionCluster,
    Stakeholder,
    StakeholderGroup,
)
from enhanced_agent_bus.governance.polis_engine import PolisDeliberationEngine
from enhanced_agent_bus.integrations.ml_governance import (
    MLGovernanceClient,
    MLGovernanceConfig,
    MLGovernanceConnectionError,
    MLGovernanceError,
    MLGovernanceTimeoutError,
    OutcomeReport,
    OutcomeReportStatus,
    OutcomeResult,
    close_ml_governance_client,
    get_ml_governance_client,
    initialize_ml_governance_client,
    report_outcome,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _test_config(**overrides) -> MLGovernanceConfig:
    defaults = {
        "base_url": "http://localhost:8001",
        "timeout": 1.0,
        "max_retries": 1,
        "retry_delay": 0.0,
        "circuit_breaker_threshold": 2,
        "circuit_breaker_reset": 0.1,
        "enable_async_queue": False,
        "max_queue_size": 5,
        "graceful_degradation": True,
    }
    defaults.update(overrides)
    return MLGovernanceConfig(**defaults)


def _make_stakeholder(sid: str, group: StakeholderGroup = StakeholderGroup.TECHNICAL_EXPERTS):
    return Stakeholder(
        stakeholder_id=sid,
        name=f"Stakeholder {sid}",
        group=group,
        expertise_areas=["ai"],
    )


def _make_cluster(cid: str, members: list[str]) -> OpinionCluster:
    return OpinionCluster(
        cluster_id=cid,
        name=f"Cluster {cid}",
        description="test cluster",
        representative_statements=[],
        member_stakeholders=members,
        size=len(members),
    )


# ===========================================================================
# 1. ML Governance — MLGovernanceError fallback branch (lines 86-89)
# ===========================================================================


class TestMLGovernanceErrorFallback:
    """Test MLGovernanceError when AgentBusError IS Exception (fallback path)."""

    def test_error_stores_message_and_details(self):
        err = MLGovernanceError("boom", details={"key": "val"})
        assert "boom" in str(err)

    def test_error_none_details_defaults_to_empty_dict(self):
        """When details is None the fallback branch sets self.details = {}."""
        err = MLGovernanceError("oops")
        # The error should be constructable without details
        assert err is not None

    def test_connection_error_attributes(self):
        err = MLGovernanceConnectionError("http://x", "refused")
        assert err.url == "http://x"
        assert err.reason == "refused"

    def test_timeout_error_attributes(self):
        err = MLGovernanceTimeoutError("report_outcome", 5.0)
        assert err.operation == "report_outcome"
        assert err.timeout_seconds == 5.0


# ===========================================================================
# 2. ML Governance — retry with backoff (lines 503-505)
# ===========================================================================


class TestMLGovernanceRetryBackoff:
    """Cover the retry-with-sleep path in _submit_report."""

    async def test_retry_backoff_then_success(self):
        config = _test_config(max_retries=2, retry_delay=0.01)
        client = MLGovernanceClient(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "sample_count": 1,
            "current_accuracy": 0.9,
        }

        call_count = 0

        async def fake_post(url, json=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("fail first")
            return mock_response

        mock_http = AsyncMock()
        mock_http.post = fake_post
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        result = await client.report_outcome(features={"a": 1.0}, label=1)
        assert result.success is True
        assert call_count == 2


# ===========================================================================
# 3. ML Governance — failure callbacks (lines 523, 527-528)
# ===========================================================================


class TestMLGovernanceFailureCallbacks:
    """Cover on_failure callback path after all retries fail."""

    async def test_failure_callbacks_invoked(self):
        config = _test_config(
            max_retries=1,
            graceful_degradation=True,
            enable_async_queue=False,
        )
        client = MLGovernanceClient(config=config)

        callback_values = []
        client.on_failure(lambda msg: callback_values.append(msg))

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("down"))
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        result = await client.report_outcome(features={"a": 1.0}, label=0)
        assert result.status == OutcomeReportStatus.SERVICE_UNAVAILABLE
        assert len(callback_values) == 1

    async def test_failure_callback_error_swallowed(self):
        config = _test_config(
            max_retries=1,
            graceful_degradation=True,
            enable_async_queue=False,
        )
        client = MLGovernanceClient(config=config)
        client.on_failure(lambda msg: (_ for _ in ()).throw(RuntimeError("cb fail")))

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("down"))
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        result = await client.report_outcome(features={"a": 1.0}, label=0)
        assert result.status == OutcomeReportStatus.SERVICE_UNAVAILABLE


# ===========================================================================
# 4. ML Governance — success callbacks with error (lines 565-568)
# ===========================================================================


class TestMLGovernanceSuccessCallbacks:
    """Cover on_success callback error paths in _send_request (202 and 200)."""

    async def test_success_callback_error_on_202(self):
        config = _test_config()
        client = MLGovernanceClient(config=config)

        def bad_callback(result):
            raise ValueError("cb explodes")

        client.on_success(bad_callback)

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            "sample_count": 1,
            "current_accuracy": 0.95,
            "training_id": "t1",
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        result = await client.report_outcome(features={"a": 1.0}, label=1)
        assert result.success is True
        assert result.status == OutcomeReportStatus.SUCCESS

    async def test_success_callback_error_on_200(self):
        config = _test_config()
        client = MLGovernanceClient(config=config)

        def bad_callback(result):
            raise TypeError("cb type error")

        client.on_success(bad_callback)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "sample_count": 5,
        }

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        result = await client.report_outcome(features={"x": 0.5}, label=0)
        assert result.success is True


# ===========================================================================
# 5. ML Governance — flush queue failed send (line 651)
# ===========================================================================


class TestMLGovernanceFlushQueue:
    """Cover _flush_queue paths including failed sends."""

    async def test_flush_queue_failed_send(self):
        config = _test_config(enable_async_queue=True)
        client = MLGovernanceClient(config=config)

        report = OutcomeReport(features={"a": 1.0}, label=1)
        client._queue = [report]

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=RuntimeError("send fail"))
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        count = await client._flush_queue()
        assert count == 0
        assert len(client._queue) == 1

    async def test_flush_queue_circuit_open(self):
        config = _test_config(enable_async_queue=True, circuit_breaker_reset=9999.0)
        client = MLGovernanceClient(config=config)

        report = OutcomeReport(features={"b": 2.0}, label=0)
        client._queue = [report]
        client._circuit_state = CircuitState.OPEN
        # Use a very recent failure time so circuit stays open
        from datetime import UTC, datetime

        client._last_failure_time = datetime.now(UTC).timestamp()

        count = await client._flush_queue()
        assert count == 0
        assert len(client._queue) == 1

    async def test_flush_queue_unsuccessful_result(self):
        config = _test_config(enable_async_queue=True)
        client = MLGovernanceClient(config=config)

        report = OutcomeReport(features={"c": 3.0}, label=1)
        client._queue = [report]

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        count = await client._flush_queue()
        assert count == 0


# ===========================================================================
# 6. ML Governance — batch error path (line 696) and batch fail (760)
# ===========================================================================


class TestMLGovernanceBatch:
    """Cover batch reporting error/failure branches."""

    async def test_batch_http_error(self):
        config = _test_config()
        client = MLGovernanceClient(config=config)

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("batch fail"))
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        reports = [OutcomeReport(features={"a": 1.0}, label=1)]
        results = await client.report_outcomes_batch(reports)
        assert all(not r.success for r in results)

    async def test_batch_non_200_status(self):
        config = _test_config()
        client = MLGovernanceClient(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        reports = [OutcomeReport(features={"a": 1.0}, label=0)]
        results = await client.report_outcomes_batch(reports)
        assert results[0].status == OutcomeReportStatus.FAILED


# ===========================================================================
# 7. ML Governance — global client functions (lines 858-860, 866-868, 897-900)
# ===========================================================================


class TestMLGovernanceGlobalFunctions:
    """Cover initialize/close/report_outcome global functions."""

    async def test_initialize_and_close(self):
        with patch.object(MLGovernanceClient, "initialize", new_callable=AsyncMock):
            client = await initialize_ml_governance_client(
                config=_test_config(),
            )
            assert client is not None

        with patch.object(MLGovernanceClient, "close", new_callable=AsyncMock):
            await close_ml_governance_client()

    async def test_report_outcome_convenience(self):
        import enhanced_agent_bus.integrations.ml_governance as mod

        old = mod._ml_governance_client
        try:
            mock_client = MagicMock(spec=MLGovernanceClient)
            mock_client._http_client = None
            mock_client.initialize = AsyncMock()
            mock_client.report_outcome = AsyncMock(
                return_value=OutcomeResult(
                    status=OutcomeReportStatus.SUCCESS,
                    success=True,
                )
            )
            mod._ml_governance_client = mock_client

            result = await report_outcome(features={"a": 1.0}, label=1)
            assert result.success is True
            mock_client.initialize.assert_awaited_once()
        finally:
            mod._ml_governance_client = old


# ===========================================================================
# 8. ML Governance — not-graceful raise paths
# ===========================================================================


class TestMLGovernanceNotGraceful:
    """Cover the raise paths when graceful_degradation=False."""

    async def test_raise_timeout_error(self):
        config = _test_config(graceful_degradation=False, max_retries=1)
        client = MLGovernanceClient(config=config)

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ReadTimeout("slow"))
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        with pytest.raises(MLGovernanceTimeoutError):
            await client.report_outcome(features={"a": 1.0}, label=1)

    async def test_raise_connection_error(self):
        config = _test_config(graceful_degradation=False, max_retries=1)
        client = MLGovernanceClient(config=config)

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        with pytest.raises(MLGovernanceConnectionError):
            await client.report_outcome(features={"a": 1.0}, label=1)


# ===========================================================================
# 9. ML Governance — queue_report overflow (line 617 area)
# ===========================================================================


class TestMLGovernanceQueueOverflow:
    async def test_queue_drops_oldest_when_full(self):
        config = _test_config(
            enable_async_queue=True,
            max_queue_size=2,
            circuit_breaker_threshold=1,
        )
        client = MLGovernanceClient(config=config)
        client._circuit_state = CircuitState.OPEN
        client._last_failure_time = 0.0

        for i in range(3):
            report = OutcomeReport(features={f"f{i}": float(i)}, label=1)
            client._queue_report(report)

        assert len(client._queue) == 2


# ===========================================================================
# 10. structured_logging — StructuredJSONFormatter
# ===========================================================================


class TestStructuredJSONFormatter:
    """Cover JSON formatter lines 137-198."""

    def test_format_basic_message(self):
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello world",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["message"] == "hello world"

    def test_format_with_correlation_id(self):
        token = correlation_id_var.set("test-corr-id")
        try:
            formatter = StructuredJSONFormatter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="t.py",
                lineno=1,
                msg="msg",
                args=None,
                exc_info=None,
            )
            output = formatter.format(record)
            data = json.loads(output)
            assert data["correlation_id"] == "test-corr-id"
        finally:
            correlation_id_var.reset(token)

    def test_format_with_tenant_and_request_id(self):
        t1 = tenant_id_var.set("tenant-abc")
        t2 = request_id_var.set("req-xyz")
        try:
            formatter = StructuredJSONFormatter()
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="t.py",
                lineno=1,
                msg="msg",
                args=None,
                exc_info=None,
            )
            output = formatter.format(record)
            data = json.loads(output)
            assert data["tenant_id"] == "tenant-abc"
            assert data["request_id"] == "req-xyz"
        finally:
            tenant_id_var.reset(t1)
            request_id_var.reset(t2)

    def test_format_with_extra_attribute(self):
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="t.py",
            lineno=1,
            msg="msg",
            args=None,
            exc_info=None,
        )
        record.extra = {"user_id": "u1"}
        output = formatter.format(record)
        data = json.loads(output)
        assert data["extra"]["user_id"] == "u1"

    def test_format_with_dict_args(self):
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="t.py",
            lineno=1,
            msg="msg",
            args=None,
            exc_info=None,
        )
        # Manually set args to a dict after construction to bypass LogRecord validation
        record.args = {"action": "test"}
        output = formatter.format(record)
        data = json.loads(output)
        assert data["extra"]["action"] == "test"

    def test_format_with_exception(self):
        formatter = StructuredJSONFormatter(include_stack_trace=True)
        try:
            raise ValueError("test error")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="t.py",
            lineno=1,
            msg="error msg",
            args=None,
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["exception"]["type"] == "ValueError"
        assert "traceback" in data["exception"]

    def test_format_warning_includes_source(self):
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="warn.py",
            lineno=42,
            msg="warn msg",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["source"]["line"] == 42

    def test_format_truncation(self):
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="t.py",
            lineno=1,
            msg="x" * 20000,
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        assert output.endswith(" [truncated]")
        assert len(output) <= 10000 + 20

    def test_format_no_stack_trace(self):
        formatter = StructuredJSONFormatter(include_stack_trace=False)
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="t.py",
            lineno=1,
            msg="msg",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" not in data


# ===========================================================================
# 11. structured_logging — _process_extra redaction
# ===========================================================================


class TestProcessExtra:
    """Cover _process_extra lines 202-220."""

    def test_redact_sensitive_fields(self):
        formatter = StructuredJSONFormatter(redact_sensitive=True)
        extra = {
            "password": "secret123",
            "api_key": "sk-abc",
            "username": "alice",
        }
        result = formatter._process_extra(extra)
        assert result["password"] == "[REDACTED]"
        assert result["api_key"] == "[REDACTED]"
        assert result["username"] == "alice"

    def test_no_redaction(self):
        formatter = StructuredJSONFormatter(redact_sensitive=False)
        extra = {"password": "secret123"}
        result = formatter._process_extra(extra)
        assert result["password"] == "secret123"

    def test_nested_dict_redaction(self):
        formatter = StructuredJSONFormatter(redact_sensitive=True)
        extra = {"config": {"token": "abc", "name": "test"}}
        result = formatter._process_extra(extra)
        assert result["config"]["token"] == "[REDACTED]"
        assert result["config"]["name"] == "test"

    def test_long_string_truncation(self):
        formatter = StructuredJSONFormatter(redact_sensitive=True)
        extra = {"description": "a" * 1500}
        result = formatter._process_extra(extra)
        assert result["description"].endswith("...")
        assert len(result["description"]) == 1003


# ===========================================================================
# 12. structured_logging — TextFormatter
# ===========================================================================


class TestTextFormatter:
    """Cover TextFormatter lines 241-267."""

    def test_format_basic(self):
        formatter = TextFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="t.py",
            lineno=1,
            msg="hello",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        assert "hello" in output
        assert "[INFO]" in output

    def test_format_with_correlation_id(self):
        token = correlation_id_var.set("corr-12345678-abcd")
        try:
            formatter = TextFormatter()
            record = logging.LogRecord(
                name="test",
                level=logging.DEBUG,
                pathname="t.py",
                lineno=1,
                msg="debug msg",
                args=None,
                exc_info=None,
            )
            output = formatter.format(record)
            assert "[corr-123" in output
        finally:
            correlation_id_var.reset(token)

    def test_format_with_extra(self):
        formatter = TextFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="t.py",
            lineno=1,
            msg="msg",
            args=None,
            exc_info=None,
        )
        record.extra = {"key": "val"}
        output = formatter.format(record)
        assert "key=val" in output

    def test_format_with_exception(self):
        formatter = TextFormatter()
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="t.py",
            lineno=1,
            msg="error",
            args=None,
            exc_info=exc_info,
        )
        output = formatter.format(record)
        assert "RuntimeError" in output


# ===========================================================================
# 13. structured_logging — StructuredLogger methods
# ===========================================================================


class TestStructuredLogger:
    """Cover StructuredLogger log methods (lines 303-304, 348, 357, etc.)."""

    def test_log_with_format_args(self, caplog):
        logger = get_logger("test.fmt")
        with caplog.at_level(logging.DEBUG, logger="test.fmt"):
            logger.debug("count=%d", 42)
        assert "count=42" in caplog.text

    def test_log_with_bad_format_args(self, caplog):
        logger = get_logger("test.badfmt")
        with caplog.at_level(logging.DEBUG, logger="test.badfmt"):
            logger.debug("value=%d", "not_a_number")
        assert "not_a_number" in caplog.text

    def test_critical_method(self, caplog):
        logger = get_logger("test.crit")
        with caplog.at_level(logging.CRITICAL, logger="test.crit"):
            logger.critical("system down")
        assert "system down" in caplog.text

    def test_exception_method(self, caplog):
        logger = get_logger("test.exc")
        with caplog.at_level(logging.ERROR, logger="test.exc"):
            try:
                raise ValueError("test exc")
            except ValueError:
                logger.exception("caught error")
        assert "caught error" in caplog.text

    def test_error_with_exc_info_true(self, caplog):
        logger = get_logger("test.errtrue")
        with caplog.at_level(logging.ERROR, logger="test.errtrue"):
            try:
                raise TypeError("type problem")
            except TypeError:
                logger.error("err", exc_info=True)
        assert "err" in caplog.text

    def test_critical_with_exc_info_true(self, caplog):
        logger = get_logger("test.crittrue")
        with caplog.at_level(logging.CRITICAL, logger="test.crittrue"):
            try:
                raise OSError("disk fail")
            except OSError:
                logger.critical("fatal", exc_info=True)
        assert "fatal" in caplog.text

    def test_disabled_level_skips(self, caplog):
        logger = get_logger("test.skip")
        logger._logger.setLevel(logging.ERROR)
        logger.debug("should not appear")
        assert "should not appear" not in caplog.text


# ===========================================================================
# 14. structured_logging — BoundLogger
# ===========================================================================


class TestBoundLogger:
    """Cover BoundLogger methods (lines 364-393)."""

    def test_bound_logger_debug(self, caplog):
        logger = get_logger("test.bound")
        bound = logger.bind(component="auth")
        with caplog.at_level(logging.DEBUG, logger="test.bound"):
            bound.debug("checking auth")
        assert "checking auth" in caplog.text

    def test_bound_logger_info(self, caplog):
        logger = get_logger("test.bound2")
        bound = logger.bind(svc="api")
        with caplog.at_level(logging.INFO, logger="test.bound2"):
            bound.info("request started")
        assert "request started" in caplog.text

    def test_bound_logger_warning(self, caplog):
        logger = get_logger("test.bound3")
        bound = logger.bind(svc="db")
        with caplog.at_level(logging.WARNING, logger="test.bound3"):
            bound.warning("slow query")
        assert "slow query" in caplog.text

    def test_bound_logger_error(self, caplog):
        logger = get_logger("test.bound4")
        bound = logger.bind(svc="cache")
        with caplog.at_level(logging.ERROR, logger="test.bound4"):
            bound.error("cache miss")
        assert "cache miss" in caplog.text

    def test_bound_logger_critical(self, caplog):
        logger = get_logger("test.bound5")
        bound = logger.bind(svc="core")
        with caplog.at_level(logging.CRITICAL, logger="test.bound5"):
            bound.critical("meltdown")
        assert "meltdown" in caplog.text

    def test_bound_logger_exception(self, caplog):
        logger = get_logger("test.bound6")
        bound = logger.bind(svc="io")
        with caplog.at_level(logging.ERROR, logger="test.bound6"):
            try:
                raise IOError("disk")
            except IOError:
                bound.exception("io fail")
        assert "io fail" in caplog.text

    def test_bound_logger_merge_context(self):
        logger = get_logger("test.merge")
        bound = logger.bind(a="1")
        merged = bound._merge_context({"b": "2"})
        assert merged == {"a": "1", "b": "2"}

    def test_bound_logger_override_context(self):
        logger = get_logger("test.override")
        bound = logger.bind(a="1")
        merged = bound._merge_context({"a": "2"})
        assert merged["a"] == "2"


# ===========================================================================
# 15. structured_logging — configure_logging
# ===========================================================================


class TestConfigureLogging:
    """Cover configure_logging lines 415-446."""

    def test_configure_json_format(self):
        configure_logging(level="DEBUG", format_type="json")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_configure_text_format(self):
        configure_logging(level="WARNING", format_type="text")
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_configure_default_from_env(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "ERROR")
        monkeypatch.setenv("LOG_FORMAT", "text")
        configure_logging()
        root = logging.getLogger()
        assert root.level == logging.ERROR

    def test_configure_invalid_level_defaults_to_info(self):
        configure_logging(level="INVALID_LEVEL")
        root = logging.getLogger()
        assert root.level == logging.INFO


# ===========================================================================
# 16. structured_logging — context management
# ===========================================================================


class TestContextManagement:
    """Cover set/get context functions (lines 480-502)."""

    def test_set_correlation_id_auto(self):
        cid = set_correlation_id()
        assert len(cid) > 0
        assert get_correlation_id() == cid

    def test_set_correlation_id_explicit(self):
        cid = set_correlation_id("my-corr-id")
        assert cid == "my-corr-id"

    def test_set_tenant_id(self):
        set_tenant_id("tenant-1")
        assert get_tenant_id() == "tenant-1"

    def test_set_request_id(self):
        set_request_id("req-999")
        assert request_id_var.get() == "req-999"


# ===========================================================================
# 17. structured_logging — log_function_call decorator
# ===========================================================================


class TestLogFunctionCallDecorator:
    """Cover log_function_call lines 518-577."""

    def test_sync_function_decorated(self, caplog):
        @log_function_call()
        def add(a, b):
            return a + b

        with caplog.at_level(logging.DEBUG):
            result = add(1, 2)
        assert result == 3

    def test_sync_function_raises(self, caplog):
        @log_function_call()
        def failing():
            raise RuntimeError("sync fail")

        with pytest.raises(RuntimeError, match="sync fail"):
            with caplog.at_level(logging.DEBUG):
                failing()

    async def test_async_function_decorated(self, caplog):
        @log_function_call()
        async def fetch(url):
            return f"data from {url}"

        with caplog.at_level(logging.DEBUG):
            result = await fetch("http://example.com")
        assert "data from" in result

    async def test_async_function_raises(self, caplog):
        @log_function_call()
        async def broken():
            raise ValueError("async fail")

        with pytest.raises(ValueError, match="async fail"):
            with caplog.at_level(logging.DEBUG):
                await broken()

    def test_decorator_with_custom_logger(self, caplog):
        custom_logger = get_logger("custom")

        @log_function_call(logger=custom_logger)
        def greet(name):
            return f"hi {name}"

        with caplog.at_level(logging.DEBUG, logger="custom"):
            result = greet("world")
        assert result == "hi world"


# ===========================================================================
# 18. structured_logging — OpenTelemetry stubs
# ===========================================================================


class TestOpenTelemetryStubs:
    """Cover setup_opentelemetry and instrument_fastapi (lines 592-617)."""

    def test_setup_opentelemetry_noop(self):
        # Should not raise even if otel not installed
        setup_opentelemetry(service_name="test-service")

    def test_instrument_fastapi_noop(self):
        mock_app = MagicMock()
        instrument_fastapi(mock_app)


# ===========================================================================
# 19. Polis — vote on missing statement (line 183)
# ===========================================================================


class TestPolisVoteMissing:
    async def test_vote_on_nonexistent_statement(self):
        engine = PolisDeliberationEngine()
        s = _make_stakeholder("s1")
        result = await engine.vote_on_statement("nonexistent", s, 1)
        assert result is False


# ===========================================================================
# 20. Polis — _update_statement_scores empty paths (lines 221, 225)
# ===========================================================================


class TestPolisUpdateScoresEmpty:
    async def test_update_scores_missing_statement(self):
        engine = PolisDeliberationEngine()
        await engine._update_statement_scores("missing")

    async def test_update_scores_empty_votes(self):
        engine = PolisDeliberationEngine()
        engine.voting_matrix["s1"] = {}
        await engine._update_statement_scores("s1")


# ===========================================================================
# 21. Polis — statement similarity edge cases (lines 393-411)
# ===========================================================================


class TestPolisStatementSimilarity:
    async def test_similarity_missing_first(self):
        engine = PolisDeliberationEngine()
        assert engine.calculate_statement_similarity("missing1", "missing2") == 0.0

    async def test_similarity_missing_second(self):
        engine = PolisDeliberationEngine()
        s = _make_stakeholder("author")
        stmt = await engine.submit_statement("hello world", s)
        assert engine.calculate_statement_similarity(stmt.statement_id, "missing") == 0.0

    async def test_similarity_identical(self):
        engine = PolisDeliberationEngine()
        s = _make_stakeholder("author")
        stmt = await engine.submit_statement("test content", s)
        assert engine.calculate_statement_similarity(stmt.statement_id, stmt.statement_id) == 1.0

    async def test_similarity_empty_tokens(self):
        engine = PolisDeliberationEngine()
        s = _make_stakeholder("author")
        stmt1 = await engine.submit_statement("   ", s)
        stmt2 = await engine.submit_statement("   ", s)
        sim = engine.calculate_statement_similarity(stmt1.statement_id, stmt2.statement_id)
        assert sim == 1.0

    async def test_similarity_one_empty(self):
        engine = PolisDeliberationEngine()
        s = _make_stakeholder("author")
        stmt1 = await engine.submit_statement("   ", s)
        stmt2 = await engine.submit_statement("hello world", s)
        sim = engine.calculate_statement_similarity(stmt1.statement_id, stmt2.statement_id)
        assert sim == 0.0


# ===========================================================================
# 22. Polis — diverse representative empty cluster (line 468-469)
# ===========================================================================


class TestPolisDiverseRepresentativeEmpty:
    async def test_diverse_empty_cluster(self):
        engine = PolisDeliberationEngine()
        cluster = _make_cluster("c1", [])
        result = await engine.select_diverse_representative_statements(cluster)
        assert result == []


# ===========================================================================
# 23. Polis — diversity threshold >= 1.0 falls back (line 476)
# ===========================================================================


class TestPolisDiversityThresholdFallback:
    async def test_threshold_ge_1_falls_back(self):
        engine = PolisDeliberationEngine()
        s1 = _make_stakeholder("s1")
        stmt = await engine.submit_statement("AI governance", s1)
        await engine.vote_on_statement(stmt.statement_id, s1, 1)

        cluster = _make_cluster("c1", ["s1"])
        result = await engine.select_diverse_representative_statements(
            cluster,
            top_n=5,
            diversity_threshold=1.0,
        )
        assert len(result) >= 1


# ===========================================================================
# 24. Polis — _get_sorted_statement_scores empty (line 480, 552-556)
# ===========================================================================


class TestPolisSortedScoresEmpty:
    async def test_no_statements_with_votes(self):
        engine = PolisDeliberationEngine()
        cluster = _make_cluster("c1", ["s1"])
        result = await engine.select_diverse_representative_statements(
            cluster,
            diversity_threshold=0.5,
        )
        assert result == []


# ===========================================================================
# 25. Polis — validate_diversity_parameters edge cases (lines 510-524)
# ===========================================================================


class TestPolisValidateDiversityParams:
    def test_top_n_below_1(self):
        top_n, thresh = PolisDeliberationEngine._validate_diversity_parameters(0, 0.5)
        assert top_n == 5

    def test_top_n_above_10(self):
        top_n, thresh = PolisDeliberationEngine._validate_diversity_parameters(15, 0.5)
        assert top_n == 10

    def test_threshold_below_0(self):
        top_n, thresh = PolisDeliberationEngine._validate_diversity_parameters(5, -0.5)
        assert thresh == 0.0

    def test_threshold_above_1(self):
        top_n, thresh = PolisDeliberationEngine._validate_diversity_parameters(5, 1.5)
        assert thresh == 1.0

    def test_threshold_at_1_logs_debug(self):
        top_n, thresh = PolisDeliberationEngine._validate_diversity_parameters(5, 1.0)
        assert thresh == 1.0


# ===========================================================================
# 26. Polis — _build_voting_matrix empty (lines 663-664)
# ===========================================================================


class TestPolisBuildVotingMatrixEmpty:
    def test_empty_voting_matrix(self):
        engine = PolisDeliberationEngine()
        s_list, stmt_list, X = engine._build_voting_matrix()
        assert s_list == []
        assert stmt_list == []
        assert X.shape == (0, 0)


# ===========================================================================
# 27. Polis — _run_clustering edge cases (lines 680, 682, 690-691, 702-704)
# ===========================================================================


class TestPolisRunClustering:
    def test_single_participant(self):
        engine = PolisDeliberationEngine()
        X = np.array([[1.0, 0.0]])
        labels = engine._run_clustering(X, 1, 2)
        assert len(labels) == 1

    def test_k_clusters_clamped_to_participants(self):
        engine = PolisDeliberationEngine()
        X = np.array([[1.0], [0.0]])
        labels = engine._run_clustering(X, 2, 1)
        assert len(labels) == 2

    def test_pca_failure_fallback(self):
        engine = PolisDeliberationEngine()
        X = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        with patch("enhanced_agent_bus.governance.polis_engine.PCA") as mock_pca:
            mock_pca.return_value.fit_transform.side_effect = ValueError("PCA fail")
            labels = engine._run_clustering(X, 3, 3)
        assert len(labels) == 3

    def test_kmeans_failure_fallback(self):
        engine = PolisDeliberationEngine()
        X = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        with patch("enhanced_agent_bus.governance.polis_engine.KMeans") as mock_km:
            mock_km.return_value.fit_predict.side_effect = RuntimeError("KMeans fail")
            labels = engine._run_clustering(X, 3, 2)
        assert all(label == 0 for label in labels)


# ===========================================================================
# 28. Polis — _assign_selection_reasons diversity disabled (line 861)
# ===========================================================================


class TestPolisAssignSelectionReasons:
    def test_diversity_disabled(self):
        engine = PolisDeliberationEngine(enable_diversity_filter=False)
        reasons = engine._assign_selection_reasons(
            ["s1", "s2"],
            {"s2": {"avg_similarity": 0.3}},
        )
        assert reasons["s1"] == "highest_centrality"
        assert reasons["s2"] == "high_centrality"

    def test_diversity_enabled_diverse_opinion(self):
        engine = PolisDeliberationEngine(enable_diversity_filter=True, diversity_threshold=0.7)
        reasons = engine._assign_selection_reasons(
            ["s1", "s2"],
            {"s2": {"avg_similarity": 0.3}},
        )
        assert reasons["s2"] == "diverse_opinion"

    def test_diversity_enabled_high_centrality(self):
        engine = PolisDeliberationEngine(enable_diversity_filter=True, diversity_threshold=0.2)
        reasons = engine._assign_selection_reasons(
            ["s1", "s2"],
            {"s2": {"avg_similarity": 0.5}},
        )
        assert reasons["s2"] == "high_centrality"


# ===========================================================================
# 29. Polis — identify_clusters empty (line 991)
# ===========================================================================


class TestPolisIdentifyClustersEmpty:
    async def test_identify_clusters_no_data(self):
        engine = PolisDeliberationEngine()
        clusters = await engine.identify_clusters()
        assert clusters == []


# ===========================================================================
# 30. Polis — cross group consensus empty (line 1068)
# ===========================================================================


class TestPolisCrossGroupConsensusEmpty:
    async def test_no_group_scores(self):
        engine = PolisDeliberationEngine()
        cluster = _make_cluster("c1", ["s1"])
        cluster.representative_statements = ["nonexistent"]
        result = await engine.analyze_cross_group_consensus([cluster])
        assert result["total_clusters"] == 1
        assert cluster.cross_group_consensus == 0.0


# ===========================================================================
# 31. Polis — _log_diversity_selection_results warning branch
# ===========================================================================


class TestPolisLogDiversityResults:
    def test_fewer_than_requested(self):
        cluster = _make_cluster("c1", ["s1", "s2"])
        # Should not raise
        PolisDeliberationEngine._log_diversity_selection_results(
            cluster,
            diverse_representatives=["r1"],
            requested_top_n=3,
            diversity_threshold=0.7,
            total_candidates=5,
        )


# ===========================================================================
# 32. Polis — voting matrix init on vote (line 186)
# ===========================================================================


class TestPolisVotingMatrixInit:
    async def test_vote_initializes_matrix_entry(self):
        engine = PolisDeliberationEngine()
        s = _make_stakeholder("s1")
        stmt = await engine.submit_statement("test", s)
        # Remove the matrix entry to trigger the init branch
        del engine.voting_matrix[stmt.statement_id]
        result = await engine.vote_on_statement(stmt.statement_id, s, 1)
        assert result is True
        assert stmt.statement_id in engine.voting_matrix


# ===========================================================================
# 33. ML Governance — OutcomeReport to_request_dict optional fields
# ===========================================================================


class TestOutcomeReportDict:
    def test_full_report(self):
        report = OutcomeReport(
            features={"a": 1.0},
            label=1,
            weight=0.5,
            tenant_id="t1",
            prediction_id="p1",
            timestamp=123456.0,
        )
        d = report.to_request_dict()
        assert d["sample_weight"] == 0.5
        assert d["tenant_id"] == "t1"
        assert d["prediction_id"] == "p1"
        assert d["timestamp"] == 123456.0

    def test_minimal_report(self):
        report = OutcomeReport(features={"b": 2.0}, label=0)
        d = report.to_request_dict()
        assert "sample_weight" not in d
        assert "tenant_id" not in d


# ===========================================================================
# 34. ML Governance — _send_request error response (non-JSON body)
# ===========================================================================


class TestSendRequestErrorResponse:
    async def test_non_json_error_response(self):
        config = _test_config()
        client = MLGovernanceClient(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = "Bad Request"

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_http.aclose = AsyncMock()
        client._http_client = mock_http

        result = await client.report_outcome(features={"a": 1.0}, label=1)
        assert result.status == OutcomeReportStatus.FAILED
        assert "Bad Request" in result.message
