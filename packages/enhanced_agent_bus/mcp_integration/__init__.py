"""
ACGS-2 MCP Native Integration Module.

Provides comprehensive Model Context Protocol (MCP) integration for the
Enhanced Agent Bus, enabling bidirectional communication with external
AI systems while maintaining constitutional governance.

Key Features:
- Bidirectional MCP protocol support (client and server modes)
- Tool discovery and registration with constitutional validation
- MACI-aware role-based access control for MCP operations
- Support for 16,000+ MCP server compatibility
- Comprehensive audit logging and compliance tracking

Constitutional Hash: cdd01ef066bc6cf2

Usage:
    from enhanced_agent_bus.mcp_integration import (
        MCPClient,
        MCPIntegrationServer,
        MCPToolRegistry,
        MCPConstitutionalValidator,
    )

    # Create MCP client for connecting to external servers
    client = MCPClient(config=MCPClientConfig(server_url="http://localhost:8000"))
    await client.connect()

    # Create MCP server for exposing ACGS-2 capabilities
    server = MCPIntegrationServer(config=MCPIntegrationConfig())
    await server.start()
"""

__version__ = "1.0.0"

# Import centralized constitutional hash
from src.core.shared.constants import CONSTITUTIONAL_HASH

__constitutional_hash__ = CONSTITUTIONAL_HASH

# MCP Client
try:
    from .client import (
        MCPClient,
        MCPClientConfig,
        MCPClientState,
        MCPConnectionError,
        MCPConnectionPool,
        MCPServerConnection,
        create_mcp_client,
    )

    MCP_CLIENT_AVAILABLE = True
except ImportError:
    MCP_CLIENT_AVAILABLE = False
    MCPClient = object  # type: ignore[assignment, misc]
    MCPClientConfig = object  # type: ignore[assignment, misc]
    MCPClientState = object  # type: ignore[assignment, misc]
    MCPConnectionError = object  # type: ignore[assignment, misc]
    MCPConnectionPool = object  # type: ignore[assignment, misc]
    MCPServerConnection = object  # type: ignore[assignment, misc]
    create_mcp_client = object  # type: ignore[assignment, misc]

# MCP Server
try:
    from .server import (
        MCPIntegrationConfig,
        MCPIntegrationServer,
        MCPServerMetrics,
        MCPServerState,
        create_mcp_integration_server,
    )

    MCP_SERVER_AVAILABLE = True
except ImportError:
    MCP_SERVER_AVAILABLE = False
    MCPIntegrationConfig = object  # type: ignore[assignment, misc]
    MCPIntegrationServer = object  # type: ignore[assignment, misc]
    MCPServerMetrics = object  # type: ignore[assignment, misc]
    MCPServerState = object  # type: ignore[assignment, misc]
    create_mcp_integration_server = object  # type: ignore[assignment, misc]

# Tool Registry
try:
    from .tool_registry import (
        ExternalTool,
        MCPToolRegistry,
        ToolCapability,
        ToolDiscoveryResult,
        ToolExecutionContext,
        ToolRegistrationResult,
        create_tool_registry,
    )

    MCP_TOOL_REGISTRY_AVAILABLE = True
except ImportError:
    MCP_TOOL_REGISTRY_AVAILABLE = False
    ExternalTool = object  # type: ignore[assignment, misc]
    MCPToolRegistry = object  # type: ignore[assignment, misc]
    ToolCapability = object  # type: ignore[assignment, misc]
    ToolDiscoveryResult = object  # type: ignore[assignment, misc]
    ToolExecutionContext = object  # type: ignore[assignment, misc]
    ToolRegistrationResult = object  # type: ignore[assignment, misc]
    create_tool_registry = object  # type: ignore[assignment, misc]

# Constitutional Validators
try:
    from .validators import (
        MCPConstitutionalValidator,
        MCPOperationContext,
        MCPValidationConfig,
        MCPValidationResult,
        OperationType,
        create_mcp_validator,
    )

    MCP_VALIDATORS_AVAILABLE = True
except ImportError:
    MCP_VALIDATORS_AVAILABLE = False
    MCPConstitutionalValidator = object  # type: ignore[assignment, misc]
    MCPOperationContext = object  # type: ignore[assignment, misc]
    MCPValidationConfig = object  # type: ignore[assignment, misc]
    MCPValidationResult = object  # type: ignore[assignment, misc]
    OperationType = object  # type: ignore[assignment, misc]
    create_mcp_validator = object  # type: ignore[assignment, misc]

__all__ = [
    "CONSTITUTIONAL_HASH",
    # Availability flags
    "MCP_CLIENT_AVAILABLE",
    "MCP_SERVER_AVAILABLE",
    "MCP_TOOL_REGISTRY_AVAILABLE",
    "MCP_VALIDATORS_AVAILABLE",
    # Tool Registry
    "ExternalTool",
    # Client
    "MCPClient",
    "MCPClientConfig",
    "MCPClientState",
    "MCPConnectionError",
    "MCPConnectionPool",
    # Validators
    "MCPConstitutionalValidator",
    # Server
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
    "ToolCapability",
    "ToolDiscoveryResult",
    "ToolExecutionContext",
    "ToolRegistrationResult",
    "__constitutional_hash__",
    # Module info
    "__version__",
    "create_mcp_client",
    "create_mcp_integration_server",
    "create_mcp_validator",
    "create_tool_registry",
]
