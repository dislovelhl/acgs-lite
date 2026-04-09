"""exp189: GovernanceEscrow — held decisions pending multi-party approval.

Actions requiring high-stakes governance review are placed in escrow until
a configurable number of independent approvers sign off.  Supports N-of-M
approval thresholds, timeout policies (auto-deny / auto-escalate on expiry),
MACI-enforced separation (requestor ≠ approver), and full audit trail.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class EscrowStatus(Enum):
    HELD = "held"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ESCALATED = "escalated"


class TimeoutAction(Enum):
    DENY = "deny"
    ESCALATE = "escalate"
    APPROVE = "approve"


@dataclass
class EscrowApproval:
    """Single approval or rejection from an approver."""

    approver_id: str
    decision: str  # "approve" | "reject"
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EscrowedAction:
    """An action held in escrow pending multi-party approval."""

    escrow_id: str
    action: str
    context: dict[str, Any]
    requestor_id: str
    required_approvals: int
    created_at: datetime
    timeout: timedelta
    timeout_action: TimeoutAction
    status: EscrowStatus = EscrowStatus.HELD
    approvals: list[EscrowApproval] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    resolved_at: datetime | None = None

    @property
    def approval_count(self) -> int:
        return sum(1 for a in self.approvals if a.decision == "approve")

    @property
    def rejection_count(self) -> int:
        return sum(1 for a in self.approvals if a.decision == "reject")

    @property
    def expires_at(self) -> datetime:
        return self.created_at + self.timeout

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at and self.status == EscrowStatus.HELD

    def to_dict(self) -> dict[str, Any]:
        return {
            "escrow_id": self.escrow_id,
            "action": self.action,
            "context": self.context,
            "requestor_id": self.requestor_id,
            "required_approvals": self.required_approvals,
            "status": self.status.value,
            "approval_count": self.approval_count,
            "rejection_count": self.rejection_count,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "approvals": [
                {
                    "approver_id": a.approver_id,
                    "decision": a.decision,
                    "reason": a.reason,
                    "timestamp": a.timestamp.isoformat(),
                }
                for a in self.approvals
            ],
            "metadata": self.metadata,
        }


@dataclass
class EscrowPolicy:
    """Configuration for escrow behavior."""

    required_approvals: int = 2
    timeout: timedelta = field(default_factory=lambda: timedelta(hours=24))
    timeout_action: TimeoutAction = TimeoutAction.DENY
    rejection_threshold: int = 1
    allow_self_approval: bool = False  # MACI: requestor ≠ approver


class GovernanceEscrow:
    """Multi-party approval escrow for high-stakes governance decisions.

    Actions are held until a configurable N-of-M approvers sign off.
    Expired escrows are resolved according to timeout policy.

    Example::

        escrow = GovernanceEscrow(EscrowPolicy(required_approvals=2))
        item = escrow.hold("deploy to prod", {"env": "production"}, "agent-1")
        escrow.approve(item.escrow_id, "reviewer-1", "Looks safe")
        escrow.approve(item.escrow_id, "reviewer-2", "LGTM")
        assert item.status == EscrowStatus.APPROVED
    """

    def __init__(self, policy: EscrowPolicy | None = None) -> None:
        self._policy = policy or EscrowPolicy()
        self._items: dict[str, EscrowedAction] = {}
        self._history: list[dict[str, Any]] = []

    @property
    def policy(self) -> EscrowPolicy:
        return self._policy

    def hold(
        self,
        action: str,
        context: dict[str, Any],
        requestor_id: str,
        *,
        metadata: dict[str, Any] | None = None,
        required_approvals: int | None = None,
        timeout: timedelta | None = None,
        timeout_action: TimeoutAction | None = None,
    ) -> EscrowedAction:
        """Place an action in escrow pending approval."""
        item = EscrowedAction(
            escrow_id=uuid.uuid4().hex[:16],
            action=action,
            context=context,
            requestor_id=requestor_id,
            required_approvals=required_approvals or self._policy.required_approvals,
            created_at=datetime.now(timezone.utc),
            timeout=timeout or self._policy.timeout,
            timeout_action=timeout_action or self._policy.timeout_action,
            metadata=metadata or {},
        )
        self._items[item.escrow_id] = item
        self._record("hold", item.escrow_id, requestor_id)
        return item

    def approve(self, escrow_id: str, approver_id: str, reason: str = "") -> EscrowedAction:
        """Record an approval. Auto-releases if threshold met."""
        item = self._get_held(escrow_id)
        self._check_expired(item)

        if not self._policy.allow_self_approval and approver_id == item.requestor_id:
            raise ValueError(f"MACI violation: requestor '{approver_id}' cannot approve own escrow")
        if any(a.approver_id == approver_id for a in item.approvals):
            raise ValueError(f"Approver '{approver_id}' already voted on escrow '{escrow_id}'")

        item.approvals.append(EscrowApproval(approver_id, "approve", reason))
        self._record("approve", escrow_id, approver_id)

        if item.approval_count >= item.required_approvals:
            item.status = EscrowStatus.APPROVED
            item.resolved_at = datetime.now(timezone.utc)
            self._record("released", escrow_id, approver_id)

        return item

    def reject(self, escrow_id: str, approver_id: str, reason: str = "") -> EscrowedAction:
        """Record a rejection. Auto-rejects if rejection threshold met."""
        item = self._get_held(escrow_id)
        self._check_expired(item)

        if any(a.approver_id == approver_id for a in item.approvals):
            raise ValueError(f"Approver '{approver_id}' already voted on escrow '{escrow_id}'")

        item.approvals.append(EscrowApproval(approver_id, "reject", reason))
        self._record("reject", escrow_id, approver_id)

        if item.rejection_count >= self._policy.rejection_threshold:
            item.status = EscrowStatus.REJECTED
            item.resolved_at = datetime.now(timezone.utc)
            self._record("rejected", escrow_id, approver_id)

        return item

    def resolve_expired(self) -> list[EscrowedAction]:
        """Resolve all expired escrows per timeout policy."""
        resolved: list[EscrowedAction] = []
        now = datetime.now(timezone.utc)
        for item in list(self._items.values()):
            if item.status != EscrowStatus.HELD:
                continue
            if now <= item.expires_at:
                continue
            if item.timeout_action == TimeoutAction.DENY:
                item.status = EscrowStatus.EXPIRED
            elif item.timeout_action == TimeoutAction.ESCALATE:
                item.status = EscrowStatus.ESCALATED
            elif item.timeout_action == TimeoutAction.APPROVE:
                item.status = EscrowStatus.APPROVED
            item.resolved_at = now
            self._record("timeout_resolved", item.escrow_id, "system", item.timeout_action.value)
            resolved.append(item)
        return resolved

    def get(self, escrow_id: str) -> EscrowedAction:
        """Retrieve an escrowed action by ID."""
        if escrow_id not in self._items:
            raise KeyError(f"Escrow '{escrow_id}' not found")
        return self._items[escrow_id]

    def held(self) -> list[EscrowedAction]:
        """Return all currently held (unresolved) escrows."""
        return [i for i in self._items.values() if i.status == EscrowStatus.HELD]

    def by_requestor(self, requestor_id: str) -> list[EscrowedAction]:
        """Return all escrows filed by a given requestor."""
        return [i for i in self._items.values() if i.requestor_id == requestor_id]

    def summary(self) -> dict[str, Any]:
        """Aggregate escrow statistics."""
        statuses: dict[str, int] = {}
        for item in self._items.values():
            statuses[item.status.value] = statuses.get(item.status.value, 0) + 1
        return {
            "total": len(self._items),
            "by_status": statuses,
            "policy": {
                "required_approvals": self._policy.required_approvals,
                "timeout_seconds": int(self._policy.timeout.total_seconds()),
                "timeout_action": self._policy.timeout_action.value,
                "rejection_threshold": self._policy.rejection_threshold,
                "allow_self_approval": self._policy.allow_self_approval,
            },
        }

    def history(self) -> list[dict[str, Any]]:
        """Return full audit trail of escrow operations."""
        return list(self._history)

    def _get_held(self, escrow_id: str) -> EscrowedAction:
        if escrow_id not in self._items:
            raise KeyError(f"Escrow '{escrow_id}' not found")
        item = self._items[escrow_id]
        if item.status != EscrowStatus.HELD:
            raise ValueError(f"Escrow '{escrow_id}' already resolved as {item.status.value}")
        return item

    def _check_expired(self, item: EscrowedAction) -> None:
        if item.is_expired:
            self.resolve_expired()
            raise ValueError(f"Escrow '{item.escrow_id}' has expired")

    def _record(self, event: str, escrow_id: str, actor: str, detail: str = "") -> None:
        self._history.append(
            {
                "event": event,
                "escrow_id": escrow_id,
                "actor": actor,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
