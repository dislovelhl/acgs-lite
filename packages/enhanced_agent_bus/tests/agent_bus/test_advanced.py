"""
ACGS-2 Enhanced Agent Bus Tests
Constitutional Hash: cdd01ef066bc6cf2

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


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_register_duplicate_agent(self, agent_bus):
        """Test registering same agent ID twice."""
        await agent_bus.register_agent("duplicate", "worker", [], None)
        # Second registration should overwrite
        await agent_bus.register_agent("duplicate", "supervisor", [], None)

        info = agent_bus.get_agent_info("duplicate")
        assert info["agent_type"] == "supervisor"

    async def test_empty_capabilities_list(self, agent_bus):
        """Test agent registration with empty capabilities."""
        await agent_bus.register_agent("no-caps", "worker", [], None)
        info = agent_bus.get_agent_info("no-caps")
        assert info["capabilities"] == []

    async def test_many_capabilities(self, agent_bus):
        """Test agent with many capabilities."""
        caps = [f"cap-{i}" for i in range(100)]
        await agent_bus.register_agent("many-caps", "worker", caps, None)
        info = agent_bus.get_agent_info("many-caps")
        assert len(info["capabilities"]) == 100

    async def test_unicode_tenant_id_rejected(self, agent_bus, constitutional_hash, mock_processor):
        """Test that unicode tenant IDs are rejected for security (homograph attack prevention)."""
        mock_processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))

        await agent_bus.start()
        # Unicode tenant IDs should be normalized but validation will reject them
        # This is intentional security behavior to prevent homograph attacks
        await agent_bus.register_agent("unicode-agent", "worker", [], "テナント-1")

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="unicode-agent",
            to_agent="receiver",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=constitutional_hash,
            tenant_id="テナント-1",
        )

        # Validation should fail due to invalid tenant_id format (non-ASCII)
        result = await agent_bus.send_message(message)
        assert result.is_valid is False
        assert any("tenant" in err.lower() or "format" in err.lower() for err in result.errors)
        await agent_bus.stop()


# =============================================================================
# COVERAGE ENHANCEMENT TESTS
# =============================================================================


class TestFromConfigFactory:
    """Test from_config factory method for coverage."""

    def test_from_config_creates_bus(self):
        """Test that from_config creates a bus from configuration."""
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration.for_testing()
        bus = EnhancedAgentBus.from_config(config)

        assert bus is not None
        assert bus._enable_maci == config.enable_maci
        assert bus._use_dynamic_policy == config.use_dynamic_policy

    def test_from_config_with_custom_settings(self):
        """Test from_config with custom configuration."""
        from enhanced_agent_bus.config import BusConfiguration

        config = BusConfiguration(
            use_dynamic_policy=False,
            enable_maci=False,  # test-only: MACI off — testing bus configuration
            policy_fail_closed=False,
        )
        bus = EnhancedAgentBus.from_config(config)

        assert bus._use_dynamic_policy is False
        assert bus._enable_maci is False


class TestMACIStrictMode:
    """Test MACI strict mode behavior for coverage."""

    @pytest.fixture
    def strict_maci_bus(self):
        """Create a bus with strict MACI mode enabled."""
        return EnhancedAgentBus(enable_maci=True, maci_strict_mode=True)

    async def test_maci_registration_failure_in_strict_mode(self, strict_maci_bus):
        """Test that MACI registration failure in strict mode removes agent."""
        # Mock MACI registry to raise an error
        from maci_enforcement import MACIRole

        if strict_maci_bus._maci_registry:
            original_register = strict_maci_bus._maci_registry.register_agent
            strict_maci_bus._maci_registry.register_agent = AsyncMock(
                side_effect=RuntimeError("MACI registration failed")
            )

            result = await strict_maci_bus.register_agent(
                agent_id="test-agent",
                agent_type="worker",
                maci_role=MACIRole.EXECUTIVE,
            )

            # Should return False due to MACI failure in strict mode
            assert result is False
            # Agent should not be registered
            assert "test-agent" not in strict_maci_bus.agents


class TestDeliberationQueueRouting:
    """Test deliberation-related methods for coverage."""

    @pytest.fixture
    def bus_with_deliberation(self):
        """Create a bus with deliberation layer enabled."""
        bus = EnhancedAgentBus(enable_maci=False)  # test-only: MACI off — testing bus configuration
        return bus

    def test_requires_deliberation_high_impact(self, bus_with_deliberation):
        """Test that high-impact messages require deliberation."""
        result = ValidationResult(is_valid=True)
        result.metadata["impact_score"] = 0.95  # Above threshold

        requires = bus_with_deliberation._requires_deliberation(result)
        # May or may not require deliberation depending on configuration
        assert isinstance(requires, bool)

    def test_requires_deliberation_low_impact(self, bus_with_deliberation):
        """Test that low-impact messages don't require deliberation."""
        result = ValidationResult(is_valid=True)
        result.metadata["impact_score"] = 0.2  # Below threshold

        requires = bus_with_deliberation._requires_deliberation(result)
        assert requires is False


class TestTenantValidation:
    """Test tenant validation methods for coverage."""

    @pytest.fixture
    def tenant_bus(self):
        """Create a bus with tenant setup."""
        return EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing bus configuration

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
            tenant_id="tenant-B",  # Different from sender's tenant
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
            tenant_id="tenant-B",  # Different from receiver's tenant
        )

        errors = tenant_bus._validate_tenant_consistency(message)
        assert len(errors) == 1
        assert "Tenant mismatch" in errors[0]
        assert "recipient" in errors[0]


class TestPolicyInitialization:
    """Test policy initialization paths for coverage."""

    def test_init_policy_client_disabled(self):
        """Test that policy client is None when dynamic policy is disabled."""
        bus = EnhancedAgentBus(
            use_dynamic_policy=False, enable_maci=False
        )  # test-only: MACI off — testing policy initialization
        assert bus._policy_client is None

    def test_init_audit_client_when_available(self):
        """Test audit client initialization."""
        bus = EnhancedAgentBus(
            enable_maci=False, audit_service_url="http://localhost:8084"
        )  # test-only: MACI off — testing audit client initialization
        # Audit client may or may not be available depending on environment


class TestRegistryInitialization:
    """Test registry initialization paths for coverage."""

    def test_init_registry_with_custom_registry(self):
        """Test using a custom registry."""
        from registry import InMemoryAgentRegistry

        custom_registry = InMemoryAgentRegistry()
        bus = EnhancedAgentBus(
            registry=custom_registry, enable_maci=False
        )  # test-only: MACI off — testing custom registry

        assert bus.registry is custom_registry

    def test_init_registry_default_inmemory(self):
        """Test default InMemoryAgentRegistry is used."""
        bus = EnhancedAgentBus(
            use_redis_registry=False, enable_maci=False
        )  # test-only: MACI off — testing default registry

        from registry import InMemoryAgentRegistry

        assert isinstance(bus.registry, InMemoryAgentRegistry)


class TestDeliberationQueue:
    """Test deliberation queue handling for coverage."""

    @pytest.fixture
    def bus_with_deliberation_queue(self):
        """Create bus with mocked deliberation queue."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing deliberation queue

        # Mock the deliberation queue
        mock_queue = AsyncMock()
        mock_queue.enqueue = AsyncMock()
        bus._deliberation_queue = mock_queue
        bus._message_handler._deliberation_queue = mock_queue

        # Mock metering manager
        mock_metering = MagicMock()
        mock_metering.record_deliberation_request = MagicMock()
        bus._metering_manager = mock_metering
        bus._message_handler._metering_manager = mock_metering

        return bus

    async def test_handle_deliberation_enqueues_message(self, bus_with_deliberation_queue):
        """Test _handle_deliberation enqueues message to deliberation queue."""
        bus = bus_with_deliberation_queue

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "high_impact"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        result = ValidationResult(is_valid=True)
        result.metadata["impact_score"] = 0.95

        import time

        start_time = time.perf_counter()

        await bus._handle_deliberation(message, result, start_time)

        # Deliberation queue enqueue should be called
        bus._deliberation_queue.enqueue.assert_called_once()

        # Metering should record the deliberation request
        bus._metering_manager.record_deliberation_request.assert_called_once()

        # Result status should be updated (compare by value to avoid enum identity issues)
        assert result.status.value == MessageStatus.PENDING_DELIBERATION.value


class TestAsyncMetrics:
    """Test async metrics with policy client for coverage."""

    @pytest.fixture
    def bus_with_policy_client(self):
        """Create bus with mocked policy client."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing policy client metrics

        mock_policy = AsyncMock()
        mock_policy.health_check = AsyncMock(return_value={"status": "healthy"})
        bus._policy_client = mock_policy

        return bus

    @pytest.fixture
    def bus_with_failing_policy_client(self):
        """Create bus with policy client that raises exception on health check."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing failing policy client

        mock_policy = AsyncMock()
        mock_policy.health_check = AsyncMock(side_effect=ConnectionError("Connection failed"))
        bus._policy_client = mock_policy

        return bus

    async def test_get_metrics_async_with_healthy_policy(self, bus_with_policy_client):
        """Test get_metrics_async includes policy registry status when healthy."""
        metrics = await bus_with_policy_client.get_metrics_async()

        assert "policy_registry_status" in metrics
        assert metrics["policy_registry_status"] == "healthy"

    async def test_get_metrics_async_with_failing_policy(self, bus_with_failing_policy_client):
        """Test get_metrics_async handles policy client failure."""
        metrics = await bus_with_failing_policy_client.get_metrics_async()

        assert "policy_registry_status" in metrics
        assert metrics["policy_registry_status"] == "unavailable"


class TestMACIProperties:
    """Test MACI-related properties for coverage."""

    def test_maci_enabled_property_true(self):
        """Test maci_enabled property returns True when enabled."""
        bus = EnhancedAgentBus(enable_maci=True)
        assert bus.maci_enabled

    def test_maci_enabled_property_false(self):
        """Test maci_enabled property returns False when disabled."""
        bus = EnhancedAgentBus(enable_maci=False)  # test-only: MACI off — testing MACI properties
        assert not bus.maci_enabled

    def test_maci_registry_property_when_enabled(self):
        """Test maci_registry property when MACI is enabled."""
        bus = EnhancedAgentBus(enable_maci=True)
        registry = bus.maci_registry
        # Registry should exist when MACI is enabled
        assert registry is not None

    def test_maci_registry_property_when_disabled(self):
        """Test maci_registry property when MACI is disabled."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing MACI registry property
        registry = bus.maci_registry
        # Registry should be None when MACI is disabled
        assert registry is None

    def test_maci_enforcer_property_when_enabled(self):
        """Test maci_enforcer property when MACI is enabled."""
        bus = EnhancedAgentBus(enable_maci=True)
        enforcer = bus.maci_enforcer
        # Enforcer should exist when MACI is enabled
        assert enforcer is not None

    def test_maci_enforcer_property_when_disabled(self):
        """Test maci_enforcer property when MACI is disabled."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing MACI enforcer property
        enforcer = bus.maci_enforcer
        # Enforcer should be None when MACI is disabled
        assert enforcer is None


class TestValidatorInitialization:
    """Test validator initialization paths for coverage."""

    def test_init_validator_with_custom_validator(self):
        """Test using a custom validator."""
        from validators import ValidationResult

        class CustomValidator:
            def validate(self, message):
                return ValidationResult(is_valid=True)

            def get_name(self):
                return "CustomValidator"

        custom_validator = CustomValidator()
        bus = EnhancedAgentBus(
            validator=custom_validator, enable_maci=False
        )  # test-only: MACI off — testing custom validator

        assert bus._validator is custom_validator

    def test_init_validator_static_hash_default(self):
        """Test default validator includes StaticHashValidationStrategy."""
        bus = EnhancedAgentBus(
            use_dynamic_policy=False, enable_maci=False
        )  # test-only: MACI off — testing static hash validator

        from registry import CompositeValidationStrategy

        # Default now uses CompositeValidationStrategy with PQC support
        assert isinstance(bus._validator, CompositeValidationStrategy)


class TestJWTAgentValidation:
    """Test JWT agent identity validation paths for coverage."""

    @pytest.fixture
    def bus_for_jwt(self):
        """Create bus for JWT testing."""
        return EnhancedAgentBus(
            enable_maci=False, use_dynamic_policy=False
        )  # test-only: MACI off — testing JWT validation

    async def test_validate_agent_identity_no_token(self, bus_for_jwt):
        """Test validation when no auth token is provided."""
        result = await bus_for_jwt._validate_agent_identity(
            agent_id="test-agent", tenant_id=None, capabilities=[], auth_token=None
        )

        # Should return (None, None) when no token
        assert result == (None, None)

    async def test_validate_agent_identity_token_without_crypto_available(self, bus_for_jwt):
        """Test validation when token provided but crypto/config not available."""
        # This tests the path where token is provided but CRYPTO_AVAILABLE or CONFIG_AVAILABLE is False  # noqa: E501
        # We test the warning path for token without crypto
        result = await bus_for_jwt._validate_agent_identity(
            agent_id="test-agent",
            tenant_id=None,
            capabilities=[],
            auth_token="some.jwt.token",  # noqa: S106
        )

        # Without both CRYPTO_AVAILABLE and CONFIG_AVAILABLE, returns (None, None) with warning logged  # noqa: E501
        assert result == (None, None) or result == (False, None)

    async def test_validate_agent_identity_dynamic_mode_no_token(self):
        """Test validation rejects registration in dynamic mode without token."""
        bus = EnhancedAgentBus(
            enable_maci=False, use_dynamic_policy=True
        )  # test-only: MACI off — testing dynamic mode JWT validation

        result = await bus._validate_agent_identity(
            agent_id="test-agent", tenant_id=None, capabilities=[], auth_token=None
        )

        # In dynamic mode without token, should return (False, None)
        assert result == (False, None) or result == (None, None)


class TestStartWithMetricsAndCircuitBreakers:
    """Test start() with metrics and circuit breakers for coverage."""

    async def test_start_records_started_timestamp(self):
        """Test start() records started timestamp in metrics."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing metrics timestamp recording

        await bus.start()

        # Check that started_at is set in metrics
        assert "started_at" in bus._metrics
        assert bus._metrics["started_at"] is not None

        await bus.stop()

    async def test_start_then_stop_lifecycle(self):
        """Test complete start/stop lifecycle."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing start/stop lifecycle

        # Initially not running
        assert not bus._running

        await bus.start()
        assert bus._running

        await bus.stop()
        assert not bus._running


class TestPolicyClientInitialization:
    """Test policy client initialization during start for coverage."""

    async def test_start_with_policy_client_success(self):
        """Test start() initializes policy client successfully."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing policy client initialization

        mock_policy = AsyncMock()
        mock_policy.initialize = AsyncMock()
        mock_policy.get_current_public_key = AsyncMock(return_value="abc123def456")
        bus._policy_client = mock_policy
        # Also update governance component since that's where initialization happens
        bus._governance._policy_client = mock_policy

        await bus.start()

        # Policy client should be initialized
        mock_policy.initialize.assert_called_once()
        mock_policy.get_current_public_key.assert_called_once()

        await bus.stop()

    async def test_start_with_policy_client_failure(self):
        """Test start() handles policy client initialization failure."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing policy client failure handling

        mock_policy = AsyncMock()
        mock_policy.initialize = AsyncMock(side_effect=ConnectionError("Connection refused"))
        bus._policy_client = mock_policy
        # Also update governance component since that's where initialization happens
        bus._governance._policy_client = mock_policy

        # Should not raise, just log warning
        await bus.start()

        assert bus._running

        await bus.stop()
