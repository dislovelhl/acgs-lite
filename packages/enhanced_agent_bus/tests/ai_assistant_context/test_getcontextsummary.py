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


class TestGetContextSummary:
    def test_minimal_summary(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        summary = mgr.get_context_summary(ctx)
        assert "State:" in summary
        assert "Messages:" in summary

    def test_summary_with_user_profile(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.user_profile = UserProfile(user_id="u1", name="Bob")
        summary = mgr.get_context_summary(ctx)
        assert "User:" in summary
        assert "u1" in summary

    def test_summary_without_user_profile(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        summary = mgr.get_context_summary(ctx)
        assert "User:" not in summary

    def test_summary_message_count(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        for i in range(5):
            ctx.add_message(MessageRole.USER, f"m{i}")
        summary = mgr.get_context_summary(ctx)
        assert "Messages: 5" in summary

    def test_summary_with_entities(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("product", "laptop")
        summary = mgr.get_context_summary(ctx)
        assert "Entities:" in summary
        assert "product" in summary

    def test_summary_without_entities(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        summary = mgr.get_context_summary(ctx)
        assert "Entities:" not in summary

    def test_summary_with_slots(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.set_slot("order_id", "ORD-123")
        summary = mgr.get_context_summary(ctx)
        assert "Slots:" in summary
        assert "order_id" in summary

    def test_summary_without_slots(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        summary = mgr.get_context_summary(ctx)
        assert "Slots:" not in summary

    def test_summary_uses_pipe_separator(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(MessageRole.USER, "hi")
        summary = mgr.get_context_summary(ctx)
        assert " | " in summary

    def test_summary_state_value(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.transition_state(ConversationState.PROCESSING)
        summary = mgr.get_context_summary(ctx)
        assert "processing" in summary

    def test_summary_multiple_entities(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("product", "laptop")
        ctx.update_entity("color", "silver")
        summary = mgr.get_context_summary(ctx)
        assert "product" in summary
        assert "color" in summary

    def test_summary_multiple_slots(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.set_slot("slot_a", "val_a")
        ctx.set_slot("slot_b", "val_b")
        summary = mgr.get_context_summary(ctx)
        assert "slot_a" in summary
        assert "slot_b" in summary


# ---------------------------------------------------------------------------
# Edge cases and integration scenarios
# ---------------------------------------------------------------------------
