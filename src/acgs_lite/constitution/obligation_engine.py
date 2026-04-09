"""exp229: ObligationEngine — post-decision obligation tracking with SLA deadlines.

Extends exp132\'s basic Obligation/ObligationSet with a full obligation lifecycle:

1. **Conditional-allow pattern** — A ``Rule`` may allow an action but attach
   obligations (e.g. "access permitted but you must log this within 60 seconds").
   The ``ObligationEngine`` emits these obligations when it detects a rule has
   fired with ``obligation_mode="conditional_allow"``.

2. **SLA-deadline tracking** — Each obligation has a due date derived from
   ``sla_minutes``.  The engine tracks outstanding obligations and exposes
   ``overdue()`` for breach detection.

3. **Fulfillment verification** — Agents call ``fulfill(obligation_id)`` to
   mark an obligation complete.  Fulfilled obligations are immutably recorded.

4. **Breach reporting** — ``breach_report()`` returns all overdue unfulfilled
   obligations with time-overdue information.

5. **Audit trail** — All obligation creation, fulfillment, and breach events are
   logged with wall-clock timestamps.

Design note: ``ObligationEngine`` does NOT modify the hot-path engine.  It is
a post-decision companion that downstream orchestrators call after
``Constitution.explain()`` or ``engine.validate()``.

Usage::

    from acgs_lite.constitution.obligation_engine import ObligationEngine, ObligationSpec

    # Define obligations for specific rules
    specs = {
        "DATA-READ-001": [
            ObligationSpec(
                description="Log PII access to audit trail",
                obligation_type="log_enhanced",
                sla_minutes=1,
            ),
            ObligationSpec(
                description="Notify data steward of PHI access",
                obligation_type="notify",
                sla_minutes=5,
                assignee="data-steward",
            ),
        ],
    }

    engine = ObligationEngine(obligation_specs=specs)

    # After governance allows action with rule DATA-READ-001:
    ids = engine.emit("agent-alpha", "access patient records", triggered_rule_ids=["DATA-READ-001"])
    # ids = ["obl-<uuid1>", "obl-<uuid2>"]

    # Agent fulfills the log obligation:
    engine.fulfill(ids[0], fulfilled_by="agent-alpha")

    # Check for breaches after SLA window:
    report = engine.breach_report()
    if report["overdue_count"] > 0:
        escalate(report)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

# ── obligation lifecycle states ───────────────────────────────────────────────


class ObligationStatus(str, Enum):
    """Lifecycle state of an emitted obligation."""

    PENDING = "pending"
    FULFILLED = "fulfilled"
    BREACHED = "breached"  # overdue + not fulfilled
    WAIVED = "waived"


# ── configuration types ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ObligationSpec:
    """Template for an obligation attached to a specific rule.

    Attributes:
        description: Human-readable description of the required action.
        obligation_type: Category (log_enhanced / notify / human_review / time_bounded).
        sla_minutes: Deadline in minutes from obligation creation (0 = no deadline).
        assignee: Agent or role responsible for fulfillment (optional).
        metadata: Arbitrary key-value data passed through to obligation.
    """

    description: str
    obligation_type: str = "log_enhanced"
    sla_minutes: int = 60
    assignee: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "obligation_type": self.obligation_type,
            "sla_minutes": self.sla_minutes,
            "assignee": self.assignee,
            "metadata": self.metadata,
        }


@dataclass
class ObligationRecord:
    """A single emitted (live) obligation with full lifecycle state.

    Attributes:
        obligation_id: Unique identifier (obl-<uuid>).
        rule_id: Rule that triggered this obligation.
        agent_id: Agent that took the action.
        action: The action string that triggered this.
        spec: The spec template this was created from.
        created_at: UTC creation timestamp.
        due_at: UTC deadline (None if sla_minutes=0).
        status: Current lifecycle status.
        fulfilled_at: UTC fulfillment timestamp (None if not fulfilled).
        fulfilled_by: Identifier of who fulfilled this (None if not fulfilled).
        waive_reason: Reason for waiver (None if not waived).
        audit_events: Ordered list of audit log entries.
    """

    obligation_id: str
    rule_id: str
    agent_id: str
    action: str
    spec: ObligationSpec
    created_at: datetime
    due_at: datetime | None
    status: ObligationStatus = ObligationStatus.PENDING
    fulfilled_at: datetime | None = None
    fulfilled_by: str | None = None
    waive_reason: str | None = None
    audit_events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_overdue(self) -> bool:
        """True when past deadline and not yet fulfilled."""
        if self.status != ObligationStatus.PENDING:
            return False
        if self.due_at is None:
            return False
        return datetime.now(timezone.utc) > self.due_at

    @property
    def minutes_overdue(self) -> float:
        """Minutes past deadline (0.0 if not overdue)."""
        if not self.is_overdue or self.due_at is None:
            return 0.0
        delta = datetime.now(timezone.utc) - self.due_at
        return delta.total_seconds() / 60.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "rule_id": self.rule_id,
            "agent_id": self.agent_id,
            "action": self.action,
            "description": self.spec.description,
            "obligation_type": self.spec.obligation_type,
            "sla_minutes": self.spec.sla_minutes,
            "assignee": self.spec.assignee,
            "created_at": self.created_at.isoformat(),
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "status": self.status.value,
            "fulfilled_at": self.fulfilled_at.isoformat() if self.fulfilled_at else None,
            "fulfilled_by": self.fulfilled_by,
            "waive_reason": self.waive_reason,
            "is_overdue": self.is_overdue,
            "minutes_overdue": round(self.minutes_overdue, 2),
        }

    def _log_event(self, event_type: str, **kwargs: Any) -> None:
        self.audit_events.append(
            {
                "event_type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **kwargs,
            }
        )


# ── engine ────────────────────────────────────────────────────────────────────


class ObligationEngine:
    """Post-decision obligation lifecycle manager.

    Maps rule IDs to :class:`ObligationSpec` templates and manages the full
    lifecycle of emitted obligations (pending → fulfilled | breached | waived).

    Args:
        obligation_specs: Dict of ``{rule_id: [ObligationSpec, ...]}`` mapping
            rules to their associated obligations.

    Example::

        engine = ObligationEngine({
            "DATA-001": [ObligationSpec("Log access", sla_minutes=1)],
        })
        ids = engine.emit("agent-x", "read patient data", ["DATA-001"])
        engine.fulfill(ids[0], fulfilled_by="agent-x")
        report = engine.breach_report()
    """

    def __init__(
        self,
        obligation_specs: dict[str, list[ObligationSpec]] | None = None,
    ) -> None:
        self._specs: dict[str, list[ObligationSpec]] = obligation_specs or {}
        self._obligations: dict[str, ObligationRecord] = {}

    # ── spec management ───────────────────────────────────────────────────

    def register_spec(self, rule_id: str, spec: ObligationSpec) -> None:
        """Add an obligation spec for a rule (appends to existing).

        Args:
            rule_id: Rule to attach the spec to.
            spec: The obligation spec to register.
        """
        if rule_id not in self._specs:
            self._specs[rule_id] = []
        self._specs[rule_id].append(spec)

    def unregister_specs(self, rule_id: str) -> int:
        """Remove all obligation specs for a rule.

        Args:
            rule_id: Rule to deregister.

        Returns:
            Number of specs removed.
        """
        removed = self._specs.pop(rule_id, [])
        return len(removed)

    # ── emission ──────────────────────────────────────────────────────────

    def emit(
        self,
        agent_id: str,
        action: str,
        triggered_rule_ids: list[str],
        *,
        now: datetime | None = None,
    ) -> list[str]:
        """Emit obligations for all triggered rules that have specs.

        Call this after a governance decision to register the resulting
        obligations.  Only rules present in ``obligation_specs`` produce
        obligations.

        Args:
            agent_id: The acting agent.
            action: The action string that was evaluated.
            triggered_rule_ids: Rule IDs that fired in the governance decision.
            now: Override current time (useful in tests).

        Returns:
            List of ``obligation_id`` strings for the emitted obligations.
        """
        ts = now or datetime.now(timezone.utc)
        emitted_ids: list[str] = []

        for rule_id in triggered_rule_ids:
            specs = self._specs.get(rule_id, [])
            for spec in specs:
                obl_id = f"obl-{uuid.uuid4().hex[:12]}"
                due = ts + timedelta(minutes=spec.sla_minutes) if spec.sla_minutes > 0 else None
                record = ObligationRecord(
                    obligation_id=obl_id,
                    rule_id=rule_id,
                    agent_id=agent_id,
                    action=action,
                    spec=spec,
                    created_at=ts,
                    due_at=due,
                )
                record._log_event(
                    "emitted",
                    rule_id=rule_id,
                    agent_id=agent_id,
                    action=action,
                    sla_minutes=spec.sla_minutes,
                )
                self._obligations[obl_id] = record
                emitted_ids.append(obl_id)

        return emitted_ids

    # ── lifecycle operations ───────────────────────────────────────────────

    def fulfill(self, obligation_id: str, *, fulfilled_by: str = "") -> ObligationRecord:
        """Mark an obligation as fulfilled.

        Args:
            obligation_id: The obligation to fulfill.
            fulfilled_by: Identifier of the fulfilling agent/actor.

        Returns:
            Updated :class:`ObligationRecord`.

        Raises:
            KeyError: If obligation_id not found.
            ValueError: If obligation is already fulfilled, waived, or breached.
        """
        record = self._get_record(obligation_id)
        if record.status != ObligationStatus.PENDING:
            raise ValueError(
                f"Cannot fulfill obligation {obligation_id!r} in status {record.status.value!r}"
            )
        record.status = ObligationStatus.FULFILLED
        record.fulfilled_at = datetime.now(timezone.utc)
        record.fulfilled_by = fulfilled_by
        record._log_event("fulfilled", fulfilled_by=fulfilled_by)
        return record

    def waive(self, obligation_id: str, *, reason: str) -> ObligationRecord:
        """Waive an obligation with a documented reason.

        Args:
            obligation_id: The obligation to waive.
            reason: Mandatory justification for waiver.

        Returns:
            Updated :class:`ObligationRecord`.

        Raises:
            KeyError: If obligation_id not found.
            ValueError: If obligation is already fulfilled or waived.
        """
        if not reason:
            raise ValueError("waive() requires a non-empty reason")
        record = self._get_record(obligation_id)
        if record.status not in (ObligationStatus.PENDING, ObligationStatus.BREACHED):
            raise ValueError(
                f"Cannot waive obligation {obligation_id!r} in status {record.status.value!r}"
            )
        record.status = ObligationStatus.WAIVED
        record.waive_reason = reason
        record._log_event("waived", reason=reason)
        return record

    def mark_breached(self, obligation_id: str) -> ObligationRecord:
        """Explicitly mark an overdue obligation as breached.

        The engine does not auto-transition to breached on every query — call
        this method (or rely on ``breach_report()`` to detect them) to update
        the stored status.

        Args:
            obligation_id: The obligation to mark breached.

        Returns:
            Updated :class:`ObligationRecord`.
        """
        record = self._get_record(obligation_id)
        if record.status == ObligationStatus.PENDING and record.is_overdue:
            record.status = ObligationStatus.BREACHED
            record._log_event("breached", minutes_overdue=round(record.minutes_overdue, 2))
        return record

    # ── queries ────────────────────────────────────────────────────────────

    def pending(self) -> list[ObligationRecord]:
        """Return all PENDING (not yet fulfilled) obligations."""
        return [r for r in self._obligations.values() if r.status == ObligationStatus.PENDING]

    def overdue(self) -> list[ObligationRecord]:
        """Return all overdue PENDING obligations (past deadline)."""
        return [r for r in self.pending() if r.is_overdue]

    def fulfilled(self) -> list[ObligationRecord]:
        """Return all FULFILLED obligations."""
        return [r for r in self._obligations.values() if r.status == ObligationStatus.FULFILLED]

    def for_agent(self, agent_id: str) -> list[ObligationRecord]:
        """Return all obligations for a specific agent (any status)."""
        return [r for r in self._obligations.values() if r.agent_id == agent_id]

    def for_rule(self, rule_id: str) -> list[ObligationRecord]:
        """Return all obligations triggered by a specific rule."""
        return [r for r in self._obligations.values() if r.rule_id == rule_id]

    # ── reporting ─────────────────────────────────────────────────────────

    def breach_report(self) -> dict[str, Any]:
        """Return a structured breach report for all overdue obligations.

        Automatically marks overdue pending obligations as BREACHED in storage.

        Returns:
            Dict with overdue_count, total_pending, breach details by agent and rule.
        """
        overdue_records = self.overdue()
        # Persist breached status
        for record in overdue_records:
            self.mark_breached(record.obligation_id)

        by_agent: dict[str, int] = {}
        by_rule: dict[str, int] = {}
        details: list[dict[str, Any]] = []

        for record in overdue_records:
            by_agent[record.agent_id] = by_agent.get(record.agent_id, 0) + 1
            by_rule[record.rule_id] = by_rule.get(record.rule_id, 0) + 1
            details.append(
                {
                    "obligation_id": record.obligation_id,
                    "agent_id": record.agent_id,
                    "rule_id": record.rule_id,
                    "action": record.action,
                    "description": record.spec.description,
                    "minutes_overdue": round(record.minutes_overdue, 2),
                    "due_at": record.due_at.isoformat() if record.due_at else None,
                }
            )

        total = len(self._obligations)
        pending_count = len(self.pending())

        return {
            "overdue_count": len(overdue_records),
            "total_obligations": total,
            "pending_count": pending_count,
            "fulfilled_count": len(self.fulfilled()),
            "by_agent": by_agent,
            "by_rule": by_rule,
            "details": details,
        }

    def summary(self) -> dict[str, Any]:
        """Return aggregate obligation statistics."""
        status_counts: dict[str, int] = {}
        for record in self._obligations.values():
            status_counts[record.status.value] = status_counts.get(record.status.value, 0) + 1

        return {
            "total": len(self._obligations),
            "by_status": status_counts,
            "registered_rule_specs": {
                rule_id: len(specs) for rule_id, specs in self._specs.items()
            },
            "overdue_count": len(self.overdue()),
        }

    # ── helpers ───────────────────────────────────────────────────────────

    def _get_record(self, obligation_id: str) -> ObligationRecord:
        try:
            return self._obligations[obligation_id]
        except KeyError:
            raise KeyError(f"Obligation {obligation_id!r} not found") from None

    def __repr__(self) -> str:
        s = self.summary()
        return (
            f"ObligationEngine(total={s['total']}, "
            f"pending={s['by_status'].get('pending', 0)}, "
            f"overdue={s['overdue_count']}, "
            f"specs_for={list(self._specs.keys())})"
        )
