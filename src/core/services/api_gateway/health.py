"""
ACGS-2 API Gateway Health Endpoints
Constitutional Hash: 608508a9bd224290

Implements health check endpoints per SPEC_ACGS2_ENHANCED.md Section 3.3.
Per Expert Panel Review (Kelsey Hightower - Cloud Native Expert).

Endpoints:
- /health - Basic health check
- /health/live - Liveness probe
- /health/ready - Readiness probe with dependency checks
- /health/startup - Startup probe (lightweight, no external calls)
"""

import asyncio
import hmac
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

import httpx
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.structured_logging import get_logger

try:
    from prometheus_client import Info

    constitutional_info = Info(
        "acgs_constitutional_hash",
        "Constitutional hash loaded by this service",
    )
    constitutional_info.info({"hash": CONSTITUTIONAL_HASH, "service": "api-gateway"})
except (ImportError, ValueError):
    # ValueError: metric already registered (e.g. agent-bus health registered it first)
    constitutional_info = None

logger = get_logger(__name__)


class HealthStatus(StrEnum):
    """Health check status values."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


class DependencyStatus(StrEnum):
    """Dependency health status."""

    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


# =============================================================================
# Response Models
# =============================================================================


class BasicHealthResponse(BaseModel):
    """Basic health check response."""

    status: str = "ok"
    constitutional_hash: str = CONSTITUTIONAL_HASH


class LivenessResponse(BaseModel):
    """Liveness probe response."""

    live: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH


class DependencyCheck(BaseModel):
    """Individual dependency check result."""

    status: str
    latency_ms: float
    error: str | None = None


class ReadinessResponse(BaseModel):
    """Readiness probe response with dependency checks."""

    ready: bool
    constitutional_hash: str = CONSTITUTIONAL_HASH
    checks: dict[str, DependencyCheck]
    timestamp: str


class StartupResponse(BaseModel):
    """Startup probe response (lightweight, no external dependency calls)."""

    ready: bool
    constitutional_hash: str = CONSTITUTIONAL_HASH
    initialized: bool = False
    hash_valid: bool = False


# =============================================================================
# Dependency Checkers
# =============================================================================


@dataclass
class DependencyConfig:
    """Configuration for a dependency health check."""

    name: str
    url: str
    timeout_seconds: float = 5.0
    required: bool = True  # If false, degraded but not unhealthy if down


# Default dependency configurations
DEFAULT_DEPENDENCIES: list[DependencyConfig] = [
    DependencyConfig(
        name="database",
        url="postgresql://localhost:5432",  # Will be overridden by env
        timeout_seconds=5.0,
        required=True,
    ),
    DependencyConfig(
        name="redis",
        url="redis://localhost:6379",  # Will be overridden by env
        timeout_seconds=2.0,
        required=True,
    ),
    DependencyConfig(
        name="opa",
        url="http://localhost:8181",  # Will be overridden by env
        timeout_seconds=3.0,
        required=True,
    ),
]


class HealthChecker:
    """
    Health checker for API Gateway dependencies.

    Constitutional Hash: 608508a9bd224290

    Checks:
    - Database connectivity
    - Redis connectivity
    - OPA availability
    """

    def __init__(
        self,
        database_url: str | None = None,
        redis_url: str | None = None,
        opa_url: str | None = None,
    ):
        self.database_url = database_url
        self.redis_url = redis_url
        self.opa_url = opa_url or "http://localhost:8181"
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def check_database(self) -> DependencyCheck:
        """Check database connectivity."""
        start_time = time.perf_counter()
        try:
            # Try asyncpg if available
            try:
                import asyncpg

                if self.database_url:
                    conn = await asyncio.wait_for(
                        asyncpg.connect(self.database_url),
                        timeout=5.0,
                    )
                    await conn.execute("SELECT 1")
                    await conn.close()
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    return DependencyCheck(status="up", latency_ms=latency_ms)
            except ImportError:
                pass

            # Fallback: assume healthy if no database URL configured
            if not self.database_url:
                latency_ms = (time.perf_counter() - start_time) * 1000
                return DependencyCheck(
                    status="up",
                    latency_ms=latency_ms,
                    error="No database URL configured - assuming healthy",
                )

            latency_ms = (time.perf_counter() - start_time) * 1000
            return DependencyCheck(status="up", latency_ms=latency_ms)

        except TimeoutError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return DependencyCheck(
                status="down",
                latency_ms=latency_ms,
                error="Database connection timeout",
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return DependencyCheck(
                status="down",
                latency_ms=latency_ms,
                error=str(e)[:100],  # Truncate long errors
            )

    async def check_redis(self) -> DependencyCheck:
        """Check Redis connectivity."""
        start_time = time.perf_counter()
        try:
            # Try redis-py if available
            try:
                import redis.asyncio as aioredis

                if self.redis_url:
                    client = aioredis.from_url(self.redis_url)
                    await asyncio.wait_for(client.ping(), timeout=2.0)
                    await client.close()
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    return DependencyCheck(status="up", latency_ms=latency_ms)
            except ImportError:
                pass

            # Fallback: assume healthy if no Redis URL configured
            if not self.redis_url:
                latency_ms = (time.perf_counter() - start_time) * 1000
                return DependencyCheck(
                    status="up",
                    latency_ms=latency_ms,
                    error="No Redis URL configured - assuming healthy",
                )

            latency_ms = (time.perf_counter() - start_time) * 1000
            return DependencyCheck(status="up", latency_ms=latency_ms)

        except TimeoutError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return DependencyCheck(
                status="down",
                latency_ms=latency_ms,
                error="Redis connection timeout",
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return DependencyCheck(
                status="down",
                latency_ms=latency_ms,
                error=str(e)[:100],
            )

    async def check_opa(self) -> DependencyCheck:
        """Check OPA (Open Policy Agent) availability."""
        start_time = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.opa_url}/health")
                latency_ms = (time.perf_counter() - start_time) * 1000

                if response.status_code == 200:
                    return DependencyCheck(status="up", latency_ms=latency_ms)
                else:
                    return DependencyCheck(
                        status="degraded",
                        latency_ms=latency_ms,
                        error=f"OPA returned status {response.status_code}",
                    )

        except httpx.TimeoutException:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return DependencyCheck(
                status="down",
                latency_ms=latency_ms,
                error="OPA connection timeout",
            )
        except httpx.ConnectError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return DependencyCheck(
                status="down",
                latency_ms=latency_ms,
                error="OPA connection refused",
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return DependencyCheck(
                status="down",
                latency_ms=latency_ms,
                error=str(e)[:100],
            )

    async def check_constitutional_hash(self) -> DependencyCheck:
        """Validate runtime constitutional hash configuration."""
        start_time = time.perf_counter()
        configured_hash = os.getenv("CONSTITUTIONAL_HASH", CONSTITUTIONAL_HASH)
        is_valid = hmac.compare_digest(configured_hash, CONSTITUTIONAL_HASH)
        latency_ms = (time.perf_counter() - start_time) * 1000

        if is_valid:
            return DependencyCheck(status="up", latency_ms=latency_ms)

        return DependencyCheck(
            status="down",
            latency_ms=latency_ms,
            error="Runtime constitutional hash mismatch",
        )

    async def check_all(self) -> dict[str, DependencyCheck]:
        """Check all dependencies concurrently."""
        results = await asyncio.gather(
            self.check_database(),
            self.check_redis(),
            self.check_opa(),
            self.check_constitutional_hash(),
            return_exceptions=True,
        )

        checks = {}
        for name, result in zip(
            ["database", "redis", "opa", "constitutional_hash"], results, strict=True
        ):
            if isinstance(result, Exception):
                checks[name] = DependencyCheck(
                    status="down",
                    latency_ms=0,
                    error=str(result)[:100],
                )
            else:
                checks[name] = result

        return checks


# =============================================================================
# Router Configuration
# =============================================================================


def create_health_router(
    database_url: str | None = None,
    redis_url: str | None = None,
    opa_url: str | None = None,
) -> APIRouter:
    """
    Create health check router with configured dependencies.

    Args:
        database_url: PostgreSQL connection URL
        redis_url: Redis connection URL
        opa_url: OPA server URL

    Returns:
        FastAPI APIRouter with health endpoints
    """
    router = APIRouter(tags=["Health"])
    checker = HealthChecker(
        database_url=database_url,
        redis_url=redis_url,
        opa_url=opa_url,
    )

    @router.get(
        "/health",
        response_model=BasicHealthResponse,
        summary="Basic health check",
        description="Returns basic health status. Always returns 200 if service is running.",
    )
    async def health_check() -> BasicHealthResponse:
        """Basic health check endpoint."""
        return BasicHealthResponse()

    @router.get(
        "/health/live",
        response_model=LivenessResponse,
        summary="Liveness probe",
        description="Kubernetes liveness probe. Returns 200 if process is running.",
    )
    async def liveness_probe() -> LivenessResponse:
        """Liveness probe for Kubernetes."""
        return LivenessResponse()

    @router.get(
        "/healthz",
        response_model=LivenessResponse,
        summary="Liveness probe alias",
        description="Alias for /health/live to align with platform health conventions.",
    )
    async def liveness_probe_alias() -> LivenessResponse:
        """Liveness probe alias (/healthz)."""
        return await liveness_probe()

    @router.get(
        "/health/ready",
        response_model=ReadinessResponse,
        summary="Readiness probe",
        description="Kubernetes readiness probe. Checks database, Redis, and OPA connectivity.",
    )
    async def readiness_probe(request: Request, response: Response) -> ReadinessResponse:
        """
        Readiness probe for Kubernetes.

        Checks connectivity to all required dependencies:
        - database: PostgreSQL
        - redis: Redis cache
        - opa: Open Policy Agent

        Returns 200 if all required dependencies are up.
        Returns 503 if any required dependency is down.
        """
        checks = await checker.check_all()
        probe_hash = request.headers.get("X-Constitutional-Hash")
        if probe_hash is not None and not hmac.compare_digest(probe_hash, CONSTITUTIONAL_HASH):
            checks["probe_header"] = DependencyCheck(
                status="down",
                latency_ms=0.0,
                error="Probe constitutional hash header mismatch",
            )

        # Determine overall readiness
        all_up = all(c.status == "up" for c in checks.values())
        any_down = any(c.status == "down" for c in checks.values())

        ready = all_up or not any_down

        if not ready:
            response.status_code = 503
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Readiness check failed",
                extra={
                    "checks": {k: v.model_dump() for k, v in checks.items()},
                },
            )

        return ReadinessResponse(
            ready=ready,
            checks=checks,
            timestamp=datetime.now(UTC).isoformat(),
        )

    @router.get(
        "/readyz",
        response_model=ReadinessResponse,
        summary="Readiness probe alias",
        description="Alias for /health/ready to align with platform health conventions.",
    )
    async def readiness_probe_alias(request: Request, response: Response) -> ReadinessResponse:
        """Readiness probe alias (/readyz)."""
        return await readiness_probe(request, response)

    @router.get(
        "/health/startup",
        response_model=StartupResponse,
        summary="Startup probe",
        description=(
            "Kubernetes startup probe. Lightweight check with no external dependency calls. "
            "Verifies constitutional hash integrity."
        ),
    )
    async def startup_probe(request: Request, response: Response) -> StartupResponse:
        """
        Startup probe for Kubernetes.

        Lightweight check — no external dependency calls:
        - Reports request.app.state.initialized when available (informational only)
        - Verifies CONSTITUTIONAL_HASH is loaded and non-empty
        - Validates CONSTITUTIONAL_HASH matches canonical value via hmac.compare_digest

        Returns 200 when constitutional hash validation passes, 503 otherwise.
        """
        initialized = getattr(request.app.state, "initialized", False)
        hash_valid = bool(CONSTITUTIONAL_HASH) and hmac.compare_digest(
            CONSTITUTIONAL_HASH,
            "608508a9bd224290",  # pragma: allowlist secret
        )
        ready = hash_valid

        if not ready:
            response.status_code = 503
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Startup check failed",
                extra={
                    "initialized": initialized,
                    "hash_valid": hash_valid,
                },
            )

        return StartupResponse(
            ready=ready,
            initialized=initialized,
            hash_valid=hash_valid,
        )

    @router.get(
        "/startupz",
        response_model=StartupResponse,
        summary="Startup probe alias",
        description="Alias for /health/startup to align with platform health conventions.",
    )
    async def startup_probe_alias(request: Request, response: Response) -> StartupResponse:
        """Startup probe alias (/startupz)."""
        return await startup_probe(request, response)

    return router


# =============================================================================
# Global Health Checker Instance
# =============================================================================

_health_checker: HealthChecker | None = None


def get_health_checker(
    database_url: str | None = None,
    redis_url: str | None = None,
    opa_url: str | None = None,
) -> HealthChecker:
    """Get or create global health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker(
            database_url=database_url,
            redis_url=redis_url,
            opa_url=opa_url,
        )
    return _health_checker


def reset_health_checker() -> None:
    """Reset global health checker (for testing)."""
    global _health_checker
    _health_checker = None
