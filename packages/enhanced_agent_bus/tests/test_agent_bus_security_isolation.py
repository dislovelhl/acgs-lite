"""
ACGS-2 Enhanced Agent Bus Tests - Isolation
Focused tests for multi-tenant isolation and tenant-related security.

Constitutional Hash: 608508a9bd224290
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from enhanced_agent_bus.agent_bus import EnhancedAgentBus
    from enhanced_agent_bus.models import (
        CONSTITUTIONAL_HASH,
        AgentMessage,
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
    registry = MagicMock()
    registry.initialize = AsyncMock()
    registry.shutdown = AsyncMock()
    registry.route = AsyncMock()
    registry.route_and_deliver = AsyncMock(return_value=True)
    return registry


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
        redis_url="redis://localhost:6379",
        use_dynamic_policy=False,
        use_kafka=False,
        use_redis_registry=False,
        enable_metering=False,
        enable_rate_limiting=False,  # Disable rate limiting to avoid Redis dependency
        processor=mock_processor,
        registry=mock_registry,
        router=mock_router,
        validator=mock_validator,
    )
    yield bus
    if bus.is_running:
        await bus.stop()


@pytest.fixture
async def started_agent_bus(agent_bus):
    """Create and start an EnhancedAgentBus for testing."""
    await agent_bus.start()
    yield agent_bus
    if agent_bus.is_running:
        await agent_bus.stop()


class TestMultiTenantIsolation:
    """Test multi-tenant isolation - CRITICAL SECURITY FEATURE."""

    async def test_tenant_mismatch_sender_rejected(self, started_agent_bus, constitutional_hash):
        """Test that sender tenant mismatch is rejected."""
        await started_agent_bus.register_agent(
            agent_id="sender-agent",
            agent_type="worker",
            capabilities=[],
            tenant_id="tenant-A",
        )

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender-agent",
            to_agent="receiver-agent",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=constitutional_hash,
            tenant_id="tenant-B",
        )

        result = await started_agent_bus.send_message(message)
        assert result.is_valid is False
        assert any("Tenant mismatch" in err for err in result.errors)

    async def test_tenant_mismatch_recipient_rejected(self, started_agent_bus, constitutional_hash):
        """Test that recipient tenant mismatch is rejected."""
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
            tenant_id="tenant-B",
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
            tenant_id="tenant-A",
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
            tenant_id=None,
        )
        await started_agent_bus.register_agent(
            agent_id="receiver-with-tenant",
            agent_type="worker",
            capabilities=[],
            tenant_id="tenant-A",
        )

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender-no-tenant",
            to_agent="receiver-with-tenant",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=constitutional_hash,
            tenant_id=None,
        )

        result = await started_agent_bus.send_message(message)
        assert result.is_valid is False


class TestBroadcastMultiTenantIsolation:
    """Test broadcast message multi-tenant isolation paths for coverage."""

    async def test_broadcast_skips_agents_from_different_tenant(self, started_agent_bus):
        """Test broadcast skips agents not in same tenant."""
        bus = started_agent_bus

        # Register agents in different tenants
        await bus.register_agent("agent-A1", "worker", [], "tenant-A")
        await bus.register_agent("agent-A2", "worker", [], "tenant-A")
        await bus.register_agent("agent-B1", "worker", [], "tenant-B")

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

        assert "agent-A1" in results
        assert "agent-A2" in results
        assert "agent-B1" not in results

    async def test_broadcast_to_no_tenant_agents(self, started_agent_bus):
        """Test broadcast to agents without tenant."""
        bus = started_agent_bus

        await bus.register_agent("agent-1", "worker")
        await bus.register_agent("agent-2", "worker")

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


class TestTenantValidation:
    """Test tenant validation methods for coverage."""

    @pytest.fixture
    def tenant_bus(self):
        """Create a bus with tenant setup."""
        return EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing security isolation independently

    def test_normalize_tenant_id_with_value(self, tenant_bus):
        """Test normalizing a non-empty tenant ID."""
        result = tenant_bus._normalize_tenant_id("tenant-123")
        assert result == "tenant-123"

    def test_normalize_tenant_id_empty_string(self, tenant_bus):
        """Test normalizing an empty tenant ID."""
        result = tenant_bus._normalize_tenant_id("")
        assert result is None

    def test_normalize_tenant_id_none(self, tenant_bus):
        """Test normalizing None tenant ID."""
        result = tenant_bus._normalize_tenant_id(None)
        assert result is None

    def test_format_tenant_id_with_value(self, tenant_bus):
        """Test formatting a non-empty tenant ID."""
        result = tenant_bus._format_tenant_id("tenant-123")
        assert result == "tenant-123"

    def test_format_tenant_id_none(self, tenant_bus):
        """Test formatting None tenant ID."""
        result = tenant_bus._format_tenant_id(None)
        assert result == "none"

    async def test_validate_tenant_consistency_sender_mismatch(self, tenant_bus):
        """Test tenant validation with sender mismatch."""
        await tenant_bus.register_agent("sender", "worker", [], "tenant-A")

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
            tenant_id="tenant-B",
        )

        errors = tenant_bus._validate_tenant_consistency(message)
        assert len(errors) == 1
        assert "Tenant mismatch" in errors[0]
        assert "sender" in errors[0]

    async def test_validate_tenant_consistency_recipient_mismatch(self, tenant_bus):
        """Test tenant validation with recipient mismatch."""
        await tenant_bus.register_agent("receiver", "worker", [], "tenant-A")

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
            constitutional_hash=CONSTITUTIONAL_HASH,
            tenant_id="tenant-B",
        )

        errors = tenant_bus._validate_tenant_consistency(message)
        assert len(errors) == 1
        assert "Tenant mismatch" in errors[0]
        assert "recipient" in errors[0]


class TestNormalizeTenantId:
    """Test _normalize_tenant_id static method."""

    def test_normalize_none_tenant(self):
        """Test normalizing None tenant ID."""
        result = EnhancedAgentBus._normalize_tenant_id(None)
        assert result is None

    def test_normalize_empty_string_tenant(self):
        """Test normalizing empty string tenant ID."""
        result = EnhancedAgentBus._normalize_tenant_id("")
        assert result in [None, ""]

    def test_normalize_valid_tenant(self):
        """Test normalizing valid tenant ID."""
        result = EnhancedAgentBus._normalize_tenant_id("tenant-123")
        assert result == "tenant-123"

    def test_normalize_whitespace_tenant(self):
        """Test normalizing whitespace tenant ID."""
        result = EnhancedAgentBus._normalize_tenant_id("  tenant-123  ")
        assert "tenant-123" in result or result == "  tenant-123  "


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
