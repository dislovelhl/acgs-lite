"""
Agent Health — Healing Actions.
Constitutional Hash: 608508a9bd224290

Implements governed healing actions for the agent health sub-system.

Classes:
    AgentBusGateway    — Protocol defining the minimal bus interface required
    GracefulRestarter  — Drains in-flight messages and restarts the agent process
    QuarantineManager  — Marks agent QUARANTINED and signals bus to re-route
    HITLRequestor      — Posts to the HITL approvals service; deduplicates reviews
    SupervisorNotifier — Notifies supervisor endpoint for Tier 2 (BOUNDED) agents
"""

from __future__ import annotations

import asyncio
import inspect
import os
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

import httpx

from enhanced_agent_bus._compat.types import AgentID
from enhanced_agent_bus.agent_health.models import (
    CONSTITUTIONAL_HASH,
    AgentHealthThresholds,
    AutonomyTier,
    HealingAction,
    HealingTrigger,
    HealthState,
)
from enhanced_agent_bus.agent_health.store import AgentHealthStore
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocol — minimal bus interface required by GracefulRestarter
# ---------------------------------------------------------------------------


@runtime_checkable
class AgentBusGateway(Protocol):
    """Minimal Agent Bus interface required by healing action executors.

    Callers must inject a concrete implementation (or test double) at
    construction time; no module-level singleton is used.

    Constitutional Hash: 608508a9bd224290
    """

    async def drain(self, agent_id: AgentID) -> None:
        """Await until all in-flight messages for *agent_id* are processed.

        Implementations should return as soon as the queue is empty.
        GracefulRestarter will apply its own timeout via asyncio.wait_for,
        so this method should block until naturally drained.
        """
        ...  # pragma: no cover

    async def get_in_flight_messages(self, agent_id: AgentID) -> list[Any]:
        """Return the list of messages currently in-flight for *agent_id*."""
        ...  # pragma: no cover

    async def requeue(self, message: Any, headers: dict[str, str]) -> None:
        """Re-enqueue *message* with the given *headers* onto the bus."""
        ...  # pragma: no cover

    async def reroute_agent(self, agent_id: AgentID) -> None:
        """Signal the bus to re-route all messages destined for *agent_id*.

        Must complete within 500ms (FR-006). The bus stops routing new messages
        to the agent and redirects them to healthy agents or a quarantine queue.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# GracefulRestarter
# ---------------------------------------------------------------------------

_RETRY_HEADER: dict[str, str] = {"X-ACGS-Retry": "true"}


class GracefulRestarter:
    """Governed graceful-restart action for a single agent instance.

    Lifecycle (FR-005):
      1. Write health_state=RESTARTING to the store to stop new message ingestion.
      2. Attempt to drain in-flight messages within *thresholds.drain_timeout_seconds*.
      3. On timeout: retrieve remaining in-flight messages and requeue each one
         onto the bus with the header ``X-ACGS-Retry: true``.
      4. Invoke *restart_callback* (if provided) to trigger the agent process restart.

    All audit log writes and constitutional hash validation are the caller's
    responsibility (handled by the healing engine that constructs this action).

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        store: AgentHealthStore,
        bus: AgentBusGateway,
        restart_callback: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._store = store
        self._bus = bus
        self._restart_callback = restart_callback

    async def execute(
        self,
        agent_id: AgentID,
        thresholds: AgentHealthThresholds,
    ) -> None:
        """Execute the graceful restart for *agent_id*.

        Args:
            agent_id: Unique identifier for the target agent.
            thresholds: Thresholds controlling drain timeout and other parameters.
        """
        # ------------------------------------------------------------------
        # Step 1: Stop new message ingestion — set health_state to RESTARTING.
        # This must happen BEFORE drain begins so the bus can stop routing.
        # ------------------------------------------------------------------
        await self._set_restarting(agent_id)

        # ------------------------------------------------------------------
        # Step 2: Drain in-flight messages with a hard timeout.
        # ------------------------------------------------------------------
        timeout = float(thresholds.drain_timeout_seconds)
        logger.info(
            "GracefulRestarter: drain start",
            agent_id=agent_id,
            drain_timeout_seconds=timeout,
        )

        drained = False
        drain_operation = self._bus.drain(agent_id)
        try:
            await asyncio.wait_for(
                drain_operation,
                timeout=timeout,
            )
            drained = True
            logger.info(
                "GracefulRestarter: drain complete",
                agent_id=agent_id,
            )
        except TimeoutError:
            logger.warning(
                "GracefulRestarter: drain timeout — requeuing remaining messages",
                agent_id=agent_id,
                drain_timeout_seconds=timeout,
            )
        finally:
            if inspect.iscoroutine(drain_operation) and drain_operation.cr_frame is not None:
                drain_operation.close()

        # ------------------------------------------------------------------
        # Step 3 (timeout path only): Requeue remaining in-flight messages.
        # ------------------------------------------------------------------
        if not drained:
            remaining = await self._bus.get_in_flight_messages(agent_id)
            requeue_count = len(remaining)
            for message in remaining:
                await self._bus.requeue(message, headers=dict(_RETRY_HEADER))
            logger.info(
                "GracefulRestarter: requeue complete",
                agent_id=agent_id,
                requeue_count=requeue_count,
            )

        # ------------------------------------------------------------------
        # Step 4: Trigger agent process restart via lifecycle callback.
        # ------------------------------------------------------------------
        if self._restart_callback is not None:
            await self._restart_callback()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _set_restarting(self, agent_id: AgentID) -> None:
        """Update the agent's health record to RESTARTING in the store."""
        record = await self._store.get_health_record(agent_id)
        if record is None:
            logger.warning(
                "GracefulRestarter: no health record found; cannot set RESTARTING",
                agent_id=agent_id,
            )
            return
        record.health_state = HealthState.RESTARTING
        await self._store.upsert_health_record(record)
        logger.info(
            "GracefulRestarter: health_state set to RESTARTING",
            agent_id=agent_id,
        )


# ---------------------------------------------------------------------------
# QuarantineManager
# ---------------------------------------------------------------------------

_QUARANTINE_REROUTE_TIMEOUT: float = 0.5  # FR-006: 500ms budget


class QuarantineManager:
    """Quarantine action: stops the agent from accepting new messages.

    Lifecycle (FR-006):
      1. Write health_state=QUARANTINED to the store.
      2. Signal the Agent Bus to re-route messages away from this agent;
         the reroute call must complete within 500ms.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, bus: AgentBusGateway) -> None:
        self._bus = bus

    async def execute(self, agent_id: AgentID, store: AgentHealthStore) -> None:
        """Set health_state=QUARANTINED and trigger bus re-routing.

        Args:
            agent_id: Unique identifier for the target agent.
            store: AgentHealthStore to persist the QUARANTINED state.
        """
        # Step 1: Write QUARANTINED to the store before signalling the bus.
        record = await store.get_health_record(agent_id)
        if record is None:
            logger.warning(
                "QuarantineManager: no health record found; cannot quarantine",
                agent_id=agent_id,
            )
            return
        record.health_state = HealthState.QUARANTINED
        await store.upsert_health_record(record)
        logger.info(
            "QuarantineManager: health_state set to QUARANTINED",
            agent_id=agent_id,
        )

        # Step 2: Signal bus to re-route within 500ms (FR-006).
        reroute_operation = self._bus.reroute_agent(agent_id)
        try:
            await asyncio.wait_for(
                reroute_operation,
                timeout=_QUARANTINE_REROUTE_TIMEOUT,
            )
            logger.info(
                "QuarantineManager: bus reroute complete",
                agent_id=agent_id,
            )
        except TimeoutError:
            logger.warning(
                "QuarantineManager: bus reroute timed out (>500ms); quarantine persists",
                agent_id=agent_id,
            )
        finally:
            if inspect.iscoroutine(reroute_operation) and reroute_operation.cr_frame is not None:
                reroute_operation.close()


# ---------------------------------------------------------------------------
# HITLRequestor
# ---------------------------------------------------------------------------

_HITL_REVIEWS_PATH = "/api/v1/reviews"
_HITL_DEFAULT_ENV = "HITL_SERVICE_URL"
_HITL_DEFAULT_FALLBACK = "http://localhost:8002"
_HTTP_TIMEOUT = 30.0


class HITLRequestor:
    """Submit or update a HITL review request to the hitl_approvals service.

    Deduplication (spec edge case 2):
      Before creating a new review, the requestor checks for an existing pending
      review for the agent. If one exists, it is updated (PATCH) rather than
      creating a duplicate (POST). Returns the HITL review_id in either case.

    Service URL is read from *hitl_service_url* constructor arg; if None, falls
    back to the ``HITL_SERVICE_URL`` environment variable.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, hitl_service_url: str | None = None) -> None:
        self._base_url = hitl_service_url or os.environ.get(
            _HITL_DEFAULT_ENV, _HITL_DEFAULT_FALLBACK
        )

    async def execute(
        self,
        agent_id: AgentID,
        trigger: HealingTrigger,
        action: HealingAction,
    ) -> str:
        """Submit a HITL review request, updating an existing one if present.

        Args:
            agent_id: Unique identifier for the target agent.
            trigger: The condition that triggered healing.
            action: The HealingAction record (provides action_id, tier, hash).

        Returns:
            The HITL review_id string.
        """
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            existing_id = await self._find_existing_review(client, agent_id)

            if existing_id:
                return await self._update_review(client, existing_id, trigger, action)
            return await self._create_review(client, agent_id, trigger, action)

    async def _find_existing_review(
        self, client: httpx.AsyncClient, agent_id: AgentID
    ) -> str | None:
        """Return the review_id of an existing pending review, or None."""
        response = await client.get(
            f"{self._base_url}{_HITL_REVIEWS_PATH}",
            params={"agent_id": agent_id, "status": "pending"},
        )
        if response.status_code == 200:
            items = response.json().get("items", [])
            if items:
                return str(items[0]["review_id"])
        return None

    async def _create_review(
        self,
        client: httpx.AsyncClient,
        agent_id: AgentID,
        trigger: HealingTrigger,
        action: HealingAction,
    ) -> str:
        """POST a new HITL review and return its review_id."""
        response = await client.post(
            f"{self._base_url}{_HITL_REVIEWS_PATH}",
            json={
                "agent_id": agent_id,
                "trigger": trigger.value,
                "action_id": action.action_id,
                "tier": action.tier_determined_by.value,
                "constitutional_hash": action.constitutional_hash,
            },
        )
        response.raise_for_status()
        review_id = str(response.json()["review_id"])
        logger.info(
            "HITLRequestor: created new review",
            agent_id=agent_id,
            review_id=review_id,
        )
        return review_id

    async def _update_review(
        self,
        client: httpx.AsyncClient,
        review_id: str,
        trigger: HealingTrigger,
        action: HealingAction,
    ) -> str:
        """PATCH an existing HITL review and return its review_id."""
        response = await client.patch(
            f"{self._base_url}{_HITL_REVIEWS_PATH}/{review_id}",
            json={
                "trigger": trigger.value,
                "action_id": action.action_id,
                "constitutional_hash": action.constitutional_hash,
            },
        )
        response.raise_for_status()
        logger.info(
            "HITLRequestor: updated existing review (deduplication)",
            review_id=review_id,
        )
        return review_id


# ---------------------------------------------------------------------------
# SupervisorNotifier
# ---------------------------------------------------------------------------

_SUPERVISOR_NOTIFY_PATH = "/api/v1/supervisor/notifications"
_SUPERVISOR_DEFAULT_ENV = "SUPERVISOR_URL"
_SUPERVISOR_DEFAULT_FALLBACK = "http://localhost:8003"


class SupervisorNotifier:
    """Notify the supervisor endpoint for Tier 2 (BOUNDED) healing events.

    Sends an HTTP POST with agent_id, tier, trigger reason, and the
    constitutional hash. Service URL is read from *supervisor_url* constructor
    arg; if None, falls back to the ``SUPERVISOR_URL`` environment variable.

    The *sla_timeout_seconds* parameter configures the SLA window within which
    supervisor approval is expected (used by callers that await a callback).

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        supervisor_url: str | None = None,
        sla_timeout_seconds: int = 1800,
    ) -> None:
        self._base_url = supervisor_url or os.environ.get(
            _SUPERVISOR_DEFAULT_ENV, _SUPERVISOR_DEFAULT_FALLBACK
        )
        self._sla_timeout_seconds = sla_timeout_seconds

    async def notify(
        self,
        agent_id: AgentID,
        tier: AutonomyTier,
        trigger: HealingTrigger,
    ) -> None:
        """POST a supervisor notification with agent_id, tier, and trigger reason.

        Args:
            agent_id: Unique identifier for the target agent.
            tier: Autonomy tier that determined the supervisor notification.
            trigger: The condition that triggered healing.
        """
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(
                f"{self._base_url}{_SUPERVISOR_NOTIFY_PATH}",
                json={
                    "agent_id": agent_id,
                    "tier": tier.value,
                    "trigger": trigger.value,
                    "sla_timeout_seconds": self._sla_timeout_seconds,
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )
            response.raise_for_status()
            data = response.json()
            notification_id = data.get("notification_id")
            logger.info(
                "SupervisorNotifier: notification sent",
                agent_id=agent_id,
                tier=tier.value,
                trigger=trigger.value,
                notification_id=notification_id,
                sla_timeout_seconds=self._sla_timeout_seconds,
            )


__all__ = [
    "AgentBusGateway",
    "GracefulRestarter",
    "HITLRequestor",
    "QuarantineManager",
    "SupervisorNotifier",
]
