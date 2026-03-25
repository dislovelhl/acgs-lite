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


class TestConversationStateEnum:
    """Full enumeration coverage."""

    def test_all_states_have_string_values(self):
        for state in ConversationState:
            assert isinstance(state.value, str)

    def test_initialized(self):
        assert ConversationState.INITIALIZED.value == "initialized"

    def test_active(self):
        assert ConversationState.ACTIVE.value == "active"

    def test_awaiting_input(self):
        assert ConversationState.AWAITING_INPUT.value == "awaiting_input"

    def test_waiting_input_alias(self):
        # Alias for compatibility
        assert ConversationState.WAITING_INPUT.value == "waiting_input"

    def test_awaiting_confirmation(self):
        assert ConversationState.AWAITING_CONFIRMATION.value == "awaiting_confirmation"

    def test_processing(self):
        assert ConversationState.PROCESSING.value == "processing"

    def test_completed(self):
        assert ConversationState.COMPLETED.value == "completed"

    def test_escalated(self):
        assert ConversationState.ESCALATED.value == "escalated"

    def test_failed(self):
        assert ConversationState.FAILED.value == "failed"

    def test_error(self):
        assert ConversationState.ERROR.value == "error"
