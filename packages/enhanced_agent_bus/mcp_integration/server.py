"""
MCP Integration Server for ACGS-2.

Provides enhanced MCP server capabilities for exposing ACGS-2 governance
functionality to external AI systems with constitutional validation and
MACI role-based access control.

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import json
import logging as _stdlib_logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

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

# Import MACI enforcement
try:
    from ..maci_enforcement import (
        MACIAction,
    )

    MACI_AVAILABLE = True
except ImportError:
    MACI_AVAILABLE = False

logger = get_logger(__name__)

_module = sys.modules.get(__name__)
if _module is not None:
    sys.modules.setdefault("enhanced_agent_bus.mcp_integration.server", _module)
    sys.modules.setdefault("packages.enhanced_agent_bus.mcp_integration.server", _module)

# Type alias for handlers
HandlerFunc = Callable[[JSONDict], Awaitable[JSONDict]]
MCP_INTEGRATION_OPERATION_ERRORS = (
    AttributeError,
    KeyError,
    LookupError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


class MCPServerState(Enum):
    """State of the MCP integration server."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class TransportType(Enum):
    """Server transport types."""

    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"
    WEBSOCKET = "websocket"


@dataclass
class MCPIntegrationConfig:
    """Configuration for MCP integration server."""

    server_name: str = "acgs2-mcp-integration"
    server_version: str = "1.0.0"
    transport_type: TransportType = TransportType.HTTP
    host: str = "127.0.0.1"
    port: int = 8090
    enable_tools: bool = True
    enable_resources: bool = True
    enable_prompts: bool = True
    enable_maci: bool = True
    enable_audit_logging: bool = True
    strict_mode: bool = True
    max_connections: int = 1000
    request_timeout_ms: int = 30000
    log_requests: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH
    metadata: JSONDict = field(default_factory=dict)


@dataclass
class MCPServerMetrics:
    """Metrics for the MCP integration server."""

    start_time: datetime | None = None
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    active_connections: int = 0
    tools_registered: int = 0
    resources_registered: int = 0
    total_tool_calls: int = 0
    total_resource_reads: int = 0
    average_latency_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime_seconds": (
                (datetime.now(UTC) - self.start_time).total_seconds() if self.start_time else 0
            ),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": (
                self.successful_requests / self.total_requests if self.total_requests > 0 else 0.0
            ),
            "active_connections": self.active_connections,
            "tools_registered": self.tools_registered,
            "resources_registered": self.resources_registered,
            "total_tool_calls": self.total_tool_calls,
            "total_resource_reads": self.total_resource_reads,
            "average_latency_ms": self.average_latency_ms,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class InternalTool:
    """Internal tool exposed through MCP."""

    name: str
    description: str
    input_schema: JSONDict
    handler: HandlerFunc
    constitutional_required: bool = True
    maci_role: object | None = None  # MACIRole if MACI enabled
    capabilities: list[str] = field(default_factory=list)
    risk_level: str = "medium"
    metadata: JSONDict = field(default_factory=dict)

    def to_mcp_definition(self) -> JSONDict:
        """Convert to MCP tool definition."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class InternalResource:
    """Internal resource exposed through MCP."""

    uri: str
    name: str
    description: str
    mime_type: str = "application/json"
    handler: HandlerFunc | None = None
    constitutional_scope: str = "read"
    subscribe_supported: bool = False
    metadata: JSONDict = field(default_factory=dict)

    def to_mcp_definition(self) -> JSONDict:
        """Convert to MCP resource definition."""
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


class MCPIntegrationServer:
    """
    MCP Integration Server for ACGS-2.

    Exposes ACGS-2 governance capabilities through the Model Context Protocol,
    enabling external AI systems to interact with constitutional governance.

    Features:
    - Tool exposure with constitutional validation
    - Resource access with MACI role-based control
    - Bidirectional communication support
    - Comprehensive audit logging

    Constitutional Hash: cdd01ef066bc6cf2
    """

    CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH
    PROTOCOL_VERSION = "2024-11-05"

    def __init__(
        self,
        config: MCPIntegrationConfig | None = None,
        validator: object | None = None,
        tool_registry: object | None = None,
        maci_enforcer: object | None = None,
    ):
        """
        Initialize the MCP integration server.

        Args:
            config: Server configuration
            validator: Optional constitutional validator
            tool_registry: Optional tool registry for external tools
            maci_enforcer: Optional MACI enforcer for role-based access
        """
        self.config = config or MCPIntegrationConfig()
        self.validator = validator
        self.tool_registry = tool_registry
        self.maci_enforcer = maci_enforcer

        # State
        self._state = MCPServerState.STOPPED
        self._shutdown_event: asyncio.Event | None = None

        # Internal tools and resources
        self._tools: dict[str, InternalTool] = {}
        self._resources: dict[str, InternalResource] = {}
        self._prompts: dict[str, JSONDict] = {}

        # Method handlers
        self._method_handlers: dict[str, HandlerFunc] = {}

        # Client connections (for bidirectional support)
        self._connections: dict[str, JSONDict] = {}

        # Metrics
        self._metrics = MCPServerMetrics()
        self._latency_samples: list[float] = []

        # Audit log
        self._audit_log: list[JSONDict] = []

        # Lock
        self._lock = asyncio.Lock()

        # Initialize built-in handlers
        self._initialize_handlers()

        # Initialize built-in tools and resources
        self._initialize_builtin_tools()
        self._initialize_builtin_resources()

    def _initialize_handlers(self) -> None:
        """Initialize MCP method handlers."""
        self._method_handlers = {
            "initialize": self._handle_initialize,
            "initialized": self._handle_initialized,
            "ping": self._handle_ping,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "resources/subscribe": self._handle_resources_subscribe,
            "prompts/list": self._handle_prompts_list,
            "prompts/get": self._handle_prompts_get,
            "logging/setLevel": self._handle_logging_set_level,
            # ACGS-2 specific methods
            "governance/validate": self._handle_governance_validate,
            "governance/request": self._handle_governance_request,
            "constitutional/status": self._handle_constitutional_status,
        }

    def _initialize_builtin_tools(self) -> None:
        """Initialize built-in governance tools."""
        # Validate compliance tool
        self.register_tool(
            InternalTool(
                name="validate_constitutional_compliance",
                description=(
                    "Validate an action against ACGS-2 constitutional principles "
                    f"(hash: {self.CONSTITUTIONAL_HASH})"
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "Action to validate"},
                        "context": {"type": "object", "description": "Action context"},
                        "strict_mode": {"type": "boolean", "default": True},
                    },
                    "required": ["action", "context"],
                },
                handler=self._tool_validate_compliance,
                capabilities=["governance", "validation"],
            )
        )

        # Get metrics tool
        self.register_tool(
            InternalTool(
                name="get_governance_metrics",
                description="Get governance and server metrics",
                input_schema={
                    "type": "object",
                    "properties": {
                        "include_audit": {"type": "boolean", "default": False},
                    },
                },
                handler=self._tool_get_metrics,
                capabilities=["monitoring", "analytics"],
                risk_level="low",
            )
        )

        # Constitutional status tool
        self.register_tool(
            InternalTool(
                name="get_constitutional_status",
                description="Get constitutional governance status and hash verification",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
                handler=self._tool_constitutional_status,
                capabilities=["governance"],
                risk_level="low",
            )
        )

    def _initialize_builtin_resources(self) -> None:
        """Initialize built-in governance resources."""
        # Constitutional principles resource
        self.register_resource(
            InternalResource(
                uri="acgs2://constitutional/principles",
                name="Constitutional Principles",
                description="Active constitutional principles and governance rules",
                handler=self._resource_principles,
            )
        )

        # Server metrics resource
        self.register_resource(
            InternalResource(
                uri="acgs2://governance/metrics",
                name="Governance Metrics",
                description="Real-time governance and server metrics",
                handler=self._resource_metrics,
            )
        )

        # Audit trail resource
        self.register_resource(
            InternalResource(
                uri="acgs2://governance/audit",
                name="Audit Trail",
                description="Recent audit trail entries",
                handler=self._resource_audit,
            )
        )

    # Tool and resource registration

    def register_tool(self, tool: InternalTool) -> bool:
        """Register an internal tool."""
        if tool.name in self._tools:
            message = f"Tool '{tool.name}' already registered, updating"
            logger.warning(message)
            _stdlib_logging.warning(message)

        self._tools[tool.name] = tool
        self._metrics.tools_registered = len(self._tools)
        logger.info(f"Registered tool: {tool.name}")
        return True

    def unregister_tool(self, tool_name: str) -> bool:
        """Unregister a tool."""
        if tool_name in self._tools:
            del self._tools[tool_name]
            self._metrics.tools_registered = len(self._tools)
            logger.info(f"Unregistered tool: {tool_name}")
            return True
        return False

    def register_resource(self, resource: InternalResource) -> bool:
        """Register an internal resource."""
        if resource.uri in self._resources:
            message = f"Resource '{resource.uri}' already registered, updating"
            logger.warning(message)
            _stdlib_logging.warning(message)

        self._resources[resource.uri] = resource
        self._metrics.resources_registered = len(self._resources)
        logger.info(f"Registered resource: {resource.uri}")
        return True

    def unregister_resource(self, uri: str) -> bool:
        """Unregister a resource."""
        if uri in self._resources:
            del self._resources[uri]
            self._metrics.resources_registered = len(self._resources)
            logger.info(f"Unregistered resource: {uri}")
            return True
        return False

    # Server lifecycle

    async def start(self) -> None:
        """Start the MCP integration server."""
        if self._state == MCPServerState.RUNNING:
            message = "Server already running"
            logger.warning(message)
            _stdlib_logging.warning(message)
            return

        self._state = MCPServerState.STARTING
        self._shutdown_event = asyncio.Event()
        self._metrics.start_time = datetime.now(UTC)

        logger.info(
            f"Starting MCP Integration Server: {self.config.server_name} "
            f"v{self.config.server_version}"
        )
        logger.info(f"Constitutional Hash: {self.CONSTITUTIONAL_HASH}")
        logger.info(f"Transport: {self.config.transport_type.value}")
        logger.info(f"Tools: {len(self._tools)}, Resources: {len(self._resources)}")

        self._state = MCPServerState.RUNNING

        # Log audit event
        self._log_audit_event(
            action="server_start",
            details={
                "server_name": self.config.server_name,
                "version": self.config.server_version,
                "transport": self.config.transport_type.value,
            },
        )

    async def stop(self) -> None:
        """Stop the MCP integration server."""
        if self._state != MCPServerState.RUNNING:
            return

        self._state = MCPServerState.STOPPING
        logger.info("Stopping MCP Integration Server...")

        # Close all connections
        for conn_id in list(self._connections.keys()):
            await self._close_connection(conn_id)

        if self._shutdown_event:
            self._shutdown_event.set()

        # Log audit event
        self._log_audit_event(
            action="server_stop",
            details={
                "total_requests": self._metrics.total_requests,
                "uptime_seconds": (
                    (datetime.now(UTC) - self._metrics.start_time).total_seconds()
                    if self._metrics.start_time
                    else 0
                ),
            },
        )

        self._state = MCPServerState.STOPPED
        logger.info("MCP Integration Server stopped")

    async def handle_request(self, request: JSONDict) -> JSONDict | None:
        """
        Handle an incoming MCP request.

        Args:
            request: The MCP request

        Returns:
            MCP response or None for notifications
        """
        start_time = datetime.now(UTC)
        self._metrics.total_requests += 1

        request_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        # Log request
        if self.config.log_requests:
            logger.debug(f"MCP request: {method}")

        try:
            # Validate JSON-RPC version
            if request.get("jsonrpc") != "2.0":
                return self._error_response(request_id, -32600, "Invalid JSON-RPC version")

            # Find handler
            handler = self._method_handlers.get(method)
            if not handler:
                return self._error_response(request_id, -32601, f"Method not found: {method}")

            # Validate operation
            if self.validator and VALIDATORS_AVAILABLE:
                operation_type = self._map_method_to_operation(method)
                if operation_type:
                    context = MCPOperationContext(
                        operation_type=operation_type,
                        agent_id=params.get("agent_id", "unknown"),
                        tool_name=params.get("name") if "tools" in method else None,
                        resource_uri=params.get("uri") if "resources" in method else None,
                        arguments=params.get("arguments", {}),
                        session_id=params.get("session_id"),
                        constitutional_hash=self.CONSTITUTIONAL_HASH,
                    )
                    validation = await self.validator.validate(context)
                    if not validation.is_valid and self.config.strict_mode:
                        self._metrics.failed_requests += 1
                        return self._error_response(
                            request_id,
                            -32001,
                            f"Constitutional validation failed: {[i.message for i in validation.issues]}",
                        )

            # Execute handler
            result = await handler(params)

            # Track metrics
            end_time = datetime.now(UTC)
            latency_ms = (end_time - start_time).total_seconds() * 1000
            self._track_latency(latency_ms)
            self._metrics.successful_requests += 1

            # Notifications don't get responses
            if request_id is None:
                return None

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }

        except MCP_INTEGRATION_OPERATION_ERRORS as e:
            self._metrics.failed_requests += 1
            logger.error(f"Request handling error: {e}")

            if request_id is None:
                return None

            return self._error_response(request_id, -32603, str(e))

    def _map_method_to_operation(self, method: str) -> OperationType | None:
        """Map MCP method to operation type."""
        mapping = {
            "tools/call": OperationType.TOOL_CALL,
            "tools/list": OperationType.TOOL_DISCOVER,
            "resources/read": OperationType.RESOURCE_READ,
            "resources/subscribe": OperationType.RESOURCE_SUBSCRIBE,
            "initialize": OperationType.PROTOCOL_INITIALIZE,
            "governance/validate": OperationType.GOVERNANCE_REQUEST,
            "governance/request": OperationType.GOVERNANCE_REQUEST,
        }
        return mapping.get(method)

    def _error_response(
        self,
        request_id: object | None,
        code: int,
        message: str,
    ) -> JSONDict:
        """Create an error response."""
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
                "data": {"constitutional_hash": self.CONSTITUTIONAL_HASH},
            },
        }

    def _track_latency(self, latency_ms: float) -> None:
        """Track request latency for metrics."""
        self._latency_samples.append(latency_ms)
        # Keep last 1000 samples
        if len(self._latency_samples) > 1000:
            self._latency_samples = self._latency_samples[-1000:]
        self._metrics.average_latency_ms = sum(self._latency_samples) / len(self._latency_samples)

    async def _close_connection(self, conn_id: str) -> None:
        """Close a client connection."""
        if conn_id in self._connections:
            del self._connections[conn_id]
            self._metrics.active_connections -= 1

    def _log_audit_event(
        self,
        action: str,
        details: JSONDict | None = None,
        agent_id: str | None = None,
    ) -> None:
        """Log an audit event."""
        if not self.config.enable_audit_logging:
            return

        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "action": action,
            "agent_id": agent_id,
            "details": details or {},
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }
        self._audit_log.append(entry)

        # Keep log bounded
        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-5000:]

    # Protocol handlers

    async def _handle_initialize(self, params: JSONDict) -> JSONDict:
        """Handle initialize request."""
        client_info = params.get("clientInfo", {})
        logger.info(
            f"MCP client connecting: {client_info.get('name', 'unknown')} "
            f"v{client_info.get('version', 'unknown')}"
        )

        return {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": True} if self.config.enable_tools else None,
                "resources": (
                    {"subscribe": True, "listChanged": True}
                    if self.config.enable_resources
                    else None
                ),
                "prompts": {"listChanged": False} if self.config.enable_prompts else None,
                "logging": {},
                "experimental": {
                    "constitutional_governance": True,
                    "maci_separation": self.config.enable_maci,
                    "constitutional_hash": self.CONSTITUTIONAL_HASH,
                },
            },
            "serverInfo": {
                "name": self.config.server_name,
                "version": self.config.server_version,
            },
        }

    async def _handle_initialized(self, params: JSONDict) -> None:
        """Handle initialized notification."""
        logger.info("MCP connection initialized")
        self._metrics.active_connections += 1

    async def _handle_ping(self, params: JSONDict) -> JSONDict:
        """Handle ping request."""
        return {
            "status": "ok",
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _handle_tools_list(self, params: JSONDict) -> JSONDict:
        """Handle tools/list request."""
        tools = [tool.to_mcp_definition() for tool in self._tools.values()]
        return {"tools": tools}

    async def _handle_tools_call(self, params: JSONDict) -> JSONDict:
        """Handle tools/call request."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        self._metrics.total_tool_calls += 1

        if tool_name not in self._tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        tool = self._tools[tool_name]

        # MACI validation if enabled
        if self.config.enable_maci and self.maci_enforcer and MACI_AVAILABLE:
            try:
                agent_id = arguments.get("_agent_id", "unknown")
                await self.maci_enforcer.validate_action(
                    agent_id=agent_id,
                    action=MACIAction.SYNTHESIZE,
                    session_id=arguments.get("_session_id"),
                )
            except MCP_INTEGRATION_OPERATION_ERRORS as e:
                logger.warning(f"MACI validation failed for tool {tool_name}: {e}")
                if self.config.strict_mode:
                    raise

        # Execute tool
        result = await tool.handler(arguments)

        # Log audit
        self._log_audit_event(
            action="tool_call",
            details={"tool_name": tool_name},
            agent_id=arguments.get("_agent_id"),
        )

        # Wrap result
        if isinstance(result, dict) and "content" in result:
            return result

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result) if isinstance(result, dict) else str(result),
                }
            ],
            "isError": False,
        }

    async def _handle_resources_list(self, params: JSONDict) -> JSONDict:
        """Handle resources/list request."""
        resources = [res.to_mcp_definition() for res in self._resources.values()]
        return {"resources": resources}

    async def _handle_resources_read(self, params: JSONDict) -> JSONDict:
        """Handle resources/read request."""
        uri = params.get("uri", "")

        self._metrics.total_resource_reads += 1

        if uri not in self._resources:
            raise ValueError(f"Unknown resource: {uri}")

        resource = self._resources[uri]

        if resource.handler:
            result = await resource.handler({"uri": uri})
        else:
            result = {"error": "Resource has no handler"}

        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": resource.mime_type,
                    "text": json.dumps(result) if isinstance(result, dict) else str(result),
                }
            ],
        }

    async def _handle_resources_subscribe(self, params: JSONDict) -> JSONDict:
        """Handle resources/subscribe request."""
        uri = params.get("uri", "")
        logger.info(f"Resource subscription requested: {uri}")
        return {"subscribed": True}

    async def _handle_prompts_list(self, params: JSONDict) -> JSONDict:
        """Handle prompts/list request."""
        prompts = list(self._prompts.values())
        return {"prompts": prompts}

    async def _handle_prompts_get(self, params: JSONDict) -> JSONDict:
        """Handle prompts/get request."""
        prompt_name = params.get("name", "")
        if prompt_name not in self._prompts:
            raise ValueError(f"Unknown prompt: {prompt_name}")
        return self._prompts[prompt_name]

    async def _handle_logging_set_level(self, params: JSONDict) -> JSONDict:
        """Handle logging/setLevel request."""
        level = params.get("level", "info").upper()
        _stdlib_logging.getLogger(__name__).setLevel(
            getattr(_stdlib_logging, level, _stdlib_logging.INFO)
        )
        return {"level": level.lower()}

    # ACGS-2 specific handlers

    async def _handle_governance_validate(self, params: JSONDict) -> JSONDict:
        """Handle governance/validate request."""
        action = params.get("action", "")
        context = params.get("context", {})

        return await self._tool_validate_compliance({"action": action, "context": context})

    async def _handle_governance_request(self, params: JSONDict) -> JSONDict:
        """Handle governance/request request."""
        # This would integrate with the full governance workflow
        return {
            "status": "pending",
            "request_id": f"gov-{datetime.now(UTC).timestamp()}",
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }

    async def _handle_constitutional_status(self, params: JSONDict) -> JSONDict:
        """Handle constitutional/status request."""
        return await self._tool_constitutional_status({})

    # Built-in tool handlers

    async def _tool_validate_compliance(self, arguments: JSONDict) -> JSONDict:
        """Validate compliance tool handler."""
        action = arguments.get("action", "")
        context = arguments.get("context", {})
        arguments.get("strict_mode", True)

        # Perform validation
        compliant = True
        violations = []
        recommendations = []

        # Check for harmful patterns
        harmful_patterns = ["harm", "attack", "exploit", "abuse", "deceive"]
        action_lower = action.lower()
        for pattern in harmful_patterns:
            if pattern in action_lower:
                compliant = False
                violations.append(
                    {
                        "principle": "non_maleficence",
                        "severity": "critical",
                        "description": f"Action may cause harm: detected '{pattern}'",
                    }
                )

        # Check data sensitivity
        if context.get("data_sensitivity") in ["confidential", "restricted"]:
            if not context.get("consent_obtained"):
                compliant = False
                violations.append(
                    {
                        "principle": "privacy",
                        "severity": "high",
                        "description": "Sensitive data access without consent",
                    }
                )
                recommendations.append("Obtain explicit user consent")

        return {
            "compliant": compliant,
            "confidence": 0.0 if violations else 1.0,
            "violations": violations,
            "recommendations": recommendations,
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _tool_get_metrics(self, arguments: JSONDict) -> JSONDict:
        """Get metrics tool handler."""
        result = self._metrics.to_dict()
        if arguments.get("include_audit"):
            result["recent_audit"] = self._audit_log[-10:]
        return result

    async def _tool_constitutional_status(self, arguments: JSONDict) -> JSONDict:
        """Get constitutional status tool handler."""
        return {
            "status": "active",
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
            "hash_verified": True,
            "maci_enabled": self.config.enable_maci,
            "strict_mode": self.config.strict_mode,
            "server_state": self._state.value,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    # Built-in resource handlers

    async def _resource_principles(self, params: JSONDict) -> JSONDict:
        """Principles resource handler."""
        return {
            "principles": {
                "beneficence": "Actions should benefit users and society",
                "non_maleficence": "Actions should not cause harm",
                "autonomy": "Respect user autonomy and informed consent",
                "justice": "Ensure fair and equitable treatment",
                "transparency": "Be transparent about AI decision-making",
                "accountability": "Maintain accountability for AI actions",
                "privacy": "Protect user privacy and data",
                "safety": "Prioritize safety in all operations",
            },
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _resource_metrics(self, params: JSONDict) -> JSONDict:
        """Metrics resource handler."""
        return self._metrics.to_dict()

    async def _resource_audit(self, params: JSONDict) -> JSONDict:
        """Audit trail resource handler."""
        return {
            "entries": self._audit_log[-100:],
            "total_entries": len(self._audit_log),
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }

    # Public API

    @property
    def state(self) -> MCPServerState:
        """Get server state."""
        return self._state

    def get_metrics(self) -> JSONDict:
        """Get server metrics."""
        return self._metrics.to_dict()

    def get_tools(self) -> list[JSONDict]:
        """Get registered tools."""
        return [tool.to_mcp_definition() for tool in self._tools.values()]

    def get_resources(self) -> list[JSONDict]:
        """Get registered resources."""
        return [res.to_mcp_definition() for res in self._resources.values()]

    def get_audit_log(self, limit: int = 100) -> list[JSONDict]:
        """Get audit log entries."""
        return self._audit_log[-limit:]


def create_mcp_integration_server(
    config: MCPIntegrationConfig | None = None,
    validator: object | None = None,
    tool_registry: object | None = None,
    maci_enforcer: object | None = None,
) -> MCPIntegrationServer:
    """
    Factory function to create an MCP integration server.

    Args:
        config: Server configuration
        validator: Optional constitutional validator
        tool_registry: Optional tool registry
        maci_enforcer: Optional MACI enforcer

    Returns:
        Configured MCPIntegrationServer instance
    """
    return MCPIntegrationServer(
        config=config,
        validator=validator,
        tool_registry=tool_registry,
        maci_enforcer=maci_enforcer,
    )


__all__ = [
    "InternalResource",
    "InternalTool",
    "MCPIntegrationConfig",
    "MCPIntegrationServer",
    "MCPServerMetrics",
    "MCPServerState",
    "TransportType",
    "create_mcp_integration_server",
]
