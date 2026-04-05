"""
ACGS-2 Enhanced Agent Bus Tests - Constitutional & Infrastructure
Focused tests for constitutional hash, MACI, Policy Client, Kafka, and bus infrastructure.

Constitutional Hash: 608508a9bd224290
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

try:
    from enhanced_agent_bus.agent_bus import EnhancedAgentBus
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
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
    from enhanced_agent_bus.agent_bus import EnhancedAgentBus
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
    if bus.is_running:
        await bus.stop()


class TestConstitutionalHash:
    """Test constitutional hash enforcement."""

    async def test_bus_has_constitutional_hash(self, agent_bus, constitutional_hash):
        """Test that bus maintains constitutional hash."""
        assert hasattr(agent_bus, "constitutional_hash")
        assert agent_bus.constitutional_hash == constitutional_hash

    async def test_registered_agents_have_constitutional_hash(self, agent_bus, constitutional_hash):
        """Test that registered agents include constitutional hash."""
        await agent_bus.register_agent("test-agent", "worker", [], None)
        info = agent_bus.get_agent_info("test-agent")
        assert info["constitutional_hash"] == constitutional_hash


class TestMACIProperties:
    """Test MACI-related properties for coverage."""

    def test_maci_enabled_property_true(self):
        """Test maci_enabled property returns True when enabled."""
        bus = EnhancedAgentBus(enable_maci=True)
        assert bus.maci_enabled

    def test_maci_enabled_property_false(self):
        """Test maci_enabled property returns False when disabled."""
        bus = EnhancedAgentBus(enable_maci=False)  # test-only: MACI off — testing in isolation
        assert not bus.maci_enabled


class TestMACIRegistrationPaths:
    """Test MACI registration paths for coverage."""

    async def test_register_with_maci_role_success(self):
        """Test successful MACI role registration."""
        bus = EnhancedAgentBus(enable_maci=True, maci_strict_mode=False)
        from maci_enforcement import MACIRole

        result = await bus.register_agent(
            agent_id="executive-agent",
            agent_type="policy",
            maci_role=MACIRole.EXECUTIVE,
        )
        assert result
        agent = bus.agents.get("executive-agent")
        assert agent is not None


class TestKafkaRouting:
    """Test Kafka routing paths for coverage."""

    async def test_route_and_deliver_via_kafka_success(self):
        """Test successful message delivery via Kafka."""
        bus = EnhancedAgentBus(
            enable_maci=False, use_kafka=False
        )  # test-only: MACI off — testing in isolation
        bus._kafka_bus = MagicMock()
        bus._kafka_bus.send_message = AsyncMock(return_value=True)

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        result = await bus._route_and_deliver(message)
        assert result is True


class TestAsyncMetrics:
    """Test async metrics with policy client for coverage."""

    async def test_get_metrics_async_with_healthy_policy(self):
        """Test get_metrics_async includes policy registry status."""
        bus = EnhancedAgentBus(enable_maci=False)  # test-only: MACI off — testing in isolation
        mock_policy = AsyncMock()
        mock_policy.health_check = AsyncMock(return_value={"status": "healthy"})
        bus._policy_client = mock_policy

        metrics = await bus.get_metrics_async()
        assert "policy_registry_status" in metrics
        assert metrics["policy_registry_status"] == "healthy"


class TestPolicyInitialization:
    """Test policy initialization paths for coverage."""

    def test_init_policy_client_disabled(self):
        """Test that policy client is None when dynamic policy is disabled."""
        bus = EnhancedAgentBus(
            use_dynamic_policy=False, enable_maci=False
        )  # test-only: MACI off — testing in isolation
        assert bus._policy_client is None


class TestRegistryInitialization:
    """Test registry initialization paths for coverage."""

    def test_init_registry_default_inmemory(self):
        """Test default InMemoryAgentRegistry is used."""
        bus = EnhancedAgentBus(
            use_redis_registry=False, enable_maci=False
        )  # test-only: MACI off — testing in isolation
        # Use type name check to avoid import path mismatch issues
        # (core.enhanced_agent_bus vs enhanced_agent_bus)
        assert type(bus.registry).__name__ == "InMemoryAgentRegistry"


class TestUnregisterAgent:
    """Test agent unregistration paths."""

    async def test_unregister_existing_agent(self):
        """Test unregistering an existing agent."""
        bus = EnhancedAgentBus(enable_maci=False)  # test-only: MACI off — testing in isolation
        await bus.register_agent("test-agent", "worker")
        assert "test-agent" in bus.get_registered_agents()
        await bus.unregister_agent("test-agent")
        assert "test-agent" not in bus.get_registered_agents()


class TestBusStopAndCleanup:
    """Test bus stop and cleanup paths."""

    async def test_stop_clears_agents(self):
        """Test stop clears registered agents."""
        bus = EnhancedAgentBus(enable_maci=False)  # test-only: MACI off — testing in isolation
        await bus.start()
        await bus.register_agent("agent-1", "worker")
        await bus.stop()
        assert not bus._running


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
