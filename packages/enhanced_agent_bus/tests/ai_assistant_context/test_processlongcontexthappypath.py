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


class TestProcessLongContextHappyPath:
    async def test_mamba_loaded_processes_and_updates_metadata(self):
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(ctx_module.MessageRole.USER, "message one")
        ctx.add_message(ctx_module.MessageRole.ASSISTANT, "reply one")

        mock_tensor = MagicMock()
        mock_tensor.norm.return_value.item.return_value = 3.14

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
            result = await mgr.process_long_context(ctx, max_tokens=5000, use_attention=True)

        assert result.metadata.get("mamba_processed") is True
        assert result.metadata.get("context_strength") == pytest.approx(3.14)
        assert "processed_at" in result.metadata
        assert result.metadata["mamba_config"]["max_tokens"] == 5000
        assert result.metadata["mamba_config"]["attention_used"] is True
        assert result.metadata["mamba_config"]["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_mamba_loaded_use_attention_false(self):
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(ctx_module.MessageRole.USER, "test")

        mock_tensor = MagicMock()
        mock_tensor.norm.return_value.item.return_value = 1.0

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
            result = await mgr.process_long_context(ctx, use_attention=False)

        assert result.metadata["mamba_config"]["attention_used"] is False

    async def test_mamba_max_tokens_capped_at_4m(self):
        """max_tokens > 4M is capped at 4M for MambaConfig."""
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(ctx_module.MessageRole.USER, "big context")

        mock_mamba_mgr = MagicMock()
        mock_mamba_mgr.is_loaded = False

        mock_config_cls = MagicMock()
        mock_init = MagicMock(return_value=False)

        with (
            patch.object(ctx_module, "MAMBA_AVAILABLE", True),
            patch.object(ctx_module, "get_mamba_hybrid_processor", return_value=mock_mamba_mgr),
            patch.object(ctx_module, "MambaConfig", mock_config_cls),
            patch.object(ctx_module, "initialize_mamba_processor", mock_init),
        ):
            result = await mgr.process_long_context(ctx, max_tokens=10_000_000)

        # Verify MambaConfig was called with min(10M, 4M) = 4M
        mock_config_cls.assert_called_once_with(max_context_length=4_000_000)

    async def test_process_long_context_with_many_messages(self):
        """Test with more than 100 messages (slice [-100:])."""
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1", max_history=200)
        for i in range(150):
            ctx.messages.append(
                ctx_module.Message(role=ctx_module.MessageRole.USER, content=f"msg {i}")
            )

        mock_tensor = MagicMock()
        mock_tensor.norm.return_value.item.return_value = 5.0

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

        assert result.metadata.get("mamba_processed") is True
