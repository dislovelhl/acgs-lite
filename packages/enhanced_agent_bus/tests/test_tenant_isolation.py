"""
Module.

Constitutional Hash: 608508a9bd224290
"""

from enhanced_agent_bus.agent_bus import EnhancedAgentBus
from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage, MessageType
from enhanced_agent_bus.registry import DirectMessageRouter, InMemoryAgentRegistry


class TestTenantIsolation:
    """Tests for tenant isolation in routing and delivery."""

    async def test_send_message_denies_cross_tenant_recipient(self):
        bus = EnhancedAgentBus(allow_unstarted=True)
        await bus.register_agent("sender", "worker", tenant_id="tenant_A")
        await bus.register_agent("receiver", "worker", tenant_id="tenant_B")

        message = AgentMessage(
            message_type=MessageType.COMMAND,
            content={"command": "execute"},
            from_agent="sender",
            to_agent="receiver",
            tenant_id="tenant_A",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        result = await bus.send_message(message)

        assert not result.is_valid
        assert any("recipient tenant_id 'tenant_b'" in error.lower() for error in result.errors)

    async def test_send_message_denies_missing_message_tenant_for_sender(self):
        bus = EnhancedAgentBus(allow_unstarted=True)
        await bus.register_agent("sender", "worker", tenant_id="tenant_A")
        await bus.register_agent("receiver", "worker", tenant_id="tenant_A")

        message = AgentMessage(
            message_type=MessageType.COMMAND,
            content={"command": "execute"},
            from_agent="sender",
            to_agent="receiver",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        result = await bus.send_message(message)

        assert not result.is_valid
        assert any("sender tenant_id 'tenant_a'" in error.lower() for error in result.errors)

    async def test_direct_message_router_denies_cross_tenant(self):
        registry = InMemoryAgentRegistry()
        await registry.register(
            "agent_B",
            metadata={"tenant_id": "tenant_B"},
        )

        message = AgentMessage(
            message_type=MessageType.NOTIFICATION,
            content={"alert": True},
            from_agent="agent_A",
            to_agent="agent_B",
            tenant_id="tenant_A",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        router = DirectMessageRouter()
        route = await router.route(message, registry)

        assert route is None

    async def test_direct_message_router_allows_same_tenant(self):
        registry = InMemoryAgentRegistry()
        await registry.register(
            "agent_A",
            metadata={"tenant_id": "tenant_A"},
        )

        message = AgentMessage(
            message_type=MessageType.NOTIFICATION,
            content={"alert": True},
            from_agent="agent_A",
            to_agent="agent_A",
            tenant_id="tenant_A",
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        router = DirectMessageRouter()
        route = await router.route(message, registry)

        assert route == "agent_A"
