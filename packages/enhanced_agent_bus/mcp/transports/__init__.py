# Constitutional Hash: 608508a9bd224290
"""
MCP transports package for ACGS-2.

Re-exports the canonical Protocol and all concrete transport implementations
so callers can import from the single stable surface::

    from enhanced_agent_bus.mcp.transports import HTTPTransport, MCPTransport

Available transports
--------------------
- :class:`HTTPTransport`  — maps JSON-RPC to Toolbox REST endpoints
- :class:`MCPTransport`   — structural Protocol satisfied by any transport
- :class:`MCPTransportError` — base exception for transport-layer failures

Constitutional Hash: 608508a9bd224290
"""

from enhanced_agent_bus.mcp.transports.base import (
    MCPTransport,
    MCPTransportError,
)
from enhanced_agent_bus.mcp.transports.http import HTTPTransport

__all__ = [
    "HTTPTransport",
    "MCPTransport",
    "MCPTransportError",
]
