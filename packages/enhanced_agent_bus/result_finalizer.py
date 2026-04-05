from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Protocol

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.data_flywheel.ingest import build_decision_event
from enhanced_agent_bus.observability.structured_logging import get_logger

from .message_processor_components import build_dlq_entry
from .models import AgentMessage, Priority, get_enum_value
from .validators import ValidationResult

logger = get_logger(__name__)


class BackgroundTaskScheduler(Protocol):
    def __call__(self, coroutine: Awaitable[object], background_tasks: set[object]) -> object: ...


class ResultFinalizer:
    """Shared result sink orchestration for MessageProcessor.

    Keeps success/failure side effects together so early rejections and strategy failures can use
    the same audit, persistence, metering, and DLQ behavior.
    """

    async def handle_successful_processing(
        self,
        *,
        msg: AgentMessage,
        result: ValidationResult,
        cache_key: str,
        latency_ms: float,
        validation_cache: object,
        clone_validation_result: Callable[[ValidationResult], ValidationResult],
        processed_counter_increment: Callable[[], None],
        schedule_governance_audit_event: Callable[[AgentMessage, ValidationResult], None],
        persist_flywheel_decision_event: Callable[[AgentMessage, ValidationResult], Awaitable[None]],
        requires_independent_validation: Callable[[AgentMessage], bool],
        record_agent_workflow_event: Callable[..., None],
        metering_hooks: object | None,
        async_metering_callback: Callable[[AgentMessage, float], Awaitable[None]],
        schedule_background_task_fn: BackgroundTaskScheduler,
        background_tasks: set[object],
    ) -> None:
        if isinstance(result.metadata, dict):
            result.metadata.setdefault("latency_ms", latency_ms)
            result.metadata.setdefault(
                "flywheel_decision_event",
                build_decision_event(msg, result).model_dump(mode="json"),
            )
        validation_cache.set(cache_key, clone_validation_result(result))
        processed_counter_increment()
        schedule_governance_audit_event(msg, result)
        await persist_flywheel_decision_event(msg, result)

        if not requires_independent_validation(msg):
            record_agent_workflow_event(
                event_type="autonomous_action",
                msg=msg,
                reason="no_independent_validation_required",
            )

        if metering_hooks:
            schedule_background_task_fn(
                async_metering_callback(msg, latency_ms),
                background_tasks,
            )

    async def handle_failed_processing(
        self,
        *,
        msg: AgentMessage,
        result: ValidationResult,
        increment_failed_count: bool,
        failed_counter_increment: Callable[[], None],
        failure_stage: str,
        extract_rejection_reason: Callable[[ValidationResult], str],
        schedule_governance_audit_event: Callable[[AgentMessage, ValidationResult], None],
        persist_flywheel_decision_event: Callable[[AgentMessage, ValidationResult], Awaitable[None]],
        record_agent_workflow_event: Callable[..., None],
        send_to_dlq: Callable[[AgentMessage, ValidationResult], Awaitable[None]],
        schedule_background_task_fn: BackgroundTaskScheduler,
        background_tasks: set[object],
    ) -> None:
        if isinstance(result.metadata, dict):
            result.metadata.setdefault("rejection_stage", failure_stage)
            result.metadata.setdefault(
                "flywheel_decision_event",
                build_decision_event(msg, result).model_dump(mode="json"),
            )
        if increment_failed_count:
            failed_counter_increment()
        rejection_reason = extract_rejection_reason(result)
        schedule_governance_audit_event(msg, result)
        await persist_flywheel_decision_event(msg, result)

        record_agent_workflow_event(
            event_type="gate_failure",
            msg=msg,
            reason=rejection_reason,
        )

        if msg.priority == Priority.CRITICAL:
            record_agent_workflow_event(
                event_type="rollback_trigger",
                msg=msg,
                reason="critical_message_rejected",
            )

        schedule_background_task_fn(send_to_dlq(msg, result), background_tasks)

    def schedule_governance_audit_event(
        self,
        *,
        msg: AgentMessage,
        result: ValidationResult,
        audit_client: object | None,
        schedule_background_task_fn: BackgroundTaskScheduler,
        background_tasks: set[object],
        emit_governance_audit_event: Callable[[AgentMessage, ValidationResult], Awaitable[None]],
    ) -> None:
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        if audit_client is None:
            return
        has_governance_artifacts = (
            "governance_decision" in metadata or "governance_receipt" in metadata
        )
        if not result.is_valid and not has_governance_artifacts:
            schedule_background_task_fn(
                emit_governance_audit_event(msg, result),
                background_tasks,
            )
            return
        if not has_governance_artifacts:
            return
        schedule_background_task_fn(
            emit_governance_audit_event(msg, result),
            background_tasks,
        )

    async def emit_governance_audit_event(
        self,
        *,
        msg: AgentMessage,
        result: ValidationResult,
        audit_client: object | None,
        extract_rejection_reason: Callable[[ValidationResult], str],
        governance_core_mode: str,
    ) -> None:
        if audit_client is None:
            return

        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        details: JSONDict = {
            "message_id": msg.message_id,
            "tenant_id": msg.tenant_id,
            "from_agent": msg.from_agent,
            "to_agent": msg.to_agent,
            "message_type": get_enum_value(msg.message_type),
            "constitutional_hash": msg.constitutional_hash,
            "result_valid": result.is_valid,
            "rejection_reason": extract_rejection_reason(result) if not result.is_valid else None,
            "rejection_stage": metadata.get("rejection_stage"),
            "governance_core_mode": metadata.get("governance_core_mode", governance_core_mode),
            "governance_decision": metadata.get("governance_decision"),
            "governance_receipt": metadata.get("governance_receipt"),
            "governance_shadow": metadata.get("governance_shadow"),
        }

        try:
            if hasattr(audit_client, "log_event"):
                await audit_client.log_event(
                    event_type="message_processor.governance_decision",
                    details=details,
                    correlation_id=msg.message_id,
                )
            elif hasattr(audit_client, "log"):
                await audit_client.log(
                    action="message_processor.governance_decision",
                    resource_type="agent_message",
                    resource_id=msg.message_id,
                    details=details,
                )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.warning(
                "governance_audit_event_failed",
                message_id=msg.message_id,
                error=str(exc),
            )

    async def persist_flywheel_decision_event(
        self,
        *,
        msg: AgentMessage,
        result: ValidationResult,
        workflow_repository: object | None,
    ) -> None:
        if workflow_repository is None:
            return

        try:
            await workflow_repository.save_decision_event(build_decision_event(msg, result))
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.warning(
                "flywheel_decision_event_persistence_failed",
                message_id=msg.message_id,
                tenant_id=msg.tenant_id,
                error=str(exc),
            )

    async def send_to_dlq(
        self,
        *,
        msg: AgentMessage,
        result: ValidationResult,
        get_dlq_redis: Callable[[], Awaitable[object]],
    ) -> None:
        try:
            import json

            client = await get_dlq_redis()
            dlq_entry = build_dlq_entry(msg, result, time.time())
            await client.lpush("acgs:dlq:messages", json.dumps(dlq_entry))
            await client.ltrim("acgs:dlq:messages", 0, 9999)
            logger.info("dlq_message_stored", message_id=msg.message_id)
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.warning(f"DLQ write failed (non-fatal): {exc}")
            raise
