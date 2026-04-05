"""
Tests for ACGS-AI-007: Safe Autonomy Tiers
Constitutional Hash: 608508a9bd224290

Tests for AutonomyTier enum enforcement in the message processing pipeline.
"""

import pytest

from enhanced_agent_bus.enums import AutonomyTier, MessageType
from enhanced_agent_bus.message_processor import MessageProcessor
from enhanced_agent_bus.models import AgentMessage


class TestAutonomyTiers:
    """Test enforcement of autonomy tiers."""

    @pytest.fixture
    def processor(self):
        return MessageProcessor(isolated_mode=True)

    async def test_advisory_agent_blocked_execution(self, processor):
        """Advisory agents cannot execute commands."""
        msg = AgentMessage(
            from_agent="advisor_gpt",
            message_type=MessageType.COMMAND,
            content={"action": "refresh_cache", "target": "users"},
            autonomy_tier=AutonomyTier.ADVISORY,
        )

        result = await processor.process(msg)
        assert not result.is_valid
        assert result.metadata["rejection_reason"] == "autonomy_tier_violation"
        assert "Advisory agent cannot execute commands" in result.errors[0]

    async def test_advisory_agent_allowed_query(self, processor):
        """Advisory agents can send queries."""
        msg = AgentMessage(
            from_agent="advisor_gpt",
            message_type=MessageType.QUERY,
            content={"query": "list_active_sessions"},
            autonomy_tier=AutonomyTier.ADVISORY,
        )

        result = await processor.process(msg)
        assert result.is_valid

    async def test_human_approved_blocked_without_validator(self, processor):
        """Human-approved tier requires validation evidence."""
        msg = AgentMessage(
            from_agent="risky_bot",
            message_type=MessageType.COMMAND,
            content={"action": "publish_release", "version": "2.0.0"},
            autonomy_tier=AutonomyTier.HUMAN_APPROVED,
        )

        result = await processor.process(msg)
        assert not result.is_valid
        assert result.metadata["rejection_reason"] == "autonomy_tier_violation"
        assert "Human-approved tier requires independent validation" in result.errors[0]

    async def test_human_approved_allowed_with_validator(self, processor):
        """Human-approved tier allowed with validator evidence."""
        msg = AgentMessage(
            from_agent="risky_bot",
            message_type=MessageType.COMMAND,
            content={"action": "publish_release", "version": "2.0.0"},
            autonomy_tier=AutonomyTier.HUMAN_APPROVED,
            metadata={"validated_by_agent": "human_reviewer"},
        )

        result = await processor.process(msg)
        assert result.is_valid

    async def test_bounded_agent_allowed(self, processor):
        """Bounded agents can execute (subject to other policies)."""
        msg = AgentMessage(
            from_agent="safe_bot",
            message_type=MessageType.COMMAND,
            content={"action": "refresh_cache"},
            autonomy_tier=AutonomyTier.BOUNDED,
        )

        result = await processor.process(msg)
        assert result.is_valid
