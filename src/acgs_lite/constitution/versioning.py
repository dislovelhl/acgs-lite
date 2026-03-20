"""Constitutional rules — the core of ACGS-Lite.

A Constitution is a set of Rules that govern agent behavior.
Rules can be loaded from YAML, dicts, or created programmatically.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import Rule


@dataclass(frozen=True)
class RuleSnapshot:
    """exp106: Immutable snapshot of a Rule's state at a point in time.

    Stored in ``Constitution.rule_history`` when a rule is updated via
    ``Constitution.update_rule()``. Enables change management dashboards,
    compliance audit trails, and rollback analysis.

    Attributes:
        rule_id: ID of the rule this snapshot belongs to.
        timestamp: Unix timestamp when this version was captured.
        version: Version number (1 = original, 2 = first update, ...).
        text: Rule text at this version.
        severity: Severity level at this version.
        enabled: Whether the rule was enabled at this version.
        keywords: Keywords at this version.
        category: Category at this version.
        subcategory: Subcategory at this version.
        workflow_action: Workflow action at this version.
        change_reason: Optional human-readable reason for this change.
    """

    rule_id: str
    timestamp: float
    version: int
    text: str
    severity: str
    enabled: bool
    keywords: tuple[str, ...]
    category: str
    subcategory: str
    workflow_action: str
    change_reason: str = ""

    @classmethod
    def from_rule(cls, rule: Rule, version: int, change_reason: str = "") -> RuleSnapshot:
        """Create a snapshot from a Rule instance."""
        return cls(
            rule_id=rule.id,
            timestamp=time.time(),
            version=version,
            text=rule.text,
            severity=rule.severity.value,
            enabled=rule.enabled,
            keywords=tuple(rule.keywords),
            category=rule.category,
            subcategory=rule.subcategory,
            workflow_action=rule.workflow_action,
            change_reason=change_reason,
        )

    def to_dict(self) -> dict:
        """Serialise snapshot to a JSON-compatible dict."""
        return {
            "rule_id": self.rule_id,
            "timestamp": self.timestamp,
            "version": self.version,
            "text": self.text,
            "severity": self.severity,
            "enabled": self.enabled,
            "keywords": list(self.keywords),
            "category": self.category,
            "subcategory": self.subcategory,
            "workflow_action": self.workflow_action,
            "change_reason": self.change_reason,
        }
