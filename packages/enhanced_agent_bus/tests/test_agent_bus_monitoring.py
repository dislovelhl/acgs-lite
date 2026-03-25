"""
ACGS-2 Enhanced Agent Bus Tests - Monitoring
Constitutional Hash: 608508a9bd224290

Comprehensive test coverage for monitoring functionality in agent_bus.py.
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
    from enhanced_agent_bus.agent_bus import EnhancedAgentBus
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
    return router


@pytest.fixture
def mock_validator():
    """Mock validation strategy for testing."""
    validator = MagicMock()
    validator.initialize = AsyncMock()
    validator.shutdown = AsyncMock()
    validator.validate = AsyncMock(return_value=(True, None))
    return validator


@pytest.fixture
async def agent_bus(mock_processor, mock_registry, mock_router, mock_validator):
    """Create an EnhancedAgentBus for testing."""
    bus = EnhancedAgentBus(
        use_dynamic_policy=False,
        use_kafka=False,
        use_redis_registry=False,
        enable_metering=False,
        enable_rate_limiting=False,
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
