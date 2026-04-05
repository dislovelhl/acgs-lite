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


class TestDetectTopicShift:
    def test_returns_none_when_nlu_is_none(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        assert mgr._detect_topic_shift(None, ctx) is None

    def test_returns_none_when_no_messages(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        assert mgr._detect_topic_shift({"intent": "greet"}, ctx) is None

    def test_returns_none_when_no_intent_in_nlu(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(MessageRole.USER, "hi")
        assert mgr._detect_topic_shift({"entities": []}, ctx) is None

    def test_returns_none_when_intent_is_none(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(MessageRole.USER, "hi")
        assert mgr._detect_topic_shift({"intent": None}, ctx) is None

    def test_returns_none_when_no_prior_user_message_with_intent(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        # message without intent
        ctx.add_message(MessageRole.USER, "hi")
        assert mgr._detect_topic_shift({"intent": "order"}, ctx) is None

    def test_detects_greeting_to_order_shift(self):
        """Uses string "user" role to match the `m.role == "user"` check."""
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        prior = Message(role="user", content="hi", intent="greeting")  # type: ignore[arg-type]
        ctx.messages.append(prior)
        result = mgr._detect_topic_shift({"intent": "order_purchase"}, ctx)
        assert result is not None
        assert result["from"] == "greeting"
        assert result["to"] == "order"

    def test_detects_support_to_information_shift(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        prior = Message(role="user", content="help", intent="help_issue")  # type: ignore[arg-type]
        ctx.messages.append(prior)
        result = mgr._detect_topic_shift({"intent": "question_inquiry"}, ctx)
        assert result is not None
        assert result["from"] == "support"
        assert result["to"] == "information"

    def test_no_shift_when_same_topic(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        prior = Message(role="user", content="buy", intent="purchase")  # type: ignore[arg-type]
        ctx.messages.append(prior)
        # Both map to "order" topic
        result = mgr._detect_topic_shift({"intent": "order_now"}, ctx)
        assert result is None

    def test_no_shift_when_previous_topic_unknown(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        prior = Message(role="user", content="x", intent="completely_unknown")  # type: ignore[arg-type]
        ctx.messages.append(prior)
        result = mgr._detect_topic_shift({"intent": "order_purchase"}, ctx)
        # previous_topic is None → no shift
        assert result is None

    def test_no_shift_when_current_topic_unknown(self):
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        prior = Message(role="user", content="hi", intent="greeting")  # type: ignore[arg-type]
        ctx.messages.append(prior)
        result = mgr._detect_topic_shift({"intent": "completely_unknown"}, ctx)
        # current_topic is None → no shift
        assert result is None

    def test_uses_last_user_message_from_last_5(self):
        """Uses the intent from the LAST user message in the window."""
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        # Add messages beyond the -5 window
        for i in range(10):
            ctx.messages.append(
                Message(role="user", content=f"old {i}", intent="order_old")  # type: ignore[arg-type]
            )
        # The last one in the -5 window is the one that matters
        result = mgr._detect_topic_shift({"intent": "help_needed"}, ctx)
        # order → support: shift detected
        assert result is not None

    def test_topic_indicators_greeting_and_farewell(self):
        """Both greeting and farewell map to the 'greeting' topic."""
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        prior = Message(role="user", content="bye", intent="farewell")  # type: ignore[arg-type]
        ctx.messages.append(prior)
        result = mgr._detect_topic_shift({"intent": "farewell_final"}, ctx)
        # farewell → farewell (both greeting topic): no shift
        assert result is None


# ---------------------------------------------------------------------------
# ContextManager._prune_context
# ---------------------------------------------------------------------------
