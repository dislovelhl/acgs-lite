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


class TestContextManagerCRUD:
    def test_create_context(self):
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        assert ctx.user_id == "u1"
        assert ctx.session_id == "s1"
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH

    def test_create_context_with_kwargs(self):
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1", tenant_id="tenant-X")
        assert ctx.tenant_id == "tenant-X"

    def test_create_context_stores_in_sessions(self):
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        assert mgr._sessions["s1"] is ctx

    def test_get_context_returns_context(self):
        mgr = ContextManager()
        created = mgr.create_context(user_id="u1", session_id="s1")
        retrieved = mgr.get_context("s1")
        assert retrieved is created

    def test_get_context_returns_none_for_missing(self):
        mgr = ContextManager()
        assert mgr.get_context("nonexistent") is None

    def test_delete_context_returns_true(self):
        mgr = ContextManager()
        mgr.create_context(user_id="u1", session_id="s1")
        assert mgr.delete_context("s1") is True
        assert mgr.get_context("s1") is None

    def test_delete_context_returns_false_for_missing(self):
        mgr = ContextManager()
        assert mgr.delete_context("nonexistent") is False

    def test_list_user_contexts_filters_by_user(self):
        mgr = ContextManager()
        mgr.create_context(user_id="userA", session_id="s1")
        mgr.create_context(user_id="userA", session_id="s2")
        mgr.create_context(user_id="userB", session_id="s3")
        contexts = mgr.list_user_contexts("userA")
        assert len(contexts) == 2
        assert all(c.user_id == "userA" for c in contexts)

    def test_list_user_contexts_empty_result(self):
        mgr = ContextManager()
        mgr.create_context(user_id="userB", session_id="s1")
        contexts = mgr.list_user_contexts("userA")
        assert contexts == []


# ---------------------------------------------------------------------------
# ContextManager.update_context (async)
# ---------------------------------------------------------------------------
