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


class TestUserProfileDataclass:
    def test_default_profile(self):
        p = UserProfile(user_id="u1")
        assert p.user_id == "u1"
        assert p.name is None
        assert p.email is None
        assert p.preferences == {}
        assert p.metadata == {}
        assert p.history_summary == ""
        assert p.language == "en"
        assert p.timezone == "UTC"
        assert p.constitutional_hash == CONSTITUTIONAL_HASH

    def test_full_profile(self):
        p = UserProfile(
            user_id="u2",
            name="Alice",
            email="alice@test.com",
            preferences={"theme": "dark"},
            metadata={"tier": "gold"},
            history_summary="Previous orders: 3",
            language="fr",
            timezone="Europe/Paris",
        )
        assert p.name == "Alice"
        assert p.email == "alice@test.com"
        assert p.preferences["theme"] == "dark"
        assert p.history_summary == "Previous orders: 3"
        assert p.language == "fr"
        assert p.timezone == "Europe/Paris"

    def test_to_dict_all_keys(self):
        p = UserProfile(user_id="u1", name="Bob", email="bob@test.com", language="de")
        d = p.to_dict()
        expected_keys = {
            "user_id",
            "name",
            "email",
            "preferences",
            "metadata",
            "history_summary",
            "language",
            "timezone",
            "created_at",
            "last_active",
            "constitutional_hash",
        }
        assert set(d.keys()) == expected_keys
        assert d["user_id"] == "u1"
        assert d["name"] == "Bob"
        assert d["language"] == "de"
        assert isinstance(d["created_at"], str)
        assert isinstance(d["last_active"], str)

    def test_to_dict_none_name_and_email(self):
        p = UserProfile(user_id="u1")
        d = p.to_dict()
        assert d["name"] is None
        assert d["email"] is None


# ---------------------------------------------------------------------------
# ConversationContext dataclass
# ---------------------------------------------------------------------------
