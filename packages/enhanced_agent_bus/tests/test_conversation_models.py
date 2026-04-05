"""
Tests for Conversation Models (Pydantic v2 Serialization)
Constitutional Hash: 608508a9bd224290

Tests the ConversationMessage and ConversationState Pydantic models
for proper serialization/deserialization with Pydantic v2 API.
"""

import json
from datetime import UTC, datetime, timezone

from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    ConversationMessage,
    ConversationState,
)


class TestConversationMessageSerialization:
    """Tests for ConversationMessage Pydantic model serialization."""

    def test_conversation_message_model_dump(self):
        """Test ConversationMessage model_dump() serialization."""
        msg = ConversationMessage(
            role="user",
            content="Test message content",
            intent="test_intent",
            verification_result={"is_valid": True, "confidence": 0.95},
        )

        # Serialize to dict
        data = msg.model_dump()

        assert data["role"] == "user"
        assert data["content"] == "Test message content"
        assert data["intent"] == "test_intent"
        assert data["verification_result"]["is_valid"] is True
        assert data["verification_result"]["confidence"] == 0.95
        assert "timestamp" in data

    def test_conversation_message_model_dump_json(self):
        """Test ConversationMessage model_dump_json() serialization."""
        msg = ConversationMessage(
            role="assistant",
            content="Response content",
        )

        # Serialize to JSON string
        json_str = msg.model_dump_json()

        # Verify it's valid JSON
        data = json.loads(json_str)
        assert data["role"] == "assistant"
        assert data["content"] == "Response content"
        assert data["intent"] is None
        assert data["verification_result"] is None

    def test_conversation_message_model_validate(self):
        """Test ConversationMessage model_validate() deserialization from dict."""
        timestamp = datetime.now(UTC)
        data = {
            "role": "user",
            "content": "Validated message",
            "timestamp": timestamp,
            "intent": "query",
            "verification_result": {"is_valid": True, "confidence": 0.8},
        }

        msg = ConversationMessage.model_validate(data)

        assert msg.role == "user"
        assert msg.content == "Validated message"
        assert msg.intent == "query"
        assert msg.verification_result["confidence"] == 0.8

    def test_conversation_message_model_validate_json(self):
        """Test ConversationMessage model_validate_json() deserialization from JSON string."""
        json_str = json.dumps(
            {
                "role": "user",
                "content": "JSON validated message",
                "timestamp": datetime.now(UTC).isoformat(),
                "intent": None,
                "verification_result": None,
            }
        )

        msg = ConversationMessage.model_validate_json(json_str)

        assert msg.role == "user"
        assert msg.content == "JSON validated message"
        assert msg.intent is None
        assert msg.verification_result is None

    def test_conversation_message_default_timestamp(self):
        """Test that ConversationMessage generates default timestamp."""
        msg = ConversationMessage(role="user", content="Test")
        assert msg.timestamp is not None
        assert isinstance(msg.timestamp, datetime)

    def test_conversation_message_roundtrip(self):
        """Test full serialization/deserialization roundtrip."""
        original = ConversationMessage(
            role="user",
            content="Roundtrip test",
            intent="test",
            verification_result={"is_valid": True, "confidence": 0.99, "critique": "No issues"},
        )

        # Serialize to JSON and back
        json_str = original.model_dump_json()
        restored = ConversationMessage.model_validate_json(json_str)

        assert restored.role == original.role
        assert restored.content == original.content
        assert restored.intent == original.intent
        assert restored.verification_result == original.verification_result


class TestConversationStateSerialization:
    """Tests for ConversationState Pydantic model serialization."""

    def test_conversation_state_model_dump(self):
        """Test ConversationState model_dump() serialization."""
        state = ConversationState(
            session_id="test-session-123",
            tenant_id="tenant-abc",
            messages=[
                ConversationMessage(role="user", content="Hello"),
                ConversationMessage(role="assistant", content="Hi there"),
            ],
        )

        data = state.model_dump()

        assert data["session_id"] == "test-session-123"
        assert data["tenant_id"] == "tenant-abc"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_conversation_state_model_dump_json(self):
        """Test ConversationState model_dump_json() serialization."""
        state = ConversationState(
            session_id="json-session",
            tenant_id="json-tenant",
            messages=[],
        )

        json_str = state.model_dump_json()

        # Verify valid JSON
        data = json.loads(json_str)
        assert data["session_id"] == "json-session"
        assert data["tenant_id"] == "json-tenant"
        assert data["messages"] == []

    def test_conversation_state_model_validate(self):
        """Test ConversationState model_validate() deserialization from dict."""
        now = datetime.now(UTC)
        data = {
            "session_id": "validated-session",
            "tenant_id": "validated-tenant",
            "messages": [
                {"role": "user", "content": "Test", "timestamp": now},
            ],
            "created_at": now,
            "updated_at": now,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        state = ConversationState.model_validate(data)

        assert state.session_id == "validated-session"
        assert state.tenant_id == "validated-tenant"
        assert len(state.messages) == 1
        assert state.messages[0].role == "user"

    def test_conversation_state_model_validate_json(self):
        """Test ConversationState model_validate_json() deserialization from JSON string."""
        now = datetime.now(UTC).isoformat()
        json_str = json.dumps(
            {
                "session_id": "json-validated-session",
                "tenant_id": "json-validated-tenant",
                "messages": [
                    {"role": "user", "content": "Hello", "timestamp": now},
                    {"role": "assistant", "content": "World", "timestamp": now},
                ],
                "created_at": now,
                "updated_at": now,
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        )

        state = ConversationState.model_validate_json(json_str)

        assert state.session_id == "json-validated-session"
        assert len(state.messages) == 2

    def test_conversation_state_default_timestamps(self):
        """Test that ConversationState generates default timestamps."""
        state = ConversationState(
            session_id="test-session",
            tenant_id="test-tenant",
        )

        assert state.created_at is not None
        assert state.updated_at is not None
        assert isinstance(state.created_at, datetime)
        assert isinstance(state.updated_at, datetime)

    def test_conversation_state_default_constitutional_hash(self):
        """Test that ConversationState has default constitutional hash."""
        state = ConversationState(
            session_id="test-session",
            tenant_id="test-tenant",
        )

        assert state.constitutional_hash == CONSTITUTIONAL_HASH

    def test_conversation_state_roundtrip(self):
        """Test full serialization/deserialization roundtrip for ConversationState."""
        original = ConversationState(
            session_id="roundtrip-session",
            tenant_id="roundtrip-tenant",
            messages=[
                ConversationMessage(
                    role="user",
                    content="User message",
                    intent="query",
                    verification_result={"is_valid": True, "confidence": 0.9},
                ),
                ConversationMessage(
                    role="assistant",
                    content="Assistant response",
                    verification_result={"is_valid": True, "confidence": 0.95},
                ),
            ],
        )

        # Serialize to JSON and back
        json_str = original.model_dump_json()
        restored = ConversationState.model_validate_json(json_str)

        assert restored.session_id == original.session_id
        assert restored.tenant_id == original.tenant_id
        assert len(restored.messages) == len(original.messages)
        assert restored.messages[0].content == original.messages[0].content
        assert restored.messages[1].content == original.messages[1].content
        assert restored.constitutional_hash == original.constitutional_hash


def test_conversation_state_serialization():
    """Main test for ConversationState serialization (matches subtask test name).

    This comprehensive test verifies:
    1. ConversationState creates correctly with required fields
    2. ConversationMessage nesting works properly
    3. Pydantic v2 model_dump() produces correct dict
    4. Pydantic v2 model_dump_json() produces valid JSON
    5. Pydantic v2 model_validate_json() deserializes correctly
    6. Full roundtrip serialization preserves all data
    """
    # Create a conversation state with messages
    state = ConversationState(
        session_id="test-session-001",
        tenant_id="tenant-xyz",
        messages=[
            ConversationMessage(
                role="user",
                content="What is the policy for data retention?",
                intent="policy_query",
                verification_result={"is_valid": True, "confidence": 0.85},
            ),
            ConversationMessage(
                role="assistant",
                content="Data retention policy requires...",
                verification_result={"is_valid": True, "confidence": 0.92},
            ),
        ],
    )

    # Test model_dump() - Pydantic v2 dict serialization
    data = state.model_dump()
    assert isinstance(data, dict)
    assert data["session_id"] == "test-session-001"
    assert data["tenant_id"] == "tenant-xyz"
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["verification_result"]["confidence"] == 0.85

    # Test model_dump_json() - Pydantic v2 JSON serialization
    json_str = state.model_dump_json()
    assert isinstance(json_str, str)

    # Verify valid JSON structure
    parsed = json.loads(json_str)
    assert parsed["session_id"] == "test-session-001"

    # Test model_validate_json() - Pydantic v2 JSON deserialization
    restored = ConversationState.model_validate_json(json_str)
    assert isinstance(restored, ConversationState)
    assert restored.session_id == state.session_id
    assert restored.tenant_id == state.tenant_id
    assert len(restored.messages) == 2
    assert restored.messages[0].content == state.messages[0].content
    assert restored.messages[1].content == state.messages[1].content
    assert restored.constitutional_hash == CONSTITUTIONAL_HASH

    # Verify nested ConversationMessage deserialization
    assert isinstance(restored.messages[0], ConversationMessage)
    assert restored.messages[0].verification_result["confidence"] == 0.85
