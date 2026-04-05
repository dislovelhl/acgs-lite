"""Shared engine result models and helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .decision_record import GovernanceDecisionRecord
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from acgs_lite.constitution import Severity


class Violation(NamedTuple):
    """A single rule violation (NamedTuple for C-speed construction)."""

    rule_id: str
    rule_text: str
    severity: Severity
    matched_content: str
    category: str


@dataclass(slots=True)
class ValidationResult:
    """Result of validating an action against the constitution."""

    valid: bool
    constitutional_hash: str
    violations: list[Violation] = field(default_factory=list)
    rules_checked: int = 0
    latency_ms: float = 0.0
    request_id: str = ""
    timestamp: str = ""
    action: str = ""
    agent_id: str = ""

    @property
    def blocking_violations(self) -> list[Violation]:
        """Violations that block execution."""
        return [v for v in self.violations if v.severity.blocks()]

    @property
    def warnings(self) -> list[Violation]:
        """Non-blocking violations (warnings)."""
        return [v for v in self.violations if not v.severity.blocks()]

    def to_decision_record(self) -> GovernanceDecisionRecord:
        """Convert to canonical :class:`GovernanceDecisionRecord`."""
        from .decision_record import GovernanceDecisionRecord, TriggeredRule

        triggered = [
            TriggeredRule(
                id=v.rule_id, text=v.rule_text, severity=v.severity.value, category=v.category
            )
            for v in self.violations
        ]
        violations_dicts = [
            {
                "rule_id": v.rule_id,
                "rule_text": v.rule_text,
                "severity": v.severity.value,
                "matched_content": v.matched_content,
                "category": v.category,
            }
            for v in self.violations
        ]
        return GovernanceDecisionRecord(
            decision="deny" if not self.valid else "allow",
            triggered_rules=triggered,
            violations=violations_dicts,
            confidence=1.0,
            model_id="deterministic",
            latency_ms=self.latency_ms,
            constitutional_hash=self.constitutional_hash,
            audit_entry_id=self.request_id,
            action=self.action,
            agent_id=self.agent_id,
            rules_checked=self.rules_checked,
            timestamp=self.timestamp,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "valid": self.valid,
            "constitutional_hash": self.constitutional_hash,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "rule_text": v.rule_text,
                    "severity": v.severity.value,
                    "matched_content": v.matched_content,
                    "category": v.category,
                }
                for v in self.violations
            ],
            "rules_checked": self.rules_checked,
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
            "action": self.action,
            "agent_id": self.agent_id,
        }


def _dedup_violations(violations: list) -> list:
    """Deduplicate violations by rule_id (called only when len > 1)."""
    seen: set[str] = set()
    result = []
    for v in violations:
        if v.rule_id not in seen:
            seen.add(v.rule_id)
            result.append(v)
    return result


CustomValidator = Callable[[str, dict[str, Any]], list[Violation]]


__all__ = [
    "CustomValidator",
    "Severity",
    "ValidationResult",
    "Violation",
    "_dedup_violations",
]
