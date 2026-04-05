"""
Integration test for AdaptiveRouter with SDPC Intent Classification.
Constitutional Hash: 608508a9bd224290
"""

from datetime import UTC, datetime, timezone

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.deliberation_layer.adaptive_router import AdaptiveRouter
from enhanced_agent_bus.deliberation_layer.intent_classifier import IntentType
from enhanced_agent_bus.models import AgentMessage, MessageStatus, MessageType, Priority


async def test_adaptive_router_intent_routing():
    router = AdaptiveRouter(impact_threshold=0.8)

    # Test Factual Intent (should have lower threshold)
    factual_msg = AgentMessage(
        message_id="msg_factual",
        from_agent="agent_1",
        to_agent="agent_2",
        content="What is the capital of Japan?",
        message_type=MessageType.QUERY,
        priority=Priority.NORMAL,
        status=MessageStatus.PENDING,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        constitutional_hash=CONSTITUTIONAL_HASH,
    )
    factual_msg.impact_score = (
        0.7  # Below 0.8, but should trigger deliberation because 0.7 >= 0.6 (FACTUAL limit)
    )

    decision = await router.route_message(factual_msg)
    assert decision["intent_type"] == IntentType.FACTUAL.value
    assert decision["lane"] == "deliberation"  # Correct based on dynamic threshold 0.6

    # Test Creative Intent (should have higher threshold)
    creative_msg = AgentMessage(
        message_id="msg_creative",
        from_agent="agent_1",
        to_agent="agent_2",
        content="Write a song about robots",
        message_type=MessageType.QUERY,
        priority=Priority.NORMAL,
        status=MessageStatus.PENDING,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        constitutional_hash=CONSTITUTIONAL_HASH,
    )
    creative_msg.impact_score = (
        0.85  # Above 0.8, but should trigger fast path because 0.85 < 0.9 (CREATIVE limit)
    )

    decision = await router.route_message(creative_msg)
    assert decision["intent_type"] == IntentType.CREATIVE.value
    assert decision["lane"] == "fast"
