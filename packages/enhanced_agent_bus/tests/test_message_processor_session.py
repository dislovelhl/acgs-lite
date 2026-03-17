"""
Tests for MessageProcessor session context integration (Subtask 3.2)
Constitutional Hash: cdd01ef066bc6cf2

Acceptance Criteria:
1. Extract session_id from message metadata
2. Load session context from SessionContextManager
3. Attach session context to processing pipeline
4. Graceful fallback when session not found
5. Metrics for session resolution
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from packages.enhanced_agent_bus.config import BusConfiguration
from packages.enhanced_agent_bus.message_processor import MessageProcessor
from packages.enhanced_agent_bus.models import (
    AgentMessage,
    MessageType,
    Priority,
    RiskLevel,
    SessionGovernanceConfig,
)
from packages.enhanced_agent_bus.session_context import SessionContext, SessionContextManager


@pytest.fixture
def mock_session_context():
    """Create a mock session context for testing."""
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
def bus_config():
    """Create a bus configuration with session governance enabled."""
    config = BusConfiguration.for_testing()
    config.enable_session_governance = True
    config.session_policy_cache_ttl = 300
    config.session_context_ttl = 3600
    return config


@pytest.fixture
def message_processor(bus_config):
    """Create a MessageProcessor instance with session governance enabled."""
    return MessageProcessor(
        config=bus_config,
        isolated_mode=False,
        enable_maci=False,  # test-only: MACI off — testing message processor directly
    )


class TestSessionContextExtraction:
    """Test session context extraction from messages."""

    @pytest.mark.asyncio
    async def test_extract_from_session_id_field(self, message_processor, mock_session_context):
        """Test extracting session context from message session_id field."""
        # Arrange
        msg = AgentMessage(
            from_agent="test-agent",
            to_agent="target-agent",
            content="test content",
            message_type=MessageType.COMMAND,
            priority=Priority.NORMAL,
            session_id="test-session-123",
            tenant_id="test-tenant",  # Must match session context tenant
        )

        # Mock the session context manager with AsyncMock
        mock_get = AsyncMock(return_value=mock_session_context)
        with patch.object(message_processor._session_context_manager, "get", mock_get):
            # Act
            result = await message_processor._extract_session_context(msg)

            # Assert
            assert result is not None
            assert result.session_id == "test-session-123"
            assert result.governance_config.tenant_id == "test-tenant"
            assert message_processor._session_resolved_count == 1

    @pytest.mark.asyncio
    async def test_extract_from_headers(self, message_processor, mock_session_context):
        """Test extracting session context from message headers."""
        # Arrange
        msg = AgentMessage(
            from_agent="test-agent",
            to_agent="target-agent",
            content="test content",
            message_type=MessageType.COMMAND,
            priority=Priority.NORMAL,
            tenant_id="test-tenant",  # Must match session context tenant
        )
        msg.headers = {"X-Session-ID": "test-session-123"}

        # Mock the session context manager with AsyncMock
        mock_get = AsyncMock(return_value=mock_session_context)
        with patch.object(message_processor._session_context_manager, "get", mock_get):
            # Act
            result = await message_processor._extract_session_context(msg)

            # Assert
            assert result is not None
            assert result.session_id == "test-session-123"

    @pytest.mark.asyncio
    async def test_extract_from_metadata(self, message_processor, mock_session_context):
        """Test extracting session context from message metadata."""
        # Arrange
        msg = AgentMessage(
            from_agent="test-agent",
            to_agent="target-agent",
            content="test content",
            message_type=MessageType.COMMAND,
            priority=Priority.NORMAL,
            tenant_id="test-tenant",  # Must match session context tenant
        )
        msg.metadata = {"session_id": "test-session-123"}

        # Mock the session context manager with AsyncMock
        mock_get = AsyncMock(return_value=mock_session_context)
        with patch.object(message_processor._session_context_manager, "get", mock_get):
            # Act
            result = await message_processor._extract_session_context(msg)

            # Assert
            assert result is not None
            assert result.session_id == "test-session-123"

    @pytest.mark.asyncio
    async def test_extract_from_content_dict(self, message_processor, mock_session_context):
        """Test extracting session context from message content (dict)."""
        # Arrange
        msg = AgentMessage(
            from_agent="test-agent",
            to_agent="target-agent",
            content={"session_id": "test-session-123", "data": "test"},
            message_type=MessageType.COMMAND,
            priority=Priority.NORMAL,
            tenant_id="test-tenant",  # Must match session context tenant
        )

        # Mock the session context manager with AsyncMock
        mock_get = AsyncMock(return_value=mock_session_context)
        with patch.object(message_processor._session_context_manager, "get", mock_get):
            # Act
            result = await message_processor._extract_session_context(msg)

            # Assert
            assert result is not None
            assert result.session_id == "test-session-123"

    @pytest.mark.asyncio
    async def test_session_already_attached(self, message_processor, mock_session_context):
        """Test when session_context is already attached to message."""
        # Arrange
        msg = AgentMessage(
            from_agent="test-agent",
            to_agent="target-agent",
            content="test content",
            message_type=MessageType.COMMAND,
            priority=Priority.NORMAL,
        )
        msg.session_context = mock_session_context

        # Act
        result = await message_processor._extract_session_context(msg)

        # Assert
        assert result is not None
        assert result == mock_session_context
        # Should not call SessionContextManager.get() since context is already attached
        assert message_processor._session_resolved_count == 1


class TestSessionContextGracefulFallback:
    """Test graceful fallback when session not found."""

    @pytest.mark.asyncio
    async def test_no_session_id_graceful_fallback(self, message_processor):
        """Test graceful fallback when no session_id found in message."""
        # Arrange
        msg = AgentMessage(
            from_agent="test-agent",
            to_agent="target-agent",
            content="test content",
            message_type=MessageType.COMMAND,
            priority=Priority.NORMAL,
        )

        # Act
        result = await message_processor._extract_session_context(msg)

        # Assert
        assert result is None
        # No counters should be incremented for missing session_id
        assert message_processor._session_resolved_count == 0
        assert message_processor._session_not_found_count == 0
        assert message_processor._session_error_count == 0

    @pytest.mark.asyncio
    async def test_session_not_found_graceful_fallback(self, message_processor):
        """Test graceful fallback when session context not found in store."""
        # Arrange
        msg = AgentMessage(
            from_agent="test-agent",
            to_agent="target-agent",
            content="test content",
            message_type=MessageType.COMMAND,
            priority=Priority.NORMAL,
            session_id="nonexistent-session",
        )

        # Mock the session context manager to return None (not found)
        mock_get = AsyncMock(return_value=None)
        with patch.object(message_processor._session_context_manager, "get", mock_get):
            # Act
            result = await message_processor._extract_session_context(msg)

            # Assert
            assert result is None
            assert message_processor._session_not_found_count == 1

    @pytest.mark.asyncio
    async def test_session_load_error_graceful_fallback(self, message_processor):
        """Test graceful fallback when error occurs loading session context."""
        # Arrange
        msg = AgentMessage(
            from_agent="test-agent",
            to_agent="target-agent",
            content="test content",
            message_type=MessageType.COMMAND,
            priority=Priority.NORMAL,
            session_id="error-session",
        )

        # Mock the session context manager to raise an exception
        mock_get = AsyncMock(side_effect=RuntimeError("Redis connection error"))
        with patch.object(message_processor._session_context_manager, "get", mock_get):
            # Act
            result = await message_processor._extract_session_context(msg)

            # Assert
            assert result is None
            assert message_processor._session_error_count == 1


class TestSessionContextMetrics:
    """Test metrics tracking for session resolution."""

    @pytest.mark.asyncio
    async def test_metrics_included_when_enabled(self, message_processor):
        """Test that session metrics are included when session governance is enabled."""
        # Act
        metrics = message_processor.get_metrics()

        # Assert
        assert "session_governance_enabled" in metrics
        assert metrics["session_governance_enabled"] is True
        assert "session_resolved_count" in metrics
        assert "session_not_found_count" in metrics
        assert "session_error_count" in metrics
        assert "session_resolution_rate" in metrics

    def test_metrics_when_disabled(self):
        """Test that session metrics indicate disabled when feature is off."""
        # Arrange
        config = BusConfiguration.for_testing()
        config.enable_session_governance = False
        processor = MessageProcessor(config=config, isolated_mode=False)

        # Act
        metrics = processor.get_metrics()

        # Assert
        assert "session_governance_enabled" in metrics
        assert metrics["session_governance_enabled"] is False

    @pytest.mark.asyncio
    async def test_session_resolution_rate_calculation(
        self, message_processor, mock_session_context
    ):
        """Test that session resolution rate is calculated correctly."""
        # Arrange - simulate multiple session resolutions
        msg1 = AgentMessage(
            from_agent="test-agent",
            to_agent="target-agent",
            content="test 1",
            message_type=MessageType.COMMAND,
            priority=Priority.NORMAL,
            session_id="session-1",
            tenant_id="test-tenant",  # Must match session context tenant
        )
        msg2 = AgentMessage(
            from_agent="test-agent",
            to_agent="target-agent",
            content="test 2",
            message_type=MessageType.COMMAND,
            priority=Priority.NORMAL,
            session_id="session-2",
            tenant_id="test-tenant",  # Must match session context tenant
        )
        msg3 = AgentMessage(
            from_agent="test-agent",
            to_agent="target-agent",
            content="test 3",
            message_type=MessageType.COMMAND,
            priority=Priority.NORMAL,
            session_id="session-not-found",
            tenant_id="test-tenant",  # Must match session context tenant
        )

        # Mock the session context manager (accepts session_id and tenant_id)
        async def mock_get(session_id, tenant_id):
            if session_id in ["session-1", "session-2"]:
                return mock_session_context
            return None

        with patch.object(message_processor._session_context_manager, "get", side_effect=mock_get):
            # Act
            await message_processor._extract_session_context(msg1)  # resolved
            await message_processor._extract_session_context(msg2)  # resolved
            await message_processor._extract_session_context(msg3)  # not found

            metrics = message_processor.get_metrics()

            # Assert
            assert metrics["session_resolved_count"] == 2
            assert metrics["session_not_found_count"] == 1
            assert metrics["session_resolution_rate"] == 2 / 3  # 2 out of 3 resolved


class TestSessionContextDisabled:
    """Test behavior when session governance is disabled."""

    def test_session_governance_disabled_by_config(self):
        """Test that session governance is disabled when config flag is False."""
        # Arrange
        config = BusConfiguration.for_testing()
        config.enable_session_governance = False

        # Act
        processor = MessageProcessor(config=config, isolated_mode=False)

        # Assert
        assert processor._enable_session_governance is False
        assert processor._session_context_manager is None

    def test_session_governance_disabled_in_isolated_mode(self):
        """Test that session governance is disabled in isolated mode."""
        # Arrange
        config = BusConfiguration.for_testing()
        config.enable_session_governance = True

        # Act
        processor = MessageProcessor(config=config, isolated_mode=True)

        # Assert
        assert processor._enable_session_governance is False
        assert processor._session_context_manager is None

    @pytest.mark.asyncio
    async def test_extract_session_context_returns_none_when_disabled(self):
        """Test that _extract_session_context returns None when disabled."""
        # Arrange
        config = BusConfiguration.for_testing()
        config.enable_session_governance = False
        processor = MessageProcessor(config=config, isolated_mode=False)

        msg = AgentMessage(
            from_agent="test-agent",
            to_agent="target-agent",
            content="test content",
            message_type=MessageType.COMMAND,
            priority=Priority.NORMAL,
            session_id="test-session",
        )

        # Act
        result = await processor._extract_session_context(msg)

        # Assert
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
