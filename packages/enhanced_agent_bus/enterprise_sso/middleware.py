"""
ACGS-2 Enterprise SSO Authentication Middleware
Constitutional Hash: 608508a9bd224290

FastAPI middleware for SSO authentication with multi-tenancy integration.
Provides request-scoped SSO session management and authentication enforcement.

Phase 10 Task 2: Enterprise SSO & Identity Management Integration
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from functools import wraps
from typing import (
    TYPE_CHECKING,
    TypeVar,
)

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

# Optional FastAPI imports
try:
    from fastapi import Depends, HTTPException, Request, Response
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    # Create placeholder classes for type hints
    Request = object  # type: ignore[misc, assignment]
    Response = object  # type: ignore[misc, assignment]
    HTTPException = Exception  # type: ignore[misc, assignment]
    BaseHTTPMiddleware = object  # type: ignore[misc, assignment]

if TYPE_CHECKING:
    from .integration import EnterpriseSSOService

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

logger = get_logger(__name__)
_SSO_MIDDLEWARE_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)

# Context variable for SSO session
_sso_session_context: ContextVar[SSOSessionContext | None] = ContextVar(
    "sso_session_context", default=None
)

F = TypeVar("F", bound=Callable[..., object])


@dataclass
class SSOSessionContext:
    """Request-scoped SSO session context."""

    session_id: str
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    maci_roles: list[str]
    idp_groups: list[str]
    attributes: JSONDict
    authenticated_at: datetime
    expires_at: datetime
    access_token: str | None = None
    refresh_token: str | None = None
    idp_id: str | None = None
    idp_type: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.now(UTC) >= self.expires_at

    @property
    def time_until_expiry(self) -> float:
        """Get seconds until session expires."""
        delta = self.expires_at - datetime.now(UTC)
        return max(0.0, delta.total_seconds())

    def has_role(self, role: str) -> bool:
        """Check if session has a specific MACI role."""
        return role.upper() in [r.upper() for r in self.maci_roles]

    def has_any_role(self, roles: list[str]) -> bool:
        """Check if session has any of the specified MACI roles."""
        upper_roles = {r.upper() for r in roles}
        session_roles = {r.upper() for r in self.maci_roles}
        return bool(upper_roles & session_roles)

    def has_all_roles(self, roles: list[str]) -> bool:
        """Check if session has all of the specified MACI roles."""
        upper_roles = {r.upper() for r in roles}
        session_roles = {r.upper() for r in self.maci_roles}
        return upper_roles.issubset(session_roles)

    def to_dict(self) -> JSONDict:
        """Convert context to dictionary."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "email": self.email,
            "display_name": self.display_name,
            "maci_roles": self.maci_roles,
            "idp_groups": self.idp_groups,
            "attributes": self.attributes,
            "authenticated_at": self.authenticated_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "idp_id": self.idp_id,
            "idp_type": self.idp_type,
            "constitutional_hash": self.constitutional_hash,
        }


def get_current_sso_session() -> SSOSessionContext | None:
    """
    Get the current SSO session from context.

    Returns:
        Current SSO session context or None if not authenticated.
    """
    return _sso_session_context.get()


def set_sso_session(session: SSOSessionContext | None) -> None:
    """
    Set the current SSO session in context.

    Args:
        session: SSO session context to set, or None to clear.
    """
    _sso_session_context.set(session)


def clear_sso_session() -> None:
    """Clear the current SSO session from context."""
    _sso_session_context.set(None)


def _raise_auth_error(status: int, detail: str, headers: dict | None = None) -> None:
    """Raise HTTPException if FastAPI is available, else PermissionError."""
    if FASTAPI_AVAILABLE:
        raise HTTPException(status_code=status, detail=detail, headers=headers or {})
    raise PermissionError(detail)


def _check_session_valid(session: object | None, allow_expired: bool) -> None:
    """Check session exists and is not expired; raise on failure."""
    if session is None:
        _raise_auth_error(401, "SSO authentication required", {"WWW-Authenticate": "Bearer"})
    if not allow_expired and getattr(session, "is_expired", False):
        _raise_auth_error(401, "SSO session expired", {"WWW-Authenticate": "Bearer"})


def _check_session_roles(session: object, roles: list[str], any_role: bool) -> None:
    """Check MACI role requirements; raise on failure."""
    if not roles:
        return
    if any_role:
        if not session.has_any_role(roles):  # type: ignore[union-attr]
            _raise_auth_error(403, f"Requires one of roles: {roles}")
    else:
        if not session.has_all_roles(roles):  # type: ignore[union-attr]
            _raise_auth_error(403, f"Requires all roles: {roles}")


def _check_session_valid_sync(session: object | None, allow_expired: bool) -> None:
    """Check session exists and is not expired; raise PermissionError (sync path)."""
    if session is None:
        raise PermissionError("SSO authentication required")
    if not allow_expired and getattr(session, "is_expired", False):
        raise PermissionError("SSO session expired")


def _check_session_roles_sync(session: object, roles: list[str], any_role: bool) -> None:
    """Check MACI role requirements; raise PermissionError (sync path)."""
    if not roles:
        return
    if any_role:
        if not session.has_any_role(roles):  # type: ignore[union-attr]
            raise PermissionError(f"Requires one of roles: {roles}")
    else:
        if not session.has_all_roles(roles):  # type: ignore[union-attr]
            raise PermissionError(f"Requires all roles: {roles}")


def require_sso_authentication(
    roles: list[str] | None = None,
    any_role: bool = True,
    allow_expired: bool = False,
) -> Callable[[F], F]:
    """
    Decorator to require SSO authentication for a function.

    Args:
        roles: Optional list of required MACI roles.
        any_role: If True, any listed role is sufficient. If False, all roles required.
        allow_expired: If True, allow expired sessions (for token refresh flows).

    Returns:
        Decorated function that enforces SSO authentication.

    Example:
        @require_sso_authentication(roles=["ADMIN", "OPERATOR"], any_role=True)
        async def admin_endpoint(request: Request):
            session = get_current_sso_session()
            return {"user": session.user_id}
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: object, **kwargs: object) -> object:
            session = get_current_sso_session()
            _check_session_valid(session, allow_expired)
            _check_session_roles(session, roles or [], any_role)
            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args: object, **kwargs: object) -> object:
            session = get_current_sso_session()
            _check_session_valid_sync(session, allow_expired)
            _check_session_roles_sync(session, roles or [], any_role)
            return func(*args, **kwargs)

        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


@dataclass
class SSOMiddlewareConfig:
    """Configuration for SSO authentication middleware."""

    # Paths that don't require authentication
    excluded_paths: set[str] = field(
        default_factory=lambda: {
            "/health",
            "/healthz",
            "/ready",
            "/readyz",
            "/metrics",
            "/api/v1/auth/login",
            "/api/v1/auth/sso/callback",
            "/api/v1/auth/sso/metadata",
            "/docs",
            "/redoc",
            "/openapi.json",
        }
    )

    # Path prefixes that don't require authentication
    excluded_prefixes: set[str] = field(
        default_factory=lambda: {
            "/static/",
            "/assets/",
            "/.well-known/",
        }
    )

    # Header name for session token
    token_header: str = "Authorization"

    # Token prefix (e.g., "Bearer")
    token_prefix: str = "Bearer"

    # Cookie name for session token (alternative to header)
    session_cookie: str = "acgs_sso_session"

    # Whether to check cookie if header is missing
    allow_cookie_auth: bool = True

    # Whether to set tenant context from SSO session
    set_tenant_context: bool = True

    # Whether to require valid session (vs just parsing if present)
    # Fail-closed: require authentication by default
    require_authentication: bool = True

    # Whether to refresh sessions that are close to expiry
    auto_refresh_sessions: bool = True

    # Refresh when less than this many seconds remain
    refresh_threshold_seconds: int = 300  # 5 minutes

    # Constitutional hash for validation
    constitutional_hash: str = CONSTITUTIONAL_HASH


if FASTAPI_AVAILABLE:

    class SSOAuthenticationMiddleware(BaseHTTPMiddleware):
        """
        FastAPI middleware for SSO authentication.

        Extracts SSO tokens from requests, validates sessions,
        and sets up request-scoped SSO context with multi-tenancy integration.

        Example:
            from fastapi import FastAPI
            from enterprise_sso.middleware import SSOAuthenticationMiddleware

            app = FastAPI()
            app.add_middleware(
                SSOAuthenticationMiddleware,
                sso_service=enterprise_sso_service,
                config=SSOMiddlewareConfig(require_authentication=True),
            )
        """

        def __init__(
            self,
            app: object,
            sso_service: EnterpriseSSOService,
            config: SSOMiddlewareConfig | None = None,
        ):
            """
            Initialize SSO authentication middleware.

            Args:
                app: FastAPI application.
                sso_service: Enterprise SSO service instance.
                config: Middleware configuration.
            """
            super().__init__(app)
            self.sso_service = sso_service
            self.config = config or SSOMiddlewareConfig()

            logger.info(
                "SSO middleware initialized with constitutional hash: %s",
                self.config.constitutional_hash,
            )

        async def dispatch(
            self,
            request: Request,
            call_next: RequestResponseEndpoint,
        ) -> Response:
            """
            Process request through SSO authentication.

            Args:
                request: Incoming HTTP request.
                call_next: Next middleware or route handler.

            Returns:
                HTTP response.
            """
            # Check if path is excluded from authentication
            if self._is_excluded_path(request.url.path):
                return await call_next(request)

            # Extract token from request
            token = self._extract_token(request)

            if token is None:
                if self.config.require_authentication:
                    return Response(
                        content='{"detail": "SSO authentication required"}',
                        status_code=401,
                        media_type="application/json",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                return await call_next(request)

            # Validate session and create context
            try:
                session_context = await self._validate_and_create_context(token, request)

                if session_context is None:
                    if self.config.require_authentication:
                        return Response(
                            content='{"detail": "Invalid or expired SSO session"}',
                            status_code=401,
                            media_type="application/json",
                            headers={"WWW-Authenticate": "Bearer"},
                        )
                    return await call_next(request)

                # Set SSO session context
                set_sso_session(session_context)

                # Set tenant context if configured
                if self.config.set_tenant_context:
                    await self._set_tenant_context(session_context)

                try:
                    # Process request
                    response = await call_next(request)

                    # Auto-refresh session if needed
                    if self.config.auto_refresh_sessions:
                        response = await self._handle_session_refresh(session_context, response)

                    return response
                finally:
                    # Clear SSO session context
                    clear_sso_session()

            except _SSO_MIDDLEWARE_OPERATION_ERRORS as e:
                logger.exception("SSO middleware error: %s", str(e))
                if self.config.require_authentication:
                    return Response(
                        content='{"detail": "SSO authentication error"}',
                        status_code=500,
                        media_type="application/json",
                    )
                return await call_next(request)

        def _is_excluded_path(self, path: str) -> bool:
            """Check if path is excluded from authentication."""
            if path in self.config.excluded_paths:
                return True

            return any(path.startswith(prefix) for prefix in self.config.excluded_prefixes)

        def _extract_token(self, request: Request) -> str | None:
            """Extract SSO token from request headers or cookies."""
            # Try Authorization header first
            auth_header = request.headers.get(self.config.token_header)
            if auth_header:
                prefix = f"{self.config.token_prefix} "
                if auth_header.startswith(prefix):
                    return str(auth_header[len(prefix) :])
                # Handle case where token is passed without prefix
                if not auth_header.startswith(("Bearer ", "Basic ")):
                    return str(auth_header)

            # Try cookie if allowed
            if self.config.allow_cookie_auth:
                cookie_token = request.cookies.get(self.config.session_cookie)
                if cookie_token:
                    return str(cookie_token)

            return None

        async def _validate_and_create_context(
            self,
            token: str,
            request: Request,
        ) -> SSOSessionContext | None:
            """Validate token and create SSO session context."""
            try:
                # Validate session with SSO service
                session = self.sso_service.validate_session(token)

                if session is None:
                    return None

                # Check if session is expired
                # Note: session is SSOSession dataclass, access attributes directly
                session_expires_at = getattr(session, "expires_at", None)
                if session_expires_at:
                    if isinstance(session_expires_at, str):
                        expires_at = datetime.fromisoformat(
                            session_expires_at.replace("Z", "+00:00")
                        )
                    else:
                        expires_at = session_expires_at
                    if datetime.now(UTC) >= expires_at:
                        return None
                else:
                    expires_at = datetime.now(UTC)

                # Parse authenticated_at
                session_auth_at = getattr(session, "authenticated_at", None)
                if session_auth_at:
                    if isinstance(session_auth_at, str):
                        authenticated_at = datetime.fromisoformat(
                            session_auth_at.replace("Z", "+00:00")
                        )
                    else:
                        authenticated_at = session_auth_at
                else:
                    authenticated_at = datetime.now(UTC)

                # Create session context from SSOSession dataclass
                return SSOSessionContext(
                    session_id=getattr(session, "session_id", ""),
                    user_id=getattr(session, "user_id", ""),
                    tenant_id=getattr(session, "tenant_id", ""),
                    email=getattr(session, "email", "") or getattr(session, "external_id", ""),
                    display_name=getattr(session, "display_name", "")
                    or getattr(session, "user_id", ""),
                    maci_roles=getattr(session, "maci_roles", []),
                    idp_groups=getattr(session, "idp_groups", []),
                    attributes=getattr(session, "attributes", {})
                    or getattr(session, "metadata", {}),
                    authenticated_at=authenticated_at,
                    expires_at=expires_at,
                    access_token=token,
                    refresh_token=getattr(session, "refresh_token", None),
                    idp_id=getattr(session, "idp_id", None),
                    idp_type=getattr(session, "idp_type", None),
                    constitutional_hash=self.config.constitutional_hash,
                )

            except _SSO_MIDDLEWARE_OPERATION_ERRORS as e:
                logger.warning("Failed to validate SSO session: %s", str(e))
                return None

        async def _set_tenant_context(self, session: SSOSessionContext) -> None:
            """Set tenant context from SSO session."""
            try:
                # Import multi-tenancy module
                from ..multi_tenancy import TenantContext, set_current_tenant

                # Create tenant context from SSO session
                tenant = TenantContext(  # type: ignore[call-arg]
                    tenant_id=session.tenant_id,
                    tenant_name=session.attributes.get("tenant_name", session.tenant_id),
                    config=session.attributes.get("tenant_config", {}),
                    metadata={
                        "sso_session_id": session.session_id,
                        "sso_user_id": session.user_id,
                        "sso_email": session.email,
                        "sso_authenticated_at": session.authenticated_at.isoformat(),
                    },
                )

                set_current_tenant(tenant)

            except ImportError:
                logger.debug("Multi-tenancy module not available")
            except _SSO_MIDDLEWARE_OPERATION_ERRORS as e:
                logger.warning("Failed to set tenant context: %s", str(e))

        async def _handle_session_refresh(
            self,
            session: SSOSessionContext,
            response: Response,
        ) -> Response:
            """Handle automatic session refresh if needed."""
            try:
                if session.time_until_expiry < self.config.refresh_threshold_seconds:
                    # Attempt to refresh session
                    if session.refresh_token:
                        new_token = self.sso_service.refresh_session(
                            session.session_id,
                        )

                        if new_token:
                            # Add refreshed token to response headers
                            response.headers["X-SSO-Token-Refreshed"] = "true"
                            response.headers["X-SSO-New-Token"] = new_token.session_id

                            logger.info(
                                "SSO session refreshed for user %s",
                                session.user_id,
                            )
            except _SSO_MIDDLEWARE_OPERATION_ERRORS as e:
                logger.warning("Failed to refresh SSO session: %s", str(e))

            return response

else:
    # Placeholder class when FastAPI is not available
    class SSOAuthenticationMiddleware:  # type: ignore[no-redef]
        """Placeholder SSO middleware when FastAPI is not available."""

        def __init__(self, *args: object, **kwargs: object):
            raise ImportError(
                "FastAPI is required for SSOAuthenticationMiddleware. "
                "Install with: pip install fastapi starlette"
            )


# FastAPI dependency for SSO session
if FASTAPI_AVAILABLE:
    security = HTTPBearer(auto_error=False)

    async def get_sso_session_dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
    ) -> SSOSessionContext | None:
        """
        FastAPI dependency to get current SSO session.

        Usage:
            @app.get("/api/user")
            async def get_user(session: SSOSessionContext = Depends(get_sso_session_dependency)):
                if session is None:
                    raise HTTPException(status_code=401)
                return {"user_id": session.user_id}
        """
        return get_current_sso_session()

    async def require_sso_session_dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
    ) -> SSOSessionContext:
        """
        FastAPI dependency that requires SSO authentication.

        Raises HTTPException 401 if not authenticated.

        Usage:
            @app.get("/api/protected")
            async def protected_endpoint(session: SSOSessionContext = Depends(require_sso_session_dependency)):
                return {"user_id": session.user_id}
        """
        session = get_current_sso_session()
        if session is None:
            raise HTTPException(
                status_code=401,
                detail="SSO authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if session.is_expired:
            raise HTTPException(
                status_code=401,
                detail="SSO session expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return session

    def require_roles(*roles: str, any_role: bool = True):
        """
        Create FastAPI dependency that requires specific MACI roles.

        Args:
            *roles: Required MACI roles.
            any_role: If True, any listed role is sufficient. If False, all required.

        Usage:
            @app.get("/api/admin")
            async def admin_endpoint(
                session: SSOSessionContext = Depends(require_roles("ADMIN", "SUPER_ADMIN"))
            ):
                return {"admin": session.user_id}
        """

        async def role_dependency(
            session: SSOSessionContext = Depends(require_sso_session_dependency),
        ) -> SSOSessionContext:
            role_list = list(roles)

            if any_role:
                if not session.has_any_role(role_list):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Requires one of roles: {role_list}",
                    )
            else:
                if not session.has_all_roles(role_list):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Requires all roles: {role_list}",
                    )

            return session

        return role_dependency


# Export additional utilities
__all__ = [
    "CONSTITUTIONAL_HASH",
    "SSOAuthenticationMiddleware",
    "SSOMiddlewareConfig",
    "SSOSessionContext",
    "clear_sso_session",
    "get_current_sso_session",
    "require_sso_authentication",
    "set_sso_session",
]

if FASTAPI_AVAILABLE:
    __all__.extend(
        [
            "get_sso_session_dependency",
            "require_roles",
            "require_sso_session_dependency",
        ]
    )
