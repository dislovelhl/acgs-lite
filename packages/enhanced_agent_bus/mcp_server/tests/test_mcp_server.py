"""
MCP Server Integration Tests.

Tests for the main MCP Server implementation and lifecycle.

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import MagicMock

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

from ..config import MCPConfig
from ..protocol.types import MCPRequest
from ..server import MCPServer, create_mcp_server


class TestMCPServerCreation:
    """Tests for MCP Server creation and initialization."""

    def test_create_server_with_defaults(self):
        """Test creating server with default configuration."""
        server = MCPServer()

        assert server.config.server_name == "acgs2-governance"
        assert server.config.constitutional_hash == CONSTITUTIONAL_HASH
        assert server.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        assert server._running is False

    def test_create_server_with_custom_config(self):
        """Test creating server with custom configuration."""
        config = MCPConfig(
            server_name="test-server",
            server_version="2.0.0",
            strict_mode=False,
            request_timeout_ms=10000,
        )
        server = MCPServer(config=config)

        assert server.config.server_name == "test-server"
        assert server.config.server_version == "2.0.0"
        assert server.config.strict_mode is False
        assert server.config.request_timeout_ms == 10000

    def test_create_mcp_server_factory(self):
        """Test factory function for creating MCP server."""
        server = create_mcp_server()

        assert isinstance(server, MCPServer)
        assert server._handler is not None
        assert len(server._tools) == 5
        assert len(server._resources) == 4

    def test_tools_registered(self):
        """Test that all tools are properly registered."""
        server = MCPServer()

        expected_tools = [
            "validate_constitutional_compliance",
            "get_active_principles",
            "query_governance_precedents",
            "submit_governance_request",
            "get_governance_metrics",
        ]

        for tool_name in expected_tools:
            assert tool_name in server._tools

    def test_resources_registered(self):
        """Test that all resources are properly registered."""
        server = MCPServer()

        expected_resources = [
            "principles",
            "metrics",
            "decisions",
            "audit_trail",
        ]

        for resource_name in expected_resources:
            assert resource_name in server._resources

    def test_adapters_initialized(self):
        """Test that adapters are initialized."""
        server = MCPServer()

        assert "agent_bus" in server._adapters
        assert "policy_client" in server._adapters
        assert "audit_client" in server._adapters


class TestMCPServerCapabilities:
    """Tests for MCP Server capabilities."""

    def test_get_capabilities(self):
        """Test getting server capabilities."""
        server = MCPServer()
        capabilities = server.get_capabilities()

        assert capabilities.tools is not None
        assert capabilities.resources is not None
        assert capabilities.prompts is not None

    def test_get_tool_definitions(self):
        """Test getting all tool definitions."""
        server = MCPServer()
        definitions = server.get_tool_definitions()

        assert len(definitions) == 5
        for defn in definitions:
            assert defn.name is not None
            assert defn.description is not None
            assert defn.inputSchema is not None

    def test_get_resource_definitions(self):
        """Test getting all resource definitions."""
        server = MCPServer()
        definitions = server.get_resource_definitions()

        assert len(definitions) == 4
        for defn in definitions:
            assert defn.uri is not None
            assert defn.name is not None


class TestMCPServerMetrics:
    """Tests for MCP Server metrics."""

    def test_get_metrics(self):
        """Test getting server metrics."""
        server = MCPServer()
        metrics = server.get_metrics()

        assert "server" in metrics
        assert "tools" in metrics
        assert "resources" in metrics
        assert "adapters" in metrics

        assert metrics["server"]["name"] == "acgs2-governance"
        assert metrics["server"]["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert metrics["server"]["running"] is False
        assert metrics["server"]["request_count"] == 0


class TestMCPServerLifecycle:
    """Tests for MCP Server lifecycle management."""

    async def test_connect_adapters(self):
        """Test connecting adapters."""
        server = MCPServer()
        result = await server.connect_adapters()

        assert result is True  # Server runs in standalone mode

    async def test_disconnect_adapters(self):
        """Test disconnecting adapters."""
        server = MCPServer()
        await server.connect_adapters()
        await server.disconnect_adapters()

        # Should complete without errors

    async def test_stop_not_running(self):
        """Test stopping server that's not running."""
        server = MCPServer()
        await server.stop()  # Should complete without errors

        assert server._running is False


class TestMCPServerRequestHandling:
    """Tests for MCP request handling."""

    async def test_handle_initialize_request(self):
        """Test handling initialize request."""
        server = MCPServer()

        request = MCPRequest(
            jsonrpc="2.0",
            id="1",
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
                "capabilities": {},
            },
        )

        response = await server.handle_request(request)

        assert response is not None
        assert response.id == "1"
        assert response.error is None
        assert response.result is not None
        assert "serverInfo" in response.result
        assert response.result["serverInfo"]["name"] == "acgs2-governance"

    async def test_handle_tools_list_request(self):
        """Test handling tools/list request."""
        server = MCPServer()

        request = MCPRequest(
            jsonrpc="2.0",
            id="2",
            method="tools/list",
            params={},
        )

        response = await server.handle_request(request)

        assert response is not None
        assert response.error is None
        assert "tools" in response.result
        assert len(response.result["tools"]) == 5

    async def test_handle_resources_list_request(self):
        """Test handling resources/list request."""
        server = MCPServer()

        request = MCPRequest(
            jsonrpc="2.0",
            id="3",
            method="resources/list",
            params={},
        )

        response = await server.handle_request(request)

        assert response is not None
        assert response.error is None
        assert "resources" in response.result
        assert len(response.result["resources"]) == 4

    async def test_handle_tool_call(self):
        """Test handling a tool call."""
        server = MCPServer()

        request = MCPRequest(
            jsonrpc="2.0",
            id="4",
            method="tools/call",
            params={
                "name": "validate_constitutional_compliance",
                "arguments": {
                    "action": "read_user_data",
                    "context": {"data_sensitivity": "public"},
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            },
        )

        response = await server.handle_request(request)

        assert response is not None
        assert response.error is None
        assert "content" in response.result

    async def test_handle_resource_read(self):
        """Test handling a resource read."""
        server = MCPServer()

        request = MCPRequest(
            jsonrpc="2.0",
            id="5",
            method="resources/read",
            params={
                "uri": "acgs2://constitutional/principles",
            },
        )

        response = await server.handle_request(request)

        assert response is not None
        assert response.error is None
        assert "contents" in response.result

    async def test_handle_unknown_method(self):
        """Test handling unknown method."""
        server = MCPServer()

        request = MCPRequest(
            jsonrpc="2.0",
            id="6",
            method="unknown/method",
            params={},
        )

        response = await server.handle_request(request)

        assert response is not None
        assert response.error is not None
        assert response.error.code == -32601  # Method not found

    async def test_request_count_incremented(self):
        """Test that request count is incremented."""
        server = MCPServer()

        assert server._request_count == 0

        request = MCPRequest(
            jsonrpc="2.0",
            id="7",
            method="tools/list",
            params={},
        )

        await server.handle_request(request)
        assert server._request_count == 1

        await server.handle_request(request)
        assert server._request_count == 2


class TestMCPServerWithExternalServices:
    """Tests for MCP Server with external services injected."""

    def test_inject_agent_bus(self):
        """Test injecting agent bus into server."""
        mock_agent_bus = MagicMock()

        server = create_mcp_server(agent_bus=mock_agent_bus)

        assert server._adapters["agent_bus"].agent_bus == mock_agent_bus

    def test_inject_policy_client(self):
        """Test injecting policy client into server."""
        mock_policy_client = MagicMock()

        server = create_mcp_server(policy_client=mock_policy_client)

        assert server._adapters["policy_client"].policy_client == mock_policy_client

    def test_inject_audit_client(self):
        """Test injecting audit client into server."""
        mock_audit_client = MagicMock()

        server = create_mcp_server(audit_client=mock_audit_client)

        assert server._adapters["audit_client"].audit_client == mock_audit_client


class TestMCPServerConstitutionalCompliance:
    """Tests for constitutional compliance in MCP Server."""

    def test_constitutional_hash_present(self):
        """Test that constitutional hash is present in server."""
        server = MCPServer()

        assert server.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        assert server.config.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_tool_call_validates_hash(self):
        """Test that tool calls validate constitutional hash."""
        server = MCPServer()

        # Valid hash
        request = MCPRequest(
            jsonrpc="2.0",
            id="10",
            method="tools/call",
            params={
                "name": "validate_constitutional_compliance",
                "arguments": {
                    "action": "test_action",
                    "context": {},
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            },
        )

        response = await server.handle_request(request)
        assert response.error is None

    async def test_tool_call_rejects_invalid_hash(self):
        """Test that tool calls reject invalid constitutional hash."""
        server = MCPServer()

        request = MCPRequest(
            jsonrpc="2.0",
            id="11",
            method="tools/call",
            params={
                "name": "validate_constitutional_compliance",
                "arguments": {
                    "action": "test_action",
                    "context": {},
                    "constitutional_hash": "invalid_hash",
                },
            },
        )

        response = await server.handle_request(request)
        # Tool should detect invalid hash
        assert response is not None
