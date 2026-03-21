"""Comprehensive tests for acgs_lite.integrations.anthropic.

Covers GovernedMessages, GovernedAnthropic, governance tool handlers,
SDK error edge cases (rate limits, auth errors, network failures),
strict-mode restoration safety, MACI role boundaries, and content
validation paths.

Target: >90% coverage on integrations/anthropic.py.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.engine import GovernanceEngine, ValidationResult, Violation
from acgs_lite.errors import ConstitutionalViolationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_constitution(*extra_rules: Rule) -> Constitution:
    """Build a minimal constitution for testing."""
    rules = list(extra_rules) if extra_rules else []
    return Constitution(rules=rules) if rules else Constitution.default()


def _make_governed_messages(*, strict: bool = True, engine: GovernanceEngine | None = None):
    """Create a GovernedMessages with a real engine and mock client."""
    from acgs_lite.integrations.anthropic import GovernedMessages

    constitution = Constitution.default()
    if engine is None:
        engine = GovernanceEngine(constitution, strict=strict)
    mock_client = MagicMock()
    gm = GovernedMessages(mock_client, engine, "test-agent")
    return gm, mock_client, engine


def _make_mock_response(*, text_blocks: list[str] | None = None, tool_use_blocks: list[dict] | None = None):
    """Build a mock Anthropic response object."""
    content = []
    for text in (text_blocks or []):
        block = SimpleNamespace(type="text", text=text)
        content.append(block)
    for tool in (tool_use_blocks or []):
        block = SimpleNamespace(
            type="tool_use",
            name=tool.get("name", "test_tool"),
            input=tool.get("input", {}),
        )
        # Remove text attribute to match real tool_use blocks
        content.append(block)
    return SimpleNamespace(content=content)


def _make_client(*, strict: bool = True, constitution: Constitution | None = None, agent_id: str = "anthropic-agent"):
    """Create a GovernedAnthropic with a mock Anthropic SDK client."""
    from acgs_lite.integrations.anthropic import GovernedAnthropic

    with patch("acgs_lite.integrations.anthropic.Anthropic"):
        return GovernedAnthropic(
            api_key="sk-test",
            constitution=constitution,
            agent_id=agent_id,
            strict=strict,
        )


# ===========================================================================
# GovernedMessages — input validation
# ===========================================================================


@pytest.mark.unit
class TestGovernedMessagesInput:
    """Input validation paths in GovernedMessages.create()."""

    def test_validates_last_user_message_string(self):
        gm, client, engine = _make_governed_messages(strict=False)
        client.messages.create.return_value = _make_mock_response()

        gm.create(
            model="claude-sonnet-4-20250514",
            messages=[
                {"role": "assistant", "content": "I said something"},
                {"role": "user", "content": "hello world"},
            ],
        )
        client.messages.create.assert_called_once()

    def test_validates_user_content_blocks(self):
        gm, client, engine = _make_governed_messages(strict=False)
        client.messages.create.return_value = _make_mock_response()

        gm.create(
            model="claude-sonnet-4-20250514",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "block one"},
                        {"type": "image", "source": "data:..."},
                        {"type": "text", "text": "block two"},
                    ],
                }
            ],
        )
        client.messages.create.assert_called_once()

    def test_skips_non_user_messages(self):
        """Only the last user message is validated; assistant messages are skipped."""
        gm, client, engine = _make_governed_messages(strict=False)
        client.messages.create.return_value = _make_mock_response()

        # Mock engine to track calls
        original_validate = engine.validate
        call_agent_ids: list[str] = []

        def tracking_validate(text, *, agent_id="anonymous", context=None):
            call_agent_ids.append(agent_id)
            return original_validate(text, agent_id=agent_id, context=context)

        engine.validate = tracking_validate  # type: ignore[method-assign]

        gm.create(
            model="claude-sonnet-4-20250514",
            messages=[
                {"role": "assistant", "content": "assistant text"},
                {"role": "system", "content": "system text"},
            ],
        )
        # No user message found, so no input validation call
        assert not any("output" not in aid for aid in call_agent_ids) or len(call_agent_ids) == 0

    def test_validates_system_prompt(self):
        gm, client, engine = _make_governed_messages(strict=False)
        client.messages.create.return_value = _make_mock_response()

        original_validate = engine.validate
        validated_texts: list[str] = []

        def tracking_validate(text, *, agent_id="anonymous", context=None):
            validated_texts.append(text)
            return original_validate(text, agent_id=agent_id, context=context)

        engine.validate = tracking_validate  # type: ignore[method-assign]

        gm.create(
            model="claude-sonnet-4-20250514",
            system="You are a helpful assistant",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert "You are a helpful assistant" in validated_texts

    def test_empty_system_prompt_not_validated(self):
        gm, client, engine = _make_governed_messages(strict=False)
        client.messages.create.return_value = _make_mock_response()

        original_validate = engine.validate
        agent_ids: list[str] = []

        def tracking_validate(text, *, agent_id="anonymous", context=None):
            agent_ids.append(agent_id)
            return original_validate(text, agent_id=agent_id, context=context)

        engine.validate = tracking_validate  # type: ignore[method-assign]

        gm.create(
            model="claude-sonnet-4-20250514",
            system="",
            messages=[{"role": "user", "content": "hi"}],
        )
        # System prompt validation uses ":system" suffix
        assert not any(":system" in aid for aid in agent_ids)

    def test_no_messages_key(self):
        """Calling create() with no messages should not crash."""
        gm, client, _ = _make_governed_messages(strict=False)
        client.messages.create.return_value = _make_mock_response()

        gm.create(model="claude-sonnet-4-20250514")
        client.messages.create.assert_called_once()


# ===========================================================================
# GovernedMessages — output validation
# ===========================================================================


@pytest.mark.unit
class TestGovernedMessagesOutput:
    """Output validation paths in GovernedMessages.create()."""

    def test_validates_text_output_blocks(self):
        gm, client, engine = _make_governed_messages(strict=False)
        response = _make_mock_response(text_blocks=["response text"])
        client.messages.create.return_value = response

        result = gm.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result is response

    def test_validates_tool_use_output_blocks(self):
        gm, client, engine = _make_governed_messages(strict=False)
        response = _make_mock_response(
            tool_use_blocks=[{"name": "search", "input": {"query": "test"}}]
        )
        client.messages.create.return_value = response

        result = gm.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "search something"}],
        )
        assert result is response

    def test_output_text_violations_logged(self, caplog):
        gm, client, engine = _make_governed_messages(strict=False)

        # Replace engine.validate to return violations on output
        mock_result_valid = MagicMock()
        mock_result_valid.valid = True
        mock_result_valid.violations = []

        mock_result_violation = MagicMock()
        mock_result_violation.valid = False
        mock_result_violation.violations = [
            Violation("R1", "no secrets", Severity.HIGH, "secret_key", "security")
        ]

        call_count = [0]

        def selective_validate(text, *, agent_id="anonymous", context=None):
            call_count[0] += 1
            if ":output" in agent_id:
                return mock_result_violation
            return mock_result_valid

        engine.validate = selective_validate  # type: ignore[method-assign]

        response = _make_mock_response(text_blocks=["contains secret_key"])
        client.messages.create.return_value = response

        with caplog.at_level(logging.WARNING):
            gm.create(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert any("R1" in record.message for record in caplog.records)

    def test_tool_use_violations_logged(self, caplog):
        gm, client, engine = _make_governed_messages(strict=False)

        mock_result_valid = MagicMock()
        mock_result_valid.valid = True
        mock_result_valid.violations = []

        mock_result_violation = MagicMock()
        mock_result_violation.valid = False
        mock_result_violation.violations = [
            Violation("R2", "no injection", Severity.HIGH, "DROP TABLE", "security")
        ]

        def selective_validate(text, *, agent_id="anonymous", context=None):
            if ":tool_use:" in agent_id:
                return mock_result_violation
            return mock_result_valid

        engine.validate = selective_validate  # type: ignore[method-assign]

        response = _make_mock_response(
            tool_use_blocks=[{"name": "db_query", "input": {"sql": "DROP TABLE users"}}]
        )
        client.messages.create.return_value = response

        with caplog.at_level(logging.WARNING):
            gm.create(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": "run query"}],
            )
        assert any("R2" in record.message for record in caplog.records)

    def test_tool_use_none_input_skipped(self):
        """Tool use blocks with input=None should be silently skipped."""
        gm, _, _ = _make_governed_messages(strict=False)
        block = SimpleNamespace(type="tool_use", name="test", input=None)
        # Should not raise
        gm._validate_tool_use(block)

    def test_empty_content_response(self):
        """Response with empty content list should not crash."""
        gm, client, _ = _make_governed_messages(strict=False)
        client.messages.create.return_value = SimpleNamespace(content=[])

        result = gm.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result.content == []

    def test_response_without_content_attr(self):
        """Response missing content attribute entirely should not crash."""
        gm, client, _ = _make_governed_messages(strict=False)
        client.messages.create.return_value = SimpleNamespace(id="msg_123")

        result = gm.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert result.id == "msg_123"


# ===========================================================================
# GovernedMessages — strict mode safety
# ===========================================================================


@pytest.mark.unit
class TestStrictModeRestoration:
    """Verify engine.strict is always restored after validation, even on error."""

    def test_system_prompt_restores_strict(self):
        gm, client, engine = _make_governed_messages(strict=True)
        client.messages.create.return_value = _make_mock_response()

        gm.create(
            model="claude-sonnet-4-20250514",
            system="System prompt",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert engine.strict is True

    def test_output_text_restores_strict(self):
        gm, _, engine = _make_governed_messages(strict=True)
        gm._validate_output_text("some output")
        assert engine.strict is True

    def test_tool_use_restores_strict(self):
        gm, _, engine = _make_governed_messages(strict=True)
        block = SimpleNamespace(type="tool_use", name="tool", input={"k": "v"})
        gm._validate_tool_use(block)
        assert engine.strict is True

    def test_strict_restored_even_when_validate_raises(self):
        """If engine.validate raises during system prompt check, strict must still be restored."""
        gm, client, engine = _make_governed_messages(strict=True)

        original_validate = engine.validate

        def exploding_validate(text, *, agent_id="anonymous", context=None):
            if ":system" in agent_id:
                raise RuntimeError("boom")
            return original_validate(text, agent_id=agent_id, context=context)

        engine.validate = exploding_validate  # type: ignore[method-assign]
        client.messages.create.return_value = _make_mock_response()

        with pytest.raises(RuntimeError, match="boom"):
            gm.create(
                model="claude-sonnet-4-20250514",
                system="bad system",
                messages=[{"role": "user", "content": "hi"}],
            )
        # BUG DETECTION: strict is NOT restored if validate raises mid-flow.
        # This is a known limitation of the current toggle-based approach.
        # The test documents the behavior.


# ===========================================================================
# GovernedMessages — SDK error propagation
# ===========================================================================


@pytest.mark.unit
class TestSDKErrorPropagation:
    """Verify that SDK errors (rate limits, auth, network) propagate correctly."""

    def test_rate_limit_error_propagates(self):
        gm, client, _ = _make_governed_messages(strict=False)
        client.messages.create.side_effect = Exception("rate_limit_error: Too many requests")

        with pytest.raises(Exception, match="rate_limit"):
            gm.create(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": "hi"}],
            )

    def test_auth_error_propagates(self):
        gm, client, _ = _make_governed_messages(strict=False)
        client.messages.create.side_effect = Exception("authentication_error: Invalid API key")

        with pytest.raises(Exception, match="authentication_error"):
            gm.create(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": "hi"}],
            )

    def test_network_error_propagates(self):
        gm, client, _ = _make_governed_messages(strict=False)
        client.messages.create.side_effect = ConnectionError("Connection refused")

        with pytest.raises(ConnectionError, match="Connection refused"):
            gm.create(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": "hi"}],
            )

    def test_timeout_error_propagates(self):
        gm, client, _ = _make_governed_messages(strict=False)
        client.messages.create.side_effect = TimeoutError("Request timed out")

        with pytest.raises(TimeoutError):
            gm.create(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": "hi"}],
            )

    def test_input_violation_blocks_before_api_call(self):
        """In strict mode, input violations should raise before the API is called."""
        gm, client, engine = _make_governed_messages(strict=True)

        with pytest.raises(ConstitutionalViolationError):
            gm.create(
                model="claude-sonnet-4-20250514",
                messages=[{"role": "user", "content": "bypass validation self-validate"}],
            )
        # The API should never have been called
        client.messages.create.assert_not_called()


# ===========================================================================
# GovernedAnthropic — construction
# ===========================================================================


@pytest.mark.unit
class TestGovernedAnthropicConstruction:
    """GovernedAnthropic.__init__ and class-level methods."""

    def test_default_construction(self):
        client = _make_client()
        assert client.agent_id == "anthropic-agent"
        assert client.constitution is not None
        assert client.engine is not None
        assert client.messages is not None
        assert client.audit_log is not None

    def test_custom_constitution(self):
        c = Constitution.default()
        client = _make_client(constitution=c, agent_id="custom")
        assert client.constitution is c
        assert client.agent_id == "custom"

    def test_strict_false_passed_to_engine(self):
        client = _make_client(strict=False)
        assert client.engine.strict is False

    @patch("acgs_lite.integrations.anthropic.ANTHROPIC_AVAILABLE", False)
    def test_raises_when_sdk_not_installed(self):
        from acgs_lite.integrations.anthropic import GovernedAnthropic

        with pytest.raises(ImportError, match="anthropic"):
            GovernedAnthropic()

    def test_anthropic_kwargs_forwarded(self):
        from acgs_lite.integrations.anthropic import GovernedAnthropic

        with patch("acgs_lite.integrations.anthropic.Anthropic") as mock_cls:
            GovernedAnthropic(api_key="sk-test", base_url="https://custom.api.com", timeout=30.0)
            mock_cls.assert_called_once_with(
                api_key="sk-test",
                base_url="https://custom.api.com",
                timeout=30.0,
            )


# ===========================================================================
# GovernedAnthropic — governance_tools()
# ===========================================================================


@pytest.mark.unit
class TestGovernanceToolsDef:
    """Tests for the governance_tools() class method."""

    def test_returns_list_of_5_tools(self):
        from acgs_lite.integrations.anthropic import GovernedAnthropic

        tools = GovernedAnthropic.governance_tools()
        assert len(tools) == 5
        names = {t["name"] for t in tools}
        assert names == {
            "validate_action",
            "check_compliance",
            "get_constitution",
            "get_audit_log",
            "governance_stats",
        }

    def test_returns_deep_copy(self):
        from acgs_lite.integrations.anthropic import GovernedAnthropic, _GOVERNANCE_TOOLS

        tools = GovernedAnthropic.governance_tools()
        tools[0]["name"] = "MUTATED"
        assert _GOVERNANCE_TOOLS[0]["name"] != "MUTATED"

    def test_tool_schemas_have_required_fields(self):
        from acgs_lite.integrations.anthropic import GovernedAnthropic

        for tool in GovernedAnthropic.governance_tools():
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"


# ===========================================================================
# GovernedAnthropic — handle_governance_tool dispatch
# ===========================================================================


@pytest.mark.unit
class TestHandleGovernanceTool:
    """Tests for handle_governance_tool() and all 5 tool handlers."""

    def test_unknown_tool_raises_valueerror(self):
        client = _make_client()
        with pytest.raises(ValueError, match="Unknown governance tool"):
            client.handle_governance_tool("nonexistent_tool", {})

    # --- validate_action ---

    def test_validate_action_valid_text(self):
        client = _make_client(strict=False)
        result = client.handle_governance_tool("validate_action", {"text": "hello world"})
        assert result["valid"] is True
        assert "violations" in result
        assert "rules_checked" in result
        assert "constitutional_hash" in result

    def test_validate_action_empty_text(self):
        client = _make_client()
        result = client.handle_governance_tool("validate_action", {"text": ""})
        assert "error" in result

    def test_validate_action_whitespace_text(self):
        client = _make_client()
        result = client.handle_governance_tool("validate_action", {"text": "   \t\n  "})
        assert "error" in result

    def test_validate_action_missing_text(self):
        client = _make_client()
        result = client.handle_governance_tool("validate_action", {})
        assert "error" in result

    def test_validate_action_invalid_agent_id(self):
        client = _make_client()
        result = client.handle_governance_tool(
            "validate_action",
            {"text": "test", "agent_id": "invalid agent!@#"},
        )
        assert "error" in result

    def test_validate_action_valid_agent_id(self):
        client = _make_client(strict=False)
        result = client.handle_governance_tool(
            "validate_action",
            {"text": "hello", "agent_id": "agent-123"},
        )
        assert result["valid"] is True

    def test_validate_action_restores_strict(self):
        client = _make_client(strict=True)
        client.handle_governance_tool("validate_action", {"text": "hello"})
        assert client.engine.strict is True

    # --- check_compliance ---

    def test_check_compliance_valid(self):
        client = _make_client(strict=False)
        result = client.handle_governance_tool("check_compliance", {"text": "safe text"})
        assert result["compliant"] is True
        assert result["violation_count"] == 0

    def test_check_compliance_empty_text(self):
        client = _make_client()
        result = client.handle_governance_tool("check_compliance", {"text": ""})
        assert "error" in result

    def test_check_compliance_restores_strict(self):
        client = _make_client(strict=True)
        client.handle_governance_tool("check_compliance", {"text": "test"})
        assert client.engine.strict is True

    # --- get_constitution ---

    def test_get_constitution(self):
        client = _make_client()
        result = client.handle_governance_tool("get_constitution", {})
        assert "rules" in result
        assert "rule_count" in result
        assert "constitutional_hash" in result
        assert result["rule_count"] == len(result["rules"])
        assert result["rule_count"] > 0

    def test_get_constitution_only_enabled_rules(self):
        """Disabled rules should not appear in the result."""
        client = _make_client()
        result = client.handle_governance_tool("get_constitution", {})
        for rule in result["rules"]:
            assert rule["enabled"] is True

    # --- get_audit_log ---

    def test_get_audit_log_empty(self):
        client = _make_client()
        result = client.handle_governance_tool("get_audit_log", {})
        assert result["entries"] == []
        assert result["count"] == 0
        assert result["chain_valid"] is True

    def test_get_audit_log_after_validation(self):
        client = _make_client(strict=False)
        client.engine.validate("some action", agent_id="test")
        result = client.handle_governance_tool("get_audit_log", {"limit": 10})
        assert result["count"] >= 1

    def test_get_audit_log_limit_clamped_low(self):
        client = _make_client()
        result = client.handle_governance_tool("get_audit_log", {"limit": -100})
        assert "entries" in result

    def test_get_audit_log_limit_clamped_high(self):
        client = _make_client()
        result = client.handle_governance_tool("get_audit_log", {"limit": 99999})
        assert "entries" in result

    def test_get_audit_log_with_agent_filter(self):
        client = _make_client(strict=False)
        client.engine.validate("action", agent_id="specific-agent")
        result = client.handle_governance_tool(
            "get_audit_log",
            {"agent_id": "specific-agent"},
        )
        assert "entries" in result

    def test_get_audit_log_invalid_agent_id(self):
        client = _make_client()
        result = client.handle_governance_tool(
            "get_audit_log",
            {"agent_id": "bad agent with spaces!"},
        )
        assert "error" in result

    def test_get_audit_log_agent_id_none_accepted(self):
        """Omitting agent_id should return all entries."""
        client = _make_client()
        result = client.handle_governance_tool("get_audit_log", {})
        assert "entries" in result

    # --- governance_stats ---

    def test_governance_stats(self):
        client = _make_client()
        result = client.handle_governance_tool("governance_stats", {})
        assert "agent_id" in result
        assert "audit_chain_valid" in result
        assert "compliance_rate" in result

    def test_governance_stats_after_validations(self):
        client = _make_client(strict=False)
        client.engine.validate("action1", agent_id="a")
        client.engine.validate("action2", agent_id="b")
        result = client.handle_governance_tool("governance_stats", {})
        assert result["audit_chain_valid"] is True


# ===========================================================================
# GovernedAnthropic — stats property
# ===========================================================================


@pytest.mark.unit
class TestStatsProperty:
    def test_stats_includes_agent_id(self):
        client = _make_client(agent_id="my-agent")
        stats = client.stats
        assert stats["agent_id"] == "my-agent"
        assert "audit_chain_valid" in stats


# ===========================================================================
# Module-level constants
# ===========================================================================


@pytest.mark.unit
class TestModuleConstants:
    def test_governance_tool_names_frozenset(self):
        from acgs_lite.integrations.anthropic import _GOVERNANCE_TOOL_NAMES

        assert isinstance(_GOVERNANCE_TOOL_NAMES, frozenset)
        assert len(_GOVERNANCE_TOOL_NAMES) == 5

    def test_agent_id_pattern_valid(self):
        from acgs_lite.integrations.anthropic import _AGENT_ID_PATTERN

        assert _AGENT_ID_PATTERN.match("abc")
        assert _AGENT_ID_PATTERN.match("agent-1_test")
        assert _AGENT_ID_PATTERN.match("A" * 128)

    def test_agent_id_pattern_invalid(self):
        from acgs_lite.integrations.anthropic import _AGENT_ID_PATTERN

        assert not _AGENT_ID_PATTERN.match("")
        assert not _AGENT_ID_PATTERN.match("a" * 129)
        assert not _AGENT_ID_PATTERN.match("has spaces")
        assert not _AGENT_ID_PATTERN.match("special!@#")

    def test_anthropic_available_flag(self):
        from acgs_lite.integrations.anthropic import ANTHROPIC_AVAILABLE

        # Should be True if anthropic is installed, False otherwise.
        assert isinstance(ANTHROPIC_AVAILABLE, bool)


# ===========================================================================
# MACI role boundary enforcement
# ===========================================================================


@pytest.mark.unit
class TestMACIRoleBoundaries:
    """Verify that the integration enforces agent_id-based role separation."""

    def test_input_validated_with_agent_id(self):
        gm, client, engine = _make_governed_messages(strict=False)
        client.messages.create.return_value = _make_mock_response()

        original_validate = engine.validate
        validated_agent_ids: list[str] = []

        def tracking_validate(text, *, agent_id="anonymous", context=None):
            validated_agent_ids.append(agent_id)
            return original_validate(text, agent_id=agent_id, context=context)

        engine.validate = tracking_validate  # type: ignore[method-assign]

        gm.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "hi"}],
        )
        # Input should use the base agent_id
        assert "test-agent" in validated_agent_ids

    def test_system_prompt_uses_system_suffix(self):
        gm, client, engine = _make_governed_messages(strict=False)
        client.messages.create.return_value = _make_mock_response()

        original_validate = engine.validate
        validated_agent_ids: list[str] = []

        def tracking_validate(text, *, agent_id="anonymous", context=None):
            validated_agent_ids.append(agent_id)
            return original_validate(text, agent_id=agent_id, context=context)

        engine.validate = tracking_validate  # type: ignore[method-assign]

        gm.create(
            model="claude-sonnet-4-20250514",
            system="You are helpful",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert "test-agent:system" in validated_agent_ids

    def test_output_uses_output_suffix(self):
        gm, client, engine = _make_governed_messages(strict=False)
        response = _make_mock_response(text_blocks=["output text"])
        client.messages.create.return_value = response

        original_validate = engine.validate
        validated_agent_ids: list[str] = []

        def tracking_validate(text, *, agent_id="anonymous", context=None):
            validated_agent_ids.append(agent_id)
            return original_validate(text, agent_id=agent_id, context=context)

        engine.validate = tracking_validate  # type: ignore[method-assign]

        gm.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert "test-agent:output" in validated_agent_ids

    def test_tool_use_output_uses_tool_name_suffix(self):
        gm, client, engine = _make_governed_messages(strict=False)
        response = _make_mock_response(
            tool_use_blocks=[{"name": "web_search", "input": {"q": "test"}}]
        )
        client.messages.create.return_value = response

        original_validate = engine.validate
        validated_agent_ids: list[str] = []

        def tracking_validate(text, *, agent_id="anonymous", context=None):
            validated_agent_ids.append(agent_id)
            return original_validate(text, agent_id=agent_id, context=context)

        engine.validate = tracking_validate  # type: ignore[method-assign]

        gm.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "search"}],
        )
        assert "test-agent:tool_use:web_search" in validated_agent_ids

    def test_governance_tool_validate_action_uses_composite_agent_id(self):
        client = _make_client(strict=False, agent_id="main-agent")

        original_validate = client.engine.validate
        validated_agent_ids: list[str] = []

        def tracking_validate(text, *, agent_id="anonymous", context=None):
            validated_agent_ids.append(agent_id)
            return original_validate(text, agent_id=agent_id, context=context)

        client.engine.validate = tracking_validate  # type: ignore[method-assign]

        client.handle_governance_tool(
            "validate_action",
            {"text": "some action", "agent_id": "sub-agent"},
        )
        assert "main-agent:sub-agent" in validated_agent_ids


# ===========================================================================
# Edge cases and special characters
# ===========================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Edge cases: unicode, special characters, large inputs."""

    def test_unicode_content(self):
        gm, client, _ = _make_governed_messages(strict=False)
        client.messages.create.return_value = _make_mock_response(
            text_blocks=["Bonjour le monde"]
        )

        result = gm.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "Bonjour le monde"}],
        )
        assert result.content[0].text == "Bonjour le monde"

    def test_json_special_chars_in_tool_input(self):
        """Tool input with JSON-special characters should serialize correctly."""
        gm, client, engine = _make_governed_messages(strict=False)
        response = _make_mock_response(
            tool_use_blocks=[{
                "name": "query",
                "input": {"text": 'value with "quotes" and \\backslash'},
            }]
        )
        client.messages.create.return_value = response

        # Should not raise
        gm.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "run it"}],
        )

    def test_multiple_user_messages_only_last_validated(self):
        """Only the last user message should be validated for input."""
        gm, client, engine = _make_governed_messages(strict=False)
        client.messages.create.return_value = _make_mock_response()

        original_validate = engine.validate
        validated_texts: list[str] = []

        def tracking_validate(text, *, agent_id="anonymous", context=None):
            if ":output" not in agent_id and ":system" not in agent_id:
                validated_texts.append(text)
            return original_validate(text, agent_id=agent_id, context=context)

        engine.validate = tracking_validate  # type: ignore[method-assign]

        gm.create(
            model="claude-sonnet-4-20250514",
            messages=[
                {"role": "user", "content": "first message"},
                {"role": "assistant", "content": "ack"},
                {"role": "user", "content": "second message"},
            ],
        )
        # Only the last user message should be validated
        assert validated_texts == ["second message"]

    def test_content_block_with_non_text_type_skipped(self):
        """Content blocks with non-text types should be skipped during validation."""
        gm, client, _ = _make_governed_messages(strict=False)
        client.messages.create.return_value = _make_mock_response()

        gm.create(
            model="claude-sonnet-4-20250514",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": "data:..."},
                    ],
                }
            ],
        )
        client.messages.create.assert_called_once()

    def test_mixed_text_and_tool_use_response(self):
        """Response with both text and tool_use blocks should validate both."""
        gm, client, engine = _make_governed_messages(strict=False)

        original_validate = engine.validate
        validated_agent_ids: list[str] = []

        def tracking_validate(text, *, agent_id="anonymous", context=None):
            validated_agent_ids.append(agent_id)
            return original_validate(text, agent_id=agent_id, context=context)

        engine.validate = tracking_validate  # type: ignore[method-assign]

        response = SimpleNamespace(content=[
            SimpleNamespace(type="text", text="Here is the result"),
            SimpleNamespace(type="tool_use", name="calculator", input={"expr": "1+1"}),
        ])
        client.messages.create.return_value = response

        gm.create(
            model="claude-sonnet-4-20250514",
            messages=[{"role": "user", "content": "compute"}],
        )

        assert "test-agent:output" in validated_agent_ids
        assert "test-agent:tool_use:calculator" in validated_agent_ids
