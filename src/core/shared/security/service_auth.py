"""
ACGS-2 Service-to-Service Authentication
Constitutional Hash: cdd01ef066bc6cf2

Provides JWT-based identity and authentication for inter-service communication.
"""

import os
import time

import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.shared.errors.exceptions import ConfigurationError
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

# Service secret for signing internal tokens
SERVICE_ALGORITHM = "HS256"


def _get_runtime_environment() -> str:
    return (
        (os.getenv("AGENT_RUNTIME_ENVIRONMENT") or os.getenv("ENVIRONMENT") or "development")
        .strip()
        .lower()
    )


def _get_service_secret() -> str:
    """Get service secret from environment with production safety check."""
    secret = os.environ.get("ACGS2_SERVICE_SECRET")
    if secret:
        return secret

    environment = _get_runtime_environment()
    if environment not in {"development", "dev", "test", "testing", "local"}:
        raise ConfigurationError(
            "ACGS2_SERVICE_SECRET environment variable is required outside local development/test "
            f"(current environment: {environment!r}). "
            'Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"',
            error_code="SERVICE_SECRET_MISSING",
        )

    # NOTE: Dev fallback secret — only reachable in development/test environments.
    # The RuntimeError above blocks production usage.
    logger.warning(
        "Using development ACGS2_SERVICE_SECRET. Set ACGS2_SERVICE_SECRET for production."
    )
    # pragma: allowlist secret - Dev-only fallback, blocked in production by env check above
    return "dev-service-secret-32-bytes-minimum-length"


SERVICE_SECRET = _get_service_secret()


class ServiceAuth:
    """Manager for service identity and verification."""

    @staticmethod
    def create_service_token(service_name: str, expires_in: int = 3600) -> str:
        """Create a JWT token for a service."""
        payload = {
            "sub": service_name,
            "iat": int(time.time()),
            "exp": int(time.time()) + expires_in,
            "iss": "acgs2-internal",
            "type": "service",
        }
        return jwt.encode(payload, SERVICE_SECRET, algorithm=SERVICE_ALGORITHM)

    @staticmethod
    def verify_service_token(token: str) -> str | None:
        """Verify a service JWT token and return service name."""
        try:
            payload = jwt.decode(
                token, SERVICE_SECRET, algorithms=[SERVICE_ALGORITHM], issuer="acgs2-internal"
            )
            if payload.get("type") != "service":
                return None
            return payload.get("sub")
        except jwt.PyJWTError as e:
            logger.warning(f"Service token verification failed: {e}")
            return None


security = HTTPBearer()


async def require_service_auth(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    """FastAPI dependency to require service authentication."""
    service_name = ServiceAuth.verify_service_token(credentials.credentials)
    if not service_name:
        raise HTTPException(status_code=401, detail="Invalid service token")
    return service_name


__all__ = ["ServiceAuth", "require_service_auth"]
