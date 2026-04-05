"""Unit tests for MCP client operations (call_tool, read_resource, ping).
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.mcp_integration.client import (
    MCPConnectionError,
    MCPServerConnection,
)

from .helpers import _make_client

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMCPClientCallTool:
    async def test_call_tool_not_connected_raises(self):
        client = _make_client()
        with pytest.raises(MCPConnectionError, match="Not connected"):
            await client.call_tool("my_tool", {"arg": "val"})

    async def test_call_tool_success(self):
        client = _make_client()
        await client.connect()
        result = await client.call_tool("example_tool", {"input": "hello"})
        assert "content" in result
        assert result["isError"] is False

    async def test_call_tool_updates_last_activity(self):
        client = _make_client()
        await client.connect()
        before = datetime.now(UTC)
        await client.call_tool("example_tool", {})
        assert client._connection.last_activity is not None
        assert client._connection.last_activity >= before

    async def test_call_tool_with_session_id(self):
        client = _make_client()
        await client.connect()
        result = await client.call_tool("example_tool", {}, session_id="sess-abc")
        assert result is not None


class TestMCPClientReadResource:
    async def test_read_resource_not_connected_raises(self):
        client = _make_client()
        with pytest.raises(MCPConnectionError, match="Not connected"):
            await client.read_resource("example://resource")

    async def test_read_resource_success(self):
        client = _make_client()
        await client.connect()
        result = await client.read_resource("example://resource")
        assert "contents" in result

    async def test_read_resource_updates_last_activity(self):
        client = _make_client()
        await client.connect()
        before = datetime.now(UTC)
        await client.read_resource("example://resource")
        assert client._connection.last_activity >= before

    async def test_read_resource_with_session_id(self):
        client = _make_client()
        await client.connect()
        result = await client.read_resource("example://resource", session_id="sess-res")
        assert result is not None


class TestMCPClientPing:
    async def test_ping_not_connected_raises(self):
        client = _make_client()
        with pytest.raises(MCPConnectionError, match="Not connected"):
            await client.ping()

    async def test_ping_success(self):
        client = _make_client()
        await client.connect()
        result = await client.ping()
        assert result["status"] == "ok"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "timestamp" in result


class TestMCPClientSendRequest:
    async def test_send_request_increments_total_requests(self):
        client = _make_client()
        await client.connect()
        initial = client._total_requests
        await client.ping()
        assert client._total_requests > initial

    async def test_send_request_increments_connection_request_count(self):
        client = _make_client()
        await client.connect()
        prev = client._connection.request_count
        await client.ping()
        assert client._connection.request_count > prev

    async def test_send_request_unknown_method_returns_error(self):
        client = _make_client()
        await client.connect()
        with pytest.raises(MCPConnectionError, match="Method not found"):
            await client._send_request("unknown/method", {})

    async def test_send_request_error_increments_error_count(self):
        client = _make_client()
        await client.connect()
        with pytest.raises(MCPConnectionError):
            await client._send_request("bad/method", {})
        assert client._total_requests > 0

    async def test_send_request_timeout_increments_errors(self):
        client = _make_client()
        await client.connect()
        initial_errors = client._total_errors
        initial_conn_errors = client._connection.error_count

        async def timeout_simulate(req):
            raise TimeoutError()

        client._simulate_request = timeout_simulate
        with pytest.raises(MCPConnectionError, match="timed out"):
            await client._send_request("ping", {})
        assert client._total_errors == initial_errors + 1
        assert client._connection.error_count == initial_conn_errors + 1

    async def test_send_request_cleans_up_pending_on_success(self):
        client = _make_client()
        await client.connect()
        await client.ping()
        assert len(client._pending_requests) == 0

    async def test_send_request_cleans_up_pending_on_error(self):
        client = _make_client()
        await client.connect()
        with pytest.raises(MCPConnectionError):
            await client._send_request("unknown/method", {})
        assert len(client._pending_requests) == 0

    async def test_simulate_request_initialize(self):
        client = _make_client()
        client._connection = MCPServerConnection(server_id="x", config=client.config)
        req = {"jsonrpc": "2.0", "id": "1", "method": "initialize", "params": {}}
        resp = await client._simulate_request(req)
        assert resp["result"]["protocolVersion"] == "2024-11-05"

    async def test_simulate_request_tools_list(self):
        client = _make_client()
        client._connection = MCPServerConnection(server_id="x", config=client.config)
        req = {"jsonrpc": "2.0", "id": "2", "method": "tools/list", "params": {}}
        resp = await client._simulate_request(req)
        assert len(resp["result"]["tools"]) >= 1

    async def test_simulate_request_resources_list(self):
        client = _make_client()
        client._connection = MCPServerConnection(server_id="x", config=client.config)
        req = {"jsonrpc": "2.0", "id": "3", "method": "resources/list", "params": {}}
        resp = await client._simulate_request(req)
        assert len(resp["result"]["resources"]) >= 1

    async def test_simulate_request_tools_call(self):
        client = _make_client()
        client._connection = MCPServerConnection(server_id="x", config=client.config)
        req = {
            "jsonrpc": "2.0",
            "id": "4",
            "method": "tools/call",
            "params": {"name": "test", "arguments": {}},
        }
        resp = await client._simulate_request(req)
        assert resp["result"]["isError"] is False

    async def test_simulate_request_resources_read(self):
        client = _make_client()
        client._connection = MCPServerConnection(server_id="x", config=client.config)
        req = {
            "jsonrpc": "2.0",
            "id": "5",
            "method": "resources/read",
            "params": {"uri": "test://uri"},
        }
        resp = await client._simulate_request(req)
        assert resp["result"]["contents"][0]["uri"] == "test://uri"

    async def test_simulate_request_ping(self):
        client = _make_client()
        client._connection = MCPServerConnection(server_id="x", config=client.config)
        req = {"jsonrpc": "2.0", "id": "6", "method": "ping", "params": {}}
        resp = await client._simulate_request(req)
        assert resp["result"]["status"] == "ok"

    async def test_simulate_request_unknown_method(self):
        client = _make_client()
        client._connection = MCPServerConnection(server_id="x", config=client.config)
        req = {"jsonrpc": "2.0", "id": "7", "method": "no/such/method", "params": {}}
        resp = await client._simulate_request(req)
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    async def test_send_request_no_connection_still_tracks_requests(self):
        client = _make_client()

        async def fake_simulate(req):
            return {"jsonrpc": "2.0", "id": req["id"], "result": {"ok": True}}

        client._simulate_request = fake_simulate
        result = await client._send_request("custom", {})
        assert result == {"ok": True}
        assert client._total_requests == 1


class TestMCPClientSendNotification:
    async def test_send_notification_does_not_raise(self):
        client = _make_client()
        await client._send_notification("initialized", {})

    async def test_send_notification_arbitrary_method(self):
        client = _make_client()
        await client._send_notification("custom/notification", {"key": "val"})
