"""
MCP Performance Tests.
Constitutional Hash: 608508a9bd224290
"""

from datetime import UTC, datetime, timezone

import pytest

from .conftest import CONSTITUTIONAL_HASH

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestPerformance:
    """Performance tests for MCP integration."""

    async def test_validation_latency(self):
        """Test validation latency is within acceptable bounds."""
        from ...mcp_integration.validators import (
            MCPConstitutionalValidator,
            MCPOperationContext,
            OperationType,
        )

        validator = MCPConstitutionalValidator()

        context = MCPOperationContext(
            operation_type=OperationType.TOOL_CALL,
            agent_id="test-agent",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        result = await validator.validate(context)

        # Validation should complete in under 100ms
        assert result.latency_ms < 100

    async def test_batch_validation_performance(self):
        """Test batch validation performance."""
        from ...mcp_integration.validators import (
            MCPConstitutionalValidator,
            MCPOperationContext,
            OperationType,
        )

        validator = MCPConstitutionalValidator()

        contexts = [
            MCPOperationContext(
                operation_type=OperationType.TOOL_CALL,
                agent_id=f"agent-{i}",
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            for i in range(100)
        ]

        start = datetime.now(UTC)
        results = await validator.validate_batch(contexts)
        end = datetime.now(UTC)

        total_ms = (end - start).total_seconds() * 1000

        assert len(results) == 100
        # 100 validations should complete in under 1 second
        assert total_ms < 1000

    async def test_tool_registry_scalability(self):
        """Test tool registry can handle many tools."""
        from ...mcp_integration.tool_registry import (
            ExternalTool,
            MCPToolRegistry,
            ToolInputSchema,
        )

        registry = MCPToolRegistry()

        # Register 1000 tools
        for i in range(1000):
            tool = ExternalTool(
                name=f"tool_{i}",
                description=f"Tool {i}",
                server_id=f"server-{i % 100}",
                input_schema=ToolInputSchema(),
            )
            await registry.register_tool(tool, "test-agent")

        metrics = registry.get_metrics()

        assert metrics["total_tools"] == 1000
        assert metrics["total_servers"] == 100
