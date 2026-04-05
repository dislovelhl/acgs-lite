"""LLM-as-Judge protocol and adapters for governance decision evaluation.

Provides:
- ``LLMGovernanceJudge`` Protocol for pluggable LLM judges
- ``LLMJudgment`` result dataclass
- ``InMemoryLLMJudge`` stub for tests
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class JudgmentScore:
    """Per-dimension score from an LLM judge evaluation."""

    accuracy: float = 0.0  # Did the engine get the decision right?
    proportionality: float = 0.0  # Was the severity appropriate?
    reasoning_quality: float = 0.0  # Was the reasoning clear and complete?
    missed_violations: list[str] = field(
        default_factory=list
    )  # Rule IDs the judge thinks should have fired
    false_positives: list[str] = field(default_factory=list)  # Rule IDs that fired unnecessarily


@dataclass(slots=True)
class LLMJudgment:
    """Result of an LLM judge evaluating a governance decision."""

    decision: str  # "allow" | "deny" — the judge's independent verdict
    confidence: float  # 0.0 to 1.0
    violations: list[dict[str, Any]] = field(default_factory=list)
    reasoning: str = ""
    scores: JudgmentScore = field(default_factory=JudgmentScore)
    model_id: str = ""
    latency_ms: float = 0.0


@runtime_checkable
class LLMGovernanceJudge(Protocol):
    """Protocol for LLM-based governance evaluation.

    Implementations must accept an action string, context dict, and
    constitution object and return an ``LLMJudgment``.
    """

    async def evaluate(
        self,
        action: str,
        context: dict[str, Any],
        constitution: Any,
    ) -> LLMJudgment: ...


class InMemoryLLMJudge:
    """Deterministic test stub that records calls and returns configurable judgments.

    Default behavior: always agrees with the deterministic engine (returns allow
    with full confidence).  Override ``default_judgment`` or ``judgment_map`` for
    custom behavior.
    """

    def __init__(
        self,
        *,
        default_judgment: LLMJudgment | None = None,
        judgment_map: dict[str, LLMJudgment] | None = None,
    ) -> None:
        self.default_judgment = default_judgment or LLMJudgment(
            decision="allow",
            confidence=1.0,
            reasoning="InMemoryLLMJudge: default allow",
            model_id="in-memory-stub",
        )
        self.judgment_map: dict[str, LLMJudgment] = judgment_map or {}
        self.calls: list[dict[str, Any]] = []

    async def evaluate(
        self,
        action: str,
        context: dict[str, Any],
        constitution: Any,
    ) -> LLMJudgment:
        self.calls.append({"action": action, "context": context})
        return self.judgment_map.get(action, self.default_judgment)


__all__ = [
    "InMemoryLLMJudge",
    "JudgmentScore",
    "LLMGovernanceJudge",
    "LLMJudgment",
]
