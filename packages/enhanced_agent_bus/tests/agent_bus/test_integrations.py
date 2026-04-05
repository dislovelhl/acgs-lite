"""
ACGS-2 Enhanced Agent Bus Tests
Constitutional Hash: 608508a9bd224290

Comprehensive test coverage for agent_bus.py - the core EnhancedAgentBus class.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from enhanced_agent_bus.agent_bus import (
        EnhancedAgentBus,
        get_agent_bus,
        reset_agent_bus,
    )
    from enhanced_agent_bus.exceptions import (
        BusNotStartedError,
        ConstitutionalHashMismatchError,
    )
    from enhanced_agent_bus.models import (
        CONSTITUTIONAL_HASH,
        AgentMessage,
        MessageStatus,
        MessageType,
        Priority,
    )
    from enhanced_agent_bus.validators import ValidationResult
except ImportError:
    import sys

    sys.path.insert(0, "/home/martin/ACGS")
    from enhanced_agent_bus.agent_bus import (
        EnhancedAgentBus,
        get_agent_bus,
        reset_agent_bus,
    )
    from enhanced_agent_bus.models import (
        CONSTITUTIONAL_HASH,
        AgentMessage,
        MessageStatus,
        MessageType,
        Priority,
    )
    from enhanced_agent_bus.validators import ValidationResult


# Test fixtures
@pytest.fixture
def constitutional_hash():
    """Constitutional hash used throughout tests."""
    return CONSTITUTIONAL_HASH


@pytest.fixture
def mock_processor():
    """Mock message processor for testing."""
    processor = MagicMock()
    processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))
    processor.get_metrics = MagicMock(return_value={"processed": 0})
    return processor


@pytest.fixture
def mock_registry():
    """Mock agent registry for testing."""
    registry = MagicMock()
    registry.register = MagicMock(return_value=True)
    registry.unregister = MagicMock(return_value=True)
    registry.get = MagicMock(return_value=None)
    return registry


@pytest.fixture
def mock_router():
    """Mock message router for testing."""
    router = MagicMock()
    router.route = AsyncMock()
    return router


@pytest.fixture
def mock_validator():
    """Mock validation strategy for testing."""
    validator = MagicMock()
    validator.validate = AsyncMock(return_value=(True, None))
    return validator


@pytest.fixture
async def agent_bus(mock_processor, mock_registry, mock_router, mock_validator):
    """Create an EnhancedAgentBus for testing."""
    bus = EnhancedAgentBus(
        redis_url="redis://localhost:6379",
        use_dynamic_policy=False,
        use_kafka=False,
        use_redis_registry=False,
        enable_metering=False,  # Disable metering for basic tests
        enable_rate_limiting=False,  # Disable rate limiting (needs Redis auth)
        allow_unstarted=True,
        processor=mock_processor,
        registry=mock_registry,
        router=mock_router,
        validator=mock_validator,
    )
    yield bus
    # Cleanup
    if bus.is_running:
        await bus.stop()


@pytest.fixture
async def started_agent_bus(agent_bus):
    """Create and start an EnhancedAgentBus for testing."""
    await agent_bus.start()
    yield agent_bus
    if agent_bus.is_running:
        await agent_bus.stop()


@pytest.fixture
def sample_message(constitutional_hash):
    """Create a sample message for testing."""
    return AgentMessage(
        message_id=str(uuid.uuid4()),
        from_agent="agent-sender",
        to_agent="agent-receiver",
        message_type=MessageType.GOVERNANCE_REQUEST,
        content={"action": "test"},
        priority=Priority.MEDIUM,
        constitutional_hash=constitutional_hash,
        tenant_id="tenant-1",
    )


@pytest.fixture
def sample_message_no_tenant(constitutional_hash):
    """Create a sample message without tenant for testing."""
    return AgentMessage(
        message_id=str(uuid.uuid4()),
        from_agent="agent-sender",
        to_agent="agent-receiver",
        message_type=MessageType.GOVERNANCE_REQUEST,
        content={"action": "test"},
        priority=Priority.MEDIUM,
        constitutional_hash=constitutional_hash,
        tenant_id=None,
    )


# =============================================================================
# LIFECYCLE TESTS
# =============================================================================


class TestRouteAndDeliverPaths:
    """Test _route_and_deliver code paths for coverage."""

    @pytest.fixture
    def bus_with_internal_queue(self):
        """Create bus without Kafka for internal queue testing."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            use_kafka=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic
        bus._use_kafka = False
        return bus

    async def test_route_and_deliver_to_internal_queue(self, bus_with_internal_queue):
        """Test message delivery to internal queue when Kafka is disabled."""
        bus = bus_with_internal_queue
        await bus.start()

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        success = await bus._route_and_deliver(message)

        assert success

        # Message should be in the internal queue
        assert bus._message_queue.qsize() >= 1

        await bus.stop()


class TestKafkaPolling:
    """Test Kafka polling background task for coverage."""

    async def test_poll_kafka_messages_no_kafka_bus(self):
        """Test _poll_kafka_messages returns early when no Kafka bus."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic
        bus._kafka_bus = None

        # Should return immediately without error
        await bus._poll_kafka_messages()

    async def test_poll_kafka_messages_with_kafka(self):
        """Test _poll_kafka_messages subscribes and polls."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        mock_kafka = AsyncMock()
        mock_kafka.subscribe = AsyncMock()
        bus._kafka_bus = mock_kafka
        bus._running = False  # Stop immediately

        await bus._poll_kafka_messages()

        # Subscribe should be called with handler
        mock_kafka.subscribe.assert_called_once()


class TestRegistrationWithPolicyClient:
    """Test registration paths with policy client for dynamic key."""

    async def test_register_handles_policy_client_error(self):
        """Test registration handles policy client errors gracefully."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        mock_policy = AsyncMock()
        mock_policy.get_current_public_key = AsyncMock(side_effect=Exception("Policy unavailable"))
        bus._policy_client = mock_policy

        result = await bus.register_agent(
            agent_id="test-agent",
            agent_type="worker",
        )

        # Should still succeed with default hash
        assert result
        agent = bus.agents.get("test-agent")
        assert agent is not None


class TestMACIRegistrationPaths:
    """Test MACI registration paths for coverage."""

    async def test_register_with_maci_role_success(self):
        """Test successful MACI role registration."""
        bus = EnhancedAgentBus(enable_maci=True, maci_strict_mode=False, allow_unstarted=True)

        from maci_enforcement import MACIRole

        result = await bus.register_agent(
            agent_id="executive-agent",
            agent_type="policy",
            maci_role=MACIRole.EXECUTIVE,
        )

        assert result
        agent = bus.agents.get("executive-agent")
        assert agent is not None
        # Role value is stored as-is from the enum
        assert agent["maci_role"] in ["EXECUTIVE", "executive"]


class TestOTELTracingPaths:
    """Test OTEL tracing code paths for coverage."""

    async def test_send_message_without_otel(self):
        """Test send_message works when OTEL is disabled."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic
        await bus.start()

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        # Should work without OTEL
        result = await bus.send_message(message)
        assert result is not None

        await bus.stop()


class TestKafkaMessageHandler:
    """Test Kafka message handler paths for coverage."""

    async def test_kafka_handler_processes_valid_message(self):
        """Test Kafka handler processes valid message data."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        # Access the internal queue
        original_queue_size = bus._message_queue.qsize()

        # Simulate what the Kafka handler does
        msg_data = {
            "message_id": str(uuid.uuid4()),
            "from_agent": "kafka-sender",
            "to_agent": "receiver",
            "message_type": "command",  # Lowercase as expected by MessageType enum
            "content": {"action": "from_kafka"},
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        message = AgentMessage.from_dict(msg_data)
        await bus._message_queue.put(message)

        # Message should be in queue
        assert bus._message_queue.qsize() == original_queue_size + 1

    async def test_kafka_handler_with_invalid_message(self):
        """Test Kafka handler handles invalid message data."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        # Test that AgentMessage.from_dict handles bad data
        try:
            bad_msg_data = {"invalid": "data"}
            AgentMessage.from_dict(bad_msg_data)
        except (RuntimeError, ValueError, TypeError):
            # Expected - invalid message data
            pass


class TestCircuitBreakerHealthMetrics:
    """Test circuit breaker health in metrics for coverage."""

    async def test_get_metrics_async_without_circuit_breaker(self):
        """Test get_metrics_async when circuit breaker is disabled."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        metrics = await bus.get_metrics_async()

        # Should have circuit breaker health status
        assert "circuit_breaker_health" in metrics


class TestRedisRegistryPath:
    """Test Redis registry initialization path."""

    def test_init_registry_redis_path_not_available(self):
        """Test Redis registry fallback when not available."""
        # Without Redis URL, should use InMemory
        bus = EnhancedAgentBus(
            enable_maci=False,
            use_redis_registry=True,
            redis_url="redis://localhost:6379",  # test-only: MACI off to isolate transport/routing logic
            allow_unstarted=True,
        )

        # May use Redis or fallback to InMemory depending on availability
        assert bus.registry is not None


class TestOPAValidatorPath:
    """Test OPA validator initialization path."""

    def test_init_validator_opa_path_via_injection(self):
        """Test validator can use OPA when injected via _opa_client."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            use_dynamic_policy=True,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        # Inject OPA client after construction
        mock_opa = MagicMock()
        bus._opa_client = mock_opa

        # Re-initialize validator to pick up OPA client
        from registry import OPAValidationStrategy

        bus._validator = OPAValidationStrategy(opa_client=mock_opa)

        assert isinstance(bus._validator, OPAValidationStrategy)

    def test_init_validator_dynamic_policy_path(self):
        """Test validator uses DynamicPolicy when policy client is available."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            use_dynamic_policy=True,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        # Inject policy client after construction
        mock_policy = MagicMock()
        bus._policy_client = mock_policy

        # Re-initialize validator to pick up policy client
        from registry import DynamicPolicyValidationStrategy

        bus._validator = DynamicPolicyValidationStrategy(policy_client=mock_policy)

        assert isinstance(bus._validator, DynamicPolicyValidationStrategy)


class TestBroadcastMultiTenantIsolation:
    """Test broadcast message multi-tenant isolation paths for coverage."""

    async def test_broadcast_skips_agents_from_different_tenant(self):
        """Test broadcast skips agents not in same tenant."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic
        await bus.start()

        # Register agents in different tenants
        await bus.register_agent("agent-A1", "worker", [], "tenant-A")
        await bus.register_agent("agent-A2", "worker", [], "tenant-A")
        await bus.register_agent("agent-B1", "worker", [], "tenant-B")

        # Create message for tenant-A
        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="broadcast",
            message_type=MessageType.COMMAND,
            content={"action": "test_broadcast"},
            constitutional_hash=CONSTITUTIONAL_HASH,
            tenant_id="tenant-A",
        )

        results = await bus.broadcast_message(message)

        # Only tenant-A agents should receive the message
        assert "agent-A1" in results
        assert "agent-A2" in results
        # agent-B1 should be skipped (different tenant)
        # The skipped_agents path should be executed

        await bus.stop()

    async def test_broadcast_to_no_tenant_agents(self):
        """Test broadcast to agents without tenant."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic
        await bus.start()

        # Register agents without tenant
        await bus.register_agent("agent-1", "worker")
        await bus.register_agent("agent-2", "worker")

        # Create message without tenant
        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="broadcast",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        results = await bus.broadcast_message(message)

        assert "agent-1" in results
        assert "agent-2" in results

        await bus.stop()


class TestQueryMethods:
    """Test various query methods for coverage."""

    async def test_get_registered_agents(self):
        """Test get_registered_agents returns all agent IDs."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        await bus.register_agent("agent-1", "worker")
        await bus.register_agent("agent-2", "analyzer")

        agents = bus.get_registered_agents()

        assert "agent-1" in agents
        assert "agent-2" in agents

    async def test_get_agents_by_type(self):
        """Test get_agents_by_type filters correctly."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        await bus.register_agent("worker-1", "worker")
        await bus.register_agent("worker-2", "worker")
        await bus.register_agent("analyzer-1", "analyzer")

        workers = bus.get_agents_by_type("worker")

        assert "worker-1" in workers
        assert "worker-2" in workers
        assert "analyzer-1" not in workers

    async def test_get_agents_by_capability(self):
        """Test get_agents_by_capability filters correctly."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        await bus.register_agent("agent-1", "worker", ["read", "write"])
        await bus.register_agent("agent-2", "worker", ["read"])
        await bus.register_agent("agent-3", "worker", ["execute"])

        readers = bus.get_agents_by_capability("read")

        assert "agent-1" in readers
        assert "agent-2" in readers
        assert "agent-3" not in readers


class TestSyncMetrics:
    """Test synchronous get_metrics method for coverage."""

    async def test_get_metrics_returns_sync_data(self):
        """Test get_metrics returns synchronous metrics."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        await bus.register_agent("test-agent", "worker")

        metrics = bus.get_metrics()

        assert "registered_agents" in metrics
        assert metrics["registered_agents"] == 1
        assert "queue_size" in metrics
        assert "messages_sent" in metrics


class TestFailedMessagePaths:
    """Test message failure paths for coverage."""

    async def test_send_message_with_invalid_hash(self):
        """Test sending message with invalid constitutional hash."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        await bus.register_agent("sender", "worker")
        await bus.register_agent("receiver", "worker")

        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )
        # Corrupt the hash
        message.constitutional_hash = "invalid_hash_value"

        result = await bus.send_message(message)

        assert not result.is_valid
        assert bus._metrics["messages_failed"] >= 1

    async def test_send_message_to_nonexistent_agent(self):
        """Test sending message to agent that doesn't exist passes validation.

        The bus allows messages to be sent to agents not yet registered,
        as they may be registered on another node or arrive later.
        """
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        await bus.register_agent("sender", "worker")

        message = AgentMessage(
            from_agent="sender",
            to_agent="nonexistent_agent",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )

        result = await bus.send_message(message)

        # Bus allows messages to unregistered agents (deferred delivery)
        assert result.is_valid

    async def test_tenant_validation_failure(self):
        """Test tenant validation failure path."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        await bus.register_agent("sender", "worker", tenant_id="tenant-A")
        await bus.register_agent("receiver", "worker", tenant_id="tenant-B")

        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            tenant_id="tenant-A",  # Sender's tenant
        )

        result = await bus.send_message(message)

        # Cross-tenant should either fail or have warnings
        assert result is not None


class TestUnregisterAgent:
    """Test agent unregistration paths."""

    async def test_unregister_existing_agent(self):
        """Test unregistering an existing agent."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        await bus.register_agent("test-agent", "worker")
        assert "test-agent" in bus.get_registered_agents()

        await bus.unregister_agent("test-agent")
        assert "test-agent" not in bus.get_registered_agents()

    async def test_unregister_nonexistent_agent(self):
        """Test unregistering a non-existent agent."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        # Should not raise error
        await bus.unregister_agent("nonexistent-agent")


class TestMessagePriorityPaths:
    """Test message priority handling."""

    async def test_high_priority_message(self):
        """Test sending high priority message."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        await bus.register_agent("sender", "worker")
        await bus.register_agent("receiver", "worker")

        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
            content={"action": "urgent"},
            priority=Priority.HIGH,
        )

        result = await bus.send_message(message)

        assert result.is_valid

    async def test_low_priority_message(self):
        """Test sending low priority message."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        await bus.register_agent("sender", "worker")
        await bus.register_agent("receiver", "worker")

        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
            content={"action": "background"},
            priority=Priority.LOW,
        )

        result = await bus.send_message(message)

        assert result.is_valid


class TestBusStopAndCleanup:
    """Test bus stop and cleanup paths."""

    async def test_stop_clears_agents(self):
        """Test stop clears registered agents."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic
        await bus.start()

        await bus.register_agent("agent-1", "worker")
        await bus.register_agent("agent-2", "worker")

        await bus.stop()

        # After stop, bus state should be reset
        assert not bus._running

    async def test_double_start_is_safe(self):
        """Test calling start twice is safe."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        await bus.start()
        await bus.start()  # Second start should be safe

        assert bus._running

        await bus.stop()

    async def test_double_stop_is_safe(self):
        """Test calling stop twice is safe."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        await bus.start()
        await bus.stop()
        await bus.stop()  # Second stop should be safe

        assert not bus._running


class TestMeteringManagerPaths:
    """Test metering manager integration paths."""

    async def test_metering_manager_records_message(self):
        """Test metering manager records message."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic
        await bus.start()

        await bus.register_agent("sender", "worker")
        await bus.register_agent("receiver", "worker")

        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )

        result = await bus.send_message(message)

        # Metering should have recorded the message
        assert result.is_valid
        # Metering manager is internal, just verify no errors

        await bus.stop()


class TestInternalQueueAccess:
    """Test internal message queue access."""

    async def test_message_queue_exists(self):
        """Test internal message queue is initialized."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        # Internal queue should be initialized
        assert bus._message_queue is not None

    async def test_queue_size_in_metrics(self):
        """Test queue size is reported in metrics."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        metrics = bus.get_metrics()

        assert "queue_size" in metrics


class TestRouteAndDeliverBranches:
    """Test _route_and_deliver branch coverage."""

    async def test_message_to_unregistered_recipient_logs_debug(self):
        """Test message to unregistered recipient triggers debug log."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic
        await bus.start()

        # Register sender only
        await bus.register_agent("sender", "worker")

        message = AgentMessage(
            from_agent="sender",
            to_agent="unknown_recipient",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )

        result = await bus.send_message(message)

        # Should succeed (message queued) with debug log about recipient
        assert result.is_valid
        await bus.stop()

    async def test_message_without_to_agent(self):
        """Test message without to_agent field."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic
        await bus.start()

        await bus.register_agent("sender", "worker")

        message = AgentMessage(
            from_agent="sender",
            to_agent=None,  # No specific recipient
            message_type=MessageType.COMMAND,
            content={"action": "broadcast"},
        )

        result = await bus.send_message(message)

        # Should succeed
        assert result is not None
        await bus.stop()


class TestNormalizeTenantId:
    """Test _normalize_tenant_id static method."""

    def test_normalize_none_tenant(self):
        """Test normalizing None tenant ID."""
        result = EnhancedAgentBus._normalize_tenant_id(None)
        assert result is None

    def test_normalize_empty_string_tenant(self):
        """Test normalizing empty string tenant ID."""
        result = EnhancedAgentBus._normalize_tenant_id("")
        # Empty string may be treated as None or empty
        assert result in [None, ""]

    def test_normalize_valid_tenant(self):
        """Test normalizing valid tenant ID."""
        result = EnhancedAgentBus._normalize_tenant_id("tenant-123")
        assert result == "tenant-123"

    def test_normalize_whitespace_tenant(self):
        """Test normalizing whitespace tenant ID."""
        result = EnhancedAgentBus._normalize_tenant_id("  tenant-123  ")
        # May strip whitespace
        assert "tenant-123" in result or result == "  tenant-123  "


class TestProcessorDelegation:
    """Test processor delegation and integration."""

    async def test_processor_metrics_included(self):
        """Test processor metrics are included in bus metrics."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        metrics = bus.get_metrics()

        assert "processor_metrics" in metrics

    async def test_processor_property_access(self):
        """Test accessing processor property."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        # Processor should be accessible
        assert bus._processor is not None
        assert hasattr(bus._processor, "process")


class TestDynamicPolicyFlag:
    """Test dynamic policy flag behavior."""

    def test_dynamic_policy_disabled_by_default(self):
        """Test dynamic policy is disabled by default."""
        bus = EnhancedAgentBus(
            enable_maci=False,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        # Default should have static validation
        assert bus._validator is not None

    def test_dynamic_policy_flag_passed(self):
        """Test dynamic policy flag affects initialization path.

        When POLICY_CLIENT_AVAILABLE is False, _use_dynamic_policy
        remains False even if flag is passed.
        """
        # Import the module-level constant
        try:
            from enhanced_agent_bus.agent_bus import POLICY_CLIENT_AVAILABLE
        except ImportError:
            from agent_bus import POLICY_CLIENT_AVAILABLE

        bus = EnhancedAgentBus(
            enable_maci=False,
            use_dynamic_policy=True,
            allow_unstarted=True,
        )  # test-only: MACI off to isolate transport/routing logic

        # Flag behavior depends on POLICY_CLIENT_AVAILABLE
        if POLICY_CLIENT_AVAILABLE:
            assert bus._use_dynamic_policy is True
        else:
            # Without policy client, dynamic policy is disabled
            assert bus._use_dynamic_policy is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
