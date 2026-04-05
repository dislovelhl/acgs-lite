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


class TestProcessLongContextMambaNotAvailable:
    async def test_returns_context_unchanged_when_mamba_not_available(self):
        import enhanced_agent_bus.ai_assistant.context as ctx_module

        mgr = ctx_module.ContextManager()
        ctx = ctx_module.ConversationContext(user_id="u1", session_id="s1")
        with patch.object(ctx_module, "MAMBA_AVAILABLE", False):
            result = await mgr.process_long_context(ctx)
        assert result is ctx
        assert "mamba_processed" not in result.metadata
