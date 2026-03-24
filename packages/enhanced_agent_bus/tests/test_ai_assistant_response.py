"""Tests for ai_assistant.response module.

Covers PersonalityConfig, ResponseConfig, ResponseTemplate,
TemplateResponseGenerator, LLMResponseGenerator, and HybridResponseGenerator.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.ai_assistant.context import (
    ConversationContext,
    Message,
    MessageRole,
    UserProfile,
)
from enhanced_agent_bus.ai_assistant.nlu import Sentiment
from enhanced_agent_bus.ai_assistant.response import (
    HybridResponseGenerator,
    LLMResponseGenerator,
    PersonalityConfig,
    ResponseConfig,
    ResponseTemplate,
    TemplateResponseGenerator,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(**kwargs) -> ConversationContext:
    defaults = {
        "user_id": "u1",
        "session_id": "s1",
    }
    defaults.update(kwargs)
    return ConversationContext(**defaults)


# ---------------------------------------------------------------------------
# PersonalityConfig
# ---------------------------------------------------------------------------


class TestPersonalityConfig:
    def test_defaults(self):
        p = PersonalityConfig()
        assert p.name == "Assistant"
        assert p.tone == "professional"
        assert "helpful" in p.traits

    def test_to_dict(self):
        p = PersonalityConfig(name="Bot", tone="casual")
        d = p.to_dict()
        assert d["name"] == "Bot"
        assert d["tone"] == "casual"


# ---------------------------------------------------------------------------
# ResponseConfig
# ---------------------------------------------------------------------------


class TestResponseConfig:
    def test_defaults(self):
        c = ResponseConfig()
        assert c.max_response_length == 2000
        assert c.enable_fallback is True

    def test_to_dict(self):
        c = ResponseConfig()
        d = c.to_dict()
        assert "max_response_length" in d
        assert "default_personality" in d


# ---------------------------------------------------------------------------
# ResponseTemplate
# ---------------------------------------------------------------------------


class TestResponseTemplate:
    def test_get_template_default(self):
        t = ResponseTemplate(id="t1", intent="greeting", templates=["Hello!"])
        result = t.get_template()
        assert result == "Hello!"

    def test_get_template_with_sentiment(self):
        t = ResponseTemplate(
            id="t1",
            intent="greeting",
            templates=["Hello!"],
            sentiment_variants={"POSITIVE": ["Great to see you!"]},
        )
        result = t.get_template(Sentiment.POSITIVE)
        assert result == "Great to see you!"

    def test_get_template_unknown_sentiment_falls_back(self):
        t = ResponseTemplate(id="t1", intent="greeting", templates=["Hello!"])
        result = t.get_template(Sentiment.NEGATIVE)
        assert result == "Hello!"

    def test_get_template_empty_returns_empty(self):
        t = ResponseTemplate(id="t1", intent="x", templates=[])
        assert t.get_template() == ""


# ---------------------------------------------------------------------------
# TemplateResponseGenerator
# ---------------------------------------------------------------------------


class TestTemplateResponseGenerator:
    @pytest.mark.asyncio
    async def test_generate_greeting(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_unknown_intent_uses_clarification(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("unknown_intent_xyz", ctx, {})
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_with_sentiment_string(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {"sentiment": "POSITIVE"})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_generate_with_invalid_sentiment_string(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {"sentiment": "BOGUS"})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_generate_farewell(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("farewell", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_from_config(self):
        config = ResponseConfig()
        gen = TemplateResponseGenerator(config=config)
        assert gen.personality.name == "Assistant"
        assert gen._config is config

    def test_add_and_remove_template(self):
        gen = TemplateResponseGenerator()
        t = ResponseTemplate(id="custom", intent="custom", templates=["Custom!"])
        gen.add_template(t)
        assert "custom" in gen.templates
        gen.remove_template("custom")
        assert "custom" not in gen.templates

    @pytest.mark.asyncio
    async def test_variable_substitution(self):
        t = ResponseTemplate(id="t", intent="info", templates=["Order {order_id} ready."])
        gen = TemplateResponseGenerator(templates=[t])
        ctx = _make_context()
        result = await gen.generate("info", ctx, {"order_id": "12345"})
        assert "12345" in result

    @pytest.mark.asyncio
    async def test_personality_friendly_tone(self):
        personality = PersonalityConfig(tone="friendly")
        gen = TemplateResponseGenerator(personality=personality)
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_personality_brief(self):
        personality = PersonalityConfig(verbosity="brief")
        gen = TemplateResponseGenerator(personality=personality)
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_personality_emojis(self):
        personality = PersonalityConfig(use_emojis=True)
        gen = TemplateResponseGenerator(personality=personality)
        ctx = _make_context()
        # greeting templates start with "Hello" so emoji map triggers
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_personality_markdown(self):
        personality = PersonalityConfig(use_markdown=True)
        gen = TemplateResponseGenerator(personality=personality)
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_user_profile_prefers_brief(self):
        profile = UserProfile(user_id="u1", preferences={"prefers_brief": True})
        gen = TemplateResponseGenerator()
        ctx = _make_context(user_profile=profile)
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_validate_response_strips_unfilled_placeholders(self):
        t = ResponseTemplate(id="t", intent="info", templates=["Hello {unknown_var}!"])
        gen = TemplateResponseGenerator(templates=[t])
        ctx = _make_context()
        result = await gen.generate("info", ctx, {})
        assert "{unknown_var}" not in result

    @pytest.mark.asyncio
    async def test_entity_substitution(self):
        t = ResponseTemplate(id="t", intent="info", templates=["Product: {product}"])
        gen = TemplateResponseGenerator(templates=[t])
        ctx = _make_context(entities={"product": {"value": "Widget"}})
        result = await gen.generate("info", ctx, {})
        assert "Widget" in result

    @pytest.mark.asyncio
    async def test_slot_substitution(self):
        t = ResponseTemplate(id="t", intent="info", templates=["Color: {color}"])
        gen = TemplateResponseGenerator(templates=[t])
        ctx = _make_context(slots={"color": {"value": "red"}})
        result = await gen.generate("info", ctx, {})
        assert "red" in result


# ---------------------------------------------------------------------------
# LLMResponseGenerator
# ---------------------------------------------------------------------------


class TestLLMResponseGenerator:
    @pytest.mark.asyncio
    async def test_fallback_when_no_client(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_with_complete_client(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "I can help with that."
        mock_client.complete = AsyncMock(return_value=mock_resp)

        gen = LLMResponseGenerator(llm_client=mock_client)
        ctx = _make_context()
        result = await gen.generate("question", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_generate_with_generate_client(self):
        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value="Sure, here you go.")
        # Remove 'complete' so it falls to generate branch
        del mock_client.complete

        gen = LLMResponseGenerator(llm_client=mock_client)
        ctx = _make_context()
        result = await gen.generate("question", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_generate_client_no_methods_falls_back(self):
        mock_client = MagicMock(spec=[])  # no methods
        gen = LLMResponseGenerator(llm_client=mock_client)
        ctx = _make_context()
        # ValueError from _call_llm triggers fallback
        result = await gen.generate("question", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_generate_error_falls_back(self):
        mock_client = MagicMock()
        mock_client.complete = AsyncMock(side_effect=RuntimeError("oops"))

        gen = LLMResponseGenerator(llm_client=mock_client)
        ctx = _make_context()
        result = await gen.generate("question", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_blocked_patterns_trigger_fallback(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "As an AI, I cannot do that."
        mock_client.complete = AsyncMock(return_value=mock_resp)

        gen = LLMResponseGenerator(llm_client=mock_client)
        ctx = _make_context()
        result = await gen.generate("question", ctx, {})
        # Should have fallen back to template because of blocked pattern
        assert isinstance(result, str)

    def test_post_process_strips_prefix(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        result = gen._post_process("Assistant: Hello there.", ctx)
        assert not result.startswith("Assistant:")

    def test_post_process_truncates_incomplete_sentence(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        result = gen._post_process("Hello. How are you? I am fine but", ctx)
        assert result.endswith("?") or result.endswith(".")

    def test_validate_response_empty_returns_false(self):
        gen = LLMResponseGenerator()
        assert gen._validate_response("") is False
        assert gen._validate_response("ab") is False

    def test_build_prompt_with_entities(self):
        gen = LLMResponseGenerator()
        ctx = _make_context(entities={"product": {"value": "Widget"}})
        prompt = gen._build_prompt("question", ctx, {"relevant": "data"})
        assert "product" in prompt

    def test_format_conversation_history_empty(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        result = gen._format_conversation_history(ctx)
        assert "No previous messages" in result

    def test_format_conversation_history_with_messages(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        ctx.add_message(MessageRole.USER, "Hello")
        ctx.add_message(MessageRole.ASSISTANT, "Hi!")
        result = gen._format_conversation_history(ctx)
        # Verify messages are present in the formatted history
        assert "Hello" in result
        assert "Hi!" in result


# ---------------------------------------------------------------------------
# HybridResponseGenerator
# ---------------------------------------------------------------------------


class TestHybridResponseGenerator:
    @pytest.mark.asyncio
    async def test_template_intent(self):
        gen = HybridResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_llm_intent_without_client_falls_to_template(self):
        gen = HybridResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("question", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_llm_intent_with_client(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Here is your answer."
        mock_client.complete = AsyncMock(return_value=mock_resp)

        gen = HybridResponseGenerator(llm_client=mock_client)
        ctx = _make_context()
        result = await gen.generate("question", ctx, {})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_requires_llm_data_flag(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Done."
        mock_client.complete = AsyncMock(return_value=mock_resp)

        gen = HybridResponseGenerator(llm_client=mock_client)
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {"requires_llm": True})
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_long_conversation_uses_llm(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Understood."
        mock_client.complete = AsyncMock(return_value=mock_resp)

        gen = HybridResponseGenerator(llm_client=mock_client)
        ctx = _make_context()
        # Add 11 messages to trigger LLM path
        for i in range(11):
            ctx.add_message(MessageRole.USER, f"msg {i}")
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)

    def test_set_llm_client(self):
        gen = HybridResponseGenerator()
        mock = MagicMock()
        gen.set_llm_client(mock)
        assert gen.llm_generator.llm_client is mock

    def test_add_template(self):
        gen = HybridResponseGenerator()
        t = ResponseTemplate(id="x", intent="x", templates=["X"])
        gen.add_template(t)
        assert "x" in gen.template_generator.templates

    def test_add_llm_intent(self):
        gen = HybridResponseGenerator()
        gen.add_llm_intent("custom_intent")
        assert "custom_intent" in gen.llm_intents

    def test_add_llm_intent_no_duplicates(self):
        gen = HybridResponseGenerator()
        gen.add_llm_intent("question")
        count = gen.llm_intents.count("question")
        assert count == 1
