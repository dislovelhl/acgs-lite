"""
MCP Server Tests.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from .conftest import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMCPIntegrationConfig:
    """Tests for MCPIntegrationConfig."""

    def test_create_config(self):
        """Test creating server config."""
        from ...mcp_integration.server import MCPIntegrationConfig

        config = MCPIntegrationConfig(
            server_name="test-mcp-server",
            port=9000,
            strict_mode=True,
        )

        assert config.server_name == "test-mcp-server"
        assert config.port == 9000
        assert config.strict_mode is True
        assert config.constitutional_hash == CONSTITUTIONAL_HASH


class TestMCPIntegrationServer:
    """Tests for MCPIntegrationServer."""

    @pytest.fixture
    def server(self):
        """Create server fixture."""
        from ...mcp_integration.server import (
            MCPIntegrationConfig,
            MCPIntegrationServer,
        )

        config = MCPIntegrationConfig(
            server_name="test-server",
            enable_maci=False,  # test-only: MACI off — testing MCP integration
        )
        return MCPIntegrationServer(config=config)

    async def test_start_stop(self, server):
        """Test starting and stopping server."""
        await server.start()
        assert server.state.value == "running"

        await server.stop()
        assert server.state.value == "stopped"

    async def test_handle_initialize(self, server):
        """Test handling initialize request."""
        await server.start()

        request = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test-client", "version": "1.0"},
                "capabilities": {},
            },
        }

        response = await server.handle_request(request)

        assert response is not None
        assert response["id"] == "1"
        assert "result" in response
        assert "serverInfo" in response["result"]

    async def test_handle_tools_list(self, server):
        """Test handling tools/list request."""
        await server.start()

        request = {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tools/list",
            "params": {},
        }

        response = await server.handle_request(request)

        assert response is not None
        assert "tools" in response["result"]
        # Server has built-in tools
        assert len(response["result"]["tools"]) >= 3

    async def test_handle_resources_list(self, server):
        """Test handling resources/list request."""
        await server.start()

        request = {
            "jsonrpc": "2.0",
            "id": "3",
            "method": "resources/list",
            "params": {},
        }

        response = await server.handle_request(request)

        assert response is not None
        assert "resources" in response["result"]
        # Server has built-in resources
        assert len(response["result"]["resources"]) >= 3

    async def test_handle_tool_call(self, server):
        """Test handling tools/call request."""
        await server.start()

        request = {
            "jsonrpc": "2.0",
            "id": "4",
            "method": "tools/call",
            "params": {
                "name": "validate_constitutional_compliance",
                "arguments": {
                    "action": "read_data",
                    "context": {"data_sensitivity": "public"},
                },
            },
        }

        response = await server.handle_request(request)

        assert response is not None
        assert "result" in response
        assert "content" in response["result"]

    async def test_handle_resource_read(self, server):
        """Test handling resources/read request."""
        await server.start()

        request = {
            "jsonrpc": "2.0",
            "id": "5",
            "method": "resources/read",
            "params": {
                "uri": "acgs2://constitutional/principles",
            },
        }

        response = await server.handle_request(request)

        assert response is not None
        assert "contents" in response["result"]

    async def test_handle_ping(self, server):
        """Test handling ping request."""
        await server.start()

        request = {
            "jsonrpc": "2.0",
            "id": "6",
            "method": "ping",
            "params": {},
        }

        response = await server.handle_request(request)

        assert response is not None
        assert response["result"]["status"] == "ok"
        assert response["result"]["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_handle_unknown_method(self, server):
        """Test handling unknown method."""
        await server.start()

        request = {
            "jsonrpc": "2.0",
            "id": "7",
            "method": "unknown/method",
            "params": {},
        }

        response = await server.handle_request(request)

        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32601

    async def test_handle_invalid_jsonrpc(self, server):
        """Test handling invalid JSON-RPC version."""
        await server.start()

        request = {
            "jsonrpc": "1.0",
            "id": "8",
            "method": "ping",
            "params": {},
        }

        response = await server.handle_request(request)

        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == -32600

    async def test_register_custom_tool(self, server):
        """Test registering a custom tool."""
        from ...mcp_integration.server import InternalTool

        async def custom_handler(args):
            return {"custom": "result"}

        tool = InternalTool(
            name="custom_tool",
            description="A custom tool",
            input_schema={"type": "object"},
            handler=custom_handler,
        )

        success = server.register_tool(tool)

        assert success is True

        # Verify tool is registered
        tools = server.get_tools()
        assert any(t["name"] == "custom_tool" for t in tools)

    async def test_register_custom_resource(self, server):
        """Test registering a custom resource."""
        from ...mcp_integration.server import InternalResource

        async def custom_handler(params):
            return {"custom": "data"}

        resource = InternalResource(
            uri="custom://resource",
            name="Custom Resource",
            description="A custom resource",
            handler=custom_handler,
        )

        success = server.register_resource(resource)

        assert success is True

        # Verify resource is registered
        resources = server.get_resources()
        assert any(r["uri"] == "custom://resource" for r in resources)

    def test_get_metrics(self, server):
        """Test getting server metrics."""
        metrics = server.get_metrics()

        assert "total_requests" in metrics
        assert "tools_registered" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_governance_validate(self, server):
        """Test governance/validate method."""
        await server.start()

        request = {
            "jsonrpc": "2.0",
            "id": "9",
            "method": "governance/validate",
            "params": {
                "action": "safe_action",
                "context": {},
            },
        }

        response = await server.handle_request(request)

        assert response is not None
        assert "result" in response
        assert "compliant" in response["result"]

    async def test_constitutional_status(self, server):
        """Test constitutional/status method."""
        await server.start()

        request = {
            "jsonrpc": "2.0",
            "id": "10",
            "method": "constitutional/status",
            "params": {},
        }

        response = await server.handle_request(request)

        assert response is not None
        assert response["result"]["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert response["result"]["hash_verified"] is True

    def test_get_audit_log(self, server):
        """Test getting audit log."""
        audit_log = server.get_audit_log()

        assert isinstance(audit_log, list)
