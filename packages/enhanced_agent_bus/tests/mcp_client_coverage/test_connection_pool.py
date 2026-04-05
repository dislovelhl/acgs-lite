"""Unit tests for MCPConnectionPool.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.mcp_integration.client import (
    MCPConnectionError,
    MCPConnectionPool,
)

from .helpers import _make_config

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMCPConnectionPoolInit:
    def test_default_init(self):
        pool = MCPConnectionPool()
        assert pool.validator is None
        assert pool.tool_registry is None
        assert pool.default_agent_id == "mcp-pool"
        assert pool._clients == {}

    def test_custom_init(self):
        validator = MagicMock()
        registry = MagicMock()
        pool = MCPConnectionPool(
            validator=validator, tool_registry=registry, default_agent_id="my-pool"
        )
        assert pool.validator is validator
        assert pool.tool_registry is registry
        assert pool.default_agent_id == "my-pool"

    def test_constitutional_hash(self):
        assert MCPConnectionPool.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_max_connections(self):
        assert MCPConnectionPool.MAX_CONNECTIONS == 20000


class TestMCPConnectionPoolAddServer:
    async def test_add_server_auto_connect(self):
        pool = MCPConnectionPool()
        cfg = _make_config()
        client = await pool.add_server(cfg)
        assert client.is_connected
        assert len(pool._clients) == 1

    async def test_add_server_no_auto_connect(self):
        pool = MCPConnectionPool()
        cfg = _make_config()
        client = await pool.add_server(cfg, auto_connect=False)
        assert not client.is_connected
        assert len(pool._clients) == 1

    async def test_add_server_custom_agent_id(self):
        pool = MCPConnectionPool()
        cfg = _make_config()
        client = await pool.add_server(cfg, agent_id="special-agent", auto_connect=False)
        assert client.agent_id == "special-agent"

    async def test_add_server_uses_default_agent_id(self):
        pool = MCPConnectionPool(default_agent_id="pool-default")
        cfg = _make_config()
        client = await pool.add_server(cfg, auto_connect=False)
        assert client.agent_id == "pool-default"

    async def test_add_server_max_connections_raises(self):
        pool = MCPConnectionPool()
        with patch.object(type(pool), "MAX_CONNECTIONS", 0):
            with pytest.raises(MCPConnectionError, match="Maximum connections reached"):
                await pool.add_server(_make_config())

    async def test_add_server_with_validator(self):
        validator = MagicMock()
        validation_result = MagicMock()
        validation_result.is_valid = True
        validator.validate = AsyncMock(return_value=validation_result)

        with patch("enhanced_agent_bus.mcp_integration.client.VALIDATORS_AVAILABLE", True):
            pool = MCPConnectionPool(validator=validator)
            cfg = _make_config()
            client = await pool.add_server(cfg)

        assert client is not None
        validator.validate.assert_called()


class TestMCPConnectionPoolRemoveServer:
    async def test_remove_existing_connected_server(self):
        pool = MCPConnectionPool()
        cfg = _make_config()
        client = await pool.add_server(cfg)
        server_id = client.server_id
        result = await pool.remove_server(server_id)
        assert result is True
        assert server_id not in pool._clients

    async def test_remove_existing_disconnected_server(self):
        pool = MCPConnectionPool()
        cfg = _make_config()
        client = await pool.add_server(cfg, auto_connect=False)
        server_id = client.server_id
        result = await pool.remove_server(server_id)
        assert result is True

    async def test_remove_nonexistent_server_returns_false(self):
        pool = MCPConnectionPool()
        result = await pool.remove_server("does-not-exist")
        assert result is False

    async def test_remove_server_disconnects_client(self):
        pool = MCPConnectionPool()
        cfg = _make_config()
        client = await pool.add_server(cfg)
        assert client.is_connected
        server_id = client.server_id
        await pool.remove_server(server_id)
        assert not client.is_connected


class TestMCPConnectionPoolQuery:
    async def test_get_client_existing(self):
        pool = MCPConnectionPool()
        cfg = _make_config()
        added = await pool.add_server(cfg, auto_connect=False)
        retrieved = pool.get_client(added.server_id)
        assert retrieved is added

    def test_get_client_nonexistent(self):
        pool = MCPConnectionPool()
        assert pool.get_client("no-such-id") is None

    async def test_list_servers_empty(self):
        pool = MCPConnectionPool()
        assert pool.list_servers() == []

    async def test_list_servers_after_add(self):
        pool = MCPConnectionPool()
        cfg = _make_config()
        await pool.add_server(cfg)
        servers = pool.list_servers()
        assert len(servers) == 1

    async def test_list_servers_disconnected_client(self):
        pool = MCPConnectionPool()
        cfg = _make_config()
        client = await pool.add_server(cfg, auto_connect=False)
        client._connection = None
        servers = pool.list_servers()
        assert len(servers) == 1
        assert servers[0]["state"] == "unknown"


class TestMCPConnectionPoolBulkOps:
    async def test_connect_all_empty_pool(self):
        pool = MCPConnectionPool()
        results = await pool.connect_all()
        assert results == {}

    async def test_connect_all_already_connected(self):
        pool = MCPConnectionPool()
        cfg = _make_config()
        await pool.add_server(cfg)
        results = await pool.connect_all()
        assert results == {}

    async def test_connect_all_connects_disconnected(self):
        pool = MCPConnectionPool()
        cfg = _make_config()
        client = await pool.add_server(cfg, auto_connect=False)
        results = await pool.connect_all()
        assert results[client.server_id] is True
        assert client.is_connected

    async def test_connect_all_records_failure(self):
        pool = MCPConnectionPool()
        cfg = _make_config(retry_attempts=1)
        client = await pool.add_server(cfg, auto_connect=False)

        async def always_fail():
            raise OSError("network down")

        client._establish_connection = always_fail
        results = await pool.connect_all()
        assert results[client.server_id] is False

    async def test_disconnect_all_empty_pool(self):
        pool = MCPConnectionPool()
        await pool.disconnect_all()

    async def test_disconnect_all_connected(self):
        pool = MCPConnectionPool()
        cfg = _make_config()
        client = await pool.add_server(cfg)
        assert client.is_connected
        await pool.disconnect_all()
        assert not client.is_connected

    async def test_disconnect_all_mixed(self):
        pool = MCPConnectionPool()
        cfg1 = _make_config(server_url="http://a.example.com/mcp")
        cfg2 = _make_config(server_url="http://b.example.com/mcp")
        c1 = await pool.add_server(cfg1)
        c2 = await pool.add_server(cfg2, auto_connect=False)
        await pool.disconnect_all()
        assert not c1.is_connected
        assert not c2.is_connected


class TestMCPConnectionPoolMetrics:
    def test_get_metrics_empty(self):
        pool = MCPConnectionPool()
        m = pool.get_metrics()
        assert m["total_servers"] == 0
        assert m["connected_servers"] == 0
        assert m["disconnected_servers"] == 0
        assert m["max_connections"] == MCPConnectionPool.MAX_CONNECTIONS
        assert m["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_metrics_with_connections(self):
        pool = MCPConnectionPool()
        cfg1 = _make_config(server_url="http://s1.example.com/mcp")
        cfg2 = _make_config(server_url="http://s2.example.com/mcp")
        await pool.add_server(cfg1)
        await pool.add_server(cfg2, auto_connect=False)
        m = pool.get_metrics()
        assert m["total_servers"] == 2
        assert m["connected_servers"] == 1
        assert m["disconnected_servers"] == 1
