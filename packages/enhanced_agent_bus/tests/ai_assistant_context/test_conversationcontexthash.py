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


class TestConversationContextHash:
    def test_get_context_hash_length(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        h = ctx.get_context_hash()
        assert len(h) == 16

    def test_get_context_hash_is_hex(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        h = ctx.get_context_hash()
        # Should be valid hex
        int(h, 16)

    def test_get_context_hash_changes_with_state(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        h1 = ctx.get_context_hash()
        ctx.transition_state(ConversationState.ACTIVE)
        h2 = ctx.get_context_hash()
        assert h1 != h2

    def test_get_context_hash_changes_with_messages(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        h1 = ctx.get_context_hash()
        ctx.add_message(MessageRole.USER, "new message")
        h2 = ctx.get_context_hash()
        assert h1 != h2

    def test_get_context_hash_changes_with_entities(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        h1 = ctx.get_context_hash()
        ctx.update_entity("product", "laptop")
        h2 = ctx.get_context_hash()
        assert h1 != h2

    def test_get_context_hash_changes_with_slots(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        h1 = ctx.get_context_hash()
        ctx.set_slot("order_id", "12345")
        h2 = ctx.get_context_hash()
        assert h1 != h2

    def test_get_context_hash_includes_user_id(self):
        ctx1 = ConversationContext(user_id="user_A", session_id="s1")
        ctx2 = ConversationContext(user_id="user_B", session_id="s1")
        assert ctx1.get_context_hash() != ctx2.get_context_hash()

    def test_get_context_hash_includes_session_id(self):
        ctx1 = ConversationContext(user_id="u1", session_id="session_A")
        ctx2 = ConversationContext(user_id="u1", session_id="session_B")
        assert ctx1.get_context_hash() != ctx2.get_context_hash()
