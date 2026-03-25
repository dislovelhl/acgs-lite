"""WorkOS webhook endpoints for SSO event ingestion.

Constitutional Hash: 608508a9bd224290
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request as StarletteRequest

from src.core.services.api_gateway.workos_event_ingestion import (
    WorkOSEventForwardingError,
    get_workos_ingestion_service,
)
from src.core.shared.auth.workos import (
    WORKOS_SIGNATURE_HEADER,
    WorkOSConfigurationError,
    WorkOSWebhookVerificationError,
    parse_and_verify_workos_webhook,
)
from src.core.shared.config import settings
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class WorkOSWebhookAck(BaseModel):
    """Acknowledgement payload for WorkOS webhooks."""

    received: bool = Field(True)
    event_id: str
    event_type: str
    duplicate: bool = False
    forwarded: bool = True
    audit_entry_hash: str | None = None


@router.post("/webhooks/events", response_model=WorkOSWebhookAck)
async def workos_webhook_events(req: StarletteRequest) -> WorkOSWebhookAck:
    """Verify and accept WorkOS webhook events."""
    if not settings.sso.workos_enabled:
        raise HTTPException(status_code=503, detail="WorkOS integration is not enabled.")

    signature_header = req.headers.get(WORKOS_SIGNATURE_HEADER)
    if not signature_header:
        raise HTTPException(
            status_code=400, detail=f"Missing required header: {WORKOS_SIGNATURE_HEADER}"
        )

    payload_bytes = await req.body()

    try:
        event = parse_and_verify_workos_webhook(
            event_body=payload_bytes,
            event_signature=signature_header,
        )
    except WorkOSConfigurationError as exc:
        logger.error("WorkOS webhook configuration error", extra={"error_type": type(exc).__name__})
        raise HTTPException(status_code=503, detail="WorkOS webhook configuration error.") from exc
    except WorkOSWebhookVerificationError as exc:
        raise HTTPException(status_code=401, detail="Invalid WorkOS webhook signature.") from exc

    ingestion_service = get_workos_ingestion_service()
    try:
        ingestion_result = await ingestion_service.ingest_event(event)
    except WorkOSEventForwardingError as exc:
        logger.error("WorkOS event forwarding failed", extra={"error_type": type(exc).__name__})
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    logger.info(
        "Received WorkOS webhook event",
        extra={
            "event_id": event.id,
            "event_type": event.event,
            "duplicate": ingestion_result.duplicate,
            "forwarded": ingestion_result.forwarded,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
    )

    return WorkOSWebhookAck(
        event_id=event.id,
        event_type=event.event,
        duplicate=ingestion_result.duplicate,
        forwarded=ingestion_result.forwarded,
        audit_entry_hash=ingestion_result.audit_entry_hash,
    )
