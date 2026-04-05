"""
MCP Integration Tests - End-to-End Testing.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from .conftest import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMCPIntegration:
    """Integration tests for MCP components."""

    async def test_client_server_integration(self):
        """Test client and server integration."""
        from ...mcp_integration.client import MCPClient, MCPClientConfig
        from ...mcp_integration.server import (
            MCPIntegrationConfig,
            MCPIntegrationServer,
        )

        # Create server
        server_config = MCPIntegrationConfig(
            server_name="integration-server",
            enable_maci=False,  # test-only: MACI off — testing MCP integration
        )
        server = MCPIntegrationServer(config=server_config)
        await server.start()

        # Create client
        client_config = MCPClientConfig(
            server_url="http://localhost:8090",
            server_name="integration-server",
        )
        client = MCPClient(config=client_config)
        await client.connect()

        # Test tool call
        result = await client.call_tool(
            tool_name="example_tool",
            arguments={"input": "test"},
        )

        assert result is not None

        # Cleanup
        await client.disconnect()
        await server.stop()

    async def test_validator_with_tool_registry(self):
        """Test validator integrated with tool registry."""
        from ...mcp_integration.tool_registry import (
            ExternalTool,
            MCPToolRegistry,
            ToolInputSchema,
        )
        from ...mcp_integration.validators import (
            MCPConstitutionalValidator,
            MCPValidationConfig,
        )

        # Create validator
        config = MCPValidationConfig(strict_mode=True)
        validator = MCPConstitutionalValidator(config=config)

        # Create registry with validator
        registry = MCPToolRegistry(validator=validator)

        # Register tool
        tool = ExternalTool(
            name="validated_tool",
            description="A validated tool",
            server_id="test-server",
            input_schema=ToolInputSchema(),
        )

        result = await registry.register_tool(
            tool=tool,
            agent_id="test-agent",
        )

        assert result.success is True

    async def test_full_governance_flow(self):
        """Test full governance flow through MCP."""
        from ...mcp_integration.server import (
            MCPIntegrationConfig,
            MCPIntegrationServer,
        )
        from ...mcp_integration.validators import (
            MCPConstitutionalValidator,
            MCPValidationConfig,
        )

        # Create validator
        validator_config = MCPValidationConfig(strict_mode=True)
        validator = MCPConstitutionalValidator(config=validator_config)

        # Create server with validator
        server_config = MCPIntegrationConfig(
            server_name="governance-server",
            enable_maci=False,  # test-only: MACI off — testing MCP integration
        )
        server = MCPIntegrationServer(
            config=server_config,
            validator=validator,
        )
        await server.start()

        # Test governance validation
        request = {
            "jsonrpc": "2.0",
            "id": "gov-1",
            "method": "governance/validate",
            "params": {
                "action": "access_data",
                "context": {
                    "data_sensitivity": "public",
                    "consent_obtained": True,
                },
            },
        }

        response = await server.handle_request(request)

        assert response is not None
        assert response["result"]["compliant"] is True

        await server.stop()


class TestModuleInitialization:
    """Tests for module initialization."""

    def test_import_module(self):
        """Test module can be imported."""
        from ...mcp_integration import (
            CONSTITUTIONAL_HASH,
            MCP_CLIENT_AVAILABLE,
            MCP_SERVER_AVAILABLE,
            MCP_TOOL_REGISTRY_AVAILABLE,
            MCP_VALIDATORS_AVAILABLE,
        )

        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        assert MCP_CLIENT_AVAILABLE is True
        assert MCP_SERVER_AVAILABLE is True
        assert MCP_TOOL_REGISTRY_AVAILABLE is True
        assert MCP_VALIDATORS_AVAILABLE is True

    def test_constitutional_hash_consistency(self):
        """Test constitutional hash is consistent across all modules."""
        from ...mcp_integration.client import MCPClient
        from ...mcp_integration.server import MCPIntegrationServer
        from ...mcp_integration.tool_registry import MCPToolRegistry
        from ...mcp_integration.validators import MCPConstitutionalValidator

        assert MCPClient.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        assert MCPIntegrationServer.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        assert MCPToolRegistry.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
        assert MCPConstitutionalValidator.CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH
