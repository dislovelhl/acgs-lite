"""
Tests for mcp_integration/client.py (MCPClient, MCPConnectionPool)

Note: The originally requested source file `connection_manager.py` does not exist.
This test file covers `mcp_integration/client.py` which provides connection
management functionality.

Covers:
- MCPClientConfig, MCPServerInfo, MCPServerConnection dataclasses
- MCPClient: connect, disconnect, call_tool, read_resource, ping
- MCPClient: state properties, event handlers, metrics
- MCPConnectionError
- MCPConnectionPool basics
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.mcp_integration.client import (
    MCPClient,
    MCPClientConfig,
    MCPClientState,
    MCPConnectionError,
    MCPConnectionPool,
    MCPServerConnection,
    MCPServerInfo,
    MCPTransportType,
)

# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestMCPClientConfig:
    def test_defaults(self):
        cfg = MCPClientConfig()
        assert cfg.server_url == ""
        assert cfg.transport_type == MCPTransportType.HTTP
        assert cfg.timeout_ms == 30000
        assert cfg.retry_attempts == 3

    def test_auto_server_name_from_url(self):
        cfg = MCPClientConfig(server_url="http://example.com/myserver")
        assert cfg.server_name == "myserver"

    def test_explicit_server_name_preserved(self):
        cfg = MCPClientConfig(server_url="http://example.com/x", server_name="custom")
        assert cfg.server_name == "custom"


class TestMCPServerInfo:
    def test_to_dict(self):
        info = MCPServerInfo(name="test", version="1.0", protocol_version="2024-11-05")
        d = info.to_dict()
        assert d["name"] == "test"
        assert d["version"] == "1.0"
        assert "connected_at" in d


class TestMCPServerConnection:
    def test_to_dict(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        conn = MCPServerConnection(server_id="s-1", config=cfg)
        d = conn.to_dict()
        assert d["server_id"] == "s-1"
        assert d["state"] == "disconnected"
        assert d["tools_count"] == 0

    def test_to_dict_with_server_info(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        info = MCPServerInfo(name="srv", version="1.0", protocol_version="2024-11-05")
        conn = MCPServerConnection(server_id="s-1", config=cfg, server_info=info)
        d = conn.to_dict()
        assert d["server_info"]["name"] == "srv"


# ---------------------------------------------------------------------------
# MCPConnectionError
# ---------------------------------------------------------------------------


class TestMCPConnectionError:
    def test_basic_error(self):
        err = MCPConnectionError("connection refused", server_id="s-1")
        assert "connection refused" in str(err)
        assert err.server_id == "s-1"

    def test_error_with_server_id(self):
        err = MCPConnectionError("bad request", server_id="s-1", error_code=400)
        assert err.server_id == "s-1"


# ---------------------------------------------------------------------------
# MCPClient - initialization
# ---------------------------------------------------------------------------


class TestMCPClientInit:
    def test_initial_state(self):
        cfg = MCPClientConfig(server_url="http://localhost:8080")
        client = MCPClient(config=cfg)
        assert client.state == MCPClientState.DISCONNECTED
        assert client.is_connected is False
        assert client.server_id != ""

    def test_custom_agent_id(self):
        cfg = MCPClientConfig()
        client = MCPClient(config=cfg, agent_id="custom-agent")
        assert client.agent_id == "custom-agent"


# ---------------------------------------------------------------------------
# MCPClient - connect / disconnect
# ---------------------------------------------------------------------------


class TestMCPClientConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        result = await client.connect()
        assert result is True
        assert client.is_connected is True
        assert client.state == MCPClientState.READY
        assert client._connection is not None
        assert client._connection.server_info is not None

    @pytest.mark.asyncio
    async def test_connect_discovers_tools(self):
        cfg = MCPClientConfig(server_url="http://localhost", enable_tool_discovery=True)
        client = MCPClient(config=cfg)
        await client.connect()
        tools = client.get_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "example_tool"

    @pytest.mark.asyncio
    async def test_connect_discovers_resources(self):
        cfg = MCPClientConfig(server_url="http://localhost", enable_resource_discovery=True)
        client = MCPClient(config=cfg)
        await client.connect()
        resources = client.get_resources()
        assert len(resources) == 1

    @pytest.mark.asyncio
    async def test_disconnect(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        await client.connect()
        await client.disconnect()
        assert client.state == MCPClientState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        await client.disconnect()  # Should not raise

    @pytest.mark.asyncio
    async def test_connect_fires_handler(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        handler_called = False

        def on_connect(conn):
            nonlocal handler_called
            handler_called = True

        client.on_connect(on_connect)
        await client.connect()
        assert handler_called is True

    @pytest.mark.asyncio
    async def test_disconnect_fires_handler(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        handler_called = False

        def on_disconnect(conn):
            nonlocal handler_called
            handler_called = True

        client.on_disconnect(on_disconnect)
        await client.connect()
        await client.disconnect()
        assert handler_called is True


# ---------------------------------------------------------------------------
# MCPClient - call_tool, read_resource, ping
# ---------------------------------------------------------------------------


class TestMCPClientOperations:
    @pytest.mark.asyncio
    async def test_call_tool(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        await client.connect()
        result = await client.call_tool("example_tool", {"input": "test"})
        assert "content" in result

    @pytest.mark.asyncio
    async def test_call_tool_not_connected_raises(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        with pytest.raises(MCPConnectionError, match="Not connected"):
            await client.call_tool("example_tool", {})

    @pytest.mark.asyncio
    async def test_read_resource(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        await client.connect()
        result = await client.read_resource("example://resource")
        assert "contents" in result

    @pytest.mark.asyncio
    async def test_read_resource_not_connected_raises(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        with pytest.raises(MCPConnectionError, match="Not connected"):
            await client.read_resource("example://resource")

    @pytest.mark.asyncio
    async def test_ping(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        await client.connect()
        result = await client.ping()
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_ping_not_connected_raises(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        with pytest.raises(MCPConnectionError, match="Not connected"):
            await client.ping()


# ---------------------------------------------------------------------------
# MCPClient - metrics and info
# ---------------------------------------------------------------------------


class TestMCPClientMetrics:
    @pytest.mark.asyncio
    async def test_get_metrics_before_connect(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        m = client.get_metrics()
        assert m["state"] == "disconnected"
        assert m["connection_attempts"] == 0

    @pytest.mark.asyncio
    async def test_get_metrics_after_connect(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        await client.connect()
        m = client.get_metrics()
        assert m["state"] == "ready"
        assert m["connection_attempts"] == 1
        assert m["successful_connections"] == 1
        assert m["total_requests"] > 0

    @pytest.mark.asyncio
    async def test_get_connection_info_none(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        assert client.get_connection_info() is None

    @pytest.mark.asyncio
    async def test_get_connection_info_connected(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        await client.connect()
        info = client.get_connection_info()
        assert info is not None
        assert info["state"] == "ready"

    @pytest.mark.asyncio
    async def test_get_tools_when_not_connected(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        assert client.get_tools() == []

    @pytest.mark.asyncio
    async def test_get_resources_when_not_connected(self):
        cfg = MCPClientConfig(server_url="http://localhost")
        client = MCPClient(config=cfg)
        assert client.get_resources() == []


# ---------------------------------------------------------------------------
# MCPClient - event handlers
# ---------------------------------------------------------------------------


class TestEventHandlers:
    def test_register_on_error_handler(self):
        cfg = MCPClientConfig()
        client = MCPClient(config=cfg)
        handler = MagicMock()
        client.on_error(handler)
        assert handler in client._on_error_handlers


# ---------------------------------------------------------------------------
# MCPConnectionPool
# ---------------------------------------------------------------------------


class TestMCPConnectionPool:
    def test_init(self):
        pool = MCPConnectionPool()
        assert pool.default_agent_id == "mcp-pool"
        assert len(pool._clients) == 0

    def test_init_custom_agent_id(self):
        pool = MCPConnectionPool(default_agent_id="custom")
        assert pool.default_agent_id == "custom"
