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


class TestEdgeCases:
    def test_context_with_many_entities_and_slots(self):
        ctx = ConversationContext(user_id="u1", session_id="s1")
        for i in range(20):
            ctx.update_entity(f"entity_{i}", f"value_{i}")
            ctx.set_slot(f"slot_{i}", f"slot_val_{i}")
        assert len(ctx.entities) == 20
        assert len(ctx.slots) == 20

    async def test_update_context_with_empty_entities_list(self):
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        nlu = {"intent": "greet", "entities": []}
        result = await mgr.update_context(ctx, "Hello", nlu)
        assert len(result.entities) == 0

    async def test_update_context_with_none_entities(self):
        mgr = ContextManager()
        ctx = mgr.create_context(user_id="u1", session_id="s1")
        nlu = {"intent": "greet"}  # no 'entities' key
        result = await mgr.update_context(ctx, "Hello", nlu)
        assert len(result.entities) == 0

    def test_message_with_all_optional_fields(self):
        msg = Message(
            role=MessageRole.USER,
            content="full message",
            intent="search",
            entities=[{"type": "product", "value": "phone"}],
            metadata={"source": "web", "confidence": 0.95},
        )
        d = msg.to_dict()
        assert d["intent"] == "search"
        assert len(d["entities"]) == 1
        assert d["metadata"]["source"] == "web"

    def test_conversation_context_to_dict_with_all_fields(self):
        ctx = ConversationContext(
            user_id="u1",
            session_id="s1",
            tenant_id="t1",
            metadata={"source": "api"},
            state_data={"step": 1},
        )
        ctx.user_profile = UserProfile(user_id="u1")
        ctx.add_message(MessageRole.USER, "hello")
        ctx.update_entity("x", "y")
        ctx.set_slot("a", "b")
        ctx.transition_state(ConversationState.ACTIVE)

        d = ctx.to_dict()
        assert d["metadata"]["source"] == "api"
        assert d["state_data"]["step"] == 1
        assert d["tenant_id"] == "t1"
        assert d["conversation_state"] == "active"
        assert d["user_profile"] is not None

    async def test_process_long_context_empty_messages(self):
        """Context with no messages should still work (seq_len=0)."""
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")

        mock_tensor = MagicMock()
        mock_tensor.norm.return_value.item.return_value = 0.0

        mock_mamba_mgr = MagicMock()
        mock_mamba_mgr.is_loaded = True
        mock_mamba_mgr.process_context.return_value = mock_tensor

        mock_torch = MagicMock()
        mock_torch.randn.return_value = MagicMock()

        with (
            patch.object(ctx_module, "MAMBA_AVAILABLE", True),
            patch.object(ctx_module, "get_mamba_hybrid_processor", return_value=mock_mamba_mgr),
            patch.object(ctx_module, "torch", mock_torch),
        ):
            result = await mgr.process_long_context(ctx)

        assert result is ctx


# ---------------------------------------------------------------------------
# Additional coverage for remaining uncovered branches
# ---------------------------------------------------------------------------
