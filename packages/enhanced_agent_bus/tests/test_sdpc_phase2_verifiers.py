"""
Tests for SDPC Phase 2 Verifiers

Constitutional Hash: 608508a9bd224290
"""

import pytest

pytest.importorskip("enhanced_agent_bus.sdpc")


import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.deliberation_layer.intent_classifier import IntentType
from enhanced_agent_bus.sdpc.asc_verifier import ASCVerifier
from enhanced_agent_bus.sdpc.graph_check import GraphCheckVerifier
from enhanced_agent_bus.sdpc.pacar_verifier import PACARVerifier


async def test_asc_verifier_skipped():
    verifier = ASCVerifier()
    result = await verifier.verify("Some content", IntentType.GENERAL)
    assert result["is_valid"] is True
    assert "skipped" in result["reason"]


async def test_asc_verifier_factual():
    verifier = ASCVerifier()
    # Mock LLM Assistant
    mock_assistant = MagicMock()
    mock_assistant.analyze_message_impact = AsyncMock(
        return_value={"risk_level": "low", "confidence": 0.9, "reasoning": ["Verified consistent"]}
    )
    verifier.assistant = mock_assistant

    result = await verifier.verify("Factual content", IntentType.FACTUAL)
    assert result["is_valid"] is True
    assert result["confidence"] == 0.9


async def test_graph_check_verifier():
    verifier = GraphCheckVerifier(db_type="mock")
    # Content with known mock keywords
    content = "The supply chain in Asia is at risk."
    result = await verifier.verify_entities(content)
    assert result["is_valid"] is True
    assert len(result["results"]) > 0
    assert any(r["status"] == "grounded" for r in result["results"])


async def test_pacar_verifier():
    verifier = PACARVerifier()
    # Mock LLM Assistant
    mock_assistant = MagicMock()
    mock_assistant.analyze_message_impact = AsyncMock(
        return_value={
            "risk_level": "low",
            "confidence": 0.85,
            "reasoning": ["Red team found no issues", "Validator approved"],
            "mitigations": ["None"],
        }
    )
    verifier.assistant = mock_assistant

    result = await verifier.verify("Deliberative content", "Investigate risk")
    assert result["is_valid"] is True
    assert result["consensus_reached"] is True


async def test_pacar_verify_with_context_new_session():
    """Test PACAR verifier creates new conversation state for new session_id"""
    verifier = PACARVerifier()

    # Mock Redis client - return None to simulate no existing conversation
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(return_value=True)
    verifier.redis_client = mock_redis

    # Mock LLM Assistant with ainvoke_multi_turn (used in verify_with_context)
    mock_assistant = MagicMock()
    mock_assistant.ainvoke_multi_turn = AsyncMock(
        return_value={
            "risk_level": "low",
            "confidence": 0.9,
            "reasoning": ["Content verified"],
            "mitigations": ["None"],
            "recommended_decision": "approve",
        }
    )
    mock_assistant.analyze_message_impact = AsyncMock(
        return_value={
            "risk_level": "low",
            "confidence": 0.9,
            "reasoning": ["Content verified"],
            "mitigations": ["None"],
        }
    )
    verifier.assistant = mock_assistant

    # Mock PACARManager to avoid Redis connections
    mock_manager = MagicMock()
    mock_state = MagicMock()
    mock_state.messages = []
    mock_manager.add_message = AsyncMock(return_value=None)
    mock_manager.get_state = AsyncMock(return_value=mock_state)
    verifier.manager = mock_manager

    # Mock audit client
    verifier.audit_client = MagicMock()
    verifier.audit_client.report_decision = AsyncMock(return_value=None)

    result = await verifier.verify_with_context(
        content="Test content for new session",
        original_intent="test_intent",
        session_id="test-session-123",
        tenant_id="test-tenant",
    )

    # Verify result structure
    assert result["is_valid"] is True
    assert result["confidence"] == 0.9
    assert result["session_id"] == "test-session-123"
    assert result["message_count"] == 1
    assert result["consensus_reached"] is True

    # Verify Redis operations
    mock_redis.get.assert_called_once()
    mock_redis.setex.assert_called_once()

    # Verify the stored conversation data
    call_args = mock_redis.setex.call_args
    stored_key = call_args[0][0]
    stored_ttl = call_args[0][1]
    stored_data = call_args[0][2]

    assert "test-session-123" in stored_key
    assert stored_ttl == 3600  # Default TTL
    conversation_data = json.loads(stored_data)
    assert conversation_data["session_id"] == "test-session-123"
    assert conversation_data["tenant_id"] == "test-tenant"
    assert len(conversation_data["messages"]) == 1
    assert conversation_data["messages"][0]["role"] == "user"
    assert conversation_data["messages"][0]["content"] == "Test content for new session"


async def test_pacar_verify_with_context_existing_session():
    """Test PACAR verifier retrieves and appends to existing conversation state"""
    verifier = PACARVerifier()

    # Pre-existing conversation data from previous interaction
    existing_conversation = {
        "session_id": "existing-session-456",
        "tenant_id": "test-tenant",
        "messages": [
            {
                "role": "user",
                "content": "First message in session",
                "timestamp": "2024-01-01T10:00:00+00:00",
                "intent": "initial_intent",
                "verification_result": {"is_valid": True, "confidence": 0.95},
            },
            {
                "role": "user",
                "content": "Second message in session",
                "timestamp": "2024-01-01T10:05:00+00:00",
                "intent": "followup_intent",
                "verification_result": {"is_valid": True, "confidence": 0.88},
            },
        ],
        "created_at": "2024-01-01T10:00:00+00:00",
        "updated_at": "2024-01-01T10:05:00+00:00",
    }

    # Mock Redis client - return existing conversation data
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(existing_conversation))
    mock_redis.setex = AsyncMock(return_value=True)
    verifier.redis_client = mock_redis

    # Mock LLM Assistant with ainvoke_multi_turn (used in verify_with_context)
    mock_assistant = MagicMock()
    mock_assistant.ainvoke_multi_turn = AsyncMock(
        return_value={
            "risk_level": "low",
            "confidence": 0.92,
            "reasoning": ["Context verified with history"],
            "mitigations": ["None"],
            "recommended_decision": "approve",
        }
    )
    mock_assistant.analyze_message_impact = AsyncMock(
        return_value={
            "risk_level": "low",
            "confidence": 0.92,
            "reasoning": ["Context verified with history"],
            "mitigations": ["None"],
        }
    )
    verifier.assistant = mock_assistant

    # Mock PACARManager to avoid Redis connections
    mock_manager = MagicMock()
    mock_state = MagicMock()
    mock_state.messages = []
    mock_manager.add_message = AsyncMock(return_value=None)
    mock_manager.get_state = AsyncMock(return_value=mock_state)
    verifier.manager = mock_manager

    # Mock audit client
    verifier.audit_client = MagicMock()
    verifier.audit_client.report_decision = AsyncMock(return_value=None)

    result = await verifier.verify_with_context(
        content="Third message continuing conversation",
        original_intent="continuation_intent",
        session_id="existing-session-456",
        tenant_id="test-tenant",
    )

    # Verify result structure
    assert result["is_valid"] is True
    assert result["confidence"] == 0.92
    assert result["session_id"] == "existing-session-456"
    assert result["message_count"] == 3  # 2 existing + 1 new
    assert result["consensus_reached"] is True

    # Verify Redis operations
    mock_redis.get.assert_called_once()
    mock_redis.setex.assert_called_once()

    # Verify the stored conversation data includes all messages
    call_args = mock_redis.setex.call_args
    stored_key = call_args[0][0]
    stored_ttl = call_args[0][1]
    stored_data = call_args[0][2]

    assert "existing-session-456" in stored_key
    assert stored_ttl == 3600  # Default TTL
    conversation_data = json.loads(stored_data)
    assert conversation_data["session_id"] == "existing-session-456"
    assert conversation_data["tenant_id"] == "test-tenant"
    assert len(conversation_data["messages"]) == 3

    # Verify existing messages are preserved
    assert conversation_data["messages"][0]["content"] == "First message in session"
    assert conversation_data["messages"][1]["content"] == "Second message in session"

    # Verify new message was appended
    assert conversation_data["messages"][2]["role"] == "user"
    assert conversation_data["messages"][2]["content"] == "Third message continuing conversation"
    assert conversation_data["messages"][2]["intent"] == "continuation_intent"
    assert conversation_data["messages"][2]["verification_result"]["is_valid"] is True
    assert conversation_data["messages"][2]["verification_result"]["confidence"] == 0.92


async def test_pacar_context_window_pruning():
    """Test PACAR verifier enforces 50-message context window limit"""
    verifier = PACARVerifier()

    # Create existing conversation with 52 messages (exceeds 50 limit)
    existing_messages = []
    for i in range(52):
        existing_messages.append(
            {
                "role": "user",
                "content": f"Message number {i}",
                "timestamp": f"2024-01-01T10:{i:02d}:00+00:00",
                "intent": f"intent_{i}",
                "verification_result": {"is_valid": True, "confidence": 0.9},
            }
        )

    existing_conversation = {
        "session_id": "pruning-test-session",
        "tenant_id": "test-tenant",
        "messages": existing_messages,
        "created_at": "2024-01-01T10:00:00+00:00",
        "updated_at": "2024-01-01T10:51:00+00:00",
    }

    # Mock Redis client - return existing conversation with 52 messages
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=json.dumps(existing_conversation))
    mock_redis.setex = AsyncMock(return_value=True)
    verifier.redis_client = mock_redis

    # Mock LLM Assistant with ainvoke_multi_turn (used in verify_with_context)
    mock_assistant = MagicMock()
    mock_assistant.ainvoke_multi_turn = AsyncMock(
        return_value={
            "risk_level": "low",
            "confidence": 0.88,
            "reasoning": ["Context window pruning test"],
            "mitigations": ["None"],
            "recommended_decision": "approve",
        }
    )
    mock_assistant.analyze_message_impact = AsyncMock(
        return_value={
            "risk_level": "low",
            "confidence": 0.88,
            "reasoning": ["Context window pruning test"],
            "mitigations": ["None"],
        }
    )
    verifier.assistant = mock_assistant

    # Mock PACARManager to avoid Redis connections
    mock_manager = MagicMock()
    mock_state = MagicMock()
    mock_state.messages = []
    mock_manager.add_message = AsyncMock(return_value=None)
    mock_manager.get_state = AsyncMock(return_value=mock_state)
    verifier.manager = mock_manager

    # Mock audit client
    verifier.audit_client = MagicMock()
    verifier.audit_client.report_decision = AsyncMock(return_value=None)

    # Call verify_with_context - this adds 1 message (53 total before pruning)
    result = await verifier.verify_with_context(
        content="New message after pruning threshold",
        original_intent="pruning_test_intent",
        session_id="pruning-test-session",
        tenant_id="test-tenant",
    )

    # Verify result structure
    assert result["is_valid"] is True
    assert result["confidence"] == 0.88
    assert result["session_id"] == "pruning-test-session"
    assert result["consensus_reached"] is True

    # Verify Redis operations
    mock_redis.get.assert_called_once()
    mock_redis.setex.assert_called_once()

    # Verify the stored conversation was pruned to 50 messages
    call_args = mock_redis.setex.call_args
    stored_data = call_args[0][2]
    conversation_data = json.loads(stored_data)

    # After adding 1 message to 52, we have 53. Pruning should keep last 50.
    assert len(conversation_data["messages"]) == 50, (
        f"Expected 50 messages after pruning, got {len(conversation_data['messages'])}"
    )

    # Verify oldest messages were removed (messages 0, 1, 2 should be gone)
    # The first remaining message should be "Message number 3"
    assert conversation_data["messages"][0]["content"] == "Message number 3", (
        "Oldest messages should have been pruned"
    )

    # Verify the new message is the last one
    assert conversation_data["messages"][-1]["content"] == "New message after pruning threshold"
    assert conversation_data["messages"][-1]["intent"] == "pruning_test_intent"
    assert conversation_data["messages"][-1]["verification_result"]["is_valid"] is True


async def test_redis_unavailable_fallback():
    """Test PACAR verifier gracefully degrades when Redis is unavailable"""
    verifier = PACARVerifier()

    # Simulate Redis unavailable by setting redis_client to None
    verifier.redis_client = None

    # Mock LLM Assistant with ainvoke_multi_turn (used in verify_with_context)
    mock_assistant = MagicMock()
    mock_assistant.ainvoke_multi_turn = AsyncMock(
        return_value={
            "risk_level": "low",
            "confidence": 0.87,
            "reasoning": ["Content verified without Redis context"],
            "mitigations": ["None"],
            "recommended_decision": "approve",
        }
    )
    mock_assistant.analyze_message_impact = AsyncMock(
        return_value={
            "risk_level": "low",
            "confidence": 0.87,
            "reasoning": ["Content verified without Redis context"],
            "mitigations": ["None"],
        }
    )
    verifier.assistant = mock_assistant

    # Mock PACARManager to avoid Redis connections
    mock_manager = MagicMock()
    mock_state = MagicMock()
    mock_state.messages = []
    mock_manager.add_message = AsyncMock(return_value=None)
    mock_manager.get_state = AsyncMock(return_value=mock_state)
    verifier.manager = mock_manager

    # Mock audit client
    verifier.audit_client = MagicMock()
    verifier.audit_client.report_decision = AsyncMock(return_value=None)

    # Call verify_with_context with session_id - should still work
    result = await verifier.verify_with_context(
        content="Test content when Redis is unavailable",
        original_intent="fallback_test_intent",
        session_id="fallback-test-session-789",
        tenant_id="test-tenant",
    )

    # Verify result structure - verification should succeed despite Redis unavailability
    assert result["is_valid"] is True
    assert result["confidence"] == 0.87
    assert result["session_id"] == "fallback-test-session-789"
    assert result["message_count"] == 1  # New in-memory conversation
    assert result["consensus_reached"] is True

    # Verify LLM assistant's ainvoke_multi_turn was called (verify_with_context uses this)
    mock_assistant.ainvoke_multi_turn.assert_called()
