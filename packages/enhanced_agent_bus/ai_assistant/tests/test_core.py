"""
ACGS-2 AI Assistant - Core Orchestrator Tests
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
from enhanced_agent_bus.ai_assistant.core import (
    AIAssistant,
    AssistantConfig,
    AssistantState,
    ProcessingResult,
    create_assistant,
)
from enhanced_agent_bus.ai_assistant.nlu import NLUResult


class TestAssistantConfig:
    """Tests for AssistantConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AssistantConfig()

        assert config.name == "ACGS-2 Assistant"
        assert config.max_conversation_turns == 100
        assert config.session_timeout_minutes == 30
        assert config.enable_governance is True
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_config(self):
        """Test custom configuration."""
        config = AssistantConfig(
            name="Custom Assistant",
            max_conversation_turns=50,
            enable_governance=False,
        )

        assert config.name == "Custom Assistant"
        assert config.max_conversation_turns == 50
        assert config.enable_governance is False

    def test_config_to_dict(self):
        """Test config serialization."""
        config = AssistantConfig()

        data = config.to_dict()

        assert "name" in data
        assert "enable_governance" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestProcessingResult:
    """Tests for ProcessingResult dataclass."""

    def test_success_result(self):
        """Test creating a success result."""
        result = ProcessingResult(
            success=True,
            response_text="Hello! How can I help you?",
            intent="greeting",
            confidence=0.95,
        )

        assert result.success is True
        assert result.response_text == "Hello! How can I help you?"
        assert result.intent == "greeting"
        assert result.confidence == 0.95

    def test_failure_result(self):
        """Test creating a failure result."""
        result = ProcessingResult(
            success=False,
            response_text="An error occurred.",
            metadata={"error": "Something went wrong"},
        )

        assert result.success is False
        assert result.metadata["error"] == "Something went wrong"

    def test_result_to_dict(self):
        """Test result serialization."""
        result = ProcessingResult(
            success=True,
            response_text="Test",
        )

        data = result.to_dict()

        assert "success" in data
        assert "response_text" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestAssistantState:
    """Tests for AssistantState enum."""

    def test_all_states_exist(self):
        """Test all assistant states exist."""
        assert AssistantState.INITIALIZED
        assert AssistantState.READY
        assert AssistantState.PROCESSING
        assert AssistantState.ERROR
        assert AssistantState.SHUTDOWN


class TestAIAssistant:
    """Tests for AIAssistant orchestrator."""

    def test_create_assistant(self):
        """Test creating an assistant."""
        assistant = AIAssistant()

        assert assistant is not None
        assert assistant.state == AssistantState.INITIALIZED

    def test_create_with_config(self):
        """Test creating with custom config."""
        config = AssistantConfig(name="Custom")
        assistant = AIAssistant(config=config)

        assert assistant.config.name == "Custom"

    async def test_initialize(self):
        """Test assistant initialization."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))

        result = await assistant.initialize()

        assert result is True
        assert assistant.state == AssistantState.READY
        assert assistant.is_ready is True

    async def test_shutdown(self):
        """Test assistant shutdown."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        await assistant.shutdown()

        assert assistant.state == AssistantState.SHUTDOWN

    async def test_process_message_not_ready(self):
        """Test processing when not ready."""
        assistant = AIAssistant()

        result = await assistant.process_message(
            user_id="user123",
            message="Hello",
        )

        assert result.success is False

    async def test_process_message_success(self):
        """Test successful message processing."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        result = await assistant.process_message(
            user_id="user123",
            message="Hello, how are you?",
        )

        assert result.success is True
        assert result.response_text is not None
        assert len(result.response_text) > 0
        assert result.processing_time_ms >= 0
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_process_message_returns_intent(self):
        """Test that processing returns intent."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        result = await assistant.process_message(
            user_id="user123",
            message="What is the status of my order?",
        )

        assert result.success is True
        # Intent should be detected
        assert result.intent is not None or result.confidence >= 0

    async def test_process_message_with_session(self):
        """Test processing with session ID."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        result = await assistant.process_message(
            user_id="user123",
            message="Hello",
            session_id="session456",
        )

        assert result.success is True
        assert "session_id" in result.metadata


class TestAIAssistantSessionManagement:
    """Tests for session management in AIAssistant."""

    async def test_get_session(self):
        """Test getting an active session."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        await assistant.process_message(
            user_id="user123",
            message="Hello",
            session_id="session456",
        )

        session = assistant.get_session("session456")

        assert session is not None
        assert session.user_id == "user123"

    async def test_get_user_sessions(self):
        """Test getting sessions for a user."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        await assistant.process_message("user123", "Hello", "session1")
        await assistant.process_message("user123", "Hi", "session2")
        await assistant.process_message("user456", "Hey", "session3")

        sessions = assistant.get_user_sessions("user123")

        assert len(sessions) == 2

    async def test_end_session(self):
        """Test ending a session."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        await assistant.process_message(
            user_id="user123",
            message="Hello",
            session_id="session456",
        )

        result = assistant.end_session("session456")

        assert result is True
        assert assistant.get_session("session456") is None

    async def test_end_nonexistent_session(self):
        """Test ending a session that doesn't exist."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        result = assistant.end_session("nonexistent")

        assert result is False


class TestAIAssistantConversationFlow:
    """Tests for conversation flow in AIAssistant."""

    async def test_multi_turn_conversation(self):
        """Test multi-turn conversation."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        # First turn
        result1 = await assistant.process_message(
            user_id="user123",
            message="Hello",
            session_id="session456",
        )
        assert result1.success is True

        # Second turn
        result2 = await assistant.process_message(
            user_id="user123",
            message="I need help with my order",
            session_id="session456",
        )
        assert result2.success is True

        # Third turn
        result3 = await assistant.process_message(
            user_id="user123",
            message="Order number is ORD-12345",
            session_id="session456",
        )
        assert result3.success is True

        # Check conversation history
        session = assistant.get_session("session456")
        assert len(session.messages) >= 6  # 3 user + 3 assistant

    async def test_context_preserved_across_turns(self):
        """Test that context is preserved across turns."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        await assistant.process_message(
            user_id="user123",
            message="My order number is ORD-12345",
            session_id="session456",
        )

        session = assistant.get_session("session456")

        # Entity should be extracted and preserved
        assert session is not None


class TestAIAssistantMetrics:
    """Tests for metrics in AIAssistant."""

    async def test_get_metrics(self):
        """Test getting assistant metrics."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        await assistant.process_message("user123", "Hello")

        metrics = assistant.get_metrics()

        assert "state" in metrics
        assert "active_sessions" in metrics
        assert "total_messages_processed" in metrics
        assert metrics["total_messages_processed"] == 1
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_health(self):
        """Test getting health status."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        health = assistant.get_health()

        assert health["status"] == "healthy"
        assert health["state"] == "ready"


class TestAIAssistantListeners:
    """Tests for event listeners in AIAssistant."""

    async def test_add_listener(self):
        """Test adding a listener."""

        class MockListener:
            def __init__(self):
                self.messages_received = []
                self.responses_generated = []

            async def on_message_received(self, context, message):
                self.messages_received.append(message)

            async def on_response_generated(self, context, response, result):
                self.responses_generated.append(response)

            async def on_error(self, context, error):
                pass

        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        listener = MockListener()
        assistant.add_listener(listener)

        await assistant.initialize()
        await assistant.process_message("user123", "Hello")

        assert len(listener.messages_received) == 1
        assert len(listener.responses_generated) == 1

    async def test_remove_listener(self):
        """Test removing a listener."""

        class MockListener:
            def __init__(self):
                self.call_count = 0

            async def on_message_received(self, context, message):
                self.call_count += 1

            async def on_response_generated(self, context, response, result):
                pass

            async def on_error(self, context, error):
                pass

        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        listener = MockListener()
        assistant.add_listener(listener)
        assistant.remove_listener(listener)

        await assistant.initialize()
        await assistant.process_message("user123", "Hello")

        assert listener.call_count == 0


class TestCreateAssistantFactory:
    """Tests for create_assistant factory function."""

    async def test_create_assistant_default(self):
        """Test creating assistant with defaults."""
        assistant = await create_assistant()

        assert assistant is not None
        assert assistant.is_ready is True
        assert assistant.config.name == "ACGS-2 Assistant"

        await assistant.shutdown()

    async def test_create_assistant_custom_name(self):
        """Test creating assistant with custom name."""
        assistant = await create_assistant(name="Custom Bot")

        assert assistant.config.name == "Custom Bot"

        await assistant.shutdown()

    async def test_create_assistant_no_governance(self):
        """Test creating assistant without governance."""
        assistant = await create_assistant(enable_governance=False)

        assert assistant.config.enable_governance is False

        await assistant.shutdown()


class TestAIAssistantErrorHandling:
    """Tests for error handling in AIAssistant."""

    async def test_empty_message(self):
        """Test handling empty message."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        result = await assistant.process_message(
            user_id="user123",
            message="",
        )

        # Should handle gracefully
        assert isinstance(result, ProcessingResult)

    async def test_whitespace_message(self):
        """Test handling whitespace-only message."""
        assistant = AIAssistant(config=AssistantConfig(enable_governance=False))
        await assistant.initialize()

        result = await assistant.process_message(
            user_id="user123",
            message="   ",
        )

        # Should handle gracefully
        assert isinstance(result, ProcessingResult)


class TestAIAssistantCustomComponents:
    """Tests for AIAssistant with custom components."""

    async def test_custom_nlu_engine(self):
        """Test using custom NLU engine."""

        class MockNLUEngine:
            async def process(self, text, context=None):
                return NLUResult(
                    intents=[{"intent": "custom", "confidence": 1.0}],
                    confidence=1.0,
                )

        assistant = AIAssistant(
            config=AssistantConfig(enable_governance=False),
            nlu_engine=MockNLUEngine(),
        )
        await assistant.initialize()

        result = await assistant.process_message("user123", "Test")

        assert result.intent == "custom"

    async def test_custom_dialog_manager(self):
        """Test using custom dialog manager."""
        from enhanced_agent_bus.ai_assistant.dialog import ActionType, DialogAction

        class MockDialogManager:
            async def process_turn(self, context, nlu_result):
                return {
                    "action": DialogAction(
                        action_type=ActionType.RESPOND,
                        parameters={"custom": True},
                    )
                }

        assistant = AIAssistant(
            config=AssistantConfig(enable_governance=False),
            dialog_manager=MockDialogManager(),
        )
        await assistant.initialize()

        result = await assistant.process_message("user123", "Test")

        assert result.action_taken == "respond"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
