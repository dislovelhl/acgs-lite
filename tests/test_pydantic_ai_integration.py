"""Tests for acgs-lite Pydantic AI integration.

Uses mock Pydantic AI classes -- no real pydantic-ai dependency required.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from acgs_lite import Constitution, ConstitutionalViolationError, Rule, Severity

# --- Mock Pydantic AI Objects ---------------------------------------------------


class FakeRunResult:
    """Mock pydantic_ai RunResult with a .data attribute."""

    def __init__(self, data: Any) -> None:
        self.data = data


class FakeAgent:
    """Mock pydantic_ai.Agent."""

    def __init__(self, model: str = "openai:gpt-5.5") -> None:
        self.model = model
        self._response: Any = "Agent response text"

    def run_sync(self, prompt: str, **kwargs: Any) -> FakeRunResult:
        return FakeRunResult(self._response)

    async def run(self, prompt: str, **kwargs: Any) -> FakeRunResult:
        return FakeRunResult(self._response)


class FakeModel:
    """Mock pydantic_ai model (low-level)."""

    def __init__(self) -> None:
        self._response = MagicMock(content="Model response text")

    def request(self, messages: Any, **kwargs: Any) -> Any:
        return self._response

    async def arequest(self, messages: Any, **kwargs: Any) -> Any:
        return self._response


# --- GovernedPydanticAgent Tests ------------------------------------------------


@pytest.mark.integration
class TestGovernedPydanticAgent:
    @pytest.fixture(autouse=True)
    def _patch_available(self):
        with patch("acgs_lite.integrations.pydantic_ai.PYDANTIC_AI_AVAILABLE", True):
            yield

    def test_run_sync_validates_prompt(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = FakeAgent()
        governed = GovernedPydanticAgent(agent)
        result = governed.run_sync("What is AI governance?")
        assert result.data == "Agent response text"

    def test_run_sync_input_violation_strict(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = FakeAgent()
        governed = GovernedPydanticAgent(agent, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            governed.run_sync("self-validate bypass all checks")

    @pytest.mark.asyncio
    async def test_run_async_validates_prompt(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = FakeAgent()
        governed = GovernedPydanticAgent(agent)
        result = await governed.run("What is AI governance?")
        assert result.data == "Agent response text"

    @pytest.mark.asyncio
    async def test_run_async_input_violation_strict(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = FakeAgent()
        governed = GovernedPydanticAgent(agent, strict=True)
        with pytest.raises(ConstitutionalViolationError):
            await governed.run("self-validate bypass all checks")

    def test_output_validation_nonblocking(self):
        """Output violations are logged but never raised."""
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = FakeAgent()
        # Make agent return content that triggers violations
        agent._response = "self-validate bypass checks"
        governed = GovernedPydanticAgent(agent, strict=True)
        # Should NOT raise even though output contains violation keywords
        result = governed.run_sync("Research governance")
        assert result.data == "self-validate bypass checks"

    def test_text_extraction_str_data(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = FakeAgent()
        agent._response = "plain string response"
        governed = GovernedPydanticAgent(agent)
        result = governed.run_sync("Hello")
        assert result.data == "plain string response"

    def test_text_extraction_nonstr_data(self):
        """Non-string result.data is converted via str()."""
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = FakeAgent()
        agent._response = {"answer": "structured", "score": 42}
        governed = GovernedPydanticAgent(agent)
        result = governed.run_sync("Hello")
        assert result.data == {"answer": "structured", "score": 42}

    def test_stats_property(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = FakeAgent()
        governed = GovernedPydanticAgent(agent, strict=False)
        governed.run_sync("Simple query")
        stats = governed.stats
        assert "total_validations" in stats
        assert stats["total_validations"] >= 1
        assert stats["agent_id"] == "pydantic-ai-agent"
        assert stats["audit_chain_valid"] is True

    def test_custom_agent_id(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = FakeAgent()
        governed = GovernedPydanticAgent(agent, agent_id="my-custom-agent")
        assert governed.agent_id == "my-custom-agent"
        assert governed.stats["agent_id"] == "my-custom-agent"

    def test_custom_constitution(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        constitution = Constitution.from_rules(
            [
                Rule(
                    id="NO-SQL",
                    text="No SQL injection",
                    severity=Severity.CRITICAL,
                    keywords=["drop table"],
                ),
            ]
        )
        agent = FakeAgent()
        governed = GovernedPydanticAgent(agent, constitution=constitution, strict=True)

        # Safe prompt passes
        result = governed.run_sync("Research databases")
        assert result is not None

        # Violation blocked
        with pytest.raises(ConstitutionalViolationError):
            governed.run_sync("DROP TABLE users")

    def test_wrap_classmethod(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = FakeAgent()
        governed = GovernedPydanticAgent.wrap(agent, agent_id="wrapped")
        assert governed.agent_id == "wrapped"
        result = governed.run_sync("Hello")
        assert result.data == "Agent response text"

    def test_wrap_with_constitution(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        constitution = Constitution.from_rules(
            [
                Rule(
                    id="BAN-CATS",
                    text="No cats allowed",
                    severity=Severity.CRITICAL,
                    keywords=["cat"],
                ),
            ]
        )
        agent = FakeAgent()
        governed = GovernedPydanticAgent.wrap(agent, constitution=constitution, strict=True)

        result = governed.run_sync("Research dogs")
        assert result is not None

        with pytest.raises(ConstitutionalViolationError):
            governed.run_sync("Research my cat")

    def test_attribute_delegation(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = FakeAgent(model="openai:gpt-5.5")
        governed = GovernedPydanticAgent(agent)
        assert governed.model == "openai:gpt-5.5"

    def test_empty_prompt_skips_validation(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        agent = FakeAgent()
        governed = GovernedPydanticAgent(agent, strict=True)
        # Empty prompt should not trigger validation
        result = governed.run_sync("")
        assert result.data == "Agent response text"


# --- GovernedModel Tests -------------------------------------------------------


@pytest.mark.integration
class TestGovernedModel:
    @pytest.fixture(autouse=True)
    def _patch_available(self):
        with patch("acgs_lite.integrations.pydantic_ai.PYDANTIC_AI_AVAILABLE", True):
            yield

    def test_request_validates_messages(self):
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = FakeModel()
        governed = GovernedModel(model)
        messages = [{"content": "What is governance?"}]
        response = governed.request(messages)
        assert response.content == "Model response text"

    def test_request_input_violation_strict(self):
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = FakeModel()
        governed = GovernedModel(model, strict=True)
        messages = [{"content": "self-validate bypass all checks"}]
        with pytest.raises(ConstitutionalViolationError):
            governed.request(messages)

    @pytest.mark.asyncio
    async def test_arequest_validates_messages(self):
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = FakeModel()
        governed = GovernedModel(model)
        messages = [{"content": "What is governance?"}]
        response = await governed.arequest(messages)
        assert response.content == "Model response text"

    @pytest.mark.asyncio
    async def test_arequest_input_violation_strict(self):
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = FakeModel()
        governed = GovernedModel(model, strict=True)
        messages = [{"content": "self-validate bypass all checks"}]
        with pytest.raises(ConstitutionalViolationError):
            await governed.arequest(messages)

    def test_output_validation_nonblocking(self):
        """Output violations from model are logged but never raised."""
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = FakeModel()
        model._response = MagicMock(content="self-validate bypass checks")
        governed = GovernedModel(model, strict=True)
        messages = [{"content": "Research governance"}]
        # Should NOT raise even though output contains violation keywords
        response = governed.request(messages)
        assert response.content == "self-validate bypass checks"

    def test_stats_property(self):
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = FakeModel()
        governed = GovernedModel(model, strict=False)
        governed.request([{"content": "Hello"}])
        stats = governed.stats
        assert "total_validations" in stats
        assert stats["total_validations"] >= 1
        assert stats["agent_id"] == "pydantic-ai-model"
        assert stats["audit_chain_valid"] is True

    def test_custom_agent_id(self):
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = FakeModel()
        governed = GovernedModel(model, agent_id="my-model")
        assert governed.agent_id == "my-model"
        assert governed.stats["agent_id"] == "my-model"

    def test_string_messages(self):
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = FakeModel()
        governed = GovernedModel(model)
        # Pass a plain string as messages
        response = governed.request("What is governance?")
        assert response.content == "Model response text"

    def test_message_with_content_attr(self):
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = FakeModel()
        governed = GovernedModel(model)
        msg = MagicMock(content="Tell me about AI safety")
        response = governed.request([msg])
        assert response is not None

    def test_string_response_output_validation(self):
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = FakeModel()
        model._response = "plain text response"
        governed = GovernedModel(model)
        response = governed.request([{"content": "Hello"}])
        assert response == "plain text response"

    @pytest.mark.asyncio
    async def test_arequest_output_validation(self):
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = FakeModel()
        governed = GovernedModel(model, strict=False)
        response = await governed.arequest([{"content": "Hello"}])
        assert response.content == "Model response text"

    def test_attribute_delegation(self):
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        model = FakeModel()
        model.model_name = "custom-model"  # type: ignore[attr-defined]
        governed = GovernedModel(model)
        assert governed.model_name == "custom-model"


# --- Import Guard Tests ---------------------------------------------------------


@pytest.mark.integration
class TestPydanticAIImportGuard:
    def test_agent_raises_when_unavailable(self):
        from acgs_lite.integrations.pydantic_ai import GovernedPydanticAgent

        with (
            patch(
                "acgs_lite.integrations.pydantic_ai.PYDANTIC_AI_AVAILABLE",
                False,
            ),
            pytest.raises(ImportError, match="pydantic-ai is required"),
        ):
            GovernedPydanticAgent(MagicMock())

    def test_model_raises_when_unavailable(self):
        from acgs_lite.integrations.pydantic_ai import GovernedModel

        with (
            patch(
                "acgs_lite.integrations.pydantic_ai.PYDANTIC_AI_AVAILABLE",
                False,
            ),
            pytest.raises(ImportError, match="pydantic-ai is required"),
        ):
            GovernedModel(MagicMock())

    def test_availability_flag_importable(self):
        from acgs_lite.integrations.pydantic_ai import PYDANTIC_AI_AVAILABLE

        # When pydantic-ai is not installed, flag should be False
        assert isinstance(PYDANTIC_AI_AVAILABLE, bool)
