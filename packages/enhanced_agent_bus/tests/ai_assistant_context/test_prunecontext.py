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


class TestPruneContext:
    def test_prune_keeps_system_messages(self):
        """String-role 'system' messages are kept via the system_messages list."""
        mgr = ContextManager(max_context_length=3)
        ctx = ConversationContext(user_id="u1", session_id="s1")
        sys_msg = Message(role="system", content="sys")  # type: ignore[arg-type]
        ctx.messages.append(sys_msg)
        for i in range(5):
            ctx.messages.append(Message(role=MessageRole.USER, content=f"user {i}"))

        pruned = mgr._prune_context(ctx)
        # System message should be present
        contents = [m.content for m in pruned.messages]
        assert "sys" in contents

    def test_prune_limits_to_max_context_length(self):
        mgr = ContextManager(max_context_length=3)
        ctx = ConversationContext(user_id="u1", session_id="s1")
        for i in range(10):
            ctx.messages.append(Message(role=MessageRole.USER, content=f"m{i}"))

        pruned = mgr._prune_context(ctx)
        # max_context_length=3, no system messages → at most 3 recent
        assert len(pruned.messages) <= 3

    def test_prune_removes_old_entities(self):
        mgr = ContextManager(max_context_length=50, max_entity_age_turns=2)
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.entities["stale"] = {
            "value": "old_value",
            "updated_at": datetime.now(UTC).isoformat(),
            "metadata": {"source_turn": 0},
        }
        for i in range(10):
            ctx.messages.append(Message(role=MessageRole.USER, content=f"m{i}"))

        pruned = mgr._prune_context(ctx)
        assert "stale" not in pruned.entities

    def test_prune_keeps_fresh_entities(self):
        mgr = ContextManager(max_context_length=50, max_entity_age_turns=20)
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.entities["fresh"] = {
            "value": "new_value",
            "updated_at": datetime.now(UTC).isoformat(),
            "metadata": {"source_turn": 9},
        }
        for i in range(10):
            ctx.messages.append(Message(role=MessageRole.USER, content=f"m{i}"))

        pruned = mgr._prune_context(ctx)
        assert "fresh" in pruned.entities

    def test_prune_handles_entity_without_source_turn(self):
        """Entities without source_turn in metadata use default 0."""
        mgr = ContextManager(max_context_length=50, max_entity_age_turns=2)
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.entities["no_source"] = {
            "value": "val",
            "updated_at": datetime.now(UTC).isoformat(),
            "metadata": {},  # no source_turn
        }
        for i in range(10):
            ctx.messages.append(Message(role=MessageRole.USER, content=f"m{i}"))

        pruned = mgr._prune_context(ctx)
        # source_turn defaults to 0, current_turn = 10, age = 10 > max_entity_age_turns=2
        assert "no_source" not in pruned.entities

    def test_prune_handles_entity_without_metadata_key(self):
        """Entities without 'metadata' key in entity_data use default {}."""
        mgr = ContextManager(max_context_length=50, max_entity_age_turns=2)
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.entities["no_meta"] = {
            "value": "val",
            "updated_at": datetime.now(UTC).isoformat(),
            # no "metadata" key at all
        }
        for i in range(10):
            ctx.messages.append(Message(role=MessageRole.USER, content=f"m{i}"))

        pruned = mgr._prune_context(ctx)
        # metadata defaults to {}, source_turn defaults to 0 → pruned
        assert "no_meta" not in pruned.entities

    def test_prune_returns_context(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        result = mgr._prune_context(ctx)
        assert result is ctx


# ---------------------------------------------------------------------------
# ContextManager.get_context_summary
# ---------------------------------------------------------------------------
