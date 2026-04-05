"""
ACGS-2 Secure CORS Configuration
Constitutional Hash: 608508a9bd224290

Centralized CORS configuration that enforces security best practices:
- Explicit origin allowlists (no wildcards in production)
- Environment-specific policies
- Credential handling safety
- Header and method restrictions

Security Requirements:
- NEVER use allow_origins=["*"] with allow_credentials=True (security vulnerability)
- Production must use explicit origin lists
- Development can use localhost origins only
- All configurations are logged for audit

Usage:
    from src.core.shared.security.cors_config import get_cors_config, CORSEnvironment

    config = get_cors_config(CORSEnvironment.PRODUCTION)
    app.add_middleware(CORSMiddleware, **config)
"""

import json
import os
from dataclasses import dataclass, field
from enum import StrEnum

# Constitutional hash for validation
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)


class CORSEnvironment(StrEnum):
    """Deployment environment for CORS configuration."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


@dataclass
class CORSConfig:
    """
    CORS configuration with security validations.

    Attributes:
        allow_origins: List of allowed origins (explicit, no wildcards in prod)
        allow_credentials: Whether to allow credentials (cookies, auth headers)
        allow_methods: Allowed HTTP methods
        allow_headers: Allowed request headers
        expose_headers: Headers exposed to browser
        max_age: Preflight cache duration in seconds
        environment: Deployment environment
    """

    allow_origins: list[str]
    allow_credentials: bool = True
    allow_methods: list[str] = field(
        default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    )
    allow_headers: list[str] = field(
        default_factory=lambda: [
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "X-Constitutional-Hash",
            "X-Tenant-ID",
        ]
    )
    expose_headers: list[str] = field(
        default_factory=lambda: [
            "X-Request-ID",
            "X-Constitutional-Hash",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ]
    )
    max_age: int = 600  # 10 minutes
    environment: CORSEnvironment = CORSEnvironment.DEVELOPMENT

    def __post_init__(self):
        """Validate configuration on creation."""
        self._validate()

    def _validate(self) -> None:
        """
        Validate CORS configuration for security issues.

        Raises:
            ValueError: If configuration is insecure
        """
        # Check for wildcard origin with credentials (critical vulnerability)
        if "*" in self.allow_origins and self.allow_credentials:
            if self.environment == CORSEnvironment.PRODUCTION:
                raise ValueError(
                    "SECURITY ERROR: allow_origins=['*'] with allow_credentials=True "
                    "is a critical security vulnerability in production. "
                    "This allows any origin to make authenticated requests."
                )
            else:
                logger.warning(
                    "SECURITY WARNING: Using wildcard origin with credentials in "
                    f"{self.environment.value}. This would be blocked in production."
                )

        # Check for wildcard in production
        if "*" in self.allow_origins and self.environment == CORSEnvironment.PRODUCTION:
            raise ValueError(
                "SECURITY ERROR: Wildcard origins not allowed in production. "
                "Specify explicit allowed origins."
            )

        # Validate origin formats
        for origin in self.allow_origins:
            if origin != "*" and not self._is_valid_origin(origin):
                raise ValueError(f"Invalid origin format: {origin}")

    @staticmethod
    def _is_valid_origin(origin: str) -> bool:
        """Check if origin is a valid URL format."""
        from urllib.parse import urlparse

        try:
            result = urlparse(origin)
            return all(
                [
                    result.scheme in ("http", "https"),
                    result.netloc,
                    not result.fragment,  # Origins shouldn't have fragments
                ]
            )
        except (ValueError, AttributeError):
            return False

    def to_middleware_kwargs(self) -> dict:
        """Convert to FastAPI CORSMiddleware kwargs."""
        return {
            "allow_origins": self.allow_origins,
            "allow_credentials": self.allow_credentials,
            "allow_methods": self.allow_methods,
            "allow_headers": self.allow_headers,
            "expose_headers": self.expose_headers,
            "max_age": self.max_age,
        }


# Default origin configurations by environment
DEFAULT_ORIGINS = {
    CORSEnvironment.DEVELOPMENT: [
        "http://localhost:3000",  # React dev server
        "http://localhost:8080",  # API Gateway
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:5173",
    ],
    CORSEnvironment.TEST: [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://testserver",  # pytest httpx testclient
    ],
    CORSEnvironment.STAGING: [
        "https://staging.acgs2.example.com",
        "https://staging-api.acgs2.example.com",
        "https://staging-admin.acgs2.example.com",
    ],
    CORSEnvironment.PRODUCTION: [
        "https://acgs2.example.com",
        "https://api.acgs2.example.com",
        "https://admin.acgs2.example.com",
        "https://folo.example.com",
    ],
}


def detect_environment() -> CORSEnvironment:
    """
    Detect current environment from environment variables.

    Checks (in order):
    1. CORS_ENVIRONMENT
    2. AGENT_RUNTIME_ENVIRONMENT
    3. ENVIRONMENT
    4. ENV
    4. Defaults to DEVELOPMENT
    """
    env_value = (
        (
            os.environ.get("CORS_ENVIRONMENT")
            or os.environ.get("AGENT_RUNTIME_ENVIRONMENT")
            or os.environ.get("ENVIRONMENT")
            or os.environ.get("ENV")
            or "development"
        )
        .strip()
        .lower()
    )

    mapping = {
        "development": CORSEnvironment.DEVELOPMENT,
        "dev": CORSEnvironment.DEVELOPMENT,
        "staging": CORSEnvironment.STAGING,
        "stage": CORSEnvironment.STAGING,
        "production": CORSEnvironment.PRODUCTION,
        "prod": CORSEnvironment.PRODUCTION,
        "test": CORSEnvironment.TEST,
        "testing": CORSEnvironment.TEST,
    }

    return mapping.get(env_value, CORSEnvironment.DEVELOPMENT)


def get_origins_from_env() -> list[str] | None:
    """
    Get allowed origins from environment variable.

    Environment variables checked (in order):
    - CORS_ALLOWED_ORIGINS (comma-separated list)
    - CORS_ORIGINS (comma-separated list, for backward compatibility)

    Examples:
    CORS_ALLOWED_ORIGINS=https://app1.example.com,https://app2.example.com
    CORS_ORIGINS=http://localhost:3000,http://localhost:8080
    """
    # Try CORS_ALLOWED_ORIGINS first
    origins_str = os.environ.get("CORS_ALLOWED_ORIGINS") or os.environ.get("CORS_ORIGINS")
    if origins_str:
        origins_str = origins_str.strip()
        if origins_str.startswith("["):
            try:
                parsed = json.loads(origins_str)
                if isinstance(parsed, list):
                    origins = [str(o).strip() for o in parsed if str(o).strip()]
                    logger.info(f"Loaded {len(origins)} CORS origins from JSON env")
                    return origins
                logger.warning("CORS origins JSON must be a list")
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse CORS origins JSON", error=str(e))  # type: ignore[call-arg]
        origins = [o.strip() for o in origins_str.split(",") if o.strip()]
        logger.info(f"Loaded {len(origins)} CORS origins from environment")
        return origins
    return None


def get_cors_config(
    environment: CORSEnvironment | None = None,
    additional_origins: list[str] | None = None,
    allow_credentials: bool = True,
) -> dict:
    """
    Get secure CORS configuration for FastAPI middleware.

    Args:
        environment: Target environment (auto-detected if None)
        additional_origins: Additional origins to allow beyond defaults
        allow_credentials: Whether to allow credentials

    Returns:
        Dictionary suitable for CORSMiddleware(**config)

    Example:
        from fastapi.middleware.cors import CORSMiddleware
        from src.core.shared.security.cors_config import get_cors_config

        app.add_middleware(CORSMiddleware, **get_cors_config())
    """
    if environment is None:
        environment = detect_environment()

    # Start with environment-specific defaults
    origins = list(DEFAULT_ORIGINS.get(environment, []))

    # Add origins from environment variable (takes precedence)
    env_origins = get_origins_from_env()
    if env_origins:
        origins = env_origins

    # Add any additional origins
    if additional_origins:
        origins.extend(additional_origins)

    # Remove duplicates while preserving order
    seen: set[str] = set()
    unique_origins = []
    for origin in origins:
        if origin not in seen:
            seen.add(origin)
            unique_origins.append(origin)

    # Create and validate configuration
    config = CORSConfig(
        allow_origins=unique_origins,
        allow_credentials=allow_credentials,
        environment=environment,
    )

    logger.info(
        f"CORS configured for {environment.value}: "
        f"{len(unique_origins)} origins, "
        f"credentials={'enabled' if allow_credentials else 'disabled'}, "
        f"constitutional_hash={CONSTITUTIONAL_HASH}"
    )

    return config.to_middleware_kwargs()


def get_strict_cors_config() -> dict:
    """
    Get the most restrictive CORS configuration.

    Use this for highly sensitive endpoints that should only be accessed
    from the main application domain.
    """
    environment = detect_environment()

    if environment == CORSEnvironment.PRODUCTION:
        origins = ["https://acgs2.example.com"]
    elif environment == CORSEnvironment.STAGING:
        origins = ["https://staging.acgs2.example.com"]
    else:
        origins = ["http://localhost:3000"]

    return CORSConfig(
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],  # Restricted methods
        environment=environment,
    ).to_middleware_kwargs()


def validate_origin(origin: str, allowed_origins: list[str]) -> bool:
    """
    Validate if an origin is allowed.

    Args:
        origin: The origin to check
        allowed_origins: List of allowed origins

    Returns:
        True if origin is allowed
    """
    if "*" in allowed_origins:
        return True
    return origin in allowed_origins


__all__ = [
    "CONSTITUTIONAL_HASH",
    "DEFAULT_ORIGINS",
    "CORSConfig",
    "CORSEnvironment",
    "detect_environment",
    "get_cors_config",
    "get_origins_from_env",
    "get_strict_cors_config",
    "validate_origin",
]
