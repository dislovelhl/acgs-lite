"""
ACGS-2 Tenant Context Middleware
Constitutional Hash: cdd01ef066bc6cf2

Extracts and validates tenant context from X-Tenant-ID header for
multi-tenant isolation. Ensures all requests are properly scoped
to their respective tenants.

Security Features:
- Tenant ID validation (alphanumeric, hyphens, underscores only)
- Maximum length enforcement (64 characters)
- Path traversal prevention
- Injection attack prevention
- Request state propagation

Usage:
    from src.core.shared.security.tenant_context import TenantContextMiddleware, get_tenant_id

    app.add_middleware(TenantContextMiddleware)

    @app.get("/api/resource")
    async def get_resource(tenant_id: str = Depends(get_tenant_id)):
        # tenant_id is guaranteed to be valid
        pass
"""

import os
import re
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field

from fastapi import Header, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse, Response

# Constitutional hash for validation
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ACGSBaseError
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)
# Context variable for tenant ID (thread-safe)
_tenant_id_ctx: ContextVar[str | None] = ContextVar("tenant_id", default=None)

# Tenant ID validation constants
TENANT_ID_MAX_LENGTH = 64
TENANT_ID_MIN_LENGTH = 1
# Pattern: alphanumeric, hyphens, underscores; must start/end with alphanumeric
TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-_]{0,62}[a-zA-Z0-9]$|^[a-zA-Z0-9]$")
# Characters that could indicate injection attempts
DANGEROUS_CHARS = re.compile(r"[<>'\";`\\|&$(){}[\]]")


class TenantValidationError(ACGSBaseError):
    """Raised when tenant ID validation fails (Q-H4 migration)."""

    http_status_code = 400
    error_code = "TENANT_VALIDATION_ERROR"

    def __init__(self, message: str, tenant_id: str | None = None, **kwargs):
        self.tenant_id = tenant_id
        details = kwargs.pop("details", {}) or {}
        details["tenant_id"] = tenant_id
        super().__init__(message, details=details, **kwargs)

    def __str__(self) -> str:
        """Preserve legacy string representation expected by callers/tests."""
        return self.message


@dataclass
class TenantContextConfig:
    """
    Configuration for tenant context middleware.

    Attributes:
        header_name: HTTP header containing tenant ID
        enabled: Whether tenant context extraction is enabled
        required: Whether X-Tenant-ID header is required
        exempt_paths: Paths exempt from tenant ID requirement
        allow_query_param: Allow tenant_id in query parameters as fallback
        echo_header: Include tenant ID in response headers
        fail_open: Allow requests without tenant ID when not required
    """

    header_name: str = "X-Tenant-ID"
    enabled: bool = True
    required: bool = True
    exempt_paths: list[str] = field(
        default_factory=lambda: [
            "/health",
            "/healthz",
            "/ready",
            "/readyz",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
        ]
    )
    allow_query_param: bool = False
    echo_header: bool = True
    fail_open: bool = False

    @classmethod
    def from_env(cls) -> "TenantContextConfig":
        """Create configuration from environment variables."""
        exempt_paths_str = os.environ.get("TENANT_EXEMPT_PATHS", "")
        exempt_paths = [p.strip() for p in exempt_paths_str.split(",") if p.strip()]

        return cls(
            header_name=os.environ.get("TENANT_HEADER_NAME", "X-Tenant-ID"),
            enabled=os.environ.get("TENANT_CONTEXT_ENABLED", "true").lower() == "true",
            required=os.environ.get("TENANT_CONTEXT_REQUIRED", "true").lower() == "true",
            exempt_paths=exempt_paths
            or [
                "/health",
                "/healthz",
                "/ready",
                "/readyz",
                "/metrics",
                "/docs",
                "/redoc",
                "/openapi.json",
                "/favicon.ico",
            ],
            allow_query_param=os.environ.get("TENANT_ALLOW_QUERY_PARAM", "false").lower() == "true",
            echo_header=os.environ.get("TENANT_ECHO_HEADER", "true").lower() == "true",
            fail_open=os.environ.get("TENANT_FAIL_OPEN", "false").lower() == "true",
        )


def validate_tenant_id(tenant_id: str) -> bool:
    """
    Validate tenant ID for security and format compliance.

    Args:
        tenant_id: The tenant ID to validate

    Returns:
        True if valid, raises TenantValidationError otherwise

    Raises:
        TenantValidationError: If validation fails
    """
    if not tenant_id:
        raise TenantValidationError("Tenant ID cannot be empty")

    # Check length
    if len(tenant_id) < TENANT_ID_MIN_LENGTH:
        raise TenantValidationError(
            f"Tenant ID must be at least {TENANT_ID_MIN_LENGTH} character(s)",
            tenant_id=tenant_id,
        )

    if len(tenant_id) > TENANT_ID_MAX_LENGTH:
        raise TenantValidationError(
            f"Tenant ID exceeds maximum length of {TENANT_ID_MAX_LENGTH}",
            tenant_id=tenant_id[:20] + "...",  # Truncate for logging
        )

    # Check for dangerous characters (injection prevention)
    if DANGEROUS_CHARS.search(tenant_id):
        logger.warning(f"Rejected tenant ID with dangerous characters: {tenant_id[:20]}...")
        raise TenantValidationError(
            "Tenant ID contains invalid characters",
            tenant_id=None,  # Don't log potentially malicious input
        )

    # Check for path traversal attempts
    if ".." in tenant_id or "/" in tenant_id or "\\" in tenant_id:
        logger.warning("Rejected tenant ID with path traversal attempt")
        raise TenantValidationError(
            "Tenant ID contains invalid path characters",
            tenant_id=None,
        )

    # Check format pattern
    if not TENANT_ID_PATTERN.match(tenant_id):
        raise TenantValidationError(
            "Tenant ID must start and end with alphanumeric characters, "
            "and contain only alphanumeric characters, hyphens, or underscores",
            tenant_id=tenant_id,
        )

    return True


def sanitize_tenant_id(tenant_id: str) -> str:
    """
    Sanitize tenant ID by stripping whitespace.

    Args:
        tenant_id: Raw tenant ID from request

    Returns:
        Sanitized tenant ID
    """
    return tenant_id.strip()


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette middleware for tenant context extraction and validation.

    Extracts X-Tenant-ID header from requests, validates it, and attaches
    the tenant context to the request state for downstream use.

    Features:
    - Tenant ID format validation
    - Security checks for injection prevention
    - Request state propagation
    - Optional response header echo
    - Configurable exempt paths

    Example:
        from src.core.shared.security.tenant_context import TenantContextMiddleware

        app = FastAPI()
        app.add_middleware(TenantContextMiddleware)
    """

    def __init__(
        self,
        app: object,
        config: TenantContextConfig | None = None,
    ):
        super().__init__(app)
        self.config = config or TenantContextConfig.from_env()
        self._constitutional_hash = CONSTITUTIONAL_HASH

        if not self.config.enabled:
            logger.info("Tenant context middleware is disabled")

    def _is_exempt(self, path: str) -> bool:
        """Check if path is exempt from tenant ID requirement."""
        return any(path.startswith(exempt_path) for exempt_path in self.config.exempt_paths)

    def _extract_tenant_id(self, request: StarletteRequest) -> str | None:
        """
        Extract tenant ID from request headers or query params.

        Args:
            request: The incoming request

        Returns:
            Tenant ID if found, None otherwise
        """
        # Try header first
        tenant_id = request.headers.get(self.config.header_name)
        if tenant_id:
            return sanitize_tenant_id(tenant_id)

        # Try query parameter if allowed
        if self.config.allow_query_param:
            tenant_id = request.query_params.get("tenant_id")
            if tenant_id:
                return sanitize_tenant_id(tenant_id)

        return None

    async def dispatch(
        self,
        request: StarletteRequest,
        call_next: Callable,
    ) -> Response:
        """Process request through tenant context extraction."""
        # Skip if disabled
        if not self.config.enabled:
            return await call_next(request)

        # Skip exempt paths
        if self._is_exempt(request.url.path):
            return await call_next(request)

        # Extract tenant ID
        tenant_id = self._extract_tenant_id(request)

        # Handle missing tenant ID
        if not tenant_id:
            if self.config.required and not self.config.fail_open:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Bad Request",
                        "message": f"Missing required header: {self.config.header_name}",
                        "code": "MISSING_TENANT_ID",
                        "constitutional_hash": self._constitutional_hash,
                    },
                )
            # Fail open or not required - continue without tenant context
            return await call_next(request)

        # Validate tenant ID
        try:
            validate_tenant_id(tenant_id)
        except TenantValidationError as e:
            logger.warning(f"Invalid tenant ID: {e.message}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Bad Request",
                    "message": f"Invalid tenant ID: {e.message}",
                    "code": "INVALID_TENANT_ID",
                    "constitutional_hash": self._constitutional_hash,
                },
            )

        # Attach tenant context to request state
        request.state.tenant_id = tenant_id

        # Set context variable for thread-safe access
        token = _tenant_id_ctx.set(tenant_id)

        try:
            # Process request
            response = await call_next(request)

            # Echo tenant ID in response header
            if self.config.echo_header:
                response.headers[self.config.header_name] = tenant_id

            return response
        finally:
            # Reset context variable
            _tenant_id_ctx.reset(token)


def get_current_tenant_id() -> str | None:
    """
    Get the current tenant ID from context variable.

    This can be used outside of request handlers where the request
    object is not available.

    Returns:
        Current tenant ID or None
    """
    return _tenant_id_ctx.get()


async def get_tenant_id(
    request: Request,
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
) -> str:
    """
    FastAPI dependency to get validated tenant ID.

    Use this in route handlers to get the tenant ID with proper
    validation and error handling.

    Args:
        request: FastAPI request object
        x_tenant_id: Tenant ID from header (automatically extracted)

    Returns:
        Validated tenant ID string

    Raises:
        HTTPException: If tenant ID is missing or invalid

    Example:
        @app.get("/api/resources")
        async def list_resources(tenant_id: str = Depends(get_tenant_id)):
            return get_resources_for_tenant(tenant_id)
    """
    # Try request state first (set by middleware)
    tenant_id = getattr(request.state, "tenant_id", None)

    # Fall back to header if not in state
    if not tenant_id and x_tenant_id:
        tenant_id = sanitize_tenant_id(x_tenant_id)

    # Check if present
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Bad Request",
                "message": "Missing required header: X-Tenant-ID",
                "code": "MISSING_TENANT_ID",
            },
        )

    # Validate
    try:
        validate_tenant_id(tenant_id)
    except TenantValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Bad Request",
                "message": f"Invalid tenant ID: {e.message}",
                "code": "INVALID_TENANT_ID",
            },
        ) from e

    return tenant_id


async def get_optional_tenant_id(
    request: Request,
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
) -> str | None:
    """
    FastAPI dependency to get optional tenant ID.

    Similar to get_tenant_id but returns None if not provided
    instead of raising an exception.

    Args:
        request: FastAPI request object
        x_tenant_id: Tenant ID from header (automatically extracted)

    Returns:
        Validated tenant ID string or None

    Raises:
        HTTPException: Only if tenant ID is provided but invalid

    Example:
        @app.get("/api/public")
        async def public_endpoint(tenant_id: Optional[str] = Depends(get_optional_tenant_id)):
            if tenant_id:
                return get_tenant_specific_content(tenant_id)
            return get_default_content()
    """
    # Try request state first (set by middleware)
    tenant_id = getattr(request.state, "tenant_id", None)

    # Fall back to header if not in state
    if not tenant_id and x_tenant_id:
        tenant_id = sanitize_tenant_id(x_tenant_id)

    # Return None if not present
    if not tenant_id:
        return None

    # Validate if present
    try:
        validate_tenant_id(tenant_id)
    except TenantValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Bad Request",
                "message": f"Invalid tenant ID: {e.message}",
                "code": "INVALID_TENANT_ID",
            },
        ) from e

    return tenant_id


def require_tenant_scope(tenant_id_from_request: str, resource_tenant_id: str) -> None:
    """
    Verify that a request's tenant ID matches a resource's tenant ID.

    Use this to enforce cross-tenant access prevention.

    Args:
        tenant_id_from_request: Tenant ID from the current request
        resource_tenant_id: Tenant ID associated with the resource

    Raises:
        HTTPException: 403 if tenant IDs don't match
    """
    if tenant_id_from_request != resource_tenant_id:
        logger.warning(
            f"Cross-tenant access attempt: request tenant '{tenant_id_from_request}' "
            f"tried to access resource for tenant '{resource_tenant_id}'"
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Forbidden",
                "message": "Access denied: resource belongs to a different tenant",
                "code": "CROSS_TENANT_ACCESS_DENIED",
            },
        )


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "TENANT_ID_MAX_LENGTH",
    "TENANT_ID_MIN_LENGTH",
    "TENANT_ID_PATTERN",
    "TenantContextConfig",
    # Middleware
    "TenantContextMiddleware",
    # Errors
    "TenantValidationError",
    "get_current_tenant_id",
    "get_optional_tenant_id",
    # Dependencies
    "get_tenant_id",
    "require_tenant_scope",
    "sanitize_tenant_id",
    # Validation
    "validate_tenant_id",
]
