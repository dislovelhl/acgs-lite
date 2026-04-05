# Constitutional Hash: 608508a9bd224290
"""Optional MCP Native Integration Module."""

try:
    from .mcp_integration import (
        MCP_CLIENT_AVAILABLE,
        MCP_SERVER_AVAILABLE,
        MCP_TOOL_REGISTRY_AVAILABLE,
        MCP_VALIDATORS_AVAILABLE,
        MCPClient,
        MCPClientConfig,
        MCPClientState,
        MCPConnectionError,
        MCPConnectionPool,
        MCPConstitutionalValidator,
        MCPIntegrationConfig,
        MCPIntegrationServer,
        MCPOperationContext,
        MCPServerConnection,
        MCPServerMetrics,
        MCPServerState,
        MCPToolRegistry,
        MCPValidationConfig,
        MCPValidationResult,
        OperationType,
        create_mcp_client,
        create_mcp_integration_server,
        create_mcp_validator,
        create_tool_registry,
    )

    MCP_INTEGRATION_AVAILABLE = True
except ImportError:
    MCP_INTEGRATION_AVAILABLE = False
    MCP_CLIENT_AVAILABLE = False
    MCP_SERVER_AVAILABLE = False
    MCP_TOOL_REGISTRY_AVAILABLE = False
    MCP_VALIDATORS_AVAILABLE = False
    MCPClient = object  # type: ignore[assignment, misc]
    MCPClientConfig = object  # type: ignore[assignment, misc]
    MCPClientState = object  # type: ignore[assignment, misc]
    MCPConnectionError = object  # type: ignore[assignment, misc]
    MCPConnectionPool = object  # type: ignore[assignment, misc]
    MCPConstitutionalValidator = object  # type: ignore[assignment, misc]
    MCPIntegrationConfig = object  # type: ignore[assignment, misc]
    MCPIntegrationServer = object  # type: ignore[assignment, misc]
    MCPOperationContext = object  # type: ignore[assignment, misc]
    MCPServerConnection = object  # type: ignore[assignment, misc]
    MCPServerMetrics = object  # type: ignore[assignment, misc]
    MCPServerState = object  # type: ignore[assignment, misc]
    MCPToolRegistry = object  # type: ignore[assignment, misc]
    MCPValidationConfig = object  # type: ignore[assignment, misc]
    MCPValidationResult = object  # type: ignore[assignment, misc]
    OperationType = object  # type: ignore[assignment, misc]
    create_mcp_client = object  # type: ignore[assignment, misc]
    create_mcp_integration_server = object  # type: ignore[assignment, misc]
    create_mcp_validator = object  # type: ignore[assignment, misc]
    create_tool_registry = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "MCP_INTEGRATION_AVAILABLE",
    "MCP_CLIENT_AVAILABLE",
    "MCP_SERVER_AVAILABLE",
    "MCP_TOOL_REGISTRY_AVAILABLE",
    "MCP_VALIDATORS_AVAILABLE",
    "MCPClient",
    "MCPClientConfig",
    "MCPClientState",
    "MCPConnectionError",
    "MCPConnectionPool",
    "MCPConstitutionalValidator",
    "MCPIntegrationConfig",
    "MCPIntegrationServer",
    "MCPOperationContext",
    "MCPServerConnection",
    "MCPServerMetrics",
    "MCPServerState",
    "MCPToolRegistry",
    "MCPValidationConfig",
    "MCPValidationResult",
    "OperationType",
    "create_mcp_client",
    "create_mcp_integration_server",
    "create_mcp_validator",
    "create_tool_registry",
]
