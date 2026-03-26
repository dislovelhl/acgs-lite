"""
ACGS-2 Enhanced Agent Bus - Deliberation Layer Feedback Tests
Constitutional Hash: 608508a9bd224290

Tests for Deliberation Layer Feedback Loop integration.
"""

import os
import sys
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# Add enhanced_agent_bus directory to path for proper package resolution
enhanced_agent_bus_dir = os.path.dirname(os.path.dirname(__file__))
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)

# Add src directory to path for core.shared imports
src_dir = os.path.dirname(os.path.dirname(os.path.dirname(enhanced_agent_bus_dir)))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# Use standard imports - these work when PYTHONPATH is properly configured
try:
    from enhanced_agent_bus.deliberation_layer.deliberation_queue import DeliberationTask
    from enhanced_agent_bus.deliberation_layer.integration import DeliberationLayer
    from enhanced_agent_bus.models import (
        CONSTITUTIONAL_HASH,
        AgentMessage,
        MessageType,
        Priority,
    )
except ImportError:
    # Fallback for when running as standalone
    from deliberation_layer.deliberation_queue import DeliberationTask  # type: ignore
    from deliberation_layer.integration import DeliberationLayer  # type: ignore
    from models import CONSTITUTIONAL_HASH, AgentMessage, MessageType, Priority  # type: ignore


class TestDeliberationFeedback:
    async def test_feedback_loop_integration(self):
        """Test that resolving a deliberation item triggers router feedback."""
        # Mock dependencies
        mock_queue = AsyncMock()
        mock_router = MagicMock()
        mock_router.update_performance_feedback = AsyncMock()
        mock_scorer = Mock()

        # Setup DeliberationLayer with mocks
        layer = DeliberationLayer(
            impact_scorer=mock_scorer,
            adaptive_router=mock_router,
            deliberation_queue=mock_queue,
            enable_redis=False,
        )

        # Mock task data
        message = AgentMessage(
            content="test",
            message_type=MessageType.TASK_REQUEST,
            from_agent="tester",
            to_agent="system",
            priority=Priority.HIGH,
        )
        task = DeliberationTask(task_id="task-123", message=message, created_at=datetime.now(UTC))

        # Configure queue mock
        mock_queue.resolve_task = AsyncMock()
        mock_queue.get_task = Mock(return_value=task)

        # Action: Resolve item
        await layer.resolve_deliberation_item(item_id="task-123", approved=True, feedback_score=0.9)

        # Assertions
        # 1. Queue should be resolved
        mock_queue.resolve_task.assert_called_with("task-123", True)

        # 2. Router should receive feedback
        # Verify call args
        call_args = mock_router.update_performance_feedback.call_args
        assert call_args is not None
        _, kwargs = call_args

        assert kwargs["message_id"] == message.message_id
        assert kwargs["actual_outcome"] == "approved"
        assert kwargs["feedback_score"] == 0.9
        assert "processing_time" in kwargs
