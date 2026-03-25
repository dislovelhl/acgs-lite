"""Tests for AI Assistant Core module.

Covers AssistantConfig, ProcessingResult, AIAssistant lifecycle,
session management, metrics, health, listeners, and factory function.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.ai_assistant.core import (
    AIAssistant,
    AssistantConfig,
    AssistantState,
    ProcessingResult,
    create_assistant,
)

# ---------------------------------------------------------------------------
# AssistantConfig tests
# ---------------------------------------------------------------------------


class TestAssistantConfig:
    def test_defaults(self):
        cfg = AssistantConfig()
        assert cfg.name == "ACGS-2 Assistant"
        assert cfg.max_conversation_turns == 100
        assert cfg.session_timeout_minutes == 30
        assert cfg.enable_governance is True

    def test_to_dict(self):
        cfg = AssistantConfig(name="Test Bot")
        d = cfg.to_dict()
        assert d["name"] == "Test Bot"
        assert "constitutional_hash" in d
        assert "max_conversation_turns" in d


# ---------------------------------------------------------------------------
# ProcessingResult tests
# ---------------------------------------------------------------------------


class TestProcessingResult:
    def test_defaults(self):
        result = ProcessingResult(success=True, response_text="Hello")
        assert result.success is True
        assert result.confidence == 0.0
        assert result.entities == {}

    def test_to_dict(self):
        result = ProcessingResult(
            success=True,
            response_text="Hi",
            intent="greet",
            confidence=0.95,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["intent"] == "greet"
        assert d["confidence"] == 0.95
        assert "constitutional_hash" in d


# ---------------------------------------------------------------------------
# AIAssistant tests
# ---------------------------------------------------------------------------


class TestAIAssistant:
    def _make_assistant(self, **config_overrides):
        config = AssistantConfig(**config_overrides)
        # Mock heavy deps
        mock_integration = MagicMock()
        mock_integration.initialize = AsyncMock()
        mock_integration.shutdown = AsyncMock()
        mock_integration.validate_message = AsyncMock()
        mock_integration.check_governance = AsyncMock()
        mock_integration.execute_task = AsyncMock()

        return AIAssistant(
            config=config,
            nlu_engine=MagicMock(),
            dialog_manager=MagicMock(),
            response_generator=MagicMock(),
            integration=mock_integration,
        )

    def test_initial_state(self):
        assistant = self._make_assistant()
        assert assistant.state == AssistantState.INITIALIZED
        assert assistant.is_ready is False

    @pytest.mark.asyncio
    async def test_initialize(self):
        assistant = self._make_assistant()
        result = await assistant.initialize()
        assert result is True
        assert assistant.state == AssistantState.READY
        assert assistant.is_ready is True

    @pytest.mark.asyncio
    async def test_initialize_without_governance(self):
        assistant = self._make_assistant(enable_governance=False)
        result = await assistant.initialize()
        assert result is True
        assistant._integration.initialize.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_initialize_failure(self):
        assistant = self._make_assistant()
        assistant._integration.initialize = AsyncMock(side_effect=RuntimeError("fail"))
        result = await assistant.initialize()
        assert result is False
        assert assistant.state == AssistantState.ERROR

    @pytest.mark.asyncio
    async def test_shutdown(self):
        assistant = self._make_assistant()
        await assistant.initialize()
        await assistant.shutdown()
        assert assistant.state == AssistantState.SHUTDOWN

    @pytest.mark.asyncio
    async def test_shutdown_without_governance(self):
        assistant = self._make_assistant(enable_governance=False)
        await assistant.initialize()
        await assistant.shutdown()
        assistant._integration.shutdown.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_message_not_ready(self):
        assistant = self._make_assistant()
        result = await assistant.process_message("user1", "hello")
        assert result.success is False
        assert "not ready" in result.response_text

    # --- Session management ---

    @pytest.mark.asyncio
    async def test_get_or_create_context_new(self):
        assistant = self._make_assistant()
        ctx = await assistant._get_or_create_context("user1", "session1")
        assert ctx.user_id == "user1"
        assert ctx.session_id == "session1"

    @pytest.mark.asyncio
    async def test_get_or_create_context_existing(self):
        assistant = self._make_assistant()
        ctx1 = await assistant._get_or_create_context("user1", "session1")
        ctx2 = await assistant._get_or_create_context("user1", "session1")
        assert ctx1 is ctx2

    @pytest.mark.asyncio
    async def test_get_or_create_context_expired(self):
        assistant = self._make_assistant(session_timeout_minutes=0)
        ctx1 = await assistant._get_or_create_context("user1", "session1")
        # Force activity time far in the past
        ctx1.last_activity = datetime.now(UTC) - timedelta(minutes=10)
        ctx2 = await assistant._get_or_create_context("user1", "session1")
        assert ctx2 is not ctx1

    @pytest.mark.asyncio
    async def test_get_or_create_context_auto_session_id(self):
        assistant = self._make_assistant()
        ctx = await assistant._get_or_create_context("user1")
        assert ctx.session_id.startswith("user1_")

    def test_get_session(self):
        assistant = self._make_assistant()
        assert assistant.get_session("nonexistent") is None

    def test_end_session(self):
        assistant = self._make_assistant()
        # Manually insert a session
        mock_ctx = MagicMock()
        mock_ctx.user_id = "user1"
        assistant._active_sessions["s1"] = mock_ctx
        assert assistant.end_session("s1") is True
        assert assistant.end_session("s1") is False

    def test_get_user_sessions(self):
        assistant = self._make_assistant()
        mock_ctx1 = MagicMock()
        mock_ctx1.user_id = "user1"
        mock_ctx2 = MagicMock()
        mock_ctx2.user_id = "user2"
        assistant._active_sessions["s1"] = mock_ctx1
        assistant._active_sessions["s2"] = mock_ctx2
        sessions = assistant.get_user_sessions("user1")
        assert len(sessions) == 1

    def test_clear_expired_sessions(self):
        assistant = self._make_assistant(session_timeout_minutes=5)
        mock_ctx = MagicMock()
        mock_ctx.last_activity = datetime.now(UTC) - timedelta(minutes=10)
        assistant._active_sessions["s1"] = mock_ctx
        cleared = assistant.clear_expired_sessions()
        assert cleared == 1
        assert len(assistant._active_sessions) == 0

    def test_clear_expired_sessions_none_expired(self):
        assistant = self._make_assistant(session_timeout_minutes=60)
        mock_ctx = MagicMock()
        mock_ctx.last_activity = datetime.now(UTC)
        assistant._active_sessions["s1"] = mock_ctx
        cleared = assistant.clear_expired_sessions()
        assert cleared == 0

    # --- Listeners ---

    def test_add_remove_listener(self):
        assistant = self._make_assistant()
        listener = MagicMock()
        assistant.add_listener(listener)
        assert listener in assistant._listeners
        assistant.remove_listener(listener)
        assert listener not in assistant._listeners

    def test_remove_nonexistent_listener(self):
        assistant = self._make_assistant()
        listener = MagicMock()
        assistant.remove_listener(listener)  # should not raise

    @pytest.mark.asyncio
    async def test_notify_message_received(self):
        assistant = self._make_assistant()
        listener = MagicMock()
        listener.on_message_received = AsyncMock()
        assistant.add_listener(listener)
        ctx = MagicMock()
        await assistant._notify_message_received(ctx, "hello")
        listener.on_message_received.assert_awaited_once_with(ctx, "hello")

    @pytest.mark.asyncio
    async def test_notify_message_received_error_handled(self):
        assistant = self._make_assistant()
        listener = MagicMock()
        listener.on_message_received = AsyncMock(side_effect=RuntimeError("fail"))
        assistant.add_listener(listener)
        ctx = MagicMock()
        # Should not raise
        await assistant._notify_message_received(ctx, "hello")

    @pytest.mark.asyncio
    async def test_notify_response_generated(self):
        assistant = self._make_assistant()
        listener = MagicMock()
        listener.on_response_generated = AsyncMock()
        assistant.add_listener(listener)
        ctx = MagicMock()
        result = ProcessingResult(success=True, response_text="resp")
        await assistant._notify_response_generated(ctx, "resp", result)
        listener.on_response_generated.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notify_error(self):
        assistant = self._make_assistant()
        listener = MagicMock()
        listener.on_error = AsyncMock()
        assistant.add_listener(listener)
        ctx = MagicMock()
        await assistant._notify_error(ctx, RuntimeError("oops"))
        listener.on_error.assert_awaited_once()

    # --- Metrics & Health ---

    def test_get_metrics(self):
        assistant = self._make_assistant()
        metrics = assistant.get_metrics()
        assert metrics["state"] == "initialized"
        assert metrics["total_messages_processed"] == 0
        assert metrics["uptime_seconds"] is None

    @pytest.mark.asyncio
    async def test_get_metrics_with_uptime(self):
        assistant = self._make_assistant()
        await assistant.initialize()
        metrics = assistant.get_metrics()
        assert metrics["uptime_seconds"] is not None
        assert metrics["uptime_seconds"] >= 0

    def test_get_health_not_ready(self):
        assistant = self._make_assistant()
        health = assistant.get_health()
        assert health["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_get_health_ready(self):
        assistant = self._make_assistant()
        await assistant.initialize()
        health = assistant.get_health()
        assert health["status"] == "healthy"
        assert "constitutional_hash" in health


# ---------------------------------------------------------------------------
# create_assistant factory
# ---------------------------------------------------------------------------


class TestCreateAssistant:
    @pytest.mark.asyncio
    async def test_create_default(self):
        with patch("enhanced_agent_bus.ai_assistant.core.AgentBusIntegration") as MockIntegration:
            mock_instance = MagicMock()
            mock_instance.initialize = AsyncMock()
            MockIntegration.return_value = mock_instance

            assistant = await create_assistant(name="TestBot", enable_governance=True)
            assert assistant.config.name == "TestBot"

    @pytest.mark.asyncio
    async def test_create_with_agent_bus(self):
        mock_bus = MagicMock()
        with patch("enhanced_agent_bus.ai_assistant.core.AgentBusIntegration") as MockIntegration:
            mock_instance = MagicMock()
            mock_instance.initialize = AsyncMock()
            MockIntegration.return_value = mock_instance

            assistant = await create_assistant(agent_bus=mock_bus)
            MockIntegration.assert_called_once_with(agent_bus=mock_bus)
