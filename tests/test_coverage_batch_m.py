"""Tests targeting uncovered lines in rule.py, testing.py, and google_genai.py.

Missing lines from coverage report:
  rule.py:      47, 73, 135, 237-238, 262, 296, 329-330, 370-395, 426-457, 509, 514-517, 566-567, 628
  testing.py:   50, 81-82, 93-104, 108-111, 122-161, 172, 184
  google_genai: 34-36, 48-51, 53-55, 63-71, 102, 119, 137-157, 197
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from acgs_lite.constitution.rule import (
    AcknowledgedTension,
    Rule,
    RuleSynthesisProvider,
    Severity,
    _cosine_sim,
    _heuristic_rule_payload,
)
from acgs_lite.constitution.testing import (
    GovernanceTestCase,
    GovernanceTestSuite,
    TestCaseFailure,
    TestSuiteResult,
)

# ─── rule.py coverage ────────────────────────────────────────────────────────


class TestCosineSimZeroMag:
    """Line 47: _cosine_sim returns None for zero-magnitude vectors."""

    def test_zero_vector_a(self) -> None:
        assert _cosine_sim([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]) is None

    def test_zero_vector_b(self) -> None:
        assert _cosine_sim([1.0, 2.0, 3.0], [0.0, 0.0, 0.0]) is None

    def test_both_zero(self) -> None:
        assert _cosine_sim([0.0, 0.0], [0.0, 0.0]) is None

    def test_empty_lists(self) -> None:
        assert _cosine_sim([], []) is None

    def test_mismatched_lengths(self) -> None:
        assert _cosine_sim([1.0], [1.0, 2.0]) is None


class TestAcknowledgedTensionEmpty:
    """Line 73: AcknowledgedTension raises ValueError for empty rule_id."""

    def test_empty_string(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            AcknowledgedTension(rule_id="")

    def test_whitespace_only(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            AcknowledgedTension(rule_id="   ")


class TestHeuristicRulePayloadMediumSeverity:
    """Line 135: branch where severity is set to MEDIUM for advisory/warn keywords."""

    def test_warn_keyword(self) -> None:
        result = _heuristic_rule_payload("warn the user about something")
        assert result["severity"] == Severity.MEDIUM

    def test_advisory_keyword(self) -> None:
        result = _heuristic_rule_payload("This is an advisory note for compliance")
        assert result["severity"] == Severity.MEDIUM

    def test_informational_keyword(self) -> None:
        result = _heuristic_rule_payload("Informational notice only")
        assert result["severity"] == Severity.MEDIUM

    def test_prohibit_overrides_to_critical(self) -> None:
        result = _heuristic_rule_payload("Must not ever prohibit access")
        assert result["severity"] == Severity.CRITICAL


class TestValidateTemporalFieldsInvalid:
    """Lines 237-238: invalid ISO-8601 strings raise ValueError."""

    def test_invalid_date(self) -> None:
        with pytest.raises(ValueError):
            Rule(id="R1", text="test", valid_from="not-a-date")

    def test_invalid_datetime(self) -> None:
        with pytest.raises(ValueError):
            Rule(id="R1", text="test", valid_until="2025-13-99")


class TestMatchesDisabledRule:
    """Line 262: matches_with_signals returns False for disabled rule."""

    def test_disabled(self) -> None:
        rule = Rule(id="R1", text="test", keywords=["bad"], enabled=False)
        assert rule.matches_with_signals("bad stuff", True, False) is False


class TestMatchDetailDisabled:
    """Line 296: match_detail for disabled rule."""

    def test_disabled_rule_match_detail(self) -> None:
        rule = Rule(id="R1", text="test", keywords=["bad"], enabled=False)
        detail = rule.match_detail("bad stuff")
        assert detail["matched"] is False
        assert detail["rule_id"] == "R1"
        assert detail["trigger_type"] is None


class TestMatchDetailPattern:
    """Lines 329-330: match_detail triggers on regex pattern."""

    def test_pattern_match(self) -> None:
        rule = Rule(id="R1", text="test", patterns=[r"secret\w+"])
        detail = rule.match_detail("leak secretkey here")
        assert detail["matched"] is True
        assert detail["trigger_type"] == "pattern"
        assert "secret" in detail["trigger_value"]


class TestExplain:
    """Lines 370-395: Rule.explain() method."""

    def test_explain_with_keywords_and_patterns(self) -> None:
        rule = Rule(
            id="R1",
            text="Do not leak secrets",
            severity=Severity.CRITICAL,
            keywords=["secret", "password"],
            patterns=[r"api[_-]?key"],
            workflow_action="block",
            depends_on=["R0"],
        )
        exp = rule.explain()
        assert exp["rule_id"] == "R1"
        assert "CRITICAL" in exp["summary"]
        assert "keywords" in exp["how_it_detects"].lower()
        assert "1 regex" in exp["how_it_detects"]
        assert exp["when_triggered"] == "Hard block — action is rejected immediately"
        assert exp["dependencies"] == ["R0"]
        assert "Critical" in exp["severity_label"]

    def test_explain_no_detection(self) -> None:
        rule = Rule(id="R2", text="Some rule", severity=Severity.LOW)
        exp = rule.explain()
        assert "No automatic detection" in exp["how_it_detects"]
        assert "Low" in exp["severity_label"]

    def test_explain_workflow_actions(self) -> None:
        for action, expected_substr in [
            ("block_and_notify", "alert"),
            ("require_human_review", "human review"),
            ("escalate_to_senior", "senior"),
            ("warn", "warning"),
        ]:
            rule = Rule(id="R3", text="t", workflow_action=action)
            exp = rule.explain()
            assert expected_substr in exp["when_triggered"].lower()

    def test_explain_halt_workflow(self) -> None:
        """ViolationAction.HALT has a dedicated explanation."""
        from acgs_lite.constitution.rule import ViolationAction

        rule = Rule(id="R4", text="t", workflow_action=ViolationAction.HALT)
        exp = rule.explain()
        assert "halt" in exp["when_triggered"].lower()


class TestImpactScore:
    """Lines 426-457: Rule.impact_score() method."""

    def test_high_impact_critical_rule(self) -> None:
        rule = Rule(
            id="R1",
            text="Never allow",
            severity=Severity.CRITICAL,
            keywords=["a", "b", "c", "d", "e"],
            patterns=[r"x", r"y"],
            workflow_action="block",
            tags=["gdpr"],
            depends_on=["R0"],
            subcategory="pii",
        )
        score = rule.impact_score()
        assert score["rule_id"] == "R1"
        assert score["score"] >= 0.7
        assert score["classification"] == "high-impact"
        assert score["blocking"] is True
        assert score["severity_weight"] == 1.0

    def test_low_impact_rule(self) -> None:
        rule = Rule(id="R2", text="Info only", severity=Severity.LOW)
        score = rule.impact_score()
        assert score["score"] < 0.4
        assert score["classification"] == "low-impact"
        assert score["blocking"] is False

    def test_moderate_impact_rule(self) -> None:
        rule = Rule(
            id="R3",
            text="Moderate",
            severity=Severity.HIGH,
            keywords=["data", "leak", "expose", "breach"],
            workflow_action="warn",
            tags=["compliance"],
        )
        score = rule.impact_score()
        assert score["classification"] == "moderate-impact"
        assert 0.4 <= score["score"] < 0.7

    def test_detection_breadth_capped(self) -> None:
        rule = Rule(
            id="R4",
            text="Many kw",
            severity=Severity.HIGH,
            keywords=[f"kw{i}" for i in range(20)],
        )
        score = rule.impact_score()
        assert score["detection_breadth"] == 1.0


class TestFromDescriptionEdgeCases:
    """Line 509: empty id after synthesis; Lines 514-517: severity type handling."""

    def test_empty_description(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            Rule.from_description("")

    def test_severity_string_from_provider(self) -> None:
        provider = MagicMock(spec=RuleSynthesisProvider)
        provider.generate_rule.return_value = {
            "id": "LLM-001",
            "severity": "critical",
            "text": "No data leaks",
        }
        rule = Rule.from_description("No data leaks", llm_provider=provider)
        assert rule.severity == Severity.CRITICAL

    def test_severity_enum_from_provider(self) -> None:
        provider = MagicMock(spec=RuleSynthesisProvider)
        provider.generate_rule.return_value = {
            "id": "LLM-002",
            "severity": Severity.LOW,
            "text": "Informational",
        }
        rule = Rule.from_description("Informational", llm_provider=provider)
        assert rule.severity == Severity.LOW

    def test_severity_invalid_type_raises(self) -> None:
        provider = MagicMock(spec=RuleSynthesisProvider)
        provider.generate_rule.return_value = {
            "id": "LLM-003",
            "severity": 42,
            "text": "Bad",
        }
        with pytest.raises(TypeError, match="str or Severity"):
            Rule.from_description("Bad severity type", llm_provider=provider)

    def test_synthesized_empty_id_raises(self) -> None:
        provider = MagicMock(spec=RuleSynthesisProvider)
        provider.generate_rule.return_value = {"id": "", "text": "x"}
        with pytest.raises(ValueError, match="non-empty"):
            Rule.from_description("something", rule_id="", llm_provider=provider)


class TestValidatePatterns:
    """Line 217 area (covered partially): invalid regex pattern validation."""

    def test_invalid_regex_raises(self) -> None:
        with pytest.raises(ValueError):
            Rule(id="R1", text="test", patterns=["[invalid"])


class TestCosineSimOnRules:
    """Lines 566-567, 628: Rule.cosine_similarity delegating to _cosine_sim."""

    def test_cosine_similarity_between_rules(self) -> None:
        r1 = Rule(id="R1", text="t", embedding=[1.0, 0.0, 0.0])
        r2 = Rule(id="R2", text="t", embedding=[1.0, 0.0, 0.0])
        sim = r1.cosine_similarity(r2)
        assert sim is not None
        assert abs(sim - 1.0) < 1e-6

    def test_cosine_similarity_no_embedding(self) -> None:
        r1 = Rule(id="R1", text="t", embedding=[1.0, 0.0])
        r2 = Rule(id="R2", text="t", embedding=[])
        assert r1.cosine_similarity(r2) is None

    def test_cosine_similarity_orthogonal(self) -> None:
        r1 = Rule(id="R1", text="t", embedding=[1.0, 0.0])
        r2 = Rule(id="R2", text="t", embedding=[0.0, 1.0])
        sim = r1.cosine_similarity(r2)
        assert sim is not None
        assert abs(sim) < 1e-6


# ─── testing.py coverage ─────────────────────────────────────────────────────


class TestTestSuiteResultToDict:
    """Line 50: TestSuiteResult.to_dict()."""

    def test_to_dict_with_failures(self) -> None:
        tc = GovernanceTestCase(
            action="do bad thing",
            expected_decision="deny",
            context={"env": "prod"},
            description="test case",
            tags=("safety",),
        )
        failure = TestCaseFailure(
            test_case=tc,
            actual_decision="allow",
            details="Expected 'deny' but got 'allow'",
        )
        result = TestSuiteResult(
            total=1,
            passed=0,
            failed=1,
            failures=(failure,),
            pass_rate=0.0,
            duration_ms=1.5,
        )
        d = result.to_dict()
        assert d["total"] == 1
        assert d["failed"] == 1
        assert d["pass_rate"] == 0.0
        assert len(d["failures"]) == 1
        assert d["failures"][0]["actual_decision"] == "allow"
        assert d["failures"][0]["test_case"]["action"] == "do bad thing"
        assert d["failures"][0]["test_case"]["tags"] == ["safety"]

    def test_to_dict_no_failures(self) -> None:
        result = TestSuiteResult(
            total=2, passed=2, failed=0, failures=(), pass_rate=1.0, duration_ms=0.5
        )
        d = result.to_dict()
        assert d["failures"] == []
        assert d["pass_rate"] == 1.0


class TestGovernanceTestSuiteAddCase:
    """Lines 81-82, 93-104: add_case with all parameters and max-size guard."""

    def test_add_case_basic(self) -> None:
        suite = GovernanceTestSuite(name="test")
        case = suite.add_case(
            action="do something",
            expected_decision="allow",
            context={"env": "dev"},
            description="basic test",
            tags=("unit",),
        )
        assert case.action == "do something"
        assert case.context == {"env": "dev"}
        assert case.description == "basic test"
        assert case.tags == ("unit",)
        assert len(suite) == 1

    def test_add_case_max_exceeded(self) -> None:
        suite = GovernanceTestSuite()
        suite._cases = [
            GovernanceTestCase(action=f"a{i}", expected_decision="allow") for i in range(10_000)
        ]
        with pytest.raises(ValueError, match="max size"):
            suite.add_case(action="overflow", expected_decision="deny")


class TestGovernanceTestSuiteAddCases:
    """Lines 108-111: add_cases bulk method."""

    def test_add_cases(self) -> None:
        suite = GovernanceTestSuite()
        cases = [
            GovernanceTestCase(action="a1", expected_decision="allow"),
            GovernanceTestCase(action="a2", expected_decision="deny"),
        ]
        suite.add_cases(cases)
        assert len(suite) == 2

    def test_add_cases_overflow(self) -> None:
        suite = GovernanceTestSuite()
        suite._cases = [
            GovernanceTestCase(action=f"a{i}", expected_decision="allow") for i in range(9_999)
        ]
        cases = [
            GovernanceTestCase(action="x", expected_decision="deny"),
            GovernanceTestCase(action="y", expected_decision="deny"),
        ]
        with pytest.raises(ValueError, match="max size"):
            suite.add_cases(cases)


class TestGovernanceTestSuiteRun:
    """Lines 122-161: run() method with various engine behaviors."""

    def _make_engine(self, valid: bool, violations: list[Any] | None = None) -> MagicMock:
        engine = MagicMock()
        result = MagicMock()
        result.valid = valid
        result.violations = violations or []
        engine.validate.return_value = result
        return engine

    def test_run_all_pass(self) -> None:
        suite = GovernanceTestSuite()
        suite.add_case("good action", "allow")
        engine = self._make_engine(valid=True)
        result = suite.run(engine)
        assert result.total == 1
        assert result.passed == 1
        assert result.failed == 0
        assert result.pass_rate == 1.0

    def test_run_with_failure(self) -> None:
        suite = GovernanceTestSuite()
        suite.add_case("good action", "deny")  # expect deny but engine says allow
        engine = self._make_engine(valid=True)
        result = suite.run(engine)
        assert result.failed == 1
        assert result.failures[0].actual_decision == "allow"

    def test_run_engine_exception_maps_to_deny(self) -> None:
        suite = GovernanceTestSuite()
        suite.add_case("bad action", "deny")
        engine = MagicMock()
        engine.validate.side_effect = RuntimeError("boom")
        result = suite.run(engine)
        assert result.passed == 1
        assert result.failed == 0

    def test_run_blocking_violation(self) -> None:
        suite = GovernanceTestSuite()
        suite.add_case("risky action", "deny")
        violation = MagicMock()
        violation.severity = MagicMock()
        violation.severity.blocks.return_value = True
        engine = self._make_engine(valid=False, violations=[violation])
        result = suite.run(engine)
        assert result.passed == 1  # expect deny, got deny

    def test_run_non_blocking_violation_escalates(self) -> None:
        suite = GovernanceTestSuite()
        suite.add_case("risky action", "escalate")
        violation = MagicMock()
        violation.severity = MagicMock()
        violation.severity.blocks.return_value = False
        engine = self._make_engine(valid=False, violations=[violation])
        result = suite.run(engine)
        assert result.passed == 1

    def test_run_violation_no_severity_attr(self) -> None:
        """When violation has no severity, blocks() defaults to True -> deny."""
        suite = GovernanceTestSuite()
        suite.add_case("risky action", "deny")
        violation = MagicMock(spec=[])  # no attributes
        engine = self._make_engine(valid=False, violations=[violation])
        result = suite.run(engine)
        assert result.passed == 1

    def test_run_empty_suite(self) -> None:
        suite = GovernanceTestSuite()
        engine = self._make_engine(valid=True)
        result = suite.run(engine)
        assert result.total == 0
        assert result.pass_rate == 1.0

    def test_run_with_context(self) -> None:
        suite = GovernanceTestSuite()
        suite.add_case("action", "allow", context={"env": "prod"})
        engine = self._make_engine(valid=True)
        result = suite.run(engine)
        assert result.passed == 1
        engine.validate.assert_called_once_with("action", context={"env": "prod"})

    def test_run_empty_context_passed_as_none(self) -> None:
        """Empty context dict becomes None in run()."""
        suite = GovernanceTestSuite()
        suite.add_case("action", "allow", context={})
        engine = self._make_engine(valid=True)
        suite.run(engine)
        engine.validate.assert_called_once_with("action", context=None)


class TestGovernanceTestSuiteExport:
    """Line 172: export() method."""

    def test_export(self) -> None:
        suite = GovernanceTestSuite()
        suite.add_case("act1", "allow", description="desc", tags=("t1", "t2"))
        exported = suite.export()
        assert len(exported) == 1
        assert exported[0]["action"] == "act1"
        assert exported[0]["tags"] == ["t1", "t2"]
        assert exported[0]["description"] == "desc"


class TestGovernanceTestSuiteLen:
    """Line 184: __len__."""

    def test_len(self) -> None:
        suite = GovernanceTestSuite()
        assert len(suite) == 0
        suite.add_case("a", "allow")
        assert len(suite) == 1


# ─── google_genai.py coverage ────────────────────────────────────────────────


class TestExtractContentText:
    """Lines 48-55: _extract_content_text edge cases."""

    def test_string_input(self) -> None:
        from acgs_lite.integrations.google_genai import _extract_content_text

        assert _extract_content_text("hello") == "hello"

    def test_list_of_strings(self) -> None:
        from acgs_lite.integrations.google_genai import _extract_content_text

        assert _extract_content_text(["hello", "world"]) == "hello world"

    def test_list_of_dicts(self) -> None:
        from acgs_lite.integrations.google_genai import _extract_content_text

        result = _extract_content_text([{"text": "foo"}, {"text": "bar"}])
        assert result == "foo bar"

    def test_list_with_text_attr(self) -> None:
        from acgs_lite.integrations.google_genai import _extract_content_text

        item = MagicMock()
        item.text = "from_attr"
        result = _extract_content_text([item])
        assert result == "from_attr"

    def test_object_with_text_attr(self) -> None:
        from acgs_lite.integrations.google_genai import _extract_content_text

        obj = MagicMock()
        obj.text = "obj_text"
        result = _extract_content_text(obj)
        assert result == "obj_text"

    def test_fallback_to_str(self) -> None:
        from acgs_lite.integrations.google_genai import _extract_content_text

        result = _extract_content_text(42)
        assert result == "42"


class TestExtractResponseText:
    """Lines 63-71: _extract_response_text edge cases."""

    def test_response_with_text(self) -> None:
        from acgs_lite.integrations.google_genai import _extract_response_text

        resp = MagicMock()
        resp.text = "response_text"
        assert _extract_response_text(resp) == "response_text"

    def test_response_with_candidates(self) -> None:
        from acgs_lite.integrations.google_genai import _extract_response_text

        part = MagicMock()
        part.text = "from_candidate"
        content = MagicMock()
        content.parts = [part]
        candidate = MagicMock()
        candidate.content = content
        resp = MagicMock(spec=[])  # no .text
        resp.candidates = [candidate]
        assert _extract_response_text(resp) == "from_candidate"

    def test_response_empty_text(self) -> None:
        from acgs_lite.integrations.google_genai import _extract_response_text

        resp = MagicMock()
        resp.text = ""
        assert _extract_response_text(resp) == ""

    def test_response_none_text(self) -> None:
        from acgs_lite.integrations.google_genai import _extract_response_text

        resp = MagicMock()
        resp.text = None
        assert _extract_response_text(resp) == ""

    def test_response_no_attrs(self) -> None:
        from acgs_lite.integrations.google_genai import _extract_response_text

        resp = object()
        assert _extract_response_text(resp) == ""

    def test_response_index_error(self) -> None:
        from acgs_lite.integrations.google_genai import _extract_response_text

        resp = MagicMock(spec=[])
        resp.candidates = []
        assert _extract_response_text(resp) == ""


class TestGovernedModels:
    """Lines 102, 119: GovernedModels.generate_content response validation + __getattr__."""

    def test_generate_content_with_response_violations(self) -> None:
        from acgs_lite.integrations.google_genai import GovernedModels

        client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "bad output with bypass security"
        client.models.generate_content.return_value = mock_response

        engine = MagicMock()
        # First call (input validation): pass
        # Second call (output validation): return violations
        violation = MagicMock()
        violation.rule_id = "R1"
        output_result = MagicMock()
        output_result.valid = False
        output_result.violations = [violation]
        engine.validate.side_effect = [None, output_result]
        engine.strict = True

        models = GovernedModels(client, engine, "test-agent")
        result = models.generate_content(model="gemini", contents="hello")
        assert result == mock_response
        assert engine.validate.call_count == 2

    def test_generate_content_stream(self) -> None:
        from acgs_lite.integrations.google_genai import GovernedModels

        client = MagicMock()
        engine = MagicMock()
        engine.strict = True
        models = GovernedModels(client, engine, "test-agent")
        models.generate_content_stream(model="gemini", contents="hello")
        client.models.generate_content_stream.assert_called_once()

    def test_getattr_delegation(self) -> None:
        from acgs_lite.integrations.google_genai import GovernedModels

        client = MagicMock()
        client.models.list_models.return_value = ["model1"]
        engine = MagicMock()
        models = GovernedModels(client, engine, "test-agent")
        result = models.list_models()
        assert result == ["model1"]


@pytest.mark.asyncio
class TestGovernedAsyncModels:
    """Lines 137-157: GovernedAsyncModels.generate_content."""

    async def test_async_generate_content_with_violations(self) -> None:
        from acgs_lite.integrations.google_genai import GovernedAsyncModels

        client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "bad output with bypass"
        client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        engine = MagicMock()
        violation = MagicMock()
        violation.rule_id = "R1"
        output_result = MagicMock()
        output_result.valid = False
        output_result.violations = [violation]
        engine.validate.side_effect = [None, output_result]
        engine.strict = True

        models = GovernedAsyncModels(client, engine, "test-agent")
        result = await models.generate_content(model="gemini", contents="hello")
        assert result == mock_response
        assert engine.validate.call_count == 2

    async def test_async_generate_content_clean(self) -> None:
        from acgs_lite.integrations.google_genai import GovernedAsyncModels

        client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "clean output"
        client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        engine = MagicMock()
        clean_result = MagicMock()
        clean_result.valid = True
        clean_result.violations = []
        engine.validate.side_effect = [None, clean_result]
        engine.strict = True

        models = GovernedAsyncModels(client, engine, "test-agent")
        result = await models.generate_content(model="gemini", contents="hello")
        assert result == mock_response


class TestGovernedGenAIInit:
    """Lines 34-36, 197: GovernedGenAI.__init__ without google-genai installed."""

    def test_import_error_when_genai_unavailable(self) -> None:
        from acgs_lite.integrations import google_genai as mod

        original = mod.GENAI_AVAILABLE
        try:
            mod.GENAI_AVAILABLE = False
            with pytest.raises(ImportError, match="google-genai"):
                mod.GovernedGenAI(api_key="fake")
        finally:
            mod.GENAI_AVAILABLE = original

    def test_stats_property(self) -> None:
        """Line 197 area: stats property."""
        from acgs_lite.integrations.google_genai import GovernedGenAI

        with (
            patch("acgs_lite.integrations.google_genai.GENAI_AVAILABLE", True),
            patch("acgs_lite.integrations.google_genai.GenAIClient") as mock_client_cls,
        ):
            mock_client_cls.return_value = MagicMock()
            client = GovernedGenAI(api_key="fake-key")
            stats = client.stats
            assert "agent_id" in stats
            assert stats["agent_id"] == "gemini-agent"
            assert "audit_chain_valid" in stats

    def test_generate_content_convenience(self) -> None:
        """GovernedGenAI.generate_content delegates to models."""
        from acgs_lite.integrations.google_genai import GovernedGenAI

        with (
            patch("acgs_lite.integrations.google_genai.GENAI_AVAILABLE", True),
            patch("acgs_lite.integrations.google_genai.GenAIClient") as mock_client_cls,
        ):
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "hi"
            mock_instance.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_instance

            client = GovernedGenAI(api_key="fake-key", strict=False)
            result = client.generate_content(model="gemini", contents="hello")
            assert result == mock_response
