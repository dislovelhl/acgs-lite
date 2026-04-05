# Constitutional Hash: 608508a9bd224290
"""
MCPTransport Protocol definition for ACGS-2.

Defines the structural Protocol that all MCP transport implementations must
satisfy, enabling duck-typed interoperability across HTTP, stdio, SSE, and
WebSocket transports without coupling to a concrete base class.

Constitutional Hash: 608508a9bd224290
"""

from typing import Protocol, runtime_checkable

from enhanced_agent_bus._compat.errors import ACGSBaseError
from enhanced_agent_bus.bus_types import JSONDict
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


class MCPTransportError(ACGSBaseError):
    """
    Raised when an MCP transport operation fails.

    Covers connection failures, timeout, protocol errors, and auth failures
    that occur at the transport layer (below JSON-RPC semantics).

    Attributes:
        transport_type: The transport implementation that raised the error.
        endpoint: The remote endpoint involved, if applicable.
    """

    http_status_code = 503
    error_code = "MCP_TRANSPORT_ERROR"

    def __init__(
        self,
        message: str,
        *,
        transport_type: str = "unknown",
        endpoint: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.transport_type = transport_type
        self.endpoint = endpoint
        super().__init__(
            message,
            details={
                "transport_type": transport_type,
                "endpoint": endpoint,
            },
        )
        if cause is not None:
            self.__cause__ = cause


@runtime_checkable
class MCPTransport(Protocol):
    """
    Structural Protocol for MCP transports.

    Any object exposing ``connect``, ``disconnect``, and ``send`` with the
    correct signatures is considered a valid ``MCPTransport`` — no explicit
    inheritance required.

    All I/O methods are ``async``; implementations MUST NOT block the event
    loop.

    Example usage::

        from enhanced_agent_bus.mcp.transports import HTTPTransport, MCPTransport

        transport: MCPTransport = HTTPTransport(base_url="http://localhost:5000")
        assert isinstance(transport, MCPTransport)

        await transport.connect()
        result = await transport.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        await transport.disconnect()
    """

    async def connect(self) -> None:
        """
        Establish the underlying transport connection.

        Must be called before :meth:`send`.  Implementations should raise
        :class:`MCPTransportError` on failure rather than propagating raw
        network exceptions.

        Raises:
            MCPTransportError: If the connection cannot be established.
        """
        ...

    async def disconnect(self) -> None:
        """
        Gracefully close the transport connection and release resources.

        Safe to call even when not connected; repeated calls must be
        idempotent.

        Raises:
            MCPTransportError: If an error occurs during teardown (callers
                should log but not re-raise on clean shutdown paths).
        """
        ...

    async def send(self, message: JSONDict) -> JSONDict:
        """
        Send a JSON-RPC 2.0 message and return the response.

        Args:
            message: A valid JSON-RPC 2.0 request dict, e.g.::

                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/list",
                    "params": {},
                }

        Returns:
            A JSON-RPC 2.0 response dict with either ``"result"`` or
            ``"error"`` key, e.g.::

                {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "result": {"tools": [...]},
                }

        Raises:
            MCPTransportError: On network failure, timeout, or when the
                transport is not connected.
        """
        ...


__all__ = [
    "MCPTransport",
    "MCPTransportError",
]
