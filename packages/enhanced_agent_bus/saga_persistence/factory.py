"""
Saga Repository Factory
Constitutional Hash: 608508a9bd224290

Factory for creating saga state repositories based on configuration.
Supports Redis and PostgreSQL backends with automatic fallback.

Usage:
    from saga_persistence.factory import create_saga_repository, SagaBackend

    # Create Redis repository
    repo = await create_saga_repository(SagaBackend.REDIS, redis_url="redis://localhost")

    # Create PostgreSQL repository
    repo = await create_saga_repository(SagaBackend.POSTGRES, dsn="postgresql://...")

    # Auto-detect based on environment
    repo = await create_saga_repository()  # Uses SAGA_BACKEND env var
"""

import os
from enum import Enum

try:
    from src.core.shared.constants import (
        CONSTITUTIONAL_HASH,
        DEFAULT_REDIS_URL,
    )
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
    DEFAULT_REDIS_URL = "redis://localhost:6379"

from enhanced_agent_bus.observability.structured_logging import get_logger

from .repository import RepositoryError, SagaStateRepository

logger = get_logger(__name__)
SAGA_BACKEND_OPERATION_ERRORS = (
    ConnectionError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


class SagaBackend(str, Enum):
    """Supported saga persistence backends."""

    REDIS = "redis"
    POSTGRES = "postgres"


class BackendUnavailableError(RepositoryError):
    """Raised when a requested backend is not available."""

    def __init__(self, backend: SagaBackend, reason: str):
        self.backend = backend
        self.reason = reason
        super().__init__(
            f"Backend '{backend.value}' is unavailable: {reason}",
            saga_id=None,
        )


async def create_saga_repository(
    backend: SagaBackend | None = None,
    *,
    redis_url: str | None = None,
    dsn: str | None = None,
    fallback: bool = True,
) -> SagaStateRepository:
    """
    Create a saga state repository based on configuration.

    Constitutional Hash: 608508a9bd224290

    Args:
        backend: The backend to use. If None, uses SAGA_BACKEND env var
                 or defaults to Redis.
        redis_url: Redis connection URL (for Redis backend).
                   Defaults to REDIS_URL env var or redis://localhost:6379.
        dsn: PostgreSQL connection string (for Postgres backend).
             Defaults to DATABASE_URL env var.
        fallback: If True and primary backend fails, try alternate backend.

    Returns:
        Configured SagaStateRepository instance.

    Raises:
        BackendUnavailableError: If requested backend is not available.
        RepositoryError: If repository creation fails.

    Example:
        # Use Redis explicitly
        repo = await create_saga_repository(SagaBackend.REDIS)

        # Use PostgreSQL with custom DSN
        repo = await create_saga_repository(
            SagaBackend.POSTGRES,
            dsn="postgresql://user:pass@host/db"
        )

        # Auto-detect with fallback
        repo = await create_saga_repository(fallback=True)
    """
    if backend is None:
        backend = _detect_backend()

    logger.info(
        "Creating saga repository",
        extra={
            "backend": backend.value,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
    )

    try:
        if backend == SagaBackend.REDIS:
            return await _create_redis_repository(redis_url)
        elif backend == SagaBackend.POSTGRES:
            return await _create_postgres_repository(dsn)
        else:
            raise BackendUnavailableError(backend, f"Unknown backend: {backend}")
    except BackendUnavailableError:
        if fallback:
            return await _try_fallback(backend, redis_url, dsn)
        raise


def _detect_backend() -> SagaBackend:
    """
    Detect the backend to use based on environment variables.

    Priority:
    1. SAGA_BACKEND env var (explicit choice)
    2. DATABASE_URL set -> Postgres
    3. Default -> Redis
    """
    env_backend = os.environ.get("SAGA_BACKEND", "").lower()

    if env_backend == "postgres":
        return SagaBackend.POSTGRES
    elif env_backend == "redis":
        return SagaBackend.REDIS
    elif os.environ.get("DATABASE_URL"):
        return SagaBackend.POSTGRES
    else:
        return SagaBackend.REDIS


async def _create_redis_repository(
    redis_url: str | None = None,
) -> SagaStateRepository:
    """
    Create a Redis-backed saga repository.

    Args:
        redis_url: Redis connection URL.

    Returns:
        RedisSagaStateRepository instance.

    Raises:
        BackendUnavailableError: If Redis is not available.
    """
    # Check if Redis module is available
    from . import REDIS_AVAILABLE, RedisSagaStateRepository

    if not REDIS_AVAILABLE or RedisSagaStateRepository is None:
        raise BackendUnavailableError(
            SagaBackend.REDIS,
            "redis package not installed. Install with: pip install redis",
        )

    # Resolve URL from environment if not provided
    url = redis_url or os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)

    try:
        import redis.asyncio as redis_client

        client = redis_client.from_url(url)

        # Test connection
        await client.ping()

        logger.info(f"Connected to Redis at {_mask_url(url)}")

        return RedisSagaStateRepository(redis_client=client)

    except SAGA_BACKEND_OPERATION_ERRORS as e:
        raise BackendUnavailableError(
            SagaBackend.REDIS,
            f"Failed to connect to Redis at {_mask_url(url)}: {e}",
        ) from e


async def _create_postgres_repository(
    dsn: str | None = None,
) -> SagaStateRepository:
    """
    Create a PostgreSQL-backed saga repository.

    Args:
        dsn: PostgreSQL connection string.

    Returns:
        PostgresSagaStateRepository instance.

    Raises:
        BackendUnavailableError: If PostgreSQL is not available.
    """
    # Check if PostgreSQL module is available
    from . import POSTGRES_AVAILABLE, PostgresSagaStateRepository

    if not POSTGRES_AVAILABLE or PostgresSagaStateRepository is None:
        raise BackendUnavailableError(
            SagaBackend.POSTGRES,
            "asyncpg package not installed. Install with: pip install asyncpg",
        )

    # Resolve DSN from environment if not provided
    connection_dsn = dsn or os.environ.get("DATABASE_URL")

    if not connection_dsn:
        raise BackendUnavailableError(
            SagaBackend.POSTGRES,
            "No DSN provided. Set DATABASE_URL env var or pass dsn parameter.",
        )

    try:
        repo = PostgresSagaStateRepository(dsn=connection_dsn)
        await repo.initialize()

        logger.info(f"Connected to PostgreSQL at {_mask_url(connection_dsn)}")

        return repo

    except SAGA_BACKEND_OPERATION_ERRORS as e:
        raise BackendUnavailableError(
            SagaBackend.POSTGRES,
            f"Failed to connect to PostgreSQL: {e}",
        ) from e


async def _try_fallback(
    failed_backend: SagaBackend,
    redis_url: str | None,
    dsn: str | None,
) -> SagaStateRepository:
    """
    Try the fallback backend when primary fails.

    Args:
        failed_backend: The backend that failed.
        redis_url: Redis URL if available.
        dsn: PostgreSQL DSN if available.

    Returns:
        SagaStateRepository from fallback backend.

    Raises:
        BackendUnavailableError: If fallback also fails.
    """
    fallback_backend = (
        SagaBackend.REDIS if failed_backend == SagaBackend.POSTGRES else SagaBackend.POSTGRES
    )

    logger.warning(
        f"Primary backend {failed_backend.value} unavailable, "
        f"falling back to {fallback_backend.value}"
    )

    try:
        if fallback_backend == SagaBackend.REDIS:
            return await _create_redis_repository(redis_url)
        else:
            return await _create_postgres_repository(dsn)
    except BackendUnavailableError as e:
        raise BackendUnavailableError(
            failed_backend,
            f"Both backends unavailable. Primary: {failed_backend.value}, "
            f"Fallback: {fallback_backend.value} - {e.reason}",
        ) from e


def _mask_url(url: str) -> str:
    """
    Mask sensitive parts of a connection URL for logging.

    Args:
        url: Connection URL that may contain credentials.

    Returns:
        URL with password masked.
    """
    if "@" in url:
        # Mask password in URL like postgres://user:pass@host
        parts = url.split("@")
        credentials = parts[0]
        host = "@".join(parts[1:])

        if ":" in credentials.split("//")[-1]:
            protocol = credentials.split("://")[0] if "://" in credentials else ""
            user = credentials.split("://")[-1].split(":")[0]
            masked = f"{protocol}://{user}:***@{host}"
            return masked

    return url


__all__ = [
    "BackendUnavailableError",
    "SagaBackend",
    "create_saga_repository",
]
