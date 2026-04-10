"""Intervention actions and rule model.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class InterventionAction(StrEnum):
    BLOCK = "block"  # Raise GovernanceHaltError
    THROTTLE = "throttle"  # Enforce rate limit
    NOTIFY = "notify"  # Fire webhook notification
    ESCALATE = "escalate"  # Set requires_review=True in CDP metadata
    COOL_OFF = "cool_off"  # Time-based lockout (in-memory TTL)
    LOG_ONLY = "log_only"  # No action beyond logging


@dataclass
class InterventionRule:
    """A rule that maps a condition to an intervention action.

    Attributes:
        rule_id: Unique identifier for this rule.
        name: Human-readable name.
        action: The intervention to trigger.
        condition: Dict describing the trigger condition (see conditions.py).
        enabled: Whether this rule is active.
        priority: Lower = checked first.
        metadata: Additional rule context (e.g. threshold values).

    Note:
        Throttle and cool-off state is in-memory and not thread-safe.
        Intended for single-process use only.
    """

    rule_id: str
    name: str
    action: InterventionAction
    condition: dict[str, Any]
    enabled: bool = True
    priority: int = 100
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "action": self.action.value,
            "condition": self.condition,
            "enabled": self.enabled,
            "priority": self.priority,
            "metadata": self.metadata,
        }
