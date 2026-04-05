from __future__ import annotations

from datetime import UTC, datetime

from enhanced_agent_bus.core_models import AgentMessage, RoutingContext
from enhanced_agent_bus.enums import MessageType, Priority


class TestAgentMessageRoundTrip:
    def test_to_dict_raw_preserves_routing_and_transport_fields(self) -> None:
        created_at = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
        updated_at = datetime(2026, 4, 2, 12, 5, tzinfo=UTC)
        expires_at = datetime(2026, 4, 2, 13, 0, tzinfo=UTC)
        message = AgentMessage(
            message_id="msg-1",
            conversation_id="conv-1",
            content={"body": "hello"},
            payload={"task": "review"},
            from_agent="planner",
            to_agent="validator",
            sender_id="planner-session",
            message_type=MessageType.GOVERNANCE_REQUEST,
            routing=RoutingContext(
                source_agent_id="planner",
                target_agent_id="validator",
                routing_key="governance.review",
                routing_tags=["tenant:t1", "urgent"],
                retry_count=1,
                max_retries=5,
                timeout_ms=9000,
                constitutional_hash="route-hash",
            ),
            headers={"x-request-id": "req-1"},
            tenant_id="tenant-1",
            security_context={"classification": "restricted"},
            priority=Priority.HIGH,
            constitutional_hash="msg-hash",
            constitutional_validated=True,
            metadata={"validated_by_agent": "validator-2"},
            session_id="session-123",
            payload_hmac="abc123",
            requested_tool="deliberate",
            created_at=created_at,
            updated_at=updated_at,
            expires_at=expires_at,
            impact_score=0.92,
            performance_metrics={"latency_ms": 14.2},
        )

        restored = AgentMessage.from_dict(message.to_dict_raw())

        assert restored.payload == {"task": "review"}
        assert restored.sender_id == "planner-session"
        assert restored.headers == {"x-request-id": "req-1"}
        assert restored.security_context == {"classification": "restricted"}
        assert restored.routing is not None
        assert restored.routing.routing_key == "governance.review"
        assert restored.routing.routing_tags == ["tenant:t1", "urgent"]
        assert restored.constitutional_hash == "msg-hash"
        assert restored.constitutional_validated is True
        assert restored.impact_score == 0.92
        assert restored.created_at == created_at
        assert restored.updated_at == updated_at
        assert restored.expires_at == expires_at
