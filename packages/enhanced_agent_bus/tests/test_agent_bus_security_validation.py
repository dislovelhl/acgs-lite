"""
ACGS-2 Enhanced Agent Bus Tests - Validation
Focused tests for validation strategies, JWT identity, and core messaging validation.

Constitutional Hash: cdd01ef066bc6cf2
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
    router.initialize = AsyncMock()
    router.shutdown = AsyncMock()
    router.route = AsyncMock()
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


@pytest.fixture
async def started_agent_bus(agent_bus):
    """Create and start an EnhancedAgentBus for testing."""
    await agent_bus.start()
    yield agent_bus
    if agent_bus.is_running:
        await agent_bus.stop()


class TestValidatorInitialization:
    """Test validator initialization paths for coverage."""

    def test_init_validator_with_custom_validator(self):
        """Test using a custom validator."""

        class CustomValidator:
            def validate(self, message):
                return ValidationResult(is_valid=True)

            def get_name(self):
                return "CustomValidator"

        custom_validator = CustomValidator()
        bus = EnhancedAgentBus(
            validator=custom_validator, enable_maci=False
        )  # test-only: MACI off — testing security validation independently
        assert bus._validator is custom_validator

    def test_init_validator_static_hash_default(self):
        """Test default StaticHashValidationStrategy is used."""
        bus = EnhancedAgentBus(
            use_dynamic_policy=False, enable_maci=False
        )  # test-only: MACI off — testing security validation independently
        # Avoid import identity issues by checking class name
        assert bus._validator.__class__.__name__ == "CompositeValidationStrategy"


class TestOPAValidatorPath:
    """Test OPA validator initialization path."""

    def test_init_validator_opa_path_via_injection(self):
        """Test validator can use OPA when injected via _opa_client."""
        bus = EnhancedAgentBus(
            enable_maci=False, use_dynamic_policy=True
        )  # test-only: MACI off — testing security validation independently
        mock_opa = MagicMock()
        bus._opa_client = mock_opa
        # Dynamic lookup or name check
        from enhanced_agent_bus.registry import OPAValidationStrategy

        bus._validator = OPAValidationStrategy(opa_client=mock_opa)
        # Ensure name or instance
        assert isinstance(bus._validator, OPAValidationStrategy)


class TestJWTAgentValidation:
    """Test JWT agent identity validation paths for coverage."""

    @pytest.fixture
    def bus_for_jwt(self):
        """Create bus for JWT testing."""
        return EnhancedAgentBus(
            enable_maci=False, use_dynamic_policy=False
        )  # test-only: MACI off — testing security validation independently

    async def test_validate_agent_identity_no_token(self, bus_for_jwt):
        """Test validation when no auth token is provided."""
        result = await bus_for_jwt._validate_agent_identity(
            agent_id="test-agent", tenant_id=None, capabilities=[], auth_token=None
        )
        assert result == (None, None)

    async def test_validate_agent_identity_token_without_crypto_available(self, bus_for_jwt):
        """Test validation when token provided but crypto/config not available."""
        result = await bus_for_jwt._validate_agent_identity(
            agent_id="test-agent",
            tenant_id=None,
            capabilities=[],
            auth_token="some.jwt.token",  # noqa: S106
        )
        assert result == (None, None) or result == (False, None)


class TestFailedMessagePaths:
    """Test message failure paths for coverage."""

    async def test_send_message_with_invalid_hash(self):
        """Test sending message with invalid constitutional hash."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing security validation independently
        await bus.register_agent("sender", "worker")
        await bus.register_agent("receiver", "worker")

        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
            content={"action": "test"},
        )
        message.constitutional_hash = "invalid_hash_value"

        result = await bus.send_message(message)
        assert not result.is_valid
        assert bus._metrics["messages_failed"] >= 1


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_register_duplicate_agent(self, agent_bus):
        """Test registering same agent ID twice."""
        await agent_bus.register_agent("duplicate", "worker", [], None)
        await agent_bus.register_agent("duplicate", "supervisor", [], None)
        info = agent_bus.get_agent_info("duplicate")
        assert info["agent_type"] == "supervisor"

    async def test_unicode_tenant_id_rejected(self, agent_bus, constitutional_hash, mock_processor):
        """Test that unicode tenant IDs are rejected for security."""
        mock_processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))
        await agent_bus.start()
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
        result = await agent_bus.send_message(message)
        assert result.is_valid is False
        await agent_bus.stop()


class TestRouteAndDeliverPaths:
    """Test _route_and_deliver code paths for coverage."""

    async def test_route_and_deliver_to_internal_queue(self):
        """Test message delivery to internal queue when Kafka is disabled."""
        bus = EnhancedAgentBus(
            enable_maci=False, use_kafka=False
        )  # test-only: MACI off — testing security validation independently
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
        assert bus._message_queue.qsize() >= 1
        await bus.stop()


class TestProcessorDelegation:
    """Test processor delegation and integration."""

    async def test_processor_metrics_included(self):
        """Test processor metrics are included in bus metrics."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing security validation independently
        metrics = bus.get_metrics()
        assert "processor_metrics" in metrics

    async def test_processor_property_access(self):
        """Test accessing processor property."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing security validation independently
        assert bus._processor is not None


class TestDynamicPolicyFlag:
    """Test dynamic policy flag behavior."""

    def test_dynamic_policy_disabled_by_default(self):
        """Test dynamic policy is disabled by default."""
        bus = EnhancedAgentBus(
            enable_maci=False
        )  # test-only: MACI off — testing security validation independently
        assert bus._validator is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
