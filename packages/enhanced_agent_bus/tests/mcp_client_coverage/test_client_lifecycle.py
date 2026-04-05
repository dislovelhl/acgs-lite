"""Unit tests for MCP client lifecycle (connect, disconnect, retry).
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.mcp_integration.client import (
    MCPClient,
    MCPClientConfig,
    MCPClientState,
    MCPConnectionError,
    MCPServerConnection,
)

from .helpers import _make_client, _make_config

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMCPClientInit:
    def test_server_id_generated(self):
        client = _make_client()
        assert len(client.server_id) == 16
        assert isinstance(client.server_id, str)

    def test_initial_state_disconnected(self):
        client = _make_client()
        assert client.state == MCPClientState.DISCONNECTED

    def test_is_connected_false_initially(self):
        client = _make_client()
        assert client.is_connected is False

    def test_get_metrics_initial(self):
        client = _make_client()
        m = client.get_metrics()
        assert m["connection_attempts"] == 0
        assert m["successful_connections"] == 0
        assert m["total_requests"] == 0
        assert m["total_errors"] == 0
        assert m["state"] == "disconnected"
        assert m["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert m["pending_requests"] == 0

    def test_constitutional_hash_class_attr(self):
        assert MCPClient.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_protocol_version_class_attr(self):
        assert MCPClient.PROTOCOL_VERSION == "2024-11-05"

    def test_custom_agent_id(self):
        client = _make_client(agent_id="custom-agent")
        assert client.agent_id == "custom-agent"

    def test_event_handlers_empty_initially(self):
        client = _make_client()
        assert client._on_connect_handlers == []
        assert client._on_disconnect_handlers == []
        assert client._on_error_handlers == []


class TestMCPClientEventHandlers:
    def test_on_connect(self):
        client = _make_client()
        handler = MagicMock()
        client.on_connect(handler)
        assert handler in client._on_connect_handlers

    def test_on_disconnect(self):
        client = _make_client()
        handler = MagicMock()
        client.on_disconnect(handler)
        assert handler in client._on_disconnect_handlers

    def test_on_error(self):
        client = _make_client()
        handler = MagicMock()
        client.on_error(handler)
        assert handler in client._on_error_handlers

    def test_multiple_handlers(self):
        client = _make_client()
        h1, h2 = MagicMock(), MagicMock()
        client.on_connect(h1)
        client.on_connect(h2)
        assert len(client._on_connect_handlers) == 2


class TestMCPClientConnect:
    async def test_connect_success(self):
        client = _make_client()
        result = await client.connect()
        assert result is True
        assert client.is_connected
        assert client.state == MCPClientState.READY

    async def test_connect_increments_connection_attempts(self):
        client = _make_client()
        await client.connect()
        assert client._connection_attempts == 1

    async def test_connect_increments_successful_connections(self):
        client = _make_client()
        await client.connect()
        assert client._successful_connections == 1

    async def test_connect_sets_connected_at(self):
        client = _make_client()
        await client.connect()
        assert client._connection.connected_at is not None

    async def test_connect_discovers_tools(self):
        client = _make_client()
        await client.connect()
        assert len(client.get_tools()) > 0

    async def test_connect_discovers_resources(self):
        client = _make_client()
        await client.connect()
        assert len(client.get_resources()) > 0

    async def test_connect_no_tool_discovery(self):
        cfg = _make_config(enable_tool_discovery=False)
        client = _make_client(config=cfg)
        await client.connect()
        assert client.get_tools() == []

    async def test_connect_no_resource_discovery(self):
        cfg = _make_config(enable_resource_discovery=False)
        client = _make_client(config=cfg)
        await client.connect()
        assert client.get_resources() == []

    async def test_connect_with_session_id(self):
        client = _make_client()
        result = await client.connect(session_id="sess-001")
        assert result is True

    async def test_connect_fires_sync_handler(self):
        client = _make_client()
        handler = MagicMock()
        client.on_connect(handler)
        await client.connect()
        handler.assert_called_once()
        assert isinstance(handler.call_args[0][0], MCPServerConnection)

    async def test_connect_fires_async_handler(self):
        client = _make_client()
        async_handler = AsyncMock()
        client.on_connect(async_handler)
        await client.connect()
        async_handler.assert_called_once()

    async def test_connect_handler_error_does_not_raise(self):
        client = _make_client()

        def bad_handler(conn):
            raise RuntimeError("handler exploded")

        client.on_connect(bad_handler)
        result = await client.connect()
        assert result is True

    async def test_connect_server_info_populated(self):
        client = _make_client()
        await client.connect()
        info = client._connection.server_info
        assert info is not None
        assert info.name
        assert info.protocol_version == "2024-11-05"

    async def test_get_connection_info_after_connect(self):
        client = _make_client()
        await client.connect()
        info = client.get_connection_info()
        assert info is not None
        assert info["state"] == "ready"

    async def test_get_metrics_after_connect(self):
        client = _make_client()
        await client.connect()
        m = client.get_metrics()
        assert m["connection_attempts"] == 1
        assert m["successful_connections"] == 1
        assert m["state"] == "ready"


class TestMCPClientConnectRetry:
    async def test_retry_on_transient_failure(self):
        cfg = _make_config(retry_attempts=3, retry_delay_ms=1)
        mcp = MCPClient(config=cfg)
        call_count = 0
        original = mcp._establish_connection

        async def failing_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("transient")
            await original()

        mcp._establish_connection = failing_then_ok
        result = await mcp.connect()
        assert result is True
        assert call_count == 2

    async def test_all_retries_exhausted_raises(self):
        cfg = _make_config(retry_attempts=2, retry_delay_ms=1)
        client = MCPClient(config=cfg)

        async def always_fail():
            raise OSError("network down")

        client._establish_connection = always_fail
        with pytest.raises(MCPConnectionError, match="Failed to connect"):
            await client.connect()
        assert client._total_errors == 1
        assert client._connection.state == MCPClientState.ERROR

    async def test_single_attempt_no_retry_on_failure(self):
        cfg = _make_config(retry_attempts=1, retry_delay_ms=1)
        client = MCPClient(config=cfg)

        async def always_fail():
            raise RuntimeError("boom")

        client._establish_connection = always_fail
        with pytest.raises(MCPConnectionError):
            await client.connect()


class TestMCPClientDisconnect:
    async def test_disconnect_when_not_connected_noop(self):
        client = _make_client()
        await client.disconnect()

    async def test_disconnect_after_connect(self):
        client = _make_client()
        await client.connect()
        assert client.is_connected
        await client.disconnect()
        assert not client.is_connected
        assert client.state == MCPClientState.DISCONNECTED

    async def test_disconnect_cancels_pending_requests(self):
        client = _make_client()
        await client.connect()
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        client._pending_requests["fake-req"] = fut
        await client.disconnect()
        assert fut.cancelled()
        assert len(client._pending_requests) == 0

    async def test_disconnect_fires_sync_handler(self):
        client = _make_client()
        await client.connect()
        handler = MagicMock()
        client.on_disconnect(handler)
        await client.disconnect()
        handler.assert_called_once()

    async def test_disconnect_fires_async_handler(self):
        client = _make_client()
        await client.connect()
        async_handler = AsyncMock()
        client.on_disconnect(async_handler)
        await client.disconnect()
        async_handler.assert_called_once()

    async def test_disconnect_handler_error_does_not_raise(self):
        client = _make_client()
        await client.connect()

        def bad_handler(conn):
            raise ValueError("handler failed")

        client.on_disconnect(bad_handler)
        await client.disconnect()

    async def test_disconnect_with_session_id(self):
        client = _make_client()
        await client.connect()
        await client.disconnect(session_id="sess-xyz")
        assert client.state == MCPClientState.DISCONNECTED

    async def test_pending_future_already_done_not_cancelled(self):
        client = _make_client()
        await client.connect()
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        fut.set_result("done")
        client._pending_requests["done-req"] = fut
        await client.disconnect()
        assert not fut.cancelled()
        assert fut.result() == "done"
