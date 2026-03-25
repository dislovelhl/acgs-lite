"""
ACGS-2 Enhanced Agent Bus Tests - Edge Cases
Constitutional Hash: 608508a9bd224290

Comprehensive test coverage for agent_bus.py - edge cases and error handling.
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
    router._router = router
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
        """Test that degraded mode still validates constitutional hash."""
        mock_processor.process = AsyncMock(side_effect=Exception("Processor failure"))

        # Message with correct hash should pass
        message_valid = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=constitutional_hash,
            metadata={"prevalidated": True},
            tenant_id=None,
        )

        result = await started_agent_bus.send_message(message_valid)
        assert result.is_valid is True

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


class TestInitialization:
    """Test EnhancedAgentBus initialization options."""

    def test_default_initialization(self):
        """Test default initialization with minimal parameters."""
        bus = EnhancedAgentBus()
        assert bus.is_running is False
        assert bus.constitutional_hash == CONSTITUTIONAL_HASH

    def test_initialization_with_custom_redis(self):
        """Test initialization with custom Redis URL."""
        bus = EnhancedAgentBus(redis_url="redis://custom:6380")
        # Should not raise

    def test_initialization_with_dynamic_policy(self):
        """Test initialization with dynamic policy enabled."""
        bus = EnhancedAgentBus(use_dynamic_policy=True, policy_fail_closed=True)
        # Should not raise

    def test_initialization_with_metering_disabled(self):
        """Test initialization with metering explicitly disabled."""
        bus = EnhancedAgentBus(enable_metering=False)
        metrics = bus.get_metrics()
        assert metrics["metering_enabled"] is False


# =============================================================================
# CONSTITUTIONAL HASH VALIDATION TESTS
# =============================================================================
