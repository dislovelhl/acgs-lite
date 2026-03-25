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


class TestContextManagerResolveReferences:
    async def test_pronoun_it_resolved_with_object_entity(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("object", "MacBook")
        resolved = await mgr.resolve_references("I want it please", ctx)
        assert "MacBook" in resolved
        assert "it" not in resolved.replace("MacBook", "")

    async def test_pronoun_they_resolved_with_people_entity(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("people", "the_team")
        resolved = await mgr.resolve_references("they are ready", ctx)
        assert "the_team" in resolved

    async def test_pronoun_he_resolved(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("male_person", "John")
        resolved = await mgr.resolve_references("he arrived", ctx)
        assert "John" in resolved

    async def test_pronoun_she_resolved(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("female_person", "Alice")
        resolved = await mgr.resolve_references("she called", ctx)
        assert "Alice" in resolved

    async def test_pronoun_that_resolved(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("previous_topic", "project_X")
        resolved = await mgr.resolve_references("about that matter", ctx)
        assert "project_X" in resolved

    async def test_pronoun_this_resolved(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("current_topic", "current_task")
        resolved = await mgr.resolve_references("this is important", ctx)
        assert "current_task" in resolved

    async def test_pronoun_there_resolved(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("location", "New_York")
        resolved = await mgr.resolve_references("go there", ctx)
        assert "New_York" in resolved

    async def test_pronoun_not_resolved_no_entity(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        resolved = await mgr.resolve_references("I want it please", ctx)
        assert "it" in resolved

    async def test_temporal_today_resolved(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        resolved = await mgr.resolve_references("today is special", ctx)
        assert "today" not in resolved

    async def test_temporal_tomorrow_resolved(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        resolved = await mgr.resolve_references("see you tomorrow", ctx)
        assert "tomorrow" not in resolved

    async def test_temporal_yesterday_resolved(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        resolved = await mgr.resolve_references("yesterday was good", ctx)
        assert "yesterday" not in resolved

    async def test_temporal_next_week_resolved(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        resolved = await mgr.resolve_references("next week meeting", ctx)
        assert "next week" not in resolved

    async def test_temporal_last_week_resolved(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        resolved = await mgr.resolve_references("last week event", ctx)
        assert "last week" not in resolved

    async def test_temporal_now_resolved(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        resolved = await mgr.resolve_references("do it now", ctx)
        assert "now" not in resolved

    async def test_temporal_later_resolved(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        resolved = await mgr.resolve_references("maybe later", ctx)
        assert "later" not in resolved

    async def test_no_references_text_unchanged(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        text = "the quick brown fox"
        resolved = await mgr.resolve_references(text, ctx)
        assert resolved == text

    async def test_multiple_pronouns_resolved(self):
        """Multiple entities can be resolved in a single call."""
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("object", "laptop_X")
        ctx.update_entity("location", "office")
        resolved = await mgr.resolve_references("take it there", ctx)
        assert "laptop_X" in resolved
        assert "office" in resolved


# ---------------------------------------------------------------------------
# ContextManager._resolve_temporal
# ---------------------------------------------------------------------------
