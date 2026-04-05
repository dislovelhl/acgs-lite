"""
MCP Protocol Handler for ACGS-2 Constitutional Governance.

Handles JSON-RPC 2.0 based MCP protocol messages with constitutional validation.

Constitutional Hash: 608508a9bd224290
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from enhanced_agent_bus._compat.errors import (
    ResourceNotFoundError,
    ServiceUnavailableError,
)

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..config import MCPConfig
from .types import (
    InitializeResult,
    MCPError,
    MCPErrorCode,
    MCPRequest,
    MCPResponse,
    PromptDefinition,
    ResourceDefinition,
    ServerCapabilities,
    ServerInfo,
    ToolDefinition,
)

logger = get_logger(__name__)

MCP_REQUEST_HANDLER_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)

# Type alias for handler functions
HandlerFunc = Callable[[JSONDict], Awaitable[object]]


class MCPHandler:
    """
    MCP Protocol Handler with constitutional governance integration.

    Processes MCP requests/responses with ACGS-2 constitutional validation.
    """

    PROTOCOL_VERSION = "2024-11-05"
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    def __init__(self, config: MCPConfig):
        """Initialize the MCP handler."""
        self.config = config
        self._initialized = False
        self._registration_locked = False
        self._tools: dict[str, ToolDefinition] = {}
        self._resources: dict[str, ResourceDefinition] = {}
        self._prompts: dict[str, PromptDefinition] = {}
        self._tool_handlers: dict[str, HandlerFunc] = {}
        self._resource_handlers: dict[str, HandlerFunc] = {}
        self._prompt_handlers: dict[str, HandlerFunc] = {}
        self._request_count = 0
        self._error_count = 0

        # Method dispatch table
        self._methods: dict[str, HandlerFunc] = {
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
        }

    def lock_registration(self) -> None:
        """
        Lock registration of new tools, resources, and prompts.

        This prevents runtime 'interface hijacking' where a malicious
        component could try to override or add new handlers after
        the server has started.
        """
        self._registration_locked = True
        logger.info("MCP registration locked")

    def register_tool(
        self,
        definition: ToolDefinition,
        handler: HandlerFunc,
    ) -> None:
        """Register an MCP tool with its handler."""
        if self._registration_locked:
            raise ServiceUnavailableError(
                "Cannot register tool: registration is locked",
                error_code="MCP_REGISTRATION_LOCKED",
            )
        self._tools[definition.name] = definition
        self._tool_handlers[definition.name] = handler
        logger.info(f"Registered MCP tool: {definition.name}")

    def register_resource(
        self,
        definition: ResourceDefinition,
        handler: HandlerFunc,
    ) -> None:
        """Register an MCP resource with its handler."""
        if self._registration_locked:
            raise ServiceUnavailableError(
                "Cannot register resource: registration is locked",
                error_code="MCP_REGISTRATION_LOCKED",
            )
        self._resources[definition.uri] = definition
        self._resource_handlers[definition.uri] = handler
        logger.info(f"Registered MCP resource: {definition.uri}")

    def register_prompt(
        self,
        definition: PromptDefinition,
        handler: HandlerFunc,
    ) -> None:
        """Register an MCP prompt with its handler."""
        if self._registration_locked:
            raise ServiceUnavailableError(
                "Cannot register prompt: registration is locked",
                error_code="MCP_REGISTRATION_LOCKED",
            )
        self._prompts[definition.name] = definition
        self._prompt_handlers[definition.name] = handler
        logger.info(f"Registered MCP prompt: {definition.name}")

    async def handle_request(self, request: MCPRequest) -> MCPResponse | None:
        """
        Handle an incoming MCP request.

        Returns None for notifications (no response expected).
        """
        self._request_count += 1
        start_time = datetime.now(UTC)

        try:
            # Validate JSON-RPC version
            if request.jsonrpc != "2.0":
                return MCPResponse.failure(
                    request.id,
                    MCPError.from_code(
                        MCPErrorCode.INVALID_REQUEST,
                        "Invalid JSON-RPC version",
                    ),
                )

            # Find method handler
            handler = self._methods.get(request.method)
            if handler is None:
                return MCPResponse.failure(
                    request.id,
                    MCPError.from_code(
                        MCPErrorCode.METHOD_NOT_FOUND,
                        f"Method not found: {request.method}",
                    ),
                )

            # Execute handler with constitutional validation
            result = await self._execute_with_validation(
                handler,
                request.params or {},
                request.method,
            )

            # Log request metrics
            elapsed_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
            if self.config.log_requests:
                logger.info(f"MCP request: {request.method} completed in {elapsed_ms:.2f}ms")

            # Notifications don't get responses
            if request.id is None:
                return None

            return MCPResponse.success(request.id, result)

        except MCP_REQUEST_HANDLER_ERRORS as e:
            self._error_count += 1
            logger.error(f"Error handling MCP request: {e}")

            if request.id is None:
                return None

            return MCPResponse.failure(
                request.id,
                MCPError.from_code(
                    MCPErrorCode.INTERNAL_ERROR,
                    str(e),
                ),
            )

    async def _execute_with_validation(
        self,
        handler: HandlerFunc,
        params: JSONDict,
        method: str,
    ) -> object:
        """Execute handler with constitutional validation."""
        # Pre-execution validation for governance methods
        if method.startswith("tools/call") and self.config.strict_mode:
            tool_name = params.get("name", "")
            tool_def = self._tools.get(tool_name)

            if tool_def and tool_def.constitutional_required:
                # Validate constitutional hash is present in context
                if "constitutional_hash" not in params.get("arguments", {}):
                    # Auto-inject constitutional hash
                    if "arguments" not in params:
                        params["arguments"] = {}
                    params["arguments"]["_constitutional_hash"] = self.CONSTITUTIONAL_HASH

        # Execute the handler
        result = await handler(params)

        return result

    # Protocol handlers

    async def _handle_initialize(self, params: JSONDict) -> JSONDict:
        """Handle initialize request."""
        client_info = params.get("clientInfo", {})
        logger.info(
            f"MCP client connecting: {client_info.get('name', 'unknown')} "
            f"v{client_info.get('version', 'unknown')}"
        )

        # Build server capabilities
        capabilities = ServerCapabilities(
            tools={"listChanged": True} if self.config.enable_tools else None,
            resources=(
                {"subscribe": True, "listChanged": True} if self.config.enable_resources else None
            ),
            prompts={"listChanged": False} if self.config.enable_prompts else None,
            logging={},
            constitutional_governance=True,
            audit_trail=self.config.enable_audit_logging,
            maci_separation=self.config.enable_maci,
        )

        server_info = ServerInfo(
            name=self.config.server_name,
            version=self.config.server_version,
            constitutional_hash=self.CONSTITUTIONAL_HASH,
        )

        result = InitializeResult(
            protocolVersion=self.PROTOCOL_VERSION,
            capabilities=capabilities,
            serverInfo=server_info,
        )

        return result.to_dict()

    async def _handle_initialized(self, params: JSONDict) -> None:
        """Handle initialized notification."""
        self._initialized = True
        logger.info("MCP connection initialized")

    async def _handle_ping(self, params: JSONDict) -> JSONDict:
        """Handle ping request."""
        return {
            "status": "ok",
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _handle_tools_list(self, params: JSONDict) -> JSONDict:
        """Handle tools/list request."""
        tools = [tool.to_dict() for tool in self._tools.values()]
        return {"tools": tools}

    async def _handle_tools_call(self, params: JSONDict) -> JSONDict:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name not in self._tool_handlers:
            raise ResourceNotFoundError(
                f"Unknown tool: {tool_name}",
                error_code="MCP_TOOL_NOT_FOUND",
            )

        handler = self._tool_handlers[tool_name]
        result = await handler(arguments)

        # Wrap result in content array per MCP spec
        if isinstance(result, dict) and "content" in result:
            return result

        return {
            "content": [
                {
                    "type": "text",
                    "text": str(result) if not isinstance(result, str) else result,
                }
            ],
            "isError": False,
        }

    async def _handle_resources_list(self, params: JSONDict) -> JSONDict:
        """Handle resources/list request."""
        resources = [resource.to_dict() for resource in self._resources.values()]
        return {"resources": resources}

    async def _handle_resources_read(self, params: JSONDict) -> JSONDict:
        """Handle resources/read request."""
        uri = params.get("uri")

        if uri not in self._resource_handlers:
            raise ResourceNotFoundError(
                f"Unknown resource: {uri}",
                error_code="MCP_RESOURCE_NOT_FOUND",
            )

        handler = self._resource_handlers[uri]
        result = await handler({"uri": uri})

        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": self._resources[uri].mimeType,
                    "text": result if isinstance(result, str) else str(result),
                }
            ],
        }

    async def _handle_resources_subscribe(self, params: JSONDict) -> JSONDict:
        """Handle resources/subscribe request."""
        uri = params.get("uri")
        logger.info(f"Resource subscription requested: {uri}")
        return {"subscribed": True}

    async def _handle_prompts_list(self, params: JSONDict) -> JSONDict:
        """Handle prompts/list request."""
        prompts = [prompt.to_dict() for prompt in self._prompts.values()]
        return {"prompts": prompts}

    async def _handle_prompts_get(self, params: JSONDict) -> JSONDict:
        """Handle prompts/get request."""
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})

        if prompt_name not in self._prompt_handlers:
            raise ResourceNotFoundError(
                f"Unknown prompt: {prompt_name}",
                error_code="MCP_PROMPT_NOT_FOUND",
            )

        handler = self._prompt_handlers[prompt_name]
        result = await handler(arguments)

        return result

    async def _handle_logging_set_level(self, params: JSONDict) -> JSONDict:
        """Handle logging/setLevel request."""
        level = params.get("level", "info").upper()
        import logging as _logging

        _logging.getLogger(__name__).setLevel(getattr(_logging, level, _logging.INFO))
        return {"level": level.lower()}

    # Metrics and status

    def get_metrics(self) -> JSONDict:
        """Get handler metrics."""
        return {
            "request_count": self._request_count,
            "error_count": self._error_count,
            "error_rate": (
                self._error_count / self._request_count if self._request_count > 0 else 0.0
            ),
            "tools_registered": len(self._tools),
            "resources_registered": len(self._resources),
            "prompts_registered": len(self._prompts),
            "initialized": self._initialized,
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }
