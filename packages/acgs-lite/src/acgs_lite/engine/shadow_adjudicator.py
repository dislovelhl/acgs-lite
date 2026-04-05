"""Shadow LLM adjudicator for governance validation.

Runs an LLM judge **shadow-only** alongside the deterministic engine. It
processes ambiguous cases (deterministic allows but LLM disagrees) and logs
disagreements to the audit trail. Does NOT override deterministic denials.

Design principles:
- Shadow failures are silent (fire-and-forget, never blocks hot path)
- Deterministic deny paths are NEVER overridden
- All shadow results logged as ``type="shadow_disagreement"`` audit entries
- LLM errors are fail-closed to ``None`` (no shadow opinion)

MACI role: VALIDATOR (read-only evaluation, no action execution)
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from acgs_lite.fail_closed import fail_closed

logger = logging.getLogger(__name__)

# Pattern for detecting conditional/ambiguous language
_AMBIGUOUS_PATTERNS = re.compile(
    r"\b(could|might|should|would|if|unless|perhaps|maybe|possibly)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ShadowResult:
    """Result of a shadow LLM adjudication."""

    action: str
    deterministic_decision: str  # "allow" | "deny"
    shadow_decision: str | None  # "allow" | "deny" | None (if shadow didn't run or failed)
    shadow_confidence: float = 0.0
    shadow_reasoning: str = ""
    disagreement: bool = False
    ambiguity_score: float = 0.0
    model_id: str = ""


@runtime_checkable
class ShadowJudgeProtocol(Protocol):
    """Protocol for shadow LLM judge implementations."""

    async def evaluate(
        self,
        action: str,
        context: dict[str, Any],
        constitution: Any,
    ) -> dict[str, Any]:
        """Return dict with at minimum ``decision`` and ``confidence`` keys."""
        ...


class ShadowAdjudicator:
    """Shadow LLM adjudicator that runs alongside the deterministic engine.

    Parameters
    ----------
    llm_judge:
        An async callable matching ``ShadowJudgeProtocol``.
    ambiguity_threshold:
        Minimum ambiguity score (0-1) to trigger LLM shadow evaluation.
        Default 0.3 — triggers on moderately ambiguous actions.
    min_action_length:
        Actions shorter than this skip shadow evaluation.
    """

    def __init__(
        self,
        llm_judge: ShadowJudgeProtocol,
        *,
        ambiguity_threshold: float = 0.3,
        min_action_length: int = 50,
    ) -> None:
        self._judge = llm_judge
        self._ambiguity_threshold = ambiguity_threshold
        self._min_action_length = min_action_length
        self._shadow_results: list[ShadowResult] = []

    def compute_ambiguity(
        self,
        action: str,
        deterministic_violations: list[Any],
    ) -> float:
        """Compute an ambiguity score for the action.

        Higher score = more ambiguous = more likely to benefit from LLM review.
        Score in [0.0, 1.0].
        """
        if deterministic_violations:
            return 0.0  # Clear match, no ambiguity

        score = 0.0
        # Length factor: longer actions are harder to match deterministically
        if len(action) > 200:
            score += 0.3
        elif len(action) > 100:
            score += 0.15

        # Conditional language factor
        matches = _AMBIGUOUS_PATTERNS.findall(action)
        score += min(0.3, len(matches) * 0.1)

        # Question mark factor
        if "?" in action:
            score += 0.15

        # Multi-sentence factor
        sentences = action.count(".") + action.count("!") + action.count("?")
        if sentences > 2:
            score += 0.15

        return min(1.0, score)

    @fail_closed(deny_value=None, message="shadow adjudicator: LLM call failed, ignoring")
    async def _run_shadow_judge(
        self,
        action: str,
        context: dict[str, Any],
        constitution: Any,
    ) -> dict[str, Any] | None:
        """Run the LLM judge, fail-closed to None on any error."""
        result = await self._judge.evaluate(action, context, constitution)
        return result

    async def evaluate_shadow(
        self,
        action: str,
        deterministic_decision: str,
        deterministic_violations: list[Any],
        context: dict[str, Any] | None = None,
        constitution: Any = None,
    ) -> ShadowResult:
        """Run shadow evaluation on an action.

        Returns immediately if:
        - deterministic engine denied (we never override denials)
        - action is too short
        - ambiguity score is below threshold

        Otherwise fires the LLM judge and logs the result.
        """
        result = ShadowResult(
            action=action[:500],
            deterministic_decision=deterministic_decision,
            shadow_decision=None,
        )

        # Never shadow-check deterministic denials
        if deterministic_decision == "deny":
            return result

        # Skip short actions
        if len(action) < self._min_action_length:
            return result

        # Compute ambiguity
        ambiguity = self.compute_ambiguity(action, deterministic_violations)
        result.ambiguity_score = ambiguity

        if ambiguity < self._ambiguity_threshold:
            return result

        # Fire LLM shadow check
        judge_result = await self._run_shadow_judge(
            action,
            context or {},
            constitution,
        )

        if judge_result is None:
            return result  # LLM failed, shadow is silent

        shadow_decision = judge_result.get("decision", "")
        if shadow_decision not in ("allow", "deny"):
            shadow_decision = "deny"  # fail-closed

        result.shadow_decision = shadow_decision
        result.shadow_confidence = judge_result.get("confidence", 0.0)
        result.shadow_reasoning = judge_result.get("reasoning", "")
        result.model_id = judge_result.get("model_id", "")
        result.disagreement = shadow_decision != deterministic_decision

        if result.disagreement:
            logger.info(
                "shadow_disagreement",
                extra={
                    "action_prefix": action[:100],
                    "deterministic": deterministic_decision,
                    "shadow": shadow_decision,
                    "confidence": result.shadow_confidence,
                    "ambiguity": ambiguity,
                },
            )

        self._shadow_results.append(result)
        return result

    def fire_and_forget(
        self,
        action: str,
        deterministic_decision: str,
        deterministic_violations: list[Any],
        context: dict[str, Any] | None = None,
        constitution: Any = None,
    ) -> None:
        """Schedule shadow evaluation without blocking the caller.

        This is the primary integration point — call from the hot path
        after the deterministic engine returns, and the shadow runs
        in the background without adding latency.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # No event loop, skip silently

        loop.create_task(
            self.evaluate_shadow(
                action,
                deterministic_decision,
                deterministic_violations,
                context,
                constitution,
            )
        )

    @property
    def results(self) -> list[ShadowResult]:
        """Access accumulated shadow results (for metrics/audit)."""
        return list(self._shadow_results)

    @property
    def disagreement_count(self) -> int:
        return sum(1 for r in self._shadow_results if r.disagreement)

    @property
    def shadow_override_rate(self) -> float:
        """Fraction of shadow evaluations where LLM would have denied."""
        evaluated = [r for r in self._shadow_results if r.shadow_decision is not None]
        if not evaluated:
            return 0.0
        denies = sum(1 for r in evaluated if r.shadow_decision == "deny")
        return denies / len(evaluated)

    def clear_results(self) -> None:
        self._shadow_results.clear()


class InMemoryShadowJudge:
    """Test stub for shadow judge."""

    def __init__(self, *, default_decision: str = "allow", default_confidence: float = 0.9) -> None:
        self.default_decision = default_decision
        self.default_confidence = default_confidence
        self.calls: list[dict[str, Any]] = []

    async def evaluate(
        self, action: str, context: dict[str, Any], constitution: Any
    ) -> dict[str, Any]:
        self.calls.append({"action": action})
        return {
            "decision": self.default_decision,
            "confidence": self.default_confidence,
            "reasoning": "stub",
            "model_id": "in-memory-shadow",
        }


__all__ = [
    "InMemoryShadowJudge",
    "ShadowAdjudicator",
    "ShadowJudgeProtocol",
    "ShadowResult",
]
