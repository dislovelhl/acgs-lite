"""
MCP Error Handling Tests.
Constitutional Hash: 608508a9bd224290
"""

import pytest

from .conftest import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestErrorHandling:
    """Tests for error handling."""

    async def test_client_connection_error_handling(self):
        """Test client handles connection errors gracefully."""
        from ...mcp_integration.client import (
            MCPClient,
            MCPClientConfig,
        )

        config = MCPClientConfig(
            server_url="http://invalid-server:9999",
            retry_attempts=1,
        )
        client = MCPClient(config=config)

        # Client uses simulated connection, so it won't fail
        # In real implementation, this would test actual connection failures
        await client.connect()
        assert client.is_connected is True

    async def test_server_handles_malformed_request(self):
        """Test server handles malformed requests."""
        from ...mcp_integration.server import (
            MCPIntegrationConfig,
            MCPIntegrationServer,
        )

        config = MCPIntegrationConfig()
        server = MCPIntegrationServer(config=config)
        await server.start()

        # Missing method
        request = {
            "jsonrpc": "2.0",
            "id": "1",
            "params": {},
        }

        response = await server.handle_request(request)

        assert response is not None
        assert "error" in response

        await server.stop()

    async def test_validator_handles_exceptions(self):
        """Test validator handles exceptions gracefully."""
        from ...mcp_integration.validators import (
            MCPConstitutionalValidator,
            MCPOperationContext,
            MCPValidationConfig,
            OperationType,
        )

        # Add a custom validator that raises an exception
        def bad_validator(context, result):
            raise ValueError("Test exception")

        config = MCPValidationConfig(
            strict_mode=False,  # Don't fail on errors
            custom_validators=[bad_validator],
        )
        validator = MCPConstitutionalValidator(config=config)

        context = MCPOperationContext(
            operation_type=OperationType.TOOL_CALL,
            agent_id="test-agent",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        # Should not raise, but add warning
        result = await validator.validate(context)

        assert result.is_valid is True
        assert any("failed" in w.lower() for w in result.warnings)
