"""
ACGS-2 Enhanced Agent Bus Tests - Messaging
Constitutional Hash: 608508a9bd224290

Comprehensive test coverage for messaging functionality in agent_bus.py.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from enhanced_agent_bus.agent_bus import (
        EnhancedAgentBus,
        get_agent_bus,
        reset_agent_bus,
    )
    from enhanced_agent_bus.bus.messaging import MessageHandler
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
    from enhanced_agent_bus.agent_bus import EnhancedAgentBus
    from enhanced_agent_bus.bus.messaging import MessageHandler
    from enhanced_agent_bus.models import (
        CONSTITUTIONAL_HASH,
        AgentMessage,
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
    processor.initialize = AsyncMock()
    processor.shutdown = AsyncMock()
    processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))
    processor.get_metrics = MagicMock(return_value={"processed": 0})
    return processor


@pytest.fixture
def mock_registry():
    """Mock agent registry for testing."""
    registry = MagicMock()
    registry.initialize = AsyncMock()
    registry.shutdown = AsyncMock()
    registry.register = MagicMock(return_value=True)
    registry.unregister = MagicMock(return_value=True)
    registry.get = MagicMock(return_value=None)
    return registry


@pytest.fixture
def mock_router():
    """Mock message router for testing."""
    router = MagicMock()
    router.initialize = AsyncMock()
    router.shutdown = AsyncMock()
    router.route = AsyncMock()
    router.route_and_deliver = AsyncMock(return_value=True)
    # Ensure hasattr(router, "_router") returns False so EnhancedAgentBus wraps it
    del router._router
    return router


@pytest.fixture
def mock_validator():
    """Mock validation strategy for testing."""
    validator = MagicMock()
    validator.initialize = AsyncMock()
    validator.shutdown = AsyncMock()
    validator.validate = AsyncMock(return_value=(True, None))
    validator.evaluate_adaptive_governance = AsyncMock(return_value=(True, "Allowed"))
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
        enable_rate_limiting=False,  # Disable rate limiting to avoid Redis dependency
        processor=mock_processor,
        registry_manager=None,  # Or wrap mock_registry if needed
        registry=mock_registry,  # kwargs for RegistryManager
        router=mock_router,
        governance=mock_validator,  # Correct argument name
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


class TestMessageSending:
    """Test message sending functionality."""

    async def test_send_message_success(self, started_agent_bus, sample_message, mock_processor):
        """Test successful message sending."""
        mock_processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        result = await started_agent_bus.send_message(sample_message)
        assert result.is_valid is True

    async def test_send_message_validation_failure(
        self, started_agent_bus, sample_message, mock_processor
    ):
        """Test message sending with validation failure."""
        failed_result = ValidationResult(is_valid=False)
        failed_result.add_error("Validation failed")
        mock_processor.process = AsyncMock(return_value=failed_result)

        result = await started_agent_bus.send_message(sample_message)
        assert result.is_valid is False

    async def test_send_message_increments_metrics(
        self, started_agent_bus, sample_message, mock_processor, mock_router
    ):
        """Test that sending message updates metrics."""
        mock_processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        # Get initial metrics
        initial_metrics = started_agent_bus.get_metrics()

        await started_agent_bus.send_message(sample_message)

        # Verify metrics increment was updated
        updated_metrics = started_agent_bus.get_metrics()
        assert updated_metrics["messages_sent"] == initial_metrics["messages_sent"] + 1
        assert updated_metrics["sent"] == initial_metrics["sent"] + 1

    async def test_send_message_failed_increments_failed_metrics(
        self, started_agent_bus, sample_message, mock_processor
    ):
        """Test that failed message updates failed metrics."""
        failed_result = ValidationResult(is_valid=False)
        mock_processor.process = AsyncMock(return_value=failed_result)
        initial_metrics = started_agent_bus.get_metrics()

        await started_agent_bus.send_message(sample_message)

        updated_metrics = started_agent_bus.get_metrics()
        assert updated_metrics["messages_failed"] == initial_metrics["messages_failed"] + 1


class TestMessageHandlerFallback:
    async def test_fallback_denies_without_explicit_prevalidation(self, sample_message):
        processor = MagicMock()
        processor.process = AsyncMock(side_effect=RuntimeError("processor down"))
        handler = MessageHandler(
            processor=processor,
            router_component=MagicMock(),
            registry_manager=MagicMock(),
            governance=MagicMock(),
            validator=MagicMock(),
            message_queue=MagicMock(),
            deliberation_queue=None,
            metering_manager=MagicMock(),
            kafka_bus=None,
            metrics={},
            config={},
        )

        result = await handler.process_message_with_fallback(sample_message)

        assert result.is_valid is False
        assert result.decision == "DENY"

    async def test_fallback_allows_when_explicitly_prevalidated(self, sample_message):
        processor = MagicMock()
        processor.process = AsyncMock(side_effect=RuntimeError("processor down"))
        sample_message.metadata["prevalidated"] = True
        handler = MessageHandler(
            processor=processor,
            router_component=MagicMock(),
            registry_manager=MagicMock(),
            governance=MagicMock(),
            validator=MagicMock(),
            message_queue=MagicMock(),
            deliberation_queue=None,
            metering_manager=MagicMock(),
            kafka_bus=None,
            metrics={},
            config={},
        )

        result = await handler.process_message_with_fallback(sample_message)

        assert result.is_valid is True
        assert result.decision == "ALLOW"


# =============================================================================
# MULTI-TENANT ISOLATION TESTS (CRITICAL SECURITY)
# =============================================================================


class TestBroadcast:
    """Test broadcast functionality with tenant isolation."""

    async def test_broadcast_to_same_tenant_only(
        self, started_agent_bus, constitutional_hash, mock_processor
    ):
        """Test broadcast only reaches agents in same tenant."""
        mock_processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        # Register agents in different tenants
        await started_agent_bus.register_agent("agent-a1", "worker", [], "tenant-A")
        await started_agent_bus.register_agent("agent-a2", "worker", [], "tenant-A")
        await started_agent_bus.register_agent("agent-b1", "worker", [], "tenant-B")

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="broadcaster",
            to_agent=None,
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "broadcast"},
            priority=Priority.HIGH,
            constitutional_hash=constitutional_hash,
            tenant_id="tenant-A",
        )

        results = await started_agent_bus.broadcast_message(message)

        # Should only include tenant-A agents
        assert "agent-a1" in results
        assert "agent-a2" in results
        assert "agent-b1" not in results

    async def test_broadcast_no_tenant_isolation(
        self, started_agent_bus, constitutional_hash, mock_processor
    ):
        """Test broadcast without tenant only reaches agents without tenant."""
        mock_processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        await started_agent_bus.register_agent("agent-no-tenant", "worker", [], None)
        await started_agent_bus.register_agent("agent-with-tenant", "worker", [], "tenant-A")

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="broadcaster",
            to_agent=None,
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "broadcast"},
            priority=Priority.HIGH,
            constitutional_hash=constitutional_hash,
            tenant_id=None,
        )

        results = await started_agent_bus.broadcast_message(message)

        assert "agent-no-tenant" in results
        assert "agent-with-tenant" not in results


# =============================================================================
# MESSAGE RECEIVING TESTS
# =============================================================================


class TestMessageReceiving:
    """Test message receiving functionality."""

    async def test_receive_message_timeout(self, started_agent_bus):
        """Test receiving message times out when queue is empty."""
        result = await started_agent_bus.receive_message(timeout=0.1)
        assert result is None

    async def test_receive_message_success(
        self, started_agent_bus, sample_message_no_tenant, mock_processor
    ):
        """Test receiving message from queue."""
        mock_processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        # Send message first (will be queued)
        await started_agent_bus.send_message(sample_message_no_tenant)

        # Receive the message
        received = await started_agent_bus.receive_message(timeout=1.0)
        assert received is not None
        assert received.message_id == sample_message_no_tenant.message_id


# =============================================================================
# METRICS TESTS
# =============================================================================
