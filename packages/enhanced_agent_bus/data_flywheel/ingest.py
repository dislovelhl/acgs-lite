"""Normalization helpers for flywheel decision and feedback ingestion."""

from __future__ import annotations

from typing import Any, Mapping

from enhanced_agent_bus.core_models import AgentMessage
from enhanced_agent_bus.validators import ValidationResult

from .models import DecisionEvent, FeedbackEvent
from .workload_registry import build_workload_key


def build_decision_event(
    msg: AgentMessage,
    result: ValidationResult,
    *,
    service: str = "enhanced_agent_bus",
    route_or_tool: str | None = None,
    decision_kind: str | None = None,
) -> DecisionEvent:
    metadata = msg.metadata if isinstance(msg.metadata, dict) else {}
    validator_id = metadata.get("validated_by_agent") or metadata.get("independent_validator_id")
    resolved_kind = decision_kind or str(metadata.get("decision_kind") or msg.message_type.value)
    resolved_route = route_or_tool or str(
        metadata.get("route_or_tool") or metadata.get("requested_tool") or "message_processor"
    )
    workload = build_workload_key(
        tenant_id=msg.tenant_id,
        service=service,
        route_or_tool=resolved_route,
        decision_kind=resolved_kind,
        constitutional_hash=msg.constitutional_hash,
    )
    return DecisionEvent(
        decision_id=msg.message_id,
        tenant_id=msg.tenant_id,
        workload_key=workload.as_key(),
        constitutional_hash=msg.constitutional_hash,
        from_agent=msg.from_agent,
        validated_by_agent=str(validator_id) if isinstance(validator_id, str) else None,
        decision_kind=resolved_kind,
        request_context={
            "to_agent": msg.to_agent,
            "message_type": msg.message_type.value,
            "priority": msg.priority.value,
        },
        decision_payload={
            "result_valid": result.is_valid,
            "errors": list(result.errors),
            "warnings": list(result.warnings),
            "metadata": result.metadata,
        },
        latency_ms=_extract_latency_ms(result.metadata),
        outcome="allow" if result.is_valid else "deny",
        created_at=msg.created_at,
    )


def build_feedback_event(
    feedback_record: Mapping[str, Any],
    *,
    tenant_id: str,
    service: str = "api_gateway",
    route_or_tool: str = "gateway_feedback",
    decision_kind: str = "user_feedback",
    constitutional_hash: str,
) -> FeedbackEvent:
    metadata = feedback_record.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    workload = build_workload_key(
        tenant_id=tenant_id,
        service=service,
        route_or_tool=route_or_tool,
        decision_kind=decision_kind,
        constitutional_hash=constitutional_hash,
    )
    return FeedbackEvent(
        feedback_id=str(feedback_record.get("feedback_id") or ""),
        decision_id=_coerce_optional_string(feedback_record.get("decision_id")),
        tenant_id=tenant_id,
        workload_key=workload.as_key(),
        constitutional_hash=constitutional_hash,
        feedback_type=str(feedback_record.get("category") or "general"),
        outcome_status="submitted",
        comment=_coerce_optional_string(feedback_record.get("description")),
        actual_impact=None,
        metadata={
            **metadata,
            "rating": feedback_record.get("rating"),
            "submission_auth_mode": feedback_record.get("submission_auth_mode"),
            "user_id_verified": feedback_record.get("user_id_verified"),
        },
        created_at=feedback_record.get("timestamp") or feedback_record.get("created_at"),
    )


def _extract_latency_ms(metadata: object) -> float | None:
    if not isinstance(metadata, dict):
        return None
    for key in ("latency_ms", "total_latency_ms"):
        value = metadata.get(key)
        if isinstance(value, int | float):
            return float(value)
    return None


def _coerce_optional_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


__all__ = ["build_decision_event", "build_feedback_event"]
