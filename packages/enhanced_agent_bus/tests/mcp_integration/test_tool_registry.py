"""
MCP Tool Registry Tests.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from .conftest import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestExternalTool:
    """Tests for ExternalTool."""

    def test_create_tool(self):
        """Test creating an external tool."""
        from ...mcp_integration.tool_registry import (
            ExternalTool,
            ToolCapability,
            ToolInputSchema,
            ToolRiskLevel,
        )

        tool = ExternalTool(
            name="test_tool",
            description="A test tool",
            server_id="server-1",
            input_schema=ToolInputSchema(
                properties={"input": {"type": "string"}},
                required=["input"],
            ),
            capabilities=[ToolCapability.VALIDATION],
            risk_level=ToolRiskLevel.LOW,
        )

        assert tool.name == "test_tool"
        assert tool.server_id == "server-1"
        assert ToolCapability.VALIDATION in tool.capabilities
        assert tool.constitutional_hash == CONSTITUTIONAL_HASH

    def test_tool_to_dict(self):
        """Test tool serialization."""
        from ...mcp_integration.tool_registry import (
            ExternalTool,
            ToolInputSchema,
        )

        tool = ExternalTool(
            name="test_tool",
            description="A test tool",
            server_id="server-1",
            input_schema=ToolInputSchema(),
        )

        data = tool.to_dict()

        assert data["name"] == "test_tool"
        assert data["server_id"] == "server-1"
        assert "tool_id" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_tool_mcp_definition(self):
        """Test MCP tool definition format."""
        from ...mcp_integration.tool_registry import (
            ExternalTool,
            ToolInputSchema,
        )

        tool = ExternalTool(
            name="test_tool",
            description="A test tool",
            server_id="server-1",
            input_schema=ToolInputSchema(
                properties={"value": {"type": "integer"}},
            ),
        )

        defn = tool.to_mcp_definition()

        assert defn["name"] == "test_tool"
        assert defn["description"] == "A test tool"
        assert "inputSchema" in defn

    def test_tool_id_uses_fast_kernel_when_available(self, monkeypatch):
        """Tool ID generation uses fast kernel when available."""
        from ...mcp_integration import tool_registry as tool_registry_module
        from ...mcp_integration.tool_registry import ExternalTool, ToolInputSchema

        called = {"value": False}

        def _fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0xBEEF

        monkeypatch.setattr(tool_registry_module, "FAST_HASH_AVAILABLE", True)
        monkeypatch.setattr(
            tool_registry_module,
            "fast_hash",
            _fake_fast_hash,
            raising=False,
        )

        tool = ExternalTool(
            name="test_tool",
            description="A test tool",
            server_id="server-1",
            input_schema=ToolInputSchema(),
        )
        assert called["value"] is True
        assert tool.tool_id == "000000000000beef"

    def test_tool_id_falls_back_to_sha256_when_kernel_unavailable(self, monkeypatch):
        """Tool ID generation falls back to sha256 when kernel unavailable."""
        from ...mcp_integration import tool_registry as tool_registry_module
        from ...mcp_integration.tool_registry import ExternalTool, ToolInputSchema

        monkeypatch.setattr(tool_registry_module, "FAST_HASH_AVAILABLE", False)

        tool = ExternalTool(
            name="test_tool",
            description="A test tool",
            server_id="server-1",
            input_schema=ToolInputSchema(),
        )
        assert len(tool.tool_id) == 16
        int(tool.tool_id, 16)


class TestMCPToolRegistry:
    """Tests for MCPToolRegistry."""

    @pytest.fixture
    def registry(self):
        """Create registry fixture."""
        from ...mcp_integration.tool_registry import MCPToolRegistry

        return MCPToolRegistry(enable_audit=True)

    @pytest.fixture
    def sample_tool(self):
        """Create sample tool fixture."""
        from ...mcp_integration.tool_registry import (
            ExternalTool,
            ToolCapability,
            ToolInputSchema,
        )

        return ExternalTool(
            name="sample_tool",
            description="A sample tool",
            server_id="test-server",
            input_schema=ToolInputSchema(),
            capabilities=[ToolCapability.VALIDATION],
        )

    async def test_register_tool(self, registry, sample_tool):
        """Test registering a tool."""
        result = await registry.register_tool(
            tool=sample_tool,
            agent_id="test-agent",
        )

        assert result.success is True
        assert result.tool_name == "sample_tool"
        assert result.tool_id is not None

    async def test_unregister_tool(self, registry, sample_tool):
        """Test unregistering a tool."""
        reg_result = await registry.register_tool(sample_tool, "test-agent")
        tool_id = reg_result.tool_id

        success = await registry.unregister_tool(tool_id, "test-agent")

        assert success is True
        assert registry.get_tool(tool_id) is None

    async def test_get_tool_by_name(self, registry, sample_tool):
        """Test getting a tool by name."""
        await registry.register_tool(sample_tool, "test-agent")

        tool = registry.get_tool_by_name("sample_tool")

        assert tool is not None
        assert tool.name == "sample_tool"

    async def test_discover_tools(self, registry):
        """Test tool discovery from server."""
        tool_definitions = [
            {
                "name": "tool_1",
                "description": "First tool",
                "inputSchema": {"type": "object"},
            },
            {
                "name": "tool_2",
                "description": "Second tool",
                "inputSchema": {"type": "object"},
            },
        ]

        result = await registry.discover_tools(
            server_id="discover-server",
            server_name="Discovery Server",
            tools_definitions=tool_definitions,
            agent_id="test-agent",
        )

        assert result.tools_found == 2
        assert result.tools_registered == 2
        assert len(result.tools) == 2

    async def test_list_tools_by_server(self, registry, sample_tool):
        """Test listing tools by server."""
        await registry.register_tool(sample_tool, "test-agent")

        tools = registry.list_tools(server_id="test-server")

        assert len(tools) == 1
        assert tools[0].server_id == "test-server"

    async def test_list_tools_by_capability(self, registry, sample_tool):
        """Test listing tools by capability."""
        from ...mcp_integration.tool_registry import ToolCapability

        await registry.register_tool(sample_tool, "test-agent")

        tools = registry.list_tools(capability=ToolCapability.VALIDATION)

        assert len(tools) == 1

    def test_get_metrics(self, registry):
        """Test getting registry metrics."""
        metrics = registry.get_metrics()

        assert "total_tools" in metrics
        assert "total_servers" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_max_tools_limit(self, registry):
        """Test maximum tools per server limit."""
        from ...mcp_integration.tool_registry import (
            ExternalTool,
            ToolInputSchema,
        )

        # Register up to limit
        registry.MAX_TOOLS_PER_SERVER = 5

        for i in range(6):
            tool = ExternalTool(
                name=f"tool_{i}",
                description=f"Tool {i}",
                server_id="same-server",
                input_schema=ToolInputSchema(),
            )
            result = await registry.register_tool(tool, "test-agent")

            if i < 5:
                assert result.success is True
            else:
                assert result.success is False
                assert "Maximum tools per server" in result.error
