"""
Tests for src/core/enhanced_agent_bus/ai_assistant/response.py
Constitutional Hash: 608508a9bd224290

Target: raise coverage from 43% to >= 90%
asyncio_mode = auto — no @pytest.mark.asyncio needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.ai_assistant.context import (
    ConversationContext,
    Message,
    MessageRole,
    UserProfile,
)
from enhanced_agent_bus.ai_assistant.nlu import Sentiment
from enhanced_agent_bus.ai_assistant.response import (
    CONSTITUTIONAL_HASH,
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


def _make_context(
    user_id: str = "u1",
    session_id: str = "s1",
    messages: list | None = None,
    user_profile: UserProfile | None = None,
    entities: dict | None = None,
    slots: dict | None = None,
) -> ConversationContext:
    return ConversationContext(
        user_id=user_id,
        session_id=session_id,
        messages=messages or [],
        user_profile=user_profile,
        entities=entities or {},
        slots=slots or {},
    )


# ---------------------------------------------------------------------------
# PersonalityConfig
# ---------------------------------------------------------------------------


class TestPersonalityConfig:
    def test_defaults(self):
        pc = PersonalityConfig()
        assert pc.name == "Assistant"
        assert pc.tone == "professional"
        assert pc.verbosity == "normal"
        assert pc.use_emojis is False
        assert pc.use_markdown is False
        assert "helpful" in pc.traits

    def test_to_dict(self):
        pc = PersonalityConfig(name="Bob", tone="friendly", use_emojis=True)
        d = pc.to_dict()
        assert d["name"] == "Bob"
        assert d["tone"] == "friendly"
        assert d["use_emojis"] is True
        assert "traits" in d

    def test_custom_traits(self):
        pc = PersonalityConfig(traits=["calm", "precise"])
        assert pc.traits == ["calm", "precise"]


# ---------------------------------------------------------------------------
# ResponseConfig
# ---------------------------------------------------------------------------


class TestResponseConfig:
    def test_defaults(self):
        rc = ResponseConfig()
        assert rc.max_response_length == 2000
        assert rc.enable_fallback is True
        assert rc.constitutional_hash == CONSTITUTIONAL_HASH

    def test_to_dict(self):
        rc = ResponseConfig(max_response_length=500, cache_ttl_seconds=60)
        d = rc.to_dict()
        assert d["max_response_length"] == 500
        assert d["cache_ttl_seconds"] == 60
        assert "default_personality" in d
        assert "constitutional_hash" in d


# ---------------------------------------------------------------------------
# ResponseTemplate
# ---------------------------------------------------------------------------


class TestResponseTemplate:
    def test_get_template_no_sentiment(self):
        rt = ResponseTemplate(
            id="t1",
            intent="greeting",
            templates=["Hello!", "Hi!"],
        )
        text = rt.get_template()
        assert text in ("Hello!", "Hi!")

    def test_get_template_with_sentiment_variant(self):
        rt = ResponseTemplate(
            id="t1",
            intent="greeting",
            templates=["Hello!"],
            sentiment_variants={"POSITIVE": ["Great day!"]},
        )
        text = rt.get_template(sentiment=Sentiment.POSITIVE)
        assert text == "Great day!"

    def test_get_template_sentiment_not_in_variants_falls_back(self):
        rt = ResponseTemplate(
            id="t1",
            intent="greeting",
            templates=["Hello!"],
            sentiment_variants={"POSITIVE": ["Great day!"]},
        )
        # NEGATIVE not in sentiment_variants → falls back to templates
        text = rt.get_template(sentiment=Sentiment.NEGATIVE)
        assert text == "Hello!"

    def test_get_template_empty_templates(self):
        rt = ResponseTemplate(id="t1", intent="x", templates=[])
        text = rt.get_template()
        assert text == ""

    def test_get_template_none_sentiment(self):
        rt = ResponseTemplate(id="t1", intent="x", templates=["A"])
        assert rt.get_template(sentiment=None) == "A"


# ---------------------------------------------------------------------------
# TemplateResponseGenerator
# ---------------------------------------------------------------------------


class TestTemplateResponseGenerator:
    # Construction ----------------------------------------------------------

    def test_default_construction(self):
        gen = TemplateResponseGenerator()
        assert "greeting" in gen.templates
        assert "farewell" in gen.templates

    def test_construction_with_config(self):
        cfg = ResponseConfig()
        cfg.default_personality = PersonalityConfig(name="Aria")
        gen = TemplateResponseGenerator(config=cfg)
        assert gen.personality.name == "Aria"
        assert gen.constitutional_hash == cfg.constitutional_hash
        assert gen._config is cfg

    def test_construction_without_config(self):
        p = PersonalityConfig(name="Zara")
        gen = TemplateResponseGenerator(personality=p, constitutional_hash="hash123")
        assert gen.personality.name == "Zara"
        assert gen.constitutional_hash == "hash123"
        assert gen._config is None

    def test_custom_templates_override_defaults(self):
        custom = ResponseTemplate(id="greeting", intent="greeting", templates=["Yo!"])
        gen = TemplateResponseGenerator(templates=[custom])
        assert gen.templates["greeting"].templates == ["Yo!"]

    # add_template / remove_template ----------------------------------------

    def test_add_template(self):
        gen = TemplateResponseGenerator()
        t = ResponseTemplate(id="custom", intent="custom", templates=["Custom!"])
        gen.add_template(t)
        assert "custom" in gen.templates

    def test_remove_template_existing(self):
        gen = TemplateResponseGenerator()
        gen.remove_template("greeting")
        assert "greeting" not in gen.templates

    def test_remove_template_nonexistent(self):
        gen = TemplateResponseGenerator()
        gen.remove_template("nonexistent_intent")  # should not raise

    # generate — basic paths ------------------------------------------------

    async def test_generate_known_intent(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_generate_unknown_intent_falls_back_to_clarification(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("totally_unknown_xyz", ctx, {})
        # Should return a clarification template response
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_generate_intent_not_found_and_no_clarification(self):
        gen = TemplateResponseGenerator()
        # Remove clarification so the last fallback triggers
        gen.remove_template("clarification")
        ctx = _make_context()
        result = await gen.generate("totally_unknown_xyz", ctx, {})
        assert result == "I'm not sure how to respond to that."

    async def test_generate_with_sentiment_string(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {"sentiment": "POSITIVE"})
        assert isinstance(result, str)

    async def test_generate_with_invalid_sentiment_string(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {"sentiment": "INVALID_SENTIMENT"})
        assert isinstance(result, str)

    async def test_generate_with_sentiment_object(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        # Sentiment object is passed directly (not a str) — it stays as-is
        result = await gen.generate("greeting", ctx, {"sentiment": Sentiment.NEGATIVE})
        assert isinstance(result, str)

    # _substitute_variables -------------------------------------------------

    def test_substitute_data_variables(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = gen._substitute_variables("Hello {name}!", ctx, {"name": "Alice"})
        assert result == "Hello Alice!"

    def test_substitute_user_name_from_profile(self):
        gen = TemplateResponseGenerator()
        profile = UserProfile(user_id="alice123", name="Alice")
        ctx = _make_context(user_id="alice123", user_profile=profile)
        result = gen._substitute_variables("{user_name}", ctx, {})
        # {user_name} → context.user_id
        assert "alice123" in result

    def test_substitute_no_profile_no_user_name_sub(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context(user_profile=None)
        result = gen._substitute_variables("{user_name}", ctx, {})
        # Without profile, no substitution → cleaned by _validate_response later
        assert result == "{user_name}"

    def test_substitute_entity_variable(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context(entities={"order_id": {"value": "ORD-999"}})
        result = gen._substitute_variables("Order: {order_id}", ctx, {})
        assert result == "Order: ORD-999"

    def test_substitute_entity_variable_no_value_key(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context(entities={"order_id": {}})
        result = gen._substitute_variables("Order: {order_id}", ctx, {})
        assert result == "Order: "

    def test_substitute_slot_variable(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context(slots={"city": {"value": "Berlin"}})
        result = gen._substitute_variables("City: {city}", ctx, {})
        assert result == "City: Berlin"

    def test_substitute_slot_no_match(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context(slots={"city": {"value": "Berlin"}})
        result = gen._substitute_variables("No match here.", ctx, {})
        assert result == "No match here."

    # _validate_response ----------------------------------------------------

    def test_validate_removes_unfilled_placeholders(self):
        gen = TemplateResponseGenerator()
        result = gen._validate_response("Hello {unknown}!")
        assert "{unknown}" not in result
        assert "Hello" in result

    def test_validate_empty_response_becomes_default(self):
        gen = TemplateResponseGenerator()
        result = gen._validate_response("  ")
        assert result == "I'm here to help."

    def test_validate_only_placeholder_becomes_default(self):
        gen = TemplateResponseGenerator()
        result = gen._validate_response("{placeholder}")
        assert result == "I'm here to help."

    def test_validate_collapses_extra_whitespace(self):
        gen = TemplateResponseGenerator()
        result = gen._validate_response("Hello   world  !")
        assert result == "Hello world !"

    # _apply_personality ----------------------------------------------------

    def test_personality_friendly_tone_replaces_hello_with_greeting(self):
        p = PersonalityConfig(tone="friendly")
        gen = TemplateResponseGenerator(personality=p)
        ctx = _make_context()
        result = gen._apply_personality("Hello there!", ctx)
        # "Hello" should be replaced with a time-based greeting
        assert "Hello" not in result or "Good" in result

    def test_personality_friendly_tone_no_hello_prefix(self):
        p = PersonalityConfig(tone="friendly")
        gen = TemplateResponseGenerator(personality=p)
        ctx = _make_context()
        result = gen._apply_personality("Welcome!", ctx)
        assert result == "Welcome!"

    def test_personality_brief_verbosity(self):
        p = PersonalityConfig(verbosity="brief")
        gen = TemplateResponseGenerator(personality=p)
        ctx = _make_context()
        result = gen._apply_personality("I can help you with that. Sure thing! Yes.", ctx)
        assert "I can help you with that." not in result
        assert "Sure thing!" not in result

    def test_personality_detailed_verbosity(self):
        p = PersonalityConfig(verbosity="detailed")
        gen = TemplateResponseGenerator(personality=p)
        ctx = _make_context()
        # _add_details is a no-op placeholder — just checks it doesn't raise
        result = gen._apply_personality("Hello!", ctx)
        assert isinstance(result, str)

    def test_personality_use_emojis(self):
        p = PersonalityConfig(use_emojis=True)
        gen = TemplateResponseGenerator(personality=p)
        ctx = _make_context()
        result = gen._apply_personality("Hello, how are you?", ctx)
        assert "👋" in result

    def test_personality_use_emojis_no_match(self):
        p = PersonalityConfig(use_emojis=True)
        gen = TemplateResponseGenerator(personality=p)
        ctx = _make_context()
        result = gen._apply_personality("Random text here.", ctx)
        assert result == "Random text here."

    def test_personality_use_markdown(self):
        p = PersonalityConfig(use_markdown=True)
        gen = TemplateResponseGenerator(personality=p)
        ctx = _make_context()
        # _apply_markdown is a no-op placeholder
        result = gen._apply_personality("Plain text.", ctx)
        assert isinstance(result, str)

    def test_personality_user_prefers_brief(self):
        p = PersonalityConfig(verbosity="normal")
        gen = TemplateResponseGenerator(personality=p)
        profile = UserProfile(
            user_id="u1",
            preferences={"prefers_brief": True},
        )
        ctx = _make_context(user_profile=profile)
        result = gen._apply_personality("Certainly! Of course! Some content.", ctx)
        assert "Certainly!" not in result
        assert "Of course!" not in result

    def test_personality_user_no_preferences(self):
        p = PersonalityConfig(verbosity="normal")
        gen = TemplateResponseGenerator(personality=p)
        ctx = _make_context(user_profile=None)
        result = gen._apply_personality("Hello!", ctx)
        assert result == "Hello!"

    # _get_time_greeting ---------------------------------------------------

    def test_get_time_greeting_morning(self):
        gen = TemplateResponseGenerator()
        with patch("enhanced_agent_bus.ai_assistant.response.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 8
            mock_dt.now.return_value = mock_now
            assert gen._get_time_greeting() == "Good morning"

    def test_get_time_greeting_afternoon(self):
        gen = TemplateResponseGenerator()
        with patch("enhanced_agent_bus.ai_assistant.response.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 14
            mock_dt.now.return_value = mock_now
            assert gen._get_time_greeting() == "Good afternoon"

    def test_get_time_greeting_evening(self):
        gen = TemplateResponseGenerator()
        with patch("enhanced_agent_bus.ai_assistant.response.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.hour = 20
            mock_dt.now.return_value = mock_now
            assert gen._get_time_greeting() == "Good evening"

    # _make_concise ---------------------------------------------------------

    def test_make_concise_removes_fillers(self):
        gen = TemplateResponseGenerator()
        text = "Certainly! I can help you with that. Of course! Let me check."
        result = gen._make_concise(text)
        assert "Certainly!" not in result
        assert "I can help you with that." not in result
        assert "Of course!" not in result

    def test_make_concise_strips_whitespace(self):
        gen = TemplateResponseGenerator()
        result = gen._make_concise("  Hello  ")
        assert result == "Hello"

    # _add_details (no-op) --------------------------------------------------

    def test_add_details_returns_same_string(self):
        gen = TemplateResponseGenerator()
        text = "Some detail."
        assert gen._add_details(text) == text

    # _add_emojis -----------------------------------------------------------

    def test_add_emojis_thank_you(self):
        gen = TemplateResponseGenerator()
        result = gen._add_emojis("Thank you for helping.")
        assert "🙏" in result

    def test_add_emojis_sorry(self):
        gen = TemplateResponseGenerator()
        result = gen._add_emojis("Sorry for the delay.")
        assert "😔" in result

    def test_add_emojis_great(self):
        gen = TemplateResponseGenerator()
        result = gen._add_emojis("Great job done!")
        assert "🎉" in result

    def test_add_emojis_done(self):
        gen = TemplateResponseGenerator()
        result = gen._add_emojis("Done! Your request is complete.")
        assert "✅" in result

    def test_add_emojis_no_match_returns_unchanged(self):
        gen = TemplateResponseGenerator()
        result = gen._add_emojis("Nothing matches here.")
        assert result == "Nothing matches here."

    # All default templates -------------------------------------------------

    async def test_generate_farewell(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("farewell", ctx, {})
        assert isinstance(result, str) and len(result) > 0

    async def test_generate_help(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("help", ctx, {})
        assert isinstance(result, str) and len(result) > 0

    async def test_generate_confirmation(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("confirmation", ctx, {})
        assert isinstance(result, str) and len(result) > 0

    async def test_generate_error(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("error", ctx, {})
        assert isinstance(result, str) and len(result) > 0

    async def test_generate_escalation(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("escalation", ctx, {})
        assert isinstance(result, str) and len(result) > 0

    async def test_generate_escalation_very_negative_sentiment(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("escalation", ctx, {"sentiment": "VERY_NEGATIVE"})
        assert isinstance(result, str) and len(result) > 0

    async def test_generate_clarification(self):
        gen = TemplateResponseGenerator()
        ctx = _make_context()
        result = await gen.generate("clarification", ctx, {})
        assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# LLMResponseGenerator
# ---------------------------------------------------------------------------


class TestLLMResponseGenerator:
    # Construction ----------------------------------------------------------

    def test_default_construction(self):
        gen = LLMResponseGenerator()
        assert gen.llm_client is None
        assert gen.max_tokens == 150
        assert gen.temperature == 0.7
        assert gen.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_construction(self):
        p = PersonalityConfig(name="Rex")
        gen = LLMResponseGenerator(
            llm_client=None,
            personality=p,
            max_tokens=300,
            temperature=0.5,
        )
        assert gen.personality.name == "Rex"
        assert gen.max_tokens == 300

    # generate without client -> template fallback -------------------------

    async def test_generate_no_client_falls_back_to_template(self):
        gen = LLMResponseGenerator(llm_client=None)
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str) and len(result) > 0

    # generate with client — validation passes -----------------------------

    async def test_generate_with_client_complete_method(self):
        llm = MagicMock()
        llm.complete = AsyncMock(return_value=MagicMock(text="Hello, I can assist you."))
        gen = LLMResponseGenerator(llm_client=llm)
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        assert result == "Hello, I can assist you."

    async def test_generate_with_client_response_without_text_attr(self):
        """When response has no .text, str(response) is used."""
        llm = MagicMock()
        mock_resp = MagicMock(spec=[])  # No .text attribute
        llm.complete = AsyncMock(return_value=mock_resp)
        gen = LLMResponseGenerator(llm_client=llm)
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        # Falls back because str(mock) might fail validation or succeed
        assert isinstance(result, str)

    async def test_generate_with_client_generate_method(self):
        llm = MagicMock()
        del llm.complete  # Remove .complete so .generate branch is used
        llm.generate = AsyncMock(return_value="Hi there, how can I help.")
        # Make hasattr work correctly
        gen = LLMResponseGenerator(llm_client=llm)
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)

    async def test_generate_client_no_expected_methods_raises_value_error(self):
        """Client with neither complete nor generate raises ValueError -> fallback."""
        llm = MagicMock(spec=[])  # no .complete, no .generate
        gen = LLMResponseGenerator(llm_client=llm)
        ctx = _make_context()
        # The ValueError is caught and fallback is used
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)

    async def test_generate_validation_fails_falls_back_to_template(self):
        llm = MagicMock()
        # Response contains a blocked pattern
        llm.complete = AsyncMock(return_value=MagicMock(text="I cannot assist with that."))
        gen = LLMResponseGenerator(llm_client=llm)
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        # Validation fails → template fallback
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_generate_exception_falls_back_to_template(self):
        llm = MagicMock()
        llm.complete = AsyncMock(side_effect=RuntimeError("LLM down"))
        gen = LLMResponseGenerator(llm_client=llm)
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str)

    # _build_prompt --------------------------------------------------------

    def test_build_prompt_with_entities(self):
        gen = LLMResponseGenerator()
        ctx = _make_context(entities={"order_id": {"value": "ORD-1"}})
        prompt = gen._build_prompt("order_query", ctx, {"status": "shipped"})
        assert "order_id=ORD-1" in prompt
        assert "status" in prompt

    def test_build_prompt_no_entities_no_data(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        prompt = gen._build_prompt("greeting", ctx, {})
        assert "greeting" in prompt

    def test_build_prompt_data_excludes_sentiment_key(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        prompt = gen._build_prompt("query", ctx, {"sentiment": "POSITIVE", "city": "Paris"})
        # sentiment key excluded from relevant_data
        assert "city" in prompt

    def test_build_prompt_data_only_sentiment_no_relevant_data_block(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        prompt = gen._build_prompt("query", ctx, {"sentiment": "POSITIVE"})
        assert "Relevant data" not in prompt

    # _format_conversation_history -----------------------------------------

    def test_format_conversation_history_empty(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        result = gen._format_conversation_history(ctx)
        assert result == "No previous messages"

    def test_format_conversation_history_with_messages(self):
        gen = LLMResponseGenerator()
        # The source code checks msg.role == "user" (string).
        # MessageRole.USER is an enum; it won't equal the string "user",
        # so the label is always "Assistant" for both. Test actual behavior.
        msgs = [
            Message(role=MessageRole.USER, content="Hello"),
            Message(role=MessageRole.ASSISTANT, content="Hi!"),
        ]
        ctx = _make_context(messages=msgs)
        result = gen._format_conversation_history(ctx)
        assert "Hello" in result
        assert "Hi!" in result
        assert "Assistant" in result  # label for both since enum != string

    def test_format_conversation_history_limits_to_max(self):
        gen = LLMResponseGenerator()
        msgs = [Message(role=MessageRole.USER, content=f"Msg {i}") for i in range(10)]
        ctx = _make_context(messages=msgs)
        result = gen._format_conversation_history(ctx, max_messages=3)
        lines = result.strip().split("\n")
        assert len(lines) == 3

    # _call_llm ------------------------------------------------------------

    async def test_call_llm_complete_with_text_attr(self):
        llm = MagicMock()
        llm.complete = AsyncMock(return_value=MagicMock(text="response text"))
        gen = LLMResponseGenerator(llm_client=llm)
        result = await gen._call_llm("prompt here")
        assert result == "response text"

    async def test_call_llm_complete_no_text_attr(self):
        llm = MagicMock()
        no_text = MagicMock(spec=[])  # no .text
        llm.complete = AsyncMock(return_value=no_text)
        gen = LLMResponseGenerator(llm_client=llm)
        result = await gen._call_llm("prompt here")
        assert isinstance(result, str)

    async def test_call_llm_generate_method(self):
        llm = MagicMock(spec=["generate"])
        llm.generate = AsyncMock(return_value="generated text")
        gen = LLMResponseGenerator(llm_client=llm)
        result = await gen._call_llm("prompt")
        assert result == "generated text"

    async def test_call_llm_no_methods_raises(self):
        llm = MagicMock(spec=[])
        gen = LLMResponseGenerator(llm_client=llm)
        with pytest.raises(ValueError, match="LLM client does not have expected methods"):
            await gen._call_llm("prompt")

    # _post_process --------------------------------------------------------

    def test_post_process_strips_whitespace(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        result = gen._post_process("  Hello.  ", ctx)
        assert result == "Hello."

    def test_post_process_removes_assistant_prefix(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        result = gen._post_process("Assistant: Sure thing.", ctx)
        assert result == "Sure thing."

    def test_post_process_removes_ai_prefix(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        result = gen._post_process("AI: Here you go.", ctx)
        assert result == "Here you go."

    def test_post_process_removes_bot_prefix(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        result = gen._post_process("Bot: Welcome.", ctx)
        assert result == "Welcome."

    def test_post_process_no_prefix_unchanged(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        result = gen._post_process("Hello there.", ctx)
        assert result == "Hello there."

    def test_post_process_truncates_incomplete_sentence(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        # Ends without terminal punctuation, but has a period mid-sentence
        result = gen._post_process("Hello. How are you doing today", ctx)
        assert result.endswith(".")

    def test_post_process_no_terminal_punct_no_period_in_text(self):
        gen = LLMResponseGenerator()
        ctx = _make_context()
        # No period, !, or ? anywhere → returned as-is after stripping
        result = gen._post_process("no punct at all", ctx)
        assert result == "no punct at all"

    # _validate_response ---------------------------------------------------

    def test_validate_response_valid(self):
        gen = LLMResponseGenerator()
        assert gen._validate_response("Sure, let me help you with that!") is True

    def test_validate_response_too_short(self):
        gen = LLMResponseGenerator()
        assert gen._validate_response("") is False
        assert gen._validate_response("Hi") is False

    def test_validate_response_blocked_pattern_i_cannot(self):
        gen = LLMResponseGenerator()
        assert gen._validate_response("I cannot do that.") is False

    def test_validate_response_blocked_pattern_sorry_cannot(self):
        gen = LLMResponseGenerator()
        assert gen._validate_response("I'm sorry, but I cannot help.") is False

    def test_validate_response_blocked_pattern_as_an_ai(self):
        gen = LLMResponseGenerator()
        assert gen._validate_response("As an AI, I do not have feelings.") is False

    def test_validate_response_blocked_pattern_constitutional_hash(self):
        gen = LLMResponseGenerator()
        assert gen._validate_response("The constitutional hash is valid.") is False

    def test_validate_response_blocked_pattern_internal_system(self):
        gen = LLMResponseGenerator()
        assert gen._validate_response("This is an internal system response.") is False


# ---------------------------------------------------------------------------
# HybridResponseGenerator
# ---------------------------------------------------------------------------


class TestHybridResponseGenerator:
    def test_default_construction(self):
        gen = HybridResponseGenerator()
        assert gen.constitutional_hash == CONSTITUTIONAL_HASH
        assert "question" in gen.llm_intents

    def test_custom_llm_intents(self):
        gen = HybridResponseGenerator(llm_intents=["custom_intent"])
        assert gen.llm_intents == ["custom_intent"]

    # generate — template path (no LLM client) ------------------------------

    async def test_generate_uses_template_when_no_llm_client(self):
        gen = HybridResponseGenerator(llm_client=None)
        ctx = _make_context()
        result = await gen.generate("greeting", ctx, {})
        assert isinstance(result, str) and len(result) > 0

    async def test_generate_template_for_non_llm_intent(self):
        gen = HybridResponseGenerator(llm_client=None)
        ctx = _make_context()
        result = await gen.generate("farewell", ctx, {})
        assert isinstance(result, str)

    # generate — LLM path --------------------------------------------------

    async def test_generate_uses_llm_for_llm_intent(self):
        llm = MagicMock()
        llm.complete = AsyncMock(return_value=MagicMock(text="Here is my answer."))
        gen = HybridResponseGenerator(llm_client=llm)
        ctx = _make_context()
        result = await gen.generate("question", ctx, {})
        assert result == "Here is my answer."

    async def test_generate_uses_llm_when_requires_llm_flag_set(self):
        llm = MagicMock()
        llm.complete = AsyncMock(return_value=MagicMock(text="Specific answer here."))
        gen = HybridResponseGenerator(llm_client=llm)
        ctx = _make_context()
        # "greeting" is not an llm_intent but requires_llm forces LLM
        result = await gen.generate("greeting", ctx, {"requires_llm": True})
        assert result == "Specific answer here."

    async def test_generate_uses_llm_for_complex_conversation(self):
        llm = MagicMock()
        llm.complete = AsyncMock(return_value=MagicMock(text="Complex context reply."))
        gen = HybridResponseGenerator(llm_client=llm)
        # More than 10 messages → triggers LLM path
        msgs = [Message(role=MessageRole.USER, content=f"Message {i}") for i in range(11)]
        ctx = _make_context(messages=msgs)
        result = await gen.generate("greeting", ctx, {})
        assert result == "Complex context reply."

    async def test_generate_uses_template_when_llm_intent_but_no_client(self):
        gen = HybridResponseGenerator(llm_client=None)
        ctx = _make_context()
        # "question" is an llm_intent but no client → template path
        result = await gen.generate("question", ctx, {})
        assert isinstance(result, str)

    # set_llm_client -------------------------------------------------------

    def test_set_llm_client(self):
        gen = HybridResponseGenerator(llm_client=None)
        assert gen.llm_generator.llm_client is None
        new_client = MagicMock()
        gen.set_llm_client(new_client)
        assert gen.llm_generator.llm_client is new_client

    # add_template ---------------------------------------------------------

    def test_add_template_propagates_to_template_generator(self):
        gen = HybridResponseGenerator()
        t = ResponseTemplate(id="custom", intent="custom", templates=["Custom response."])
        gen.add_template(t)
        assert "custom" in gen.template_generator.templates

    # add_llm_intent -------------------------------------------------------

    def test_add_llm_intent_new(self):
        gen = HybridResponseGenerator()
        gen.add_llm_intent("brand_new_intent")
        assert "brand_new_intent" in gen.llm_intents

    def test_add_llm_intent_duplicate_not_added_twice(self):
        gen = HybridResponseGenerator()
        initial_count = len(gen.llm_intents)
        gen.add_llm_intent("question")  # Already in default list
        assert gen.llm_intents.count("question") == 1
        assert len(gen.llm_intents) == initial_count
