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


class TestContextManagerInit:
    def test_default_init(self):
        mgr = ContextManager()
        assert mgr.max_context_length == 50
        assert mgr.max_entity_age_turns == 10
        assert mgr.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(mgr._sessions, dict)
        assert len(mgr._sessions) == 0

    def test_custom_init(self):
        mgr = ContextManager(
            max_context_length=20,
            max_entity_age_turns=5,
            constitutional_hash="custom_hash",
        )
        assert mgr.max_context_length == 20
        assert mgr.max_entity_age_turns == 5
        assert mgr.constitutional_hash == "custom_hash"

    def test_reference_patterns_compiled(self):
        mgr = ContextManager()
        patterns = mgr._reference_patterns
        assert "pronouns" in patterns
        assert "temporal" in patterns
        assert "it" in patterns["pronouns"]
        assert "they" in patterns["pronouns"]
        assert "he" in patterns["pronouns"]
        assert "she" in patterns["pronouns"]
        assert "that" in patterns["pronouns"]
        assert "this" in patterns["pronouns"]
        assert "there" in patterns["pronouns"]
        assert "today" in patterns["temporal"]
        assert "tomorrow" in patterns["temporal"]
        assert "yesterday" in patterns["temporal"]
        assert "next week" in patterns["temporal"]
        assert "last week" in patterns["temporal"]
        assert "now" in patterns["temporal"]
        assert "later" in patterns["temporal"]
