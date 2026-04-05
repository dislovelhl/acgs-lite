"""
HealingEngine — constitutional tier-based healing orchestrator.
Constitutional Hash: 608508a9bd224290

Governs all healing decisions for agent instances:
  - Validates CONSTITUTIONAL_HASH before any audit write (FR-009)
  - Checks active HealingOverride before tier routing
  - Routes by AutonomyTier: ADVISORY, BOUNDED, HUMAN_APPROVED
  - Writes audit log entry BEFORE dispatching any action
  - Emits acgs_agent_healing_actions_total Prometheus counter
  - Persists completed HealingAction to store
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from enhanced_agent_bus.agent_health.actions import (
    GracefulRestarter,
    HITLRequestor,
    QuarantineManager,
    SupervisorNotifier,
)
from enhanced_agent_bus.agent_health.metrics import HEALING_ACTIONS_COUNTER
from enhanced_agent_bus.agent_health.models import (
    CONSTITUTIONAL_HASH,
    AgentHealthRecord,
    AgentHealthThresholds,
    AutonomyTier,
    HealingAction,
    HealingActionType,
    HealingTrigger,
    OverrideMode,
)
from enhanced_agent_bus.agent_health.store import AgentHealthStore

try:
    from enhanced_agent_bus._compat.types import AgentID
except ImportError:
    AgentID = str  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

# Type alias for the BOUNDED-tier approval waiter.
# Returns True when supervisor approves; raises asyncio.TimeoutError or returns False on SLA breach.
BoundedApprovalAwaiter = Callable[[AgentID], Awaitable[bool]]


def _validate_constitutional_hash() -> None:
    """Raise RuntimeError if the module-local CONSTITUTIONAL_HASH diverges from shared constants."""
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH as _CANONICAL_HASH

    if CONSTITUTIONAL_HASH != _CANONICAL_HASH:
        raise RuntimeError(
            f"Constitutional hash validation failed: expected '{_CANONICAL_HASH}', "
            f"got '{CONSTITUTIONAL_HASH}'"
        )


class HealingEngine:
    """Orchestrates governed healing decisions based on an agent's AutonomyTier.

    All audit log writes happen BEFORE any action is dispatched (FR-009).
    Operator overrides bypass tier routing entirely.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        store: AgentHealthStore,
        audit_log_client: Any,
        restarter: GracefulRestarter,
        quarantine_manager: QuarantineManager,
        hitl_requestor: HITLRequestor,
        supervisor_notifier: SupervisorNotifier,
        thresholds: AgentHealthThresholds,
        bounded_approval_awaiter: BoundedApprovalAwaiter | None = None,
    ) -> None:
        self._store = store
        self._audit = audit_log_client
        self._restarter = restarter
        self._quarantine_manager = quarantine_manager
        self._hitl_requestor = hitl_requestor
        self._supervisor_notifier = supervisor_notifier
        self._thresholds = thresholds
        self._bounded_approval_awaiter = bounded_approval_awaiter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def handle(
        self,
        agent_id: AgentID,
        trigger: HealingTrigger,
        record: AgentHealthRecord,
    ) -> HealingAction | None:
        """Evaluate health state and dispatch the appropriate governed healing action.

        Writes an audit log entry BEFORE executing any action.

        Args:
            agent_id: Unique identifier for the target agent.
            trigger: Condition that triggered healing (failure loop / memory / manual).
            record:  Current health snapshot for the agent.

        Returns:
            Completed HealingAction record, or None if healing was suppressed.

        Raises:
            RuntimeError: If CONSTITUTIONAL_HASH does not match the expected value.
        """
        _validate_constitutional_hash()

        audit_event_id = str(uuid.uuid4())

        # Check for an active operator override first.
        override = await self._store.get_override(agent_id)
        if override is not None:
            return await self._handle_override(agent_id, trigger, record, override, audit_event_id)

        return await self._route_by_tier(agent_id, trigger, record, audit_event_id)

    # ------------------------------------------------------------------
    # Internal: override handling
    # ------------------------------------------------------------------

    async def _handle_override(
        self,
        agent_id: AgentID,
        trigger: HealingTrigger,
        record: AgentHealthRecord,
        override: Any,
        audit_event_id: str,
    ) -> HealingAction | None:
        if override.mode == OverrideMode.SUPPRESS_HEALING:
            await self._write_audit(
                agent_id=agent_id,
                trigger=trigger,
                tier=record.autonomy_tier,
                action_type="SUPPRESSED",
                audit_event_id=audit_event_id,
                extra={"suppressed_by_override": True, "override_mode": "SUPPRESS_HEALING"},
            )
            logger.info(
                "Healing suppressed by operator override",
                agent_id=agent_id,
                override_id=override.override_id,
            )
            return None

        if override.mode == OverrideMode.FORCE_RESTART:
            action_type = HealingActionType.GRACEFUL_RESTART
            await self._write_audit(
                agent_id=agent_id,
                trigger=trigger,
                tier=record.autonomy_tier,
                action_type=action_type.value,
                audit_event_id=audit_event_id,
                extra={"override_mode": "FORCE_RESTART"},
            )
            await self._restarter.execute(agent_id, self._thresholds)

        else:  # FORCE_QUARANTINE
            action_type = HealingActionType.QUARANTINE
            await self._write_audit(
                agent_id=agent_id,
                trigger=trigger,
                tier=record.autonomy_tier,
                action_type=action_type.value,
                audit_event_id=audit_event_id,
                extra={"override_mode": "FORCE_QUARANTINE"},
            )
            await self._quarantine_manager.execute(agent_id, self._store)

        return await self._complete(
            agent_id, trigger, record.autonomy_tier, action_type, audit_event_id
        )

    # ------------------------------------------------------------------
    # Internal: tier routing
    # ------------------------------------------------------------------

    async def _route_by_tier(
        self,
        agent_id: AgentID,
        trigger: HealingTrigger,
        record: AgentHealthRecord,
        audit_event_id: str,
    ) -> HealingAction:
        tier = record.autonomy_tier

        if tier == AutonomyTier.HUMAN_APPROVED:
            return await self._handle_human_approved(agent_id, trigger, record, audit_event_id)

        if tier == AutonomyTier.BOUNDED:
            return await self._handle_bounded(agent_id, trigger, record, audit_event_id)

        # Default: ADVISORY
        return await self._handle_advisory(agent_id, trigger, record, audit_event_id)

    async def _handle_human_approved(
        self,
        agent_id: AgentID,
        trigger: HealingTrigger,
        record: AgentHealthRecord,
        audit_event_id: str,
    ) -> HealingAction:
        """Tier 3: autonomous graceful restart — no HITL or supervisor required."""
        action_type = HealingActionType.GRACEFUL_RESTART
        await self._write_audit(
            agent_id=agent_id,
            trigger=trigger,
            tier=AutonomyTier.HUMAN_APPROVED,
            action_type=action_type.value,
            audit_event_id=audit_event_id,
        )
        await self._restarter.execute(agent_id, self._thresholds)
        return await self._complete(
            agent_id, trigger, AutonomyTier.HUMAN_APPROVED, action_type, audit_event_id
        )

    async def _handle_bounded(
        self,
        agent_id: AgentID,
        trigger: HealingTrigger,
        record: AgentHealthRecord,
        audit_event_id: str,
    ) -> HealingAction:
        """Tier 2: notify supervisor; proceed with restart on approval; escalate to ADVISORY on timeout."""
        # Write audit BEFORE sending the supervisor notification.
        await self._write_audit(
            agent_id=agent_id,
            trigger=trigger,
            tier=AutonomyTier.BOUNDED,
            action_type=HealingActionType.SUPERVISOR_NOTIFY.value,
            audit_event_id=audit_event_id,
        )
        await self._supervisor_notifier.notify(agent_id, AutonomyTier.BOUNDED, trigger)

        approved = await self._await_bounded_approval(agent_id)

        if approved:
            await self._restarter.execute(agent_id, self._thresholds)
            return await self._complete(
                agent_id,
                trigger,
                AutonomyTier.BOUNDED,
                HealingActionType.GRACEFUL_RESTART,
                audit_event_id,
            )

        # SLA timeout or no awaiter → escalate to ADVISORY behavior (spec edge case 6).
        logger.warning(
            "BOUNDED: supervisor approval SLA elapsed — escalating to ADVISORY",
            agent_id=agent_id,
        )
        await self._quarantine_manager.execute(agent_id, self._store)
        await self._hitl_requestor.execute(
            agent_id,
            trigger,
            self._pending_action(
                agent_id,
                trigger,
                AutonomyTier.BOUNDED,
                HealingActionType.HITL_REQUEST,
                audit_event_id,
            ),
        )
        return await self._complete(
            agent_id, trigger, AutonomyTier.BOUNDED, HealingActionType.HITL_REQUEST, audit_event_id
        )

    async def _handle_advisory(
        self,
        agent_id: AgentID,
        trigger: HealingTrigger,
        record: AgentHealthRecord,
        audit_event_id: str,
    ) -> HealingAction:
        """Tier 1: quarantine agent then create HITL review request."""
        action_type = HealingActionType.HITL_REQUEST
        await self._write_audit(
            agent_id=agent_id,
            trigger=trigger,
            tier=AutonomyTier.ADVISORY,
            action_type=action_type.value,
            audit_event_id=audit_event_id,
        )
        pending = self._pending_action(
            agent_id, trigger, AutonomyTier.ADVISORY, action_type, audit_event_id
        )
        await self._quarantine_manager.execute(agent_id, self._store)
        await self._hitl_requestor.execute(agent_id, trigger, pending)
        return await self._complete(
            agent_id, trigger, AutonomyTier.ADVISORY, action_type, audit_event_id
        )

    # ------------------------------------------------------------------
    # Internal: helpers
    # ------------------------------------------------------------------

    async def _await_bounded_approval(self, agent_id: AgentID) -> bool:
        """Await supervisor approval for a BOUNDED agent. Returns False on timeout or if no awaiter."""
        if self._bounded_approval_awaiter is None:
            return False
        try:
            return await self._bounded_approval_awaiter(agent_id)
        except TimeoutError:
            return False

    def _pending_action(
        self,
        agent_id: AgentID,
        trigger: HealingTrigger,
        tier: AutonomyTier,
        action_type: HealingActionType,
        audit_event_id: str,
    ) -> HealingAction:
        """Create an in-progress HealingAction (no completed_at) for passing to executors."""
        return HealingAction(
            agent_id=agent_id,
            trigger=trigger,
            action_type=action_type,
            tier_determined_by=tier,
            initiated_at=datetime.now(UTC),
            audit_event_id=audit_event_id,
        )

    async def _complete(
        self,
        agent_id: AgentID,
        trigger: HealingTrigger,
        tier: AutonomyTier,
        action_type: HealingActionType,
        audit_event_id: str,
    ) -> HealingAction:
        """Create the completed HealingAction, emit metrics, and persist to store."""
        action = HealingAction(
            agent_id=agent_id,
            trigger=trigger,
            action_type=action_type,
            tier_determined_by=tier,
            initiated_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            audit_event_id=audit_event_id,
        )

        HEALING_ACTIONS_COUNTER.labels(
            agent_id=agent_id,
            autonomy_tier=tier.value,
            action_type=action_type.value,
            trigger=trigger.value,
        ).inc()

        await self._store.save_healing_action(action)

        logger.info(
            "HealingEngine: action complete",
            agent_id=agent_id,
            action_type=action_type.value,
            tier=tier.value,
            trigger=trigger.value,
            audit_event_id=audit_event_id,
        )
        return action

    async def _write_audit(
        self,
        agent_id: AgentID,
        trigger: HealingTrigger,
        tier: AutonomyTier,
        action_type: str,
        audit_event_id: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Write a governance audit log entry via the injected audit_log_client."""
        from enhanced_agent_bus._compat.audit.logger import AuditEventType, AuditSeverity

        action_payload: dict[str, Any] = {
            "type": "HEALING_ACTION",
            "action_type": action_type,
            "trigger": trigger.value,
            "audit_event_id": audit_event_id,
        }
        if extra:
            action_payload.update(extra)

        await self._audit.log(
            event_type=AuditEventType.APPROVAL,
            severity=AuditSeverity.WARNING,
            actor={"type": "system", "component": "HealingEngine"},
            resource={"agent_id": agent_id, "autonomy_tier": tier.value},
            action=action_payload,
            result={"status": "initiated", "constitutional_hash": CONSTITUTIONAL_HASH},
        )


__all__ = ["BoundedApprovalAwaiter", "HealingEngine"]
