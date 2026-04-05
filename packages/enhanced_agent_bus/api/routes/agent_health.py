"""
Agent Health API Routes — GET/POST/DELETE /api/v1/agents/{agent_id}/health*
Constitutional Hash: 608508a9bd224290

Exposes health snapshots and operator override management for agent instances.
Authentication and operator-role enforcement are provided by require_operator_role.
The AgentHealthStore and AuditLogClient are injected via dependencies for testability.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..rate_limiting import limiter
from pydantic import BaseModel, Field

from enhanced_agent_bus.agent_health.models import (
    CONSTITUTIONAL_HASH,
    AutonomyTier,
    HealingOverride,
    HealthState,
    OverrideMode,
)
from enhanced_agent_bus.agent_health.store import AgentHealthStore
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["agent-health"])


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class HealingOverrideResponse(BaseModel):
    """Serialised view of an active HealingOverride."""

    override_id: str
    mode: OverrideMode
    issued_by: str
    issued_at: datetime
    expires_at: datetime | None = None


class AgentHealthResponse(BaseModel):
    """Response body for GET /api/v1/agents/{agent_id}/health."""

    agent_id: str
    health_state: HealthState
    consecutive_failure_count: int
    memory_usage_pct: float
    last_error_type: str | None = None
    last_event_at: datetime
    autonomy_tier: AutonomyTier
    healing_override: HealingOverrideResponse | None = None
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH)


class HealingOverrideRequest(BaseModel):
    """Request body for POST /api/v1/agents/{agent_id}/health/override.

    Fields are kept as plain Python types so that validation errors are
    reported as 400 (HTTPException) rather than FastAPI's default 422.
    """

    mode: str = Field(description="One of: SUPPRESS_HEALING, FORCE_RESTART, FORCE_QUARANTINE")
    reason: str = Field(description="Human-readable rationale (max 1000 chars)")
    expires_at: datetime | None = Field(
        default=None, description="Optional expiry (must be future)"
    )


class CreateOverrideResponse(BaseModel):
    """Response body for POST /api/v1/agents/{agent_id}/health/override (201)."""

    override_id: str
    agent_id: str
    mode: OverrideMode
    issued_by: str
    issued_at: datetime
    expires_at: datetime | None = None
    audit_event_id: str


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_audit_log_client(request: Request) -> Any:
    """Dependency: returns the audit log client from app.state, or raises 503."""
    client = getattr(request.app.state, "audit_log_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Audit log client not initialised",
        )
    return client


def get_agent_health_store(request: Request) -> AgentHealthStore:
    """Dependency: returns the AgentHealthStore from app.state, or raises 503."""
    store: AgentHealthStore | None = getattr(request.app.state, "agent_health_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="AgentHealthStore not initialised",
        )
    return store


async def require_operator_role(request: Request) -> str:
    """Dependency: enforces JWT authentication and operator role.

    Checks the Authorization: Bearer <token> header. Raises:
    - 401 if no valid Bearer token is present.
    - 403 if the authenticated principal does not hold the operator role.

    In development/test environments this dependency is overridden via
    app.dependency_overrides; in production it delegates to the shared
    JWT + RBAC infrastructure when available.

    Returns the operator identity string (e.g. subject claim from JWT).
    """
    # Attempt to delegate to the shared JWT RBAC validator when available.
    try:
        from enhanced_agent_bus._compat.security.rbac import validate_operator_token

        result: str = await validate_operator_token(request)
        return result
    except ImportError:
        pass

    # Fallback: minimal header-based check used in environments where the
    # shared security layer is not installed (dev/test).
    environment = os.environ.get("ENVIRONMENT", "").lower()
    dev_envs = frozenset(("development", "dev", "test", "testing", "ci"))
    if environment not in dev_envs:
        raise HTTPException(
            status_code=503,
            detail="JWT RBAC security dependency not available outside dev environments",
        )

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header[len("Bearer ") :]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # In dev/test fallback, accept any non-empty token as operator.
    return f"dev-operator:{token[:16]}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{agent_id}/health",
    response_model=AgentHealthResponse,
    summary="Get agent health",
    description=(
        "Returns the current health state, consecutive failure count, memory usage "
        "percentage, last event timestamp, and Autonomy Tier for the specified agent (FR-007)."
    ),
)
@limiter.limit("60/minute")
async def get_agent_health(
    agent_id: str,
    request: Request,
    operator: str = Depends(require_operator_role),
    store: AgentHealthStore = Depends(get_agent_health_store),
) -> AgentHealthResponse:
    """Retrieve current health snapshot for *agent_id*."""
    record = await store.get_health_record(agent_id)
    if record is None:
        logger.info("Health record not found", agent_id=agent_id, operator=operator)
        raise HTTPException(
            status_code=404,
            detail=f"No health record found for agent '{agent_id}'",
        )

    override_response: HealingOverrideResponse | None = None
    if record.healing_override_id:
        override: HealingOverride | None = await store.get_override(agent_id)
        if override is not None:
            override_response = HealingOverrideResponse(
                override_id=override.override_id,
                mode=override.mode,
                issued_by=override.issued_by,
                issued_at=override.issued_at,
                expires_at=override.expires_at,
            )

    logger.info(
        "Health record retrieved",
        agent_id=agent_id,
        health_state=record.health_state,
        operator=operator,
    )

    return AgentHealthResponse(
        agent_id=record.agent_id,
        health_state=record.health_state,
        consecutive_failure_count=record.consecutive_failure_count,
        memory_usage_pct=record.memory_usage_pct,
        last_error_type=record.last_error_type,
        last_event_at=record.last_event_at,
        autonomy_tier=record.autonomy_tier,
        healing_override=override_response,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


@router.post(
    "/{agent_id}/health/override",
    response_model=CreateOverrideResponse,
    status_code=201,
    summary="Create healing override",
    description=(
        "Creates an operator override to suppress or force a healing action for the "
        "specified agent (FR-008). Written to the governance audit log before taking effect."
    ),
)
@limiter.limit("20/minute")
async def create_healing_override(
    agent_id: str,
    request: Request,
    body: HealingOverrideRequest,
    operator: str = Depends(require_operator_role),
    store: AgentHealthStore = Depends(get_agent_health_store),
    audit_client: Any = Depends(get_audit_log_client),
) -> CreateOverrideResponse:
    """Create a healing override for *agent_id*."""
    # --- Validate request body (return 400 for all client errors) ---
    try:
        mode = OverrideMode(body.mode)
    except ValueError as err:
        valid = ", ".join(m.value for m in OverrideMode)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{body.mode}'. Must be one of: {valid}",
        ) from err

    if len(body.reason) > 1000:
        raise HTTPException(
            status_code=400,
            detail="reason must be at most 1000 characters",
        )

    now = datetime.now(UTC)
    if body.expires_at is not None and body.expires_at <= now:
        raise HTTPException(
            status_code=400,
            detail="expires_at must be in the future",
        )

    # --- 409 if an active override already exists ---
    existing = await store.get_override(agent_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"An active override already exists for agent '{agent_id}'",
        )

    audit_event_id = str(uuid.uuid4())

    # --- Write audit log entry BEFORE storing override (FR-009) ---
    from enhanced_agent_bus._compat.audit.logger import AuditEventType, AuditSeverity

    await audit_client.log(
        event_type=AuditEventType.APPROVAL,
        severity=AuditSeverity.WARNING,
        actor={"type": "operator", "identity": operator},
        resource={"agent_id": agent_id},
        action={
            "type": "HEALING_OVERRIDE_CREATED",
            "mode": mode.value,
            "reason": body.reason,
            "expires_at": body.expires_at.isoformat() if body.expires_at else None,
            "audit_event_id": audit_event_id,
        },
        result={
            "status": "created",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
    )

    # --- Persist the override ---
    override = HealingOverride(
        agent_id=agent_id,
        mode=mode,
        reason=body.reason,
        issued_by=operator,
        issued_at=now,
        expires_at=body.expires_at,
    )
    await store.set_override(override)

    logger.info(
        "Healing override created",
        agent_id=agent_id,
        mode=mode.value,
        operator=operator,
        audit_event_id=audit_event_id,
    )

    return CreateOverrideResponse(
        override_id=override.override_id,
        agent_id=agent_id,
        mode=mode,
        issued_by=operator,
        issued_at=now,
        expires_at=body.expires_at,
        audit_event_id=audit_event_id,
    )


@router.delete(
    "/{agent_id}/health/override",
    status_code=204,
    summary="Delete healing override",
    description=(
        "Removes the active healing override for the specified agent, restoring "
        "automatic healing (FR-008). Written to the governance audit log."
    ),
)
@limiter.limit("20/minute")
async def delete_healing_override(
    agent_id: str,
    request: Request,
    operator: str = Depends(require_operator_role),
    store: AgentHealthStore = Depends(get_agent_health_store),
    audit_client: Any = Depends(get_audit_log_client),
) -> Response:
    """Remove the active healing override for *agent_id*."""
    existing = await store.get_override(agent_id)
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active override found for agent '{agent_id}'",
        )

    # --- Write audit log entry before removing override (FR-009) ---
    from enhanced_agent_bus._compat.audit.logger import AuditEventType, AuditSeverity

    await audit_client.log(
        event_type=AuditEventType.APPROVAL,
        severity=AuditSeverity.INFO,
        actor={"type": "operator", "identity": operator},
        resource={"agent_id": agent_id},
        action={
            "type": "HEALING_OVERRIDE_DELETED",
            "override_id": existing.override_id,
            "mode": existing.mode.value,
        },
        result={
            "status": "deleted",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
    )

    await store.delete_override(agent_id)

    logger.info(
        "Healing override deleted",
        agent_id=agent_id,
        override_id=existing.override_id,
        operator=operator,
    )

    return Response(status_code=204)


__all__ = [
    "AgentHealthResponse",
    "CreateOverrideResponse",
    "HealingOverrideRequest",
    "HealingOverrideResponse",
    "get_agent_health_store",
    "get_audit_log_client",
    "require_operator_role",
    "router",
]
