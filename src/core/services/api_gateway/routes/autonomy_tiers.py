"""Admin API router for autonomy tier CRUD operations.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.services.api_gateway.models.tier_assignment import AgentTierAssignment
from src.core.services.api_gateway.repositories.tier_assignment import (
    NotFoundError,
    TierAssignmentRepository,
)
from src.core.services.api_gateway.schemas.tier_assignment import (
    AgentTierAssignmentCreate,
    AgentTierAssignmentResponse,
    AgentTierAssignmentUpdate,
)
from src.core.shared.security.auth import UserClaims, get_current_user
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# List response model
# ---------------------------------------------------------------------------


class TierAssignmentListResponse(BaseModel):
    """Response schema for the list-all-tier-assignments endpoint."""

    items: list[AgentTierAssignmentResponse]
    total: int


# ---------------------------------------------------------------------------
# Dependency factories (overridable in tests via app.dependency_overrides)
# ---------------------------------------------------------------------------

_engine = None
_async_session_factory = None


def _get_async_engine():  # pragma: no cover
    global _engine
    if _engine is None:
        database_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./acgs2_gateway.db")
        _engine = create_async_engine(database_url, echo=False)
    return _engine


def _get_async_session_factory():  # pragma: no cover
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(_get_async_engine(), expire_on_commit=False)
    return _async_session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:  # pragma: no cover
    """Yield an async database session from DATABASE_URL."""
    session_factory = _get_async_session_factory()
    async with session_factory() as session:
        async with session.begin():
            yield session


async def get_redis_client() -> Redis:  # pragma: no cover
    """Return an async Redis client from REDIS_URL."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    return redis_from_url(redis_url, decode_responses=True)


async def get_tier_repo(
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis_client),
) -> TierAssignmentRepository:
    """Build a TierAssignmentRepository from injected session and Redis client."""
    return TierAssignmentRepository(session=session, redis=redis)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/autonomy-tiers", tags=["autonomy-tiers"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_tenant_admin(user: UserClaims) -> None:
    """Raise HTTP 403 if the caller does not have the tenant_admin role."""
    if "tenant_admin" not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_admin role required",
        )


def _to_response(assignment: AgentTierAssignment) -> AgentTierAssignmentResponse:
    """Convert ORM model to Pydantic response schema."""
    return AgentTierAssignmentResponse(
        id=assignment.id,
        agent_id=assignment.agent_id,
        tenant_id=assignment.tenant_id,
        tier=assignment.tier,
        action_boundaries=assignment.action_boundaries,
        assigned_by=assignment.assigned_by,
        assigned_at=assignment.assigned_at,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/admin/autonomy-tiers
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentTierAssignmentResponse,
    summary="Create tier assignment",
    description="Assign or create a tier assignment for an agent. Tenant Admin only.",
)
async def create_tier_assignment(
    body: AgentTierAssignmentCreate,
    user: UserClaims = Depends(get_current_user),
    repo: TierAssignmentRepository = Depends(get_tier_repo),
) -> AgentTierAssignmentResponse:
    """Create a new agent tier assignment (Tenant Admin only)."""
    _require_tenant_admin(user)
    assignment = await repo.create(data=body, assigned_by=user.sub, tenant_id=user.tenant_id)
    logger.info(
        "tier_assignment.admin.created",
        agent_id=body.agent_id,
        tenant_id=user.tenant_id,
        tier=str(body.tier),
        assigned_by=user.sub,
    )
    return _to_response(assignment)


# ---------------------------------------------------------------------------
# GET /api/v1/admin/autonomy-tiers/{agent_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{agent_id}",
    response_model=AgentTierAssignmentResponse,
    summary="Get tier assignment",
    description="Retrieve current tier assignment for an agent. Tenant Admin only.",
)
async def get_tier_assignment(
    agent_id: str,
    user: UserClaims = Depends(get_current_user),
    repo: TierAssignmentRepository = Depends(get_tier_repo),
) -> AgentTierAssignmentResponse:
    """Retrieve a tier assignment by agent ID (Tenant Admin only)."""
    _require_tenant_admin(user)
    assignment = await repo.get_by_agent(agent_id=agent_id, tenant_id=user.tenant_id)
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No tier assignment found for agent {agent_id!r}",
        )
    return _to_response(assignment)


# ---------------------------------------------------------------------------
# PUT /api/v1/admin/autonomy-tiers/{agent_id}
# ---------------------------------------------------------------------------


@router.put(
    "/{agent_id}",
    response_model=AgentTierAssignmentResponse,
    summary="Update tier assignment",
    description="Update existing tier assignment for an agent. Tenant Admin only.",
)
async def update_tier_assignment(
    agent_id: str,
    body: AgentTierAssignmentUpdate,
    user: UserClaims = Depends(get_current_user),
    repo: TierAssignmentRepository = Depends(get_tier_repo),
) -> AgentTierAssignmentResponse:
    """Update an existing tier assignment (Tenant Admin only)."""
    _require_tenant_admin(user)
    try:
        assignment = await repo.update(
            agent_id=agent_id,
            tenant_id=user.tenant_id,
            data=body,
            assigned_by=user.sub,
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No tier assignment found for agent {agent_id!r}",
        ) from e
    logger.info(
        "tier_assignment.admin.updated",
        agent_id=agent_id,
        tenant_id=user.tenant_id,
        tier=str(body.tier),
        assigned_by=user.sub,
    )
    return _to_response(assignment)


# ---------------------------------------------------------------------------
# DELETE /api/v1/admin/autonomy-tiers/{agent_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete tier assignment",
    description="Remove tier assignment for an agent. Tenant Admin only.",
)
async def delete_tier_assignment(
    agent_id: str,
    user: UserClaims = Depends(get_current_user),
    repo: TierAssignmentRepository = Depends(get_tier_repo),
) -> None:
    """Delete a tier assignment (Tenant Admin only)."""
    _require_tenant_admin(user)
    try:
        await repo.delete(agent_id=agent_id, tenant_id=user.tenant_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No tier assignment found for agent {agent_id!r}",
        ) from e
    logger.info(
        "tier_assignment.admin.deleted",
        agent_id=agent_id,
        tenant_id=user.tenant_id,
        deleted_by=user.sub,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/admin/autonomy-tiers (list)
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=TierAssignmentListResponse,
    summary="List tier assignments",
    description="List all tier assignments for the caller's tenant. Tenant Admin only.",
)
async def list_tier_assignments(
    user: UserClaims = Depends(get_current_user),
    repo: TierAssignmentRepository = Depends(get_tier_repo),
) -> TierAssignmentListResponse:
    """List all tier assignments scoped to the caller's tenant (Tenant Admin only)."""
    _require_tenant_admin(user)
    assignments = await repo.list_by_tenant(tenant_id=user.tenant_id)
    items = [_to_response(a) for a in assignments]
    return TierAssignmentListResponse(items=items, total=len(items))


# ---------------------------------------------------------------------------
# Public export alias
# ---------------------------------------------------------------------------

autonomy_tiers_router = router

__all__ = ["TierAssignmentListResponse", "autonomy_tiers_router", "get_tier_repo"]
