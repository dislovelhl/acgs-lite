# Constitutional Hash: 608508a9bd224290
"""
Extended coverage tests for src/core/enhanced_agent_bus/mcp_server/server.py.

Targets the branches not exercised by test_mcp_server.py:
- start() / stop() full lifecycle with audit log
- _run_stdio_transport() all branches
- _run_sse_transport() fallback
- handle_request() error branch
- get_metrics() hasattr branches
- create_mcp_server() with external services
- main() entry point

asyncio_mode = "auto" is set in pyproject.toml — no @pytest.mark.asyncio needed.
"""

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

from ..config import MCPConfig, TransportType
from ..protocol.types import MCPRequest
from ..resources.audit_trail import AuditEventType
from ..server import MCPServer, create_mcp_server, main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_server(transport: TransportType = TransportType.STDIO) -> MCPServer:
    config = MCPConfig(transport_type=transport)
    return MCPServer(config=config)


def _make_request(method: str, params: dict | None = None, req_id: str = "1") -> MCPRequest:
    return MCPRequest(jsonrpc="2.0", id=req_id, method=method, params=params or {})


def _make_mock_loop() -> MagicMock:
    """Return a mock event loop suitable for patching asyncio.get_running_loop()."""
    loop = MagicMock()
    loop.connect_read_pipe = AsyncMock(return_value=(MagicMock(), MagicMock()))
    loop.connect_write_pipe = AsyncMock(return_value=(MagicMock(), MagicMock()))
    return loop


# ---------------------------------------------------------------------------
# start() / stop() lifecycle
# ---------------------------------------------------------------------------


class TestMCPServerStartStop:
    """Tests for the full server start / stop lifecycle."""

    async def test_start_already_running_returns_early(self):
        """start() when _running=True logs warning and returns immediately."""
        server = _make_server()
        server._running = True  # pretend already running

        with patch.object(server, "_run_stdio_transport", new_callable=AsyncMock) as mock_stdio:
            with patch.object(server, "connect_adapters", new_callable=AsyncMock) as mock_conn:
                await server.start()
                mock_conn.assert_not_called()
                mock_stdio.assert_not_called()

    async def test_start_logs_audit_event(self):
        """start() records a SYSTEM audit event on the audit_trail resource."""
        server = _make_server()
        audit_resource = server._resources["audit_trail"]
        initial_count = audit_resource._entry_counter

        with patch.object(server, "_run_stdio_transport", new_callable=AsyncMock):
            await server.start()

        assert audit_resource._entry_counter > initial_count
        last_entry = audit_resource._entries[-1]
        assert last_entry.event_type == AuditEventType.SYSTEM
        assert last_entry.actor_id == "mcp-server"
        assert "started" in last_entry.action.lower()

    async def test_start_locks_handler_registration(self):
        """start() calls handler.lock_registration()."""
        server = _make_server()

        with patch.object(server, "_run_stdio_transport", new_callable=AsyncMock):
            await server.start()

        assert server._handler._registration_locked is True

    async def test_start_sets_running_flag(self):
        """start() sets _running=True and clears the shutdown event."""
        server = _make_server()

        with patch.object(server, "_run_stdio_transport", new_callable=AsyncMock):
            await server.start()

        # After transport returns, _running remains True (transport ended cleanly)
        assert server._running is True

    async def test_start_runs_stdio_transport_by_default(self):
        """start() dispatches to _run_stdio_transport for STDIO transport."""
        server = _make_server(TransportType.STDIO)

        with patch.object(server, "_run_stdio_transport", new_callable=AsyncMock) as mock_stdio:
            await server.start()

        mock_stdio.assert_awaited_once()

    async def test_start_runs_sse_transport_for_sse(self):
        """start() dispatches to _run_sse_transport for SSE transport."""
        server = _make_server(TransportType.SSE)

        with patch.object(server, "_run_sse_transport", new_callable=AsyncMock) as mock_sse:
            await server.start()

        mock_sse.assert_awaited_once()

    async def test_start_raises_for_unknown_transport(self):
        """start() raises ValueError for an unknown transport type."""
        server = _make_server()
        # Use WEBSOCKET which is an enum value but not handled in start()
        server.config.transport_type = TransportType.WEBSOCKET

        with pytest.raises(ValueError, match="Unknown transport"):
            await server.start()

    async def test_stop_when_running_logs_audit_and_disconnects(self):
        """stop() logs audit event, disconnects adapters, and sets _running=False."""
        server = _make_server()
        server._running = True
        server._request_count = 10
        server._error_count = 1

        audit_resource = server._resources["audit_trail"]
        initial_count = audit_resource._entry_counter

        with patch.object(server, "disconnect_adapters", new_callable=AsyncMock) as mock_disc:
            await server.stop()

        assert server._running is False
        assert server._shutdown_event.is_set()
        mock_disc.assert_awaited_once()

        assert audit_resource._entry_counter > initial_count
        last_entry = audit_resource._entries[-1]
        assert last_entry.event_type == AuditEventType.SYSTEM
        assert "stopped" in last_entry.action.lower()
        assert last_entry.details["requests_processed"] == 10
        assert last_entry.details["errors"] == 1

    async def test_stop_not_running_is_noop(self):
        """stop() when _running=False exits immediately without calling disconnect."""
        server = _make_server()
        server._running = False

        with patch.object(server, "disconnect_adapters", new_callable=AsyncMock) as mock_disc:
            await server.stop()

        mock_disc.assert_not_called()

    async def test_stop_no_audit_resource(self):
        """stop() works without an audit_trail resource in _resources."""
        server = _make_server()
        server._running = True
        server._resources.pop("audit_trail")

        with patch.object(server, "disconnect_adapters", new_callable=AsyncMock):
            await server.stop()

        assert server._running is False

    async def test_start_no_audit_resource(self):
        """start() works without an audit_trail resource in _resources."""
        server = _make_server()
        server._resources.pop("audit_trail")

        with patch.object(server, "_run_stdio_transport", new_callable=AsyncMock):
            await server.start()

        assert server._running is True


# ---------------------------------------------------------------------------
# connect_adapters / disconnect_adapters
# ---------------------------------------------------------------------------


class TestAdapterLifecycle:
    """Tests for adapter connect / disconnect paths."""

    async def test_connect_adapters_success_path(self):
        """connect_adapters returns True when adapter.connect() returns True."""
        server = _make_server()
        agent_bus_adapter = server._adapters["agent_bus"]

        with patch.object(agent_bus_adapter, "connect", new_callable=AsyncMock, return_value=True):
            result = await server.connect_adapters()

        assert result is True

    async def test_connect_adapters_failure_path(self):
        """connect_adapters still returns True (standalone mode) even when connect() = False."""
        server = _make_server()
        agent_bus_adapter = server._adapters["agent_bus"]

        with patch.object(agent_bus_adapter, "connect", new_callable=AsyncMock, return_value=False):
            result = await server.connect_adapters()

        assert result is True

    async def test_connect_adapters_without_agent_bus_adapter(self):
        """connect_adapters handles missing agent_bus adapter gracefully."""
        server = _make_server()
        server._adapters.pop("agent_bus")

        result = await server.connect_adapters()
        assert result is True

    async def test_disconnect_adapters_calls_agent_bus_disconnect(self):
        """disconnect_adapters calls disconnect() on the agent_bus adapter."""
        server = _make_server()
        agent_bus_adapter = server._adapters["agent_bus"]

        with patch.object(agent_bus_adapter, "disconnect", new_callable=AsyncMock) as mock_disc:
            await server.disconnect_adapters()

        mock_disc.assert_awaited_once()

    async def test_disconnect_adapters_no_agent_bus_key(self):
        """disconnect_adapters handles missing agent_bus key gracefully."""
        server = _make_server()
        server._adapters.pop("agent_bus")

        # Should not raise
        await server.disconnect_adapters()


# Resolve the real import path from the imported server class to avoid stale module aliases.
_SERVER_MODULE = MCPServer.__module__


# ---------------------------------------------------------------------------
# _run_stdio_transport — use mock event loop to avoid real stdin/stdout
# ---------------------------------------------------------------------------


def _build_stdio_mocks(
    lines: list[bytes],
    server: MCPServer,
    extra_timeout_errors: int = 0,
) -> tuple[MagicMock, MagicMock, MagicMock, list[bytes]]:
    """
    Build a fake reader and writer and a mock loop.

    The fake reader yields each line in `lines`, then raises CancelledError
    (after setting server._running = False) to exit the transport loop.
    Extra asyncio.TimeoutError raises can be inserted before CancelledError.
    """
    call_count = 0
    line_count = len(lines)
    timeout_count = extra_timeout_errors

    async def fake_readline():
        nonlocal call_count, timeout_count
        call_count += 1

        if call_count <= line_count:
            return lines[call_count - 1]

        if timeout_count > 0:
            timeout_count -= 1
            raise TimeoutError()

        server._running = False
        raise asyncio.CancelledError()

    mock_reader = MagicMock()
    mock_reader.readline = fake_readline

    written: list[bytes] = []
    mock_writer = MagicMock()
    mock_writer.write = lambda data: written.append(data)
    mock_writer.drain = AsyncMock()

    mock_loop = _make_mock_loop()

    return mock_reader, mock_writer, mock_loop, written


class TestStdioTransport:
    """Tests for the STDIO transport internals."""

    async def test_stdio_transport_processes_valid_request(self):
        """_run_stdio_transport reads a JSON-RPC line and writes a response."""
        server = _make_server()
        server._running = True

        req = (
            json.dumps(
                {"jsonrpc": "2.0", "id": "99", "method": "tools/list", "params": {}}
            ).encode()
            + b"\n"
        )

        mock_reader, mock_writer, mock_loop, written = _build_stdio_mocks([req], server)

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=MagicMock()),
            patch("asyncio.StreamWriter", return_value=mock_writer),
            patch(f"{_SERVER_MODULE}.asyncio.get_running_loop", return_value=mock_loop),
        ):
            try:
                await server._run_stdio_transport()
            except asyncio.CancelledError:
                pass

        assert server._request_count >= 1
        # A response should have been written
        assert len(written) >= 1
        payload = json.loads(written[0].decode())
        assert "tools" in payload["result"]

    async def test_stdio_transport_handles_json_decode_error(self):
        """_run_stdio_transport increments error_count and sends error response on bad JSON."""
        server = _make_server()
        server._running = True

        mock_reader, mock_writer, mock_loop, written = _build_stdio_mocks(
            [b"NOT_VALID_JSON\n"], server
        )

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=MagicMock()),
            patch("asyncio.StreamWriter", return_value=mock_writer),
            patch(f"{_SERVER_MODULE}.asyncio.get_running_loop", return_value=mock_loop),
        ):
            try:
                await server._run_stdio_transport()
            except asyncio.CancelledError:
                pass

        assert server._error_count >= 1
        assert len(written) >= 1
        error_payload = json.loads(written[0].decode())
        assert error_payload["error"]["code"] == -32700

    async def test_stdio_transport_handles_empty_line(self):
        """_run_stdio_transport skips empty lines (b'') without writing anything."""
        server = _make_server()
        server._running = True

        mock_reader, mock_writer, mock_loop, written = _build_stdio_mocks([b""], server)

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=MagicMock()),
            patch("asyncio.StreamWriter", return_value=mock_writer),
            patch(f"{_SERVER_MODULE}.asyncio.get_running_loop", return_value=mock_loop),
        ):
            try:
                await server._run_stdio_transport()
            except asyncio.CancelledError:
                pass

        assert len(written) == 0

    async def test_stdio_transport_handles_timeout(self):
        """_run_stdio_transport continues the loop on asyncio.TimeoutError (no error count)."""
        server = _make_server()
        server._running = True

        # No content lines — just 2 timeouts then CancelledError
        mock_reader, mock_writer, mock_loop, _written = _build_stdio_mocks(
            [], server, extra_timeout_errors=2
        )

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=MagicMock()),
            patch("asyncio.StreamWriter", return_value=mock_writer),
            patch(f"{_SERVER_MODULE}.asyncio.get_running_loop", return_value=mock_loop),
        ):
            try:
                await server._run_stdio_transport()
            except asyncio.CancelledError:
                pass

        assert server._error_count == 0

    async def test_stdio_transport_handles_operation_error(self):
        """_run_stdio_transport catches MCP_SERVER_OPERATION_ERRORS, increments error_count."""
        server = _make_server()
        server._running = True

        req = (
            json.dumps({"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}}).encode()
            + b"\n"
        )

        mock_reader, mock_writer, mock_loop, _written = _build_stdio_mocks([req], server)

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=MagicMock()),
            patch("asyncio.StreamWriter", return_value=mock_writer),
            patch(f"{_SERVER_MODULE}.asyncio.get_running_loop", return_value=mock_loop),
            patch.object(
                server._handler,
                "handle_request",
                new_callable=AsyncMock,
                side_effect=OSError("pipe broken"),
            ),
        ):
            try:
                await server._run_stdio_transport()
            except asyncio.CancelledError:
                pass

        assert server._error_count >= 1

    async def test_stdio_transport_none_response_not_written(self):
        """_run_stdio_transport does NOT write when handler returns None (notification)."""
        server = _make_server()
        server._running = True

        # A notification has id=None; handler returns None
        notif = (
            json.dumps(
                {"jsonrpc": "2.0", "id": None, "method": "initialized", "params": {}}
            ).encode()
            + b"\n"
        )

        mock_reader, mock_writer, mock_loop, written = _build_stdio_mocks([notif], server)

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=MagicMock()),
            patch("asyncio.StreamWriter", return_value=mock_writer),
            patch(f"{_SERVER_MODULE}.asyncio.get_running_loop", return_value=mock_loop),
        ):
            try:
                await server._run_stdio_transport()
            except asyncio.CancelledError:
                pass

        assert len(written) == 0

    async def test_stdio_transport_breaks_on_cancelled_error(self):
        """_run_stdio_transport exits the loop cleanly on CancelledError."""
        server = _make_server()
        server._running = True

        mock_reader, mock_writer, mock_loop, _written = _build_stdio_mocks([], server)

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=MagicMock()),
            patch("asyncio.StreamWriter", return_value=mock_writer),
            patch(f"{_SERVER_MODULE}.asyncio.get_running_loop", return_value=mock_loop),
        ):
            try:
                await server._run_stdio_transport()
            except asyncio.CancelledError:
                pass  # expected

        # Server should not have crashed
        assert server._request_count == 0


# ---------------------------------------------------------------------------
# _run_sse_transport
# ---------------------------------------------------------------------------


class TestSSETransport:
    async def test_sse_transport_falls_back_to_stdio(self):
        """_run_sse_transport delegates to _run_stdio_transport."""
        server = _make_server(TransportType.SSE)

        with patch.object(server, "_run_stdio_transport", new_callable=AsyncMock) as mock_stdio:
            await server._run_sse_transport()

        mock_stdio.assert_awaited_once()


# ---------------------------------------------------------------------------
# handle_request() error branch
# ---------------------------------------------------------------------------


class TestHandleRequestErrors:
    async def test_handle_request_catches_operation_errors(self):
        """handle_request() catches MCP_SERVER_OPERATION_ERRORS and returns error response."""
        server = _make_server()

        with patch.object(
            server._handler,
            "handle_request",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            response = await server.handle_request(_make_request("tools/list"))

        assert response is not None
        assert response.error is not None
        assert response.error.code == -32603
        assert "boom" in response.error.data["detail"]
        assert server._error_count == 1

    async def test_handle_request_increments_request_count_on_error(self):
        """handle_request() increments _request_count even when an error occurs."""
        server = _make_server()

        with patch.object(
            server._handler,
            "handle_request",
            new_callable=AsyncMock,
            side_effect=ValueError("bad value"),
        ):
            await server.handle_request(_make_request("tools/list"))

        assert server._request_count == 1

    async def test_handle_request_error_uses_request_id(self):
        """Error response preserves the original request id."""
        server = _make_server()

        with patch.object(
            server._handler,
            "handle_request",
            new_callable=AsyncMock,
            side_effect=TypeError("type error"),
        ):
            response = await server.handle_request(_make_request("tools/list", req_id="xyz-42"))

        assert response.id == "xyz-42"

    async def test_handle_request_all_operation_error_types(self):
        """Verify all MCP_SERVER_OPERATION_ERRORS are caught (not re-raised)."""
        from ..server import MCP_SERVER_OPERATION_ERRORS

        server = _make_server()

        for exc_class in MCP_SERVER_OPERATION_ERRORS:
            server._error_count = 0
            with patch.object(
                server._handler,
                "handle_request",
                new_callable=AsyncMock,
                side_effect=exc_class("test error"),
            ):
                response = await server.handle_request(_make_request("tools/list"))

            assert response is not None
            assert response.error is not None, f"Expected error response for {exc_class}"

    async def test_handle_request_success_path_no_error(self):
        """handle_request() returns response without errors for valid request."""
        server = _make_server()

        response = await server.handle_request(_make_request("tools/list"))
        assert response is not None
        assert response.error is None
        assert server._request_count == 1
        assert server._error_count == 0


# ---------------------------------------------------------------------------
# get_metrics() hasattr branches
# ---------------------------------------------------------------------------


class TestGetMetricsHasattr:
    def test_get_metrics_tools_with_get_metrics(self):
        """get_metrics() includes metrics from tools that have get_metrics()."""
        server = _make_server()
        metrics = server.get_metrics()
        assert isinstance(metrics["tools"], dict)

    def test_get_metrics_tools_without_get_metrics(self):
        """get_metrics() skips tools that lack get_metrics()."""
        server = _make_server()

        # Replace a real tool with a mock that has no get_metrics
        mock_tool = MagicMock(spec=[])  # spec=[] means no attributes
        server._tools["no_metrics_tool"] = mock_tool

        metrics = server.get_metrics()
        assert "no_metrics_tool" not in metrics["tools"]

    def test_get_metrics_resources_with_get_metrics(self):
        """get_metrics() includes metrics from resources that have get_metrics()."""
        server = _make_server()
        metrics = server.get_metrics()
        assert isinstance(metrics["resources"], dict)
        assert "audit_trail" in metrics["resources"]

    def test_get_metrics_resources_without_get_metrics(self):
        """get_metrics() skips resources that lack get_metrics()."""
        server = _make_server()

        mock_resource = MagicMock(spec=[])  # no get_metrics
        server._resources["no_metrics_resource"] = mock_resource

        metrics = server.get_metrics()
        assert "no_metrics_resource" not in metrics["resources"]

    def test_get_metrics_adapters_with_get_metrics(self):
        """get_metrics() includes metrics from adapters that have get_metrics()."""
        server = _make_server()
        metrics = server.get_metrics()
        assert isinstance(metrics["adapters"], dict)
        assert "agent_bus" in metrics["adapters"]

    def test_get_metrics_adapters_without_get_metrics(self):
        """get_metrics() skips adapters that lack get_metrics()."""
        server = _make_server()

        mock_adapter = MagicMock(spec=[])  # no get_metrics
        server._adapters["no_metrics_adapter"] = mock_adapter

        metrics = server.get_metrics()
        assert "no_metrics_adapter" not in metrics["adapters"]

    def test_get_metrics_server_section_keys(self):
        """get_metrics() server section contains expected keys."""
        server = _make_server()
        server._request_count = 5
        server._error_count = 2

        metrics = server.get_metrics()
        s = metrics["server"]
        assert s["name"] == server.config.server_name
        assert s["version"] == server.config.server_version
        assert s["running"] is False
        assert s["request_count"] == 5
        assert s["error_count"] == 2
        assert s["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_metrics_running_state_reflected(self):
        """get_metrics() reflects the current _running state."""
        server = _make_server()
        server._running = True

        metrics = server.get_metrics()
        assert metrics["server"]["running"] is True


# ---------------------------------------------------------------------------
# create_mcp_server() with all external services
# ---------------------------------------------------------------------------


class TestCreateMCPServerFactory:
    def test_create_with_all_services(self):
        """create_mcp_server() injects all three external services."""
        mock_agent_bus = MagicMock()
        mock_policy_client = MagicMock()
        mock_audit_client = MagicMock()

        server = create_mcp_server(
            agent_bus=mock_agent_bus,
            policy_client=mock_policy_client,
            audit_client=mock_audit_client,
        )

        assert server._adapters["agent_bus"].agent_bus is mock_agent_bus
        assert server._adapters["policy_client"].policy_client is mock_policy_client
        assert server._adapters["audit_client"].audit_client is mock_audit_client

    def test_create_with_custom_config_and_services(self):
        """create_mcp_server() applies custom config and injects services."""
        config = MCPConfig(server_name="my-server", strict_mode=False)
        mock_bus = MagicMock()

        server = create_mcp_server(config=config, agent_bus=mock_bus)

        assert server.config.server_name == "my-server"
        assert server._adapters["agent_bus"].agent_bus is mock_bus

    def test_create_with_no_services(self):
        """create_mcp_server() works fine with no services (None defaults)."""
        server = create_mcp_server()

        assert server._adapters["agent_bus"].agent_bus is None
        assert server._adapters["policy_client"].policy_client is None
        assert server._adapters["audit_client"].audit_client is None

    def test_create_with_agent_bus_only(self):
        """create_mcp_server() sets only agent_bus when others are None."""
        mock_bus = MagicMock()
        server = create_mcp_server(agent_bus=mock_bus)

        assert server._adapters["agent_bus"].agent_bus is mock_bus
        assert server._adapters["policy_client"].policy_client is None
        assert server._adapters["audit_client"].audit_client is None


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


class TestMain:
    async def test_main_starts_and_stops_server(self):
        """main() creates a server, calls start() then stop() in a finally block."""
        with patch(f"{_SERVER_MODULE}.create_mcp_server") as mock_factory:
            mock_server = AsyncMock()
            mock_factory.return_value = mock_server

            await main()

        mock_server.start.assert_awaited_once()
        mock_server.stop.assert_awaited_once()

    async def test_main_calls_stop_on_keyboard_interrupt(self):
        """main() calls stop() even when start() raises KeyboardInterrupt."""
        with patch(f"{_SERVER_MODULE}.create_mcp_server") as mock_factory:
            mock_server = AsyncMock()
            mock_server.start.side_effect = KeyboardInterrupt()
            mock_factory.return_value = mock_server

            await main()

        mock_server.stop.assert_awaited_once()

    async def test_main_configures_logging(self):
        """main() sets up basicConfig logging before starting the server."""
        with patch(f"{_SERVER_MODULE}.create_mcp_server") as mock_factory:
            mock_server = AsyncMock()
            mock_factory.return_value = mock_server

            with patch("logging.basicConfig") as mock_logging:
                await main()

            mock_logging.assert_called_once()

    async def test_main_uses_default_config(self):
        """main() passes a default MCPConfig to create_mcp_server."""
        with patch(f"{_SERVER_MODULE}.create_mcp_server") as mock_factory:
            mock_server = AsyncMock()
            mock_factory.return_value = mock_server

            await main()

        # create_mcp_server should have been called with a config kwarg
        call_kwargs = mock_factory.call_args.kwargs
        assert "config" in call_kwargs
        assert isinstance(call_kwargs["config"], MCPConfig)


# ---------------------------------------------------------------------------
# Branch coverage: _handler is None (line 204->207)
# ---------------------------------------------------------------------------


class TestHandlerNoneBranch:
    async def test_start_with_no_handler_skips_lock(self):
        """start() skips lock_registration() when _handler is None."""
        server = _make_server()
        server._handler = None  # Force the False branch on line 204

        with patch.object(server, "_run_stdio_transport", new_callable=AsyncMock):
            await server.start()

        # No error; _running should be True after start
        assert server._running is True


# ---------------------------------------------------------------------------
# Branch coverage: shutdown_event exits while loop (line 276->exit)
# ---------------------------------------------------------------------------


class TestShutdownEventExitsLoop:
    async def test_stdio_transport_exits_on_shutdown_event(self):
        """
        _run_stdio_transport exits when _shutdown_event is set,
        even if _running is still True.
        """
        server = _make_server()
        server._running = True

        call_count = 0

        async def fake_readline():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Set shutdown event — loop should exit at top of next iteration
                server._shutdown_event.set()
                raise TimeoutError()
            # Should not reach here
            raise asyncio.CancelledError()

        mock_reader = MagicMock()
        mock_reader.readline = fake_readline
        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_loop = _make_mock_loop()

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=MagicMock()),
            patch("asyncio.StreamWriter", return_value=mock_writer),
            patch(f"{_SERVER_MODULE}.asyncio.get_running_loop", return_value=mock_loop),
        ):
            # Should return cleanly (not raise)
            await server._run_stdio_transport()

        assert call_count >= 1


# ---------------------------------------------------------------------------
# _register_handlers
# ---------------------------------------------------------------------------


class TestRegisterHandlers:
    def test_register_handlers_is_noop(self):
        """_register_handlers() is a pass-through — no additional handlers added."""
        server = _make_server()
        # Just ensure it can be called without error
        server._register_handlers()


# ---------------------------------------------------------------------------
# Protocol version constant
# ---------------------------------------------------------------------------


class TestProtocolVersion:
    def test_protocol_version_constant(self):
        """MCPServer exposes PROTOCOL_VERSION = '2024-11-05'."""
        assert MCPServer.PROTOCOL_VERSION == "2024-11-05"


# ---------------------------------------------------------------------------
# Constitutional compliance checks within server
# ---------------------------------------------------------------------------


class TestServerConstitutionalHash:
    def test_constitutional_hash_class_attribute(self):
        """CONSTITUTIONAL_HASH is accessible as class attribute."""
        assert MCPServer.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_metrics(self):
        """get_metrics() embeds the constitutional hash."""
        server = _make_server()
        metrics = server.get_metrics()
        assert metrics["server"]["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_constitutional_hash_matches_expected(self):
        """CONSTITUTIONAL_HASH value is the canonical governance hash."""
        assert MCPServer.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH  # pragma: allowlist secret
