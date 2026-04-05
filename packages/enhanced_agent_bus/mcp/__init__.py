"""
ACGS-2 Enhanced Agent Bus — MCP Client Package.

Provides a lightweight, MACI-aware MCP client layer for the Enhanced Agent Bus.
This package is intentionally separate from the heavier ``mcp_integration`` and
``mcp_server`` packages so it can be imported in minimal contexts without pulling
in optional dependencies.

Constitutional Hash: 608508a9bd224290

Quick start::

    from enhanced_agent_bus.mcp import MCPClient, MCPClientConfig

    config = MCPClientConfig(server_url="http://localhost:8080")
    async with MCPClient(config=config) as client:
        tools = await client.list_tools()
        result = await client.call_tool(
            "search_documents",
            arguments={"query": "constitutional governance"},
            agent_id="agent-1",
            maci_role="executive",
        )
        assert result.constitutional_hash == CONSTITUTIONAL_HASH
"""

__version__ = "1.0.0"

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

__constitutional_hash__ = CONSTITUTIONAL_HASH

from .client import (
    MCPClient,
    MCPClientConfig,
    MCPClientError,
    MCPClientState,
    MCPConnectionError,
    MCPMACIViolationError,
    MCPToolCallError,
    create_mcp_client,
)
from .config import (
    NEURAL_MCP_SERVER_NAME,
    TOOLBOX_SERVER_NAME,
    MCPConfig,
    MCPServerConfig,
    get_mcp_config,
    load_config,
    load_from_env,
    load_from_yaml,
)
from .pool import (
    MCPClientPool,
    MCPPoolDuplicateClientError,
    MCPPoolError,
    MCPToolNotFoundError,
    create_mcp_pool,
)
from .router import (
    MCPRouter,
    ToolCategory,
    ToolRequest,
    ToolResponse,
)
from .transports import (
    HTTPTransport,
    MCPTransport,
    MCPTransportError,
)
from .types import (
    CONSTITUTIONAL_HASH,
    MCPTool,
    MCPToolResult,
    MCPToolStatus,
)

__all__ = [
    # type exports
    "CONSTITUTIONAL_HASH",
    "NEURAL_MCP_SERVER_NAME",
    "TOOLBOX_SERVER_NAME",
    # transport exports
    "HTTPTransport",
    # client exports
    "MCPClient",
    "MCPClientConfig",
    "MCPClientError",
    # pool exports
    "MCPClientPool",
    "MCPClientState",
    # config exports
    "MCPConfig",
    "MCPConnectionError",
    "MCPMACIViolationError",
    "MCPPoolDuplicateClientError",
    "MCPPoolError",
    # router exports
    "MCPRouter",
    "MCPServerConfig",
    "MCPTool",
    "MCPToolCallError",
    "MCPToolNotFoundError",
    "MCPToolResult",
    "MCPToolStatus",
    "MCPTransport",
    "MCPTransportError",
    "ToolCategory",
    "ToolRequest",
    "ToolResponse",
    "create_mcp_client",
    "create_mcp_pool",
    "get_mcp_config",
    "load_config",
    "load_from_env",
    "load_from_yaml",
]
