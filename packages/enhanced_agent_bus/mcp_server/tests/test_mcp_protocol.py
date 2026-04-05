"""
MCP Protocol Tests.

Tests for MCP protocol types and handler.

Constitutional Hash: 608508a9bd224290
"""

from unittest.mock import AsyncMock

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

from ..config import MCPConfig
from ..protocol.handler import MCPHandler
from ..protocol.types import (
    MCPError,
    MCPErrorCode,
    MCPRequest,
    MCPResponse,
    ResourceDefinition,
    ServerCapabilities,
    ToolDefinition,
    ToolInputSchema,
)


class TestMCPRequest:
    """Tests for MCPRequest."""

    def test_create_request(self):
        """Test creating an MCP request."""
        request = MCPRequest(
            jsonrpc="2.0",
            id="1",
            method="initialize",
            params={"key": "value"},
        )

        assert request.jsonrpc == "2.0"
        assert request.id == "1"
        assert request.method == "initialize"
        assert request.params == {"key": "value"}

    def test_request_from_dict(self):
        """Test creating request from dictionary."""
        data = {
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tools/list",
            "params": {},
        }

        request = MCPRequest.from_dict(data)

        assert request.id == "2"
        assert request.method == "tools/list"

    def test_request_to_dict(self):
        """Test converting request to dictionary."""
        request = MCPRequest(
            jsonrpc="2.0",
            id="3",
            method="resources/read",
            params={"uri": "test://resource"},
        )

        data = request.to_dict()

        assert data["jsonrpc"] == "2.0"
        assert data["id"] == "3"
        assert data["method"] == "resources/read"

    def test_notification_no_id(self):
        """Test that notifications have no id."""
        request = MCPRequest(
            jsonrpc="2.0",
            id=None,
            method="notifications/initialized",
            params={},
        )

        assert request.id is None
        assert request.is_notification() is True

    def test_request_has_id(self):
        """Test that requests have an id."""
        request = MCPRequest(
            jsonrpc="2.0",
            id="test-id",
            method="tools/call",
            params={},
        )

        assert request.is_notification() is False


class TestMCPResponse:
    """Tests for MCPResponse."""

    def test_create_success_response(self):
        """Test creating a success response."""
        response = MCPResponse(
            jsonrpc="2.0",
            id="1",
            result={"status": "ok"},
        )

        assert response.jsonrpc == "2.0"
        assert response.id == "1"
        assert response.result == {"status": "ok"}
        assert response.error is None

    def test_create_error_response(self):
        """Test creating an error response."""
        error = MCPError(
            code=-32600,
            message="Invalid Request",
            data=None,
        )

        response = MCPResponse(
            jsonrpc="2.0",
            id="2",
            error=error,
        )

        assert response.error is not None
        assert response.error.code == -32600
        assert response.result is None

    def test_response_to_dict(self):
        """Test converting response to dictionary."""
        response = MCPResponse(
            jsonrpc="2.0",
            id="3",
            result={"data": "test"},
        )

        data = response.to_dict()

        assert data["jsonrpc"] == "2.0"
        assert data["id"] == "3"
        assert data["result"] == {"data": "test"}
        assert "error" not in data


class TestMCPError:
    """Tests for MCPError."""

    def test_create_error(self):
        """Test creating an error."""
        error = MCPError(
            code=-32601,
            message="Method not found",
            data={"method": "unknown"},
        )

        assert error.code == -32601
        assert error.message == "Method not found"
        assert error.data == {"method": "unknown"}

    def test_constitutional_violation_error(self):
        """Test creating constitutional violation error."""
        error = MCPError.constitutional_violation(
            reason="Invalid hash provided",
            context={"provided": "wrong_hash"},
        )

        assert error.code == MCPErrorCode.CONSTITUTIONAL_VIOLATION.value
        assert "Constitutional violation" in error.message
        assert error.data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_governance_denied_error(self):
        """Test creating governance denied error."""
        error = MCPError.governance_denied(
            reason="Action violates safety principles",
            violations=[{"principle": "safety", "severity": "high"}],
        )

        assert error.code == MCPErrorCode.GOVERNANCE_DENIED.value
        assert "Governance denied" in error.message

    def test_validation_failed_error(self):
        """Test creating validation failed error."""
        error = MCPError.validation_failed(
            field="action",
            reason="Action cannot be empty",
        )

        assert error.code == MCPErrorCode.VALIDATION_FAILED.value

    def test_error_to_dict(self):
        """Test converting error to dictionary."""
        error = MCPError(
            code=-32700,
            message="Parse error",
            data={"line": 1},
        )

        data = error.to_dict()

        assert data["code"] == -32700
        assert data["message"] == "Parse error"
        assert data["data"] == {"line": 1}


class TestToolDefinition:
    """Tests for ToolDefinition."""

    def test_create_tool_definition(self):
        """Test creating a tool definition."""
        definition = ToolDefinition(
            name="test_tool",
            description="A test tool",
            inputSchema={
                "type": "object",
                "properties": {
                    "param1": {"type": "string"},
                },
                "required": ["param1"],
            },
        )

        assert definition.name == "test_tool"
        assert definition.description == "A test tool"
        assert "properties" in definition.inputSchema

    def test_tool_definition_to_dict(self):
        """Test converting tool definition to dictionary."""
        # Test with dict inputSchema
        definition = ToolDefinition(
            name="validate",
            description="Validate action",
            inputSchema={"type": "object"},
            constitutional_required=True,
        )

        data = definition.to_dict()

        assert data["name"] == "validate"
        assert data["description"] == "Validate action"
        assert data["inputSchema"] == {"type": "object"}

    def test_tool_definition_to_dict_with_schema_object(self):
        """Test converting tool definition with ToolInputSchema to dictionary."""
        definition = ToolDefinition(
            name="validate",
            description="Validate action",
            inputSchema=ToolInputSchema(
                type="object",
                properties={"action": {"type": "string"}},
                required=["action"],
            ),
            constitutional_required=True,
        )

        data = definition.to_dict()

        assert data["name"] == "validate"
        assert data["description"] == "Validate action"
        assert data["inputSchema"]["type"] == "object"
        assert "action" in data["inputSchema"]["properties"]


class TestResourceDefinition:
    """Tests for ResourceDefinition."""

    def test_create_resource_definition(self):
        """Test creating a resource definition."""
        definition = ResourceDefinition(
            uri="acgs2://test/resource",
            name="Test Resource",
            description="A test resource",
            mimeType="application/json",
        )

        assert definition.uri == "acgs2://test/resource"
        assert definition.name == "Test Resource"
        assert definition.mimeType == "application/json"

    def test_resource_definition_to_dict(self):
        """Test converting resource definition to dictionary."""
        definition = ResourceDefinition(
            uri="acgs2://governance/metrics",
            name="Metrics",
            description="Governance metrics",
            mimeType="application/json",
            constitutional_scope="read",
        )

        data = definition.to_dict()

        assert data["uri"] == "acgs2://governance/metrics"
        assert data["name"] == "Metrics"


class TestServerCapabilities:
    """Tests for ServerCapabilities."""

    def test_create_capabilities(self):
        """Test creating server capabilities."""
        capabilities = ServerCapabilities(
            tools={"listChanged": True},
            resources={"subscribe": True, "listChanged": True},
            prompts={"listChanged": False},
            logging={},
        )

        assert capabilities.tools["listChanged"] is True
        assert capabilities.resources["subscribe"] is True

    def test_capabilities_to_dict(self):
        """Test converting capabilities to dictionary."""
        capabilities = ServerCapabilities(
            tools={"listChanged": True},
            resources={"subscribe": False},
            prompts={},
            logging={},
        )

        data = capabilities.to_dict()

        assert "tools" in data
        assert "resources" in data


class TestMCPHandler:
    """Tests for MCPHandler."""

    def test_create_handler(self):
        """Test creating an MCP handler."""
        config = MCPConfig()
        handler = MCPHandler(config)

        assert handler.PROTOCOL_VERSION == "2024-11-05"
        assert handler.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_register_tool(self):
        """Test registering a tool."""
        config = MCPConfig()
        handler = MCPHandler(config)

        definition = ToolDefinition(
            name="custom_tool",
            description="Custom tool",
            inputSchema={"type": "object"},
        )

        async def tool_handler(params):
            return {"result": "ok"}

        handler.register_tool(definition, tool_handler)

        assert "custom_tool" in handler._tools

    def test_register_resource(self):
        """Test registering a resource."""
        config = MCPConfig()
        handler = MCPHandler(config)

        definition = ResourceDefinition(
            uri="custom://resource",
            name="Custom",
            description="Custom resource",
            mimeType="application/json",
        )

        async def resource_handler(params):
            return "{}"

        handler.register_resource(definition, resource_handler)

        assert "custom://resource" in handler._resources

    async def test_handle_initialize(self):
        """Test handling initialize request."""
        config = MCPConfig()
        handler = MCPHandler(config)

        request = MCPRequest(
            jsonrpc="2.0",
            id="1",
            method="initialize",
            params={
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test", "version": "1.0"},
                "capabilities": {},
            },
        )

        response = await handler.handle_request(request)

        assert response is not None
        assert response.error is None
        assert "protocolVersion" in response.result
        assert "serverInfo" in response.result

    async def test_handle_tools_list(self):
        """Test handling tools/list request."""
        config = MCPConfig()
        handler = MCPHandler(config)

        # Register a tool
        definition = ToolDefinition(
            name="test_tool",
            description="Test",
            inputSchema={"type": "object"},
        )
        handler.register_tool(definition, AsyncMock())

        request = MCPRequest(
            jsonrpc="2.0",
            id="2",
            method="tools/list",
            params={},
        )

        response = await handler.handle_request(request)

        assert response is not None
        assert "tools" in response.result
        assert len(response.result["tools"]) >= 1

    async def test_handle_resources_list(self):
        """Test handling resources/list request."""
        config = MCPConfig()
        handler = MCPHandler(config)

        # Register a resource
        definition = ResourceDefinition(
            uri="test://resource",
            name="Test",
            description="Test resource",
            mimeType="text/plain",
        )
        handler.register_resource(definition, AsyncMock(return_value="data"))

        request = MCPRequest(
            jsonrpc="2.0",
            id="3",
            method="resources/list",
            params={},
        )

        response = await handler.handle_request(request)

        assert response is not None
        assert "resources" in response.result

    async def test_handle_tool_call(self):
        """Test handling tool call."""
        config = MCPConfig()
        handler = MCPHandler(config)

        # Register a tool
        definition = ToolDefinition(
            name="echo",
            description="Echo tool",
            inputSchema={"type": "object", "properties": {"message": {"type": "string"}}},
        )

        async def echo_handler(args):
            return {"echo": args.get("message", "")}

        handler.register_tool(definition, echo_handler)

        request = MCPRequest(
            jsonrpc="2.0",
            id="4",
            method="tools/call",
            params={
                "name": "echo",
                "arguments": {"message": "hello"},
            },
        )

        response = await handler.handle_request(request)

        assert response is not None
        assert response.error is None
        assert "content" in response.result

    async def test_handle_resource_read(self):
        """Test handling resource read."""
        config = MCPConfig()
        handler = MCPHandler(config)

        # Register a resource
        definition = ResourceDefinition(
            uri="data://test",
            name="Test Data",
            description="Test data resource",
            mimeType="application/json",
        )

        async def read_handler(params):
            return '{"data": "test"}'

        handler.register_resource(definition, read_handler)

        request = MCPRequest(
            jsonrpc="2.0",
            id="5",
            method="resources/read",
            params={"uri": "data://test"},
        )

        response = await handler.handle_request(request)

        assert response is not None
        assert response.error is None
        assert "contents" in response.result

    async def test_handle_unknown_method(self):
        """Test handling unknown method."""
        config = MCPConfig()
        handler = MCPHandler(config)

        request = MCPRequest(
            jsonrpc="2.0",
            id="6",
            method="unknown/method",
            params={},
        )

        response = await handler.handle_request(request)

        assert response is not None
        assert response.error is not None
        assert response.error.code == -32601

    async def test_handle_notification(self):
        """Test handling notification (no response expected)."""
        config = MCPConfig()
        handler = MCPHandler(config)

        request = MCPRequest(
            jsonrpc="2.0",
            id=None,
            method="initialized",
            params={},
        )

        response = await handler.handle_request(request)

        # Notifications should not receive responses
        assert response is None

    async def test_constitutional_hash_injection(self):
        """Test that constitutional hash is injected for required tools."""
        config = MCPConfig(strict_mode=True)
        handler = MCPHandler(config)

        # Register a constitutional-required tool
        definition = ToolDefinition(
            name="constitutional_tool",
            description="Requires constitutional hash",
            inputSchema={"type": "object"},
            constitutional_required=True,
        )

        received_params = {}

        async def tool_handler(args):
            received_params.update(args)
            return {"result": "ok"}

        handler.register_tool(definition, tool_handler)

        request = MCPRequest(
            jsonrpc="2.0",
            id="7",
            method="tools/call",
            params={
                "name": "constitutional_tool",
                "arguments": {"test": "value"},
            },
        )

        await handler.handle_request(request)

        # In strict mode, constitutional hash should be injected
        assert "_constitutional_hash" in received_params
        assert received_params["_constitutional_hash"] == CONSTITUTIONAL_HASH
