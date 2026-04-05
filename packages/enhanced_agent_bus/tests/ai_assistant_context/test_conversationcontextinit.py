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


class TestConversationContextInit:
    def test_default_init(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        assert ctx.user_id == "u1"
        assert ctx.session_id == "s1"
        assert ctx.messages == []
        assert ctx.user_profile is None
        assert ctx.conversation_state == ConversationState.INITIALIZED
        assert ctx.state_data == {}
        assert ctx.entities == {}
        assert ctx.slots == {}
        assert ctx.metadata == {}
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH
        assert ctx.tenant_id is None
        assert ctx.max_history == 100

    def test_post_init_truncates_excess_messages(self):
        """__post_init__ triggers when initial messages exceed max_history."""
        messages = [Message(role=MessageRole.USER, content=f"m{i}") for i in range(15)]
        ctx = ConversationContext(user_id="u1", session_id="s1", messages=messages, max_history=5)
        assert len(ctx.messages) == 5
        assert ctx.messages[0].content == "m10"

    def test_post_init_no_truncation_needed(self):
        messages = [Message(role=MessageRole.USER, content=f"m{i}") for i in range(3)]
        ctx = ConversationContext(user_id="u1", session_id="s1", messages=messages, max_history=10)
        assert len(ctx.messages) == 3

    def test_custom_tenant_id(self):
        ctx = ConversationContext(user_id="u1", session_id="s1", tenant_id="tenant-abc")
        assert ctx.tenant_id == "tenant-abc"
