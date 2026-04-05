"""
ACGS-2 Enhanced Agent Bus — OPAL Policy Client
Constitutional Hash: 608508a9bd224290

Provides OPALPolicyClient: wraps the existing OPA client with live policy updates
delivered via the OPAL (Open Policy Administration Layer) websocket channel.

Graceful degradation: if OPAL server is unavailable the client falls back to
direct OPA HTTP queries using the existing OPAClient / CircuitBreakerOPAClient.

Key design:
- Connect once; receive policy/data push events over websocket
- On each push event invalidate the local OPA cache and notify listeners
- All policy update events are forwarded to the audit service
- Fail-closed: if OPA itself is down, evaluations return deny

References:
  OPAL docs  - https://docs.opal.ac/
  OPAL PyPI  - opal-client (optional dep)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from .audit_client import AuditClient
except ImportError:
    AuditClient = None  # type: ignore[assignment,misc]

try:
    from .opa_client import OPAClient
except ImportError:
    OPAClient = None  # type: ignore[assignment,misc]

try:
    import websockets  # type: ignore[import-untyped]

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

OPAL_DEFAULT_SERVER_URL = "http://opal-server:7002"
OPAL_DEFAULT_CLIENT_TOKEN = ""
OPAL_DEFAULT_PROPAGATION_TIMEOUT = 60


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class OPALConnectionState(str, Enum):
    """Websocket connection lifecycle states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class PolicyUpdateEvent(BaseModel):
    """Normalised OPAL policy-update event."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str = Field(description="OPAL event type, e.g. policy_update / data_update")
    policy_id: str | None = Field(default=None, description="Policy identifier if applicable")
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="Hash validated at update time",
    )
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    opal_server_url: str = Field(default="")
    raw_payload: JSONDict = Field(default_factory=dict)


class OPALClientStatus(BaseModel):
    """Runtime status snapshot for the OPAL client."""

    enabled: bool
    connection_state: OPALConnectionState
    opal_server_url: str
    last_update_at: str | None = None
    total_updates_received: int = 0
    fallback_active: bool = False
    constitutional_hash: str = CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class OPALPolicyClient:
    """
    Wraps the existing OPA client with live policy distribution via OPAL.

    Usage::

        client = OPALPolicyClient(
            opa_url="http://localhost:8181",
            opal_server_url="http://opal-server:7002",
        )
        await client.connect()

        # Evaluate as normal — updates arrive automatically in background
        result = await client.evaluate("data.acgs.allow", {"action": "read"})

        await client.disconnect()

    If the OPAL server is unreachable, the client continues to serve OPA
    queries from the current (cached) policy state.
    """

    def __init__(
        self,
        opa_url: str | None = None,
        opal_server_url: str | None = None,
        opal_token: str | None = None,
        opal_enabled: bool = True,
        propagation_timeout: int = OPAL_DEFAULT_PROPAGATION_TIMEOUT,
        audit_service_url: str = "http://localhost:8001",
        fail_closed: bool = True,
    ) -> None:
        """Initialise the OPAL policy client.

        Args:
            opa_url: OPA HTTP API endpoint (defaults to OPA_URL env var).
            opal_server_url: OPAL server base URL (defaults to OPAL_SERVER_URL env var).
            opal_token: Bearer token for OPAL auth (defaults to OPAL_CLIENT_TOKEN env var).
            opal_enabled: Feature flag — set False to bypass OPAL entirely.
            propagation_timeout: Seconds to wait for propagation confirmation.
            audit_service_url: Audit service endpoint for event logging.
            fail_closed: Return deny on OPA errors (security default).
        """
        self.opa_url = (opa_url or os.getenv("OPA_URL", "http://localhost:8181")).rstrip("/")
        self.opal_server_url = (
            opal_server_url or os.getenv("OPAL_SERVER_URL", OPAL_DEFAULT_SERVER_URL)
        ).rstrip("/")
        self.opal_token = opal_token or os.getenv("OPAL_CLIENT_TOKEN", OPAL_DEFAULT_CLIENT_TOKEN)
        self.opal_enabled = opal_enabled and bool(
            os.getenv("OPAL_ENABLED", "true").lower() != "false"
        )
        self.propagation_timeout = propagation_timeout
        self.audit_service_url = audit_service_url
        self.fail_closed = fail_closed

        # Internal state
        self._connection_state = OPALConnectionState.DISCONNECTED
        self._last_update_at: str | None = None
        self._total_updates: int = 0
        self._fallback_active: bool = False
        self._ws_task: asyncio.Task[None] | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._opa_client: Any = None
        self._audit_client: Any = None
        self._update_listeners: list[asyncio.Queue[PolicyUpdateEvent]] = []
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Connect to OPA and start the OPAL websocket listener."""
        self._http_client = httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )

        # Initialise audit client
        if AuditClient:
            try:
                self._audit_client = AuditClient(service_url=self.audit_service_url)
                await self._audit_client.start()
            except (ConnectionError, TimeoutError, httpx.HTTPError, ValueError) as exc:
                logger.warning("Audit client init failed (non-fatal): %s", exc)
                self._audit_client = None

        # Initialise OPA client
        if OPAClient:
            try:
                self._opa_client = OPAClient(opa_url=self.opa_url)
                await self._opa_client.initialize()
                logger.info("OPA client connected at %s", self.opa_url)
            except (ConnectionError, TimeoutError, httpx.HTTPError, ValueError) as exc:
                logger.warning("OPA client init failed (non-fatal): %s", exc)
                self._opa_client = None

        # Start OPAL websocket listener
        if self.opal_enabled:
            self._stop_event.clear()
            self._ws_task = asyncio.create_task(
                self._run_websocket_listener(), name="opal-ws-listener"
            )
            logger.info("OPAL websocket listener started (server=%s)", self.opal_server_url)
        else:
            logger.info("OPAL disabled — using direct OPA queries only")
            self._fallback_active = True

    async def disconnect(self) -> None:
        """Stop the websocket listener and close all connections."""
        self._stop_event.set()

        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task
            self._ws_task = None

        if self._opa_client:
            with contextlib.suppress(Exception):
                await self._opa_client.close()
            self._opa_client = None

        if self._audit_client:
            with contextlib.suppress(Exception):
                await self._audit_client.stop()
            self._audit_client = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        self._connection_state = OPALConnectionState.DISCONNECTED
        logger.info("OPAL policy client disconnected")

    # ------------------------------------------------------------------
    # Policy evaluation (delegates to underlying OPA client)
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        policy_path: str,
        input_data: JSONDict,
        *,
        default_deny: bool | None = None,
    ) -> bool:
        """Evaluate a policy against OPA.

        Args:
            policy_path: OPA data path, e.g. ``data.acgs.allow``.
            input_data: Input document passed to OPA.
            default_deny: Override fail_closed behaviour for this call.

        Returns:
            True if policy allows the request, False otherwise.
        """
        deny_on_error = self.fail_closed if default_deny is None else default_deny

        if self._opa_client:
            try:
                result = await self._opa_client.evaluate(policy_path, input_data)
                return bool(result)
            except (ConnectionError, TimeoutError, httpx.HTTPError, ValueError) as exc:
                logger.error("OPA evaluation error (%s): %s", policy_path, exc)
                return not deny_on_error

        # No OPA client — direct HTTP fallback
        return await self._evaluate_direct_http(policy_path, input_data, deny_on_error)

    async def _evaluate_direct_http(
        self, policy_path: str, input_data: JSONDict, deny_on_error: bool
    ) -> bool:
        """Call OPA REST API directly as last-resort fallback."""
        if not self._http_client:
            logger.error("No HTTP client for OPA fallback evaluation")
            return not deny_on_error

        path = policy_path.replace("data.", "", 1).replace(".", "/")
        url = f"{self.opa_url}/v1/data/{path}"
        try:
            response = await self._http_client.post(url, json={"input": input_data})
            if response.status_code == 200:
                body = response.json()
                return bool(body.get("result", False))
            logger.warning("OPA HTTP %s for path %s", response.status_code, policy_path)
            return not deny_on_error
        except httpx.HTTPError as exc:
            logger.error("OPA HTTP error for %s: %s", policy_path, exc)
            return not deny_on_error

    # ------------------------------------------------------------------
    # OPAL websocket listener
    # ------------------------------------------------------------------

    async def _run_websocket_listener(self) -> None:
        """Persistent reconnecting websocket listener for OPAL push events."""
        retry_delay = 1.0
        max_retry_delay = 30.0

        while not self._stop_event.is_set():
            try:
                await self._connect_websocket()
                retry_delay = 1.0  # reset on successful connection
            except asyncio.CancelledError:
                break
            except (ConnectionError, OSError, TimeoutError, httpx.HTTPError) as exc:
                logger.warning("OPAL websocket error (retry in %.0fs): %s", retry_delay, exc)
                self._connection_state = OPALConnectionState.RECONNECTING
                self._fallback_active = True

                try:
                    await asyncio.wait_for(
                        asyncio.shield(self._stop_event.wait()), timeout=retry_delay
                    )
                    break  # stop_event fired during sleep
                except TimeoutError:
                    pass

                retry_delay = min(retry_delay * 2, max_retry_delay)

        self._connection_state = OPALConnectionState.DISCONNECTED

    async def _connect_websocket(self) -> None:
        """Establish one websocket connection and process messages until closed."""
        if not WEBSOCKETS_AVAILABLE:
            # websockets library not installed — stay in fallback mode
            self._connection_state = OPALConnectionState.FAILED
            self._fallback_active = True
            logger.info(
                "websockets library not installed; OPAL live updates disabled. "
                "Install with: pip install websockets"
            )
            # Park here until stop_event to avoid tight retry loop
            await self._stop_event.wait()
            return

        ws_url = (
            self.opal_server_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        )
        headers = {}
        if self.opal_token:
            headers["Authorization"] = f"Bearer {self.opal_token}"

        self._connection_state = OPALConnectionState.CONNECTING
        logger.debug("OPAL: connecting to %s", ws_url)

        async with websockets.connect(ws_url, extra_headers=headers) as ws:  # type: ignore[attr-defined]
            self._connection_state = OPALConnectionState.CONNECTED
            self._fallback_active = False
            logger.info("OPAL: websocket connected to %s", ws_url)

            async for raw_message in ws:
                if self._stop_event.is_set():
                    break
                await self._handle_ws_message(raw_message)

    async def _handle_ws_message(self, raw_message: str | bytes) -> None:
        """Parse and dispatch an incoming OPAL websocket message."""
        try:
            payload: JSONDict = json.loads(raw_message)
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.debug("OPAL: non-JSON message ignored")
            return

        event_type = payload.get("type", "unknown")
        logger.info("OPAL: received event type=%s", event_type)

        event = PolicyUpdateEvent(
            event_type=str(event_type),
            policy_id=payload.get("policy_id"),
            opal_server_url=self.opal_server_url,
            raw_payload=payload,
        )

        self._last_update_at = event.timestamp
        self._total_updates += 1

        # Invalidate OPA cache so next evaluation fetches fresh policy
        await self._invalidate_opa_cache(event)

        # Forward to audit service
        await self._audit_policy_update(event)

        # Notify any registered listeners
        for queue in self._update_listeners:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    async def _invalidate_opa_cache(self, event: PolicyUpdateEvent) -> None:
        """Invalidate the local OPA client cache after an OPAL push."""
        if self._opa_client and hasattr(self._opa_client, "clear_cache"):
            try:
                await self._opa_client.clear_cache()
                logger.debug("OPA cache invalidated after OPAL event %s", event.event_id)
            except (AttributeError, ConnectionError, TimeoutError, httpx.HTTPError) as exc:
                logger.warning("OPA cache invalidation failed: %s", exc)

    async def _audit_policy_update(self, event: PolicyUpdateEvent) -> None:
        """Log the policy update event to the audit service."""
        event_data: JSONDict = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "policy_id": event.policy_id,
            "constitutional_hash": event.constitutional_hash,
            "timestamp": event.timestamp,
            "opal_server_url": event.opal_server_url,
        }

        if self._audit_client:
            try:
                await self._audit_client.log(
                    event_type="opal_policy_update",
                    data=event_data,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                )
            except (ConnectionError, TimeoutError, httpx.HTTPError, ValueError) as exc:
                logger.warning("Audit log failed for OPAL event: %s", exc)

        logger.info(
            "OPAL_POLICY_EVENT: type=%s policy_id=%s hash=%s",
            event.event_type,
            event.policy_id,
            CONSTITUTIONAL_HASH,
        )

    # ------------------------------------------------------------------
    # Propagation tracking
    # ------------------------------------------------------------------

    async def wait_for_propagation(self, timeout: int | None = None) -> bool:
        """Block until the next policy update event arrives or timeout expires.

        Used for SLA measurement: call immediately before triggering a policy
        push, then await this to confirm propagation.

        Args:
            timeout: Seconds to wait (defaults to ``propagation_timeout``).

        Returns:
            True if an update arrived within the timeout window.
        """
        effective_timeout = timeout if timeout is not None else self.propagation_timeout
        queue: asyncio.Queue[PolicyUpdateEvent] = asyncio.Queue(maxsize=1)
        self._update_listeners.append(queue)
        try:
            await asyncio.wait_for(queue.get(), timeout=float(effective_timeout))
            return True
        except TimeoutError:
            logger.warning("OPAL propagation not confirmed within %ds", effective_timeout)
            return False
        finally:
            self._update_listeners.remove(queue)

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------

    def status(self) -> OPALClientStatus:
        """Return a snapshot of current client state."""
        return OPALClientStatus(
            enabled=self.opal_enabled,
            connection_state=self._connection_state,
            opal_server_url=self.opal_server_url,
            last_update_at=self._last_update_at,
            total_updates_received=self._total_updates,
            fallback_active=self._fallback_active,
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> OPALPolicyClient:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()


__all__ = [
    "OPALClientStatus",
    "OPALConnectionState",
    "OPALPolicyClient",
    "PolicyUpdateEvent",
]
