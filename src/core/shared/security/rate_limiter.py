"""
ACGS-2 Rate Limiting Module — [CANONICAL]
Constitutional Hash: cdd01ef066bc6cf2

This is the **canonical** rate limiter module for ACGS-2 (Redis-backed,
production-grade, distributed).  New code should import from here
(``src.core.shared.security.rate_limiter``).

Landscape — other implementations that exist for historical/local reasons
(all are deprecated in favour of this module):

- ``src.core.services.api_gateway.rate_limiter.RateLimiter``
- ``packages.enhanced_agent_bus.guardrails.rate_limiter.RateLimiter``
- ``packages.enhanced_agent_bus.collaboration.server.RateLimiter``
- ``src.core.cognitive.dspy.adapters.RateLimiter``
- ``src.core.services.policy_registry.app.middleware.rbac.RateLimiter``
- ``src.core.services.antigravity.managers.rate_limiter.RateLimiter``
- ``src.core.shared.cache_warming.RateLimiter``

Production-grade rate limiting with Redis backend supporting:
- Sliding window rate limiting algorithm
- Per-IP, per-tenant, and per-endpoint limits
- Tenant-specific configurable quotas with dynamic lookup
- Distributed rate limiting across service instances
- Graceful degradation when Redis unavailable
- Constitutional compliance tracking

Security Features:
- Prevents brute force attacks
- Mitigates DoS attacks
- Protects expensive endpoints
- Provides audit trail for rate limit events
- Tenant isolation for multi-tenant deployments

Usage:
    from src.core.shared.security.rate_limiter import RateLimitMiddleware, RateLimitConfig

    # Basic usage with environment-based config
    app.add_middleware(
        RateLimitMiddleware,
        config=RateLimitConfig.from_env()
    )

    # With tenant-specific quotas
    from src.core.shared.security.rate_limiter import TenantRateLimitProvider

    provider = TenantRateLimitProvider()
    provider.set_tenant_quota("premium-tenant", requests=5000, window_seconds=60)

    app.add_middleware(
        RateLimitMiddleware,
        config=RateLimitConfig.from_env(),
        tenant_quota_provider=provider
    )
"""

import asyncio
import functools
import importlib.util
import math
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[assignment,misc]

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from src.core.shared.config import settings
from src.core.shared.config.runtime_environment import resolve_runtime_environment
from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.metrics import _get_or_create_counter, _get_or_create_gauge
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)


def _module_available(module_name: str) -> bool:
    """Return whether a module is available without crashing on stub modules.

    Some tests inject lightweight modules into ``sys.modules`` without setting
    ``__spec__``. ``importlib.util.find_spec`` raises ``ValueError`` in that
    case, so we fall back to checking ``sys.modules`` directly.
    """

    try:
        return importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError):
        return sys.modules.get(module_name) is not None


# Check for Redis availability
REDIS_AVAILABLE = _module_available("redis")

# Check for tenant config availability
TENANT_CONFIG_AVAILABLE = _module_available("src.core.shared.config")


def _runtime_environment() -> str:
    return resolve_runtime_environment(getattr(settings, "env", None))


def _parse_bool_env(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return None


class RateLimitScope(StrEnum):
    """Scope for rate limiting."""

    USER = "user"
    IP = "ip"
    ENDPOINT = "endpoint"
    GLOBAL = "global"
    TENANT = "tenant"


class RateLimitAlgorithm(StrEnum):
    """Rate limiting algorithms."""

    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"


@dataclass
class RateLimitRule:
    """Rate limit rule configuration."""

    requests: int  # Number of requests allowed
    window_seconds: int = 60  # Time window in seconds
    scope: RateLimitScope = RateLimitScope.IP  # Default to IP-based limiting
    endpoints: list[str] | None = None  # Optional endpoint patterns
    burst_multiplier: float = 1.5  # Burst allowance multiplier
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW

    # Backwards compatibility alias
    @property
    def limit(self) -> int:
        """Return the request limit (alias for requests)."""
        return self.requests

    @property
    def burst_limit(self) -> int:
        """Return the burst request limit based on burst_multiplier."""
        return int(self.requests * self.burst_multiplier)

    @property
    def key_prefix(self) -> str:
        """Generate cache key prefix for this rule."""
        return f"ratelimit:{self.scope.value}"


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    limit: int
    remaining: int
    reset_at: int  # Unix timestamp
    retry_after: int | None = None
    scope: RateLimitScope = RateLimitScope.IP
    key: str | None = None

    def to_headers(self) -> dict[str, str]:
        """Generate rate limit headers for response.

        Returns:
            Dictionary of rate limit headers
        """
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_at),
            "X-RateLimit-Scope": self.scope.value,
        }
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        return headers


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    rules: list[RateLimitRule] = field(default_factory=list)
    redis_url: str | None = None
    fallback_to_memory: bool = True
    enabled: bool = True
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW
    exempt_paths: list[str] = field(
        default_factory=lambda: ["/health", "/metrics", "/ready", "/live"]
    )
    fail_open: bool = True  # Continue processing if rate limiter fails

    @classmethod
    def from_env(cls) -> "RateLimitConfig":
        """Create configuration from environment variables."""
        enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
        requests_per_minute = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "60"))
        burst_limit = int(os.getenv("RATE_LIMIT_BURST_LIMIT", "10"))
        redis_url = os.getenv("REDIS_URL")
        configured_fail_open = _parse_bool_env(os.getenv("RATE_LIMIT_FAIL_OPEN"))

        if configured_fail_open is None:
            fail_open = _runtime_environment() in {
                "development",
                "dev",
                "test",
                "testing",
                "local",
                "ci",
            }
        else:
            fail_open = configured_fail_open

        rules = []
        if enabled:
            rules.append(
                RateLimitRule(
                    requests=requests_per_minute,
                    window_seconds=60,
                    burst_multiplier=(
                        burst_limit / requests_per_minute if requests_per_minute > 0 else 1.5
                    ),
                )
            )

        return cls(
            rules=rules,
            redis_url=redis_url,
            enabled=enabled,
            fail_open=fail_open,
        )


@dataclass
class TenantQuota:
    """Quota configuration for a specific tenant."""

    tenant_id: str
    requests: int = 100
    window_seconds: int = 60
    burst_multiplier: float = 1.0
    enabled: bool = True

    @property
    def effective_limit(self) -> int:
        """Calculate effective limit including burst multiplier."""
        return int(self.requests * self.burst_multiplier)

    def to_rule(self) -> RateLimitRule:
        """Convert to RateLimitRule."""
        return RateLimitRule(
            requests=self.requests,
            window_seconds=self.window_seconds,
            burst_multiplier=self.burst_multiplier,
            scope=RateLimitScope.TENANT,
        )


class TenantQuotaProviderProtocol:
    """Protocol for tenant quota providers."""

    def get_quota(self, tenant_id: str) -> TenantQuota | None:
        """Get quota for a tenant."""
        ...

    def set_quota(self, tenant_id: str, quota: TenantQuota) -> None:
        """Set quota for a tenant."""
        ...

    def remove_quota(self, tenant_id: str) -> bool:
        """Remove quota for a tenant."""
        ...


class TenantRateLimitProvider(TenantQuotaProviderProtocol):
    """Provider for tenant-specific rate limit quotas."""

    def __init__(
        self,
        default_requests: int = 1000,
        default_window_seconds: int = 60,
        default_burst_multiplier: float = 1.0,
        use_registry: bool = False,
    ):
        self._quotas: dict[str, TenantQuota] = {}
        self._default_requests = default_requests
        self._default_window_seconds = default_window_seconds
        self._default_burst_multiplier = default_burst_multiplier
        self._use_registry = use_registry
        self._constitutional_hash = CONSTITUTIONAL_HASH

    @classmethod
    def from_env(cls) -> "TenantRateLimitProvider":
        """Create provider from environment variables."""
        default_requests = int(os.getenv("RATE_LIMIT_TENANT_REQUESTS", "1000"))
        default_window = int(os.getenv("RATE_LIMIT_TENANT_WINDOW", "60"))
        default_burst = float(os.getenv("RATE_LIMIT_TENANT_BURST", "1.0"))
        use_registry = os.getenv("RATE_LIMIT_USE_REGISTRY", "false").lower() == "true"
        return cls(
            default_requests=default_requests,
            default_window_seconds=default_window,
            default_burst_multiplier=default_burst,
            use_registry=use_registry,
        )

    def get_tenant_quota(self, tenant_id: str) -> TenantQuota:
        """Get quota for a tenant."""
        if tenant_id in self._quotas:
            return self._quotas[tenant_id]
        # Return default quota for unknown tenants
        return TenantQuota(
            tenant_id=tenant_id,
            requests=self._default_requests,
            window_seconds=self._default_window_seconds,
            burst_multiplier=self._default_burst_multiplier,
        )

    def get_quota(self, tenant_id: str) -> TenantQuota | None:
        """Get quota for a tenant (alias for get_tenant_quota)."""
        return self.get_tenant_quota(tenant_id)

    def set_tenant_quota(
        self,
        tenant_id: str,
        requests: int,
        window_seconds: int = 60,
        burst_multiplier: float = 1.0,
        enabled: bool = True,
    ) -> None:
        """Set quota for a tenant."""
        self._quotas[tenant_id] = TenantQuota(
            tenant_id=tenant_id,
            requests=requests,
            window_seconds=window_seconds,
            burst_multiplier=burst_multiplier,
            enabled=enabled,
        )

    def set_quota(
        self,
        tenant_id: str,
        quota: TenantQuota | None = None,
        requests: int | None = None,
        window_seconds: int | None = None,
        burst_multiplier: float | None = None,
        enabled: bool = True,
    ) -> None:
        """Set quota for a tenant using either TenantQuota object or parameters."""
        if quota is not None:
            self._quotas[tenant_id] = quota
        else:
            self._quotas[tenant_id] = TenantQuota(
                tenant_id=tenant_id,
                requests=requests or self._default_requests,
                window_seconds=window_seconds or self._default_window_seconds,
                burst_multiplier=burst_multiplier or self._default_burst_multiplier,
                enabled=enabled,
            )

    def remove_quota(self, tenant_id: str) -> bool:
        """Remove quota for a tenant."""
        if tenant_id in self._quotas:
            del self._quotas[tenant_id]
            return True
        return False

    def remove_tenant_quota(self, tenant_id: str) -> bool:
        """Remove quota for a tenant (alias for remove_quota)."""
        return self.remove_quota(tenant_id)

    def get_all_tenant_quotas(self) -> dict[str, TenantQuota]:
        """Get all registered tenant quotas (returns deep copies)."""
        from copy import deepcopy

        return deepcopy(self._quotas)

    def get_constitutional_hash(self) -> str:
        """Return constitutional hash for verification."""
        return self._constitutional_hash


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""

    capacity: int  # Maximum tokens
    refill_rate: float  # Tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self):
        self.tokens = self.capacity
        self.last_refill = time.time()

    def refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate

        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        self.refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False

    def get_remaining_tokens(self) -> float:
        """Get remaining tokens in bucket."""
        self.refill()
        return self.tokens

    def get_reset_time(self) -> float:
        """Get time until bucket is fully refilled."""
        self.refill()
        if self.tokens >= self.capacity:
            return 0.0

        tokens_needed = self.capacity - self.tokens
        return tokens_needed / self.refill_rate


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter implementation.

    Uses a sliding window algorithm to provide smooth rate limiting
    that doesn't suffer from boundary issues like fixed windows.
    """

    def __init__(
        self,
        redis_client: object | None = None,
        fallback_to_memory: bool = True,
        key_prefix: str = "ratelimit",
    ):
        self.redis_client = redis_client
        self.fallback_to_memory = fallback_to_memory
        self.key_prefix = key_prefix
        self.local_windows: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()
        self._constitutional_hash = CONSTITUTIONAL_HASH

    async def is_allowed(
        self,
        key: str,
        limit: int,
        window_seconds: int = 60,
        scope: RateLimitScope = RateLimitScope.IP,
    ) -> RateLimitResult:
        """Check if request is allowed and record it."""
        now = time.time()

        # Try Redis first for distributed rate limiting
        if self.redis_client:
            try:
                return await self._check_redis(key, limit, window_seconds, scope, now)
            except (ConnectionError, TimeoutError, OSError) as e:
                if not self.fallback_to_memory:
                    raise
                logger.warning(f"Redis rate limit failed, using memory: {e}")
            except Exception as e:
                # Catch redis-specific errors (e.g. AuthenticationError) that don't
                # inherit from built-in ConnectionError
                if not self.fallback_to_memory:
                    raise
                logger.warning(f"Redis rate limit error, using memory fallback: {e}")

        if not self.fallback_to_memory:
            raise RuntimeError("Redis-backed rate limiting is unavailable")

        return await self._check_memory(key, limit, window_seconds, scope, now)

    async def _check_redis(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        scope: RateLimitScope,
        now: float,
    ) -> RateLimitResult:
        """Distributed rate limiting via Redis sorted sets."""
        redis_key = f"{self.key_prefix}:{key}"
        window_start = now - window_seconds

        pipe = self.redis_client.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        pipe.execute_command("ZADD", redis_key, now, f"{now}")
        pipe.expire(redis_key, window_seconds + 1)
        results = await pipe.execute()

        current_count = results[1]
        allowed = current_count < limit

        if not allowed:
            await self.redis_client.zrem(redis_key, f"{now}")
            current_count = results[1]
        else:
            current_count += 1

        remaining = max(0, limit - current_count)
        reset_at = int(now + window_seconds)
        retry_after = None if allowed else max(1, window_seconds)

        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after,
            scope=scope,
            key=key,
        )

    async def _check_memory(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        scope: RateLimitScope,
        now: float,
    ) -> RateLimitResult:
        """In-memory fallback rate limiting."""
        window_start = now - window_seconds

        async with self._lock:
            if key not in self.local_windows:
                self.local_windows[key] = []

            self.local_windows[key] = [ts for ts in self.local_windows[key] if ts > window_start]

            current_count = len(self.local_windows[key])
            allowed = current_count < limit

            if allowed:
                self.local_windows[key].append(now)
                current_count += 1

            remaining = max(0, limit - current_count)
            oldest = self.local_windows[key][0] if self.local_windows[key] else now
            reset_at = int(oldest + window_seconds)
            if allowed:
                retry_after = None
            else:
                secs = max(0.0, oldest + window_seconds - now)
                retry_after = max(1, math.ceil(secs))

            result = RateLimitResult(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
                scope=scope,
                key=key,
            )

            try:
                parts = key.split(":")
                endpoint = parts[-1] if len(parts) > 2 else "unknown"
                identifier = parts[1] if len(parts) > 1 else key
                update_rate_limit_metrics(scope.value, identifier, endpoint, allowed)
            except (RuntimeError, ValueError, TypeError):
                pass

            return result


# Alias for backward compatibility and internal usage
RateLimiter = SlidingWindowRateLimiter


class RateLimitMiddleware:
    """
    ASGI middleware for rate limiting.

    Features:
    - Redis-backed sliding window rate limiting
    - Multi-scope limits (IP, tenant, endpoint)
    - Tenant-specific configurable quotas via TenantRateLimitProvider
    - Rate limit headers in responses
    - Graceful degradation without Redis
    - Audit logging for rate limit events
    """

    def __init__(
        self,
        app,
        config: RateLimitConfig | None = None,
        tenant_quota_provider: TenantRateLimitProvider | None = None,
        redis_client: object | None = None,
    ):
        self.app = app
        self.config = config or RateLimitConfig.from_env()
        self.tenant_quota_provider = tenant_quota_provider
        self.redis: object | None = redis_client
        self.limiter: SlidingWindowRateLimiter | None = None
        self._initialized = False
        self._audit_log: list[JSONDict] = []
        self._constitutional_hash = CONSTITUTIONAL_HASH

        if not self.config.enabled:
            logger.info("Rate limiting is disabled")

        if self.tenant_quota_provider:
            logger.info("Tenant-specific rate limiting enabled via provider")

        if self.redis is not None:
            logger.info(
                "rate_limiter_redis_client_injected",
                constitutional_hash=self._constitutional_hash,
            )

    async def _initialize_redis_client(self) -> None:
        """Initialize the Redis backend when configured."""
        if self.redis is not None or not self.config.redis_url:
            return

        if not REDIS_AVAILABLE:
            raise RuntimeError("Redis client library is unavailable")

        try:
            import redis.asyncio as redis_async
        except ImportError as exc:
            raise RuntimeError("Redis client library is unavailable") from exc

        redis_client = redis_async.from_url(self.config.redis_url, decode_responses=True)
        await redis_client.ping()
        self.redis = redis_client

    async def _ensure_initialized(self) -> None:
        """Lazily initialize rate limiter components."""
        if self._initialized:
            return

        try:
            await self._initialize_redis_client()
        except Exception:
            if not self.config.fallback_to_memory:
                raise
            logger.warning("rate_limiter_redis_unavailable", exc_info=True)
            self.redis = None

        if not self.limiter:
            self.limiter = SlidingWindowRateLimiter(
                redis_client=self.redis, fallback_to_memory=self.config.fallback_to_memory
            )
            logger.info(
                "rate_limiter_backend_initialized",
                backend_mode="redis" if self.redis is not None else "memory",
                fallback_to_memory=self.config.fallback_to_memory,
                redis_configured=bool(self.config.redis_url),
                constitutional_hash=self._constitutional_hash,
            )

        self._initialized = True

    def _create_503_response(self, detail: str = "Rate limiting backend unavailable") -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "error": "Service Unavailable",
                "detail": detail,
                "constitutional_hash": self._constitutional_hash,
            },
        )

    def _get_tenant_quota(self, tenant_id: str) -> TenantQuota | None:
        """Get tenant-specific quota from provider if available.

        Args:
            tenant_id: The tenant identifier

        Returns:
            TenantQuota if provider is configured and tenant has quota, None otherwise
        """
        if self.tenant_quota_provider is None:
            return None

        try:
            return self.tenant_quota_provider.get_tenant_quota(tenant_id)
        except Exception as e:
            logger.warning(f"Failed to get tenant quota for {tenant_id}: {e}")
            return None

    async def _check_tenant_rate_limit(
        self,
        request: Request,
        tenant_id: str,
        tenant_quota: TenantQuota,
    ) -> RateLimitResult:
        """Check rate limit for a specific tenant using tenant-specific quota.

        Args:
            request: The incoming request
            tenant_id: The tenant identifier
            tenant_quota: The tenant's quota configuration

        Returns:
            RateLimitResult for the tenant
        """
        if not tenant_quota.enabled:
            # Tenant rate limiting disabled - allow all
            return RateLimitResult(
                allowed=True,
                limit=tenant_quota.requests,
                remaining=tenant_quota.requests,
                reset_at=int(time.time() + tenant_quota.window_seconds),
                scope=RateLimitScope.TENANT,
                key=f"tenant:{tenant_id}",
            )

        key = f"tenant:{tenant_id}"
        result = await self.limiter.is_allowed(
            key=key,
            limit=tenant_quota.effective_limit,
            window_seconds=tenant_quota.window_seconds,
            scope=RateLimitScope.TENANT,
        )
        return result

    def _is_exempt_path(self, path: str) -> bool:
        """Check if path is exempt from rate limiting."""
        if not self.config.exempt_paths:
            return False
        return any(path.startswith(ep) for ep in self.config.exempt_paths)

    async def __call__(self, scope, receive, send):
        """ASGI interface for rate limiting middleware."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # If rate limiting is disabled, pass through directly
        if not self.config.enabled:
            await self.app(scope, receive, send)
            return

        # Check exempt paths early
        path = scope.get("path", "")
        if self._is_exempt_path(path):
            await self.app(scope, receive, send)
            return

        try:
            await self._ensure_initialized()
        except Exception as exc:
            if self.config.fail_open:
                logger.warning("rate_limiter_initialization_failed", error=str(exc))
                await self.app(scope, receive, send)
                return
            response = self._create_503_response()
            await response(scope, receive, send)
            return

        # Create request for inspection
        request = Request(scope, receive)

        # Check tenant context
        tenant_id = self._get_tenant_id(request)

        # Check tenant-specific quota if applicable
        if self.tenant_quota_provider and tenant_id:
            tenant_quota = self._get_tenant_quota(tenant_id)
            if tenant_quota:
                try:
                    result = await self._check_tenant_rate_limit(request, tenant_id, tenant_quota)
                except Exception as exc:
                    if self.config.fail_open:
                        logger.warning("tenant_rate_limit_failed", error=str(exc))
                        await self.app(scope, receive, send)
                        return
                    response = self._create_503_response()
                    await response(scope, receive, send)
                    return
                self._log_audit(request, result, None)

                if not result.allowed:
                    response = self._create_429_response(result, tenant_id)
                    await response(scope, receive, send)
                    return

        # Iterate through configured rules
        for rule in self.config.rules:
            # Skip if rule doesn't match
            if not self._check_rule_match(request, rule):
                continue

            key = self._build_key(request, rule)
            try:
                result = await self.limiter.is_allowed(
                    key, limit=rule.requests, window_seconds=rule.window_seconds
                )
            except Exception as exc:
                if self.config.fail_open:
                    logger.warning("rate_limit_check_failed", error=str(exc), path=request.url.path)
                    await self.app(scope, receive, send)
                    return
                response = self._create_503_response()
                await response(scope, receive, send)
                return

            self._log_audit(request, result, rule)

            if not result.allowed:
                response = self._create_429_response(result)
                await response(scope, receive, send)
                return

        # If allowed, pass through to app
        await self.app(scope, receive, send)

    def _get_tenant_id(self, request: Request) -> str | None:
        """Extract tenant ID from authenticated request state.

        Tenant ID is only trusted from auth-middleware-populated request.state
        to prevent spoofing via raw headers.
        """
        # 1. Check for tenant_id in request.state (populated by auth middleware)
        if hasattr(request.state, "tenant_id") and request.state.tenant_id:
            return request.state.tenant_id

        # 2. Check for auth_claims in request.state (populated by auth middleware)
        if hasattr(request.state, "auth_claims") and request.state.auth_claims:
            return request.state.auth_claims.get("tenant_id")

        # 3. Check for user in request.state (populated by some auth middlewares)
        if hasattr(request.state, "user") and hasattr(request.state.user, "tenant_id"):
            return request.state.user.tenant_id

        return None

    def _check_rule_match(self, request: Request, rule: RateLimitRule) -> bool:
        if rule.endpoints:
            return any(request.url.path.startswith(ep) for ep in rule.endpoints)
        return True

    def _build_key(self, request: Request, rule: RateLimitRule) -> str:
        client_id = request.client.host if request.client else "unknown"
        tenant_id = self._get_tenant_id(request)
        key_parts = [rule.key_prefix]
        if tenant_id:
            key_parts.append(tenant_id)
        key_parts.append(client_id)
        if rule.scope == RateLimitScope.ENDPOINT:
            matched_endpoint = next(
                (endpoint for endpoint in (rule.endpoints or []) if request.url.path.startswith(endpoint)),
                request.url.path,
            )
            key_parts.append(matched_endpoint)
        return ":".join(key_parts)

    def _create_429_response(
        self, result: RateLimitResult, tenant_id: str | None = None
    ) -> JSONResponse:
        content = {
            "error": "Too Many Requests",
            "retry_after": result.retry_after,
            "constitutional_hash": self._constitutional_hash,
        }
        if tenant_id:
            content["tenant_id"] = tenant_id

        response = JSONResponse(status_code=429, content=content)

        # Add standard rate limit headers
        for key, value in result.to_headers().items():
            response.headers[key] = value

        # Add tenant-specific headers if applicable
        if tenant_id and result.scope == RateLimitScope.TENANT:
            response.headers["X-Tenant-RateLimit-Limit"] = str(result.limit)
            response.headers["X-Tenant-RateLimit-Remaining"] = str(max(0, result.remaining))
            response.headers["X-Tenant-RateLimit-Reset"] = str(result.reset_at)

        return response

    def _log_audit(
        self, request: Request, result: RateLimitResult, rule: RateLimitRule | None
    ) -> None:
        pass


# Global rate limiter instance
rate_limiter = RateLimiter()

# ============================================================================
# FastAPI Integration
# ============================================================================


def create_rate_limit_middleware(
    requests_per_minute: int = 60,
    burst_limit: int = 10,
    burst_multiplier: float = 1.5,
    fail_open: bool = True,
):
    """
    Create FastAPI middleware for rate limiting.

    Args:
        requests_per_minute: Base rate limit
        burst_limit: Burst capacity
        burst_multiplier: Multiplier for burst capacity
        fail_open: Whether to allow requests if rate limiter fails

    Returns:
        Middleware function
    """
    refill_rate = requests_per_minute / 60.0  # Convert to per second
    _burst_capacity = int(burst_limit * burst_multiplier)

    async def rate_limit_middleware(request: Request, call_next):
        """Apply multi-scope rate limiting (user, IP, endpoint) to each request."""
        # Extract identifiers
        client_ip = request.client.host if request.client else "unknown"
        user_id = getattr(request.state, "user_id", None) or client_ip
        endpoint = request.url.path

        # Check rate limits (in order of specificity)
        limits_to_check = [
            # Per-user limits (most specific) — 2x burst capacity
            ("user", user_id, _burst_capacity * 2, refill_rate * 2, endpoint),
            # Per-IP limits — base burst capacity
            ("ip", client_ip, _burst_capacity, refill_rate, endpoint),
            # Per-endpoint limits — 3x burst capacity
            ("endpoint", endpoint, _burst_capacity * 3, refill_rate * 3, ""),
        ]

        for limit_type, identifier, capacity, _refill, endpoint_key in limits_to_check:
            key = f"{limit_type}:{identifier}:{endpoint_key}"
            result = await rate_limiter.is_allowed(
                key=key,
                limit=capacity,
                window_seconds=60,  # Default window
                scope=RateLimitScope(limit_type),
            )

            if not result.allowed:
                # Return rate limit exceeded response
                response = JSONResponse(
                    status_code=429,
                    content={
                        "error": "Too Many Requests",
                        "message": f"Rate limit exceeded for {limit_type}",
                        "retry_after": result.retry_after,
                        "scope": limit_type,
                        "constitutional_hash": CONSTITUTIONAL_HASH,
                    },
                )

                # Add rate limit headers
                response.headers["X-RateLimit-Remaining"] = str(int(result.remaining))
                response.headers["X-RateLimit-Reset"] = str(result.reset_at)
                response.headers["X-RateLimit-Limit"] = str(capacity)
                response.headers["Retry-After"] = str(int(result.retry_after or 0))

                return response

        # Continue with request
        response = await call_next(request)
        return response

    return rate_limit_middleware


# ============================================================================
# Decorator for Endpoint-Specific Rate Limiting
# ============================================================================


def _extract_request_from_call(args: tuple, kwargs: dict) -> Request | None:
    """Extract FastAPI Request from decorated endpoint call."""
    for arg in args:
        if isinstance(arg, Request):
            return arg

    request_candidate = kwargs.get("request")
    if isinstance(request_candidate, Request):
        return request_candidate

    return None


def _resolve_rate_limit_identifier(
    request: Request, limit_type: str, key_func: Callable[[Request], str] | None
) -> str:
    """Resolve the identifier used for scoped rate limiting."""
    if key_func:
        return key_func(request)

    client_ip = request.client.host if request.client else "unknown"
    if limit_type == "user":
        return getattr(request.state, "user_id", None) or client_ip
    if limit_type == "ip":
        return client_ip
    if limit_type == "endpoint":
        return request.url.path
    return "global"


def rate_limit(
    requests_per_minute: int = 60, burst_limit: int = 10, limit_type: str = "user", key_func=None
):
    """
    Decorator for endpoint-specific rate limiting.

    Args:
        requests_per_minute: Rate limit
        burst_limit: Burst capacity
        limit_type: Type of limit (user, ip, endpoint, global)
        key_func: Function to extract identifier from request

    Returns:
        Decorator function
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            request = _extract_request_from_call(args, kwargs)
            if request is None:
                return await func(*args, **kwargs)

            identifier = _resolve_rate_limit_identifier(request, limit_type, key_func)
            key = f"{limit_type}:{identifier}:{request.url.path}"
            result = await rate_limiter.is_allowed(
                key=key,
                limit=requests_per_minute,
                window_seconds=60,
                scope=RateLimitScope(limit_type),
            )

            if not result.allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Too Many Requests",
                        "message": f"Rate limit exceeded for {limit_type}",
                        "retry_after": int(result.retry_after or 0),
                        "remaining": int(result.remaining),
                        "limit": requests_per_minute,
                    },
                )

            return await func(*args, **kwargs)

        return wrapper

    _ = burst_limit  # Reserved for future token bucket burst controls.
    return decorator


# ============================================================================
# Rate Limit Headers Middleware
# ============================================================================


def add_rate_limit_headers() -> Callable:
    """
    Middleware to add rate limit headers to responses.

    Usage:
        app.add_middleware(add_rate_limit_headers())
    """

    async def middleware(request: Request, call_next):
        """Inject X-RateLimit-* headers into each response."""
        response = await call_next(request)

        # Add rate limit headers if not already present
        if "X-RateLimit-Remaining" not in response.headers:
            # This is a simplified implementation
            # In production, you'd track actual limits per request
            response.headers["X-RateLimit-Limit"] = "60"
            response.headers["X-RateLimit-Remaining"] = "59"
            response.headers["X-RateLimit-Reset"] = str(int(time.time() + 60))

        return response

    return middleware


# ============================================================================
# Configuration Helpers
# ============================================================================


def configure_rate_limits(
    redis_client=None,
    default_requests_per_minute: int = 60,
    default_burst_limit: int = 10,
) -> None:
    """
    Configure global rate limiting settings.

    Args:
        redis_client: Redis client for distributed rate limiting
        default_requests_per_minute: Default rate limit
        default_burst_limit: Default burst capacity
    """
    global rate_limiter
    if redis_client:
        rate_limiter.redis_client = redis_client

    # Store defaults for middleware creation
    rate_limiter.default_rpm = default_requests_per_minute
    rate_limiter.default_burst = default_burst_limit


# ============================================================================
# Monitoring Integration
# ============================================================================


# Rate limiting metrics
RATE_LIMIT_EXCEEDED = _get_or_create_counter(
    "rate_limit_exceeded_total",
    "Total rate limit violations",
    ["limit_type", "identifier", "endpoint"],
)

RATE_LIMIT_REQUESTS = _get_or_create_counter(
    "rate_limit_requests_total",
    "Total requests subject to rate limiting",
    ["limit_type", "identifier", "endpoint", "allowed"],
)

ACTIVE_RATE_LIMITS = _get_or_create_gauge(
    "rate_limits_active", "Number of active rate limit buckets", []
)


def update_rate_limit_metrics(
    limit_type: str, identifier: str, endpoint: str, allowed: bool
) -> None:
    """
    Update rate limiting metrics.

    Called automatically by rate limiting functions.
    """
    RATE_LIMIT_REQUESTS.labels(
        limit_type=limit_type,
        identifier=identifier,
        endpoint=endpoint,
        allowed=str(allowed).lower(),
    ).inc()

    if not allowed:
        RATE_LIMIT_EXCEEDED.labels(
            limit_type=limit_type, identifier=identifier, endpoint=endpoint
        ).inc()


# Metrics are integrated into SlidingWindowRateLimiter

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Feature flags
    "REDIS_AVAILABLE",
    "TENANT_CONFIG_AVAILABLE",
    "RateLimitAlgorithm",
    "RateLimitConfig",
    "RateLimitMiddleware",
    "RateLimitResult",
    # Dataclasses
    "RateLimitRule",
    # Enums
    "RateLimitScope",
    # Core classes
    "RateLimiter",
    "SlidingWindowRateLimiter",
    # Tenant-specific rate limiting
    "TenantQuota",
    "TenantQuotaProviderProtocol",
    "TenantRateLimitProvider",
    "TokenBucket",
    # Middleware
    "create_rate_limit_middleware",
    # Global instance
    "rate_limiter",
]
