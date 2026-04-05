"""Tests for message route metadata normalization and validator evidence propagation.

Constitutional Hash: 608508a9bd224290
"""

from enhanced_agent_bus.api.routes.messages import (
    _build_agent_message,
    _merge_validator_headers_into_metadata,
)
from enhanced_agent_bus.api_models import MessageRequest
from enhanced_agent_bus.models import MessageType, Priority


def test_merge_validator_headers_into_metadata_adds_missing_fields() -> None:
    request = MessageRequest(content="governance action", sender="agent-proposer", metadata={})

    metadata = _merge_validator_headers_into_metadata(
        message_request=request,
        validated_by_agent="agent-validator",
        independent_validator_id="validator-01",
        validation_stage="independent",
    )

    assert metadata["validated_by_agent"] == "agent-validator"
    assert metadata["independent_validator_id"] == "validator-01"
    assert metadata["validation_stage"] == "independent"


def test_merge_validator_headers_into_metadata_preserves_body_values() -> None:
    request = MessageRequest(
        content="governance action",
        sender="agent-proposer",
        metadata={
            "validated_by_agent": "validator-from-body",
            "validation_stage": "independent",
        },
    )

    metadata = _merge_validator_headers_into_metadata(
        message_request=request,
        validated_by_agent="validator-from-header",
        independent_validator_id="validator-01",
        validation_stage="ignored-stage",
    )

    assert metadata["validated_by_agent"] == "validator-from-body"
    assert metadata["validation_stage"] == "independent"
    assert metadata["independent_validator_id"] == "validator-01"


def test_build_agent_message_sets_metadata_payload_and_impact_score() -> None:
    request = MessageRequest(
        content="high impact action",
        sender="agent-proposer",
        recipient="agent-executor",
    )
    metadata = {
        "impact_score": 0.92,
        "validated_by_agent": "agent-validator",
        "validation_stage": "independent",
    }

    message = _build_agent_message(
        message_request=request,
        message_metadata=metadata,
        tenant_id="tenant-001",
        msg_type=MessageType.GOVERNANCE_REQUEST,
        priority=Priority.HIGH,
        resolved_session_id="session-abc",
    )

    assert message.metadata == metadata
    assert message.payload == metadata
    assert message.metadata is not message.payload
    assert message.impact_score == 0.92


def test_build_agent_message_ignores_non_numeric_impact_score() -> None:
    request = MessageRequest(content="test", sender="agent-proposer")
    metadata = {"impact_score": "not-a-number"}

    message = _build_agent_message(
        message_request=request,
        message_metadata=metadata,
        tenant_id="tenant-001",
        msg_type=MessageType.COMMAND,
        priority=Priority.MEDIUM,
        resolved_session_id=None,
    )

    assert message.impact_score is None
