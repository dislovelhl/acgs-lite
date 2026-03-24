"""
Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .models import AgentMessage, get_enum_value
from .validators import ValidationResult
from .verification_orchestrator import VerificationResult

MessageT = TypeVar("MessageT")


class OPAStatsProvider(Protocol):
    def get_stats(self) -> JSONDict: ...


class WorkflowMetricsCollector(Protocol):
    def snapshot(self) -> JSONDict: ...


ValidationGateCallable = Callable[[MessageT], ValidationResult | None]
AsyncValidationGateCallable = Callable[[MessageT], Awaitable[ValidationResult | None]]
FailureCallback = Callable[[], None]


def extract_session_id_for_governance(msg: object) -> str | None:
    """Extract session_id for session governance resolution.

    Priority: headers > metadata > content.
    """
    if hasattr(msg, "headers") and msg.headers:
        raw = msg.headers.get("X-Session-ID") or msg.headers.get("x-session-id")
        session_id: str | None = str(raw) if raw else None
        if session_id:
            return session_id

    if hasattr(msg, "metadata") and isinstance(msg.metadata, dict) and "session_id" in msg.metadata:
        raw2 = msg.metadata.get("session_id")
        session_id = str(raw2) if raw2 else None
        if session_id:
            return session_id

    if hasattr(msg, "content") and isinstance(msg.content, dict) and "session_id" in msg.content:
        raw3 = msg.content.get("session_id")
        session_id = str(raw3) if raw3 else None
        if session_id:
            return session_id

    return None


def extract_session_id_for_pacar(msg: object) -> str | None:
    """Extract session_id for PACAR multi-turn context tracking.

    Priority: session_id > headers > conversation_id > content > payload.
    """
    if hasattr(msg, "session_id") and msg.session_id:
        return str(msg.session_id)
    if hasattr(msg, "headers") and msg.headers:
        raw = msg.headers.get("X-Session-ID") or msg.headers.get("x-session-id")
        session_id: str | None = str(raw) if raw else None
        if session_id:
            return session_id
    if hasattr(msg, "conversation_id") and msg.conversation_id:
        return str(msg.conversation_id)
    if hasattr(msg, "content") and isinstance(msg.content, dict):
        raw2 = msg.content.get("session_id")
        session_id = str(raw2) if raw2 else None
        if session_id:
            return session_id
    if hasattr(msg, "payload") and isinstance(msg.payload, dict):
        raw3 = msg.payload.get("session_id")
        session_id = str(raw3) if raw3 else None
        if session_id:
            return session_id
    return None


def enforce_autonomy_tier_rules(
    *,
    msg: object,
    advisory_blocked_types: frozenset[str],
) -> ValidationResult | None:
    """Apply autonomy-tier policy checks and return validation failure when blocked."""
    tier = getattr(msg, "autonomy_tier", None)
    if tier is None:
        return None

    tier_value = getattr(tier, "value", str(tier))
    message_type = getattr(msg, "message_type", None)
    msg_type_value = getattr(message_type, "value", str(message_type))
    metadata: dict[str, object] = (
        msg.metadata if isinstance(getattr(msg, "metadata", None), dict) else {}
    )  # type: ignore[assignment]

    if tier_value == "advisory":
        if msg_type_value == "command":
            return ValidationResult(
                is_valid=False,
                errors=["Advisory agent cannot execute commands"],
                metadata={"rejection_reason": "autonomy_tier_violation"},
            )
        if msg_type_value in advisory_blocked_types:
            return ValidationResult(
                is_valid=False,
                errors=[f"Advisory agent cannot send {msg_type_value} messages"],
                metadata={"rejection_reason": "autonomy_tier_violation"},
            )

    elif tier_value == "human_approved":
        validator_id = metadata.get("validated_by_agent") or metadata.get(
            "independent_validator_id"
        )
        if not isinstance(validator_id, str) or not validator_id.strip():
            return ValidationResult(
                is_valid=False,
                errors=["Human-approved tier requires independent validation evidence"],
                metadata={"rejection_reason": "autonomy_tier_violation"},
            )

    elif tier_value == "unrestricted":
        grant_id = metadata.get("unrestricted_grant_id")
        grant_authority = metadata.get("grant_authority")
        if not grant_id or not isinstance(grant_id, str) or not grant_id.strip():
            return ValidationResult(
                is_valid=False,
                errors=["UNRESTRICTED tier requires unrestricted_grant_id in metadata"],
                metadata={"rejection_reason": "autonomy_tier_violation"},
            )
        if (
            not grant_authority
            or not isinstance(grant_authority, str)
            or not grant_authority.strip()
        ):
            return ValidationResult(
                is_valid=False,
                errors=["UNRESTRICTED tier requires grant_authority in metadata"],
                metadata={"rejection_reason": "autonomy_tier_violation"},
            )

    return None


async def run_message_validation_gates(
    *,
    msg: MessageT,
    autonomy_gate: Callable[[MessageT], ValidationResult | None],
    security_scan: Callable[[MessageT], Awaitable[ValidationResult | None]],
    independent_validator_gate: Callable[[MessageT], ValidationResult | None],
    prompt_injection_gate: Callable[[MessageT], ValidationResult | None],
    increment_failure: FailureCallback,
) -> ValidationResult | None:
    autonomy_result = autonomy_gate(msg)
    if autonomy_result:
        increment_failure()
        return autonomy_result

    security_result = await security_scan(msg)
    if security_result:
        return security_result

    independent_validation_result = independent_validator_gate(msg)
    if independent_validation_result:
        increment_failure()
        return independent_validation_result

    injection_result = prompt_injection_gate(msg)
    if injection_result:
        increment_failure()
        return injection_result

    return None


def compute_message_cache_key(
    msg: AgentMessage,
    *,
    cache_hash_mode: str,
    fast_hash_available: bool,
    fast_hash_func: Callable[[str], int] | None = None,
) -> str:
    content = msg.content
    content_str = content if isinstance(content, str) else str(content)
    autonomy_tier = msg.autonomy_tier
    tier_val = get_enum_value(autonomy_tier) if autonomy_tier else "none"
    cache_dimensions = (
        f"{content_str}:{msg.constitutional_hash}:{msg.tenant_id}:"
        f"{msg.from_agent}:{get_enum_value(msg.message_type)}:{tier_val}"
    )
    if cache_hash_mode == "fast" and fast_hash_available and fast_hash_func is not None:
        return f"fast:{fast_hash_func(cache_dimensions):016x}"
    return hashlib.sha256(cache_dimensions.encode()).hexdigest()


def prepare_message_content_string(msg: AgentMessage) -> str:
    content = msg.content
    return content if isinstance(content, str) else str(content)


def merge_verification_metadata(sdpc_metadata: JSONDict, pqc_metadata: JSONDict) -> JSONDict:
    merged_metadata = dict(sdpc_metadata)
    if pqc_metadata:
        merged_metadata.update(pqc_metadata)
    return merged_metadata


def extract_pqc_failure_result(verification_result: VerificationResult) -> ValidationResult | None:
    return verification_result.pqc_result


def apply_latency_metadata(result: ValidationResult, latency_ms: float) -> None:
    result.metadata["latency_ms"] = latency_ms


def build_dlq_entry(msg: AgentMessage, result: ValidationResult, timestamp: float) -> JSONDict:
    return {
        "message_id": msg.message_id,
        "from_agent": msg.from_agent,
        "to_agent": msg.to_agent,
        "message_type": msg.message_type.value,
        "errors": result.errors,
        "timestamp": timestamp,
    }


def calculate_session_resolution_rate(
    resolved_count: int, not_found_count: int, error_count: int
) -> float:
    session_total = resolved_count + not_found_count + error_count
    return resolved_count / max(1, session_total) if session_total > 0 else 0.0


def apply_session_governance_metrics(
    metrics: JSONDict,
    *,
    enabled: bool,
    resolved_count: int,
    not_found_count: int,
    error_count: int,
    resolution_rate: float,
) -> None:
    if enabled:
        metrics.update(
            {
                "session_governance_enabled": True,
                "session_resolved_count": resolved_count,
                "session_not_found_count": not_found_count,
                "session_error_count": error_count,
                "session_resolution_rate": resolution_rate,
            }
        )
    else:
        metrics["session_governance_enabled"] = False


def enrich_metrics_with_opa_stats(metrics: JSONDict, opa_client: OPAStatsProvider | None) -> None:
    if opa_client is None or not hasattr(opa_client, "get_stats"):
        return

    try:
        opa_stats = opa_client.get_stats()
        if isinstance(opa_stats, dict):
            metrics["opa_multipath_evaluation_count"] = opa_stats.get(
                "multipath_evaluation_count", 0
            )
            metrics["opa_multipath_last_path_count"] = opa_stats.get("multipath_last_path_count", 0)
            metrics["opa_multipath_last_diversity_ratio"] = opa_stats.get(
                "multipath_last_diversity_ratio", 0.0
            )
            metrics["opa_multipath_last_support_family_count"] = opa_stats.get(
                "multipath_last_support_family_count", 0
            )
    except (AttributeError, TypeError, ValueError):
        metrics["opa_multipath_evaluation_count"] = 0
        metrics["opa_multipath_last_path_count"] = 0
        metrics["opa_multipath_last_diversity_ratio"] = 0.0
        metrics["opa_multipath_last_support_family_count"] = 0


def enrich_metrics_with_workflow_telemetry(
    metrics: JSONDict, collector: WorkflowMetricsCollector | None
) -> bool:
    if collector is None:
        return False

    workflow_summary = collector.snapshot()
    metrics.update(
        {
            "workflow_intervention_rate": workflow_summary["intervention_rate"],
            "workflow_gate_failures_total": workflow_summary["gate_failures_total"],
            "workflow_rollback_triggers_total": workflow_summary["rollback_triggers_total"],
            "workflow_autonomous_actions_total": workflow_summary["autonomous_actions_total"],
        }
    )
    return True


def extract_rejection_reason(result: ValidationResult) -> str:
    rejection_reason = "validation_failed"
    if isinstance(result.metadata, dict):
        metadata_reason = result.metadata.get("rejection_reason")
        if isinstance(metadata_reason, str) and metadata_reason:
            rejection_reason = metadata_reason
    return rejection_reason


def schedule_background_task(
    coroutine: Awaitable[object], background_tasks: set[asyncio.Task[object]]
) -> asyncio.Task[object]:
    task = asyncio.create_task(coroutine)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task
