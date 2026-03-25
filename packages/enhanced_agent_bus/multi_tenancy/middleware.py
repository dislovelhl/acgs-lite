"""
ACGS-2 Multi-Tenancy Middleware
Constitutional Hash: 608508a9bd224290

FastAPI middleware for automatic tenant context management.
Extracts tenant identification from requests and sets the tenant context.
"""

from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from enhanced_agent_bus.observability.structured_logging import get_logger

from .context import CONSTITUTIONAL_HASH, TenantContext, clear_tenant_context, set_current_tenant

logger = get_logger(__name__)
# Header names for tenant identification
TENANT_ID_HEADER = "X-Tenant-ID"
TENANT_SLUG_HEADER = "X-Tenant-Slug"
CONSTITUTIONAL_HASH_HEADER = "X-Constitutional-Hash"

# URL patterns that don't require tenant context
PUBLIC_PATHS = [
    "/health",
    "/ready",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
]


def extract_tenant_from_request(request: Request) -> str | None:
    """Extract tenant ID from request with security validation.

    Constitutional Hash: 608508a9bd224290

    SECURITY: Tenant ID extraction follows principle of least privilege.
    JWT claims are the authoritative source for tenant identity.

    Priority order (most secure first):
    1. JWT token claims (authoritative, validated by auth middleware)
    2. X-Tenant-ID header (must match JWT if both present)
    3. URL path parameter (must match JWT if present)

    REMOVED: Query parameter extraction - too easily spoofed.

    Args:
        request: Starlette/FastAPI request object.

    Returns:
        Tenant ID if found and validated, None otherwise.
    """
    jwt_tenant_id: str | None = None

    # Primary source: JWT claims (set by auth middleware)
    if hasattr(request.state, "user"):
        user = request.state.user
        jwt_tenant_id = getattr(user, "tenant_id", None)
        if jwt_tenant_id:
            # JWT is authoritative - validate other sources match
            header_tenant = request.headers.get(TENANT_ID_HEADER)
            if header_tenant and header_tenant != jwt_tenant_id:
                logger.warning(
                    f"Tenant ID mismatch: header={header_tenant}, jwt={jwt_tenant_id}. "
                    "Using JWT tenant (authoritative). Constitutional Hash: 608508a9bd224290"
                )
            path_tenant = request.path_params.get("tenant_id")
            if path_tenant and path_tenant != jwt_tenant_id:
                logger.warning(
                    f"Tenant ID mismatch: path={path_tenant}, jwt={jwt_tenant_id}. "
                    "Using JWT tenant (authoritative). Constitutional Hash: 608508a9bd224290"
                )
            return jwt_tenant_id

    # Fallback: X-Tenant-ID header (for service-to-service calls)
    raw_tenant_id = request.headers.get(TENANT_ID_HEADER)
    if raw_tenant_id:
        return str(raw_tenant_id)

    # Fallback: URL path parameter
    if "tenant_id" in request.path_params:
        return str(request.path_params["tenant_id"])

    # SECURITY: Query parameter extraction REMOVED - too easily spoofed
    # Do NOT add: request.query_params.get("tenant_id")

    return None


def extract_user_from_request(request: Request) -> str | None:
    """Extract user ID from request.

    Args:
        request: Starlette/FastAPI request object.

    Returns:
        User ID if found, None otherwise.
    """
    # Try from JWT claims (set by auth middleware)
    if hasattr(request.state, "user"):
        return getattr(request.state.user, "sub", None)  # type: ignore[no-any-return]

    # Try from header
    raw_uid = request.headers.get("X-User-ID")
    return str(raw_uid) if raw_uid else None


def is_admin_request(request: Request) -> bool:
    """Check if request is from an admin user.

    Args:
        request: Starlette/FastAPI request object.

    Returns:
        True if admin, False otherwise.
    """
    # Check from JWT claims
    if hasattr(request.state, "user"):
        user = request.state.user
        if hasattr(user, "is_admin"):
            return bool(user.is_admin)
        if hasattr(user, "roles"):
            return "admin" in user.roles or "super_admin" in user.roles

    # Check from header (for internal services)
    admin_header = request.headers.get("X-Admin", "").lower()
    return admin_header in ("true", "1", "yes")


class TenantMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for tenant context management.

    Constitutional Hash: 608508a9bd224290

    This middleware:
    1. Extracts tenant ID from incoming requests
    2. Sets the tenant context for the request duration
    3. Clears the context after response

    Usage:
        from fastapi import FastAPI
        from multi_tenancy.middleware import TenantMiddleware

        app = FastAPI()
        app.add_middleware(TenantMiddleware)
    """

    def __init__(
        self,
        app: Callable,
        require_tenant: bool = True,
        public_paths: list[str] | None = None,
        tenant_header: str = TENANT_ID_HEADER,
    ) -> None:
        """Initialize the middleware.

        Args:
            app: ASGI application.
            require_tenant: Whether to require tenant for non-public paths.
            public_paths: Paths that don't require tenant context.
            tenant_header: Header name for tenant ID.
        """
        super().__init__(app)
        self.require_tenant = require_tenant
        self.public_paths = public_paths or PUBLIC_PATHS
        self.tenant_header = tenant_header

    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (doesn't require tenant)."""
        return any(path.startswith(public_path) for public_path in self.public_paths)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Process the request with tenant context.

        Args:
            request: Incoming request.
            call_next: Next middleware/handler.

        Returns:
            Response with tenant context headers.
        """
        path = request.url.path

        # Skip tenant context for public paths
        if self._is_public_path(path):
            return await call_next(request)

        # Extract tenant ID
        tenant_id = extract_tenant_from_request(request)

        if not tenant_id:
            if self.require_tenant:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "tenant_required",
                        "message": f"Missing {self.tenant_header} header",
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                )
            # Continue without tenant context
            return await call_next(request)

        # Validate constitutional hash if provided
        request_hash = request.headers.get(CONSTITUTIONAL_HASH_HEADER)
        if request_hash and request_hash != CONSTITUTIONAL_HASH:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "constitutional_hash_mismatch",
                    "message": "Invalid constitutional hash",
                    "expected": CONSTITUTIONAL_HASH,
                    "received": request_hash,
                },
            )

        # Create tenant context
        context = TenantContext(
            tenant_id=tenant_id,
            constitutional_hash=CONSTITUTIONAL_HASH,
            user_id=extract_user_from_request(request),
            request_id=request.headers.get("X-Request-ID"),
            source_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            is_admin=is_admin_request(request),
        )

        # Validate context
        if not context.validate():
            return JSONResponse(
                status_code=403,
                content={
                    "error": "invalid_tenant_context",
                    "message": "Tenant context validation failed",
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        # Set context and process request
        set_current_tenant(context)
        try:
            # Store context in request state for access in handlers
            request.state.tenant_context = context

            response = await call_next(request)

            # Add tenant context to response headers
            response.headers["X-Tenant-ID"] = tenant_id
            response.headers["X-Constitutional-Hash"] = CONSTITUTIONAL_HASH

            return response

        finally:
            # Always clear context
            clear_tenant_context()


class TenantContextDependency:
    """FastAPI dependency for tenant context.

    Usage:
        from fastapi import Depends
        from multi_tenancy.middleware import TenantContextDependency

        get_tenant = TenantContextDependency()

        @app.get("/items")
        async def list_items(ctx: TenantContext = Depends(get_tenant)):
            return await repository.list_items()
    """

    def __init__(self, required: bool = True) -> None:
        """Initialize the dependency.

        Args:
            required: Whether tenant context is required.
        """
        self.required = required

    async def __call__(self, request: Request) -> TenantContext | None:
        """Get tenant context from request.

        Args:
            request: FastAPI request.

        Returns:
            TenantContext if available.

        Raises:
            HTTPException: If required and not available.
        """
        from fastapi import HTTPException

        # Try from request state (set by middleware)
        if hasattr(request.state, "tenant_context"):
            return request.state.tenant_context  # type: ignore[no-any-return]

        # Try to extract directly
        tenant_id = extract_tenant_from_request(request)
        if tenant_id:
            return TenantContext(
                tenant_id=tenant_id,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

        if self.required:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "tenant_required",
                    "message": "Tenant context not available",
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                },
            )

        return None
