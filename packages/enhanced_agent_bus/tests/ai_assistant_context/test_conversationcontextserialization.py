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
from datetime import UTC, datetime, timezone
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


class TestConversationContextSerialization:
    def test_to_dict_all_keys(self):
        ctx = ConversationContext(user_id="u1", session_id="s1", tenant_id="t1")
        d = ctx.to_dict()
        expected_keys = {
            "user_id",
            "session_id",
            "messages",
            "user_profile",
            "conversation_state",
            "state_data",
            "entities",
            "slots",
            "metadata",
            "created_at",
            "updated_at",
            "constitutional_hash",
            "tenant_id",
        }
        assert set(d.keys()) == expected_keys
        assert d["tenant_id"] == "t1"
        assert d["user_profile"] is None

    def test_to_dict_with_user_profile(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.user_profile = UserProfile(user_id="u1", name="Bob")
        d = ctx.to_dict()
        assert d["user_profile"] is not None
        assert d["user_profile"]["name"] == "Bob"

    def test_to_dict_messages_serialized(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(MessageRole.USER, "test")
        d = ctx.to_dict()
        assert len(d["messages"]) == 1
        assert d["messages"][0]["content"] == "test"

    def test_from_dict_minimal(self):
        data = {
            "user_id": "u1",
            "session_id": "s1",
            "messages": [],
            "conversation_state": "initialized",
        }
        ctx = ConversationContext.from_dict(data)
        assert ctx.user_id == "u1"
        assert ctx.session_id == "s1"

    def test_from_dict_full(self):
        data = {
            "user_id": "u2",
            "session_id": "s2",
            "messages": [
                {
                    "role": "user",
                    "content": "hello",
                    "timestamp": "2024-01-01T00:00:00+00:00",
                    "metadata": {},
                    "intent": None,
                    "entities": [],
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                }
            ],
            "conversation_state": "active",
            "state_data": {"key": "val"},
            "entities": {},
            "slots": {},
            "metadata": {"info": "test"},
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-02T00:00:00+00:00",
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "tenant_id": "tenant-99",
        }
        ctx = ConversationContext.from_dict(data)
        assert ctx.user_id == "u2"
        assert len(ctx.messages) == 1
        assert ctx.conversation_state == ConversationState.ACTIVE
        assert ctx.state_data["key"] == "val"
        assert ctx.tenant_id == "tenant-99"
        assert isinstance(ctx.created_at, datetime)
        assert isinstance(ctx.updated_at, datetime)

    def test_from_dict_missing_timestamps(self):
        data = {
            "user_id": "u1",
            "session_id": "s1",
            "messages": [],
            "conversation_state": "initialized",
        }
        ctx = ConversationContext.from_dict(data)
        assert isinstance(ctx.created_at, datetime)
        assert isinstance(ctx.updated_at, datetime)

    def test_from_dict_with_user_profile(self):
        data = {
            "user_id": "u1",
            "session_id": "s1",
            "messages": [],
            "conversation_state": "active",
            "user_profile": {
                "user_id": "u1",
                "name": "Alice",
                "email": None,
                "preferences": {},
                "metadata": {},
                "history_summary": "",
                "language": "en",
                "timezone": "UTC",
                "created_at": datetime.now(UTC).isoformat(),
                "last_active": datetime.now(UTC).isoformat(),
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        }
        ctx = ConversationContext.from_dict(data)
        assert ctx.user_profile is not None
        assert ctx.user_profile.name == "Alice"

    def test_from_dict_without_user_profile(self):
        data = {
            "user_id": "u1",
            "session_id": "s1",
            "messages": [],
            "conversation_state": "active",
        }
        ctx = ConversationContext.from_dict(data)
        assert ctx.user_profile is None

    def test_from_dict_custom_constitutional_hash(self):
        data = {
            "user_id": "u1",
            "session_id": "s1",
            "messages": [],
            "conversation_state": "initialized",
            "constitutional_hash": "custom_hash",
        }
        ctx = ConversationContext.from_dict(data)
        assert ctx.constitutional_hash == "custom_hash"

    def test_roundtrip_serialization(self):
        ctx = ConversationContext(user_id="u1", session_id="s1", tenant_id="t1")
        ctx.add_message(MessageRole.USER, "hello")
        ctx.update_entity("product", "laptop")
        ctx.set_slot("order_id", "ORD-001")
        ctx.transition_state(ConversationState.ACTIVE)

        d = ctx.to_dict()
        ctx2 = ConversationContext.from_dict(d)

        assert ctx2.user_id == ctx.user_id
        assert ctx2.session_id == ctx.session_id
        assert len(ctx2.messages) == len(ctx.messages)
        assert ctx2.conversation_state == ctx.conversation_state


# ---------------------------------------------------------------------------
# ContextManager
# ---------------------------------------------------------------------------
