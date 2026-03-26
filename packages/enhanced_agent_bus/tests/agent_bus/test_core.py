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
    # Required async methods for lifecycle management
    router.initialize = AsyncMock()
    router.shutdown = AsyncMock()
    # Required async method for message routing
    router.route_and_deliver = AsyncMock(return_value=True)
    # Set _router to self so EnhancedAgentBus doesn't wrap it in RouterComponent
    router._router = router
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
        enable_rate_limiting=False,  # Disable rate limiting to avoid Redis dependency
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


class TestLifecycle:
    """Test EnhancedAgentBus lifecycle management."""

    async def test_initial_state_not_running(self, agent_bus):
        """Test that bus starts in non-running state."""
        assert agent_bus.is_running is False

    async def test_start_sets_running_true(self, agent_bus):
        """Test that start() sets running state to True."""
        await agent_bus.start()
        assert agent_bus.is_running is True
        await agent_bus.stop()

    async def test_stop_sets_running_false(self, started_agent_bus):
        """Test that stop() sets running state to False."""
        await started_agent_bus.stop()
        assert started_agent_bus.is_running is False

    async def test_double_start_is_safe(self, agent_bus):
        """Test that calling start() twice is safe (idempotent)."""
        await agent_bus.start()
        await agent_bus.start()  # Should not raise
        assert agent_bus.is_running is True
        await agent_bus.stop()

    async def test_double_stop_is_safe(self, started_agent_bus):
        """Test that calling stop() twice is safe (idempotent)."""
        await started_agent_bus.stop()
        await started_agent_bus.stop()  # Should not raise
        assert started_agent_bus.is_running is False


# =============================================================================
# AGENT REGISTRATION TESTS
# =============================================================================


class TestAgentRegistration:
    """Test agent registration functionality."""

    async def test_register_agent_success(self, agent_bus, constitutional_hash):
        """Test successful agent registration."""
        result = await agent_bus.register_agent(
            agent_id="test-agent-1",
            agent_type="worker",
            capabilities=["process", "analyze"],
            tenant_id="tenant-1",
        )
        assert result is True

    async def test_register_agent_with_constitutional_hash(self, agent_bus, constitutional_hash):
        """Test agent registration includes constitutional hash."""
        await agent_bus.register_agent(
            agent_id="test-agent-2",
            agent_type="worker",
            capabilities=[],
            tenant_id=None,
        )
        info = agent_bus.get_agent_info("test-agent-2")
        assert info is not None
        assert "constitutional_hash" in info
        assert info["constitutional_hash"] == constitutional_hash

    async def test_register_multiple_agents(self, agent_bus):
        """Test registering multiple agents."""
        await agent_bus.register_agent("agent-1", "worker", [], None)
        await agent_bus.register_agent("agent-2", "supervisor", [], None)
        await agent_bus.register_agent("agent-3", "worker", [], None)

        agents = agent_bus.get_registered_agents()
        assert len(agents) == 3
        assert "agent-1" in agents
        assert "agent-2" in agents
        assert "agent-3" in agents

    async def test_unregister_agent_success(self, agent_bus):
        """Test successful agent unregistration."""
        await agent_bus.register_agent("test-agent", "worker", [], None)
        result = await agent_bus.unregister_agent("test-agent")
        assert result is True
        assert "test-agent" not in agent_bus.get_registered_agents()

    async def test_unregister_nonexistent_agent(self, agent_bus):
        """Test unregistering agent that doesn't exist."""
        result = await agent_bus.unregister_agent("nonexistent-agent")
        assert result is False

    async def test_get_agent_info_exists(self, agent_bus):
        """Test getting info for registered agent."""
        await agent_bus.register_agent(
            agent_id="info-agent",
            agent_type="analyzer",
            capabilities=["cap1", "cap2"],
            tenant_id="tenant-x",
        )
        info = agent_bus.get_agent_info("info-agent")
        assert info is not None
        assert info["agent_type"] == "analyzer"
        assert info["capabilities"] == ["cap1", "cap2"]
        assert info["tenant_id"] == "tenant-x"

    async def test_get_agent_info_not_exists(self, agent_bus):
        """Test getting info for non-existent agent."""
        info = agent_bus.get_agent_info("nonexistent")
        assert info is None


# =============================================================================
# AGENT FILTERING TESTS
# =============================================================================


class TestAgentFiltering:
    """Test agent filtering by type and capability."""

    async def test_get_agents_by_type(self, agent_bus):
        """Test filtering agents by type."""
        await agent_bus.register_agent("worker-1", "worker", [], None)
        await agent_bus.register_agent("worker-2", "worker", [], None)
        await agent_bus.register_agent("supervisor-1", "supervisor", [], None)

        workers = agent_bus.get_agents_by_type("worker")
        assert len(workers) == 2
        assert "worker-1" in workers
        assert "worker-2" in workers

    async def test_get_agents_by_type_empty(self, agent_bus):
        """Test filtering by type returns empty for no matches."""
        await agent_bus.register_agent("worker-1", "worker", [], None)

        result = agent_bus.get_agents_by_type("nonexistent_type")
        assert result == []

    async def test_get_agents_by_capability(self, agent_bus):
        """Test filtering agents by capability."""
        await agent_bus.register_agent("agent-1", "worker", ["analyze", "process"], None)
        await agent_bus.register_agent("agent-2", "worker", ["analyze"], None)
        await agent_bus.register_agent("agent-3", "worker", ["export"], None)

        analyzers = agent_bus.get_agents_by_capability("analyze")
        assert len(analyzers) == 2
        assert "agent-1" in analyzers
        assert "agent-2" in analyzers
        assert "agent-3" not in analyzers

    async def test_get_agents_by_capability_empty(self, agent_bus):
        """Test filtering by capability returns empty for no matches."""
        await agent_bus.register_agent("agent-1", "worker", ["analyze"], None)

        result = agent_bus.get_agents_by_capability("nonexistent_cap")
        assert result == []


# =============================================================================
# MESSAGE SENDING TESTS
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
        self, started_agent_bus, sample_message, mock_processor
    ):
        """Test that sending message updates metrics."""
        mock_processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))
        initial_metrics = started_agent_bus.get_metrics()

        await started_agent_bus.send_message(sample_message)

        updated_metrics = started_agent_bus.get_metrics()
        assert updated_metrics["messages_sent"] == initial_metrics["messages_sent"] + 1

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


# =============================================================================
# MULTI-TENANT ISOLATION TESTS (CRITICAL SECURITY)
# =============================================================================


class TestMultiTenantIsolation:
    """Test multi-tenant isolation - CRITICAL SECURITY FEATURE."""

    async def test_tenant_mismatch_sender_rejected(self, started_agent_bus, constitutional_hash):
        """Test that sender tenant mismatch is rejected."""
        # Register sender with different tenant than message
        await started_agent_bus.register_agent(
            agent_id="sender-agent",
            agent_type="worker",
            capabilities=[],
            tenant_id="tenant-A",  # Different from message tenant
        )

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender-agent",
            to_agent="receiver-agent",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=constitutional_hash,
            tenant_id="tenant-B",  # Different tenant!
        )

        result = await started_agent_bus.send_message(message)
        assert result.is_valid is False
        assert any("Tenant mismatch" in err for err in result.errors)

    async def test_tenant_mismatch_recipient_rejected(self, started_agent_bus, constitutional_hash):
        """Test that recipient tenant mismatch is rejected."""
        # Register both agents
        await started_agent_bus.register_agent(
            agent_id="sender-agent",
            agent_type="worker",
            capabilities=[],
            tenant_id="tenant-A",
        )
        await started_agent_bus.register_agent(
            agent_id="receiver-agent",
            agent_type="worker",
            capabilities=[],
            tenant_id="tenant-B",  # Different from message tenant
        )

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender-agent",
            to_agent="receiver-agent",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=constitutional_hash,
            tenant_id="tenant-A",
        )

        result = await started_agent_bus.send_message(message)
        assert result.is_valid is False
        assert any("Tenant mismatch" in err for err in result.errors)

    async def test_tenant_match_accepted(
        self, started_agent_bus, constitutional_hash, mock_processor
    ):
        """Test that matching tenant is accepted."""
        mock_processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        await started_agent_bus.register_agent(
            agent_id="sender-agent",
            agent_type="worker",
            capabilities=[],
            tenant_id="tenant-A",
        )
        await started_agent_bus.register_agent(
            agent_id="receiver-agent",
            agent_type="worker",
            capabilities=[],
            tenant_id="tenant-A",  # Same tenant
        )

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender-agent",
            to_agent="receiver-agent",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=constitutional_hash,
            tenant_id="tenant-A",  # Matching tenant
        )

        result = await started_agent_bus.send_message(message)
        # Should proceed to validation (tenant check passed)
        assert result.is_valid is True

    async def test_no_tenant_agents_isolated(
        self, started_agent_bus, constitutional_hash, mock_processor
    ):
        """Test that agents without tenant are isolated from tenanted agents."""
        mock_processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        await started_agent_bus.register_agent(
            agent_id="sender-no-tenant",
            agent_type="worker",
            capabilities=[],
            tenant_id=None,  # No tenant
        )
        await started_agent_bus.register_agent(
            agent_id="receiver-with-tenant",
            agent_type="worker",
            capabilities=[],
            tenant_id="tenant-A",  # Has tenant
        )

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender-no-tenant",
            to_agent="receiver-with-tenant",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=constitutional_hash,
            tenant_id=None,  # No tenant
        )

        result = await started_agent_bus.send_message(message)
        assert result.is_valid is False


# =============================================================================
# BROADCAST TESTS
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


class TestMetrics:
    """Test metrics collection functionality."""

    async def test_get_metrics_includes_required_fields(self, agent_bus, constitutional_hash):
        """Test that metrics include all required fields."""
        metrics = agent_bus.get_metrics()

        assert "messages_sent" in metrics
        assert "messages_failed" in metrics
        assert "messages_received" in metrics
        assert "registered_agents" in metrics
        assert "queue_size" in metrics
        assert "is_running" in metrics
        assert "constitutional_hash" in metrics
        assert metrics["constitutional_hash"] == constitutional_hash

    async def test_get_metrics_async_includes_circuit_breaker(self, started_agent_bus):
        """Test that async metrics include circuit breaker health."""
        metrics = await started_agent_bus.get_metrics_async()

        assert "circuit_breaker_health" in metrics

    async def test_metrics_track_registered_agents(self, agent_bus):
        """Test that metrics correctly track registered agents count."""
        initial_metrics = agent_bus.get_metrics()
        assert initial_metrics["registered_agents"] == 0

        await agent_bus.register_agent("test-agent-1", "worker", [], None)
        await agent_bus.register_agent("test-agent-2", "worker", [], None)

        updated_metrics = agent_bus.get_metrics()
        assert updated_metrics["registered_agents"] == 2


# =============================================================================
# DEGRADED MODE TESTS
# =============================================================================


class TestDegradedMode:
    """Test degraded mode fallback behavior."""

    async def test_fallback_to_static_validation_on_processor_failure(
        self, started_agent_bus, sample_message_no_tenant, mock_processor
    ):
        """Test fallback to static hash validation when processor fails."""
        mock_processor.process = AsyncMock(side_effect=Exception("Processor failure"))

        result = await started_agent_bus.send_message(sample_message_no_tenant)

        # Should fallback to static validation in DEGRADED mode
        assert result.metadata.get("governance_mode") == "DEGRADED"
        assert "fallback_reason" in result.metadata

    async def test_degraded_mode_still_validates_hash(
        self, started_agent_bus, constitutional_hash, mock_processor
    ):
        """Test degraded mode denies fallback without explicit prevalidation."""
        mock_processor.process = AsyncMock(side_effect=Exception("Processor failure"))

        # Correct hash alone is insufficient without explicit prevalidation metadata.
        message_valid = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=constitutional_hash,
            tenant_id=None,
        )

        result = await started_agent_bus.send_message(message_valid)
        assert result.is_valid is False
        assert "explicit prevalidation" in result.errors[0]

    async def test_degraded_mode_allows_prevalidated_message(
        self, started_agent_bus, constitutional_hash, mock_processor
    ):
        """Test degraded mode allows explicitly prevalidated messages with valid hash."""
        mock_processor.process = AsyncMock(side_effect=Exception("Processor failure"))

        message_valid = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=constitutional_hash,
            tenant_id=None,
            metadata={"prevalidated": True},
        )

        result = await started_agent_bus.send_message(message_valid)
        assert result.is_valid is True
        assert result.metadata.get("governance_mode") == "DEGRADED"

    async def test_degraded_mode_rejects_invalid_hash(self, started_agent_bus, mock_processor):
        """Test that degraded mode rejects invalid constitutional hash."""
        mock_processor.process = AsyncMock(side_effect=Exception("Processor failure"))

        # Message with invalid hash should fail
        message_invalid = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash="invalid_hash_12345",
            tenant_id=None,
        )

        result = await started_agent_bus.send_message(message_invalid)
        assert result.is_valid is False


# =============================================================================
# DI COMPONENT TESTS
# =============================================================================


class TestDIComponents:
    """Test dependency injection and component access."""

    async def test_processor_property(self, agent_bus, mock_processor):
        """Test processor property returns injected processor."""
        assert agent_bus.processor is mock_processor

    async def test_registry_property(self, agent_bus, mock_registry):
        """Test registry property returns injected registry."""
        assert agent_bus.registry is mock_registry

    async def test_router_property(self, agent_bus, mock_router):
        """Test router property returns injected router."""
        assert agent_bus.router is mock_router

    async def test_validator_property(self, agent_bus, mock_validator):
        """Test validator property returns injected validator."""
        assert agent_bus.validator is mock_validator


# =============================================================================
# SINGLETON TESTS
# =============================================================================


class TestSingleton:
    """Test singleton pattern for default agent bus."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_agent_bus()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_agent_bus()

    def test_get_agent_bus_creates_singleton(self):
        """Test that get_agent_bus creates a singleton."""
        bus1 = get_agent_bus()
        bus2 = get_agent_bus()
        assert bus1 is bus2

    def test_reset_agent_bus_clears_singleton(self):
        """Test that reset_agent_bus clears the singleton."""
        bus1 = get_agent_bus()
        reset_agent_bus()
        bus2 = get_agent_bus()
        assert bus1 is not bus2


# =============================================================================
# TENANT HELPER TESTS
# =============================================================================


class TestTenantHelpers:
    """Test tenant helper methods."""

    def test_normalize_tenant_id_none(self):
        """Test normalizing None tenant ID."""
        result = EnhancedAgentBus._normalize_tenant_id(None)
        assert result is None

    def test_normalize_tenant_id_empty_string(self):
        """Test normalizing empty string tenant ID."""
        result = EnhancedAgentBus._normalize_tenant_id("")
        assert result is None

    def test_normalize_tenant_id_value(self):
        """Test normalizing actual tenant ID."""
        result = EnhancedAgentBus._normalize_tenant_id("tenant-123")
        assert result == "tenant-123"

    def test_format_tenant_id_none(self):
        """Test formatting None tenant ID."""
        result = EnhancedAgentBus._format_tenant_id(None)
        assert result == "none"

    def test_format_tenant_id_value(self):
        """Test formatting actual tenant ID."""
        result = EnhancedAgentBus._format_tenant_id("tenant-123")
        assert result == "tenant-123"


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================
