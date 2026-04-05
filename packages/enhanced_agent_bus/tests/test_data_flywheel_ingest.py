from __future__ import annotations

from datetime import UTC, datetime

from enhanced_agent_bus.data_flywheel.ingest import build_decision_event, build_feedback_event
from enhanced_agent_bus.models import AgentMessage, MessageType
from enhanced_agent_bus.validators import ValidationResult


def test_build_decision_event_uses_validator_metadata_and_message_identity() -> None:
    message = AgentMessage(
        message_id="msg-1",
        tenant_id="tenant-a",
        from_agent="proposer",
        to_agent="validator",
        message_type=MessageType.GOVERNANCE_REQUEST,
        metadata={
            "validated_by_agent": "validator-1",
            "route_or_tool": "policy_router",
            "decision_kind": "policy_evaluation",
        },
        created_at=datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC),
    )
    result = ValidationResult(
        is_valid=True,
        metadata={"latency_ms": 12.5},
    )

    event = build_decision_event(message, result)

    assert event.decision_id == "msg-1"
    assert event.validated_by_agent == "validator-1"
    assert event.workload_key.startswith("tenant-a/enhanced_agent_bus/policy_router/")
    assert event.outcome == "allow"
    assert event.latency_ms == 12.5


def test_build_feedback_event_uses_public_tenant_bucket_and_feedback_fields() -> None:
    event = build_feedback_event(
        {
            "feedback_id": "fb-1",
            "description": "Looks wrong",
            "rating": 2,
            "submission_auth_mode": "anonymous",
            "user_id_verified": False,
            "metadata": {"page": "/governance"},
            "timestamp": datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC),
        },
        tenant_id="public",
        constitutional_hash="608508a9bd224290",
    )

    assert event.feedback_id == "fb-1"
    assert event.tenant_id == "public"
    assert event.feedback_type == "general"
    assert event.metadata["rating"] == 2
    assert event.workload_key.startswith("public/api_gateway/gateway_feedback/")
