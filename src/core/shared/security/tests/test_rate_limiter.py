"""
Module.

Constitutional Hash: cdd01ef066bc6cf2
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.core.shared.security.rate_limiter import (
    CONSTITUTIONAL_HASH,
    RateLimitAlgorithm,
    RateLimitConfig,
    RateLimitMiddleware,
    RateLimitResult,
    RateLimitRule,
    RateLimitScope,
    SlidingWindowRateLimiter,
    TenantQuota,
    TenantRateLimitProvider,
    TokenBucket,
    create_rate_limit_middleware,
    rate_limit,
)


# Test RateLimitResult
def test_rate_limit_result_initialization():
    reset_at = datetime.now(UTC)
    result = RateLimitResult(
        allowed=True, limit=100, remaining=99, reset_at=reset_at, retry_after=None
    )
    assert result.allowed is True
    assert result.limit == 100
    assert result.remaining == 99
    assert result.reset_at == reset_at
    assert result.retry_after is None


# Test RateLimitRule
def test_rate_limit_rule_defaults():
    rule = RateLimitRule(requests=100)
    assert rule.requests == 100
    assert rule.window_seconds == 60
    assert rule.scope == RateLimitScope.IP
    assert rule.burst_multiplier == 1.5
    assert rule.algorithm == RateLimitAlgorithm.SLIDING_WINDOW
    assert rule.limit == 100
    assert rule.burst_limit == 150
    assert rule.key_prefix == "ratelimit:ip"


def test_rate_limit_rule_custom():
    rule = RateLimitRule(
        requests=50,
        window_seconds=30,
        scope=RateLimitScope.USER,
        endpoints=["/api/v1"],
        burst_multiplier=2.0,
    )
    assert rule.requests == 50
    assert rule.window_seconds == 30
    assert rule.scope == RateLimitScope.USER
    assert rule.limit == 50
    assert rule.burst_limit == 100
    assert rule.key_prefix == "ratelimit:user"


# Test RateLimitConfig
def test_rate_limit_config_defaults():
    config = RateLimitConfig()
    assert config.rules == []
    assert config.redis_url is None
    assert config.fallback_to_memory is True
    assert config.enabled is True
    assert config.fail_open is True


def test_rate_limit_config_from_env():
    # Must patch settings.env — it's pre-computed at import time.
    # _runtime_environment() reads settings.env, not AGENT_RUNTIME_ENVIRONMENT env var.
    from src.core.shared.config import settings

    with (
        patch.dict(
            "os.environ",
            {
                "RATE_LIMIT_ENABLED": "true",
                "RATE_LIMIT_REQUESTS_PER_MINUTE": "120",
                "RATE_LIMIT_BURST_LIMIT": "20",
                "REDIS_URL": "redis://localhost:6379",
            },
        ),
        patch.object(settings, "env", "production"),
    ):
        config = RateLimitConfig.from_env()
        assert config.enabled is True
        assert config.redis_url == "redis://localhost:6379"
        assert config.fail_open is False
        assert len(config.rules) == 1
        assert config.rules[0].requests == 120
        # burst_multiplier = burst_limit / requests_per_minute = 20/120
        assert config.rules[0].burst_multiplier == 20 / 120


def test_rate_limit_config_fail_open_override(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_ENVIRONMENT", "production")
    monkeypatch.setenv("RATE_LIMIT_FAIL_OPEN", "true")

    config = RateLimitConfig.from_env()
    assert config.fail_open is True


def test_rate_limit_config_runtime_environment_precedence(monkeypatch):
    # _runtime_environment() reads settings.env, not AGENT_RUNTIME_ENVIRONMENT.
    from src.core.shared.config import settings

    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.delenv("RATE_LIMIT_FAIL_OPEN", raising=False)

    config = RateLimitConfig.from_env()
    assert config.fail_open is False


# Test TenantQuota
def test_tenant_quota_effective_limit():
    quota = TenantQuota(tenant_id="t1", requests=100, burst_multiplier=1.5)
    assert quota.effective_limit == 150

    rule = quota.to_rule()
    assert rule.requests == 100
    assert rule.scope == RateLimitScope.TENANT
    assert rule.burst_multiplier == 1.5


# Test TenantRateLimitProvider
def test_tenant_provider_crud():
    provider = TenantRateLimitProvider(default_requests=500)

    # Get default for unknown
    quota = provider.get_quota("unknown")
    assert quota.tenant_id == "unknown"
    assert quota.requests == 500

    # Set quota
    provider.set_tenant_quota("t1", requests=1000)
    quota = provider.get_quota("t1")
    assert quota.requests == 1000

    # Remove usage
    assert provider.remove_quota("t1") is True
    assert provider.remove_quota("unknown") is False


def test_tenant_provider_env():
    with patch.dict("os.environ", {"RATE_LIMIT_TENANT_REQUESTS": "2000"}):
        provider = TenantRateLimitProvider.from_env()
        assert provider._default_requests == 2000


def test_tenant_provider_hash():
    provider = TenantRateLimitProvider()
    assert provider.get_constitutional_hash() == CONSTITUTIONAL_HASH


# Test TokenBucket
def test_token_bucket_logic():
    bucket = TokenBucket(capacity=10, refill_rate=1.0)  # 1 token per second
    assert bucket.tokens == 10

    # Consume 5
    assert bucket.consume(5) is True
    assert abs(bucket.tokens - 5.0) < 0.001

    # Consume 6 (insufficient)
    assert bucket.consume(6) is False
    assert abs(bucket.tokens - 5.0) < 0.001

    # Refill logic
    # Mock time to advance 2 seconds
    with patch("time.time") as mock_time:
        mock_time.return_value = bucket.last_refill + 2.0
        bucket.refill()
        assert abs(bucket.tokens - 7.0) < 0.001

        # Reset time check
        assert bucket.get_remaining_tokens() > 0


# Test SlidingWindowRateLimiter
@pytest.mark.asyncio
async def test_sliding_window_allow_deny():
    limiter = SlidingWindowRateLimiter(fallback_to_memory=True)
    key = "test_key"

    # First request
    result = await limiter.is_allowed(key, limit=2, window_seconds=1)
    assert result.allowed is True
    assert result.remaining == 1

    # Second request
    result = await limiter.is_allowed(key, limit=2, window_seconds=1)
    assert result.allowed is True
    assert result.remaining == 0

    # Third request (should fail)
    result = await limiter.is_allowed(key, limit=2, window_seconds=1)
    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after == 1


@pytest.mark.asyncio
async def test_sliding_window_expiry():
    limiter = SlidingWindowRateLimiter(fallback_to_memory=True)
    key = "test_expiry_logic"

    # Logic test with explicit time patching
    with patch("time.time") as mock_time:
        mock_time.return_value = 1000.0
        # First call at t=1000
        result = await limiter.is_allowed(key, limit=1, window_seconds=10)
        assert result.allowed is True

        # Move time to 1005 (inside window) -> Deny
        mock_time.return_value = 1005.0
        result = await limiter.is_allowed(key, limit=1, window_seconds=10)
        assert result.allowed is False

        # Move time to 1011 (outside window) -> Allow (window slid)
        mock_time.return_value = 1011.0
        result = await limiter.is_allowed(key, limit=1, window_seconds=10)
        assert result.allowed is True


@pytest.mark.asyncio
async def test_sliding_window_retry_after_uses_oldest_timestamp():
    limiter = SlidingWindowRateLimiter(fallback_to_memory=True)
    key = "test_retry_after_oldest"
    window_seconds = 10

    with patch("time.time") as mock_time:
        mock_time.return_value = 1000.0
        result = await limiter.is_allowed(key, limit=2, window_seconds=window_seconds)
        assert result.allowed is True

        mock_time.return_value = 1001.0
        result = await limiter.is_allowed(key, limit=2, window_seconds=window_seconds)
        assert result.allowed is True

        mock_time.return_value = 1002.0
        result = await limiter.is_allowed(key, limit=2, window_seconds=window_seconds)
        assert result.allowed is False
        assert result.retry_after == 8
        assert result.reset_at == 1010


# Test RateLimitMiddleware
@pytest.mark.asyncio
async def test_middleware_logic():
    app_mock = AsyncMock()
    middleware = RateLimitMiddleware(app_mock)
    await middleware._ensure_initialized()

    scope = {
        "type": "http",
        "client": ("127.0.0.1", 1234),
        "path": "/api",
        "method": "GET",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
    }
    receive = AsyncMock()
    send = AsyncMock()

    # Allow
    with patch.object(
        SlidingWindowRateLimiter,
        "is_allowed",
        return_value=RateLimitResult(
            allowed=True, limit=10, remaining=9, reset_at=datetime.now(UTC)
        ),
    ):
        await middleware(scope, receive, send)
        app_mock.assert_called()

    # Deny
    app_mock.reset_mock()
    with patch.object(
        SlidingWindowRateLimiter,
        "is_allowed",
        return_value=RateLimitResult(
            allowed=False, limit=10, remaining=0, reset_at=datetime.now(UTC), retry_after=5
        ),
    ):
        await middleware(scope, receive, send)
        # Verify 429 response
        assert send.call_count > 0
        found_429 = False
        for call in send.call_args_list:
            if call[0][0].get("type") == "http.response.start":
                if call[0][0].get("status") == 429:
                    found_429 = True
                    break
        assert found_429


# Test create_rate_limit_middleware burst_capacity wiring (1C)
@pytest.mark.asyncio
async def test_middleware_burst_capacity_wiring():
    """Per-user capacity in limits_to_check should be int(burst_limit * burst_multiplier) * 2."""
    burst_limit = 10
    burst_multiplier = 1.5
    expected_burst_capacity = int(burst_limit * burst_multiplier)  # 15
    expected_user_capacity = expected_burst_capacity * 2  # 30

    captured_calls = []

    async def mock_is_allowed(key, limit, window_seconds, scope):
        captured_calls.append({"key": key, "limit": limit})
        return RateLimitResult(
            allowed=True, limit=limit, remaining=limit - 1, reset_at=datetime.now(UTC)
        )

    middleware_fn = create_rate_limit_middleware(
        requests_per_minute=60,
        burst_limit=burst_limit,
        burst_multiplier=burst_multiplier,
    )

    from starlette.applications import Starlette
    from starlette.responses import Response
    from starlette.routing import Route

    async def homepage(request):
        return Response("ok")

    _app = Starlette(routes=[Route("/", homepage)])

    with patch.object(SlidingWindowRateLimiter, "is_allowed", side_effect=mock_is_allowed):
        from starlette.requests import Request as StarletteRequest

        scope = {
            "type": "http",
            "client": ("127.0.0.1", 1234),
            "path": "/test",
            "method": "GET",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
        }
        call_next = AsyncMock(return_value=Response("ok"))

        req = StarletteRequest(scope)
        await middleware_fn(req, call_next)

    # The first call is for "user" limit — should use burst_capacity * 2
    assert len(captured_calls) >= 1
    user_call = captured_calls[0]
    assert user_call["limit"] == expected_user_capacity, (
        f"Expected user capacity={expected_user_capacity}, got {user_call['limit']}"
    )


# Test rate_limit decorator window_seconds and limit (1D)
@pytest.mark.asyncio
async def test_rate_limit_decorator_correct_window_and_limit():
    """rate_limit decorator should call is_allowed with window_seconds=60 and limit=requests_per_minute."""
    requests_per_minute = 120

    captured_kwargs = {}

    async def mock_is_allowed(key, limit, window_seconds, scope):
        captured_kwargs.update({"limit": limit, "window_seconds": window_seconds})
        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=limit - 1,
            reset_at=datetime.now(UTC),
        )

    from starlette.requests import Request as StarletteRequest

    scope = {
        "type": "http",
        "client": ("127.0.0.1", 1234),
        "path": "/api/test",
        "method": "POST",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
    }
    request = StarletteRequest(scope)

    @rate_limit(requests_per_minute=requests_per_minute, burst_limit=20)
    async def dummy_endpoint(request):
        return {"status": "ok"}

    with patch.object(SlidingWindowRateLimiter, "is_allowed", side_effect=mock_is_allowed):
        await dummy_endpoint(request)

    assert captured_kwargs.get("window_seconds") == 60, (
        f"Expected window_seconds=60, got {captured_kwargs.get('window_seconds')}"
    )
    assert captured_kwargs.get("limit") == requests_per_minute, (
        f"Expected limit={requests_per_minute}, got {captured_kwargs.get('limit')}"
    )
