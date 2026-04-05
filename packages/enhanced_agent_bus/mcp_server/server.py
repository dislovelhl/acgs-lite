"""
MCP Server for ACGS-2 Constitutional Governance.

Main server implementation providing constitutional AI governance
through the Model Context Protocol.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import inspect
import json
import sys
from dataclasses import dataclass, field

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .adapters.agent_bus import AgentBusAdapter
from .adapters.audit_client import AuditClientAdapter
from .adapters.policy_client import PolicyClientAdapter
from .config import MCPConfig, TransportType
from .protocol.handler import MCPHandler
from .protocol.types import (
    MCPError,
    MCPRequest,
    MCPResponse,
    ResourceDefinition,
    ServerCapabilities,
    ToolDefinition,
)
from .resources.audit_trail import AuditEventType, AuditTrailResource
from .resources.decisions import DecisionsResource
from .resources.metrics import MetricsResource
from .resources.principles import PrinciplesResource
from .tools.get_metrics import GetMetricsTool
from .tools.get_principles import GetPrinciplesTool
from .tools.query_precedents import QueryPrecedentsTool
from .tools.submit_governance import SubmitGovernanceTool
from .tools.validate_compliance import ValidateComplianceTool

logger = get_logger(__name__)

MCP_SERVER_OPERATION_ERRORS = (
    AttributeError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


@dataclass
class MCPServer:
    """
    MCP Server for Constitutional AI Governance.

    Provides constitutional validation, principle management,
    precedent queries, and governance request handling through
    the Model Context Protocol.
    """

    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    PROTOCOL_VERSION = "2024-11-05"

    config: MCPConfig = field(default_factory=MCPConfig)

    # Internal state
    _handler: MCPHandler | None = field(default=None, init=False)
    _tools: JSONDict = field(default_factory=dict, init=False)
    _resources: JSONDict = field(default_factory=dict, init=False)
    _adapters: JSONDict = field(default_factory=dict, init=False)
    _running: bool = field(default=False, init=False)
    _shutdown_event: asyncio.Event | None = field(default=None, init=False)
    _request_count: int = field(default=0, init=False)
    _error_count: int = field(default=0, init=False)

    def __post_init__(self):
        """Initialize server components."""
        self._handler = MCPHandler(self.config)
        self._shutdown_event = asyncio.Event()
        self._initialize_adapters()
        self._initialize_tools()
        self._initialize_resources()
        self._register_handlers()

    def _initialize_adapters(self) -> None:
        """Initialize adapters for external services."""
        self._adapters = {
            "agent_bus": AgentBusAdapter(mcp_agent_id=f"mcp-{self.config.server_name}"),
            "policy_client": PolicyClientAdapter(),
            "audit_client": AuditClientAdapter(),
        }
        logger.info("MCP adapters initialized")

    def _initialize_tools(self) -> None:
        """Initialize MCP tools."""
        policy_adapter = self._adapters.get("policy_client")
        audit_adapter = self._adapters.get("audit_client")
        agent_bus_adapter = self._adapters.get("agent_bus")

        self._tools = {
            "validate_constitutional_compliance": ValidateComplianceTool(
                agent_bus_adapter=agent_bus_adapter,
            ),
            "get_active_principles": GetPrinciplesTool(
                policy_client_adapter=policy_adapter,
            ),
            "query_governance_precedents": QueryPrecedentsTool(
                audit_client_adapter=audit_adapter,
            ),
            "submit_governance_request": SubmitGovernanceTool(
                agent_bus_adapter=agent_bus_adapter,
            ),
            "get_governance_metrics": GetMetricsTool(),
        }

        # Register tools with handler
        for _name, tool in self._tools.items():
            definition = tool.get_definition()
            self._handler.register_tool(definition, tool.execute)

        logger.info(f"Registered {len(self._tools)} MCP tools")

    def _initialize_resources(self) -> None:
        """Initialize MCP resources."""
        audit_adapter = self._adapters.get("audit_client")

        # Get references to tools for resources that need them
        get_principles_tool = self._tools.get("get_active_principles")
        submit_governance_tool = self._tools.get("submit_governance_request")

        self._resources = {
            "principles": PrinciplesResource(
                get_principles_tool=get_principles_tool,
            ),
            "metrics": MetricsResource(),
            "decisions": DecisionsResource(
                submit_governance_tool=submit_governance_tool,
            ),
            "audit_trail": AuditTrailResource(
                audit_client_adapter=audit_adapter,
            ),
        }

        # Register resources with handler
        for _name, resource in self._resources.items():
            definition = resource.get_definition()
            self._handler.register_resource(definition, resource.read)

        logger.info(f"Registered {len(self._resources)} MCP resources")

    def _register_handlers(self) -> None:
        """Register additional method handlers."""
        # The handler already has initialize, tools/list, resources/list
        # Add any additional custom handlers here
        pass

    async def connect_adapters(self) -> bool:
        """
        Connect adapters to external services.

        Returns:
            True if all critical adapters connected
        """
        results = {}

        # Connect agent bus adapter
        agent_bus_adapter = self._adapters.get("agent_bus")
        if agent_bus_adapter:
            results["agent_bus"] = await agent_bus_adapter.connect()

        # Log connection status
        for name, success in results.items():
            if success:
                logger.info(f"Adapter '{name}' connected successfully")
            else:
                logger.warning(f"Adapter '{name}' running in standalone mode")

        return True  # Server can run in standalone mode

    async def disconnect_adapters(self) -> None:
        """Disconnect all adapters."""
        agent_bus_adapter = self._adapters.get("agent_bus")
        if agent_bus_adapter:
            await agent_bus_adapter.disconnect()
        logger.info("All adapters disconnected")

    async def start(self) -> None:
        """Start the MCP server."""
        if self._running:
            logger.warning("Server already running")
            return

        logger.info(f"Starting MCP Server: {self.config.server_name} v{self.config.server_version}")
        logger.info(f"Constitutional Hash: {self.CONSTITUTIONAL_HASH}")
        logger.info(f"Transport: {self.config.transport_type.value}")

        # Connect adapters
        await self.connect_adapters()

        # Lock registration to prevent runtime hijacking (RPC-Racer mitigation)
        if self._handler:
            self._handler.lock_registration()

        self._running = True
        self._shutdown_event.clear()

        # Log audit event
        audit_resource = self._resources.get("audit_trail")
        if audit_resource:
            audit_resource.log_event(
                event_type=AuditEventType.SYSTEM,
                actor_id="mcp-server",
                action="Server started",
                details={
                    "server_name": self.config.server_name,
                    "version": self.config.server_version,
                    "transport": self.config.transport_type.value,
                },
                outcome="success",
            )

        # Start appropriate transport
        if self.config.transport_type == TransportType.STDIO:
            await self._run_stdio_transport()
        elif self.config.transport_type == TransportType.SSE:
            await self._run_sse_transport()
        else:
            raise ValueError(f"Unknown transport: {self.config.transport_type}")

    async def stop(self) -> None:
        """Stop the MCP server."""
        if not self._running:
            return

        logger.info("Stopping MCP server...")

        # Log audit event
        audit_resource = self._resources.get("audit_trail")
        if audit_resource:
            audit_resource.log_event(
                event_type=AuditEventType.SYSTEM,
                actor_id="mcp-server",
                action="Server stopped",
                details={
                    "requests_processed": self._request_count,
                    "errors": self._error_count,
                },
                outcome="success",
            )

        # Disconnect adapters
        await self.disconnect_adapters()

        self._running = False
        self._shutdown_event.set()
        logger.info("MCP server stopped")

    async def _run_stdio_transport(self) -> None:
        """Run the STDIO transport for MCP communication."""
        logger.info("Running STDIO transport")

        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)

        loop = asyncio.get_running_loop()
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        writer_transport, writer_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

        while self._running and not self._shutdown_event.is_set():
            try:
                # Read line from stdin
                read_operation = reader.readline()
                try:
                    line = await asyncio.wait_for(
                        read_operation,
                        timeout=1.0,
                    )
                finally:
                    if inspect.iscoroutine(read_operation) and read_operation.cr_frame is not None:
                        read_operation.close()

                if not line:
                    continue

                # Parse and handle request
                try:
                    data = json.loads(line.decode("utf-8").strip())
                    request = MCPRequest.from_dict(data)
                    self._request_count += 1

                    response = await self._handler.handle_request(request)

                    if response:
                        response_json = json.dumps(response.to_dict()) + "\n"
                        writer.write(response_json.encode("utf-8"))
                        await writer.drain()

                except json.JSONDecodeError as e:
                    self._error_count += 1
                    logger.error(f"Invalid JSON: {e}")
                    error_response = MCPResponse(
                        jsonrpc="2.0",
                        id=None,
                        error=MCPError(
                            code=-32700,
                            message="Parse error",
                            data={"detail": str(e)},
                        ),
                    )
                    writer.write((json.dumps(error_response.to_dict()) + "\n").encode("utf-8"))
                    await writer.drain()

            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except MCP_SERVER_OPERATION_ERRORS as e:
                self._error_count += 1
                logger.error(f"Transport error: {e}")

    async def _run_sse_transport(self) -> None:
        """Run the SSE transport for MCP communication."""
        # SSE transport would be implemented here for HTTP-based communication
        # This is a placeholder for future implementation
        logger.warning("SSE transport not yet implemented, falling back to STDIO")
        await self._run_stdio_transport()

    async def handle_request(self, request: MCPRequest) -> MCPResponse | None:
        """
        Handle a single MCP request.

        Args:
            request: The MCP request to handle

        Returns:
            MCP response or None for notifications
        """
        self._request_count += 1

        try:
            return await self._handler.handle_request(request)
        except MCP_SERVER_OPERATION_ERRORS as e:
            self._error_count += 1
            logger.error(f"Request handling error: {e}")
            return MCPResponse(
                jsonrpc="2.0",
                id=request.id,
                error=MCPError(
                    code=-32603,
                    message="Internal error",
                    data={"detail": str(e)},
                ),
            )

    def get_capabilities(self) -> ServerCapabilities:
        """Get server capabilities."""
        return ServerCapabilities(
            tools={"listChanged": True},
            resources={"subscribe": False, "listChanged": True},
            prompts={"listChanged": False},
            logging={},
        )

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """Get all registered tool definitions."""
        return [tool.get_definition() for tool in self._tools.values()]

    def get_resource_definitions(self) -> list[ResourceDefinition]:
        """Get all registered resource definitions."""
        return [resource.get_definition() for resource in self._resources.values()]

    def get_metrics(self) -> JSONDict:
        """Get server metrics."""
        tool_metrics = {}
        for name, tool in self._tools.items():
            if hasattr(tool, "get_metrics"):
                tool_metrics[name] = tool.get_metrics()

        resource_metrics = {}
        for name, resource in self._resources.items():
            if hasattr(resource, "get_metrics"):
                resource_metrics[name] = resource.get_metrics()

        adapter_metrics = {}
        for name, adapter in self._adapters.items():
            if hasattr(adapter, "get_metrics"):
                adapter_metrics[name] = adapter.get_metrics()

        return {
            "server": {
                "name": self.config.server_name,
                "version": self.config.server_version,
                "running": self._running,
                "request_count": self._request_count,
                "error_count": self._error_count,
                "constitutional_hash": self.CONSTITUTIONAL_HASH,
            },
            "tools": tool_metrics,
            "resources": resource_metrics,
            "adapters": adapter_metrics,
        }


def create_mcp_server(
    config: MCPConfig | None = None,
    agent_bus: object | None = None,
    policy_client: object | None = None,
    audit_client: object | None = None,
) -> MCPServer:
    """
    Create an MCP server with optional external service connections.

    Args:
        config: Server configuration
        agent_bus: Optional EnhancedAgentBus instance
        policy_client: Optional PolicyClient instance
        audit_client: Optional AuditClient instance

    Returns:
        Configured MCPServer instance
    """
    if config is None:
        config = MCPConfig()

    server = MCPServer(config=config)

    # Inject external services if provided
    if agent_bus is not None:
        server._adapters["agent_bus"].agent_bus = agent_bus

    if policy_client is not None:
        server._adapters["policy_client"].policy_client = policy_client

    if audit_client is not None:
        server._adapters["audit_client"].audit_client = audit_client

    return server


async def main():
    """Main entry point for running the MCP server."""
    import logging as _logging

    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = MCPConfig()
    server = create_mcp_server(config=config)

    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
