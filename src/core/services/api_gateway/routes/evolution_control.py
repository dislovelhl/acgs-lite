"""Admin API routes for self-evolution operator control.
Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

try:
    from src.core.self_evolution.research.operator_control import (
        ResearchOperatorControlPlane,
        ResearchOperatorControlSnapshot,
    )
except ImportError:

    class ResearchOperatorControlSnapshot(BaseModel):
        """Fallback snapshot model when self_evolution is unavailable."""

        paused: bool = False
        stop_requested: bool = False
        status: str = "unavailable"
        updated_by: str | None = None
        reason: str | None = None

    class ResearchOperatorControlPlane(Protocol):
        """Fallback control plane protocol for typing only."""

        async def snapshot(self) -> dict[str, object]: ...

        async def request_pause(self, user_id: str, reason: str | None) -> dict[str, object]: ...

        async def request_resume(self, user_id: str, reason: str | None) -> dict[str, object]: ...

        async def request_stop(self, user_id: str, reason: str | None) -> dict[str, object]: ...


from src.core.shared.security.auth import UserClaims, get_current_user
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/evolution/operator-control", tags=["self-evolution-control"])


class OperatorControlCommandRequest(BaseModel):
    """Request body for pause/resume/stop operator commands."""

    reason: str | None = Field(default=None, max_length=1000)


async def get_operator_control_plane(request: Request) -> ResearchOperatorControlPlane:
    """Resolve the shared operator control plane from gateway state."""
    plane = getattr(request.app.state, "research_operator_control_plane", None)
    if plane is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Self-evolution operator control is not configured",
        )
    return plane


@router.get("", response_model=ResearchOperatorControlSnapshot)
async def get_operator_control_status(
    _user: UserClaims = Depends(get_current_user),
    control_plane: ResearchOperatorControlPlane = Depends(get_operator_control_plane),
) -> ResearchOperatorControlSnapshot:
    """Return current self-evolution operator control state."""
    try:
        return ResearchOperatorControlSnapshot(**(await control_plane.snapshot()))
    except (RedisError, RuntimeError, ValueError) as exc:
        logger.warning("self_evolution_operator_control_status_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Self-evolution operator control unavailable",
        ) from exc


@router.post("/pause", response_model=ResearchOperatorControlSnapshot)
async def request_operator_pause(
    body: OperatorControlCommandRequest,
    user: UserClaims = Depends(get_current_user),
    control_plane: ResearchOperatorControlPlane = Depends(get_operator_control_plane),
) -> ResearchOperatorControlSnapshot:
    """Request a pause at the next safe evolution boundary."""
    try:
        snapshot = await control_plane.request_pause(user.sub, body.reason)
    except (RedisError, RuntimeError, ValueError) as exc:
        logger.warning("self_evolution_operator_pause_failed", error=str(exc), user_id=user.sub)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to request self-evolution pause",
        ) from exc

    logger.info("self_evolution_operator_pause_requested", user_id=user.sub, reason=body.reason)
    return ResearchOperatorControlSnapshot(**snapshot)


@router.post("/resume", response_model=ResearchOperatorControlSnapshot)
async def request_operator_resume(
    body: OperatorControlCommandRequest,
    user: UserClaims = Depends(get_current_user),
    control_plane: ResearchOperatorControlPlane = Depends(get_operator_control_plane),
) -> ResearchOperatorControlSnapshot:
    """Clear pause/stop state and allow evolution to continue."""
    try:
        snapshot = await control_plane.request_resume(user.sub, body.reason)
    except (RedisError, RuntimeError, ValueError) as exc:
        logger.warning("self_evolution_operator_resume_failed", error=str(exc), user_id=user.sub)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to request self-evolution resume",
        ) from exc

    logger.info("self_evolution_operator_resume_requested", user_id=user.sub, reason=body.reason)
    return ResearchOperatorControlSnapshot(**snapshot)


@router.post("/stop", response_model=ResearchOperatorControlSnapshot)
async def request_operator_stop(
    body: OperatorControlCommandRequest,
    user: UserClaims = Depends(get_current_user),
    control_plane: ResearchOperatorControlPlane = Depends(get_operator_control_plane),
) -> ResearchOperatorControlSnapshot:
    """Request a stop at the next safe evolution boundary."""
    try:
        snapshot = await control_plane.request_stop(user.sub, body.reason)
    except (RedisError, RuntimeError, ValueError) as exc:
        logger.warning("self_evolution_operator_stop_failed", error=str(exc), user_id=user.sub)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to request self-evolution stop",
        ) from exc

    logger.info("self_evolution_operator_stop_requested", user_id=user.sub, reason=body.reason)
    return ResearchOperatorControlSnapshot(**snapshot)
