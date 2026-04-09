"""Tests for Shadow Adjudicator (Phase 2)."""

from __future__ import annotations

import asyncio

import pytest

from acgs_lite.engine.shadow_adjudicator import (
    InMemoryShadowJudge,
    ShadowAdjudicator,
    ShadowResult,
)


class TestAmbiguityScore:
    def test_clear_violation_is_zero(self):
        judge = InMemoryShadowJudge()
        sa = ShadowAdjudicator(judge)
        score = sa.compute_ambiguity("send ssn", deterministic_violations=["NO-PII"])
        assert score == 0.0

    def test_short_clear_action_low_ambiguity(self):
        judge = InMemoryShadowJudge()
        sa = ShadowAdjudicator(judge)
        score = sa.compute_ambiguity("hello world", deterministic_violations=[])
        assert score < 0.3

    def test_long_conditional_action_high_ambiguity(self):
        judge = InMemoryShadowJudge()
        sa = ShadowAdjudicator(judge)
        action = (
            "If the user could possibly provide their social security number, "
            "perhaps we should consider whether to store it. Maybe we should "
            "check with compliance first? Unless the regulation says otherwise."
        )
        score = sa.compute_ambiguity(action, deterministic_violations=[])
        assert score > 0.5

    def test_question_mark_adds_ambiguity(self):
        judge = InMemoryShadowJudge()
        sa = ShadowAdjudicator(judge)
        base = "process the user data" + " " * 100  # make it long enough
        score_no_q = sa.compute_ambiguity(base, deterministic_violations=[])
        score_q = sa.compute_ambiguity(base + "?", deterministic_violations=[])
        assert score_q > score_no_q


class TestShadowEvaluation:
    @pytest.mark.asyncio
    async def test_skips_deterministic_deny(self):
        judge = InMemoryShadowJudge(default_decision="allow")
        sa = ShadowAdjudicator(judge)

        result = await sa.evaluate_shadow(
            "send malware to target",
            deterministic_decision="deny",
            deterministic_violations=["NO-HARM"],
        )

        assert result.shadow_decision is None
        assert result.deterministic_decision == "deny"
        assert len(judge.calls) == 0  # LLM was never called

    @pytest.mark.asyncio
    async def test_skips_short_action(self):
        judge = InMemoryShadowJudge()
        sa = ShadowAdjudicator(judge, min_action_length=100)

        result = await sa.evaluate_shadow(
            "short action",
            deterministic_decision="allow",
            deterministic_violations=[],
        )

        assert result.shadow_decision is None
        assert len(judge.calls) == 0

    @pytest.mark.asyncio
    async def test_skips_low_ambiguity(self):
        judge = InMemoryShadowJudge()
        sa = ShadowAdjudicator(judge, ambiguity_threshold=0.9, min_action_length=10)

        result = await sa.evaluate_shadow(
            "a simple clear action with no ambiguity at all whatsoever period",
            deterministic_decision="allow",
            deterministic_violations=[],
        )

        assert result.shadow_decision is None

    @pytest.mark.asyncio
    async def test_runs_llm_on_ambiguous_action(self):
        judge = InMemoryShadowJudge(default_decision="deny")
        sa = ShadowAdjudicator(judge, ambiguity_threshold=0.1, min_action_length=10)

        long_ambiguous = (
            "If the user could possibly provide sensitive data, maybe we should "
            "consider whether to process it? Perhaps check compliance first. "
            "Unless the regulation says otherwise, we might proceed."
        )
        result = await sa.evaluate_shadow(
            long_ambiguous,
            deterministic_decision="allow",
            deterministic_violations=[],
        )

        assert result.shadow_decision == "deny"
        assert result.disagreement is True
        assert result.shadow_confidence == 0.9
        assert len(judge.calls) == 1

    @pytest.mark.asyncio
    async def test_agreement_no_disagreement_flag(self):
        judge = InMemoryShadowJudge(default_decision="allow")
        sa = ShadowAdjudicator(judge, ambiguity_threshold=0.1, min_action_length=10)

        long_action = "Could the system possibly help with something? " * 5
        result = await sa.evaluate_shadow(
            long_action,
            deterministic_decision="allow",
            deterministic_violations=[],
        )

        assert result.shadow_decision == "allow"
        assert result.disagreement is False


class TestFailClosed:
    @pytest.mark.asyncio
    async def test_llm_error_returns_none_shadow(self):
        """LLM failure should be silent — shadow_decision stays None."""

        class FailingJudge:
            async def evaluate(self, action, context, constitution):
                raise RuntimeError("LLM API down")

        sa = ShadowAdjudicator(FailingJudge(), ambiguity_threshold=0.1, min_action_length=10)

        long_ambiguous = "Could we possibly maybe perhaps consider this option? " * 4
        result = await sa.evaluate_shadow(
            long_ambiguous,
            deterministic_decision="allow",
            deterministic_violations=[],
        )

        assert result.shadow_decision is None
        assert result.disagreement is False

    @pytest.mark.asyncio
    async def test_invalid_decision_fails_closed_to_deny(self):
        class BadJudge:
            async def evaluate(self, action, context, constitution):
                return {"decision": "maybe", "confidence": 0.5}

        sa = ShadowAdjudicator(BadJudge(), ambiguity_threshold=0.1, min_action_length=10)

        long_action = "If the system could possibly process this sensitive data? " * 4
        result = await sa.evaluate_shadow(
            long_action,
            deterministic_decision="allow",
            deterministic_violations=[],
        )

        assert result.shadow_decision == "deny"  # fail-closed


class TestDeterministicDenyNeverOverridden:
    """Critical invariant: deterministic deny must NEVER be overridden."""

    @pytest.mark.asyncio
    async def test_deny_not_overridden_even_if_llm_allows(self):
        judge = InMemoryShadowJudge(default_decision="allow")
        sa = ShadowAdjudicator(judge)

        result = await sa.evaluate_shadow(
            "send malware " * 50,  # long action
            deterministic_decision="deny",
            deterministic_violations=["NO-HARM"],
        )

        # Shadow should NOT have run at all
        assert result.shadow_decision is None
        assert result.deterministic_decision == "deny"
        assert len(judge.calls) == 0


class TestMetrics:
    @pytest.mark.asyncio
    async def test_shadow_override_rate(self):
        judge = InMemoryShadowJudge(default_decision="deny")
        sa = ShadowAdjudicator(judge, ambiguity_threshold=0.1, min_action_length=10)

        for i in range(5):
            await sa.evaluate_shadow(
                f"Could the system possibly handle sensitive request {i}? " * 3,
                deterministic_decision="allow",
                deterministic_violations=[],
            )

        assert sa.disagreement_count == 5
        assert sa.shadow_override_rate == 1.0

    @pytest.mark.asyncio
    async def test_clear_results(self):
        judge = InMemoryShadowJudge(default_decision="deny")
        sa = ShadowAdjudicator(judge, ambiguity_threshold=0.1, min_action_length=10)

        await sa.evaluate_shadow(
            "Could this possibly be an issue? " * 5,
            deterministic_decision="allow",
            deterministic_violations=[],
        )

        assert len(sa.results) == 1
        sa.clear_results()
        assert len(sa.results) == 0
        assert sa.shadow_override_rate == 0.0
