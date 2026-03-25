from src.core.shared.constants import CONSTITUTIONAL_HASH

"""
ACGS-2 Application Settings
Constitutional Hash: 608508a9bd224290

Centralized settings for all ACGS-2 services.
"""

import os
import sys
from dataclasses import dataclass, field

from src.core.shared.security.key_loader import load_key_material


def _get_runtime_environment() -> str:
    return (
        (os.getenv("AGENT_RUNTIME_ENVIRONMENT") or os.getenv("ENVIRONMENT") or "development")
        .strip()
        .lower()
    )


def _get_secret_key() -> str:
    """
    Get secret key from environment.

    In production, SECRET_KEY must be explicitly set.
    In development/testing, a default is allowed with a warning.
    """
    secret = os.getenv("SECRET_KEY")
    if secret:
        return secret

    environment = _get_runtime_environment()
    if environment not in {"development", "dev", "test", "testing", "local", "ci"}:
        raise ValueError(
            "SECRET_KEY environment variable is required outside local development/test "
            f"(current environment: {environment!r}). "
            'Generate a secure key with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )

    # Development/testing fallback with deterministic key for test reproducibility
    import warnings

    warnings.warn(
        "Using development SECRET_KEY. Set SECRET_KEY environment variable for production.",
        UserWarning,
        stacklevel=2,
    )
    return "dev-only-secret-key-not-for-production"


def _get_jwt_private_key() -> str:
    configured_value = (os.getenv("JWT_PRIVATE_KEY") or "").strip()
    if not configured_value:
        return ""
    return load_key_material(configured_value)


def _get_jwt_public_key() -> str:
    configured_value = (os.getenv("JWT_PUBLIC_KEY") or "").strip()
    if not configured_value:
        return ""
    return load_key_material(configured_value)


@dataclass
class RedisSettings:
    """Redis connection settings."""

    host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
    password: str | None = field(default_factory=lambda: os.getenv("REDIS_PASSWORD"))
    max_connections: int = field(
        default_factory=lambda: int(os.getenv("REDIS_MAX_CONNECTIONS", "2000"))
    )
    socket_timeout: float = field(
        default_factory=lambda: float(os.getenv("REDIS_SOCKET_TIMEOUT", "1.0"))
    )
    retry_on_timeout: bool = field(
        default_factory=lambda: os.getenv("REDIS_RETRY_ON_TIMEOUT", "true").lower() == "true"
    )
    ssl: bool = field(default_factory=lambda: os.getenv("REDIS_SSL", "false").lower() == "true")
    ssl_cert_reqs: str | None = field(default_factory=lambda: os.getenv("REDIS_SSL_CERT_REQS"))
    ssl_ca_certs: str | None = field(default_factory=lambda: os.getenv("REDIS_SSL_CA_CERTS"))
    socket_keepalive: bool = field(
        default_factory=lambda: os.getenv("REDIS_SOCKET_KEEPALIVE", "true").lower() == "true"
    )
    health_check_interval: int = field(
        default_factory=lambda: int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))
    )


@dataclass
class DatabaseSettings:
    """Database connection settings."""

    host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))
    name: str = field(default_factory=lambda: os.getenv("DB_NAME", "acgs2"))
    user: str = field(default_factory=lambda: os.getenv("DB_USER", "postgres"))
    password: str | None = field(default_factory=lambda: os.getenv("DB_PASSWORD"))


@dataclass
class Settings:
    """Main application settings."""

    # Application
    app_name: str = "ACGS-2"
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    environment: str = field(default_factory=_get_runtime_environment)

    # Constitutional Hash
    constitutional_hash: str = CONSTITUTIONAL_HASH

    # Subsystem settings
    redis: RedisSettings = field(default_factory=RedisSettings)
    database: DatabaseSettings = field(default_factory=DatabaseSettings)

    # Security
    secret_key: str = field(default_factory=_get_secret_key)
    jwt_algorithm: str = "RS256"
    jwt_private_key: str = field(default_factory=_get_jwt_private_key)
    jwt_public_key: str = field(default_factory=_get_jwt_public_key)
    access_token_expire_minutes: int = 30


# Singleton settings instance
settings = Settings()


def __getattr__(name: str):
    """
    Delegate attribute access to the singleton settings instance.

    This keeps compatibility when callers import the `config.settings` module
    (instead of the `settings` object) and then access attributes like
    `settings.redis`.
    """
    from src.core.shared.config.unified import settings as unified_settings

    if hasattr(unified_settings, name):
        return getattr(unified_settings, name)
    if hasattr(settings, name):
        return getattr(settings, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Keep `from src.core.shared.config import settings` bound to unified settings.
_config_pkg = sys.modules.get("src.core.shared.config")
if _config_pkg is not None:
    from src.core.shared.config.unified import settings as _unified_settings

    _config_pkg.settings = _unified_settings
