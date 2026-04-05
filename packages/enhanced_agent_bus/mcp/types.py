"""
MCP Type Definitions for ACGS-2 Enhanced Agent Bus.

Provides core dataclasses for the MCP client layer:
- MCPTool: describes a tool exposed by an MCP server
- MCPToolResult: carries the outcome of a tool invocation

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict


class MCPToolStatus(str, Enum):
    """Outcome status of a tool invocation."""

    SUCCESS = "success"
    ERROR = "error"
    FORBIDDEN = "forbidden"  # MACI role restriction blocked the call
    TIMEOUT = "timeout"


@dataclass
class MCPTool:
    """Descriptor for a tool available on a connected MCP server.

    Attributes:
        name: Unique tool identifier within the server namespace.
        description: Human-readable description of what the tool does.
        input_schema: JSON Schema describing the tool's input parameters.
        server_id: Identifier of the server that exposes this tool.
        tags: Arbitrary labels for categorisation / MACI role filtering.
        metadata: Any additional server-supplied metadata.
    """

    name: str
    description: str
    input_schema: JSONDict
    server_id: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)

    def as_dict(self) -> JSONDict:
        """Serialise to a plain JSON-compatible dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "server_id": self.server_id,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }


@dataclass
class MCPToolResult:
    """Result of a tool invocation routed through the MCP client.

    Every result embeds the constitutional hash so downstream consumers can
    verify that it originated from a constitutionally-governed call chain.

    Attributes:
        tool_name: Name of the tool that was invoked.
        status: Outcome status of the invocation.
        content: The tool's output payload (None on error / forbidden).
        error: Human-readable error description when status != SUCCESS.
        agent_id: Agent that performed the call (for audit trail).
        maci_role: MACI role of the calling agent.
        constitutional_hash: Governance fingerprint (always set to the project hash).
        timestamp: timezone.utc timestamp of the result creation.
        metadata: Optional call-site metadata passed through for auditability.
    """

    tool_name: str
    status: MCPToolStatus
    content: Any | None = None
    error: str | None = None
    agent_id: str = ""
    maci_role: str = ""
    constitutional_hash: str = CONSTITUTIONAL_HASH
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: JSONDict = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Convenience constructors
    # ------------------------------------------------------------------ #

    @classmethod
    def success(
        cls,
        tool_name: str,
        content: Any,
        *,
        agent_id: str = "",
        maci_role: str = "",
        metadata: JSONDict | None = None,
    ) -> MCPToolResult:
        """Create a successful result."""
        return cls(
            tool_name=tool_name,
            status=MCPToolStatus.SUCCESS,
            content=content,
            agent_id=agent_id,
            maci_role=maci_role,
            metadata=metadata or {},
        )

    @classmethod
    def error_result(
        cls,
        tool_name: str,
        error: str,
        *,
        agent_id: str = "",
        maci_role: str = "",
        metadata: JSONDict | None = None,
    ) -> MCPToolResult:
        """Create an error result."""
        return cls(
            tool_name=tool_name,
            status=MCPToolStatus.ERROR,
            error=error,
            agent_id=agent_id,
            maci_role=maci_role,
            metadata=metadata or {},
        )

    @classmethod
    def forbidden(
        cls,
        tool_name: str,
        reason: str,
        *,
        agent_id: str = "",
        maci_role: str = "",
    ) -> MCPToolResult:
        """Create a MACI-forbidden result."""
        return cls(
            tool_name=tool_name,
            status=MCPToolStatus.FORBIDDEN,
            error=reason,
            agent_id=agent_id,
            maci_role=maci_role,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @property
    def is_success(self) -> bool:
        """True when the invocation completed without errors."""
        return self.status == MCPToolStatus.SUCCESS

    def as_dict(self) -> JSONDict:
        """Serialise to a plain JSON-compatible dictionary."""
        return {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "content": self.content,
            "error": self.error,
            "agent_id": self.agent_id,
            "maci_role": self.maci_role,
            "constitutional_hash": self.constitutional_hash,
            "timestamp": self.timestamp.isoformat(),
            "metadata": dict(self.metadata),
        }


__all__ = [
    "CONSTITUTIONAL_HASH",
    "MCPTool",
    "MCPToolResult",
    "MCPToolStatus",
]
