"""
Comprehensive pytest test file for mcp_integration/server.py.

Targets full coverage (≥95%) of all classes, methods, and code paths.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from enhanced_agent_bus.mcp_integration.server import (
    InternalResource,
    InternalTool,
    MCPIntegrationConfig,
    MCPIntegrationServer,
    MCPServerMetrics,
    MCPServerState,
    TransportType,
    create_mcp_integration_server,
)
from enhanced_agent_bus.observability.structured_logging import get_logger

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _noop_handler(args):
    return {}


def _make_server(
    *,
    enable_maci: bool = False,
    strict_mode: bool = True,
    enable_audit: bool = True,
    log_requests: bool = True,
    enable_tools: bool = True,
    enable_resources: bool = True,
    enable_prompts: bool = True,
) -> MCPIntegrationServer:
    config = MCPIntegrationConfig(
        server_name="test-server",
        enable_maci=enable_maci,
        strict_mode=strict_mode,
        enable_audit_logging=enable_audit,
        log_requests=log_requests,
        enable_tools=enable_tools,
        enable_resources=enable_resources,
        enable_prompts=enable_prompts,
    )
    return MCPIntegrationServer(config=config)


def _rpc(method: str, params: dict | None = None, req_id: str | int | None = "r1") -> dict:
    req: dict = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if req_id is not None:
        req["id"] = req_id
    return req


def _notification(method: str, params: dict | None = None) -> dict:
    """JSON-RPC notification — no 'id' field."""
    return {"jsonrpc": "2.0", "method": method, "params": params or {}}


# ---------------------------------------------------------------------------
# MCPServerState enum
# ---------------------------------------------------------------------------


class TestMCPServerStateEnum:
    def test_all_states_present(self):
        values = {s.value for s in MCPServerState}
        assert values == {"stopped", "starting", "running", "stopping", "error"}

    def test_state_values_are_strings(self):
        for state in MCPServerState:
            assert isinstance(state.value, str)

    def test_state_inequality(self):
        assert MCPServerState.STOPPED != MCPServerState.RUNNING
        assert MCPServerState.RUNNING == MCPServerState.RUNNING

    def test_error_state(self):
        assert MCPServerState.ERROR.value == "error"


# ---------------------------------------------------------------------------
# TransportType enum
# ---------------------------------------------------------------------------


class TestTransportTypeEnum:
    def test_all_transport_types(self):
        values = {t.value for t in TransportType}
        assert values == {"stdio", "sse", "http", "websocket"}

    def test_transport_type_values(self):
        assert TransportType.STDIO.value == "stdio"
        assert TransportType.SSE.value == "sse"
        assert TransportType.HTTP.value == "http"
        assert TransportType.WEBSOCKET.value == "websocket"


# ---------------------------------------------------------------------------
# MCPIntegrationConfig
# ---------------------------------------------------------------------------


class TestMCPIntegrationConfig:
    def test_default_values(self):
        config = MCPIntegrationConfig()
        assert config.server_name == "acgs2-mcp-integration"
        assert config.server_version == "1.0.0"
        assert config.transport_type == TransportType.HTTP
        assert config.host == "127.0.0.1"
        assert config.port == 8090
        assert config.enable_tools is True
        assert config.enable_resources is True
        assert config.enable_prompts is True
        assert config.enable_maci is True
        assert config.enable_audit_logging is True
        assert config.strict_mode is True
        assert config.max_connections == 1000
        assert config.request_timeout_ms == 30000
        assert config.log_requests is True
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_metadata_default_is_empty_dict(self):
        config = MCPIntegrationConfig()
        assert config.metadata == {}

    def test_custom_metadata(self):
        config = MCPIntegrationConfig(metadata={"env": "test"})
        assert config.metadata["env"] == "test"

    def test_custom_transport(self):
        config = MCPIntegrationConfig(transport_type=TransportType.STDIO)
        assert config.transport_type == TransportType.STDIO

    def test_custom_port(self):
        config = MCPIntegrationConfig(port=9000)
        assert config.port == 9000

    def test_disable_features(self):
        config = MCPIntegrationConfig(
            enable_tools=False,
            enable_resources=False,
            enable_prompts=False,
            enable_maci=False,
            enable_audit_logging=False,
            strict_mode=False,
            log_requests=False,
        )
        assert config.enable_tools is False
        assert config.enable_resources is False
        assert config.enable_prompts is False
        assert config.enable_maci is False
        assert config.enable_audit_logging is False
        assert config.strict_mode is False
        assert config.log_requests is False


# ---------------------------------------------------------------------------
# MCPServerMetrics
# ---------------------------------------------------------------------------


class TestMCPServerMetrics:
    def test_to_dict_no_start_time(self):
        m = MCPServerMetrics()
        d = m.to_dict()
        assert d["start_time"] is None
        assert d["uptime_seconds"] == 0
        assert d["total_requests"] == 0
        assert d["success_rate"] == 0.0
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_with_start_time(self):
        m = MCPServerMetrics()
        m.start_time = datetime.now(UTC)
        m.total_requests = 10
        m.successful_requests = 8
        d = m.to_dict()
        assert d["start_time"] is not None
        assert d["uptime_seconds"] >= 0
        assert d["success_rate"] == pytest.approx(0.8)

    def test_to_dict_success_rate_zero_when_no_requests(self):
        m = MCPServerMetrics()
        m.total_requests = 0
        assert m.to_dict()["success_rate"] == 0.0

    def test_to_dict_all_counter_fields(self):
        m = MCPServerMetrics()
        m.total_requests = 5
        m.successful_requests = 3
        m.failed_requests = 2
        m.active_connections = 1
        m.tools_registered = 4
        m.resources_registered = 2
        m.total_tool_calls = 10
        m.total_resource_reads = 7
        m.average_latency_ms = 3.14
        d = m.to_dict()
        assert d["failed_requests"] == 2
        assert d["active_connections"] == 1
        assert d["tools_registered"] == 4
        assert d["resources_registered"] == 2
        assert d["total_tool_calls"] == 10
        assert d["total_resource_reads"] == 7
        assert d["average_latency_ms"] == pytest.approx(3.14)

    def test_constitutional_hash_in_metrics(self):
        m = MCPServerMetrics()
        assert m.constitutional_hash == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# InternalTool
# ---------------------------------------------------------------------------


class TestInternalTool:
    def test_to_mcp_definition(self):
        tool = InternalTool(
            name="my_tool",
            description="Test tool",
            input_schema={"type": "object"},
            handler=_noop_handler,
        )
        defn = tool.to_mcp_definition()
        assert defn["name"] == "my_tool"
        assert defn["description"] == "Test tool"
        assert defn["inputSchema"] == {"type": "object"}

    def test_default_fields(self):
        tool = InternalTool(
            name="t",
            description="d",
            input_schema={},
            handler=_noop_handler,
        )
        assert tool.constitutional_required is True
        assert tool.maci_role is None
        assert tool.capabilities == []
        assert tool.risk_level == "medium"
        assert tool.metadata == {}

    def test_custom_fields(self):
        tool = InternalTool(
            name="risky",
            description="desc",
            input_schema={},
            handler=_noop_handler,
            constitutional_required=False,
            capabilities=["admin"],
            risk_level="high",
            metadata={"owner": "ops"},
        )
        assert tool.constitutional_required is False
        assert "admin" in tool.capabilities
        assert tool.risk_level == "high"
        assert tool.metadata["owner"] == "ops"


# ---------------------------------------------------------------------------
# InternalResource
# ---------------------------------------------------------------------------


class TestInternalResource:
    def test_to_mcp_definition(self):
        res = InternalResource(
            uri="acgs2://test/res",
            name="Test Resource",
            description="A resource",
        )
        defn = res.to_mcp_definition()
        assert defn["uri"] == "acgs2://test/res"
        assert defn["name"] == "Test Resource"
        assert defn["description"] == "A resource"
        assert defn["mimeType"] == "application/json"

    def test_default_fields(self):
        res = InternalResource(uri="u", name="n", description="d")
        assert res.mime_type == "application/json"
        assert res.handler is None
        assert res.constitutional_scope == "read"
        assert res.subscribe_supported is False
        assert res.metadata == {}

    def test_custom_mime_type(self):
        res = InternalResource(uri="u", name="n", description="d", mime_type="text/plain")
        assert res.to_mcp_definition()["mimeType"] == "text/plain"


# ---------------------------------------------------------------------------
# MCPIntegrationServer — construction & initialization
# ---------------------------------------------------------------------------


class TestMCPIntegrationServerInit:
    def test_default_construction(self):
        server = MCPIntegrationServer()
        assert server._state == MCPServerState.STOPPED
        assert server.config.server_name == "acgs2-mcp-integration"
        assert server.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_custom_config(self):
        config = MCPIntegrationConfig(server_name="custom")
        server = MCPIntegrationServer(config=config)
        assert server.config.server_name == "custom"

    def test_builtin_tools_registered(self):
        server = _make_server()
        tool_names = list(server._tools.keys())
        assert "validate_constitutional_compliance" in tool_names
        assert "get_governance_metrics" in tool_names
        assert "get_constitutional_status" in tool_names

    def test_builtin_resources_registered(self):
        server = _make_server()
        uris = list(server._resources.keys())
        assert "acgs2://constitutional/principles" in uris
        assert "acgs2://governance/metrics" in uris
        assert "acgs2://governance/audit" in uris

    def test_metrics_initialized(self):
        server = _make_server()
        assert server._metrics.tools_registered == len(server._tools)
        assert server._metrics.resources_registered == len(server._resources)

    def test_method_handlers_registered(self):
        server = _make_server()
        expected = [
            "initialize",
            "initialized",
            "ping",
            "tools/list",
            "tools/call",
            "resources/list",
            "resources/read",
            "resources/subscribe",
            "prompts/list",
            "prompts/get",
            "logging/setLevel",
            "governance/validate",
            "governance/request",
            "constitutional/status",
        ]
        for method in expected:
            assert method in server._method_handlers

    def test_with_validator_and_maci(self):
        validator = MagicMock()
        maci = MagicMock()
        server = MCPIntegrationServer(validator=validator, maci_enforcer=maci)
        assert server.validator is validator
        assert server.maci_enforcer is maci

    def test_with_tool_registry(self):
        registry = MagicMock()
        server = MCPIntegrationServer(tool_registry=registry)
        assert server.tool_registry is registry


# ---------------------------------------------------------------------------
# register_tool / unregister_tool
# ---------------------------------------------------------------------------


class TestRegisterTool:
    def test_register_new_tool(self):
        server = _make_server()
        initial_count = len(server._tools)
        tool = InternalTool(
            name="new_tool", description="d", input_schema={}, handler=_noop_handler
        )
        result = server.register_tool(tool)
        assert result is True
        assert len(server._tools) == initial_count + 1
        assert server._metrics.tools_registered == len(server._tools)

    def test_register_updates_existing_tool(self, caplog):
        server = _make_server()
        tool1 = InternalTool(
            name="dup_tool", description="first", input_schema={}, handler=_noop_handler
        )
        tool2 = InternalTool(
            name="dup_tool", description="second", input_schema={}, handler=_noop_handler
        )
        server.register_tool(tool1)
        with caplog.at_level(logging.WARNING):
            server.register_tool(tool2)
        assert server._tools["dup_tool"].description == "second"
        assert "already registered" in caplog.text

    def test_unregister_existing_tool(self):
        server = _make_server()
        tool = InternalTool(
            name="temp_tool", description="d", input_schema={}, handler=_noop_handler
        )
        server.register_tool(tool)
        result = server.unregister_tool("temp_tool")
        assert result is True
        assert "temp_tool" not in server._tools
        assert server._metrics.tools_registered == len(server._tools)

    def test_unregister_nonexistent_tool(self):
        server = _make_server()
        result = server.unregister_tool("nonexistent")
        assert result is False


# ---------------------------------------------------------------------------
# register_resource / unregister_resource
# ---------------------------------------------------------------------------


class TestRegisterResource:
    def test_register_new_resource(self):
        server = _make_server()
        initial_count = len(server._resources)
        res = InternalResource(uri="acgs2://new/res", name="New", description="d")
        result = server.register_resource(res)
        assert result is True
        assert len(server._resources) == initial_count + 1
        assert server._metrics.resources_registered == len(server._resources)

    def test_register_updates_existing_resource(self, caplog):
        server = _make_server()
        res1 = InternalResource(uri="acgs2://dup", name="First", description="d1")
        res2 = InternalResource(uri="acgs2://dup", name="Second", description="d2")
        server.register_resource(res1)
        with caplog.at_level(logging.WARNING):
            server.register_resource(res2)
        assert server._resources["acgs2://dup"].name == "Second"
        assert "already registered" in caplog.text

    def test_unregister_existing_resource(self):
        server = _make_server()
        res = InternalResource(uri="acgs2://temp", name="Temp", description="d")
        server.register_resource(res)
        result = server.unregister_resource("acgs2://temp")
        assert result is True
        assert "acgs2://temp" not in server._resources
        assert server._metrics.resources_registered == len(server._resources)

    def test_unregister_nonexistent_resource(self):
        server = _make_server()
        result = server.unregister_resource("acgs2://does-not-exist")
        assert result is False


# ---------------------------------------------------------------------------
# Server lifecycle: start / stop
# ---------------------------------------------------------------------------


class TestServerLifecycle:
    async def test_start_sets_state_to_running(self):
        server = _make_server()
        await server.start()
        assert server._state == MCPServerState.RUNNING
        assert server._metrics.start_time is not None

    async def test_start_already_running_is_idempotent(self, caplog):
        server = _make_server()
        await server.start()
        with caplog.at_level(logging.WARNING):
            await server.start()
        assert "already running" in caplog.text
        assert server._state == MCPServerState.RUNNING

    async def test_stop_sets_state_to_stopped(self):
        server = _make_server()
        await server.start()
        await server.stop()
        assert server._state == MCPServerState.STOPPED

    async def test_stop_when_not_running_is_noop(self):
        server = _make_server()
        # Should not raise
        await server.stop()
        assert server._state == MCPServerState.STOPPED

    async def test_stop_closes_connections(self):
        server = _make_server()
        await server.start()
        # Add a fake connection manually
        server._connections["conn-1"] = {"id": "conn-1"}
        server._metrics.active_connections = 1
        await server.stop()
        assert len(server._connections) == 0
        assert server._state == MCPServerState.STOPPED

    async def test_stop_sets_shutdown_event(self):
        server = _make_server()
        await server.start()
        assert server._shutdown_event is not None
        await server.stop()
        assert server._shutdown_event.is_set()

    async def test_stop_without_start_time_no_error(self):
        """Stop server that was started — verify uptime logged even when start_time is None."""
        server = _make_server()
        await server.start()
        # Force start_time to None to exercise else branch in stop
        server._metrics.start_time = None
        await server.stop()
        assert server._state == MCPServerState.STOPPED

    async def test_audit_event_logged_on_start(self):
        server = _make_server()
        await server.start()
        actions = [e["action"] for e in server._audit_log]
        assert "server_start" in actions

    async def test_audit_event_logged_on_stop(self):
        server = _make_server()
        await server.start()
        await server.stop()
        actions = [e["action"] for e in server._audit_log]
        assert "server_stop" in actions


# ---------------------------------------------------------------------------
# handle_request — core dispatch
# ---------------------------------------------------------------------------


class TestHandleRequest:
    async def test_invalid_jsonrpc_version_returns_error(self):
        server = _make_server()
        resp = await server.handle_request(
            {"jsonrpc": "1.0", "id": "x", "method": "ping", "params": {}}
        )
        assert resp["error"]["code"] == -32600

    async def test_unknown_method_returns_method_not_found(self):
        server = _make_server()
        resp = await server.handle_request(_rpc("no_such_method"))
        assert resp["error"]["code"] == -32601

    async def test_valid_ping_returns_result(self):
        server = _make_server()
        resp = await server.handle_request(_rpc("ping"))
        assert "result" in resp
        assert resp["result"]["status"] == "ok"

    async def test_notification_returns_none(self):
        """Requests without 'id' are notifications; response must be None."""
        server = _make_server()
        note = {"jsonrpc": "2.0", "method": "initialized", "params": {}}
        resp = await server.handle_request(note)
        assert resp is None

    async def test_metrics_incremented_on_success(self):
        server = _make_server()
        await server.handle_request(_rpc("ping"))
        assert server._metrics.total_requests == 1
        assert server._metrics.successful_requests == 1

    async def test_metrics_incremented_on_error(self):
        server = _make_server()
        # tools/call with unknown tool raises ValueError → failed_requests
        resp = await server.handle_request(_rpc("tools/call", {"name": "does_not_exist"}))
        assert resp["error"]["code"] == -32603
        assert server._metrics.failed_requests == 1

    async def test_log_requests_false_skips_debug(self):
        server = _make_server(log_requests=False)
        # Should not raise even when logging suppressed
        resp = await server.handle_request(_rpc("ping"))
        assert resp["result"]["status"] == "ok"

    async def test_error_response_notification_returns_none(self):
        """Even on exception, if no id → return None."""
        server = _make_server()
        note = {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "bad_tool"}}
        resp = await server.handle_request(note)
        assert resp is None
        assert server._metrics.failed_requests == 1

    async def test_handle_request_with_validator_valid(self):
        """Validator present, VALIDATORS_AVAILABLE=True, validation passes."""
        from enhanced_agent_bus.mcp_integration.validators import (
            MCPOperationContext,
            OperationType,
        )

        mock_validator = AsyncMock()
        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.issues = []
        mock_validator.validate.return_value = mock_result

        server = MCPIntegrationServer(validator=mock_validator)

        with patch("enhanced_agent_bus.mcp_integration.server.VALIDATORS_AVAILABLE", True):
            resp = await server.handle_request(_rpc("tools/list"))
        assert "result" in resp

    async def test_handle_request_with_validator_invalid_strict(self):
        """Validator fails in strict mode → returns -32001 error."""
        mock_validator = AsyncMock()
        mock_result = MagicMock()
        mock_result.is_valid = False
        issue = MagicMock()
        issue.message = "not allowed"
        mock_result.issues = [issue]
        mock_validator.validate.return_value = mock_result

        server = MCPIntegrationServer(
            validator=mock_validator,
            config=MCPIntegrationConfig(strict_mode=True),
        )

        with patch("enhanced_agent_bus.mcp_integration.server.VALIDATORS_AVAILABLE", True):
            resp = await server.handle_request(_rpc("tools/list"))
        assert resp["error"]["code"] == -32001
        assert server._metrics.failed_requests == 1

    async def test_handle_request_with_validator_invalid_non_strict(self):
        """Validator fails but strict_mode=False → request proceeds."""
        mock_validator = AsyncMock()
        mock_result = MagicMock()
        mock_result.is_valid = False
        issue = MagicMock()
        issue.message = "soft warning"
        mock_result.issues = [issue]
        mock_validator.validate.return_value = mock_result

        server = MCPIntegrationServer(
            validator=mock_validator,
            config=MCPIntegrationConfig(strict_mode=False),
        )

        with patch("enhanced_agent_bus.mcp_integration.server.VALIDATORS_AVAILABLE", True):
            resp = await server.handle_request(_rpc("tools/list"))
        # Should succeed since strict_mode is False
        assert "result" in resp


# ---------------------------------------------------------------------------
# _map_method_to_operation
# ---------------------------------------------------------------------------


class TestMapMethodToOperation:
    def test_mapped_methods(self):
        from enhanced_agent_bus.mcp_integration.validators import OperationType

        server = _make_server()
        mapping = {
            "tools/call": OperationType.TOOL_CALL,
            "tools/list": OperationType.TOOL_DISCOVER,
            "resources/read": OperationType.RESOURCE_READ,
            "resources/subscribe": OperationType.RESOURCE_SUBSCRIBE,
            "initialize": OperationType.PROTOCOL_INITIALIZE,
            "governance/validate": OperationType.GOVERNANCE_REQUEST,
            "governance/request": OperationType.GOVERNANCE_REQUEST,
        }
        for method, expected in mapping.items():
            result = server._map_method_to_operation(method)
            assert result == expected, f"Failed for {method}"

    def test_unmapped_method_returns_none(self):
        server = _make_server()
        result = server._map_method_to_operation("ping")
        assert result is None

    def test_another_unmapped_method(self):
        server = _make_server()
        result = server._map_method_to_operation("prompts/get")
        assert result is None


# ---------------------------------------------------------------------------
# _error_response
# ---------------------------------------------------------------------------


class TestErrorResponse:
    def test_error_response_structure(self):
        server = _make_server()
        resp = server._error_response("id-1", -32600, "Bad request")
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == "id-1"
        assert resp["error"]["code"] == -32600
        assert resp["error"]["message"] == "Bad request"
        assert resp["error"]["data"]["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_error_response_with_none_id(self):
        server = _make_server()
        resp = server._error_response(None, -32603, "Internal error")
        assert resp["id"] is None


# ---------------------------------------------------------------------------
# _track_latency
# ---------------------------------------------------------------------------


class TestTrackLatency:
    def test_single_sample(self):
        server = _make_server()
        server._track_latency(10.0)
        assert server._metrics.average_latency_ms == pytest.approx(10.0)

    def test_multiple_samples_average(self):
        server = _make_server()
        server._track_latency(10.0)
        server._track_latency(20.0)
        assert server._metrics.average_latency_ms == pytest.approx(15.0)

    def test_samples_capped_at_1000(self):
        server = _make_server()
        for i in range(1100):
            server._track_latency(float(i))
        assert len(server._latency_samples) == 1000


# ---------------------------------------------------------------------------
# _close_connection
# ---------------------------------------------------------------------------


class TestCloseConnection:
    async def test_close_existing_connection(self):
        server = _make_server()
        server._connections["c1"] = {"id": "c1"}
        server._metrics.active_connections = 1
        await server._close_connection("c1")
        assert "c1" not in server._connections
        assert server._metrics.active_connections == 0

    async def test_close_nonexistent_connection(self):
        server = _make_server()
        # Should not raise
        await server._close_connection("nonexistent")


# ---------------------------------------------------------------------------
# _log_audit_event
# ---------------------------------------------------------------------------


class TestLogAuditEvent:
    def test_audit_event_logged(self):
        server = _make_server()
        server._log_audit_event("test_action", details={"key": "val"}, agent_id="agent-1")
        entry = server._audit_log[-1]
        assert entry["action"] == "test_action"
        assert entry["details"]["key"] == "val"
        assert entry["agent_id"] == "agent-1"
        assert entry["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_audit_disabled_skips_logging(self):
        server = _make_server(enable_audit=False)
        initial_count = len(server._audit_log)
        server._log_audit_event("should_not_log")
        assert len(server._audit_log) == initial_count

    def test_audit_log_bounded_at_10000(self):
        server = _make_server()
        # Fill audit log beyond 10000 entries
        for i in range(10005):
            server._audit_log.append(
                {"action": f"e{i}", "details": {}, "constitutional_hash": CONSTITUTIONAL_HASH}
            )
        # Trigger another audit event to invoke the bounding logic
        server._log_audit_event("overflow_trigger")
        assert len(server._audit_log) <= 5001  # trimmed to last 5000 + new entry

    def test_audit_event_without_agent_id(self):
        server = _make_server()
        server._log_audit_event("no_agent")
        entry = server._audit_log[-1]
        assert entry["agent_id"] is None


# ---------------------------------------------------------------------------
# Protocol handlers
# ---------------------------------------------------------------------------


class TestHandleInitialize:
    async def test_returns_protocol_version(self):
        server = _make_server()
        result = await server._handle_initialize(
            {"clientInfo": {"name": "test-client", "version": "0.1"}}
        )
        assert result["protocolVersion"] == MCPIntegrationServer.PROTOCOL_VERSION

    async def test_capabilities_with_all_enabled(self):
        server = _make_server(enable_tools=True, enable_resources=True, enable_prompts=True)
        result = await server._handle_initialize({})
        caps = result["capabilities"]
        assert caps["tools"] is not None
        assert caps["resources"] is not None
        assert caps["prompts"] is not None

    async def test_capabilities_with_tools_disabled(self):
        server = _make_server(enable_tools=False, enable_resources=False, enable_prompts=False)
        result = await server._handle_initialize({})
        caps = result["capabilities"]
        assert caps["tools"] is None
        assert caps["resources"] is None
        assert caps["prompts"] is None

    async def test_server_info_in_result(self):
        server = _make_server()
        result = await server._handle_initialize({})
        assert result["serverInfo"]["name"] == server.config.server_name
        assert result["serverInfo"]["version"] == server.config.server_version

    async def test_constitutional_hash_in_capabilities(self):
        server = _make_server()
        result = await server._handle_initialize({})
        exp = result["capabilities"]["experimental"]
        assert exp["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert exp["constitutional_governance"] is True


class TestHandleInitialized:
    async def test_increments_active_connections(self):
        server = _make_server()
        await server._handle_initialized({})
        assert server._metrics.active_connections == 1


class TestHandlePing:
    async def test_ping_response(self):
        server = _make_server()
        result = await server._handle_ping({})
        assert result["status"] == "ok"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "timestamp" in result


class TestHandleToolsList:
    async def test_returns_tools_list(self):
        server = _make_server()
        result = await server._handle_tools_list({})
        assert "tools" in result
        assert isinstance(result["tools"], list)
        names = [t["name"] for t in result["tools"]]
        assert "validate_constitutional_compliance" in names

    async def test_via_handle_request(self):
        server = _make_server()
        resp = await server.handle_request(_rpc("tools/list"))
        assert "result" in resp
        assert "tools" in resp["result"]


class TestHandleToolsCall:
    async def test_call_known_tool(self):
        server = _make_server()
        resp = await server.handle_request(
            _rpc("tools/call", {"name": "get_constitutional_status", "arguments": {}})
        )
        assert "result" in resp
        assert "content" in resp["result"] or "status" in resp["result"]

    async def test_call_unknown_tool_returns_error(self):
        server = _make_server()
        resp = await server.handle_request(
            _rpc("tools/call", {"name": "ghost_tool", "arguments": {}})
        )
        assert resp["error"]["code"] == -32603

    async def test_metrics_incremented_on_tool_call(self):
        server = _make_server()
        initial = server._metrics.total_tool_calls
        await server.handle_request(
            _rpc("tools/call", {"name": "get_governance_metrics", "arguments": {}})
        )
        assert server._metrics.total_tool_calls == initial + 1

    async def test_tool_result_with_content_key_returned_as_is(self):
        """If handler returns dict with 'content' key, it's returned directly."""
        server = _make_server()

        async def handler_with_content(args):
            return {"content": [{"type": "text", "text": "hello"}], "isError": False}

        tool = InternalTool(
            name="content_tool", description="d", input_schema={}, handler=handler_with_content
        )
        server.register_tool(tool)
        resp = await server.handle_request(
            _rpc("tools/call", {"name": "content_tool", "arguments": {}})
        )
        assert "result" in resp
        assert "content" in resp["result"]

    async def test_tool_result_wrapped_when_no_content_key(self):
        """Handler returning dict without 'content' key gets wrapped."""
        server = _make_server()

        async def simple_handler(args):
            return {"value": 42}

        tool = InternalTool(
            name="simple_tool", description="d", input_schema={}, handler=simple_handler
        )
        server.register_tool(tool)
        resp = await server.handle_request(
            _rpc("tools/call", {"name": "simple_tool", "arguments": {}})
        )
        assert "result" in resp
        result = resp["result"]
        assert "content" in result
        assert result["isError"] is False

    async def test_tool_result_string_wrapped(self):
        """Handler returning non-dict value gets stringified."""
        server = _make_server()

        async def str_handler(args):
            return "plain string result"

        tool = InternalTool(name="str_tool", description="d", input_schema={}, handler=str_handler)
        server.register_tool(tool)
        resp = await server.handle_request(
            _rpc("tools/call", {"name": "str_tool", "arguments": {}})
        )
        assert "result" in resp
        assert resp["result"]["content"][0]["text"] == "plain string result"

    async def test_tool_call_with_maci_strict_mode_raises(self):
        """MACI enforcer raising error in strict mode propagates the exception."""
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.side_effect = ValueError("MACI blocked")

        with patch("enhanced_agent_bus.mcp_integration.server.MACI_AVAILABLE", True):
            server = MCPIntegrationServer(
                config=MCPIntegrationConfig(enable_maci=True, strict_mode=True),
                maci_enforcer=mock_enforcer,
            )

        resp = await server.handle_request(
            _rpc(
                "tools/call",
                {"name": "get_governance_metrics", "arguments": {"_agent_id": "agent-x"}},
            )
        )
        assert resp["error"]["code"] == -32603

    async def test_tool_call_with_maci_non_strict_continues(self):
        """MACI enforcer raising error in non-strict mode: warning logged, execution continues."""
        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action.side_effect = ValueError("MACI soft block")

        with patch("enhanced_agent_bus.mcp_integration.server.MACI_AVAILABLE", True):
            server = MCPIntegrationServer(
                config=MCPIntegrationConfig(enable_maci=True, strict_mode=False),
                maci_enforcer=mock_enforcer,
            )

        resp = await server.handle_request(
            _rpc(
                "tools/call",
                {"name": "get_governance_metrics", "arguments": {"_agent_id": "agent-y"}},
            )
        )
        # Non-strict: should succeed despite MACI error
        assert "result" in resp


class TestHandleResourcesList:
    async def test_returns_resources_list(self):
        server = _make_server()
        result = await server._handle_resources_list({})
        assert "resources" in result
        uris = [r["uri"] for r in result["resources"]]
        assert "acgs2://constitutional/principles" in uris

    async def test_via_handle_request(self):
        server = _make_server()
        resp = await server.handle_request(_rpc("resources/list"))
        assert "resources" in resp["result"]


class TestHandleResourcesRead:
    async def test_read_existing_resource(self):
        server = _make_server()
        resp = await server.handle_request(
            _rpc("resources/read", {"uri": "acgs2://constitutional/principles"})
        )
        assert "result" in resp
        assert "contents" in resp["result"]
        assert server._metrics.total_resource_reads >= 1

    async def test_read_unknown_resource_returns_error(self):
        server = _make_server()
        resp = await server.handle_request(_rpc("resources/read", {"uri": "acgs2://unknown"}))
        assert resp["error"]["code"] == -32603

    async def test_read_resource_without_handler(self):
        """Resource with no handler should return 'error' key in result."""
        server = _make_server()
        res = InternalResource(
            uri="acgs2://no-handler", name="No Handler", description="d", handler=None
        )
        server.register_resource(res)
        resp = await server.handle_request(_rpc("resources/read", {"uri": "acgs2://no-handler"}))
        assert "result" in resp
        contents = resp["result"]["contents"][0]["text"]
        assert "error" in contents

    async def test_metrics_incremented_on_resource_read(self):
        server = _make_server()
        initial = server._metrics.total_resource_reads
        await server._handle_resources_read({"uri": "acgs2://governance/metrics"})
        assert server._metrics.total_resource_reads == initial + 1


class TestHandleResourcesSubscribe:
    async def test_subscribe_returns_subscribed(self):
        server = _make_server()
        result = await server._handle_resources_subscribe({"uri": "acgs2://test"})
        assert result["subscribed"] is True

    async def test_via_handle_request(self):
        server = _make_server()
        resp = await server.handle_request(
            _rpc("resources/subscribe", {"uri": "acgs2://governance/metrics"})
        )
        assert resp["result"]["subscribed"] is True


class TestHandlePromptsList:
    async def test_empty_prompts_list(self):
        server = _make_server()
        result = await server._handle_prompts_list({})
        assert result["prompts"] == []

    async def test_prompts_list_with_entries(self):
        server = _make_server()
        server._prompts["p1"] = {"name": "p1", "description": "prompt 1"}
        result = await server._handle_prompts_list({})
        assert len(result["prompts"]) == 1


class TestHandlePromptsGet:
    async def test_get_existing_prompt(self):
        server = _make_server()
        server._prompts["my_prompt"] = {"name": "my_prompt", "messages": []}
        result = await server._handle_prompts_get({"name": "my_prompt"})
        assert result["name"] == "my_prompt"

    async def test_get_unknown_prompt_raises(self):
        server = _make_server()
        with pytest.raises(ValueError, match="Unknown prompt"):
            await server._handle_prompts_get({"name": "ghost"})

    async def test_via_handle_request_unknown_prompt_returns_error(self):
        server = _make_server()
        resp = await server.handle_request(_rpc("prompts/get", {"name": "ghost"}))
        assert resp["error"]["code"] == -32603


class TestHandleLoggingSetLevel:
    async def test_set_level_debug(self):
        server = _make_server()
        result = await server._handle_logging_set_level({"level": "debug"})
        assert result["level"] == "debug"

    async def test_set_level_warning(self):
        server = _make_server()
        result = await server._handle_logging_set_level({"level": "warning"})
        assert result["level"] == "warning"

    async def test_set_level_default_info(self):
        server = _make_server()
        result = await server._handle_logging_set_level({})
        assert result["level"] == "info"

    async def test_via_handle_request(self):
        server = _make_server()
        resp = await server.handle_request(_rpc("logging/setLevel", {"level": "error"}))
        assert resp["result"]["level"] == "error"


# ---------------------------------------------------------------------------
# ACGS-2 specific handlers
# ---------------------------------------------------------------------------


class TestHandleGovernanceValidate:
    async def test_returns_compliance_result(self):
        server = _make_server()
        result = await server._handle_governance_validate({"action": "test action", "context": {}})
        assert "compliant" in result
        assert "constitutional_hash" in result

    async def test_via_handle_request(self):
        server = _make_server()
        resp = await server.handle_request(
            _rpc("governance/validate", {"action": "safe action", "context": {}})
        )
        assert "result" in resp
        assert resp["result"]["compliant"] is True


class TestHandleGovernanceRequest:
    async def test_returns_pending_status(self):
        server = _make_server()
        result = await server._handle_governance_request({})
        assert result["status"] == "pending"
        assert "request_id" in result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_via_handle_request(self):
        server = _make_server()
        resp = await server.handle_request(_rpc("governance/request", {}))
        assert resp["result"]["status"] == "pending"


class TestHandleConstitutionalStatus:
    async def test_returns_status(self):
        server = _make_server()
        result = await server._handle_constitutional_status({})
        assert result["status"] == "active"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert result["hash_verified"] is True

    async def test_via_handle_request(self):
        server = _make_server()
        resp = await server.handle_request(_rpc("constitutional/status"))
        assert resp["result"]["status"] == "active"


# ---------------------------------------------------------------------------
# Built-in tool handlers
# ---------------------------------------------------------------------------


class TestToolValidateCompliance:
    async def test_compliant_action(self):
        server = _make_server()
        result = await server._tool_validate_compliance({"action": "help user", "context": {}})
        assert result["compliant"] is True
        assert result["violations"] == []
        assert result["confidence"] == 1.0

    async def test_harmful_action_not_compliant(self):
        server = _make_server()
        result = await server._tool_validate_compliance(
            {"action": "attack the server", "context": {}}
        )
        assert result["compliant"] is False
        assert len(result["violations"]) > 0
        assert result["confidence"] == 0.0

    async def test_sensitive_data_without_consent(self):
        server = _make_server()
        context = {"data_sensitivity": "confidential", "consent_obtained": False}
        result = await server._tool_validate_compliance({"action": "read data", "context": context})
        assert result["compliant"] is False
        privacy_violations = [v for v in result["violations"] if v["principle"] == "privacy"]
        assert len(privacy_violations) == 1
        assert len(result["recommendations"]) > 0

    async def test_sensitive_data_with_consent(self):
        server = _make_server()
        context = {"data_sensitivity": "confidential", "consent_obtained": True}
        result = await server._tool_validate_compliance({"action": "read data", "context": context})
        assert result["compliant"] is True

    async def test_restricted_data_without_consent(self):
        server = _make_server()
        context = {"data_sensitivity": "restricted", "consent_obtained": False}
        result = await server._tool_validate_compliance(
            {"action": "access restricted", "context": context}
        )
        assert result["compliant"] is False

    async def test_all_harmful_patterns(self):
        server = _make_server()
        harmful_words = ["harm", "attack", "exploit", "abuse", "deceive"]
        for word in harmful_words:
            result = await server._tool_validate_compliance(
                {"action": f"I will {word} something", "context": {}}
            )
            assert result["compliant"] is False, f"Expected non-compliant for '{word}'"

    async def test_constitutional_hash_in_result(self):
        server = _make_server()
        result = await server._tool_validate_compliance({"action": "safe", "context": {}})
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_timestamp_in_result(self):
        server = _make_server()
        result = await server._tool_validate_compliance({"action": "safe", "context": {}})
        assert "timestamp" in result


class TestToolGetMetrics:
    async def test_returns_metrics_dict(self):
        server = _make_server()
        result = await server._tool_get_metrics({})
        assert "total_requests" in result
        assert "constitutional_hash" in result

    async def test_include_audit(self):
        server = _make_server()
        server._log_audit_event("test_event")
        result = await server._tool_get_metrics({"include_audit": True})
        assert "recent_audit" in result
        assert isinstance(result["recent_audit"], list)

    async def test_no_audit_by_default(self):
        server = _make_server()
        result = await server._tool_get_metrics({})
        assert "recent_audit" not in result


class TestToolConstitutionalStatus:
    async def test_returns_status_dict(self):
        server = _make_server()
        result = await server._tool_constitutional_status({})
        assert result["status"] == "active"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert result["hash_verified"] is True
        assert "maci_enabled" in result
        assert "strict_mode" in result
        assert "server_state" in result
        assert "timestamp" in result

    async def test_server_state_reflects_current_state(self):
        server = _make_server()
        result = await server._tool_constitutional_status({})
        assert result["server_state"] == MCPServerState.STOPPED.value


# ---------------------------------------------------------------------------
# Built-in resource handlers
# ---------------------------------------------------------------------------


class TestResourcePrinciples:
    async def test_returns_principles(self):
        server = _make_server()
        result = await server._resource_principles({})
        assert "principles" in result
        principles = result["principles"]
        assert "beneficence" in principles
        assert "non_maleficence" in principles
        assert "privacy" in principles
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_via_resources_read(self):
        server = _make_server()
        resp = await server.handle_request(
            _rpc("resources/read", {"uri": "acgs2://constitutional/principles"})
        )
        assert "result" in resp
        text = resp["result"]["contents"][0]["text"]
        assert "beneficence" in text


class TestResourceMetrics:
    async def test_returns_metrics(self):
        server = _make_server()
        result = await server._resource_metrics({})
        assert "total_requests" in result


class TestResourceAudit:
    async def test_returns_audit_entries(self):
        server = _make_server()
        server._log_audit_event("audit_test")
        result = await server._resource_audit({})
        assert "entries" in result
        assert "total_entries" in result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_entries_limited_to_100(self):
        server = _make_server()
        for i in range(200):
            server._audit_log.append(
                {"action": f"e{i}", "details": {}, "constitutional_hash": CONSTITUTIONAL_HASH}
            )
        result = await server._resource_audit({})
        assert len(result["entries"]) == 100

    async def test_total_entries_reflects_full_count(self):
        server = _make_server()
        for i in range(50):
            server._audit_log.append(
                {"action": f"e{i}", "details": {}, "constitutional_hash": CONSTITUTIONAL_HASH}
            )
        result = await server._resource_audit({})
        assert result["total_entries"] == len(server._audit_log)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class TestPublicAPI:
    def test_state_property(self):
        server = _make_server()
        assert server.state == MCPServerState.STOPPED

    async def test_state_property_after_start(self):
        server = _make_server()
        await server.start()
        assert server.state == MCPServerState.RUNNING
        await server.stop()

    def test_get_metrics(self):
        server = _make_server()
        metrics = server.get_metrics()
        assert isinstance(metrics, dict)
        assert "total_requests" in metrics

    def test_get_tools(self):
        server = _make_server()
        tools = server.get_tools()
        assert isinstance(tools, list)
        assert len(tools) >= 3
        names = [t["name"] for t in tools]
        assert "validate_constitutional_compliance" in names

    def test_get_resources(self):
        server = _make_server()
        resources = server.get_resources()
        assert isinstance(resources, list)
        assert len(resources) >= 3

    def test_get_audit_log_default_limit(self):
        server = _make_server()
        for i in range(150):
            server._log_audit_event(f"evt-{i}")
        log = server.get_audit_log()
        assert len(log) == 100

    def test_get_audit_log_custom_limit(self):
        server = _make_server()
        for i in range(50):
            server._log_audit_event(f"evt-{i}")
        log = server.get_audit_log(limit=10)
        assert len(log) == 10

    def test_get_audit_log_fewer_than_limit(self):
        server = _make_server()
        server._log_audit_event("only_one")
        log = server.get_audit_log(limit=100)
        # server_start not logged since start() not called, but _log_audit_event called once
        assert len(log) >= 1

    def test_protocol_version_constant(self):
        assert MCPIntegrationServer.PROTOCOL_VERSION == "2024-11-05"

    def test_constitutional_hash_constant(self):
        assert MCPIntegrationServer.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


class TestCreateMCPIntegrationServer:
    def test_factory_returns_server(self):
        server = create_mcp_integration_server()
        assert isinstance(server, MCPIntegrationServer)
        assert server._state == MCPServerState.STOPPED

    def test_factory_with_config(self):
        config = MCPIntegrationConfig(server_name="factory-server")
        server = create_mcp_integration_server(config=config)
        assert server.config.server_name == "factory-server"

    def test_factory_with_validator(self):
        validator = MagicMock()
        server = create_mcp_integration_server(validator=validator)
        assert server.validator is validator

    def test_factory_with_tool_registry(self):
        registry = MagicMock()
        server = create_mcp_integration_server(tool_registry=registry)
        assert server.tool_registry is registry

    def test_factory_with_maci_enforcer(self):
        enforcer = MagicMock()
        server = create_mcp_integration_server(maci_enforcer=enforcer)
        assert server.maci_enforcer is enforcer

    def test_factory_with_all_args(self):
        config = MCPIntegrationConfig(server_name="full-factory")
        validator = MagicMock()
        registry = MagicMock()
        enforcer = MagicMock()
        server = create_mcp_integration_server(
            config=config, validator=validator, tool_registry=registry, maci_enforcer=enforcer
        )
        assert server.config.server_name == "full-factory"
        assert server.validator is validator
        assert server.tool_registry is registry
        assert server.maci_enforcer is enforcer


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports_importable(self):
        from enhanced_agent_bus.mcp_integration import server as srv_module

        for name in srv_module.__all__:
            assert hasattr(srv_module, name), f"Missing export: {name}"


# ---------------------------------------------------------------------------
# Edge cases and integration scenarios
# ---------------------------------------------------------------------------


class TestEdgeCases:
    async def test_handle_request_missing_params_uses_empty_dict(self):
        """Request without 'params' key should default to empty dict."""
        server = _make_server()
        req = {"jsonrpc": "2.0", "id": "x", "method": "ping"}  # no params
        resp = await server.handle_request(req)
        assert "result" in resp

    async def test_multiple_requests_track_latency(self):
        server = _make_server()
        for _ in range(5):
            await server.handle_request(_rpc("ping"))
        assert server._metrics.average_latency_ms >= 0
        assert server._metrics.total_requests == 5

    async def test_tool_audit_logged_on_call(self):
        server = _make_server()
        initial_audit_count = len(server._audit_log)
        await server.handle_request(
            _rpc("tools/call", {"name": "get_governance_metrics", "arguments": {"_agent_id": "a1"}})
        )
        assert len(server._audit_log) > initial_audit_count
        actions = [e["action"] for e in server._audit_log]
        assert "tool_call" in actions

    async def test_complete_lifecycle(self):
        """Integration: start → handle requests → stop."""
        server = _make_server()
        await server.start()
        assert server.state == MCPServerState.RUNNING

        resp = await server.handle_request(_rpc("ping"))
        assert resp["result"]["status"] == "ok"

        resp = await server.handle_request(_rpc("tools/list"))
        assert len(resp["result"]["tools"]) >= 3

        await server.stop()
        assert server.state == MCPServerState.STOPPED
        assert server._metrics.total_requests >= 2

    async def test_resources_read_mime_type_in_response(self):
        server = _make_server()
        resp = await server.handle_request(
            _rpc("resources/read", {"uri": "acgs2://governance/metrics"})
        )
        assert "result" in resp
        contents = resp["result"]["contents"][0]
        assert "mimeType" in contents
        assert contents["mimeType"] == "application/json"

    def test_server_has_lock(self):
        server = _make_server()
        assert server._lock is not None
        assert isinstance(server._lock, asyncio.Lock)

    async def test_governance_validate_via_handler(self):
        """Test _handle_governance_validate delegates to _tool_validate_compliance."""
        server = _make_server()
        result = await server._handle_governance_validate(
            {"action": "exploit vulnerability", "context": {}}
        )
        assert result["compliant"] is False

    async def test_constitutional_status_reflects_maci_config(self):
        server_with_maci = MCPIntegrationServer(config=MCPIntegrationConfig(enable_maci=True))
        result = await server_with_maci._tool_constitutional_status({})
        assert result["maci_enabled"] is True

        server_no_maci = MCPIntegrationServer(config=MCPIntegrationConfig(enable_maci=False))
        result2 = await server_no_maci._tool_constitutional_status({})
        assert result2["maci_enabled"] is False

    async def test_stop_with_no_shutdown_event(self):
        """Cover branch: _shutdown_event is None when stop() is called.

        Force _state to RUNNING without going through start() so
        _shutdown_event stays None — exercises the falsy branch at line 462.
        """
        server = _make_server()
        # Manually set state to RUNNING without calling start()
        server._state = MCPServerState.RUNNING
        # _shutdown_event stays None
        assert server._shutdown_event is None
        await server.stop()
        assert server._state == MCPServerState.STOPPED

    async def test_handle_request_with_validator_unmapped_method(self):
        """Cover branch: validator present, VALIDATORS_AVAILABLE=True, but
        method does not map to an OperationType (operation_type is None).

        'ping' is handled but has no entry in _map_method_to_operation, so
        the if-operation_type block is skipped and execution continues
        directly to handler(params) — exercises line 515->535.
        """
        mock_validator = AsyncMock()
        server = MCPIntegrationServer(validator=mock_validator)

        with patch("enhanced_agent_bus.mcp_integration.server.VALIDATORS_AVAILABLE", True):
            resp = await server.handle_request(_rpc("ping"))

        # Validator.validate should NOT have been called because operation_type is None
        mock_validator.validate.assert_not_called()
        assert resp["result"]["status"] == "ok"
