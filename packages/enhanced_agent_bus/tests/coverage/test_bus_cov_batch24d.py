"""
Comprehensive coverage tests for shared config and security modules (batch 24d).

Targets:
- src/core/shared/security/rate_limiter.py (74 missing lines, 83.0%)
- src/core/shared/config/security.py (69 missing lines, 53.1%)
- src/core/shared/config/governance.py (45 missing lines, 50.0%)

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# Module 1: src.core.shared.security.rate_limiter
# =============================================================================


class TestParseBoolEnv:
    """Test _parse_bool_env helper."""

    def test_none_returns_none(self):
        from src.core.shared.security.rate_limiter import _parse_bool_env

        assert _parse_bool_env(None) is None

    def test_true_variants(self):
        from src.core.shared.security.rate_limiter import _parse_bool_env

        for val in ["true", "1", "yes", "on", "TRUE", " True ", " YES ", " On "]:
            assert _parse_bool_env(val) is True, f"Expected True for {val!r}"

    def test_false_variants(self):
        from src.core.shared.security.rate_limiter import _parse_bool_env

        for val in ["false", "0", "no", "off", "FALSE", " False ", " NO ", " Off "]:
            assert _parse_bool_env(val) is False, f"Expected False for {val!r}"

    def test_unrecognized_returns_none(self):
        from src.core.shared.security.rate_limiter import _parse_bool_env

        assert _parse_bool_env("maybe") is None
        assert _parse_bool_env("") is None
        assert _parse_bool_env("2") is None


class TestModuleAvailable:
    """Test _module_available helper."""

    def test_available_module(self):
        from src.core.shared.security.rate_limiter import _module_available

        assert _module_available("os") is True

    def test_unavailable_module(self):
        from src.core.shared.security.rate_limiter import _module_available

        assert _module_available("nonexistent_module_xyz_123") is False

    def test_stub_module_in_sys_modules(self):
        """Test that stub modules without __spec__ are detected via sys.modules fallback."""
        import sys

        from src.core.shared.security.rate_limiter import _module_available

        stub = MagicMock(spec=[])  # no __spec__ attribute
        del stub.__spec__  # ensure ValueError from find_spec
        old = sys.modules.get("_test_stub_mod_24d")
        sys.modules["_test_stub_mod_24d"] = stub
        try:
            result = _module_available("_test_stub_mod_24d")
            assert result is True
        finally:
            if old is None:
                sys.modules.pop("_test_stub_mod_24d", None)
            else:
                sys.modules["_test_stub_mod_24d"] = old


class TestRateLimitRule:
    """Test RateLimitRule dataclass properties."""

    def test_limit_alias(self):
        from src.core.shared.security.rate_limiter import RateLimitRule

        rule = RateLimitRule(requests=100)
        assert rule.limit == 100

    def test_burst_limit(self):
        from src.core.shared.security.rate_limiter import RateLimitRule

        rule = RateLimitRule(requests=100, burst_multiplier=2.0)
        assert rule.burst_limit == 200

    def test_key_prefix(self):
        from src.core.shared.security.rate_limiter import RateLimitRule, RateLimitScope

        rule = RateLimitRule(requests=50, scope=RateLimitScope.TENANT)
        assert rule.key_prefix == "ratelimit:tenant"

    def test_default_values(self):
        from src.core.shared.security.rate_limiter import (
            RateLimitAlgorithm,
            RateLimitRule,
            RateLimitScope,
        )

        rule = RateLimitRule(requests=10)
        assert rule.window_seconds == 60
        assert rule.scope == RateLimitScope.IP
        assert rule.endpoints is None
        assert rule.burst_multiplier == 1.5
        assert rule.algorithm == RateLimitAlgorithm.SLIDING_WINDOW


class TestRateLimitResult:
    """Test RateLimitResult to_headers method."""

    def test_to_headers_without_retry(self):
        from src.core.shared.security.rate_limiter import RateLimitResult, RateLimitScope

        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=50,
            reset_at=1234567890,
            scope=RateLimitScope.IP,
        )
        headers = result.to_headers()
        assert headers["X-RateLimit-Limit"] == "100"
        assert headers["X-RateLimit-Remaining"] == "50"
        assert headers["X-RateLimit-Reset"] == "1234567890"
        assert headers["X-RateLimit-Scope"] == "ip"
        assert "Retry-After" not in headers

    def test_to_headers_with_retry(self):
        from src.core.shared.security.rate_limiter import RateLimitResult, RateLimitScope

        result = RateLimitResult(
            allowed=False,
            limit=100,
            remaining=-5,
            reset_at=1234567890,
            retry_after=30,
            scope=RateLimitScope.USER,
        )
        headers = result.to_headers()
        assert headers["X-RateLimit-Remaining"] == "0"  # max(0, -5)
        assert headers["Retry-After"] == "30"
        assert headers["X-RateLimit-Scope"] == "user"


class TestRateLimitConfig:
    """Test RateLimitConfig.from_env()."""

    def test_from_env_defaults(self):
        from src.core.shared.security.rate_limiter import RateLimitConfig

        env = {
            "RATE_LIMIT_ENABLED": "true",
            "RATE_LIMIT_REQUESTS_PER_MINUTE": "60",
            "RATE_LIMIT_BURST_LIMIT": "10",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch(
                "src.core.shared.security.rate_limiter._runtime_environment",
                return_value="test",
            ):
                with patch.dict("os.environ", {"RATE_LIMIT_FAIL_OPEN": ""}, clear=False):
                    # Remove RATE_LIMIT_FAIL_OPEN to test auto-detect
                    import os

                    old = os.environ.pop("RATE_LIMIT_FAIL_OPEN", None)
                    try:
                        config = RateLimitConfig.from_env()
                        assert config.enabled is True
                        assert len(config.rules) == 1
                        assert config.rules[0].requests == 60
                        # test env -> fail_open=True
                        assert config.fail_open is True
                    finally:
                        if old is not None:
                            os.environ["RATE_LIMIT_FAIL_OPEN"] = old

    def test_from_env_disabled(self):
        from src.core.shared.security.rate_limiter import RateLimitConfig

        with patch.dict(
            "os.environ",
            {"RATE_LIMIT_ENABLED": "false", "RATE_LIMIT_FAIL_OPEN": "true"},
            clear=False,
        ):
            config = RateLimitConfig.from_env()
            assert config.enabled is False
            assert len(config.rules) == 0

    def test_from_env_explicit_fail_open_false(self):
        from src.core.shared.security.rate_limiter import RateLimitConfig

        with patch.dict(
            "os.environ",
            {"RATE_LIMIT_FAIL_OPEN": "false", "RATE_LIMIT_ENABLED": "true"},
            clear=False,
        ):
            config = RateLimitConfig.from_env()
            assert config.fail_open is False

    def test_from_env_production_fail_open_auto(self):
        """In production env with no explicit setting, fail_open should be False."""
        import os

        from src.core.shared.security.rate_limiter import RateLimitConfig

        env_copy = {
            "RATE_LIMIT_ENABLED": "true",
            "RATE_LIMIT_REQUESTS_PER_MINUTE": "60",
            "RATE_LIMIT_BURST_LIMIT": "10",
        }
        with patch.dict("os.environ", env_copy, clear=False):
            os.environ.pop("RATE_LIMIT_FAIL_OPEN", None)
            with patch(
                "src.core.shared.security.rate_limiter._runtime_environment",
                return_value="production",
            ):
                config = RateLimitConfig.from_env()
                assert config.fail_open is False

    def test_from_env_zero_requests_per_minute(self):
        from src.core.shared.security.rate_limiter import RateLimitConfig

        with patch.dict(
            "os.environ",
            {
                "RATE_LIMIT_ENABLED": "true",
                "RATE_LIMIT_REQUESTS_PER_MINUTE": "0",
                "RATE_LIMIT_BURST_LIMIT": "10",
                "RATE_LIMIT_FAIL_OPEN": "true",
            },
            clear=False,
        ):
            config = RateLimitConfig.from_env()
            assert config.rules[0].burst_multiplier == 1.5


class TestTenantQuota:
    """Test TenantQuota dataclass."""

    def test_effective_limit(self):
        from src.core.shared.security.rate_limiter import TenantQuota

        q = TenantQuota(tenant_id="t1", requests=100, burst_multiplier=1.5)
        assert q.effective_limit == 150

    def test_to_rule(self):
        from src.core.shared.security.rate_limiter import RateLimitScope, TenantQuota

        q = TenantQuota(tenant_id="t1", requests=200, window_seconds=120, burst_multiplier=2.0)
        rule = q.to_rule()
        assert rule.requests == 200
        assert rule.window_seconds == 120
        assert rule.burst_multiplier == 2.0
        assert rule.scope == RateLimitScope.TENANT


class TestTenantRateLimitProvider:
    """Test TenantRateLimitProvider."""

    def test_get_tenant_quota_default(self):
        from src.core.shared.security.rate_limiter import TenantRateLimitProvider

        provider = TenantRateLimitProvider(default_requests=500)
        q = provider.get_tenant_quota("unknown-tenant")
        assert q.tenant_id == "unknown-tenant"
        assert q.requests == 500

    def test_set_and_get_tenant_quota(self):
        from src.core.shared.security.rate_limiter import TenantRateLimitProvider

        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=2000, window_seconds=120, burst_multiplier=1.5)
        q = provider.get_tenant_quota("t1")
        assert q.requests == 2000
        assert q.window_seconds == 120

    def test_get_quota_alias(self):
        from src.core.shared.security.rate_limiter import TenantRateLimitProvider

        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=100)
        q = provider.get_quota("t1")
        assert q is not None
        assert q.requests == 100

    def test_set_quota_with_object(self):
        from src.core.shared.security.rate_limiter import TenantQuota, TenantRateLimitProvider

        provider = TenantRateLimitProvider()
        quota = TenantQuota(tenant_id="t2", requests=300)
        provider.set_quota("t2", quota=quota)
        assert provider.get_quota("t2").requests == 300

    def test_set_quota_with_params(self):
        from src.core.shared.security.rate_limiter import TenantRateLimitProvider

        provider = TenantRateLimitProvider()
        provider.set_quota("t3", requests=400, window_seconds=30)
        q = provider.get_quota("t3")
        assert q.requests == 400
        assert q.window_seconds == 30

    def test_set_quota_defaults_from_provider(self):
        from src.core.shared.security.rate_limiter import TenantRateLimitProvider

        provider = TenantRateLimitProvider(
            default_requests=999, default_window_seconds=120, default_burst_multiplier=2.0
        )
        provider.set_quota("t4")
        q = provider.get_quota("t4")
        assert q.requests == 999
        assert q.window_seconds == 120
        assert q.burst_multiplier == 2.0

    def test_remove_quota(self):
        from src.core.shared.security.rate_limiter import TenantRateLimitProvider

        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=100)
        assert provider.remove_quota("t1") is True
        assert provider.remove_quota("t1") is False

    def test_remove_tenant_quota_alias(self):
        from src.core.shared.security.rate_limiter import TenantRateLimitProvider

        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=100)
        assert provider.remove_tenant_quota("t1") is True
        assert provider.remove_tenant_quota("t1") is False

    def test_get_all_tenant_quotas_returns_deep_copy(self):
        from src.core.shared.security.rate_limiter import TenantRateLimitProvider

        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=100)
        provider.set_tenant_quota("t2", requests=200)
        all_quotas = provider.get_all_tenant_quotas()
        assert len(all_quotas) == 2
        assert "t1" in all_quotas
        # Verify it's a copy
        all_quotas["t1"].requests = 9999
        assert provider.get_tenant_quota("t1").requests == 100

    def test_get_constitutional_hash(self):
        from src.core.shared.security.rate_limiter import TenantRateLimitProvider

        provider = TenantRateLimitProvider()
        assert provider.get_constitutional_hash() == "cdd01ef066bc6cf2"

    def test_from_env(self):
        from src.core.shared.security.rate_limiter import TenantRateLimitProvider

        with patch.dict(
            "os.environ",
            {
                "RATE_LIMIT_TENANT_REQUESTS": "2000",
                "RATE_LIMIT_TENANT_WINDOW": "120",
                "RATE_LIMIT_TENANT_BURST": "1.5",
                "RATE_LIMIT_USE_REGISTRY": "true",
            },
            clear=False,
        ):
            provider = TenantRateLimitProvider.from_env()
            assert provider._default_requests == 2000
            assert provider._default_window_seconds == 120
            assert provider._default_burst_multiplier == 1.5
            assert provider._use_registry is True

    def test_set_tenant_quota_disabled(self):
        from src.core.shared.security.rate_limiter import TenantRateLimitProvider

        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=100, enabled=False)
        q = provider.get_tenant_quota("t1")
        assert q.enabled is False


class TestTokenBucket:
    """Test TokenBucket dataclass."""

    def test_initial_state(self):
        from src.core.shared.security.rate_limiter import TokenBucket

        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.tokens == 10
        assert bucket.capacity == 10

    def test_consume_success(self):
        from src.core.shared.security.rate_limiter import TokenBucket

        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(5) is True
        assert bucket.tokens <= 5.1  # allow small refill

    def test_consume_failure(self):
        from src.core.shared.security.rate_limiter import TokenBucket

        bucket = TokenBucket(capacity=2, refill_rate=0.001)
        assert bucket.consume(1) is True
        assert bucket.consume(1) is True
        assert bucket.consume(1) is False

    def test_get_remaining_tokens(self):
        from src.core.shared.security.rate_limiter import TokenBucket

        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        remaining = bucket.get_remaining_tokens()
        assert remaining >= 9.9  # allow small time delta

    def test_get_reset_time_full(self):
        from src.core.shared.security.rate_limiter import TokenBucket

        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.get_reset_time() == 0.0

    def test_get_reset_time_partial(self):
        from src.core.shared.security.rate_limiter import TokenBucket

        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        bucket.tokens = 0
        bucket.last_refill = time.time()  # reset to now so refill is ~0
        reset_time = bucket.get_reset_time()
        assert reset_time > 0

    def test_refill(self):
        from src.core.shared.security.rate_limiter import TokenBucket

        bucket = TokenBucket(capacity=10, refill_rate=10000.0)
        bucket.tokens = 0
        bucket.last_refill = time.time() - 1  # 1 second ago
        bucket.refill()
        assert bucket.tokens == 10  # capped at capacity


class TestSlidingWindowRateLimiter:
    """Test SlidingWindowRateLimiter."""

    async def test_memory_allow(self):
        from src.core.shared.security.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter()
        result = await limiter.is_allowed("test:key", limit=5, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 4

    async def test_memory_deny_after_limit(self):
        from src.core.shared.security.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter()
        for i in range(5):
            result = await limiter.is_allowed("test:deny", limit=5, window_seconds=60)
        # 6th request should be denied
        result = await limiter.is_allowed("test:deny", limit=5, window_seconds=60)
        assert result.allowed is False
        assert result.retry_after is not None
        assert result.retry_after >= 1

    async def test_redis_allowed(self):
        from src.core.shared.security.rate_limiter import SlidingWindowRateLimiter

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 2, True, True])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        limiter = SlidingWindowRateLimiter(redis_client=mock_redis)
        result = await limiter.is_allowed("test:redis", limit=10, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 7  # 10 - (2+1)

    async def test_redis_denied(self):
        from src.core.shared.security.rate_limiter import SlidingWindowRateLimiter

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[0, 10, True, True])  # count=10 >= limit=10
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        mock_redis.zrem = AsyncMock()

        limiter = SlidingWindowRateLimiter(redis_client=mock_redis)
        result = await limiter.is_allowed("test:redis:denied", limit=10, window_seconds=60)
        assert result.allowed is False
        assert result.retry_after == 60

    async def test_redis_fallback_on_connection_error(self):
        from src.core.shared.security.rate_limiter import SlidingWindowRateLimiter

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=ConnectionError("Redis down"))
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=True)
        result = await limiter.is_allowed("test:fallback", limit=10, window_seconds=60)
        assert result.allowed is True  # memory fallback allows first request

    async def test_redis_no_fallback_raises(self):
        from src.core.shared.security.rate_limiter import SlidingWindowRateLimiter

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=ConnectionError("Redis down"))
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=False)
        with pytest.raises(ConnectionError):
            await limiter.is_allowed("test:nofallback", limit=10, window_seconds=60)

    async def test_redis_generic_error_fallback(self):
        """Test that non-builtin exceptions (like redis AuthenticationError) also trigger fallback."""
        from src.core.shared.security.rate_limiter import SlidingWindowRateLimiter

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=RuntimeError("Auth failed"))
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=True)
        result = await limiter.is_allowed("test:auth_err", limit=10, window_seconds=60)
        assert result.allowed is True

    async def test_redis_generic_error_no_fallback_raises(self):
        from src.core.shared.security.rate_limiter import SlidingWindowRateLimiter

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock()
        mock_pipe.zcard = MagicMock()
        mock_pipe.execute_command = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=RuntimeError("Auth failed"))
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=False)
        with pytest.raises(RuntimeError):
            await limiter.is_allowed("test:auth_err_nofb", limit=10, window_seconds=60)

    async def test_memory_metrics_update(self):
        """Test that _check_memory calls update_rate_limit_metrics."""
        from src.core.shared.security.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter()
        with patch(
            "src.core.shared.security.rate_limiter.update_rate_limit_metrics"
        ) as mock_metrics:
            await limiter.is_allowed("scope:ident:endpoint", limit=10, window_seconds=60)
            mock_metrics.assert_called_once()

    async def test_memory_metrics_key_parsing_short_key(self):
        """Test key parsing with short key (fewer than 3 parts)."""
        from src.core.shared.security.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter()
        with patch(
            "src.core.shared.security.rate_limiter.update_rate_limit_metrics"
        ) as mock_metrics:
            await limiter.is_allowed("simplekey", limit=10, window_seconds=60)
            mock_metrics.assert_called_once()
            args = mock_metrics.call_args[0]
            assert args[1] == "simplekey"  # identifier fallback
            assert args[2] == "unknown"  # endpoint fallback

    async def test_memory_metrics_error_swallowed(self):
        """Test that metrics errors are silently swallowed."""
        from src.core.shared.security.rate_limiter import SlidingWindowRateLimiter

        limiter = SlidingWindowRateLimiter()
        with patch(
            "src.core.shared.security.rate_limiter.update_rate_limit_metrics",
            side_effect=RuntimeError("metrics broken"),
        ):
            result = await limiter.is_allowed("test:metrics:err", limit=10, window_seconds=60)
            assert result.allowed is True  # should not crash


class TestRateLimitMiddleware:
    """Test RateLimitMiddleware ASGI middleware."""

    def _make_middleware(self, config=None, tenant_provider=None):
        from src.core.shared.security.rate_limiter import RateLimitConfig, RateLimitMiddleware

        app = AsyncMock()
        cfg = config or RateLimitConfig(enabled=True, rules=[], fail_open=True)
        return RateLimitMiddleware(app=app, config=cfg, tenant_quota_provider=tenant_provider)

    async def test_non_http_passes_through(self):
        mw = self._make_middleware()
        scope = {"type": "websocket", "path": "/ws"}
        receive = AsyncMock()
        send = AsyncMock()
        await mw(scope, receive, send)
        mw.app.assert_awaited_once()

    async def test_disabled_passes_through(self):
        from src.core.shared.security.rate_limiter import RateLimitConfig

        config = RateLimitConfig(enabled=False)
        mw = self._make_middleware(config=config)
        scope = {"type": "http", "path": "/api/test"}
        receive = AsyncMock()
        send = AsyncMock()
        await mw(scope, receive, send)
        mw.app.assert_awaited_once()

    async def test_exempt_path_passes_through(self):
        from src.core.shared.security.rate_limiter import RateLimitConfig

        config = RateLimitConfig(enabled=True, exempt_paths=["/health", "/metrics"])
        mw = self._make_middleware(config=config)
        scope = {"type": "http", "path": "/health"}
        receive = AsyncMock()
        send = AsyncMock()
        await mw(scope, receive, send)
        mw.app.assert_awaited_once()

    def test_is_exempt_path_empty(self):
        from src.core.shared.security.rate_limiter import RateLimitConfig

        config = RateLimitConfig(enabled=True, exempt_paths=[])
        mw = self._make_middleware(config=config)
        assert mw._is_exempt_path("/health") is False

    async def test_ensure_initialized(self):
        mw = self._make_middleware()
        assert mw._initialized is False
        await mw._ensure_initialized()
        assert mw._initialized is True
        assert mw.limiter is not None
        # Second call is no-op
        await mw._ensure_initialized()
        assert mw._initialized is True

    def test_get_tenant_quota_no_provider(self):
        mw = self._make_middleware()
        assert mw._get_tenant_quota("t1") is None

    def test_get_tenant_quota_with_provider(self):
        from src.core.shared.security.rate_limiter import TenantRateLimitProvider

        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=500)
        mw = self._make_middleware(tenant_provider=provider)
        q = mw._get_tenant_quota("t1")
        assert q is not None
        assert q.requests == 500

    def test_get_tenant_quota_provider_error(self):
        provider = MagicMock()
        provider.get_tenant_quota = MagicMock(side_effect=Exception("boom"))
        mw = self._make_middleware(tenant_provider=provider)
        assert mw._get_tenant_quota("t1") is None

    async def test_check_tenant_rate_limit_disabled(self):
        from src.core.shared.security.rate_limiter import RateLimitScope, TenantQuota

        mw = self._make_middleware()
        await mw._ensure_initialized()
        quota = TenantQuota(tenant_id="t1", requests=100, enabled=False)
        request = MagicMock()
        result = await mw._check_tenant_rate_limit(request, "t1", quota)
        assert result.allowed is True
        assert result.scope == RateLimitScope.TENANT

    async def test_check_tenant_rate_limit_enabled(self):
        from src.core.shared.security.rate_limiter import TenantQuota

        mw = self._make_middleware()
        await mw._ensure_initialized()
        quota = TenantQuota(tenant_id="t1", requests=100, enabled=True)
        request = MagicMock()
        result = await mw._check_tenant_rate_limit(request, "t1", quota)
        assert result.allowed is True

    def test_check_rule_match_no_endpoints(self):
        from src.core.shared.security.rate_limiter import RateLimitRule

        mw = self._make_middleware()
        rule = RateLimitRule(requests=10, endpoints=None)
        request = MagicMock()
        request.url.path = "/api/test"
        assert mw._check_rule_match(request, rule) is True

    def test_check_rule_match_with_endpoints(self):
        from src.core.shared.security.rate_limiter import RateLimitRule

        mw = self._make_middleware()
        rule = RateLimitRule(requests=10, endpoints=["/api/"])
        request = MagicMock()
        request.url.path = "/api/test"
        assert mw._check_rule_match(request, rule) is True

        request.url.path = "/other/path"
        assert mw._check_rule_match(request, rule) is False

    def test_build_key(self):
        from src.core.shared.security.rate_limiter import RateLimitRule

        mw = self._make_middleware()
        rule = RateLimitRule(requests=10)
        request = MagicMock()
        request.client = SimpleNamespace(host="1.2.3.4")
        request.state = SimpleNamespace(tenant_id=None, auth_claims=None, user=None)
        key = mw._build_key(request, rule)
        assert "1.2.3.4" in key
        assert "ratelimit:ip" in key

    def test_create_429_response_without_tenant(self):
        from src.core.shared.security.rate_limiter import RateLimitResult, RateLimitScope

        mw = self._make_middleware()
        result = RateLimitResult(
            allowed=False,
            limit=10,
            remaining=0,
            reset_at=9999999,
            retry_after=60,
            scope=RateLimitScope.IP,
        )
        response = mw._create_429_response(result)
        assert response.status_code == 429

    def test_create_429_response_with_tenant(self):
        from src.core.shared.security.rate_limiter import RateLimitResult, RateLimitScope

        mw = self._make_middleware()
        result = RateLimitResult(
            allowed=False,
            limit=10,
            remaining=0,
            reset_at=9999999,
            retry_after=60,
            scope=RateLimitScope.TENANT,
            key="tenant:t1",
        )
        response = mw._create_429_response(result, tenant_id="t1")
        assert response.status_code == 429
        assert response.headers.get("X-Tenant-RateLimit-Limit") == "10"

    def test_get_tenant_id_from_state(self):
        mw = self._make_middleware()
        request = MagicMock()
        request.state.tenant_id = "state-tenant"
        assert mw._get_tenant_id(request) == "state-tenant"

    def test_get_tenant_id_from_auth_claims(self):
        mw = self._make_middleware()
        request = MagicMock(spec=["state", "headers", "url", "client"])
        request.state = MagicMock(spec=["auth_claims"])
        request.state.auth_claims = {"tenant_id": "claims-tenant"}
        assert mw._get_tenant_id(request) == "claims-tenant"

    def test_get_tenant_id_from_user(self):
        mw = self._make_middleware()
        request = MagicMock(spec=["state", "headers", "url", "client"])
        state = MagicMock(spec=["user"])
        state.user = MagicMock(spec=["tenant_id"])
        state.user.tenant_id = "user-tenant"
        request.state = state
        assert mw._get_tenant_id(request) == "user-tenant"

    def test_get_tenant_id_does_not_trust_raw_header(self):
        mw = self._make_middleware()
        request = MagicMock(spec=["state", "headers", "url", "client"])
        request.state = MagicMock(spec=[])  # no tenant_id, auth_claims, or user
        request.headers = {"X-Tenant-ID": "header-tenant"}
        request.url.path = "/api/test"
        request.client.host = "1.2.3.4"
        assert mw._get_tenant_id(request) is None

    def test_get_tenant_id_none(self):
        mw = self._make_middleware()
        request = MagicMock(spec=["state", "headers", "url", "client"])
        request.state = MagicMock(spec=[])
        request.headers = {}
        assert mw._get_tenant_id(request) is None


class TestCreateRateLimitMiddleware:
    """Test create_rate_limit_middleware factory."""

    async def test_allowed_request(self):
        from src.core.shared.security.rate_limiter import create_rate_limit_middleware

        middleware_fn = create_rate_limit_middleware(
            requests_per_minute=100, burst_limit=10, burst_multiplier=1.5
        )
        request = MagicMock()
        request.client.host = "1.2.3.4"
        request.state = MagicMock(spec=[])
        request.url.path = "/api/test"

        call_next = AsyncMock(return_value=MagicMock())
        response = await middleware_fn(request, call_next)
        call_next.assert_awaited_once()

    async def test_rate_limited_request(self):
        from src.core.shared.security.rate_limiter import (
            SlidingWindowRateLimiter,
            create_rate_limit_middleware,
            rate_limiter,
        )

        # Save original state
        orig_windows = dict(rate_limiter.local_windows)

        try:
            middleware_fn = create_rate_limit_middleware(
                requests_per_minute=1, burst_limit=1, burst_multiplier=1.0
            )
            request = MagicMock()
            request.client.host = "rate-test-host"
            request.state = MagicMock(spec=[])
            request.url.path = "/api/rate-test"
            call_next = AsyncMock()

            # Exhaust the per-user limit (capacity=2 -> 1*1.0*2=2)
            for _ in range(5):
                response = await middleware_fn(request, call_next)

            # Eventually should get 429
            # The middleware checks user, ip, endpoint in order
            # We need more requests to exhaust all scopes
            for _ in range(20):
                response = await middleware_fn(request, call_next)

            assert response.status_code == 429
        finally:
            # Cleanup rate limiter state
            keys_to_remove = [
                k for k in rate_limiter.local_windows if "rate-test" in k
            ]
            for k in keys_to_remove:
                rate_limiter.local_windows.pop(k, None)


class TestRateLimitDecorator:
    """Test @rate_limit decorator."""

    async def test_decorator_allows(self):
        from src.core.shared.security.rate_limiter import rate_limit

        @rate_limit(requests_per_minute=100)
        async def my_endpoint(request):
            return {"ok": True}

        request = MagicMock()
        request.client.host = "10.0.0.1"
        request.state = MagicMock(spec=[])
        request.url.path = "/api/decorated"

        result = await my_endpoint(request)
        assert result == {"ok": True}

    async def test_decorator_no_request_passes_through(self):
        from src.core.shared.security.rate_limiter import rate_limit

        @rate_limit(requests_per_minute=100)
        async def my_func(data):
            return data

        result = await my_func("hello")
        assert result == "hello"

    async def test_decorator_request_in_kwargs(self):
        from src.core.shared.security.rate_limiter import rate_limit

        @rate_limit(requests_per_minute=100)
        async def my_endpoint(request=None):
            return {"ok": True}

        request = MagicMock()
        request.client.host = "10.0.0.2"
        request.state = MagicMock(spec=[])
        request.url.path = "/api/kw-test"

        result = await my_endpoint(request=request)
        assert result == {"ok": True}


class TestResolveRateLimitIdentifier:
    """Test _resolve_rate_limit_identifier."""

    def test_custom_key_func(self):
        from src.core.shared.security.rate_limiter import _resolve_rate_limit_identifier

        request = MagicMock()
        result = _resolve_rate_limit_identifier(request, "user", lambda r: "custom-key")
        assert result == "custom-key"

    def test_user_type(self):
        from src.core.shared.security.rate_limiter import _resolve_rate_limit_identifier

        request = MagicMock()
        request.state.user_id = "user-123"
        result = _resolve_rate_limit_identifier(request, "user", None)
        assert result == "user-123"

    def test_user_type_fallback_to_ip(self):
        from src.core.shared.security.rate_limiter import _resolve_rate_limit_identifier

        request = MagicMock(spec=["state", "client"])
        request.state = MagicMock(spec=[])  # no user_id
        request.client.host = "5.6.7.8"
        result = _resolve_rate_limit_identifier(request, "user", None)
        assert result == "5.6.7.8"

    def test_ip_type(self):
        from src.core.shared.security.rate_limiter import _resolve_rate_limit_identifier

        request = MagicMock()
        request.client.host = "9.8.7.6"
        result = _resolve_rate_limit_identifier(request, "ip", None)
        assert result == "9.8.7.6"

    def test_ip_type_no_client(self):
        from src.core.shared.security.rate_limiter import _resolve_rate_limit_identifier

        request = MagicMock()
        request.client = None
        result = _resolve_rate_limit_identifier(request, "ip", None)
        assert result == "unknown"

    def test_endpoint_type(self):
        from src.core.shared.security.rate_limiter import _resolve_rate_limit_identifier

        request = MagicMock()
        request.url.path = "/api/endpoint"
        result = _resolve_rate_limit_identifier(request, "endpoint", None)
        assert result == "/api/endpoint"

    def test_global_type(self):
        from src.core.shared.security.rate_limiter import _resolve_rate_limit_identifier

        request = MagicMock()
        result = _resolve_rate_limit_identifier(request, "global", None)
        assert result == "global"

    def test_unknown_type(self):
        from src.core.shared.security.rate_limiter import _resolve_rate_limit_identifier

        request = MagicMock()
        result = _resolve_rate_limit_identifier(request, "banana", None)
        assert result == "global"


class TestExtractRequestFromCall:
    """Test _extract_request_from_call."""

    def test_request_in_args(self):
        from fastapi import Request
        from src.core.shared.security.rate_limiter import _extract_request_from_call

        req = MagicMock(spec=Request)
        result = _extract_request_from_call((req,), {})
        assert result is req

    def test_request_in_kwargs(self):
        from fastapi import Request
        from src.core.shared.security.rate_limiter import _extract_request_from_call

        req = MagicMock(spec=Request)
        result = _extract_request_from_call((), {"request": req})
        assert result is req

    def test_no_request(self):
        from src.core.shared.security.rate_limiter import _extract_request_from_call

        result = _extract_request_from_call(("hello",), {"data": 123})
        assert result is None


class TestAddRateLimitHeaders:
    """Test add_rate_limit_headers middleware factory."""

    async def test_adds_headers_when_missing(self):
        from src.core.shared.security.rate_limiter import add_rate_limit_headers

        middleware_fn = add_rate_limit_headers()

        request = MagicMock()
        response = MagicMock()
        response.headers = {}
        call_next = AsyncMock(return_value=response)

        result = await middleware_fn(request, call_next)
        assert "X-RateLimit-Limit" in result.headers
        assert result.headers["X-RateLimit-Limit"] == "60"

    async def test_skips_when_headers_present(self):
        from src.core.shared.security.rate_limiter import add_rate_limit_headers

        middleware_fn = add_rate_limit_headers()

        request = MagicMock()
        response = MagicMock()
        response.headers = {"X-RateLimit-Remaining": "42"}
        call_next = AsyncMock(return_value=response)

        result = await middleware_fn(request, call_next)
        assert result.headers["X-RateLimit-Remaining"] == "42"


class TestConfigureRateLimits:
    """Test configure_rate_limits global config."""

    def test_configure_with_redis(self):
        from src.core.shared.security.rate_limiter import configure_rate_limits, rate_limiter

        old_client = rate_limiter.redis_client
        old_rpm = getattr(rate_limiter, "default_rpm", None)
        old_burst = getattr(rate_limiter, "default_burst", None)
        try:
            mock_redis = MagicMock()
            configure_rate_limits(redis_client=mock_redis, default_requests_per_minute=120)
            assert rate_limiter.redis_client is mock_redis
            assert rate_limiter.default_rpm == 120
        finally:
            rate_limiter.redis_client = old_client
            if old_rpm is not None:
                rate_limiter.default_rpm = old_rpm
            if old_burst is not None:
                rate_limiter.default_burst = old_burst

    def test_configure_without_redis(self):
        from src.core.shared.security.rate_limiter import configure_rate_limits, rate_limiter

        old_burst = getattr(rate_limiter, "default_burst", None)
        try:
            configure_rate_limits(default_burst_limit=20)
            assert rate_limiter.default_burst == 20
        finally:
            if old_burst is not None:
                rate_limiter.default_burst = old_burst


class TestUpdateRateLimitMetrics:
    """Test update_rate_limit_metrics."""

    def test_allowed_request(self):
        from src.core.shared.security.rate_limiter import update_rate_limit_metrics

        # Should not raise
        update_rate_limit_metrics("ip", "1.2.3.4", "/api/test", True)

    def test_denied_request(self):
        from src.core.shared.security.rate_limiter import update_rate_limit_metrics

        # Should increment exceeded counter
        update_rate_limit_metrics("ip", "1.2.3.4", "/api/test", False)


class TestRateLimitEnums:
    """Test enum values."""

    def test_scope_values(self):
        from src.core.shared.security.rate_limiter import RateLimitScope

        assert RateLimitScope.USER == "user"
        assert RateLimitScope.IP == "ip"
        assert RateLimitScope.ENDPOINT == "endpoint"
        assert RateLimitScope.GLOBAL == "global"
        assert RateLimitScope.TENANT == "tenant"

    def test_algorithm_values(self):
        from src.core.shared.security.rate_limiter import RateLimitAlgorithm

        assert RateLimitAlgorithm.TOKEN_BUCKET == "token_bucket"
        assert RateLimitAlgorithm.SLIDING_WINDOW == "sliding_window"
        assert RateLimitAlgorithm.FIXED_WINDOW == "fixed_window"


# =============================================================================
# Module 2: src.core.shared.config.security
# =============================================================================


class TestSecuritySettings:
    """Test SecuritySettings (pydantic-settings or dataclass fallback)."""

    def test_defaults(self):
        from src.core.shared.config.security import SecuritySettings

        s = SecuritySettings()
        assert s.jwt_public_key == "SYSTEM_PUBLIC_KEY_PLACEHOLDER"

    def test_with_env_vars(self):
        from src.core.shared.config.security import SecuritySettings

        with patch.dict("os.environ", {"JWT_PUBLIC_KEY": "test-key"}, clear=False):
            s = SecuritySettings()
            assert s.jwt_public_key == "test-key"

    def test_placeholder_validation(self):
        from src.core.shared.config.security import HAS_PYDANTIC_SETTINGS, SecuritySettings

        if HAS_PYDANTIC_SETTINGS:
            with pytest.raises(Exception):
                with patch.dict("os.environ", {"JWT_SECRET": "PLACEHOLDER"}, clear=False):
                    SecuritySettings()


class TestOPASettings:
    """Test OPASettings."""

    def test_defaults(self):
        from src.core.shared.config.security import OPASettings

        s = OPASettings()
        assert s.url == "http://localhost:8181"
        assert s.fail_closed is True

    def test_with_custom_values(self):
        from src.core.shared.config.security import OPASettings

        with patch.dict(
            "os.environ",
            {"OPA_URL": "http://opa:8181", "OPA_MODE": "embedded"},
            clear=False,
        ):
            s = OPASettings()
            assert s.url == "http://opa:8181"
            assert s.mode == "embedded"

    def test_ssl_fields(self):
        from src.core.shared.config.security import OPASettings

        with patch.dict(
            "os.environ",
            {
                "OPA_SSL_VERIFY": "false",
                "OPA_SSL_CERT": "/cert.pem",
                "OPA_SSL_KEY": "/key.pem",
            },
            clear=False,
        ):
            s = OPASettings()
            assert s.ssl_verify is False
            assert s.ssl_cert == "/cert.pem"


class TestAuditSettings:
    """Test AuditSettings."""

    def test_defaults(self):
        from src.core.shared.config.security import AuditSettings

        s = AuditSettings()
        assert s.url == "http://localhost:8001"

    def test_custom_url(self):
        from src.core.shared.config.security import AuditSettings

        with patch.dict("os.environ", {"AUDIT_SERVICE_URL": "http://audit:9000"}, clear=False):
            s = AuditSettings()
            assert s.url == "http://audit:9000"


class TestVaultSettings:
    """Test VaultSettings."""

    def test_defaults(self):
        from src.core.shared.config.security import VaultSettings

        s = VaultSettings()
        assert s.address == "http://127.0.0.1:8200"
        assert s.token is None
        assert s.kv_version == 2
        assert s.timeout == 30.0
        assert s.verify_tls is True
        assert s.transit_mount == "transit"
        assert s.kv_mount == "secret"

    def test_with_token(self):
        from src.core.shared.config.security import VaultSettings

        with patch.dict("os.environ", {"VAULT_TOKEN": "hvs.test-token"}, clear=False):
            s = VaultSettings()
            assert s.token is not None
            assert s.token.get_secret_value() == "hvs.test-token"

    def test_all_optional_fields(self):
        from src.core.shared.config.security import VaultSettings

        with patch.dict(
            "os.environ",
            {
                "VAULT_NAMESPACE": "admin",
                "VAULT_CACERT": "/ca.pem",
                "VAULT_CLIENT_CERT": "/client.pem",
                "VAULT_CLIENT_KEY": "/client-key.pem",
                "VAULT_KV_VERSION": "1",
                "VAULT_TIMEOUT": "10.0",
                "VAULT_VERIFY_TLS": "false",
                "VAULT_TRANSIT_MOUNT": "my-transit",
                "VAULT_KV_MOUNT": "my-secret",
            },
            clear=False,
        ):
            s = VaultSettings()
            assert s.namespace == "admin"
            assert s.ca_cert == "/ca.pem"
            assert s.client_cert == "/client.pem"
            assert s.client_key == "/client-key.pem"
            assert s.kv_version == 1
            assert s.timeout == 10.0
            assert s.verify_tls is False
            assert s.transit_mount == "my-transit"
            assert s.kv_mount == "my-secret"


class TestSSOSettings:
    """Test SSOSettings."""

    def test_defaults(self, monkeypatch: pytest.MonkeyPatch):
        from src.core.shared.config.security import SSOSettings

        for env_var in (
            "SSO_ENABLED",
            "OIDC_ENABLED",
            "OIDC_USE_PKCE",
            "SAML_ENABLED",
            "SAML_SIGN_REQUESTS",
            "SAML_WANT_ASSERTIONS_SIGNED",
            "SAML_WANT_ASSERTIONS_ENCRYPTED",
            "SSO_AUTO_PROVISION",
            "SSO_DEFAULT_ROLE",
            "WORKOS_ENABLED",
        ):
            monkeypatch.delenv(env_var, raising=False)

        s = SSOSettings()
        assert s.enabled is True
        assert s.session_lifetime_seconds == 3600
        assert s.oidc_enabled is True
        assert s.oidc_use_pkce is True
        assert s.saml_enabled is True
        assert s.saml_sign_requests is True
        assert s.saml_want_assertions_signed is True
        assert s.saml_want_assertions_encrypted is False
        assert s.auto_provision_users is True
        assert s.default_role_on_provision == "viewer"
        assert s.workos_enabled is False

    def test_oidc_fields(self):
        from src.core.shared.config.security import SSOSettings

        with patch.dict(
            "os.environ",
            {
                "OIDC_CLIENT_ID": "my-client",
                "OIDC_ISSUER_URL": "https://issuer.example.com",
                "OIDC_CLIENT_SECRET": "oidc-secret-val",
                "OIDC_SCOPES": '["openid","email"]',
                "OIDC_USE_PKCE": "false",
                "OIDC_ENABLED": "false",
            },
            clear=False,
        ):
            s = SSOSettings()
            assert s.oidc_client_id == "my-client"
            assert s.oidc_issuer_url == "https://issuer.example.com"
            assert s.oidc_enabled is False

    def test_saml_fields(self):
        from src.core.shared.config.security import SSOSettings

        with patch.dict(
            "os.environ",
            {
                "SAML_ENTITY_ID": "urn:example:sp",
                "SAML_IDP_SSO_URL": "https://idp.example.com/sso",
                "SAML_IDP_SLO_URL": "https://idp.example.com/slo",
                "SAML_IDP_METADATA_URL": "https://idp.example.com/metadata",
                "SAML_IDP_CERTIFICATE": "CERT_DATA",
                "SAML_SP_CERTIFICATE": "SP_CERT",
                "SAML_SP_PRIVATE_KEY": "SP_KEY_DATA",
                "SAML_SIGN_REQUESTS": "false",
                "SAML_WANT_ASSERTIONS_SIGNED": "false",
                "SAML_WANT_ASSERTIONS_ENCRYPTED": "true",
                "SAML_ENABLED": "false",
            },
            clear=False,
        ):
            s = SSOSettings()
            assert s.saml_entity_id == "urn:example:sp"
            assert s.saml_idp_sso_url == "https://idp.example.com/sso"
            assert s.saml_idp_slo_url == "https://idp.example.com/slo"
            assert s.saml_sp_private_key is not None
            assert s.saml_enabled is False

    def test_workos_fields(self):
        from src.core.shared.config.security import SSOSettings

        with patch.dict(
            "os.environ",
            {
                "WORKOS_ENABLED": "true",
                "WORKOS_CLIENT_ID": "wos_client",
                "WORKOS_API_BASE_URL": "https://custom.workos.com",
                "WORKOS_API_KEY": "wos_api_key",
                "WORKOS_WEBHOOK_SECRET": "wos_webhook_sec",
                "WORKOS_PORTAL_DEFAULT_INTENT": "dsync",
                "WORKOS_PORTAL_RETURN_URL": "https://app.example.com/return",
                "WORKOS_PORTAL_SUCCESS_URL": "https://app.example.com/success",
                "WORKOS_WEBHOOK_DEDUPE_TTL_SECONDS": "3600",
                "WORKOS_WEBHOOK_FAIL_CLOSED": "false",
            },
            clear=False,
        ):
            s = SSOSettings()
            assert s.workos_enabled is True
            assert s.workos_client_id == "wos_client"
            assert s.workos_portal_default_intent == "dsync"
            assert s.workos_api_key is not None
            assert s.workos_webhook_secret is not None

    def test_allowed_domains(self):
        from src.core.shared.config.security import HAS_PYDANTIC_SETTINGS, SSOSettings

        if HAS_PYDANTIC_SETTINGS:
            # pydantic-settings expects JSON for list fields
            with patch.dict(
                "os.environ",
                {"SSO_ALLOWED_DOMAINS": '["example.com","test.com"]'},
                clear=False,
            ):
                s = SSOSettings()
                assert s.allowed_domains is not None
                assert "example.com" in s.allowed_domains
        else:
            with patch.dict(
                "os.environ",
                {"SSO_ALLOWED_DOMAINS": "example.com,test.com"},
                clear=False,
            ):
                s = SSOSettings()
                assert s.allowed_domains is not None
                assert "example.com" in s.allowed_domains

    def test_provisioning_and_session(self):
        from src.core.shared.config.security import SSOSettings

        with patch.dict(
            "os.environ",
            {
                "SSO_ENABLED": "false",
                "SSO_SESSION_LIFETIME": "7200",
                "SSO_AUTO_PROVISION": "false",
                "SSO_DEFAULT_ROLE": "admin",
            },
            clear=False,
        ):
            s = SSOSettings()
            assert s.enabled is False
            assert s.session_lifetime_seconds == 7200
            assert s.auto_provision_users is False
            assert s.default_role_on_provision == "admin"


class TestSecuritySettingsDataclassFallback:
    """Test the dataclass fallback branch explicitly for coverage.

    These tests exercise the else branch by constructing settings from env vars.
    """

    def test_security_settings_with_api_key_env(self):
        from src.core.shared.config.security import HAS_PYDANTIC_SETTINGS

        if not HAS_PYDANTIC_SETTINGS:
            with patch.dict("os.environ", {"API_KEY_INTERNAL": "test-key-123"}, clear=False):
                from src.core.shared.config.security import SecuritySettings

                s = SecuritySettings()
                assert s.api_key_internal is not None

    def test_security_settings_cors_origins(self):
        from src.core.shared.config.security import HAS_PYDANTIC_SETTINGS

        if not HAS_PYDANTIC_SETTINGS:
            with patch.dict("os.environ", {"CORS_ORIGINS": "http://a.com,http://b.com"}, clear=False):
                from src.core.shared.config.security import SecuritySettings

                s = SecuritySettings()
                assert len(s.cors_origins) == 2


# =============================================================================
# Module 3: src.core.shared.config.governance
# =============================================================================


class TestMACISettings:
    """Test MACISettings."""

    def test_defaults(self):
        from src.core.shared.config.governance import MACISettings

        s = MACISettings()
        assert s.strict_mode is True
        assert s.default_role is None
        assert s.config_path is None

    def test_custom_values(self):
        from src.core.shared.config.governance import MACISettings

        with patch.dict(
            "os.environ",
            {
                "MACI_STRICT_MODE": "false",
                "MACI_DEFAULT_ROLE": "validator",
                "MACI_CONFIG_PATH": "/etc/maci",
            },
            clear=False,
        ):
            s = MACISettings()
            assert s.strict_mode is False
            assert s.default_role == "validator"
            assert s.config_path == "/etc/maci"


class TestVotingSettings:
    """Test VotingSettings."""

    def test_defaults(self):
        from src.core.shared.config.governance import VotingSettings

        s = VotingSettings()
        assert s.default_timeout_seconds == 30
        assert s.vote_topic_pattern == "acgs.tenant.{tenant_id}.votes"
        assert s.audit_topic_pattern == "acgs.tenant.{tenant_id}.audit.votes"
        assert s.redis_election_prefix == "election:"
        assert s.enable_weighted_voting is True
        assert s.signature_algorithm == "HMAC-SHA256"
        assert s.audit_signature_key is None
        assert s.timeout_check_interval_seconds == 5

    def test_custom_values(self):
        from src.core.shared.config.governance import VotingSettings

        with patch.dict(
            "os.environ",
            {
                "VOTING_DEFAULT_TIMEOUT_SECONDS": "60",
                "VOTING_VOTE_TOPIC_PATTERN": "custom.{tenant_id}.votes",
                "VOTING_AUDIT_TOPIC_PATTERN": "custom.{tenant_id}.audit",
                "VOTING_REDIS_ELECTION_PREFIX": "vote:",
                "VOTING_ENABLE_WEIGHTED": "false",
                "VOTING_SIGNATURE_ALGORITHM": "SHA-512",
                "AUDIT_SIGNATURE_KEY": "secret-key",
                "VOTING_TIMEOUT_CHECK_INTERVAL": "10",
            },
            clear=False,
        ):
            s = VotingSettings()
            assert s.default_timeout_seconds == 60
            assert s.enable_weighted_voting is False
            assert s.audit_signature_key is not None
            assert s.vote_topic_pattern == "custom.{tenant_id}.votes"
            assert s.redis_election_prefix == "vote:"
            assert s.signature_algorithm == "SHA-512"
            assert s.timeout_check_interval_seconds == 10


class TestCircuitBreakerSettings:
    """Test CircuitBreakerSettings."""

    def test_defaults(self):
        from src.core.shared.config.governance import CircuitBreakerSettings

        s = CircuitBreakerSettings()
        assert s.default_failure_threshold == 5
        assert s.default_timeout_seconds == 30.0
        assert s.default_half_open_requests == 3
        assert s.policy_registry_failure_threshold == 3
        assert s.policy_registry_timeout_seconds == 10.0
        assert s.policy_registry_fallback_ttl_seconds == 300
        assert s.opa_evaluator_failure_threshold == 5
        assert s.opa_evaluator_timeout_seconds == 5.0
        assert s.blockchain_anchor_failure_threshold == 10
        assert s.blockchain_anchor_timeout_seconds == 60.0
        assert s.blockchain_anchor_max_queue_size == 10000
        assert s.blockchain_anchor_retry_interval_seconds == 300
        assert s.redis_cache_failure_threshold == 3
        assert s.redis_cache_timeout_seconds == 1.0
        assert s.kafka_producer_failure_threshold == 5
        assert s.kafka_producer_timeout_seconds == 30.0
        assert s.kafka_producer_max_queue_size == 10000
        assert s.audit_service_failure_threshold == 5
        assert s.audit_service_timeout_seconds == 30.0
        assert s.audit_service_max_queue_size == 5000
        assert s.deliberation_layer_failure_threshold == 7
        assert s.deliberation_layer_timeout_seconds == 45.0
        assert s.health_check_enabled is True
        assert s.metrics_enabled is True

    def test_custom_values(self):
        from src.core.shared.config.governance import CircuitBreakerSettings

        with patch.dict(
            "os.environ",
            {
                "CB_DEFAULT_FAILURE_THRESHOLD": "10",
                "CB_DEFAULT_TIMEOUT_SECONDS": "60.0",
                "CB_DEFAULT_HALF_OPEN_REQUESTS": "5",
                "CB_POLICY_REGISTRY_FAILURE_THRESHOLD": "5",
                "CB_POLICY_REGISTRY_TIMEOUT_SECONDS": "20.0",
                "CB_POLICY_REGISTRY_FALLBACK_TTL": "600",
                "CB_OPA_EVALUATOR_FAILURE_THRESHOLD": "3",
                "CB_OPA_EVALUATOR_TIMEOUT_SECONDS": "10.0",
                "CB_BLOCKCHAIN_ANCHOR_FAILURE_THRESHOLD": "20",
                "CB_BLOCKCHAIN_ANCHOR_TIMEOUT_SECONDS": "120.0",
                "CB_BLOCKCHAIN_ANCHOR_MAX_QUEUE_SIZE": "20000",
                "CB_BLOCKCHAIN_ANCHOR_RETRY_INTERVAL": "600",
                "CB_REDIS_CACHE_FAILURE_THRESHOLD": "5",
                "CB_REDIS_CACHE_TIMEOUT_SECONDS": "2.0",
                "CB_KAFKA_PRODUCER_FAILURE_THRESHOLD": "10",
                "CB_KAFKA_PRODUCER_TIMEOUT_SECONDS": "60.0",
                "CB_KAFKA_PRODUCER_MAX_QUEUE_SIZE": "20000",
                "CB_AUDIT_SERVICE_FAILURE_THRESHOLD": "8",
                "CB_AUDIT_SERVICE_TIMEOUT_SECONDS": "60.0",
                "CB_AUDIT_SERVICE_MAX_QUEUE_SIZE": "10000",
                "CB_DELIBERATION_LAYER_FAILURE_THRESHOLD": "12",
                "CB_DELIBERATION_LAYER_TIMEOUT_SECONDS": "90.0",
                "CB_HEALTH_CHECK_ENABLED": "false",
                "CB_METRICS_ENABLED": "false",
            },
            clear=False,
        ):
            s = CircuitBreakerSettings()
            assert s.default_failure_threshold == 10
            assert s.default_timeout_seconds == 60.0
            assert s.default_half_open_requests == 5
            assert s.policy_registry_failure_threshold == 5
            assert s.policy_registry_timeout_seconds == 20.0
            assert s.policy_registry_fallback_ttl_seconds == 600
            assert s.blockchain_anchor_failure_threshold == 20
            assert s.blockchain_anchor_timeout_seconds == 120.0
            assert s.blockchain_anchor_max_queue_size == 20000
            assert s.blockchain_anchor_retry_interval_seconds == 600
            assert s.redis_cache_failure_threshold == 5
            assert s.redis_cache_timeout_seconds == 2.0
            assert s.kafka_producer_failure_threshold == 10
            assert s.kafka_producer_timeout_seconds == 60.0
            assert s.kafka_producer_max_queue_size == 20000
            assert s.audit_service_failure_threshold == 8
            assert s.audit_service_timeout_seconds == 60.0
            assert s.audit_service_max_queue_size == 10000
            assert s.deliberation_layer_failure_threshold == 12
            assert s.deliberation_layer_timeout_seconds == 90.0
            assert s.health_check_enabled is False
            assert s.metrics_enabled is False


class TestHasPydanticSettings:
    """Test the HAS_PYDANTIC_SETTINGS flag is consistent."""

    def test_security_has_flag(self):
        from src.core.shared.config.security import HAS_PYDANTIC_SETTINGS

        assert isinstance(HAS_PYDANTIC_SETTINGS, bool)

    def test_governance_has_flag(self):
        from src.core.shared.config.governance import HAS_PYDANTIC_SETTINGS

        assert isinstance(HAS_PYDANTIC_SETTINGS, bool)

    def test_flags_are_consistent(self):
        from src.core.shared.config.governance import HAS_PYDANTIC_SETTINGS as gov_flag
        from src.core.shared.config.security import HAS_PYDANTIC_SETTINGS as sec_flag

        assert gov_flag == sec_flag
