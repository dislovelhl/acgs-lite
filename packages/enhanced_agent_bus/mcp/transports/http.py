# Constitutional Hash: 608508a9bd224290
"""
HTTP Transport for MCP Toolbox communication.

Maps MCP JSON-RPC 2.0 method calls to Toolbox REST endpoints:

    tools/list   -> GET  /api/tools
    tools/call   -> POST /api/tools/{name}

Unsupported JSON-RPC methods return a JSON-RPC ``method_not_found`` error
response so callers remain unaware of the transport layer.

Features
--------
- Async ``httpx.AsyncClient`` with configurable connect / read timeouts.
- Exponential back-off retry with optional jitter (configurable).
- Bearer-token and arbitrary header auth.
- Structured logging at every retry and failure boundary.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict
from enhanced_agent_bus.mcp.transports.base import MCPTransportError
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_JSONRPC_VERSION = "2.0"

# JSON-RPC standard error codes
_ERR_METHOD_NOT_FOUND = -32601
_ERR_INTERNAL = -32603

# Toolbox REST path prefix
_TOOLS_PREFIX = "/api/tools"

# HTTP status codes that are safe to retry
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})


# ---------------------------------------------------------------------------
# Helper: JSON-RPC response builders
# ---------------------------------------------------------------------------


def _rpc_success(request_id: str | int | None, result: Any) -> JSONDict:
    """Return a minimal JSON-RPC 2.0 success response."""
    return {
        "jsonrpc": _JSONRPC_VERSION,
        "id": request_id,
        "result": result,
    }


def _rpc_error(
    request_id: str | int | None,
    code: int,
    message: str,
    data: JSONDict | None = None,
) -> JSONDict:
    """Return a minimal JSON-RPC 2.0 error response."""
    error: JSONDict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": _JSONRPC_VERSION,
        "id": request_id,
        "error": error,
    }


# ---------------------------------------------------------------------------
# HTTPTransport
# ---------------------------------------------------------------------------


class HTTPTransport:
    """
    MCP transport that maps JSON-RPC calls to Toolbox REST endpoints.

    Implements the :class:`~packages.enhanced_agent_bus.mcp.transports.base.MCPTransport`
    structural Protocol; no explicit inheritance is required.

    Args:
        base_url:
            Root URL of the Toolbox REST API, e.g. ``"http://localhost:5000"``.
        auth_token:
            Optional Bearer token sent in every request as
            ``Authorization: Bearer <token>``.
        extra_headers:
            Additional HTTP headers merged into every request.  Header names
            are case-insensitive.
        connect_timeout:
            Seconds to wait for the TCP connection to be established.
            Default: ``5.0``.
        read_timeout:
            Seconds to wait for the server to begin sending a response body.
            Default: ``30.0``.
        max_retries:
            Maximum number of additional attempts after the first failure
            (``0`` means try once, no retries).  Default: ``3``.
        retry_base_delay:
            Base delay in seconds for the first retry back-off interval.
            Subsequent intervals grow exponentially.  Default: ``0.5``.
        retry_max_delay:
            Upper bound on the back-off delay in seconds.  Default: ``10.0``.
        retry_jitter:
            When *True* a random fraction of ``retry_base_delay`` is added to
            each back-off interval to spread thundering-herd load.
            Default: ``True``.

    Example::

        transport = HTTPTransport(
            base_url="http://toolbox:5000",
            auth_token="secret-token",
            max_retries=3,
        )
        await transport.connect()
        response = await transport.send({
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}
        })
        tools = response["result"]["tools"]
        await transport.disconnect()
    """

    CONSTITUTIONAL_HASH: str = CONSTITUTIONAL_HASH

    def __init__(
        self,
        base_url: str,
        *,
        auth_token: str | None = None,
        extra_headers: dict[str, str] | None = None,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
        max_retries: int = 3,
        retry_base_delay: float = 0.5,
        retry_max_delay: float = 10.0,
        retry_jitter: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth_token = auth_token
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._max_retries = max(0, max_retries)
        self._retry_base_delay = retry_base_delay
        self._retry_max_delay = retry_max_delay
        self._retry_jitter = retry_jitter

        # Build static headers applied to every request
        self._headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Constitutional-Hash": self.CONSTITUTIONAL_HASH,
        }
        if auth_token:
            self._headers["Authorization"] = f"Bearer {auth_token}"
        if extra_headers:
            self._headers.update(extra_headers)

        self._client: httpx.AsyncClient | None = None
        self._connected: bool = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """
        Create the underlying ``httpx.AsyncClient`` and verify connectivity.

        A lightweight ``GET /api/tools`` probe is issued to confirm that the
        Toolbox is reachable.  Raises :class:`MCPTransportError` on failure.
        """
        if self._connected and self._client is not None:
            logger.debug(
                "HTTPTransport.connect() called on already-connected transport",
                extra={"base_url": self._base_url},
            )
            return

        # Use read_timeout as the default for all phases; override connect specifically.
        timeout = httpx.Timeout(self._read_timeout, connect=self._connect_timeout)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=timeout,
            follow_redirects=True,
        )

        # Probe connectivity with a lightweight tools/list request
        try:
            resp = await self._client.get(_TOOLS_PREFIX)
            resp.raise_for_status()
            self._connected = True
            logger.info(
                "HTTPTransport connected",
                extra={
                    "base_url": self._base_url,
                    "probe_status": resp.status_code,
                    "constitutional_hash": self.CONSTITUTIONAL_HASH,
                },
            )
        except httpx.HTTPStatusError as exc:
            await self._teardown_client()
            raise MCPTransportError(
                f"Toolbox connectivity probe failed with HTTP {exc.response.status_code}",
                transport_type="http",
                endpoint=str(exc.request.url),
                cause=exc,
            ) from exc
        except httpx.TransportError as exc:
            await self._teardown_client()
            raise MCPTransportError(
                f"Toolbox connectivity probe failed: {exc}",
                transport_type="http",
                endpoint=self._base_url,
                cause=exc,
            ) from exc

    async def disconnect(self) -> None:
        """
        Close the HTTP client and release all associated resources.

        Idempotent — safe to call multiple times.
        """
        was_connected = self._connected
        self._connected = False
        await self._teardown_client()
        if was_connected:
            logger.info(
                "HTTPTransport disconnected",
                extra={"base_url": self._base_url},
            )

    # ------------------------------------------------------------------
    # Core send / dispatch
    # ------------------------------------------------------------------

    async def send(self, message: JSONDict) -> JSONDict:
        """
        Dispatch a JSON-RPC 2.0 request to the Toolbox REST API.

        Routing table:

        +-----------------+----------------------------------+
        | JSON-RPC method | REST call                        |
        +=================+==================================+
        | tools/list      | GET  /api/tools                  |
        +-----------------+----------------------------------+
        | tools/call      | POST /api/tools/{params["name"]} |
        +-----------------+----------------------------------+

        Any other method returns a JSON-RPC ``method_not_found`` error.

        Args:
            message: JSON-RPC 2.0 request dict.

        Returns:
            JSON-RPC 2.0 response dict (``"result"`` or ``"error"`` key).

        Raises:
            MCPTransportError: On unrecoverable network or HTTP failure.
        """
        if not self._connected or self._client is None:
            raise MCPTransportError(
                "HTTPTransport.send() called before connect()",
                transport_type="http",
                endpoint=self._base_url,
            )

        method: str = str(message.get("method", ""))
        request_id = message.get("id")
        params: JSONDict = message.get("params") or {}  # type: ignore[assignment]

        logger.debug(
            "HTTPTransport.send()",
            extra={"method": method, "request_id": request_id},
        )

        if method == "tools/list":
            return await self._tools_list(request_id)
        elif method == "tools/call":
            return await self._tools_call(request_id, params)
        else:
            logger.warning(
                "HTTPTransport: unsupported JSON-RPC method",
                extra={"method": method},
            )
            return _rpc_error(
                request_id,
                _ERR_METHOD_NOT_FOUND,
                f"Method not supported by HTTPTransport: {method}",
            )

    # ------------------------------------------------------------------
    # Method handlers
    # ------------------------------------------------------------------

    async def _tools_list(self, request_id: str | int | None) -> JSONDict:
        """Handle ``tools/list`` -> GET /api/tools."""
        raw = await self._get_with_retry(_TOOLS_PREFIX)

        # Toolbox may return a list directly or a dict with a "tools" key
        if isinstance(raw, list):
            tools = raw
        elif isinstance(raw, dict):
            tools = raw.get("tools", raw)
        else:
            tools = []

        return _rpc_success(request_id, {"tools": tools})

    async def _tools_call(
        self,
        request_id: str | int | None,
        params: JSONDict,
    ) -> JSONDict:
        """Handle ``tools/call`` -> POST /api/tools/{name}."""
        tool_name = params.get("name")
        if not tool_name:
            return _rpc_error(
                request_id,
                _ERR_INTERNAL,
                "tools/call requires params.name",
            )

        arguments: JSONDict = params.get("arguments") or {}  # type: ignore[assignment]
        endpoint = f"{_TOOLS_PREFIX}/{tool_name}"
        raw = await self._post_with_retry(endpoint, body=arguments)

        # Normalise to MCP tool-result content envelope
        if isinstance(raw, dict) and "content" in raw:
            result = raw
        else:
            result = {
                "content": [{"type": "text", "text": str(raw)}],
                "isError": False,
            }

        return _rpc_success(request_id, result)

    # ------------------------------------------------------------------
    # HTTP helpers with retry / back-off
    # ------------------------------------------------------------------

    async def _get_with_retry(self, path: str) -> Any:
        """Issue a GET request with exponential back-off retry."""
        return await self._request_with_retry("GET", path)

    async def _post_with_retry(self, path: str, body: JSONDict) -> Any:
        """Issue a POST request with exponential back-off retry."""
        return await self._request_with_retry("POST", path, json_body=body)

    async def _request_with_retry(
        self,
        http_method: str,
        path: str,
        json_body: JSONDict | None = None,
    ) -> Any:
        """
        Execute an HTTP request with configurable retry and back-off.

        Args:
            http_method: ``"GET"`` or ``"POST"``.
            path: URL path relative to ``base_url``.
            json_body: Optional JSON payload for POST requests.

        Returns:
            Parsed JSON response body.

        Raises:
            MCPTransportError: After all retry attempts are exhausted.
        """
        assert self._client is not None  # guarded by connect() check in send()

        last_exc: BaseException | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(
                    http_method,
                    path,
                    json=json_body,
                )

                if response.status_code in _RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                    # Treat retryable HTTP errors the same as transport errors
                    logger.warning(
                        "HTTPTransport: retryable HTTP status, will retry",
                        extra={
                            "method": http_method,
                            "path": path,
                            "status": response.status_code,
                            "attempt": attempt + 1,
                            "max_retries": self._max_retries,
                        },
                    )
                    await self._backoff(attempt)
                    continue

                response.raise_for_status()
                return response.json()

            except httpx.TimeoutException as exc:
                last_exc = exc
                logger.warning(
                    "HTTPTransport: request timed out",
                    extra={
                        "method": http_method,
                        "path": path,
                        "attempt": attempt + 1,
                        "max_retries": self._max_retries,
                        "error": str(exc),
                    },
                )
            except httpx.HTTPStatusError as exc:
                # Non-retryable HTTP error (or exhausted retries above)
                raise MCPTransportError(
                    f"HTTP {exc.response.status_code} from Toolbox at {path}",
                    transport_type="http",
                    endpoint=str(exc.request.url),
                    cause=exc,
                ) from exc
            except httpx.TransportError as exc:
                last_exc = exc
                logger.warning(
                    "HTTPTransport: transport error",
                    extra={
                        "method": http_method,
                        "path": path,
                        "attempt": attempt + 1,
                        "max_retries": self._max_retries,
                        "error": str(exc),
                    },
                )

            if attempt < self._max_retries:
                await self._backoff(attempt)

        # All attempts exhausted
        raise MCPTransportError(
            f"All {self._max_retries + 1} attempt(s) failed for {http_method} {path}",
            transport_type="http",
            endpoint=f"{self._base_url}{path}",
            cause=last_exc,
        )

    async def _backoff(self, attempt: int) -> None:
        """
        Sleep for an exponentially increasing interval.

        delay = min(base * 2^attempt + jitter, max_delay)
        """
        delay = min(self._retry_base_delay * (2**attempt), self._retry_max_delay)
        if self._retry_jitter:
            delay += random.uniform(0, self._retry_base_delay)
        logger.debug(
            "HTTPTransport: back-off before retry",
            extra={"attempt": attempt, "delay_seconds": round(delay, 3)},
        )
        await asyncio.sleep(delay)

    # ------------------------------------------------------------------
    # Internal teardown
    # ------------------------------------------------------------------

    async def _teardown_client(self) -> None:
        """Close and nullify the internal httpx client."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                logger.debug("HTTPTransport: error closing httpx client (suppressed)")
            finally:
                self._client = None

    # ------------------------------------------------------------------
    # Properties / context manager
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Return *True* if the transport is currently connected."""
        return self._connected

    @property
    def base_url(self) -> str:
        """Return the Toolbox base URL."""
        return self._base_url

    async def __aenter__(self) -> HTTPTransport:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"HTTPTransport(base_url={self._base_url!r}, status={status!r})"


__all__ = ["HTTPTransport"]
