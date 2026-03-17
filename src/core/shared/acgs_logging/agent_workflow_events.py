"""
Standardized agent-workflow telemetry events.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

logger = get_logger(__name__)


class AgentWorkflowEventType(StrEnum):
    """Canonical event taxonomy for agent-workflow telemetry."""

    INTERVENTION = "intervention"
    GATE_FAILURE = "gate_failure"
    ROLLBACK_TRIGGER = "rollback_trigger"
    AUTONOMOUS_ACTION = "autonomous_action"


@dataclass(frozen=True)
class AgentWorkflowEvent:
    """Structured event payload for agent-workflow telemetry."""

    event_type: AgentWorkflowEventType
    tenant_id: str
    source: str
    reason: str
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )


def emit_agent_workflow_event(event: AgentWorkflowEvent) -> None:
    """Emit a standardized JSON log event for workflow telemetry."""
    payload: JSONDict = {
        "event_name": "agent_workflow_telemetry",
        "event_type": event.event_type.value,
        "tenant_id": event.tenant_id,
        "source": event.source,
        "reason": event.reason,
        "metadata": event.metadata,
        "constitutional_hash": event.constitutional_hash,
        "timestamp_utc": event.timestamp_utc,
    }
    logger.info(json.dumps(payload, default=str))


def create_agent_workflow_event(
    *,
    event_type: AgentWorkflowEventType,
    tenant_id: str,
    source: str,
    reason: str,
    metadata: JSONDict | None = None,
) -> AgentWorkflowEvent:
    """Factory helper with sensible defaults for optional metadata."""
    return AgentWorkflowEvent(
        event_type=event_type,
        tenant_id=tenant_id,
        source=source,
        reason=reason,
        metadata=metadata or {},
    )


def parse_agent_workflow_event_type(value: str) -> AgentWorkflowEventType:
    """Parse string input into canonical workflow event type."""
    normalized = value.strip().lower()
    alias_map = {
        "intervention": AgentWorkflowEventType.INTERVENTION,
        "gate_failure": AgentWorkflowEventType.GATE_FAILURE,
        "gate-failure": AgentWorkflowEventType.GATE_FAILURE,
        "rollback_trigger": AgentWorkflowEventType.ROLLBACK_TRIGGER,
        "rollback-trigger": AgentWorkflowEventType.ROLLBACK_TRIGGER,
        "autonomous_action": AgentWorkflowEventType.AUTONOMOUS_ACTION,
        "autonomous-action": AgentWorkflowEventType.AUTONOMOUS_ACTION,
    }
    if normalized not in alias_map:
        raise ACGSValidationError(
            f"Unsupported agent workflow event type: {value}",
            error_code="WORKFLOW_EVENT_TYPE_UNSUPPORTED",
        )
    return alias_map[normalized]


def event_to_dict(event: AgentWorkflowEvent) -> JSONDict:
    """Convert event dataclass to dictionary for API responses/tests."""
    return {
        "event_type": event.event_type.value,
        "tenant_id": event.tenant_id,
        "source": event.source,
        "reason": event.reason,
        "metadata": event.metadata,
        "constitutional_hash": event.constitutional_hash,
        "timestamp_utc": event.timestamp_utc,
    }


__all__ = [
    "AgentWorkflowEvent",
    "AgentWorkflowEventType",
    "create_agent_workflow_event",
    "emit_agent_workflow_event",
    "event_to_dict",
    "parse_agent_workflow_event_type",
]
