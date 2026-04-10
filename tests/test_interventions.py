"""Tests for the intervention engine (Phase 5 CDP, AD-6).

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from acgs_lite.interventions.actions import InterventionAction, InterventionRule
from acgs_lite.interventions.conditions import evaluate_condition
from acgs_lite.interventions.defaults import get_default_rules
from acgs_lite.interventions.engine import InterventionEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cdp(
    verdict: str = "allow",
    risk_score: float = 0.0,
    violated_rules: list[str] | None = None,
    runtime_obligations: list[dict[str, Any]] | None = None,
    compliance_frameworks: list[str] | None = None,
    subject_id: str = "user-1",
) -> dict[str, Any]:
    return {
        "cdp_id": "cdp-test-001",
        "verdict": verdict,
        "risk_score": risk_score,
        "violated_rules": violated_rules or [],
        "runtime_obligations": runtime_obligations or [],
        "compliance_frameworks": compliance_frameworks or [],
        "subject_id": subject_id,
    }


def _rule(
    rule_id: str,
    action: InterventionAction,
    condition: dict[str, Any],
    priority: int = 100,
    enabled: bool = True,
    metadata: dict[str, Any] | None = None,
) -> InterventionRule:
    return InterventionRule(
        rule_id=rule_id,
        name=f"Test rule {rule_id}",
        action=action,
        condition=condition,
        priority=priority,
        enabled=enabled,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# evaluate_condition
# ---------------------------------------------------------------------------


class TestEvaluateConditionVerdict:
    def test_verdict_match(self) -> None:
        assert evaluate_condition({"verdict": "deny"}, _cdp(verdict="deny")) is True

    def test_verdict_no_match(self) -> None:
        assert evaluate_condition({"verdict": "deny"}, _cdp(verdict="allow")) is False

    def test_verdict_in_matches_deny(self) -> None:
        assert (
            evaluate_condition(
                {"verdict_in": ["deny", "conditional"]}, _cdp(verdict="deny")
            )
            is True
        )

    def test_verdict_in_matches_conditional(self) -> None:
        assert (
            evaluate_condition(
                {"verdict_in": ["deny", "conditional"]}, _cdp(verdict="conditional")
            )
            is True
        )

    def test_verdict_in_no_match(self) -> None:
        assert (
            evaluate_condition(
                {"verdict_in": ["deny", "conditional"]}, _cdp(verdict="allow")
            )
            is False
        )


class TestEvaluateConditionRiskScore:
    def test_risk_score_gte_matches(self) -> None:
        assert evaluate_condition({"risk_score_gte": 0.8}, _cdp(risk_score=0.9)) is True

    def test_risk_score_gte_exact(self) -> None:
        assert evaluate_condition({"risk_score_gte": 0.8}, _cdp(risk_score=0.8)) is True

    def test_risk_score_gte_no_match(self) -> None:
        assert evaluate_condition({"risk_score_gte": 0.8}, _cdp(risk_score=0.5)) is False


class TestEvaluateConditionViolatedRules:
    def test_has_violated_rule_present(self) -> None:
        record = _cdp(violated_rules=["PHI_GUARD", "OTHER"])
        assert evaluate_condition({"has_violated_rule": "PHI_GUARD"}, record) is True

    def test_has_violated_rule_absent(self) -> None:
        record = _cdp(violated_rules=["OTHER"])
        assert evaluate_condition({"has_violated_rule": "PHI_GUARD"}, record) is False

    def test_has_violated_rule_empty(self) -> None:
        record = _cdp(violated_rules=[])
        assert evaluate_condition({"has_violated_rule": "PHI_GUARD"}, record) is False


class TestEvaluateConditionObligations:
    def test_has_obligation_type_present(self) -> None:
        obs = [{"obligation_type": "phi_guard", "severity": "blocking", "satisfied": False}]
        assert (
            evaluate_condition({"has_obligation_type": "phi_guard"}, _cdp(runtime_obligations=obs))
            is True
        )

    def test_has_obligation_type_absent(self) -> None:
        obs = [{"obligation_type": "other_type", "severity": "soft", "satisfied": True}]
        assert (
            evaluate_condition({"has_obligation_type": "phi_guard"}, _cdp(runtime_obligations=obs))
            is False
        )

    def test_has_obligation_type_empty(self) -> None:
        assert (
            evaluate_condition({"has_obligation_type": "phi_guard"}, _cdp()) is False
        )

    def test_has_blocking_unsatisfied_true(self) -> None:
        obs = [{"obligation_type": "foo", "severity": "blocking", "satisfied": False}]
        assert (
            evaluate_condition(
                {"has_blocking_unsatisfied": True}, _cdp(runtime_obligations=obs)
            )
            is True
        )

    def test_has_blocking_unsatisfied_all_satisfied(self) -> None:
        obs = [{"obligation_type": "foo", "severity": "blocking", "satisfied": True}]
        assert (
            evaluate_condition(
                {"has_blocking_unsatisfied": True}, _cdp(runtime_obligations=obs)
            )
            is False
        )

    def test_has_blocking_unsatisfied_not_blocking(self) -> None:
        obs = [{"obligation_type": "foo", "severity": "soft", "satisfied": False}]
        assert (
            evaluate_condition(
                {"has_blocking_unsatisfied": True}, _cdp(runtime_obligations=obs)
            )
            is False
        )

    def test_has_blocking_unsatisfied_false_condition(self) -> None:
        obs = [{"obligation_type": "foo", "severity": "blocking", "satisfied": False}]
        assert (
            evaluate_condition(
                {"has_blocking_unsatisfied": False}, _cdp(runtime_obligations=obs)
            )
            is False
        )


class TestEvaluateConditionFramework:
    def test_framework_in_match(self) -> None:
        record = _cdp(compliance_frameworks=["igaming", "gdpr"])
        assert evaluate_condition({"framework_in": ["igaming"]}, record) is True

    def test_framework_in_no_match(self) -> None:
        record = _cdp(compliance_frameworks=["gdpr"])
        assert evaluate_condition({"framework_in": ["igaming"]}, record) is False

    def test_framework_in_empty(self) -> None:
        assert evaluate_condition({"framework_in": ["igaming"]}, _cdp()) is False


class TestEvaluateConditionLogical:
    def test_and_both_true(self) -> None:
        record = _cdp(verdict="deny", risk_score=0.9)
        cond = {"and": [{"verdict": "deny"}, {"risk_score_gte": 0.8}]}
        assert evaluate_condition(cond, record) is True

    def test_and_one_false(self) -> None:
        record = _cdp(verdict="deny", risk_score=0.5)
        cond = {"and": [{"verdict": "deny"}, {"risk_score_gte": 0.8}]}
        assert evaluate_condition(cond, record) is False

    def test_or_one_true(self) -> None:
        record = _cdp(verdict="allow", risk_score=0.9)
        cond = {"or": [{"verdict": "deny"}, {"risk_score_gte": 0.8}]}
        assert evaluate_condition(cond, record) is True

    def test_or_both_false(self) -> None:
        record = _cdp(verdict="allow", risk_score=0.3)
        cond = {"or": [{"verdict": "deny"}, {"risk_score_gte": 0.8}]}
        assert evaluate_condition(cond, record) is False

    def test_not_negates_true(self) -> None:
        record = _cdp(verdict="deny")
        assert evaluate_condition({"not": {"verdict": "deny"}}, record) is False

    def test_not_negates_false(self) -> None:
        record = _cdp(verdict="allow")
        assert evaluate_condition({"not": {"verdict": "deny"}}, record) is True

    def test_nested_and_or(self) -> None:
        record = _cdp(verdict="deny", risk_score=0.9)
        cond = {
            "and": [
                {"or": [{"verdict": "deny"}, {"verdict": "conditional"}]},
                {"risk_score_gte": 0.7},
            ]
        }
        assert evaluate_condition(cond, record) is True


class TestEvaluateConditionUnknown:
    def test_unknown_type_returns_false(self) -> None:
        assert evaluate_condition({"totally_unknown_key": "value"}, _cdp()) is False

    def test_empty_condition_returns_false(self) -> None:
        assert evaluate_condition({}, _cdp()) is False


# ---------------------------------------------------------------------------
# InterventionAction enum
# ---------------------------------------------------------------------------


class TestInterventionActionEnum:
    def test_all_six_values(self) -> None:
        values = {a.value for a in InterventionAction}
        assert values == {"block", "throttle", "notify", "escalate", "cool_off", "log_only"}

    def test_is_str_enum(self) -> None:
        assert InterventionAction.BLOCK == "block"
        assert InterventionAction.COOL_OFF == "cool_off"


# ---------------------------------------------------------------------------
# InterventionRule.to_dict
# ---------------------------------------------------------------------------


class TestInterventionRuleToDict:
    def test_to_dict_contains_all_fields(self) -> None:
        rule = _rule("r1", InterventionAction.ESCALATE, {"verdict": "deny"}, priority=5)
        d = rule.to_dict()
        assert d["rule_id"] == "r1"
        assert d["action"] == "escalate"
        assert d["condition"] == {"verdict": "deny"}
        assert d["enabled"] is True
        assert d["priority"] == 5
        assert d["metadata"] == {}
        assert "name" in d


# ---------------------------------------------------------------------------
# InterventionEngine.evaluate — basic
# ---------------------------------------------------------------------------


class TestInterventionEngineEvaluate:
    def test_empty_rules_returns_empty(self) -> None:
        engine = InterventionEngine()
        outcomes = engine.evaluate(_cdp())
        assert outcomes == []

    def test_no_match_returns_empty(self) -> None:
        rule = _rule("r1", InterventionAction.ESCALATE, {"verdict": "deny"})
        engine = InterventionEngine(rules=[rule])
        outcomes = engine.evaluate(_cdp(verdict="allow"))
        assert outcomes == []

    def test_matching_rule_returns_escalate_outcome(self) -> None:
        rule = _rule("r1", InterventionAction.ESCALATE, {"verdict": "deny"})
        engine = InterventionEngine(rules=[rule])
        outcomes = engine.evaluate(_cdp(verdict="deny"))
        assert len(outcomes) == 1
        assert outcomes[0].action == "escalate"
        assert outcomes[0].triggered is True
        assert outcomes[0].metadata.get("requires_review") is True

    def test_disabled_rule_skipped(self) -> None:
        rule = _rule("r1", InterventionAction.ESCALATE, {"verdict": "deny"}, enabled=False)
        engine = InterventionEngine(rules=[rule])
        outcomes = engine.evaluate(_cdp(verdict="deny"))
        assert outcomes == []

    def test_rules_evaluated_in_priority_order(self) -> None:
        """Lower priority number checked first — both match, both appear in order."""
        r_low = _rule("r-low", InterventionAction.LOG_ONLY, {"verdict": "deny"}, priority=10)
        r_high = _rule("r-high", InterventionAction.ESCALATE, {"verdict": "deny"}, priority=50)
        engine = InterventionEngine(rules=[r_high, r_low])  # Intentionally reversed
        outcomes = engine.evaluate(_cdp(verdict="deny"))
        assert len(outcomes) == 2
        assert outcomes[0].reason == "rule:r-low"
        assert outcomes[1].action == "escalate"

    def test_add_rule_resorts_by_priority(self) -> None:
        engine = InterventionEngine()
        r_high = _rule("r-high", InterventionAction.ESCALATE, {"verdict": "deny"}, priority=100)
        r_low = _rule("r-low", InterventionAction.LOG_ONLY, {"verdict": "deny"}, priority=10)
        engine.add_rule(r_high)
        engine.add_rule(r_low)
        assert engine.rules[0].rule_id == "r-low"


# ---------------------------------------------------------------------------
# InterventionEngine — THROTTLE
# ---------------------------------------------------------------------------


class TestThrottleHandler:
    def test_first_request_not_triggered(self) -> None:
        rule = _rule(
            "throttle-1",
            InterventionAction.THROTTLE,
            {"verdict": "allow"},
            metadata={"window_seconds": 60, "max_requests": 3},
        )
        engine = InterventionEngine(rules=[rule])
        outcome = engine.evaluate(_cdp())[0]
        assert outcome.triggered is False
        assert outcome.metadata["count"] == 1

    def test_exceeding_max_requests_triggers(self) -> None:
        rule = _rule(
            "throttle-2",
            InterventionAction.THROTTLE,
            {"verdict": "allow"},
            metadata={"window_seconds": 60, "max_requests": 2},
        )
        engine = InterventionEngine(rules=[rule])
        for _ in range(2):
            engine.evaluate(_cdp())
        outcome = engine.evaluate(_cdp())[0]
        assert outcome.triggered is True

    def test_window_reset(self) -> None:
        rule = _rule(
            "throttle-3",
            InterventionAction.THROTTLE,
            {"verdict": "allow"},
            metadata={"window_seconds": 0.01, "max_requests": 1},
        )
        engine = InterventionEngine(rules=[rule])
        engine.evaluate(_cdp())
        engine.evaluate(_cdp())  # triggers (count=2 > 1)
        # Expire the window
        time.sleep(0.05)
        outcome = engine.evaluate(_cdp())[0]
        # After window expiry, count resets to 1 — not triggered
        assert outcome.triggered is False


# ---------------------------------------------------------------------------
# InterventionEngine — COOL_OFF
# ---------------------------------------------------------------------------


class TestCoolOffHandler:
    def test_cool_off_sets_state(self) -> None:
        rule = _rule(
            "cooloff-1",
            InterventionAction.COOL_OFF,
            {"verdict": "deny"},
            metadata={"duration_seconds": 3600},
        )
        engine = InterventionEngine(rules=[rule])
        outcome = engine.evaluate(_cdp(verdict="deny", subject_id="user-99"))[0]
        assert outcome.triggered is True
        assert outcome.action == "cool_off"
        assert engine.is_cooled_off("cooloff-1:user-99") is True

    def test_is_cooled_off_false_when_not_set(self) -> None:
        engine = InterventionEngine()
        assert engine.is_cooled_off("nonexistent-key") is False

    def test_cool_off_expires(self) -> None:
        rule = _rule(
            "cooloff-2",
            InterventionAction.COOL_OFF,
            {"verdict": "deny"},
            metadata={"duration_seconds": 0.01},
        )
        engine = InterventionEngine(rules=[rule])
        engine.evaluate(_cdp(verdict="deny", subject_id="user-exp"))
        time.sleep(0.05)
        assert engine.is_cooled_off("cooloff-2:user-exp") is False


# ---------------------------------------------------------------------------
# InterventionEngine — NOTIFY
# ---------------------------------------------------------------------------


class TestNotifyHandler:
    def test_notify_no_webhook_returns_not_triggered(self) -> None:
        rule = _rule("notify-1", InterventionAction.NOTIFY, {"verdict": "deny"})
        engine = InterventionEngine(rules=[rule])
        outcome = engine.evaluate(_cdp(verdict="deny"))[0]
        assert outcome.triggered is False
        assert outcome.reason == "no_webhook_url"

    def test_notify_fires_webhook(self) -> None:
        rule = _rule("notify-2", InterventionAction.NOTIFY, {"verdict": "deny"})
        engine = InterventionEngine(rules=[rule], webhook_url="http://example.com/hook")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            outcome = engine.evaluate(_cdp(verdict="deny"))[0]

        assert outcome.triggered is True
        assert "200" in outcome.reason

    def test_notify_rule_webhook_url_metadata(self) -> None:
        rule = _rule(
            "notify-3",
            InterventionAction.NOTIFY,
            {"verdict": "deny"},
            metadata={"webhook_url": "http://meta.example.com/hook"},
        )
        engine = InterventionEngine(rules=[rule])

        mock_resp = MagicMock()
        mock_resp.status = 201
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            outcome = engine.evaluate(_cdp(verdict="deny"))[0]

        assert outcome.triggered is True


# ---------------------------------------------------------------------------
# InterventionEngine — BLOCK
# ---------------------------------------------------------------------------


class TestBlockHandler:
    def test_block_raises_governance_halt_error(self) -> None:
        from acgs_lite.circuit_breaker import GovernanceHaltError

        rule = _rule("block-1", InterventionAction.BLOCK, {"verdict": "deny"})
        engine = InterventionEngine(rules=[rule])
        with pytest.raises(GovernanceHaltError):
            engine.evaluate(_cdp(verdict="deny"))

    def test_block_does_not_raise_when_no_match(self) -> None:
        rule = _rule("block-2", InterventionAction.BLOCK, {"verdict": "deny"})
        engine = InterventionEngine(rules=[rule])
        outcomes = engine.evaluate(_cdp(verdict="allow"))
        assert outcomes == []


# ---------------------------------------------------------------------------
# InterventionEngine — handler failure
# ---------------------------------------------------------------------------


class TestHandlerFailure:
    def test_handler_exception_produces_non_triggered_outcome(self) -> None:
        rule = _rule("err-1", InterventionAction.ESCALATE, {"verdict": "deny"})
        engine = InterventionEngine(rules=[rule])

        # Patch _handle_escalate to raise a non-halt error
        with patch.object(engine, "_handle_escalate", side_effect=RuntimeError("boom")):
            outcomes = engine.evaluate(_cdp(verdict="deny"))

        assert len(outcomes) == 1
        assert outcomes[0].triggered is False
        assert "handler_error" in outcomes[0].reason

    def test_log_only_action(self) -> None:
        rule = _rule("log-1", InterventionAction.LOG_ONLY, {"verdict": "deny"})
        engine = InterventionEngine(rules=[rule])
        outcomes = engine.evaluate(_cdp(verdict="deny"))
        assert len(outcomes) == 1
        assert outcomes[0].action == "log_only"
        assert outcomes[0].triggered is True


# ---------------------------------------------------------------------------
# get_default_rules
# ---------------------------------------------------------------------------


class TestGetDefaultRules:
    def test_general_returns_escalate_rule(self) -> None:
        rules = get_default_rules("general")
        actions = {r.action for r in rules}
        assert InterventionAction.ESCALATE in actions

    def test_legal_contains_escalate_for_deny(self) -> None:
        rules = get_default_rules("legal")
        rule_ids = {r.rule_id for r in rules}
        assert "legal-escalate-any-deny" in rule_ids

    def test_legal_contains_log_only_conditional(self) -> None:
        rules = get_default_rules("legal")
        rule_ids = {r.rule_id for r in rules}
        assert "legal-log-conditional" in rule_ids

    def test_healthcare_contains_block_for_phi_deny(self) -> None:
        rules = get_default_rules("healthcare")
        block_rules = [r for r in rules if r.action == InterventionAction.BLOCK]
        assert len(block_rules) >= 1
        assert block_rules[0].rule_id == "healthcare-block-phi-deny"

    def test_healthcare_contains_escalate_phi_obligation(self) -> None:
        rules = get_default_rules("healthcare")
        rule_ids = {r.rule_id for r in rules}
        assert "healthcare-escalate-phi" in rule_ids

    def test_igaming_contains_cool_off(self) -> None:
        rules = get_default_rules("igaming")
        cool_off_rules = [r for r in rules if r.action == InterventionAction.COOL_OFF]
        assert len(cool_off_rules) >= 1

    def test_igaming_contains_escalate_deny(self) -> None:
        rules = get_default_rules("igaming")
        rule_ids = {r.rule_id for r in rules}
        assert "igaming-escalate-deny" in rule_ids

    def test_igaming_contains_throttle(self) -> None:
        rules = get_default_rules("igaming")
        throttle_rules = [r for r in rules if r.action == InterventionAction.THROTTLE]
        assert len(throttle_rules) >= 1

    def test_rules_sorted_by_priority(self) -> None:
        for vertical in ("general", "legal", "healthcare", "igaming"):
            rules = get_default_rules(vertical)
            priorities = [r.priority for r in rules]
            assert priorities == sorted(priorities), f"Rules not sorted for {vertical}"

    def test_igaming_evaluate_cooloff_triggers(self) -> None:
        """Integration: igaming rules evaluate against a matching CDP record."""
        rules = get_default_rules("igaming")
        engine = InterventionEngine(rules=rules)
        obs = [{"obligation_type": "spend_limit", "severity": "blocking", "satisfied": False}]
        record = _cdp(
            verdict="allow",
            compliance_frameworks=["igaming"],
            runtime_obligations=obs,
        )
        outcomes = engine.evaluate(record)
        cool_off_outcomes = [o for o in outcomes if o.action == "cool_off"]
        assert len(cool_off_outcomes) >= 1
        assert cool_off_outcomes[0].triggered is True


# ---------------------------------------------------------------------------
# GovernedAgent integration
# ---------------------------------------------------------------------------


class TestGovernedAgentIntegrationEngine:
    """Verify GovernedAgent accepts and wires intervention_engine."""

    def test_governed_agent_accepts_intervention_engine(self) -> None:
        from acgs_lite import GovernedAgent

        dummy_agent = MagicMock()
        dummy_agent.run = MagicMock(return_value="ok")
        engine = InterventionEngine()

        ga = GovernedAgent(dummy_agent, intervention_engine=engine)
        assert ga._intervention_engine is engine

    def test_governed_agent_default_none(self) -> None:
        from acgs_lite import GovernedAgent

        dummy_agent = MagicMock()
        dummy_agent.run = MagicMock(return_value="ok")
        ga = GovernedAgent(dummy_agent)
        assert ga._intervention_engine is None
