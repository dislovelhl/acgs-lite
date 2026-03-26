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


class TestAdditionalCoverageBranches:
    def test_message_from_dict_with_datetime_timestamp(self):
        """Covers line 109->112: timestamp is already a datetime (not str, not None)."""
        from datetime import datetime

        ts = datetime.now(UTC)
        # When timestamp is a datetime object, neither isinstance(str) nor None branch fires.
        # The code falls through both branches and uses it as-is.
        data = {"role": "user", "content": "test", "timestamp": ts}
        msg = Message.from_dict(data)
        assert msg.timestamp == ts

    def test_add_message_object_enforces_max_history(self):
        """Covers line 230: max_history trim when adding a Message object directly."""
        ctx = ConversationContext(user_id="u1", session_id="s1", max_history=3)
        # Pre-fill with 3 messages so adding one more triggers trim
        for i in range(3):
            ctx.add_message(MessageRole.USER, f"existing {i}")
        assert len(ctx.messages) == 3
        # Now add a Message object directly - triggers line 230
        msg = Message(role=MessageRole.USER, content="fourth")
        ctx.add_message(msg)
        assert len(ctx.messages) == 3
        assert ctx.messages[-1].content == "fourth"

    def test_get_last_user_message_no_user_messages_in_list(self):
        """Covers line 237->236 branch: loop exits without finding a user message."""
        ctx = ConversationContext(user_id="u1", session_id="s1")
        # Only system messages - loop will iterate but never return USER
        ctx.add_message(MessageRole.SYSTEM, "system msg")
        ctx.add_message(MessageRole.ASSISTANT, "assistant msg")
        result = ctx.get_last_user_message()
        assert result is None

    def test_get_last_assistant_message_no_assistant_messages(self):
        """Similar branch coverage for get_last_assistant_message."""
        ctx = ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(MessageRole.SYSTEM, "system msg")
        ctx.add_message(MessageRole.USER, "user msg")
        result = ctx.get_last_assistant_message()
        assert result is None

    async def test_update_context_not_initialized_state_no_transition(self):
        """Covers line 493->496: already active state, no transition needed."""
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        # Pre-transition to non-INITIALIZED state
        ctx.transition_state(ConversationState.PROCESSING)
        result = await mgr.update_context(ctx, "hello")
        # Should NOT transition to ACTIVE since it was PROCESSING
        assert result.conversation_state == ConversationState.PROCESSING

    async def test_update_context_completed_state_no_transition(self):
        """Covers the else branch of conversation_state == INITIALIZED check."""
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        ctx.transition_state(ConversationState.COMPLETED)
        result = await mgr.update_context(ctx, "message")
        assert result.conversation_state == ConversationState.COMPLETED

    async def test_update_context_topic_shift_with_from_to(self):
        """Covers line 482: topic_shift metadata with from/to values."""
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        prior = Message(role="user", content="greet", intent="greeting")  # type: ignore[arg-type]
        ctx.messages.append(prior)
        nlu = {"intent": "order_purchase", "entities": []}
        result = await mgr.update_context(ctx, "I want to buy", nlu)
        assert "topic_shift" in result.metadata
        assert result.metadata["topic_shift"]["from_topic"] == "greeting"
        assert result.metadata["topic_shift"]["to_topic"] == "order"
        assert "detected_at" in result.metadata["topic_shift"]

    def test_detect_topic_shift_get_topic_returns_none_for_both(self):
        """Covers line 664: _detect_topic_shift returns None when both topics unknown."""
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        prior = Message(role="user", content="x", intent="completely_unknown_xyz")  # type: ignore[arg-type]
        ctx.messages.append(prior)
        # current intent also maps to nothing
        result = mgr._detect_topic_shift({"intent": "another_completely_unknown"}, ctx)
        assert result is None

    def test_detect_topic_shift_returns_none_when_same_topic(self):
        """Covers line 664: returns None when topics are the same."""
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        prior = Message(role="user", content="buy", intent="buy")  # type: ignore[arg-type]
        ctx.messages.append(prior)
        # Both "buy" and "purchase" map to "order"
        result = mgr._detect_topic_shift({"intent": "purchase"}, ctx)
        assert result is None

    def test_detect_topic_shift_get_topic_inner_function_returns_none(self):
        """Covers line 656: get_topic returning None (all loop iterations miss)."""
        mgr = ContextManager()
        ctx = ConversationContext(user_id="u1", session_id="s1")
        prior = Message(role="user", content="x", intent="xyz_unmapped")  # type: ignore[arg-type]
        ctx.messages.append(prior)
        result = mgr._detect_topic_shift({"intent": "order_now"}, ctx)
        # previous_topic is None (xyz_unmapped doesn't match) → no shift
        assert result is None

    def test_prune_context_entity_deletion_loop_executes(self):
        """Covers lines 691, 694: the entity deletion loop when entities are pruned."""
        mgr = ContextManager(max_context_length=50, max_entity_age_turns=1)
        ctx = ConversationContext(user_id="u1", session_id="s1")
        # Create two stale entities
        ctx.entities["stale_1"] = {
            "value": "val1",
            "updated_at": datetime.now(UTC).isoformat(),
            "metadata": {"source_turn": 0},
        }
        ctx.entities["stale_2"] = {
            "value": "val2",
            "updated_at": datetime.now(UTC).isoformat(),
            "metadata": {"source_turn": 0},
        }
        # One fresh entity
        ctx.entities["fresh"] = {
            "value": "fresh_val",
            "updated_at": datetime.now(UTC).isoformat(),
            "metadata": {"source_turn": 9},
        }
        for i in range(10):
            ctx.messages.append(Message(role=MessageRole.USER, content=f"m{i}"))

        pruned = mgr._prune_context(ctx)
        assert "stale_1" not in pruned.entities
        assert "stale_2" not in pruned.entities
        assert "fresh" in pruned.entities

    async def test_process_long_context_mamba_init_succeeds_processes_tensor(self):
        """Covers line 580->586: init succeeds (True), continues to tensor processing."""
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mock_tensor = MagicMock()
        mock_tensor.norm.return_value.item.return_value = 2.5

        mock_mamba_mgr = MagicMock()
        mock_mamba_mgr.is_loaded = False  # triggers init path
        mock_mamba_mgr.process_context.return_value = mock_tensor

        mock_config_cls = MagicMock()
        # init returns True → does NOT return early, continues to tensor processing
        mock_init = MagicMock(return_value=True)

        mock_torch = MagicMock()
        mock_torch.randn.return_value = MagicMock()

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(ctx_module.MessageRole.USER, "test message for init")

        with (
            patch.object(ctx_module, "MAMBA_AVAILABLE", True),
            patch.object(ctx_module, "get_mamba_hybrid_processor", return_value=mock_mamba_mgr),
            patch.object(ctx_module, "MambaConfig", mock_config_cls),
            patch.object(ctx_module, "initialize_mamba_processor", mock_init),
            patch.object(ctx_module, "torch", mock_torch),
        ):
            result = await mgr.process_long_context(ctx)

        # init was called
        mock_init.assert_called_once()
        # process_context was called (since init returned True, we continue)
        mock_mamba_mgr.process_context.assert_called_once()
        assert result.metadata.get("mamba_processed") is True
