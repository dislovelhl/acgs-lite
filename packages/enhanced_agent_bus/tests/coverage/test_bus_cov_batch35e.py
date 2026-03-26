"""
Coverage tests for:
- enhanced_agent_bus.guardrails.siem_providers (splunk/ES providers, retry, health)
- enhanced_agent_bus.memory_profiler (profiler, queue, decorator, snapshots)
- enhanced_agent_bus.api.app (helpers, lifespan, factory, DSN normalize)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import tracemalloc
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from src.core.shared.errors.exceptions import (
    ServiceUnavailableError,
)
from src.core.shared.errors.exceptions import (
    ValidationError as ACGSValidationError,
)

# ---------------------------------------------------------------------------
# api.app imports (helpers only - avoid triggering full app creation)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.api.app import (
    _is_development_like_environment,
    _normalize_workflow_dsn,
)

# ---------------------------------------------------------------------------
# siem_providers imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.guardrails.siem_providers import (
    ElasticsearchProvider,
    SIEMProvider,
    SIEMProviderConfig,
    SIEMProviderType,
    SplunkHECProvider,
    create_siem_provider,
)

# ---------------------------------------------------------------------------
# memory_profiler imports
# ---------------------------------------------------------------------------
from enhanced_agent_bus.memory_profiler import (
    AsyncMemoryQueue,
    MemoryDelta,
    MemoryProfiler,
    MemoryProfilingConfig,
    MemoryProfilingContext,
    MemorySnapshot,
    ProfilingLevel,
    get_memory_profiler,
    get_memory_queue,
    profile_memory,
)

# ===================================================================
# Helpers
# ===================================================================


def _splunk_config(**overrides) -> SIEMProviderConfig:
    defaults = {
        "provider_type": SIEMProviderType.SPLUNK,
        "endpoint_url": "https://splunk.example.com:8088/services/collector",
        "auth_token": "test-hec-token",
        "index": "acgs2_audit",
        "max_retries": 2,
        "timeout_seconds": 5.0,
    }
    defaults.update(overrides)
    return SIEMProviderConfig(**defaults)


def _es_config(**overrides) -> SIEMProviderConfig:
    defaults = {
        "provider_type": SIEMProviderType.ELASTICSEARCH,
        "endpoint_url": "https://es.example.com:9200",
        "auth_token": "test-api-key",
        "index": "acgs2_audit",
        "max_retries": 2,
        "timeout_seconds": 5.0,
    }
    defaults.update(overrides)
    return SIEMProviderConfig(**defaults)


def _mock_response(status_code: int = 200, json_data: dict | None = None, text: str = ""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


# ===================================================================
# SIEM Providers Tests
# ===================================================================


class TestSIEMProviderConfig:
    def test_defaults(self):
        cfg = SIEMProviderConfig(
            provider_type=SIEMProviderType.SPLUNK,
            endpoint_url="https://x",
            auth_token="tok",
        )
        assert cfg.index == "acgs2_audit"
        assert cfg.verify_ssl is True
        assert cfg.timeout_seconds == 30.0
        assert cfg.max_retries == 3
        assert cfg.enabled is True


class TestSIEMProviderType:
    def test_enum_values(self):
        assert SIEMProviderType.SPLUNK.value == "splunk"
        assert SIEMProviderType.ELASTICSEARCH.value == "elasticsearch"


class TestCreateSiemProvider:
    def test_creates_splunk(self):
        provider = create_siem_provider(_splunk_config())
        assert isinstance(provider, SplunkHECProvider)

    def test_creates_elasticsearch(self):
        provider = create_siem_provider(_es_config())
        assert isinstance(provider, ElasticsearchProvider)


class TestSplunkHECProviderInit:
    def test_wrong_type_raises(self):
        with pytest.raises(ACGSValidationError):
            SplunkHECProvider(_es_config())


class TestElasticsearchProviderInit:
    def test_wrong_type_raises(self):
        with pytest.raises(ACGSValidationError):
            ElasticsearchProvider(_splunk_config())


class TestSIEMProviderContextManager:
    async def test_aenter_aexit(self):
        provider = SplunkHECProvider(_splunk_config())
        with (
            patch.object(provider, "start", new_callable=AsyncMock) as mock_start,
            patch.object(provider, "close", new_callable=AsyncMock) as mock_close,
        ):
            async with provider as p:
                assert p is provider
                mock_start.assert_awaited_once()
            mock_close.assert_awaited_once()


class TestSIEMProviderStartClose:
    async def test_start_creates_client(self):
        provider = SplunkHECProvider(_splunk_config())
        assert provider._client is None
        await provider.start()
        assert provider._client is not None
        await provider.close()
        assert provider._client is None

    async def test_start_idempotent(self):
        provider = SplunkHECProvider(_splunk_config())
        await provider.start()
        client1 = provider._client
        await provider.start()
        assert provider._client is client1
        await provider.close()

    async def test_close_when_no_client(self):
        provider = SplunkHECProvider(_splunk_config())
        await provider.close()  # should not raise


class TestSIEMProviderEnrichEvent:
    def test_enrich_adds_metadata(self):
        provider = SplunkHECProvider(_splunk_config())
        event = {"action": "validate", "allowed": True}
        enriched = provider._enrich_event(event)
        assert "_siem_metadata" in enriched
        assert enriched["_siem_metadata"]["provider"] == "splunk"
        assert "ingestion_timestamp" in enriched["_siem_metadata"]
        # Original event unchanged
        assert "_siem_metadata" not in event


class TestSplunkSendEvent:
    async def test_send_success(self):
        provider = SplunkHECProvider(_splunk_config())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(200, {"code": 0}))
        provider._client = mock_client

        result = await provider.send_event({"action": "test"})
        assert result is True

    async def test_send_auto_starts_client(self):
        provider = SplunkHECProvider(_splunk_config())
        with patch.object(provider, "start", new_callable=AsyncMock) as mock_start:
            # After start, _client is still None (we didn't really start)
            # so it should raise ServiceUnavailableError
            with pytest.raises(ServiceUnavailableError):
                await provider.send_event({"action": "test"})
            mock_start.assert_awaited_once()

    async def test_send_server_error_code(self):
        provider = SplunkHECProvider(_splunk_config())
        mock_client = AsyncMock()
        # First attempt: server returns error code, second attempt too
        mock_client.post = AsyncMock(
            return_value=_mock_response(200, {"code": 5, "text": "Internal Error"})
        )
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.send_event({"action": "test"})
        assert result is False

    async def test_send_http_non_200(self):
        provider = SplunkHECProvider(_splunk_config())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(503))
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.send_event({"action": "test"})
        assert result is False

    async def test_send_timeout_retries(self):
        provider = SplunkHECProvider(_splunk_config(max_retries=2))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.send_event({"action": "test"})
        assert result is False

    async def test_send_connect_error_retries(self):
        provider = SplunkHECProvider(_splunk_config(max_retries=2))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.send_event({"action": "test"})
        assert result is False

    async def test_send_runtime_error_caught(self):
        provider = SplunkHECProvider(_splunk_config())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("boom"))
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.send_event({"action": "test"})
        assert result is False


class TestSplunkHealthCheck:
    async def test_healthy(self):
        provider = SplunkHECProvider(_splunk_config())
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(200))
        provider._client = mock_client

        result = await provider.health_check()
        assert result["status"] == "healthy"

    async def test_unhealthy_status_code(self):
        provider = SplunkHECProvider(_splunk_config())
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(503))
        provider._client = mock_client

        result = await provider.health_check()
        assert result["status"] == "unhealthy"
        assert result["status_code"] == 503

    async def test_unhealthy_exception(self):
        provider = SplunkHECProvider(_splunk_config())
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=OSError("down"))
        provider._client = mock_client

        result = await provider.health_check()
        assert result["status"] == "unhealthy"
        assert "error" in result

    async def test_health_auto_starts(self):
        provider = SplunkHECProvider(_splunk_config())
        with patch.object(provider, "start", new_callable=AsyncMock):
            with pytest.raises(ServiceUnavailableError):
                await provider.health_check()


class TestSplunkLogRequestError:
    def test_timeout(self):
        SplunkHECProvider._log_request_error(httpx.TimeoutException("t"), 0)

    def test_connect_error(self):
        SplunkHECProvider._log_request_error(httpx.ConnectError("c"), 1)

    def test_generic_error(self):
        SplunkHECProvider._log_request_error(RuntimeError("r"), 2)


class TestSplunkBuildPayload:
    def test_payload_structure(self):
        provider = SplunkHECProvider(_splunk_config())
        event = {"action": "test", "hostname": "myhost"}
        payload = provider._build_hec_payload(event)
        assert payload["host"] == "myhost"
        assert payload["source"] == "acgs2:audit"
        assert payload["sourcetype"] == "_json"
        assert payload["index"] == "acgs2_audit"
        assert payload["event"] is event
        assert "time" in payload

    def test_default_host(self):
        provider = SplunkHECProvider(_splunk_config())
        payload = provider._build_hec_payload({"action": "test"})
        assert payload["host"] == "acgs2-audit"


# ===================================================================
# Elasticsearch Provider Tests
# ===================================================================


class TestElasticsearchIndexName:
    def test_date_suffix(self):
        provider = ElasticsearchProvider(_es_config())
        name = provider._get_index_name()
        assert name.startswith("acgs2_audit-")
        # Verify date format YYYY.MM.DD
        parts = name.split("-", 1)[1].split(".")
        assert len(parts) == 3


class TestElasticsearchSendEvent:
    async def test_send_success(self):
        provider = ElasticsearchProvider(_es_config())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(201, {"result": "created"}))
        provider._client = mock_client

        result = await provider.send_event({"action": "test"})
        assert result is True

    async def test_send_updated_result(self):
        provider = ElasticsearchProvider(_es_config())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(200, {"result": "updated"}))
        provider._client = mock_client

        result = await provider.send_event({"action": "test"})
        assert result is True

    async def test_send_unexpected_result(self):
        provider = ElasticsearchProvider(_es_config())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(200, {"result": "noop"}))
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.send_event({"action": "test"})
        assert result is False

    async def test_send_404_creates_index_and_retries(self):
        provider = ElasticsearchProvider(_es_config(max_retries=3))
        mock_client = AsyncMock()

        responses = [
            _mock_response(404, text="index not found"),
            _mock_response(201, {"result": "created"}),
        ]
        mock_client.post = AsyncMock(side_effect=responses)
        mock_client.put = AsyncMock(return_value=_mock_response(200))
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.send_event({"action": "test"})
        assert result is True
        mock_client.put.assert_awaited_once()

    async def test_send_404_index_creation_fails(self):
        provider = ElasticsearchProvider(_es_config(max_retries=2))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(404, text="missing"))
        mock_client.put = AsyncMock(return_value=_mock_response(500))
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.send_event({"action": "test"})
        assert result is False

    async def test_send_http_error(self):
        provider = ElasticsearchProvider(_es_config(max_retries=1))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(500, text="server error"))
        provider._client = mock_client

        result = await provider.send_event({"action": "test"})
        assert result is False

    async def test_send_timeout_retries(self):
        provider = ElasticsearchProvider(_es_config(max_retries=2))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.send_event({"action": "test"})
        assert result is False

    async def test_send_connect_error(self):
        provider = ElasticsearchProvider(_es_config(max_retries=1))
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        provider._client = mock_client

        result = await provider.send_event({"action": "test"})
        assert result is False

    async def test_send_runtime_error_caught(self):
        provider = ElasticsearchProvider(_es_config())
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("boom"))
        provider._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await provider.send_event({"action": "test"})
        assert result is False

    async def test_auto_starts_client(self):
        provider = ElasticsearchProvider(_es_config())
        with patch.object(provider, "start", new_callable=AsyncMock):
            with pytest.raises(ServiceUnavailableError):
                await provider.send_event({"action": "test"})


class TestElasticsearchPrepareEvent:
    def test_adds_timestamp(self):
        provider = ElasticsearchProvider(_es_config())
        event = {"action": "test"}
        prepared = provider._prepare_es_event(event)
        assert "@timestamp" in prepared
        assert "_siem_metadata" in prepared

    def test_preserves_existing_timestamp(self):
        provider = ElasticsearchProvider(_es_config())
        event = {"action": "test", "@timestamp": "2024-01-01T00:00:00"}
        prepared = provider._prepare_es_event(event)
        assert prepared["@timestamp"] == "2024-01-01T00:00:00"


class TestElasticsearchCreateIndex:
    async def test_create_success(self):
        provider = ElasticsearchProvider(_es_config())
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=_mock_response(200))
        provider._client = mock_client

        result = await provider._create_index("test-index")
        assert result is True

    async def test_create_failure(self):
        provider = ElasticsearchProvider(_es_config())
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(return_value=_mock_response(500))
        provider._client = mock_client

        result = await provider._create_index("test-index")
        assert result is False

    async def test_create_no_client(self):
        provider = ElasticsearchProvider(_es_config())
        result = await provider._create_index("test-index")
        assert result is False

    async def test_create_exception(self):
        provider = ElasticsearchProvider(_es_config())
        mock_client = AsyncMock()
        mock_client.put = AsyncMock(side_effect=OSError("down"))
        provider._client = mock_client

        result = await provider._create_index("test-index")
        assert result is False


class TestElasticsearchHealthCheck:
    async def test_healthy(self):
        provider = ElasticsearchProvider(_es_config())
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_response(
                200,
                {
                    "status": "green",
                    "cluster_name": "test",
                    "number_of_nodes": 3,
                },
            )
        )
        provider._client = mock_client

        result = await provider.health_check()
        assert result["status"] == "green"
        assert result["cluster_name"] == "test"
        assert result["number_of_nodes"] == 3

    async def test_unhealthy_status(self):
        provider = ElasticsearchProvider(_es_config())
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(503))
        provider._client = mock_client

        result = await provider.health_check()
        assert result["status"] == "unhealthy"

    async def test_exception(self):
        provider = ElasticsearchProvider(_es_config())
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=RuntimeError("down"))
        provider._client = mock_client

        result = await provider.health_check()
        assert result["status"] == "unhealthy"
        assert "error" in result

    async def test_auto_starts(self):
        provider = ElasticsearchProvider(_es_config())
        with patch.object(provider, "start", new_callable=AsyncMock):
            with pytest.raises(ServiceUnavailableError):
                await provider.health_check()


class TestElasticsearchLogError:
    def test_timeout(self):
        ElasticsearchProvider._log_es_error(httpx.TimeoutException("t"), 0)

    def test_connect_error(self):
        ElasticsearchProvider._log_es_error(httpx.ConnectError("c"), 1)

    def test_generic(self):
        ElasticsearchProvider._log_es_error(RuntimeError("r"), 2)


# ===================================================================
# Memory Profiler Tests
# ===================================================================


class TestMemorySnapshot:
    def test_properties(self):
        snap = MemorySnapshot(
            timestamp=1.0,
            current_bytes=1024 * 1024 * 5,
            peak_bytes=1024 * 1024 * 10,
            trace_id="abc",
            operation="test",
        )
        assert snap.current_mb == pytest.approx(5.0)
        assert snap.peak_mb == pytest.approx(10.0)

    def test_to_dict(self):
        snap = MemorySnapshot(
            timestamp=1.0,
            current_bytes=1048576,
            peak_bytes=2097152,
            trace_id="t1",
            operation="op1",
            top_allocations=[{"file": "x.py", "size_bytes": 100, "count": 1}],
        )
        d = snap.to_dict()
        assert d["current_mb"] == 1.0
        assert d["peak_mb"] == 2.0
        assert d["trace_id"] == "t1"
        assert d["operation"] == "op1"
        assert len(d["top_allocations"]) == 1
        assert "constitutional_hash" in d


class TestMemoryDelta:
    def test_properties(self):
        delta = MemoryDelta(
            start_bytes=1000,
            end_bytes=2000,
            delta_bytes=1000,
            peak_bytes=3000,
            duration_ms=5.0,
            operation="test",
        )
        assert delta.delta_mb == pytest.approx(1000 / (1024 * 1024))
        assert delta.is_leak_candidate is False

    def test_leak_candidate(self):
        delta = MemoryDelta(
            start_bytes=0,
            end_bytes=11 * 1024 * 1024,
            delta_bytes=11 * 1024 * 1024,
            peak_bytes=11 * 1024 * 1024,
            duration_ms=1.0,
            operation="big",
        )
        assert delta.is_leak_candidate is True

    def test_to_dict(self):
        delta = MemoryDelta(
            start_bytes=0,
            end_bytes=100,
            delta_bytes=100,
            peak_bytes=200,
            duration_ms=1.5,
            operation="op",
            trace_id="t1",
        )
        d = delta.to_dict()
        assert d["operation"] == "op"
        assert d["trace_id"] == "t1"
        assert "delta_mb" in d
        assert "is_leak_candidate" in d
        assert "constitutional_hash" in d


class TestProfilingLevel:
    def test_values(self):
        assert ProfilingLevel.DISABLED.value == "disabled"
        assert ProfilingLevel.SUMMARY.value == "summary"
        assert ProfilingLevel.DETAILED.value == "detailed"
        assert ProfilingLevel.FULL.value == "full"


class TestMemoryProfilingConfig:
    def test_defaults(self):
        cfg = MemoryProfilingConfig()
        assert cfg.enabled is False
        assert cfg.level == ProfilingLevel.SUMMARY
        assert cfg.top_n_allocations == 10
        assert cfg.queue_size == 1000


class TestAsyncMemoryQueue:
    async def test_start_stop(self):
        cfg = MemoryProfilingConfig(queue_size=10)
        queue = AsyncMemoryQueue(cfg)
        await queue.start()
        assert queue._running is True
        await queue.stop()
        assert queue._running is False

    async def test_start_idempotent(self):
        cfg = MemoryProfilingConfig(queue_size=10)
        queue = AsyncMemoryQueue(cfg)
        await queue.start()
        task1 = queue._worker_task
        await queue.start()
        assert queue._worker_task is task1
        await queue.stop()

    async def test_enqueue_when_not_running(self):
        cfg = MemoryProfilingConfig(queue_size=10)
        queue = AsyncMemoryQueue(cfg)
        snap = MemorySnapshot(timestamp=1.0, current_bytes=100, peak_bytes=200)
        result = await queue.enqueue(snap)
        assert result is False

    async def test_enqueue_and_process(self):
        cfg = MemoryProfilingConfig(queue_size=10, flush_interval_s=0.1)
        callback = MagicMock()
        queue = AsyncMemoryQueue(cfg, callback=callback)
        await queue.start()

        snap = MemorySnapshot(timestamp=1.0, current_bytes=100, peak_bytes=200)
        result = await queue.enqueue(snap)
        assert result is True

        # Give worker time to process
        await asyncio.sleep(0.05)

        await queue.stop()
        callback.assert_called_once_with(snap)
        assert len(queue._snapshots) == 1

    async def test_enqueue_full_queue(self):
        cfg = MemoryProfilingConfig(queue_size=1)
        queue = AsyncMemoryQueue(cfg)
        await queue.start()

        snap = MemorySnapshot(timestamp=1.0, current_bytes=100, peak_bytes=200)
        # Fill the queue
        await queue.enqueue(snap)
        # Queue should be full now
        result = await queue.enqueue(snap)
        assert result is False
        await queue.stop()

    async def test_callback_error_handled(self):
        cfg = MemoryProfilingConfig(queue_size=10, flush_interval_s=0.1)
        callback = MagicMock(side_effect=RuntimeError("callback error"))
        queue = AsyncMemoryQueue(cfg, callback=callback)
        await queue.start()

        snap = MemorySnapshot(timestamp=1.0, current_bytes=100, peak_bytes=200)
        await queue.enqueue(snap)
        await asyncio.sleep(0.05)

        await queue.stop()
        # Despite error, snapshot is still stored
        assert len(queue._snapshots) == 1

    def test_get_recent_snapshots_empty(self):
        cfg = MemoryProfilingConfig()
        queue = AsyncMemoryQueue(cfg)
        assert queue.get_recent_snapshots() == []

    def test_get_recent_snapshots(self):
        cfg = MemoryProfilingConfig()
        queue = AsyncMemoryQueue(cfg)
        for i in range(5):
            queue._snapshots.append(
                MemorySnapshot(timestamp=float(i), current_bytes=i * 100, peak_bytes=i * 200)
            )
        recent = queue.get_recent_snapshots(3)
        assert len(recent) == 3
        assert recent[0].timestamp == 2.0

    def test_get_memory_stats_empty(self):
        cfg = MemoryProfilingConfig()
        queue = AsyncMemoryQueue(cfg)
        stats = queue.get_memory_stats()
        assert stats["total_snapshots"] == 0

    def test_get_memory_stats_with_data(self):
        cfg = MemoryProfilingConfig()
        queue = AsyncMemoryQueue(cfg)
        for i in range(1, 4):
            queue._snapshots.append(
                MemorySnapshot(
                    timestamp=float(i),
                    current_bytes=i * 1024 * 1024,
                    peak_bytes=i * 2 * 1024 * 1024,
                )
            )
        stats = queue.get_memory_stats()
        assert stats["total_snapshots"] == 3
        assert "avg_current_mb" in stats
        assert "max_current_mb" in stats
        assert "min_current_mb" in stats
        assert "avg_peak_mb" in stats
        assert "max_peak_mb" in stats


class TestMemoryProfiler:
    def test_init_defaults(self):
        profiler = MemoryProfiler()
        assert profiler.config.enabled is False
        assert profiler._started is False

    def test_start_disabled(self):
        profiler = MemoryProfiler(MemoryProfilingConfig(enabled=False))
        profiler.start()
        assert profiler._started is False

    def test_start_disabled_level(self):
        profiler = MemoryProfiler(
            MemoryProfilingConfig(enabled=True, level=ProfilingLevel.DISABLED)
        )
        profiler.start()
        assert profiler._started is False

    def test_start_enabled(self):
        was_tracing = tracemalloc.is_tracing()
        profiler = MemoryProfiler(MemoryProfilingConfig(enabled=True, level=ProfilingLevel.SUMMARY))
        profiler.start()
        assert profiler._started is True
        assert profiler._baseline is not None
        profiler.stop()
        assert profiler._started is False
        # Restore state
        if was_tracing and not tracemalloc.is_tracing():
            tracemalloc.start()

    def test_stop_not_started(self):
        profiler = MemoryProfiler()
        profiler.stop()  # should not raise

    def test_take_snapshot_summary(self):
        was_tracing = tracemalloc.is_tracing()
        if not was_tracing:
            tracemalloc.start()
        try:
            profiler = MemoryProfiler(
                MemoryProfilingConfig(enabled=True, level=ProfilingLevel.SUMMARY)
            )
            profiler._started = True
            snap = profiler.take_snapshot(operation="test", trace_id="t1")
            assert snap.operation == "test"
            assert snap.trace_id == "t1"
            assert snap.top_allocations == []
        finally:
            if not was_tracing:
                tracemalloc.stop()

    def test_take_snapshot_detailed(self):
        was_tracing = tracemalloc.is_tracing()
        if not was_tracing:
            tracemalloc.start()
        try:
            profiler = MemoryProfiler(
                MemoryProfilingConfig(enabled=True, level=ProfilingLevel.DETAILED)
            )
            profiler._started = True
            snap = profiler.take_snapshot(operation="detailed_test")
            assert isinstance(snap.top_allocations, list)
        finally:
            if not was_tracing:
                tracemalloc.stop()

    def test_reset_peak_started(self):
        was_tracing = tracemalloc.is_tracing()
        if not was_tracing:
            tracemalloc.start()
        try:
            profiler = MemoryProfiler(
                MemoryProfilingConfig(enabled=True, level=ProfilingLevel.SUMMARY)
            )
            profiler._started = True
            profiler.reset_peak()  # should not raise
        finally:
            if not was_tracing:
                tracemalloc.stop()

    def test_reset_peak_not_started(self):
        profiler = MemoryProfiler()
        profiler.reset_peak()  # should not raise

    def test_compare_to_baseline_not_started(self):
        profiler = MemoryProfiler()
        assert profiler.compare_to_baseline() is None

    def test_compare_to_baseline(self):
        was_tracing = tracemalloc.is_tracing()
        if not was_tracing:
            tracemalloc.start()
        try:
            profiler = MemoryProfiler(
                MemoryProfilingConfig(enabled=True, level=ProfilingLevel.SUMMARY)
            )
            profiler._started = True
            profiler._baseline = tracemalloc.take_snapshot()
            # Allocate something
            _ = [0] * 1000
            result = profiler.compare_to_baseline()
            assert result is not None
            assert isinstance(result, list)
        finally:
            if not was_tracing:
                tracemalloc.stop()

    def test_profile_async_returns_context(self):
        profiler = MemoryProfiler()
        ctx = profiler.profile_async("test_op", trace_id="t1")
        assert isinstance(ctx, MemoryProfilingContext)


class TestMemoryProfilingContext:
    async def test_context_disabled(self):
        profiler = MemoryProfiler(MemoryProfilingConfig(enabled=False))
        async with profiler.profile_async("test") as ctx:
            pass
        assert ctx.delta is None

    async def test_context_enabled(self):
        was_tracing = tracemalloc.is_tracing()
        if not was_tracing:
            tracemalloc.start()
        try:
            profiler = MemoryProfiler(
                MemoryProfilingConfig(enabled=True, level=ProfilingLevel.SUMMARY)
            )
            profiler._started = True

            async with profiler.profile_async("test_op", trace_id="t1") as ctx:
                _ = [0] * 100

            assert ctx.delta is not None
            assert ctx.delta.operation == "test_op"
            assert ctx.delta.trace_id == "t1"
            assert ctx.delta.duration_ms >= 0
        finally:
            if not was_tracing:
                tracemalloc.stop()

    async def test_context_with_queue(self):
        was_tracing = tracemalloc.is_tracing()
        if not was_tracing:
            tracemalloc.start()
        try:
            cfg = MemoryProfilingConfig(enabled=True, level=ProfilingLevel.SUMMARY)
            profiler = MemoryProfiler(cfg)
            profiler._started = True

            queue = AsyncMemoryQueue(cfg)
            await queue.start()
            profiler._queue = queue

            async with profiler.profile_async("queued_op") as ctx:
                pass

            await asyncio.sleep(0.05)
            await queue.stop()

            assert ctx.delta is not None
            assert len(queue._snapshots) >= 1
        finally:
            if not was_tracing:
                tracemalloc.stop()

    async def test_context_leak_warning(self):
        was_tracing = tracemalloc.is_tracing()
        if not was_tracing:
            tracemalloc.start()
        try:
            profiler = MemoryProfiler(
                MemoryProfilingConfig(enabled=True, level=ProfilingLevel.SUMMARY)
            )
            profiler._started = True

            # Mock take_snapshot to return large delta
            start_snap = MemorySnapshot(timestamp=1.0, current_bytes=0, peak_bytes=0)
            end_snap = MemorySnapshot(
                timestamp=2.0,
                current_bytes=20 * 1024 * 1024,
                peak_bytes=20 * 1024 * 1024,
            )
            call_count = 0

            def mock_take_snapshot(**kwargs):
                nonlocal call_count
                call_count += 1
                return start_snap if call_count == 1 else end_snap

            profiler.take_snapshot = mock_take_snapshot
            profiler.reset_peak = MagicMock()

            async with profiler.profile_async("leak_test") as ctx:
                pass

            assert ctx.delta is not None
            assert ctx.delta.is_leak_candidate is True
        finally:
            if not was_tracing:
                tracemalloc.stop()


class TestGetMemoryProfiler:
    def test_returns_profiler(self):
        import enhanced_agent_bus.memory_profiler as mp

        old = mp._profiler
        try:
            mp._profiler = None
            p = get_memory_profiler()
            assert isinstance(p, MemoryProfiler)
            # Second call returns same instance
            assert get_memory_profiler() is p
        finally:
            mp._profiler = old


class TestGetMemoryQueue:
    async def test_returns_queue(self):
        import enhanced_agent_bus.memory_profiler as mp

        old = mp._queue
        try:
            mp._queue = None
            q = await get_memory_queue()
            assert isinstance(q, AsyncMemoryQueue)
            # Not started because enabled=False by default
            assert q._running is False
        finally:
            mp._queue = old

    async def test_starts_when_enabled(self):
        cfg = MemoryProfilingConfig(enabled=True, level=ProfilingLevel.SUMMARY)
        q = AsyncMemoryQueue(cfg)
        await q.start()
        assert q._running is True
        await q.stop()
        assert q._running is False


class TestProfileMemoryDecorator:
    async def test_disabled(self):
        import enhanced_agent_bus.memory_profiler as mp

        old = mp._profiler
        try:
            mp._profiler = MemoryProfiler(MemoryProfilingConfig(enabled=False))

            @profile_memory("test_op")
            async def my_func(x):
                return x + 1

            result = await my_func(5)
            assert result == 6
        finally:
            mp._profiler = old

    async def test_enabled(self):
        was_tracing = tracemalloc.is_tracing()
        if not was_tracing:
            tracemalloc.start()
        import enhanced_agent_bus.memory_profiler as mp

        old = mp._profiler
        try:
            cfg = MemoryProfilingConfig(enabled=True, level=ProfilingLevel.SUMMARY)
            profiler = MemoryProfiler(cfg)
            profiler._started = True
            mp._profiler = profiler

            @profile_memory("decorated_op")
            async def my_func(x, trace_id=None):
                return x * 2

            result = await my_func(3, trace_id="t1")
            assert result == 6
        finally:
            mp._profiler = old
            if not was_tracing:
                tracemalloc.stop()

    async def test_trace_id_from_first_arg(self):
        was_tracing = tracemalloc.is_tracing()
        if not was_tracing:
            tracemalloc.start()
        import enhanced_agent_bus.memory_profiler as mp

        old = mp._profiler
        try:
            cfg = MemoryProfilingConfig(enabled=True, level=ProfilingLevel.SUMMARY)
            profiler = MemoryProfiler(cfg)
            profiler._started = True
            mp._profiler = profiler

            class Msg:
                trace_id = "from_obj"

            @profile_memory("obj_op")
            async def process(msg):
                return msg.trace_id

            result = await process(Msg())
            assert result == "from_obj"
        finally:
            mp._profiler = old
            if not was_tracing:
                tracemalloc.stop()


# ===================================================================
# api.app helper function tests
# ===================================================================


class TestNormalizeWorkflowDsn:
    def test_asyncpg_prefix(self):
        dsn = "postgresql+asyncpg://user:pass@host/db"
        assert _normalize_workflow_dsn(dsn) == "postgresql://user:pass@host/db"

    def test_regular_prefix(self):
        dsn = "postgresql://user:pass@host/db"
        assert _normalize_workflow_dsn(dsn) == dsn

    def test_other_prefix(self):
        dsn = "sqlite:///test.db"
        assert _normalize_workflow_dsn(dsn) == dsn


class TestIsDevelopmentLikeEnvironment:
    def test_development(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "development"}):
            assert _is_development_like_environment() is True

    def test_dev(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "dev"}):
            assert _is_development_like_environment() is True

    def test_test(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "test"}):
            assert _is_development_like_environment() is True

    def test_testing(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "testing"}):
            assert _is_development_like_environment() is True

    def test_ci(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "ci"}):
            assert _is_development_like_environment() is True

    def test_production(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            assert _is_development_like_environment() is False

    def test_empty(self):
        with patch.dict("os.environ", {"ENVIRONMENT": ""}):
            assert _is_development_like_environment() is False

    def test_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _is_development_like_environment() is False


class TestLoadOptionalRouters:
    def test_load_visual_studio_router_import_error(self):
        from enhanced_agent_bus.api.app import _load_visual_studio_router

        with patch(
            "enhanced_agent_bus.api.app.import_module",
            side_effect=ImportError("no module"),
        ):
            assert _load_visual_studio_router() is None

    def test_load_visual_studio_router_no_router_attr(self):
        from enhanced_agent_bus.api.app import _load_visual_studio_router

        mock_module = MagicMock(spec=[])
        with patch("enhanced_agent_bus.api.app.import_module", return_value=mock_module):
            assert _load_visual_studio_router() is None

    def test_load_visual_studio_router_wrong_type(self):
        from enhanced_agent_bus.api.app import _load_visual_studio_router

        mock_module = MagicMock()
        mock_module.router = "not_a_router"
        with patch("enhanced_agent_bus.api.app.import_module", return_value=mock_module):
            assert _load_visual_studio_router() is None

    def test_load_copilot_router_import_error(self):
        from enhanced_agent_bus.api.app import _load_copilot_router

        with patch(
            "enhanced_agent_bus.api.app.import_module",
            side_effect=ImportError("no module"),
        ):
            assert _load_copilot_router() is None

    def test_load_copilot_router_no_router_attr(self):
        from enhanced_agent_bus.api.app import _load_copilot_router

        mock_module = MagicMock(spec=[])
        with patch("enhanced_agent_bus.api.app.import_module", return_value=mock_module):
            assert _load_copilot_router() is None


class TestInitializeAgentBusState:
    def test_success(self):
        from enhanced_agent_bus.api.app import _initialize_agent_bus_state

        with patch("enhanced_agent_bus.api.app.MessageProcessor") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = _initialize_agent_bus_state()
            assert result is mock_cls.return_value

    def test_failure_dev_mode(self):
        from enhanced_agent_bus.api.app import _initialize_agent_bus_state

        with (
            patch(
                "enhanced_agent_bus.api.app.MessageProcessor",
                side_effect=RuntimeError("no bus"),
            ),
            patch.dict("os.environ", {"ENVIRONMENT": "development"}),
        ):
            result = _initialize_agent_bus_state()
            assert isinstance(result, dict)
            assert result["status"] == "mock_initialized"

    def test_failure_production_raises(self):
        from enhanced_agent_bus.api.app import _initialize_agent_bus_state

        with (
            patch(
                "enhanced_agent_bus.api.app.MessageProcessor",
                side_effect=RuntimeError("no bus"),
            ),
            patch.dict("os.environ", {"ENVIRONMENT": "production"}),
        ):
            with pytest.raises(RuntimeError):
                _initialize_agent_bus_state()


class TestInitializeWorkflowComponents:
    async def test_success(self):
        from enhanced_agent_bus.api.app import _initialize_workflow_components

        mock_app = MagicMock()
        mock_app.state = MagicMock()

        with (
            patch("enhanced_agent_bus.api.app.PostgresWorkflowRepository") as mock_repo_cls,
            patch("enhanced_agent_bus.api.app.DurableWorkflowExecutor") as mock_exec_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            executor, repo = await _initialize_workflow_components(mock_app)
            assert executor is mock_exec_cls.return_value
            assert repo is mock_repo
            mock_repo.initialize.assert_awaited_once()

    async def test_import_error_non_dev(self):
        from enhanced_agent_bus.api.app import _initialize_workflow_components

        mock_app = MagicMock()
        mock_app.state = MagicMock()

        with (
            patch(
                "enhanced_agent_bus.api.app.PostgresWorkflowRepository",
                side_effect=ImportError("no asyncpg"),
            ),
            patch(
                "enhanced_agent_bus.api.app._is_development_like_environment",
                return_value=False,
            ),
        ):
            executor, repo = await _initialize_workflow_components(mock_app)
            assert executor is None
            assert repo is None

    async def test_import_error_dev_fallback(self):
        from enhanced_agent_bus.api.app import _initialize_workflow_components

        mock_app = MagicMock()
        mock_app.state = MagicMock()

        with (
            patch(
                "enhanced_agent_bus.api.app.PostgresWorkflowRepository",
                side_effect=ImportError("no asyncpg"),
            ),
            patch(
                "enhanced_agent_bus.api.app._is_development_like_environment",
                return_value=True,
            ),
        ):
            executor, repo = await _initialize_workflow_components(mock_app)
            assert executor is not None
            assert repo is None

    async def test_generic_exception_non_dev(self):
        from enhanced_agent_bus.api.app import _initialize_workflow_components

        mock_app = MagicMock()
        mock_app.state = MagicMock()

        with (
            patch(
                "enhanced_agent_bus.api.app.PostgresWorkflowRepository",
                side_effect=Exception("db down"),
            ),
            patch(
                "enhanced_agent_bus.api.app._is_development_like_environment",
                return_value=False,
            ),
        ):
            executor, repo = await _initialize_workflow_components(mock_app)
            assert executor is None
            assert repo is None


class TestInitializeBatchProcessorState:
    def test_success(self):
        from enhanced_agent_bus.api.app import _initialize_batch_processor_state

        mock_mp = MagicMock()
        with patch("enhanced_agent_bus.api.app.BatchMessageProcessor") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = _initialize_batch_processor_state(mock_mp)
            assert result is mock_cls.return_value

    def test_failure_returns_none(self):
        from enhanced_agent_bus.api.app import _initialize_batch_processor_state

        mock_mp = MagicMock()
        with patch(
            "enhanced_agent_bus.api.app.BatchMessageProcessor",
            side_effect=RuntimeError("fail"),
        ):
            result = _initialize_batch_processor_state(mock_mp)
            assert result is None


class TestStopCacheWarmer:
    async def test_no_warmer(self):
        from enhanced_agent_bus.api.app import _stop_cache_warmer_if_running

        with patch(
            "enhanced_agent_bus.api.app.import_module",
            side_effect=ImportError("no cache"),
        ):
            # Should not raise even with import error in the function itself
            await _stop_cache_warmer_if_running()

    async def test_error_handled(self):
        from enhanced_agent_bus.api.app import _stop_cache_warmer_if_running

        # The function catches errors internally, just ensure no unhandled exceptions
        await _stop_cache_warmer_if_running()


class TestShutdownSessionManager:
    async def test_import_error(self):
        from enhanced_agent_bus.api.app import _shutdown_session_manager_if_available

        # This catches ImportError internally
        await _shutdown_session_manager_if_available()


class TestCloseWorkflowRepository:
    async def test_with_repo(self):
        from enhanced_agent_bus.api.app import _close_workflow_repository_if_available

        mock_repo = AsyncMock()
        await _close_workflow_repository_if_available(mock_repo)
        mock_repo.close.assert_awaited_once()

    async def test_with_none(self):
        from enhanced_agent_bus.api.app import _close_workflow_repository_if_available

        await _close_workflow_repository_if_available(None)

    async def test_with_error(self):
        from enhanced_agent_bus.api.app import _close_workflow_repository_if_available

        mock_repo = AsyncMock()
        mock_repo.close = AsyncMock(side_effect=Exception("close error"))
        await _close_workflow_repository_if_available(mock_repo)


class TestRegisterExceptionHandlers:
    def test_registers_handlers(self):
        from enhanced_agent_bus.api.app import _register_exception_handlers

        mock_app = MagicMock()
        _register_exception_handlers(mock_app)
        # 1 rate limit + 10 bus exception handlers = 11 calls
        assert mock_app.add_exception_handler.call_count == 11


class TestInitializeSessionManager:
    async def test_import_error(self):
        from enhanced_agent_bus.api.app import _initialize_session_manager_if_available

        with patch(
            "enhanced_agent_bus.api.app.import_module",
            side_effect=ImportError("no sessions"),
        ):
            # Should not raise - catches ImportError
            await _initialize_session_manager_if_available()
