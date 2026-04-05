"""
ACGS-2 Session Governance - Router Configuration
Constitutional Hash: 608508a9bd224290

FastAPI router setup, lifecycle management, and route registration.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status

from enhanced_agent_bus._compat.security.auth import get_current_user
from enhanced_agent_bus.observability.structured_logging import get_logger

from . import endpoints

# Import from fallbacks module for consistency
from ._fallbacks import SessionContextManager, get_tenant_id
from .models import (
    CreateSessionRequest,
    ErrorResponse,
    PolicySelectionRequest,
    PolicySelectionResponse,
    SessionMetricsResponse,
    SessionResponse,
    UpdateGovernanceRequest,
)

logger = get_logger(__name__)

# =============================================================================
# Router Setup
# =============================================================================

router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["Session Governance"],
    dependencies=[Depends(get_current_user)],
)

# Global session context manager (initialized on startup)
_session_manager: SessionContextManager | None = None


def get_session_manager() -> SessionContextManager:
    """Get the global session context manager.

    Raises:
        HTTPException: If manager is not initialized
    """
    if _session_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session context manager not initialized",
        )
    return _session_manager


# =============================================================================
# Lifecycle Functions
# =============================================================================


async def init_session_manager(redis_url: str = "redis://localhost:6379") -> bool:
    """Initialize the session context manager.

    Args:
        redis_url: Redis connection URL

    Returns:
        True if initialized successfully
    """
    global _session_manager
    _session_manager = SessionContextManager(redis_url=redis_url)
    return await _session_manager.connect()


async def shutdown_session_manager() -> None:
    """Shutdown the session context manager."""
    global _session_manager
    if _session_manager:
        await _session_manager.disconnect()
        _session_manager = None


# =============================================================================
# Route Registration
# =============================================================================


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Session created successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        409: {"model": ErrorResponse, "description": "Session already exists"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Create session with governance configuration",
    description="""
Create a new session with the specified governance configuration.

**Features:**
- Dynamic per-session policy enforcement
- Configurable risk levels and automation limits
- TTL-based automatic expiration
- Multi-tenant isolation
- Constitutional compliance validation

**Constitutional Hash:** 608508a9bd224290
    """,
)
async def create_session_route(
    request: CreateSessionRequest,
    tenant_id: str = Depends(get_tenant_id),
    x_user_id: str | None = Header(None, alias="X-User-ID"),
    manager: SessionContextManager = Depends(get_session_manager),
) -> SessionResponse:
    """Create a new session with governance configuration."""
    return await endpoints.create_session(request, tenant_id, x_user_id, manager)


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    responses={
        200: {"description": "Session retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Session not found"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Get session details",
    description="Retrieve session governance configuration by session ID.",
)
async def get_session_route(
    session_id: str,
    tenant_id: str = Depends(get_tenant_id),
    manager: SessionContextManager = Depends(get_session_manager),
) -> SessionResponse:
    """Get session governance configuration by ID."""
    return await endpoints.get_session(session_id, tenant_id, manager)


@router.put(
    "/{session_id}/governance",
    response_model=SessionResponse,
    responses={
        200: {"description": "Governance configuration updated successfully"},
        404: {"model": ErrorResponse, "description": "Session not found"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        400: {"model": ErrorResponse, "description": "Invalid update data"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Update session governance configuration",
    description="""
Update the governance configuration for an existing session.

Only the fields provided in the request will be updated.
Other fields retain their current values.
    """,
)
async def update_session_governance_route(
    session_id: str,
    request: UpdateGovernanceRequest,
    tenant_id: str = Depends(get_tenant_id),
    manager: SessionContextManager = Depends(get_session_manager),
) -> SessionResponse:
    """Update session governance configuration."""
    return await endpoints.update_session_governance(session_id, request, tenant_id, manager)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Delete session",
    description="Delete a session and its governance configuration.",
)
async def delete_session_route(
    session_id: str,
    tenant_id: str = Depends(get_tenant_id),
    manager: SessionContextManager = Depends(get_session_manager),
):
    """Delete a session."""
    return await endpoints.delete_session(session_id, tenant_id, manager)


@router.post(
    "/{session_id}/extend",
    response_model=SessionResponse,
    responses={
        200: {"description": "Session TTL extended successfully"},
        404: {"model": ErrorResponse, "description": "Session not found"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Extend session TTL",
    description="Extend the time-to-live for an existing session.",
)
async def extend_session_ttl_route(
    session_id: str,
    ttl_seconds: int = 3600,
    tenant_id: str = Depends(get_tenant_id),
    manager: SessionContextManager = Depends(get_session_manager),
) -> SessionResponse:
    """Extend session TTL."""
    return await endpoints.extend_session_ttl(session_id, ttl_seconds, tenant_id, manager)


@router.post(
    "/{session_id}/policies/select",
    response_model=PolicySelectionResponse,
    responses={
        200: {"description": "Policy selection completed successfully"},
        404: {"model": ErrorResponse, "description": "Session not found"},
        403: {"model": ErrorResponse, "description": "Access denied"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Select applicable policies for session",
    description="""
Context-driven policy selection based on session governance configuration.

This endpoint evaluates the session's governance context (risk level, tenant,
user, policy overrides) and returns the most appropriate policies to apply.

**Selection Priority:**
1. Session-specific policy overrides (highest priority)
2. Session enabled_policies list
3. Tenant-specific policies
4. Global policies (fallback)

**Features:**
- Risk-level aware filtering
- Multi-tenant isolation
- Cache-optimized for sub-millisecond performance
- Detailed selection reasoning for audit trails

**Constitutional Hash:** 608508a9bd224290
    """,
)
async def select_session_policies_route(
    session_id: str,
    request: PolicySelectionRequest | None = None,
    tenant_id: str = Depends(get_tenant_id),
    manager: SessionContextManager = Depends(get_session_manager),
) -> PolicySelectionResponse:
    """Select applicable policies based on session context."""
    return await endpoints.select_session_policies(session_id, request, tenant_id, manager)


@router.get(
    "",
    response_model=SessionMetricsResponse,
    responses={
        200: {"description": "Session manager metrics"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Get session manager metrics",
    description="Get performance and usage metrics for the session manager.",
)
async def get_session_metrics_route(
    manager: SessionContextManager = Depends(get_session_manager),
) -> SessionMetricsResponse:
    """Get session manager performance metrics."""
    return await endpoints.get_session_metrics(manager)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "get_session_manager",
    "init_session_manager",
    "router",
    "shutdown_session_manager",
]
