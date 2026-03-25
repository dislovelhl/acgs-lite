"""
ACGS-2 Enhanced Agent Bus - Tenant Management API
Constitutional Hash: 608508a9bd224290

Provides REST API endpoints for managing multi-tenant configurations,
enabling tenant lifecycle management, quota enforcement, and hierarchical tenancy.
"""

from __future__ import annotations

import hmac
import os
from typing import NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.security.error_sanitizer import safe_error_detail

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models.tenant_models import (
    CreateTenantRequest,
    ErrorResponse,
    QuotaCheckRequest,
    QuotaCheckResponse,
    SuspendTenantRequest,
    TenantHierarchyResponse,
    TenantListResponse,
    TenantResponse,
    UpdateQuotaRequest,
    UpdateTenantRequest,
    UsageIncrementRequest,
    UsageResponse,
)

try:
    from ..multi_tenancy import (
        Tenant,
        TenantConfig,
        TenantManager,
        TenantNotFoundError,
        TenantQuota,
        TenantQuotaExceededError,
        TenantStatus,
        TenantUsage,
        TenantValidationError,
        get_tenant_manager,
    )
except (ImportError, ValueError):
    try:
        from multi_tenancy import (  # type: ignore[no-redef]
            Tenant,
            TenantConfig,
            TenantManager,
            TenantNotFoundError,
            TenantQuota,
            TenantQuotaExceededError,
            TenantStatus,
            TenantUsage,
            TenantValidationError,
            get_tenant_manager,
        )
    except ImportError:
        # Minimal models for standalone testing
        from enum import Enum

        from pydantic import BaseModel
        from src.core.shared.errors.exceptions import ACGSBaseError

        class TenantStatus(str, Enum):  # type: ignore[no-redef]
            PENDING = "pending"
            ACTIVE = "active"
            SUSPENDED = "suspended"
            DEACTIVATED = "deactivated"
            MIGRATING = "migrating"

        class TenantConfig(BaseModel):  # type: ignore[no-redef]
            pass

        class TenantQuota(BaseModel):  # type: ignore[no-redef]
            max_agents: int = 100
            max_policies: int = 1000
            max_messages_per_minute: int = 10000

        class TenantUsage(BaseModel):  # type: ignore[no-redef]
            agents_count: int = 0
            policies_count: int = 0
            messages_this_minute: int = 0

        class Tenant(BaseModel):  # type: ignore[no-redef]
            tenant_id: str
            name: str
            slug: str
            status: TenantStatus = TenantStatus.PENDING

        class TenantNotFoundError(ACGSBaseError):  # type: ignore[no-redef]
            """Fallback stub for TenantNotFoundError when import fails."""

            http_status_code = 404
            error_code = "TENANT_NOT_FOUND"

            def __init__(
                self, message: str, tenant_id: str | None = None, **kwargs: object
            ) -> None:
                super().__init__(message, details={"tenant_id": tenant_id})
                self.tenant_id = tenant_id

        class TenantQuotaExceededError(ACGSBaseError):  # type: ignore[no-redef]
            """Fallback stub for TenantQuotaExceededError when import fails."""

            http_status_code = 429
            error_code = "TENANT_QUOTA_EXCEEDED"

            def __init__(
                self, message: str, tenant_id: str | None = None, **kwargs: object
            ) -> None:
                super().__init__(message, details={"tenant_id": tenant_id})
                self.tenant_id = tenant_id

        class TenantValidationError(ACGSBaseError):  # type: ignore[no-redef]
            """Fallback stub for TenantValidationError when import fails."""

            http_status_code = 400
            error_code = "TENANT_VALIDATION_ERROR"

            def __init__(
                self, message: str, tenant_id: str | None = None, **kwargs: object
            ) -> None:
                super().__init__(message, details={"tenant_id": tenant_id})
                self.tenant_id = tenant_id

        class TenantManager:  # type: ignore[no-redef]
            """Mock manager for testing."""

            pass

        def get_tenant_manager() -> TenantManager:  # type: ignore[no-redef]
            return TenantManager()


logger = get_logger(__name__)


def _to_dict_safe(obj: object) -> JSONDict:
    """Safely convert an object to a dictionary.

    Handles multiple serialization methods:
    - Pydantic models (model_dump)
    - Dataclasses with to_dict method
    - Dataclasses via dataclasses.asdict
    - Plain dicts

    Returns empty dict if obj is None or conversion fails.
    """
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    try:
        from dataclasses import asdict, is_dataclass

        if is_dataclass(obj) and not isinstance(obj, type):
            return asdict(obj)
    except (ImportError, TypeError):
        pass
    try:
        return dict(obj)
    except (TypeError, ValueError):
        return {}


# Create router with prefix and tags
router = APIRouter(prefix="/api/v1/tenants", tags=["Tenant Management"])


# =============================================================================
# Authorization Helpers
# =============================================================================

# Security configuration from environment
TENANT_ADMIN_KEY = os.environ.get("TENANT_ADMIN_KEY", "")
TENANT_AUTH_MODE = os.environ.get("TENANT_AUTH_MODE", "strict").strip().lower()
ENVIRONMENT = os.environ.get("AGENT_RUNTIME_ENVIRONMENT", "development")
NORMALIZED_ENVIRONMENT = ENVIRONMENT.strip().lower()

# JWT configuration (reuse from agent_runtime if available)
_ALLOWED_JWT_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "EdDSA"})
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "RS256")
if JWT_ALGORITHM not in _ALLOWED_JWT_ALGORITHMS:
    raise ValueError(
        f"Unsupported JWT_ALGORITHM={JWT_ALGORITHM!r}. Allowed: {sorted(_ALLOWED_JWT_ALGORITHMS)}"
    )
JWT_ISSUER = os.environ.get("JWT_ISSUER", "acgs2-agent-runtime")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "acgs2-services")

# Security scheme for Bearer token authentication
security = HTTPBearer(auto_error=False)

# SECURITY FIX (2026-03): Fail-closed in production — refuse to start without auth keys.
# Previously this only logged a warning; an operator could miss it and run without JWT
# secrets, leaving the tenant management API unprotected.
if NORMALIZED_ENVIRONMENT == "production" and not TENANT_ADMIN_KEY and not JWT_SECRET_KEY:
    raise ValueError(
        "SECURITY: Production environment requires TENANT_ADMIN_KEY or JWT_SECRET_KEY. "
        "Set at least one via environment variables before starting in production. "
        f"Constitutional Hash: {CONSTITUTIONAL_HASH}"
    )


_DEV_ENVIRONMENTS = frozenset({"development", "dev", "test", "testing", "local"})


def _is_production_runtime() -> bool:
    """Return True for any environment NOT in the explicit dev/test allowlist.

    Staging, preprod, stage, and unknown environments are treated as production-equivalent
    so the dev-mode auth bypass cannot be triggered outside intentional dev/test contexts.
    """
    return NORMALIZED_ENVIRONMENT not in _DEV_ENVIRONMENTS


def _has_auth_configuration() -> bool:
    return bool(TENANT_ADMIN_KEY or JWT_SECRET_KEY)


def _validate_admin_api_key(provided_key: str) -> bool:
    """
    Validate admin API key using timing-safe comparison.

    Args:
        provided_key: The API key provided in the request header.

    Returns:
        True if the key is valid, False otherwise.
    """
    if not TENANT_ADMIN_KEY:
        return False

    # Use timing-safe comparison to prevent timing attacks
    return hmac.compare_digest(
        provided_key.encode("utf-8"),
        TENANT_ADMIN_KEY.encode("utf-8"),
    )


def _validate_jwt_token(token: str) -> dict | None:
    """
    Validate JWT token and extract claims.

    Args:
        token: JWT token string.

    Returns:
        Decoded token payload if valid, None otherwise.
    """
    if not JWT_SECRET_KEY:
        return None

    try:
        import jwt

        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["sub", "tenant_id", "exp", "iat", "iss", "aud"]},
        )

        # Validate constitutional hash if present
        token_hash = payload.get("constitutional_hash")
        if token_hash and token_hash != CONSTITUTIONAL_HASH:
            logger.warning(
                f"JWT constitutional hash mismatch: expected {CONSTITUTIONAL_HASH}, got {token_hash}"
            )
            return None

        # Check for admin role/permission
        maci_role = payload.get("maci_role", "")
        permissions = set(payload.get("permissions", []))

        # Allow CONTROLLER role or explicit admin permission
        if maci_role == "CONTROLLER" or "ADMIN" in permissions or "TENANT_MANAGE" in permissions:
            return payload  # type: ignore[no-any-return]

        logger.warning(
            f"JWT token lacks admin permissions: role={maci_role}, permissions={permissions}"
        )
        return None

    except ImportError:
        logger.warning("PyJWT not available for JWT validation")
        return None
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None


def _ensure_auth_configured() -> None:
    """Ensure authentication is properly configured in production."""
    if _is_production_runtime() and not _has_auth_configuration():
        logger.critical(
            "Tenant management authentication is misconfigured in production; rejecting request"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "Tenant management authentication is not configured",
                "code": "AUTH_CONFIGURATION_ERROR",
                "constitutional_hash": CONSTITUTIONAL_HASH,
            },
        )


def _authenticate_via_jwt(credentials: HTTPAuthorizationCredentials, admin_id: str) -> str:
    """Authenticate request using JWT token."""
    token_payload = _validate_jwt_token(credentials.credentials)
    if token_payload:
        # Extract tenant/agent info from token
        final_admin_id = token_payload.get("tenant_id", admin_id)
        agent_id = token_payload.get("sub", "unknown")
        logger.info(
            f"Tenant management access granted via JWT: agent={agent_id}, tenant={final_admin_id}"
        )
        return str(final_admin_id)
    else:
        # JWT was provided but invalid
        logger.warning(f"Invalid JWT token provided for tenant management from tenant={admin_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Invalid or expired authentication token",
                "code": "INVALID_TOKEN",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )


def _authenticate_via_api_key(x_admin_key: str | None, admin_id: str) -> str:
    """Authenticate request using API key."""
    if not x_admin_key:
        logger.warning(f"Tenant management request without authentication from tenant={admin_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Authentication required. Provide Bearer token or X-Admin-Key header.",
                "code": "AUTH_REQUIRED",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Development mode bypass (DANGEROUS - only for local testing)
    if TENANT_AUTH_MODE == "development" and not _is_production_runtime():
        logger.warning(
            f"SECURITY: Development mode authentication bypass used for tenant={admin_id}. "
            "This should NEVER be enabled in production!"
        )
        return admin_id

    # Validate API key with timing-safe comparison
    if _validate_admin_api_key(x_admin_key):
        logger.info(f"Tenant management access granted via API key for tenant={admin_id}")
        return admin_id

    # Authentication failed
    logger.warning(f"Invalid admin key provided for tenant management from tenant={admin_id}")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": "Invalid authentication credentials",
            "code": "INVALID_CREDENTIALS",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_admin_tenant_id(
    x_admin_tenant_id: str | None = Header(None, alias="X-Admin-Tenant-ID"),
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """Get admin tenant ID for tenant management operations.

    Implements secure authentication using either:
    1. JWT Bearer token authentication (preferred)
    2. API key authentication with timing-safe comparison

    Args:
        x_admin_tenant_id: Optional tenant ID for the admin making the request.
        x_admin_key: API key for authentication (if not using Bearer token).
        credentials: HTTP Bearer credentials for JWT authentication.

    Returns:
        The admin tenant ID to use for the operation.
    """
    _ensure_auth_configured()

    admin_id = x_admin_tenant_id or "system-admin"

    # Try JWT Bearer token authentication first (preferred)
    if credentials and credentials.credentials:
        return _authenticate_via_jwt(credentials, admin_id)

    # Fall back to API key authentication
    return _authenticate_via_api_key(x_admin_key, admin_id)


async def get_optional_tenant_id(
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
) -> str | None:
    """Get optional tenant ID from header."""
    return x_tenant_id


_UUID_RE = None


def _is_uuid(value: str) -> bool:
    """Return True if value looks like a UUID (tenant identity)."""
    global _UUID_RE
    if _UUID_RE is None:
        import re

        _UUID_RE = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
    return bool(_UUID_RE.match(value))


def _check_tenant_scope(
    admin_id: str,
    target_tenant_id: str,
    is_super_admin: bool = False,
) -> None:
    """Enforce cross-tenant scoping for tenant admin operations.

    Raises HTTP 403 if the caller is trying to operate on a tenant they do not own,
    unless they are an explicit super-admin, the system-admin account, the target
    tenant itself, or a non-UUID admin identity (API-key authenticated admin).

    Args:
        admin_id: Authenticated admin identity (tenant_id from JWT or API key identity).
        target_tenant_id: The tenant being operated on (path parameter).
        is_super_admin: Explicit flag for callers that have already validated super-admin
            privileges.
    """
    # Non-UUID admin IDs (e.g. "admin-tenant", "system-admin") represent system-level
    # admins authenticated via API key and have cross-tenant access by design.
    if is_super_admin or admin_id == target_tenant_id or not _is_uuid(admin_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "Cross-tenant access denied",
            "code": "CROSS_TENANT_DENIED",
        },
    )


def _build_tenant_config_and_quota(
    request: CreateTenantRequest,
) -> tuple[TenantConfig | None, TenantQuota | None]:
    """Build TenantConfig and TenantQuota from request data."""
    return (
        TenantConfig(**request.config) if request.config else None,
        TenantQuota(**request.quota) if request.quota else None,
    )


def _parse_status_filter(status_filter: str | None) -> TenantStatus | None:
    """Parse and validate status filter string, raising HTTP 400 if invalid."""
    if not status_filter:
        return None
    try:
        return TenantStatus(status_filter.lower())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid status: {status_filter}. "
                "Valid values: pending, active, suspended, deactivated, migrating"
            ),
        ) from None


async def _get_tenant_or_404(manager: TenantManager, tenant_id: str) -> Tenant:
    """Retrieve tenant by ID, raising HTTP 404 if not found."""
    tenant = await manager.get_tenant(tenant_id)
    if tenant:
        return tenant
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Tenant {tenant_id} not found",
    )


def _tenant_response(tenant: Tenant) -> TenantResponse:
    """Convert Tenant model to TenantResponse."""
    return TenantResponse.from_tenant(tenant)


def _tenant_responses(tenants: list[Tenant]) -> list[TenantResponse]:
    """Convert list of Tenant models to TenantResponse list."""
    return [TenantResponse.from_tenant(tenant) for tenant in tenants]


def _build_tenant_list_response(
    tenants: list[Tenant],
    *,
    page: int,
    page_size: int,
    has_more: bool,
) -> TenantListResponse:
    """Build paginated tenant list response with metadata."""
    return TenantListResponse(
        tenants=_tenant_responses(tenants),
        total_count=len(tenants),
        page=page,
        page_size=page_size,
        has_more=has_more,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


def _extract_usage_and_quota_dicts(
    tenant: Tenant,
    *,
    usage_override: object | None = None,
) -> tuple[JSONDict, JSONDict]:
    """Extract usage and quota as dictionaries from tenant, with optional override."""
    usage_source = usage_override if usage_override is not None else getattr(tenant, "usage", None)
    quota_source = getattr(tenant, "quota", None)
    return _to_dict_safe(usage_source), _to_dict_safe(quota_source)


_QUOTA_RESOURCE_MAP: dict[str, tuple[str, str]] = {
    "agents": ("agents_count", "max_agents"),
    "policies": ("policies_count", "max_policies"),
    "messages": ("messages_this_minute", "max_messages_per_minute"),
    "batch": ("batch_size", "max_batch_size"),
    "storage": ("storage_mb", "max_storage_mb"),
    "sessions": ("concurrent_sessions", "max_concurrent_sessions"),
}


def _quota_resource_keys(resource: str) -> tuple[str, str]:
    """Map resource name to (usage_key, quota_key) tuple."""
    return _QUOTA_RESOURCE_MAP.get(resource, (f"{resource}_count", f"max_{resource}"))


_USAGE_UTILIZATION_PAIRS: tuple[tuple[str, str], ...] = (
    ("agents_count", "max_agents"),
    ("policies_count", "max_policies"),
    ("messages_this_minute", "max_messages_per_minute"),
)


def _calculate_utilization(usage_dict: JSONDict, quota_dict: JSONDict) -> dict[str, float]:
    """Calculate utilization percentages for each resource."""
    utilization: dict[str, float] = {}
    for usage_key, quota_key in _USAGE_UTILIZATION_PAIRS:
        usage_val = usage_dict.get(usage_key, 0)
        quota_val = quota_dict.get(quota_key, 0)
        if (
            isinstance(usage_val, (int, float))
            and isinstance(quota_val, (int, float))
            and quota_val > 0
        ):
            utilization[usage_key] = round(usage_val / quota_val * 100, 2)
    return utilization


def _build_usage_response(
    tenant_id: str,
    *,
    usage_dict: JSONDict,
    quota_dict: JSONDict,
    utilization: dict[str, float] | None = None,
) -> UsageResponse:
    """Build usage response with utilization metrics."""
    return UsageResponse(
        tenant_id=tenant_id,
        usage=usage_dict,
        quota=quota_dict,
        utilization=utilization or {},
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


def _build_quota_check_response(
    tenant_id: str,
    request: QuotaCheckRequest,
    *,
    available: bool,
    usage_dict: JSONDict,
    quota_dict: JSONDict,
) -> QuotaCheckResponse:
    """Build quota check response with availability and warning status."""
    usage_key, quota_key = _quota_resource_keys(request.resource)
    current_usage = usage_dict.get(usage_key, 0)
    quota_limit = quota_dict.get(quota_key, 0)
    if not isinstance(current_usage, int):
        current_usage = 0
    if not isinstance(quota_limit, int):
        quota_limit = 0
    remaining = max(0, quota_limit - current_usage)
    warning_threshold = quota_limit * 0.8
    return QuotaCheckResponse(
        tenant_id=tenant_id,
        resource=request.resource,
        available=available,
        current_usage=current_usage,
        quota_limit=quota_limit,
        requested_amount=request.requested_amount,
        remaining=remaining,
        warning_threshold_reached=current_usage >= warning_threshold,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


def _build_tenant_hierarchy_response(
    tenant_id: str,
    *,
    ancestors: list[Tenant],
    descendants: list[Tenant],
) -> TenantHierarchyResponse:
    """Build tenant hierarchy response with ancestors and descendants."""
    return TenantHierarchyResponse(
        tenant_id=tenant_id,
        ancestors=_tenant_responses(ancestors[:-1]) if len(ancestors) > 1 else [],
        descendants=_tenant_responses(descendants),
        depth=len(ancestors) - 1 if ancestors else 0,
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


def _raise_tenant_not_found(e: TenantNotFoundError) -> NoReturn:
    """Raise HTTP 404 for tenant not found error."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=safe_error_detail(e, "tenant operation"),
    ) from e


def _raise_internal_tenant_error(e: Exception, action: str, log_context: str) -> NoReturn:
    """Log error and raise HTTP 500 for internal tenant operation failure."""
    logger.error(f"Failed to {log_context}: {e}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=safe_error_detail(e, action),
    ) from e


def _raise_value_http_error(
    e: ValueError,
    *,
    action: str,
    duplicate_markers: tuple[str, ...] = ("already exists", "duplicate"),
    conflict_markers: tuple[str, ...] = (),
) -> NoReturn:
    """Raise HTTP 409 for conflicts or HTTP 400 for other ValueError."""
    message = str(e).lower()
    if any(marker in message for marker in duplicate_markers + conflict_markers):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=safe_error_detail(e, "tenant operation"),
        ) from e
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=safe_error_detail(e, "tenant operation" if action == "tenant operation" else action),
    ) from e


# =============================================================================
# Dependency Injection
# =============================================================================


def get_manager() -> TenantManager:
    """Get the tenant manager instance."""
    try:
        return get_tenant_manager()
    except (RuntimeError, ValueError, TypeError) as e:
        logger.error(f"Failed to get tenant manager: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tenant manager not available",
        ) from e


# =============================================================================
# API Endpoints - CRUD Operations
# =============================================================================


@router.post(
    "",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "Tenant created successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request data"},
        409: {"model": ErrorResponse, "description": "Tenant slug already exists"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Create a new tenant",
    description="""
Create a new tenant with the specified configuration.

**Features:**
- Unique slug validation
- Optional hierarchical parent
- Configurable resource quotas
- Auto-activation option

**Constitutional Hash:** 608508a9bd224290
    """,
)
async def create_tenant(
    request: CreateTenantRequest,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> TenantResponse:
    """Create a new tenant."""
    try:
        config, quota = _build_tenant_config_and_quota(request)

        # Create tenant
        tenant = await manager.create_tenant(
            name=request.name,
            slug=request.slug,
            config=config,
            quota=quota,
            metadata=request.metadata,
            parent_tenant_id=request.parent_tenant_id,
            auto_activate=request.auto_activate,
        )

        logger.info(f"Admin {admin_id} created tenant {tenant.tenant_id} ({request.slug})")

        return _tenant_response(tenant)

    except TenantValidationError as e:
        logger.warning(f"Tenant validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "tenant operation"),
        ) from e
    except ValueError as e:
        _raise_value_http_error(e, action="tenant operation")
    except (RuntimeError, TypeError) as e:
        _raise_internal_tenant_error(e, "create tenant", "create tenant")


@router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
    responses={
        200: {"description": "Tenant retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Get tenant by ID",
    description="Retrieve tenant details by tenant ID.",
)
async def get_tenant(
    tenant_id: str,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> TenantResponse:
    """Get tenant by ID."""
    try:
        _check_tenant_scope(admin_id, tenant_id)
        tenant = await _get_tenant_or_404(manager, tenant_id)
        return _tenant_response(tenant)

    except HTTPException:
        raise
    except TenantNotFoundError as e:
        _raise_tenant_not_found(e)
    except (RuntimeError, ValueError, TypeError) as e:
        _raise_internal_tenant_error(e, "retrieve tenant", f"get tenant {tenant_id}")


@router.get(
    "/by-slug/{slug}",
    response_model=TenantResponse,
    responses={
        200: {"description": "Tenant retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Get tenant by slug",
    description="Retrieve tenant details by unique slug.",
)
async def get_tenant_by_slug(
    slug: str,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> TenantResponse:
    """Get tenant by slug."""
    try:
        tenant = await manager.get_tenant_by_slug(slug)

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant with slug '{slug}' not found",
            )

        return _tenant_response(tenant)

    except HTTPException:
        raise
    except (RuntimeError, ValueError, TypeError) as e:
        _raise_internal_tenant_error(e, "retrieve tenant", f"get tenant by slug {slug}")


@router.get(
    "",
    response_model=TenantListResponse,
    responses={
        200: {"description": "Tenants listed successfully"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="List tenants",
    description="List tenants with optional filtering by status and parent.",
)
async def list_tenants(
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    parent_id: str | None = Query(None, description="Filter by parent tenant ID"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum items to return"),
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> TenantListResponse:
    """List tenants with optional filtering."""
    try:
        # Parse status filter
        status_enum = _parse_status_filter(status_filter)

        tenants = await manager.list_tenants(
            status=status_enum,
            parent_id=parent_id,
            skip=skip,
            limit=limit + 1,  # Fetch one extra to check if there's more
        )

        has_more = len(tenants) > limit
        if has_more:
            tenants = tenants[:limit]

        return _build_tenant_list_response(
            tenants,
            page=skip // limit if limit > 0 else 0,
            page_size=limit,
            has_more=has_more,
        )

    except HTTPException:
        raise
    except (RuntimeError, ValueError, TypeError) as e:
        _raise_internal_tenant_error(e, "list tenants", "list tenants")


@router.patch(
    "/{tenant_id}",
    response_model=TenantResponse,
    responses={
        200: {"description": "Tenant updated successfully"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        400: {"model": ErrorResponse, "description": "Invalid update data"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Update tenant",
    description="Update tenant name, configuration, or metadata.",
)
async def update_tenant(
    tenant_id: str,
    request: UpdateTenantRequest,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> TenantResponse:
    """Update tenant details."""
    try:
        _check_tenant_scope(admin_id, tenant_id)

        # Get existing tenant
        tenant = await _get_tenant_or_404(manager, tenant_id)

        # Update name if provided
        if request.name:
            tenant.name = request.name

        # Update config if provided
        if request.config:
            current_config = (
                tenant.config.model_dump() if hasattr(tenant.config, "model_dump") else {}
            )
            current_config.update(request.config)
            tenant = await manager.update_config(tenant_id, TenantConfig(**current_config))

        # Update metadata if provided
        if request.metadata:
            current_metadata = tenant.metadata or {}
            current_metadata.update(request.metadata)
            tenant.metadata = current_metadata

        logger.info(f"Admin {admin_id} updated tenant {tenant_id}")

        return _tenant_response(tenant)

    except HTTPException:
        raise
    except TenantNotFoundError as e:
        _raise_tenant_not_found(e)
    except (RuntimeError, ValueError, TypeError) as e:
        _raise_internal_tenant_error(e, "update tenant", f"update tenant {tenant_id}")


@router.delete(
    "/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        204: {"description": "Tenant deleted successfully"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        409: {"model": ErrorResponse, "description": "Tenant has children"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Delete tenant",
    description="Delete a tenant. Fails if tenant has child tenants unless force=true.",
)
async def delete_tenant(
    tenant_id: str,
    force: bool = Query(False, description="Force delete including children"),
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
):
    """Delete a tenant."""
    try:
        _check_tenant_scope(admin_id, tenant_id)

        success = await manager.delete_tenant(tenant_id, force=force)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {tenant_id} not found",
            )

        logger.info(f"Admin {admin_id} deleted tenant {tenant_id}")

    except HTTPException:
        raise
    except TenantNotFoundError as e:
        _raise_tenant_not_found(e)
    except ValueError as e:
        _raise_value_http_error(e, action="tenant operation", conflict_markers=("children",))
    except (RuntimeError, TypeError) as e:
        _raise_internal_tenant_error(e, "delete tenant", f"delete tenant {tenant_id}")


# =============================================================================
# API Endpoints - Lifecycle Management
# =============================================================================


@router.post(
    "/{tenant_id}/activate",
    response_model=TenantResponse,
    responses={
        200: {"description": "Tenant activated successfully"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        400: {"model": ErrorResponse, "description": "Cannot activate tenant"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Activate tenant",
    description="Activate a pending or suspended tenant.",
)
async def activate_tenant(
    tenant_id: str,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> TenantResponse:
    """Activate a tenant."""
    try:
        _check_tenant_scope(admin_id, tenant_id)

        tenant = await manager.activate_tenant(tenant_id)

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {tenant_id} not found",
            )

        logger.info(f"Admin {admin_id} activated tenant {tenant_id}")

        return _tenant_response(tenant)

    except HTTPException:
        raise
    except TenantNotFoundError as e:
        _raise_tenant_not_found(e)
    except (RuntimeError, ValueError, TypeError) as e:
        _raise_internal_tenant_error(e, "activate tenant", f"activate tenant {tenant_id}")


@router.post(
    "/{tenant_id}/suspend",
    response_model=TenantResponse,
    responses={
        200: {"description": "Tenant suspended successfully"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        400: {"model": ErrorResponse, "description": "Cannot suspend tenant"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Suspend tenant",
    description="Suspend an active tenant with optional reason.",
)
async def suspend_tenant(
    tenant_id: str,
    request: SuspendTenantRequest | None = None,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> TenantResponse:
    """Suspend a tenant."""
    try:
        _check_tenant_scope(admin_id, tenant_id)

        reason = request.reason if request else None
        suspend_children = request.suspend_children if request else True

        tenant = await manager.suspend_tenant(
            tenant_id,
            reason=reason,
            suspend_children=suspend_children,
        )

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {tenant_id} not found",
            )

        logger.info(
            f"Admin {admin_id} suspended tenant {tenant_id}"
            + (f" (reason: {reason})" if reason else "")
        )

        return _tenant_response(tenant)

    except HTTPException:
        raise
    except TenantNotFoundError as e:
        _raise_tenant_not_found(e)
    except (RuntimeError, ValueError, TypeError) as e:
        _raise_internal_tenant_error(e, "suspend tenant", f"suspend tenant {tenant_id}")


@router.post(
    "/{tenant_id}/deactivate",
    response_model=TenantResponse,
    responses={
        200: {"description": "Tenant deactivated successfully"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        400: {"model": ErrorResponse, "description": "Cannot deactivate tenant"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Deactivate tenant",
    description="Permanently deactivate a tenant. This is typically irreversible.",
)
async def deactivate_tenant(
    tenant_id: str,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> TenantResponse:
    """Deactivate a tenant."""
    try:
        _check_tenant_scope(admin_id, tenant_id)

        tenant = await manager.deactivate_tenant(tenant_id)  # type: ignore[attr-defined]

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {tenant_id} not found",
            )

        logger.info(f"Admin {admin_id} deactivated tenant {tenant_id}")

        return _tenant_response(tenant)

    except HTTPException:
        raise
    except TenantNotFoundError as e:
        _raise_tenant_not_found(e)
    except (RuntimeError, ValueError, TypeError) as e:
        _raise_internal_tenant_error(e, "deactivate tenant", f"deactivate tenant {tenant_id}")


# =============================================================================
# API Endpoints - Quota Management
# =============================================================================


@router.put(
    "/{tenant_id}/quota",
    response_model=TenantResponse,
    responses={
        200: {"description": "Quota updated successfully"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        400: {"model": ErrorResponse, "description": "Invalid quota data"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Update tenant quota",
    description="Update resource quota limits for a tenant.",
)
async def update_tenant_quota(
    tenant_id: str,
    request: UpdateQuotaRequest,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> TenantResponse:
    """Update tenant quota."""
    try:
        # Get existing tenant
        tenant = await _get_tenant_or_404(manager, tenant_id)

        # Build updated quota
        current_quota = tenant.quota.model_dump() if hasattr(tenant.quota, "model_dump") else {}
        updates = request.model_dump(exclude_none=True)
        current_quota.update(updates)

        tenant = await manager.update_quota(tenant_id, TenantQuota(**current_quota))

        logger.info(f"Admin {admin_id} updated quota for tenant {tenant_id}")

        return _tenant_response(tenant)

    except HTTPException:
        raise
    except TenantNotFoundError as e:
        _raise_tenant_not_found(e)
    except (RuntimeError, ValueError, TypeError) as e:
        _raise_internal_tenant_error(e, "update quota", f"update quota for tenant {tenant_id}")


@router.post(
    "/{tenant_id}/quota/check",
    response_model=QuotaCheckResponse,
    responses={
        200: {"description": "Quota check completed"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Check quota availability",
    description="Check if quota is available for a specific resource.",
)
async def check_quota(
    tenant_id: str,
    request: QuotaCheckRequest,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> QuotaCheckResponse:
    """Check quota availability."""
    try:
        available = await manager.check_quota(
            tenant_id,
            request.resource,
            request.requested_amount,
        )

        # Get tenant for usage details
        tenant = await manager.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {tenant_id} not found",
            )

        usage_dict, quota_dict = _extract_usage_and_quota_dicts(tenant)

        return _build_quota_check_response(
            tenant_id,
            request,
            available=available,
            usage_dict=usage_dict,
            quota_dict=quota_dict,
        )

    except HTTPException:
        raise
    except TenantNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "tenant operation"),
        ) from e
    except (RuntimeError, ValueError, TypeError) as e:
        logger.error(f"Failed to check quota for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "check quota"),
        ) from e


@router.get(
    "/{tenant_id}/usage",
    response_model=UsageResponse,
    responses={
        200: {"description": "Usage retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Get tenant usage",
    description="Get current resource usage and quota utilization.",
)
async def get_tenant_usage(
    tenant_id: str,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> UsageResponse:
    """Get tenant usage statistics."""
    try:
        tenant = await manager.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {tenant_id} not found",
            )

        usage_dict, quota_dict = _extract_usage_and_quota_dicts(tenant)

        return _build_usage_response(
            tenant_id,
            usage_dict=usage_dict,
            quota_dict=quota_dict,
            utilization=_calculate_utilization(usage_dict, quota_dict),
        )

    except HTTPException:
        raise
    except TenantNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "tenant operation"),
        ) from e
    except (RuntimeError, ValueError, TypeError) as e:
        logger.error(f"Failed to get usage for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "get usage"),
        ) from e


@router.post(
    "/{tenant_id}/usage/increment",
    response_model=UsageResponse,
    responses={
        200: {"description": "Usage incremented successfully"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        429: {"model": ErrorResponse, "description": "Quota exceeded"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Increment usage",
    description="Increment resource usage for a tenant.",
)
async def increment_usage(
    tenant_id: str,
    request: UsageIncrementRequest,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> UsageResponse:
    """Increment tenant usage."""
    try:
        usage = await manager.increment_usage(
            tenant_id,
            request.resource,
            request.amount,
        )

        tenant = await _get_tenant_or_404(manager, tenant_id)
        usage_dict, quota_dict = _extract_usage_and_quota_dicts(tenant, usage_override=usage)

        return _build_usage_response(
            tenant_id,
            usage_dict=usage_dict,
            quota_dict=quota_dict,
        )

    except TenantQuotaExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=safe_error_detail(e, "tenant operation"),
        ) from e
    except TenantNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "tenant operation"),
        ) from e
    except (RuntimeError, ValueError, TypeError) as e:
        logger.error(f"Failed to increment usage for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "increment usage"),
        ) from e


# =============================================================================
# API Endpoints - Hierarchy Management
# =============================================================================


@router.get(
    "/{tenant_id}/hierarchy",
    response_model=TenantHierarchyResponse,
    responses={
        200: {"description": "Hierarchy retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Get tenant hierarchy",
    description="Get the hierarchical structure of a tenant (ancestors and descendants).",
)
async def get_tenant_hierarchy(
    tenant_id: str,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> TenantHierarchyResponse:
    """Get tenant hierarchy."""
    try:
        # Get ancestors (path from root to this tenant)
        ancestors = await manager.get_tenant_hierarchy(tenant_id)

        # Get descendants (children recursively)
        descendants = await manager.get_all_descendants(tenant_id)

        return _build_tenant_hierarchy_response(
            tenant_id,
            ancestors=ancestors,
            descendants=descendants,
        )

    except TenantNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "tenant operation"),
        ) from e
    except (RuntimeError, ValueError, TypeError) as e:
        logger.error(f"Failed to get hierarchy for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "get hierarchy"),
        ) from e


@router.get(
    "/{tenant_id}/children",
    response_model=TenantListResponse,
    responses={
        200: {"description": "Children retrieved successfully"},
        404: {"model": ErrorResponse, "description": "Tenant not found"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        503: {"model": ErrorResponse, "description": "Service unavailable"},
    },
    summary="Get child tenants",
    description="Get immediate child tenants of a tenant.",
)
async def get_child_tenants(
    tenant_id: str,
    admin_id: str = Depends(get_admin_tenant_id),
    manager: TenantManager = Depends(get_manager),
) -> TenantListResponse:
    """Get child tenants."""
    try:
        children = await manager.get_child_tenants(tenant_id)

        return _build_tenant_list_response(
            children,
            page=0,
            page_size=len(children),
            has_more=False,
        )

    except TenantNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "tenant operation"),
        ) from e
    except (RuntimeError, ValueError, TypeError) as e:
        logger.error(f"Failed to get children for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "get children"),
        ) from e


# Export router
__all__ = ["router"]
