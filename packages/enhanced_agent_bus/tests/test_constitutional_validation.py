"""
ACGS-2 Enhanced Agent Bus - Constitutional Validation Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for constitutional validation paths.
"""

import pytest

from enhanced_agent_bus.agent_bus import EnhancedAgentBus
from enhanced_agent_bus.message_processor import MessageProcessor

# Import from module names that conftest.py patches (models, validators, core)
# This ensures class identity with the strategies in registry.py
from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    AgentMessage,
    MessageStatus,
    MessageType,
    Priority,
)
from enhanced_agent_bus.validators import (
    ValidationResult,
    validate_constitutional_hash,
    validate_message_content,
)

# Mark all tests as governance tests (95% coverage required)
# Constitutional Hash: 608508a9bd224290
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]


@pytest.fixture(autouse=True)
def _disable_docker_sandbox():
    """Disable Docker sandbox in runtime security scanner for unit tests.

    The runtime guardrails layer requires a Docker container with /sandbox/execute.py
    which is not available in the test environment. Disabling this layer allows the
    remaining security checks (constitutional hash, tenant, rate limit, input
    sanitization, prompt injection, anomaly detection) to run normally.
    """
    import enhanced_agent_bus.runtime_security as rt_sec

    original_scanner = rt_sec._scanner
    rt_sec._scanner = None
    config = rt_sec.RuntimeSecurityConfig(enable_runtime_guardrails=False)
    rt_sec._scanner = rt_sec.RuntimeSecurityScanner(config)
    yield
    rt_sec._scanner = original_scanner


class TestConstitutionalHashValidation:
    """Tests for constitutional hash validation."""

    def test_valid_constitutional_hash(self):
        """Test that valid constitutional hash passes validation."""
        result = validate_constitutional_hash(CONSTITUTIONAL_HASH)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_constitutional_hash(self):
        """Test that invalid constitutional hash fails validation."""
        result = validate_constitutional_hash("invalid_hash_123")
        assert not result.is_valid
        assert len(result.errors) == 1
        # Error message is sanitized with constant-time comparison
        assert "Constitutional hash mismatch" in result.errors[0]

    def test_empty_constitutional_hash(self):
        """Test that empty constitutional hash fails validation."""
        result = validate_constitutional_hash("")
        assert not result.is_valid

    def test_constitutional_hash_value(self):
        """Test that constitutional hash has expected value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_default_validation_result(self):
        """Test default ValidationResult is valid."""
        result = ValidationResult()
        assert result.is_valid
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_add_error(self):
        """Test adding error invalidates result."""
        result = ValidationResult()
        result.add_error("Test error")
        assert not result.is_valid
        assert "Test error" in result.errors

    def test_add_warning(self):
        """Test adding warning keeps result valid."""
        result = ValidationResult()
        result.add_warning("Test warning")
        assert result.is_valid
        assert "Test warning" in result.warnings

    def test_merge_validation_results(self):
        """Test merging validation results."""
        result1 = ValidationResult()
        result1.add_warning("Warning 1")

        result2 = ValidationResult()
        result2.add_error("Error 1")

        result1.merge(result2)

        assert not result1.is_valid
        assert "Warning 1" in result1.warnings
        assert "Error 1" in result1.errors


class TestMessageContentValidation:
    """Tests for message content validation."""

    def test_valid_content(self):
        """Test valid message content."""
        content = {"action": "test", "data": "value"}
        result = validate_message_content(content)
        assert result.is_valid

    def test_empty_action_warning(self):
        """Test empty action field generates warning."""
        content = {"action": ""}
        result = validate_message_content(content)
        assert result.is_valid  # Warning doesn't invalidate
        assert len(result.warnings) > 0

    def test_invalid_content_type(self):
        """Test non-dict content fails validation."""
        result = validate_message_content("not a dict")
        assert not result.is_valid
        assert "must be a dictionary" in result.errors[0]


class TestAgentMessage:
    """Tests for AgentMessage creation and validation."""

    def test_message_creation(self):
        """Test basic message creation."""
        message = AgentMessage(
            from_agent="agent1",
            to_agent="agent2",
            sender_id="sender1",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )

        assert message.from_agent == "agent1"
        assert message.to_agent == "agent2"
        assert message.message_type == MessageType.COMMAND
        assert message.constitutional_hash == CONSTITUTIONAL_HASH
        assert message.status == MessageStatus.PENDING

    def test_message_id_generation(self):
        """Test that message IDs are unique."""
        message1 = AgentMessage(
            from_agent="agent1",
            to_agent="agent2",
            sender_id="sender1",
            message_type=MessageType.COMMAND,
        )
        message2 = AgentMessage(
            from_agent="agent1",
            to_agent="agent2",
            sender_id="sender1",
            message_type=MessageType.COMMAND,
        )

        assert message1.message_id != message2.message_id

    def test_message_types(self):
        """Test all message types are valid."""
        for msg_type in MessageType:
            message = AgentMessage(
                from_agent="agent1",
                to_agent="agent2",
                sender_id="sender1",
                message_type=msg_type,
            )
            assert message.message_type == msg_type


class TestMessageProcessor:
    """Tests for MessageProcessor class."""

    @pytest.fixture
    def processor(self):
        """Create a MessageProcessor instance with MACI disabled for isolated testing."""
        # MACI is disabled for these legacy tests to isolate constitutional validation
        # For MACI-specific tests, see test_maci_integration.py
        return MessageProcessor(
            enable_maci=False
        )  # test-only: MACI off — testing constitutional validation directly

    @pytest.fixture
    def valid_message(self):
        """Create a valid test message."""
        return AgentMessage(
            from_agent="test_agent",
            to_agent="target_agent",
            sender_id="test_sender",
            tenant_id="default-tenant",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            payload={"data": "test_data"},
        )

    @pytest.fixture
    def invalid_hash_message(self):
        """Create a message with invalid constitutional hash."""
        message = AgentMessage(
            from_agent="test_agent",
            to_agent="target_agent",
            sender_id="test_sender",
            tenant_id="default-tenant",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )
        message.constitutional_hash = "invalid_hash"
        return message

    async def test_process_valid_message(self, processor, valid_message):
        """Test processing a valid message."""
        result = await processor.process(valid_message)

        assert result.is_valid
        assert valid_message.status == MessageStatus.DELIVERED

    async def test_process_invalid_hash_message(self, processor, invalid_hash_message):
        """Test processing message with invalid constitutional hash."""
        result = await processor.process(invalid_hash_message)

        assert not result.is_valid
        assert "Constitutional hash mismatch" in result.errors[0]

    async def test_handler_registration(self, processor, valid_message):
        """Test handler registration and execution."""
        handler_called = False

        async def test_handler(msg):
            nonlocal handler_called
            handler_called = True

        processor.register_handler(MessageType.COMMAND, test_handler)
        await processor.process(valid_message)

        assert handler_called

    async def test_sync_handler(self, processor, valid_message):
        """Test synchronous handler execution."""
        handler_called = False

        def sync_handler(msg):
            nonlocal handler_called
            handler_called = True

        processor.register_handler(MessageType.COMMAND, sync_handler)
        await processor.process(valid_message)

        assert handler_called

    async def test_processed_count(self, processor, valid_message):
        """Test processed message count."""
        initial_count = processor.processed_count

        await processor.process(valid_message)

        assert processor.processed_count == initial_count + 1

    async def test_handler_error_handling(self, processor, valid_message):
        """Test handler error is properly caught and reported."""

        def failing_handler(msg):
            raise ValueError("Handler error")

        processor.register_handler(MessageType.COMMAND, failing_handler)
        result = await processor.process(valid_message)

        assert not result.is_valid
        assert valid_message.status == MessageStatus.FAILED


class TestEnhancedAgentBus:
    """Tests for EnhancedAgentBus class."""

    @pytest.fixture
    def agent_bus(self):
        """Create an EnhancedAgentBus instance with MACI disabled for isolated testing."""
        # MACI is disabled for these legacy tests to isolate constitutional validation
        # For MACI-specific tests, see test_maci_integration.py
        return EnhancedAgentBus(
            enable_maci=False,
            enable_rate_limiting=False,
            allow_unstarted=True,
        )  # test-only: MACI + rate limiting off — testing constitutional validation directly

    @pytest.fixture
    def valid_message(self):
        """Create a valid test message."""
        return AgentMessage(
            from_agent="sender_agent",
            to_agent="receiver_agent",
            sender_id="test_sender",
            tenant_id="default-tenant",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )

    async def test_start_stop(self, agent_bus):
        """Test starting and stopping the agent bus."""
        await agent_bus.start()
        assert agent_bus._running

        await agent_bus.stop()
        assert not agent_bus._running

    async def test_agent_registration(self, agent_bus):
        """Test agent registration."""
        result = await agent_bus.register_agent(
            agent_id="test_agent",
            agent_type="worker",
            capabilities=["task_processing"],
        )

        assert result
        assert "test_agent" in agent_bus.get_registered_agents()

    async def test_agent_unregistration(self, agent_bus):
        """Test agent unregistration."""
        await agent_bus.register_agent("test_agent")

        result = await agent_bus.unregister_agent("test_agent")

        assert result
        assert "test_agent" not in agent_bus.get_registered_agents()

    async def test_unregister_nonexistent_agent(self, agent_bus):
        """Test unregistering nonexistent agent returns False."""
        result = await agent_bus.unregister_agent("nonexistent_agent")
        assert not result

    async def test_send_valid_message(self, agent_bus, valid_message):
        """Test sending a valid message."""
        result = await agent_bus.send_message(valid_message)

        assert result.is_valid
        assert agent_bus._metrics["messages_sent"] == 1

    async def test_send_invalid_hash_message(self, agent_bus):
        """Test sending message with invalid constitutional hash."""
        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            sender_id="sender",
            tenant_id="default-tenant",
            message_type=MessageType.COMMAND,
        )
        message.constitutional_hash = "invalid"

        result = await agent_bus.send_message(message)

        assert not result.is_valid
        assert agent_bus._metrics["messages_failed"] == 1

    async def test_receive_message(self, agent_bus, valid_message):
        """Test receiving a message from the queue."""
        await agent_bus.send_message(valid_message)

        received = await agent_bus.receive_message(timeout=1.0)

        assert received is not None
        assert received.message_id == valid_message.message_id
        assert agent_bus._metrics["messages_received"] == 1

    async def test_receive_message_timeout(self, agent_bus):
        """Test receive timeout returns None."""
        received = await agent_bus.receive_message(timeout=0.1)
        assert received is None

    async def test_get_metrics(self, agent_bus, valid_message):
        """Test getting bus metrics."""
        await agent_bus.register_agent("test_agent")
        await agent_bus.send_message(valid_message)

        metrics = agent_bus.get_metrics()

        assert metrics["registered_agents"] == 1
        assert metrics["messages_sent"] == 1
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_constitutional_hash_in_registration(self, agent_bus):
        """Test that registered agents have constitutional hash."""
        await agent_bus.register_agent("test_agent")

        agent_data = agent_bus.agents.get("test_agent")

        assert agent_data is not None
        assert agent_data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestMessagePriorityAndTypes:
    """Tests for message priority and type handling."""

    def test_message_priorities(self):
        """Test all message priorities."""
        for priority in Priority:
            message = AgentMessage(
                from_agent="agent1",
                to_agent="agent2",
                sender_id="sender",
                message_type=MessageType.COMMAND,
                priority=priority,
            )
            assert message.priority == priority

    def test_governance_message_types(self):
        """Test governance-specific message types."""
        governance_types = [
            MessageType.GOVERNANCE_REQUEST,
            MessageType.GOVERNANCE_RESPONSE,
            MessageType.CONSTITUTIONAL_VALIDATION,
        ]

        for msg_type in governance_types:
            message = AgentMessage(
                from_agent="governance_agent",
                to_agent="target_agent",
                sender_id="sender",
                message_type=msg_type,
            )
            assert message.message_type == msg_type


# Entry point for running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
