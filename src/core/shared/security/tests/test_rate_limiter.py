"""
Tests for src.core.shared.security.rate_limiter

Constitutional Hash: 608508a9bd224290
"""

import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

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
    TenantQuotaProviderProtocol,
    TenantRateLimitProvider,
    TokenBucket,
    _extract_request_from_call,
    _module_available,
    _parse_bool_env,
    _resolve_rate_limit_identifier,
    add_rate_limit_headers,
    configure_rate_limits,
    create_rate_limit_middleware,
    rate_limit,
    rate_limiter,
)

# ============================================================================
# _module_available
# ============================================================================


class TestModuleAvailable:
    def test_available_module(self):
        assert _module_available("os") is True

    def test_unavailable_module(self):
        assert _module_available("nonexistent_module_xyz_123") is False

    def test_stub_module_in_sys_modules(self):
        """Covers the ValueError fallback when __spec__ is missing."""
        stub = MagicMock(spec=[])  # no __spec__
        del stub.__spec__
        with patch.dict("sys.modules", {"_fake_stub_mod": stub}):
            # find_spec may raise ValueError for stub modules; fallback checks sys.modules
            assert _module_available("_fake_stub_mod") is True

    def test_stub_module_not_in_sys_modules(self):
        with patch("importlib.util.find_spec", side_effect=ValueError("no spec")):
            assert _module_available("nonexistent_xyz") is False


# ============================================================================
# _parse_bool_env
# ============================================================================


class TestParseBoolEnv:
    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "on", " True "])
    def test_truthy_values(self, value):
        assert _parse_bool_env(value) is True

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", "no", "off", " false "])
    def test_falsy_values(self, value):
        assert _parse_bool_env(value) is False

    def test_none_returns_none(self):
        assert _parse_bool_env(None) is None

    def test_unrecognized_returns_none(self):
        assert _parse_bool_env("maybe") is None
        assert _parse_bool_env("") is None


# ============================================================================
# RateLimitResult
# ============================================================================


class TestRateLimitResult:
    def test_initialization(self):
        reset_at = datetime.now(UTC)
        result = RateLimitResult(
            allowed=True, limit=100, remaining=99, reset_at=reset_at, retry_after=None
        )
        assert result.allowed is True
        assert result.limit == 100
        assert result.remaining == 99
        assert result.retry_after is None

    def test_to_headers_allowed(self):
        result = RateLimitResult(
            allowed=True, limit=100, remaining=50, reset_at=1700000000, scope=RateLimitScope.IP
        )
        headers = result.to_headers()
        assert headers["X-RateLimit-Limit"] == "100"
        assert headers["X-RateLimit-Remaining"] == "50"
        assert headers["X-RateLimit-Reset"] == "1700000000"
        assert headers["X-RateLimit-Scope"] == "ip"
        assert "Retry-After" not in headers

    def test_to_headers_denied_with_retry(self):
        result = RateLimitResult(
            allowed=False, limit=10, remaining=-5, reset_at=1700000060, retry_after=30
        )
        headers = result.to_headers()
        assert headers["X-RateLimit-Remaining"] == "0"  # clamped to 0
        assert headers["Retry-After"] == "30"


# ============================================================================
# RateLimitRule
# ============================================================================


class TestRateLimitRule:
    def test_defaults(self):
        rule = RateLimitRule(requests=100)
        assert rule.requests == 100
        assert rule.window_seconds == 60
        assert rule.scope == RateLimitScope.IP
        assert rule.burst_multiplier == 1.5
        assert rule.algorithm == RateLimitAlgorithm.SLIDING_WINDOW
        assert rule.limit == 100
        assert rule.burst_limit == 150
        assert rule.key_prefix == "ratelimit:ip"

    def test_custom(self):
        rule = RateLimitRule(
            requests=50,
            window_seconds=30,
            scope=RateLimitScope.USER,
            endpoints=["/api/v1"],
            burst_multiplier=2.0,
        )
        assert rule.limit == 50
        assert rule.burst_limit == 100
        assert rule.key_prefix == "ratelimit:user"

    def test_all_scopes_key_prefix(self):
        for scope in RateLimitScope:
            rule = RateLimitRule(requests=10, scope=scope)
            assert rule.key_prefix == f"ratelimit:{scope.value}"


# ============================================================================
# RateLimitConfig
# ============================================================================


class TestRateLimitConfig:
    def test_defaults(self):
        config = RateLimitConfig()
        assert config.rules == []
        assert config.redis_url is None
        assert config.fallback_to_memory is True
        assert config.enabled is True
        assert config.fail_open is True

    def test_from_env_production(self):
        from src.core.shared.config import settings

        with (
            patch.dict(
                "os.environ",
                {
                    "RATE_LIMIT_ENABLED": "true",
                    "RATE_LIMIT_REQUESTS_PER_MINUTE": "120",
                    "RATE_LIMIT_BURST_LIMIT": "20",
                    "REDIS_URL": "redis://localhost:6379",
                    # Clear env vars that override settings.env (e.g. EAB conftest sets ENVIRONMENT=test)
                    "ENVIRONMENT": "",
                    "APP_ENV": "",
                    "ACGS2_ENV": "",
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
            assert config.rules[0].burst_multiplier == 20 / 120

    def test_from_env_disabled(self):
        with patch.dict("os.environ", {"RATE_LIMIT_ENABLED": "false"}, clear=False):
            config = RateLimitConfig.from_env()
            assert config.enabled is False
            assert config.rules == []

    def test_from_env_fail_open_override(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_FAIL_OPEN", "true")
        config = RateLimitConfig.from_env()
        assert config.fail_open is True

    def test_from_env_fail_open_dev_default(self):
        from src.core.shared.config import settings

        with (
            patch.object(settings, "env", "development"),
            patch.dict("os.environ", {}, clear=False),
        ):
            # Remove RATE_LIMIT_FAIL_OPEN so it falls through to env check
            import os

            os.environ.pop("RATE_LIMIT_FAIL_OPEN", None)
            config = RateLimitConfig.from_env()
            assert config.fail_open is True

    def test_from_env_environment_only_production_disables_fail_open(self):
        from src.core.shared.config import settings

        with (
            patch.object(settings, "env", "development"),
            patch.dict("os.environ", {"ENVIRONMENT": "production"}, clear=False),
        ):
            import os

            os.environ.pop("APP_ENV", None)
            os.environ.pop("RATE_LIMIT_FAIL_OPEN", None)
            config = RateLimitConfig.from_env()
            assert config.fail_open is False

    def test_from_env_zero_requests(self):
        """When requests_per_minute is 0, burst_multiplier should default to 1.5."""
        with patch.dict(
            "os.environ",
            {
                "RATE_LIMIT_ENABLED": "true",
                "RATE_LIMIT_REQUESTS_PER_MINUTE": "0",
                "RATE_LIMIT_BURST_LIMIT": "10",
            },
            clear=False,
        ):
            config = RateLimitConfig.from_env()
            assert config.enabled is True
            assert len(config.rules) == 1
            assert config.rules[0].burst_multiplier == 1.5

    def test_exempt_paths_default(self):
        config = RateLimitConfig()
        assert "/health" in config.exempt_paths
        assert "/metrics" in config.exempt_paths


# ============================================================================
# TenantQuota
# ============================================================================


class TestTenantQuota:
    def test_effective_limit(self):
        quota = TenantQuota(tenant_id="t1", requests=100, burst_multiplier=1.5)
        assert quota.effective_limit == 150

    def test_to_rule(self):
        quota = TenantQuota(tenant_id="t1", requests=100, burst_multiplier=1.5)
        rule = quota.to_rule()
        assert rule.requests == 100
        assert rule.scope == RateLimitScope.TENANT
        assert rule.burst_multiplier == 1.5


# ============================================================================
# TenantQuotaProviderProtocol
# ============================================================================


class TestTenantQuotaProviderProtocol:
    def test_protocol_methods_exist(self):
        proto = TenantQuotaProviderProtocol()
        # These should not raise -- they are stubs returning None
        assert proto.get_quota("x") is None
        assert proto.set_quota("x", TenantQuota(tenant_id="x")) is None
        assert proto.remove_quota("x") is None


# ============================================================================
# TenantRateLimitProvider
# ============================================================================


class TestTenantRateLimitProvider:
    def test_crud(self):
        provider = TenantRateLimitProvider(default_requests=500)
        # Default quota for unknown
        quota = provider.get_quota("unknown")
        assert quota.tenant_id == "unknown"
        assert quota.requests == 500

        provider.set_tenant_quota("t1", requests=1000)
        assert provider.get_quota("t1").requests == 1000

        assert provider.remove_quota("t1") is True
        assert provider.remove_quota("nonexistent") is False

    def test_set_quota_with_object(self):
        provider = TenantRateLimitProvider()
        q = TenantQuota(tenant_id="t2", requests=200)
        provider.set_quota("t2", quota=q)
        assert provider.get_quota("t2").requests == 200

    def test_set_quota_with_params(self):
        provider = TenantRateLimitProvider(default_requests=100)
        provider.set_quota("t3", requests=300, window_seconds=120, burst_multiplier=2.0)
        q = provider.get_quota("t3")
        assert q.requests == 300
        assert q.window_seconds == 120
        assert q.burst_multiplier == 2.0

    def test_set_quota_defaults_fallback(self):
        provider = TenantRateLimitProvider(
            default_requests=50, default_window_seconds=30, default_burst_multiplier=1.2
        )
        provider.set_quota("t4")
        q = provider.get_quota("t4")
        assert q.requests == 50
        assert q.window_seconds == 30
        assert q.burst_multiplier == 1.2

    def test_remove_tenant_quota_alias(self):
        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t5", requests=100)
        assert provider.remove_tenant_quota("t5") is True
        assert provider.remove_tenant_quota("t5") is False

    def test_get_all_tenant_quotas_deep_copy(self):
        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t6", requests=100)
        all_quotas = provider.get_all_tenant_quotas()
        assert "t6" in all_quotas
        # Verify deep copy
        all_quotas["t6"].requests = 999
        assert provider.get_quota("t6").requests == 100

    def test_from_env(self):
        with patch.dict(
            "os.environ",
            {
                "RATE_LIMIT_TENANT_REQUESTS": "2000",
                "RATE_LIMIT_TENANT_WINDOW": "120",
                "RATE_LIMIT_TENANT_BURST": "2.0",
                "RATE_LIMIT_USE_REGISTRY": "true",
            },
        ):
            provider = TenantRateLimitProvider.from_env()
            assert provider._default_requests == 2000
            assert provider._default_window_seconds == 120
            assert provider._default_burst_multiplier == 2.0
            assert provider._use_registry is True

    def test_constitutional_hash(self):
        provider = TenantRateLimitProvider()
        assert provider.get_constitutional_hash() == CONSTITUTIONAL_HASH


# ============================================================================
# TokenBucket
# ============================================================================


class TestTokenBucket:
    def test_initial_state(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.tokens == 10

    def test_consume_success(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(5) is True

    def test_consume_insufficient(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(5) is True
        assert bucket.consume(6) is False

    def test_refill_with_time_advance(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        bucket.consume(5)
        with patch("time.time") as mock_time:
            mock_time.return_value = bucket.last_refill + 2.0
            bucket.refill()
            assert abs(bucket.tokens - 7.0) < 0.01

    def test_refill_caps_at_capacity(self):
        bucket = TokenBucket(capacity=10, refill_rate=100.0)
        bucket.consume(5)
        with patch("time.time") as mock_time:
            mock_time.return_value = bucket.last_refill + 10.0
            bucket.refill()
            assert bucket.tokens == 10  # capped

    def test_get_remaining_tokens(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.get_remaining_tokens() >= 9.9  # close to 10

    def test_get_reset_time_full(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.get_reset_time() == 0.0

    def test_get_reset_time_partial(self):
        bucket = TokenBucket(capacity=10, refill_rate=2.0)
        bucket.consume(10)
        with patch("time.time") as mock_time:
            mock_time.return_value = bucket.last_refill
            reset_time = bucket.get_reset_time()
            # 10 tokens needed / 2 per second = 5 seconds
            assert abs(reset_time - 5.0) < 0.1


# ============================================================================
# SlidingWindowRateLimiter - memory backend
# ============================================================================


class TestSlidingWindowMemory:
    async def test_allow_then_deny(self):
        limiter = SlidingWindowRateLimiter(fallback_to_memory=True)
        key = "test_allow_deny"

        r1 = await limiter.is_allowed(key, limit=2, window_seconds=1)
        assert r1.allowed is True
        assert r1.remaining == 1

        r2 = await limiter.is_allowed(key, limit=2, window_seconds=1)
        assert r2.allowed is True
        assert r2.remaining == 0

        r3 = await limiter.is_allowed(key, limit=2, window_seconds=1)
        assert r3.allowed is False
        assert r3.retry_after >= 1

    async def test_window_expiry(self):
        limiter = SlidingWindowRateLimiter(fallback_to_memory=True)
        key = "test_expiry"

        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            r1 = await limiter.is_allowed(key, limit=1, window_seconds=10)
            assert r1.allowed is True

            mock_time.return_value = 1005.0
            r2 = await limiter.is_allowed(key, limit=1, window_seconds=10)
            assert r2.allowed is False

            mock_time.return_value = 1011.0
            r3 = await limiter.is_allowed(key, limit=1, window_seconds=10)
            assert r3.allowed is True

    async def test_retry_after_uses_oldest_timestamp(self):
        limiter = SlidingWindowRateLimiter(fallback_to_memory=True)
        key = "test_retry_oldest"

        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            await limiter.is_allowed(key, limit=2, window_seconds=10)
            mock_time.return_value = 1001.0
            await limiter.is_allowed(key, limit=2, window_seconds=10)
            mock_time.return_value = 1002.0
            result = await limiter.is_allowed(key, limit=2, window_seconds=10)
            assert result.allowed is False
            assert result.retry_after == 8
            assert result.reset_at == 1010

    async def test_metrics_update_error_handled(self):
        """Metrics update errors should not propagate."""
        limiter = SlidingWindowRateLimiter(fallback_to_memory=True)
        with patch(
            "src.core.shared.security.rate_limiter.update_rate_limit_metrics",
            side_effect=RuntimeError("metrics broken"),
        ):
            result = await limiter.is_allowed("scope:id:endpoint", limit=10, window_seconds=60)
            assert result.allowed is True  # should not raise

    async def test_key_parsing_single_part(self):
        """Keys with fewer than 2 parts should still work."""
        limiter = SlidingWindowRateLimiter(fallback_to_memory=True)
        result = await limiter.is_allowed("simple", limit=10, window_seconds=60)
        assert result.allowed is True


# ============================================================================
# SlidingWindowRateLimiter - Redis backend
# ============================================================================


class TestSlidingWindowRedis:
    async def test_redis_success(self):
        """Covers _check_redis happy path."""
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 3, True, True])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=True)
        result = await limiter.is_allowed("key", limit=10, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 6  # 10 - (3+1)

    async def test_redis_denied(self):
        """Covers _check_redis deny path (count >= limit)."""
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 10, True, True])

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        mock_redis.zrem = AsyncMock()

        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=True)
        result = await limiter.is_allowed("key", limit=10, window_seconds=60)
        assert result.allowed is False
        assert result.retry_after == 60

    async def test_redis_connection_error_falls_back(self):
        """Covers the ConnectionError fallback branch."""
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=ConnectionError("Redis down"))

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=True)
        result = await limiter.is_allowed("fallback_key", limit=10, window_seconds=60)
        assert result.allowed is True  # memory fallback allows first request

    async def test_redis_generic_error_falls_back(self):
        """Covers the generic Exception fallback branch."""
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=Exception("auth error"))

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=True)
        result = await limiter.is_allowed("fallback_key2", limit=10, window_seconds=60)
        assert result.allowed is True

    async def test_redis_error_no_fallback_raises(self):
        """When fallback_to_memory=False, Redis errors propagate."""
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=ConnectionError("Redis down"))

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=False)
        with pytest.raises(ConnectionError):
            await limiter.is_allowed("no_fallback", limit=10, window_seconds=60)

    async def test_redis_generic_error_no_fallback_raises(self):
        """When fallback_to_memory=False, generic errors propagate."""
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=Exception("auth error"))

        mock_redis = MagicMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=False)
        with pytest.raises(Exception, match="auth error"):
            await limiter.is_allowed("no_fallback2", limit=10, window_seconds=60)


# ============================================================================
# RateLimitMiddleware
# ============================================================================


def _make_asgi_scope(path="/api/test", client=("127.0.0.1", 1234), headers=None):
    """Helper to build a minimal ASGI scope for middleware tests."""
    return {
        "type": "http",
        "client": client,
        "path": path,
        "method": "GET",
        "headers": headers or [],
        "query_string": b"",
        "server": ("testserver", 80),
    }


class TestRateLimitMiddleware:
    async def test_passthrough_when_disabled(self):
        app = AsyncMock()
        config = RateLimitConfig(enabled=False)
        mw = RateLimitMiddleware(app, config=config)

        scope = _make_asgi_scope()
        await mw(scope, AsyncMock(), AsyncMock())
        app.assert_called_once()

    async def test_passthrough_non_http(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        scope = {"type": "websocket"}
        await mw(scope, AsyncMock(), AsyncMock())
        app.assert_called_once()

    async def test_exempt_path_passthrough(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        scope = _make_asgi_scope(path="/health")
        await mw(scope, AsyncMock(), AsyncMock())
        app.assert_called_once()

    async def test_allow(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        await mw._ensure_initialized()

        scope = _make_asgi_scope()
        with patch.object(
            SlidingWindowRateLimiter,
            "is_allowed",
            return_value=RateLimitResult(
                allowed=True, limit=10, remaining=9, reset_at=int(time.time() + 60)
            ),
        ):
            await mw(scope, AsyncMock(), AsyncMock())
            app.assert_called()

    async def test_deny_returns_429(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        await mw._ensure_initialized()

        scope = _make_asgi_scope()
        send = AsyncMock()
        with patch.object(
            SlidingWindowRateLimiter,
            "is_allowed",
            return_value=RateLimitResult(
                allowed=False, limit=10, remaining=0, reset_at=int(time.time() + 60), retry_after=5
            ),
        ):
            await mw(scope, AsyncMock(), send)
            # Verify 429 was sent
            found_429 = False
            for call in send.call_args_list:
                msg = call[0][0]
                if msg.get("type") == "http.response.start" and msg.get("status") == 429:
                    found_429 = True
                    break
            assert found_429

    async def test_strict_mode_returns_503_when_backend_unavailable(self):
        app = AsyncMock()
        config = RateLimitConfig(
            rules=[RateLimitRule(requests=10)],
            redis_url="redis://localhost:6379",
            fallback_to_memory=False,
            fail_open=False,
        )
        mw = RateLimitMiddleware(app, config=config)

        scope = _make_asgi_scope()
        send = AsyncMock()
        with patch.object(
            RateLimitMiddleware, "_ensure_initialized", side_effect=RuntimeError("down")
        ):
            await mw(scope, AsyncMock(), send)

        found_503 = False
        for call in send.call_args_list:
            msg = call[0][0]
            if msg.get("type") == "http.response.start" and msg.get("status") == 503:
                found_503 = True
                break
        assert found_503

    async def test_is_exempt_path(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        assert mw._is_exempt_path("/health") is True
        assert mw._is_exempt_path("/metrics") is True
        assert mw._is_exempt_path("/api/v1/data") is False

    async def test_is_exempt_path_empty(self):
        app = AsyncMock()
        config = RateLimitConfig(exempt_paths=[])
        mw = RateLimitMiddleware(app, config=config)
        assert mw._is_exempt_path("/health") is False

    async def test_ensure_initialized_idempotent(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        await mw._ensure_initialized()
        limiter1 = mw.limiter
        await mw._ensure_initialized()
        assert mw.limiter is limiter1

    async def test_ensure_initialized_uses_injected_redis_client(self):
        app = AsyncMock()
        redis_client = AsyncMock()
        mw = RateLimitMiddleware(app, redis_client=redis_client)

        await mw._ensure_initialized()

        assert mw.redis is redis_client
        assert mw.limiter is not None
        assert mw.limiter.redis_client is redis_client

    async def test_check_rule_match_with_endpoints(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        scope = _make_asgi_scope(path="/api/v1/data")
        from starlette.requests import Request

        request = Request(scope)

        rule_match = RateLimitRule(requests=10, endpoints=["/api/v1"])
        rule_no_match = RateLimitRule(requests=10, endpoints=["/admin"])
        rule_all = RateLimitRule(requests=10)

        assert mw._check_rule_match(request, rule_match) is True
        assert mw._check_rule_match(request, rule_no_match) is False
        assert mw._check_rule_match(request, rule_all) is True

    async def test_build_key(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        scope = _make_asgi_scope(client=("10.0.0.1", 5000))
        from starlette.requests import Request

        request = Request(scope)
        rule = RateLimitRule(requests=10, scope=RateLimitScope.IP)
        key = mw._build_key(request, rule)
        assert "10.0.0.1" in key

    async def test_build_key_includes_trusted_tenant(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        scope = _make_asgi_scope(client=("10.0.0.1", 5000))
        scope["state"] = {"tenant_id": "tenant-42"}
        from starlette.requests import Request

        request = Request(scope)
        rule = RateLimitRule(requests=10, scope=RateLimitScope.IP)
        key = mw._build_key(request, rule)
        assert "tenant-42" in key
        assert "10.0.0.1" in key

    async def test_build_key_shares_bucket_for_grouped_multi_endpoint_rules(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        from starlette.requests import Request

        rule = RateLimitRule(
            requests=10,
            scope=RateLimitScope.IP,
            endpoints=["/x402/validate", "/x402/audit"],
        )
        validate_request = Request(
            _make_asgi_scope(path="/x402/validate", client=("10.0.0.1", 5000))
        )
        audit_request = Request(_make_asgi_scope(path="/x402/audit", client=("10.0.0.1", 5000)))

        assert mw._build_key(validate_request, rule) == mw._build_key(audit_request, rule)

    async def test_build_key_includes_endpoint_for_endpoint_scope_rules(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        scope = _make_asgi_scope(path="/api/v1/auth/login", client=("10.0.0.1", 5000))
        from starlette.requests import Request

        request = Request(scope)
        rule = RateLimitRule(
            requests=10, scope=RateLimitScope.ENDPOINT, endpoints=["/api/v1/auth/"]
        )
        key = mw._build_key(request, rule)
        assert "/api/v1/auth/" in key


# ============================================================================
# RateLimitMiddleware - tenant rate limiting
# ============================================================================


class TestMiddlewareTenantRateLimiting:
    async def test_tenant_quota_provider_integration(self):
        """Middleware with tenant provider checks tenant quota."""
        app = AsyncMock()
        provider = TenantRateLimitProvider(default_requests=100)
        config = RateLimitConfig(enabled=True, rules=[])
        mw = RateLimitMiddleware(app, config=config, tenant_quota_provider=provider)
        await mw._ensure_initialized()

        scope = _make_asgi_scope()
        scope["state"] = {"tenant_id": "tenant-1"}
        send = AsyncMock()
        await mw(scope, AsyncMock(), send)
        # With 100 request limit and first request, should pass through
        app.assert_called()

    async def test_get_tenant_quota_error_handled(self):
        app = AsyncMock()
        provider = MagicMock()
        provider.get_tenant_quota = MagicMock(side_effect=Exception("DB error"))
        mw = RateLimitMiddleware(app, tenant_quota_provider=provider)
        result = mw._get_tenant_quota("t1")
        assert result is None

    async def test_check_tenant_rate_limit_disabled(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        mw.limiter = SlidingWindowRateLimiter()

        scope = _make_asgi_scope()
        from starlette.requests import Request

        request = Request(scope)
        quota = TenantQuota(tenant_id="t1", requests=100, enabled=False)
        result = await mw._check_tenant_rate_limit(request, "t1", quota)
        assert result.allowed is True
        assert result.scope == RateLimitScope.TENANT

    async def test_check_tenant_rate_limit_enabled(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        mw.limiter = SlidingWindowRateLimiter()

        scope = _make_asgi_scope()
        from starlette.requests import Request

        request = Request(scope)
        quota = TenantQuota(tenant_id="t1", requests=5, enabled=True, burst_multiplier=1.0)
        result = await mw._check_tenant_rate_limit(request, "t1", quota)
        assert result.allowed is True
        assert result.scope == RateLimitScope.TENANT


# ============================================================================
# RateLimitMiddleware._get_tenant_id
# ============================================================================


class TestGetTenantId:
    def _make_request(self, scope=None):
        from starlette.requests import Request

        return Request(scope or _make_asgi_scope())

    def test_from_state_tenant_id(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        request = self._make_request()
        request.state.tenant_id = "state-tenant"
        assert mw._get_tenant_id(request) == "state-tenant"

    def test_from_state_auth_claims(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        request = self._make_request()
        request.state.auth_claims = {"tenant_id": "claims-tenant"}
        assert mw._get_tenant_id(request) == "claims-tenant"

    def test_from_state_user(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        request = self._make_request()
        user = MagicMock()
        user.tenant_id = "user-tenant"
        request.state.user = user
        assert mw._get_tenant_id(request) == "user-tenant"

    def test_from_header_fallback(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        scope = _make_asgi_scope(headers=[(b"x-tenant-id", b"header-tenant")])
        request = self._make_request(scope)
        assert mw._get_tenant_id(request) is None

    def test_no_tenant(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        request = self._make_request()
        assert mw._get_tenant_id(request) is None


# ============================================================================
# RateLimitMiddleware._create_429_response
# ============================================================================


class TestCreate429Response:
    def test_basic_429(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        result = RateLimitResult(
            allowed=False, limit=10, remaining=0, reset_at=1700000000, retry_after=30
        )
        response = mw._create_429_response(result)
        assert response.status_code == 429
        assert "X-RateLimit-Limit" in response.headers

    def test_429_with_tenant(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app)
        result = RateLimitResult(
            allowed=False,
            limit=10,
            remaining=0,
            reset_at=1700000000,
            retry_after=30,
            scope=RateLimitScope.TENANT,
        )
        response = mw._create_429_response(result, tenant_id="t1")
        assert response.status_code == 429
        assert "X-Tenant-RateLimit-Limit" in response.headers
        assert "X-Tenant-RateLimit-Remaining" in response.headers
        assert "X-Tenant-RateLimit-Reset" in response.headers


# ============================================================================
# _extract_request_from_call
# ============================================================================


class TestExtractRequest:
    def test_from_args(self):
        from starlette.requests import Request

        scope = _make_asgi_scope()
        request = Request(scope)
        result = _extract_request_from_call((request,), {})
        assert result is request

    def test_from_kwargs(self):
        from starlette.requests import Request

        scope = _make_asgi_scope()
        request = Request(scope)
        result = _extract_request_from_call((), {"request": request})
        assert result is request

    def test_not_found(self):
        result = _extract_request_from_call(("not_a_request",), {})
        assert result is None

    def test_non_request_in_kwargs(self):
        result = _extract_request_from_call((), {"request": "not_a_request"})
        assert result is None


# ============================================================================
# _resolve_rate_limit_identifier
# ============================================================================


class TestResolveIdentifier:
    def _make_request(self, user_id=None, client_ip="10.0.0.1"):
        from starlette.requests import Request

        scope = _make_asgi_scope(client=(client_ip, 1234))
        request = Request(scope)
        if user_id:
            request.state.user_id = user_id
        return request

    def test_custom_key_func(self):
        request = self._make_request()
        result = _resolve_rate_limit_identifier(request, "user", lambda r: "custom-key")
        assert result == "custom-key"

    def test_user_with_user_id(self):
        request = self._make_request(user_id="user-42")
        result = _resolve_rate_limit_identifier(request, "user", None)
        assert result == "user-42"

    def test_user_without_user_id(self):
        request = self._make_request(client_ip="1.2.3.4")
        result = _resolve_rate_limit_identifier(request, "user", None)
        assert result == "1.2.3.4"

    def test_ip(self):
        request = self._make_request(client_ip="192.168.1.1")
        result = _resolve_rate_limit_identifier(request, "ip", None)
        assert result == "192.168.1.1"

    def test_endpoint(self):
        request = self._make_request()
        result = _resolve_rate_limit_identifier(request, "endpoint", None)
        assert result == "/api/test"

    def test_global_fallback(self):
        request = self._make_request()
        result = _resolve_rate_limit_identifier(request, "global", None)
        assert result == "global"


# ============================================================================
# rate_limit decorator
# ============================================================================


class TestRateLimitDecorator:
    async def test_allowed(self):
        @rate_limit(requests_per_minute=60)
        async def endpoint(request):
            return {"ok": True}

        from starlette.requests import Request

        scope = _make_asgi_scope()
        request = Request(scope)

        with patch.object(
            SlidingWindowRateLimiter,
            "is_allowed",
            return_value=RateLimitResult(
                allowed=True, limit=60, remaining=59, reset_at=int(time.time() + 60)
            ),
        ):
            result = await endpoint(request)
            assert result == {"ok": True}

    async def test_denied_raises_429(self):
        @rate_limit(requests_per_minute=1)
        async def endpoint(request):
            return {"ok": True}

        from starlette.requests import Request

        scope = _make_asgi_scope()
        request = Request(scope)

        with patch.object(
            SlidingWindowRateLimiter,
            "is_allowed",
            return_value=RateLimitResult(
                allowed=False,
                limit=1,
                remaining=0,
                reset_at=int(time.time() + 60),
                retry_after=60,
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await endpoint(request)
            assert exc_info.value.status_code == 429

    async def test_no_request_passes_through(self):
        @rate_limit(requests_per_minute=60)
        async def endpoint(data: str):
            return {"data": data}

        result = await endpoint("hello")
        assert result == {"data": "hello"}

    async def test_request_in_kwargs(self):
        @rate_limit(requests_per_minute=60)
        async def endpoint(request):
            return {"ok": True}

        from starlette.requests import Request

        scope = _make_asgi_scope()
        request = Request(scope)

        with patch.object(
            SlidingWindowRateLimiter,
            "is_allowed",
            return_value=RateLimitResult(
                allowed=True, limit=60, remaining=59, reset_at=int(time.time() + 60)
            ),
        ):
            result = await endpoint(request=request)
            assert result == {"ok": True}


# ============================================================================
# create_rate_limit_middleware
# ============================================================================


class TestCreateRateLimitMiddleware:
    async def test_burst_capacity_wiring(self):
        burst_limit = 10
        burst_multiplier = 1.5
        expected_burst_capacity = int(burst_limit * burst_multiplier)
        expected_user_capacity = expected_burst_capacity * 2

        captured_calls = []

        async def mock_is_allowed(key, limit, window_seconds, scope):
            captured_calls.append({"key": key, "limit": limit})
            return RateLimitResult(
                allowed=True, limit=limit, remaining=limit - 1, reset_at=int(time.time() + 60)
            )

        middleware_fn = create_rate_limit_middleware(
            requests_per_minute=60,
            burst_limit=burst_limit,
            burst_multiplier=burst_multiplier,
        )

        from starlette.requests import Request as StarletteRequest
        from starlette.responses import Response

        scope = _make_asgi_scope()
        req = StarletteRequest(scope)
        call_next = AsyncMock(return_value=Response("ok"))

        with patch.object(SlidingWindowRateLimiter, "is_allowed", side_effect=mock_is_allowed):
            await middleware_fn(req, call_next)

        assert len(captured_calls) >= 1
        assert captured_calls[0]["limit"] == expected_user_capacity

    async def test_deny_returns_429_json(self):
        """Covers the 429 response branch in create_rate_limit_middleware."""
        middleware_fn = create_rate_limit_middleware(requests_per_minute=60, burst_limit=10)

        from starlette.requests import Request as StarletteRequest
        from starlette.responses import Response

        scope = _make_asgi_scope()
        req = StarletteRequest(scope)
        call_next = AsyncMock(return_value=Response("ok"))

        with patch.object(
            SlidingWindowRateLimiter,
            "is_allowed",
            return_value=RateLimitResult(
                allowed=False,
                limit=10,
                remaining=0,
                reset_at=int(time.time() + 60),
                retry_after=60,
            ),
        ):
            response = await middleware_fn(req, call_next)
            assert response.status_code == 429
            call_next.assert_not_called()


# ============================================================================
# add_rate_limit_headers
# ============================================================================


class TestAddRateLimitHeaders:
    async def test_adds_headers(self):
        middleware_fn = add_rate_limit_headers()

        from starlette.requests import Request as StarletteRequest
        from starlette.responses import Response

        scope = _make_asgi_scope()
        req = StarletteRequest(scope)
        response = Response("ok")
        call_next = AsyncMock(return_value=response)

        result = await middleware_fn(req, call_next)
        assert "X-RateLimit-Limit" in result.headers
        assert "X-RateLimit-Remaining" in result.headers
        assert "X-RateLimit-Reset" in result.headers

    async def test_does_not_overwrite_existing(self):
        middleware_fn = add_rate_limit_headers()

        from starlette.requests import Request as StarletteRequest
        from starlette.responses import Response

        scope = _make_asgi_scope()
        req = StarletteRequest(scope)
        response = Response("ok")
        response.headers["X-RateLimit-Remaining"] = "42"
        call_next = AsyncMock(return_value=response)

        result = await middleware_fn(req, call_next)
        assert result.headers["X-RateLimit-Remaining"] == "42"


# ============================================================================
# configure_rate_limits
# ============================================================================


class TestConfigureRateLimits:
    def test_configure_with_redis(self):
        mock_redis = MagicMock()
        configure_rate_limits(
            redis_client=mock_redis, default_requests_per_minute=120, default_burst_limit=20
        )
        assert rate_limiter.redis_client is mock_redis
        assert rate_limiter.default_rpm == 120
        assert rate_limiter.default_burst == 20
        # Clean up
        rate_limiter.redis_client = None

    def test_configure_without_redis(self):
        configure_rate_limits(default_requests_per_minute=30, default_burst_limit=5)
        assert rate_limiter.default_rpm == 30
        assert rate_limiter.default_burst == 5


# ============================================================================
# RateLimiter alias
# ============================================================================


class TestRateLimiterAlias:
    def test_alias(self):
        from src.core.shared.security.rate_limiter import RateLimiter

        assert RateLimiter is SlidingWindowRateLimiter
