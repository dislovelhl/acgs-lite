"""
MCP Tool Registry for ACGS-2.

Provides tool discovery, registration, and management for MCP integration,
enabling dynamic tool registration with constitutional validation.

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

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

logger = get_logger(__name__)
try:
    from acgs2_perf import fast_hash

    FAST_HASH_AVAILABLE = True
except ImportError:
    FAST_HASH_AVAILABLE = False

TOOL_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)

# Type alias for tool handler functions
ToolHandler = Callable[[JSONDict], Awaitable[JSONDict]]
MCP_TOOL_REGISTRY_OPERATION_ERRORS = (
    AttributeError,
    KeyError,
    LookupError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


class ToolCapability(Enum):
    """Capabilities that tools can provide."""

    GOVERNANCE = "governance"
    VALIDATION = "validation"
    AUDIT = "audit"
    ANALYTICS = "analytics"
    AUTOMATION = "automation"
    INTEGRATION = "integration"
    SECURITY = "security"
    MONITORING = "monitoring"
    CONFIGURATION = "configuration"
    DATA_ACCESS = "data_access"


class ToolStatus(Enum):
    """Status of a registered tool."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_APPROVAL = "pending_approval"
    DEPRECATED = "deprecated"


class ToolRiskLevel(Enum):
    """Risk level classification for tools."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ToolInputSchema:
    """JSON Schema for tool input validation."""

    type: str = "object"
    properties: JSONDict = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    additionalProperties: bool = False

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "type": self.type,
            "properties": self.properties,
            "required": self.required,
            "additionalProperties": self.additionalProperties,
        }


@dataclass
class ExternalTool:
    """
    Represents an external MCP tool.

    Tools are registered from external MCP servers and can be invoked
    through the ACGS-2 Enhanced Agent Bus with constitutional validation.
    """

    name: str
    description: str
    server_id: str
    input_schema: ToolInputSchema
    capabilities: list[ToolCapability] = field(default_factory=list)
    risk_level: ToolRiskLevel = ToolRiskLevel.MEDIUM
    status: ToolStatus = ToolStatus.ACTIVE
    constitutional_required: bool = True
    requires_approval: bool = False
    handler: ToolHandler | None = None
    metadata: JSONDict = field(default_factory=dict)
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_invoked: datetime | None = None
    invocation_count: int = 0
    error_count: int = 0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self):
        """Generate tool ID if not provided."""
        if "tool_id" not in self.metadata:
            self.metadata["tool_id"] = self._generate_tool_id()

    def _generate_tool_id(self) -> str:
        """Generate unique tool ID."""
        content = f"{self.server_id}:{self.name}:{self.registered_at.isoformat()}"
        if FAST_HASH_AVAILABLE:
            return f"{fast_hash(content):016x}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @property
    def tool_id(self) -> str:
        """Get the tool ID."""
        return self.metadata.get("tool_id", "")  # type: ignore[no-any-return]

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "server_id": self.server_id,
            "tool_id": self.tool_id,
            "input_schema": self.input_schema.to_dict(),
            "capabilities": [cap.value for cap in self.capabilities],
            "risk_level": self.risk_level.value,
            "status": self.status.value,
            "constitutional_required": self.constitutional_required,
            "requires_approval": self.requires_approval,
            "metadata": self.metadata,
            "registered_at": self.registered_at.isoformat(),
            "last_invoked": self.last_invoked.isoformat() if self.last_invoked else None,
            "invocation_count": self.invocation_count,
            "error_count": self.error_count,
            "constitutional_hash": self.constitutional_hash,
        }

    def to_mcp_definition(self) -> JSONDict:
        """Convert to MCP tool definition format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema.to_dict(),
        }


@dataclass
class ToolExecutionContext:
    """Context for tool execution."""

    tool: ExternalTool
    arguments: JSONDict
    agent_id: str
    session_id: str | None = None
    tenant_id: str | None = None
    request_id: str | None = None
    timeout_ms: int = 30000
    constitutional_hash: str = CONSTITUTIONAL_HASH
    metadata: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "tool_name": self.tool.name,
            "tool_id": self.tool.tool_id,
            "arguments": self.arguments,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "request_id": self.request_id,
            "timeout_ms": self.timeout_ms,
            "constitutional_hash": self.constitutional_hash,
            "metadata": self.metadata,
        }


@dataclass
class ToolRegistrationResult:
    """Result of tool registration."""

    success: bool
    tool_id: str | None = None
    tool_name: str | None = None
    server_id: str | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    registered_at: datetime | None = None

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "server_id": self.server_id,
            "error": self.error,
            "warnings": self.warnings,
            "constitutional_hash": self.constitutional_hash,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
        }


@dataclass
class ToolDiscoveryResult:
    """Result of tool discovery from an MCP server."""

    server_id: str
    server_name: str
    tools_found: int
    tools_registered: int
    tools_skipped: int
    tools: list[ExternalTool] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    discovery_time_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "server_id": self.server_id,
            "server_name": self.server_name,
            "tools_found": self.tools_found,
            "tools_registered": self.tools_registered,
            "tools_skipped": self.tools_skipped,
            "tools": [t.to_dict() for t in self.tools],
            "errors": self.errors,
            "warnings": self.warnings,
            "discovery_time_ms": self.discovery_time_ms,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class ToolExecutionResult:
    """Result of tool execution."""

    success: bool
    tool_name: str
    tool_id: str
    result: JSONDict | None = None
    error: str | None = None
    execution_time_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "tool_name": self.tool_name,
            "tool_id": self.tool_id,
            "result": self.result,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "constitutional_hash": self.constitutional_hash,
        }


class MCPToolRegistry:
    """
    Registry for managing MCP tools.

    Provides tool discovery, registration, validation, and execution
    with constitutional compliance and MACI integration.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    CONSTITUTIONAL_HASH = CONSTITUTIONAL_HASH
    MAX_TOOLS_PER_SERVER = 1000
    MAX_TOTAL_TOOLS = 50000  # Support for 16,000+ server compatibility

    def __init__(
        self,
        validator: object | None = None,
        enable_caching: bool = True,
        enable_audit: bool = True,
    ):
        """
        Initialize the tool registry.

        Args:
            validator: Optional MCPConstitutionalValidator instance
            enable_caching: Enable tool caching for performance
            enable_audit: Enable audit logging
        """
        self.validator = validator
        self.enable_caching = enable_caching
        self.enable_audit = enable_audit

        # Tool storage
        self._tools: dict[str, ExternalTool] = {}  # tool_id -> tool
        self._tools_by_name: dict[str, str] = {}  # name -> tool_id
        self._tools_by_server: dict[str, set[str]] = {}  # server_id -> set of tool_ids
        self._tools_by_capability: dict[ToolCapability, set[str]] = {
            cap: set() for cap in ToolCapability
        }

        # Server tracking
        self._servers: dict[str, JSONDict] = {}  # server_id -> server info

        # Metrics
        self._registration_count = 0
        self._discovery_count = 0
        self._execution_count = 0
        self._error_count = 0

        # Audit log
        self._audit_log: list[JSONDict] = []

        # Thread safety
        self._lock = asyncio.Lock()

    async def register_tool(
        self,
        tool: ExternalTool,
        agent_id: str,
        session_id: str | None = None,
    ) -> ToolRegistrationResult:
        """
        Register an external tool.

        Args:
            tool: Tool to register
            agent_id: ID of the agent performing registration
            session_id: Optional session context

        Returns:
            ToolRegistrationResult with registration outcome
        """
        async with self._lock:
            self._registration_count += 1

            # Validate registration
            if self.validator and VALIDATORS_AVAILABLE:
                context = MCPOperationContext(
                    operation_type=OperationType.TOOL_REGISTER,
                    agent_id=agent_id,
                    tool_name=tool.name,
                    session_id=session_id,
                    constitutional_hash=self.CONSTITUTIONAL_HASH,
                )
                validation = await self.validator.validate(context)
                if not validation.is_valid:
                    return ToolRegistrationResult(
                        success=False,
                        tool_name=tool.name,
                        server_id=tool.server_id,
                        error=f"Validation failed: {[i.message for i in validation.issues]}",
                    )

            # Check limits
            if len(self._tools) >= self.MAX_TOTAL_TOOLS:
                return ToolRegistrationResult(
                    success=False,
                    tool_name=tool.name,
                    server_id=tool.server_id,
                    error=f"Maximum tool limit reached ({self.MAX_TOTAL_TOOLS})",
                )

            server_tools = self._tools_by_server.get(tool.server_id, set())
            if len(server_tools) >= self.MAX_TOOLS_PER_SERVER:
                return ToolRegistrationResult(
                    success=False,
                    tool_name=tool.name,
                    server_id=tool.server_id,
                    error=f"Maximum tools per server reached ({self.MAX_TOOLS_PER_SERVER})",
                )

            # Check for duplicate
            warnings = []
            if tool.name in self._tools_by_name:
                existing_id = self._tools_by_name[tool.name]
                existing = self._tools.get(existing_id)
                if existing and existing.server_id != tool.server_id:
                    warnings.append(
                        f"Tool '{tool.name}' already registered from server '{existing.server_id}'"
                    )
                else:
                    # Update existing tool
                    warnings.append(f"Updating existing tool '{tool.name}'")

            # Register tool
            tool_id = tool.tool_id
            self._tools[tool_id] = tool
            self._tools_by_name[tool.name] = tool_id

            # Update server index
            if tool.server_id not in self._tools_by_server:
                self._tools_by_server[tool.server_id] = set()
            self._tools_by_server[tool.server_id].add(tool_id)

            # Update capability index
            for cap in tool.capabilities:
                self._tools_by_capability[cap].add(tool_id)

            # Audit log
            if self.enable_audit:
                self._audit_log.append(
                    {
                        "action": "register_tool",
                        "tool_id": tool_id,
                        "tool_name": tool.name,
                        "server_id": tool.server_id,
                        "agent_id": agent_id,
                        "session_id": session_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "constitutional_hash": self.CONSTITUTIONAL_HASH,
                    }
                )

            logger.info(
                f"Registered tool '{tool.name}' (id: {tool_id}) from server '{tool.server_id}'"
            )

            return ToolRegistrationResult(
                success=True,
                tool_id=tool_id,
                tool_name=tool.name,
                server_id=tool.server_id,
                warnings=warnings,
                registered_at=tool.registered_at,
            )

    async def unregister_tool(
        self,
        tool_id: str,
        agent_id: str,
        session_id: str | None = None,
    ) -> bool:
        """
        Unregister a tool.

        Args:
            tool_id: ID of the tool to unregister
            agent_id: ID of the agent performing unregistration
            session_id: Optional session context

        Returns:
            True if tool was unregistered
        """
        async with self._lock:
            if tool_id not in self._tools:
                return False

            tool = self._tools[tool_id]

            # Validate unregistration
            if self.validator and VALIDATORS_AVAILABLE:
                context = MCPOperationContext(
                    operation_type=OperationType.TOOL_UNREGISTER,
                    agent_id=agent_id,
                    tool_name=tool.name,
                    target_id=tool_id,
                    session_id=session_id,
                    constitutional_hash=self.CONSTITUTIONAL_HASH,
                )
                validation = await self.validator.validate(context)
                if not validation.is_valid:
                    logger.warning(f"Unregistration validation failed: {validation.issues}")
                    return False

            # Remove from all indices
            del self._tools[tool_id]
            if tool.name in self._tools_by_name:
                del self._tools_by_name[tool.name]
            if tool.server_id in self._tools_by_server:
                self._tools_by_server[tool.server_id].discard(tool_id)
            for cap in tool.capabilities:
                self._tools_by_capability[cap].discard(tool_id)

            # Audit log
            if self.enable_audit:
                self._audit_log.append(
                    {
                        "action": "unregister_tool",
                        "tool_id": tool_id,
                        "tool_name": tool.name,
                        "server_id": tool.server_id,
                        "agent_id": agent_id,
                        "session_id": session_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "constitutional_hash": self.CONSTITUTIONAL_HASH,
                    }
                )

            logger.info(f"Unregistered tool '{tool.name}' (id: {tool_id})")
            return True

    async def discover_tools(
        self,
        server_id: str,
        server_name: str,
        tools_definitions: list[JSONDict],
        agent_id: str,
        session_id: str | None = None,
    ) -> ToolDiscoveryResult:
        """
        Discover and register tools from an MCP server.

        Args:
            server_id: Unique server identifier
            server_name: Human-readable server name
            tools_definitions: Tool definitions from the server
            agent_id: ID of the agent performing discovery
            session_id: Optional session context

        Returns:
            ToolDiscoveryResult with discovery outcome
        """
        start_time = datetime.now(UTC)
        self._discovery_count += 1

        result = ToolDiscoveryResult(
            server_id=server_id,
            server_name=server_name,
            tools_found=len(tools_definitions),
            tools_registered=0,
            tools_skipped=0,
        )

        # Validate discovery operation
        if self.validator and VALIDATORS_AVAILABLE:
            context = MCPOperationContext(
                operation_type=OperationType.TOOL_DISCOVER,
                agent_id=agent_id,
                target_id=server_id,
                session_id=session_id,
                constitutional_hash=self.CONSTITUTIONAL_HASH,
            )
            validation = await self.validator.validate(context)
            if not validation.is_valid:
                result.errors.append(f"Discovery validation failed: {validation.issues}")
                return result

        # Register server
        self._servers[server_id] = {
            "server_id": server_id,
            "server_name": server_name,
            "discovered_at": start_time.isoformat(),
            "tools_count": len(tools_definitions),
        }

        # Process each tool definition
        for tool_def in tools_definitions:
            try:
                # Parse tool definition
                tool = self._parse_tool_definition(server_id, tool_def)

                # Register tool
                reg_result = await self.register_tool(tool, agent_id, session_id)

                if reg_result.success:
                    result.tools_registered += 1
                    result.tools.append(tool)
                else:
                    result.tools_skipped += 1
                    result.warnings.append(
                        f"Tool '{tool_def.get('name', 'unknown')}': {reg_result.error}"
                    )
                    result.warnings.extend(reg_result.warnings)

            except MCP_TOOL_REGISTRY_OPERATION_ERRORS as e:
                result.tools_skipped += 1
                result.errors.append(
                    f"Error processing tool '{tool_def.get('name', 'unknown')}': {e}"
                )

        end_time = datetime.now(UTC)
        result.discovery_time_ms = (end_time - start_time).total_seconds() * 1000

        logger.info(
            f"Discovered {result.tools_registered}/{result.tools_found} tools from '{server_name}'"
        )

        return result

    def _parse_tool_definition(self, server_id: str, tool_def: JSONDict) -> ExternalTool:
        """Parse an MCP tool definition into an ExternalTool."""
        name = tool_def.get("name", "")
        description = tool_def.get("description", "")
        input_schema_raw = tool_def.get("inputSchema", {})

        input_schema = ToolInputSchema(
            type=input_schema_raw.get("type", "object"),
            properties=input_schema_raw.get("properties", {}),
            required=input_schema_raw.get("required", []),
            additionalProperties=input_schema_raw.get("additionalProperties", False),
        )

        # Determine capabilities from tool name/description
        capabilities = self._infer_capabilities(name, description)

        # Determine risk level
        risk_level = self._assess_risk_level(name, description, input_schema)

        return ExternalTool(
            name=name,
            description=description,
            server_id=server_id,
            input_schema=input_schema,
            capabilities=capabilities,
            risk_level=risk_level,
            constitutional_required=True,
            requires_approval=risk_level in (ToolRiskLevel.HIGH, ToolRiskLevel.CRITICAL),
        )

    def _infer_capabilities(self, name: str, description: str) -> list[ToolCapability]:
        """Infer tool capabilities from name and description."""
        capabilities = []
        text = f"{name} {description}".lower()

        capability_keywords = {
            ToolCapability.GOVERNANCE: ["governance", "policy", "compliance", "constitutional"],
            ToolCapability.VALIDATION: ["validate", "verify", "check", "compliance"],
            ToolCapability.AUDIT: ["audit", "log", "track", "history"],
            ToolCapability.ANALYTICS: ["analytics", "metrics", "statistics", "report"],
            ToolCapability.AUTOMATION: ["automate", "workflow", "trigger", "schedule"],
            ToolCapability.INTEGRATION: ["integrate", "connect", "sync", "api"],
            ToolCapability.SECURITY: ["security", "auth", "encrypt", "permission"],
            ToolCapability.MONITORING: ["monitor", "alert", "health", "status"],
            ToolCapability.CONFIGURATION: ["config", "setting", "parameter", "option"],
            ToolCapability.DATA_ACCESS: ["data", "query", "fetch", "retrieve", "search"],
        }

        for cap, keywords in capability_keywords.items():
            if any(kw in text for kw in keywords):
                capabilities.append(cap)

        return capabilities if capabilities else [ToolCapability.INTEGRATION]

    def _assess_risk_level(
        self,
        name: str,
        description: str,
        input_schema: ToolInputSchema,
    ) -> ToolRiskLevel:
        """Assess the risk level of a tool."""
        text = f"{name} {description}".lower()

        # Critical risk patterns
        critical_patterns = ["delete", "drop", "admin", "root", "system", "execute"]
        if any(p in text for p in critical_patterns):
            return ToolRiskLevel.CRITICAL

        # High risk patterns
        high_patterns = ["modify", "update", "write", "create", "remove", "config"]
        if any(p in text for p in high_patterns):
            return ToolRiskLevel.HIGH

        # Medium risk patterns
        medium_patterns = ["send", "submit", "process", "transform"]
        if any(p in text for p in medium_patterns):
            return ToolRiskLevel.MEDIUM

        return ToolRiskLevel.LOW

    async def execute_tool(
        self,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        """
        Execute a registered tool.

        Args:
            context: Tool execution context

        Returns:
            ToolExecutionResult with execution outcome
        """
        start_time = datetime.now(UTC)
        self._execution_count += 1

        tool = context.tool

        # Validate execution
        if self.validator and VALIDATORS_AVAILABLE:
            val_context = MCPOperationContext(
                operation_type=OperationType.TOOL_CALL,
                agent_id=context.agent_id,
                tool_name=tool.name,
                target_id=tool.tool_id,
                arguments=context.arguments,
                session_id=context.session_id,
                tenant_id=context.tenant_id,
                constitutional_hash=self.CONSTITUTIONAL_HASH,
            )
            validation = await self.validator.validate(val_context)
            if not validation.is_valid:
                self._error_count += 1
                return ToolExecutionResult(
                    success=False,
                    tool_name=tool.name,
                    tool_id=tool.tool_id,
                    error=f"Validation failed: {[i.message for i in validation.issues]}",
                )

        # Check tool status
        if tool.status != ToolStatus.ACTIVE:
            self._error_count += 1
            return ToolExecutionResult(
                success=False,
                tool_name=tool.name,
                tool_id=tool.tool_id,
                error=f"Tool is not active (status: {tool.status.value})",
            )

        # Execute if handler available
        if not tool.handler:
            return ToolExecutionResult(
                success=False,
                tool_name=tool.name,
                tool_id=tool.tool_id,
                error="Tool has no handler registered",
            )

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                tool.handler(context.arguments),
                timeout=context.timeout_ms / 1000.0,
            )

            # Update tool stats
            tool.last_invoked = datetime.now(UTC)
            tool.invocation_count += 1

            end_time = datetime.now(UTC)

            return ToolExecutionResult(
                success=True,
                tool_name=tool.name,
                tool_id=tool.tool_id,
                result=result,
                execution_time_ms=(end_time - start_time).total_seconds() * 1000,
            )

        except TimeoutError:
            self._error_count += 1
            tool.error_count += 1
            return ToolExecutionResult(
                success=False,
                tool_name=tool.name,
                tool_id=tool.tool_id,
                error=f"Execution timed out after {context.timeout_ms}ms",
            )
        except TOOL_EXECUTION_ERRORS as e:
            self._error_count += 1
            tool.error_count += 1
            return ToolExecutionResult(
                success=False,
                tool_name=tool.name,
                tool_id=tool.tool_id,
                error=f"Execution error: {e}",
            )

    # Query methods

    def get_tool(self, tool_id: str) -> ExternalTool | None:
        """Get a tool by ID."""
        return self._tools.get(tool_id)

    def get_tool_by_name(self, name: str) -> ExternalTool | None:
        """Get a tool by name."""
        tool_id = self._tools_by_name.get(name)
        return self._tools.get(tool_id) if tool_id else None

    def list_tools(
        self,
        server_id: str | None = None,
        capability: ToolCapability | None = None,
        status: ToolStatus | None = None,
        limit: int = 100,
    ) -> list[ExternalTool]:
        """List tools with optional filters."""
        tool_ids = set(self._tools.keys())

        if server_id:
            tool_ids &= self._tools_by_server.get(server_id, set())

        if capability:
            tool_ids &= self._tools_by_capability.get(capability, set())

        tools = [self._tools[tid] for tid in tool_ids if tid in self._tools]

        if status:
            tools = [t for t in tools if t.status == status]

        return tools[:limit]

    def list_servers(self) -> list[JSONDict]:
        """List all registered servers."""
        return list(self._servers.values())

    def get_metrics(self) -> JSONDict:
        """Get registry metrics."""
        # Count unique servers from both registered servers and tools
        unique_servers = set(self._servers.keys()) | set(self._tools_by_server.keys())
        return {
            "total_tools": len(self._tools),
            "total_servers": len(unique_servers),
            "registration_count": self._registration_count,
            "discovery_count": self._discovery_count,
            "execution_count": self._execution_count,
            "error_count": self._error_count,
            "tools_by_status": {
                status.value: len([t for t in self._tools.values() if t.status == status])
                for status in ToolStatus
            },
            "tools_by_risk": {
                risk.value: len([t for t in self._tools.values() if t.risk_level == risk])
                for risk in ToolRiskLevel
            },
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }

    def get_audit_log(self, limit: int = 100) -> list[JSONDict]:
        """Get audit log entries."""
        return self._audit_log[-limit:]


def create_tool_registry(
    validator: object | None = None,
    enable_caching: bool = True,
    enable_audit: bool = True,
) -> MCPToolRegistry:
    """
    Factory function to create an MCP tool registry.

    Args:
        validator: Optional MCPConstitutionalValidator instance
        enable_caching: Enable tool caching
        enable_audit: Enable audit logging

    Returns:
        Configured MCPToolRegistry instance
    """
    return MCPToolRegistry(
        validator=validator,
        enable_caching=enable_caching,
        enable_audit=enable_audit,
    )


__all__ = [
    "ExternalTool",
    "MCPToolRegistry",
    "ToolCapability",
    "ToolDiscoveryResult",
    "ToolExecutionContext",
    "ToolExecutionResult",
    "ToolInputSchema",
    "ToolRegistrationResult",
    "ToolRiskLevel",
    "ToolStatus",
    "create_tool_registry",
]
