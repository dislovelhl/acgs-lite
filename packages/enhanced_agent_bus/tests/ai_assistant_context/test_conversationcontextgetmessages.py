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


class TestConversationContextGetMessages:
    def test_get_last_user_message(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(MessageRole.USER, "first")
        ctx.add_message(MessageRole.ASSISTANT, "reply")
        ctx.add_message(MessageRole.USER, "second")
        msg = ctx.get_last_user_message()
        assert msg is not None
        assert msg.content == "second"

    def test_get_last_user_message_none_when_empty(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        assert ctx.get_last_user_message() is None

    def test_get_last_user_message_none_when_only_assistant(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(MessageRole.ASSISTANT, "only assistant")
        assert ctx.get_last_user_message() is None

    def test_get_last_assistant_message(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(MessageRole.USER, "question")
        ctx.add_message(MessageRole.ASSISTANT, "answer")
        msg = ctx.get_last_assistant_message()
        assert msg is not None
        assert msg.content == "answer"

    def test_get_last_assistant_message_none_when_empty(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        assert ctx.get_last_assistant_message() is None

    def test_get_last_assistant_message_none_when_only_user(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(MessageRole.USER, "only user")
        assert ctx.get_last_assistant_message() is None

    def test_get_recent_messages_default_count(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        for i in range(15):
            ctx.add_message(MessageRole.USER, f"m{i}")
        recent = ctx.get_recent_messages()
        assert len(recent) == 10
        assert recent[-1].content == "m14"

    def test_get_recent_messages_custom_count(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        for i in range(10):
            ctx.add_message(MessageRole.USER, f"m{i}")
        recent = ctx.get_recent_messages(3)
        assert len(recent) == 3
        assert recent[0].content == "m7"

    def test_get_recent_messages_empty_context(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        recent = ctx.get_recent_messages(5)
        assert recent == []

    def test_get_recent_messages_fewer_than_count(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(MessageRole.USER, "only one")
        recent = ctx.get_recent_messages(10)
        assert len(recent) == 1
