"""Tests for integrations module refactoring fixes.

Covers the strict-kwarg bug fix in anthropic.py, the a2a.py title removal,
and helper function edge cases across integration modules.
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest


class TestIntegrationsPackageSurface:
    """Smoke tests for the integrations package surface."""

    def test_integrations_package_imports_cleanly(self):
        mod = importlib.import_module("acgs_lite.integrations")
        assert mod.__name__ == "acgs_lite.integrations"
        assert hasattr(mod, "__all__")
        assert "GovernedOpenAI" not in mod.__dict__


class TestAnthropicStrictKwargFix:
    """Verify that GovernedMessages uses engine.strict toggle, not a kwarg."""

    def _make_governed_messages(self):
        from acgs_lite.constitution import Constitution
        from acgs_lite.engine import GovernanceEngine
        from acgs_lite.integrations.anthropic import GovernedMessages

        constitution = Constitution.default()
        engine = GovernanceEngine(constitution, strict=True)
        client = MagicMock()
        return GovernedMessages(client, engine, "test-agent"), engine, client

    def test_system_prompt_validated_non_strict(self):
        """System prompts should be validated with strict=False temporarily."""
        gm, engine, client = self._make_governed_messages()
        assert engine.strict is True

        mock_response = MagicMock()
        mock_response.content = []
        client.messages.create.return_value = mock_response

        gm.create(
            messages=[{"role": "user", "content": "hello"}],
            system="You are helpful",
        )

        # Engine strict should be restored after the call
        assert engine.strict is True

    def test_output_text_validated_non_strict(self):
        """Output text validation should temporarily set strict=False."""
        gm, engine, _ = self._make_governed_messages()
        assert engine.strict is True

        gm._validate_output_text("some output text")

        # strict restored
        assert engine.strict is True

    def test_tool_use_validated_non_strict(self):
        """Tool use validation should temporarily set strict=False."""
        gm, engine, _ = self._make_governed_messages()
        assert engine.strict is True

        block = MagicMock()
        block.input = {"key": "value"}
        block.name = "test_tool"
        gm._validate_tool_use(block)

        assert engine.strict is True


class TestGovernedAnthropicToolHandlers:
    """Verify governance tool handlers use strict toggle correctly."""

    def _make_client(self):
        from acgs_lite.integrations.anthropic import ANTHROPIC_AVAILABLE, GovernedAnthropic

        if not ANTHROPIC_AVAILABLE:
            pytest.skip("anthropic not installed")

        with patch("acgs_lite.integrations.anthropic.Anthropic"):
            return GovernedAnthropic(api_key="test")

    def test_handle_validate_action_restores_strict(self):
        """_handle_validate_action should restore engine.strict after call."""
        client = self._make_client()
        client.engine.strict = True

        client._handle_validate_action({"text": "hello", "agent_id": "test"})

        assert client.engine.strict is True

    def test_handle_check_compliance_restores_strict(self):
        """_handle_check_compliance should restore engine.strict after call."""
        client = self._make_client()
        client.engine.strict = True

        client._handle_check_compliance({"text": "hello"})

        assert client.engine.strict is True


class TestA2AAppCreation:
    """Verify A2A app creation works after title attribute removal."""

    def test_create_a2a_app_returns_starlette(self):
        """create_a2a_app should return a Starlette app without errors."""
        from acgs_lite.integrations.a2a import create_a2a_app

        app = create_a2a_app()
        assert app.routes is not None


class TestLiteLLMHelpers:
    """Test litellm helper functions."""

    def test_extract_user_message_empty(self):
        from acgs_lite.integrations.litellm import _extract_user_message

        assert _extract_user_message([]) == ""

    def test_extract_user_message_content_blocks(self):
        from acgs_lite.integrations.litellm import _extract_user_message

        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "text", "text": "world"},
                ],
            }
        ]
        assert _extract_user_message(msgs) == "hello world"

    def test_extract_response_text_no_choices(self):
        from acgs_lite.integrations.litellm import _extract_response_text

        assert _extract_response_text(MagicMock(spec=[])) == ""


class TestGoogleGenAIHelpers:
    """Test google_genai helper functions."""

    def test_extract_content_text_list_of_dicts(self):
        from acgs_lite.integrations.google_genai import _extract_content_text

        result = _extract_content_text([{"text": "hi"}, "there"])
        assert "hi" in result
        assert "there" in result

    def test_extract_content_text_object_with_text(self):
        from acgs_lite.integrations.google_genai import _extract_content_text

        obj = MagicMock()
        obj.text = "test"
        assert _extract_content_text(obj) == "test"

    def test_extract_response_text_empty(self):
        from acgs_lite.integrations.google_genai import _extract_response_text

        assert _extract_response_text(object()) == ""


class TestCloudLoggingSeverity:
    """Test cloud logging severity mapping."""

    def test_severity_critical(self):
        from acgs_lite.audit import AuditEntry
        from acgs_lite.integrations.cloud_logging import _severity_to_cloud_severity

        entry = AuditEntry(
            id="t1",
            type="validation",
            agent_id="a",
            action="x",
            valid=False,
            violations=["r1"],
            metadata={"severity": "critical"},
        )
        assert _severity_to_cloud_severity(entry) == "CRITICAL"

    def test_severity_valid(self):
        from acgs_lite.audit import AuditEntry
        from acgs_lite.integrations.cloud_logging import _severity_to_cloud_severity

        entry = AuditEntry(
            id="t2",
            type="validation",
            agent_id="a",
            action="x",
            valid=True,
        )
        assert _severity_to_cloud_severity(entry) == "INFO"
