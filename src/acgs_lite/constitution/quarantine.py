"""exp180: Governance quarantine queue for pending approval actions.

Actions requiring human review enter quarantine with configurable
timeouts and auto-resolution policies. Enables async governance
workflows where agents don't block indefinitely waiting for approval.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any


class QuarantineStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"
    WITHDRAWN = "withdrawn"


class TimeoutPolicy(str, Enum):
    DENY = "deny"
    APPROVE = "approve"
    ESCALATE = "escalate"


class QuarantinedAction:
    """An action held in governance quarantine awaiting review."""

    __slots__ = (
        "quarantine_id",
        "action",
        "action_preview",
        "reason",
        "sphere",
        "risk_score",
        "severity",
        "agent_id",
        "status",
        "submitted_at",
        "timeout_at",
        "timeout_policy",
        "resolved_at",
        "resolved_by",
        "resolution_reason",
        "metadata",
    )

    def __init__(
        self,
        *,
        quarantine_id: str,
        action: str,
        reason: str = "",
        sphere: str = "",
        risk_score: float = 0.0,
        severity: str = "",
        agent_id: str = "",
        timeout_at: str = "",
        timeout_policy: str = "deny",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.quarantine_id = quarantine_id
        self.action = action
        self.action_preview = action[:80]
        self.reason = reason
        self.sphere = sphere
        self.risk_score = risk_score
        self.severity = severity
        self.agent_id = agent_id
        self.status = QuarantineStatus.PENDING
        self.submitted_at = datetime.now(timezone.utc).isoformat()
        self.timeout_at = timeout_at
        self.timeout_policy = TimeoutPolicy(timeout_policy)
        self.resolved_at = ""
        self.resolved_by = ""
        self.resolution_reason = ""
        self.metadata = metadata or {}

    def is_timed_out(self, at: str | None = None) -> bool:
        if not self.timeout_at:
            return False
        ts = at or datetime.now(timezone.utc).isoformat()
        return ts >= self.timeout_at

    def is_pending(self) -> bool:
        return self.status == QuarantineStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "quarantine_id": self.quarantine_id,
            "action_preview": self.action_preview,
            "reason": self.reason,
            "sphere": self.sphere,
            "risk_score": self.risk_score,
            "severity": self.severity,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "submitted_at": self.submitted_at,
            "timeout_at": self.timeout_at,
            "timeout_policy": self.timeout_policy.value,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "resolution_reason": self.resolution_reason,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return (
            f"QuarantinedAction({self.quarantine_id!r}, "
            f"{self.status.value}, agent={self.agent_id!r})"
        )


class GovernanceQuarantine:
    """Queue for actions requiring human review before execution.

    Actions enter quarantine when governance routes them to
    mandatory_approval or escalate. Reviewers approve/deny via
    the registry. Timed-out actions auto-resolve per their
    timeout_policy.

    Args:
        default_timeout_policy: Policy for actions that time out
            without explicit review (deny/approve/escalate).
    """

    __slots__ = ("_items", "_counter", "_history", "_default_timeout_policy")

    def __init__(self, *, default_timeout_policy: str = "deny") -> None:
        self._items: dict[str, QuarantinedAction] = {}
        self._counter = 0
        self._history: list[dict[str, Any]] = []
        self._default_timeout_policy = TimeoutPolicy(default_timeout_policy)

    def _next_id(self) -> str:
        self._counter += 1
        return f"QRN-{self._counter:05d}"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def submit(
        self,
        *,
        action: str,
        reason: str = "",
        sphere: str = "",
        risk_score: float = 0.0,
        severity: str = "",
        agent_id: str = "",
        timeout_at: str = "",
        timeout_policy: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> QuarantinedAction:
        """Submit an action to quarantine for review.

        Returns:
            The QuarantinedAction with a unique quarantine_id.
        """
        policy = timeout_policy or self._default_timeout_policy.value
        item = QuarantinedAction(
            quarantine_id=self._next_id(),
            action=action,
            reason=reason,
            sphere=sphere,
            risk_score=risk_score,
            severity=severity,
            agent_id=agent_id,
            timeout_at=timeout_at,
            timeout_policy=policy,
            metadata=metadata,
        )
        self._items[item.quarantine_id] = item
        self._history.append(
            {
                "event": "submitted",
                "quarantine_id": item.quarantine_id,
                "agent_id": agent_id,
                "timestamp": item.submitted_at,
            }
        )
        return item

    def approve(
        self, quarantine_id: str, *, reviewer_id: str, reason: str = ""
    ) -> QuarantinedAction:
        """Approve a quarantined action."""
        item = self._get_pending(quarantine_id)
        item.status = QuarantineStatus.APPROVED
        item.resolved_at = self._now()
        item.resolved_by = reviewer_id
        item.resolution_reason = reason
        self._history.append(
            {
                "event": "approved",
                "quarantine_id": quarantine_id,
                "reviewer_id": reviewer_id,
                "reason": reason,
                "timestamp": item.resolved_at,
            }
        )
        return item

    def deny(self, quarantine_id: str, *, reviewer_id: str, reason: str = "") -> QuarantinedAction:
        """Deny a quarantined action."""
        item = self._get_pending(quarantine_id)
        item.status = QuarantineStatus.DENIED
        item.resolved_at = self._now()
        item.resolved_by = reviewer_id
        item.resolution_reason = reason
        self._history.append(
            {
                "event": "denied",
                "quarantine_id": quarantine_id,
                "reviewer_id": reviewer_id,
                "reason": reason,
                "timestamp": item.resolved_at,
            }
        )
        return item

    def withdraw(self, quarantine_id: str, *, reason: str = "") -> QuarantinedAction:
        """Withdraw a pending action from quarantine (agent-initiated)."""
        item = self._get_pending(quarantine_id)
        item.status = QuarantineStatus.WITHDRAWN
        item.resolved_at = self._now()
        item.resolved_by = item.agent_id
        item.resolution_reason = reason or "withdrawn by submitter"
        self._history.append(
            {
                "event": "withdrawn",
                "quarantine_id": quarantine_id,
                "timestamp": item.resolved_at,
            }
        )
        return item

    def process_timeouts(self, at: str | None = None) -> list[QuarantinedAction]:
        """Process all timed-out pending actions per their timeout_policy.

        Returns:
            List of actions that were auto-resolved.
        """
        resolved: list[QuarantinedAction] = []
        for item in self._items.values():
            if not item.is_pending() or not item.is_timed_out(at):
                continue

            now = at or self._now()
            item.resolved_at = now
            item.resolved_by = "system:timeout"

            if item.timeout_policy == TimeoutPolicy.APPROVE:
                item.status = QuarantineStatus.APPROVED
                item.resolution_reason = "auto-approved on timeout"
            elif item.timeout_policy == TimeoutPolicy.ESCALATE:
                item.status = QuarantineStatus.TIMED_OUT
                item.resolution_reason = "escalated on timeout"
            else:
                item.status = QuarantineStatus.DENIED
                item.resolution_reason = "auto-denied on timeout"

            self._history.append(
                {
                    "event": "timeout_resolved",
                    "quarantine_id": item.quarantine_id,
                    "policy": item.timeout_policy.value,
                    "status": item.status.value,
                    "timestamp": now,
                }
            )
            resolved.append(item)
        return resolved

    def pending(self) -> list[QuarantinedAction]:
        return [i for i in self._items.values() if i.is_pending()]

    def by_agent(self, agent_id: str) -> list[QuarantinedAction]:
        return [i for i in self._items.values() if i.agent_id == agent_id]

    def by_status(self, status: str) -> list[QuarantinedAction]:
        s = QuarantineStatus(status)
        return [i for i in self._items.values() if i.status == s]

    def summary(self) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        by_agent: dict[str, int] = {}
        for item in self._items.values():
            by_status[item.status.value] = by_status.get(item.status.value, 0) + 1
            if item.agent_id:
                by_agent[item.agent_id] = by_agent.get(item.agent_id, 0) + 1

        pending_count = by_status.get("pending", 0)
        total = len(self._items)
        return {
            "total": total,
            "by_status": by_status,
            "by_agent": by_agent,
            "pending_count": pending_count,
            "approval_rate": round(by_status.get("approved", 0) / total, 4) if total else 0.0,
            "default_timeout_policy": self._default_timeout_policy.value,
            "history_entries": len(self._history),
        }

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def _get_pending(self, quarantine_id: str) -> QuarantinedAction:
        try:
            item = self._items[quarantine_id]
        except KeyError:
            raise KeyError(f"Quarantine item {quarantine_id!r} not found") from None
        if not item.is_pending():
            raise ValueError(f"Item {quarantine_id!r} is already {item.status.value}")
        return item

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        pending = sum(1 for i in self._items.values() if i.is_pending())
        return f"GovernanceQuarantine({len(self._items)} items, {pending} pending)"
