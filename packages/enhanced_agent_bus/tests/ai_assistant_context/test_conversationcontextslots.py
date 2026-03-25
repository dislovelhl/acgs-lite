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


class TestConversationContextSlots:
    def test_set_and_get_slot(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.set_slot("order_id", "ORD-001")
        assert ctx.get_slot("order_id") == "ORD-001"

    def test_get_slot_default_none(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        assert ctx.get_slot("missing_slot") is None

    def test_get_slot_custom_default(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        assert ctx.get_slot("missing_slot", "fallback") == "fallback"

    def test_set_slot_stores_filled_at(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.set_slot("name", "Alice")
        assert "filled_at" in ctx.slots["name"]

    def test_set_slot_updates_updated_at(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        before = ctx.updated_at
        ctx.set_slot("x", "y")
        assert ctx.updated_at >= before

    def test_clear_slots(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.set_slot("a", 1)
        ctx.set_slot("b", 2)
        ctx.clear_slots()
        assert ctx.slots == {}

    def test_clear_slots_updates_updated_at(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.set_slot("x", "y")
        before = ctx.updated_at
        ctx.clear_slots()
        assert ctx.updated_at >= before

    def test_get_slot_with_slot_missing_value_key(self):
        """Edge case: slot dict has no 'value' key."""
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.slots["odd_slot"] = {"filled_at": "2024-01-01"}
        assert ctx.get_slot("odd_slot") is None
