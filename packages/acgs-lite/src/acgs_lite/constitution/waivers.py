"""exp174: PolicyWaiver + WaiverRegistry — compliance exception ops.

First-class policy exception workflow with expiring waivers, compensating
controls, approver chains, SLA enforcement, and evidence collection for
audit packs.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class WaiverStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    expired = "expired"
    revoked = "revoked"


@dataclass
class PolicyWaiver:
    """Time-bounded exception to a constitutional rule.

    A waiver is created when an action would normally be blocked by a rule
    but a legitimate business need requires a temporary exception. Waivers
    must be approved, have compensating controls, and auto-expire.

    Usage::

        from acgs_lite.constitution.waivers import PolicyWaiver, WaiverRegistry
        from datetime import datetime, timezone, timedelta

        registry = WaiverRegistry()

        waiver = registry.request(
            rule_id="PII-001",
            action_pattern="export pii for audit",
            requester="agent-analytics",
            reason="Quarterly compliance audit requires PII export to external auditor",
            compensating_controls=["data encrypted in transit", "auditor NDA signed"],
            expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        )

        # Approve
        registry.approve(waiver.waiver_id, approver="compliance-officer")

        # Check if a specific action is covered
        result = registry.check(action="export pii for audit", rule_id="PII-001")
        print(result["waived"])  # True

        # Audit evidence pack
        pack = registry.evidence_pack()
    """

    waiver_id: str
    rule_id: str
    action_pattern: str
    requester: str
    reason: str
    compensating_controls: list[str]
    expires_at: str
    created_at: str
    status: WaiverStatus = WaiverStatus.pending
    approver: str = ""
    approved_at: str = ""
    denied_at: str = ""
    denial_reason: str = ""
    revoked_at: str = ""
    revocation_reason: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, at: str | None = None) -> bool:
        ts = at or datetime.now(timezone.utc).isoformat()
        return ts >= self.expires_at

    def is_active(self, at: str | None = None) -> bool:
        return self.status == WaiverStatus.approved and not self.is_expired(at)

    def covers(self, action: str, rule_id: str, at: str | None = None) -> bool:
        pattern_lower = self.action_pattern.lower()
        action_lower = action.lower()
        return (
            self.rule_id == rule_id
            and self.is_active(at)
            and (pattern_lower in action_lower or action_lower in pattern_lower)
        )

    def add_evidence(self, evidence_type: str, description: str, **kwargs: Any) -> None:
        self.evidence.append(
            {
                "evidence_type": evidence_type,
                "description": description,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                **kwargs,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "waiver_id": self.waiver_id,
            "rule_id": self.rule_id,
            "action_pattern": self.action_pattern,
            "requester": self.requester,
            "reason": self.reason,
            "compensating_controls": self.compensating_controls,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "status": self.status.value,
            "approver": self.approver,
            "approved_at": self.approved_at,
            "denied_at": self.denied_at,
            "denial_reason": self.denial_reason,
            "revoked_at": self.revoked_at,
            "revocation_reason": self.revocation_reason,
            "evidence": self.evidence,
            "metadata": self.metadata,
            "is_active": self.is_active(),
            "is_expired": self.is_expired(),
        }


class WaiverRegistry:
    """Registry for managing policy exception waivers.

    Maintains a collection of PolicyWaivers with approval workflow,
    expiry enforcement, and audit evidence generation.

    Usage::

        registry = WaiverRegistry()

        waiver = registry.request(
            rule_id="PII-001",
            action_pattern="export pii for audit",
            requester="agent-analytics",
            reason="Quarterly compliance audit",
            compensating_controls=["encrypted transit", "auditor NDA"],
            expires_at="2026-04-15T00:00:00+00:00",
        )

        registry.approve(waiver.waiver_id, approver="compliance-officer")

        result = registry.check("export pii for audit", rule_id="PII-001")
        # {"waived": True, "waiver_id": "...", "rule_id": "PII-001", ...}
    """

    __slots__ = ("_waivers", "_counter")

    def __init__(self) -> None:
        self._waivers: dict[str, PolicyWaiver] = {}
        self._counter: int = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"WVR-{self._counter:05d}"

    def request(
        self,
        rule_id: str,
        action_pattern: str,
        requester: str,
        reason: str,
        *,
        compensating_controls: list[str] | None = None,
        expires_at: str,
        metadata: dict[str, Any] | None = None,
    ) -> PolicyWaiver:
        """Create a new waiver request in pending status.

        Args:
            rule_id: The rule ID this waiver applies to.
            action_pattern: Action substring that the waiver covers.
            requester: Agent or user requesting the exception.
            reason: Business justification for the exception.
            compensating_controls: List of mitigating measures in place.
            expires_at: ISO-8601 timestamp when waiver auto-expires.
            metadata: Optional additional key-value data.

        Returns:
            The newly created PolicyWaiver in ``pending`` status.
        """
        waiver = PolicyWaiver(
            waiver_id=self._next_id(),
            rule_id=rule_id,
            action_pattern=action_pattern,
            requester=requester,
            reason=reason,
            compensating_controls=list(compensating_controls or []),
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )
        self._waivers[waiver.waiver_id] = waiver
        return waiver

    def approve(self, waiver_id: str, *, approver: str) -> PolicyWaiver:
        """Approve a pending waiver.

        Args:
            waiver_id: The waiver to approve.
            approver: Identifier of the approving authority.

        Returns:
            The updated PolicyWaiver.

        Raises:
            KeyError: If waiver_id is not found.
            ValueError: If waiver is not in pending status.
        """
        waiver = self._get(waiver_id)
        if waiver.status != WaiverStatus.pending:
            msg = f"Cannot approve waiver {waiver_id!r} in status {waiver.status.value!r}"
            raise ValueError(msg)
        waiver.status = WaiverStatus.approved
        waiver.approver = approver
        waiver.approved_at = datetime.now(timezone.utc).isoformat()
        return waiver

    def deny(self, waiver_id: str, *, approver: str, reason: str = "") -> PolicyWaiver:
        """Deny a pending waiver request.

        Args:
            waiver_id: The waiver to deny.
            approver: Identifier of the denying authority.
            reason: Optional reason for denial.

        Returns:
            The updated PolicyWaiver in ``denied`` status.

        Raises:
            KeyError: If waiver_id is not found.
            ValueError: If waiver is not in pending status.
        """
        waiver = self._get(waiver_id)
        if waiver.status != WaiverStatus.pending:
            msg = f"Cannot deny waiver {waiver_id!r} in status {waiver.status.value!r}"
            raise ValueError(msg)
        waiver.status = WaiverStatus.denied
        waiver.approver = approver
        waiver.denied_at = datetime.now(timezone.utc).isoformat()
        waiver.denial_reason = reason
        return waiver

    def revoke(self, waiver_id: str, *, reason: str = "") -> PolicyWaiver:
        """Revoke a previously approved waiver early.

        Args:
            waiver_id: The waiver to revoke.
            reason: Reason for early revocation.

        Returns:
            The updated PolicyWaiver in ``revoked`` status.

        Raises:
            KeyError: If waiver_id is not found.
            ValueError: If waiver is not in approved status.
        """
        waiver = self._get(waiver_id)
        if waiver.status != WaiverStatus.approved:
            msg = f"Cannot revoke waiver {waiver_id!r} in status {waiver.status.value!r}"
            raise ValueError(msg)
        waiver.status = WaiverStatus.revoked
        waiver.revoked_at = datetime.now(timezone.utc).isoformat()
        waiver.revocation_reason = reason
        return waiver

    def check(self, action: str, *, rule_id: str, at: str | None = None) -> dict[str, Any]:
        """Check if a blocked action is covered by an active waiver.

        Args:
            action: The action string being evaluated.
            rule_id: The rule that would block the action.
            at: ISO-8601 timestamp for temporal check (default: now).

        Returns:
            dict with:
                - ``waived``: True if an active waiver covers this action.
                - ``waiver_id``: Matching waiver ID (empty if not waived).
                - ``rule_id``: The checked rule.
                - ``action``: The evaluated action.
                - ``expires_at``: Waiver expiry (empty if not waived).
                - ``compensating_controls``: Controls in place (empty if not waived).
        """
        self._expire_stale()
        for waiver in self._waivers.values():
            if waiver.covers(action, rule_id, at):
                return {
                    "waived": True,
                    "waiver_id": waiver.waiver_id,
                    "rule_id": rule_id,
                    "action": action,
                    "expires_at": waiver.expires_at,
                    "approver": waiver.approver,
                    "compensating_controls": waiver.compensating_controls,
                }
        return {
            "waived": False,
            "waiver_id": "",
            "rule_id": rule_id,
            "action": action,
            "expires_at": "",
            "approver": "",
            "compensating_controls": [],
        }

    def get(self, waiver_id: str) -> PolicyWaiver | None:
        return self._waivers.get(waiver_id)

    def list_active(self, at: str | None = None) -> list[PolicyWaiver]:
        self._expire_stale()
        return [w for w in self._waivers.values() if w.is_active(at)]

    def list_expired(self) -> list[PolicyWaiver]:
        self._expire_stale()
        return [w for w in self._waivers.values() if w.status == WaiverStatus.expired]

    def list_pending(self) -> list[PolicyWaiver]:
        return [w for w in self._waivers.values() if w.status == WaiverStatus.pending]

    def evidence_pack(self, waiver_id: str | None = None) -> dict[str, Any]:
        """Generate an audit evidence pack.

        Args:
            waiver_id: If provided, pack only that waiver. Otherwise all waivers.

        Returns:
            dict with waivers list, summary stats, and generated_at timestamp.
        """
        self._expire_stale()
        waivers = [self._get(waiver_id)] if waiver_id is not None else list(self._waivers.values())

        by_status: dict[str, int] = {}
        for w in waivers:
            by_status[w.status.value] = by_status.get(w.status.value, 0) + 1

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_waivers": len(waivers),
            "by_status": by_status,
            "waivers": [w.to_dict() for w in waivers],
        }

    def summary(self) -> dict[str, Any]:
        self._expire_stale()
        by_status: dict[str, int] = {}
        by_rule: dict[str, int] = {}
        for w in self._waivers.values():
            by_status[w.status.value] = by_status.get(w.status.value, 0) + 1
            by_rule[w.rule_id] = by_rule.get(w.rule_id, 0) + 1
        return {
            "total": len(self._waivers),
            "by_status": by_status,
            "by_rule": by_rule,
            "active_count": sum(1 for w in self._waivers.values() if w.is_active()),
        }

    def _expire_stale(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for waiver in self._waivers.values():
            if waiver.status == WaiverStatus.approved and waiver.is_expired(now):
                waiver.status = WaiverStatus.expired

    def _get(self, waiver_id: str) -> PolicyWaiver:
        try:
            return self._waivers[waiver_id]
        except KeyError:
            raise KeyError(f"Waiver {waiver_id!r} not found") from None

    def __len__(self) -> int:
        return len(self._waivers)

    def __repr__(self) -> str:
        return f"WaiverRegistry({len(self._waivers)} waivers)"
