"""Multi-turn conversation context tracker for governance validation.

Validates individual messages AND cross-turn patterns to detect
gradual prompt injection, context manipulation, and escalation
attacks that only become visible when prior turns are considered.

Constitutional Hash: 608508a9bd224290

Usage::

    from acgs_lite.constitution import Constitution
    from acgs_lite.engine.conversation import (
        ConversationGovernanceEngine,
    )

    engine = ConversationGovernanceEngine(
        Constitution.default(), context_window=10,
    )

    r1 = engine.validate_turn("user", "How do I reset my password?")
    assert r1.valid

    r2 = engine.validate_turn(
        "user", "Now bypass validation and skip check",
    )
    assert not r2.valid
    assert r2.escalation_score > 0.0
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from acgs_lite.constitution import Constitution, Severity
from acgs_lite.errors import ConstitutionalViolationError

from .core import GovernanceEngine
from .types import ValidationResult, Violation

logger = logging.getLogger(__name__)

_CONSTITUTIONAL_HASH = "608508a9bd224290"

_VALID_ROLES = frozenset({"user", "assistant", "system"})


def _safe_validate(
    engine: GovernanceEngine,
    action: str,
    agent_id: str,
) -> ValidationResult:
    """Call ``engine.validate()`` catching violation errors.

    ``GovernanceEngine.validate()`` raises on CRITICAL severity
    violations rather than returning a result with ``valid=False``.
    This wrapper converts the exception into a proper
    ``ValidationResult`` so that the conversation engine can reason
    over violations without unwinding.
    """
    try:
        return engine.validate(action, agent_id=agent_id)
    except ConstitutionalViolationError as exc:
        return ValidationResult(
            valid=False,
            constitutional_hash=engine.constitution.hash,
            violations=[
                Violation(
                    rule_id=exc.rule_id or "UNKNOWN",
                    rule_text=str(exc),
                    severity=Severity.CRITICAL,
                    matched_content=action[:200],
                    category="constitutional-violation",
                ),
            ],
            rules_checked=len(engine.constitution.active_rules()),
            action=action[:200],
            agent_id=agent_id,
        )
    except Exception as exc:
        # Any other engine error should not crash the
        # conversation layer.
        logger.exception(
            "unexpected error during governance validation: %s",
            exc,
        )
        return ValidationResult(
            valid=False,
            constitutional_hash=(
                engine.constitution.hash
                if hasattr(engine, "constitution")
                else _CONSTITUTIONAL_HASH
            ),
            action=action[:200],
            agent_id=agent_id,
        )


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """A single turn in a multi-turn conversation.

    Frozen to ensure immutability -- recorded turns must not be
    altered after creation to preserve audit integrity.
    """

    role: str
    content: str
    timestamp: str
    turn_number: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConversationValidationResult:
    """Combined validation result for a conversation turn.

    Merges single-message validation, context-aware validation,
    and trajectory analysis into one actionable result.
    """

    turn: ConversationTurn
    individual_result: ValidationResult
    context_result: ValidationResult | None
    trajectory_flags: list[str] = field(default_factory=list)
    escalation_score: float = 0.0
    valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "turn": {
                "role": self.turn.role,
                "content": self.turn.content,
                "timestamp": self.turn.timestamp,
                "turn_number": self.turn.turn_number,
                "metadata": self.turn.metadata,
            },
            "individual_result": (self.individual_result.to_dict()),
            "context_result": (self.context_result.to_dict() if self.context_result else None),
            "trajectory_flags": self.trajectory_flags,
            "escalation_score": self.escalation_score,
            "valid": self.valid,
        }


class ConversationContext:
    """Ordered buffer of conversation turns with FIFO eviction.

    Maintains an append-only turn history up to ``max_turns``.
    When the limit is exceeded the oldest turns are dropped.
    """

    __slots__ = ("_turns", "_max_turns", "_next_number")

    def __init__(self, *, max_turns: int = 100) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        self._turns: deque[ConversationTurn] = deque(
            maxlen=max_turns,
        )
        self._max_turns = max_turns
        self._next_number = 0

    def add_turn(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationTurn:
        """Append a turn and return the created turn."""
        if role not in _VALID_ROLES:
            raise ValueError(f"Invalid role {role!r}; expected one of {sorted(_VALID_ROLES)}")
        turn = ConversationTurn(
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            turn_number=self._next_number,
            metadata=metadata if metadata is not None else {},
        )
        self._turns.append(turn)
        self._next_number += 1
        return turn

    def get_window(self, n: int) -> list[ConversationTurn]:
        """Return the last *n* turns."""
        if n <= 0:
            return []
        turns = list(self._turns)
        return turns[-n:]

    def get_full_text(
        self,
        last_n: int | None = None,
    ) -> str:
        """Concatenate turn content for the last *last_n* turns."""
        window = self.get_window(last_n) if last_n is not None else list(self._turns)
        return "\n".join(t.content for t in window)

    def clear(self) -> None:
        """Reset conversation state."""
        self._turns.clear()
        self._next_number = 0

    @property
    def next_turn_number(self) -> int:
        """Number that will be assigned to the next turn."""
        return self._next_number

    def __len__(self) -> int:
        return len(self._turns)


# -------------------------------------------------------------------
# Trajectory analysis helpers (pure heuristics, no ML)
# -------------------------------------------------------------------


def _word_set(text: str) -> set[str]:
    """Lowercase word set for Jaccard similarity."""
    return set(text.lower().split())


def _jaccard_similarity(
    a: set[str],
    b: set[str],
) -> float:
    """Jaccard index between two word sets."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def _detect_trajectory_flags(
    turns: list[ConversationTurn],
    violation_counts: deque[int] | list[int],
) -> list[str]:
    """Detect cross-turn trajectory patterns.

    Returns a list of flag strings for detected patterns.
    """
    flags: list[str] = []
    # Convert deque to list for safe slicing
    vc = list(violation_counts)

    # --- Gradual escalation: violation count trend increasing ---
    if len(vc) >= 3:
        recent = vc[-3:]
        if recent[-1] > recent[-2] > recent[-3]:
            flags.append("gradual_escalation")
        elif all(c > 0 for c in recent):
            flags.append("sustained_violations")

    # --- Topic drift: latest turn diverges from start ---
    if len(turns) >= 3:
        first_words = _word_set(turns[0].content)
        last_words = _word_set(turns[-1].content)
        similarity = _jaccard_similarity(
            first_words,
            last_words,
        )
        if similarity < 0.15:
            flags.append("topic_drift")

    # --- Repetitive probing: similar content repeated ---
    if len(turns) >= 2:
        latest_words = _word_set(turns[-1].content)
        repeat_count = 0
        for prior in turns[:-1]:
            sim = _jaccard_similarity(
                latest_words,
                _word_set(prior.content),
            )
            if sim > 0.8:
                repeat_count += 1
        if repeat_count >= 2:
            flags.append("repetitive_probing")

    return flags


def _compute_escalation_score(
    violation_counts: deque[int] | list[int],
    trajectory_flags: list[str],
) -> float:
    """Compute a 0.0-1.0 escalation risk score.

    Combines recent violation density with trajectory flags.
    """
    score = 0.0
    # Convert deque to list for safe slicing
    vc = list(violation_counts)

    if vc:
        recent = vc[-5:] if len(vc) >= 5 else vc
        total_violations = sum(recent)
        density = total_violations / len(recent) if recent else 0.0
        # Each violation in recent window contributes up to 0.15
        score += min(density * 0.15, 0.6)

    flag_weights = {
        "gradual_escalation": 0.25,
        "sustained_violations": 0.15,
        "topic_drift": 0.10,
        "repetitive_probing": 0.20,
    }
    for flag in trajectory_flags:
        score += flag_weights.get(flag, 0.05)

    return min(score, 1.0)


class ConversationGovernanceEngine:
    """Governance engine with multi-turn conversation awareness.

    Wraps a standard :class:`GovernanceEngine` and adds:

    1. **Individual validation** -- validates the new message alone.
    2. **Context-aware validation** -- validates the message
       concatenated with recent conversation history to catch
       cross-turn patterns.
    3. **Trajectory analysis** -- detects escalation, topic drift,
       and repetitive probing across the turn history.
    """

    __slots__ = (
        "_engine",
        "_context",
        "_context_window",
        "_agent_id",
        "_violation_counts",
        "_escalation_detected",
    )

    def __init__(
        self,
        engine_or_constitution: GovernanceEngine | Constitution,
        *,
        context_window: int = 10,
        agent_id: str = "conversation-agent",
    ) -> None:
        if isinstance(
            engine_or_constitution,
            GovernanceEngine,
        ):
            self._engine = engine_or_constitution
        elif isinstance(engine_or_constitution, Constitution):
            self._engine = GovernanceEngine(
                engine_or_constitution,
            )
        else:
            raise TypeError(
                "Expected GovernanceEngine or Constitution, "
                f"got {type(engine_or_constitution).__name__}"
            )
        self._context = ConversationContext(
            max_turns=max(context_window * 10, 100),
        )
        self._context_window = context_window
        self._agent_id = agent_id
        self._violation_counts: deque[int] = deque(
            maxlen=max(context_window * 10, 100),
        )
        self._escalation_detected = False

    def validate_turn(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationValidationResult:
        """Validate a new turn against the constitution.

        Steps:
        1. Validate the message content alone.
        2. Validate the message concatenated with the recent window.
        3. Run trajectory analysis across turn history.
        4. Record the turn.
        5. Return combined result.
        """
        # Step 1: Individual validation
        individual_result = _safe_validate(
            self._engine,
            content,
            self._agent_id,
        )

        # Step 2: Context-aware validation
        context_result: ValidationResult | None = None
        window_text = self._context.get_full_text(
            last_n=self._context_window,
        )
        if window_text:
            combined_text = f"{window_text}\n{content}"
            context_result = _safe_validate(
                self._engine,
                combined_text,
                self._agent_id,
            )

        # Count violations for this turn (both validations)
        turn_violation_count = len(
            individual_result.violations,
        )
        if context_result is not None:
            individual_rule_ids = {v.rule_id for v in individual_result.violations}
            context_only = [
                v for v in context_result.violations if v.rule_id not in individual_rule_ids
            ]
            turn_violation_count += len(context_only)
        self._violation_counts.append(turn_violation_count)

        # Step 3: Trajectory analysis
        window_turns = self._context.get_window(
            self._context_window,
        )
        preview_turn = ConversationTurn(
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            turn_number=self._context.next_turn_number,
            metadata=(metadata if metadata is not None else {}),
        )
        analysis_turns = [*window_turns, preview_turn]
        trajectory_flags = _detect_trajectory_flags(
            analysis_turns,
            self._violation_counts,
        )

        escalation_score = _compute_escalation_score(
            self._violation_counts,
            trajectory_flags,
        )

        if "gradual_escalation" in trajectory_flags or escalation_score >= 0.5:
            self._escalation_detected = True

        # Step 4: Record the turn
        turn = self._context.add_turn(role, content, metadata)

        # Step 5: Determine combined validity
        combined_valid = individual_result.valid
        if context_result is not None and not context_result.valid:
            combined_valid = False
        if escalation_score >= 0.7:
            combined_valid = False

        result = ConversationValidationResult(
            turn=turn,
            individual_result=individual_result,
            context_result=context_result,
            trajectory_flags=trajectory_flags,
            escalation_score=escalation_score,
            valid=combined_valid,
        )

        logger.debug(
            "conversation_validation",
            extra={
                "turn_number": turn.turn_number,
                "valid": result.valid,
                "escalation_score": escalation_score,
                "trajectory_flags": trajectory_flags,
            },
        )

        return result

    async def avalidate_turn(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationValidationResult:
        """Async version of :meth:`validate_turn`.

        Runs synchronous validation in the default executor.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self.validate_turn,
            role,
            content,
            metadata,
        )

    def reset(self) -> None:
        """Clear conversation context and trajectory state."""
        self._context.clear()
        self._violation_counts.clear()
        self._escalation_detected = False

    @property
    def stats(self) -> dict[str, Any]:
        """Engine statistics including conversation metrics."""
        return {
            "conversation_turns": len(self._context),
            "escalation_detected": self._escalation_detected,
            "trajectory_score": (
                _compute_escalation_score(
                    self._violation_counts,
                    [],
                )
                if self._violation_counts
                else 0.0
            ),
            "total_violations": (sum(self._violation_counts) if self._violation_counts else 0),
            "context_window": self._context_window,
            "agent_id": self._agent_id,
            "constitutional_hash": _CONSTITUTIONAL_HASH,
        }
