"""Shared helpers for MCP client coverage tests.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from enhanced_agent_bus.mcp_integration.client import (
    MCPClient,
    MCPClientConfig,
    MCPTransportType,
)


def _make_config(
    *,
    server_url: str = "http://localhost:9000/mcp",
    server_name: str = "test-server",
    transport_type: MCPTransportType = MCPTransportType.HTTP,
    retry_attempts: int = 1,
    retry_delay_ms: int = 10,
    enable_tool_discovery: bool = True,
    enable_resource_discovery: bool = True,
    enable_validation: bool = False,
    strict_mode: bool = True,
    timeout_ms: int = 1000,
) -> MCPClientConfig:
    return MCPClientConfig(
        server_url=server_url,
        server_name=server_name,
        transport_type=transport_type,
        retry_attempts=retry_attempts,
        retry_delay_ms=retry_delay_ms,
        enable_tool_discovery=enable_tool_discovery,
        enable_resource_discovery=enable_resource_discovery,
        enable_validation=enable_validation,
        strict_mode=strict_mode,
        timeout_ms=timeout_ms,
    )


def _make_client(config: MCPClientConfig | None = None, **kwargs) -> MCPClient:
    cfg = config or _make_config()
    return MCPClient(config=cfg, **kwargs)
