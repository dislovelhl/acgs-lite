"""Shared execution model for swarm lifecycle and execution receipts.

This package historically exposed overlapping lifecycle models:
``TaskNode``/``NodeStatus`` for DAG execution and ``TaskContract``/
``ContractStatus`` for delegation receipts. This module defines a single
shared status enum and an immutable receipt type so both APIs speak the same
execution language.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any


class ExecutionStatus(Enum):
    """Canonical execution states shared across swarm internals."""

    BLOCKED = "blocked"
    READY = "ready"
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ContractStatus(Enum):
    """Backward-compatible lifecycle states exposed by receipt APIs."""

    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    EXPIRED = "expired"


_CONTRACT_TO_EXECUTION: dict[ContractStatus, ExecutionStatus] = {
    ContractStatus.PENDING: ExecutionStatus.READY,
    ContractStatus.CLAIMED: ExecutionStatus.CLAIMED,
    ContractStatus.IN_PROGRESS: ExecutionStatus.RUNNING,
    ContractStatus.COMPLETED: ExecutionStatus.COMPLETED,
    ContractStatus.FAILED: ExecutionStatus.FAILED,
    ContractStatus.REJECTED: ExecutionStatus.REJECTED,
    ContractStatus.EXPIRED: ExecutionStatus.EXPIRED,
}

_EXECUTION_TO_CONTRACT: dict[ExecutionStatus, ContractStatus] = {
    ExecutionStatus.BLOCKED: ContractStatus.PENDING,
    ExecutionStatus.READY: ContractStatus.PENDING,
    ExecutionStatus.CLAIMED: ContractStatus.CLAIMED,
    ExecutionStatus.RUNNING: ContractStatus.IN_PROGRESS,
    ExecutionStatus.COMPLETED: ContractStatus.COMPLETED,
    ExecutionStatus.FAILED: ContractStatus.FAILED,
    ExecutionStatus.REJECTED: ContractStatus.REJECTED,
    ExecutionStatus.EXPIRED: ContractStatus.EXPIRED,
}


def contract_status_from_execution(status: ExecutionStatus) -> ContractStatus:
    """Map a canonical execution status to the public receipt status."""
    try:
        return _EXECUTION_TO_CONTRACT[status]
    except KeyError as exc:
        raise ValueError(f"Execution status {status.value} has no receipt mapping") from exc


@dataclass(frozen=True, slots=True)
class WorkReceipt:
    """Immutable view of a unit of work and its latest execution state."""

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    description: str = ""
    domain: str = ""
    required_capabilities: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    max_budget_tokens: int = 0
    deadline_epoch: float = 0.0
    priority: int = 0
    status: ContractStatus = ContractStatus.PENDING
    claimed_by: str | None = None
    claimed_at: float = 0.0
    completed_at: float = 0.0
    result: Any = None
    error: str | None = None
    constitutional_hash: str = ""
    parent_task_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def claim(self, agent_id: str) -> WorkReceipt:
        """Return a claimed copy of this receipt."""
        if self.status != ContractStatus.PENDING:
            raise ValueError(f"Cannot claim receipt in state {self.status.value}")
        return replace(
            self,
            status=ContractStatus.CLAIMED,
            claimed_by=agent_id,
            claimed_at=time.time(),
        )

    def complete(self, result: Any) -> WorkReceipt:
        """Return a completed copy of this receipt."""
        if self.status not in (ContractStatus.CLAIMED, ContractStatus.IN_PROGRESS):
            raise ValueError(f"Cannot complete receipt in state {self.status.value}")
        return replace(
            self,
            status=ContractStatus.COMPLETED,
            completed_at=time.time(),
            result=result,
            error=None,
        )

    def fail(self, error: str) -> WorkReceipt:
        """Return a failed copy of this receipt."""
        return replace(
            self,
            status=ContractStatus.FAILED,
            completed_at=time.time(),
            error=error,
        )

    @property
    def execution_status(self) -> ExecutionStatus:
        """Canonical execution status for shared swarm/receipt reasoning."""
        return _CONTRACT_TO_EXECUTION[self.status]

    @property
    def is_expired(self) -> bool:
        """Check whether the receipt's deadline has elapsed."""
        if self.deadline_epoch <= 0:
            return False
        return time.time() > self.deadline_epoch

    @property
    def is_claimable(self) -> bool:
        """Check whether the receipt is available to be claimed."""
        return self.status == ContractStatus.PENDING and not self.is_expired


# Backward-compatible API names
TaskContract = WorkReceipt
