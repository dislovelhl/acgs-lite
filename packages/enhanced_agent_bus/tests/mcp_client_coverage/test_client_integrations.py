"""Unit tests for MCP client integrations (Validator, ToolRegistry).
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.mcp_integration.client import (
    MCPConnectionError,
)

from .helpers import _make_client

pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


class TestMCPClientConnectWithValidator:
    async def test_connect_validator_passes(self):
        validator = MagicMock()
        validation_result = MagicMock()
        validation_result.is_valid = True
        validator.validate = AsyncMock(return_value=validation_result)

        with patch("enhanced_agent_bus.mcp_integration.client.VALIDATORS_AVAILABLE", True):
            client = _make_client(validator=validator)
            result = await client.connect()
        assert result is True
        validator.validate.assert_called_once()

    async def test_connect_validator_fails_raises(self):
        validator = MagicMock()
        issue = MagicMock()
        issue.message = "forbidden"
        validation_result = MagicMock()
        validation_result.is_valid = False
        validation_result.issues = [issue]
        validator.validate = AsyncMock(return_value=validation_result)

        with patch("enhanced_agent_bus.mcp_integration.client.VALIDATORS_AVAILABLE", True):
            client = _make_client(validator=validator)
            with pytest.raises(MCPConnectionError, match="Connection validation failed"):
                await client.connect()

    async def test_connect_no_validator_skips_validation(self):
        with patch("enhanced_agent_bus.mcp_integration.client.VALIDATORS_AVAILABLE", True):
            client = _make_client(validator=None)
            result = await client.connect()
        assert result is True

    async def test_connect_validators_not_available_skips(self):
        validator = MagicMock()
        validator.validate = AsyncMock()
        with patch("enhanced_agent_bus.mcp_integration.client.VALIDATORS_AVAILABLE", False):
            client = _make_client(validator=validator)
            result = await client.connect()
        assert result is True
        validator.validate.assert_not_called()


class TestMCPClientToolRegistry:
    async def test_tool_registry_discover_called(self):
        registry = MagicMock()
        registry.discover_tools = AsyncMock()

        with patch("enhanced_agent_bus.mcp_integration.client.TOOL_REGISTRY_AVAILABLE", True):
            client = _make_client(tool_registry=registry)
            await client.connect()

        registry.discover_tools.assert_called_once()
        call_kwargs = registry.discover_tools.call_args[1]
        assert call_kwargs["server_id"] == client.server_id
        assert call_kwargs["agent_id"] == client.agent_id

    async def test_tool_registry_not_available_skips(self):
        registry = MagicMock()
        registry.discover_tools = AsyncMock()

        with patch("enhanced_agent_bus.mcp_integration.client.TOOL_REGISTRY_AVAILABLE", False):
            client = _make_client(tool_registry=registry)
            await client.connect()

        registry.discover_tools.assert_not_called()

    async def test_no_tool_registry_no_error(self):
        client = _make_client(tool_registry=None)
        result = await client.connect()
        assert result is True
