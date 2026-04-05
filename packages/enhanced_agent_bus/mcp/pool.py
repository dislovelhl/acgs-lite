"""
MCPClientPool — Multi-server MCP client pool for ACGS-2 Enhanced Agent Bus.

Manages multiple MCPClient instances, provides a unified tool catalogue
across all connected MCP servers, routes tool calls to the correct server,
and supports health checks with automatic reconnection on failure.

Constitutional Hash: 608508a9bd224290

Quick start::

    from enhanced_agent_bus.mcp.pool import MCPClientPool
    from enhanced_agent_bus.mcp.client import MCPClient, MCPClientConfig

    pool = MCPClientPool()
    pool.register_client(MCPClient(MCPClientConfig(server_url="http://srv-a:8080", server_id="srv-a")))
    pool.register_client(MCPClient(MCPClientConfig(server_url="http://srv-b:8080", server_id="srv-b")))

    async with pool:
        tools = await pool.list_tools(maci_role="executive")
        result = await pool.call_tool(
            "search_documents",
            arguments={"query": "governance"},
            agent_id="agent-1",
            agent_role="executive",
        )
        health = await pool.health_check()
        # → {"srv-a": True, "srv-b": True}

MACI enforcement
----------------
``call_tool`` delegates to the owning :class:`MCPClient`, which enforces
MACI role restrictions before forwarding the call to the server.

``list_tools`` applies a pre-filter so agents only see the tools they are
permitted to call, using the same role-restriction mapping enforced by the
individual clients.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict
from enhanced_agent_bus.observability.structured_logging import get_logger

from .client import (
    MCPClient,
    _role_may_call_tool,  # internal — same package; call-permission predicate
    _validate_maci_role,
)
from .types import MCPTool, MCPToolResult

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pool-level exceptions
# ---------------------------------------------------------------------------


class MCPPoolError(Exception):
    """Base exception for :class:`MCPClientPool` failures."""

    def __init__(
        self,
        message: str,
        *,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        self.constitutional_hash = constitutional_hash
        super().__init__(message)


class MCPPoolDuplicateClientError(MCPPoolError):
    """Raised when a client with the same ``server_id`` is registered twice."""


class MCPToolNotFoundError(MCPPoolError):
    """Raised when a requested tool is not available in any registered server."""


# ---------------------------------------------------------------------------
# MCPClientPool
# ---------------------------------------------------------------------------


class MCPClientPool:
    """Manages a pool of :class:`MCPClient` instances with unified tool routing.

    Features
    --------
    - **Unified tool discovery** — aggregates tools from all registered servers
      into a single index.  Tool name conflicts are resolved in favour of the
      *first* registered server that exposes the tool (FIFO priority); a
      warning is emitted for every collision.
    - **MACI role filtering** — :meth:`list_tools` optionally restricts the
      returned catalogue to tools that the caller's MACI role may invoke.
    - **Correct routing** — :meth:`call_tool` dispatches to the specific
      server that owns the tool as determined during index construction; each
      client independently enforces MACI role restrictions.
    - **Health checks with reconnection** — :meth:`health_check` verifies the
      liveness of every registered client and transparently reconnects clients
      that have dropped, rebuilding their tool index on success.

    Thread-safety
    -------------
    All mutations to the routing index are guarded by an :class:`asyncio.Lock`.
    The pool is designed for single-event-loop, concurrent async usage; it is
    **not** safe to share across OS threads without external locking.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self) -> None:
        # Ordered registry of all clients (insertion order = FIFO priority)
        self._clients: list[MCPClient] = []
        # tool_name → MCPClient that owns the tool (routing table)
        self._tool_routing: dict[str, MCPClient] = {}
        # tool_name → MCPTool descriptor (for list_tools queries)
        self._tool_descriptors: dict[str, MCPTool] = {}
        # Serialises writes to the two index dicts above
        self._lock: asyncio.Lock = asyncio.Lock()

        logger.info(
            "mcp_pool_created",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #

    def register_client(self, client: MCPClient) -> None:
        """Register an :class:`MCPClient` with the pool.

        The client is **not** connected by this call.  Invoke
        :meth:`connect_all` (or open the pool as an async context manager)
        after registering all desired clients.

        Args:
            client: A configured (but not necessarily connected) MCPClient.

        Raises:
            MCPPoolDuplicateClientError: If a client with the same
                ``server_id`` has already been registered.
        """
        existing_ids = {c.server_id for c in self._clients}
        if client.server_id in existing_ids:
            raise MCPPoolDuplicateClientError(
                f"A client with server_id '{client.server_id}' is already "
                "registered in this pool.  Each server_id must be unique.",
            )
        self._clients.append(client)
        logger.info(
            "mcp_pool_client_registered",
            server_id=client.server_id,
            total_clients=len(self._clients),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def connect_all(self) -> None:
        """Connect all registered clients concurrently.

        After all connection attempts finish (whether successful or not),
        the unified tool index is rebuilt from every client that is in
        ``CONNECTED`` state.

        Individual connection failures are logged as warnings; the remaining
        clients still connect and contribute their tools to the index.
        """
        if not self._clients:
            logger.warning(
                "mcp_pool_connect_all_no_clients",
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            return

        logger.info(
            "mcp_pool_connecting_all",
            client_count=len(self._clients),
            server_ids=[c.server_id for c in self._clients],
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        async def _safe_connect(client: MCPClient) -> None:
            try:
                await client.connect()
                logger.info(
                    "mcp_pool_client_connected",
                    server_id=client.server_id,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
            except Exception as exc:
                logger.warning(
                    "mcp_pool_client_connect_failed",
                    server_id=client.server_id,
                    error=str(exc),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )

        await asyncio.gather(*(_safe_connect(c) for c in self._clients))
        await self._rebuild_tool_index()

    async def disconnect_all(self) -> None:
        """Disconnect all registered clients concurrently.

        The tool index is cleared after all disconnection attempts complete.
        Individual disconnect failures are logged but never propagated.
        """
        logger.info(
            "mcp_pool_disconnecting_all",
            client_count=len(self._clients),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        async def _safe_disconnect(client: MCPClient) -> None:
            try:
                await client.disconnect()
            except Exception as exc:
                logger.warning(
                    "mcp_pool_client_disconnect_failed",
                    server_id=client.server_id,
                    error=str(exc),
                )

        await asyncio.gather(*(_safe_disconnect(c) for c in self._clients))

        async with self._lock:
            self._tool_routing.clear()
            self._tool_descriptors.clear()

        logger.info(
            "mcp_pool_disconnected_all",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    # ------------------------------------------------------------------ #
    # Context-manager support
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> MCPClientPool:
        await self.connect_all()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect_all()

    # ------------------------------------------------------------------ #
    # Tool discovery
    # ------------------------------------------------------------------ #

    async def list_tools(self, maci_role: str | None = None) -> list[MCPTool]:
        """Return all tools available across all connected servers.

        The returned list reflects the state of the pool's tool index at the
        time of the call.  The index is populated during :meth:`connect_all`
        and incrementally updated when :meth:`health_check` successfully
        reconnects a dropped client.

        Args:
            maci_role: Optional MACI role of the caller.  When provided, tools
                that the role is **not** permitted to invoke are excluded from
                the result.  ``None`` preserves the internal unfiltered
                catalogue path; an explicit empty or unknown role returns no
                tools.

        Returns:
            A list of :class:`MCPTool` descriptors (possibly empty), ordered
            by the insertion order of the registering server.
        """
        async with self._lock:
            tools: list[MCPTool] = list(self._tool_descriptors.values())

        # Apply MACI role filter only when the caller explicitly supplies a role.
        if maci_role is not None:
            valid, role_or_reason = _validate_maci_role(maci_role)
            if not valid:
                logger.warning(
                    "mcp_pool_list_tools_invalid_maci_role",
                    maci_role=maci_role,
                    reason=role_or_reason,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                tools = []
            else:
                tools = [t for t in tools if _role_may_call_tool(role_or_reason, t.name)[0]]

        logger.debug(
            "mcp_pool_list_tools",
            total_indexed=len(self._tool_descriptors),
            returned_count=len(tools),
            maci_role="none" if maci_role is None else maci_role,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        return tools

    # ------------------------------------------------------------------ #
    # Tool invocation
    # ------------------------------------------------------------------ #

    async def call_tool(
        self,
        tool_name: str,
        arguments: JSONDict | None = None,
        agent_id: str = "",
        agent_role: str = "",
    ) -> MCPToolResult:
        """Invoke a named tool on whichever server owns it.

        The pool looks up the tool in its routing index and delegates the
        actual call — including MACI role enforcement — to the owning
        :class:`MCPClient`.

        Args:
            tool_name: Name of the tool to invoke.
            arguments: Input parameters for the tool (defaults to ``{}``).
            agent_id: Identifier of the calling agent (for audit logging).
            agent_role: MACI role of the calling agent.  Passed through to
                the owning client which enforces role-level restrictions.

        Returns:
            :class:`MCPToolResult` from the owning server.  If the tool is
            not found in any registered server an ``ERROR`` result is returned
            (no exception is raised) so callers can handle the absence
            gracefully.
        """
        async with self._lock:
            client: MCPClient | None = self._tool_routing.get(tool_name)

        if client is None:
            async with self._lock:
                available = sorted(self._tool_routing.keys())
            logger.warning(
                "mcp_pool_tool_not_found",
                tool_name=tool_name,
                agent_id=agent_id,
                available_count=len(available),
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            return MCPToolResult.error_result(
                tool_name=tool_name,
                error=(
                    f"Tool '{tool_name}' is not available in any registered "
                    "MCP server.  Check that the owning server is connected "
                    "and that connect_all() / health_check() has been called."
                ),
                agent_id=agent_id,
                maci_role=agent_role,
                metadata={"constitutional_hash": CONSTITUTIONAL_HASH},
            )

        logger.debug(
            "mcp_pool_routing_tool_call",
            tool_name=tool_name,
            routed_to=client.server_id,
            agent_id=agent_id,
            agent_role=agent_role,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        return await client.call_tool(
            tool_name,
            arguments=arguments,
            agent_id=agent_id,
            maci_role=agent_role,
        )

    # ------------------------------------------------------------------ #
    # Health checks
    # ------------------------------------------------------------------ #

    async def health_check(self) -> dict[str, bool]:
        """Check liveness of all registered clients.

        For each client that is **not** in ``CONNECTED`` state the pool
        attempts a transparent reconnection.  If reconnection succeeds, the
        client's tools are incrementally added back into the routing index.

        Returns:
            A ``dict`` mapping each server's ``server_id`` to a ``bool``
            health status — ``True`` means the client is (or just became)
            connected; ``False`` means it is unreachable.

        Example::

            health = await pool.health_check()
            if not all(health.values()):
                degraded = [sid for sid, ok in health.items() if not ok]
                logger.warning("Degraded servers", servers=degraded)
        """
        results: dict[str, bool] = {}

        for client in self._clients:
            server_id = client.server_id

            if client.is_connected:
                results[server_id] = True
                logger.debug(
                    "mcp_pool_health_check_ok",
                    server_id=server_id,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                continue

            # Client is not connected — attempt reconnection
            logger.info(
                "mcp_pool_health_check_reconnecting",
                server_id=server_id,
                state=client.state.value,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            try:
                await client.connect()
                # Re-index this server's tools into the pool
                await self._index_client_tools(client)
                results[server_id] = True
                logger.info(
                    "mcp_pool_health_check_reconnected",
                    server_id=server_id,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
            except Exception as exc:
                results[server_id] = False
                logger.warning(
                    "mcp_pool_health_check_reconnect_failed",
                    server_id=server_id,
                    error=str(exc),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )

        logger.info(
            "mcp_pool_health_check_complete",
            healthy=sum(v for v in results.values()),
            total=len(results),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        return results

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    @property
    def client_count(self) -> int:
        """Number of registered clients (connected or not)."""
        return len(self._clients)

    @property
    def tool_count(self) -> int:
        """Number of indexed tools across all currently connected servers."""
        return len(self._tool_descriptors)

    def server_ids(self) -> list[str]:
        """Return the ``server_id`` of every registered client in order."""
        return [c.server_id for c in self._clients]

    def __repr__(self) -> str:
        return (
            f"MCPClientPool("
            f"clients={len(self._clients)}, "
            f"tools={len(self._tool_descriptors)}, "
            f"constitutional_hash={CONSTITUTIONAL_HASH!r}"
            f")"
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    async def _rebuild_tool_index(self) -> None:
        """Rebuild the entire routing / descriptor index from scratch.

        Only clients in ``CONNECTED`` state contribute tools.  Existing
        index data is atomically replaced under the lock once all tools have
        been collected.
        """
        new_routing: dict[str, MCPClient] = {}
        new_descriptors: dict[str, MCPTool] = {}

        for client in self._clients:
            if not client.is_connected:
                continue
            await self._collect_client_tools(client, new_routing, new_descriptors)

        async with self._lock:
            self._tool_routing = new_routing
            self._tool_descriptors = new_descriptors

        logger.info(
            "mcp_pool_tool_index_rebuilt",
            total_tools=len(new_descriptors),
            connected_servers=sum(1 for c in self._clients if c.is_connected),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    async def _index_client_tools(self, client: MCPClient) -> None:
        """Incrementally merge a single client's tools into the pool index.

        This is called after a successful reconnection so that the client's
        tools become visible immediately without a full index rebuild.  Any
        tool names that already exist in the index (owned by another server)
        are **skipped** (first-registered wins) with a warning.

        Args:
            client: A client that has just successfully connected.
        """
        added: dict[str, MCPClient] = {}
        descriptors: dict[str, MCPTool] = {}

        await self._collect_client_tools(client, added, descriptors)

        async with self._lock:
            for tool_name, owning_client in added.items():
                # Honour first-registered rule at incremental-index time too
                if tool_name not in self._tool_routing:
                    self._tool_routing[tool_name] = owning_client
                    self._tool_descriptors[tool_name] = descriptors[tool_name]
                else:
                    existing = self._tool_routing[tool_name].server_id
                    logger.warning(
                        "mcp_pool_incremental_index_conflict",
                        tool_name=tool_name,
                        existing_server=existing,
                        new_server=client.server_id,
                        resolution="keeping_existing",
                        constitutional_hash=CONSTITUTIONAL_HASH,
                    )

        logger.debug(
            "mcp_pool_client_tools_indexed",
            server_id=client.server_id,
            new_tools=len(added),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    async def _collect_client_tools(
        self,
        client: MCPClient,
        routing: dict[str, MCPClient],
        descriptors: dict[str, MCPTool],
    ) -> None:
        """Fetch tools from *client* and write them into *routing*/*descriptors*.

        Tool name conflicts within the provided dicts are also resolved by
        FIFO priority: if the same name arrives from two servers during a
        full rebuild, the one from the earlier-registered client wins.

        Errors during ``list_tools()`` are caught and logged; the client
        contributes zero tools rather than aborting the entire index build.

        Args:
            client: A connected :class:`MCPClient` to query.
            routing: Mutable dict to populate with ``{tool_name: client}``.
            descriptors: Mutable dict to populate with ``{tool_name: MCPTool}``.
        """
        try:
            tools = await client.list_tools()
        except Exception as exc:
            logger.warning(
                "mcp_pool_list_tools_failed",
                server_id=client.server_id,
                error=str(exc),
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            return

        for tool in tools:
            # Stamp server_id onto the descriptor when the client didn't set it
            if not tool.server_id:
                tool.server_id = client.server_id

            if tool.name in routing:
                existing_server_id = routing[tool.name].server_id
                logger.warning(
                    "mcp_pool_tool_conflict",
                    tool_name=tool.name,
                    existing_server=existing_server_id,
                    duplicate_server=client.server_id,
                    resolution="keeping_first_registered",
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                continue  # First-registered server retains ownership

            routing[tool.name] = client
            descriptors[tool.name] = tool


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def create_mcp_pool(*clients: MCPClient) -> MCPClientPool:
    """Convenience factory that creates a pool and registers *clients* in order.

    Args:
        *clients: Zero or more :class:`MCPClient` instances to register.

    Returns:
        A configured :class:`MCPClientPool` with all provided clients already
        registered (but not yet connected).

    Example::

        pool = create_mcp_pool(client_a, client_b)
        async with pool:
            result = await pool.call_tool("search", {"query": "governance"})
    """
    pool = MCPClientPool()
    for client in clients:
        pool.register_client(client)
    return pool


__all__ = [
    "MCPClientPool",
    "MCPPoolDuplicateClientError",
    "MCPPoolError",
    "MCPToolNotFoundError",
    "create_mcp_pool",
]
