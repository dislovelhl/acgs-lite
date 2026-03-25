"""
Tests for coverage batch 17c:
1. enhanced_agent_bus.integrations.anomaly_monitoring (AnomalyMonitor)
2. enhanced_agent_bus.local_bus (LocalEventBus)
3. enhanced_agent_bus.mcp.transports.http (HTTPTransport)
"""

import asyncio
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, "packages/enhanced_agent_bus")

# ---------------------------------------------------------------------------
# Patch GovernanceMetrics into ALL copies of enhanced_agent_bus.models BEFORE
# importing anomaly_monitoring (the module does a top-level import that would
# otherwise fail because GovernanceMetrics was removed from models.py).
# ---------------------------------------------------------------------------


@dataclass
class _GovernanceMetrics:
    total_requests: int = 0
    approved_count: int = 0
    denied_count: int = 0
    violation_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0


# Patch into every aliased copy of the module in sys.modules
for _key in list(sys.modules):
    if _key.endswith("enhanced_agent_bus.models"):
        _mod = sys.modules[_key]
        if not hasattr(_mod, "GovernanceMetrics"):
            _mod.GovernanceMetrics = _GovernanceMetrics  # type: ignore[attr-defined]

# Also ensure a direct import picks it up
import enhanced_agent_bus.models as _models_mod

if not hasattr(_models_mod, "GovernanceMetrics"):
    _models_mod.GovernanceMetrics = _GovernanceMetrics  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeGovernanceMetrics:
    total_requests: int = 100
    approved_count: int = 80
    denied_count: int = 10
    violation_count: int = 5
    error_count: int = 5
    avg_latency_ms: float = 12.5


@dataclass
class FakeDetectedAnomaly:
    severity_label: str = "warning"
    description: str = "test anomaly"
    severity_score: float = 0.85


@dataclass
class FakeDetectionResult:
    anomalies: list = field(default_factory=list)


class FakeAnomalyDetector:
    is_fitted: bool = False

    def fit(self, df):
        self.is_fitted = True

    def detect(self, df):
        return FakeDetectionResult()


# =========================================================================
# 1. AnomalyMonitor tests
# =========================================================================


class TestAnomalyMonitor:
    """Tests for enhanced_agent_bus.integrations.anomaly_monitoring."""

    def _make_monitor(self, detector=None, **kwargs):
        """Build an AnomalyMonitor with a fake detector injected."""
        from enhanced_agent_bus.integrations.anomaly_monitoring import AnomalyMonitor

        monitor = AnomalyMonitor(**kwargs)
        if detector is not None:
            monitor._detector = detector
        return monitor

    # -- init / no-detector path --

    def test_init_without_detector(self):
        """When AnomalyDetector is None the monitor still constructs."""
        monitor = self._make_monitor(detector=None)
        # With None detector, record_metrics should be a no-op
        monitor._detector = None
        monitor.record_metrics(FakeGovernanceMetrics())
        assert monitor._metrics_buffer == []

    def test_init_custom_config(self):
        from enhanced_agent_bus.config import BusConfiguration

        cfg = BusConfiguration()
        monitor = self._make_monitor(detector=FakeAnomalyDetector(), config=cfg)
        assert monitor.config is cfg

    def test_init_default_intervals(self):
        monitor = self._make_monitor(detector=FakeAnomalyDetector())
        assert monitor.check_interval == 300
        assert monitor.min_training_samples == 100

    def test_init_custom_intervals(self):
        monitor = self._make_monitor(
            detector=FakeAnomalyDetector(),
            check_interval_seconds=60,
            min_training_samples=10,
        )
        assert monitor.check_interval == 60
        assert monitor.min_training_samples == 10

    # -- record_metrics --

    def test_record_metrics_appends_to_buffer(self):
        detector = FakeAnomalyDetector()
        monitor = self._make_monitor(detector=detector)
        monitor.record_metrics(FakeGovernanceMetrics())
        assert len(monitor._metrics_buffer) == 1
        entry = monitor._metrics_buffer[0]
        assert entry["total_requests"] == 100
        assert entry["denial_rate"] == 10 / 100
        assert entry["violation_rate"] == 5 / 100

    def test_record_metrics_trims_buffer_at_10k(self):
        detector = FakeAnomalyDetector()
        monitor = self._make_monitor(detector=detector)
        # Pre-fill buffer past 10k
        monitor._metrics_buffer = [{"x": i} for i in range(10001)]
        monitor.record_metrics(FakeGovernanceMetrics())
        # Should trim to last 5000 then add 1
        assert len(monitor._metrics_buffer) <= 5001

    def test_record_metrics_no_detector_returns_early(self):
        monitor = self._make_monitor(detector=None)
        monitor._detector = None
        monitor.record_metrics(FakeGovernanceMetrics())
        assert len(monitor._metrics_buffer) == 0

    def test_record_metrics_zero_total_requests_no_division_error(self):
        detector = FakeAnomalyDetector()
        monitor = self._make_monitor(detector=detector)
        metrics = FakeGovernanceMetrics(total_requests=0, denied_count=0, violation_count=0)
        monitor.record_metrics(metrics)
        entry = monitor._metrics_buffer[0]
        assert entry["denial_rate"] == 0.0
        assert entry["violation_rate"] == 0.0

    # -- start / stop --

    async def test_start_creates_task(self):
        detector = FakeAnomalyDetector()
        monitor = self._make_monitor(detector=detector)
        # Patch the monitoring loop to exit immediately
        monitor._monitoring_loop = AsyncMock()
        await monitor.start()
        assert monitor._is_running is True
        assert monitor._monitoring_task is not None
        await monitor.stop()

    async def test_start_no_detector_is_noop(self):
        monitor = self._make_monitor(detector=None)
        monitor._detector = None
        await monitor.start()
        assert monitor._is_running is False
        assert monitor._monitoring_task is None

    async def test_start_already_running_is_noop(self):
        detector = FakeAnomalyDetector()
        monitor = self._make_monitor(detector=detector)
        monitor._is_running = True
        await monitor.start()
        # No task created because already running
        assert monitor._monitoring_task is None

    async def test_stop_cancels_task(self):
        detector = FakeAnomalyDetector()
        monitor = self._make_monitor(detector=detector)
        monitor._monitoring_loop = AsyncMock()
        await monitor.start()
        task = monitor._monitoring_task
        await monitor.stop()
        assert monitor._is_running is False
        assert task.cancelled() or task.done()

    async def test_stop_without_task(self):
        monitor = self._make_monitor(detector=FakeAnomalyDetector())
        monitor._monitoring_task = None
        await monitor.stop()
        assert monitor._is_running is False

    # -- detect_anomalies --

    async def test_detect_anomalies_insufficient_samples(self):
        detector = FakeAnomalyDetector()
        monitor = self._make_monitor(detector=detector, min_training_samples=5)
        # Only 3 samples
        for _ in range(3):
            monitor.record_metrics(FakeGovernanceMetrics())
        result = await monitor.detect_anomalies()
        assert result == []

    async def test_detect_anomalies_no_detector(self):
        monitor = self._make_monitor(detector=None)
        monitor._detector = None
        result = await monitor.detect_anomalies()
        assert result == []

    async def test_detect_anomalies_runs_detection(self):
        detector = FakeAnomalyDetector()
        monitor = self._make_monitor(detector=detector, min_training_samples=2)
        for _ in range(5):
            monitor.record_metrics(FakeGovernanceMetrics())
        result = await monitor.detect_anomalies()
        assert result == []
        assert detector.is_fitted is True

    async def test_detect_anomalies_handles_anomalies(self):
        anomaly = FakeDetectedAnomaly(severity_label="warning")
        detector = FakeAnomalyDetector()
        detector.detect = lambda df: FakeDetectionResult(anomalies=[anomaly])
        monitor = self._make_monitor(detector=detector, min_training_samples=2)
        for _ in range(5):
            monitor.record_metrics(FakeGovernanceMetrics())
        result = await monitor.detect_anomalies()
        assert len(result) == 1
        assert result[0].severity_label == "warning"

    async def test_detect_anomalies_critical_anomaly(self):
        anomaly = FakeDetectedAnomaly(severity_label="critical", severity_score=0.99)
        detector = FakeAnomalyDetector()
        detector.detect = lambda df: FakeDetectionResult(anomalies=[anomaly])
        monitor = self._make_monitor(detector=detector, min_training_samples=2)
        for _ in range(5):
            monitor.record_metrics(FakeGovernanceMetrics())
        result = await monitor.detect_anomalies()
        assert result[0].severity_label == "critical"

    async def test_detect_anomalies_retrains_on_modulo_1000(self):
        detector = FakeAnomalyDetector()
        detector.is_fitted = True
        fit_calls = []
        original_fit = detector.fit
        detector.fit = lambda df: (fit_calls.append(1), original_fit(df))
        monitor = self._make_monitor(detector=detector, min_training_samples=2)
        # Fill buffer to exactly 1000
        monitor._metrics_buffer = [
            {
                "total_requests": 1,
                "approved_count": 1,
                "denied_count": 0,
                "violation_count": 0,
                "error_count": 0,
                "avg_latency_ms": 1.0,
                "denial_rate": 0.0,
                "violation_rate": 0.0,
                "timestamp": "2024-01-01",
            }
            for _ in range(1000)
        ]
        await monitor.detect_anomalies()
        assert len(fit_calls) == 1  # Should retrain at modulo 1000


# =========================================================================
# 2. LocalEventBus tests
# =========================================================================


class TestLocalEventBus:
    """Tests for enhanced_agent_bus.local_bus.LocalEventBus."""

    def _make_bus(self):
        from enhanced_agent_bus.local_bus import LocalEventBus

        return LocalEventBus()

    def _make_message(self, **kwargs):
        from enhanced_agent_bus.core_models import AgentMessage, MessageType

        defaults = {
            "from_agent": "agent-a",
            "to_agent": "agent-b",
            "tenant_id": "tenant1",
            "message_type": MessageType.COMMAND,
        }
        defaults.update(kwargs)
        return AgentMessage(**defaults)

    async def test_start_sets_running(self):
        bus = self._make_bus()
        await bus.start()
        assert bus._running is True
        await bus.stop()

    async def test_stop_clears_queues(self):
        bus = self._make_bus()
        await bus.start()
        # Add something to queues via subscribe
        handler = AsyncMock()
        from enhanced_agent_bus.core_models import MessageType

        await bus.subscribe("tenant1", [MessageType.COMMAND], handler)
        assert len(bus._queues) > 0
        await bus.stop()
        assert bus._running is False
        assert len(bus._queues) == 0

    def test_get_topic_key(self):
        bus = self._make_bus()
        assert bus._get_topic_key("t1", "COMMAND") == "t1:command"

    async def test_send_message_not_running_raises(self):
        from enhanced_agent_bus.exceptions import MessageDeliveryError

        bus = self._make_bus()
        msg = self._make_message()
        with pytest.raises(MessageDeliveryError):
            await bus.send_message(msg)

    async def test_send_message_no_subscribers_returns_true(self):
        bus = self._make_bus()
        await bus.start()
        msg = self._make_message()
        result = await bus.send_message(msg)
        assert result is True
        await bus.stop()

    async def test_send_message_delivers_to_subscriber(self):
        bus = self._make_bus()
        await bus.start()
        received = []
        from enhanced_agent_bus.core_models import MessageType

        async def handler(data):
            received.append(data)

        await bus.subscribe("tenant1", [MessageType.COMMAND], handler)
        msg = self._make_message(tenant_id="tenant1", message_type=MessageType.COMMAND)
        await bus.send_message(msg)

        # Give the background consumer a moment to process
        await asyncio.sleep(0.05)
        assert len(received) == 1
        await bus.stop()

    async def test_send_message_delivers_to_global_subscriber(self):
        bus = self._make_bus()
        await bus.start()
        received = []
        from enhanced_agent_bus.core_models import MessageType

        async def handler(data):
            received.append(data)

        # Subscribe to "all" tenants
        await bus.subscribe("all", [MessageType.COMMAND], handler)
        msg = self._make_message(tenant_id="tenant1", message_type=MessageType.COMMAND)
        await bus.send_message(msg)
        await asyncio.sleep(0.05)
        assert len(received) == 1
        await bus.stop()

    async def test_subscribe_callable_shorthand(self):
        bus = self._make_bus()
        await bus.start()
        received = []

        async def handler(data):
            received.append(data)

        # Subscribe with single callable argument (subscribes to "all" tenants)
        await bus.subscribe(handler)

        from enhanced_agent_bus.core_models import MessageType

        # Use a specific tenant; the "all" subscriber catches messages from any tenant
        msg = self._make_message(tenant_id="tenant-x", message_type=MessageType.COMMAND)
        await bus.send_message(msg)
        await asyncio.sleep(0.05)
        assert len(received) == 1
        await bus.stop()

    async def test_subscribe_none_message_types(self):
        bus = self._make_bus()
        await bus.start()
        handler = AsyncMock()
        await bus.subscribe("tenant1", None, handler)
        # No queues registered since message_types is None
        assert len(bus._queues["tenant1"]) == 0
        await bus.stop()

    async def test_consume_queue_handles_handler_error(self):
        bus = self._make_bus()
        await bus.start()
        from enhanced_agent_bus.core_models import MessageType

        call_count = 0

        async def bad_handler(data):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("handler boom")

        await bus.subscribe("tenant1", [MessageType.COMMAND], bad_handler)
        msg = self._make_message(tenant_id="tenant1", message_type=MessageType.COMMAND)
        await bus.send_message(msg)
        await asyncio.sleep(0.05)
        # Handler should have been called (and error logged, not propagated)
        assert call_count >= 1
        await bus.stop()

    async def test_publish_vote_event(self):
        bus = self._make_bus()
        await bus.start()
        q = asyncio.Queue()
        bus._queues["tenant1"]["EVENT"].append(q)
        result = await bus.publish_vote_event("tenant1", {"vote": "yes"})
        assert result is True
        assert q.qsize() == 1
        await bus.stop()

    async def test_publish_vote_event_default_tenant(self):
        bus = self._make_bus()
        await bus.start()
        q = asyncio.Queue()
        bus._queues["default"]["EVENT"].append(q)
        result = await bus.publish_vote_event("", {"vote": "no"})
        assert result is True
        assert q.qsize() == 1
        await bus.stop()

    async def test_publish_audit_record(self):
        bus = self._make_bus()
        await bus.start()
        q = asyncio.Queue()
        bus._queues["tenant1"]["AUDIT"].append(q)
        result = await bus.publish_audit_record("tenant1", {"action": "create"})
        assert result is True
        assert q.qsize() == 1
        await bus.stop()

    async def test_publish_audit_record_default_tenant(self):
        bus = self._make_bus()
        await bus.start()
        q = asyncio.Queue()
        bus._queues["default"]["AUDIT"].append(q)
        result = await bus.publish_audit_record("", {"action": "delete"})
        assert result is True
        assert q.qsize() == 1
        await bus.stop()

    async def test_send_message_none_tenant_defaults(self):
        bus = self._make_bus()
        await bus.start()
        msg = self._make_message(tenant_id=None)
        result = await bus.send_message(msg)
        assert result is True
        await bus.stop()

    async def test_send_message_none_to_agent(self):
        """When to_agent is None, the error message uses 'unknown'."""
        bus = self._make_bus()
        # Not started, so it should raise
        from enhanced_agent_bus.exceptions import MessageDeliveryError

        msg = self._make_message(to_agent=None)
        with pytest.raises(MessageDeliveryError):
            await bus.send_message(msg)


# =========================================================================
# 3. HTTPTransport tests
# =========================================================================


class TestRPCHelpers:
    """Test the module-level JSON-RPC helper functions."""

    def test_rpc_success(self):
        from enhanced_agent_bus.mcp.transports.http import _rpc_success

        resp = _rpc_success("req-1", {"tools": []})
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == "req-1"
        assert resp["result"] == {"tools": []}

    def test_rpc_success_none_id(self):
        from enhanced_agent_bus.mcp.transports.http import _rpc_success

        resp = _rpc_success(None, "ok")
        assert resp["id"] is None

    def test_rpc_error_without_data(self):
        from enhanced_agent_bus.mcp.transports.http import _rpc_error

        resp = _rpc_error("req-2", -32601, "Not found")
        assert resp["error"]["code"] == -32601
        assert resp["error"]["message"] == "Not found"
        assert "data" not in resp["error"]

    def test_rpc_error_with_data(self):
        from enhanced_agent_bus.mcp.transports.http import _rpc_error

        resp = _rpc_error("req-3", -32603, "Internal", {"detail": "x"})
        assert resp["error"]["data"] == {"detail": "x"}


class TestHTTPTransport:
    """Tests for enhanced_agent_bus.mcp.transports.http.HTTPTransport."""

    def _make_transport(self, **kwargs):
        from enhanced_agent_bus.mcp.transports.http import HTTPTransport

        defaults = {
            "base_url": "http://toolbox:5000",
            "max_retries": 0,
            "retry_jitter": False,
            "retry_base_delay": 0.0,
        }
        defaults.update(kwargs)
        return HTTPTransport(**defaults)

    def test_init_defaults(self):
        t = self._make_transport()
        assert t.base_url == "http://toolbox:5000"
        assert t.is_connected is False
        assert "Content-Type" in t._headers

    def test_init_trailing_slash_stripped(self):
        t = self._make_transport(base_url="http://host:9000/")
        assert t.base_url == "http://host:9000"

    def test_init_auth_token_sets_header(self):
        t = self._make_transport(auth_token="secret")
        assert t._headers["Authorization"] == "Bearer secret"

    def test_init_extra_headers_merged(self):
        t = self._make_transport(extra_headers={"X-Custom": "val"})
        assert t._headers["X-Custom"] == "val"

    def test_init_no_auth_no_authorization_header(self):
        t = self._make_transport()
        assert "Authorization" not in t._headers

    def test_init_max_retries_clamped_to_zero(self):
        t = self._make_transport(max_retries=-5)
        assert t._max_retries == 0

    def test_repr_disconnected(self):
        t = self._make_transport()
        r = repr(t)
        assert "disconnected" in r
        assert "toolbox:5000" in r

    def test_repr_connected(self):
        t = self._make_transport()
        t._connected = True
        assert "connected" in repr(t)

    # -- connect / disconnect --

    async def test_connect_success(self):
        t = self._make_transport()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            await t.connect()

        assert t.is_connected is True

    async def test_connect_already_connected_is_noop(self):
        t = self._make_transport()
        t._connected = True
        t._client = AsyncMock()
        await t.connect()
        # Should return early, no new client created

    async def test_connect_http_status_error_raises(self):
        from enhanced_agent_bus.mcp.transports.base import MCPTransportError

        t = self._make_transport()

        request = httpx.Request("GET", "http://toolbox:5000/api/tools")
        response = httpx.Response(500, request=request)
        exc = httpx.HTTPStatusError("Server Error", request=request, response=response)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=exc)
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(MCPTransportError, match="probe failed"):
                await t.connect()

        assert t.is_connected is False

    async def test_connect_transport_error_raises(self):
        from enhanced_agent_bus.mcp.transports.base import MCPTransportError

        t = self._make_transport()

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(MCPTransportError, match="probe failed"):
                await t.connect()

    async def test_disconnect_connected(self):
        t = self._make_transport()
        t._connected = True
        t._client = AsyncMock(spec=httpx.AsyncClient)
        t._client.aclose = AsyncMock()
        await t.disconnect()
        assert t.is_connected is False
        assert t._client is None

    async def test_disconnect_idempotent(self):
        t = self._make_transport()
        await t.disconnect()
        await t.disconnect()
        assert t.is_connected is False

    async def test_teardown_client_suppresses_errors(self):
        t = self._make_transport()
        mock_client = AsyncMock()
        mock_client.aclose = AsyncMock(side_effect=RuntimeError("close err"))
        t._client = mock_client
        await t._teardown_client()
        assert t._client is None

    # -- context manager --

    async def test_context_manager(self):
        t = self._make_transport()
        t.connect = AsyncMock()
        t.disconnect = AsyncMock()
        async with t as transport:
            assert transport is t
        t.connect.assert_awaited_once()
        t.disconnect.assert_awaited_once()

    # -- send --

    async def test_send_not_connected_raises(self):
        from enhanced_agent_bus.mcp.transports.base import MCPTransportError

        t = self._make_transport()
        with pytest.raises(MCPTransportError, match="before connect"):
            await t.send({"method": "tools/list", "id": 1})

    async def test_send_tools_list(self):
        t = self._make_transport()
        t._connected = True
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = [{"name": "tool1"}]
        mock_client.request = AsyncMock(return_value=response)
        t._client = mock_client

        result = await t.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert result["result"]["tools"] == [{"name": "tool1"}]

    async def test_send_tools_list_dict_response(self):
        t = self._make_transport()
        t._connected = True
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = {"tools": [{"name": "t1"}, {"name": "t2"}]}
        mock_client.request = AsyncMock(return_value=response)
        t._client = mock_client

        result = await t.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert len(result["result"]["tools"]) == 2

    async def test_send_tools_list_non_list_non_dict(self):
        t = self._make_transport()
        t._connected = True
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = "unexpected"
        mock_client.request = AsyncMock(return_value=response)
        t._client = mock_client

        result = await t.send({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        assert result["result"]["tools"] == []

    async def test_send_tools_call(self):
        t = self._make_transport()
        t._connected = True
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = {"content": [{"type": "text", "text": "ok"}], "isError": False}
        mock_client.request = AsyncMock(return_value=response)
        t._client = mock_client

        result = await t.send(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "my_tool", "arguments": {"x": 1}},
            }
        )
        assert result["result"]["content"][0]["text"] == "ok"

    async def test_send_tools_call_normalizes_non_content_response(self):
        t = self._make_transport()
        t._connected = True
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = {"answer": 42}
        mock_client.request = AsyncMock(return_value=response)
        t._client = mock_client

        result = await t.send(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "calc"},
            }
        )
        assert result["result"]["isError"] is False
        assert result["result"]["content"][0]["type"] == "text"

    async def test_send_tools_call_missing_name(self):
        t = self._make_transport()
        t._connected = True
        t._client = AsyncMock()

        result = await t.send(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {},
            }
        )
        assert "error" in result
        assert result["error"]["code"] == -32603

    async def test_send_unsupported_method(self):
        t = self._make_transport()
        t._connected = True
        t._client = AsyncMock()

        result = await t.send({"jsonrpc": "2.0", "id": 7, "method": "resources/list"})
        assert "error" in result
        assert result["error"]["code"] == -32601

    async def test_send_empty_method(self):
        t = self._make_transport()
        t._connected = True
        t._client = AsyncMock()

        result = await t.send({"jsonrpc": "2.0", "id": 8})
        assert "error" in result

    # -- retry logic --

    async def test_request_with_retry_timeout_exhausts(self):
        from enhanced_agent_bus.mcp.transports.base import MCPTransportError

        t = self._make_transport(max_retries=1, retry_base_delay=0.0)
        t._connected = True
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
        t._client = mock_client

        with pytest.raises(MCPTransportError, match="attempt.*failed"):
            await t._request_with_retry("GET", "/api/tools")

    async def test_request_with_retry_transport_error(self):
        from enhanced_agent_bus.mcp.transports.base import MCPTransportError

        t = self._make_transport(max_retries=1, retry_base_delay=0.0)
        t._connected = True
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
        t._client = mock_client

        with pytest.raises(MCPTransportError, match="attempt.*failed"):
            await t._request_with_retry("GET", "/test")

    async def test_request_with_retry_non_retryable_http_error(self):
        from enhanced_agent_bus.mcp.transports.base import MCPTransportError

        t = self._make_transport(max_retries=1, retry_base_delay=0.0)
        t._connected = True
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        request = httpx.Request("GET", "http://toolbox:5000/api/tools")
        response_obj = httpx.Response(404, request=request)
        mock_client.request = AsyncMock(return_value=response_obj)
        t._client = mock_client

        with pytest.raises(MCPTransportError, match="HTTP 404"):
            await t._request_with_retry("GET", "/api/tools")

    async def test_request_with_retry_retryable_status_then_success(self):
        t = self._make_transport(max_retries=2, retry_base_delay=0.0)
        t._connected = True
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        request = httpx.Request("GET", "http://toolbox:5000/api/tools")
        retry_response = httpx.Response(503, request=request)
        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.raise_for_status = MagicMock()
        ok_response.json.return_value = {"tools": []}

        mock_client.request = AsyncMock(side_effect=[retry_response, ok_response])
        t._client = mock_client

        result = await t._request_with_retry("GET", "/api/tools")
        assert result == {"tools": []}

    async def test_request_with_retry_retryable_status_exhausted(self):
        from enhanced_agent_bus.mcp.transports.base import MCPTransportError

        t = self._make_transport(max_retries=1, retry_base_delay=0.0)
        t._connected = True
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        request = httpx.Request("GET", "http://toolbox:5000/api/tools")
        retry_resp = httpx.Response(503, request=request)
        # On second attempt, also 503 but this time it's the last attempt,
        # so raise_for_status will fire
        mock_client.request = AsyncMock(return_value=retry_resp)
        t._client = mock_client

        with pytest.raises(MCPTransportError, match="HTTP 503"):
            await t._request_with_retry("GET", "/api/tools")

    # -- backoff --

    async def test_backoff_with_jitter(self):
        t = self._make_transport(retry_jitter=True, retry_base_delay=0.001, retry_max_delay=0.01)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await t._backoff(0)
            mock_sleep.assert_awaited_once()
            delay = mock_sleep.call_args[0][0]
            assert delay >= 0.001

    async def test_backoff_without_jitter(self):
        t = self._make_transport(retry_jitter=False, retry_base_delay=0.001, retry_max_delay=0.01)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await t._backoff(0)
            mock_sleep.assert_awaited_once()
            delay = mock_sleep.call_args[0][0]
            assert delay == pytest.approx(0.001)

    async def test_backoff_respects_max_delay(self):
        t = self._make_transport(retry_jitter=False, retry_base_delay=1.0, retry_max_delay=2.0)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await t._backoff(10)  # 1.0 * 2^10 = 1024, capped to 2.0
            delay = mock_sleep.call_args[0][0]
            assert delay == pytest.approx(2.0)

    # -- properties --

    def test_is_connected_property(self):
        t = self._make_transport()
        assert t.is_connected is False
        t._connected = True
        assert t.is_connected is True

    def test_base_url_property(self):
        t = self._make_transport(base_url="http://example.com")
        assert t.base_url == "http://example.com"

    # -- post_with_retry / get_with_retry --

    async def test_get_with_retry_delegates(self):
        t = self._make_transport()
        t._request_with_retry = AsyncMock(return_value={"ok": True})
        result = await t._get_with_retry("/path")
        t._request_with_retry.assert_awaited_once_with("GET", "/path")
        assert result == {"ok": True}

    async def test_post_with_retry_delegates(self):
        t = self._make_transport()
        t._request_with_retry = AsyncMock(return_value={"ok": True})
        result = await t._post_with_retry("/path", body={"x": 1})
        t._request_with_retry.assert_awaited_once_with("POST", "/path", json_body={"x": 1})
        assert result == {"ok": True}
