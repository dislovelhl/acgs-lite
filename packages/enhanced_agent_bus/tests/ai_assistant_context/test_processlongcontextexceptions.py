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


class TestProcessLongContextExceptions:
    async def test_runtime_error_stored_in_metadata(self):
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(ctx_module.MessageRole.USER, "test")

        mock_mamba_mgr = MagicMock()
        mock_mamba_mgr.is_loaded = True
        mock_mamba_mgr.process_context.side_effect = RuntimeError("runtime boom")

        mock_torch = MagicMock()
        mock_torch.randn.return_value = MagicMock()

        with (
            patch.object(ctx_module, "MAMBA_AVAILABLE", True),
            patch.object(ctx_module, "get_mamba_hybrid_processor", return_value=mock_mamba_mgr),
            patch.object(ctx_module, "torch", mock_torch),
        ):
            result = await mgr.process_long_context(ctx)

        assert "mamba_error" in result.metadata
        assert "runtime boom" in result.metadata["mamba_error"]

    async def test_value_error_stored_in_metadata(self):
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(ctx_module.MessageRole.USER, "test")

        mock_mamba_mgr = MagicMock()
        mock_mamba_mgr.is_loaded = True
        mock_mamba_mgr.process_context.side_effect = ValueError("value boom")

        mock_torch = MagicMock()
        mock_torch.randn.return_value = MagicMock()

        with (
            patch.object(ctx_module, "MAMBA_AVAILABLE", True),
            patch.object(ctx_module, "get_mamba_hybrid_processor", return_value=mock_mamba_mgr),
            patch.object(ctx_module, "torch", mock_torch),
        ):
            result = await mgr.process_long_context(ctx)

        assert "mamba_error" in result.metadata

    async def test_type_error_stored_in_metadata(self):
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(ctx_module.MessageRole.USER, "test")

        mock_mamba_mgr = MagicMock()
        mock_mamba_mgr.is_loaded = True
        mock_mamba_mgr.process_context.side_effect = TypeError("type boom")

        mock_torch = MagicMock()
        mock_torch.randn.return_value = MagicMock()

        with (
            patch.object(ctx_module, "MAMBA_AVAILABLE", True),
            patch.object(ctx_module, "get_mamba_hybrid_processor", return_value=mock_mamba_mgr),
            patch.object(ctx_module, "torch", mock_torch),
        ):
            result = await mgr.process_long_context(ctx)

        assert "mamba_error" in result.metadata

    async def test_key_error_stored_in_metadata(self):
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(ctx_module.MessageRole.USER, "test")

        mock_mamba_mgr = MagicMock()
        mock_mamba_mgr.is_loaded = True
        mock_mamba_mgr.process_context.side_effect = KeyError("key_boom")

        mock_torch = MagicMock()
        mock_torch.randn.return_value = MagicMock()

        with (
            patch.object(ctx_module, "MAMBA_AVAILABLE", True),
            patch.object(ctx_module, "get_mamba_hybrid_processor", return_value=mock_mamba_mgr),
            patch.object(ctx_module, "torch", mock_torch),
        ):
            result = await mgr.process_long_context(ctx)

        assert "mamba_error" in result.metadata

    async def test_attribute_error_stored_in_metadata(self):
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(ctx_module.MessageRole.USER, "test")

        mock_mamba_mgr = MagicMock()
        mock_mamba_mgr.is_loaded = True
        mock_mamba_mgr.process_context.side_effect = AttributeError("attr boom")

        mock_torch = MagicMock()
        mock_torch.randn.return_value = MagicMock()

        with (
            patch.object(ctx_module, "MAMBA_AVAILABLE", True),
            patch.object(ctx_module, "get_mamba_hybrid_processor", return_value=mock_mamba_mgr),
            patch.object(ctx_module, "torch", mock_torch),
        ):
            result = await mgr.process_long_context(ctx)

        assert "mamba_error" in result.metadata

    async def test_os_error_stored_in_metadata(self):
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(ctx_module.MessageRole.USER, "test")

        mock_mamba_mgr = MagicMock()
        mock_mamba_mgr.is_loaded = True
        mock_mamba_mgr.process_context.side_effect = OSError("os boom")

        mock_torch = MagicMock()
        mock_torch.randn.return_value = MagicMock()

        with (
            patch.object(ctx_module, "MAMBA_AVAILABLE", True),
            patch.object(ctx_module, "get_mamba_hybrid_processor", return_value=mock_mamba_mgr),
            patch.object(ctx_module, "torch", mock_torch),
        ):
            result = await mgr.process_long_context(ctx)

        assert "mamba_error" in result.metadata

    async def test_error_returns_context_unchanged_except_metadata(self):
        """Context is returned with mamba_error set but no mamba_processed."""
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")
        ctx.add_message(ctx_module.MessageRole.USER, "test")

        mock_mamba_mgr = MagicMock()
        mock_mamba_mgr.is_loaded = True
        mock_mamba_mgr.process_context.side_effect = RuntimeError("fail")

        mock_torch = MagicMock()
        mock_torch.randn.return_value = MagicMock()

        with (
            patch.object(ctx_module, "MAMBA_AVAILABLE", True),
            patch.object(ctx_module, "get_mamba_hybrid_processor", return_value=mock_mamba_mgr),
            patch.object(ctx_module, "torch", mock_torch),
        ):
            result = await mgr.process_long_context(ctx)

        assert result is ctx
        assert "mamba_processed" not in result.metadata


# ---------------------------------------------------------------------------
# ContextManager._detect_topic_shift
# ---------------------------------------------------------------------------
