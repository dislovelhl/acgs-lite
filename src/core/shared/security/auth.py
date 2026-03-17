"""
ACGS-2 Authentication and Authorization Module
Constitutional Hash: cdd01ef066bc6cf2

Provides JWT-based authentication and role-based authorization for all services.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, params
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from pydantic import BaseModel, Field

from src.core.shared.config import settings
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ConfigurationError
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

_JWT_SECRET_ENV_KEYS = ("JWT_SECRET", "JWT_SECRET_KEY")

# Security schemes
security = HTTPBearer(auto_error=False)


class UserClaims(BaseModel):
    """JWT user claims model."""

    sub: str  # User ID
    tenant_id: str
    roles: list[str]
    permissions: list[str]
    exp: int
    iat: int
    iss: str = "acgs2"
    aud: str = "acgs2-api"  # Audience claim for token scope validation
    jti: str = Field(default_factory=lambda: uuid.uuid4().hex)  # JWT ID for revocation tracking
    constitutional_hash: str = CONSTITUTIONAL_HASH  # Constitutional hash binding


class TokenResponse(BaseModel):
    """Token response model."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105


def _current_jwt_secret() -> str | None:
    """Return the configured JWT secret with runtime env overrides first."""
    for env_key in _JWT_SECRET_ENV_KEYS:
        if secret := os.environ.get(env_key):
            return secret

    if settings.security.jwt_secret:
        return settings.security.jwt_secret.get_secret_value()

    return None


def has_jwt_secret() -> bool:
    """Return True when any supported JWT secret source is configured."""
    return _current_jwt_secret() is not None


def create_access_token(
    user_id: str,
    tenant_id: str,
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        user_id: User identifier
        tenant_id: Tenant identifier
        roles: List of user roles
        permissions: List of user permissions
        expires_delta: Token expiration time

    Returns:
        JWT token string
    """
    if expires_delta is None:
        expires_delta = timedelta(hours=1)

    expire = datetime.now(UTC) + expires_delta

    to_encode = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "roles": roles or [],
        "permissions": permissions or [],
        "exp": expire,
        "iat": datetime.now(UTC),
        "iss": "acgs2",
        "aud": "acgs2-api",  # Audience claim for token scope validation
        "jti": str(uuid.uuid4()),  # JWT ID for revocation tracking
        "constitutional_hash": CONSTITUTIONAL_HASH,  # Bind to constitutional hash
    }

    secret = _current_jwt_secret()
    if not secret:
        raise ConfigurationError(
            message="JWT_SECRET not configured",
            error_code="JWT_SECRET_MISSING",
        )

    encoded_jwt = jwt.encode(to_encode, secret, algorithm="HS256")

    return encoded_jwt


def verify_token(token: str) -> UserClaims:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string

    Returns:
        UserClaims object

    Raises:
        HTTPException: If token is invalid
    """
    try:
        secret = _current_jwt_secret()
        if not secret:
            raise HTTPException(status_code=500, detail="JWT secret not configured")

        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="acgs2-api",
        )

        # Validate issuer
        if payload.get("iss") != "acgs2":
            raise HTTPException(status_code=401, detail="Invalid token issuer")

        # Validate constitutional hash binding (H-2 security fix)
        if payload.get("constitutional_hash") != CONSTITUTIONAL_HASH:
            logger.warning(
                f"Token constitutional hash mismatch: "
                f"expected {CONSTITUTIONAL_HASH}, got {payload.get('constitutional_hash')}"
            )
            raise HTTPException(
                status_code=401,
                detail="Token constitutional hash mismatch - token may be compromised",
            )

        # Validate JTI presence (H-2 security fix)
        if not payload.get("jti"):
            raise HTTPException(status_code=401, detail="Token missing JTI claim")

        return UserClaims(**payload)

    except HTTPException:
        # Re-raise HTTPExceptions as-is (don't wrap with generic message)
        raise
    except ExpiredSignatureError as e:
        logger.warning("JWT verification failed: %s", e)
        raise HTTPException(status_code=401, detail="Authentication token has expired") from e
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token") from e
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed") from e


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserClaims:
    """
    FastAPI dependency to get current authenticated user.

    Args:
        credentials: HTTP Bearer token credentials

    Returns:
        UserClaims for authenticated user

    Raises:
        HTTPException: If authentication fails
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_token(credentials.credentials)


async def get_current_user_optional(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(security)
) -> UserClaims | None:
    """
    Optional authentication - returns None if no token provided.

    Args:
        request: FastAPI request
        credentials: HTTP Bearer token credentials

    Returns:
        UserClaims if authenticated, None otherwise
    """
    token = None
    if credentials and not isinstance(credentials, params.Depends):
        token = credentials.credentials
    else:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        return None

    try:
        return verify_token(token)
    except HTTPException:
        return None


def require_role(required_role: str):
    """
    Create a dependency that requires a specific role.

    Args:
        required_role: Role that user must have

    Returns:
        Dependency function
    """

    async def role_checker(user: UserClaims = Depends(get_current_user)) -> UserClaims:
        """Verify the current user has the required role."""
        if required_role not in user.roles:
            raise HTTPException(status_code=403, detail=f"Role '{required_role}' required")
        return user

    return role_checker


def require_permission(required_permission: str):
    """
    Create a dependency that requires a specific permission.

    Args:
        required_permission: Permission that user must have

    Returns:
        Dependency function
    """

    async def permission_checker(user: UserClaims = Depends(get_current_user)) -> UserClaims:
        """Verify the current user has the required permission."""
        if required_permission not in user.permissions:
            raise HTTPException(
                status_code=403, detail=f"Permission '{required_permission}' required"
            )
        return user

    return permission_checker


def require_tenant_access(tenant_id: str | None = None):
    """
    Create a dependency that ensures user has access to specified tenant.

    Args:
        tenant_id: Specific tenant ID to check (optional)

    Returns:
        Dependency function
    """

    async def tenant_checker(
        user: UserClaims = Depends(get_current_user), request: Request = None
    ) -> UserClaims:
        """Verify the current user has access to the required tenant."""
        # If specific tenant_id provided, check it
        if tenant_id and user.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Access denied for this tenant")

        # If no specific tenant but request has tenant context, check it
        if request and hasattr(request.state, "tenant_id"):
            if user.tenant_id != request.state.tenant_id:
                raise HTTPException(status_code=403, detail="Tenant access denied")

        return user

    return tenant_checker


# ============================================================================
# FastAPI Middleware for Authentication
# ============================================================================

try:
    from fastapi.middleware.base import BaseHTTPMiddleware
except ImportError:
    # Fallback for older FastAPI versions
    from starlette.middleware.base import BaseHTTPMiddleware


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for automatic authentication.

    Adds user information to request state if token is present.
    """

    async def dispatch(self, request: Request, call_next):
        """Authenticate the request and attach user info to request state."""
        # Try to authenticate user
        user = await get_current_user_optional(request)

        if user:
            # Add user to request state
            request.state.user = user
            request.state.user_id = user.sub
            request.state.tenant_id = user.tenant_id
            request.state.user_roles = user.roles
            request.state.user_permissions = user.permissions

        # Continue with request
        response = await call_next(request)
        return response


# ============================================================================
# Utility Functions
# ============================================================================


def create_test_token(
    user_id: str = "test-user",
    tenant_id: str = "test-tenant",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> str:
    """
    Create a test JWT token for testing purposes.

    Args:
        user_id: Test user ID
        tenant_id: Test tenant ID
        roles: Test user roles
        permissions: Test user permissions

    Returns:
        JWT token string
    """
    return create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles or ["user"],
        permissions=permissions or ["read"],
        expires_delta=timedelta(hours=24),  # Longer for testing
    )


__all__ = [
    "AuthenticationMiddleware",
    "TokenResponse",
    "UserClaims",
    "create_access_token",
    "create_test_token",
    "get_current_user",
    "get_current_user_optional",
    "has_jwt_secret",
    "require_permission",
    "require_role",
    "require_tenant_access",
    "security",
    "verify_token",
]
