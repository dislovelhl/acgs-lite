"""
ACGS-2 AI Assistant - Context Management Tests
Constitutional Hash: 608508a9bd224290
"""

import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)

# Import centralized constitutional hash with fallback
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.ai_assistant.context import (
    ContextManager,
    ConversationContext,
    ConversationState,
    Message,
    MessageRole,
    UserProfile,
)


class TestMessage:
    """Tests for Message dataclass."""

    def test_create_user_message(self):
        """Test creating a user message."""
        msg = Message(role=MessageRole.USER, content="Hello, world!")

        assert msg.role == MessageRole.USER
        assert msg.content == "Hello, world!"
        assert msg.timestamp is not None
        assert isinstance(msg.metadata, dict)

    def test_create_assistant_message(self):
        """Test creating an assistant message."""
        msg = Message(
            role=MessageRole.ASSISTANT,
            content="How can I help you?",
            metadata={"intent": "greeting"},
        )

        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "How can I help you?"
        assert msg.metadata["intent"] == "greeting"

    def test_message_to_dict(self):
        """Test message serialization."""
        msg = Message(role=MessageRole.USER, content="Test")
        result = msg.to_dict()

        assert "role" in result
        assert "content" in result
        assert "timestamp" in result
        assert result["content"] == "Test"


class TestUserProfile:
    """Tests for UserProfile dataclass."""

    def test_create_default_profile(self):
        """Test creating a default user profile."""
        profile = UserProfile(user_id="user123")

        assert profile.user_id == "user123"
        assert profile.name is None
        assert profile.preferences == {}
        assert profile.constitutional_hash == CONSTITUTIONAL_HASH

    def test_create_full_profile(self):
        """Test creating a profile with all fields."""
        profile = UserProfile(
            user_id="user123",
            name="John Doe",
            email="john@example.com",
            preferences={"language": "en"},
            metadata={"tier": "premium"},
        )

        assert profile.name == "John Doe"
        assert profile.email == "john@example.com"
        assert profile.preferences["language"] == "en"
        assert profile.metadata["tier"] == "premium"


class TestConversationContext:
    """Tests for ConversationContext."""

    def test_create_default_context(self):
        """Test creating a default context."""
        ctx = ConversationContext(
            user_id="user123",
            session_id="session456",
        )

        assert ctx.user_id == "user123"
        assert ctx.session_id == "session456"
        assert ctx.conversation_state == ConversationState.INITIALIZED
        assert ctx.messages == []
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH

    def test_add_message(self):
        """Test adding a message to context."""
        ctx = ConversationContext(user_id="user123", session_id="session456")
        msg = Message(role=MessageRole.USER, content="Hello")

        ctx.add_message(msg)

        assert len(ctx.messages) == 1
        assert ctx.messages[0].content == "Hello"

    def test_get_last_user_message(self):
        """Test getting the last user message."""
        ctx = ConversationContext(user_id="user123", session_id="session456")
        ctx.add_message(Message(role=MessageRole.USER, content="First"))
        ctx.add_message(Message(role=MessageRole.ASSISTANT, content="Response"))
        ctx.add_message(Message(role=MessageRole.USER, content="Second"))

        last_msg = ctx.get_last_user_message()

        assert last_msg is not None
        assert last_msg.content == "Second"

    def test_get_last_assistant_message(self):
        """Test getting the last assistant message."""
        ctx = ConversationContext(user_id="user123", session_id="session456")
        ctx.add_message(Message(role=MessageRole.USER, content="Hello"))
        ctx.add_message(Message(role=MessageRole.ASSISTANT, content="Hi there!"))

        last_msg = ctx.get_last_assistant_message()

        assert last_msg is not None
        assert last_msg.content == "Hi there!"

    def test_set_and_get_slot(self):
        """Test slot management."""
        ctx = ConversationContext(user_id="user123", session_id="session456")

        ctx.set_slot("order_id", "12345")

        assert ctx.get_slot("order_id") == "12345"
        assert ctx.get_slot("nonexistent") is None
        assert ctx.get_slot("nonexistent", "default") == "default"

    def test_update_entity(self):
        """Test entity management."""
        ctx = ConversationContext(user_id="user123", session_id="session456")

        ctx.update_entity("product", "laptop")

        # Use get_entity() for proper API access
        assert ctx.get_entity("product") == "laptop"
        # Raw entities dict stores value with metadata
        assert ctx.entities["product"]["value"] == "laptop"

    def test_context_to_dict(self):
        """Test context serialization."""
        ctx = ConversationContext(
            user_id="user123",
            session_id="session456",
        )
        ctx.add_message(Message(role=MessageRole.USER, content="Test"))

        result = ctx.to_dict()

        assert result["user_id"] == "user123"
        assert result["session_id"] == "session456"
        assert "messages" in result
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestConversationState:
    """Tests for ConversationState enum."""

    def test_all_states_exist(self):
        """Test all conversation states are defined."""
        assert ConversationState.INITIALIZED
        assert ConversationState.ACTIVE
        assert ConversationState.WAITING_INPUT
        assert ConversationState.PROCESSING
        assert ConversationState.COMPLETED
        assert ConversationState.FAILED
        assert ConversationState.ESCALATED

    def test_state_values(self):
        """Test state values are strings."""
        assert isinstance(ConversationState.ACTIVE.value, str)


class TestContextManager:
    """Tests for ContextManager."""

    def test_create_context_manager(self):
        """Test creating a context manager."""
        manager = ContextManager()
        assert manager is not None

    def test_create_context(self):
        """Test creating a context through manager."""
        manager = ContextManager()
        ctx = manager.create_context(user_id="user123", session_id="session456")

        assert ctx.user_id == "user123"
        assert ctx.session_id == "session456"

    def test_get_context(self):
        """Test retrieving a context."""
        manager = ContextManager()
        created = manager.create_context(user_id="user123", session_id="session456")

        retrieved = manager.get_context("session456")

        assert retrieved is not None
        assert retrieved.session_id == created.session_id

    def test_update_context(self):
        """Test that context modifications persist in manager."""
        manager = ContextManager()
        ctx = manager.create_context(user_id="user123", session_id="session456")
        ctx.add_message(Message(role=MessageRole.USER, content="Hello"))

        # Context is stored by reference, so modifications persist
        retrieved = manager.get_context("session456")

        assert len(retrieved.messages) == 1
        assert retrieved.messages[0].content == "Hello"

    def test_delete_context(self):
        """Test deleting a context."""
        manager = ContextManager()
        manager.create_context(user_id="user123", session_id="session456")

        result = manager.delete_context("session456")

        assert result is True
        assert manager.get_context("session456") is None

    def test_delete_nonexistent_context(self):
        """Test deleting a context that doesn't exist."""
        manager = ContextManager()

        result = manager.delete_context("nonexistent")

        assert result is False

    def test_list_user_contexts(self):
        """Test listing contexts for a user."""
        manager = ContextManager()
        manager.create_context(user_id="user123", session_id="session1")
        manager.create_context(user_id="user123", session_id="session2")
        manager.create_context(user_id="user456", session_id="session3")

        contexts = manager.list_user_contexts("user123")

        assert len(contexts) == 2


class TestConversationContextAdvanced:
    """Advanced tests for ConversationContext."""

    def test_max_messages_limit(self):
        """Test context respects max messages."""
        ctx = ConversationContext(
            user_id="user123",
            session_id="session456",
            max_history=5,
        )

        for i in range(10):
            ctx.add_message(Message(role=MessageRole.USER, content=f"Message {i}"))

        # Should only keep last 5 messages
        assert len(ctx.messages) <= 5

    def test_get_recent_messages(self):
        """Test getting recent messages."""
        ctx = ConversationContext(user_id="user123", session_id="session456")
        for i in range(10):
            ctx.add_message(Message(role=MessageRole.USER, content=f"Message {i}"))

        recent = ctx.get_recent_messages(3)

        assert len(recent) == 3
        assert recent[-1].content == "Message 9"

    def test_has_entity(self):
        """Test checking for entity existence."""
        ctx = ConversationContext(user_id="user123", session_id="session456")
        ctx.update_entity("product", "laptop")

        assert ctx.has_entity("product") is True
        assert ctx.has_entity("nonexistent") is False

    def test_clear_slots(self):
        """Test clearing all slots."""
        ctx = ConversationContext(user_id="user123", session_id="session456")
        ctx.set_slot("slot1", "value1")
        ctx.set_slot("slot2", "value2")

        ctx.clear_slots()

        assert len(ctx.slots) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
