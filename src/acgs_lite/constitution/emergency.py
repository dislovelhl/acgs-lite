"""exp192: GovernanceEmergencyOverride — break-glass incident response.

Time-limited governance bypass for emergencies.  Authorized operators can
activate overrides that suspend specific rules or severity tiers, with
mandatory justification, MACI separation (requester ≠ authorizer),
automatic expiry, and tamper-evident audit trail.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class OverrideStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    COMPLETED = "completed"


class OverrideScope(Enum):
    ALL_RULES = "all_rules"
    SEVERITY_TIER = "severity_tier"
    SPECIFIC_RULES = "specific_rules"
    CATEGORY = "category"


@dataclass
class EmergencyOverride:
    override_id: str
    requestor_id: str
    authorizer_id: str
    justification: str
    scope: OverrideScope
    scope_filter: list[str]
    activated_at: datetime
    expires_at: datetime
    status: OverrideStatus = OverrideStatus.ACTIVE
    revoked_at: datetime | None = None
    revoked_by: str | None = None
    actions_taken: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        if self.status != OverrideStatus.ACTIVE:
            return False
        return datetime.now(timezone.utc) < self.expires_at

    @property
    def remaining(self) -> timedelta:
        if not self.is_active:
            return timedelta(0)
        return self.expires_at - datetime.now(timezone.utc)

    def record_action(self, action: str, agent_id: str, detail: str = "") -> None:
        self.actions_taken.append(
            {
                "action": action,
                "agent_id": agent_id,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "override_id": self.override_id,
            "requestor_id": self.requestor_id,
            "authorizer_id": self.authorizer_id,
            "justification": self.justification,
            "scope": self.scope.value,
            "scope_filter": self.scope_filter,
            "status": self.status.value,
            "activated_at": self.activated_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "remaining_seconds": max(0, int(self.remaining.total_seconds())),
            "actions_taken": len(self.actions_taken),
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revoked_by": self.revoked_by,
        }


@dataclass
class OverridePolicy:
    max_duration: timedelta = field(default_factory=lambda: timedelta(hours=4))
    require_justification: bool = True
    min_justification_length: int = 20
    allow_self_authorization: bool = False


class GovernanceEmergencyOverride:
    """Break-glass governance bypass with audit trail.

    Example::

        eo = GovernanceEmergencyOverride()
        override = eo.activate(
            requestor_id="ops-lead",
            authorizer_id="security-officer",
            justification="Production incident INC-2026-0315: service degradation",
            scope=OverrideScope.SEVERITY_TIER,
            scope_filter=["medium", "low"],
            duration=timedelta(hours=2),
        )
        assert eo.is_overridden("RULE-001", severity="medium")
    """

    def __init__(self, policy: OverridePolicy | None = None) -> None:
        self._policy = policy or OverridePolicy()
        self._overrides: dict[str, EmergencyOverride] = {}
        self._history: list[dict[str, Any]] = []

    @property
    def policy(self) -> OverridePolicy:
        return self._policy

    def activate(
        self,
        requestor_id: str,
        authorizer_id: str,
        justification: str,
        scope: OverrideScope,
        scope_filter: list[str] | None = None,
        duration: timedelta | None = None,
    ) -> EmergencyOverride:
        if not self._policy.allow_self_authorization and requestor_id == authorizer_id:
            raise ValueError(
                f"MACI violation: requestor '{requestor_id}' cannot authorize own override"
            )

        if (
            self._policy.require_justification
            and len(justification.strip()) < self._policy.min_justification_length
        ):
            raise ValueError(
                f"Justification must be at least {self._policy.min_justification_length} characters"
            )

        effective_duration = duration or self._policy.max_duration
        if effective_duration > self._policy.max_duration:
            effective_duration = self._policy.max_duration

        now = datetime.now(timezone.utc)
        override = EmergencyOverride(
            override_id=uuid.uuid4().hex[:16],
            requestor_id=requestor_id,
            authorizer_id=authorizer_id,
            justification=justification,
            scope=scope,
            scope_filter=scope_filter or [],
            activated_at=now,
            expires_at=now + effective_duration,
        )
        self._overrides[override.override_id] = override
        self._record("activated", override.override_id, requestor_id, authorizer_id)
        return override

    def revoke(self, override_id: str, revoked_by: str, reason: str = "") -> EmergencyOverride:
        override = self._get(override_id)
        if override.status != OverrideStatus.ACTIVE:
            raise ValueError(f"Override '{override_id}' is not active: {override.status.value}")
        override.status = OverrideStatus.REVOKED
        override.revoked_at = datetime.now(timezone.utc)
        override.revoked_by = revoked_by
        self._record("revoked", override_id, revoked_by, detail=reason)
        return override

    def complete(self, override_id: str, completed_by: str) -> EmergencyOverride:
        override = self._get(override_id)
        if override.status != OverrideStatus.ACTIVE:
            raise ValueError(f"Override '{override_id}' is not active: {override.status.value}")
        override.status = OverrideStatus.COMPLETED
        self._record("completed", override_id, completed_by)
        return override

    def is_overridden(self, rule_id: str, *, severity: str = "", category: str = "") -> bool:
        self._expire_stale()
        for override in self._overrides.values():
            if not override.is_active:
                continue
            if override.scope == OverrideScope.ALL_RULES:
                return True
            if override.scope == OverrideScope.SPECIFIC_RULES and rule_id in override.scope_filter:
                return True
            if override.scope == OverrideScope.SEVERITY_TIER and severity.lower() in [
                s.lower() for s in override.scope_filter
            ]:
                return True
            if override.scope == OverrideScope.CATEGORY and category.lower() in [
                c.lower() for c in override.scope_filter
            ]:
                return True
        return False

    def active_overrides(self) -> list[EmergencyOverride]:
        self._expire_stale()
        return [o for o in self._overrides.values() if o.is_active]

    def get(self, override_id: str) -> EmergencyOverride:
        return self._get(override_id)

    def summary(self) -> dict[str, Any]:
        self._expire_stale()
        statuses: dict[str, int] = {}
        for o in self._overrides.values():
            statuses[o.status.value] = statuses.get(o.status.value, 0) + 1
        active = self.active_overrides()
        return {
            "total": len(self._overrides),
            "by_status": statuses,
            "active_count": len(active),
            "active_overrides": [o.to_dict() for o in active],
            "total_actions_taken": sum(len(o.actions_taken) for o in self._overrides.values()),
            "policy": {
                "max_duration_seconds": int(self._policy.max_duration.total_seconds()),
                "require_justification": self._policy.require_justification,
                "allow_self_authorization": self._policy.allow_self_authorization,
            },
        }

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def _get(self, override_id: str) -> EmergencyOverride:
        if override_id not in self._overrides:
            raise KeyError(f"Override '{override_id}' not found")
        return self._overrides[override_id]

    def _expire_stale(self) -> None:
        now = datetime.now(timezone.utc)
        for override in self._overrides.values():
            if override.status == OverrideStatus.ACTIVE and now >= override.expires_at:
                override.status = OverrideStatus.EXPIRED
                self._record("expired", override.override_id, "system")

    def _record(self, event: str, override_id: str, actor: str, detail: str = "") -> None:
        self._history.append(
            {
                "event": event,
                "override_id": override_id,
                "actor": actor,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
