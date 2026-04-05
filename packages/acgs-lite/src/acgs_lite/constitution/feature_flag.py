"""Feature-flag gated rule activation for governance policies.

Allows governance rules to be toggled on/off via feature flags with
percentage-based rollouts, actor-targeting allow/deny lists, kill
switches for emergency deactivation, and flag lifecycle audit trail.

Example::

    from acgs_lite.constitution.feature_flag import (
        GovernanceFeatureFlag, FlagManager, FlagStatus,
    )

    mgr = FlagManager()
    mgr.create_flag("SAFE-001-v2", description="New PII rule v2", rollout_pct=25)
    assert mgr.is_enabled("SAFE-001-v2", actor="agent-a")  # 25% chance

    mgr.set_rollout("SAFE-001-v2", 100)
    assert mgr.is_enabled("SAFE-001-v2", actor="agent-a")  # always on

    mgr.kill("SAFE-001-v2", reason="Regression detected")
    assert not mgr.is_enabled("SAFE-001-v2", actor="agent-a")  # killed
"""

from __future__ import annotations

import enum
import hashlib
import time
from dataclasses import dataclass, field


class FlagStatus(str, enum.Enum):
    ACTIVE = "active"
    KILLED = "killed"
    ARCHIVED = "archived"


@dataclass
class GovernanceFeatureFlag:
    """A feature flag controlling governance rule activation."""

    flag_id: str
    description: str = ""
    status: FlagStatus = FlagStatus.ACTIVE
    rollout_pct: int = 100
    allow_actors: list[str] = field(default_factory=list)
    deny_actors: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    killed_at: float | None = None
    kill_reason: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class FlagChangeEvent:
    """Audit entry for a flag state change."""

    flag_id: str
    change_type: str
    old_value: str
    new_value: str
    actor: str
    timestamp: float


class FlagManager:
    """Manage feature flags for governance rule activation.

    Supports percentage-based rollouts using deterministic hashing,
    actor-level allow/deny targeting, kill switches for emergency
    deactivation, flag archival, and a change audit trail.

    Example::

        mgr = FlagManager()
        mgr.create_flag("new-rule", rollout_pct=50)
        enabled = mgr.is_enabled("new-rule", actor="bot-1")
        mgr.kill("new-rule", reason="Needs fix")
        assert not mgr.is_enabled("new-rule", actor="bot-1")
    """

    def __init__(self) -> None:
        self._flags: dict[str, GovernanceFeatureFlag] = {}
        self._changelog: list[FlagChangeEvent] = []

    def create_flag(
        self,
        flag_id: str,
        description: str = "",
        rollout_pct: int = 100,
        allow_actors: list[str] | None = None,
        deny_actors: list[str] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> GovernanceFeatureFlag:
        flag = GovernanceFeatureFlag(
            flag_id=flag_id,
            description=description,
            rollout_pct=max(0, min(100, rollout_pct)),
            allow_actors=allow_actors or [],
            deny_actors=deny_actors or [],
            metadata=metadata or {},
        )
        self._flags[flag_id] = flag
        self._changelog.append(
            FlagChangeEvent(
                flag_id=flag_id,
                change_type="created",
                old_value="",
                new_value=f"rollout={rollout_pct}%",
                actor="system",
                timestamp=flag.created_at,
            )
        )
        return flag

    def get_flag(self, flag_id: str) -> GovernanceFeatureFlag | None:
        return self._flags.get(flag_id)

    def list_flags(self, status: FlagStatus | None = None) -> list[GovernanceFeatureFlag]:
        if status is None:
            return list(self._flags.values())
        return [f for f in self._flags.values() if f.status == status]

    def is_enabled(self, flag_id: str, actor: str = "default") -> bool:
        """Check whether a flag is enabled for the given actor."""
        flag = self._flags.get(flag_id)
        if flag is None or flag.status != FlagStatus.ACTIVE:
            return False

        if actor in flag.deny_actors:
            return False
        if flag.allow_actors and actor in flag.allow_actors:
            return True
        if flag.allow_actors and actor not in flag.allow_actors:
            return False

        if flag.rollout_pct >= 100:
            return True
        if flag.rollout_pct <= 0:
            return False

        bucket = self._hash_bucket(flag_id, actor)
        return bucket < flag.rollout_pct

    def set_rollout(self, flag_id: str, pct: int, actor: str = "system") -> bool:
        flag = self._flags.get(flag_id)
        if flag is None:
            return False
        old = flag.rollout_pct
        flag.rollout_pct = max(0, min(100, pct))
        flag.updated_at = time.time()
        self._changelog.append(
            FlagChangeEvent(
                flag_id=flag_id,
                change_type="rollout_changed",
                old_value=f"{old}%",
                new_value=f"{flag.rollout_pct}%",
                actor=actor,
                timestamp=flag.updated_at,
            )
        )
        return True

    def add_allow_actor(self, flag_id: str, target: str) -> bool:
        flag = self._flags.get(flag_id)
        if flag is None:
            return False
        if target not in flag.allow_actors:
            flag.allow_actors.append(target)
            flag.updated_at = time.time()
        return True

    def add_deny_actor(self, flag_id: str, target: str) -> bool:
        flag = self._flags.get(flag_id)
        if flag is None:
            return False
        if target not in flag.deny_actors:
            flag.deny_actors.append(target)
            flag.updated_at = time.time()
        return True

    def remove_allow_actor(self, flag_id: str, target: str) -> bool:
        flag = self._flags.get(flag_id)
        if flag is None or target not in flag.allow_actors:
            return False
        flag.allow_actors.remove(target)
        flag.updated_at = time.time()
        return True

    def remove_deny_actor(self, flag_id: str, target: str) -> bool:
        flag = self._flags.get(flag_id)
        if flag is None or target not in flag.deny_actors:
            return False
        flag.deny_actors.remove(target)
        flag.updated_at = time.time()
        return True

    def kill(self, flag_id: str, reason: str = "", actor: str = "system") -> bool:
        """Emergency kill switch — immediately disables the flag."""
        flag = self._flags.get(flag_id)
        if flag is None or flag.status == FlagStatus.KILLED:
            return False
        now = time.time()
        flag.status = FlagStatus.KILLED
        flag.killed_at = now
        flag.kill_reason = reason
        flag.updated_at = now
        self._changelog.append(
            FlagChangeEvent(
                flag_id=flag_id,
                change_type="killed",
                old_value=FlagStatus.ACTIVE.value,
                new_value=FlagStatus.KILLED.value,
                actor=actor,
                timestamp=now,
            )
        )
        return True

    def revive(self, flag_id: str, actor: str = "system") -> bool:
        """Re-activate a killed flag."""
        flag = self._flags.get(flag_id)
        if flag is None or flag.status != FlagStatus.KILLED:
            return False
        now = time.time()
        flag.status = FlagStatus.ACTIVE
        flag.killed_at = None
        flag.kill_reason = ""
        flag.updated_at = now
        self._changelog.append(
            FlagChangeEvent(
                flag_id=flag_id,
                change_type="revived",
                old_value=FlagStatus.KILLED.value,
                new_value=FlagStatus.ACTIVE.value,
                actor=actor,
                timestamp=now,
            )
        )
        return True

    def archive(self, flag_id: str, actor: str = "system") -> bool:
        flag = self._flags.get(flag_id)
        if flag is None or flag.status == FlagStatus.ARCHIVED:
            return False
        now = time.time()
        old_status = flag.status
        flag.status = FlagStatus.ARCHIVED
        flag.updated_at = now
        self._changelog.append(
            FlagChangeEvent(
                flag_id=flag_id,
                change_type="archived",
                old_value=old_status.value,
                new_value=FlagStatus.ARCHIVED.value,
                actor=actor,
                timestamp=now,
            )
        )
        return True

    def changelog(self, flag_id: str | None = None) -> list[FlagChangeEvent]:
        if flag_id is None:
            return list(self._changelog)
        return [e for e in self._changelog if e.flag_id == flag_id]

    def summary(self) -> dict[str, object]:
        by_status: dict[str, int] = {}
        for flag in self._flags.values():
            by_status[flag.status.value] = by_status.get(flag.status.value, 0) + 1
        return {
            "total_flags": len(self._flags),
            "by_status": by_status,
            "total_changes": len(self._changelog),
        }

    @staticmethod
    def _hash_bucket(flag_id: str, actor: str) -> int:
        """Deterministic 0-99 bucket for consistent percentage rollouts."""
        digest = hashlib.md5(f"{flag_id}:{actor}".encode(), usedforsecurity=False).hexdigest()
        return int(digest[:8], 16) % 100
