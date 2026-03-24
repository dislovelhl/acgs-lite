"""
Guardrail Models for Runtime Safety.
Constitutional Hash: cdd01ef066bc6cf2
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .enums import GuardrailLayer, SafetyAction, ViolationSeverity


@dataclass
class Violation:
    """A safety violation detected by guardrails."""

    layer: GuardrailLayer
    violation_type: str
    severity: ViolationSeverity
    message: str
    details: JSONDict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    trace_id: str = ""

    def to_dict(self) -> JSONDict:
        return {
            "layer": self.layer.value,
            "violation_type": self.violation_type,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "trace_id": self.trace_id,
        }


@dataclass
class GuardrailResult:
    """Result from a guardrail layer."""

    action: SafetyAction
    allowed: bool
    violations: list[Violation] = field(default_factory=list)
    modified_data: object = None
    metadata: JSONDict = field(default_factory=dict)
    processing_time_ms: float = 0.0
    trace_id: str = ""

    def to_dict(self) -> JSONDict:
        return {
            "action": self.action.value,
            "allowed": self.allowed,
            "violations": [v.to_dict() for v in self.violations],
            "modified_data": self.modified_data,
            "metadata": self.metadata,
            "processing_time_ms": self.processing_time_ms,
            "trace_id": self.trace_id,
        }
