"""
Coverage tests for MCP Server (server.py).

Constitutional Hash: 608508a9bd224290

Covers:
- MCPServer construction and __post_init__
- connect_adapters / disconnect_adapters
- start / stop lifecycle
- handle_request (success and error branch)
- get_capabilities / get_tool_definitions / get_resource_definitions
- get_metrics (hasattr branches)
- create_mcp_server factory with injected services
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.mcp_server.config import MCPConfig, TransportType
from enhanced_agent_bus.mcp_server.protocol.types import (
    MCPRequest,
    MCPResponse,
    ServerCapabilities,
)
from enhanced_agent_bus.mcp_server.server import MCPServer, create_mcp_server

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_server(transport: TransportType = TransportType.STDIO) -> MCPServer:
    config = MCPConfig(transport_type=transport)
    return MCPServer(config=config)


def _make_request(method: str, params: dict | None = None, req_id: str | int = "1") -> MCPRequest:
    return MCPRequest(jsonrpc="2.0", method=method, id=req_id, params=params)


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------


class TestMCPServerConstruction:
    """Tests for MCPServer initialization."""

    def test_default_config(self):
        server = _make_server()
        assert server.config.server_name == "acgs2-governance"
        assert server._handler is not None
        assert server._running is False
        assert server._request_count == 0
        assert server._error_count == 0

    def test_tools_registered(self):
        server = _make_server()
        assert len(server._tools) == 5
        assert "validate_constitutional_compliance" in server._tools
        assert "get_active_principles" in server._tools
        assert "query_governance_precedents" in server._tools
        assert "submit_governance_request" in server._tools
        assert "get_governance_metrics" in server._tools

    def test_resources_registered(self):
        server = _make_server()
        assert len(server._resources) == 4
        assert "principles" in server._resources
        assert "metrics" in server._resources
        assert "decisions" in server._resources
        assert "audit_trail" in server._resources

    def test_adapters_registered(self):
        server = _make_server()
        assert "agent_bus" in server._adapters
        assert "policy_client" in server._adapters
        assert "audit_client" in server._adapters


# ---------------------------------------------------------------------------
# Adapter connection tests
# ---------------------------------------------------------------------------


class TestAdapterConnections:
    """Tests for connect/disconnect adapters."""

    async def test_connect_adapters_returns_true(self):
        server = _make_server()
        server._adapters["agent_bus"] = MagicMock()
        server._adapters["agent_bus"].connect = AsyncMock(return_value=True)
        result = await server.connect_adapters()
        assert result is True

    async def test_connect_adapters_standalone_mode(self):
        server = _make_server()
        server._adapters["agent_bus"] = MagicMock()
        server._adapters["agent_bus"].connect = AsyncMock(return_value=False)
        result = await server.connect_adapters()
        assert result is True  # Server runs in standalone mode

    async def test_disconnect_adapters(self):
        server = _make_server()
        mock_adapter = MagicMock()
        mock_adapter.disconnect = AsyncMock()
        server._adapters["agent_bus"] = mock_adapter
        await server.disconnect_adapters()
        mock_adapter.disconnect.assert_awaited_once()


# ---------------------------------------------------------------------------
# Start / Stop lifecycle
# ---------------------------------------------------------------------------


class TestStartStop:
    """Tests for server start and stop lifecycle."""

    async def test_stop_not_running_is_noop(self):
        server = _make_server()
        assert server._running is False
        await server.stop()
        assert server._running is False

    async def test_start_already_running_returns_early(self):
        server = _make_server()
        server._running = True
        # Mock the transport so it doesn't actually run
        server._adapters["agent_bus"] = MagicMock()
        server._adapters["agent_bus"].connect = AsyncMock(return_value=True)
        # Should return immediately without error
        await server.start()

    async def test_stop_disconnects_and_marks_not_running(self):
        server = _make_server()
        server._running = True
        mock_adapter = MagicMock()
        mock_adapter.disconnect = AsyncMock()
        server._adapters["agent_bus"] = mock_adapter
        # Mock audit resource
        mock_audit = MagicMock()
        server._resources["audit_trail"] = mock_audit
        await server.stop()
        assert server._running is False
        mock_adapter.disconnect.assert_awaited_once()
        mock_audit.log_event.assert_called_once()


# ---------------------------------------------------------------------------
# handle_request tests
# ---------------------------------------------------------------------------


class TestHandleRequest:
    """Tests for the handle_request method."""

    async def test_handle_request_success(self):
        server = _make_server()
        mock_response = MCPResponse(jsonrpc="2.0", id="1", result={"ok": True})
        server._handler = MagicMock()
        server._handler.handle_request = AsyncMock(return_value=mock_response)

        request = _make_request("tools/list")
        response = await server.handle_request(request)

        assert response is not None
        assert response.result == {"ok": True}
        assert server._request_count == 1
        assert server._error_count == 0

    async def test_handle_request_error(self):
        server = _make_server()
        server._handler = MagicMock()
        server._handler.handle_request = AsyncMock(side_effect=ValueError("boom"))

        request = _make_request("tools/list")
        response = await server.handle_request(request)

        assert response is not None
        assert response.error is not None
        assert response.error.code == -32603
        assert server._error_count == 1


# ---------------------------------------------------------------------------
# Capabilities and definitions
# ---------------------------------------------------------------------------


class TestCapabilitiesAndDefinitions:
    """Tests for get_capabilities, get_tool_definitions, get_resource_definitions."""

    def test_get_capabilities(self):
        server = _make_server()
        caps = server.get_capabilities()
        assert isinstance(caps, ServerCapabilities)
        assert caps.tools == {"listChanged": True}
        assert caps.resources == {"subscribe": False, "listChanged": True}

    def test_get_tool_definitions(self):
        server = _make_server()
        defs = server.get_tool_definitions()
        assert len(defs) == 5
        names = {d.name for d in defs}
        assert "validate_constitutional_compliance" in names

    def test_get_resource_definitions(self):
        server = _make_server()
        defs = server.get_resource_definitions()
        assert len(defs) == 4


# ---------------------------------------------------------------------------
# get_metrics tests
# ---------------------------------------------------------------------------


class TestGetMetrics:
    """Tests for get_metrics with various hasattr branches."""

    def test_get_metrics_basic(self):
        server = _make_server()
        metrics = server.get_metrics()
        assert metrics["server"]["name"] == "acgs2-governance"
        assert metrics["server"]["running"] is False
        assert metrics["server"]["request_count"] == 0

    def test_get_metrics_with_tool_metrics(self):
        server = _make_server()
        mock_tool = MagicMock()
        mock_tool.get_definition = MagicMock()
        mock_tool.get_metrics = MagicMock(return_value={"calls": 5})
        server._tools["test_tool"] = mock_tool
        metrics = server.get_metrics()
        assert metrics["tools"]["test_tool"] == {"calls": 5}

    def test_get_metrics_tool_without_get_metrics(self):
        server = _make_server()
        mock_tool = MagicMock(spec=[])  # No get_metrics attribute
        server._tools["no_metrics_tool"] = mock_tool
        metrics = server.get_metrics()
        assert "no_metrics_tool" not in metrics["tools"]

    def test_get_metrics_with_resource_metrics(self):
        server = _make_server()
        mock_resource = MagicMock()
        mock_resource.get_metrics = MagicMock(return_value={"reads": 10})
        server._resources["test_res"] = mock_resource
        metrics = server.get_metrics()
        assert metrics["resources"]["test_res"] == {"reads": 10}

    def test_get_metrics_with_adapter_metrics(self):
        server = _make_server()
        mock_adapter = MagicMock()
        mock_adapter.get_metrics = MagicMock(return_value={"connected": True})
        server._adapters["test_adapter"] = mock_adapter
        metrics = server.get_metrics()
        assert metrics["adapters"]["test_adapter"] == {"connected": True}


# ---------------------------------------------------------------------------
# create_mcp_server factory tests
# ---------------------------------------------------------------------------


class TestCreateMcpServer:
    """Tests for the create_mcp_server factory function."""

    def test_default_config(self):
        server = create_mcp_server()
        assert isinstance(server, MCPServer)
        assert server.config.server_name == "acgs2-governance"

    def test_custom_config(self):
        config = MCPConfig(server_name="custom-server")
        server = create_mcp_server(config=config)
        assert server.config.server_name == "custom-server"

    def test_inject_agent_bus(self):
        mock_bus = MagicMock()
        server = create_mcp_server(agent_bus=mock_bus)
        assert server._adapters["agent_bus"].agent_bus is mock_bus

    def test_inject_policy_client(self):
        mock_policy = MagicMock()
        server = create_mcp_server(policy_client=mock_policy)
        assert server._adapters["policy_client"].policy_client is mock_policy

    def test_inject_audit_client(self):
        mock_audit = MagicMock()
        server = create_mcp_server(audit_client=mock_audit)
        assert server._adapters["audit_client"].audit_client is mock_audit
