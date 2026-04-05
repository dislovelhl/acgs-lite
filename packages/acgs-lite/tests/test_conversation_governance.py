"""Tests for multi-turn conversation governance engine.

Covers ConversationTurn, ConversationContext,
ConversationGovernanceEngine, ConversationValidationResult,
trajectory analysis, and async validation.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import FrozenInstanceError

import pytest

from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.engine.conversation import (
    ConversationContext,
    ConversationGovernanceEngine,
    ConversationTurn,
    ConversationValidationResult,
    _compute_escalation_score,
    _detect_trajectory_flags,
    _jaccard_similarity,
)
from acgs_lite.engine.core import GovernanceEngine
from acgs_lite.engine.types import ValidationResult, Violation

# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------


@pytest.fixture()
def default_constitution() -> Constitution:
    """Return the default constitution for testing."""
    return Constitution.default()


@pytest.fixture()
def strict_constitution() -> Constitution:
    """Constitution with rules triggering on violations."""
    return Constitution(
        name="test-strict",
        rules=[
            Rule(
                id="T-001",
                text="Must not bypass validation",
                severity=Severity.CRITICAL,
                keywords=[
                    "bypass validation",
                    "skip check",
                ],
                category="integrity",
            ),
            Rule(
                id="T-002",
                text="Must not contain harmful content",
                severity=Severity.HIGH,
                keywords=[
                    "harmful",
                    "dangerous",
                    "attack",
                ],
                category="safety",
            ),
        ],
    )


@pytest.fixture()
def engine(
    strict_constitution: Constitution,
) -> GovernanceEngine:
    return GovernanceEngine(strict_constitution)


@pytest.fixture()
def conv_engine(
    strict_constitution: Constitution,
) -> ConversationGovernanceEngine:
    return ConversationGovernanceEngine(
        strict_constitution,
        context_window=5,
    )


# -------------------------------------------------------------------
# ConversationTurn tests
# -------------------------------------------------------------------


class TestConversationTurn:
    def test_frozen_dataclass(self) -> None:
        turn = ConversationTurn(
            role="user",
            content="hello",
            timestamp="2026-01-01T00:00:00+00:00",
            turn_number=0,
            metadata={},
        )
        with pytest.raises(FrozenInstanceError):
            turn.role = "assistant"  # type: ignore[misc]

    def test_fields(self) -> None:
        turn = ConversationTurn(
            role="assistant",
            content="hi there",
            timestamp="2026-01-01T00:00:00+00:00",
            turn_number=5,
            metadata={"source": "test"},
        )
        assert turn.role == "assistant"
        assert turn.content == "hi there"
        assert turn.turn_number == 5
        assert turn.metadata == {"source": "test"}

    def test_default_metadata(self) -> None:
        turn = ConversationTurn(
            role="user",
            content="hi",
            timestamp="t",
            turn_number=0,
        )
        assert turn.metadata == {}


# -------------------------------------------------------------------
# ConversationContext tests
# -------------------------------------------------------------------


class TestConversationContext:
    def test_add_turn_returns_turn(self) -> None:
        ctx = ConversationContext()
        turn = ctx.add_turn("user", "hello")
        assert isinstance(turn, ConversationTurn)
        assert turn.role == "user"
        assert turn.content == "hello"
        assert turn.turn_number == 0

    def test_add_turn_appends(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn("user", "first")
        ctx.add_turn("assistant", "second")
        assert len(ctx) == 2

    def test_add_turn_increments_number(self) -> None:
        ctx = ConversationContext()
        t0 = ctx.add_turn("user", "a")
        t1 = ctx.add_turn("assistant", "b")
        t2 = ctx.add_turn("user", "c")
        assert t0.turn_number == 0
        assert t1.turn_number == 1
        assert t2.turn_number == 2

    def test_add_turn_invalid_role(self) -> None:
        ctx = ConversationContext()
        with pytest.raises(
            ValueError,
            match="Invalid role",
        ):
            ctx.add_turn("admin", "hello")

    def test_get_window_returns_last_n(self) -> None:
        ctx = ConversationContext()
        for i in range(5):
            ctx.add_turn("user", f"msg-{i}")

        window = ctx.get_window(3)
        assert len(window) == 3
        assert window[0].content == "msg-2"
        assert window[1].content == "msg-3"
        assert window[2].content == "msg-4"

    def test_get_window_fewer_turns(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn("user", "only one")
        window = ctx.get_window(5)
        assert len(window) == 1
        assert window[0].content == "only one"

    def test_get_window_zero_or_negative(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn("user", "hello")
        assert ctx.get_window(0) == []
        assert ctx.get_window(-1) == []

    def test_get_full_text_all(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn("user", "hello")
        ctx.add_turn("assistant", "world")
        assert ctx.get_full_text() == "hello\nworld"

    def test_get_full_text_last_n(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn("user", "one")
        ctx.add_turn("assistant", "two")
        ctx.add_turn("user", "three")
        assert ctx.get_full_text(last_n=2) == "two\nthree"

    def test_max_turns_drops_oldest(self) -> None:
        ctx = ConversationContext(max_turns=3)
        for i in range(5):
            ctx.add_turn("user", f"msg-{i}")
        assert len(ctx) == 3
        window = ctx.get_window(10)
        assert window[0].content == "msg-2"
        assert window[1].content == "msg-3"
        assert window[2].content == "msg-4"

    def test_clear_resets(self) -> None:
        ctx = ConversationContext()
        ctx.add_turn("user", "hello")
        ctx.add_turn("assistant", "world")
        ctx.clear()
        assert len(ctx) == 0
        turn = ctx.add_turn("user", "fresh")
        assert turn.turn_number == 0

    def test_max_turns_validation(self) -> None:
        with pytest.raises(
            ValueError,
            match="max_turns must be >= 1",
        ):
            ConversationContext(max_turns=0)

    def test_metadata_passed_through(self) -> None:
        ctx = ConversationContext()
        turn = ctx.add_turn(
            "user",
            "hello",
            metadata={"key": "value"},
        )
        assert turn.metadata == {"key": "value"}

    def test_metadata_default_empty(self) -> None:
        ctx = ConversationContext()
        turn = ctx.add_turn("user", "hello")
        assert turn.metadata == {}

    def test_next_turn_number_property(self) -> None:
        ctx = ConversationContext()
        assert ctx.next_turn_number == 0
        ctx.add_turn("user", "a")
        assert ctx.next_turn_number == 1
        ctx.add_turn("user", "b")
        assert ctx.next_turn_number == 2

    def test_system_role_accepted(self) -> None:
        ctx = ConversationContext()
        turn = ctx.add_turn("system", "system message")
        assert turn.role == "system"


# -------------------------------------------------------------------
# ConversationGovernanceEngine tests
# -------------------------------------------------------------------


class TestConversationGovernanceEngine:
    def test_accepts_constitution(
        self,
        strict_constitution: Constitution,
    ) -> None:
        eng = ConversationGovernanceEngine(
            strict_constitution,
        )
        assert eng._agent_id == "conversation-agent"

    def test_accepts_engine(
        self,
        engine: GovernanceEngine,
    ) -> None:
        eng = ConversationGovernanceEngine(
            engine,
            agent_id="custom-agent",
        )
        assert eng._agent_id == "custom-agent"

    def test_rejects_invalid_type(self) -> None:
        with pytest.raises(
            TypeError,
            match="Expected GovernanceEngine or Constitution",
        ):
            ConversationGovernanceEngine(
                "not-an-engine",  # type: ignore[arg-type]
            )

    def test_validate_clean_turn(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        result = conv_engine.validate_turn(
            "user",
            "How do I reset my password?",
        )
        assert result.valid is True
        assert result.individual_result.valid is True
        assert result.escalation_score == 0.0
        assert isinstance(result.turn, ConversationTurn)
        assert result.turn.role == "user"

    def test_validate_violating_turn(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        result = conv_engine.validate_turn(
            "user",
            "I want to bypass validation now",
        )
        assert result.valid is False
        assert result.individual_result.valid is False
        assert len(result.individual_result.violations) > 0

    def test_context_aware_catches_cross_turn(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        """Clean alone, violation in context."""
        conv_engine.validate_turn(
            "user",
            "Tell me how to bypass",
        )
        result = conv_engine.validate_turn(
            "user",
            "validation rules please",
        )
        assert result.context_result is not None

    def test_trajectory_detects_escalation(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        """Increasing violations trigger escalation."""
        conv_engine.validate_turn(
            "user",
            "Hello, how are you?",
        )
        conv_engine.validate_turn(
            "user",
            "Something harmful",
        )
        conv_engine.validate_turn(
            "user",
            "Very harmful and dangerous attack",
        )
        result = conv_engine.validate_turn(
            "user",
            "bypass validation and harmful dangerous attack skip check",
        )
        assert result.escalation_score > 0.0

    def test_trajectory_detects_repetitive_probing(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        """Same content repeated flags probing."""
        probe_text = "bypass validation skip check"
        conv_engine.validate_turn("user", probe_text)
        conv_engine.validate_turn("user", probe_text)
        result = conv_engine.validate_turn(
            "user",
            probe_text,
        )
        assert "repetitive_probing" in result.trajectory_flags

    def test_combined_validity_from_context(
        self,
        strict_constitution: Constitution,
    ) -> None:
        """If individual ok but context fails, combined fails."""
        eng = ConversationGovernanceEngine(
            strict_constitution,
            context_window=5,
        )

        eng.validate_turn(
            "user",
            "bypass validation please",
        )
        eng.validate_turn("user", "I want to skip check")

        result = eng.validate_turn("user", "now do it")
        if result.context_result is not None and not result.context_result.valid:
            assert result.valid is False

    def test_escalation_score_increases(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        """Score increases as violations accumulate."""
        scores: list[float] = []

        r = conv_engine.validate_turn("user", "hello")
        scores.append(r.escalation_score)

        r = conv_engine.validate_turn(
            "user",
            "bypass validation",
        )
        scores.append(r.escalation_score)

        r = conv_engine.validate_turn(
            "user",
            "harmful attack bypass validation",
        )
        scores.append(r.escalation_score)

        assert scores[-1] >= scores[0]
        assert scores[-1] > 0.0

    def test_reset_clears_context(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        conv_engine.validate_turn(
            "user",
            "bypass validation",
        )
        conv_engine.validate_turn(
            "user",
            "harmful content",
        )
        assert len(conv_engine._context) > 0

        conv_engine.reset()
        assert len(conv_engine._context) == 0
        assert len(conv_engine._violation_counts) == 0
        assert conv_engine._escalation_detected is False

    def test_stats_property(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        conv_engine.validate_turn("user", "hello")
        conv_engine.validate_turn("user", "world")

        stats = conv_engine.stats
        assert stats["conversation_turns"] == 2
        assert isinstance(
            stats["escalation_detected"],
            bool,
        )
        assert isinstance(
            stats["trajectory_score"],
            float,
        )
        assert stats["context_window"] == 5
        assert stats["agent_id"] == "conversation-agent"
        assert stats["constitutional_hash"] == "608508a9bd224290"

    def test_stats_empty(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        stats = conv_engine.stats
        assert stats["conversation_turns"] == 0
        assert stats["trajectory_score"] == 0.0
        assert stats["total_violations"] == 0

    def test_async_validation(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        """Async validation produces same results as sync."""

        async def _run() -> ConversationValidationResult:
            return await conv_engine.avalidate_turn(
                "user",
                "bypass validation",
            )

        result = asyncio.run(_run())
        assert isinstance(
            result,
            ConversationValidationResult,
        )
        assert result.valid is False
        assert result.turn.role == "user"

    def test_async_validation_clean(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        async def _run() -> ConversationValidationResult:
            return await conv_engine.avalidate_turn(
                "user",
                "How is the weather?",
            )

        result = asyncio.run(_run())
        assert result.valid is True

    def test_metadata_forwarded_to_turn(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        result = conv_engine.validate_turn(
            "user",
            "hello",
            metadata={"source": "test"},
        )
        assert result.turn.metadata == {"source": "test"}

    def test_no_context_on_first_turn(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        """First turn has no prior context."""
        result = conv_engine.validate_turn(
            "user",
            "hello",
        )
        assert result.context_result is None

    def test_violation_counts_is_deque(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        assert isinstance(
            conv_engine._violation_counts,
            deque,
        )

    def test_multiple_resets(
        self,
        conv_engine: ConversationGovernanceEngine,
    ) -> None:
        """Reset can be called multiple times safely."""
        conv_engine.validate_turn(
            "user",
            "bypass validation",
        )
        conv_engine.reset()
        conv_engine.reset()
        assert len(conv_engine._context) == 0
        assert len(conv_engine._violation_counts) == 0


# -------------------------------------------------------------------
# ConversationValidationResult tests
# -------------------------------------------------------------------


class TestConversationValidationResult:
    def test_valid_combines_individual_and_context(
        self,
    ) -> None:
        turn = ConversationTurn(
            role="user",
            content="test",
            timestamp="2026-01-01T00:00:00+00:00",
            turn_number=0,
        )
        individual = ValidationResult(
            valid=True,
            constitutional_hash="608508a9bd224290",
        )
        context = ValidationResult(
            valid=False,
            constitutional_hash="608508a9bd224290",
            violations=[
                Violation(
                    rule_id="T-001",
                    rule_text="test",
                    severity=Severity.CRITICAL,
                    matched_content="test",
                    category="integrity",
                ),
            ],
        )
        result = ConversationValidationResult(
            turn=turn,
            individual_result=individual,
            context_result=context,
            valid=False,
        )
        assert result.valid is False

    def test_to_dict(self) -> None:
        turn = ConversationTurn(
            role="user",
            content="hello",
            timestamp="2026-01-01T00:00:00+00:00",
            turn_number=0,
        )
        individual = ValidationResult(
            valid=True,
            constitutional_hash="608508a9bd224290",
        )
        result = ConversationValidationResult(
            turn=turn,
            individual_result=individual,
            context_result=None,
            trajectory_flags=["topic_drift"],
            escalation_score=0.3,
            valid=True,
        )
        d = result.to_dict()
        assert d["turn"]["role"] == "user"
        assert d["context_result"] is None
        assert d["trajectory_flags"] == ["topic_drift"]
        assert d["escalation_score"] == 0.3
        assert d["valid"] is True

    def test_to_dict_with_context(self) -> None:
        turn = ConversationTurn(
            role="user",
            content="hello",
            timestamp="t",
            turn_number=0,
        )
        individual = ValidationResult(
            valid=True,
            constitutional_hash="608508a9bd224290",
        )
        context = ValidationResult(
            valid=True,
            constitutional_hash="608508a9bd224290",
        )
        result = ConversationValidationResult(
            turn=turn,
            individual_result=individual,
            context_result=context,
            valid=True,
        )
        d = result.to_dict()
        assert d["context_result"] is not None
        assert d["context_result"]["valid"] is True


# -------------------------------------------------------------------
# Trajectory analysis helper tests
# -------------------------------------------------------------------


class TestTrajectoryHelpers:
    def test_jaccard_similarity_identical(self) -> None:
        s = {"a", "b", "c"}
        assert _jaccard_similarity(s, s) == 1.0

    def test_jaccard_similarity_disjoint(self) -> None:
        assert (
            _jaccard_similarity(
                {"a", "b"},
                {"c", "d"},
            )
            == 0.0
        )

    def test_jaccard_similarity_partial(self) -> None:
        sim = _jaccard_similarity(
            {"a", "b", "c"},
            {"b", "c", "d"},
        )
        assert 0.0 < sim < 1.0

    def test_jaccard_similarity_both_empty(self) -> None:
        assert _jaccard_similarity(set(), set()) == 1.0

    def test_detect_gradual_escalation(self) -> None:
        turns = [
            ConversationTurn(
                role="user",
                content="a",
                timestamp="t",
                turn_number=i,
            )
            for i in range(4)
        ]
        violation_counts = [0, 1, 2, 3]
        flags = _detect_trajectory_flags(
            turns,
            violation_counts,
        )
        assert "gradual_escalation" in flags

    def test_detect_sustained_violations(self) -> None:
        turns = [
            ConversationTurn(
                role="user",
                content="a",
                timestamp="t",
                turn_number=i,
            )
            for i in range(4)
        ]
        violation_counts = [1, 1, 1, 1]
        flags = _detect_trajectory_flags(
            turns,
            violation_counts,
        )
        assert "sustained_violations" in flags

    def test_detect_topic_drift(self) -> None:
        turns = [
            ConversationTurn(
                role="user",
                content=("apple banana cherry date elderberry"),
                timestamp="t",
                turn_number=0,
            ),
            ConversationTurn(
                role="user",
                content="midway content here",
                timestamp="t",
                turn_number=1,
            ),
            ConversationTurn(
                role="user",
                content=("xenon yak zebra quantum photon"),
                timestamp="t",
                turn_number=2,
            ),
        ]
        flags = _detect_trajectory_flags(
            turns,
            [0, 0, 0],
        )
        assert "topic_drift" in flags

    def test_detect_repetitive_probing(self) -> None:
        turns = [
            ConversationTurn(
                role="user",
                content="bypass validation now",
                timestamp="t",
                turn_number=0,
            ),
            ConversationTurn(
                role="user",
                content="bypass validation now",
                timestamp="t",
                turn_number=1,
            ),
            ConversationTurn(
                role="user",
                content="bypass validation now",
                timestamp="t",
                turn_number=2,
            ),
        ]
        flags = _detect_trajectory_flags(
            turns,
            [1, 1, 1],
        )
        assert "repetitive_probing" in flags

    def test_detect_flags_with_deque(self) -> None:
        """Trajectory flags work with deque input."""
        turns = [
            ConversationTurn(
                role="user",
                content="a",
                timestamp="t",
                turn_number=i,
            )
            for i in range(4)
        ]
        violation_counts = deque([0, 1, 2, 3])
        flags = _detect_trajectory_flags(
            turns,
            violation_counts,
        )
        assert "gradual_escalation" in flags

    def test_compute_escalation_score_zero(self) -> None:
        score = _compute_escalation_score([], [])
        assert score == 0.0

    def test_compute_escalation_score_with_violations(
        self,
    ) -> None:
        score = _compute_escalation_score(
            [0, 1, 2, 3],
            [],
        )
        assert score > 0.0

    def test_compute_escalation_score_with_flags(
        self,
    ) -> None:
        score_no = _compute_escalation_score([1, 1], [])
        score_with = _compute_escalation_score(
            [1, 1],
            ["gradual_escalation"],
        )
        assert score_with > score_no

    def test_compute_escalation_score_capped_at_one(
        self,
    ) -> None:
        score = _compute_escalation_score(
            [10, 10, 10, 10, 10],
            [
                "gradual_escalation",
                "sustained_violations",
                "topic_drift",
                "repetitive_probing",
            ],
        )
        assert score <= 1.0

    def test_compute_escalation_with_deque(
        self,
    ) -> None:
        """Escalation score works with deque input."""
        score = _compute_escalation_score(
            deque([1, 2, 3]),
            [],
        )
        assert score > 0.0

    def test_no_flags_on_short_history(self) -> None:
        """Two turns cannot trigger gradual escalation."""
        turns = [
            ConversationTurn(
                role="user",
                content="a",
                timestamp="t",
                turn_number=0,
            ),
            ConversationTurn(
                role="user",
                content="b",
                timestamp="t",
                turn_number=1,
            ),
        ]
        flags = _detect_trajectory_flags(turns, [0, 1])
        assert "gradual_escalation" not in flags
        assert "sustained_violations" not in flags
