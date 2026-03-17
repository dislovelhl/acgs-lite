"""
ACGS-2 Enhanced Agent Bus - PQC Admin Routes
Constitutional Hash: cdd01ef066bc6cf2

Provides admin endpoints for managing the PQC enforcement mode:

  PATCH /api/v1/admin/pqc-enforcement  — change mode (strict | permissive)
  GET   /api/v1/admin/pqc-enforcement  — read current mode

Authorization: platform-operator or tenant-admin JWT role required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

try:
    from src.core.shared.security.auth import UserClaims, get_current_user
except ImportError:  # pragma: no cover — fallback for isolated test runs
    from unittest.mock import MagicMock

    UserClaims = MagicMock  # type: ignore[assignment,misc]

    async def get_current_user() -> MagicMock:  # type: ignore[misc]
        raise HTTPException(status_code=401, detail="Auth not configured")


try:
    from ...pqc_enforcement_config import (
        EnforcementModeConfigService,
        StorageUnavailableError,
    )
    from ...pqc_enforcement_models import (
        EnforcementModeRequest,
        EnforcementModeResponse,
    )
except ImportError:  # pragma: no cover — fallback for isolated test runs
    from pqc_enforcement_config import (  # type: ignore[no-redef]
        EnforcementModeConfigService,
        StorageUnavailableError,
    )
    from pqc_enforcement_models import (  # type: ignore[no-redef]
        EnforcementModeRequest,
        EnforcementModeResponse,
    )

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["PQC Admin"])

# Roles authorised to change/read the enforcement mode
_ADMIN_ROLES = frozenset({"platform-operator", "tenant-admin"})

PROPAGATION_DEADLINE_SECONDS = 60


# ---------------------------------------------------------------------------
# Dependency: enforcement service singleton
# ---------------------------------------------------------------------------


def get_enforcement_service() -> EnforcementModeConfigService:
    """FastAPI dependency that returns the shared enforcement-mode service.

    In production, the service is built by the app lifespan and stored on
    app.state.  In tests, override this dependency via app.dependency_overrides.
    """
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="PQC enforcement config service is not initialised",
    )


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _require_admin(user: UserClaims) -> None:
    """Raise HTTP 403 if the user does not hold an admin role."""
    if not any(role in _ADMIN_ROLES for role in (user.roles or [])):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="platform-operator or tenant-admin role required",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.patch(
    "/api/v1/admin/pqc-enforcement",
    response_model=EnforcementModeResponse,
    summary="Change PQC enforcement mode",
    status_code=status.HTTP_200_OK,
)
async def patch_pqc_enforcement(
    body: EnforcementModeRequest,
    user: Annotated[UserClaims, Depends(get_current_user)],
    svc: Annotated[EnforcementModeConfigService, Depends(get_enforcement_service)],
) -> EnforcementModeResponse:
    """Change the PQC enforcement mode (strict | permissive).

    Requires: platform-operator or tenant-admin JWT role.

    Returns the new mode with server-set activation timestamp and
    propagation deadline.
    """
    _require_admin(user)

    if body.mode == "permissive":
        logger.warning(
            "PQC enforcement mode set to permissive — classical keys will be accepted",
            extra={"activated_by": user.sub, "scope": body.scope},
        )

    try:
        await svc.set_mode(
            mode=body.mode,
            scope=body.scope,
            activated_by=user.sub,
        )
    except StorageUnavailableError as exc:
        logger.error(
            "Storage unavailable while changing PQC enforcement mode",
            extra={"error": str(exc), "activated_by": user.sub},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Enforcement mode storage unavailable; change could not be persisted",
        ) from exc

    return EnforcementModeResponse(
        mode=body.mode,
        activated_at=datetime.now(tz=UTC),
        activated_by=user.sub,
        scope=body.scope,
        propagation_deadline_seconds=PROPAGATION_DEADLINE_SECONDS,
    )


@router.get(
    "/api/v1/admin/pqc-enforcement",
    response_model=EnforcementModeResponse,
    summary="Read current PQC enforcement mode",
    status_code=status.HTTP_200_OK,
)
async def get_pqc_enforcement(
    user: Annotated[UserClaims, Depends(get_current_user)],
    svc: Annotated[EnforcementModeConfigService, Depends(get_enforcement_service)],
    scope: str = Query(default="global", description="Enforcement scope"),
) -> EnforcementModeResponse:
    """Return the current PQC enforcement mode and metadata.

    Requires: platform-operator or tenant-admin JWT role.
    """
    _require_admin(user)

    try:
        mode = await svc.get_mode(scope=scope)
    except StorageUnavailableError as exc:
        logger.error(
            "Storage unavailable while reading PQC enforcement mode",
            extra={"error": str(exc), "scope": scope},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Enforcement mode storage unavailable",
        ) from exc

    return EnforcementModeResponse(
        mode=mode,
        activated_at=datetime.now(tz=UTC),
        activated_by="system",
        scope=scope,
        propagation_deadline_seconds=PROPAGATION_DEADLINE_SECONDS,
    )


__all__ = ["get_enforcement_service", "router"]
