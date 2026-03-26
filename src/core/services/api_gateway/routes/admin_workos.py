"""Administrative WorkOS endpoints for SSO operations.

Constitutional Hash: 608508a9bd224290
"""

import re
from typing import cast
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from src.core.shared.auth.workos import (
    WorkOSAPIError,
    WorkOSConfigurationError,
    WorkOSPortalIntent,
    generate_workos_admin_portal_link,
    is_workos_enabled,
    list_workos_events,
)
from src.core.shared.config import settings
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

from .admin_sso import get_current_admin

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/admin/sso/workos", tags=["Admin WorkOS"])

VALID_WORKOS_PORTAL_INTENTS: set[str] = {
    "audit_logs",
    "certificate_renewal",
    "domain_verification",
    "dsync",
    "log_streams",
    "sso",
}


class WorkOSPortalLinkRequest(BaseModel):
    """Request body for generating a WorkOS Admin Portal link."""

    organization_id: str = Field(..., min_length=3, max_length=128)
    intent: WorkOSPortalIntent | None = Field(None)
    return_url: str | None = Field(None, max_length=2048)
    success_url: str | None = Field(None, max_length=2048)
    intent_options: JSONDict | None = Field(None)

    @field_validator("organization_id")
    @classmethod
    def validate_organization_id(cls, value: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_\-]+$", value):
            raise ValueError(
                "organization_id may only contain letters, numbers, hyphens, and underscores."
            )
        return value

    @field_validator("return_url", "success_url")
    @classmethod
    def validate_urls(cls, value: str | None) -> str | None:
        if value is None:
            return None

        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("URL must include http/https scheme and host.")

        local_hosts = {"localhost", "127.0.0.1"}
        if parsed.scheme != "https" and parsed.hostname not in local_hosts:
            raise ValueError("Only https URLs are allowed outside localhost.")

        return value


class WorkOSPortalLinkResponse(BaseModel):
    """Response payload containing generated WorkOS Admin Portal link."""

    link: str


class WorkOSEventsResponse(BaseModel):
    """Response payload for WorkOS events pull endpoint."""

    data: list[JSONDict] = Field(default_factory=list)
    list_metadata: JSONDict = Field(default_factory=dict)


def _resolve_portal_intent(override_intent: WorkOSPortalIntent | None) -> WorkOSPortalIntent:
    if override_intent is not None:
        return override_intent

    configured_intent = settings.sso.workos_portal_default_intent
    if configured_intent not in VALID_WORKOS_PORTAL_INTENTS:
        raise WorkOSConfigurationError(
            "WORKOS_PORTAL_DEFAULT_INTENT must be one of: "
            "audit_logs, certificate_renewal, domain_verification, dsync, log_streams, sso."
        )
    return cast(WorkOSPortalIntent, configured_intent)


@router.post("/portal-links", response_model=WorkOSPortalLinkResponse)
async def create_workos_portal_link(
    request_data: WorkOSPortalLinkRequest,
    admin: JSONDict = Depends(get_current_admin),
) -> WorkOSPortalLinkResponse:
    """Create an Admin Portal link for an organization."""
    if not is_workos_enabled():
        raise HTTPException(status_code=503, detail="WorkOS integration is not enabled.")

    try:
        portal_link = await generate_workos_admin_portal_link(
            organization_id=request_data.organization_id,
            intent=_resolve_portal_intent(request_data.intent),
            return_url=request_data.return_url,
            success_url=request_data.success_url,
            intent_options=request_data.intent_options,
        )
    except WorkOSConfigurationError as exc:
        logger.error(
            "WorkOS configuration error during portal link generation",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(status_code=503, detail="WorkOS configuration error.") from exc
    except WorkOSAPIError as exc:
        raise HTTPException(
            status_code=502, detail="WorkOS portal link generation failed."
        ) from exc

    logger.info(
        "Generated WorkOS admin portal link",
        extra={
            "organization_id": request_data.organization_id,
            "admin_id": admin.get("id"),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
    )
    return WorkOSPortalLinkResponse(link=portal_link)


@router.get("/events", response_model=WorkOSEventsResponse)
async def pull_workos_events(
    event: list[str] = Query(..., min_length=1),
    organization_id: str | None = Query(None),
    after: str | None = Query(None),
    range_start: str | None = Query(None, description="ISO-8601 timestamp"),
    range_end: str | None = Query(None, description="ISO-8601 timestamp"),
    limit: int = Query(100, ge=1, le=500),
    admin: JSONDict = Depends(get_current_admin),
) -> WorkOSEventsResponse:
    """Pull events from WorkOS using cursor-based pagination."""
    if not is_workos_enabled():
        raise HTTPException(status_code=503, detail="WorkOS integration is not enabled.")

    try:
        workos_response = await list_workos_events(
            event_types=event,
            organization_id=organization_id,
            after=after,
            range_start=range_start,
            range_end=range_end,
            limit=limit,
        )
    except WorkOSConfigurationError as exc:
        logger.error(
            "WorkOS configuration error during events query",
            extra={"error_type": type(exc).__name__},
        )
        raise HTTPException(status_code=503, detail="WorkOS configuration error.") from exc
    except WorkOSAPIError as exc:
        raise HTTPException(status_code=502, detail="Failed to query WorkOS events.") from exc

    data = workos_response.get("data", [])
    list_metadata = workos_response.get("list_metadata", {})

    if not isinstance(data, list):
        data = []
    filtered_data = [row for row in data if isinstance(row, dict)]

    if not isinstance(list_metadata, dict):
        list_metadata = {}

    logger.info(
        "Pulled WorkOS events",
        extra={
            "event_types": event,
            "event_count": len(filtered_data),
            "admin_id": admin.get("id"),
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
    )

    return WorkOSEventsResponse(data=filtered_data, list_metadata=list_metadata)
