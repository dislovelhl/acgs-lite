"""
ACGS-2 Enhanced Agent Bus Tests - Agent Management
Constitutional Hash: 608508a9bd224290

Comprehensive test coverage for agent_bus.py - the core EnhancedAgentBus class.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

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


class TestAgentRegistration:
    """Test agent registration functionality."""

    __test__ = False

    def __init__(self, constitutional_hash: str | None = None) -> None:
        self._constitutional_hash = constitutional_hash or CONSTITUTIONAL_HASH

    def process(self, input_value: str | None) -> str | None:
        """Validate and normalize input."""
        if input_value is None or not isinstance(input_value, str):
            return None
        return input_value

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
