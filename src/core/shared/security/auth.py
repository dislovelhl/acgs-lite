"""
ACGS-2 Authentication and Authorization Module
Constitutional Hash: cdd01ef066bc6cf2

Provides JWT-based authentication and role-based authorization for all services.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, params
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.shared.config import settings
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ConfigurationError
from src.core.shared.security.key_loader import load_key_material
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

_JWT_SECRET_ENV_KEYS = ("JWT_SECRET", "JWT_SECRET_KEY")
_JWT_PRIVATE_KEY_ENV_KEY = "JWT_PRIVATE_KEY"
_JWT_PUBLIC_KEY_ENV_KEY = "JWT_PUBLIC_KEY"
_JWT_ALGORITHM_ENV_KEY = "JWT_ALGORITHM"
_ALLOWED_JWT_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "EdDSA", "HS256"})
_JWT_ALGORITHM_CANONICAL_MAP = {
    algorithm.lower(): algorithm for algorithm in _ALLOWED_JWT_ALGORITHMS
}

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
    token_type: str = "bearer"


def _current_jwt_secret() -> str | None:
    """Return the configured JWT secret with runtime env overrides first."""
    for env_key in _JWT_SECRET_ENV_KEYS:
        if secret := os.environ.get(env_key):
            return secret

    if settings.security.jwt_secret:
        return settings.security.jwt_secret.get_secret_value()

    return None


def _current_jwt_private_key() -> str | None:
    configured = (os.getenv(_JWT_PRIVATE_KEY_ENV_KEY) or "").strip()
    if configured:
        loaded = load_key_material(configured, error_code="JWT_KEY_FILE_READ_FAILED")
        return loaded if loaded else None

    local_private_key = getattr(settings, "jwt_private_key", "")
    if isinstance(local_private_key, str) and local_private_key:
        return local_private_key

    return None


def _current_jwt_public_key() -> str | None:
    configured = (os.getenv(_JWT_PUBLIC_KEY_ENV_KEY) or "").strip()
    if configured:
        loaded = load_key_material(configured, error_code="JWT_KEY_FILE_READ_FAILED")
        return loaded if loaded else None

    local_public_key = getattr(settings, "jwt_public_key", "")
    if isinstance(local_public_key, str) and local_public_key:
        return local_public_key

    if settings.security.jwt_public_key != "SYSTEM_PUBLIC_KEY_PLACEHOLDER":
        return settings.security.jwt_public_key

    return None


def _configured_jwt_algorithm() -> str:
    env_algorithm = (os.getenv(_JWT_ALGORITHM_ENV_KEY) or "").strip()
    configured_algorithm = env_algorithm
    if not configured_algorithm:
        configured_algorithm = getattr(settings, "jwt_algorithm", "")
        if isinstance(configured_algorithm, str):
            configured_algorithm = configured_algorithm.strip()

    if not configured_algorithm:
        configured_algorithm = "RS256"

    normalized_algorithm = _JWT_ALGORITHM_CANONICAL_MAP.get(configured_algorithm.lower())
    if normalized_algorithm is None:
        raise ConfigurationError(
            message=f"Unsupported JWT algorithm: {configured_algorithm}",
            error_code="JWT_ALGORITHM_NOT_ALLOWED",
        )

    return normalized_algorithm


def _resolve_jwt_material(for_signing: bool) -> tuple[str, str]:
    requested_algorithm = _configured_jwt_algorithm()
    if requested_algorithm == "HS256":
        secret = _current_jwt_secret()
        if not secret:
            raise ConfigurationError(
                message="JWT_SECRET not configured",
                error_code="JWT_SECRET_MISSING",
            )

        return secret, "HS256"

    private_key = _current_jwt_private_key()
    public_key = _current_jwt_public_key()
    if private_key and public_key:
        return (
            (private_key, requested_algorithm) if for_signing else (public_key, requested_algorithm)
        )

    if requested_algorithm == "RS256":
        raise ConfigurationError(
            message=(
                "RS256 requested but RSA keys (JWT_PRIVATE_KEY, JWT_PUBLIC_KEY) are not "
                "configured. Set keys or change JWT_ALGORITHM to HS256."
            ),
            error_code="JWT_RSA_KEYS_MISSING",
        )

    raise ConfigurationError(
        message=(
            f"{requested_algorithm} requested but JWT_PRIVATE_KEY, JWT_PUBLIC_KEY are not "
            "configured. Set keys or change JWT_ALGORITHM to HS256."
        ),
        error_code="JWT_ASYMMETRIC_KEYS_MISSING",
    )


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

    key_material, algorithm = _resolve_jwt_material(for_signing=True)
    encoded_jwt = jwt.encode(to_encode, key_material, algorithm=algorithm)

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
        try:
            key_material, algorithm = _resolve_jwt_material(for_signing=False)
        except ConfigurationError as error:
            raise HTTPException(status_code=500, detail=error.message) from error

        payload = jwt.decode(
            token,
            key_material,
            algorithms=[algorithm],
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
    except InvalidTokenError as e:
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
        user: UserClaims = Depends(get_current_user), request: Request | None = None
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


__all__ = [
    "AuthenticationMiddleware",
    "TokenResponse",
    "UserClaims",
    "create_access_token",
    "get_current_user",
    "get_current_user_optional",
    "has_jwt_secret",
    "require_permission",
    "require_role",
    "require_tenant_access",
    "security",
    "verify_token",
]
