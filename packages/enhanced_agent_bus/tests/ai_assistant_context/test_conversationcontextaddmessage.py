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


class TestConversationContextAddMessage:
    def test_add_message_object(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        msg = Message(role=MessageRole.USER, content="hello")
        returned = ctx.add_message(msg)
        assert returned is msg
        assert len(ctx.messages) == 1

    def test_add_message_with_message_role_enum(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        msg = ctx.add_message(MessageRole.ASSISTANT, "Hi there")
        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "Hi there"

    def test_add_message_with_valid_string_role_user(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        msg = ctx.add_message("user", "from user")
        assert msg.role == MessageRole.USER

    def test_add_message_with_valid_string_role_assistant(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        msg = ctx.add_message("assistant", "from assistant")
        assert msg.role == MessageRole.ASSISTANT

    def test_add_message_with_valid_string_role_system(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        msg = ctx.add_message("system", "system msg")
        assert msg.role == MessageRole.SYSTEM

    def test_add_message_with_invalid_string_defaults_to_user(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        msg = ctx.add_message("unknown_role_xyz", "fallback content")
        assert msg.role == MessageRole.USER

    def test_add_message_empty_content_default(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        msg = ctx.add_message(MessageRole.USER)
        assert msg.content == ""

    def test_add_message_enforces_max_history(self):
        ctx = ConversationContext(user_id="u1", session_id="s1", max_history=3)
        for i in range(7):
            ctx.add_message(MessageRole.USER, f"msg {i}")
        assert len(ctx.messages) == 3
        assert ctx.messages[-1].content == "msg 6"

    def test_add_message_updates_updated_at(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        before = ctx.updated_at
        ctx.add_message(MessageRole.USER, "trigger update")
        assert ctx.updated_at >= before

    def test_add_message_uses_context_constitutional_hash(self):
        ctx = ConversationContext(
            user_id="u1", session_id="s1", constitutional_hash="custom_hash_value"
        )
        msg = ctx.add_message(MessageRole.USER, "test")
        assert msg.constitutional_hash == "custom_hash_value"

    def test_add_message_with_kwargs(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        msg = ctx.add_message(
            MessageRole.USER, "content", intent="purchase", metadata={"src": "api"}
        )
        assert msg.intent == "purchase"
        assert msg.metadata["src"] == "api"
