"""
ACGS-2 Registry Extended Coverage Tests
Constitutional Hash: 608508a9bd224290

Extended tests for registry classes.
"""

import pytest

try:
    from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage
    from enhanced_agent_bus.registry import (
        CapabilityBasedRouter,
        DirectMessageRouter,
        InMemoryAgentRegistry,
    )
except ImportError:
    from models import AgentMessage
    from registry import (
        CapabilityBasedRouter,
        DirectMessageRouter,
        InMemoryAgentRegistry,
    )


class TestInMemoryAgentRegistryExtended:
    """Extended tests for InMemoryAgentRegistry."""

    @pytest.fixture
    def registry(self):
        """Create fresh registry for testing."""
        return InMemoryAgentRegistry()

    async def test_list_agents_empty(self, registry):
        """list_agents returns empty list when no agents."""
        agents = await registry.list_agents()
        assert agents == []

    async def test_register_and_list(self, registry):
        """Register agents and list them."""
        await registry.register("agent_a", {"type": "worker"})
        await registry.register("agent_b", {"type": "coordinator"})

        agents = await registry.list_agents()
        assert "agent_a" in agents
        assert "agent_b" in agents

    async def test_get_nonexistent_agent(self, registry):
        """Getting nonexistent agent returns None."""
        result = await registry.get("nonexistent")
        assert result is None

    async def test_unregister_cleans_up(self, registry):
        """Unregistering removes agent completely."""
        await registry.register("temp_agent", {"type": "temp"})
        await registry.unregister("temp_agent")

        result = await registry.get("temp_agent")
        assert result is None

    async def test_update_metadata(self, registry):
        """Update agent metadata updates stored data."""
        await registry.register("update_agent", {"type": "initial"})

        # Update metadata
        await registry.update_metadata("update_agent", {"extra": "data"})

        # Check updated - metadata is stored in 'metadata' key
        info = await registry.get("update_agent")
        assert info is not None
        assert info.get("metadata", {}).get("extra") == "data"

    async def test_exists_method(self, registry):
        """exists method returns correct boolean."""
        assert await registry.exists("nonexistent") is False

        await registry.register("exist_agent", {"type": "test"})
        assert await registry.exists("exist_agent") is True

    async def test_clear_removes_all(self, registry):
        """clear removes all agents."""
        await registry.register("agent_1", {"type": "test"})
        await registry.register("agent_2", {"type": "test"})

        await registry.clear()

        agents = await registry.list_agents()
        assert len(agents) == 0

    def test_agent_count(self, registry):
        """agent_count property returns count."""
        assert registry.agent_count == 0

    async def test_register_duplicate(self, registry):
        """Registering same agent twice fails."""
        result1 = await registry.register("dup_agent", {"type": "test"})
        result2 = await registry.register("dup_agent", {"type": "test"})
        assert result1 is True
        assert result2 is False

    async def test_unregister_nonexistent(self, registry):
        """Unregistering nonexistent agent returns False."""
        result = await registry.unregister("nonexistent")
        assert result is False

    async def test_update_metadata_nonexistent(self, registry):
        """Updating nonexistent agent metadata returns False."""
        result = await registry.update_metadata("nonexistent", {"key": "value"})
        assert result is False


class TestDirectMessageRouter:
    """Tests for DirectMessageRouter."""

    @pytest.fixture
    def registry(self):
        """Create fresh registry for testing."""
        return InMemoryAgentRegistry()

    @pytest.fixture
    def router(self):
        """Create router instance."""
        return DirectMessageRouter()

    async def test_route_to_existing_agent(self, router, registry):
        """Route to existing agent succeeds."""
        # Include tenant_id in metadata to match AgentMessage's default tenant_id
        await registry.register(
            "target_agent", {"type": "worker"}, metadata={"tenant_id": "default"}
        )
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="target_agent",
        )
        result = await router.route(msg, registry)
        assert result == "target_agent"

    async def test_route_to_nonexistent_agent(self, router, registry):
        """Route to nonexistent agent returns None."""
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="nonexistent",
        )
        result = await router.route(msg, registry)
        assert result is None

    async def test_route_with_no_target(self, router, registry):
        """Route with no target returns None."""
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="",
        )
        result = await router.route(msg, registry)
        assert result is None

    async def test_broadcast_excludes_sender(self, router, registry):
        """Broadcast excludes sender."""
        await registry.register("agent_a", {"type": "worker"})
        await registry.register("agent_b", {"type": "worker"})
        await registry.register("sender", {"type": "sender"})

        msg = AgentMessage(
            content={"action": "broadcast"},
            from_agent="sender",
            to_agent="",
        )
        targets = await router.broadcast(msg, registry)
        assert "sender" not in targets
        assert "agent_a" in targets
        assert "agent_b" in targets

    async def test_broadcast_with_exclude(self, router, registry):
        """Broadcast respects exclude list."""
        await registry.register("agent_a", {"type": "worker"})
        await registry.register("agent_b", {"type": "worker"})
        await registry.register("agent_c", {"type": "worker"})

        msg = AgentMessage(
            content={"action": "broadcast"},
            from_agent="sender",
            to_agent="",
        )
        targets = await router.broadcast(msg, registry, exclude=["agent_b"])
        assert "agent_b" not in targets
        assert "agent_a" in targets
        assert "agent_c" in targets

    async def test_route_tenant_mismatch(self, router, registry):
        """Route fails when tenant IDs don't match."""
        # Register agent with tenant_id in metadata
        await registry.register(
            "tenant_agent", {"type": "worker"}, metadata={"tenant_id": "tenant_1"}
        )
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="tenant_agent",
            tenant_id="tenant_2",  # Different tenant
        )
        result = await router.route(msg, registry)
        assert result is None

    async def test_route_tenant_match(self, router, registry):
        """Route succeeds when tenant IDs match."""
        # Register agent with tenant_id in metadata
        await registry.register(
            "tenant_agent", {"type": "worker"}, metadata={"tenant_id": "tenant_1"}
        )
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="tenant_agent",
            tenant_id="tenant_1",
        )
        result = await router.route(msg, registry)
        assert result == "tenant_agent"


class TestCapabilityBasedRouter:
    """Tests for CapabilityBasedRouter."""

    @pytest.fixture
    def registry(self):
        """Create fresh registry for testing."""
        return InMemoryAgentRegistry()

    @pytest.fixture
    def router(self):
        """Create router instance."""
        return CapabilityBasedRouter()

    async def test_route_with_explicit_target(self, router, registry):
        """Route with explicit target goes to that target."""
        await registry.register("target_agent", {"type": "worker"})
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="target_agent",
        )
        result = await router.route(msg, registry)
        assert result == "target_agent"

    async def test_route_by_capabilities(self, router, registry):
        """Route by required capabilities."""
        await registry.register(
            "capable_agent", capabilities={"translate": True, "summarize": True}
        )
        msg = AgentMessage(
            content={
                "action": "test",
                "required_capabilities": ["translate"],
            },
            from_agent="sender",
            to_agent="",
        )
        result = await router.route(msg, registry)
        assert result == "capable_agent"

    async def test_route_no_matching_capabilities(self, router, registry):
        """Route fails when no agent has required capabilities."""
        await registry.register("limited_agent", capabilities={"translate": True})
        msg = AgentMessage(
            content={
                "action": "test",
                "required_capabilities": ["translate", "analyze"],
            },
            from_agent="sender",
            to_agent="",
        )
        result = await router.route(msg, registry)
        assert result is None

    async def test_route_no_capabilities_required(self, router, registry):
        """Route with no required capabilities returns None."""
        await registry.register("any_agent", {"type": "worker"})
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="",
        )
        result = await router.route(msg, registry)
        assert result is None

    async def test_broadcast_with_capabilities(self, router, registry):
        """Broadcast filters by capabilities."""
        await registry.register("capable_a", capabilities={"translate": True})
        await registry.register("capable_b", capabilities={"translate": True, "extra": True})
        await registry.register("incapable", capabilities={"other": True})

        msg = AgentMessage(
            content={
                "action": "broadcast",
                "required_capabilities": ["translate"],
            },
            from_agent="sender",
            to_agent="",
        )
        targets = await router.broadcast(msg, registry)
        assert "capable_a" in targets
        assert "capable_b" in targets
        assert "incapable" not in targets

    async def test_broadcast_no_capabilities_includes_all(self, router, registry):
        """Broadcast with no required capabilities includes all."""
        await registry.register("agent_a", {"type": "worker"})
        await registry.register("agent_b", {"type": "worker"})

        msg = AgentMessage(
            content={"action": "broadcast"},
            from_agent="sender",
            to_agent="",
        )
        targets = await router.broadcast(msg, registry)
        assert "agent_a" in targets
        assert "agent_b" in targets

    async def test_broadcast_excludes_sender_and_list(self, router, registry):
        """Broadcast excludes sender and exclude list."""
        await registry.register("agent_a", capabilities={"cap": True})
        await registry.register("agent_b", capabilities={"cap": True})
        await registry.register("sender", capabilities={"cap": True})

        msg = AgentMessage(
            content={
                "action": "broadcast",
                "required_capabilities": ["cap"],
            },
            from_agent="sender",
            to_agent="",
        )
        targets = await router.broadcast(msg, registry, exclude=["agent_b"])
        assert "sender" not in targets
        assert "agent_b" not in targets
        assert "agent_a" in targets
