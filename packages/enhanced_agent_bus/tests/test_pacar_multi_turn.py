"""
Tests for PACAR multi-turn support.
Constitutional Hash: 608508a9bd224290
"""

import pytest

pytest.importorskip("enhanced_agent_bus.sdpc")


import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.config import BusConfiguration
from enhanced_agent_bus.sdpc.conversation import MessageRole
from enhanced_agent_bus.sdpc.pacar_manager import PACARManager
from enhanced_agent_bus.sdpc.pacar_verifier import PACARVerifier

RUN_EAB_PACAR_MULTI_TURN_TESTS = (
    os.getenv("RUN_EAB_PACAR_MULTI_TURN_TESTS", "false").lower() == "true"
)
if not RUN_EAB_PACAR_MULTI_TURN_TESTS:
    pytestmark = pytest.mark.skip(
        reason=(
            "PACAR multi-turn tests disabled by default in this runtime. "
            "Set RUN_EAB_PACAR_MULTI_TURN_TESTS=true to run."
        )
    )


@pytest.fixture
def bus_config():
    return BusConfiguration(redis_url="redis://localhost:6379/0")


async def test_pacar_manager_add_message(bus_config):
    manager = PACARManager(config=bus_config)

    # Mock redis
    mock_redis = AsyncMock()
    with patch.object(PACARManager, "_get_redis", return_value=mock_redis):
        session_id = "test_session_1"
        content = "Test message"

        state = await manager.add_message(session_id, MessageRole.USER, content)

        assert state.session_id == session_id
        assert len(state.messages) == 1
        assert state.messages[0].content == content
        assert state.messages[0].role == MessageRole.USER

        # Verify redis call
        mock_redis.setex.assert_called_once()


async def test_pacar_verifier_multi_turn(bus_config):
    # Mock components
    mock_assistant = AsyncMock()
    mock_assistant.analyze_message_impact.return_value = {
        "risk_level": "low",
        "confidence": 0.9,
        "reasoning": ["Test review"],
    }
    mock_assistant.ainvoke_multi_turn.return_value = {
        "recommended_decision": "approve",
        "risk_level": "low",
        "confidence": 0.95,
        "reasoning": ["Content is safe."],
    }

    with patch(
        "enhanced_agent_bus.sdpc.pacar_verifier.get_llm_assistant", return_value=mock_assistant
    ):
        verifier = PACARVerifier(config=bus_config)

        # Mock manager
        verifier.manager = AsyncMock(spec=PACARManager)
        # Ensure get_state returns a mock ConversationState
        verifier.manager.get_state.return_value = MagicMock(messages=[])

        session_id = "test_session_multi"
        content = "Check this content"
        intent = "factual"

        result = await verifier.verify_with_context(content, intent, session_id=session_id)

        assert result["is_valid"] is True
        assert verifier.manager.add_message.call_count == 3  # User, Critique, Result

        # Check first call (user)
        verifier.manager.add_message.assert_any_call(
            session_id, MessageRole.USER, content, {"intent": intent}
        )


async def test_pacar_manager_redis_failure_fallback(bus_config):
    manager = PACARManager(config=bus_config)

    # Mock redis to fail
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = Exception("Redis connection error")
    mock_redis.setex.side_effect = Exception("Redis connection error")

    with patch.object(PACARManager, "_get_redis", return_value=mock_redis):
        session_id = "test_session_fail"

        # Should still work locally
        state = await manager.add_message(session_id, MessageRole.USER, "Hello")
        assert state.session_id == session_id
        assert len(state.messages) == 1

        # Second call should find it in local history
        state2 = await manager.get_state(session_id)
        assert state2 == state
