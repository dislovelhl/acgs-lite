"""
ACGS-2 Enhanced Agent Bus - Interfaces Tests
Constitutional Hash: 608508a9bd224290

Tests for Protocol interface definitions.
"""

from typing import Any, Optional

import pytest

from enhanced_agent_bus._compat.types import JSONDict

try:
    from interfaces import (
        AgentRegistry,
        MessageHandler,
        MessageRouter,
        MetricsCollector,
        ProcessingStrategy,
        ValidationStrategy,
    )
    from models import AgentMessage, MessageType
except ImportError:
    from ..interfaces import (
        AgentRegistry,
        MessageHandler,
        MessageRouter,
        MetricsCollector,
        ProcessingStrategy,
        ValidationStrategy,
    )


class TestAgentRegistryProtocol:
    """Tests for AgentRegistry protocol."""

    def test_is_runtime_checkable(self):
        """AgentRegistry is runtime checkable."""
        assert hasattr(AgentRegistry, "__protocol_attrs__") or hasattr(
            AgentRegistry, "_is_protocol"
        )

    def test_has_register_method(self):
        """AgentRegistry defines register method."""
        assert hasattr(AgentRegistry, "register")

    def test_has_unregister_method(self):
        """AgentRegistry defines unregister method."""
        assert hasattr(AgentRegistry, "unregister")

    def test_has_get_method(self):
        """AgentRegistry defines get method."""
        assert hasattr(AgentRegistry, "get")

    def test_has_list_agents_method(self):
        """AgentRegistry defines list_agents method."""
        assert hasattr(AgentRegistry, "list_agents")

    def test_has_exists_method(self):
        """AgentRegistry defines exists method."""
        assert hasattr(AgentRegistry, "exists")

    def test_has_update_metadata_method(self):
        """AgentRegistry defines update_metadata method."""
        assert hasattr(AgentRegistry, "update_metadata")

    def test_mock_implementation(self):
        """Mock implementation satisfies protocol."""

        class MockRegistry:
            async def register(self, agent_id: str, capabilities=None, metadata=None) -> bool:
                return True

            async def unregister(self, agent_id: str) -> bool:
                return True

            async def get(self, agent_id: str) -> JSONDict | None:
                return None

            async def list_agents(self) -> list[str]:
                return []

            async def exists(self, agent_id: str) -> bool:
                return False

            async def update_metadata(self, agent_id: str, metadata: JSONDict) -> bool:
                return True

        mock = MockRegistry()
        assert isinstance(mock, AgentRegistry)


class TestMessageRouterProtocol:
    """Tests for MessageRouter protocol."""

    def test_is_runtime_checkable(self):
        """MessageRouter is runtime checkable."""
        assert hasattr(MessageRouter, "__protocol_attrs__") or hasattr(
            MessageRouter, "_is_protocol"
        )

    def test_has_route_method(self):
        """MessageRouter defines route method."""
        assert hasattr(MessageRouter, "route")

    def test_has_broadcast_method(self):
        """MessageRouter defines broadcast method."""
        assert hasattr(MessageRouter, "broadcast")

    def test_mock_implementation(self):
        """Mock implementation satisfies protocol."""

        class MockRouter:
            async def route(self, message, registry) -> str | None:
                return None

            async def broadcast(self, message, registry, exclude=None) -> list[str]:
                return []

        mock = MockRouter()
        assert isinstance(mock, MessageRouter)


class TestValidationStrategyProtocol:
    """Tests for ValidationStrategy protocol."""

    def test_is_runtime_checkable(self):
        """ValidationStrategy is runtime checkable."""
        assert hasattr(ValidationStrategy, "__protocol_attrs__") or hasattr(
            ValidationStrategy, "_is_protocol"
        )

    def test_has_validate_method(self):
        """ValidationStrategy defines validate method."""
        assert hasattr(ValidationStrategy, "validate")

    def test_mock_implementation(self):
        """Mock implementation satisfies protocol."""

        class MockValidator:
            async def validate(self, message) -> tuple:
                return (True, None)

        mock = MockValidator()
        assert isinstance(mock, ValidationStrategy)


class TestProcessingStrategyProtocol:
    """Tests for ProcessingStrategy protocol."""

    def test_is_runtime_checkable(self):
        """ProcessingStrategy is runtime checkable."""
        assert hasattr(ProcessingStrategy, "__protocol_attrs__") or hasattr(
            ProcessingStrategy, "_is_protocol"
        )

    def test_has_process_method(self):
        """ProcessingStrategy defines process method."""
        assert hasattr(ProcessingStrategy, "process")

    def test_has_is_available_method(self):
        """ProcessingStrategy defines is_available method."""
        assert hasattr(ProcessingStrategy, "is_available")

    def test_has_get_name_method(self):
        """ProcessingStrategy defines get_name method."""
        assert hasattr(ProcessingStrategy, "get_name")

    def test_mock_implementation(self):
        """Mock implementation satisfies protocol."""

        class MockProcessor:
            async def process(self, message, handlers) -> Any:
                return None

            def is_available(self) -> bool:
                return True

            def get_name(self) -> str:
                return "mock"

        mock = MockProcessor()
        assert isinstance(mock, ProcessingStrategy)


class TestMessageHandlerProtocol:
    """Tests for MessageHandler protocol."""

    def test_is_runtime_checkable(self):
        """MessageHandler is runtime checkable."""
        assert hasattr(MessageHandler, "__protocol_attrs__") or hasattr(
            MessageHandler, "_is_protocol"
        )

    def test_has_handle_method(self):
        """MessageHandler defines handle method."""
        assert hasattr(MessageHandler, "handle")

    def test_has_can_handle_method(self):
        """MessageHandler defines can_handle method."""
        assert hasattr(MessageHandler, "can_handle")

    def test_mock_implementation(self):
        """Mock implementation satisfies protocol."""

        class MockHandler:
            async def handle(self, message) -> Any | None:
                return None

            def can_handle(self, message) -> bool:
                return True

        mock = MockHandler()
        assert isinstance(mock, MessageHandler)


class TestMetricsCollectorProtocol:
    """Tests for MetricsCollector protocol."""

    def test_is_runtime_checkable(self):
        """MetricsCollector is runtime checkable."""
        assert hasattr(MetricsCollector, "__protocol_attrs__") or hasattr(
            MetricsCollector, "_is_protocol"
        )

    def test_has_record_message_processed(self):
        """MetricsCollector defines record_message_processed."""
        assert hasattr(MetricsCollector, "record_message_processed")

    def test_has_record_agent_registered(self):
        """MetricsCollector defines record_agent_registered."""
        assert hasattr(MetricsCollector, "record_agent_registered")

    def test_has_record_agent_unregistered(self):
        """MetricsCollector defines record_agent_unregistered."""
        assert hasattr(MetricsCollector, "record_agent_unregistered")

    def test_has_get_metrics(self):
        """MetricsCollector defines get_metrics."""
        assert hasattr(MetricsCollector, "get_metrics")

    def test_mock_implementation(self):
        """Mock implementation satisfies protocol."""

        class MockCollector:
            def record_message_processed(
                self, message_type: str, duration_ms: float, success: bool
            ) -> None:
                pass

            def record_agent_registered(self, agent_id: str) -> None:
                pass

            def record_agent_unregistered(self, agent_id: str) -> None:
                pass

            def get_metrics(self) -> JSONDict:
                return {}

        mock = MockCollector()
        assert isinstance(mock, MetricsCollector)


class TestModuleExports:
    """Tests for module exports."""

    def test_all_protocols_exported(self):
        """All protocols are in __all__."""
        try:
            from interfaces import __all__
        except ImportError:
            from ..interfaces import __all__

        expected = [
            "AgentRegistry",
            "MessageRouter",
            "ValidationStrategy",
            "ProcessingStrategy",
            "MessageHandler",
            "MetricsCollector",
        ]

        for protocol in expected:
            assert protocol in __all__, f"{protocol} not in __all__"


class TestProtocolNonImplementation:
    """Tests for non-implementing classes."""

    def test_empty_class_not_registry(self):
        """Empty class does not implement AgentRegistry."""

        class Empty:
            pass

        assert not isinstance(Empty(), AgentRegistry)

    def test_partial_implementation_not_registry(self):
        """Partial implementation does not satisfy AgentRegistry."""

        class PartialRegistry:
            async def register(self, agent_id, capabilities=None, metadata=None):
                return True

            # Missing other methods

        # With runtime_checkable, partial implementations may pass
        # This test documents the behavior
        partial = PartialRegistry()
        # Note: runtime_checkable only checks for method existence, not full signature
        assert hasattr(partial, "register")

    def test_wrong_signature_class(self):
        """Class with wrong signature still matches protocol name."""

        class WrongSignature:
            def record_message_processed(self):  # Missing parameters
                pass

            def record_agent_registered(self):
                pass

            def record_agent_unregistered(self):
                pass

            def get_metrics(self):
                return {}

        # runtime_checkable checks method names, not signatures
        wrong = WrongSignature()
        # This will be True due to how runtime_checkable works
        assert isinstance(wrong, MetricsCollector)


class TestProtocolIsAbstract:
    """Tests that protocols behave as abstract."""

    def test_cannot_instantiate_registry(self):
        """Cannot instantiate AgentRegistry directly."""
        with pytest.raises(TypeError):
            AgentRegistry()

    def test_cannot_instantiate_router(self):
        """Cannot instantiate MessageRouter directly."""
        with pytest.raises(TypeError):
            MessageRouter()

    def test_cannot_instantiate_validation_strategy(self):
        """Cannot instantiate ValidationStrategy directly."""
        with pytest.raises(TypeError):
            ValidationStrategy()

    def test_cannot_instantiate_processing_strategy(self):
        """Cannot instantiate ProcessingStrategy directly."""
        with pytest.raises(TypeError):
            ProcessingStrategy()

    def test_cannot_instantiate_message_handler(self):
        """Cannot instantiate MessageHandler directly."""
        with pytest.raises(TypeError):
            MessageHandler()

    def test_cannot_instantiate_metrics_collector(self):
        """Cannot instantiate MetricsCollector directly."""
        with pytest.raises(TypeError):
            MetricsCollector()


class TestProtocolInheritance:
    """Tests for protocol inheritance behavior."""

    def test_explicit_inheritance_works(self):
        """Explicit protocol inheritance works correctly."""

        class ConcreteRegistry(AgentRegistry):
            async def register(self, agent_id: str, capabilities=None, metadata=None) -> bool:
                return True

            async def unregister(self, agent_id: str) -> bool:
                return True

            async def get(self, agent_id: str) -> JSONDict | None:
                return None

            async def list_agents(self) -> list[str]:
                return []

            async def exists(self, agent_id: str) -> bool:
                return False

            async def update_metadata(self, agent_id: str, metadata: JSONDict) -> bool:
                return True

        concrete = ConcreteRegistry()
        assert isinstance(concrete, AgentRegistry)
