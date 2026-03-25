"""
MCP Router — Unified Neural-MCP + Toolbox gateway for ACGS-2.

Wraps an :class:`MCPClientPool` with a high-level API that adds:

- **Tool discovery with category tagging** — tools are grouped into
  ``database``, ``neural``, ``hitl``, or ``general`` buckets based on their
  name tokens and tags, enabling the agent bus to select tools by domain
  without knowing exact names.
- **Structured request / response models** (Pydantic) — :class:`ToolRequest`
  and :class:`ToolResponse` carry agent identity, MACI role, timeout, and
  metadata for a complete audit trail.
- **OpenTelemetry spans** — every ``execute_tool`` and ``discover_tools``
  call starts a span when the OTEL SDK is present; graceful no-op when not.
- **Per-server circuit breaker** — three consecutive failures on the same
  backend server trip the breaker for a 30-second cooldown, preventing
  cascade failures from propagating through the agent bus.  After the
  cooldown a single *probe* call is allowed through; success resets the
  breaker, failure restarts the cooldown.
- **Intent-based tool lookup** — ``get_tools_for_intent`` tokenises a
  free-text intent string and scores all known tools by keyword hits across
  name, description, and tags, returning the top-10 ranked tools.

Quick start::

    from enhanced_agent_bus.mcp.pool import create_mcp_pool
    from enhanced_agent_bus.mcp.client import MCPClient, MCPClientConfig
    from enhanced_agent_bus.mcp.router import MCPRouter, ToolRequest

    pool = create_mcp_pool(
        MCPClient(MCPClientConfig(server_id="neural", server_url="http://neural-mcp:4000")),
        MCPClient(MCPClientConfig(server_id="toolbox", server_url="http://toolbox:5000")),
    )
    router = MCPRouter(pool=pool)
    await router.start()

    # Tool discovery grouped by category
    categories = await router.discover_tools()
    # → {"neural": [MCPTool(...)], "database": [...], "hitl": [...], "general": [...]}

    # Execute a named tool
    response = await router.execute_tool(
        ToolRequest(
            tool_name="predict_pattern",
            arguments={"input": [0.1, 0.2]},
            agent_id="agent-1",
            maci_role="executor",
        )
    )
    assert response.is_success

    # Find tools for an intent
    tools = await router.get_tools_for_intent("query database for governance policies")

    await router.stop()

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict
from enhanced_agent_bus.observability.structured_logging import get_logger

from .client import _validate_maci_role
from .pool import MCPClientPool
from .types import MCPTool, MCPToolResult, MCPToolStatus

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional OpenTelemetry integration (graceful degradation)
# ---------------------------------------------------------------------------

try:
    from opentelemetry import trace as _otel_trace

    _OTEL_AVAILABLE = True
    _DEFAULT_TRACER: Any = _otel_trace.get_tracer(__name__)
except ImportError:  # pragma: no cover
    _OTEL_AVAILABLE = False
    _DEFAULT_TRACER = None


@contextmanager
def _span(
    tracer: Any,
    name: str,
    attributes: dict[str, str | int | float | bool] | None = None,
) -> Generator[None, None, None]:
    """Start an OTEL span if the SDK is available, otherwise yield a no-op."""
    if tracer is not None and _OTEL_AVAILABLE:
        with tracer.start_as_current_span(name, attributes=attributes or {}):
            yield
    else:
        yield


# ---------------------------------------------------------------------------
# Tool categorisation
# ---------------------------------------------------------------------------

# Keyword sets used to classify MCPTool instances.
# Checked against tool name tokens (split on ``_``) and tag values.
# Precedence: database > neural > hitl > general.

_CATEGORY_KEYWORDS: dict[str, frozenset[str]] = {
    "database": frozenset(
        {
            "db",
            "sql",
            "database",
            "query",
            "postgres",
            "postgresql",
            "redis",
            "store",
            "fetch",
            "record",
            "table",
            "schema",
            "migrate",
            "insert",
            "select",
            "update",
            "delete",
            "transaction",
            "index",
            "collection",
        }
    ),
    "neural": frozenset(
        {
            "neural",
            "ml",
            "ai",
            "predict",
            "embed",
            "embedding",
            "classify",
            "train",
            "inference",
            "model",
            "llm",
            "gnn",
            "domain",
            "pattern",
            "score",
            "vector",
            "semantic",
            "cluster",
            "similarity",
        }
    ),
    "hitl": frozenset(
        {
            "hitl",
            "human",
            "review",
            "approval",
            "approve",
            "escalate",
            "escalation",
            "humanreview",
            "deliberation",
            "oversight",
            "manual",
            "operator",
            "supervisor",
            "delegate",
            "handoff",
        }
    ),
}


class ToolCategory(str, Enum):
    """Domain category for an MCP tool."""

    DATABASE = "database"
    NEURAL = "neural"
    HITL = "hitl"
    GENERAL = "general"


def _classify_tool(tool: MCPTool) -> ToolCategory:
    """Return the :class:`ToolCategory` for *tool*.

    Classification is based on keyword matching.  Tokens are extracted from:
    - Tool name (split on ``_``, ``-``, whitespace — all lower-cased).
    - Tool tags (lower-cased).

    Precedence order when multiple categories match: database > neural >
    hitl > general.
    """
    name_tokens: set[str] = set(re.split(r"[\s_\-]+", tool.name.lower()))
    tag_tokens: set[str] = {t.lower() for t in tool.tags}
    combined: set[str] = name_tokens | tag_tokens

    for category_name in ("database", "neural", "hitl"):
        if combined & _CATEGORY_KEYWORDS[category_name]:
            return ToolCategory(category_name)

    return ToolCategory.GENERAL


# ---------------------------------------------------------------------------
# Per-server circuit breaker
# ---------------------------------------------------------------------------

#: Consecutive failure threshold that trips the breaker.
_CB_FAILURE_THRESHOLD: int = 3
#: Cooldown duration in seconds before a tripped breaker enters HALF_OPEN.
_CB_COOLDOWN_SECONDS: float = 30.0


class _CircuitState(str, Enum):
    """Lifecycle states of :class:`_ServerCircuitBreaker`."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _ServerCircuitBreaker:
    """Lightweight per-server circuit breaker.

    State machine::

        CLOSED  --[≥ 3 consecutive failures]--> OPEN
        OPEN    --[30 s elapsed]-------------> HALF_OPEN
        HALF_OPEN --[probe succeeds]---------> CLOSED
        HALF_OPEN --[probe fails]------------> OPEN (cooldown restarted)

    Only the first concurrent caller in HALF_OPEN state is granted the *probe*
    slot (``_probing=True``).  Subsequent concurrent callers are rejected until
    the probe resolves.

    Attributes:
        server_id: Identifier of the guarded MCP server.
    """

    server_id: str
    _failure_count: int = field(default=0, init=False, repr=False)
    _last_failure_at: float | None = field(default=None, init=False, repr=False)
    _probing: bool = field(default=False, init=False, repr=False)

    # ------------------------------------------------------------------ #
    # State computation
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> _CircuitState:
        """Compute the current circuit state (not cached)."""
        if self._failure_count < _CB_FAILURE_THRESHOLD:
            return _CircuitState.CLOSED
        if self._last_failure_at is None:
            return _CircuitState.CLOSED  # safety guard
        elapsed = time.monotonic() - self._last_failure_at
        if elapsed < _CB_COOLDOWN_SECONDS:
            return _CircuitState.OPEN
        return _CircuitState.HALF_OPEN

    def is_open(self) -> bool:
        """Return ``True`` when requests must be fast-failed."""
        return self.state == _CircuitState.OPEN

    def allow_request(self) -> bool:
        """Decide whether the next request may proceed.

        - ``CLOSED`` → always ``True``.
        - ``OPEN`` → always ``False``.
        - ``HALF_OPEN`` → ``True`` only for the first concurrent caller
          (the *probe*); subsequent concurrent callers receive ``False``.
        """
        s = self.state
        if s == _CircuitState.CLOSED:
            return True
        if s == _CircuitState.OPEN:
            return False
        # HALF_OPEN: permit exactly one probe at a time
        if self._probing:
            return False
        self._probing = True
        return True

    # ------------------------------------------------------------------ #
    # State mutations
    # ------------------------------------------------------------------ #

    def record_success(self) -> None:
        """Reset the breaker to CLOSED on a successful call."""
        prev = self.state
        self._failure_count = 0
        self._last_failure_at = None
        self._probing = False
        if prev != _CircuitState.CLOSED:
            logger.info(
                "mcp_router_circuit_closed",
                server_id=self.server_id,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

    def record_failure(self) -> None:
        """Increment the failure counter; open the circuit at threshold."""
        self._failure_count += 1
        self._last_failure_at = time.monotonic()
        self._probing = False  # release the half-open probe slot on failure

        if self._failure_count == _CB_FAILURE_THRESHOLD:
            logger.warning(
                "mcp_router_circuit_opened",
                server_id=self.server_id,
                failure_count=self._failure_count,
                cooldown_seconds=_CB_COOLDOWN_SECONDS,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
        else:
            logger.debug(
                "mcp_router_circuit_failure",
                server_id=self.server_id,
                failure_count=self._failure_count,
                threshold=_CB_FAILURE_THRESHOLD,
            )

    # ------------------------------------------------------------------ #
    # Observability
    # ------------------------------------------------------------------ #

    def as_dict(self) -> JSONDict:
        """Serialise current breaker state for health-check endpoints."""
        return {
            "server_id": self.server_id,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "last_failure_at": self._last_failure_at,
            "threshold": _CB_FAILURE_THRESHOLD,
            "cooldown_seconds": _CB_COOLDOWN_SECONDS,
        }


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ToolRequest(BaseModel):
    """High-level MCP tool execution request.

    Attributes:
        tool_name: Exact name of the tool to invoke.
        arguments: Tool-specific input parameters (forwarded verbatim).
        agent_id: Calling agent identifier (for audit trail).
        maci_role: MACI role of the calling agent; controls tool access.
        server_id: Optional server hint.  When provided the router directs
            the call to that specific server even if the tool is also
            available elsewhere.
        timeout: Per-call execution timeout in seconds.  ``None`` defers to
            the pool's default.
        metadata: Arbitrary key-value pairs forwarded in the response for
            audit enrichment.
    """

    tool_name: str = Field(..., min_length=1, max_length=256)
    arguments: JSONDict = Field(default_factory=dict)
    agent_id: str = Field(default="", max_length=128)
    maci_role: str = Field(default="", max_length=64)
    server_id: str | None = Field(default=None)
    timeout: float | None = Field(default=None, gt=0)
    metadata: JSONDict = Field(default_factory=dict)


class ToolResponse(BaseModel):
    """High-level MCP tool execution response.

    Attributes:
        request_id: UUID generated by the router for correlation.
        tool_name: Name of the invoked tool.
        server_id: Server that executed (or would have executed) the tool.
        status: Outcome status (mirrors :class:`MCPToolStatus` values).
        content: Tool output payload on success; ``None`` otherwise.
        error: Human-readable error description when ``status != "success"``.
        category: Resolved :class:`ToolCategory` value for the tool.
        latency_ms: Wall-clock execution time in milliseconds.
        constitutional_hash: Governance fingerprint.
        timestamp: timezone.utc timestamp of the response creation.
        circuit_breaker_state: CB state of the target server at call time.
        metadata: Pass-through metadata from :class:`ToolRequest`.
    """

    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    tool_name: str
    server_id: str
    status: str
    content: Any | None = None
    error: str | None = None
    category: str = ToolCategory.GENERAL.value
    latency_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    circuit_breaker_state: str = _CircuitState.CLOSED.value
    metadata: JSONDict = Field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """``True`` when the tool call completed successfully."""
        return self.status == MCPToolStatus.SUCCESS.value

    model_config = ConfigDict(arbitrary_types_allowed=True)


# ---------------------------------------------------------------------------
# MCPRouter
# ---------------------------------------------------------------------------


class MCPRouter:
    """Unified MCP router wrapping an :class:`MCPClientPool`.

    The router adds category-aware tool discovery, OTEL tracing, per-server
    circuit breaking, and intent-based tool lookup on top of the pool's
    raw tool-routing capability.

    Args:
        pool: A configured (and optionally pre-connected)
            :class:`~packages.enhanced_agent_bus.mcp.pool.MCPClientPool`.
        tracer: Optional OpenTelemetry ``Tracer`` instance.  When ``None``
            the default tracer is used if the SDK is available; otherwise
            tracing is silently skipped.
    """

    def __init__(
        self,
        pool: MCPClientPool,
        tracer: Any | None = None,
    ) -> None:
        self._pool = pool
        self._tracer: Any = tracer if tracer is not None else _DEFAULT_TRACER

        # Per-server circuit breakers keyed by server_id (created lazily).
        self._breakers: dict[str, _ServerCircuitBreaker] = {}

        # Category index: category_value → [MCPTool, …]
        # Rebuilt by discover_tools().
        self._category_index: dict[str, list[MCPTool]] = {c.value: [] for c in ToolCategory}

        # Flat tool index: tool_name → MCPTool (carries server_id).
        # Rebuilt by discover_tools().
        self._tool_index: dict[str, MCPTool] = {}

        self._started: bool = False

        logger.info(
            "mcp_router_created",
            pool_size=pool.client_count,
            otel_available=_OTEL_AVAILABLE,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """Connect the pool and perform initial tool discovery.

        Idempotent — safe to call multiple times; subsequent calls are no-ops.
        """
        if self._started:
            return
        await self._pool.connect_all()
        await self.discover_tools()
        self._started = True
        logger.info(
            "mcp_router_started",
            servers=self._pool.server_ids(),
            total_tools=len(self._tool_index),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    async def stop(self) -> None:
        """Disconnect the pool.

        Idempotent — subsequent calls are no-ops.
        """
        if not self._started:
            return
        await self._pool.disconnect_all()
        self._started = False
        logger.info(
            "mcp_router_stopped",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[MCPRouter, None]:
        """Async context manager that start/stop the router automatically."""
        await self.start()
        try:
            yield self
        finally:
            await self.stop()

    # ------------------------------------------------------------------ #
    # Tool discovery
    # ------------------------------------------------------------------ #

    async def discover_tools(self) -> dict[str, list[MCPTool]]:
        """Discover and categorise all tools from connected servers.

        Calls :meth:`~MCPClientPool.list_tools` on the underlying pool,
        classifies each tool, and rebuilds the router's internal indexes.

        Servers with an OPEN circuit breaker do not contribute tools (their
        existing entries are dropped from the index until the breaker resets).

        Returns:
            Mapping of :class:`ToolCategory` string values to lists of
            :class:`MCPTool` — e.g.
            ``{"database": [...], "neural": [...], "hitl": [...],
            "general": [...]}``.

        Note:
            Call this method after the pool has connected to refresh the
            index.  The router's :meth:`start` calls it automatically.
        """
        with _span(
            self._tracer,
            "mcp.router.discover_tools",
            {"mcp.pool_size": pool_size_attr(self._pool)},
        ):
            # Fetch the full tool list from the pool (already de-duplicated
            # and server_id-stamped by the pool's _collect_client_tools).
            try:
                all_tools: list[MCPTool] = await self._pool.list_tools()
            except Exception as exc:
                logger.error(
                    "mcp_router_discover_pool_error",
                    error=str(exc),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                    exc_info=True,
                )
                return {c.value: [] for c in ToolCategory}

            # Rebuild category and flat indexes.
            new_category: dict[str, list[MCPTool]] = {c.value: [] for c in ToolCategory}
            new_flat: dict[str, MCPTool] = {}

            for tool in all_tools:
                # Skip tools from servers whose circuit is OPEN.
                sid = tool.server_id
                if sid and self._get_breaker(sid).is_open():
                    logger.warning(
                        "mcp_router_discover_skipped_open_circuit",
                        server_id=sid,
                        tool_name=tool.name,
                        constitutional_hash=CONSTITUTIONAL_HASH,
                    )
                    continue

                category = _classify_tool(tool)
                new_category[category.value].append(tool)
                new_flat[tool.name] = tool

            self._category_index = new_category
            self._tool_index = new_flat

            logger.info(
                "mcp_router_discover_complete",
                category_counts={k: len(v) for k, v in new_category.items()},
                total_tools=len(new_flat),
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            return dict(new_category)  # defensive copy

    # ------------------------------------------------------------------ #
    # Tool execution
    # ------------------------------------------------------------------ #

    async def execute_tool(self, request: ToolRequest) -> ToolResponse:
        """Execute a single tool through the MCP pool.

        Execution flow:

        1. Resolve the target server (from ``request.server_id`` or the tool
           index).
        2. Consult the per-server circuit breaker — reject immediately when
           OPEN, allow through when CLOSED or HALF_OPEN (first caller).
        3. Delegate to :meth:`~MCPClientPool.call_tool`; apply
           ``request.timeout`` if set.
        4. Record success / failure in the circuit breaker.
        5. Wrap the raw :class:`MCPToolResult` in a :class:`ToolResponse`.

        An OTEL span is created for every call (no-op when SDK is absent).

        Args:
            request: Describes the tool to invoke and its parameters.

        Returns:
            :class:`ToolResponse` — **never raises**; errors are encoded in
            the response's ``status`` and ``error`` fields.
        """
        request_id = uuid.uuid4().hex
        t_start = time.monotonic()

        span_attrs = {
            "mcp.tool_name": request.tool_name,
            "mcp.agent_id": request.agent_id,
            "mcp.maci_role": request.maci_role,
            "mcp.request_id": request_id,
            "acgs.constitutional_hash": CONSTITUTIONAL_HASH,
        }

        with _span(self._tracer, "mcp.router.execute_tool", span_attrs):
            logger.info(
                "mcp_router_execute_start",
                tool_name=request.tool_name,
                agent_id=request.agent_id,
                maci_role=request.maci_role,
                server_hint=request.server_id,
                request_id=request_id,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            valid_role, role_or_reason = _validate_maci_role(request.maci_role)
            if not valid_role:
                latency_ms = _elapsed_ms(t_start)
                logger.warning(
                    "mcp_router_invalid_maci_role",
                    tool_name=request.tool_name,
                    agent_id=request.agent_id,
                    maci_role=request.maci_role,
                    request_id=request_id,
                    reason=role_or_reason,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return _build_forbidden_response(
                    request=request,
                    server_id=request.server_id or "<unresolved>",
                    error=role_or_reason,
                    latency_ms=latency_ms,
                    request_id=request_id,
                )

            # -- Resolve server id and category ----------------------------
            server_id, tool = self._resolve_server_id(request)

            if server_id is None:
                latency_ms = _elapsed_ms(t_start)
                logger.warning(
                    "mcp_router_tool_not_found",
                    tool_name=request.tool_name,
                    request_id=request_id,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return _build_error_response(
                    request=request,
                    server_id="<unknown>",
                    error=(
                        f"Tool '{request.tool_name}' not found in any "
                        "connected server. Call discover_tools() first."
                    ),
                    latency_ms=latency_ms,
                    request_id=request_id,
                    tool=tool,
                )

            category = _classify_tool(tool).value if tool else ToolCategory.GENERAL.value

            # -- Circuit breaker check -------------------------------------
            breaker = self._get_breaker(server_id)
            cb_state_before = breaker.state.value

            if not breaker.allow_request():
                latency_ms = _elapsed_ms(t_start)
                logger.warning(
                    "mcp_router_circuit_rejected",
                    tool_name=request.tool_name,
                    server_id=server_id,
                    request_id=request_id,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
                return ToolResponse(
                    request_id=request_id,
                    tool_name=request.tool_name,
                    server_id=server_id,
                    status=MCPToolStatus.ERROR.value,
                    error=(
                        f"Circuit breaker OPEN for server '{server_id}'. "
                        f"Retry after {_CB_COOLDOWN_SECONDS:.0f} s."
                    ),
                    category=category,
                    latency_ms=latency_ms,
                    circuit_breaker_state=cb_state_before,
                    metadata={**request.metadata, "request_id": request_id},
                )

            # -- Execute via pool ------------------------------------------
            try:
                raw: MCPToolResult = await self._call_with_timeout(
                    request=request,
                    server_id=server_id,
                )
            except Exception as exc:
                breaker.record_failure()
                latency_ms = _elapsed_ms(t_start)
                logger.error(
                    "mcp_router_execute_exception",
                    tool_name=request.tool_name,
                    server_id=server_id,
                    request_id=request_id,
                    error=str(exc),
                    constitutional_hash=CONSTITUTIONAL_HASH,
                    exc_info=True,
                )
                return _build_error_response(
                    request=request,
                    server_id=server_id,
                    error=str(exc),
                    latency_ms=latency_ms,
                    request_id=request_id,
                    tool=tool,
                    circuit_breaker_state=breaker.state.value,
                )

            latency_ms = _elapsed_ms(t_start)

            # -- Update circuit breaker ------------------------------------
            if raw.status in (MCPToolStatus.SUCCESS, MCPToolStatus.FORBIDDEN):
                # FORBIDDEN means the server replied normally (MACI gate).
                breaker.record_success()
            elif raw.status == MCPToolStatus.ERROR:
                breaker.record_failure()
            # TIMEOUT is not counted: the server may have processed the call;
            # retrying blindly risks duplicate side-effects.

            logger.info(
                "mcp_router_execute_done",
                tool_name=request.tool_name,
                server_id=server_id,
                status=raw.status.value,
                request_id=request_id,
                latency_ms=round(latency_ms, 2),
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            return ToolResponse(
                request_id=request_id,
                tool_name=raw.tool_name,
                server_id=server_id,
                status=raw.status.value,
                content=raw.content,
                error=raw.error,
                category=category,
                latency_ms=latency_ms,
                constitutional_hash=CONSTITUTIONAL_HASH,
                circuit_breaker_state=breaker.state.value,
                metadata={**request.metadata, "request_id": request_id},
            )

    # ------------------------------------------------------------------ #
    # Intent-based tool lookup
    # ------------------------------------------------------------------ #

    async def get_tools_for_intent(self, intent: str) -> list[MCPTool]:
        """Return tools most relevant to *intent*.

        The intent string is tokenised (split on whitespace and punctuation)
        and each token is matched against tool name tokens, description words,
        and tag values.  Tools are ranked by hit count; the top-10 are
        returned.

        If the tool index is empty, :meth:`discover_tools` is triggered first
        so callers can use this method without calling ``start()``.

        Args:
            intent: Free-text description, e.g. ``"query database for policy"``.

        Returns:
            Up to 10 :class:`MCPTool` instances ranked best-first.
        """
        with _span(
            self._tracer,
            "mcp.router.get_tools_for_intent",
            {"mcp.intent": intent[:256]},
        ):
            if not self._tool_index:
                logger.info(
                    "mcp_router_intent_trigger_discover",
                    intent=intent[:128],
                )
                await self.discover_tools()

            # Tokenise the intent — keep tokens longer than 2 characters.
            intent_tokens: set[str] = {
                t.lower() for t in re.split(r"[\s\W]+", intent) if len(t) > 2
            }

            if not intent_tokens:
                return []

            scored: list[tuple[int, MCPTool]] = []

            for tool in self._tool_index.values():
                name_toks = set(re.split(r"[\s_\-]+", tool.name.lower()))
                desc_toks = set(re.split(r"\s+", tool.description.lower()))
                tag_toks = {t.lower() for t in tool.tags}
                candidate = name_toks | desc_toks | tag_toks

                hits = len(intent_tokens & candidate)
                if hits > 0:
                    scored.append((hits, tool))

            scored.sort(key=lambda pair: pair[0], reverse=True)
            result = [t for _, t in scored[:10]]

            logger.info(
                "mcp_router_intent_done",
                intent=intent[:128],
                token_count=len(intent_tokens),
                matches=len(result),
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
            return result

    # ------------------------------------------------------------------ #
    # Circuit-breaker introspection
    # ------------------------------------------------------------------ #

    def circuit_breaker_metrics(self) -> dict[str, JSONDict]:
        """Return circuit breaker state for every known server.

        Suitable for health-check endpoints and Prometheus exporters.

        Returns:
            ``{server_id: {state, failure_count, …}, …}``
        """
        return {sid: cb.as_dict() for sid, cb in self._breakers.items()}

    def reset_circuit_breaker(self, server_id: str) -> None:
        """Manually force the breaker for *server_id* to CLOSED.

        Intended for operator use after a known-good deployment of a backend
        server so traffic can resume without waiting for the cooldown.
        """
        cb = self._breakers.get(server_id)
        if cb is not None:
            cb.record_success()
            logger.info(
                "mcp_router_circuit_reset",
                server_id=server_id,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )
        else:
            logger.debug(
                "mcp_router_circuit_reset_noop",
                server_id=server_id,
                reason="no breaker exists for this server_id",
            )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _get_breaker(self, server_id: str) -> _ServerCircuitBreaker:
        """Return (or lazily create) the circuit breaker for *server_id*."""
        if server_id not in self._breakers:
            self._breakers[server_id] = _ServerCircuitBreaker(server_id=server_id)
        return self._breakers[server_id]

    def _resolve_server_id(self, request: ToolRequest) -> tuple[str | None, MCPTool | None]:
        """Determine the target server_id and MCPTool for *request*.

        Resolution order:

        1. ``request.server_id`` explicitly set — find the tool descriptor
           from the category index for that server.
        2. Tool index lookup by ``request.tool_name`` (uses the server_id
           embedded in the :class:`MCPTool` by the pool).
        3. Return ``(None, None)`` when the tool is not known.
        """
        # Explicit server hint
        if request.server_id:
            # Find the tool descriptor for the hinted server
            for tool in self._tool_index.values():
                if tool.name == request.tool_name and tool.server_id == request.server_id:
                    return request.server_id, tool
            # Tool not in index for that server; still honour the hint but
            # return None for the descriptor (call will likely fail).
            return request.server_id, None

        # Index lookup
        tool = self._tool_index.get(request.tool_name)
        if tool is not None:
            return tool.server_id or "<pool>", tool

        return None, None

    async def _call_with_timeout(
        self,
        request: ToolRequest,
        server_id: str,
    ) -> MCPToolResult:
        """Delegate to the pool's call_tool, applying optional timeout."""
        coro = self._pool.call_tool(
            request.tool_name,
            arguments=request.arguments,
            agent_id=request.agent_id,
            agent_role=request.maci_role,
        )
        if request.timeout is not None:
            return await asyncio.wait_for(coro, timeout=request.timeout)
        return await coro

    # ------------------------------------------------------------------ #
    # Dunder
    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:
        return (
            f"MCPRouter("
            f"servers={self._pool.server_ids()!r}, "
            f"tools={len(self._tool_index)}, "
            f"started={self._started}"
            f")"
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _elapsed_ms(t_start: float) -> float:
    """Return milliseconds elapsed since *t_start* (from ``time.monotonic``)."""
    return (time.monotonic() - t_start) * 1_000.0


def pool_size_attr(pool: MCPClientPool) -> str:
    """Return pool client count as a string (safe OTEL attribute type)."""
    return str(pool.client_count)


def _build_error_response(
    *,
    request: ToolRequest,
    server_id: str,
    error: str,
    latency_ms: float,
    request_id: str,
    tool: MCPTool | None,
    circuit_breaker_state: str = _CircuitState.CLOSED.value,
) -> ToolResponse:
    """Construct a uniform error :class:`ToolResponse`."""
    return ToolResponse(
        request_id=request_id,
        tool_name=request.tool_name,
        server_id=server_id,
        status=MCPToolStatus.ERROR.value,
        error=error,
        category=_classify_tool(tool).value if tool else ToolCategory.GENERAL.value,
        latency_ms=latency_ms,
        constitutional_hash=CONSTITUTIONAL_HASH,
        circuit_breaker_state=circuit_breaker_state,
        metadata={**request.metadata, "request_id": request_id},
    )


def _build_forbidden_response(
    *,
    request: ToolRequest,
    server_id: str,
    error: str,
    latency_ms: float,
    request_id: str,
) -> ToolResponse:
    """Construct a uniform forbidden :class:`ToolResponse`."""
    return ToolResponse(
        request_id=request_id,
        tool_name=request.tool_name,
        server_id=server_id,
        status=MCPToolStatus.FORBIDDEN.value,
        error=error,
        category=ToolCategory.GENERAL.value,
        latency_ms=latency_ms,
        constitutional_hash=CONSTITUTIONAL_HASH,
        circuit_breaker_state=_CircuitState.CLOSED.value,
        metadata={**request.metadata, "request_id": request_id},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "_CB_COOLDOWN_SECONDS",
    "_CB_FAILURE_THRESHOLD",
    # Router
    "MCPRouter",
    # Category enum + classifier
    "ToolCategory",
    # Models
    "ToolRequest",
    "ToolResponse",
    # Circuit breaker internals (exposed for tests)
    "_CircuitState",
    "_ServerCircuitBreaker",
    "_classify_tool",
    # Helpers
    "pool_size_attr",
]
