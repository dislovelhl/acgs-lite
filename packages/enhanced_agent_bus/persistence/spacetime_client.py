"""
ACGS-2 Persistence - SpacetimeDB Real-Time Governance Client
Constitutional Hash: 608508a9bd224290

Real-time governance state synchronization via SpacetimeDB.
Agents subscribe to governance state changes and receive updates
pushed automatically when decisions, principles, or role bindings change.

Key Features:
- Real-time push of governance decisions to subscribed agents
- MACI role enforcement at the database level via reducers
- Automatic state sync — no polling needed
- Tenant-isolated subscriptions
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

try:
    from spacetimedb_sdk import Identity, SpacetimeDBClient

    HAS_SPACETIMEDB = True
except ImportError:
    HAS_SPACETIMEDB = False
    SpacetimeDBClient = None  # type: ignore[assignment, misc]
    Identity = None  # type: ignore[assignment, misc]


class GovernanceEventType(str, Enum):
    """Types of governance state change events."""

    DECISION_CREATED = "decision_created"
    DECISION_VALIDATED = "decision_validated"
    PRINCIPLE_AMENDED = "principle_amended"
    PRINCIPLE_CREATED = "principle_created"
    ROLE_BINDING_CHANGED = "role_binding_changed"


@dataclass
class GovernanceEvent:
    """A governance state change event from SpacetimeDB."""

    event_type: GovernanceEventType
    table_name: str
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    timestamp: float = field(default_factory=time.monotonic)
    constitutional_hash: str = CONSTITUTIONAL_HASH


EventCallback = Callable[[GovernanceEvent], None]


@dataclass
class SpacetimeConfig:
    """Configuration for SpacetimeDB connection."""

    host: str = "http://localhost:3000"
    module_name: str = "acgs_governance"
    token: str | None = None
    auto_reconnect: bool = True
    reconnect_interval_s: float = 5.0
    constitutional_hash: str = CONSTITUTIONAL_HASH


class GovernanceStateClient:
    """Real-time governance state client via SpacetimeDB subscriptions.

    Connects to a SpacetimeDB instance running the ACGS governance module.
    Subscribes to governance tables and pushes state changes to registered
    callbacks in real-time.

    Usage:
        client = GovernanceStateClient(SpacetimeConfig(
            host="http://localhost:3000",
            module_name="acgs_governance",
        ))

        client.on(GovernanceEventType.DECISION_VALIDATED, handle_validation)
        await client.connect()

        # Propose an action (must have "proposer" role)
        await client.propose_action(
            tenant_id="tenant-1",
            action_hash="abc123",
            reasoning="This action complies with principle 1",
            principle_ids=[1, 2],
        )

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: SpacetimeConfig | None = None) -> None:
        if not HAS_SPACETIMEDB:
            raise RuntimeError(
                "spacetimedb-sdk is not installed. Install with: pip install spacetimedb-sdk"
            )
        self._config = config or SpacetimeConfig()
        self._client: SpacetimeDBClient | None = None
        self._identity: Identity | None = None
        self._connected = False
        self._callbacks: dict[GovernanceEventType, list[EventCallback]] = {}
        self._stats = {
            "events_received": 0,
            "reducer_calls": 0,
            "reconnections": 0,
            "errors": 0,
        }

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def identity(self) -> Identity | None:
        return self._identity

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def on(self, event_type: GovernanceEventType, callback: EventCallback) -> None:
        """Register a callback for a governance event type.

        Args:
            event_type: The event type to listen for.
            callback: Function called with GovernanceEvent when event occurs.
        """
        self._callbacks.setdefault(event_type, []).append(callback)

    def off(self, event_type: GovernanceEventType, callback: EventCallback) -> None:
        """Remove a callback for a governance event type."""
        callbacks = self._callbacks.get(event_type, [])
        if callback in callbacks:
            callbacks.remove(callback)

    async def connect(self) -> None:
        """Connect to SpacetimeDB and subscribe to governance tables."""
        self._client = SpacetimeDBClient(
            self._config.host,
            self._config.module_name,
        )

        self._client.on_connect(self._on_connect)
        self._client.on_disconnect(self._on_disconnect)
        self._client.on_error(self._on_error)

        # Register table update handlers
        self._client.on_row_update("governance_decision", self._on_decision_update)
        self._client.on_row_update("constitutional_principle", self._on_principle_update)
        self._client.on_row_update("maci_role_binding", self._on_role_update)

        await self._client.connect(self._config.token)
        logger.info(
            "spacetimedb_connecting", host=self._config.host, module=self._config.module_name
        )

    async def disconnect(self) -> None:
        """Disconnect from SpacetimeDB."""
        if self._client:
            await self._client.disconnect()
        self._connected = False
        logger.info("spacetimedb_disconnected")

    async def propose_action(
        self,
        tenant_id: str,
        action_hash: str,
        reasoning: str,
        principle_ids: list[int],
    ) -> None:
        """Submit a governance action proposal via SpacetimeDB reducer.

        Requires the connected identity to have "proposer" MACI role.
        """
        self._ensure_connected()
        await self._client.call_reducer(
            "propose_action",
            tenant_id,
            action_hash,
            reasoning,
            principle_ids,
        )
        self._stats["reducer_calls"] += 1
        logger.info("action_proposed", tenant_id=tenant_id, action_hash=action_hash)

    async def validate_decision(
        self,
        decision_id: int,
        verdict: str,
        reasoning: str,
    ) -> None:
        """Validate a governance decision via SpacetimeDB reducer.

        Requires the connected identity to have "validator" MACI role.
        MACI invariant: cannot validate own proposals.

        Args:
            decision_id: ID of the decision to validate.
            verdict: One of "approved", "denied", "escalated".
            reasoning: Explanation for the verdict.
        """
        self._ensure_connected()
        await self._client.call_reducer(
            "validate_decision",
            decision_id,
            verdict,
            reasoning,
        )
        self._stats["reducer_calls"] += 1
        logger.info("decision_validated", decision_id=decision_id, verdict=verdict)

    async def register_agent(
        self,
        agent_identity: Identity,
        role: str,
        tenant_id: str,
    ) -> None:
        """Register an agent with a MACI role.

        Args:
            agent_identity: The agent's SpacetimeDB identity.
            role: One of "proposer", "validator", "executor".
            tenant_id: The tenant this role applies to.
        """
        self._ensure_connected()
        await self._client.call_reducer(
            "register_agent",
            agent_identity,
            role,
            tenant_id,
        )
        self._stats["reducer_calls"] += 1
        logger.info("agent_registered", role=role, tenant_id=tenant_id)

    # --- Internal handlers ---

    def _on_connect(self, identity: Identity) -> None:
        self._identity = identity
        self._connected = True
        logger.info("spacetimedb_connected", identity=str(identity))

        # Subscribe to all governance tables
        self._client.subscribe(
            [
                "SELECT * FROM governance_decision",
                "SELECT * FROM constitutional_principle",
                "SELECT * FROM maci_role_binding",
            ]
        )

    def _on_disconnect(self) -> None:
        self._connected = False
        logger.warning("spacetimedb_disconnected_unexpectedly")
        if self._config.auto_reconnect:
            self._stats["reconnections"] += 1

    def _on_error(self, error: Exception) -> None:
        self._stats["errors"] += 1
        logger.error("spacetimedb_error", error=type(error).__name__)

    def _on_decision_update(self, old: Any, new: Any) -> None:
        self._stats["events_received"] += 1

        if old is None and new is not None:
            event_type = GovernanceEventType.DECISION_CREATED
        else:
            event_type = GovernanceEventType.DECISION_VALIDATED

        event = GovernanceEvent(
            event_type=event_type,
            table_name="governance_decision",
            old_value=self._row_to_dict(old),
            new_value=self._row_to_dict(new),
        )
        self._dispatch(event)

    def _on_principle_update(self, old: Any, new: Any) -> None:
        self._stats["events_received"] += 1

        if old is None:
            event_type = GovernanceEventType.PRINCIPLE_CREATED
        else:
            event_type = GovernanceEventType.PRINCIPLE_AMENDED

        event = GovernanceEvent(
            event_type=event_type,
            table_name="constitutional_principle",
            old_value=self._row_to_dict(old),
            new_value=self._row_to_dict(new),
        )
        self._dispatch(event)

    def _on_role_update(self, old: Any, new: Any) -> None:
        self._stats["events_received"] += 1
        event = GovernanceEvent(
            event_type=GovernanceEventType.ROLE_BINDING_CHANGED,
            table_name="maci_role_binding",
            old_value=self._row_to_dict(old),
            new_value=self._row_to_dict(new),
        )
        self._dispatch(event)

    def _dispatch(self, event: GovernanceEvent) -> None:
        for callback in self._callbacks.get(event.event_type, []):
            try:
                callback(event)
            except Exception:
                logger.exception(
                    "governance_event_callback_error", event_type=event.event_type.value
                )

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        if hasattr(row, "__dict__"):
            return {k: v for k, v in row.__dict__.items() if not k.startswith("_")}
        return {"raw": str(row)}

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("Not connected to SpacetimeDB. Call await connect() first.")
