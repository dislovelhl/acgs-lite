"""
ACGS-2 Enhanced Agent Bus Messages Routes
Constitutional Hash: cdd01ef066bc6cf2

This module provides message sending and status endpoints.
"""

from __future__ import annotations

import os
import re
from typing import Protocol, cast

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from src.core.shared.security.auth import UserClaims, get_current_user

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.models import AgentMessage, MessageType, Priority

from ...api_exceptions import correlation_id_var
from ...api_models import (
    ErrorResponse,
    MessageRequest,
    MessageResponse,
    MessageStatusEnum,
    MessageTypeEnum,
    ServiceUnavailableResponse,
)
from ..dependencies import get_agent_bus
from ..middleware import logger
from ..rate_limiting import limiter
from ._tenant_auth import DEV_ENVIRONMENTS

router = APIRouter()
MESSAGE_ID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
DEV_STATUS_TIMESTAMP = "2024-01-01T00:00:00Z"
DEV_STATUS_NOTE = "Development mode - simplified response"


class ProcessResultProtocol(Protocol):
    is_valid: bool


class MessageProcessorProtocol(Protocol):
    async def process(self, message: AgentMessage) -> ProcessResultProtocol: ...


# Message handlers mapping
MESSAGE_HANDLERS: dict[MessageTypeEnum, str] = {
    MessageTypeEnum.COMMAND: "process_command",
    MessageTypeEnum.QUERY: "process_query",
    MessageTypeEnum.RESPONSE: "process_response",
    MessageTypeEnum.EVENT: "process_event",
    MessageTypeEnum.NOTIFICATION: "process_notification",
    MessageTypeEnum.HEARTBEAT: "process_heartbeat",
    MessageTypeEnum.GOVERNANCE_REQUEST: "process_governance_request",
    MessageTypeEnum.GOVERNANCE_RESPONSE: "process_governance_response",
    MessageTypeEnum.CONSTITUTIONAL_VALIDATION: "process_constitutional_validation",
    MessageTypeEnum.TASK_REQUEST: "process_task_request",
    MessageTypeEnum.TASK_RESPONSE: "process_task_response",
    MessageTypeEnum.AUDIT_LOG: "process_audit_log",
}

_ENVIRONMENT = os.environ.get("ENVIRONMENT", "").lower()


def _resolve_message_type(raw_message_type: object) -> MessageType:
    """Resolve API message type to internal MessageType with safe fallback."""
    normalized = str(getattr(raw_message_type, "value", raw_message_type)).lower()
    try:
        return cast(MessageType, MessageType(normalized))
    except ValueError:
        return cast(MessageType, getattr(MessageType, "NOTIFICATION", MessageType.COMMAND))


def _resolve_priority(raw_priority: object) -> Priority:
    """Resolve API priority to internal Priority with MEDIUM fallback."""
    normalized = str(getattr(raw_priority, "value", raw_priority)).upper()
    try:
        return cast(Priority, Priority[normalized])
    except (KeyError, ValueError):
        return cast(Priority, Priority.MEDIUM)


def _resolve_session_id(
    header_session_id: str | None, message_request: MessageRequest
) -> str | None:
    """Resolve session id from header/body/metadata in priority order."""
    return (
        header_session_id
        or message_request.session_id
        or (message_request.metadata or {}).get("session_id")
    )


def _message_type_value(raw_message_type: object) -> str:
    """Get string value for API message type enum or literal."""
    return str(getattr(raw_message_type, "value", raw_message_type))


def _merge_validator_headers_into_metadata(
    message_request: MessageRequest,
    validated_by_agent: str | None,
    independent_validator_id: str | None,
    validation_stage: str | None,
) -> JSONDict:
    """Merge independent-validator headers into message metadata without overwriting body fields."""
    metadata: JSONDict = dict(message_request.metadata or {})
    validated_by_agent_value = validated_by_agent.strip() if validated_by_agent else ""
    independent_validator_id_value = (
        independent_validator_id.strip() if independent_validator_id else ""
    )
    validation_stage_value = validation_stage.strip() if validation_stage else ""

    if validated_by_agent_value and "validated_by_agent" not in metadata:
        metadata["validated_by_agent"] = validated_by_agent_value
    if independent_validator_id_value and "independent_validator_id" not in metadata:
        metadata["independent_validator_id"] = independent_validator_id_value
    if validation_stage_value and "validation_stage" not in metadata:
        metadata["validation_stage"] = validation_stage_value
    return metadata


def _resolve_impact_score(metadata: JSONDict) -> float | None:
    """Extract optional impact score from metadata when provided."""
    raw_score = metadata.get("impact_score")
    if raw_score is None:
        return None
    try:
        return float(raw_score)
    except (TypeError, ValueError):
        return None


def _record_failed_background_task(
    message_id: str, error: Exception, app_state: object | None = None
) -> None:
    """Record background processing failure when app state tracking is available."""
    if not (app_state and hasattr(app_state, "failed_tasks")):
        return
    app_state.failed_tasks.append(  # type: ignore[attr-defined]
        {"message_id": message_id, "error": str(error)}
    )


def _is_development_environment() -> bool:
    """Return True when endpoint can use development-only behavior."""
    return _ENVIRONMENT in DEV_ENVIRONMENTS


def _validate_tenant_consistency(message_request: MessageRequest, tenant_id: str) -> None:
    """Require tenant in payload (when present) to match authenticated tenant."""
    if not message_request.tenant_id or message_request.tenant_id == tenant_id:
        return
    raise HTTPException(
        status_code=400,
        detail=(
            f"tenant_id in body '{message_request.tenant_id}' must match "
            f"X-Tenant-ID header '{tenant_id}'"
        ),
    )


def _build_agent_message(
    message_request: MessageRequest,
    message_metadata: JSONDict,
    tenant_id: str,
    msg_type: MessageType,
    priority: Priority,
    resolved_session_id: str | None,
) -> AgentMessage:
    """Construct internal AgentMessage model and map failures to HTTP 500."""
    try:
        return AgentMessage(
            content={"text": message_request.content},
            message_type=msg_type,
            priority=priority,
            from_agent=message_request.sender,
            to_agent=message_request.recipient or "",
            tenant_id=tenant_id,
            payload=dict(message_metadata),
            metadata=dict(message_metadata),
            conversation_id=resolved_session_id or message_request.session_id,
            session_id=resolved_session_id,
            impact_score=_resolve_impact_score(message_metadata),
        )
    except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
        logger.error(f"Error sending message: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Message processing failed",
        ) from e


async def _process_message_async(
    message: AgentMessage,
    bus: MessageProcessorProtocol | dict[str, str],
    app_state: object | None = None,
) -> None:
    """Process queued message in background when real processor is available."""
    try:
        if isinstance(bus, dict):
            logger.warning("Agent bus is in mock mode, skipping real processing")
            return

        result = await bus.process(message)
        logger.info("Message %s processed: valid=%s", message.message_id, result.is_valid)
    except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
        logger.error(
            "Background processing failed for %s: %s",
            message.message_id,
            e,
            exc_info=True,
        )
        _record_failed_background_task(message.message_id, e, app_state)


def _development_status_response(message_id: str, tenant_id: str) -> JSONDict:
    """Build development-mode response for message status endpoint."""
    return {
        "message_id": message_id,
        "tenant_id": tenant_id,
        "status": "processed",
        "timestamp": DEV_STATUS_TIMESTAMP,
        "details": {"note": DEV_STATUS_NOTE},
    }


@router.post(
    "/api/v1/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("10/minute")
async def send_message(
    request: Request,
    background_tasks: BackgroundTasks,
    message_request: MessageRequest = Body(...),
    session_id: str | None = Header(None, alias="X-Session-ID"),
    validated_by_agent: str | None = Header(None, alias="X-Validated-By-Agent"),
    independent_validator_id: str | None = Header(None, alias="X-Independent-Validator-ID"),
    validation_stage: str | None = Header(None, alias="X-Validation-Stage"),
    user: UserClaims = Depends(get_current_user),
    bus: MessageProcessorProtocol | dict[str, str] = Depends(get_agent_bus),
) -> MessageResponse:
    """
    Send a message to the agent bus for processing.

    Supports all 12 message types:
    - COMMAND, QUERY, RESPONSE, EVENT, NOTIFICATION, HEARTBEAT
    - GOVERNANCE_REQUEST, GOVERNANCE_RESPONSE, CONSTITUTIONAL_VALIDATION
    - TASK_REQUEST, TASK_RESPONSE, AUDIT_LOG

    Messages are processed asynchronously. Returns HTTP 202 with message_id
    for tracking.
    """
    tenant_id = user.tenant_id
    correlation_id = correlation_id_var.get()

    _validate_tenant_consistency(message_request, tenant_id)

    msg_type = _resolve_message_type(message_request.message_type)
    priority = _resolve_priority(message_request.priority)
    resolved_session_id = _resolve_session_id(session_id, message_request)
    message_type_value = _message_type_value(message_request.message_type)
    message_metadata = _merge_validator_headers_into_metadata(
        message_request=message_request,
        validated_by_agent=validated_by_agent,
        independent_validator_id=independent_validator_id,
        validation_stage=validation_stage,
    )

    msg = _build_agent_message(
        message_request,
        message_metadata,
        tenant_id,
        msg_type,
        priority,
        resolved_session_id,
    )
    background_tasks.add_task(_process_message_async, msg, bus, request.app.state)

    return MessageResponse(
        message_id=msg.message_id,
        status=MessageStatusEnum.ACCEPTED,
        timestamp=msg.created_at.isoformat(),
        correlation_id=correlation_id,
        details={
            "session_id": msg.conversation_id,
            "message_type": message_type_value,
        },
    )


@router.get(
    "/api/v1/messages/{message_id}",
    response_model=MessageResponse,
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Not Found - Message with specified ID not found",
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal Server Error - Failed to retrieve message status",
        },
        503: {
            "model": ServiceUnavailableResponse,
            "description": "Service Unavailable - Agent bus not initialized",
        },
    },
    summary="Get message status",
    tags=["Messages"],
)
@limiter.limit("30/minute")
async def get_message_status(
    request: Request,
    message_id: str,
    user: UserClaims = Depends(get_current_user),
    _bus: MessageProcessorProtocol | dict[str, str] = Depends(get_agent_bus),
) -> JSONDict:
    """Get the status of a previously submitted message."""
    tenant_id = user.tenant_id
    if not MESSAGE_ID_PATTERN.match(message_id):
        raise HTTPException(status_code=400, detail="Invalid message ID format")

    if not _is_development_environment():
        raise HTTPException(
            status_code=501,
            detail=(
                "Message status lookup requires message persistence, "
                "which is not yet implemented. "
                "This endpoint is only available in development environments."
            ),
        )

    # NOTE: Tenant ownership verification requires message persistence (not yet
    # implemented). When persistence is added, this MUST verify
    # message.tenant_id == tenant_id and return 404 for cross-tenant access to
    # prevent IDOR vulnerabilities. For now, the dev response includes tenant_id
    # to establish the guard pattern.
    return _development_status_response(message_id, tenant_id)


__all__ = [
    "MESSAGE_HANDLERS",
    "get_message_status",
    "router",
    "send_message",
]
