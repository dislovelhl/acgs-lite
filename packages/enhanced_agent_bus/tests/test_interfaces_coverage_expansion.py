"""
ACGS-2 Interface Protocol Coverage Expansion Tests
Constitutional Hash: 608508a9bd224290

Additional comprehensive tests for protocol interface definitions in interfaces.py.
Tests mock implementations, isinstance checks, and async functional behavior.
"""

from typing import Any, Optional

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.types import JSONDict

try:
    from enhanced_agent_bus import interfaces
    from enhanced_agent_bus.interfaces import (
        AgentRegistry,
        MessageHandler,
        MessageRouter,
        MetricsCollector,
        ProcessingStrategy,
        ValidationStrategy,
    )
    from enhanced_agent_bus.models import AgentMessage, MessageType
except ImportError:
    import interfaces
    from interfaces import (
        AgentRegistry,
        MessageHandler,
        MessageRouter,
        MetricsCollector,
        ProcessingStrategy,
        ValidationStrategy,
    )
    from models import AgentMessage, MessageType

# ============================================================================
# Mock implementations for testing protocol runtime checking
# ============================================================================


class MockAgentRegistry:
    """Mock implementation of AgentRegistry protocol."""

    def __init__(self):
        self._agents: dict[str, JSONDict] = {}

    async def register(
        self,
        agent_id: str,
        capabilities: JSONDict | None = None,
        metadata: JSONDict | None = None,
    ) -> bool:
        if agent_id in self._agents:
            return False
        self._agents[agent_id] = {
            "capabilities": capabilities or {},
            "metadata": metadata or {},
        }
        return True

    async def unregister(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        return True

    async def get(self, agent_id: str) -> JSONDict | None:
        return self._agents.get(agent_id)

    async def list_agents(self) -> list[str]:
        return list(self._agents.keys())

    async def exists(self, agent_id: str) -> bool:
        return agent_id in self._agents

    async def update_metadata(self, agent_id: str, metadata: JSONDict) -> bool:
        if agent_id not in self._agents:
            return False
        self._agents[agent_id]["metadata"].update(metadata)
        return True


class MockMessageRouter:
    """Mock implementation of MessageRouter protocol."""

    async def route(self, message: AgentMessage, registry: AgentRegistry) -> str | None:
        return message.to_agent

    async def broadcast(
        self,
        message: AgentMessage,
        registry: AgentRegistry,
        exclude: list[str] | None = None,
    ) -> list[str]:
        agents = await registry.list_agents()
        exclude_set = set(exclude or [])
        return [a for a in agents if a not in exclude_set]


class MockValidationStrategy:
    """Mock implementation of ValidationStrategy protocol."""

    async def validate(self, message: AgentMessage) -> tuple[bool, str | None]:
        if not message.content:
            return False, "Empty content"
        return True, None


class MockProcessingStrategy:
    """Mock implementation of ProcessingStrategy protocol."""

    def __init__(self, available: bool = True, name: str = "mock"):
        self._available = available
        self._name = name

    async def process(self, message: AgentMessage, handlers: dict[object, list[Any]]) -> Any:
        return {"is_valid": True, "message": "processed"}

    def is_available(self) -> bool:
        return self._available

    def get_name(self) -> str:
        return self._name


class MockMessageHandler:
    """Mock implementation of MessageHandler protocol."""

    def __init__(self, message_types: list[str] | None = None):
        # MessageType enum values are lowercase: "command", "query", etc.
        self._message_types = message_types or ["command"]

    async def handle(self, message: AgentMessage) -> AgentMessage | None:
        return AgentMessage(
            content=f"Handled: {message.content}",
            from_agent=message.to_agent,
            to_agent=message.from_agent,
        )

    def can_handle(self, message: AgentMessage) -> bool:
        return message.message_type.value in self._message_types


class MockMetricsCollector:
    """Mock implementation of MetricsCollector protocol."""

    def __init__(self):
        self._messages_processed = 0
        self._agents_registered = 0
        self._agents_unregistered = 0
        self._total_duration_ms = 0.0

    def record_message_processed(
        self, message_type: str, duration_ms: float, success: bool
    ) -> None:
        self._messages_processed += 1
        self._total_duration_ms += duration_ms

    def record_agent_registered(self, agent_id: str) -> None:
        self._agents_registered += 1

    def record_agent_unregistered(self, agent_id: str) -> None:
        self._agents_unregistered += 1

    def get_metrics(self) -> JSONDict:
        return {
            "messages_processed": self._messages_processed,
            "agents_registered": self._agents_registered,
            "agents_unregistered": self._agents_unregistered,
            "total_duration_ms": self._total_duration_ms,
        }


# Incomplete implementations for negative testing
class IncompleteRegistry:
    """Incomplete AgentRegistry - missing some methods."""

    async def register(self, agent_id: str, **kwargs) -> bool:
        return True


class IncompleteRouter:
    """Incomplete MessageRouter - missing broadcast."""

    async def route(self, message, registry):
        return None


# ============================================================================
# Test Classes
# ============================================================================


class TestAgentRegistryIsinstance:
    """Tests for AgentRegistry isinstance checks."""

    def test_mock_implementation_isinstance(self):
        """Mock implementation passes isinstance check."""
        mock = MockAgentRegistry()
        assert isinstance(mock, AgentRegistry)

    def test_incomplete_implementation_not_isinstance(self):
        """Incomplete implementation fails isinstance check."""
        incomplete = IncompleteRegistry()
        # Should fail because missing methods
        assert not isinstance(incomplete, AgentRegistry)


class TestMessageRouterIsinstance:
    """Tests for MessageRouter isinstance checks."""

    def test_mock_implementation_isinstance(self):
        """Mock implementation passes isinstance check."""
        mock = MockMessageRouter()
        assert isinstance(mock, MessageRouter)

    def test_incomplete_implementation_not_isinstance(self):
        """Incomplete implementation fails isinstance check."""
        incomplete = IncompleteRouter()
        assert not isinstance(incomplete, MessageRouter)


class TestValidationStrategyIsinstance:
    """Tests for ValidationStrategy isinstance check."""

    def test_mock_implementation_isinstance(self):
        """Mock implementation passes isinstance check."""
        mock = MockValidationStrategy()
        assert isinstance(mock, ValidationStrategy)


class TestProcessingStrategyIsinstance:
    """Tests for ProcessingStrategy isinstance checks."""

    def test_mock_implementation_isinstance(self):
        """Mock implementation passes isinstance check."""
        mock = MockProcessingStrategy()
        assert isinstance(mock, ProcessingStrategy)

    def test_mock_is_available(self):
        """Mock strategy is_available works."""
        mock = MockProcessingStrategy(available=True)
        assert mock.is_available() is True

        mock_unavailable = MockProcessingStrategy(available=False)
        assert mock_unavailable.is_available() is False

    def test_mock_get_name(self):
        """Mock strategy get_name works."""
        mock = MockProcessingStrategy(name="test-strategy")
        assert mock.get_name() == "test-strategy"


class TestMessageHandlerIsinstance:
    """Tests for MessageHandler isinstance check."""

    def test_mock_implementation_isinstance(self):
        """Mock implementation passes isinstance check."""
        mock = MockMessageHandler()
        assert isinstance(mock, MessageHandler)


class TestMetricsCollectorIsinstance:
    """Tests for MetricsCollector isinstance check."""

    def test_mock_implementation_isinstance(self):
        """Mock implementation passes isinstance check."""
        mock = MockMetricsCollector()
        assert isinstance(mock, MetricsCollector)


class TestMockRegistryFunctional:
    """Functional tests for mock registry implementation."""

    async def test_register_and_get(self):
        """MockAgentRegistry can register and retrieve agents."""
        registry = MockAgentRegistry()

        result = await registry.register("agent-1", {"type": "worker"})
        assert result is True

        agent = await registry.get("agent-1")
        assert agent is not None
        assert agent["capabilities"]["type"] == "worker"

    async def test_duplicate_register(self):
        """MockAgentRegistry rejects duplicate registration."""
        registry = MockAgentRegistry()

        await registry.register("agent-1")
        result = await registry.register("agent-1")
        assert result is False

    async def test_unregister(self):
        """MockAgentRegistry can unregister agents."""
        registry = MockAgentRegistry()

        await registry.register("agent-1")
        assert await registry.exists("agent-1") is True

        result = await registry.unregister("agent-1")
        assert result is True
        assert await registry.exists("agent-1") is False

    async def test_unregister_nonexistent(self):
        """MockAgentRegistry returns False for nonexistent unregister."""
        registry = MockAgentRegistry()
        result = await registry.unregister("nonexistent")
        assert result is False

    async def test_list_agents(self):
        """MockAgentRegistry lists all agents."""
        registry = MockAgentRegistry()

        await registry.register("agent-1")
        await registry.register("agent-2")
        await registry.register("agent-3")

        agents = await registry.list_agents()
        assert len(agents) == 3
        assert "agent-1" in agents
        assert "agent-2" in agents
        assert "agent-3" in agents

    async def test_update_metadata(self):
        """MockAgentRegistry can update metadata."""
        registry = MockAgentRegistry()

        await registry.register("agent-1", metadata={"version": "1.0"})
        result = await registry.update_metadata("agent-1", {"status": "active"})
        assert result is True

        agent = await registry.get("agent-1")
        assert agent["metadata"]["version"] == "1.0"
        assert agent["metadata"]["status"] == "active"

    async def test_update_metadata_nonexistent(self):
        """MockAgentRegistry returns False for nonexistent metadata update."""
        registry = MockAgentRegistry()
        result = await registry.update_metadata("nonexistent", {"key": "value"})
        assert result is False

    async def test_get_nonexistent(self):
        """MockAgentRegistry returns None for nonexistent agent."""
        registry = MockAgentRegistry()
        agent = await registry.get("nonexistent")
        assert agent is None


class TestMockRouterFunctional:
    """Functional tests for mock router implementation."""

    async def test_route(self):
        """MockMessageRouter routes to target agent."""
        router = MockMessageRouter()
        registry = MockAgentRegistry()
        await registry.register("target-agent")

        message = AgentMessage(
            content="test",
            from_agent="sender",
            to_agent="target-agent",
        )

        target = await router.route(message, registry)
        assert target == "target-agent"

    async def test_broadcast(self):
        """MockMessageRouter broadcasts to all agents."""
        router = MockMessageRouter()
        registry = MockAgentRegistry()

        await registry.register("agent-1")
        await registry.register("agent-2")
        await registry.register("agent-3")

        message = AgentMessage(
            content="broadcast",
            from_agent="sender",
            to_agent="*",
        )

        targets = await router.broadcast(message, registry)
        assert len(targets) == 3

    async def test_broadcast_with_exclude(self):
        """MockMessageRouter respects exclusion list."""
        router = MockMessageRouter()
        registry = MockAgentRegistry()

        await registry.register("agent-1")
        await registry.register("agent-2")
        await registry.register("agent-3")

        message = AgentMessage(
            content="broadcast",
            from_agent="sender",
            to_agent="*",
        )

        targets = await router.broadcast(message, registry, exclude=["agent-2"])
        assert len(targets) == 2
        assert "agent-2" not in targets


class TestMockValidationFunctional:
    """Functional tests for mock validation implementation."""

    async def test_valid_message(self):
        """MockValidationStrategy validates valid message."""
        validator = MockValidationStrategy()

        message = AgentMessage(
            content="valid content",
            from_agent="sender",
            to_agent="receiver",
        )

        is_valid, error = await validator.validate(message)
        assert is_valid is True
        assert error is None

    async def test_invalid_message(self):
        """MockValidationStrategy rejects invalid message."""
        validator = MockValidationStrategy()

        message = AgentMessage(
            content="",  # Empty content
            from_agent="sender",
            to_agent="receiver",
        )

        is_valid, error = await validator.validate(message)
        assert is_valid is False
        assert error is not None
        assert "Empty" in error


class TestMockProcessingFunctional:
    """Functional tests for mock processing implementation."""

    async def test_process(self):
        """MockProcessingStrategy processes messages."""
        strategy = MockProcessingStrategy()

        message = AgentMessage(
            content="test",
            from_agent="sender",
            to_agent="receiver",
        )

        result = await strategy.process(message, {})
        assert result["is_valid"] is True


class TestMockHandlerFunctional:
    """Functional tests for mock handler implementation."""

    async def test_handle(self):
        """MockMessageHandler handles messages."""
        handler = MockMessageHandler()

        message = AgentMessage(
            content="original",
            from_agent="sender",
            to_agent="receiver",
        )

        response = await handler.handle(message)
        assert response is not None
        assert "Handled" in response.content
        assert response.from_agent == "receiver"
        assert response.to_agent == "sender"

    def test_can_handle_matching_type(self):
        """MockMessageHandler can_handle returns True for matching type."""
        # MessageType enum values are lowercase: "command", "query", etc.
        handler = MockMessageHandler(message_types=["command"])

        message = AgentMessage(
            content="test",
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
        )

        assert handler.can_handle(message) is True

    def test_can_handle_non_matching_type(self):
        """MockMessageHandler can_handle returns False for non-matching type."""
        handler = MockMessageHandler(message_types=["query"])

        message = AgentMessage(
            content="test",
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.COMMAND,
        )

        assert handler.can_handle(message) is False


class TestMockMetricsFunctional:
    """Functional tests for mock metrics implementation."""

    def test_record_and_get_metrics(self):
        """MockMetricsCollector records and retrieves metrics."""
        collector = MockMetricsCollector()

        collector.record_message_processed("COMMAND", 10.5, True)
        collector.record_message_processed("QUERY", 5.2, True)
        collector.record_agent_registered("agent-1")
        collector.record_agent_unregistered("agent-1")

        metrics = collector.get_metrics()
        assert metrics["messages_processed"] == 2
        assert metrics["agents_registered"] == 1
        assert metrics["agents_unregistered"] == 1
        assert metrics["total_duration_ms"] == pytest.approx(15.7)


class TestInterfacesModuleStructure:
    """Tests for interfaces module exports and structure."""

    def test_all_exports_count(self):
        """interfaces module has expected number of exports."""
        assert len(interfaces.__all__) == 20

    def test_module_docstring_has_constitutional_hash(self):
        """interfaces module docstring has constitutional hash."""
        assert interfaces.__doc__ is not None
        assert CONSTITUTIONAL_HASH in interfaces.__doc__


class TestProtocolDocstrings:
    """Tests for protocol docstrings."""

    def test_agent_registry_docstring(self):
        """AgentRegistry has docstring with constitutional hash."""
        assert AgentRegistry.__doc__ is not None
        assert CONSTITUTIONAL_HASH in AgentRegistry.__doc__

    def test_message_router_docstring(self):
        """MessageRouter has docstring with constitutional hash."""
        assert MessageRouter.__doc__ is not None
        assert CONSTITUTIONAL_HASH in MessageRouter.__doc__

    def test_validation_strategy_docstring(self):
        """ValidationStrategy has docstring with constitutional hash."""
        assert ValidationStrategy.__doc__ is not None
        assert CONSTITUTIONAL_HASH in ValidationStrategy.__doc__

    def test_processing_strategy_docstring(self):
        """ProcessingStrategy has docstring with constitutional hash."""
        assert ProcessingStrategy.__doc__ is not None
        assert CONSTITUTIONAL_HASH in ProcessingStrategy.__doc__

    def test_message_handler_docstring(self):
        """MessageHandler has docstring with constitutional hash."""
        assert MessageHandler.__doc__ is not None
        assert CONSTITUTIONAL_HASH in MessageHandler.__doc__

    def test_metrics_collector_docstring(self):
        """MetricsCollector has docstring with constitutional hash."""
        assert MetricsCollector.__doc__ is not None
        assert CONSTITUTIONAL_HASH in MetricsCollector.__doc__


class TestProtocolMethodSignatures:
    """Tests for protocol method signatures."""

    def test_agent_registry_register_signature(self):
        """AgentRegistry.register has expected parameters."""
        import inspect

        sig = inspect.signature(AgentRegistry.register)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "agent_id" in params

    def test_message_router_route_signature(self):
        """MessageRouter.route has expected parameters."""
        import inspect

        sig = inspect.signature(MessageRouter.route)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "message" in params
        assert "registry" in params

    def test_message_router_broadcast_signature(self):
        """MessageRouter.broadcast has expected parameters."""
        import inspect

        sig = inspect.signature(MessageRouter.broadcast)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "message" in params
        assert "registry" in params
        assert "exclude" in params

    def test_validation_strategy_validate_signature(self):
        """ValidationStrategy.validate has expected parameters."""
        import inspect

        sig = inspect.signature(ValidationStrategy.validate)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "message" in params

    def test_processing_strategy_process_signature(self):
        """ProcessingStrategy.process has expected parameters."""
        import inspect

        sig = inspect.signature(ProcessingStrategy.process)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "message" in params
        assert "handlers" in params


class TestRealImplementationsMatchProtocol:
    """Tests that verify real implementations match protocols."""

    def test_inmemory_agent_registry(self):
        """InMemoryAgentRegistry implements AgentRegistry protocol."""
        try:
            from enhanced_agent_bus.registry import InMemoryAgentRegistry
        except ImportError:
            from registry import InMemoryAgentRegistry

        registry = InMemoryAgentRegistry()
        assert isinstance(registry, AgentRegistry)

    def test_direct_message_router(self):
        """DirectMessageRouter implements MessageRouter protocol."""
        try:
            from enhanced_agent_bus.registry import DirectMessageRouter
        except ImportError:
            from registry import DirectMessageRouter

        router = DirectMessageRouter()
        assert isinstance(router, MessageRouter)

    def test_python_processing_strategy(self):
        """PythonProcessingStrategy implements ProcessingStrategy protocol."""
        try:
            from enhanced_agent_bus.registry import PythonProcessingStrategy
        except ImportError:
            from registry import PythonProcessingStrategy

        strategy = PythonProcessingStrategy()
        assert isinstance(strategy, ProcessingStrategy)

    def test_static_hash_validation_strategy(self):
        """StaticHashValidationStrategy implements ValidationStrategy protocol."""
        try:
            from enhanced_agent_bus.registry import StaticHashValidationStrategy
        except ImportError:
            from registry import StaticHashValidationStrategy

        strategy = StaticHashValidationStrategy()
        assert isinstance(strategy, ValidationStrategy)

    def test_opa_processing_strategy(self):
        """OPAProcessingStrategy implements ProcessingStrategy protocol."""
        try:
            from enhanced_agent_bus.registry import OPAProcessingStrategy
        except ImportError:
            from registry import OPAProcessingStrategy

        strategy = OPAProcessingStrategy()
        assert isinstance(strategy, ProcessingStrategy)

    def test_opa_validation_strategy(self):
        """OPAValidationStrategy implements ValidationStrategy protocol."""
        try:
            from enhanced_agent_bus.validation_strategies import OPAValidationStrategy
        except ImportError:
            from validation_strategies import OPAValidationStrategy

        # OPAValidationStrategy requires an opa_client argument (can be None for protocol check)
        strategy = OPAValidationStrategy(opa_client=None)
        assert isinstance(strategy, ValidationStrategy)


class TestProtocolRuntimeCheckable:
    """Tests for runtime_checkable decorator behavior."""

    def test_agent_registry_is_protocol(self):
        """AgentRegistry is marked as Protocol."""
        from typing import Protocol

        assert issubclass(AgentRegistry, Protocol)

    def test_message_router_is_protocol(self):
        """MessageRouter is marked as Protocol."""
        from typing import Protocol

        assert issubclass(MessageRouter, Protocol)

    def test_validation_strategy_is_protocol(self):
        """ValidationStrategy is marked as Protocol."""
        from typing import Protocol

        assert issubclass(ValidationStrategy, Protocol)

    def test_processing_strategy_is_protocol(self):
        """ProcessingStrategy is marked as Protocol."""
        from typing import Protocol

        assert issubclass(ProcessingStrategy, Protocol)

    def test_message_handler_is_protocol(self):
        """MessageHandler is marked as Protocol."""
        from typing import Protocol

        assert issubclass(MessageHandler, Protocol)

    def test_metrics_collector_is_protocol(self):
        """MetricsCollector is marked as Protocol."""
        from typing import Protocol

        assert issubclass(MetricsCollector, Protocol)
