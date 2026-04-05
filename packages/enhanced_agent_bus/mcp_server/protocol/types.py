try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

"""
MCP Protocol Types for ACGS-2 Constitutional Governance.

Implements JSON-RPC 2.0 based MCP protocol types as per the Model Context Protocol
specification.

Constitutional Hash: 608508a9bd224290
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from enhanced_agent_bus.bus_types import JSONDict, JSONValue


class MCPErrorCode(Enum):
    """Standard MCP error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # ACGS-2 specific error codes
    CONSTITUTIONAL_VIOLATION = -32001
    GOVERNANCE_DENIED = -32002
    VALIDATION_FAILED = -32003
    AUDIT_REQUIRED = -32004
    HASH_MISMATCH = -32005


@dataclass
class MCPRequest:
    """JSON-RPC 2.0 request for MCP."""

    jsonrpc: str
    method: str
    id: str | int | None = None
    params: JSONDict | None = None

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        result: JSONDict = {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.params is not None:
            result["params"] = self.params
        return result

    @classmethod
    def from_dict(cls, data: JSONDict) -> "MCPRequest":
        """Create from dictionary."""
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            method=data["method"],
            id=data.get("id"),
            params=data.get("params"),
        )

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "MCPRequest":
        """Parse from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def is_notification(self) -> bool:
        """Check if this is a notification (no id means no response expected)."""
        return self.id is None


@dataclass
class MCPError:
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: JSONDict | None = None

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        result = {
            "code": self.code,
            "message": self.message,
        }
        if self.data is not None:
            result["data"] = self.data
        return result

    @classmethod
    def from_code(
        cls,
        code: MCPErrorCode,
        message: str | None = None,
        data: JSONDict | None = None,
    ) -> "MCPError":
        """Create error from error code enum."""
        return cls(
            code=code.value,
            message=message or code.name.replace("_", " ").title(),
            data=data,
        )

    @classmethod
    def constitutional_violation(cls, reason: str, context: JSONDict | None = None) -> "MCPError":
        """Create constitutional violation error."""
        return cls(
            code=MCPErrorCode.CONSTITUTIONAL_VIOLATION.value,
            message=f"Constitutional violation: {reason}",
            data={
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "violation_reason": reason,
                "context": context or {},
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    @classmethod
    def governance_denied(cls, reason: str, violations: list[JSONDict] | None = None) -> "MCPError":
        """Create governance denied error."""
        return cls(
            code=MCPErrorCode.GOVERNANCE_DENIED.value,
            message=f"Governance denied: {reason}",
            data={
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "denial_reason": reason,
                "violations": violations or [],
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

    @classmethod
    def validation_failed(cls, field: str, reason: str) -> "MCPError":
        """Create validation failed error."""
        return cls(
            code=MCPErrorCode.VALIDATION_FAILED.value,
            message=f"Validation failed for '{field}': {reason}",
            data={
                "constitutional_hash": CONSTITUTIONAL_HASH,
                "field": field,
                "reason": reason,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )


@dataclass
class MCPResponse:
    """JSON-RPC 2.0 response for MCP."""

    jsonrpc: str
    id: str | int | None
    result: JSONValue | None = None
    error: MCPError | None = None

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        response: JSONDict = {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
        }
        if self.error is not None:
            response["error"] = self.error.to_dict()
        else:
            response["result"] = self.result
        return response

    @classmethod
    def success(cls, id: str | int | None, result: JSONValue) -> "MCPResponse":
        """Create success response."""
        return cls(jsonrpc="2.0", id=id, result=result)

    @classmethod
    def failure(cls, id: str | int | None, error: MCPError) -> "MCPResponse":
        """Create error response."""
        return cls(jsonrpc="2.0", id=id, error=error)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class MCPNotification:
    """JSON-RPC 2.0 notification (no id, no response expected)."""

    jsonrpc: str
    method: str
    params: JSONDict | None = None

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        result: JSONDict = {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
        }
        if self.params is not None:
            result["params"] = self.params
        return result

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class ToolInputSchema:
    """JSON Schema for tool input."""

    type: str = "object"
    properties: JSONDict = field(default_factory=dict)
    required: list[str] = field(default_factory=list)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "type": self.type,
            "properties": self.properties,
            "required": self.required,
        }


@dataclass
class ToolDefinition:
    """MCP Tool definition."""

    name: str
    description: str
    inputSchema: ToolInputSchema | JSONDict
    constitutional_required: bool = True  # ACGS-2 specific

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for MCP protocol."""
        # Handle both ToolInputSchema and raw dict
        if isinstance(self.inputSchema, dict):
            schema = self.inputSchema
        else:
            schema = self.inputSchema.to_dict()
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": schema,
        }


@dataclass
class ResourceDefinition:
    """MCP Resource definition."""

    uri: str
    name: str
    description: str
    mimeType: str = "application/json"
    constitutional_scope: str = "read"  # ACGS-2: read, write, governance

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for MCP protocol."""
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mimeType,
        }


@dataclass
class PromptArgument:
    """MCP Prompt argument."""

    name: str
    description: str
    required: bool = True

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
        }


@dataclass
class PromptDefinition:
    """MCP Prompt definition."""

    name: str
    description: str
    arguments: list[PromptArgument] = field(default_factory=list)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for MCP protocol."""
        return {
            "name": self.name,
            "description": self.description,
            "arguments": [arg.to_dict() for arg in self.arguments],
        }


# Server capability types
@dataclass
class ServerCapabilities:
    """MCP Server capabilities."""

    tools: JSONDict | None = None
    resources: JSONDict | None = None
    prompts: JSONDict | None = None
    logging: JSONDict | None = None

    # ACGS-2 specific capabilities
    constitutional_governance: bool = True
    audit_trail: bool = True
    maci_separation: bool = True

    def __post_init__(self):
        """Set defaults for capabilities."""
        if self.tools is None:
            self.tools = {"listChanged": True}
        if self.resources is None:
            self.resources = {"subscribe": True, "listChanged": True}
        if self.prompts is None:
            self.prompts = {"listChanged": False}
        if self.logging is None:
            self.logging = {}

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        capabilities = {}
        if self.tools is not None:
            capabilities["tools"] = self.tools
        if self.resources is not None:
            capabilities["resources"] = self.resources
        if self.prompts is not None:
            capabilities["prompts"] = self.prompts
        if self.logging is not None:
            capabilities["logging"] = self.logging

        # ACGS-2 experimental capabilities
        capabilities["experimental"] = {
            "constitutional_governance": self.constitutional_governance,
            "audit_trail": self.audit_trail,
            "maci_separation": self.maci_separation,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        return capabilities


@dataclass
class ServerInfo:
    """MCP Server information."""

    name: str
    version: str
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
        }


@dataclass
class InitializeResult:
    """Result of MCP initialize request."""

    protocolVersion: str
    capabilities: ServerCapabilities
    serverInfo: ServerInfo

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "protocolVersion": self.protocolVersion,
            "capabilities": self.capabilities.to_dict(),
            "serverInfo": self.serverInfo.to_dict(),
        }
