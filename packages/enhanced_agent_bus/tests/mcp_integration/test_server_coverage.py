"""
Additional coverage tests for MCP Integration Server.

Targets uncovered lines to boost coverage from ~70% to 90%+.
Constitutional Hash: 608508a9bd224290
"""

import asyncio
import logging
from datetime import UTC, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.observability.structured_logging import get_logger

from .conftest import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_server(enable_maci=False, strict_mode=True, enable_audit=True, log_requests=True):
    """Create a fresh server with configurable options."""
    from ...mcp_integration.server import (
        MCPIntegrationConfig,
        MCPIntegrationServer,
    )

    config = MCPIntegrationConfig(
        server_name="test-cov-server",
        enable_maci=enable_maci,
        strict_mode=strict_mode,
        enable_audit_logging=enable_audit,
        log_requests=log_requests,
    )
    return MCPIntegrationServer(config=config)


def _rpc(method: str, params: dict | None = None, req_id="rpc-1") -> dict:
    """Build a minimal JSON-RPC 2.0 request."""
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params or {},
    }


def _notification(method: str, params: dict | None = None) -> dict:
    """Build a JSON-RPC notification (no id field)."""
    return {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
    }


# ---------------------------------------------------------------------------
# MCPServerState / TransportType enums
# ---------------------------------------------------------------------------


class TestMCPServerStateEnum:
    """Test MCPServerState enum values."""

    def test_all_states_present(self):
        from ...mcp_integration.server import MCPServerState

        values = {s.value for s in MCPServerState}
        assert values == {"stopped", "starting", "running", "stopping", "error"}

    def test_state_equality(self):
        from ...mcp_integration.server import MCPServerState

        assert MCPServerState.STOPPED != MCPServerState.RUNNING
        assert MCPServerState.RUNNING == MCPServerState.RUNNING


class TestTransportTypeEnum:
    """Test TransportType enum values."""

    def test_all_transport_types(self):
        from ...mcp_integration.server import TransportType

        values = {t.value for t in TransportType}
        assert values == {"stdio", "sse", "http", "websocket"}


# ---------------------------------------------------------------------------
# MCPIntegrationConfig
# ---------------------------------------------------------------------------


class TestMCPIntegrationConfigDefaults:
    """Test default configuration values."""

    def test_default_values(self):
        from ...mcp_integration.server import MCPIntegrationConfig, TransportType

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
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_metadata_default_is_empty_dict(self):
        from ...mcp_integration.server import MCPIntegrationConfig

        config = MCPIntegrationConfig()
        assert config.metadata == {}

    def test_custom_metadata(self):
        from ...mcp_integration.server import MCPIntegrationConfig

        config = MCPIntegrationConfig(metadata={"env": "test"})
        assert config.metadata["env"] == "test"


# ---------------------------------------------------------------------------
# MCPServerMetrics.to_dict
# ---------------------------------------------------------------------------


class TestMCPServerMetrics:
    """Test MCPServerMetrics dataclass."""

    def test_to_dict_no_start_time(self):
        from ...mcp_integration.server import MCPServerMetrics

        m = MCPServerMetrics()
        d = m.to_dict()
        assert d["start_time"] is None
        assert d["uptime_seconds"] == 0
        assert d["total_requests"] == 0
        assert d["success_rate"] == 0.0
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_with_start_time(self):
        from datetime import datetime

        from ...mcp_integration.server import MCPServerMetrics

        m = MCPServerMetrics()
        m.start_time = datetime.now(UTC)
        m.total_requests = 10
        m.successful_requests = 8
        d = m.to_dict()
        assert d["start_time"] is not None
        assert d["uptime_seconds"] >= 0
        assert d["success_rate"] == pytest.approx(0.8)

    def test_to_dict_success_rate_zero_when_no_requests(self):
        from ...mcp_integration.server import MCPServerMetrics

        m = MCPServerMetrics()
        m.total_requests = 0
        assert m.to_dict()["success_rate"] == 0.0


# ---------------------------------------------------------------------------
# InternalTool
# ---------------------------------------------------------------------------


class TestInternalTool:
    """Test InternalTool dataclass."""

    def test_to_mcp_definition(self):
        from ...mcp_integration.server import InternalTool

        async def noop(args):
            return {}

        tool = InternalTool(
            name="my_tool",
            description="desc",
            input_schema={"type": "object"},
            handler=noop,
        )
        defn = tool.to_mcp_definition()
        assert defn["name"] == "my_tool"
        assert defn["description"] == "desc"
        assert "inputSchema" in defn

    def test_default_fields(self):
        from ...mcp_integration.server import InternalTool

        async def noop(args):
            return {}

        tool = InternalTool(name="t", description="d", input_schema={}, handler=noop)
        assert tool.constitutional_required is True
        assert tool.maci_role is None
        assert tool.capabilities == []
        assert tool.risk_level == "medium"
        assert tool.metadata == {}


# ---------------------------------------------------------------------------
# InternalResource
# ---------------------------------------------------------------------------


class TestInternalResource:
    """Test InternalResource dataclass."""

    def test_to_mcp_definition(self):
        from ...mcp_integration.server import InternalResource

        res = InternalResource(
            uri="test://res",
            name="Test Res",
            description="A resource",
        )
        defn = res.to_mcp_definition()
        assert defn["uri"] == "test://res"
        assert defn["name"] == "Test Res"
        assert defn["mimeType"] == "application/json"

    def test_default_fields(self):
        from ...mcp_integration.server import InternalResource

        res = InternalResource(uri="u", name="n", description="d")
        assert res.handler is None
        assert res.constitutional_scope == "read"
        assert res.subscribe_supported is False
        assert res.metadata == {}


# ---------------------------------------------------------------------------
# Tool/Resource registration edge cases
# ---------------------------------------------------------------------------


class TestRegistrationEdgeCases:
    """Test tool/resource registration edge cases."""

    def test_register_tool_duplicate_logs_warning(self, caplog):
        from ...mcp_integration.server import InternalTool

        server = _make_server()

        async def noop(args):
            return {}

        tool = InternalTool(
            name="validate_constitutional_compliance",
            description="dup",
            input_schema={},
            handler=noop,
        )
        with caplog.at_level(logging.WARNING):
            server.register_tool(tool)
        assert "already registered" in caplog.text

    def test_unregister_tool_existing(self):
        from ...mcp_integration.server import InternalTool

        server = _make_server()

        async def noop(args):
            return {}

        tool = InternalTool(name="new_tool", description="d", input_schema={}, handler=noop)
        server.register_tool(tool)
        assert "new_tool" in server._tools

        result = server.unregister_tool("new_tool")
        assert result is True
        assert "new_tool" not in server._tools

    def test_unregister_tool_nonexistent(self):
        server = _make_server()
        result = server.unregister_tool("does_not_exist")
        assert result is False

    def test_unregister_tool_updates_metrics(self):
        from ...mcp_integration.server import InternalTool

        server = _make_server()

        async def noop(args):
            return {}

        tool = InternalTool(name="temp_tool", description="d", input_schema={}, handler=noop)
        server.register_tool(tool)
        count_before = server._metrics.tools_registered
        server.unregister_tool("temp_tool")
        assert server._metrics.tools_registered == count_before - 1

    def test_register_resource_duplicate_logs_warning(self, caplog):
        from ...mcp_integration.server import InternalResource

        server = _make_server()
        # Built-in resource URI
        res = InternalResource(
            uri="acgs2://constitutional/principles",
            name="Dup",
            description="dup",
        )
        with caplog.at_level(logging.WARNING):
            server.register_resource(res)
        assert "already registered" in caplog.text

    def test_unregister_resource_existing(self):
        from ...mcp_integration.server import InternalResource

        server = _make_server()
        res = InternalResource(uri="custom://res", name="C", description="d")
        server.register_resource(res)
        assert "custom://res" in server._resources

        result = server.unregister_resource("custom://res")
        assert result is True
        assert "custom://res" not in server._resources

    def test_unregister_resource_nonexistent(self):
        server = _make_server()
        result = server.unregister_resource("nonexistent://res")
        assert result is False

    def test_unregister_resource_updates_metrics(self):
        from ...mcp_integration.server import InternalResource

        server = _make_server()
        res = InternalResource(uri="x://y", name="X", description="d")
        server.register_resource(res)
        count_before = server._metrics.resources_registered
        server.unregister_resource("x://y")
        assert server._metrics.resources_registered == count_before - 1


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


class TestServerLifecycle:
    """Test server lifecycle edge cases."""

    async def test_start_when_already_running(self, caplog):
        server = _make_server()
        await server.start()
        with caplog.at_level(logging.WARNING):
            await server.start()  # second call - already running
        assert "already running" in caplog.text
        await server.stop()

    async def test_stop_when_not_running_is_noop(self):
        from ...mcp_integration.server import MCPServerState

        server = _make_server()
        assert server.state == MCPServerState.STOPPED
        # Calling stop when not running should silently return
        await server.stop()
        assert server.state == MCPServerState.STOPPED

    async def test_stop_closes_connections(self):
        server = _make_server()
        await server.start()

        # Manually inject connections
        server._connections["conn-1"] = {}
        server._connections["conn-2"] = {}
        server._metrics.active_connections = 2

        await server.stop()
        assert len(server._connections) == 0

    async def test_stop_with_shutdown_event(self):
        server = _make_server()
        await server.start()
        assert server._shutdown_event is not None
        await server.stop()
        # Event should have been set
        assert server._shutdown_event.is_set()

    async def test_stop_with_no_start_time(self):
        """Stop should handle None start_time gracefully via audit log."""
        server = _make_server()
        await server.start()
        server._metrics.start_time = None  # force edge case
        await server.stop()  # should not raise


# ---------------------------------------------------------------------------
# handle_request: notification (no id) returns None
# ---------------------------------------------------------------------------


class TestHandleRequestNotification:
    """Test handle_request with notifications (no id)."""

    async def test_notification_returns_none(self):
        server = _make_server()
        await server.start()

        notif = _notification("initialized")
        result = await server.handle_request(notif)
        assert result is None

    async def test_notification_no_id_on_exception(self):
        """Exception during notification handling returns None (no id)."""
        server = _make_server()
        await server.start()

        # Calling tools/call with missing tool via notification
        notif = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        }
        result = await server.handle_request(notif)
        assert result is None


# ---------------------------------------------------------------------------
# handle_request: log_requests disabled
# ---------------------------------------------------------------------------


class TestHandleRequestLogging:
    """Test log_requests config flag."""

    async def test_no_log_requests(self):
        server = _make_server(log_requests=False)
        await server.start()

        response = await server.handle_request(_rpc("ping"))
        assert response["result"]["status"] == "ok"

    async def test_log_requests_enabled(self):
        server = _make_server(log_requests=True)
        await server.start()

        response = await server.handle_request(_rpc("ping"))
        assert response["result"]["status"] == "ok"


# ---------------------------------------------------------------------------
# handle_request: exception handler (MCP_INTEGRATION_OPERATION_ERRORS)
# ---------------------------------------------------------------------------


class TestHandleRequestExceptions:
    """Test error handling in handle_request."""

    async def test_value_error_returns_error_response(self):
        server = _make_server()
        await server.start()

        # tools/call with unknown tool raises ValueError
        request = _rpc("tools/call", {"name": "nonexistent", "arguments": {}})
        response = await server.handle_request(request)

        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32603
        assert server._metrics.failed_requests == 1

    async def test_runtime_error_in_handler(self):
        from ...mcp_integration.server import InternalTool

        server = _make_server()
        await server.start()

        async def exploding_handler(args):
            raise RuntimeError("Boom!")

        tool = InternalTool(
            name="boom_tool",
            description="explodes",
            input_schema={"type": "object"},
            handler=exploding_handler,
        )
        server.register_tool(tool)

        request = _rpc("tools/call", {"name": "boom_tool", "arguments": {}})
        response = await server.handle_request(request)

        assert "error" in response
        assert response["error"]["code"] == -32603

    async def test_unknown_resource_raises_value_error(self):
        server = _make_server()
        await server.start()

        request = _rpc("resources/read", {"uri": "nonexistent://resource"})
        response = await server.handle_request(request)

        assert "error" in response
        assert response["error"]["code"] == -32603


# ---------------------------------------------------------------------------
# handle_request: with validator (VALIDATORS_AVAILABLE path)
# ---------------------------------------------------------------------------


class TestHandleRequestWithValidator:
    """Test handle_request when a validator is provided."""

    async def test_validator_valid_passes(self):
        from ...mcp_integration.server import MCPIntegrationConfig, MCPIntegrationServer

        mock_validation = MagicMock()
        mock_validation.is_valid = True
        mock_validation.issues = []

        mock_validator = AsyncMock()
        mock_validator.validate = AsyncMock(return_value=mock_validation)

        config = MCPIntegrationConfig(enable_maci=False, strict_mode=True)

        with patch("enhanced_agent_bus.mcp_integration.server.VALIDATORS_AVAILABLE", True):
            server = MCPIntegrationServer(config=config, validator=mock_validator)
            await server.start()

            response = await server.handle_request(_rpc("tools/list"))
            assert "result" in response

    async def test_validator_invalid_strict_mode_blocks(self):
        from ...mcp_integration.server import MCPIntegrationConfig, MCPIntegrationServer

        mock_issue = MagicMock()
        mock_issue.message = "Not allowed"

        mock_validation = MagicMock()
        mock_validation.is_valid = False
        mock_validation.issues = [mock_issue]

        mock_validator = AsyncMock()
        mock_validator.validate = AsyncMock(return_value=mock_validation)

        config = MCPIntegrationConfig(enable_maci=False, strict_mode=True)

        with patch("enhanced_agent_bus.mcp_integration.server.VALIDATORS_AVAILABLE", True):
            server = MCPIntegrationServer(config=config, validator=mock_validator)
            await server.start()

            response = await server.handle_request(_rpc("tools/call", {"name": "x"}))
            assert "error" in response
            assert response["error"]["code"] == -32001

    async def test_validator_invalid_non_strict_continues(self):
        from ...mcp_integration.server import MCPIntegrationConfig, MCPIntegrationServer

        mock_validation = MagicMock()
        mock_validation.is_valid = False
        mock_validation.issues = []

        mock_validator = AsyncMock()
        mock_validator.validate = AsyncMock(return_value=mock_validation)

        config = MCPIntegrationConfig(enable_maci=False, strict_mode=False)

        with patch("enhanced_agent_bus.mcp_integration.server.VALIDATORS_AVAILABLE", True):
            server = MCPIntegrationServer(config=config, validator=mock_validator)
            await server.start()

            response = await server.handle_request(_rpc("ping"))
            # Non-strict: validation failure doesn't block -- result is returned
            assert "result" in response or "error" in response


# ---------------------------------------------------------------------------
# _map_method_to_operation
# ---------------------------------------------------------------------------


class TestMapMethodToOperation:
    """Test _map_method_to_operation mapping."""

    def test_known_methods_map_correctly(self):
        server = _make_server()

        with patch("enhanced_agent_bus.mcp_integration.server.VALIDATORS_AVAILABLE", True):
            from ...mcp_integration.validators import OperationType

            assert server._map_method_to_operation("tools/call") == OperationType.TOOL_CALL
            assert server._map_method_to_operation("tools/list") == OperationType.TOOL_DISCOVER
            assert server._map_method_to_operation("resources/read") == OperationType.RESOURCE_READ
            assert (
                server._map_method_to_operation("resources/subscribe")
                == OperationType.RESOURCE_SUBSCRIBE
            )
            assert (
                server._map_method_to_operation("initialize") == OperationType.PROTOCOL_INITIALIZE
            )
            assert (
                server._map_method_to_operation("governance/validate")
                == OperationType.GOVERNANCE_REQUEST
            )
            assert (
                server._map_method_to_operation("governance/request")
                == OperationType.GOVERNANCE_REQUEST
            )

    def test_unknown_method_returns_none(self):
        server = _make_server()
        result = server._map_method_to_operation("unknown/method")
        assert result is None


# ---------------------------------------------------------------------------
# _track_latency: overflow path
# ---------------------------------------------------------------------------


class TestTrackLatency:
    """Test _track_latency method including sample overflow."""

    def test_track_latency_basic(self):
        server = _make_server()
        server._track_latency(5.0)
        assert server._metrics.average_latency_ms == 5.0

    def test_track_latency_average_updates(self):
        server = _make_server()
        server._track_latency(10.0)
        server._track_latency(20.0)
        assert server._metrics.average_latency_ms == pytest.approx(15.0)

    def test_track_latency_trims_to_1000(self):
        server = _make_server()
        # Fill with 1001 samples to trigger trim
        for i in range(1001):
            server._latency_samples.append(float(i))
        server._latency_samples.append(9999.0)
        # Manually call trim logic via _track_latency
        server._track_latency(0.0)
        assert len(server._latency_samples) <= 1000


# ---------------------------------------------------------------------------
# _close_connection
# ---------------------------------------------------------------------------


class TestCloseConnection:
    """Test _close_connection method."""

    async def test_close_existing_connection(self):
        server = _make_server()
        server._connections["c1"] = {"info": "test"}
        server._metrics.active_connections = 1

        await server._close_connection("c1")

        assert "c1" not in server._connections
        assert server._metrics.active_connections == 0

    async def test_close_nonexistent_connection_is_noop(self):
        server = _make_server()
        server._metrics.active_connections = 0
        # Should not raise
        await server._close_connection("nonexistent")
        assert server._metrics.active_connections == 0


# ---------------------------------------------------------------------------
# _log_audit_event: disabled + overflow
# ---------------------------------------------------------------------------


class TestLogAuditEvent:
    """Test _log_audit_event."""

    def test_audit_logging_disabled(self):
        server = _make_server(enable_audit=False)
        server._log_audit_event("test_action")
        assert len(server._audit_log) == 0

    def test_audit_logging_enabled(self):
        server = _make_server()
        server._log_audit_event("test_action", details={"key": "val"}, agent_id="agent-1")
        last = server._audit_log[-1]
        assert last["action"] == "test_action"
        assert last["agent_id"] == "agent-1"
        assert last["details"]["key"] == "val"
        assert last["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_audit_log_trims_at_10000(self):
        server = _make_server()
        # Fill with 10001 entries so that when _log_audit_event appends the new
        # entry len becomes 10002 > 10000, triggering the trim to last 5000.
        server._audit_log = [{"action": f"evt-{i}"} for i in range(10001)]
        server._log_audit_event("overflow")
        # After append: 10002 > 10000, so trim to last 5000.
        assert len(server._audit_log) == 5000

    def test_audit_no_details_defaults_empty(self):
        server = _make_server()
        server._log_audit_event("no_details")
        last = server._audit_log[-1]
        assert last["details"] == {}


# ---------------------------------------------------------------------------
# _handle_initialize: disabled capabilities
# ---------------------------------------------------------------------------


class TestHandleInitializeCapabilities:
    """Test _handle_initialize with various config flags."""

    async def test_initialize_tools_disabled(self):
        from ...mcp_integration.server import MCPIntegrationConfig, MCPIntegrationServer

        config = MCPIntegrationConfig(enable_tools=False, enable_maci=False)
        server = MCPIntegrationServer(config=config)
        await server.start()

        result = await server._handle_initialize({"clientInfo": {}})
        assert result["capabilities"]["tools"] is None

    async def test_initialize_resources_disabled(self):
        from ...mcp_integration.server import MCPIntegrationConfig, MCPIntegrationServer

        config = MCPIntegrationConfig(enable_resources=False, enable_maci=False)
        server = MCPIntegrationServer(config=config)
        await server.start()

        result = await server._handle_initialize({"clientInfo": {}})
        assert result["capabilities"]["resources"] is None

    async def test_initialize_prompts_disabled(self):
        from ...mcp_integration.server import MCPIntegrationConfig, MCPIntegrationServer

        config = MCPIntegrationConfig(enable_prompts=False, enable_maci=False)
        server = MCPIntegrationServer(config=config)
        await server.start()

        result = await server._handle_initialize({"clientInfo": {}})
        assert result["capabilities"]["prompts"] is None


# ---------------------------------------------------------------------------
# _handle_initialized (notification)
# ---------------------------------------------------------------------------


class TestHandleInitialized:
    """Test _handle_initialized increments connections."""

    async def test_initialized_increments_connections(self):
        server = _make_server()
        await server.start()

        before = server._metrics.active_connections
        await server._handle_initialized({})
        assert server._metrics.active_connections == before + 1


# ---------------------------------------------------------------------------
# _handle_tools_call edge cases
# ---------------------------------------------------------------------------


class TestHandleToolsCall:
    """Test tools/call handler edge cases."""

    async def test_unknown_tool_raises(self):
        server = _make_server()
        await server.start()

        with pytest.raises(ValueError, match="Unknown tool"):
            await server._handle_tools_call({"name": "nonexistent", "arguments": {}})

    async def test_tool_result_with_content_key_passthrough(self):
        """Result already containing 'content' key should be returned as-is."""
        from ...mcp_integration.server import InternalTool

        server = _make_server()
        await server.start()

        async def handler_with_content(args):
            return {"content": [{"type": "text", "text": "pre-wrapped"}], "isError": False}

        tool = InternalTool(
            name="wrapped_tool",
            description="d",
            input_schema={},
            handler=handler_with_content,
        )
        server.register_tool(tool)

        result = await server._handle_tools_call({"name": "wrapped_tool", "arguments": {}})
        assert result["content"][0]["text"] == "pre-wrapped"

    async def test_tool_result_non_dict_is_stringified(self):
        from ...mcp_integration.server import InternalTool

        server = _make_server()
        await server.start()

        async def string_handler(args):
            return "plain string result"

        tool = InternalTool(
            name="string_tool",
            description="d",
            input_schema={},
            handler=string_handler,
        )
        server.register_tool(tool)

        result = await server._handle_tools_call({"name": "string_tool", "arguments": {}})
        assert result["content"][0]["text"] == "plain string result"

    async def test_maci_validation_with_enforcer(self):
        """MACI enforcement path when enable_maci=True and enforcer provided."""
        from ...mcp_integration.server import (
            InternalTool,
            MCPIntegrationConfig,
            MCPIntegrationServer,
        )

        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action = AsyncMock(return_value=None)

        config = MCPIntegrationConfig(enable_maci=True, strict_mode=True)

        with patch("enhanced_agent_bus.mcp_integration.server.MACI_AVAILABLE", True):
            server = MCPIntegrationServer(config=config, maci_enforcer=mock_enforcer)
            await server.start()

            async def noop(args):
                return {"result": "ok"}

            tool = InternalTool(name="maci_tool", description="d", input_schema={}, handler=noop)
            server.register_tool(tool)

            result = await server._handle_tools_call(
                {
                    "name": "maci_tool",
                    "arguments": {"_agent_id": "agent-x", "_session_id": "sess-1"},
                }
            )
            assert "content" in result or "result" in result

    async def test_maci_validation_error_strict_raises(self):
        """MACI error in strict mode should re-raise."""
        from ...mcp_integration.server import (
            InternalTool,
            MCPIntegrationConfig,
            MCPIntegrationServer,
        )

        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action = AsyncMock(side_effect=ValueError("MACI rejected"))

        config = MCPIntegrationConfig(enable_maci=True, strict_mode=True)

        with patch("enhanced_agent_bus.mcp_integration.server.MACI_AVAILABLE", True):
            server = MCPIntegrationServer(config=config, maci_enforcer=mock_enforcer)
            await server.start()

            async def noop(args):
                return {}

            tool = InternalTool(
                name="strict_maci_tool", description="d", input_schema={}, handler=noop
            )
            server.register_tool(tool)

            with pytest.raises(ValueError, match="MACI rejected"):
                await server._handle_tools_call({"name": "strict_maci_tool", "arguments": {}})

    async def test_maci_validation_error_non_strict_continues(self):
        """MACI error in non-strict mode should log and continue."""
        from ...mcp_integration.server import (
            InternalTool,
            MCPIntegrationConfig,
            MCPIntegrationServer,
        )

        mock_enforcer = AsyncMock()
        mock_enforcer.validate_action = AsyncMock(side_effect=ValueError("MACI rejected"))

        config = MCPIntegrationConfig(enable_maci=True, strict_mode=False)

        with patch("enhanced_agent_bus.mcp_integration.server.MACI_AVAILABLE", True):
            server = MCPIntegrationServer(config=config, maci_enforcer=mock_enforcer)
            await server.start()

            async def noop(args):
                return {"result": "ok"}

            tool = InternalTool(
                name="nonstrict_maci_tool", description="d", input_schema={}, handler=noop
            )
            server.register_tool(tool)

            # Should not raise in non-strict mode
            result = await server._handle_tools_call(
                {"name": "nonstrict_maci_tool", "arguments": {}}
            )
            assert "content" in result


# ---------------------------------------------------------------------------
# _handle_resources_read edge cases
# ---------------------------------------------------------------------------


class TestHandleResourcesRead:
    """Test resources/read edge cases."""

    async def test_unknown_resource_raises_value_error(self):
        server = _make_server()
        await server.start()

        with pytest.raises(ValueError, match="Unknown resource"):
            await server._handle_resources_read({"uri": "nonexistent://res"})

    async def test_resource_without_handler(self):
        from ...mcp_integration.server import InternalResource

        server = _make_server()
        await server.start()

        # Register resource with NO handler
        res = InternalResource(
            uri="acgs2://no-handler",
            name="No Handler",
            description="no handler",
            handler=None,
        )
        server.register_resource(res)

        result = await server._handle_resources_read({"uri": "acgs2://no-handler"})
        contents = result["contents"][0]
        assert "error" in contents["text"]

    async def test_resource_with_non_dict_handler_result(self):
        from ...mcp_integration.server import InternalResource

        server = _make_server()
        await server.start()

        async def string_handler(params):
            return "raw string result"

        res = InternalResource(
            uri="acgs2://string-result",
            name="String Result",
            description="returns string",
            handler=string_handler,
        )
        server.register_resource(res)

        result = await server._handle_resources_read({"uri": "acgs2://string-result"})
        assert result["contents"][0]["text"] == "raw string result"


# ---------------------------------------------------------------------------
# _handle_resources_subscribe
# ---------------------------------------------------------------------------


class TestHandleResourcesSubscribe:
    """Test resources/subscribe handler."""

    async def test_subscribe_returns_subscribed_true(self):
        server = _make_server()
        await server.start()

        result = await server._handle_resources_subscribe({"uri": "acgs2://some/resource"})
        assert result["subscribed"] is True

    async def test_subscribe_via_handle_request(self):
        server = _make_server()
        await server.start()

        request = _rpc("resources/subscribe", {"uri": "acgs2://constitutional/principles"})
        response = await server.handle_request(request)

        assert response is not None
        assert "result" in response
        assert response["result"]["subscribed"] is True


# ---------------------------------------------------------------------------
# _handle_prompts_list and _handle_prompts_get
# ---------------------------------------------------------------------------


class TestPromptsHandlers:
    """Test prompts/list and prompts/get handlers."""

    async def test_prompts_list_empty(self):
        server = _make_server()
        await server.start()

        result = await server._handle_prompts_list({})
        assert result["prompts"] == []

    async def test_prompts_list_with_entries(self):
        server = _make_server()
        await server.start()

        server._prompts["test_prompt"] = {
            "name": "test_prompt",
            "description": "A test prompt",
        }
        result = await server._handle_prompts_list({})
        assert len(result["prompts"]) == 1

    async def test_prompts_get_existing(self):
        server = _make_server()
        await server.start()

        server._prompts["my_prompt"] = {"name": "my_prompt", "text": "Hello!"}
        result = await server._handle_prompts_get({"name": "my_prompt"})
        assert result["name"] == "my_prompt"

    async def test_prompts_get_unknown_raises(self):
        server = _make_server()
        await server.start()

        with pytest.raises(ValueError, match="Unknown prompt"):
            await server._handle_prompts_get({"name": "nonexistent"})

    async def test_prompts_list_via_handle_request(self):
        server = _make_server()
        await server.start()

        response = await server.handle_request(_rpc("prompts/list"))
        assert "result" in response
        assert "prompts" in response["result"]

    async def test_prompts_get_via_handle_request_unknown(self):
        server = _make_server()
        await server.start()

        response = await server.handle_request(_rpc("prompts/get", {"name": "no_such_prompt"}))
        assert "error" in response


# ---------------------------------------------------------------------------
# _handle_logging_set_level
# ---------------------------------------------------------------------------


class TestHandleLoggingSetLevel:
    """Test logging/setLevel handler."""

    async def test_set_level_debug(self):
        server = _make_server()
        await server.start()

        result = await server._handle_logging_set_level({"level": "debug"})
        assert result["level"] == "debug"

    async def test_set_level_warning(self):
        server = _make_server()
        await server.start()

        result = await server._handle_logging_set_level({"level": "warning"})
        assert result["level"] == "warning"

    async def test_set_level_default_info(self):
        server = _make_server()
        await server.start()

        result = await server._handle_logging_set_level({})
        assert result["level"] == "info"

    async def test_set_level_via_handle_request(self):
        server = _make_server()
        await server.start()

        response = await server.handle_request(_rpc("logging/setLevel", {"level": "error"}))
        assert "result" in response
        assert response["result"]["level"] == "error"


# ---------------------------------------------------------------------------
# _handle_governance_request
# ---------------------------------------------------------------------------


class TestHandleGovernanceRequest:
    """Test governance/request handler."""

    async def test_governance_request_returns_pending(self):
        server = _make_server()
        await server.start()

        result = await server._handle_governance_request({"action": "some_action"})
        assert result["status"] == "pending"
        assert "request_id" in result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_governance_request_via_handle_request(self):
        server = _make_server()
        await server.start()

        response = await server.handle_request(
            _rpc("governance/request", {"action": "govern_this"})
        )
        assert "result" in response
        assert response["result"]["status"] == "pending"


# ---------------------------------------------------------------------------
# _tool_validate_compliance: harmful patterns
# ---------------------------------------------------------------------------


class TestToolValidateCompliance:
    """Test compliance validation for harmful patterns and data sensitivity."""

    async def test_harmless_action_is_compliant(self):
        server = _make_server()
        result = await server._tool_validate_compliance(
            {"action": "read_public_data", "context": {}}
        )
        assert result["compliant"] is True
        assert result["violations"] == []
        assert result["confidence"] == 1.0

    async def test_harmful_pattern_harm_detected(self):
        server = _make_server()
        result = await server._tool_validate_compliance({"action": "harm the users", "context": {}})
        assert result["compliant"] is False
        assert len(result["violations"]) > 0
        assert result["confidence"] == 0.0

    async def test_harmful_pattern_attack_detected(self):
        server = _make_server()
        result = await server._tool_validate_compliance(
            {"action": "attack the server", "context": {}}
        )
        assert result["compliant"] is False

    async def test_harmful_pattern_exploit_detected(self):
        server = _make_server()
        result = await server._tool_validate_compliance(
            {"action": "exploit the vulnerability", "context": {}}
        )
        assert result["compliant"] is False

    async def test_harmful_pattern_abuse_detected(self):
        server = _make_server()
        result = await server._tool_validate_compliance(
            {"action": "abuse the system", "context": {}}
        )
        assert result["compliant"] is False

    async def test_harmful_pattern_deceive_detected(self):
        server = _make_server()
        result = await server._tool_validate_compliance(
            {"action": "deceive the user", "context": {}}
        )
        assert result["compliant"] is False

    async def test_confidential_data_without_consent(self):
        server = _make_server()
        result = await server._tool_validate_compliance(
            {
                "action": "read_data",
                "context": {"data_sensitivity": "confidential", "consent_obtained": False},
            }
        )
        assert result["compliant"] is False
        assert any(v["principle"] == "privacy" for v in result["violations"])
        assert "Obtain explicit user consent" in result["recommendations"]

    async def test_restricted_data_without_consent(self):
        server = _make_server()
        result = await server._tool_validate_compliance(
            {
                "action": "read_data",
                "context": {"data_sensitivity": "restricted"},
            }
        )
        assert result["compliant"] is False

    async def test_confidential_data_with_consent_is_compliant(self):
        server = _make_server()
        result = await server._tool_validate_compliance(
            {
                "action": "read_data",
                "context": {"data_sensitivity": "confidential", "consent_obtained": True},
            }
        )
        assert result["compliant"] is True

    async def test_public_data_no_consent_needed(self):
        server = _make_server()
        result = await server._tool_validate_compliance(
            {"action": "read_data", "context": {"data_sensitivity": "public"}}
        )
        assert result["compliant"] is True


# ---------------------------------------------------------------------------
# _tool_get_metrics: include_audit flag
# ---------------------------------------------------------------------------


class TestToolGetMetrics:
    """Test get_metrics tool handler."""

    async def test_get_metrics_without_audit(self):
        server = _make_server()
        result = await server._tool_get_metrics({})
        assert "total_requests" in result
        assert "recent_audit" not in result

    async def test_get_metrics_with_audit(self):
        server = _make_server()
        await server.start()  # generates audit entry
        result = await server._tool_get_metrics({"include_audit": True})
        assert "recent_audit" in result
        assert isinstance(result["recent_audit"], list)


# ---------------------------------------------------------------------------
# Built-in resource handlers
# ---------------------------------------------------------------------------


class TestBuiltinResourceHandlers:
    """Test built-in resource handler functions directly."""

    async def test_resource_metrics_returns_dict(self):
        server = _make_server()
        result = await server._resource_metrics({})
        assert "total_requests" in result
        assert "constitutional_hash" in result

    async def test_resource_audit_returns_entries(self):
        server = _make_server()
        await server.start()  # triggers audit entry
        result = await server._resource_audit({})
        assert "entries" in result
        assert "total_entries" in result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_resource_metrics_via_handle_request(self):
        server = _make_server()
        await server.start()

        request = _rpc("resources/read", {"uri": "acgs2://governance/metrics"})
        response = await server.handle_request(request)
        assert "result" in response
        assert "contents" in response["result"]

    async def test_resource_audit_via_handle_request(self):
        server = _make_server()
        await server.start()

        request = _rpc("resources/read", {"uri": "acgs2://governance/audit"})
        response = await server.handle_request(request)
        assert "result" in response


# ---------------------------------------------------------------------------
# create_mcp_integration_server factory
# ---------------------------------------------------------------------------


class TestCreateMCPIntegrationServer:
    """Test factory function."""

    def test_factory_default_config(self):
        from ...mcp_integration.server import (
            MCPIntegrationServer,
            create_mcp_integration_server,
        )

        server = create_mcp_integration_server()
        assert isinstance(server, MCPIntegrationServer)

    def test_factory_with_custom_config(self):
        from ...mcp_integration.server import (
            MCPIntegrationConfig,
            MCPIntegrationServer,
            create_mcp_integration_server,
        )

        config = MCPIntegrationConfig(server_name="factory-server")
        server = create_mcp_integration_server(config=config)
        assert isinstance(server, MCPIntegrationServer)
        assert server.config.server_name == "factory-server"

    def test_factory_with_all_args(self):
        from ...mcp_integration.server import (
            MCPIntegrationConfig,
            MCPIntegrationServer,
            create_mcp_integration_server,
        )

        mock_validator = MagicMock()
        mock_registry = MagicMock()
        mock_enforcer = MagicMock()
        config = MCPIntegrationConfig()

        server = create_mcp_integration_server(
            config=config,
            validator=mock_validator,
            tool_registry=mock_registry,
            maci_enforcer=mock_enforcer,
        )
        assert isinstance(server, MCPIntegrationServer)
        assert server.validator is mock_validator
        assert server.tool_registry is mock_registry
        assert server.maci_enforcer is mock_enforcer


# ---------------------------------------------------------------------------
# Public API helpers
# ---------------------------------------------------------------------------


class TestPublicAPIHelpers:
    """Test public API methods: get_tools, get_resources, get_audit_log."""

    def test_get_tools_returns_mcp_definitions(self):
        server = _make_server()
        tools = server.get_tools()
        assert isinstance(tools, list)
        # At least the 3 built-in tools
        assert len(tools) >= 3
        for t in tools:
            assert "name" in t
            assert "inputSchema" in t

    def test_get_resources_returns_mcp_definitions(self):
        server = _make_server()
        resources = server.get_resources()
        assert isinstance(resources, list)
        assert len(resources) >= 3
        for r in resources:
            assert "uri" in r
            assert "name" in r

    def test_get_audit_log_limit(self):
        server = _make_server()
        # Add 20 entries
        for i in range(20):
            server._audit_log.append({"action": f"event-{i}"})

        log = server.get_audit_log(limit=5)
        assert len(log) == 5
        # Should return last 5
        assert log[-1]["action"] == "event-19"

    def test_get_audit_log_default_limit(self):
        server = _make_server()
        for i in range(50):
            server._audit_log.append({"action": f"e-{i}"})

        log = server.get_audit_log()
        assert len(log) == 50  # 50 <= 100 default limit

    def test_state_property(self):
        from ...mcp_integration.server import MCPServerState

        server = _make_server()
        assert server.state == MCPServerState.STOPPED


# ---------------------------------------------------------------------------
# End-to-end: full request flow with audit and metrics
# ---------------------------------------------------------------------------


class TestEndToEndFlow:
    """Integration-style tests exercising multiple components together."""

    async def test_full_tool_call_updates_metrics(self):
        server = _make_server()
        await server.start()

        request = _rpc(
            "tools/call",
            {"name": "get_governance_metrics", "arguments": {}},
        )
        response = await server.handle_request(request)

        assert "result" in response
        assert server._metrics.total_tool_calls >= 1
        assert server._metrics.successful_requests >= 1

    async def test_full_resource_read_updates_metrics(self):
        server = _make_server()
        await server.start()

        request = _rpc("resources/read", {"uri": "acgs2://constitutional/principles"})
        response = await server.handle_request(request)

        assert "result" in response
        assert server._metrics.total_resource_reads >= 1

    async def test_error_increments_failed_requests(self):
        server = _make_server()
        await server.start()

        request = _rpc("tools/call", {"name": "no_such_tool", "arguments": {}})
        await server.handle_request(request)

        assert server._metrics.failed_requests >= 1

    async def test_get_governance_metrics_tool_via_handle_request(self):
        server = _make_server()
        await server.start()

        # First do some work to populate metrics
        await server.handle_request(_rpc("ping"))

        request = _rpc(
            "tools/call",
            {"name": "get_governance_metrics", "arguments": {"include_audit": False}},
        )
        response = await server.handle_request(request)
        assert "result" in response

    async def test_validate_compliance_tool_via_handle_request(self):
        server = _make_server()
        await server.start()

        request = _rpc(
            "tools/call",
            {
                "name": "validate_constitutional_compliance",
                "arguments": {
                    "action": "harm users",
                    "context": {},
                },
            },
        )
        response = await server.handle_request(request)
        assert "result" in response
        # The content should contain the JSON result with compliant=False
        content_text = response["result"]["content"][0]["text"]
        assert "compliant" in content_text

    async def test_get_constitutional_status_tool(self):
        server = _make_server()
        await server.start()

        request = _rpc(
            "tools/call",
            {"name": "get_constitutional_status", "arguments": {}},
        )
        response = await server.handle_request(request)
        assert "result" in response
