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
from src.core.shared.security.key_loader import load_key_material
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)

_ALLOWED_SERVICE_ALGORITHMS = frozenset(
    {"RS256", "RS384", "RS512", "ES256", "ES384", "EdDSA", "HS256"}
)
_SERVICE_ALGORITHM_LOOKUP = {
    algorithm.upper(): algorithm for algorithm in _ALLOWED_SERVICE_ALGORITHMS
}


def _get_service_secret() -> str:
    """Get service secret from environment with production safety check."""
    secret = os.environ.get("ACGS2_SERVICE_SECRET")
    if secret:
        return secret

    # Check BOTH ACGS2_ENV and ENVIRONMENT — if either signals production, a real secret is required.
    acgs_env = os.getenv("ACGS2_ENV", "development")
    app_env = os.getenv("ENVIRONMENT", "development")
    if acgs_env != "production" and app_env != "production":
        logger.warning(
            "Using development ACGS2_SERVICE_SECRET. Set ACGS2_SERVICE_SECRET for production."
        )
        # pragma: allowlist secret - Dev-only fallback, blocked in production by env check above
        return "dev-service-secret-32-bytes-minimum-length"

    raise ConfigurationError(
        message="ACGS2_SERVICE_SECRET not configured",
        error_code="SERVICE_SECRET_MISSING",
    )


def _get_service_private_key() -> str | None:
    configured = (os.getenv("JWT_PRIVATE_KEY") or "").strip()
    if not configured:
        return None
    loaded = load_key_material(
        configured, error_code="SERVICE_JWT_KEY_FILE_READ_FAILED"
    )
    return loaded if loaded else None


def _get_service_public_key() -> str | None:
    configured = (os.getenv("JWT_PUBLIC_KEY") or "").strip()
    if not configured:
        return None
    loaded = load_key_material(
        configured, error_code="SERVICE_JWT_KEY_FILE_READ_FAILED"
    )
    return loaded if loaded else None


SERVICE_SECRET = _get_service_secret()


def _configured_service_algorithm() -> str:
    configured = (os.getenv("SERVICE_JWT_ALGORITHM", "RS256").strip() or "RS256")
    canonical_algorithm = _SERVICE_ALGORITHM_LOOKUP.get(configured.upper())
    if canonical_algorithm is None:
        allowed_algorithms = ", ".join(sorted(_ALLOWED_SERVICE_ALGORITHMS))
        raise ConfigurationError(
            message=(
                "SERVICE_JWT_ALGORITHM must be one of "
                f"{allowed_algorithms}. Got {configured!r}."
            ),
            error_code="SERVICE_JWT_ALGORITHM_INVALID",
        )
    return canonical_algorithm


def _resolve_service_jwt_material(for_signing: bool) -> tuple[str, str]:
    requested_algorithm = _configured_service_algorithm()
    if requested_algorithm == "HS256":
        return SERVICE_SECRET, "HS256"

    private_key = _get_service_private_key()
    public_key = _get_service_public_key()
    if private_key and public_key:
        return (
            (private_key, requested_algorithm)
            if for_signing
            else (public_key, requested_algorithm)
        )

    if requested_algorithm == "RS256":
        raise ConfigurationError(
            message=(
                "RS256 requested but RSA keys are not configured. Set JWT_PRIVATE_KEY and "
                "JWT_PUBLIC_KEY, or set SERVICE_JWT_ALGORITHM=HS256."
            ),
            error_code="SERVICE_RSA_KEYS_MISSING",
        )

    raise ConfigurationError(
        message=(
            f"{requested_algorithm} requested but asymmetric keys are not configured. "
            "Set JWT_PRIVATE_KEY and JWT_PUBLIC_KEY, or set SERVICE_JWT_ALGORITHM=HS256."
        ),
        error_code="SERVICE_RSA_KEYS_MISSING",
    )


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
        key_material, algorithm = _resolve_service_jwt_material(for_signing=True)
        return jwt.encode(payload, key_material, algorithm=algorithm)

    @staticmethod
    def verify_service_token(token: str) -> str | None:
        """Verify a service JWT token and return service name."""
        try:
            key_material, algorithm = _resolve_service_jwt_material(for_signing=False)
            payload = jwt.decode(
                token, key_material, algorithms=[algorithm], issuer="acgs2-internal"
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
