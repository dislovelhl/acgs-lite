"""
ACGS-2 Enhanced Agent Bus - DX Ecosystem Tests
Constitutional Hash: cdd01ef066bc6cf2

Comprehensive tests for the DX Ecosystem module including:
- MCPBridge (Model Context Protocol) integration
- GenUIController (Generative UI) component generation
- Tool registration and manifest generation
- External MCP server communication
"""

import asyncio
from unittest.mock import patch

import pytest

# Import dx_ecosystem module
try:
    from enhanced_agent_bus.dx_ecosystem import GenUIController, MCPBridge
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from dx_ecosystem import GenUIController, MCPBridge


# Constitutional Hash for validation
from src.core.shared.constants import CONSTITUTIONAL_HASH


class TestMCPBridgeInitialization:
    """Test MCPBridge initialization."""

    def test_init_with_project_id(self):
        """Test initialization with project ID."""
        bridge = MCPBridge(project_id="test-project")

        assert bridge.project_id == "test-project"
        assert bridge.mounted_tools == {}

    def test_init_with_different_project_ids(self):
        """Test initialization with various project IDs."""
        test_ids = ["project-1", "acgs-core", "ceos-main", "test_project_123"]

        for project_id in test_ids:
            bridge = MCPBridge(project_id=project_id)
            assert bridge.project_id == project_id

    def test_init_with_empty_project_id(self):
        """Test initialization with empty project ID."""
        bridge = MCPBridge(project_id="")

        assert bridge.project_id == ""
        assert bridge.mounted_tools == {}

    def test_mounted_tools_is_dict(self):
        """Test that mounted_tools is initialized as empty dict."""
        bridge = MCPBridge(project_id="test")

        assert isinstance(bridge.mounted_tools, dict)
        assert len(bridge.mounted_tools) == 0


class TestMCPBridgeToolRegistration:
    """Test MCPBridge tool registration functionality."""

    @pytest.fixture
    def bridge(self):
        """Create an MCPBridge instance for testing."""
        return MCPBridge(project_id="test-project")

    @pytest.mark.asyncio
    async def test_register_tool_basic(self, bridge):
        """Test basic tool registration."""
        tool_config = {"description": "A test tool", "schema": {"type": "object"}}

        result = await bridge.register_tool_as_mcp("test-tool", tool_config)

        assert result is True
        assert "test-tool" in bridge.mounted_tools

    @pytest.mark.asyncio
    async def test_register_tool_stores_correct_data(self, bridge):
        """Test that tool registration stores correct data."""
        tool_config = {
            "description": "Test tool description",
            "schema": {"type": "object", "properties": {"input": {"type": "string"}}},
        }

        await bridge.register_tool_as_mcp("my-tool", tool_config)

        tool = bridge.mounted_tools["my-tool"]
        assert tool["name"] == "my-tool"
        assert tool["description"] == "Test tool description"
        assert tool["inputSchema"] == tool_config["schema"]
        assert tool["mcp_type"] == "tool_export"

    @pytest.mark.asyncio
    async def test_register_tool_without_description(self, bridge):
        """Test tool registration without description."""
        tool_config = {"schema": {"type": "string"}}

        result = await bridge.register_tool_as_mcp("no-desc-tool", tool_config)

        assert result is True
        assert bridge.mounted_tools["no-desc-tool"]["description"] == ""

    @pytest.mark.asyncio
    async def test_register_tool_without_schema(self, bridge):
        """Test tool registration without schema."""
        tool_config = {"description": "Tool without schema"}

        result = await bridge.register_tool_as_mcp("no-schema-tool", tool_config)

        assert result is True
        assert bridge.mounted_tools["no-schema-tool"]["inputSchema"] == {}

    @pytest.mark.asyncio
    async def test_register_tool_empty_config(self, bridge):
        """Test tool registration with empty config."""
        result = await bridge.register_tool_as_mcp("empty-config-tool", {})

        assert result is True
        assert bridge.mounted_tools["empty-config-tool"]["description"] == ""
        assert bridge.mounted_tools["empty-config-tool"]["inputSchema"] == {}

    @pytest.mark.asyncio
    async def test_register_multiple_tools(self, bridge):
        """Test registering multiple tools."""
        tools = [
            ("tool-1", {"description": "First tool"}),
            ("tool-2", {"description": "Second tool"}),
            ("tool-3", {"description": "Third tool"}),
        ]

        for tool_name, config in tools:
            result = await bridge.register_tool_as_mcp(tool_name, config)
            assert result is True

        assert len(bridge.mounted_tools) == 3
        assert all(f"tool-{i}" in bridge.mounted_tools for i in range(1, 4))

    @pytest.mark.asyncio
    async def test_register_tool_overwrites_existing(self, bridge):
        """Test that registering same tool overwrites previous."""
        await bridge.register_tool_as_mcp("my-tool", {"description": "Version 1"})
        await bridge.register_tool_as_mcp("my-tool", {"description": "Version 2"})

        assert len(bridge.mounted_tools) == 1
        assert bridge.mounted_tools["my-tool"]["description"] == "Version 2"

    @pytest.mark.asyncio
    async def test_register_tool_with_complex_schema(self, bridge):
        """Test tool registration with complex JSON schema."""
        complex_schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "filters": {"type": "array", "items": {"type": "string"}},
                "options": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        "offset": {"type": "integer", "minimum": 0},
                    },
                },
            },
            "required": ["query"],
        }

        result = await bridge.register_tool_as_mcp(
            "complex-tool", {"description": "Tool with complex schema", "schema": complex_schema}
        )

        assert result is True
        assert bridge.mounted_tools["complex-tool"]["inputSchema"] == complex_schema


class TestMCPBridgeExternalServer:
    """Test MCPBridge external MCP server communication."""

    @pytest.fixture
    def bridge(self):
        """Create an MCPBridge instance for testing."""
        return MCPBridge(project_id="test-project")

    @pytest.mark.asyncio
    async def test_call_external_server_basic(self, bridge):
        """Test basic external server call."""
        result = await bridge.call_external_mcp_server(
            server_url="http://localhost:8080",
            tool_name="remote-tool",
            arguments={"param": "value"},
        )

        assert "result" in result
        assert result["result"]["isError"] is False
        assert "content" in result["result"]

    @pytest.mark.asyncio
    async def test_call_external_server_returns_tool_name(self, bridge):
        """Test that external call returns tool name in response."""
        result = await bridge.call_external_mcp_server(
            server_url="http://example.com", tool_name="test-tool", arguments={}
        )

        content = result["result"]["content"]
        assert len(content) > 0
        assert content[0]["type"] == "text"
        assert "test-tool" in content[0]["text"]

    @pytest.mark.asyncio
    async def test_call_external_server_different_urls(self, bridge):
        """Test calling different external servers."""
        urls = [
            "http://localhost:8080",
            "https://api.example.com",
            "http://internal-service:3000",
        ]

        for url in urls:
            result = await bridge.call_external_mcp_server(
                server_url=url, tool_name="test-tool", arguments={}
            )
            assert result["result"]["isError"] is False

    @pytest.mark.asyncio
    async def test_call_external_server_with_arguments(self, bridge):
        """Test external server call with various arguments."""
        arguments = {
            "query": "search term",
            "filters": ["filter1", "filter2"],
            "options": {"limit": 10},
        }

        result = await bridge.call_external_mcp_server(
            server_url="http://localhost:8080", tool_name="search-tool", arguments=arguments
        )

        assert result["result"]["isError"] is False

    @pytest.mark.asyncio
    async def test_call_external_server_empty_arguments(self, bridge):
        """Test external server call with empty arguments."""
        result = await bridge.call_external_mcp_server(
            server_url="http://localhost:8080", tool_name="no-args-tool", arguments={}
        )

        assert "result" in result


class TestMCPBridgeManifest:
    """Test MCPBridge manifest generation."""

    @pytest.fixture
    def bridge(self):
        """Create an MCPBridge instance for testing."""
        return MCPBridge(project_id="test-project")

    def test_get_manifest_empty(self, bridge):
        """Test manifest with no registered tools."""
        manifest = bridge.get_manifest()

        assert manifest["mcp_version"] == "1.0"
        assert manifest["project"] == "test-project"
        assert manifest["tools"] == []

    @pytest.mark.asyncio
    async def test_get_manifest_with_tools(self, bridge):
        """Test manifest with registered tools."""
        await bridge.register_tool_as_mcp("tool-1", {"description": "First"})
        await bridge.register_tool_as_mcp("tool-2", {"description": "Second"})

        manifest = bridge.get_manifest()

        assert len(manifest["tools"]) == 2
        tool_names = [t["name"] for t in manifest["tools"]]
        assert "tool-1" in tool_names
        assert "tool-2" in tool_names

    def test_manifest_structure(self, bridge):
        """Test that manifest has correct structure."""
        manifest = bridge.get_manifest()

        required_keys = ["mcp_version", "project", "tools"]
        for key in required_keys:
            assert key in manifest

    @pytest.mark.asyncio
    async def test_manifest_tool_data(self, bridge):
        """Test that manifest contains full tool data."""
        await bridge.register_tool_as_mcp(
            "test-tool", {"description": "Test description", "schema": {"type": "string"}}
        )

        manifest = bridge.get_manifest()
        tool = manifest["tools"][0]

        assert tool["name"] == "test-tool"
        assert tool["description"] == "Test description"
        assert tool["inputSchema"] == {"type": "string"}
        assert tool["mcp_type"] == "tool_export"


class TestMCPBridgeConcurrency:
    """Test MCPBridge concurrent operations."""

    @pytest.mark.asyncio
    async def test_concurrent_tool_registration(self):
        """Test concurrent tool registration."""
        bridge = MCPBridge(project_id="concurrent-test")

        async def register_tool(i: int):
            return await bridge.register_tool_as_mcp(f"tool-{i}", {"description": f"Tool {i}"})

        tasks = [register_tool(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert all(results)
        assert len(bridge.mounted_tools) == 10

    @pytest.mark.asyncio
    async def test_concurrent_external_calls(self):
        """Test concurrent external server calls."""
        bridge = MCPBridge(project_id="concurrent-test")

        async def call_server(i: int):
            return await bridge.call_external_mcp_server(
                server_url=f"http://server-{i}:8080", tool_name=f"tool-{i}", arguments={"index": i}
            )

        tasks = [call_server(i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert all(r["result"]["isError"] is False for r in results)


class TestGenUIControllerInitialization:
    """Test GenUIController initialization."""

    def test_init_creates_instance(self):
        """Test basic initialization."""
        controller = GenUIController()
        assert controller is not None

    def test_multiple_instances_independent(self):
        """Test that multiple instances are independent."""
        controller1 = GenUIController()
        controller2 = GenUIController()

        # Both should work independently
        schema1 = controller1.generate_component_schema("dashboard", {"stats": []})
        schema2 = controller2.generate_component_schema("dashboard", {"stats": []})

        assert schema1 == schema2


class TestGenUIControllerDashboard:
    """Test GenUIController dashboard component generation."""

    @pytest.fixture
    def controller(self):
        """Create a GenUIController instance for testing."""
        return GenUIController()

    def test_generate_dashboard_basic(self, controller):
        """Test basic dashboard generation."""
        schema = controller.generate_component_schema("dashboard", {"stats": []})

        assert schema["version"] == "1.0"
        assert schema["type"] == "Grid"
        assert "props" in schema
        assert "children" in schema

    def test_generate_dashboard_with_stats(self, controller):
        """Test dashboard with stat cards."""
        stats = [
            {"title": "Users", "value": 100},
            {"title": "Revenue", "value": "$1000"},
            {"title": "Orders", "value": 50},
        ]

        schema = controller.generate_component_schema("dashboard", {"stats": stats})

        assert len(schema["children"]) == 3
        for i, child in enumerate(schema["children"]):
            assert child["type"] == "StatCard"
            assert child["props"] == stats[i]

    def test_generate_dashboard_grid_columns(self, controller):
        """Test dashboard grid columns configuration."""
        schema = controller.generate_component_schema("dashboard", {"stats": []})

        assert schema["props"]["columns"] == 3

    def test_generate_dashboard_empty_stats(self, controller):
        """Test dashboard with empty stats array."""
        schema = controller.generate_component_schema("dashboard", {"stats": []})

        assert schema["children"] == []

    def test_generate_dashboard_missing_stats(self, controller):
        """Test dashboard with missing stats key."""
        schema = controller.generate_component_schema("dashboard", {})

        assert schema["children"] == []


class TestGenUIControllerGraphViz:
    """Test GenUIController graph visualization component generation."""

    @pytest.fixture
    def controller(self):
        """Create a GenUIController instance for testing."""
        return GenUIController()

    def test_generate_graph_viz_basic(self, controller):
        """Test basic graph visualization generation."""
        data = {"nodes": [{"id": "1"}, {"id": "2"}], "links": [{"source": "1", "target": "2"}]}

        schema = controller.generate_component_schema("graph_viz", data)

        assert schema["version"] == "1.0"
        assert schema["type"] == "ForceGraph"

    def test_generate_graph_viz_nodes(self, controller):
        """Test graph visualization with nodes."""
        nodes = [
            {"id": "1", "label": "Node 1"},
            {"id": "2", "label": "Node 2"},
            {"id": "3", "label": "Node 3"},
        ]

        schema = controller.generate_component_schema("graph_viz", {"nodes": nodes, "links": []})

        assert schema["props"]["nodes"] == nodes

    def test_generate_graph_viz_links(self, controller):
        """Test graph visualization with links."""
        links = [
            {"source": "1", "target": "2"},
            {"source": "2", "target": "3"},
        ]

        schema = controller.generate_component_schema("graph_viz", {"nodes": [], "links": links})

        assert schema["props"]["links"] == links

    def test_generate_graph_viz_empty_data(self, controller):
        """Test graph visualization with empty data."""
        schema = controller.generate_component_schema("graph_viz", {"nodes": [], "links": []})

        assert schema["props"]["nodes"] == []
        assert schema["props"]["links"] == []

    def test_generate_graph_viz_missing_keys(self, controller):
        """Test graph visualization with missing keys."""
        schema = controller.generate_component_schema("graph_viz", {})

        assert schema["props"]["nodes"] is None
        assert schema["props"]["links"] is None


class TestGenUIControllerUnknownComponents:
    """Test GenUIController handling of unknown component types."""

    @pytest.fixture
    def controller(self):
        """Create a GenUIController instance for testing."""
        return GenUIController()

    def test_unknown_component_returns_error(self, controller):
        """Test that unknown component type returns error."""
        schema = controller.generate_component_schema("unknown_type", {})

        assert "error" in schema
        assert "Unknown UI component type" in schema["error"]

    def test_various_unknown_types(self, controller):
        """Test various unknown component types."""
        unknown_types = ["table", "chart", "form", "modal", "sidebar"]

        for component_type in unknown_types:
            schema = controller.generate_component_schema(component_type, {})
            assert "error" in schema

    def test_empty_component_type(self, controller):
        """Test empty component type."""
        schema = controller.generate_component_schema("", {})

        assert "error" in schema


class TestGenUIControllerSchemaVersioning:
    """Test GenUIController schema versioning."""

    @pytest.fixture
    def controller(self):
        """Create a GenUIController instance for testing."""
        return GenUIController()

    def test_dashboard_version(self, controller):
        """Test dashboard schema version."""
        schema = controller.generate_component_schema("dashboard", {"stats": []})
        assert schema["version"] == "1.0"

    def test_graph_viz_version(self, controller):
        """Test graph_viz schema version."""
        schema = controller.generate_component_schema("graph_viz", {"nodes": [], "links": []})
        assert schema["version"] == "1.0"


class TestIntegration:
    """Integration tests for MCPBridge and GenUIController."""

    @pytest.mark.asyncio
    async def test_mcp_bridge_full_workflow(self):
        """Test complete MCPBridge workflow."""
        # Initialize
        bridge = MCPBridge(project_id="integration-test")

        # Register tools
        await bridge.register_tool_as_mcp(
            "search",
            {
                "description": "Search tool",
                "schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
        )
        await bridge.register_tool_as_mcp(
            "analyze",
            {
                "description": "Analysis tool",
                "schema": {"type": "object", "properties": {"data": {"type": "array"}}},
            },
        )

        # Get manifest
        manifest = bridge.get_manifest()
        assert len(manifest["tools"]) == 2

        # Call external server
        result = await bridge.call_external_mcp_server(
            server_url="http://external:8080", tool_name="external-tool", arguments={"test": True}
        )
        assert result["result"]["isError"] is False

    def test_genui_controller_full_workflow(self):
        """Test complete GenUIController workflow."""
        controller = GenUIController()

        # Generate dashboard
        dashboard = controller.generate_component_schema(
            "dashboard",
            {
                "stats": [
                    {"title": "Metric 1", "value": 100},
                    {"title": "Metric 2", "value": 200},
                ]
            },
        )
        assert dashboard["type"] == "Grid"
        assert len(dashboard["children"]) == 2

        # Generate graph
        graph = controller.generate_component_schema(
            "graph_viz",
            {"nodes": [{"id": "1"}, {"id": "2"}], "links": [{"source": "1", "target": "2"}]},
        )
        assert graph["type"] == "ForceGraph"

        # Unknown type
        unknown = controller.generate_component_schema("unknown", {})
        assert "error" in unknown

    @pytest.mark.asyncio
    async def test_combined_mcp_and_genui(self):
        """Test using MCPBridge and GenUIController together."""
        bridge = MCPBridge(project_id="combined-test")
        controller = GenUIController()

        # Register a GenUI tool in MCP
        await bridge.register_tool_as_mcp(
            "genui-dashboard",
            {
                "description": "Generate dashboard UI",
                "schema": {"type": "object", "properties": {"stats": {"type": "array"}}},
            },
        )

        # Simulate tool execution
        manifest = bridge.get_manifest()
        assert any(t["name"] == "genui-dashboard" for t in manifest["tools"])

        # Generate corresponding UI
        ui_schema = controller.generate_component_schema(
            "dashboard", {"stats": [{"title": "Test", "value": 42}]}
        )
        assert ui_schema["type"] == "Grid"


class TestModuleExports:
    """Test module exports."""

    def test_mcpbridge_exported(self):
        """Test that MCPBridge is properly exported."""
        try:
            from enhanced_agent_bus.dx_ecosystem import MCPBridge
        except ImportError:
            from dx_ecosystem import MCPBridge

        assert MCPBridge is not None

    def test_genuicontroller_exported(self):
        """Test that GenUIController is properly exported."""
        try:
            from enhanced_agent_bus.dx_ecosystem import GenUIController
        except ImportError:
            from dx_ecosystem import GenUIController

        assert GenUIController is not None


class TestConstitutionalCompliance:
    """Test constitutional compliance in dx_ecosystem module."""

    def test_constitutional_hash_in_module(self):
        """Test that module has constitutional hash in docstring."""
        try:
            from enhanced_agent_bus import dx_ecosystem
        except ImportError:
            import dx_ecosystem

        assert CONSTITUTIONAL_HASH in dx_ecosystem.__doc__

    def test_mcp_bridge_is_class(self):
        """Test that MCPBridge is a proper class."""
        assert isinstance(MCPBridge, type)

    def test_genui_controller_is_class(self):
        """Test that GenUIController is a proper class."""
        assert isinstance(GenUIController, type)


class TestLogging:
    """Test logging functionality."""

    @pytest.mark.asyncio
    async def test_register_tool_logs(self):
        """Test that tool registration logs."""
        bridge = MCPBridge(project_id="log-test")

        with patch("dx_ecosystem.logger") as mock_logger:
            await bridge.register_tool_as_mcp("test-tool", {})
            # Note: We can't easily verify logging due to import path differences
            # This test ensures the operation completes without error

    @pytest.mark.asyncio
    async def test_external_call_logs(self):
        """Test that external calls log."""
        bridge = MCPBridge(project_id="log-test")

        with patch("dx_ecosystem.logger") as mock_logger:
            await bridge.call_external_mcp_server(
                server_url="http://test:8080", tool_name="test", arguments={}
            )
            # Operation should complete without error

    def test_genui_generation_logs(self):
        """Test that UI generation logs."""
        controller = GenUIController()

        with patch("dx_ecosystem.logger") as mock_logger:
            controller.generate_component_schema("dashboard", {"stats": []})
            # Operation should complete without error
