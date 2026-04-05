"""Unit tests for MCP client edge cases and branch coverage.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from enhanced_agent_bus.mcp_integration.client import (
    MCPClientConfig,
    MCPClientState,
    MCPServerConnection,
    MCPTransportType,
)

from .helpers import _make_client, _make_config

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestEdgeCases:
    def test_mcp_client_state_property_no_connection(self):
        client = _make_client()
        assert client.state == MCPClientState.DISCONNECTED

    def test_mcp_client_state_property_with_connection(self):
        client = _make_client()
        cfg = client.config
        client._connection = MCPServerConnection(
            server_id="s", config=cfg, state=MCPClientState.CONNECTING
        )
        assert client.state == MCPClientState.CONNECTING

    def test_is_connected_false_when_connecting(self):
        client = _make_client()
        cfg = client.config
        client._connection = MCPServerConnection(
            server_id="s", config=cfg, state=MCPClientState.CONNECTING
        )
        assert not client.is_connected

    def test_is_connected_true_when_ready(self):
        client = _make_client()
        cfg = client.config
        client._connection = MCPServerConnection(
            server_id="s", config=cfg, state=MCPClientState.READY
        )
        assert client.is_connected

    def test_get_tools_with_connection_but_empty(self):
        client = _make_client()
        cfg = client.config
        client._connection = MCPServerConnection(server_id="s", config=cfg)
        assert client.get_tools() == []

    def test_get_resources_with_connection_but_empty(self):
        client = _make_client()
        cfg = client.config
        client._connection = MCPServerConnection(server_id="s", config=cfg)
        assert client.get_resources() == []

    def test_get_connection_info_with_connection(self):
        client = _make_client()
        cfg = client.config
        client._connection = MCPServerConnection(server_id="s", config=cfg)
        info = client.get_connection_info()
        assert info is not None
        assert info["server_id"] == "s"

    async def test_disconnect_when_connected_pending_already_done(self):
        client = _make_client()
        await client.connect()
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        fut.set_result("resolved")
        client._pending_requests["r1"] = fut
        await client.disconnect()
        assert len(client._pending_requests) == 0

    async def test_call_tool_increments_metrics(self):
        client = _make_client()
        await client.connect()
        prev_requests = client._total_requests
        await client.call_tool("example_tool", {})
        assert client._total_requests > prev_requests

    async def test_read_resource_increments_metrics(self):
        client = _make_client()
        await client.connect()
        prev_requests = client._total_requests
        await client.read_resource("example://resource")
        assert client._total_requests > prev_requests

    def test_server_connection_to_dict_tools_resources_count(self):
        cfg = _make_config()
        conn = MCPServerConnection(server_id="x", config=cfg)
        conn.tools = [{"name": "t1"}, {"name": "t2"}]
        conn.resources = [{"uri": "r1"}]
        conn.prompts = [{"id": "p1"}, {"id": "p2"}, {"id": "p3"}]
        d = conn.to_dict()
        assert d["tools_count"] == 2
        assert d["resources_count"] == 1
        assert d["prompts_count"] == 3

    async def test_connect_with_server_name_in_simulate_response(self):
        cfg = _make_config(server_name="my-sim-server")
        client = _make_client(config=cfg)
        await client.connect()
        assert client._connection.server_info.name == "my-sim-server"

    def test_mcp_client_config_all_transport_types(self):
        for transport in MCPTransportType:
            cfg = MCPClientConfig(transport_type=transport)
            assert cfg.transport_type == transport

    async def test_connect_async_handler_receives_connection(self):
        received = []

        async def handler(conn):
            received.append(conn)

        client = _make_client()
        client.on_connect(handler)
        await client.connect()
        assert len(received) == 1
        assert isinstance(received[0], MCPServerConnection)

    async def test_disconnect_async_handler_receives_connection(self):
        received = []

        async def handler(conn):
            received.append(conn)

        client = _make_client()
        await client.connect()
        client.on_disconnect(handler)
        await client.disconnect()
        assert len(received) == 1
