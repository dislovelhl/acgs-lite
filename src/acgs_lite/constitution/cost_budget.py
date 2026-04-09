"""Per-agent and per-role compute cost budgeting for governance.

Tracks cumulative cost usage (tokens, API calls, or arbitrary units) against
configurable budgets with soft-warn and hard-block thresholds.  Budgets can
reset on a fixed cadence (hourly, daily, weekly) and emit structured breach
events for integration with alerting or escalation systems.

Example::

    from acgs_lite.constitution.cost_budget import CostBudgetManager, CostBudget

    manager = CostBudgetManager()
    manager.set_budget(CostBudget(
        budget_id="agent:worker-1",
        soft_limit=8_000,
        hard_limit=10_000,
        reset_period="daily",
    ))

    status = manager.record("agent:worker-1", tokens=500)
    if status.hard_blocked:
        raise RuntimeError("Budget exhausted — action blocked")
    if status.soft_warned:
        print("Approaching budget limit")

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class ResetPeriod(str, Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    NEVER = "never"


class BudgetBreach(str, Enum):
    NONE = "none"
    SOFT = "soft"
    HARD = "hard"


@dataclass
class CostBudget:
    """Budget configuration for a single agent or role.

    Attributes:
        budget_id: Unique identifier (e.g. ``agent:worker-1``, ``role:executor``).
        soft_limit: Usage level that triggers a soft warning (``< hard_limit``).
        hard_limit: Usage level that hard-blocks further actions.
        reset_period: Cadence for resetting usage counters.
        description: Optional human-readable label.
        metadata: Arbitrary key-value metadata.
    """

    budget_id: str
    soft_limit: float
    hard_limit: float
    reset_period: ResetPeriod = ResetPeriod.DAILY
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.soft_limit > self.hard_limit:
            raise ValueError(
                f"soft_limit ({self.soft_limit}) must be ≤ hard_limit ({self.hard_limit})"
            )
        if self.hard_limit <= 0:
            raise ValueError("hard_limit must be positive")
        if isinstance(self.reset_period, str):
            self.reset_period = ResetPeriod(self.reset_period)


@dataclass
class UsageRecord:
    """A single cost recording event.

    Attributes:
        budget_id: The budget this event was recorded against.
        amount: Cost units consumed.
        cumulative: Running total after this event.
        breach: Breach state at time of recording.
        timestamp: UTC ISO-8601 timestamp.
        note: Optional annotation.
    """

    budget_id: str
    amount: float
    cumulative: float
    breach: BudgetBreach
    timestamp: str
    note: str = ""


@dataclass
class RecordStatus:
    """Result returned by :meth:`CostBudgetManager.record`.

    Attributes:
        budget_id: The budget that was charged.
        amount: Units charged in this call.
        cumulative: Running total after this call.
        remaining_soft: Units remaining before soft limit.
        remaining_hard: Units remaining before hard limit.
        soft_warned: True if cumulative ≥ soft_limit.
        hard_blocked: True if cumulative ≥ hard_limit.
        breach: The breach enum value.
    """

    budget_id: str
    amount: float
    cumulative: float
    remaining_soft: float
    remaining_hard: float
    soft_warned: bool
    hard_blocked: bool
    breach: BudgetBreach


class _BudgetState:
    """Mutable runtime state for a single budget (internal use)."""

    __slots__ = (
        "budget",
        "usage",
        "window_start",
        "events",
    )

    def __init__(self, budget: CostBudget) -> None:
        self.budget = budget
        self.usage: float = 0.0
        self.window_start: datetime = datetime.now(timezone.utc)
        self.events: list[UsageRecord] = []

    def _next_reset(self) -> datetime | None:
        period = self.budget.reset_period
        if period == ResetPeriod.NEVER:
            return None
        deltas = {
            ResetPeriod.HOURLY: timedelta(hours=1),
            ResetPeriod.DAILY: timedelta(days=1),
            ResetPeriod.WEEKLY: timedelta(weeks=1),
        }
        return self.window_start + deltas[period]

    def maybe_reset(self, now: datetime) -> bool:
        """Reset usage counter if the reset window has elapsed."""
        next_reset = self._next_reset()
        if next_reset is None or now < next_reset:
            return False
        self.usage = 0.0
        self.window_start = now
        return True

    def charge(self, amount: float, note: str, now: datetime) -> RecordStatus:
        self.maybe_reset(now)
        self.usage += amount
        budget = self.budget

        breach = BudgetBreach.NONE
        if self.usage >= budget.hard_limit:
            breach = BudgetBreach.HARD
        elif self.usage >= budget.soft_limit:
            breach = BudgetBreach.SOFT

        record = UsageRecord(
            budget_id=budget.budget_id,
            amount=amount,
            cumulative=self.usage,
            breach=breach,
            timestamp=now.isoformat(),
            note=note,
        )
        self.events.append(record)

        return RecordStatus(
            budget_id=budget.budget_id,
            amount=amount,
            cumulative=self.usage,
            remaining_soft=max(0.0, budget.soft_limit - self.usage),
            remaining_hard=max(0.0, budget.hard_limit - self.usage),
            soft_warned=self.usage >= budget.soft_limit,
            hard_blocked=self.usage >= budget.hard_limit,
            breach=breach,
        )


class CostBudgetManager:
    """Central manager for agent and role cost budgets.

    Usage flow:

    1. Register budgets with :meth:`set_budget`.
    2. Charge costs with :meth:`record`; inspect the returned :class:`RecordStatus`.
    3. Hard-blocked actions should be refused by the caller.
    4. Query summaries with :meth:`summary` or :meth:`status`.

    Example::

        manager = CostBudgetManager()
        manager.set_budget(CostBudget("agent:a1", soft_limit=900, hard_limit=1000))

        status = manager.record("agent:a1", tokens=100)
        assert not status.hard_blocked
    """

    def __init__(self) -> None:
        self._states: dict[str, _BudgetState] = {}

    def set_budget(self, budget: CostBudget, *, overwrite: bool = True) -> None:
        """Register or replace a budget.

        Args:
            budget: The budget configuration.
            overwrite: Replace existing budget state if True (default).
                If False and the budget_id already exists, raises ValueError.

        Raises:
            ValueError: If ``overwrite=False`` and budget_id already registered.
        """
        if budget.budget_id in self._states and not overwrite:
            raise ValueError(f"Budget '{budget.budget_id}' already registered")
        self._states[budget.budget_id] = _BudgetState(budget)

    def remove_budget(self, budget_id: str) -> None:
        """Remove a budget (and its usage history).

        Raises:
            KeyError: If budget_id not found.
        """
        if budget_id not in self._states:
            raise KeyError(f"Budget '{budget_id}' not found")
        del self._states[budget_id]

    def record(
        self,
        budget_id: str,
        *,
        tokens: float = 0.0,
        note: str = "",
        _now: datetime | None = None,
    ) -> RecordStatus:
        """Charge *tokens* cost units to *budget_id* and return status.

        Args:
            budget_id: The budget to charge.
            tokens: Cost units to add (must be ≥ 0).
            note: Optional annotation stored in the event log.
            _now: Override current time (for testing).

        Raises:
            KeyError: If budget_id not registered.
            ValueError: If tokens < 0.

        Returns:
            :class:`RecordStatus` with soft/hard breach flags.
        """
        if budget_id not in self._states:
            raise KeyError(f"Budget '{budget_id}' not registered")
        if tokens < 0:
            raise ValueError(f"tokens must be ≥ 0, got {tokens}")
        now = _now or datetime.now(timezone.utc)
        return self._states[budget_id].charge(tokens, note, now)

    def status(self, budget_id: str) -> RecordStatus:
        """Return current status for a budget without charging any cost.

        Raises:
            KeyError: If budget_id not registered.
        """
        return self.record(budget_id, tokens=0.0)

    def reset(self, budget_id: str) -> None:
        """Force-reset usage counter for *budget_id*.

        Raises:
            KeyError: If budget_id not registered.
        """
        if budget_id not in self._states:
            raise KeyError(f"Budget '{budget_id}' not found")
        state = self._states[budget_id]
        state.usage = 0.0
        state.window_start = datetime.now(timezone.utc)

    def list_budgets(self) -> list[str]:
        """Return sorted list of registered budget IDs."""
        return sorted(self._states)

    def breached(self) -> list[str]:
        """Return IDs of all budgets currently in hard-block state."""
        return [
            bid for bid, state in self._states.items() if state.usage >= state.budget.hard_limit
        ]

    def soft_warned(self) -> list[str]:
        """Return IDs of all budgets currently in soft-warn state (not hard-blocked)."""
        return [
            bid
            for bid, state in self._states.items()
            if state.budget.soft_limit <= state.usage < state.budget.hard_limit
        ]

    def history(self, budget_id: str) -> list[UsageRecord]:
        """Return usage event history for *budget_id*.

        Raises:
            KeyError: If budget_id not registered.
        """
        if budget_id not in self._states:
            raise KeyError(f"Budget '{budget_id}' not found")
        return list(self._states[budget_id].events)

    def summary(self) -> dict[str, Any]:
        """Return a human-readable summary of all budgets."""
        entries = []
        for bid, state in sorted(self._states.items()):
            b = state.budget
            breach = BudgetBreach.NONE
            if state.usage >= b.hard_limit:
                breach = BudgetBreach.HARD
            elif state.usage >= b.soft_limit:
                breach = BudgetBreach.SOFT
            entries.append(
                {
                    "budget_id": bid,
                    "usage": state.usage,
                    "soft_limit": b.soft_limit,
                    "hard_limit": b.hard_limit,
                    "reset_period": b.reset_period.value,
                    "breach": breach.value,
                    "event_count": len(state.events),
                }
            )
        return {
            "budget_count": len(self._states),
            "hard_blocked_count": len(self.breached()),
            "soft_warned_count": len(self.soft_warned()),
            "budgets": entries,
        }
