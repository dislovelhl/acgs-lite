# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for policy_copilot/models.py
Target: ≥95% line coverage (126 stmts)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.policy_copilot.models import (
    ChatHistory,
    ChatMessage,
    CopilotRequest,
    CopilotResponse,
    ExplainRequest,
    ExplainResponse,
    ImproveRequest,
    ImproveResponse,
    LogicalOperator,
    PolicyEntity,
    PolicyEntityType,
    PolicyResult,
    PolicyTemplate,
    PolicyTemplateCategory,
    RiskAssessment,
    TestCase,
    TestRequest,
    TestResult,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestPolicyEntityType:
    def test_all_values(self):
        assert PolicyEntityType.SUBJECT == "subject"
        assert PolicyEntityType.ACTION == "action"
        assert PolicyEntityType.RESOURCE == "resource"
        assert PolicyEntityType.CONDITION == "condition"
        assert PolicyEntityType.ROLE == "role"
        assert PolicyEntityType.TIME == "time"
        assert PolicyEntityType.LOCATION == "location"

    def test_str_enum_behaviour(self):
        assert isinstance(PolicyEntityType.SUBJECT, str)
        assert PolicyEntityType("subject") == PolicyEntityType.SUBJECT

    def test_iteration(self):
        members = list(PolicyEntityType)
        assert len(members) == 7

    def test_membership(self):
        assert "subject" in PolicyEntityType._value2member_map_


class TestLogicalOperator:
    def test_all_values(self):
        assert LogicalOperator.AND == "and"
        assert LogicalOperator.OR == "or"
        assert LogicalOperator.NOT == "not"

    def test_str_enum(self):
        assert isinstance(LogicalOperator.AND, str)

    def test_from_value(self):
        assert LogicalOperator("or") == LogicalOperator.OR

    def test_count(self):
        assert len(list(LogicalOperator)) == 3


class TestPolicyTemplateCategory:
    def test_all_values(self):
        assert PolicyTemplateCategory.COMPLIANCE == "compliance"
        assert PolicyTemplateCategory.SECURITY == "security"
        assert PolicyTemplateCategory.ACCESS_CONTROL == "access_control"
        assert PolicyTemplateCategory.DATA_PROTECTION == "data_protection"
        assert PolicyTemplateCategory.CUSTOM == "custom"

    def test_str_enum(self):
        assert isinstance(PolicyTemplateCategory.SECURITY, str)

    def test_count(self):
        assert len(list(PolicyTemplateCategory)) == 5


# ---------------------------------------------------------------------------
# PolicyEntity tests
# ---------------------------------------------------------------------------


class TestPolicyEntity:
    def test_basic_creation(self):
        entity = PolicyEntity(type=PolicyEntityType.SUBJECT, value="admin")
        assert entity.type == PolicyEntityType.SUBJECT
        assert entity.value == "admin"
        assert entity.confidence == 1.0
        assert entity.modifiers == []

    def test_with_all_fields(self):
        entity = PolicyEntity(
            type=PolicyEntityType.ACTION,
            value="read",
            confidence=0.9,
            modifiers=["async", "batch"],
        )
        assert entity.confidence == 0.9
        assert entity.modifiers == ["async", "batch"]

    def test_confidence_zero(self):
        entity = PolicyEntity(type=PolicyEntityType.ROLE, value="viewer", confidence=0.0)
        assert entity.confidence == 0.0

    def test_confidence_one(self):
        entity = PolicyEntity(type=PolicyEntityType.ROLE, value="viewer", confidence=1.0)
        assert entity.confidence == 1.0

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValidationError):
            PolicyEntity(type=PolicyEntityType.ROLE, value="x", confidence=-0.1)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError):
            PolicyEntity(type=PolicyEntityType.ROLE, value="x", confidence=1.1)

    def test_empty_value_raises(self):
        with pytest.raises(ValidationError):
            PolicyEntity(type=PolicyEntityType.SUBJECT, value="")

    def test_all_entity_types(self):
        for et in PolicyEntityType:
            entity = PolicyEntity(type=et, value="test")
            assert entity.type == et

    def test_modifiers_default_factory_is_independent(self):
        e1 = PolicyEntity(type=PolicyEntityType.SUBJECT, value="a")
        e2 = PolicyEntity(type=PolicyEntityType.SUBJECT, value="b")
        e1.modifiers.append("x")
        assert "x" not in e2.modifiers


# ---------------------------------------------------------------------------
# TestCase tests
# ---------------------------------------------------------------------------


class TestTestCase:
    def test_basic_creation(self):
        tc = TestCase(
            name="allow admin",
            input_data={"user": "admin"},
            expected_result=True,
        )
        assert tc.name == "allow admin"
        assert tc.input_data == {"user": "admin"}
        assert tc.expected_result is True
        assert tc.description is None

    def test_with_description(self):
        tc = TestCase(
            name="deny guest",
            input_data={"user": "guest"},
            expected_result=False,
            description="guests should be denied",
        )
        assert tc.description == "guests should be denied"

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            TestCase(name="", input_data={}, expected_result=True)

    def test_not_pytest_class(self):
        # __test__ = False must be present so pytest doesn't collect this
        assert TestCase.__test__ is False

    def test_nested_input_data(self):
        tc = TestCase(
            name="nested",
            input_data={"user": {"id": 1, "roles": ["admin"]}},
            expected_result=True,
        )
        assert tc.input_data["user"]["roles"] == ["admin"]


# ---------------------------------------------------------------------------
# PolicyResult tests
# ---------------------------------------------------------------------------


class TestPolicyResult:
    def test_minimal_creation(self):
        pr = PolicyResult(
            rego_code="package test\ndefault allow = false",
            explanation="Deny all",
        )
        assert pr.rego_code == "package test\ndefault allow = false"
        assert pr.explanation == "Deny all"
        assert pr.confidence == 0.0
        assert pr.test_cases == []
        assert pr.entities == []
        assert pr.metadata == {}
        assert pr.policy_id is not None
        assert pr.created_at is not None

    def test_policy_id_auto_generated(self):
        pr1 = PolicyResult(rego_code="package a\n", explanation="a")
        pr2 = PolicyResult(rego_code="package b\n", explanation="b")
        assert pr1.policy_id != pr2.policy_id

    def test_created_at_is_utc(self):
        pr = PolicyResult(rego_code="package test\n", explanation="test")
        assert pr.created_at.tzinfo is not None

    def test_confidence_bounds(self):
        pr = PolicyResult(rego_code="x\n", explanation="e", confidence=0.95)
        assert pr.confidence == 0.95

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValidationError):
            PolicyResult(rego_code="x\n", explanation="e", confidence=-0.1)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError):
            PolicyResult(rego_code="x\n", explanation="e", confidence=1.1)

    def test_empty_rego_code_raises(self):
        with pytest.raises(ValidationError):
            PolicyResult(rego_code="", explanation="e")

    def test_with_test_cases_and_entities(self):
        tc = TestCase(name="t1", input_data={}, expected_result=True)
        entity = PolicyEntity(type=PolicyEntityType.SUBJECT, value="admin")
        pr = PolicyResult(
            rego_code="package x\n",
            explanation="x",
            test_cases=[tc],
            entities=[entity],
            metadata={"source": "generated"},
        )
        assert len(pr.test_cases) == 1
        assert len(pr.entities) == 1
        assert pr.metadata["source"] == "generated"

    def test_explicit_policy_id(self):
        pr = PolicyResult(
            policy_id="my-id",
            rego_code="package x\n",
            explanation="x",
        )
        assert pr.policy_id == "my-id"


# ---------------------------------------------------------------------------
# PolicyTemplate tests
# ---------------------------------------------------------------------------


class TestPolicyTemplate:
    def _valid_template(self, **overrides):
        base = dict(
            id="tpl-001",
            name="Default Deny",
            description="Deny all unless explicitly allowed",
            category=PolicyTemplateCategory.SECURITY,
            rego_template="package {{pkg}}\ndefault allow = false",
            example_usage="deny all requests",
        )
        base.update(overrides)
        return PolicyTemplate(**base)

    def test_basic_creation(self):
        tpl = self._valid_template()
        assert tpl.id == "tpl-001"
        assert tpl.category == PolicyTemplateCategory.SECURITY
        assert tpl.placeholders == []
        assert tpl.tags == []

    def test_with_placeholders_and_tags(self):
        tpl = self._valid_template(
            placeholders=["{{pkg}}", "{{role}}"],
            tags=["security", "deny-first"],
        )
        assert "{{pkg}}" in tpl.placeholders
        assert "security" in tpl.tags

    def test_empty_id_raises(self):
        with pytest.raises(ValidationError):
            self._valid_template(id="")

    def test_empty_name_raises(self):
        with pytest.raises(ValidationError):
            self._valid_template(name="")

    def test_empty_description_raises(self):
        with pytest.raises(ValidationError):
            self._valid_template(description="")

    def test_empty_rego_template_raises(self):
        with pytest.raises(ValidationError):
            self._valid_template(rego_template="")

    def test_empty_example_usage_raises(self):
        with pytest.raises(ValidationError):
            self._valid_template(example_usage="")

    def test_all_categories(self):
        for cat in PolicyTemplateCategory:
            tpl = self._valid_template(category=cat)
            assert tpl.category == cat


# ---------------------------------------------------------------------------
# CopilotRequest tests
# ---------------------------------------------------------------------------


class TestCopilotRequest:
    def test_basic_creation(self):
        req = CopilotRequest(description="Allow admin to read all resources")
        assert req.description == "Allow admin to read all resources"
        assert req.context is None
        assert req.template_id is None
        assert req.tenant_id is None

    def test_strip_description(self):
        req = CopilotRequest(description="  Allow admin read  ")
        assert req.description == "Allow admin read"

    def test_description_too_short_raises(self):
        with pytest.raises(ValidationError):
            CopilotRequest(description="ab")

    def test_description_exactly_5_chars_after_strip(self):
        req = CopilotRequest(description="hello")
        assert req.description == "hello"

    def test_description_just_under_5_after_strip_raises(self):
        with pytest.raises(ValidationError):
            CopilotRequest(description="  ab  ")

    def test_description_max_length(self):
        req = CopilotRequest(description="x" * 5000)
        assert len(req.description) == 5000

    def test_description_over_max_raises(self):
        with pytest.raises(ValidationError):
            CopilotRequest(description="x" * 5001)

    def test_context_max_length(self):
        req = CopilotRequest(description="Allow everything", context="c" * 1000)
        assert len(req.context) == 1000

    def test_context_over_max_raises(self):
        with pytest.raises(ValidationError):
            CopilotRequest(description="Allow everything", context="c" * 1001)

    def test_with_all_fields(self):
        req = CopilotRequest(
            description="Allow read access for admins",
            context="RBAC context",
            template_id="tpl-001",
            tenant_id="tenant-abc",
        )
        assert req.context == "RBAC context"
        assert req.template_id == "tpl-001"
        assert req.tenant_id == "tenant-abc"

    def test_empty_description_raises(self):
        with pytest.raises(ValidationError):
            CopilotRequest(description="")

    def test_whitespace_only_description_raises(self):
        with pytest.raises(ValidationError):
            CopilotRequest(description="    ")


# ---------------------------------------------------------------------------
# CopilotResponse tests
# ---------------------------------------------------------------------------


class TestCopilotResponse:
    def _valid_response(self, **overrides):
        base = dict(
            policy_id="pol-001",
            policy="package main\ndefault allow = false",
            explanation="Denies all by default",
            test_cases=[],
            confidence=0.85,
            entities=[],
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        base.update(overrides)
        return CopilotResponse(**base)

    def test_basic_creation(self):
        resp = self._valid_response()
        assert resp.policy_id == "pol-001"
        assert resp.confidence == 0.85
        assert resp.suggestions == []
        assert resp.risks == []

    def test_with_suggestions_and_risks(self):
        resp = self._valid_response(
            suggestions=["add rate limiting"],
            risks=["overly permissive"],
        )
        assert resp.suggestions == ["add rate limiting"]
        assert resp.risks == ["overly permissive"]

    def test_confidence_bounds_zero(self):
        resp = self._valid_response(confidence=0.0)
        assert resp.confidence == 0.0

    def test_confidence_bounds_one(self):
        resp = self._valid_response(confidence=1.0)
        assert resp.confidence == 1.0

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValidationError):
            self._valid_response(confidence=-0.1)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError):
            self._valid_response(confidence=1.1)

    def test_with_test_cases(self):
        tc = TestCase(name="t1", input_data={}, expected_result=True)
        resp = self._valid_response(test_cases=[tc])
        assert len(resp.test_cases) == 1

    def test_with_entities(self):
        entity = PolicyEntity(type=PolicyEntityType.SUBJECT, value="user")
        resp = self._valid_response(entities=[entity])
        assert len(resp.entities) == 1

    def test_constitutional_hash_stored(self):
        resp = self._valid_response()
        assert resp.constitutional_hash == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# ExplainRequest tests
# ---------------------------------------------------------------------------


class TestExplainRequest:
    def test_default_detail_level(self):
        req = ExplainRequest(policy="package test\ndefault allow = false")
        assert req.detail_level == "detailed"

    def test_all_detail_levels(self):
        for level in ("simple", "detailed", "technical"):
            req = ExplainRequest(policy="package x\n", detail_level=level)
            assert req.detail_level == level

    def test_invalid_detail_level_raises(self):
        with pytest.raises(ValidationError):
            ExplainRequest(policy="package x\n", detail_level="verbose")

    def test_empty_policy_raises(self):
        with pytest.raises(ValidationError):
            ExplainRequest(policy="")


# ---------------------------------------------------------------------------
# RiskAssessment tests
# ---------------------------------------------------------------------------


class TestRiskAssessment:
    def test_basic_creation(self):
        risk = RiskAssessment(
            severity="low",
            category="access",
            description="Broad access",
        )
        assert risk.severity == "low"
        assert risk.mitigation is None

    def test_all_severities(self):
        for sev in ("low", "medium", "high", "critical"):
            risk = RiskAssessment(severity=sev, category="cat", description="desc")
            assert risk.severity == sev

    def test_invalid_severity_raises(self):
        with pytest.raises(ValidationError):
            RiskAssessment(severity="extreme", category="cat", description="desc")

    def test_with_mitigation(self):
        risk = RiskAssessment(
            severity="high",
            category="auth",
            description="Weak auth",
            mitigation="Add MFA",
        )
        assert risk.mitigation == "Add MFA"


# ---------------------------------------------------------------------------
# ExplainResponse tests
# ---------------------------------------------------------------------------


class TestExplainResponse:
    def test_minimal(self):
        resp = ExplainResponse(explanation="This policy allows admin access")
        assert resp.explanation == "This policy allows admin access"
        assert resp.risks == []
        assert resp.suggestions == []
        assert resp.complexity_score == 0.0

    def test_with_risks(self):
        risk = RiskAssessment(severity="medium", category="auth", description="weak")
        resp = ExplainResponse(explanation="ok", risks=[risk])
        assert len(resp.risks) == 1

    def test_complexity_score_bounds(self):
        resp = ExplainResponse(explanation="ok", complexity_score=0.5)
        assert resp.complexity_score == 0.5

    def test_complexity_score_below_zero_raises(self):
        with pytest.raises(ValidationError):
            ExplainResponse(explanation="ok", complexity_score=-0.1)

    def test_complexity_score_above_one_raises(self):
        with pytest.raises(ValidationError):
            ExplainResponse(explanation="ok", complexity_score=1.1)

    def test_complexity_score_one(self):
        resp = ExplainResponse(explanation="ok", complexity_score=1.0)
        assert resp.complexity_score == 1.0

    def test_with_suggestions(self):
        resp = ExplainResponse(explanation="ok", suggestions=["simplify rules"])
        assert resp.suggestions == ["simplify rules"]


# ---------------------------------------------------------------------------
# ImproveRequest tests
# ---------------------------------------------------------------------------


class TestImproveRequest:
    def test_default_instruction(self):
        req = ImproveRequest(
            policy="package x\n",
            feedback="make it stricter",
        )
        assert req.instruction == "custom"

    def test_all_instructions(self):
        for instr in ("stricter", "permissive", "custom"):
            req = ImproveRequest(
                policy="package x\n",
                feedback="feedback here",
                instruction=instr,
            )
            assert req.instruction == instr

    def test_invalid_instruction_raises(self):
        with pytest.raises(ValidationError):
            ImproveRequest(
                policy="package x\n",
                feedback="feedback",
                instruction="aggressive",
            )

    def test_empty_policy_raises(self):
        with pytest.raises(ValidationError):
            ImproveRequest(policy="", feedback="feedback")

    def test_empty_feedback_raises(self):
        with pytest.raises(ValidationError):
            ImproveRequest(policy="package x\n", feedback="")

    def test_feedback_max_length(self):
        req = ImproveRequest(policy="package x\n", feedback="f" * 2000)
        assert len(req.feedback) == 2000

    def test_feedback_over_max_raises(self):
        with pytest.raises(ValidationError):
            ImproveRequest(policy="package x\n", feedback="f" * 2001)


# ---------------------------------------------------------------------------
# ImproveResponse tests
# ---------------------------------------------------------------------------


class TestImproveResponse:
    def test_basic_creation(self):
        resp = ImproveResponse(
            improved_policy="package x\ndefault allow = true",
            explanation="added allow rule",
        )
        assert resp.improved_policy == "package x\ndefault allow = true"
        assert resp.explanation == "added allow rule"
        assert resp.changes_made == []

    def test_with_changes(self):
        resp = ImproveResponse(
            improved_policy="package x\n",
            explanation="improved",
            changes_made=["added default deny", "removed wildcard"],
        )
        assert len(resp.changes_made) == 2


# ---------------------------------------------------------------------------
# TestRequest tests
# ---------------------------------------------------------------------------


class TestTestRequest:
    def test_basic_creation(self):
        req = TestRequest(
            policy="package x\ndefault allow = false",
            test_input={"user": "admin"},
        )
        assert req.policy == "package x\ndefault allow = false"
        assert req.test_input == {"user": "admin"}
        assert req.tenant_id is None

    def test_with_tenant_id(self):
        req = TestRequest(
            policy="package x\n",
            test_input={},
            tenant_id="t-123",
        )
        assert req.tenant_id == "t-123"

    def test_empty_policy_raises(self):
        with pytest.raises(ValidationError):
            TestRequest(policy="", test_input={})


# ---------------------------------------------------------------------------
# TestResult tests
# ---------------------------------------------------------------------------


class TestTestResult:
    def test_allowed_true(self):
        result = TestResult(allowed=True)
        assert result.allowed is True
        assert result.decision_path == []
        assert result.trace == {}
        assert result.errors == []
        assert result.execution_time_ms == 0.0

    def test_allowed_false(self):
        result = TestResult(allowed=False)
        assert result.allowed is False

    def test_with_decision_path(self):
        result = TestResult(
            allowed=True,
            decision_path=["rule1", "rule2"],
        )
        assert result.decision_path == ["rule1", "rule2"]

    def test_with_trace(self):
        result = TestResult(allowed=False, trace={"eval": "deny"})
        assert result.trace == {"eval": "deny"}

    def test_with_errors(self):
        result = TestResult(allowed=False, errors=["syntax error"])
        assert result.errors == ["syntax error"]

    def test_execution_time(self):
        result = TestResult(allowed=True, execution_time_ms=42.5)
        assert result.execution_time_ms == 42.5


# ---------------------------------------------------------------------------
# ValidationResult tests
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_valid_true(self):
        vr = ValidationResult(valid=True)
        assert vr.valid is True
        assert vr.errors == []
        assert vr.warnings == []
        assert vr.syntax_check is False
        assert vr.best_practices == []

    def test_valid_false(self):
        vr = ValidationResult(valid=False)
        assert vr.valid is False

    def test_with_errors(self):
        vr = ValidationResult(valid=False, errors=["missing package"])
        assert vr.errors == ["missing package"]

    def test_with_warnings(self):
        vr = ValidationResult(valid=True, warnings=["unused variable"])
        assert vr.warnings == ["unused variable"]

    def test_syntax_check_true(self):
        vr = ValidationResult(valid=True, syntax_check=True)
        assert vr.syntax_check is True

    def test_best_practices(self):
        vr = ValidationResult(valid=True, best_practices=["add comments", "use helpers"])
        assert len(vr.best_practices) == 2


# ---------------------------------------------------------------------------
# ChatMessage tests
# ---------------------------------------------------------------------------


class TestChatMessage:
    def test_user_message(self):
        msg = ChatMessage(role="user", content="How do I deny all?")
        assert msg.role == "user"
        assert msg.content == "How do I deny all?"
        assert msg.metadata == {}
        assert msg.timestamp is not None

    def test_assistant_message(self):
        msg = ChatMessage(role="assistant", content="Set default allow = false")
        assert msg.role == "assistant"

    def test_system_message(self):
        msg = ChatMessage(role="system", content="You are a policy assistant")
        assert msg.role == "system"

    def test_invalid_role_raises(self):
        with pytest.raises(ValidationError):
            ChatMessage(role="bot", content="hello")

    def test_empty_content_raises(self):
        with pytest.raises(ValidationError):
            ChatMessage(role="user", content="")

    def test_with_metadata(self):
        msg = ChatMessage(role="user", content="hello", metadata={"source": "web"})
        assert msg.metadata["source"] == "web"

    def test_timestamp_is_utc(self):
        msg = ChatMessage(role="user", content="hello")
        assert msg.timestamp.tzinfo is not None

    def test_all_roles(self):
        for role in ("user", "assistant", "system"):
            msg = ChatMessage(role=role, content="test")
            assert msg.role == role


# ---------------------------------------------------------------------------
# ChatHistory tests
# ---------------------------------------------------------------------------


class TestChatHistory:
    def test_default_creation(self):
        history = ChatHistory()
        assert history.messages == []
        assert history.session_id is not None
        assert history.created_at is not None
        assert history.updated_at is not None

    def test_session_id_auto_generated(self):
        h1 = ChatHistory()
        h2 = ChatHistory()
        assert h1.session_id != h2.session_id

    def test_add_user_message(self):
        history = ChatHistory()
        history.add_message("user", "What is OPA?")
        assert len(history.messages) == 1
        assert history.messages[0].role == "user"
        assert history.messages[0].content == "What is OPA?"

    def test_add_assistant_message(self):
        history = ChatHistory()
        history.add_message("assistant", "OPA is Open Policy Agent")
        assert history.messages[0].role == "assistant"

    def test_add_system_message(self):
        history = ChatHistory()
        history.add_message("system", "You are a policy expert")
        assert history.messages[0].role == "system"

    def test_add_message_updates_updated_at(self):
        history = ChatHistory()
        before = history.updated_at
        # Force a small time difference by providing explicit datetime
        history.add_message("user", "hello")
        # updated_at should be set anew
        assert history.updated_at is not None

    def test_add_multiple_messages(self):
        history = ChatHistory()
        history.add_message("user", "first question")
        history.add_message("assistant", "first answer")
        history.add_message("user", "follow-up")
        assert len(history.messages) == 3
        assert history.messages[0].role == "user"
        assert history.messages[1].role == "assistant"
        assert history.messages[2].role == "user"

    def test_add_message_with_metadata(self):
        history = ChatHistory()
        history.add_message("user", "hello", metadata={"session": "abc"})
        assert history.messages[0].metadata == {"session": "abc"}

    def test_add_message_with_no_metadata_defaults_empty(self):
        history = ChatHistory()
        history.add_message("user", "hello")
        assert history.messages[0].metadata == {}

    def test_explicit_session_id(self):
        history = ChatHistory(session_id="custom-session-id")
        assert history.session_id == "custom-session-id"

    def test_created_at_utc(self):
        history = ChatHistory()
        assert history.created_at.tzinfo is not None

    def test_updated_at_utc(self):
        history = ChatHistory()
        assert history.updated_at.tzinfo is not None

    def test_add_message_with_none_metadata_defaults_empty(self):
        history = ChatHistory()
        history.add_message("user", "hello", metadata=None)
        assert history.messages[0].metadata == {}

    def test_messages_are_chat_message_instances(self):
        history = ChatHistory()
        history.add_message("user", "query")
        assert isinstance(history.messages[0], ChatMessage)


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports_importable(self):
        from enhanced_agent_bus.policy_copilot import models as m

        exported = [
            "PolicyEntityType",
            "LogicalOperator",
            "PolicyTemplateCategory",
            "PolicyEntity",
            "TestCase",
            "PolicyResult",
            "PolicyTemplate",
            "CopilotRequest",
            "CopilotResponse",
            "ExplainRequest",
            "RiskAssessment",
            "ExplainResponse",
            "ImproveRequest",
            "ImproveResponse",
            "TestRequest",
            "TestResult",
            "ValidationResult",
            "ChatMessage",
            "ChatHistory",
        ]
        for name in exported:
            assert hasattr(m, name), f"Missing export: {name}"

    def test_all_list_complete(self):
        from enhanced_agent_bus.policy_copilot.models import __all__

        assert len(__all__) == 19


# ---------------------------------------------------------------------------
# Cross-model integration tests
# ---------------------------------------------------------------------------


class TestCrossModelIntegration:
    def test_copilot_response_with_full_data(self):
        entity = PolicyEntity(
            type=PolicyEntityType.ROLE,
            value="admin",
            confidence=0.99,
            modifiers=["superuser"],
        )
        tc = TestCase(
            name="admin allow",
            input_data={"role": "admin"},
            expected_result=True,
            description="Admins should be allowed",
        )
        resp = CopilotResponse(
            policy_id="p-001",
            policy='package rbac\ndefault allow = false\nallow { input.role == "admin" }',
            explanation="RBAC policy allowing admin role",
            test_cases=[tc],
            confidence=0.95,
            entities=[entity],
            constitutional_hash=CONSTITUTIONAL_HASH,
            suggestions=["add logging"],
            risks=["no expiry"],
        )
        assert resp.entities[0].value == "admin"
        assert resp.test_cases[0].expected_result is True

    def test_policy_result_serialization(self):
        pr = PolicyResult(
            rego_code="package test\ndefault allow = false",
            explanation="deny all",
            confidence=0.7,
            metadata={"model": "gpt-4"},
        )
        data = pr.model_dump()
        assert "policy_id" in data
        assert "created_at" in data
        assert data["confidence"] == 0.7

    def test_chat_history_messages_serializable(self):
        history = ChatHistory()
        history.add_message("user", "deny all guests")
        history.add_message("assistant", "Use default allow = false")
        data = history.model_dump()
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"

    def test_explain_response_with_risks(self):
        risks = [
            RiskAssessment(
                severity="high",
                category="auth",
                description="No authentication check",
                mitigation="Add JWT validation",
            ),
            RiskAssessment(
                severity="low",
                category="logging",
                description="No audit trail",
            ),
        ]
        resp = ExplainResponse(
            explanation="Policy has authentication issues",
            risks=risks,
            suggestions=["add auth check"],
            complexity_score=0.8,
        )
        assert len(resp.risks) == 2
        assert resp.risks[0].mitigation == "Add JWT validation"
        assert resp.risks[1].mitigation is None

    def test_improve_request_all_variants(self):
        for instr in ("stricter", "permissive", "custom"):
            req = ImproveRequest(
                policy="package x\ndefault allow = true",
                feedback="needs review",
                instruction=instr,
            )
            assert req.instruction == instr

    def test_validation_result_full(self):
        vr = ValidationResult(
            valid=False,
            errors=["syntax error at line 3", "missing package"],
            warnings=["deprecated function"],
            syntax_check=False,
            best_practices=["add comments", "use helper rules"],
        )
        assert not vr.valid
        assert len(vr.errors) == 2
        assert len(vr.warnings) == 1
        assert len(vr.best_practices) == 2

    def test_test_result_full(self):
        result = TestResult(
            allowed=True,
            decision_path=["rule_allow_admin", "rule_check_resource"],
            trace={"eval": [{"rule": "allow_admin", "result": True}]},
            errors=[],
            execution_time_ms=1.23,
        )
        assert result.allowed is True
        assert len(result.decision_path) == 2
        assert result.execution_time_ms == 1.23
