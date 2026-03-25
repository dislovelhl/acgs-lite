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


class TestConversationContextEntities:
    def test_update_entity_stores_value(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("product", "laptop")
        assert ctx.entities["product"]["value"] == "laptop"

    def test_update_entity_stores_metadata(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("product", "laptop", confidence=0.95, source="nlu")
        assert ctx.entities["product"]["metadata"]["confidence"] == 0.95
        assert ctx.entities["product"]["metadata"]["source"] == "nlu"

    def test_update_entity_stores_timestamp(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("product", "phone")
        assert "updated_at" in ctx.entities["product"]

    def test_update_entity_updates_updated_at(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        before = ctx.updated_at
        ctx.update_entity("x", "y")
        assert ctx.updated_at >= before

    def test_get_entity_returns_value(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("city", "London")
        assert ctx.get_entity("city") == "London"

    def test_get_entity_returns_none_for_missing(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        assert ctx.get_entity("missing_entity") is None

    def test_get_entity_returns_none_for_empty_entity_data(self):
        """Edge case: entity exists in dict but with no 'value' key."""
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.entities["weird"] = {}  # no 'value' key
        assert ctx.get_entity("weird") is None

    def test_has_entity_true(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("product", "tablet")
        assert ctx.has_entity("product") is True

    def test_has_entity_false(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        assert ctx.has_entity("nonexistent") is False

    def test_update_entity_overwrites_existing(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.update_entity("product", "laptop")
        ctx.update_entity("product", "desktop")
        assert ctx.get_entity("product") == "desktop"
