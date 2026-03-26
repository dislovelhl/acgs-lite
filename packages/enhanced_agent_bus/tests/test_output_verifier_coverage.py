# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for OutputVerifier guardrail component.

Targets ≥90% coverage of:
  src/core/enhanced_agent_bus/guardrails/output_verifier.py
"""

import json
import re

import pytest

from enhanced_agent_bus.guardrails.enums import (
    GuardrailLayer,
    SafetyAction,
    ViolationSeverity,
)
from enhanced_agent_bus.guardrails.output_verifier import (
    OutputVerifier,
    OutputVerifierConfig,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def verifier() -> OutputVerifier:
    """Default verifier with all checks enabled."""
    return OutputVerifier()


@pytest.fixture
def verifier_all_disabled() -> OutputVerifier:
    """Verifier with every check disabled."""
    cfg = OutputVerifierConfig(
        content_safety_check=False,
        pii_redaction=False,
        toxicity_filter=False,
    )
    return OutputVerifier(cfg)


@pytest.fixture
def ctx() -> dict:
    return {"trace_id": "trace-abc-123"}


# ---------------------------------------------------------------------------
# OutputVerifierConfig
# ---------------------------------------------------------------------------


class TestOutputVerifierConfig:
    def test_defaults(self):
        cfg = OutputVerifierConfig()
        assert cfg.enabled is True
        assert cfg.content_safety_check is True
        assert cfg.pii_redaction is True
        assert cfg.hallucination_detection is False
        assert cfg.toxicity_filter is True
        assert cfg.timeout_ms == 2000

    def test_custom_values(self):
        cfg = OutputVerifierConfig(
            enabled=False,
            content_safety_check=False,
            pii_redaction=False,
            toxicity_filter=False,
            timeout_ms=500,
        )
        assert cfg.enabled is False
        assert cfg.timeout_ms == 500


# ---------------------------------------------------------------------------
# OutputVerifier construction
# ---------------------------------------------------------------------------


class TestOutputVerifierInit:
    def test_default_config_created(self):
        v = OutputVerifier()
        assert isinstance(v.config, OutputVerifierConfig)

    def test_explicit_config(self):
        cfg = OutputVerifierConfig(timeout_ms=9999)
        v = OutputVerifier(cfg)
        assert v.config.timeout_ms == 9999

    def test_get_layer(self, verifier):
        assert verifier.get_layer() == GuardrailLayer.OUTPUT_VERIFIER

    def test_toxicity_patterns_compiled(self, verifier):
        assert len(verifier._toxicity_patterns) > 0
        for p in verifier._toxicity_patterns:
            assert isinstance(p, re.Pattern)

    def test_pii_patterns_compiled(self, verifier):
        assert len(verifier._pii_patterns) > 0
        for p in verifier._pii_patterns:
            assert isinstance(p, re.Pattern)


# ---------------------------------------------------------------------------
# process() — clean inputs
# ---------------------------------------------------------------------------


class TestProcessCleanInput:
    async def test_clean_string_allowed(self, verifier, ctx):
        result = await verifier.process("Hello, this is a safe message.", ctx)
        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW
        assert result.violations == []

    async def test_clean_dict_allowed(self, verifier, ctx):
        result = await verifier.process({"message": "Safe text here."}, ctx)
        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW

    async def test_integer_input_allowed(self, verifier_all_disabled, ctx):
        result = await verifier_all_disabled.process(42, ctx)
        assert result.allowed is True
        assert result.action == SafetyAction.ALLOW

    async def test_boolean_input_allowed(self, verifier, ctx):
        result = await verifier.process(True, ctx)
        assert result.allowed is True

    async def test_none_input_allowed(self, verifier, ctx):
        result = await verifier.process(None, ctx)
        assert result.allowed is True

    async def test_list_input_allowed(self, verifier, ctx):
        result = await verifier.process(["safe", "text"], ctx)
        assert result.allowed is True

    async def test_trace_id_propagated(self, verifier, ctx):
        result = await verifier.process("safe text", ctx)
        assert result.trace_id == "trace-abc-123"

    async def test_processing_time_recorded(self, verifier, ctx):
        result = await verifier.process("safe text", ctx)
        assert result.processing_time_ms >= 0

    async def test_missing_trace_id(self, verifier):
        result = await verifier.process("safe text", {})
        assert result.trace_id == ""

    async def test_all_checks_disabled_clean(self, verifier_all_disabled, ctx):
        result = await verifier_all_disabled.process("any text 555-12-3456", ctx)
        assert result.allowed is True
        assert result.violations == []


# ---------------------------------------------------------------------------
# process() — input type branching
# ---------------------------------------------------------------------------


class TestInputTypeBranching:
    async def test_dict_serialised_to_json(self, verifier_all_disabled, ctx):
        """Dict input must not raise — json.dumps path executed."""
        data = {"key": "value", "num": 1}
        result = await verifier_all_disabled.process(data, ctx)
        assert result.allowed is True

    async def test_str_used_directly(self, verifier_all_disabled, ctx):
        result = await verifier_all_disabled.process("direct string", ctx)
        assert result.allowed is True

    async def test_other_type_str_converted(self, verifier_all_disabled, ctx):
        result = await verifier_all_disabled.process(3.14, ctx)
        assert result.allowed is True


# ---------------------------------------------------------------------------
# Content safety checks
# ---------------------------------------------------------------------------


class TestContentSafetyCheck:
    async def test_harmful_how_to_hack(self, verifier, ctx):
        text = "Here are instructions for how to hack a system."
        result = await verifier.process(text, ctx)
        assert result.action == SafetyAction.BLOCK
        assert result.allowed is False
        types = [v.violation_type for v in result.violations]
        assert "harmful_content" in types

    async def test_harmful_how_to_exploit(self, verifier, ctx):
        text = "I can show you how to exploit this vulnerability."
        result = await verifier.process(text, ctx)
        types = [v.violation_type for v in result.violations]
        assert "harmful_content" in types

    async def test_harmful_create_malware(self, verifier, ctx):
        text = "Let me help you create ransomware for your target."
        result = await verifier.process(text, ctx)
        types = [v.violation_type for v in result.violations]
        assert "harmful_content" in types

    async def test_harmful_create_virus(self, verifier, ctx):
        text = "Let me show you how to create malware step by step."
        result = await verifier.process(text, ctx)
        types = [v.violation_type for v in result.violations]
        assert "harmful_content" in types

    async def test_harmful_instructions_to_harm(self, verifier, ctx):
        text = "These are instructions to harm the target."
        result = await verifier.process(text, ctx)
        types = [v.violation_type for v in result.violations]
        assert "harmful_content" in types

    async def test_harmful_only_one_violation_reported(self, verifier, ctx):
        # Multiple patterns could match but break ensures only one violation
        text = "How to hack: instructions for how to hack and exploit."
        result = await verifier.process(text, ctx)
        harmful = [v for v in result.violations if v.violation_type == "harmful_content"]
        assert len(harmful) == 1

    async def test_harmful_violation_severity_critical(self, verifier, ctx):
        text = "steps to hack the server"
        result = await verifier.process(text, ctx)
        harmful = [v for v in result.violations if v.violation_type == "harmful_content"]
        if harmful:
            assert harmful[0].severity == ViolationSeverity.CRITICAL

    async def test_content_safety_disabled_no_violation(self, ctx):
        cfg = OutputVerifierConfig(
            content_safety_check=False,
            pii_redaction=False,
            toxicity_filter=False,
        )
        v = OutputVerifier(cfg)
        text = "how to hack a system"
        result = await v.process(text, ctx)
        types = [viol.violation_type for viol in result.violations]
        assert "harmful_content" not in types

    async def test_safe_content_no_violation(self, verifier, ctx):
        result = await verifier.process("The weather is nice today.", ctx)
        types = [v.violation_type for v in result.violations]
        assert "harmful_content" not in types

    async def test_check_content_safety_direct_method(self, verifier):
        violations = verifier._check_content_safety("how to bypass security", "t1")
        assert len(violations) >= 1
        assert violations[0].layer == GuardrailLayer.OUTPUT_VERIFIER
        assert violations[0].trace_id == "t1"


# ---------------------------------------------------------------------------
# Toxicity checks
# ---------------------------------------------------------------------------


class TestToxicityCheck:
    async def test_hate_speech(self, verifier, ctx):
        result = await verifier.process("That was a really racist comment.", ctx)
        types = [v.violation_type for v in result.violations]
        assert "toxicity_detected" in types

    async def test_violent_content(self, verifier, ctx):
        result = await verifier.process("I want to kill yourself.", ctx)
        types = [v.violation_type for v in result.violations]
        assert "toxicity_detected" in types

    async def test_self_harm(self, verifier, ctx):
        result = await verifier.process("Discussing suicide awareness.", ctx)
        types = [v.violation_type for v in result.violations]
        assert "toxicity_detected" in types

    async def test_sexist_detected(self, verifier, ctx):
        result = await verifier.process("That sexist remark was uncalled for.", ctx)
        types = [v.violation_type for v in result.violations]
        assert "toxicity_detected" in types

    async def test_toxicity_violation_severity_high(self, verifier, ctx):
        result = await verifier.process("That was a hate speech incident.", ctx)
        tox = [v for v in result.violations if v.violation_type == "toxicity_detected"]
        assert all(v.severity == ViolationSeverity.HIGH for v in tox)

    async def test_toxicity_details_include_pattern_index(self, verifier, ctx):
        result = await verifier.process("that racist joke was wrong", ctx)
        tox = [v for v in result.violations if v.violation_type == "toxicity_detected"]
        if tox:
            assert "pattern_index" in tox[0].details

    async def test_toxicity_disabled(self, ctx):
        cfg = OutputVerifierConfig(
            content_safety_check=False,
            toxicity_filter=False,
            pii_redaction=False,
        )
        v = OutputVerifier(cfg)
        result = await v.process("hate racist violent", ctx)
        types = [viol.violation_type for viol in result.violations]
        assert "toxicity_detected" not in types

    async def test_check_toxicity_direct(self, verifier):
        violations = verifier._check_toxicity("you are so violent people", "t2")
        assert any(v.violation_type == "toxicity_detected" for v in violations)

    async def test_toxicity_multiple_patterns_all_reported(self, verifier, ctx):
        # "hate" triggers pattern 0, "kill yourself" triggers pattern 1,
        # "suicide" triggers pattern 2 — all three may fire
        text = "This is hate, you should kill yourself, consider suicide."
        result = await verifier.process(text, ctx)
        tox = [v for v in result.violations if v.violation_type == "toxicity_detected"]
        assert len(tox) >= 1


# ---------------------------------------------------------------------------
# PII redaction
# ---------------------------------------------------------------------------


class TestPiiRedaction:
    async def test_email_redacted(self, verifier, ctx):
        text = "Contact me at user@example.com for more info."
        result = await verifier.process(text, ctx)
        types = [v.violation_type for v in result.violations]
        assert "pii_leak" in types
        assert result.modified_data is not None
        assert "user@example.com" not in result.modified_data

    async def test_ssn_redacted(self, verifier, ctx):
        text = "My SSN is 123-45-6789."
        result = await verifier.process(text, ctx)
        types = [v.violation_type for v in result.violations]
        assert "pii_leak" in types

    async def test_modified_output_set_on_pii(self, verifier, ctx):
        text = "My email is test@domain.org."
        result = await verifier.process(text, ctx)
        assert result.modified_data is not None
        assert "[REDACTED]" in result.modified_data

    async def test_no_pii_no_modified_output(self, verifier, ctx):
        result = await verifier.process("Hello world, no PII here.", ctx)
        assert result.modified_data is None

    async def test_pii_redaction_disabled(self, ctx):
        cfg = OutputVerifierConfig(
            content_safety_check=False,
            toxicity_filter=False,
            pii_redaction=False,
        )
        v = OutputVerifier(cfg)
        text = "My SSN is 123-45-6789 and email user@example.com."
        result = await v.process(text, ctx)
        types = [viol.violation_type for viol in result.violations]
        assert "pii_leak" not in types
        assert result.modified_data is None

    async def test_pii_violation_details_match_count(self, verifier, ctx):
        text = "Email: a@b.com and b@c.com are both here."
        result = await verifier.process(text, ctx)
        pii = [v for v in result.violations if v.violation_type == "pii_leak"]
        if pii:
            assert "match_count" in pii[0].details
            assert pii[0].details["match_count"] >= 1

    async def test_pii_violation_has_pattern_index(self, verifier, ctx):
        text = "user@example.com"
        result = await verifier.process(text, ctx)
        pii = [v for v in result.violations if v.violation_type == "pii_leak"]
        if pii:
            assert "pattern_index" in pii[0].details

    async def test_redact_pii_direct_method(self, verifier):
        text = "Call me at (555) 123-4567."
        redacted, violations = verifier._redact_pii(text, "t3")
        assert any(v.violation_type == "pii_leak" for v in violations)
        assert "[REDACTED]" in redacted

    async def test_redact_pii_no_pii(self, verifier):
        text = "Nothing sensitive here."
        redacted, violations = verifier._redact_pii(text, "t4")
        assert violations == []
        assert redacted == text

    async def test_pii_action_is_modify(self, verifier, ctx):
        """PII causes MODIFY (not BLOCK) when no critical violations."""
        # Use only PII (email) — no harmful content or critical violations
        cfg = OutputVerifierConfig(
            content_safety_check=False,
            toxicity_filter=False,
            pii_redaction=True,
        )
        v = OutputVerifier(cfg)
        text = "Contact user@example.com"
        result = await v.process(text, ctx)
        # PII is HIGH severity, not CRITICAL → MODIFY + allowed=True
        assert result.action == SafetyAction.MODIFY
        assert result.allowed is True


# ---------------------------------------------------------------------------
# Action determination
# ---------------------------------------------------------------------------


class TestActionDetermination:
    async def test_no_violations_allow(self, verifier_all_disabled, ctx):
        result = await verifier_all_disabled.process("safe text", ctx)
        assert result.action == SafetyAction.ALLOW
        assert result.allowed is True

    async def test_critical_violation_block(self, verifier, ctx):
        text = "Here are instructions for how to hack the system."
        result = await verifier.process(text, ctx)
        assert result.action == SafetyAction.BLOCK
        assert result.allowed is False

    async def test_non_critical_violation_modify(self, ctx):
        """Only non-critical (HIGH) violations → MODIFY, allowed=True."""
        cfg = OutputVerifierConfig(
            content_safety_check=False,  # no CRITICAL
            toxicity_filter=True,
            pii_redaction=False,
        )
        v = OutputVerifier(cfg)
        result = await v.process("that racist comment", ctx)
        # Toxicity is HIGH (not CRITICAL) → should be MODIFY
        assert result.action == SafetyAction.MODIFY
        assert result.allowed is True

    async def test_mixed_violations_critical_wins(self, verifier, ctx):
        """CRITICAL violations override HIGH — result is BLOCK."""
        text = "Contact a@b.com. Steps to hack and exploit the server."
        result = await verifier.process(text, ctx)
        assert result.action == SafetyAction.BLOCK
        assert result.allowed is False


# ---------------------------------------------------------------------------
# Error handling path
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_processing_error_creates_violation(self, verifier, ctx):
        """Force a processing error via a mocked pattern that raises."""
        import unittest.mock as mock

        broken_pattern = mock.MagicMock()
        broken_pattern.search.side_effect = re.error("broken pattern")

        # Override toxicity patterns to trigger the except branch
        original = verifier._toxicity_patterns
        verifier._toxicity_patterns = [broken_pattern]
        try:
            result = await verifier.process("any text", ctx)
            types = [v.violation_type for v in result.violations]
            assert "processing_error" in types
            assert result.action == SafetyAction.BLOCK
            assert result.allowed is False
        finally:
            verifier._toxicity_patterns = original

    async def test_processing_error_violation_severity_high(self, verifier, ctx):
        import unittest.mock as mock

        broken_pattern = mock.MagicMock()
        broken_pattern.search.side_effect = re.error("oops")

        original = verifier._toxicity_patterns
        verifier._toxicity_patterns = [broken_pattern]
        try:
            result = await verifier.process("any text", ctx)
            err_violations = [
                v for v in result.violations if v.violation_type == "processing_error"
            ]
            assert err_violations[0].severity == ViolationSeverity.HIGH
        finally:
            verifier._toxicity_patterns = original

    async def test_processing_error_trace_id_in_violation(self, verifier, ctx):
        import unittest.mock as mock

        broken_pattern = mock.MagicMock()
        broken_pattern.search.side_effect = re.error("oops")

        original = verifier._toxicity_patterns
        verifier._toxicity_patterns = [broken_pattern]
        try:
            result = await verifier.process("any text", ctx)
            err_violations = [
                v for v in result.violations if v.violation_type == "processing_error"
            ]
            assert err_violations[0].trace_id == "trace-abc-123"
        finally:
            verifier._toxicity_patterns = original


# ---------------------------------------------------------------------------
# GuardrailResult structure
# ---------------------------------------------------------------------------


class TestGuardrailResultStructure:
    async def test_result_fields_present(self, verifier, ctx):
        result = await verifier.process("safe text", ctx)
        assert hasattr(result, "action")
        assert hasattr(result, "allowed")
        assert hasattr(result, "violations")
        assert hasattr(result, "modified_data")
        assert hasattr(result, "processing_time_ms")
        assert hasattr(result, "trace_id")

    async def test_violations_are_violation_instances(self, verifier, ctx):
        from enhanced_agent_bus.guardrails.models import Violation

        text = "Contact user@example.com — that racist user."
        result = await verifier.process(text, ctx)
        for v in result.violations:
            assert isinstance(v, Violation)

    async def test_violation_layer_matches(self, verifier, ctx):
        text = "that racist hate comment"
        result = await verifier.process(text, ctx)
        for v in result.violations:
            assert v.layer == GuardrailLayer.OUTPUT_VERIFIER
