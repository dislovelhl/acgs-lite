"""
Lightweight authentication dependency for FastAPI endpoints.

Constitutional Hash: 608508a9bd224290

Provides a reusable FastAPI dependency that validates Bearer tokens or API keys.
Supports environment-controlled bypass for development and testing.

Token revocation:
  Call ``configure_revocation_service(service)`` at application startup to wire
  in a TokenRevocationService.  When configured, every authenticated request
  checks the JTI claim against the Redis blacklist.  Without a configured
  service the check is skipped gracefully (no behaviour change for existing
  deployments that have not yet provisioned the service).
"""

import os
from typing import TYPE_CHECKING

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.shared.config import settings
from src.core.shared.config.runtime_environment import resolve_runtime_environment
from src.core.shared.security.auth import has_jwt_verification_material, verify_token
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

if TYPE_CHECKING:
    from src.core.shared.security.token_revocation import TokenRevocationService

logger = get_logger(__name__)
_bearer_scheme = HTTPBearer(auto_error=False)

_NON_PRODUCTION_ENVS = frozenset({"development", "dev", "test", "testing", "local", "ci"})

# Module-level revocation service — set once at application startup via
# configure_revocation_service().  None = revocation checks skipped.
_revocation_service: "TokenRevocationService | None" = None


def configure_revocation_service(service: "TokenRevocationService") -> None:
    """Register the TokenRevocationService used by require_auth.

    Call this once during application lifespan startup:

        @app.on_event("startup")
        async def startup():
            svc = await create_token_revocation_service()
            configure_revocation_service(svc)
    """
    global _revocation_service
    _revocation_service = service
    logger.info("TokenRevocationService registered with require_auth")


async def initialize_revocation_service(
    redis_url: str | None = None,
) -> "TokenRevocationService":
    """Create and register the shared token revocation service.

    If no Redis URL is configured, register a degraded-mode service so
    revocation remains explicitly wired without incurring a localhost
    connection attempt at startup.
    """
    from src.core.shared.security.token_revocation import (
        TokenRevocationService,
        create_token_revocation_service,
    )

    configured_redis_url = (
        redis_url or os.getenv("TOKEN_REVOCATION_REDIS_URL") or os.getenv("REDIS_URL")
    )
    if configured_redis_url:
        service = await create_token_revocation_service(configured_redis_url)
    else:
        service = TokenRevocationService(redis_client=None)
        logger.info("TokenRevocationService initialized in degraded mode (no Redis URL)")

    configure_revocation_service(service)
    return service


async def shutdown_revocation_service() -> None:
    """Clear the shared token revocation service during lifespan shutdown."""
    global _revocation_service

    service = _revocation_service
    _revocation_service = None
    if service is None:
        return

    await service.close()
    logger.info("TokenRevocationService unregistered from require_auth")


def _is_production_environment() -> bool:
    environment = resolve_runtime_environment(
        getattr(settings, "env", None),
        extra_env_vars=("ACGS2_ENV",),
    )
    return environment not in _NON_PRODUCTION_ENVS


def _auth_disabled_requested() -> bool:
    return os.getenv("AUTH_DISABLED", "false").strip().lower() in {"true", "1", "yes"}


async def _check_revocation(jti: str | None) -> None:
    """Raise HTTP 401 if the JTI is on the revocation blacklist.

    Silently skips the check if:
    - No revocation service is configured.
    - The token has no JTI claim (handled gracefully; tokens issued by auth.py
      always include JTI so this only applies to third-party tokens).
    """
    if not jti:
        return
    if _revocation_service is None:
        if _is_production_environment():
            raise HTTPException(status_code=503, detail="Token revocation backend unavailable")
        return
    try:
        if await _revocation_service.is_token_revoked(jti):
            logger.warning("Revoked token presented: jti=%s...", jti[:8])
            raise HTTPException(status_code=401, detail="Token has been revoked")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Revocation check error: %s", e)
        if _is_production_environment():
            raise HTTPException(status_code=503, detail="Token revocation backend unavailable") from e


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
) -> JSONDict:
    """Validate Bearer token and return user context.

    Args:
        credentials: HTTP Authorization credentials (Bearer token).

    Returns:
        User context dict with sub, tenant_id, roles, and jti.

    Raises:
        HTTPException: 401 if authentication fails or token is revoked.

    Example:
        @app.post("/protected")
        async def protected_endpoint(user: dict = Depends(require_auth)):
            return {"user_id": user["sub"]}
    """
    if _auth_disabled_requested() and not _is_production_environment():
        logger.warning("AUTH_DISABLED shortcut active — requests run as dev-user with viewer role")
        return {
            "sub": "dev-user",
            "tenant_id": "dev-tenant",
            "roles": ["viewer"],
        }

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    if not has_jwt_verification_material():
        raise HTTPException(status_code=500, detail="JWT verification material not configured")

    payload = verify_token(credentials.credentials).model_dump()

    # Check revocation blacklist (no-op if service not configured)
    await _check_revocation(payload.get("jti"))

    return payload


def require_auth_optional(
    credentials: HTTPAuthorizationCredentials | None = Security(HTTPBearer(auto_error=False)),
) -> JSONDict | None:
    """Optional authentication - returns None if no credentials provided.

    Useful for endpoints that have different behavior for authenticated vs
    unauthenticated users.  Note: if credentials are provided but invalid
    (expired, tampered) a 401 is raised so callers can distinguish
    "no token" from "bad token".

    Args:
        credentials: HTTP Authorization credentials (Bearer token).

    Returns:
        User context dict if authenticated, None otherwise.

    Example:
        @app.get("/public-or-private")
        async def endpoint(user: dict | None = Depends(require_auth_optional)):
            if user:
                return {"message": f"Hello {user['sub']}"}
            return {"message": "Hello anonymous"}
    """
    if not credentials:
        return None

    try:
        if not has_jwt_verification_material():
            return None

        return verify_token(credentials.credentials).model_dump()
    except HTTPException as e:
        # Log the failure so invalid tokens are visible in audit trail
        logger.warning("Optional auth: token validation failed — %s", type(e).__name__)
        if e.status_code >= 500:
            raise
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        ) from e
