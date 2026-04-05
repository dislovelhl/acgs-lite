"""Direct tests for SessionCoordinator."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.models import (
    AgentMessage,
    MessageType,
    Priority,
    RiskLevel,
    SessionGovernanceConfig,
)
from enhanced_agent_bus.processing_context import MessageProcessingContext
from enhanced_agent_bus.session_context import SessionContext
from enhanced_agent_bus.session_context_resolver import SessionContextResolver
from enhanced_agent_bus.session_coordinator import SessionCoordinator


@pytest.fixture
def mock_session_context() -> SessionContext:
    governance_config = SessionGovernanceConfig(
        tenant_id="test-tenant",
        user_id="test-user",
        session_id="test-session-123",
        risk_level=RiskLevel.MEDIUM,
        policy_overrides={"max_tokens": 1000},
    )
    return SessionContext(
        session_id="test-session-123",
        tenant_id="test-tenant",
        governance_config=governance_config,
        metadata={"test_key": "test_value"},
    )


@pytest.fixture
def bus_config() -> BusConfiguration:
    config = BusConfiguration.for_testing()
    config.enable_session_governance = True
    config.session_policy_cache_ttl = 300
    config.session_context_ttl = 3600
    return config


def _message(**overrides: object) -> AgentMessage:
    return AgentMessage(
        from_agent="test-agent",
        to_agent="target-agent",
        content="test content",
        message_type=MessageType.COMMAND,
        priority=Priority.NORMAL,
        tenant_id="test-tenant",
        **overrides,
    )


def _coordinator(
    resolver: object,
    *,
    enabled: bool = True,
) -> SessionCoordinator:
    return SessionCoordinator(
        enable_session_governance=enabled,
        session_context_manager=None,
        session_resolver=resolver,  # type: ignore[arg-type]
    )


class TestSessionCoordinatorRuntime:
    def test_initialize_runtime_returns_disabled_state_when_feature_off(
        self, bus_config: BusConfiguration
    ) -> None:
        enabled, manager = SessionCoordinator.initialize_runtime(
            bus_config,
            enable_session_governance=False,
        )

        assert enabled is False
        assert manager is None

    @patch("enhanced_agent_bus.session_coordinator.SessionContextManager")
    def test_initialize_runtime_builds_manager_when_enabled(
        self,
        mock_manager_cls: MagicMock,
        bus_config: BusConfiguration,
    ) -> None:
        mock_manager = MagicMock()
        mock_manager_cls.return_value = mock_manager

        enabled, manager = SessionCoordinator.initialize_runtime(
            bus_config,
            enable_session_governance=True,
        )

        assert enabled is True
        assert manager is mock_manager
        mock_manager_cls.assert_called_once_with(
            cache_size=1000,
            cache_ttl=bus_config.session_policy_cache_ttl,
        )

    def test_build_session_resolver_returns_resolver_instance(
        self, bus_config: BusConfiguration
    ) -> None:
        resolver = SessionCoordinator.build_session_resolver(bus_config, None)

        assert isinstance(resolver, SessionContextResolver)


class TestSessionCoordinatorExtraction:
    @pytest.mark.asyncio
    async def test_extract_session_context_updates_metrics_from_resolver(
        self,
        mock_session_context: SessionContext,
    ) -> None:
        resolver = SimpleNamespace(
            resolve=AsyncMock(return_value=mock_session_context),
            get_metrics=MagicMock(
                return_value={"resolved_count": 1, "not_found_count": 0, "error_count": 0}
            ),
        )
        coordinator = _coordinator(resolver)

        result = await coordinator.extract_session_context(_message(session_id="test-session-123"))

        assert result is mock_session_context
        assert coordinator._session_resolved_count == 1
        assert coordinator._session_not_found_count == 0
        assert coordinator._session_error_count == 0

    @pytest.mark.asyncio
    async def test_extract_session_context_returns_none_when_disabled(self) -> None:
        resolver = SimpleNamespace(resolve=AsyncMock(), get_metrics=MagicMock(return_value={}))
        coordinator = _coordinator(resolver, enabled=False)

        result = await coordinator.extract_session_context(_message(session_id="test-session-123"))

        assert result is None
        resolver.resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_attach_session_context_supports_legacy_message_and_processing_context(
        self,
        mock_session_context: SessionContext,
    ) -> None:
        resolver = SimpleNamespace(
            resolve=AsyncMock(return_value=mock_session_context),
            get_metrics=MagicMock(
                return_value={"resolved_count": 1, "not_found_count": 0, "error_count": 0}
            ),
        )
        coordinator = _coordinator(resolver)

        legacy_message = _message(session_id=None)
        await coordinator.attach_session_context(legacy_message)
        assert legacy_message.session_context is mock_session_context
        assert legacy_message.session_id == mock_session_context.session_id

        context_message = _message(session_id=None)
        processing_context = MessageProcessingContext(message=context_message, start_time=0.0)
        await coordinator.attach_session_context(processing_context)
        assert processing_context.session_context is mock_session_context
        assert context_message.session_context is mock_session_context
        assert context_message.session_id == mock_session_context.session_id

    @patch("enhanced_agent_bus.session_coordinator.extract_session_id_for_pacar")
    def test_extract_message_session_id_delegates_to_helper(
        self,
        mock_extract_session_id: MagicMock,
    ) -> None:
        mock_extract_session_id.return_value = "session-123"
        coordinator = _coordinator(
            SimpleNamespace(resolve=AsyncMock(), get_metrics=MagicMock(return_value={}))
        )

        result = coordinator.extract_message_session_id(_message())

        mock_extract_session_id.assert_called_once()
        assert result == "session-123"


class TestSessionCoordinatorMetrics:
    def test_apply_metrics_populates_enabled_metrics(self) -> None:
        coordinator = SessionCoordinator(
            enable_session_governance=True,
            session_context_manager=None,
            session_resolver=SimpleNamespace(),  # type: ignore[arg-type]
            session_resolved_count=2,
            session_not_found_count=1,
            session_error_count=0,
        )
        metrics = {"processed_count": 1}

        coordinator.apply_metrics(metrics)

        assert metrics["session_governance_enabled"] is True
        assert metrics["session_resolved_count"] == 2
        assert metrics["session_not_found_count"] == 1
        assert metrics["session_error_count"] == 0
        assert metrics["session_resolution_rate"] == 2 / 3

    def test_sync_and_export_runtime_round_trip(self) -> None:
        initial_resolver = SimpleNamespace()
        updated_resolver = SimpleNamespace()
        coordinator = SessionCoordinator(
            enable_session_governance=False,
            session_context_manager=None,
            session_resolver=initial_resolver,  # type: ignore[arg-type]
        )

        coordinator.sync_runtime(
            enable_session_governance=True,
            session_context_manager=None,
            session_resolver=updated_resolver,  # type: ignore[arg-type]
            session_resolved_count=3,
            session_not_found_count=1,
            session_error_count=2,
        )

        assert coordinator.export_runtime_state() == (
            True,
            None,
            updated_resolver,
            3,
            1,
            2,
        )
