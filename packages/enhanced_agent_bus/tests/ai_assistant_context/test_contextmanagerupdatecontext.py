# Constitutional Hash: 608508a9bd224290
"""
ACGS-2 AI Assistant - Context Management Coverage Boost Tests

Comprehensive tests to boost coverage of ai_assistant/context.py to ≥98%.
Covers all classes, methods, code paths, error handling, and edge cases.

asyncio_mode = "auto" is set in pyproject.toml — no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.ai_assistant.context import (
    CONSTITUTIONAL_HASH,
    MAMBA_AVAILABLE,
    MAMBA_CONTEXT_PROCESSING_ERRORS,
    ContextManager,
    ConversationContext,
    ConversationState,
    Message,
    MessageRole,
    UserProfile,
)

# ---------------------------------------------------------------------------
# Module-level constants & enums
# ---------------------------------------------------------------------------


class TestContextManagerUpdateContext:
    async def test_update_context_no_nlu_transitions_to_active(self):
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        result = await mgr.update_context(ctx, "Hello there")
        assert len(result.messages) == 1
        # content stores the original message, not the lowercased resolved version
        assert result.messages[0].content == "Hello there"
        assert result.conversation_state == ConversationState.ACTIVE

    async def test_update_context_already_active_stays_active(self):
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        ctx.transition_state(ConversationState.ACTIVE)
        result = await mgr.update_context(ctx, "second message")
        assert result.conversation_state == ConversationState.ACTIVE

    async def test_update_context_with_nlu_entities_updates_context(self):
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        nlu = {
            "intent": "order",
            "entities": [{"type": "product", "value": "laptop", "confidence": 0.9}],
        }
        result = await mgr.update_context(ctx, "I want a laptop", nlu)
        assert result.get_entity("product") == "laptop"

    async def test_update_context_with_nlu_entity_missing_confidence(self):
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        nlu = {
            "intent": "order",
            "entities": [{"type": "product", "value": "tablet"}],  # no confidence
        }
        result = await mgr.update_context(ctx, "I want a tablet", nlu)
        # Should still update entity with default confidence 1.0
        assert result.get_entity("product") == "tablet"

    async def test_update_context_stores_message_intent(self):
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        nlu = {"intent": "greeting", "entities": []}
        result = await mgr.update_context(ctx, "Hello", nlu)
        assert result.messages[0].intent == "greeting"

    async def test_update_context_stores_message_entities(self):
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        nlu = {
            "intent": "search",
            "entities": [{"type": "color", "value": "blue"}],
        }
        result = await mgr.update_context(ctx, "blue item", nlu)
        assert len(result.messages[0].entities) == 1

    async def test_update_context_no_nlu_no_entities_in_message(self):
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        result = await mgr.update_context(ctx, "bare message", None)
        assert result.messages[0].intent is None
        assert result.messages[0].entities == []

    async def test_update_context_prunes_when_over_max_context_length(self):
        mgr = ContextManager(max_context_length=3)
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        for i in range(4):
            ctx.add_message(MessageRole.USER, f"old {i}")
        result = await mgr.update_context(ctx, "trigger prune")
        assert len(result.messages) <= mgr.max_context_length

    async def test_update_context_reference_resolution_stored(self):
        """Resolved content is stored in message metadata when resolution differs."""
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        # Seed an entity so "it" gets replaced
        ctx.update_entity("object", "the_laptop")
        result = await mgr.update_context(ctx, "I want it now", None)
        # The resolved text differs from original, so metadata should be stored
        last_msg = result.messages[-1]
        assert "resolved_content" in last_msg.metadata

    async def test_update_context_no_reference_resolution_metadata_when_unchanged(self):
        """When resolved text equals original, metadata is NOT stored."""
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        # Message with no pronouns or temporal refs; lowercased == lowercased
        result = await mgr.update_context(ctx, "plain message here", None)
        last_msg = result.messages[-1]
        assert "resolved_content" not in last_msg.metadata

    async def test_update_context_topic_shift_stored(self):
        """Topic shift metadata is stored when shift is detected."""
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        # Seed a prior message with string role so the string comparison hits
        prior = Message(role="user", content="greet", intent="greeting")  # type: ignore[arg-type]
        ctx.messages.append(prior)
        nlu = {"intent": "order_purchase", "entities": []}
        result = await mgr.update_context(ctx, "I want to buy", nlu)
        assert "topic_shift" in result.metadata

    async def test_update_context_topic_shift_no_prior_intent_no_metadata(self):
        """No topic shift stored when there's no prior message with intent."""
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        ctx.add_message(MessageRole.USER, "hi", intent=None)
        nlu = {"intent": "order", "entities": []}
        result = await mgr.update_context(ctx, "buy something", nlu)
        assert "topic_shift" not in result.metadata


# ---------------------------------------------------------------------------
# ContextManager.resolve_references (async)
# ---------------------------------------------------------------------------
