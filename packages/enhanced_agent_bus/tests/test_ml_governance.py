"""
Tests for ML Governance Client.

Constitutional Hash: 608508a9bd224290

Covers: enums, exceptions, config, data types, client (circuit breaker,
outcome reporting, batch, health, callbacks, queue), and module-level helpers.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from enhanced_agent_bus.circuit_breaker.enums import CircuitState
from enhanced_agent_bus.integrations.ml_governance import (
    MLGovernanceClient,
    MLGovernanceConfig,
    MLGovernanceConnectionError,
    MLGovernanceError,
    MLGovernanceTimeoutError,
    OutcomeReport,
    OutcomeReportStatus,
    OutcomeResult,
    get_ml_governance_client,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> MLGovernanceConfig:
    """Create a test config with sensible defaults."""
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


def _make_response(
    status_code: int = 200, json_data: dict | None = None, text: str = ""
) -> MagicMock:
    """Build a fake httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data or {}
    return resp


# ==========================================================================
# Enum tests
# ==========================================================================


class TestOutcomeReportStatus:
    def test_values(self):
        assert OutcomeReportStatus.SUCCESS.value == "success"
        assert OutcomeReportStatus.QUEUED.value == "queued"
        assert OutcomeReportStatus.FAILED.value == "failed"
        assert OutcomeReportStatus.CIRCUIT_OPEN.value == "circuit_open"
        assert OutcomeReportStatus.TIMEOUT.value == "timeout"
        assert OutcomeReportStatus.SERVICE_UNAVAILABLE.value == "service_unavailable"

    def test_is_string_enum(self):
        assert isinstance(OutcomeReportStatus.SUCCESS, str)


# ==========================================================================
# Exception tests
# ==========================================================================


class TestExceptions:
    def test_ml_governance_error(self):
        err = MLGovernanceError("boom")
        assert "boom" in str(err)

    def test_connection_error_attributes(self):
        err = MLGovernanceConnectionError("http://host", "refused")
        assert err.url == "http://host"
        assert err.reason == "refused"
        assert "refused" in str(err)

    def test_timeout_error_attributes(self):
        err = MLGovernanceTimeoutError("report_outcome", 5.0)
        assert err.operation == "report_outcome"
        assert err.timeout_seconds == 5.0
        assert "5.0" in str(err)


# ==========================================================================
# Config tests
# ==========================================================================


class TestMLGovernanceConfig:
    def test_defaults(self):
        cfg = MLGovernanceConfig()
        assert cfg.timeout == 5.0
        assert cfg.max_retries == 3
        assert cfg.enable_async_queue is True

    def test_for_testing(self):
        cfg = MLGovernanceConfig.for_testing()
        assert cfg.base_url == "http://localhost:8001"
        assert cfg.timeout == 1.0
        assert cfg.max_retries == 1
        assert cfg.enable_async_queue is False

    def test_to_dict(self):
        cfg = MLGovernanceConfig.for_testing()
        d = cfg.to_dict()
        assert d["base_url"] == "http://localhost:8001"
        assert "timeout" in d
        assert "constitutional_hash" not in d  # not exposed

    def test_from_environment_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            cfg = MLGovernanceConfig.from_environment()
        assert cfg.timeout == 5.0
        assert cfg.max_retries == 3

    def test_from_environment_custom(self):
        env = {
            "ADAPTIVE_LEARNING_URL": "http://custom:9000",
            "ML_GOVERNANCE_TIMEOUT": "10.0",
            "ML_GOVERNANCE_MAX_RETRIES": "5",
            "ML_GOVERNANCE_RETRY_DELAY": "1.0",
            "ML_GOVERNANCE_CIRCUIT_THRESHOLD": "10",
            "ML_GOVERNANCE_CIRCUIT_RESET": "60.0",
            "ML_GOVERNANCE_ENABLE_QUEUE": "false",
            "ML_GOVERNANCE_MAX_QUEUE_SIZE": "500",
            "ML_GOVERNANCE_GRACEFUL_DEGRADATION": "false",
        }
        with patch.dict("os.environ", env, clear=True):
            cfg = MLGovernanceConfig.from_environment()
        assert cfg.base_url == "http://custom:9000"
        assert cfg.timeout == 10.0
        assert cfg.max_retries == 5
        assert cfg.enable_async_queue is False
        assert cfg.graceful_degradation is False

    def test_from_environment_invalid_values_use_defaults(self):
        env = {
            "ML_GOVERNANCE_TIMEOUT": "not_a_number",
            "ML_GOVERNANCE_MAX_RETRIES": "nope",
        }
        with patch.dict("os.environ", env, clear=True):
            cfg = MLGovernanceConfig.from_environment()
        assert cfg.timeout == 5.0
        assert cfg.max_retries == 3


# ==========================================================================
# Data type tests
# ==========================================================================


class TestOutcomeReport:
    def test_to_request_dict_minimal(self):
        report = OutcomeReport(features={"a": 1.0}, label=1)
        d = report.to_request_dict()
        assert d == {"features": {"a": 1.0}, "label": 1}

    def test_to_request_dict_full(self):
        report = OutcomeReport(
            features={"a": 1.0},
            label=0,
            weight=0.5,
            tenant_id="t1",
            prediction_id="p1",
            timestamp=123.0,
        )
        d = report.to_request_dict()
        assert d["sample_weight"] == 0.5
        assert d["tenant_id"] == "t1"
        assert d["prediction_id"] == "p1"
        assert d["timestamp"] == 123.0


class TestOutcomeResult:
    def test_to_dict(self):
        result = OutcomeResult(
            status=OutcomeReportStatus.SUCCESS,
            success=True,
            sample_count=10,
            current_accuracy=0.95,
            message="ok",
            training_id="t-1",
        )
        d = result.to_dict()
        assert d["status"] == "success"
        assert d["success"] is True
        assert d["sample_count"] == 10
        assert d["training_id"] == "t-1"
        assert "timestamp" in d


# ==========================================================================
# Client — construction and lifecycle
# ==========================================================================


class TestClientInit:
    def test_default_config(self):
        client = MLGovernanceClient(config=_make_config())
        assert client.config.base_url == "http://localhost:8001"

    def test_base_url_override(self):
        client = MLGovernanceClient(config=_make_config(), base_url="http://other:9000/")
        assert client.config.base_url == "http://other:9000"

    def test_trailing_slash_stripped(self):
        client = MLGovernanceClient(config=_make_config(base_url="http://host:1/"))
        assert not client.config.base_url.endswith("/")

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with MLGovernanceClient(config=_make_config()) as client:
            assert client._http_client is not None
        assert client._http_client is None

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        client = MLGovernanceClient(config=_make_config())
        await client.initialize()
        first = client._http_client
        await client.initialize()
        assert client._http_client is first
        await client.close()


# ==========================================================================
# Client — circuit breaker
# ==========================================================================


class TestCircuitBreaker:
    def test_starts_closed(self):
        client = MLGovernanceClient(config=_make_config())
        assert client._circuit_state == CircuitState.CLOSED
        assert client._check_circuit() is True

    def test_opens_after_threshold(self):
        client = MLGovernanceClient(config=_make_config(circuit_breaker_threshold=2))
        client._record_failure()
        assert client._circuit_state == CircuitState.CLOSED
        client._record_failure()
        assert client._circuit_state == CircuitState.OPEN
        assert client._check_circuit() is False

    def test_half_open_after_reset_time(self):
        client = MLGovernanceClient(
            config=_make_config(circuit_breaker_threshold=1, circuit_breaker_reset=0.0)
        )
        client._record_failure()
        assert client._circuit_state == CircuitState.OPEN
        # Reset time is 0 so it should immediately transition
        assert client._check_circuit() is True
        assert client._circuit_state == CircuitState.HALF_OPEN

    def test_success_closes_half_open(self):
        client = MLGovernanceClient(config=_make_config(circuit_breaker_threshold=1))
        client._circuit_state = CircuitState.HALF_OPEN
        client._record_success()
        assert client._circuit_state == CircuitState.CLOSED
        assert client._failure_count == 0

    def test_circuit_open_callback_invoked(self):
        callback = MagicMock()
        client = MLGovernanceClient(config=_make_config(circuit_breaker_threshold=1))
        client.on_circuit_open(callback)
        client._record_failure()
        callback.assert_called_once()

    def test_circuit_open_callback_error_handled(self):
        callback = MagicMock(side_effect=RuntimeError("cb error"))
        client = MLGovernanceClient(config=_make_config(circuit_breaker_threshold=1))
        client.on_circuit_open(callback)
        # Should not raise
        client._record_failure()
        assert client._circuit_state == CircuitState.OPEN


# ==========================================================================
# Client — report_outcome (single)
# ==========================================================================


class TestReportOutcome:
    @pytest.mark.asyncio
    async def test_success_200(self):
        client = MLGovernanceClient(config=_make_config())
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(
            return_value=_make_response(
                200, {"success": True, "sample_count": 5, "current_accuracy": 0.9, "message": "ok"}
            )
        )
        client._http_client = mock_http

        result = await client.report_outcome(features={"a": 1.0}, label=1)

        assert result.success is True
        assert result.status == OutcomeReportStatus.SUCCESS
        assert result.sample_count == 5

    @pytest.mark.asyncio
    async def test_success_202(self):
        client = MLGovernanceClient(config=_make_config())
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(
            return_value=_make_response(202, {"sample_count": 3, "training_id": "t-42"})
        )
        client._http_client = mock_http

        result = await client.report_outcome(features={"a": 1.0}, label=0)

        assert result.success is True
        assert result.training_id == "t-42"

    @pytest.mark.asyncio
    async def test_success_callback_invoked(self):
        callback = MagicMock()
        client = MLGovernanceClient(config=_make_config())
        client.on_success(callback)
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(return_value=_make_response(200, {"success": True}))
        client._http_client = mock_http

        await client.report_outcome(features={"a": 1.0}, label=1)

        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_503_returns_service_unavailable(self):
        client = MLGovernanceClient(config=_make_config())
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(return_value=_make_response(503))
        client._http_client = mock_http

        result = await client.report_outcome(features={"a": 1.0}, label=1)

        assert result.status == OutcomeReportStatus.SERVICE_UNAVAILABLE
        assert result.success is False

    @pytest.mark.asyncio
    async def test_400_returns_failed(self):
        client = MLGovernanceClient(config=_make_config())
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(return_value=_make_response(400, {"detail": "bad request"}))
        client._http_client = mock_http

        result = await client.report_outcome(features={"a": 1.0}, label=1)

        assert result.status == OutcomeReportStatus.FAILED
        assert "bad request" in result.message

    @pytest.mark.asyncio
    async def test_error_response_with_no_json(self):
        client = MLGovernanceClient(config=_make_config())
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        resp = _make_response(500, text="Internal Server Error")
        resp.json.side_effect = ValueError("no json")
        mock_http.post = AsyncMock(return_value=resp)
        client._http_client = mock_http

        result = await client.report_outcome(features={"a": 1.0}, label=1)

        assert result.status == OutcomeReportStatus.FAILED
        assert result.success is False

    @pytest.mark.asyncio
    async def test_circuit_open_returns_immediately(self):
        client = MLGovernanceClient(config=_make_config(enable_async_queue=False))
        client._circuit_state = CircuitState.OPEN
        client._last_failure_time = 9999999999.0  # far in future

        result = await client.report_outcome(features={"a": 1.0}, label=1)

        assert result.status == OutcomeReportStatus.CIRCUIT_OPEN

    @pytest.mark.asyncio
    async def test_circuit_open_queues_when_enabled(self):
        client = MLGovernanceClient(config=_make_config(enable_async_queue=True))
        client._circuit_state = CircuitState.OPEN
        client._last_failure_time = 9999999999.0

        result = await client.report_outcome(features={"a": 1.0}, label=1)

        assert result.status == OutcomeReportStatus.QUEUED
        assert len(client._queue) == 1

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.integrations.ml_governance.MLGovernanceClient._sanitize_error",
        return_value="sanitized",
    )
    async def test_timeout_graceful_degradation(self, _mock_sanitize):
        client = MLGovernanceClient(
            config=_make_config(graceful_degradation=True, enable_async_queue=False)
        )
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        client._http_client = mock_http

        result = await client.report_outcome(features={"a": 1.0}, label=1)

        assert result.status == OutcomeReportStatus.SERVICE_UNAVAILABLE
        assert result.success is False

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.integrations.ml_governance.MLGovernanceClient._sanitize_error",
        return_value="sanitized",
    )
    async def test_timeout_raises_when_not_graceful(self, _mock_sanitize):
        client = MLGovernanceClient(config=_make_config(graceful_degradation=False))
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        client._http_client = mock_http

        with pytest.raises(MLGovernanceTimeoutError):
            await client.report_outcome(features={"a": 1.0}, label=1)

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.integrations.ml_governance.MLGovernanceClient._sanitize_error",
        return_value="sanitized",
    )
    async def test_connect_error_raises_when_not_graceful(self, _mock_sanitize):
        client = MLGovernanceClient(config=_make_config(graceful_degradation=False))
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        client._http_client = mock_http

        with pytest.raises(MLGovernanceConnectionError):
            await client.report_outcome(features={"a": 1.0}, label=1)

    @pytest.mark.asyncio
    @patch(
        "enhanced_agent_bus.integrations.ml_governance.MLGovernanceClient._sanitize_error",
        return_value="sanitized",
    )
    async def test_failure_callback_invoked_on_degradation(self, _mock_sanitize):
        callback = MagicMock()
        client = MLGovernanceClient(
            config=_make_config(graceful_degradation=True, enable_async_queue=False)
        )
        client.on_failure(callback)
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        client._http_client = mock_http

        await client.report_outcome(features={"a": 1.0}, label=1)

        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_unexpected_error_breaks_retry_loop(self):
        """ValueError should break immediately instead of retrying."""
        client = MLGovernanceClient(
            config=_make_config(max_retries=3, graceful_degradation=True, enable_async_queue=False)
        )
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(side_effect=ValueError("bad"))
        client._http_client = mock_http

        with patch.object(client, "_sanitize_error", return_value="sanitized"):
            result = await client.report_outcome(features={"a": 1.0}, label=1)

        assert result.status == OutcomeReportStatus.SERVICE_UNAVAILABLE
        # Should have been called only once (no retries for ValueError)
        assert mock_http.post.call_count == 1

    @pytest.mark.asyncio
    async def test_auto_initializes_when_no_client(self):
        client = MLGovernanceClient(config=_make_config())
        assert client._http_client is None

        with patch.object(client, "_send_request", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = OutcomeResult(status=OutcomeReportStatus.SUCCESS, success=True)
            result = await client.report_outcome(features={"a": 1.0}, label=1)

        assert result.success is True
        # Client should have been initialized
        assert client._http_client is not None
        await client.close()


# ==========================================================================
# Client — queue
# ==========================================================================


class TestQueue:
    def test_queue_report(self):
        client = MLGovernanceClient(config=_make_config(max_queue_size=3))
        report = OutcomeReport(features={"a": 1.0}, label=1)
        result = client._queue_report(report)
        assert result.status == OutcomeReportStatus.QUEUED
        assert len(client._queue) == 1

    def test_queue_drops_oldest_when_full(self):
        client = MLGovernanceClient(config=_make_config(max_queue_size=2))
        r1 = OutcomeReport(features={"a": 1.0}, label=0)
        r2 = OutcomeReport(features={"b": 2.0}, label=1)
        r3 = OutcomeReport(features={"c": 3.0}, label=1)
        client._queue_report(r1)
        client._queue_report(r2)
        client._queue_report(r3)
        assert len(client._queue) == 2
        # First report should have been dropped
        assert client._queue[0].features == {"b": 2.0}

    @pytest.mark.asyncio
    async def test_flush_queue_empty(self):
        client = MLGovernanceClient(config=_make_config())
        count = await client._flush_queue()
        assert count == 0

    @pytest.mark.asyncio
    async def test_flush_queue_success(self):
        client = MLGovernanceClient(config=_make_config())
        client._queue = [OutcomeReport(features={"a": 1.0}, label=1)]
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(return_value=_make_response(200, {"success": True}))
        client._http_client = mock_http

        count = await client._flush_queue()

        assert count == 1
        assert len(client._queue) == 0

    @pytest.mark.asyncio
    async def test_flush_queue_failure_keeps_in_queue(self):
        client = MLGovernanceClient(config=_make_config())
        client._queue = [OutcomeReport(features={"a": 1.0}, label=1)]
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(side_effect=OSError("network"))
        client._http_client = mock_http

        count = await client._flush_queue()

        assert count == 0
        assert len(client._queue) == 1

    @pytest.mark.asyncio
    async def test_close_flushes_queue(self):
        client = MLGovernanceClient(config=_make_config())
        await client.initialize()
        client._queue = [OutcomeReport(features={"a": 1.0}, label=1)]

        with patch.object(client, "_flush_queue", new_callable=AsyncMock) as mock_flush:
            mock_flush.return_value = 1
            await client.close()

        mock_flush.assert_called_once()


# ==========================================================================
# Client — batch reporting
# ==========================================================================


class TestBatchReporting:
    @pytest.mark.asyncio
    async def test_batch_success(self):
        client = MLGovernanceClient(config=_make_config())
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(
            return_value=_make_response(
                200, {"sample_count": 2, "accepted": 2, "current_accuracy": 0.88}
            )
        )
        client._http_client = mock_http

        reports = [
            OutcomeReport(features={"a": 1.0}, label=1),
            OutcomeReport(features={"b": 2.0}, label=0),
        ]
        results = await client.report_outcomes_batch(reports)

        assert len(results) == 2
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_batch_circuit_open(self):
        client = MLGovernanceClient(config=_make_config())
        client._circuit_state = CircuitState.OPEN
        client._last_failure_time = 9999999999.0

        reports = [OutcomeReport(features={"a": 1.0}, label=1)]
        results = await client.report_outcomes_batch(reports)

        assert len(results) == 1
        assert results[0].status == OutcomeReportStatus.CIRCUIT_OPEN

    @pytest.mark.asyncio
    async def test_batch_http_error(self):
        client = MLGovernanceClient(config=_make_config())
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("down"))
        client._http_client = mock_http

        reports = [OutcomeReport(features={"a": 1.0}, label=1)]
        results = await client.report_outcomes_batch(reports)

        assert len(results) == 1
        assert results[0].status == OutcomeReportStatus.FAILED

    @pytest.mark.asyncio
    async def test_batch_server_error(self):
        client = MLGovernanceClient(config=_make_config())
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(return_value=_make_response(500))
        client._http_client = mock_http

        reports = [OutcomeReport(features={"a": 1.0}, label=1)]
        results = await client.report_outcomes_batch(reports)

        assert results[0].status == OutcomeReportStatus.FAILED


# ==========================================================================
# Client — health check and stats
# ==========================================================================


class TestHealthAndStats:
    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        client = MLGovernanceClient(config=_make_config())
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(
            return_value=_make_response(200, {"service": "ale", "model_status": "ready"})
        )
        client._http_client = mock_http

        health = await client.health_check()

        assert health["status"] == "healthy"
        assert health["service"] == "ale"
        assert health["circuit_state"] == "closed"

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_status(self):
        client = MLGovernanceClient(config=_make_config())
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(return_value=_make_response(503))
        client._http_client = mock_http

        health = await client.health_check()

        assert health["status"] == "unhealthy"
        assert "503" in health["reason"]

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self):
        client = MLGovernanceClient(config=_make_config())
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        client._http_client = mock_http

        health = await client.health_check()

        assert health["status"] == "unhealthy"

    def test_get_stats(self):
        client = MLGovernanceClient(config=_make_config())
        stats = client.get_stats()
        assert stats["circuit_state"] == "closed"
        assert stats["failure_count"] == 0
        assert stats["queue_size"] == 0
        assert stats["initialized"] is False


# ==========================================================================
# Client — callbacks
# ==========================================================================


class TestCallbacks:
    def test_register_success_callback(self):
        client = MLGovernanceClient(config=_make_config())
        cb = MagicMock()
        client.on_success(cb)
        assert cb in client._on_success_callbacks

    def test_register_failure_callback(self):
        client = MLGovernanceClient(config=_make_config())
        cb = MagicMock()
        client.on_failure(cb)
        assert cb in client._on_failure_callbacks

    def test_register_circuit_open_callback(self):
        client = MLGovernanceClient(config=_make_config())
        cb = MagicMock()
        client.on_circuit_open(cb)
        assert cb in client._on_circuit_open_callbacks

    @pytest.mark.asyncio
    async def test_success_callback_error_handled(self):
        """Callback error should not break the request."""
        client = MLGovernanceClient(config=_make_config())
        cb = MagicMock(side_effect=RuntimeError("cb boom"))
        client.on_success(cb)
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.post = AsyncMock(return_value=_make_response(200, {"success": True}))
        client._http_client = mock_http

        result = await client.report_outcome(features={"a": 1.0}, label=1)

        assert result.success is True
        cb.assert_called_once()


# ==========================================================================
# Module-level helpers
# ==========================================================================


class TestModuleLevelHelpers:
    def test_get_ml_governance_client_returns_instance(self):
        # The module-level _ml_governance_client is defined at function scope
        # (indentation bug in source), so we set it via the module directly.
        import enhanced_agent_bus.integrations.ml_governance as mod

        original = getattr(mod, "_ml_governance_client", None)
        try:
            mod._ml_governance_client = None
            client = get_ml_governance_client()
            assert isinstance(client, MLGovernanceClient)
        finally:
            mod._ml_governance_client = original
