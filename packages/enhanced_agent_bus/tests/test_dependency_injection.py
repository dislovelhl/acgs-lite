"""
ACGS-2 Enhanced Agent Bus - Dependency Injection Tests
Constitutional Hash: 608508a9bd224290

Tests for DI pattern implementation including interfaces, registries, and core integration.
"""

import pytest

from enhanced_agent_bus.agent_bus import EnhancedAgentBus
from enhanced_agent_bus.interfaces import AgentRegistry, MessageRouter, ValidationStrategy
from enhanced_agent_bus.message_processor import MessageProcessor
from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage
from enhanced_agent_bus.registry import (
    CapabilityBasedRouter,
    CompositeValidationStrategy,
    DirectMessageRouter,
    InMemoryAgentRegistry,
    StaticHashValidationStrategy,
)

# ============================================================================
# InMemoryAgentRegistry Tests
# ============================================================================


class TestInMemoryAgentRegistry:
    """Test InMemoryAgentRegistry implementation."""

    @pytest.fixture
    def registry(self):
        """Create a fresh registry for each test."""
        return InMemoryAgentRegistry()

    async def test_register_agent(self, registry):
        """Test agent registration."""
        result = await registry.register(
            "agent-1", capabilities={"search": True}, metadata={"version": "1.0"}
        )
        assert result is True
        assert await registry.exists("agent-1")

    async def test_register_duplicate_returns_false(self, registry):
        """Test duplicate registration returns False."""
        await registry.register("agent-1")
        result = await registry.register("agent-1")
        assert result is False

    async def test_unregister_agent(self, registry):
        """Test agent unregistration."""
        await registry.register("agent-1")
        result = await registry.unregister("agent-1")
        assert result is True
        assert not await registry.exists("agent-1")

    async def test_unregister_nonexistent_returns_false(self, registry):
        """Test unregistering nonexistent agent returns False."""
        result = await registry.unregister("nonexistent")
        assert result is False

    async def test_get_agent(self, registry):
        """Test getting agent info."""
        await registry.register(
            "agent-1", capabilities={"search": True}, metadata={"version": "1.0"}
        )
        info = await registry.get("agent-1")

        assert info is not None
        assert info["agent_id"] == "agent-1"
        assert info["capabilities"] == {"search": True}
        assert info["metadata"]["version"] == "1.0"
        assert info["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_nonexistent_returns_none(self, registry):
        """Test getting nonexistent agent returns None."""
        info = await registry.get("nonexistent")
        assert info is None

    async def test_list_agents(self, registry):
        """Test listing all agents."""
        await registry.register("agent-1")
        await registry.register("agent-2")
        await registry.register("agent-3")

        agents = await registry.list_agents()
        assert len(agents) == 3
        assert "agent-1" in agents
        assert "agent-2" in agents
        assert "agent-3" in agents

    async def test_update_metadata(self, registry):
        """Test updating agent metadata."""
        await registry.register("agent-1", metadata={"version": "1.0"})
        result = await registry.update_metadata("agent-1", {"status": "active"})

        assert result is True
        info = await registry.get("agent-1")
        assert info["metadata"]["version"] == "1.0"
        assert info["metadata"]["status"] == "active"

    async def test_update_metadata_nonexistent_returns_false(self, registry):
        """Test updating nonexistent agent returns False."""
        result = await registry.update_metadata("nonexistent", {"key": "value"})
        assert result is False

    async def test_clear(self, registry):
        """Test clearing all agents."""
        await registry.register("agent-1")
        await registry.register("agent-2")
        await registry.clear()

        agents = await registry.list_agents()
        assert len(agents) == 0

    def test_agent_count(self, registry):
        """Test agent count property."""
        assert registry.agent_count == 0


# ============================================================================
# DirectMessageRouter Tests
# ============================================================================


class TestDirectMessageRouter:
    """Test DirectMessageRouter implementation."""

    @pytest.fixture
    def router(self):
        """Create a fresh router for each test."""
        return DirectMessageRouter()

    @pytest.fixture
    def registry(self):
        """Create a registry with some agents."""
        return InMemoryAgentRegistry()

    async def test_route_to_existing_agent(self, router, registry):
        """Test routing to an existing agent."""
        # Register with tenant_id in metadata to match message's default tenant_id
        await registry.register("target-agent", metadata={"tenant_id": "default"})

        message = AgentMessage(to_agent="target-agent")
        target = await router.route(message, registry)

        assert target == "target-agent"

    async def test_route_to_nonexistent_agent(self, router, registry):
        """Test routing to a nonexistent agent returns None."""
        message = AgentMessage(to_agent="nonexistent")
        target = await router.route(message, registry)

        assert target is None

    async def test_route_without_target(self, router, registry):
        """Test routing without target returns None."""
        message = AgentMessage(to_agent="")
        target = await router.route(message, registry)

        assert target is None

    async def test_broadcast_excludes_sender(self, router, registry):
        """Test broadcast excludes the sender."""
        await registry.register("sender")
        await registry.register("agent-1")
        await registry.register("agent-2")

        message = AgentMessage(from_agent="sender")
        targets = await router.broadcast(message, registry)

        assert "sender" not in targets
        assert "agent-1" in targets
        assert "agent-2" in targets

    async def test_broadcast_with_exclude_list(self, router, registry):
        """Test broadcast with explicit exclude list."""
        await registry.register("agent-1")
        await registry.register("agent-2")
        await registry.register("agent-3")

        message = AgentMessage()
        targets = await router.broadcast(message, registry, exclude=["agent-2"])

        assert "agent-1" in targets
        assert "agent-2" not in targets
        assert "agent-3" in targets


# ============================================================================
# CapabilityBasedRouter Tests
# ============================================================================


class TestCapabilityBasedRouter:
    """Test CapabilityBasedRouter implementation."""

    @pytest.fixture
    def router(self):
        """Create a fresh capability router."""
        return CapabilityBasedRouter()

    @pytest.fixture
    def registry(self):
        """Create a registry with agents having different capabilities."""
        return InMemoryAgentRegistry()

    async def test_route_by_capability(self, router, registry):
        """Test routing based on required capabilities."""
        await registry.register("agent-1", capabilities={"search": True})
        await registry.register("agent-2", capabilities={"compute": True})

        message = AgentMessage(content={"required_capabilities": ["search"]})
        target = await router.route(message, registry)

        assert target == "agent-1"

    async def test_route_explicit_target_takes_precedence(self, router, registry):
        """Test that explicit target takes precedence over capabilities."""
        await registry.register("agent-1", capabilities={"search": True})
        await registry.register("agent-2", capabilities={"compute": True})

        message = AgentMessage(to_agent="agent-2", content={"required_capabilities": ["search"]})
        target = await router.route(message, registry)

        assert target == "agent-2"


# ============================================================================
class TestStaticHashValidationStrategy:
    """Test StaticHashValidationStrategy implementation."""

    @pytest.fixture
    def validator(self):
        """Create a fresh validator."""
        return StaticHashValidationStrategy()

    @pytest.fixture
    def strict_validator(self):
        """Create a strict validator."""
        return StaticHashValidationStrategy(strict=True)

    async def test_validate_valid_message(self, validator):
        """Test validating a valid message."""
        message = AgentMessage(content={"action": "test"})
        is_valid, error = await validator.validate(message)

        assert is_valid is True
        assert error is None

    async def test_validate_strict_mode_valid_hash(self, strict_validator):
        """Test strict validation with correct hash."""
        message = AgentMessage(content={"action": "test"}, constitutional_hash=CONSTITUTIONAL_HASH)
        is_valid, _error = await strict_validator.validate(message)

        assert is_valid is True

    async def test_validate_strict_mode_invalid_hash(self, strict_validator):
        """Test strict validation rejects invalid hash."""
        message = AgentMessage(content={"action": "test"})
        message.constitutional_hash = "invalid_hash"

        is_valid, error = await strict_validator.validate(message)

        assert is_valid is False
        assert "Constitutional hash mismatch" in error


# ============================================================================
# CompositeValidationStrategy Tests
# ============================================================================


class TestCompositeValidationStrategy:
    """Test CompositeValidationStrategy implementation."""

    async def test_validate_all_pass(self):
        """Test composite validation with all strategies passing."""
        composite = CompositeValidationStrategy([StaticHashValidationStrategy()])

        message = AgentMessage(content={"action": "test"})
        is_valid, error = await composite.validate(message)

        assert is_valid is True
        assert error is None

    async def test_add_strategy(self):
        """Test adding a strategy dynamically."""
        composite = CompositeValidationStrategy()
        composite.add_strategy(StaticHashValidationStrategy())

        message = AgentMessage(content={"action": "test"})
        is_valid, _ = await composite.validate(message)

        assert is_valid is True


# ============================================================================
# EnhancedAgentBus DI Integration Tests
# ============================================================================


class TestEnhancedAgentBusDI:
    """Test EnhancedAgentBus with dependency injection."""

    async def test_default_dependencies(self):
        """Test bus initializes with default dependencies."""
        bus = EnhancedAgentBus()

        assert isinstance(bus.registry, InMemoryAgentRegistry)
        assert isinstance(bus.router, DirectMessageRouter)
        # Bus now uses CompositeValidationStrategy with PQC support by default
        assert isinstance(bus.validator, CompositeValidationStrategy)

    async def test_custom_registry_injection(self):
        """Test injecting a custom registry."""
        custom_registry = InMemoryAgentRegistry()
        await custom_registry.register("pre-registered-agent")

        bus = EnhancedAgentBus(registry=custom_registry)

        # Verify the injected registry is used
        assert bus.registry is custom_registry
        assert await bus.registry.exists("pre-registered-agent")

    async def test_custom_router_injection(self):
        """Test injecting a custom router."""
        custom_router = CapabilityBasedRouter()
        bus = EnhancedAgentBus(router=custom_router)

        assert bus.router is custom_router

    async def test_custom_validator_injection(self):
        """Test injecting a custom validator."""
        custom_validator = StaticHashValidationStrategy(strict=True)
        bus = EnhancedAgentBus(validator=custom_validator)

        assert bus.validator is custom_validator

    async def test_custom_processor_injection(self):
        """Test injecting a custom message processor."""
        custom_processor = MessageProcessor()
        bus = EnhancedAgentBus(processor=custom_processor)

        assert bus.processor is custom_processor

    async def test_backward_compatibility(self):
        """Test that existing code without DI still works."""
        # Old-style initialization (backward compatible)
        bus = EnhancedAgentBus()
        await bus.start()

        # Old-style agent registration still works
        result = await bus.register_agent(
            "test-agent", agent_type="worker", capabilities=["search"]
        )
        assert result is True

        # Old-style get_registered_agents still works
        agents = bus.get_registered_agents()
        assert "test-agent" in agents

        await bus.stop()

    async def test_full_di_workflow(self):
        """Test complete workflow with injected dependencies."""
        # Create custom implementations
        registry = InMemoryAgentRegistry()
        router = DirectMessageRouter()
        validator = StaticHashValidationStrategy()

        # Inject into bus
        bus = EnhancedAgentBus(registry=registry, router=router, validator=validator)

        await bus.start()

        # Register agent through bus (should use injected registry internally)
        await bus.register_agent("agent-1", capabilities=["compute"])

        # Verify agent exists in injected registry
        assert await registry.exists("agent-1") is True  # Registry is now correctly engaged

        # But legacy interface works
        assert "agent-1" in bus.get_registered_agents()

        await bus.stop()


# ============================================================================
# Protocol Compliance Tests
# ============================================================================


class TestProtocolCompliance:
    """Test that implementations comply with protocols."""

    def test_registry_protocol_compliance(self):
        """Test InMemoryAgentRegistry implements AgentRegistry protocol."""
        registry = InMemoryAgentRegistry()
        assert isinstance(registry, AgentRegistry)

    def test_router_protocol_compliance(self):
        """Test routers implement MessageRouter protocol."""
        direct_router = DirectMessageRouter()
        capability_router = CapabilityBasedRouter()

        assert isinstance(direct_router, MessageRouter)
        assert isinstance(capability_router, MessageRouter)

    def test_validator_protocol_compliance(self):
        """Test validators implement ValidationStrategy protocol."""
        const_validator = StaticHashValidationStrategy()
        composite_validator = CompositeValidationStrategy()

        assert isinstance(const_validator, ValidationStrategy)
        assert isinstance(composite_validator, ValidationStrategy)
