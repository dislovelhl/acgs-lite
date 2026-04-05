"""
MCP Client Implementation for ACGS-2.

Provides MCP client capabilities for connecting to external MCP servers,
enabling tool discovery, resource access, and bidirectional communication
with constitutional governance.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import hashlib
import inspect
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import ACGSBaseError

from enhanced_agent_bus.bus_types import JSONDict
from enhanced_agent_bus.observability.structured_logging import get_logger

# Import validators
try:
    from .validators import (
        MCPOperationContext,
        OperationType,
    )

    VALIDATORS_AVAILABLE = True
except ImportError:
    VALIDATORS_AVAILABLE = False

# Import tool registry - check availability
try:
    from .tool_registry import ExternalTool as _ExternalTool

    TOOL_REGISTRY_AVAILABLE = True
    del _ExternalTool
except ImportError:
    TOOL_REGISTRY_AVAILABLE = False

logger = get_logger(__name__)
sys.modules.setdefault("enhanced_agent_bus.mcp_integration.client", sys.modules[__name__])
sys.modules.setdefault("enhanced_agent_bus.mcp_integration.client", sys.modules[__name__])
try:
    from acgs2_perf import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:
    FAST_HASH_AVAILABLE = False

_MCP_CLIENT_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class MCPClientState(Enum):
    """State of an MCP client connection."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
    CLOSING = "closing"


class MCPTransportType(Enum):
    """MCP transport types."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"
    WEBSOCKET = "websocket"


class MCPConnectionError(ACGSBaseError):
    """MCP connection error.

    Inherits from ACGSBaseError to gain constitutional hash tracking,
    correlation IDs, and structured error logging.
    """

    http_status_code = 503  # Service Unavailable
    error_code = "MCP_CONNECTION_ERROR"

    def __init__(
        self,
        message: str,
        server_id: str | None = None,
        error_code: int | None = None,
    ):
        self.server_id = server_id
        self.error_code = error_code  # Instance attribute (MCP error code)
        super().__init__(
            message,
            details={"server_id": server_id, "mcp_error_code": error_code},
        )


@dataclass
class MCPClientConfig:
    """Configuration for MCP client."""

    server_url: str = ""
    server_name: str = ""
    transport_type: MCPTransportType = MCPTransportType.HTTP
    client_name: str = "acgs2-mcp-client"
    client_version: str = "1.0.0"
    timeout_ms: int = 30000
    retry_attempts: int = 3
    retry_delay_ms: int = 1000
    enable_validation: bool = True
    enable_tool_discovery: bool = True
    enable_resource_discovery: bool = True
    strict_mode: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH
    metadata: JSONDict = field(default_factory=dict)

    def __post_init__(self):
        """Generate server_id if not provided."""
        if not self.server_name and self.server_url:
            self.server_name = self.server_url.split("/")[-1] or "unknown"


@dataclass
class MCPServerInfo:
    """Information about a connected MCP server."""

    name: str
    version: str
    protocol_version: str
    capabilities: JSONDict = field(default_factory=dict)
    constitutional_hash: str | None = None
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "protocol_version": self.protocol_version,
            "capabilities": self.capabilities,
            "constitutional_hash": self.constitutional_hash,
            "connected_at": self.connected_at.isoformat(),
        }


@dataclass
class MCPServerConnection:
    """Represents a connection to an MCP server."""

    server_id: str
    config: MCPClientConfig
    state: MCPClientState = MCPClientState.DISCONNECTED
    server_info: MCPServerInfo | None = None
    tools: list[JSONDict] = field(default_factory=list)
    resources: list[JSONDict] = field(default_factory=list)
    prompts: list[JSONDict] = field(default_factory=list)
    connected_at: datetime | None = None
    last_activity: datetime | None = None
    request_count: int = 0
    error_count: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "server_id": self.server_id,
            "server_url": self.config.server_url,
            "server_name": self.config.server_name,
            "state": self.state.value,
            "server_info": self.server_info.to_dict() if self.server_info else None,
            "tools_count": len(self.tools),
            "resources_count": len(self.resources),
            "prompts_count": len(self.prompts),
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "constitutional_hash": self.constitutional_hash,
        }


class MCPClient:
    """
    MCP Client for connecting to external MCP servers.

    Provides bidirectional communication with external MCP servers,
    enabling tool discovery, resource access, and governance integration.

    Constitutional Hash: 608508a9bd224290
    """

    CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH
    PROTOCOL_VERSION = "2024-11-05"

    def __init__(
        self,
        config: MCPClientConfig,
        validator: object | None = None,
        tool_registry: object | None = None,
        agent_id: str = "mcp-client",
    ):
        """
        Initialize MCP client.

        Args:
            config: Client configuration
            validator: Optional constitutional validator
            tool_registry: Optional tool registry for discovered tools
            agent_id: Agent ID for this client
        """
        self.config = config
        self.validator = validator
        self.tool_registry = tool_registry
        self.agent_id = agent_id

        # Generate server ID
        self.server_id = self._generate_server_id()

        # Connection state
        self._connection: MCPServerConnection | None = None
        self._lock = asyncio.Lock()

        # Request tracking
        self._request_id = 0
        self._pending_requests: dict[str, asyncio.Future] = {}

        # Metrics
        self._connection_attempts = 0
        self._successful_connections = 0
        self._total_requests = 0
        self._total_errors = 0

        # Event handlers
        self._on_connect_handlers: list[Callable] = []
        self._on_disconnect_handlers: list[Callable] = []
        self._on_error_handlers: list[Callable] = []

    def _generate_server_id(self) -> str:
        """Generate unique server ID."""
        content = f"{self.config.server_url}:{datetime.now(UTC).isoformat()}"
        if FAST_HASH_AVAILABLE:
            return f"{fast_hash(content):016x}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @property
    def state(self) -> MCPClientState:
        """Get current connection state."""
        return self._connection.state if self._connection else MCPClientState.DISCONNECTED

    @property
    def is_connected(self) -> bool:
        """Check if connected and ready."""
        return self._connection is not None and self._connection.state == MCPClientState.READY

    async def connect(self, session_id: str | None = None) -> bool:
        """
        Connect to the MCP server.

        Args:
            session_id: Optional session context

        Returns:
            True if connection successful
        """
        async with self._lock:
            self._connection_attempts += 1

            # Validate connection operation
            await self._validate_connection_request(session_id)

            # Create connection instance
            self._connection = MCPServerConnection(
                server_id=self.server_id,
                config=self.config,
                state=MCPClientState.CONNECTING,
            )

            try:
                # Establish transport connection with retries
                await self._connect_with_retries()

                # Initialize MCP protocol
                await self._initialize_protocol()

                # Perform capability discovery
                await self._perform_capability_discovery(session_id)

                # Finalize successful connection
                await self._finalize_connection()

                logger.info(
                    f"Connected to MCP server '{self.config.server_name}' (id: {self.server_id})"
                )
                return True

            except _MCP_CLIENT_OPERATION_ERRORS as e:
                self._handle_connection_failure(e)
                raise

    async def _validate_connection_request(self, session_id: str | None) -> None:
        """Validate the connection request against constitutional policies."""
        if self.validator and VALIDATORS_AVAILABLE:
            context = MCPOperationContext(
                operation_type=OperationType.CONNECTION_ESTABLISH,
                agent_id=self.agent_id,
                target_id=self.server_id,
                session_id=session_id,
                constitutional_hash=self.CONSTITUTIONAL_HASH,
            )
            validation = await self.validator.validate(context)
            if not validation.is_valid:
                logger.error(f"Connection validation failed: {validation.issues}")
                raise MCPConnectionError(
                    f"Connection validation failed: {[i.message for i in validation.issues]}",
                    server_id=self.server_id,
                )

    async def _connect_with_retries(self) -> None:
        """Establish connection with retry logic."""
        for attempt in range(self.config.retry_attempts):
            try:
                await self._establish_connection()
                break
            except _MCP_CLIENT_OPERATION_ERRORS as e:
                if attempt == self.config.retry_attempts - 1:
                    raise
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}, retrying...")
                await asyncio.sleep(self.config.retry_delay_ms / 1000.0)

    async def _perform_capability_discovery(self, session_id: str | None) -> None:
        """Discover server capabilities based on configuration."""
        if self.config.enable_tool_discovery:
            await self._discover_tools(session_id)

        if self.config.enable_resource_discovery:
            await self._discover_resources()

    async def _finalize_connection(self) -> None:
        """Finalize successful connection setup."""
        self._connection.state = MCPClientState.READY
        self._connection.connected_at = datetime.now(UTC)
        self._successful_connections += 1

        # Fire connect handlers
        await self._fire_connect_handlers()

    async def _fire_connect_handlers(self) -> None:
        """Execute registered connection event handlers safely."""
        for handler in self._on_connect_handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(self._connection)
                else:
                    handler(self._connection)
            except _MCP_CLIENT_OPERATION_ERRORS as e:
                logger.warning(f"Connect handler error: {e}")

    def _handle_connection_failure(self, error: Exception) -> None:
        """Handle connection failure with proper state management."""
        self._connection.state = MCPClientState.ERROR
        self._total_errors += 1
        logger.error(f"Connection failed: {error}")
        raise MCPConnectionError(
            f"Failed to connect to {self.config.server_url}: {error}",
            server_id=self.server_id,
        ) from error

    async def _establish_connection(self) -> None:
        """Establish the underlying transport connection."""
        # This would implement actual transport connection
        # For now, we simulate successful connection
        self._connection.state = MCPClientState.CONNECTED
        await asyncio.sleep(0.01)  # Simulate connection latency

    async def _initialize_protocol(self) -> None:
        """Initialize the MCP protocol with the server."""
        self._connection.state = MCPClientState.INITIALIZING

        # Send initialize request
        response = await self._send_request(
            "initialize",
            {
                "protocolVersion": self.PROTOCOL_VERSION,
                "clientInfo": {
                    "name": self.config.client_name,
                    "version": self.config.client_version,
                },
                "capabilities": {
                    "experimental": {
                        "constitutional_governance": True,
                        "constitutional_hash": self.CONSTITUTIONAL_HASH,
                    },
                },
            },
        )

        # Parse server info
        server_info = response.get("serverInfo", {})
        capabilities = response.get("capabilities", {})

        self._connection.server_info = MCPServerInfo(
            name=server_info.get("name", "unknown"),
            version=server_info.get("version", "unknown"),
            protocol_version=response.get("protocolVersion", "unknown"),
            capabilities=capabilities,
            constitutional_hash=capabilities.get("experimental", {}).get("constitutional_hash"),
        )

        # Send initialized notification
        await self._send_notification("initialized", {})

    async def _discover_tools(self, session_id: str | None = None) -> None:
        """Discover available tools from the server."""
        response = await self._send_request("tools/list", {})
        self._connection.tools = response.get("tools", [])

        # Register tools in registry if available
        if self.tool_registry and TOOL_REGISTRY_AVAILABLE:
            await self.tool_registry.discover_tools(
                server_id=self.server_id,
                server_name=self.config.server_name,
                tools_definitions=self._connection.tools,
                agent_id=self.agent_id,
                session_id=session_id,
            )

        logger.info(f"Discovered {len(self._connection.tools)} tools")

    async def _discover_resources(self) -> None:
        """Discover available resources from the server."""
        response = await self._send_request("resources/list", {})
        self._connection.resources = response.get("resources", [])
        logger.info(f"Discovered {len(self._connection.resources)} resources")

    async def disconnect(self, session_id: str | None = None) -> None:
        """
        Disconnect from the MCP server.

        Args:
            session_id: Optional session context
        """
        async with self._lock:
            if not self._connection:
                return

            # Validate disconnection
            if self.validator and VALIDATORS_AVAILABLE:
                context = MCPOperationContext(
                    operation_type=OperationType.CONNECTION_TERMINATE,
                    agent_id=self.agent_id,
                    target_id=self.server_id,
                    session_id=session_id,
                    constitutional_hash=self.CONSTITUTIONAL_HASH,
                )
                try:
                    await self.validator.validate(context)
                except _MCP_CLIENT_OPERATION_ERRORS as e:
                    logger.warning(f"Disconnect validation error: {e}")

            self._connection.state = MCPClientState.CLOSING

            # Cancel pending requests
            for _request_id, future in self._pending_requests.items():
                if not future.done():
                    future.cancel()
            self._pending_requests.clear()

            # Fire disconnect handlers
            for handler in self._on_disconnect_handlers:
                try:
                    if inspect.iscoroutinefunction(handler):
                        await handler(self._connection)
                    else:
                        handler(self._connection)
                except _MCP_CLIENT_OPERATION_ERRORS as e:
                    logger.warning(f"Disconnect handler error: {e}")

            self._connection.state = MCPClientState.DISCONNECTED
            logger.info(f"Disconnected from MCP server '{self.config.server_name}'")

    async def call_tool(
        self,
        tool_name: str,
        arguments: JSONDict,
        session_id: str | None = None,
    ) -> JSONDict:
        """
        Call a tool on the server.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            session_id: Optional session context

        Returns:
            Tool execution result
        """
        if not self.is_connected:
            raise MCPConnectionError("Not connected to server", server_id=self.server_id)

        # Validate tool call
        if self.validator and VALIDATORS_AVAILABLE:
            context = MCPOperationContext(
                operation_type=OperationType.TOOL_CALL,
                agent_id=self.agent_id,
                tool_name=tool_name,
                target_id=self.server_id,
                arguments=arguments,
                session_id=session_id,
                constitutional_hash=self.CONSTITUTIONAL_HASH,
            )
            validation = await self.validator.validate(context)
            if not validation.is_valid:
                raise MCPConnectionError(
                    f"Tool call validation failed: {[i.message for i in validation.issues]}",
                    server_id=self.server_id,
                )

        response = await self._send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )

        self._connection.last_activity = datetime.now(UTC)
        return response

    async def read_resource(
        self,
        uri: str,
        session_id: str | None = None,
    ) -> JSONDict:
        """
        Read a resource from the server.

        Args:
            uri: Resource URI
            session_id: Optional session context

        Returns:
            Resource content
        """
        if not self.is_connected:
            raise MCPConnectionError("Not connected to server", server_id=self.server_id)

        # Validate resource read
        if self.validator and VALIDATORS_AVAILABLE:
            context = MCPOperationContext(
                operation_type=OperationType.RESOURCE_READ,
                agent_id=self.agent_id,
                resource_uri=uri,
                target_id=self.server_id,
                session_id=session_id,
                constitutional_hash=self.CONSTITUTIONAL_HASH,
            )
            validation = await self.validator.validate(context)
            if not validation.is_valid:
                raise MCPConnectionError(
                    f"Resource read validation failed: {[i.message for i in validation.issues]}",
                    server_id=self.server_id,
                )

        response = await self._send_request(
            "resources/read",
            {"uri": uri},
        )

        self._connection.last_activity = datetime.now(UTC)
        return response

    async def ping(self) -> JSONDict:
        """
        Ping the server.

        Returns:
            Ping response
        """
        if not self.is_connected:
            raise MCPConnectionError("Not connected to server", server_id=self.server_id)

        return await self._send_request("ping", {})

    async def _send_request(
        self,
        method: str,
        params: JSONDict,
    ) -> JSONDict:
        """Send a request to the server."""
        self._request_id += 1
        request_id = str(self._request_id)
        self._total_requests += 1

        if self._connection:
            self._connection.request_count += 1

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        # Create future for response
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            # Simulate sending request and receiving response
            # In real implementation, this would use actual transport
            response = await self._simulate_request(request)

            if "error" in response:
                error = response["error"]
                raise MCPConnectionError(
                    f"Server error: {error.get('message', 'Unknown error')}",
                    server_id=self.server_id,
                    error_code=error.get("code"),
                )

            return response.get("result", {})

        except TimeoutError:
            self._total_errors += 1
            if self._connection:
                self._connection.error_count += 1
            raise MCPConnectionError(
                f"Request timed out after {self.config.timeout_ms}ms",
                server_id=self.server_id,
            ) from None
        finally:
            self._pending_requests.pop(request_id, None)

    async def _send_notification(self, method: str, params: JSONDict) -> None:
        """Send a notification to the server (no response expected)."""
        # In real implementation, this would send via transport
        logger.debug(f"Sent notification: {method}")

    async def _simulate_request(self, request: JSONDict) -> JSONDict:
        """Simulate request/response for testing."""
        # This simulates server responses for testing
        # In real implementation, this would use actual transport

        method = request.get("method", "")
        await asyncio.sleep(0.01)  # Simulate network latency

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": True},
                        "resources": {"subscribe": True, "listChanged": True},
                        "experimental": {
                            "constitutional_governance": True,
                            "constitutional_hash": self.CONSTITUTIONAL_HASH,
                        },
                    },
                    "serverInfo": {
                        "name": self.config.server_name or "simulated-server",
                        "version": "1.0.0",
                    },
                },
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "tools": [
                        {
                            "name": "example_tool",
                            "description": "An example tool",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"input": {"type": "string"}},
                            },
                        }
                    ]
                },
            }

        elif method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "resources": [
                        {
                            "uri": "example://resource",
                            "name": "Example Resource",
                            "description": "An example resource",
                            "mimeType": "application/json",
                        }
                    ]
                },
            }

        elif method == "tools/call":
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "content": [{"type": "text", "text": "Tool executed successfully"}],
                    "isError": False,
                },
            }

        elif method == "resources/read":
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "contents": [
                        {
                            "uri": request["params"].get("uri"),
                            "mimeType": "application/json",
                            "text": '{"example": "data"}',
                        }
                    ]
                },
            }

        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "status": "ok",
                    "constitutional_hash": self.CONSTITUTIONAL_HASH,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }

    # Event handlers

    def on_connect(self, handler: Callable) -> None:
        """Register connect event handler."""
        self._on_connect_handlers.append(handler)

    def on_disconnect(self, handler: Callable) -> None:
        """Register disconnect event handler."""
        self._on_disconnect_handlers.append(handler)

    def on_error(self, handler: Callable) -> None:
        """Register error event handler."""
        self._on_error_handlers.append(handler)

    # Metrics and info

    def get_connection_info(self) -> JSONDict | None:
        """Get current connection info."""
        return self._connection.to_dict() if self._connection else None

    def get_tools(self) -> list[JSONDict]:
        """Get discovered tools."""
        return self._connection.tools if self._connection else []

    def get_resources(self) -> list[JSONDict]:
        """Get discovered resources."""
        return self._connection.resources if self._connection else []

    def get_metrics(self) -> JSONDict:
        """Get client metrics."""
        return {
            "server_id": self.server_id,
            "server_url": self.config.server_url,
            "state": self.state.value,
            "connection_attempts": self._connection_attempts,
            "successful_connections": self._successful_connections,
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "pending_requests": len(self._pending_requests),
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }


class MCPConnectionPool:
    """
    Connection pool for managing multiple MCP server connections.

    Supports connecting to 16,000+ MCP servers with constitutional governance.

    Constitutional Hash: 608508a9bd224290
    """

    CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH
    MAX_CONNECTIONS = 20000  # Support for 16,000+ servers with headroom

    def __init__(
        self,
        validator: object | None = None,
        tool_registry: object | None = None,
        default_agent_id: str = "mcp-pool",
    ):
        """
        Initialize connection pool.

        Args:
            validator: Optional constitutional validator
            tool_registry: Optional tool registry
            default_agent_id: Default agent ID for connections
        """
        self.validator = validator
        self.tool_registry = tool_registry
        self.default_agent_id = default_agent_id

        self._clients: dict[str, MCPClient] = {}
        self._lock = asyncio.Lock()

    async def add_server(
        self,
        config: MCPClientConfig,
        agent_id: str | None = None,
        auto_connect: bool = True,
    ) -> MCPClient:
        """
        Add a server to the pool.

        Args:
            config: Server configuration
            agent_id: Optional agent ID for this connection
            auto_connect: Auto-connect to server

        Returns:
            MCPClient instance
        """
        async with self._lock:
            if len(self._clients) >= self.MAX_CONNECTIONS:
                raise MCPConnectionError(f"Maximum connections reached ({self.MAX_CONNECTIONS})")

            client = MCPClient(
                config=config,
                validator=self.validator,
                tool_registry=self.tool_registry,
                agent_id=agent_id or self.default_agent_id,
            )

            self._clients[client.server_id] = client

            if auto_connect:
                await client.connect()

            return client

    async def remove_server(self, server_id: str) -> bool:
        """
        Remove a server from the pool.

        Args:
            server_id: Server ID to remove

        Returns:
            True if server was removed
        """
        async with self._lock:
            if server_id not in self._clients:
                return False

            client = self._clients[server_id]
            if client.is_connected:
                await client.disconnect()

            del self._clients[server_id]
            return True

    def get_client(self, server_id: str) -> MCPClient | None:
        """Get a client by server ID."""
        return self._clients.get(server_id)

    def list_servers(self) -> list[JSONDict]:
        """List all servers in the pool."""
        return [
            client.get_connection_info() or {"server_id": sid, "state": "unknown"}
            for sid, client in self._clients.items()
        ]

    async def connect_all(self) -> dict[str, bool]:
        """
        Connect to all servers in the pool.

        Returns:
            Dict of server_id to connection success
        """
        results = {}
        tasks = []

        for server_id, client in self._clients.items():
            if not client.is_connected:
                tasks.append((server_id, client.connect()))

        if tasks:
            outcomes = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
            for i, (server_id, _) in enumerate(tasks):
                results[server_id] = not isinstance(outcomes[i], Exception)

        return results

    async def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        tasks = [client.disconnect() for client in self._clients.values() if client.is_connected]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_metrics(self) -> JSONDict:
        """Get pool metrics."""
        connected = sum(1 for c in self._clients.values() if c.is_connected)
        return {
            "total_servers": len(self._clients),
            "connected_servers": connected,
            "disconnected_servers": len(self._clients) - connected,
            "max_connections": self.MAX_CONNECTIONS,
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }


def create_mcp_client(
    config: MCPClientConfig,
    validator: object | None = None,
    tool_registry: object | None = None,
    agent_id: str = "mcp-client",
) -> MCPClient:
    """
    Factory function to create an MCP client.

    Args:
        config: Client configuration
        validator: Optional constitutional validator
        tool_registry: Optional tool registry
        agent_id: Agent ID for the client

    Returns:
        Configured MCPClient instance
    """
    return MCPClient(
        config=config,
        validator=validator,
        tool_registry=tool_registry,
        agent_id=agent_id,
    )


__all__ = [
    "MCPClient",
    "MCPClientConfig",
    "MCPClientState",
    "MCPConnectionError",
    "MCPConnectionPool",
    "MCPServerConnection",
    "MCPServerInfo",
    "MCPTransportType",
    "create_mcp_client",
]
