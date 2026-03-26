"""
MCP Client for the ACGS-2 Enhanced Agent Bus.

Provides async connect / disconnect / list_tools / call_tool operations
against remote MCP servers.  MACI role-based restrictions are enforced
inside call_tool() so that no agent may invoke a tool that exceeds its
constitutional authority.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict
from enhanced_agent_bus.maci_role_projection import parse_canonical_maci_role
from enhanced_agent_bus.observability.structured_logging import get_logger

from .types import MCPTool, MCPToolResult, MCPToolStatus

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# MACI imports — optional so the client degrades gracefully in minimal envs
# ---------------------------------------------------------------------------
_MACI_AVAILABLE: bool = False
_MACIRole: type | None = None  # type: ignore[assignment]
_MACIAction: type | None = None  # type: ignore[assignment]
_ROLE_PERMISSIONS: dict[Any, set[Any]] = {}

try:
    from enhanced_agent_bus.maci_enforcement import (
        ROLE_PERMISSIONS,
        MACIAction,
        MACIRole,
    )

    _MACI_AVAILABLE = True
    _MACIRole = MACIRole  # type: ignore[misc]
    _MACIAction = MACIAction  # type: ignore[misc]
    _ROLE_PERMISSIONS = ROLE_PERMISSIONS  # type: ignore[assignment]
    logger.debug("mcp_client_maci_loaded", maci_available=True)
except ImportError as _maci_err:
    logger.warning(
        "mcp_client_maci_unavailable",
        detail=str(_maci_err),
        fallback="all tools allowed (no MACI enforcement)",
    )

# ---------------------------------------------------------------------------
# Tool restriction manifest
# ---------------------------------------------------------------------------
# Maps MACI role names to the set of *tool name prefixes* (case-insensitive)
# that the role is NOT permitted to invoke.  An empty set means unrestricted.
# This is the coarse-grained gate; fine-grained OPA evaluation can layer on
# top for production deployments.

_ROLE_TOOL_RESTRICTIONS: dict[str, set[str]] = {
    # Judicial agents validate — they must NOT execute or propose
    "judicial": {"execute_", "propose_", "write_", "modify_", "delete_"},
    # Monitors observe — read-only posture
    "monitor": {"execute_", "propose_", "write_", "modify_", "delete_", "approve_"},
    # Auditors review — similar to monitors but may invoke audit-specific tools
    "auditor": {"execute_", "propose_", "write_", "modify_", "delete_"},
    # Proposers suggest — must not self-validate
    "executive": {"validate_", "audit_"},
    # Implementers execute — must not validate their own output
    "implementer": {"validate_", "audit_"},
}


def _normalize_maci_role(maci_role: object) -> str:
    """Return a canonical, case-insensitive MACI role identifier."""
    canonical_role = parse_canonical_maci_role(maci_role)
    if canonical_role is not None:
        return canonical_role.value.lower()
    if isinstance(maci_role, str):
        return maci_role.strip().lower()
    return ""


def _validate_maci_role(maci_role: object) -> tuple[bool, str]:
    """Validate that *maci_role* is recognized in this enforcement layer."""
    canonical_role = parse_canonical_maci_role(maci_role)
    if canonical_role is not None:
        return True, canonical_role.value.lower()

    role_key = _normalize_maci_role(maci_role)
    if role_key in _ROLE_TOOL_RESTRICTIONS:
        return True, role_key

    return (
        False,
        (f"MACI role '{maci_role}' is unknown or unmapped for MCP tool access"),
    )


def _role_may_call_tool(maci_role: object, tool_name: str) -> tuple[bool, str]:
    """Check whether *maci_role* is permitted to invoke *tool_name*.

    Returns:
        (allowed, reason) — reason is empty when allowed=True.
    """
    if not _normalize_maci_role(maci_role):
        # Legacy/dynamic agents may not be registered in the MACI registry yet.
        # Preserve the historical fallback path and rely on downstream controls.
        return True, ""

    valid, role_or_reason = _validate_maci_role(maci_role)
    if not valid:
        return False, role_or_reason

    restrictions = _ROLE_TOOL_RESTRICTIONS.get(role_or_reason, set())
    tool_lower = tool_name.lower()

    for prefix in restrictions:
        if tool_lower.startswith(prefix):
            return (
                False,
                (
                    f"MACI role '{maci_role}' is not permitted to call tool "
                    f"'{tool_name}' (matches restricted prefix '{prefix}')"
                ),
            )

    return True, ""


# ---------------------------------------------------------------------------
# Public client state
# ---------------------------------------------------------------------------


class MCPClientState(str, Enum):
    """Lifecycle state of an MCPClient instance."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class MCPClientConfig:
    """Configuration for an MCPClient.

    Attributes:
        server_url: Base URL (HTTP/WS) or command (stdio) of the MCP server.
        server_id: Logical identifier for the server (defaults to a UUID).
        connect_timeout: Seconds to wait before giving up on connect().
        call_timeout: Default per-call timeout for call_tool().
        max_retries: Number of retry attempts for transient call failures.
        metadata: Arbitrary key-value pairs forwarded to the server on init.
        enforce_maci: When True, role restrictions are enforced; disable only
            in testing/demo contexts.
    """

    server_url: str = "stdio"
    server_id: str = field(default_factory=lambda: f"mcp-server-{uuid.uuid4().hex[:8]}")
    connect_timeout: float = 10.0
    call_timeout: float = 30.0
    max_retries: int = 2
    metadata: JSONDict = field(default_factory=dict)
    enforce_maci: bool = True


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MCPClientError(Exception):
    """Base exception for MCPClient failures."""

    def __init__(
        self,
        message: str,
        *,
        server_id: str = "",
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        self.server_id = server_id
        self.constitutional_hash = constitutional_hash
        super().__init__(message)


class MCPConnectionError(MCPClientError):
    """Raised when connect() or disconnect() encounters a fatal error."""


class MCPToolCallError(MCPClientError):
    """Raised when call_tool() encounters an unrecoverable error."""


class MCPMACIViolationError(MCPClientError):
    """Raised when call_tool() is blocked by a MACI role restriction."""


# ---------------------------------------------------------------------------
# MCPClient
# ---------------------------------------------------------------------------


class MCPClient:
    """Async MCP client with constitutional MACI role enforcement.

    Usage::

        config = MCPClientConfig(server_url="http://localhost:8080")
        client = MCPClient(config=config)

        async with client:                           # connect / disconnect
            tools = await client.list_tools()
            result = await client.call_tool(
                "search_documents",
                arguments={"query": "governance"},
                agent_id="agent-42",
                maci_role="executive",
            )
            logger.info("Result: %s", result.content)

    MACI enforcement
    ----------------
    call_tool() consults :data:`_ROLE_TOOL_RESTRICTIONS` before forwarding
    the request to the server.  If the calling agent's role is not permitted
    to invoke the requested tool, an :class:`MCPToolResult` with
    ``status=FORBIDDEN`` is returned (no exception) so callers can handle the
    denial gracefully.  Strict callers may also set ``raise_on_forbidden=True``
    to receive an :class:`MCPMACIViolationError` instead.
    """

    def __init__(self, config: MCPClientConfig | None = None) -> None:
        self._config = config or MCPClientConfig()
        self._state: MCPClientState = MCPClientState.DISCONNECTED
        self._tools: dict[str, MCPTool] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._connected_at: datetime | None = None
        self._call_count: int = 0

        logger.info(
            "mcp_client_created",
            server_id=self._config.server_id,
            server_url=self._config.server_url,
            enforce_maci=self._config.enforce_maci,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> MCPClientState:
        """Current lifecycle state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """True when the client is in CONNECTED state."""
        return self._state == MCPClientState.CONNECTED

    @property
    def server_id(self) -> str:
        """Logical server identifier from configuration."""
        return self._config.server_id

    @property
    def constitutional_hash(self) -> str:
        """Governance fingerprint embedded in all results."""
        return CONSTITUTIONAL_HASH  # type: ignore[no-any-return]

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        """Establish a connection to the MCP server.

        Transitions: DISCONNECTED → CONNECTING → CONNECTED.

        Raises:
            MCPConnectionError: If the connection cannot be established within
                the configured *connect_timeout*.
            RuntimeError: If the client is already connected or in an error
                state that requires explicit reset.
        """
        async with self._lock:
            if self._state == MCPClientState.CONNECTED:
                logger.debug("mcp_client_already_connected", server_id=self._config.server_id)
                return

            if self._state not in (
                MCPClientState.DISCONNECTED,
                MCPClientState.ERROR,
            ):
                raise RuntimeError(
                    f"Cannot connect from state '{self._state.value}'; disconnect first."
                )

            self._state = MCPClientState.CONNECTING
            logger.info(
                "mcp_client_connecting",
                server_id=self._config.server_id,
                server_url=self._config.server_url,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            try:
                await asyncio.wait_for(
                    self._do_connect(),
                    timeout=self._config.connect_timeout,
                )
                self._state = MCPClientState.CONNECTED
                self._connected_at = datetime.now(UTC)
                logger.info(
                    "mcp_client_connected",
                    server_id=self._config.server_id,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
            except TimeoutError as exc:
                self._state = MCPClientState.ERROR
                raise MCPConnectionError(
                    f"Connection to '{self._config.server_url}' timed out "
                    f"after {self._config.connect_timeout}s",
                    server_id=self._config.server_id,
                ) from exc
            except Exception as exc:
                self._state = MCPClientState.ERROR
                logger.error(
                    "mcp_client_connect_failed",
                    server_id=self._config.server_id,
                    error=str(exc),
                    exc_info=True,
                )
                raise MCPConnectionError(
                    f"Failed to connect to '{self._config.server_url}': {exc}",
                    server_id=self._config.server_id,
                ) from exc

    async def disconnect(self) -> None:
        """Gracefully close the connection to the MCP server.

        Idempotent — calling disconnect() on an already-disconnected client
        is a no-op.

        Transitions: CONNECTED → DISCONNECTING → DISCONNECTED.
        """
        async with self._lock:
            if self._state == MCPClientState.DISCONNECTED:
                return

            prev_state = self._state
            self._state = MCPClientState.DISCONNECTING
            logger.info(
                "mcp_client_disconnecting",
                server_id=self._config.server_id,
                prev_state=prev_state.value,
            )

            try:
                await self._do_disconnect()
            except Exception as exc:
                logger.error(
                    "mcp_client_disconnect_error",
                    server_id=self._config.server_id,
                    error=str(exc),
                    exc_info=True,
                )
            finally:
                self._state = MCPClientState.DISCONNECTED
                self._tools.clear()
                self._connected_at = None
                logger.info(
                    "mcp_client_disconnected",
                    server_id=self._config.server_id,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )

    # ------------------------------------------------------------------ #
    # Tool discovery
    # ------------------------------------------------------------------ #

    async def list_tools(self) -> list[MCPTool]:
        """Return the list of tools advertised by the connected MCP server.

        Refreshes the internal tool registry on each call.

        Returns:
            A list of :class:`MCPTool` descriptors.

        Raises:
            RuntimeError: If the client is not in CONNECTED state.
        """
        self._require_connected("list_tools")

        logger.debug(
            "mcp_client_listing_tools",
            server_id=self._config.server_id,
        )

        raw_tools = await self._fetch_tools()
        self._tools = {t.name: t for t in raw_tools}

        logger.info(
            "mcp_client_tools_listed",
            server_id=self._config.server_id,
            tool_count=len(self._tools),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        return list(self._tools.values())

    # ------------------------------------------------------------------ #
    # Tool invocation
    # ------------------------------------------------------------------ #

    async def call_tool(
        self,
        tool_name: str,
        arguments: JSONDict | None = None,
        *,
        agent_id: str = "",
        maci_role: str = "",
        timeout: float | None = None,
        raise_on_forbidden: bool = False,
        metadata: JSONDict | None = None,
    ) -> MCPToolResult:
        """Invoke a named tool on the connected MCP server.

        MACI enforcement
        ^^^^^^^^^^^^^^^^
        Before forwarding the request, the method checks whether *maci_role*
        is permitted to invoke *tool_name*.  If the check fails:

        - A :class:`MCPToolResult` with ``status=FORBIDDEN`` is returned
          (default behaviour).
        - If *raise_on_forbidden* is ``True`` an :class:`MCPMACIViolationError`
          is raised instead.

        Args:
            tool_name: Name of the tool to invoke.
            arguments: Input parameters for the tool (defaults to empty dict).
            agent_id: Identifier of the calling agent (for audit logging).
            maci_role: MACI role of the calling agent.  An empty value keeps
                the historical fallback path for legacy agents; non-empty
                roles must be mapped in this enforcement layer.
            timeout: Per-call timeout in seconds; falls back to
                ``config.call_timeout``.
            raise_on_forbidden: When True, raise instead of returning a
                FORBIDDEN result.
            metadata: Optional key-value pairs forwarded with the call for
                audit trail enrichment.

        Returns:
            :class:`MCPToolResult` describing the outcome.

        Raises:
            RuntimeError: If the client is not in CONNECTED state.
            MCPMACIViolationError: If *raise_on_forbidden* is True and the
                MACI role check fails.
            MCPToolCallError: On unrecoverable invocation errors.
        """
        self._require_connected("call_tool")

        args = arguments or {}
        call_id = uuid.uuid4().hex[:12]
        call_metadata: JSONDict = {
            **(metadata or {}),
            "call_id": call_id,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        logger.info(
            "mcp_client_call_tool_start",
            tool_name=tool_name,
            agent_id=agent_id,
            maci_role=maci_role,
            call_id=call_id,
            server_id=self._config.server_id,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        # ---- MACI role enforcement ----------------------------------------
        if self._config.enforce_maci:
            allowed, reason = _role_may_call_tool(maci_role, tool_name)
            if not allowed:
                logger.warning(
                    "mcp_client_maci_violation",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    maci_role=maci_role,
                    reason=reason,
                    call_id=call_id,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                if raise_on_forbidden:
                    raise MCPMACIViolationError(
                        reason,
                        server_id=self._config.server_id,
                    )
                return MCPToolResult.forbidden(
                    tool_name=tool_name,
                    reason=reason,
                    agent_id=agent_id,
                    maci_role=maci_role,
                )

        # ---- Invoke with retry logic ----------------------------------------
        effective_timeout = timeout if timeout is not None else self._config.call_timeout
        last_error: Exception | None = None

        for attempt in range(self._config.max_retries + 1):
            try:
                raw_content = await asyncio.wait_for(
                    self._do_call_tool(tool_name, args),
                    timeout=effective_timeout,
                )
                self._call_count += 1

                result = MCPToolResult.success(
                    tool_name=tool_name,
                    content=raw_content,
                    agent_id=agent_id,
                    maci_role=maci_role,
                    metadata=call_metadata,
                )
                logger.info(
                    "mcp_client_call_tool_success",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    maci_role=maci_role,
                    call_id=call_id,
                    attempt=attempt,
                    total_calls=self._call_count,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return result

            except TimeoutError as exc:
                last_error = exc
                logger.warning(
                    "mcp_client_call_tool_timeout",
                    tool_name=tool_name,
                    call_id=call_id,
                    attempt=attempt,
                    timeout=effective_timeout,
                )
                # Don't retry on timeout — the server-side may have already
                # started processing; retrying could cause duplicate side-effects.
                return MCPToolResult(
                    tool_name=tool_name,
                    status=MCPToolStatus.TIMEOUT,
                    error=f"Tool call timed out after {effective_timeout}s",
                    agent_id=agent_id,
                    maci_role=maci_role,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                    metadata=call_metadata,
                )

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "mcp_client_call_tool_error",
                    tool_name=tool_name,
                    call_id=call_id,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt < self._config.max_retries:
                    await asyncio.sleep(0.25 * (attempt + 1))  # simple back-off
                    continue

        # All attempts exhausted
        error_msg = str(last_error) if last_error else "Unknown error"
        logger.error(
            "mcp_client_call_tool_failed",
            tool_name=tool_name,
            agent_id=agent_id,
            maci_role=maci_role,
            call_id=call_id,
            error=error_msg,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        return MCPToolResult.error_result(
            tool_name=tool_name,
            error=error_msg,
            agent_id=agent_id,
            maci_role=maci_role,
            metadata=call_metadata,
        )

    # ------------------------------------------------------------------ #
    # Context-manager support
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> MCPClient:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()

    # ------------------------------------------------------------------ #
    # Internal helpers (overridable in subclasses / tests)
    # ------------------------------------------------------------------ #

    async def _do_connect(self) -> None:
        """Perform the actual transport-level connection.

        Override in subclasses or patch in tests.  The default implementation
        is a no-op (suitable for unit testing without a live server).
        """
        # Real implementations would negotiate the MCP handshake here.
        await asyncio.sleep(0)

    async def _do_disconnect(self) -> None:
        """Perform the actual transport-level disconnection.

        Override in subclasses or patch in tests.
        """
        await asyncio.sleep(0)

    async def _fetch_tools(self) -> list[MCPTool]:
        """Fetch the tool list from the remote server.

        Override in subclasses to integrate with a real MCP transport.
        The default returns an empty list.
        """
        return []

    async def _do_call_tool(self, tool_name: str, arguments: JSONDict) -> Any:
        """Execute the tool invocation over the transport.

        Override in subclasses to integrate with a real MCP transport.
        The default raises NotImplementedError so tests can patch it.
        """
        raise NotImplementedError(
            f"_do_call_tool not implemented for server '{self._config.server_id}'. "
            "Subclass MCPClient or mock this method in tests."
        )

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _require_connected(self, operation: str) -> None:
        """Raise RuntimeError unless the client is in CONNECTED state."""
        if self._state != MCPClientState.CONNECTED:
            raise RuntimeError(
                f"Cannot perform '{operation}': client is in state "
                f"'{self._state.value}' (expected 'connected')."
            )

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:
        return (
            f"MCPClient("
            f"server_id={self._config.server_id!r}, "
            f"state={self._state.value!r}, "
            f"calls={self._call_count}"
            f")"
        )


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def create_mcp_client(
    server_url: str = "stdio",
    server_id: str = "",
    *,
    enforce_maci: bool = True,
    connect_timeout: float = 10.0,
    call_timeout: float = 30.0,
) -> MCPClient:
    """Convenience factory for :class:`MCPClient`.

    Args:
        server_url: Transport URL or command for the MCP server.
        server_id: Optional logical name; auto-generated when omitted.
        enforce_maci: Enable MACI role-based tool restrictions.
        connect_timeout: Seconds allowed for connect().
        call_timeout: Default per-call timeout for call_tool().

    Returns:
        A configured :class:`MCPClient` instance (not yet connected).
    """
    config = MCPClientConfig(
        server_url=server_url,
        server_id=server_id or f"mcp-{uuid.uuid4().hex[:8]}",
        connect_timeout=connect_timeout,
        call_timeout=call_timeout,
        enforce_maci=enforce_maci,
    )
    return MCPClient(config=config)


__all__ = [
    "MCPClient",
    "MCPClientConfig",
    "MCPClientError",
    "MCPClientState",
    "MCPConnectionError",
    "MCPMACIViolationError",
    "MCPToolCallError",
    "create_mcp_client",
]
