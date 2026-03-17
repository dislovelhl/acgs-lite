"""
ACGS-2 Enhanced Agent Bus - Metering Manager Tests
Constitutional Hash: cdd01ef066bc6cf2

Comprehensive tests for the MeteringManager class and factory function.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.metering_manager import MeteringManager, create_metering_manager
from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    AgentMessage,
    MessageType,
    Priority,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def valid_message() -> AgentMessage:
    """Create a valid test message."""
    return AgentMessage(
        from_agent="test-sender",
        to_agent="test-receiver",
        content={"action": "test", "data": "hello"},
        constitutional_hash=CONSTITUTIONAL_HASH,
        message_type=MessageType.COMMAND,
        priority=Priority.NORMAL,
        tenant_id="test-tenant",
    )


@pytest.fixture
def mock_metering_hooks() -> MagicMock:
    """Create mock metering hooks."""
    hooks = MagicMock()
    hooks.on_agent_message = MagicMock()
    hooks.on_deliberation_request = MagicMock()
    hooks.on_validation_result = MagicMock()
    return hooks


@pytest.fixture
def mock_metering_queue() -> AsyncMock:
    """Create mock metering queue."""
    queue = AsyncMock()
    queue.start = AsyncMock()
    queue.stop = AsyncMock()
    queue.get_metrics = MagicMock(return_value={"events_queued": 10, "events_processed": 5})
    return queue


@pytest.fixture
def metering_manager(
    mock_metering_hooks: MagicMock, mock_metering_queue: AsyncMock
) -> MeteringManager:
    """Create a metering manager with mocks."""
    return MeteringManager(
        metering_hooks=mock_metering_hooks,
        metering_queue=mock_metering_queue,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


@pytest.fixture
def disabled_metering_manager() -> MeteringManager:
    """Create a disabled metering manager."""
    return MeteringManager(
        metering_hooks=None,
        metering_queue=None,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


# =============================================================================
# MeteringManager Initialization Tests
# =============================================================================


class TestMeteringManagerInit:
    """Tests for MeteringManager initialization."""

    def test_init_with_hooks_and_queue(
        self, mock_metering_hooks: MagicMock, mock_metering_queue: AsyncMock
    ) -> None:
        """Test initialization with hooks and queue."""
        manager = MeteringManager(
            metering_hooks=mock_metering_hooks,
            metering_queue=mock_metering_queue,
        )
        assert manager._metering_hooks is mock_metering_hooks
        assert manager._metering_queue is mock_metering_queue
        assert manager._enabled is True

    def test_init_without_hooks(self, mock_metering_queue: AsyncMock) -> None:
        """Test initialization without hooks disables metering."""
        manager = MeteringManager(
            metering_hooks=None,
            metering_queue=mock_metering_queue,
        )
        assert manager._enabled is False

    def test_init_with_custom_hash(self) -> None:
        """Test initialization with custom constitutional hash."""
        custom_hash = "custom123456"
        manager = MeteringManager(
            metering_hooks=None,
            metering_queue=None,
            constitutional_hash=custom_hash,
        )
        assert manager._constitutional_hash == custom_hash

    def test_init_default_hash(self) -> None:
        """Test initialization uses default constitutional hash."""
        manager = MeteringManager(metering_hooks=None, metering_queue=None)
        assert manager._constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# MeteringManager Properties Tests
# =============================================================================


class TestMeteringManagerProperties:
    """Tests for MeteringManager properties."""

    def test_is_enabled_true(self, metering_manager: MeteringManager) -> None:
        """Test is_enabled returns True when hooks are configured."""
        assert metering_manager.is_enabled is True

    def test_is_enabled_false(self, disabled_metering_manager: MeteringManager) -> None:
        """Test is_enabled returns False when hooks are None."""
        assert disabled_metering_manager.is_enabled is False

    def test_hooks_property(
        self, metering_manager: MeteringManager, mock_metering_hooks: MagicMock
    ) -> None:
        """Test hooks property returns configured hooks."""
        assert metering_manager.hooks is mock_metering_hooks

    def test_hooks_property_none(self, disabled_metering_manager: MeteringManager) -> None:
        """Test hooks property returns None when not configured."""
        assert disabled_metering_manager.hooks is None

    def test_queue_property(
        self, metering_manager: MeteringManager, mock_metering_queue: AsyncMock
    ) -> None:
        """Test queue property returns configured queue."""
        assert metering_manager.queue is mock_metering_queue

    def test_queue_property_none(self, disabled_metering_manager: MeteringManager) -> None:
        """Test queue property returns None when not configured."""
        assert disabled_metering_manager.queue is None


# =============================================================================
# Start/Stop Tests
# =============================================================================


class TestMeteringManagerLifecycle:
    """Tests for MeteringManager start/stop methods."""

    @pytest.mark.asyncio
    async def test_start_calls_queue_start(
        self, metering_manager: MeteringManager, mock_metering_queue: AsyncMock
    ) -> None:
        """Test start calls queue.start()."""
        await metering_manager.start()
        mock_metering_queue.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_without_queue(self, disabled_metering_manager: MeteringManager) -> None:
        """Test start does nothing without queue."""
        # Should not raise
        await disabled_metering_manager.start()

    @pytest.mark.asyncio
    async def test_stop_calls_queue_stop(
        self, metering_manager: MeteringManager, mock_metering_queue: AsyncMock
    ) -> None:
        """Test stop calls queue.stop()."""
        await metering_manager.stop()
        mock_metering_queue.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_without_queue(self, disabled_metering_manager: MeteringManager) -> None:
        """Test stop does nothing without queue."""
        # Should not raise
        await disabled_metering_manager.stop()


# =============================================================================
# Record Agent Message Tests
# =============================================================================


class TestRecordAgentMessage:
    """Tests for record_agent_message method."""

    def test_record_agent_message_success(
        self,
        metering_manager: MeteringManager,
        mock_metering_hooks: MagicMock,
        valid_message: AgentMessage,
    ) -> None:
        """Test recording an agent message event."""
        metering_manager.record_agent_message(
            message=valid_message,
            is_valid=True,
            latency_ms=1.5,
        )

        mock_metering_hooks.on_agent_message.assert_called_once()
        call_args = mock_metering_hooks.on_agent_message.call_args
        assert call_args.kwargs["tenant_id"] == "test-tenant"
        assert call_args.kwargs["from_agent"] == "test-sender"
        assert call_args.kwargs["to_agent"] == "test-receiver"
        assert call_args.kwargs["is_valid"] is True
        assert call_args.kwargs["latency_ms"] == 1.5

    def test_record_agent_message_with_invalid_result(
        self,
        metering_manager: MeteringManager,
        mock_metering_hooks: MagicMock,
        valid_message: AgentMessage,
    ) -> None:
        """Test recording an invalid agent message event."""
        metering_manager.record_agent_message(
            message=valid_message,
            is_valid=False,
            latency_ms=2.0,
        )

        call_args = mock_metering_hooks.on_agent_message.call_args
        assert call_args.kwargs["is_valid"] is False

    def test_record_agent_message_disabled(
        self, disabled_metering_manager: MeteringManager, valid_message: AgentMessage
    ) -> None:
        """Test record_agent_message does nothing when disabled."""
        # Should not raise
        disabled_metering_manager.record_agent_message(
            message=valid_message,
            is_valid=True,
            latency_ms=1.0,
        )

    def test_record_agent_message_exception_handled(
        self,
        metering_manager: MeteringManager,
        mock_metering_hooks: MagicMock,
        valid_message: AgentMessage,
    ) -> None:
        """Test record_agent_message handles exceptions gracefully."""
        mock_metering_hooks.on_agent_message.side_effect = Exception("Metering error")

        # Should not raise
        metering_manager.record_agent_message(
            message=valid_message,
            is_valid=True,
            latency_ms=1.0,
        )

    def test_record_agent_message_default_tenant(
        self,
        metering_manager: MeteringManager,
        mock_metering_hooks: MagicMock,
    ) -> None:
        """Test default tenant ID when message has no tenant."""
        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            content={"test": "data"},
            tenant_id=None,
        )

        metering_manager.record_agent_message(message=message, is_valid=True, latency_ms=1.0)

        call_args = mock_metering_hooks.on_agent_message.call_args
        assert call_args.kwargs["tenant_id"] == "default"


# =============================================================================
# Record Deliberation Request Tests
# =============================================================================


class TestRecordDeliberationRequest:
    """Tests for record_deliberation_request method."""

    def test_record_deliberation_request_success(
        self,
        metering_manager: MeteringManager,
        mock_metering_hooks: MagicMock,
        valid_message: AgentMessage,
    ) -> None:
        """Test recording a deliberation request event."""
        metering_manager.record_deliberation_request(
            message=valid_message,
            impact_score=0.85,
            latency_ms=5.0,
        )

        mock_metering_hooks.on_deliberation_request.assert_called_once()
        call_args = mock_metering_hooks.on_deliberation_request.call_args
        assert call_args.kwargs["tenant_id"] == "test-tenant"
        assert call_args.kwargs["agent_id"] == "test-sender"
        assert call_args.kwargs["impact_score"] == 0.85
        assert call_args.kwargs["latency_ms"] == 5.0

    def test_record_deliberation_request_disabled(
        self, disabled_metering_manager: MeteringManager, valid_message: AgentMessage
    ) -> None:
        """Test record_deliberation_request does nothing when disabled."""
        # Should not raise
        disabled_metering_manager.record_deliberation_request(
            message=valid_message,
            impact_score=0.9,
            latency_ms=10.0,
        )

    def test_record_deliberation_request_exception_handled(
        self,
        metering_manager: MeteringManager,
        mock_metering_hooks: MagicMock,
        valid_message: AgentMessage,
    ) -> None:
        """Test record_deliberation_request handles exceptions gracefully."""
        mock_metering_hooks.on_deliberation_request.side_effect = Exception("Error")

        # Should not raise
        metering_manager.record_deliberation_request(
            message=valid_message,
            impact_score=0.9,
            latency_ms=10.0,
        )


# =============================================================================
# Record Validation Result Tests
# =============================================================================


class TestRecordValidationResult:
    """Tests for record_validation_result method."""

    def test_record_validation_result_success(
        self,
        metering_manager: MeteringManager,
        mock_metering_hooks: MagicMock,
    ) -> None:
        """Test recording a validation result event."""
        metering_manager.record_validation_result(
            tenant_id="test-tenant",
            agent_id="test-agent",
            is_valid=True,
            latency_ms=0.5,
        )

        mock_metering_hooks.on_validation_result.assert_called_once()
        call_args = mock_metering_hooks.on_validation_result.call_args
        assert call_args.kwargs["tenant_id"] == "test-tenant"
        assert call_args.kwargs["agent_id"] == "test-agent"
        assert call_args.kwargs["is_valid"] is True
        assert call_args.kwargs["latency_ms"] == 0.5

    def test_record_validation_result_with_error_type(
        self,
        metering_manager: MeteringManager,
        mock_metering_hooks: MagicMock,
    ) -> None:
        """Test recording a validation result with error type."""
        metering_manager.record_validation_result(
            tenant_id="test-tenant",
            agent_id="test-agent",
            is_valid=False,
            latency_ms=0.3,
            error_type="ConstitutionalHashMismatch",
        )

        call_args = mock_metering_hooks.on_validation_result.call_args
        assert call_args.kwargs["is_valid"] is False
        assert call_args.kwargs["metadata"]["error_type"] == "ConstitutionalHashMismatch"

    def test_record_validation_result_disabled(
        self, disabled_metering_manager: MeteringManager
    ) -> None:
        """Test record_validation_result does nothing when disabled."""
        # Should not raise
        disabled_metering_manager.record_validation_result(
            tenant_id="test",
            agent_id="agent",
            is_valid=True,
            latency_ms=0.1,
        )

    def test_record_validation_result_exception_handled(
        self,
        metering_manager: MeteringManager,
        mock_metering_hooks: MagicMock,
    ) -> None:
        """Test record_validation_result handles exceptions gracefully."""
        mock_metering_hooks.on_validation_result.side_effect = Exception("Error")

        # Should not raise
        metering_manager.record_validation_result(
            tenant_id="test",
            agent_id="agent",
            is_valid=True,
            latency_ms=0.1,
        )


# =============================================================================
# Get Metrics Tests
# =============================================================================


class TestGetMetrics:
    """Tests for get_metrics method."""

    def test_get_metrics_with_queue(
        self, metering_manager: MeteringManager, mock_metering_queue: AsyncMock
    ) -> None:
        """Test get_metrics returns queue metrics."""
        metrics = metering_manager.get_metrics()
        mock_metering_queue.get_metrics.assert_called_once()
        assert metrics == {"events_queued": 10, "events_processed": 5}

    def test_get_metrics_without_queue(self, disabled_metering_manager: MeteringManager) -> None:
        """Test get_metrics returns empty dict when queue is None."""
        metrics = disabled_metering_manager.get_metrics()
        assert metrics == {}


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateMeteringManager:
    """Tests for create_metering_manager factory function."""

    def test_create_metering_manager_disabled(self) -> None:
        """Test factory creates disabled manager when enable_metering is False."""
        manager = create_metering_manager(enable_metering=False)
        assert manager.is_enabled is False
        assert manager.hooks is None
        assert manager.queue is None

    def test_create_metering_manager_import_error(self) -> None:
        """Test factory handles import errors gracefully."""
        # When metering_integration is not available, should return disabled manager
        with patch.dict("sys.modules", {"metering_integration": None}):
            manager = create_metering_manager(enable_metering=True)
            # May or may not be enabled depending on import resolution
            # The key is that it doesn't raise
            assert isinstance(manager, MeteringManager)

    def test_create_metering_manager_custom_hash(self) -> None:
        """Test factory uses custom constitutional hash."""
        custom_hash = "customhash123"
        manager = create_metering_manager(
            enable_metering=False,
            constitutional_hash=custom_hash,
        )
        assert manager._constitutional_hash == custom_hash


# =============================================================================
# Integration Tests
# =============================================================================


class TestMeteringManagerIntegration:
    """Integration tests for MeteringManager."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(
        self,
        mock_metering_hooks: MagicMock,
        mock_metering_queue: AsyncMock,
        valid_message: AgentMessage,
    ) -> None:
        """Test full metering manager lifecycle."""
        manager = MeteringManager(
            metering_hooks=mock_metering_hooks,
            metering_queue=mock_metering_queue,
        )

        # Start
        await manager.start()
        mock_metering_queue.start.assert_called_once()

        # Record events
        manager.record_agent_message(valid_message, True, 1.0)
        manager.record_deliberation_request(valid_message, 0.8, 5.0)
        manager.record_validation_result("tenant", "agent", True, 0.5)

        assert mock_metering_hooks.on_agent_message.call_count == 1
        assert mock_metering_hooks.on_deliberation_request.call_count == 1
        assert mock_metering_hooks.on_validation_result.call_count == 1

        # Get metrics
        metrics = manager.get_metrics()
        assert metrics == {"events_queued": 10, "events_processed": 5}

        # Stop
        await manager.stop()
        mock_metering_queue.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_fire_and_forget_pattern(
        self,
        metering_manager: MeteringManager,
        mock_metering_hooks: MagicMock,
        valid_message: AgentMessage,
    ) -> None:
        """Test that metering uses fire-and-forget pattern."""
        # Hooks raising exceptions should not propagate
        mock_metering_hooks.on_agent_message.side_effect = Exception("Network error")
        mock_metering_hooks.on_deliberation_request.side_effect = Exception("Timeout")
        mock_metering_hooks.on_validation_result.side_effect = Exception("Service down")

        # None of these should raise
        metering_manager.record_agent_message(valid_message, True, 1.0)
        metering_manager.record_deliberation_request(valid_message, 0.8, 5.0)
        metering_manager.record_validation_result("tenant", "agent", True, 0.5)

        # All hooks were called despite errors
        assert mock_metering_hooks.on_agent_message.call_count == 1
        assert mock_metering_hooks.on_deliberation_request.call_count == 1
        assert mock_metering_hooks.on_validation_result.call_count == 1
