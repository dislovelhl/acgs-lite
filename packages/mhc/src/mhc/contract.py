"""Task Contracts — fire-and-forget delegation with acceptance criteria.

Orchestrators publish contracts. Agents claim and execute independently.
The governance bus validates results against contracts. No polling, no check-ins.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ContractStatus(Enum):
    """Lifecycle states of a task contract."""

    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class TaskContract:
    """A contract defining a unit of work with acceptance criteria.

    Contracts enable fire-and-forget delegation:
    1. Publisher creates contract with scope + constraints + criteria
    2. Agent claims contract
    3. Agent works independently (no check-ins)
    4. Agent submits result
    5. Result validated against acceptance criteria + constitution
    """

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

    def claim(self, agent_id: str) -> TaskContract:
        """Claim this contract for execution. Returns new contract."""
        if self.status != ContractStatus.PENDING:
            raise ValueError(f"Cannot claim contract in state {self.status.value}")
        return TaskContract(
            task_id=self.task_id,
            title=self.title,
            description=self.description,
            domain=self.domain,
            required_capabilities=self.required_capabilities,
            acceptance_criteria=self.acceptance_criteria,
            constraints=self.constraints,
            max_budget_tokens=self.max_budget_tokens,
            deadline_epoch=self.deadline_epoch,
            priority=self.priority,
            status=ContractStatus.CLAIMED,
            claimed_by=agent_id,
            claimed_at=time.time(),
            constitutional_hash=self.constitutional_hash,
            parent_task_id=self.parent_task_id,
            metadata=dict(self.metadata),
        )

    def complete(self, result: Any) -> TaskContract:
        """Mark contract as completed with result. Returns new contract."""
        if self.status not in (ContractStatus.CLAIMED, ContractStatus.IN_PROGRESS):
            raise ValueError(f"Cannot complete contract in state {self.status.value}")
        return TaskContract(
            task_id=self.task_id,
            title=self.title,
            description=self.description,
            domain=self.domain,
            required_capabilities=self.required_capabilities,
            acceptance_criteria=self.acceptance_criteria,
            constraints=self.constraints,
            max_budget_tokens=self.max_budget_tokens,
            deadline_epoch=self.deadline_epoch,
            priority=self.priority,
            status=ContractStatus.COMPLETED,
            claimed_by=self.claimed_by,
            claimed_at=self.claimed_at,
            completed_at=time.time(),
            result=result,
            constitutional_hash=self.constitutional_hash,
            parent_task_id=self.parent_task_id,
            metadata=dict(self.metadata),
        )

    def fail(self, error: str) -> TaskContract:
        """Mark contract as failed. Returns new contract."""
        return TaskContract(
            task_id=self.task_id,
            title=self.title,
            description=self.description,
            domain=self.domain,
            required_capabilities=self.required_capabilities,
            acceptance_criteria=self.acceptance_criteria,
            constraints=self.constraints,
            max_budget_tokens=self.max_budget_tokens,
            deadline_epoch=self.deadline_epoch,
            priority=self.priority,
            status=ContractStatus.FAILED,
            claimed_by=self.claimed_by,
            claimed_at=self.claimed_at,
            completed_at=time.time(),
            error=error,
            constitutional_hash=self.constitutional_hash,
            parent_task_id=self.parent_task_id,
            metadata=dict(self.metadata),
        )

    @property
    def is_expired(self) -> bool:
        """Check if the contract has passed its deadline."""
        if self.deadline_epoch <= 0:
            return False
        return time.time() > self.deadline_epoch

    @property
    def is_claimable(self) -> bool:
        """Check if the contract can be claimed."""
        return self.status == ContractStatus.PENDING and not self.is_expired
