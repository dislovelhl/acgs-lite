"""
ACGS-2 Enhanced Agent Bus - Kafka Event Bus Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for KafkaEventBus, Orchestrator, and Blackboard classes.
"""

from unittest.mock import AsyncMock

import pytest

from enhanced_agent_bus.exceptions import MessageDeliveryError
from enhanced_agent_bus.kafka_bus import (
    KAFKA_AVAILABLE,
    Blackboard,
    KafkaEventBus,
    Orchestrator,
)
from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    AgentMessage,
    MessageType,
    Priority,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def kafka_bus() -> KafkaEventBus:
    """Create a KafkaEventBus instance."""
    return KafkaEventBus(bootstrap_servers="localhost:9092", client_id="test-client")


@pytest.fixture
def valid_message() -> AgentMessage:
    """Create a valid test message."""
    return AgentMessage(
        from_agent="test-sender",
        to_agent="test-receiver",
        content={"action": "test", "data": "hello"},
        constitutional_hash=CONSTITUTIONAL_HASH,
        message_type=MessageType.COMMAND,
        priority=Priority.NORMAL,
        tenant_id="tenant-123",
        conversation_id="conv-456",
    )


# =============================================================================
# KafkaEventBus Initialization Tests
# =============================================================================


class TestKafkaEventBusInitialization:
    """Tests for KafkaEventBus initialization."""

    def test_default_initialization(self) -> None:
        """Test initialization with default parameters."""
        bus = KafkaEventBus()
        assert bus.bootstrap_servers == "localhost:9092"
        assert bus.client_id == "acgs2-bus"
        assert bus.producer is None
        assert bus._consumers == {}
        assert bus._running is False

    def test_custom_initialization(self) -> None:
        """Test initialization with custom parameters."""
        bus = KafkaEventBus(
            bootstrap_servers="kafka.example.com:9093",
            client_id="custom-client",
        )
        assert bus.bootstrap_servers == "kafka.example.com:9093"
        assert bus.client_id == "custom-client"

    def test_multiple_bootstrap_servers(self) -> None:
        """Test initialization with multiple bootstrap servers."""
        servers = "kafka1:9092,kafka2:9092,kafka3:9092"
        bus = KafkaEventBus(bootstrap_servers=servers)
        assert bus.bootstrap_servers == servers


# =============================================================================
# Topic Naming Tests
# =============================================================================


class TestTopicNaming:
    """Tests for topic name generation."""

    def test_get_topic_name_basic(self, kafka_bus: KafkaEventBus) -> None:
        """Test basic topic name generation."""
        topic = kafka_bus._get_topic_name("tenant1", "COMMAND")
        assert topic == "acgs.tenant.tenant1.command"

    def test_get_topic_name_with_dots_in_tenant(self, kafka_bus: KafkaEventBus) -> None:
        """Test topic name with dots in tenant ID (should be replaced)."""
        topic = kafka_bus._get_topic_name("org.dept.team", "EVENT")
        assert topic == "acgs.tenant.org_dept_team.event"

    def test_get_topic_name_empty_tenant(self, kafka_bus: KafkaEventBus) -> None:
        """Test topic name with empty tenant ID."""
        topic = kafka_bus._get_topic_name("", "QUERY")
        assert topic == "acgs.tenant.default.query"

    def test_get_topic_name_none_tenant(self, kafka_bus: KafkaEventBus) -> None:
        """Test topic name with None tenant ID."""
        topic = kafka_bus._get_topic_name(None, "RESPONSE")
        assert topic == "acgs.tenant.default.response"

    def test_get_topic_name_case_insensitive(self, kafka_bus: KafkaEventBus) -> None:
        """Test that message type is converted to lowercase."""
        topic = kafka_bus._get_topic_name("tenant", "TASK_REQUEST")
        assert topic == "acgs.tenant.tenant.task_request"


# =============================================================================
# Start/Stop Tests (Without Kafka Available)
# =============================================================================


class TestKafkaEventBusLifecycle:
    """Tests for KafkaEventBus start/stop lifecycle."""

    async def test_start_without_kafka(self, kafka_bus: KafkaEventBus) -> None:
        """Test start when aiokafka is not available."""
        # Import the module to patch its constant
        from enhanced_agent_bus import kafka_bus as kb_module

        original_value = kb_module.KAFKA_AVAILABLE
        try:
            kb_module.KAFKA_AVAILABLE = False
            await kafka_bus.start()
            assert kafka_bus.producer is None
            assert kafka_bus._running is False
        finally:
            kb_module.KAFKA_AVAILABLE = original_value

    async def test_stop_without_producer(self, kafka_bus: KafkaEventBus) -> None:
        """Test stop when producer is not initialized."""
        await kafka_bus.stop()
        assert kafka_bus._running is False

    async def test_stop_with_mock_producer(self, kafka_bus: KafkaEventBus) -> None:
        """Test stop with a mock producer."""
        mock_producer = AsyncMock()
        kafka_bus.producer = mock_producer
        kafka_bus._running = True

        await kafka_bus.stop()

        assert kafka_bus._running is False
        mock_producer.flush.assert_called_once()
        mock_producer.stop.assert_called_once()

    async def test_stop_with_consumers(self, kafka_bus: KafkaEventBus) -> None:
        """Test stop with active consumers."""
        mock_consumer1 = AsyncMock()
        mock_consumer2 = AsyncMock()
        kafka_bus._consumers = {"consumer1": mock_consumer1, "consumer2": mock_consumer2}
        kafka_bus._running = True

        await kafka_bus.stop()

        mock_consumer1.stop.assert_called_once()
        mock_consumer2.stop.assert_called_once()


# =============================================================================
# Send Message Tests
# =============================================================================


class TestSendMessage:
    """Tests for send_message method."""

    async def test_send_message_producer_not_started(
        self, kafka_bus: KafkaEventBus, valid_message: AgentMessage
    ) -> None:
        """Test send_message when producer is not started."""
        with pytest.raises(MessageDeliveryError) as exc_info:
            await kafka_bus.send_message(valid_message)

        assert exc_info.value.reason == "Kafka producer not started"
        assert exc_info.value.message_id == valid_message.message_id

    async def test_send_message_not_running(
        self, kafka_bus: KafkaEventBus, valid_message: AgentMessage
    ) -> None:
        """Test send_message when bus is not running."""
        kafka_bus.producer = AsyncMock()
        kafka_bus._running = False

        with pytest.raises(MessageDeliveryError) as exc_info:
            await kafka_bus.send_message(valid_message)

        assert exc_info.value.reason == "Kafka producer not started"

    async def test_send_message_success(
        self, kafka_bus: KafkaEventBus, valid_message: AgentMessage
    ) -> None:
        """Test successful message sending."""
        mock_producer = AsyncMock()
        kafka_bus.producer = mock_producer
        kafka_bus._running = True

        result = await kafka_bus.send_message(valid_message)

        assert result is True
        mock_producer.send_and_wait.assert_called_once()

    async def test_send_message_with_partition_key(
        self, kafka_bus: KafkaEventBus, valid_message: AgentMessage
    ) -> None:
        """Test that conversation_id is used as partition key."""
        mock_producer = AsyncMock()
        kafka_bus.producer = mock_producer
        kafka_bus._running = True

        await kafka_bus.send_message(valid_message)

        call_kwargs = mock_producer.send_and_wait.call_args.kwargs
        assert call_kwargs["key"] == b"conv-456"

    async def test_send_message_with_auto_generated_conversation_id(
        self, kafka_bus: KafkaEventBus
    ) -> None:
        """Test send_message uses auto-generated conversation_id as key."""
        # Note: AgentMessage auto-generates conversation_id, so key is always set
        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            content={"test": "data"},
            message_type=MessageType.EVENT,
            tenant_id="tenant-1",
        )

        mock_producer = AsyncMock()
        kafka_bus.producer = mock_producer
        kafka_bus._running = True

        await kafka_bus.send_message(message)

        call_kwargs = mock_producer.send_and_wait.call_args.kwargs
        # Key is the encoded conversation_id (auto-generated UUID)
        assert call_kwargs["key"] is not None
        assert call_kwargs["key"] == message.conversation_id.encode("utf-8")

    async def test_send_message_failure(
        self, kafka_bus: KafkaEventBus, valid_message: AgentMessage
    ) -> None:
        """Test send_message when Kafka send fails."""
        mock_producer = AsyncMock()
        mock_producer.send_and_wait.side_effect = RuntimeError("Kafka send failed")
        kafka_bus.producer = mock_producer
        kafka_bus._running = True

        result = await kafka_bus.send_message(valid_message)

        assert result is False


# =============================================================================
# Subscribe Tests
# =============================================================================


class TestSubscribe:
    """Tests for subscribe method."""

    async def test_subscribe_without_kafka(self, kafka_bus: KafkaEventBus) -> None:
        """Test subscribe when aiokafka is not available."""
        handler = AsyncMock()

        # Import the module to patch its constant
        from enhanced_agent_bus import kafka_bus as kb_module

        original_value = kb_module.KAFKA_AVAILABLE
        try:
            kb_module.KAFKA_AVAILABLE = False
            await kafka_bus.subscribe(
                tenant_id="tenant-1",
                message_types=[MessageType.COMMAND],
                handler=handler,
            )
            # Should return without doing anything
            assert len(kafka_bus._consumers) == 0
        finally:
            kb_module.KAFKA_AVAILABLE = original_value


# =============================================================================
# Orchestrator Tests
# =============================================================================


class TestOrchestrator:
    """Tests for Orchestrator class."""

    def test_orchestrator_initialization(self, kafka_bus: KafkaEventBus) -> None:
        """Test Orchestrator initialization."""
        orchestrator = Orchestrator(bus=kafka_bus, tenant_id="tenant-1")
        assert orchestrator.bus is kafka_bus
        assert orchestrator.tenant_id == "tenant-1"

    async def test_dispatch_task(self, kafka_bus: KafkaEventBus) -> None:
        """Test dispatching a task to a worker."""
        mock_producer = AsyncMock()
        kafka_bus.producer = mock_producer
        kafka_bus._running = True

        orchestrator = Orchestrator(bus=kafka_bus, tenant_id="tenant-1")
        task_data = {"job_id": "job-123", "action": "process"}

        await orchestrator.dispatch_task(task_data, worker_type="processor")

        mock_producer.send_and_wait.assert_called_once()
        call_kwargs = mock_producer.send_and_wait.call_args.kwargs
        assert "value" in call_kwargs

    async def test_dispatch_task_with_worker_type(self, kafka_bus: KafkaEventBus) -> None:
        """Test that worker type is included in message."""
        mock_producer = AsyncMock()
        kafka_bus.producer = mock_producer
        kafka_bus._running = True

        orchestrator = Orchestrator(bus=kafka_bus, tenant_id="tenant-1")

        await orchestrator.dispatch_task({"data": "test"}, worker_type="analyzer")

        call_kwargs = mock_producer.send_and_wait.call_args.kwargs
        message_dict = call_kwargs["value"]
        assert message_dict["to_agent"] == "worker-analyzer"


# =============================================================================
# Blackboard Tests
# =============================================================================


class TestBlackboard:
    """Tests for Blackboard class."""

    def test_blackboard_initialization(self, kafka_bus: KafkaEventBus) -> None:
        """Test Blackboard initialization."""
        blackboard = Blackboard(
            bus=kafka_bus,
            tenant_id="tenant-1",
            board_name="shared-state",
        )
        assert blackboard.bus is kafka_bus
        assert blackboard.tenant_id == "tenant-1"
        assert blackboard.topic == "acgs.blackboard.tenant-1.shared-state"
        assert blackboard.state == {}

    def test_blackboard_topic_format(self, kafka_bus: KafkaEventBus) -> None:
        """Test blackboard topic naming format."""
        blackboard = Blackboard(
            bus=kafka_bus,
            tenant_id="org-xyz",
            board_name="coordination",
        )
        assert blackboard.topic == "acgs.blackboard.org-xyz.coordination"

    async def test_blackboard_update(self, kafka_bus: KafkaEventBus) -> None:
        """Test updating a value on the blackboard."""
        mock_producer = AsyncMock()
        kafka_bus.producer = mock_producer
        kafka_bus._running = True

        blackboard = Blackboard(
            bus=kafka_bus,
            tenant_id="tenant-1",
            board_name="shared-state",
        )

        await blackboard.update("key1", {"value": "data"})

        mock_producer.send_and_wait.assert_called_once()

    async def test_blackboard_update_content(self, kafka_bus: KafkaEventBus) -> None:
        """Test that update sends correct content."""
        mock_producer = AsyncMock()
        kafka_bus.producer = mock_producer
        kafka_bus._running = True

        blackboard = Blackboard(
            bus=kafka_bus,
            tenant_id="tenant-1",
            board_name="shared-state",
        )

        await blackboard.update("counter", 42)

        call_kwargs = mock_producer.send_and_wait.call_args.kwargs
        message_dict = call_kwargs["value"]
        assert message_dict["content"]["key"] == "counter"
        assert message_dict["content"]["value"] == 42

    async def test_blackboard_multiple_updates(self, kafka_bus: KafkaEventBus) -> None:
        """Test multiple updates to the blackboard."""
        mock_producer = AsyncMock()
        kafka_bus.producer = mock_producer
        kafka_bus._running = True

        blackboard = Blackboard(
            bus=kafka_bus,
            tenant_id="tenant-1",
            board_name="shared-state",
        )

        await blackboard.update("key1", "value1")
        await blackboard.update("key2", "value2")
        await blackboard.update("key3", "value3")

        assert mock_producer.send_and_wait.call_count == 3


# =============================================================================
# KAFKA_AVAILABLE Flag Tests
# =============================================================================


class TestKafkaAvailableFlag:
    """Tests for KAFKA_AVAILABLE flag behavior."""

    def test_kafka_available_is_boolean(self) -> None:
        """Test that KAFKA_AVAILABLE is a boolean."""
        assert isinstance(KAFKA_AVAILABLE, bool)


# =============================================================================
# Integration Tests
# =============================================================================


class TestKafkaEventBusIntegration:
    """Integration tests for KafkaEventBus components."""

    async def test_orchestrator_blackboard_workflow(self, kafka_bus: KafkaEventBus) -> None:
        """Test workflow with orchestrator and blackboard."""
        mock_producer = AsyncMock()
        kafka_bus.producer = mock_producer
        kafka_bus._running = True

        # Create orchestrator and blackboard
        orchestrator = Orchestrator(bus=kafka_bus, tenant_id="workflow-tenant")
        blackboard = Blackboard(
            bus=kafka_bus,
            tenant_id="workflow-tenant",
            board_name="workflow-state",
        )

        # Dispatch a task
        await orchestrator.dispatch_task(
            {"task": "analyze", "data": [1, 2, 3]},
            worker_type="analyzer",
        )

        # Update shared state
        await blackboard.update("analysis_status", "in_progress")
        await blackboard.update("analysis_status", "completed")

        assert mock_producer.send_and_wait.call_count == 3

    async def test_multiple_tenants(self, kafka_bus: KafkaEventBus) -> None:
        """Test operations with multiple tenants."""
        mock_producer = AsyncMock()
        kafka_bus.producer = mock_producer
        kafka_bus._running = True

        # Create orchestrators for different tenants
        orchestrator1 = Orchestrator(bus=kafka_bus, tenant_id="tenant-a")
        orchestrator2 = Orchestrator(bus=kafka_bus, tenant_id="tenant-b")

        # Dispatch tasks
        await orchestrator1.dispatch_task({"job": "a1"}, worker_type="worker")
        await orchestrator2.dispatch_task({"job": "b1"}, worker_type="worker")

        assert mock_producer.send_and_wait.call_count == 2

        # Check different topics were used
        calls = mock_producer.send_and_wait.call_args_list
        topics = [call.args[0] for call in calls]
        assert "acgs.tenant.tenant-a.task_request" in topics
        assert "acgs.tenant.tenant-b.task_request" in topics
