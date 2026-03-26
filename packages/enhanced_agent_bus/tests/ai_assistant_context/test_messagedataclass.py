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


class TestMessageDataclass:
    def test_default_fields(self):
        msg = Message(role=MessageRole.USER, content="hello")
        assert msg.intent is None
        assert msg.entities == []
        assert msg.metadata == {}
        assert msg.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(msg.timestamp, datetime)

    def test_to_dict_with_enum_role(self):
        msg = Message(role=MessageRole.ASSISTANT, content="hi")
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "hi"
        assert isinstance(d["timestamp"], str)
        assert d["intent"] is None
        assert d["entities"] == []
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_with_string_role(self):
        # role can be set as string (type: ignore) - exercises the isinstance branch
        msg = Message(role="user", content="test")  # type: ignore[arg-type]
        d = msg.to_dict()
        assert d["role"] == "user"

    def test_to_dict_with_metadata(self):
        msg = Message(role=MessageRole.USER, content="x", metadata={"key": "val"})
        d = msg.to_dict()
        assert d["metadata"]["key"] == "val"

    def test_to_dict_with_intent_and_entities(self):
        msg = Message(
            role=MessageRole.USER,
            content="order",
            intent="purchase",
            entities=[{"type": "product", "value": "laptop"}],
        )
        d = msg.to_dict()
        assert d["intent"] == "purchase"
        assert len(d["entities"]) == 1

    def test_from_dict_string_timestamp(self):
        ts = "2024-06-15T12:00:00+00:00"
        data = {
            "role": "user",
            "content": "hello",
            "timestamp": ts,
            "metadata": {},
            "intent": "greet",
            "entities": [],
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        msg = Message.from_dict(data)
        assert isinstance(msg.timestamp, datetime)
        assert msg.intent == "greet"

    def test_from_dict_none_timestamp(self):
        data = {"role": "assistant", "content": "reply", "timestamp": None}
        msg = Message.from_dict(data)
        assert isinstance(msg.timestamp, datetime)

    def test_from_dict_missing_timestamp(self):
        data = {"role": "user", "content": "bare"}
        msg = Message.from_dict(data)
        assert isinstance(msg.timestamp, datetime)

    def test_from_dict_string_role_user(self):
        data = {"role": "user", "content": "x"}
        msg = Message.from_dict(data)
        assert msg.role == MessageRole.USER

    def test_from_dict_string_role_assistant(self):
        data = {"role": "assistant", "content": "x"}
        msg = Message.from_dict(data)
        assert msg.role == MessageRole.ASSISTANT

    def test_from_dict_string_role_system(self):
        data = {"role": "system", "content": "x"}
        msg = Message.from_dict(data)
        assert msg.role == MessageRole.SYSTEM

    def test_from_dict_enum_role_passes_through(self):
        # If role is already a MessageRole, the isinstance(role, str) branch is False
        # and role is used as-is
        data = {"role": MessageRole.USER, "content": "x"}
        msg = Message.from_dict(data)
        assert msg.role == MessageRole.USER

    def test_from_dict_defaults_for_optional_fields(self):
        data = {"role": "user", "content": "bare minimum"}
        msg = Message.from_dict(data)
        assert msg.intent is None
        assert msg.entities == []
        assert msg.metadata == {}
        assert msg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_from_dict_custom_constitutional_hash(self):
        data = {"role": "user", "content": "x", "constitutional_hash": "custom_hash"}
        msg = Message.from_dict(data)
        assert msg.constitutional_hash == "custom_hash"


# ---------------------------------------------------------------------------
# UserProfile dataclass
# ---------------------------------------------------------------------------
