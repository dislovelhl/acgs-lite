"""Integration-style scenarios for MCP client and pool.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio

import pytest

from enhanced_agent_bus.mcp_integration.client import (
    MCPConnectionPool,
    MCPServerConnection,
)

from .helpers import _make_client, _make_config

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMCPClientIntegration:
    async def test_full_lifecycle(self):
        client = _make_client()
        connect_events = []
        disconnect_events = []
        client.on_connect(lambda c: connect_events.append(c.server_id))
        client.on_disconnect(lambda c: disconnect_events.append(c.server_id))
        assert await client.connect()
        assert client.is_connected
        assert len(connect_events) == 1
        tool_result = await client.call_tool("example_tool", {"input": "test"})
        assert tool_result["isError"] is False
        res_result = await client.read_resource("example://resource")
        assert "contents" in res_result
        ping_result = await client.ping()
        assert ping_result["status"] == "ok"
        m = client.get_metrics()
        assert m["total_requests"] > 0
        assert m["state"] == "ready"
        await client.disconnect()
        assert not client.is_connected
        assert len(disconnect_events) == 1

    async def test_pool_full_lifecycle(self):
        pool = MCPConnectionPool()
        cfg1 = _make_config(server_url="http://alpha.example.com/mcp", server_name="alpha")
        cfg2 = _make_config(server_url="http://beta.example.com/mcp", server_name="beta")
        c1 = await pool.add_server(cfg1, auto_connect=False)
        c2 = await pool.add_server(cfg2, auto_connect=False)
        results = await pool.connect_all()
        assert all(v for v in results.values())
        result = await c1.call_tool("example_tool", {})
        assert result is not None
        pool_metrics = pool.get_metrics()
        assert pool_metrics["connected_servers"] == 2
        await pool.disconnect_all()
        assert pool.get_metrics()["connected_servers"] == 0

    async def test_multiple_requests_sequential(self):
        client = _make_client()
        await client.connect()
        n = 5
        for _ in range(n):
            await client.ping()
        assert client._total_requests >= n

    async def test_connect_all_multiple_parallel(self):
        pool = MCPConnectionPool()
        configs = [
            _make_config(server_url=f"http://s{i}.example.com/mcp", server_name=f"s{i}")
            for i in range(5)
        ]
        clients = []
        for cfg in configs:
            c = await pool.add_server(cfg, auto_connect=False)
            clients.append(c)
        results = await pool.connect_all()
        assert len(results) == 5
        assert all(v for v in results.values())

    async def test_remove_all_servers(self):
        pool = MCPConnectionPool()
        cfgs = [_make_config(server_url=f"http://r{i}.example.com/mcp") for i in range(3)]
        client_ids = []
        for cfg in cfgs:
            c = await pool.add_server(cfg)
            client_ids.append(c.server_id)
        for sid in client_ids:
            assert await pool.remove_server(sid)
        assert len(pool._clients) == 0
        assert pool.get_metrics()["total_servers"] == 0
