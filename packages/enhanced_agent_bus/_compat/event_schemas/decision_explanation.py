"""Shim for src.core.shared.event_schemas.decision_explanation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    from src.core.shared.event_schemas.decision_explanation import *  # noqa: F403
except ImportError:

    @dataclass
    class DecisionExplanation:
        decision_id: str = ""
        decision_type: str = ""
        outcome: str = ""
        reasoning: str = ""
        factors: list[dict[str, Any]] = field(default_factory=list)
        confidence: float = 0.0
        timestamp: str = ""
        metadata: dict[str, Any] = field(default_factory=dict)

    @dataclass
    class ExplanationEvent:
        event_id: str = ""
        event_type: str = "decision_explanation"
        explanation: DecisionExplanation | None = None
        source: str = ""
        metadata: dict[str, Any] = field(default_factory=dict)
