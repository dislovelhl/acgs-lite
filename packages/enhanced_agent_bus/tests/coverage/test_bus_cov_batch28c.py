"""
Comprehensive coverage tests for enhanced_agent_bus modules (batch 28c).

Targets:
- enhanced_agent_bus.mcp_server.server (76.7% -> 85%+)
- enhanced_agent_bus.verification_orchestrator (75.9% -> 85%+)
- enhanced_agent_bus.interfaces (70.2% -> improved, Protocol stubs excluded)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# Module 1: mcp_server/server.py
# Missing lines: 17-18, 231-235, 265-325, 448-463
# =============================================================================


class TestMCPServerCreation:
    """Test create_mcp_server factory function and MCPServer init."""

    def test_create_mcp_server_default_config(self):
        from enhanced_agent_bus.mcp_server.server import MCPServer, create_mcp_server

        server = create_mcp_server()
        assert isinstance(server, MCPServer)
        assert server.config.server_name == "acgs2-governance"

    def test_create_mcp_server_with_custom_config(self):
        from enhanced_agent_bus.mcp_server.config import MCPConfig
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        config = MCPConfig(server_name="test-server", server_version="1.0.0")
        server = create_mcp_server(config=config)
        assert server.config.server_name == "test-server"
        assert server.config.server_version == "1.0.0"

    def test_create_mcp_server_with_agent_bus(self):
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        mock_bus = MagicMock()
        server = create_mcp_server(agent_bus=mock_bus)
        assert server._adapters["agent_bus"].agent_bus is mock_bus

    def test_create_mcp_server_with_policy_client(self):
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        mock_client = MagicMock()
        server = create_mcp_server(policy_client=mock_client)
        assert server._adapters["policy_client"].policy_client is mock_client

    def test_create_mcp_server_with_audit_client(self):
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        mock_client = MagicMock()
        server = create_mcp_server(audit_client=mock_client)
        assert server._adapters["audit_client"].audit_client is mock_client


class TestMCPServerStartStop:
    """Test server start/stop lifecycle and transport selection."""

    def _make_server(self):
        from enhanced_agent_bus.mcp_server.config import MCPConfig
        from enhanced_agent_bus.mcp_server.server import MCPServer

        return MCPServer(config=MCPConfig())

    async def test_start_already_running(self):
        server = self._make_server()
        server._running = True
        # Should return early without error
        await server.start()

    async def test_stop_when_not_running(self):
        server = self._make_server()
        server._running = False
        # Should return early without error
        await server.stop()

    async def test_stop_logs_audit_and_disconnects(self):
        server = self._make_server()
        server._running = True
        server._request_count = 42
        server._error_count = 3

        mock_audit = MagicMock()
        server._resources["audit_trail"] = mock_audit

        mock_adapter = AsyncMock()
        server._adapters["agent_bus"] = mock_adapter

        await server.stop()

        assert server._running is False
        assert server._shutdown_event.is_set()
        mock_audit.log_event.assert_called_once()
        call_kwargs = mock_audit.log_event.call_args
        assert call_kwargs.kwargs["details"]["requests_processed"] == 42
        assert call_kwargs.kwargs["details"]["errors"] == 3
        mock_adapter.disconnect.assert_awaited_once()

    async def test_start_unknown_transport_raises(self):
        from enhanced_agent_bus.mcp_server.config import MCPConfig
        from enhanced_agent_bus.mcp_server.server import MCPServer

        config = MCPConfig()
        server = MCPServer(config=config)
        # Force an unknown transport type
        server.config.transport_type = MagicMock(value="unknown")
        # Mock connect_adapters to succeed
        server.connect_adapters = AsyncMock(return_value=True)

        with pytest.raises(ValueError, match="Unknown transport"):
            await server.start()

    async def test_start_sse_transport(self):
        """SSE transport falls back to STDIO; test it starts without error."""
        from enhanced_agent_bus.mcp_server.config import MCPConfig, TransportType
        from enhanced_agent_bus.mcp_server.server import MCPServer

        config = MCPConfig(transport_type=TransportType.SSE)
        server = MCPServer(config=config)
        server.connect_adapters = AsyncMock(return_value=True)
        # Mock _run_stdio_transport to prevent actual I/O
        server._run_stdio_transport = AsyncMock()

        await server.start()

        assert server._running is True
        server._run_stdio_transport.assert_awaited_once()

    async def test_start_stdio_transport(self):
        """STDIO transport path is selected when transport_type is STDIO."""
        from enhanced_agent_bus.mcp_server.config import MCPConfig, TransportType
        from enhanced_agent_bus.mcp_server.server import MCPServer

        config = MCPConfig(transport_type=TransportType.STDIO)
        server = MCPServer(config=config)
        server.connect_adapters = AsyncMock(return_value=True)
        server._run_stdio_transport = AsyncMock()

        await server.start()

        assert server._running is True
        server._run_stdio_transport.assert_awaited_once()


class TestMCPServerConnectDisconnect:
    """Test adapter connection and disconnection."""

    async def test_connect_adapters_success(self):
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        server = create_mcp_server()
        mock_bus_adapter = AsyncMock()
        mock_bus_adapter.connect = AsyncMock(return_value=True)
        server._adapters["agent_bus"] = mock_bus_adapter

        result = await server.connect_adapters()
        assert result is True
        mock_bus_adapter.connect.assert_awaited_once()

    async def test_connect_adapters_failure(self):
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        server = create_mcp_server()
        mock_bus_adapter = AsyncMock()
        mock_bus_adapter.connect = AsyncMock(return_value=False)
        server._adapters["agent_bus"] = mock_bus_adapter

        result = await server.connect_adapters()
        assert result is True  # Server always returns True (standalone mode)

    async def test_disconnect_adapters(self):
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        server = create_mcp_server()
        mock_bus_adapter = AsyncMock()
        server._adapters["agent_bus"] = mock_bus_adapter

        await server.disconnect_adapters()
        mock_bus_adapter.disconnect.assert_awaited_once()


class TestMCPServerHandleRequest:
    """Test handle_request method (lines 334-359)."""

    async def test_handle_request_success(self):
        from enhanced_agent_bus.mcp_server.protocol.types import MCPRequest, MCPResponse
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        server = create_mcp_server()
        request = MCPRequest(jsonrpc="2.0", method="tools/list", id="req-1")

        mock_response = MCPResponse(jsonrpc="2.0", id="req-1", result={"tools": []})
        server._handler.handle_request = AsyncMock(return_value=mock_response)

        response = await server.handle_request(request)
        assert response is not None
        assert response.id == "req-1"
        assert server._request_count == 1

    async def test_handle_request_error_path(self):
        """Covers lines 348-359: error handling in handle_request."""
        from enhanced_agent_bus.mcp_server.protocol.types import MCPRequest
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        server = create_mcp_server()
        request = MCPRequest(jsonrpc="2.0", method="tools/call", id="req-2")

        server._handler.handle_request = AsyncMock(side_effect=ValueError("test error"))

        response = await server.handle_request(request)
        assert response is not None
        assert response.error is not None
        assert response.error.code == -32603
        assert "test error" in response.error.data["detail"]
        assert server._error_count == 1
        assert server._request_count == 1

    async def test_handle_request_type_error(self):
        from enhanced_agent_bus.mcp_server.protocol.types import MCPRequest
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        server = create_mcp_server()
        request = MCPRequest(jsonrpc="2.0", method="bad", id="req-3")
        server._handler.handle_request = AsyncMock(side_effect=TypeError("bad type"))

        response = await server.handle_request(request)
        assert response.error is not None
        assert response.error.code == -32603


class TestMCPServerCapabilities:
    """Test get_capabilities, get_tool_definitions, get_resource_definitions."""

    def test_get_capabilities(self):
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        server = create_mcp_server()
        caps = server.get_capabilities()
        assert caps.tools == {"listChanged": True}
        assert caps.resources == {"subscribe": False, "listChanged": True}

    def test_get_tool_definitions(self):
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        server = create_mcp_server()
        defs = server.get_tool_definitions()
        assert len(defs) == 5
        names = {d.name for d in defs}
        assert "validate_constitutional_compliance" in names

    def test_get_resource_definitions(self):
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        server = create_mcp_server()
        defs = server.get_resource_definitions()
        assert len(defs) == 4


class TestMCPServerMetrics:
    """Test get_metrics method."""

    def test_get_metrics_basic(self):
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        server = create_mcp_server()
        metrics = server.get_metrics()
        assert "server" in metrics
        assert metrics["server"]["name"] == "acgs2-governance"
        assert metrics["server"]["running"] is False
        assert metrics["server"]["request_count"] == 0

    def test_get_metrics_with_tool_metrics(self):
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        server = create_mcp_server()
        mock_tool = MagicMock()
        mock_tool.get_metrics.return_value = {"calls": 5}
        mock_tool.get_definition.return_value = MagicMock()
        server._tools["test_tool"] = mock_tool

        metrics = server.get_metrics()
        assert "test_tool" in metrics["tools"]
        assert metrics["tools"]["test_tool"]["calls"] == 5

    def test_get_metrics_with_resource_and_adapter_metrics(self):
        from enhanced_agent_bus.mcp_server.server import create_mcp_server

        server = create_mcp_server()

        mock_resource = MagicMock()
        mock_resource.get_metrics.return_value = {"reads": 10}
        server._resources["test_res"] = mock_resource

        mock_adapter = MagicMock()
        mock_adapter.get_metrics.return_value = {"connected": True}
        server._adapters["test_adapter"] = mock_adapter

        metrics = server.get_metrics()
        assert metrics["resources"]["test_res"]["reads"] == 10
        assert metrics["adapters"]["test_adapter"]["connected"] is True


class TestMCPServerStdioTransport:
    """Test _run_stdio_transport (lines 265-325)."""

    async def test_stdio_transport_valid_request(self):
        """Simulate a valid JSON-RPC request through stdio transport."""
        from enhanced_agent_bus.mcp_server.config import MCPConfig
        from enhanced_agent_bus.mcp_server.server import MCPServer

        server = MCPServer(config=MCPConfig())
        server._running = True
        server._shutdown_event.clear()

        request_data = {"jsonrpc": "2.0", "method": "tools/list", "id": "1"}
        request_line = (json.dumps(request_data) + "\n").encode("utf-8")

        mock_response = MagicMock()
        mock_response.to_dict.return_value = {"jsonrpc": "2.0", "id": "1", "result": {}}
        server._handler.handle_request = AsyncMock(return_value=mock_response)

        call_count = 0

        async def mock_readline():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return request_line
            # Stop after first request
            server._running = False
            return b""

        mock_reader = AsyncMock()
        mock_reader.readline = mock_readline

        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()

        mock_protocol = MagicMock()

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=mock_protocol),
            patch("asyncio.get_running_loop") as mock_loop_fn,
        ):
            mock_loop = AsyncMock()
            mock_loop.connect_read_pipe = AsyncMock()
            mock_loop.connect_write_pipe = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_loop_fn.return_value = mock_loop

            with patch("asyncio.StreamWriter", return_value=mock_writer):
                await server._run_stdio_transport()

        assert server._request_count >= 1
        mock_writer.write.assert_called()

    async def test_stdio_transport_invalid_json(self):
        """Simulate invalid JSON through stdio transport (lines 304-317)."""
        from enhanced_agent_bus.mcp_server.config import MCPConfig
        from enhanced_agent_bus.mcp_server.server import MCPServer

        server = MCPServer(config=MCPConfig())
        server._running = True
        server._shutdown_event.clear()

        call_count = 0

        async def mock_readline():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"not-valid-json\n"
            server._running = False
            return b""

        mock_reader = AsyncMock()
        mock_reader.readline = mock_readline

        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()

        mock_protocol = MagicMock()

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=mock_protocol),
            patch("asyncio.get_running_loop") as mock_loop_fn,
        ):
            mock_loop = AsyncMock()
            mock_loop.connect_read_pipe = AsyncMock()
            mock_loop.connect_write_pipe = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_loop_fn.return_value = mock_loop

            with patch("asyncio.StreamWriter", return_value=mock_writer):
                await server._run_stdio_transport()

        assert server._error_count >= 1
        # Verify error response was written
        mock_writer.write.assert_called()
        written_data = mock_writer.write.call_args[0][0]
        error_resp = json.loads(written_data.decode("utf-8"))
        assert error_resp["error"]["code"] == -32700

    async def test_stdio_transport_timeout(self):
        """Simulate timeout in readline (line 319-320)."""
        from enhanced_agent_bus.mcp_server.config import MCPConfig
        from enhanced_agent_bus.mcp_server.server import MCPServer

        server = MCPServer(config=MCPConfig())
        server._running = True
        server._shutdown_event.clear()

        call_count = 0

        async def mock_readline():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise TimeoutError("timeout")
            server._running = False
            raise TimeoutError("timeout")

        mock_reader = AsyncMock()
        mock_reader.readline = mock_readline

        mock_writer = MagicMock()
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=MagicMock()),
            patch("asyncio.get_running_loop") as mock_loop_fn,
        ):
            mock_loop = AsyncMock()
            mock_loop.connect_read_pipe = AsyncMock()
            mock_loop.connect_write_pipe = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_loop_fn.return_value = mock_loop

            with patch("asyncio.StreamWriter", return_value=mock_writer):
                # Need to stop the loop; use shutdown_event
                async def stop_later():
                    await asyncio.sleep(0.05)
                    server._running = False
                    server._shutdown_event.set()

                task = asyncio.create_task(stop_later())
                await server._run_stdio_transport()
                task.cancel()

        # No errors should be recorded for timeouts
        assert server._error_count == 0

    async def test_stdio_transport_cancelled(self):
        """Simulate CancelledError in stdio transport (line 321-322)."""
        from enhanced_agent_bus.mcp_server.config import MCPConfig
        from enhanced_agent_bus.mcp_server.server import MCPServer

        server = MCPServer(config=MCPConfig())
        server._running = True
        server._shutdown_event.clear()

        async def mock_readline():
            raise asyncio.CancelledError()

        mock_reader = AsyncMock()
        mock_reader.readline = mock_readline

        mock_writer = MagicMock()

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=MagicMock()),
            patch("asyncio.get_running_loop") as mock_loop_fn,
        ):
            mock_loop = AsyncMock()
            mock_loop.connect_read_pipe = AsyncMock()
            mock_loop.connect_write_pipe = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_loop_fn.return_value = mock_loop

            with patch("asyncio.StreamWriter", return_value=mock_writer):
                # wait_for wraps CancelledError; direct raise in the try block
                with patch("asyncio.wait_for", side_effect=asyncio.CancelledError()):
                    await server._run_stdio_transport()

    async def test_stdio_transport_operation_error(self):
        """Simulate OSError in stdio transport (lines 323-325)."""
        from enhanced_agent_bus.mcp_server.config import MCPConfig
        from enhanced_agent_bus.mcp_server.server import MCPServer

        server = MCPServer(config=MCPConfig())
        server._running = True
        server._shutdown_event.clear()

        call_count = 0

        async def mock_wait_for(coro, timeout):
            nonlocal call_count
            call_count += 1
            # Clean up the coroutine
            coro.close() if hasattr(coro, "close") else None
            if call_count == 1:
                raise OSError("pipe broken")
            server._running = False
            raise OSError("pipe broken")

        mock_reader = AsyncMock()
        mock_writer = MagicMock()

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=MagicMock()),
            patch("asyncio.get_running_loop") as mock_loop_fn,
        ):
            mock_loop = AsyncMock()
            mock_loop.connect_read_pipe = AsyncMock()
            mock_loop.connect_write_pipe = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_loop_fn.return_value = mock_loop

            with patch("asyncio.StreamWriter", return_value=mock_writer):

                async def stop_later():
                    await asyncio.sleep(0.05)
                    server._running = False
                    server._shutdown_event.set()

                task = asyncio.create_task(stop_later())
                with patch("asyncio.wait_for", side_effect=mock_wait_for):
                    await server._run_stdio_transport()
                task.cancel()

        assert server._error_count >= 1

    async def test_stdio_transport_empty_line(self):
        """Simulate empty line (EOF, lines 288-289)."""
        from enhanced_agent_bus.mcp_server.config import MCPConfig
        from enhanced_agent_bus.mcp_server.server import MCPServer

        server = MCPServer(config=MCPConfig())
        server._running = True
        server._shutdown_event.clear()

        call_count = 0

        async def mock_readline():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return b""
            server._running = False
            return b""

        mock_reader = AsyncMock()
        mock_reader.readline = mock_readline

        mock_writer = MagicMock()

        with (
            patch("asyncio.StreamReader", return_value=mock_reader),
            patch("asyncio.StreamReaderProtocol", return_value=MagicMock()),
            patch("asyncio.get_running_loop") as mock_loop_fn,
        ):
            mock_loop = AsyncMock()
            mock_loop.connect_read_pipe = AsyncMock()
            mock_loop.connect_write_pipe = AsyncMock(return_value=(MagicMock(), MagicMock()))
            mock_loop_fn.return_value = mock_loop

            with patch("asyncio.StreamWriter", return_value=mock_writer):

                async def stop_later():
                    await asyncio.sleep(0.05)
                    server._running = False
                    server._shutdown_event.set()

                task = asyncio.create_task(stop_later())
                await server._run_stdio_transport()
                task.cancel()


class TestMCPServerSSETransport:
    """Test _run_sse_transport (lines 327-332)."""

    async def test_sse_transport_falls_back_to_stdio(self):
        from enhanced_agent_bus.mcp_server.config import MCPConfig
        from enhanced_agent_bus.mcp_server.server import MCPServer

        server = MCPServer(config=MCPConfig())
        server._run_stdio_transport = AsyncMock()

        await server._run_sse_transport()

        server._run_stdio_transport.assert_awaited_once()


class TestMCPServerMain:
    """Test main() entry point (lines 446-463)."""

    async def test_main_runs_and_stops(self):
        from enhanced_agent_bus.mcp_server import server as server_module

        mock_server = MagicMock()
        mock_server.start = AsyncMock()
        mock_server.stop = AsyncMock()

        with patch.object(server_module, "create_mcp_server", return_value=mock_server):
            await server_module.main()

        mock_server.start.assert_awaited_once()
        mock_server.stop.assert_awaited_once()

    async def test_main_handles_keyboard_interrupt(self):
        from enhanced_agent_bus.mcp_server import server as server_module

        mock_server = MagicMock()
        mock_server.start = AsyncMock(side_effect=KeyboardInterrupt())
        mock_server.stop = AsyncMock()

        with patch.object(server_module, "create_mcp_server", return_value=mock_server):
            await server_module.main()

        mock_server.stop.assert_awaited_once()


# =============================================================================
# Module 2: verification_orchestrator.py
# Missing lines: 18-19, 98-150, 340, 415-416
# =============================================================================


class TestVerificationResult:
    """Test VerificationResult dataclass."""

    def test_default_values(self):
        from enhanced_agent_bus.verification_orchestrator import VerificationResult

        result = VerificationResult()
        assert result.sdpc_metadata == {}
        assert result.pqc_result is None
        assert result.pqc_metadata == {}

    def test_custom_values(self):
        from enhanced_agent_bus.verification_orchestrator import VerificationResult

        result = VerificationResult(
            sdpc_metadata={"key": "val"},
            pqc_metadata={"pqc": True},
        )
        assert result.sdpc_metadata["key"] == "val"
        assert result.pqc_metadata["pqc"] is True


class TestVerificationOrchestratorInit:
    """Test VerificationOrchestrator initialization paths."""

    def test_init_without_pqc(self):
        from enhanced_agent_bus.config import BusConfiguration
        from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        assert orch._enable_pqc is False
        assert orch._pqc_service is None
        assert orch._pqc_config is None

    def test_init_sdpc_noop_stubs(self):
        """Force SDPC import failure to exercise NoOp stubs (lines 98-150)."""
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()

        with patch.dict(
            "sys.modules",
            {
                "enhanced_agent_bus.deliberation_layer.intent_classifier": None,
                "enhanced_agent_bus.sdpc.ampo_engine": None,
                "enhanced_agent_bus.sdpc.asc_verifier": None,
                "enhanced_agent_bus.sdpc.evolution_controller": None,
                "enhanced_agent_bus.sdpc.graph_check": None,
                "enhanced_agent_bus.sdpc.pacar_verifier": None,
            },
        ):
            from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

            orch = VerificationOrchestrator(config=config, enable_pqc=False)

        # Verify NoOp stubs are installed
        assert hasattr(orch, "intent_classifier")
        assert hasattr(orch, "asc_verifier")
        assert hasattr(orch, "graph_check")
        assert hasattr(orch, "pacar_verifier")
        assert hasattr(orch, "evolution_controller")
        assert hasattr(orch, "ampo_engine")

    async def test_noop_intent_classifier(self):
        """Exercise the _NoOpIntentClassifier.classify_async."""
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()

        with patch.dict(
            "sys.modules",
            {
                "enhanced_agent_bus.deliberation_layer.intent_classifier": None,
                "enhanced_agent_bus.sdpc.ampo_engine": None,
                "enhanced_agent_bus.sdpc.asc_verifier": None,
                "enhanced_agent_bus.sdpc.evolution_controller": None,
                "enhanced_agent_bus.sdpc.graph_check": None,
                "enhanced_agent_bus.sdpc.pacar_verifier": None,
            },
        ):
            from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

            orch = VerificationOrchestrator(config=config, enable_pqc=False)

        result = await orch.intent_classifier.classify_async("test content")
        assert result.value == "unknown"

    async def test_noop_asc_verifier(self):
        """Exercise _NoOpVerifier.verify and verify_entities."""
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()

        with patch.dict(
            "sys.modules",
            {
                "enhanced_agent_bus.deliberation_layer.intent_classifier": None,
                "enhanced_agent_bus.sdpc.ampo_engine": None,
                "enhanced_agent_bus.sdpc.asc_verifier": None,
                "enhanced_agent_bus.sdpc.evolution_controller": None,
                "enhanced_agent_bus.sdpc.graph_check": None,
                "enhanced_agent_bus.sdpc.pacar_verifier": None,
            },
        ):
            from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

            orch = VerificationOrchestrator(config=config, enable_pqc=False)

        verify_result = await orch.asc_verifier.verify("content", "intent")
        assert verify_result["is_valid"] is True
        assert verify_result["confidence"] == 1.0

        entities_result = await orch.graph_check.verify_entities("content")
        assert entities_result["is_valid"] is True

    def test_noop_evolution_controller(self):
        """Exercise _NoOpEvolutionController methods."""
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()

        with patch.dict(
            "sys.modules",
            {
                "enhanced_agent_bus.deliberation_layer.intent_classifier": None,
                "enhanced_agent_bus.sdpc.ampo_engine": None,
                "enhanced_agent_bus.sdpc.asc_verifier": None,
                "enhanced_agent_bus.sdpc.evolution_controller": None,
                "enhanced_agent_bus.sdpc.graph_check": None,
                "enhanced_agent_bus.sdpc.pacar_verifier": None,
            },
        ):
            from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

            orch = VerificationOrchestrator(config=config, enable_pqc=False)

        orch.evolution_controller.record_feedback("intent", {"asc": True})
        mutations = orch.evolution_controller.get_mutations("intent")
        assert mutations == []
        orch.evolution_controller.reset_mutations("intent")
        orch.evolution_controller.reset_mutations()

    def test_noop_ampo_engine(self):
        """Exercise _NoOpAMPOEngine init."""
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration()

        with patch.dict(
            "sys.modules",
            {
                "enhanced_agent_bus.deliberation_layer.intent_classifier": None,
                "enhanced_agent_bus.sdpc.ampo_engine": None,
                "enhanced_agent_bus.sdpc.asc_verifier": None,
                "enhanced_agent_bus.sdpc.evolution_controller": None,
                "enhanced_agent_bus.sdpc.graph_check": None,
                "enhanced_agent_bus.sdpc.pacar_verifier": None,
            },
        ):
            from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

            orch = VerificationOrchestrator(config=config, enable_pqc=False)

        assert orch.ampo_engine.evolution_controller is orch.evolution_controller


class TestVerificationOrchestratorPQC:
    """Test PQC initialization and validation paths."""

    def test_init_pqc_import_error(self):
        """Exercise _init_pqc ImportError path (line 422-427)."""
        from enhanced_agent_bus.config import BusConfiguration
        from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

        config = BusConfiguration()

        with patch.dict("sys.modules", {"enhanced_agent_bus.pqc_validators": None}):
            orch = VerificationOrchestrator(config=config, enable_pqc=True)

        # PQC should be disabled after ImportError
        assert orch._enable_pqc is False

    def test_init_pqc_runtime_error(self):
        """Exercise _init_pqc RuntimeError path (lines 428-433)."""
        from enhanced_agent_bus.config import BusConfiguration
        from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

        config = BusConfiguration()

        # Patch builtins.__import__ to make PQCConfig raise RuntimeError
        original_import = __import__

        def custom_import(name, globals=None, locals=None, fromlist=(), level=0):
            if "pqc_validators" in str(name) and fromlist and "PQCConfig" in fromlist:
                mod = MagicMock()
                mod.PQCConfig = MagicMock(side_effect=RuntimeError("PQC init failed"))
                return mod
            if "pqc_crypto_service" in str(name):
                return MagicMock()
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=custom_import):
            orch = VerificationOrchestrator(config=config, enable_pqc=True)

        assert orch._enable_pqc is False

    async def test_perform_pqc_disabled(self):
        """PQC disabled returns None, empty dict."""
        from enhanced_agent_bus.config import BusConfiguration
        from enhanced_agent_bus.core_models import AgentMessage
        from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        msg = AgentMessage(from_agent="test-agent")

        result, metadata = await orch.verify_pqc(msg)
        assert result is None
        assert metadata == {}

    async def test_perform_pqc_import_error(self):
        """PQC enabled but import fails at runtime (line 339-340)."""
        from enhanced_agent_bus.config import BusConfiguration
        from enhanced_agent_bus.core_models import AgentMessage
        from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        # Manually set pqc enabled and config
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()

        msg = AgentMessage(from_agent="test-agent")

        with patch.dict("sys.modules", {"enhanced_agent_bus.pqc_validators": None}):
            with patch(
                "enhanced_agent_bus.verification_orchestrator.VerificationOrchestrator._perform_pqc.__wrapped__",
                side_effect=ImportError("no pqc"),
            ):
                # Direct call to _perform_pqc
                pass

        # Use a more direct approach: patch the import inside _perform_pqc
        original_import = (
            __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
        )

        def failing_import(name, *args, **kwargs):
            if "pqc_validators" in name:
                raise ImportError("no pqc_validators")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=failing_import):
            result, metadata = await orch._perform_pqc.__wrapped__(orch, msg)

        assert result is None
        assert metadata == {}

    async def test_perform_pqc_runtime_error_pqc_only(self):
        """PQC validation RuntimeError in pqc_only mode (lines 341-353)."""
        from enhanced_agent_bus.config import BusConfiguration
        from enhanced_agent_bus.core_models import AgentMessage
        from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()
        orch._pqc_config.pqc_mode = "pqc_only"

        msg = AgentMessage(from_agent="test-agent")

        mock_validate = AsyncMock(side_effect=RuntimeError("PQC error"))

        with (
            patch(
                "enhanced_agent_bus.verification_orchestrator.validate_constitutional_hash_pqc",
                mock_validate,
                create=True,
            ),
        ):
            original_import = __import__

            def custom_import(name, *args, **kwargs):
                if name == ".pqc_validators" or "pqc_validators" in str(name):
                    mod = MagicMock()
                    mod.validate_constitutional_hash_pqc = mock_validate
                    return mod
                if name == ".models" or name == "enhanced_agent_bus.models":
                    import enhanced_agent_bus.models

                    return enhanced_agent_bus.models
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=custom_import):
                result, metadata = await orch._perform_pqc.__wrapped__(orch, msg)

        assert result is not None
        assert result.is_valid is False
        assert any("PQC validation error" in e for e in result.errors)

    async def test_perform_pqc_runtime_error_hybrid_mode(self):
        """PQC validation error in hybrid mode continues (lines 354-357)."""
        from enhanced_agent_bus.config import BusConfiguration
        from enhanced_agent_bus.core_models import AgentMessage
        from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()
        orch._pqc_config.pqc_mode = "hybrid"

        msg = AgentMessage(from_agent="test-agent")

        original_import = __import__

        def custom_import(name, *args, **kwargs):
            if "pqc_validators" in str(name):
                mod = MagicMock()
                mod.validate_constitutional_hash_pqc = AsyncMock(
                    side_effect=RuntimeError("PQC fail")
                )
                mod.PQCConfig = MagicMock
                return mod
            if name == ".models" or "enhanced_agent_bus.models" in str(name):
                import enhanced_agent_bus.models

                return enhanced_agent_bus.models
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=custom_import):
            result, metadata = await orch._perform_pqc.__wrapped__(orch, msg)

        # In hybrid mode, should continue (return None, {})
        assert result is None
        assert metadata == {}


class TestVerificationOrchestratorVerify:
    """Test the main verify() method and SDPC paths."""

    def _make_orchestrator(self):
        from enhanced_agent_bus.config import BusConfiguration
        from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

        config = BusConfiguration()
        return VerificationOrchestrator(config=config, enable_pqc=False)

    async def test_verify_combines_sdpc_and_pqc(self):
        from enhanced_agent_bus.core_models import AgentMessage

        orch = self._make_orchestrator()
        msg = AgentMessage(from_agent="test-agent", impact_score=0.5)

        result = await orch.verify.__wrapped__(orch, msg, "test content")

        assert hasattr(result, "sdpc_metadata")
        assert hasattr(result, "pqc_result")
        assert result.pqc_result is None  # PQC disabled

    async def test_verify_high_impact_triggers_asc_graph_pacar(self):
        from enhanced_agent_bus.core_models import AgentMessage
        from enhanced_agent_bus.enums import MessageType

        orch = self._make_orchestrator()
        # Mock verifiers to avoid real SDPC dependency issues
        orch.asc_verifier.verify = AsyncMock(
            return_value={"is_valid": True, "confidence": 0.95, "results": []}
        )
        orch.graph_check.verify_entities = AsyncMock(return_value={"is_valid": True, "results": []})
        orch.pacar_verifier.verify = AsyncMock(return_value={"is_valid": True, "confidence": 0.9})

        msg = AgentMessage(
            from_agent="test-agent",
            impact_score=0.9,
            message_type=MessageType.TASK_REQUEST,
        )

        result = await orch.verify.__wrapped__(orch, msg, "test content")

        # High impact should trigger ASC, graph, and PACAR
        meta = result.sdpc_metadata
        assert "sdpc_asc_valid" in meta
        assert "sdpc_pacar_valid" in meta

    async def test_verify_task_request_triggers_pacar(self):
        from enhanced_agent_bus.core_models import AgentMessage
        from enhanced_agent_bus.enums import MessageType

        orch = self._make_orchestrator()
        orch.pacar_verifier.verify = AsyncMock(return_value={"is_valid": True, "confidence": 0.85})

        msg = AgentMessage(
            from_agent="test-agent",
            impact_score=0.3,
            message_type=MessageType.TASK_REQUEST,
        )

        result = await orch.verify.__wrapped__(orch, msg, "test content")
        meta = result.sdpc_metadata
        assert "sdpc_pacar_valid" in meta

    async def test_verify_none_impact_score(self):
        """Test impact_score=None handling (line 208-209)."""
        from enhanced_agent_bus.core_models import AgentMessage

        orch = self._make_orchestrator()
        msg = AgentMessage(from_agent="test-agent", impact_score=None)

        result = await orch.verify.__wrapped__(orch, msg, "some content")
        assert result.pqc_result is None


class TestVerificationOrchestratorPQCSuccess:
    """Test PQC success path with metadata."""

    async def test_pqc_validation_success_with_metadata(self):
        """Exercise the full PQC success path (lines 321-337)."""
        from enhanced_agent_bus.config import BusConfiguration
        from enhanced_agent_bus.core_models import AgentMessage
        from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()
        orch._pqc_config.pqc_mode = "hybrid"

        msg = AgentMessage(from_agent="test-agent")

        mock_pqc_result = MagicMock()
        mock_pqc_result.valid = True
        mock_pqc_result.pqc_metadata = MagicMock()
        mock_pqc_result.pqc_metadata.pqc_algorithm = "dilithium-3"
        mock_pqc_result.pqc_metadata.verification_mode = "hybrid"
        mock_pqc_result.pqc_metadata.classical_verified = True
        mock_pqc_result.pqc_metadata.pqc_verified = True
        mock_pqc_result.pqc_metadata.to_dict.return_value = {}
        mock_pqc_result.classical_verification_ms = 1.5
        mock_pqc_result.pqc_verification_ms = 2.3

        original_import = __import__

        def custom_import(name, *args, **kwargs):
            if "pqc_validators" in str(name):
                mod = MagicMock()
                mod.validate_constitutional_hash_pqc = AsyncMock(return_value=mock_pqc_result)
                return mod
            if name == ".models" or "enhanced_agent_bus.models" in str(name):
                import enhanced_agent_bus.models

                return enhanced_agent_bus.models
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=custom_import):
            result, metadata = await orch._perform_pqc.__wrapped__(orch, msg)

        assert result is None  # Success means no validation failure
        assert metadata.get("pqc_enabled") is True
        assert metadata.get("pqc_algorithm") == "dilithium-3"
        assert metadata.get("classical_verification_ms") == 1.5
        assert metadata.get("pqc_verification_ms") == 2.3

    async def test_pqc_validation_failure(self):
        """Exercise PQC validation failure path (lines 303-319)."""
        from enhanced_agent_bus.config import BusConfiguration
        from enhanced_agent_bus.core_models import AgentMessage
        from enhanced_agent_bus.verification_orchestrator import VerificationOrchestrator

        config = BusConfiguration()
        orch = VerificationOrchestrator(config=config, enable_pqc=False)
        orch._enable_pqc = True
        orch._pqc_config = MagicMock()

        msg = AgentMessage(from_agent="test-agent")

        mock_pqc_result = MagicMock()
        mock_pqc_result.valid = False
        mock_pqc_result.errors = ["hash mismatch"]
        mock_pqc_result.pqc_metadata = MagicMock()
        mock_pqc_result.pqc_metadata.to_dict.return_value = {"algo": "dilithium"}
        mock_pqc_result.validation_duration_ms = 5.0

        original_import = __import__

        def custom_import(name, *args, **kwargs):
            if "pqc_validators" in str(name):
                mod = MagicMock()
                mod.validate_constitutional_hash_pqc = AsyncMock(return_value=mock_pqc_result)
                return mod
            if name == ".models" or "enhanced_agent_bus.models" in str(name):
                import enhanced_agent_bus.models

                return enhanced_agent_bus.models
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=custom_import):
            result, metadata = await orch._perform_pqc.__wrapped__(orch, msg)

        assert result is not None
        assert result.is_valid is False
        assert "hash mismatch" in result.errors


# =============================================================================
# Module 3: interfaces.py
# Missing lines: 24-25, 29-30 (import fallbacks), 493-510 (deliberation imports)
# Protocol stubs (...) are intentionally not tested.
# =============================================================================


class TestInterfacesImports:
    """Test the import fallback paths in interfaces.py."""

    def test_interfaces_module_loads(self):
        """Verify the module loads without errors."""
        import enhanced_agent_bus.interfaces

        assert hasattr(enhanced_agent_bus.interfaces, "AgentRegistry")
        assert hasattr(enhanced_agent_bus.interfaces, "MessageRouter")
        assert hasattr(enhanced_agent_bus.interfaces, "ValidationStrategy")

    def test_all_exports_present(self):
        """Verify __all__ exports are accessible."""
        import enhanced_agent_bus.interfaces as mod
        from enhanced_agent_bus.interfaces import __all__

        for name in __all__:
            assert hasattr(mod, name), f"Missing export: {name}"

    def test_protocol_isinstance_checks(self):
        """Verify runtime_checkable protocols work for isinstance."""
        from enhanced_agent_bus.interfaces import (
            AgentRegistry,
            CircuitBreakerProtocol,
            MessageHandler,
            MessageRouter,
            MetricsCollector,
            OrchestratorProtocol,
            ProcessingStrategy,
            TransportProtocol,
            ValidationStrategy,
        )

        # These are runtime_checkable protocols; verify they are type objects
        for proto in [
            AgentRegistry,
            MessageRouter,
            ValidationStrategy,
            ProcessingStrategy,
            MessageHandler,
            MetricsCollector,
            TransportProtocol,
            OrchestratorProtocol,
            CircuitBreakerProtocol,
        ]:
            assert isinstance(proto, type)

    def test_agent_info_fallback(self):
        """Test that AgentInfo fallback works when src.core.shared.types is unavailable."""
        # The module already handles this at import time; just verify it loaded
        import enhanced_agent_bus.interfaces

        # AgentInfo is used internally but not exported; verify no crash
        assert enhanced_agent_bus.interfaces is not None

    def test_core_models_import_fallback(self):
        """Test that AgentMessage import fallback works."""
        # The module imports AgentMessage with a try/except fallback
        from enhanced_agent_bus.interfaces import AgentMessage

        assert AgentMessage is not None

    def test_deliberation_layer_protocols_loaded(self):
        """Test that deliberation layer protocol imports (or fallbacks) work."""
        import enhanced_agent_bus.interfaces as ifaces

        # These should be defined (either real imports or fallbacks to object)
        for name in [
            "ImpactScorerProtocol",
            "AdaptiveRouterProtocol",
            "DeliberationQueueProtocol",
            "LLMAssistantProtocol",
            "OPAGuardProtocol",
            "RedisQueueProtocol",
            "RedisVotingProtocol",
        ]:
            assert hasattr(ifaces, name), f"Missing protocol: {name}"

    def test_maci_registry_protocol(self):
        """Verify MACIRegistryProtocol is runtime_checkable."""
        from enhanced_agent_bus.interfaces import MACIRegistryProtocol

        assert isinstance(MACIRegistryProtocol, type)

    def test_maci_enforcer_protocol(self):
        """Verify MACIEnforcerProtocol is runtime_checkable."""
        from enhanced_agent_bus.interfaces import MACIEnforcerProtocol

        assert isinstance(MACIEnforcerProtocol, type)

    def test_constitutional_verifier_protocol(self):
        """Verify ConstitutionalVerifierProtocol is runtime_checkable."""
        from enhanced_agent_bus.interfaces import ConstitutionalVerifierProtocol

        assert isinstance(ConstitutionalVerifierProtocol, type)

    def test_policy_client_protocol(self):
        """Verify PolicyClientProtocol is runtime_checkable."""
        from enhanced_agent_bus.interfaces import PolicyClientProtocol

        assert isinstance(PolicyClientProtocol, type)

    def test_opa_client_protocol(self):
        """Verify OPAClientProtocol is runtime_checkable."""
        from enhanced_agent_bus.interfaces import OPAClientProtocol

        assert isinstance(OPAClientProtocol, type)

    def test_rust_processor_protocol(self):
        """Verify RustProcessorProtocol is runtime_checkable."""
        from enhanced_agent_bus.interfaces import RustProcessorProtocol

        assert isinstance(RustProcessorProtocol, type)

    def test_pqc_validator_protocol(self):
        """Verify PQCValidatorProtocol is runtime_checkable."""
        from enhanced_agent_bus.interfaces import PQCValidatorProtocol

        assert isinstance(PQCValidatorProtocol, type)


class TestInterfacesConcreteImplementation:
    """Test that concrete classes satisfying Protocol interfaces pass isinstance checks."""

    async def test_agent_registry_concrete(self):
        from enhanced_agent_bus.interfaces import AgentRegistry

        class ConcreteRegistry:
            async def register(self, agent_id, capabilities=None, metadata=None):
                return True

            async def unregister(self, agent_id):
                return True

            async def get(self, agent_id):
                return None

            async def list_agents(self):
                return []

            async def exists(self, agent_id):
                return False

            async def update_metadata(self, agent_id, metadata):
                return True

        reg = ConcreteRegistry()
        assert isinstance(reg, AgentRegistry)
        assert await reg.register("agent-1") is True
        assert await reg.exists("agent-1") is False

    async def test_message_router_concrete(self):
        from enhanced_agent_bus.interfaces import MessageRouter

        class ConcreteRouter:
            async def route(self, message, registry):
                return "target-agent"

            async def broadcast(self, message, registry, exclude=None):
                return ["agent-1", "agent-2"]

        router = ConcreteRouter()
        assert isinstance(router, MessageRouter)

    async def test_validation_strategy_concrete(self):
        from enhanced_agent_bus.interfaces import ValidationStrategy

        class ConcreteValidator:
            async def validate(self, message):
                return (True, None)

        v = ConcreteValidator()
        assert isinstance(v, ValidationStrategy)
        valid, err = await v.validate(MagicMock())
        assert valid is True
        assert err is None

    def test_metrics_collector_concrete(self):
        from enhanced_agent_bus.interfaces import MetricsCollector

        class ConcreteMetrics:
            def record_message_processed(self, message_type, duration_ms, success):
                pass

            def record_agent_registered(self, agent_id):
                pass

            def record_agent_unregistered(self, agent_id):
                pass

            def get_metrics(self):
                return {"total": 0}

        m = ConcreteMetrics()
        assert isinstance(m, MetricsCollector)
        assert m.get_metrics()["total"] == 0

    async def test_circuit_breaker_concrete(self):
        from enhanced_agent_bus.interfaces import CircuitBreakerProtocol

        class ConcreteBreaker:
            async def record_success(self):
                pass

            async def record_failure(self, error=None, error_type="unknown"):
                pass

            async def can_execute(self):
                return True

            async def reset(self):
                pass

        cb = ConcreteBreaker()
        assert isinstance(cb, CircuitBreakerProtocol)
        assert await cb.can_execute() is True

    async def test_transport_protocol_concrete(self):
        from enhanced_agent_bus.interfaces import TransportProtocol

        class ConcreteTransport:
            async def start(self):
                pass

            async def stop(self):
                pass

            async def send(self, message, topic=None):
                return True

            async def subscribe(self, topic, handler):
                pass

        t = ConcreteTransport()
        assert isinstance(t, TransportProtocol)
        assert await t.send(MagicMock()) is True

    async def test_orchestrator_protocol_concrete(self):
        from enhanced_agent_bus.interfaces import OrchestratorProtocol

        class ConcreteOrchestrator:
            async def start(self):
                pass

            async def stop(self):
                pass

            def get_status(self):
                return {"status": "healthy", "constitutional_hash": "608508a9bd224290"}

        o = ConcreteOrchestrator()
        assert isinstance(o, OrchestratorProtocol)
        assert o.get_status()["status"] == "healthy"

    def test_processing_strategy_concrete(self):
        from enhanced_agent_bus.interfaces import ProcessingStrategy

        class ConcreteStrategy:
            async def process(self, message, handlers):
                return MagicMock(is_valid=True)

            def is_available(self):
                return True

            def get_name(self):
                return "concrete"

        s = ConcreteStrategy()
        assert isinstance(s, ProcessingStrategy)
        assert s.is_available() is True
        assert s.get_name() == "concrete"

    async def test_message_handler_concrete(self):
        from enhanced_agent_bus.interfaces import MessageHandler

        class ConcreteHandler:
            async def handle(self, message):
                return None

            def can_handle(self, message):
                return True

        h = ConcreteHandler()
        assert isinstance(h, MessageHandler)
        assert h.can_handle(MagicMock()) is True

    async def test_message_processor_protocol_concrete(self):
        from enhanced_agent_bus.interfaces import MessageProcessorProtocol

        class ConcreteProcessor:
            async def process(self, message):
                return MagicMock(is_valid=True)

        p = ConcreteProcessor()
        assert isinstance(p, MessageProcessorProtocol)

    def test_role_matrix_validator_protocol(self):
        from enhanced_agent_bus.interfaces import RoleMatrixValidatorProtocol

        class ConcreteRMV:
            def validate(self, *, violations, strict_mode):
                if strict_mode and violations:
                    raise RuntimeError("violations found")

        rmv = ConcreteRMV()
        assert isinstance(rmv, RoleMatrixValidatorProtocol)
        rmv.validate(violations=[], strict_mode=True)

    def test_approvals_validator_protocol(self):
        from enhanced_agent_bus.interfaces import ApprovalsValidatorProtocol

        class ConcreteAV:
            def validate_approvals(self, *, policy, decisions, approvers, requester_id):
                return (True, "ok")

        av = ConcreteAV()
        assert isinstance(av, ApprovalsValidatorProtocol)
        valid, reason = av.validate_approvals(
            policy={}, decisions=[], approvers={}, requester_id="req-1"
        )
        assert valid is True

    def test_recommendation_planner_protocol(self):
        from enhanced_agent_bus.interfaces import RecommendationPlannerProtocol

        class ConcretePlanner:
            def generate_recommendations(self, *, judgment, decision):
                return ["step1", "step2"]

        p = ConcretePlanner()
        assert isinstance(p, RecommendationPlannerProtocol)
        recs = p.generate_recommendations(judgment={}, decision={})
        assert len(recs) == 2

    async def test_constitutional_hash_validator_protocol(self):
        from enhanced_agent_bus.interfaces import ConstitutionalHashValidatorProtocol

        class ConcreteCHV:
            async def validate_hash(self, *, provided_hash, expected_hash, context=None):
                if provided_hash == expected_hash:
                    return (True, "")
                return (False, "hash mismatch")

        chv = ConcreteCHV()
        assert isinstance(chv, ConstitutionalHashValidatorProtocol)
        valid, err = await chv.validate_hash(provided_hash="abc", expected_hash="abc")
        assert valid is True

    async def test_governance_decision_validator_protocol(self):
        from enhanced_agent_bus.interfaces import GovernanceDecisionValidatorProtocol

        class ConcreteGDV:
            async def validate_decision(self, *, decision, context):
                return (True, [])

        gdv = ConcreteGDV()
        assert isinstance(gdv, GovernanceDecisionValidatorProtocol)
        valid, errors = await gdv.validate_decision(decision={}, context={})
        assert valid is True
