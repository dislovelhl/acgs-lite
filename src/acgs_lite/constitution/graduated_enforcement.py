"""Graduated enforcement with progressive escalation for governance rules.

Instead of binary allow/block, rules can start in warning mode and escalate
to blocking after repeated violations — configurable per-rule thresholds,
cooldown windows that reset violation counts, manual override to force
enforcement level, and escalation audit trail.

Example::

    from acgs_lite.constitution.graduated_enforcement import (
        GraduatedEnforcer, EnforcementLevel, EscalationPolicy,
    )

    enforcer = GraduatedEnforcer()
    enforcer.set_policy("SAFE-001", EscalationPolicy(
        warn_threshold=0,
        block_threshold=3,
        cooldown_seconds=3600,
    ))

    level = enforcer.evaluate("SAFE-001", actor="agent-a")
    assert level == EnforcementLevel.WARN

    for _ in range(3):
        enforcer.record_violation("SAFE-001", actor="agent-a")

    level = enforcer.evaluate("SAFE-001", actor="agent-a")
    assert level == EnforcementLevel.BLOCK
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass


class EnforcementLevel(enum.IntEnum):
    """Progressive enforcement tiers."""

    ALLOW = 0
    WARN = 1
    THROTTLE = 2
    BLOCK = 3


@dataclass
class EscalationPolicy:
    """Per-rule escalation thresholds and cooldown configuration."""

    warn_threshold: int = 0
    throttle_threshold: int | None = None
    block_threshold: int = 5
    cooldown_seconds: float = 3600.0
    auto_reset: bool = True


@dataclass
class ViolationRecord:
    """Tracks violation state for a (rule, actor) pair."""

    rule_id: str
    actor: str
    count: int = 0
    first_violation_at: float = 0.0
    last_violation_at: float = 0.0
    current_level: EnforcementLevel = EnforcementLevel.ALLOW
    manually_overridden: bool = False


@dataclass
class EscalationEvent:
    """Audit entry for an enforcement level change."""

    rule_id: str
    actor: str
    from_level: EnforcementLevel
    to_level: EnforcementLevel
    violation_count: int
    timestamp: float
    reason: str = ""


class GraduatedEnforcer:
    """Progressive enforcement engine with per-rule escalation policies.

    Tracks violations per (rule_id, actor) pair, applies cooldown windows
    that optionally reset counts, supports manual level overrides, and
    maintains an escalation audit trail.

    Example::

        ge = GraduatedEnforcer()
        ge.set_policy("R1", EscalationPolicy(warn_threshold=0, block_threshold=3))
        ge.record_violation("R1", actor="bot-1")
        ge.record_violation("R1", actor="bot-1")
        ge.record_violation("R1", actor="bot-1")
        assert ge.evaluate("R1", actor="bot-1") == EnforcementLevel.BLOCK
    """

    def __init__(self) -> None:
        self._policies: dict[str, EscalationPolicy] = {}
        self._violations: dict[tuple[str, str], ViolationRecord] = {}
        self._escalation_log: list[EscalationEvent] = []

    def set_policy(self, rule_id: str, policy: EscalationPolicy) -> None:
        self._policies[rule_id] = policy

    def remove_policy(self, rule_id: str) -> bool:
        return self._policies.pop(rule_id, None) is not None

    def get_policy(self, rule_id: str) -> EscalationPolicy | None:
        return self._policies.get(rule_id)

    def record_violation(
        self,
        rule_id: str,
        actor: str = "default",
        now: float | None = None,
    ) -> ViolationRecord:
        """Record a violation and potentially escalate enforcement level."""
        current = now if now is not None else time.time()
        key = (rule_id, actor)
        record = self._violations.get(key)

        if record is None:
            record = ViolationRecord(
                rule_id=rule_id,
                actor=actor,
                first_violation_at=current,
            )
            self._violations[key] = record

        policy = self._policies.get(rule_id)
        if policy and policy.auto_reset and record.last_violation_at > 0:
            elapsed = current - record.last_violation_at
            if elapsed > policy.cooldown_seconds:
                record.count = 0
                record.first_violation_at = current
                if not record.manually_overridden:
                    record.current_level = EnforcementLevel.ALLOW

        record.count += 1
        record.last_violation_at = current

        if not record.manually_overridden and policy:
            new_level = self._compute_level(record.count, policy)
            if new_level != record.current_level:
                self._escalation_log.append(
                    EscalationEvent(
                        rule_id=rule_id,
                        actor=actor,
                        from_level=record.current_level,
                        to_level=new_level,
                        violation_count=record.count,
                        timestamp=current,
                        reason="threshold_crossed",
                    )
                )
                record.current_level = new_level

        return record

    def evaluate(
        self,
        rule_id: str,
        actor: str = "default",
        now: float | None = None,
    ) -> EnforcementLevel:
        """Return the current enforcement level for a (rule, actor) pair."""
        current = now if now is not None else time.time()
        key = (rule_id, actor)
        record = self._violations.get(key)

        if record is None:
            policy = self._policies.get(rule_id)
            if policy and policy.warn_threshold == 0:
                return EnforcementLevel.WARN
            return EnforcementLevel.ALLOW

        if record.manually_overridden:
            return record.current_level

        policy = self._policies.get(rule_id)
        if policy and policy.auto_reset and record.last_violation_at > 0:
            elapsed = current - record.last_violation_at
            if elapsed > policy.cooldown_seconds:
                record.count = 0
                record.current_level = EnforcementLevel.ALLOW
                record.first_violation_at = 0.0
                if policy.warn_threshold == 0:
                    return EnforcementLevel.WARN
                return EnforcementLevel.ALLOW

        return record.current_level

    def override_level(
        self,
        rule_id: str,
        actor: str,
        level: EnforcementLevel,
        reason: str = "manual_override",
    ) -> bool:
        """Manually set enforcement level, bypassing threshold logic."""
        key = (rule_id, actor)
        record = self._violations.get(key)
        if record is None:
            record = ViolationRecord(rule_id=rule_id, actor=actor)
            self._violations[key] = record

        old_level = record.current_level
        record.current_level = level
        record.manually_overridden = True
        self._escalation_log.append(
            EscalationEvent(
                rule_id=rule_id,
                actor=actor,
                from_level=old_level,
                to_level=level,
                violation_count=record.count,
                timestamp=time.time(),
                reason=reason,
            )
        )
        return True

    def clear_override(self, rule_id: str, actor: str) -> bool:
        """Remove manual override, reverting to threshold-based logic."""
        key = (rule_id, actor)
        record = self._violations.get(key)
        if record is None or not record.manually_overridden:
            return False
        record.manually_overridden = False
        policy = self._policies.get(rule_id)
        if policy:
            record.current_level = self._compute_level(record.count, policy)
        return True

    def reset_violations(self, rule_id: str, actor: str) -> bool:
        """Reset violation count and enforcement level for a (rule, actor) pair."""
        key = (rule_id, actor)
        record = self._violations.get(key)
        if record is None:
            return False
        record.count = 0
        record.manually_overridden = False
        record.current_level = EnforcementLevel.ALLOW
        record.first_violation_at = 0.0
        record.last_violation_at = 0.0
        return True

    def get_record(self, rule_id: str, actor: str) -> ViolationRecord | None:
        return self._violations.get((rule_id, actor))

    def escalation_log(self, rule_id: str | None = None) -> list[EscalationEvent]:
        if rule_id is None:
            return list(self._escalation_log)
        return [e for e in self._escalation_log if e.rule_id == rule_id]

    def summary(self) -> dict[str, object]:
        """Dashboard summary of enforcement state."""
        by_level: dict[str, int] = {}
        for record in self._violations.values():
            key = record.current_level.name
            by_level[key] = by_level.get(key, 0) + 1
        return {
            "total_tracked_pairs": len(self._violations),
            "policies_configured": len(self._policies),
            "by_level": by_level,
            "total_escalation_events": len(self._escalation_log),
        }

    @staticmethod
    def _compute_level(count: int, policy: EscalationPolicy) -> EnforcementLevel:
        if count >= policy.block_threshold:
            return EnforcementLevel.BLOCK
        if policy.throttle_threshold is not None and count >= policy.throttle_threshold:
            return EnforcementLevel.THROTTLE
        if count >= policy.warn_threshold:
            return EnforcementLevel.WARN
        return EnforcementLevel.ALLOW
