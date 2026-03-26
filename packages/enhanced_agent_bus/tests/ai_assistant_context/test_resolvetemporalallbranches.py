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


class TestResolveTemporalAllBranches:
    def test_current_date_format(self):
        mgr = ContextManager()
        result = mgr._resolve_temporal("current_date")
        # Should be YYYY-MM-DD
        assert len(result) == 10
        assert result[4] == "-" and result[7] == "-"

    def test_next_day_format(self):
        mgr = ContextManager()
        result = mgr._resolve_temporal("next_day")
        assert len(result) == 10

    def test_previous_day_format(self):
        mgr = ContextManager()
        result = mgr._resolve_temporal("previous_day")
        assert len(result) == 10

    def test_current_time_format(self):
        mgr = ContextManager()
        result = mgr._resolve_temporal("current_time")
        assert ":" in result
        parts = result.split(":")
        assert len(parts) == 2

    def test_next_week_format(self):
        mgr = ContextManager()
        result = mgr._resolve_temporal("next_week")
        assert len(result) == 10

    def test_previous_week_format(self):
        mgr = ContextManager()
        result = mgr._resolve_temporal("previous_week")
        assert len(result) == 10

    def test_unknown_ref_returned_verbatim(self):
        mgr = ContextManager()
        result = mgr._resolve_temporal("future_time")
        assert result == "future_time"

    def test_unknown_ref_unknown_xyz(self):
        mgr = ContextManager()
        result = mgr._resolve_temporal("some_unknown_ref")
        assert result == "some_unknown_ref"


# ---------------------------------------------------------------------------
# ContextManager.process_long_context (async) — MAMBA branches
#
# These tests use ctx_module.ContextManager and ctx_module.ConversationContext
# to ensure the patched module-level symbols are from the same module instance
# that ContextManager.process_long_context references at runtime.
# This is necessary for correct behavior under --import-mode=importlib.
# ---------------------------------------------------------------------------


def _make_mamba_ctx(ctx_module_ref):
    """Helper: create ConversationContext from the given module reference."""
    ctx = ctx_module_ref.ConversationContext(user_id="u1", session_id="s1")
    ctx.add_message(ctx_module_ref.MessageRole.USER, "test message")
    return ctx
