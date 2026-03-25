"""
Comprehensive tests for src.core.shared.security modules (batch B).

Covers:
- rate_limiter.py
- token_revocation.py
- url_file_validator.py
- retention_policy.py
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from src.core.shared.security.data_classification import (
    DataClassificationTier,
    DisposalMethod,
    RetentionPolicy,
)

# ---------------------------------------------------------------------------
# rate_limiter imports
# ---------------------------------------------------------------------------
from src.core.shared.security.rate_limiter import (
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
    _extract_request_from_call,
    _module_available,
    _parse_bool_env,
    _resolve_rate_limit_identifier,
    configure_rate_limits,
    rate_limit,
    update_rate_limit_metrics,
)

# ---------------------------------------------------------------------------
# retention_policy imports
# ---------------------------------------------------------------------------
from src.core.shared.security.retention_policy import (
    AnonymizeHandler,
    ArchiveHandler,
    DeleteHandler,
    DisposalResult,
    InMemoryRetentionStorage,
    PseudonymizeHandler,
    RetentionAction,
    RetentionActionType,
    RetentionPolicyEngine,
    RetentionRecord,
    RetentionStatus,
    get_retention_engine,
    reset_retention_engine,
)

# ---------------------------------------------------------------------------
# token_revocation imports
# ---------------------------------------------------------------------------
from src.core.shared.security.token_revocation import (
    TokenRevocationService,
    create_token_revocation_service,
)
from src.core.shared.security.token_revocation import (
    _parse_bool_env as tr_parse_bool_env,
)

# ---------------------------------------------------------------------------
# url_file_validator imports
# ---------------------------------------------------------------------------
from src.core.shared.security.url_file_validator import (
    FileType,
    FileValidationConfig,
    FileValidator,
    SSRFProtectionConfig,
    URLValidator,
    get_file_validator,
    get_url_validator,
    reset_file_validator,
    reset_url_validator,
    validate_file_content,
    validate_url,
)

# ============================================================================
# rate_limiter.py tests
# ============================================================================


class TestParseBoolEnv:
    def test_none_returns_none(self):
        assert _parse_bool_env(None) is None

    def test_true_variants(self):
        for val in ("true", "True", "TRUE", "1", "yes", "on", " True "):
            assert _parse_bool_env(val) is True

    def test_false_variants(self):
        for val in ("false", "False", "FALSE", "0", "no", "off", " false "):
            assert _parse_bool_env(val) is False

    def test_invalid_returns_none(self):
        assert _parse_bool_env("maybe") is None
        assert _parse_bool_env("") is None


class TestModuleAvailable:
    def test_existing_module(self):
        assert _module_available("os") is True

    def test_nonexistent_module(self):
        assert _module_available("nonexistent_module_xyz_12345") is False


class TestRateLimitRule:
    def test_defaults(self):
        rule = RateLimitRule(requests=100)
        assert rule.window_seconds == 60
        assert rule.scope == RateLimitScope.IP
        assert rule.endpoints is None
        assert rule.burst_multiplier == 1.5
        assert rule.algorithm == RateLimitAlgorithm.SLIDING_WINDOW

    def test_limit_alias(self):
        rule = RateLimitRule(requests=42)
        assert rule.limit == 42

    def test_burst_limit(self):
        rule = RateLimitRule(requests=100, burst_multiplier=2.0)
        assert rule.burst_limit == 200

    def test_key_prefix(self):
        rule = RateLimitRule(requests=10, scope=RateLimitScope.TENANT)
        assert rule.key_prefix == "ratelimit:tenant"


class TestRateLimitResult:
    def test_to_headers_allowed(self):
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=50,
            reset_at=1700000000,
            scope=RateLimitScope.IP,
        )
        headers = result.to_headers()
        assert headers["X-RateLimit-Limit"] == "100"
        assert headers["X-RateLimit-Remaining"] == "50"
        assert headers["X-RateLimit-Reset"] == "1700000000"
        assert headers["X-RateLimit-Scope"] == "ip"
        assert "Retry-After" not in headers

    def test_to_headers_blocked_with_retry_after(self):
        result = RateLimitResult(
            allowed=False,
            limit=100,
            remaining=-5,
            reset_at=1700000000,
            retry_after=30,
        )
        headers = result.to_headers()
        assert headers["X-RateLimit-Remaining"] == "0"
        assert headers["Retry-After"] == "30"


class TestRateLimitConfig:
    @patch.dict("os.environ", {
        "RATE_LIMIT_ENABLED": "true",
        "RATE_LIMIT_REQUESTS_PER_MINUTE": "120",
        "RATE_LIMIT_BURST_LIMIT": "20",
    }, clear=False)
    def test_from_env_enabled(self):
        config = RateLimitConfig.from_env()
        assert config.enabled is True
        assert len(config.rules) == 1
        assert config.rules[0].requests == 120

    @patch.dict("os.environ", {
        "RATE_LIMIT_ENABLED": "false",
    }, clear=False)
    def test_from_env_disabled(self):
        config = RateLimitConfig.from_env()
        assert config.enabled is False
        assert len(config.rules) == 0

    @patch.dict("os.environ", {
        "RATE_LIMIT_ENABLED": "true",
        "RATE_LIMIT_FAIL_OPEN": "true",
    }, clear=False)
    def test_from_env_fail_open_explicit(self):
        config = RateLimitConfig.from_env()
        assert config.fail_open is True

    @patch.dict("os.environ", {
        "RATE_LIMIT_ENABLED": "true",
        "RATE_LIMIT_REQUESTS_PER_MINUTE": "0",
        "RATE_LIMIT_BURST_LIMIT": "5",
    }, clear=False)
    def test_from_env_zero_rpm(self):
        config = RateLimitConfig.from_env()
        assert config.enabled is True
        assert config.rules[0].burst_multiplier == 1.5

    def test_exempt_paths_default(self):
        config = RateLimitConfig()
        assert "/health" in config.exempt_paths


class TestTenantQuota:
    def test_effective_limit(self):
        quota = TenantQuota(tenant_id="t1", requests=100, burst_multiplier=2.0)
        assert quota.effective_limit == 200

    def test_to_rule(self):
        quota = TenantQuota(tenant_id="t1", requests=50, window_seconds=30)
        rule = quota.to_rule()
        assert rule.requests == 50
        assert rule.window_seconds == 30
        assert rule.scope == RateLimitScope.TENANT


class TestTenantRateLimitProvider:
    def test_get_tenant_quota_default(self):
        provider = TenantRateLimitProvider(default_requests=500)
        quota = provider.get_tenant_quota("unknown")
        assert quota.requests == 500
        assert quota.tenant_id == "unknown"

    def test_set_and_get_tenant_quota(self):
        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=200, window_seconds=30)
        quota = provider.get_tenant_quota("t1")
        assert quota.requests == 200
        assert quota.window_seconds == 30

    def test_get_quota_alias(self):
        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=100)
        assert provider.get_quota("t1").requests == 100

    def test_set_quota_with_object(self):
        provider = TenantRateLimitProvider()
        quota = TenantQuota(tenant_id="t1", requests=999)
        provider.set_quota("t1", quota=quota)
        assert provider.get_tenant_quota("t1").requests == 999

    def test_set_quota_with_params(self):
        provider = TenantRateLimitProvider()
        provider.set_quota("t1", requests=123, window_seconds=10)
        assert provider.get_tenant_quota("t1").requests == 123

    def test_remove_quota_existing(self):
        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=100)
        assert provider.remove_quota("t1") is True
        assert provider.remove_quota("t1") is False

    def test_remove_tenant_quota_alias(self):
        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=100)
        assert provider.remove_tenant_quota("t1") is True

    def test_get_all_tenant_quotas_deep_copy(self):
        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=100)
        all_quotas = provider.get_all_tenant_quotas()
        assert "t1" in all_quotas
        # Mutating returned dict should not affect internal state
        all_quotas["t1"].requests = 9999
        assert provider.get_tenant_quota("t1").requests == 100

    def test_get_constitutional_hash(self):
        provider = TenantRateLimitProvider()
        assert provider.get_constitutional_hash() == "608508a9bd224290"

    @patch.dict("os.environ", {
        "RATE_LIMIT_TENANT_REQUESTS": "2000",
        "RATE_LIMIT_TENANT_WINDOW": "120",
        "RATE_LIMIT_TENANT_BURST": "2.0",
        "RATE_LIMIT_USE_REGISTRY": "true",
    }, clear=False)
    def test_from_env(self):
        provider = TenantRateLimitProvider.from_env()
        assert provider._default_requests == 2000
        assert provider._default_window_seconds == 120
        assert provider._default_burst_multiplier == 2.0
        assert provider._use_registry is True


class TestTokenBucket:
    def test_initial_capacity(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.tokens == 10

    def test_consume_success(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.consume(5) is True
        assert bucket.get_remaining_tokens() >= 5  # might have refilled slightly

    def test_consume_failure(self):
        bucket = TokenBucket(capacity=2, refill_rate=0.001)
        assert bucket.consume(2) is True
        assert bucket.consume(1) is False

    def test_get_reset_time_full(self):
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        assert bucket.get_reset_time() == 0.0

    def test_get_reset_time_partial(self):
        bucket = TokenBucket(capacity=10, refill_rate=100.0)
        bucket.consume(10)
        reset_time = bucket.get_reset_time()
        assert reset_time >= 0.0


class TestSlidingWindowRateLimiter:
    @pytest.mark.asyncio
    async def test_memory_allow(self):
        limiter = SlidingWindowRateLimiter()
        result = await limiter.is_allowed("test-key", limit=5, window_seconds=60)
        assert result.allowed is True
        assert result.remaining == 4

    @pytest.mark.asyncio
    async def test_memory_block_after_limit(self):
        limiter = SlidingWindowRateLimiter()
        for _ in range(5):
            await limiter.is_allowed("test-key", limit=5, window_seconds=60)
        result = await limiter.is_allowed("test-key", limit=5, window_seconds=60)
        assert result.allowed is False
        assert result.retry_after is not None
        assert result.retry_after >= 1

    def _make_redis_mock(self, execute_return=None, execute_side_effect=None):
        """Create a properly structured Redis mock for pipeline usage."""
        mock_redis = AsyncMock()
        mock_pipe = MagicMock()
        # pipeline() is called without await, so it must be a sync method
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        # Pipeline chain methods are sync
        mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
        mock_pipe.zcard = MagicMock(return_value=mock_pipe)
        mock_pipe.execute_command = MagicMock(return_value=mock_pipe)
        mock_pipe.expire = MagicMock(return_value=mock_pipe)
        # execute() is awaited
        mock_pipe.execute = AsyncMock(
            return_value=execute_return,
            side_effect=execute_side_effect,
        )
        return mock_redis, mock_pipe

    @pytest.mark.asyncio
    async def test_redis_allow(self):
        mock_redis, _mock_pipe = self._make_redis_mock(execute_return=[0, 2, True, True])
        limiter = SlidingWindowRateLimiter(redis_client=mock_redis)
        result = await limiter.is_allowed("key", limit=10, window_seconds=60)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_redis_block(self):
        mock_redis, _mock_pipe = self._make_redis_mock(execute_return=[0, 10, True, True])
        limiter = SlidingWindowRateLimiter(redis_client=mock_redis)
        result = await limiter.is_allowed("key", limit=10, window_seconds=60)
        assert result.allowed is False
        mock_redis.zrem.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_fallback_to_memory(self):
        mock_redis, _ = self._make_redis_mock(execute_side_effect=ConnectionError("Redis down"))
        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=True)
        result = await limiter.is_allowed("key", limit=10, window_seconds=60)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_redis_no_fallback_raises(self):
        mock_redis, _ = self._make_redis_mock(execute_side_effect=ConnectionError("Redis down"))
        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=False)
        with pytest.raises(ConnectionError):
            await limiter.is_allowed("key", limit=10, window_seconds=60)

    @pytest.mark.asyncio
    async def test_redis_generic_error_fallback(self):
        mock_redis, _ = self._make_redis_mock(execute_side_effect=RuntimeError("auth error"))
        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=True)
        result = await limiter.is_allowed("key", limit=10, window_seconds=60)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_redis_generic_error_no_fallback(self):
        mock_redis, _ = self._make_redis_mock(execute_side_effect=RuntimeError("auth error"))
        limiter = SlidingWindowRateLimiter(redis_client=mock_redis, fallback_to_memory=False)
        with pytest.raises(RuntimeError):
            await limiter.is_allowed("key", limit=10, window_seconds=60)

    @pytest.mark.asyncio
    async def test_memory_key_parsing(self):
        limiter = SlidingWindowRateLimiter()
        result = await limiter.is_allowed("scope:ident:endpoint", limit=5, window_seconds=60)
        assert result.allowed is True


class TestRateLimitMiddleware:
    def _make_scope(self, path="/api/test"):
        return {"type": "http", "path": path, "headers": [], "query_string": b""}

    @pytest.mark.asyncio
    async def test_disabled_passes_through(self):
        app = AsyncMock()
        config = RateLimitConfig(enabled=False)
        mw = RateLimitMiddleware(app, config=config)
        scope = self._make_scope()
        await mw(scope, AsyncMock(), AsyncMock())
        app.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_http_passes_through(self):
        app = AsyncMock()
        mw = RateLimitMiddleware(app, config=RateLimitConfig(enabled=True))
        scope = {"type": "websocket"}
        await mw(scope, AsyncMock(), AsyncMock())
        app.assert_called_once()

    @pytest.mark.asyncio
    async def test_exempt_path_passes_through(self):
        app = AsyncMock()
        config = RateLimitConfig(enabled=True, exempt_paths=["/health"])
        mw = RateLimitMiddleware(app, config=config)
        scope = self._make_scope(path="/health")
        await mw(scope, AsyncMock(), AsyncMock())
        app.assert_called_once()

    def test_is_exempt_path_empty(self):
        config = RateLimitConfig(enabled=True, exempt_paths=[])
        mw = RateLimitMiddleware(MagicMock(), config=config)
        assert mw._is_exempt_path("/anything") is False

    def test_check_rule_match_no_endpoints(self):
        mw = RateLimitMiddleware(MagicMock(), config=RateLimitConfig())
        rule = RateLimitRule(requests=10)
        request = MagicMock()
        assert mw._check_rule_match(request, rule) is True

    def test_check_rule_match_with_endpoints(self):
        mw = RateLimitMiddleware(MagicMock(), config=RateLimitConfig())
        rule = RateLimitRule(requests=10, endpoints=["/api/v1"])
        request = MagicMock()
        request.url.path = "/api/v1/users"
        assert mw._check_rule_match(request, rule) is True
        request.url.path = "/other"
        assert mw._check_rule_match(request, rule) is False

    def test_create_429_response_basic(self):
        mw = RateLimitMiddleware(MagicMock(), config=RateLimitConfig())
        result = RateLimitResult(
            allowed=False, limit=10, remaining=0, reset_at=9999, retry_after=30
        )
        response = mw._create_429_response(result)
        assert response.status_code == 429

    def test_create_429_response_with_tenant(self):
        mw = RateLimitMiddleware(MagicMock(), config=RateLimitConfig())
        result = RateLimitResult(
            allowed=False,
            limit=10,
            remaining=0,
            reset_at=9999,
            retry_after=30,
            scope=RateLimitScope.TENANT,
        )
        response = mw._create_429_response(result, tenant_id="t1")
        assert response.status_code == 429
        assert "X-Tenant-RateLimit-Limit" in response.headers

    def test_get_tenant_id_from_state(self):
        mw = RateLimitMiddleware(MagicMock(), config=RateLimitConfig())
        request = MagicMock()
        request.state.tenant_id = "tenant-abc"
        assert mw._get_tenant_id(request) == "tenant-abc"

    def test_get_tenant_id_from_auth_claims(self):
        mw = RateLimitMiddleware(MagicMock(), config=RateLimitConfig())
        request = MagicMock()
        request.state.tenant_id = None
        request.state.auth_claims = {"tenant_id": "tenant-xyz"}
        # Ensure hasattr checks work
        del request.state.user
        assert mw._get_tenant_id(request) == "tenant-xyz"

    def test_get_tenant_id_ignores_untrusted_header(self):
        mw = RateLimitMiddleware(MagicMock(), config=RateLimitConfig())
        request = MagicMock()
        request.state = MagicMock(spec=[])  # No attributes on state
        request.headers = {"X-Tenant-ID": "header-tenant"}
        request.url.path = "/api"
        request.client.host = "127.0.0.1"
        assert mw._get_tenant_id(request) is None

    def test_get_tenant_id_none(self):
        mw = RateLimitMiddleware(MagicMock(), config=RateLimitConfig())
        request = MagicMock()
        request.state = MagicMock(spec=[])
        request.headers = {}
        assert mw._get_tenant_id(request) is None

    def test_get_tenant_quota_no_provider(self):
        mw = RateLimitMiddleware(MagicMock(), config=RateLimitConfig())
        mw.tenant_quota_provider = None
        assert mw._get_tenant_quota("t1") is None

    def test_get_tenant_quota_with_provider(self):
        provider = TenantRateLimitProvider()
        provider.set_tenant_quota("t1", requests=100)
        mw = RateLimitMiddleware(MagicMock(), config=RateLimitConfig(), tenant_quota_provider=provider)
        quota = mw._get_tenant_quota("t1")
        assert quota is not None
        assert quota.requests == 100

    def test_get_tenant_quota_provider_error(self):
        provider = MagicMock()
        provider.get_tenant_quota.side_effect = RuntimeError("boom")
        mw = RateLimitMiddleware(MagicMock(), config=RateLimitConfig(), tenant_quota_provider=provider)
        assert mw._get_tenant_quota("t1") is None


class TestExtractRequestFromCall:
    def test_from_args(self):
        request = MagicMock(spec=["__class__"])
        request.__class__ = type("Request", (), {})
        # Use a real-ish Request mock
        from fastapi import Request as FRequest
        req = MagicMock(spec=FRequest)
        assert _extract_request_from_call((req,), {}) is req

    def test_from_kwargs(self):
        from fastapi import Request as FRequest
        req = MagicMock(spec=FRequest)
        assert _extract_request_from_call((), {"request": req}) is req

    def test_not_found(self):
        assert _extract_request_from_call(("hello",), {"other": 42}) is None


class TestResolveRateLimitIdentifier:
    def test_with_key_func(self):
        request = MagicMock()
        result = _resolve_rate_limit_identifier(request, "user", lambda r: "custom-id")
        assert result == "custom-id"

    def test_user_type(self):
        request = MagicMock()
        request.state.user_id = "u123"
        result = _resolve_rate_limit_identifier(request, "user", None)
        assert result == "u123"

    def test_ip_type(self):
        request = MagicMock()
        request.client.host = "1.2.3.4"
        result = _resolve_rate_limit_identifier(request, "ip", None)
        assert result == "1.2.3.4"

    def test_endpoint_type(self):
        request = MagicMock()
        request.url.path = "/api/test"
        result = _resolve_rate_limit_identifier(request, "endpoint", None)
        assert result == "/api/test"

    def test_global_type(self):
        request = MagicMock()
        result = _resolve_rate_limit_identifier(request, "global", None)
        assert result == "global"


class TestUpdateRateLimitMetrics:
    def test_allowed(self):
        update_rate_limit_metrics("ip", "1.2.3.4", "/api", True)

    def test_blocked(self):
        update_rate_limit_metrics("ip", "1.2.3.4", "/api", False)


class TestConfigureRateLimits:
    def test_configure_with_redis(self):
        mock_redis = MagicMock()
        configure_rate_limits(redis_client=mock_redis, default_requests_per_minute=30)


class TestRateLimitDecorator:
    @pytest.mark.asyncio
    async def test_decorator_no_request(self):
        @rate_limit(requests_per_minute=5)
        async def my_endpoint(x: int):
            return x

        result = await my_endpoint(42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_decorator_allowed(self):
        from fastapi import Request as FRequest
        req = MagicMock(spec=FRequest)
        req.client.host = "1.2.3.4"
        req.state.user_id = "u1"
        req.url.path = "/test"

        @rate_limit(requests_per_minute=100)
        async def my_endpoint(request):
            return "ok"

        result = await my_endpoint(req)
        assert result == "ok"


# ============================================================================
# token_revocation.py tests
# ============================================================================


class TestTokenRevocationParseBoolEnv:
    def test_none(self):
        assert tr_parse_bool_env(None) is None

    def test_true(self):
        assert tr_parse_bool_env("true") is True

    def test_false(self):
        assert tr_parse_bool_env("false") is False

    def test_invalid(self):
        assert tr_parse_bool_env("dunno") is None


class TestTokenRevocationService:
    def test_init_without_redis(self):
        service = TokenRevocationService(redis_client=None)
        assert service._use_redis is False

    def test_init_with_redis(self):
        service = TokenRevocationService(redis_client=MagicMock())
        assert service._use_redis is True

    @pytest.mark.asyncio
    async def test_revoke_token_empty_jti(self):
        from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError
        service = TokenRevocationService(redis_client=MagicMock())
        with pytest.raises(ACGSValidationError):
            await service.revoke_token(jti="", expires_at=datetime.now(UTC))

    @pytest.mark.asyncio
    async def test_revoke_token_whitespace_jti(self):
        from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError
        service = TokenRevocationService(redis_client=MagicMock())
        with pytest.raises(ACGSValidationError):
            await service.revoke_token(jti="   ", expires_at=datetime.now(UTC))

    @pytest.mark.asyncio
    async def test_revoke_token_no_redis(self):
        service = TokenRevocationService(redis_client=None)
        result = await service.revoke_token(jti="abc-123", expires_at=datetime.now(UTC) + timedelta(hours=1))
        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_token_success(self):
        mock_redis = AsyncMock()
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.revoke_token(
            jti="abc-123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert result is True
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_token_redis_connection_error(self):
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = ConnectionError("gone")
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.revoke_token(
            jti="abc-123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_token_unexpected_error(self):
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = RuntimeError("unexpected")
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.revoke_token(
            jti="abc-123",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_is_token_revoked_empty_jti(self):
        from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError
        service = TokenRevocationService(redis_client=MagicMock())
        with pytest.raises(ACGSValidationError):
            await service.is_token_revoked(jti="")

    @pytest.mark.asyncio
    async def test_is_token_revoked_no_redis_fail_open(self):
        service = TokenRevocationService(redis_client=None)
        with patch.object(TokenRevocationService, "_should_fail_open", return_value=True):
            result = await service.is_token_revoked(jti="abc-123")
            assert result is False

    @pytest.mark.asyncio
    async def test_is_token_revoked_no_redis_strict(self):
        service = TokenRevocationService(redis_client=None)
        with patch.object(TokenRevocationService, "_should_fail_open", return_value=False):
            result = await service.is_token_revoked(jti="abc-123")
            assert result is True

    @pytest.mark.asyncio
    async def test_is_token_revoked_true(self):
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 1
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.is_token_revoked(jti="abc-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_token_revoked_false(self):
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 0
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.is_token_revoked(jti="abc-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_token_revoked_connection_error_fail_open(self):
        mock_redis = AsyncMock()
        mock_redis.exists.side_effect = ConnectionError("gone")
        service = TokenRevocationService(redis_client=mock_redis)
        with patch.object(TokenRevocationService, "_should_fail_open", return_value=True):
            result = await service.is_token_revoked(jti="abc-123")
            assert result is False

    @pytest.mark.asyncio
    async def test_is_token_revoked_connection_error_strict(self):
        mock_redis = AsyncMock()
        mock_redis.exists.side_effect = ConnectionError("gone")
        service = TokenRevocationService(redis_client=mock_redis)
        with patch.object(TokenRevocationService, "_should_fail_open", return_value=False):
            result = await service.is_token_revoked(jti="abc-123")
            assert result is True

    @pytest.mark.asyncio
    async def test_is_token_revoked_unexpected_error_fail_open(self):
        mock_redis = AsyncMock()
        mock_redis.exists.side_effect = RuntimeError("unexpected")
        service = TokenRevocationService(redis_client=mock_redis)
        with patch.object(TokenRevocationService, "_should_fail_open", return_value=True):
            result = await service.is_token_revoked(jti="abc-123")
            assert result is False

    @pytest.mark.asyncio
    async def test_is_token_revoked_unexpected_error_strict(self):
        mock_redis = AsyncMock()
        mock_redis.exists.side_effect = RuntimeError("unexpected")
        service = TokenRevocationService(redis_client=mock_redis)
        with patch.object(TokenRevocationService, "_should_fail_open", return_value=False):
            result = await service.is_token_revoked(jti="abc-123")
            assert result is True


class TestTokenRevocationRevokeAllUserTokens:
    @pytest.mark.asyncio
    async def test_empty_user_id(self):
        from src.core.shared.errors.exceptions import ValidationError as ACGSValidationError
        service = TokenRevocationService(redis_client=MagicMock())
        with pytest.raises(ACGSValidationError):
            await service.revoke_all_user_tokens(user_id="", expires_at=datetime.now(UTC))

    @pytest.mark.asyncio
    async def test_no_redis(self):
        service = TokenRevocationService(redis_client=None)
        result = await service.revoke_all_user_tokens(
            user_id="user1", expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
        assert result == 0

    @pytest.mark.asyncio
    async def test_success(self):
        mock_redis = AsyncMock()
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.revoke_all_user_tokens(
            user_id="user1", expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
        assert result == 1
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_error(self):
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = ConnectionError("gone")
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.revoke_all_user_tokens(
            user_id="user1", expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
        assert result == 0

    @pytest.mark.asyncio
    async def test_unexpected_error(self):
        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = RuntimeError("unexpected")
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.revoke_all_user_tokens(
            user_id="user1", expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
        assert result == 0


class TestTokenRevocationCalculateTTL:
    def test_future_expiry(self):
        service = TokenRevocationService()
        expires = datetime.now(UTC) + timedelta(hours=1)
        ttl = service._calculate_ttl(expires)
        assert ttl > 3500  # ~3600 seconds give or take

    def test_past_expiry_min_1(self):
        service = TokenRevocationService()
        expires = datetime.now(UTC) - timedelta(hours=1)
        ttl = service._calculate_ttl(expires)
        assert ttl == 1

    def test_naive_datetime(self):
        service = TokenRevocationService()
        expires = datetime.now() + timedelta(hours=1)
        ttl = service._calculate_ttl(expires)
        assert ttl > 0


class TestTokenRevocationIsUserRevoked:
    @pytest.mark.asyncio
    async def test_no_redis_fail_open(self):
        service = TokenRevocationService(redis_client=None)
        with patch.object(TokenRevocationService, "_should_fail_open", return_value=True):
            result = await service.is_user_revoked("user1", datetime.now(UTC))
            assert result is False

    @pytest.mark.asyncio
    async def test_no_redis_strict(self):
        service = TokenRevocationService(redis_client=None)
        with patch.object(TokenRevocationService, "_should_fail_open", return_value=False):
            result = await service.is_user_revoked("user1", datetime.now(UTC))
            assert result is True

    @pytest.mark.asyncio
    async def test_no_revocation_timestamp(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.is_user_revoked("user1", datetime.now(UTC))
        assert result is False

    @pytest.mark.asyncio
    async def test_token_issued_before_revocation(self):
        mock_redis = AsyncMock()
        revoked_at = datetime.now(UTC)
        issued_at = revoked_at - timedelta(hours=1)
        mock_redis.get.return_value = revoked_at.isoformat()
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.is_user_revoked("user1", issued_at)
        assert result is True

    @pytest.mark.asyncio
    async def test_token_issued_after_revocation(self):
        mock_redis = AsyncMock()
        revoked_at = datetime.now(UTC) - timedelta(hours=2)
        issued_at = datetime.now(UTC) - timedelta(hours=1)
        mock_redis.get.return_value = revoked_at.isoformat()
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.is_user_revoked("user1", issued_at)
        assert result is False

    @pytest.mark.asyncio
    async def test_bytes_revocation_timestamp(self):
        mock_redis = AsyncMock()
        revoked_at = datetime.now(UTC)
        issued_at = revoked_at - timedelta(hours=1)
        mock_redis.get.return_value = revoked_at.isoformat().encode("utf-8")
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.is_user_revoked("user1", issued_at)
        assert result is True

    @pytest.mark.asyncio
    async def test_connection_error_fail_open(self):
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = ConnectionError("gone")
        service = TokenRevocationService(redis_client=mock_redis)
        with patch.object(TokenRevocationService, "_should_fail_open", return_value=True):
            result = await service.is_user_revoked("user1", datetime.now(UTC))
            assert result is False

    @pytest.mark.asyncio
    async def test_connection_error_strict(self):
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = ConnectionError("gone")
        service = TokenRevocationService(redis_client=mock_redis)
        with patch.object(TokenRevocationService, "_should_fail_open", return_value=False):
            result = await service.is_user_revoked("user1", datetime.now(UTC))
            assert result is True

    @pytest.mark.asyncio
    async def test_value_error(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "not-a-date"
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.is_user_revoked("user1", datetime.now(UTC))
        assert result is False

    @pytest.mark.asyncio
    async def test_unexpected_error_fail_open(self):
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = RuntimeError("unexpected")
        service = TokenRevocationService(redis_client=mock_redis)
        with patch.object(TokenRevocationService, "_should_fail_open", return_value=True):
            result = await service.is_user_revoked("user1", datetime.now(UTC))
            assert result is False

    @pytest.mark.asyncio
    async def test_unexpected_error_strict(self):
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = RuntimeError("unexpected")
        service = TokenRevocationService(redis_client=mock_redis)
        with patch.object(TokenRevocationService, "_should_fail_open", return_value=False):
            result = await service.is_user_revoked("user1", datetime.now(UTC))
            assert result is True

    @pytest.mark.asyncio
    async def test_naive_token_issued_at(self):
        mock_redis = AsyncMock()
        revoked_at = datetime.now(UTC)
        issued_at = datetime.now() - timedelta(hours=1)  # naive datetime
        mock_redis.get.return_value = revoked_at.isoformat()
        service = TokenRevocationService(redis_client=mock_redis)
        result = await service.is_user_revoked("user1", issued_at)
        assert result is True


class TestTokenRevocationGetStats:
    @pytest.mark.asyncio
    async def test_no_redis(self):
        service = TokenRevocationService(redis_client=None)
        stats = await service.get_revocation_stats()
        assert stats["redis_available"] is False
        assert stats["blacklist_count"] == 0

    @pytest.mark.asyncio
    async def test_with_redis(self):
        mock_redis = MagicMock()

        async def mock_scan_blacklist(*args, **kwargs):
            for item in ["token_blacklist:a", "token_blacklist:b"]:
                yield item

        async def mock_scan_user(*args, **kwargs):
            for item in ["user_revoked:u1"]:
                yield item

        call_count = 0

        def scan_iter_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_scan_blacklist()
            return mock_scan_user()

        mock_redis.scan_iter = MagicMock(side_effect=scan_iter_side_effect)

        service = TokenRevocationService(redis_client=mock_redis)
        stats = await service.get_revocation_stats()
        assert stats["redis_available"] is True
        assert stats["blacklist_count"] == 2
        assert stats["user_revocations"] == 1

    @pytest.mark.asyncio
    async def test_redis_error(self):
        mock_redis = MagicMock()

        async def mock_scan_error(*args, **kwargs):
            raise ConnectionError("gone")
            yield

        mock_redis.scan_iter = MagicMock(return_value=mock_scan_error())

        service = TokenRevocationService(redis_client=mock_redis)
        stats = await service.get_revocation_stats()
        assert stats["redis_available"] is False
        assert "error" in stats


class TestTokenRevocationClose:
    @pytest.mark.asyncio
    async def test_close_no_redis(self):
        service = TokenRevocationService(redis_client=None)
        await service.close()

    @pytest.mark.asyncio
    async def test_close_with_aclose(self):
        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()
        service = TokenRevocationService(redis_client=mock_redis)
        await service.close()
        mock_redis.aclose.assert_called_once()
        assert service._redis_client is None

    @pytest.mark.asyncio
    async def test_close_with_sync_close(self):
        mock_redis = MagicMock()
        del mock_redis.aclose  # no aclose
        mock_redis.close = MagicMock(return_value=None)
        service = TokenRevocationService(redis_client=mock_redis)
        await service.close()
        mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_with_async_close(self):
        mock_redis = MagicMock()
        del mock_redis.aclose
        mock_redis.close = AsyncMock()
        service = TokenRevocationService(redis_client=mock_redis)
        await service.close()
        mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_error(self):
        mock_redis = MagicMock()
        mock_redis.aclose = MagicMock(side_effect=RuntimeError("boom"))
        service = TokenRevocationService(redis_client=mock_redis)
        await service.close()
        assert service._redis_client is None


class TestTokenRevocationShouldFailOpen:
    @patch.dict("os.environ", {"TOKEN_REVOCATION_FAIL_OPEN": "true"}, clear=False)
    def test_env_true(self):
        assert TokenRevocationService._should_fail_open() is True

    @patch.dict("os.environ", {"TOKEN_REVOCATION_FAIL_OPEN": "false"}, clear=False)
    def test_env_false(self):
        assert TokenRevocationService._should_fail_open() is False


class TestCreateTokenRevocationService:
    @pytest.mark.asyncio
    async def test_redis_unavailable(self):
        """When Redis connection fails, service should operate in degraded mode."""
        import importlib

        # Simulate redis.asyncio import raising an error by patching
        # the entire create function's redis import path
        with patch("builtins.__import__", side_effect=Exception("no redis")):
            # Override __import__ only for 'redis' and 'redis.asyncio'
            original_import = importlib.__import__

            def selective_import(name, *args, **kwargs):
                if name in ("redis.asyncio", "redis"):
                    raise ImportError("no redis")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=selective_import):
                service = await create_token_revocation_service("redis://fake:6379")
                assert service._use_redis is False

    @pytest.mark.asyncio
    async def test_redis_connection_success(self):
        """When Redis connects successfully, service should have redis client."""
        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock(return_value=True)

        import redis.asyncio as redis_async

        with patch.object(redis_async, "from_url", new=AsyncMock(return_value=mock_redis_client)):
            service = await create_token_revocation_service("redis://localhost:6379")
            assert service._use_redis is True

    @pytest.mark.asyncio
    async def test_redis_no_url_uses_env(self):
        """When no URL provided, uses REDIS_URL env var."""
        service = await create_token_revocation_service()
        # Without a running Redis, it falls back to degraded mode
        assert service._use_redis is False


# ============================================================================
# url_file_validator.py tests
# ============================================================================


class TestURLValidator:
    def setup_method(self):
        reset_url_validator()

    def test_valid_url_non_production(self):
        validator = URLValidator()
        result = validator.validate_url("http://localhost:8080/api", is_production=False)
        assert result == "http://localhost:8080/api"

    def test_url_too_long(self):
        validator = URLValidator(config=SSRFProtectionConfig(max_url_length=10))
        with pytest.raises(HTTPException) as exc_info:
            validator.validate_url("https://example.com/very/long/path")
        assert exc_info.value.status_code == 400

    def test_invalid_scheme(self):
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("ftp://example.com/file", is_production=False)

    def test_https_required_in_production(self):
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("http://example.com", is_production=True)

    def test_https_not_required_for_internal(self):
        validator = URLValidator()
        result = validator.validate_url("http://redis:6379", is_production=True)
        assert result == "http://redis:6379"

    def test_missing_hostname(self):
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("https://", is_production=False)

    def test_cloud_metadata_blocked(self):
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("http://169.254.169.254/latest", is_production=False)

    def test_localhost_ip_blocked(self):
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("http://127.0.0.1/api", is_production=False)

    def test_private_ip_blocked(self):
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("http://10.0.0.1/api", is_production=False)

    def test_link_local_blocked(self):
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("http://169.254.1.1/api", is_production=False)

    def test_reserved_ip_blocked(self):
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("http://240.0.0.1/api", is_production=False)

    def test_multicast_blocked(self):
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("http://224.0.0.1/api", is_production=False)

    def test_domain_not_in_allowlist(self):
        validator = URLValidator()
        with pytest.raises(HTTPException):
            validator.validate_url("https://evil.com/phish", is_production=False)

    def test_allowed_domain(self):
        config = SSRFProtectionConfig(allowed_domains={"example.com"})
        validator = URLValidator(config=config)
        result = validator.validate_url("https://example.com/api", is_production=False)
        assert result == "https://example.com/api"

    def test_allowed_subdomain(self):
        config = SSRFProtectionConfig(allowed_domains={"example.com"})
        validator = URLValidator(config=config)
        result = validator.validate_url("https://api.example.com/test", is_production=False)
        assert result == "https://api.example.com/test"

    def test_allowed_domain_pattern(self):
        config = SSRFProtectionConfig(allowed_domain_patterns=[r".*\.myservice\.io"])
        validator = URLValidator(config=config)
        result = validator.validate_url("https://app.myservice.io/api", is_production=False)
        assert result == "https://app.myservice.io/api"

    def test_additional_allowed_domains(self):
        validator = URLValidator()
        result = validator.validate_url(
            "https://custom.org/api",
            is_production=False,
            additional_allowed_domains={"custom.org"},
        )
        assert result == "https://custom.org/api"

    def test_add_allowed_domain(self):
        validator = URLValidator()
        validator.add_allowed_domain("Dynamic.ORG")
        result = validator.validate_url("https://dynamic.org/api", is_production=False)
        assert result == "https://dynamic.org/api"

    def test_add_allowed_pattern(self):
        validator = URLValidator()
        validator.add_allowed_pattern(r".*\.dynamic\.org")
        result = validator.validate_url("https://sub.dynamic.org/api", is_production=False)
        assert result == "https://sub.dynamic.org/api"


class TestFileValidator:
    def setup_method(self):
        reset_file_validator()

    def test_detect_png(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.PNG},
            verify_extension_match=False,
            block_executables=False,
        ))
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        result = validator.validate_content(content, "image.png")
        assert result == FileType.PNG

    def test_detect_jpeg(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.JPEG},
            verify_extension_match=False,
            block_executables=False,
        ))
        content = b"\xff\xd8\xff" + b"\x00" * 100
        result = validator.validate_content(content, "photo.jpg")
        assert result == FileType.JPEG

    def test_detect_zip(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.ZIP},
            verify_extension_match=False,
            block_executables=False,
        ))
        content = b"PK\x03\x04" + b"\x00" * 100
        result = validator.validate_content(content)
        assert result == FileType.ZIP

    def test_detect_gzip(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.TAR_GZ},
            verify_extension_match=False,
            block_executables=False,
        ))
        content = b"\x1f\x8b" + b"\x00" * 100
        result = validator.validate_content(content)
        assert result == FileType.TAR_GZ

    def test_detect_pdf(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.PDF},
            verify_extension_match=False,
            block_executables=False,
        ))
        content = b"%PDF-1.4 some pdf content here"
        result = validator.validate_content(content)
        assert result == FileType.PDF

    def test_detect_gif87a(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.GIF},
            verify_extension_match=False,
            block_executables=False,
        ))
        content = b"GIF87a" + b"\x00" * 100
        result = validator.validate_content(content)
        assert result == FileType.GIF

    def test_detect_json(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.JSON},
            verify_extension_match=False,
            block_executables=False,
        ))
        content = b'{"key": "value"}'
        result = validator.validate_content(content)
        assert result == FileType.JSON

    def test_detect_json_array(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.JSON},
            verify_extension_match=False,
            block_executables=False,
        ))
        content = b'[1, 2, 3]'
        result = validator.validate_content(content)
        assert result == FileType.JSON

    def test_detect_text_fallback(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.TEXT},
            verify_extension_match=False,
            block_executables=False,
        ))
        content = b"Just plain text content"
        result = validator.validate_content(content)
        assert result == FileType.TEXT

    def test_empty_file_blocked(self):
        validator = FileValidator()
        with pytest.raises(HTTPException):
            validator.validate_content(b"")

    def test_file_too_large(self):
        validator = FileValidator(config=FileValidationConfig(max_file_size=10))
        with pytest.raises(HTTPException):
            validator.validate_content(b"x" * 100, "large.txt")

    def test_type_not_allowed(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.JSON},
            verify_extension_match=False,
            block_executables=False,
        ))
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        with pytest.raises(HTTPException):
            validator.validate_content(content)

    def test_unknown_type_not_text(self):
        validator = FileValidator(config=FileValidationConfig(
            verify_magic_bytes=True,
            verify_extension_match=False,
            block_executables=False,
        ))
        # Binary content that isn't valid text
        content = bytes(range(256)) * 10
        with pytest.raises(HTTPException):
            validator.validate_content(content)

    def test_executable_content_blocked(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.TEXT},
            verify_magic_bytes=True,
            verify_extension_match=False,
            block_executables=True,
        ))
        content = b"#!/bin/bash\nrm -rf /"
        with pytest.raises(HTTPException):
            validator.validate_content(content, "script.txt")

    def test_php_content_blocked(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.TEXT},
            verify_magic_bytes=True,
            verify_extension_match=False,
            block_executables=True,
        ))
        content = b"<?php echo 'hack'; ?>"
        with pytest.raises(HTTPException):
            validator.validate_content(content, "shell.txt")

    def test_extension_mismatch(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.PNG},
            verify_extension_match=True,
            block_executables=False,
        ))
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        with pytest.raises(HTTPException):
            validator.validate_content(content, "image.jpg")

    def test_extension_match_ok(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.PNG},
            verify_extension_match=True,
            block_executables=False,
        ))
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        result = validator.validate_content(content, "image.png")
        assert result == FileType.PNG

    def test_unknown_extension_allowed(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.JSON},
            verify_extension_match=True,
            block_executables=False,
        ))
        content = b'{"data": true}'
        result = validator.validate_content(content, "data.custom")
        assert result == FileType.JSON

    @pytest.mark.asyncio
    async def test_validate_upload(self):
        validator = FileValidator(config=FileValidationConfig(
            allowed_types={FileType.JSON},
            verify_extension_match=False,
            block_executables=False,
        ))
        file = AsyncMock(spec=UploadFile)
        file.filename = "data.json"
        file.read.return_value = b'{"key": "val"}'
        content, ftype = await validator.validate_upload(file)
        assert ftype == FileType.JSON
        assert content == b'{"key": "val"}'

    @pytest.mark.asyncio
    async def test_validate_upload_too_large(self):
        validator = FileValidator(config=FileValidationConfig(max_file_size=5))
        file = AsyncMock(spec=UploadFile)
        file.filename = "big.txt"
        file.read.return_value = b"x" * 100
        with pytest.raises(HTTPException):
            await validator.validate_upload(file)

    @pytest.mark.asyncio
    async def test_validate_upload_empty(self):
        validator = FileValidator()
        file = AsyncMock(spec=UploadFile)
        file.filename = "empty.txt"
        file.read.return_value = b""
        with pytest.raises(HTTPException):
            await validator.validate_upload(file)

    def test_is_valid_text_ascii(self):
        validator = FileValidator()
        assert validator._is_valid_text(b"Hello world\n") is True

    def test_is_valid_text_binary(self):
        validator = FileValidator()
        # Invalid UTF-8 sequences with many control characters
        content = b"\x80\x81\x82\x01\x02\x03\x04\x05\x06" * 200
        assert validator._is_valid_text(content) is False


class TestURLFileValidatorSingletons:
    def setup_method(self):
        reset_url_validator()
        reset_file_validator()

    def test_get_url_validator_singleton(self):
        v1 = get_url_validator()
        v2 = get_url_validator()
        assert v1 is v2

    def test_get_url_validator_reset(self):
        v1 = get_url_validator()
        reset_url_validator()
        v2 = get_url_validator()
        assert v1 is not v2

    def test_get_file_validator_singleton(self):
        v1 = get_file_validator()
        v2 = get_file_validator()
        assert v1 is v2

    def test_get_file_validator_with_config(self):
        v1 = get_file_validator()
        config = FileValidationConfig(max_file_size=100)
        v2 = get_file_validator(config=config)
        assert v1 is not v2

    def test_convenience_validate_url(self):
        reset_url_validator()
        result = validate_url("https://localhost/api", is_production=False)
        assert result == "https://localhost/api"

    def test_convenience_validate_file_content(self):
        reset_file_validator()
        result = validate_file_content(b'{"key": "val"}', "data.json")
        assert result == FileType.JSON


# ============================================================================
# retention_policy.py tests
# ============================================================================


class TestRetentionStatus:
    def test_values(self):
        assert RetentionStatus.ACTIVE == "active"
        assert RetentionStatus.DISPOSED == "disposed"
        assert RetentionStatus.HELD == "held"


class TestRetentionActionType:
    def test_values(self):
        assert RetentionActionType.CREATED == "created"
        assert RetentionActionType.HOLD_APPLIED == "hold_applied"


class TestInMemoryRetentionStorage:
    @pytest.mark.asyncio
    async def test_save_and_get_record(self):
        storage = InMemoryRetentionStorage()
        record = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) + timedelta(days=30),
        )
        await storage.save_record(record)
        retrieved = await storage.get_record(record.record_id)
        assert retrieved is not None
        assert retrieved.data_id == "d1"

    @pytest.mark.asyncio
    async def test_get_record_not_found(self):
        storage = InMemoryRetentionStorage()
        assert await storage.get_record("nonexistent") is None

    @pytest.mark.asyncio
    async def test_find_expired_records(self):
        storage = InMemoryRetentionStorage()
        expired_record = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) - timedelta(days=1),
        )
        active_record = RetentionRecord(
            data_id="d2",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) + timedelta(days=30),
        )
        await storage.save_record(expired_record)
        await storage.save_record(active_record)

        expired = await storage.find_expired_records()
        assert len(expired) == 1
        assert expired[0].data_id == "d1"

    @pytest.mark.asyncio
    async def test_find_expired_records_legal_hold_excluded(self):
        storage = InMemoryRetentionStorage()
        record = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) - timedelta(days=1),
            legal_hold=True,
        )
        await storage.save_record(record)
        expired = await storage.find_expired_records()
        assert len(expired) == 0

    @pytest.mark.asyncio
    async def test_find_expired_records_tenant_filter(self):
        storage = InMemoryRetentionStorage()
        r1 = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) - timedelta(days=1),
            tenant_id="t1",
        )
        r2 = RetentionRecord(
            data_id="d2",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) - timedelta(days=1),
            tenant_id="t2",
        )
        await storage.save_record(r1)
        await storage.save_record(r2)
        expired = await storage.find_expired_records(tenant_id="t1")
        assert len(expired) == 1
        assert expired[0].tenant_id == "t1"

    @pytest.mark.asyncio
    async def test_find_expired_records_limit(self):
        storage = InMemoryRetentionStorage()
        for i in range(5):
            r = RetentionRecord(
                data_id=f"d{i}",
                data_type="test",
                policy_id="p1",
                classification_tier=DataClassificationTier.INTERNAL,
                retention_until=datetime.now(UTC) - timedelta(days=1),
            )
            await storage.save_record(r)
        expired = await storage.find_expired_records(limit=3)
        assert len(expired) == 3

    @pytest.mark.asyncio
    async def test_find_expired_records_non_active_excluded(self):
        storage = InMemoryRetentionStorage()
        record = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC) - timedelta(days=1),
            status=RetentionStatus.DISPOSED,
        )
        await storage.save_record(record)
        expired = await storage.find_expired_records()
        assert len(expired) == 0

    @pytest.mark.asyncio
    async def test_log_and_get_actions(self):
        storage = InMemoryRetentionStorage()
        action = RetentionAction(
            record_id="r1",
            action_type=RetentionActionType.CREATED,
        )
        await storage.log_action(action)
        actions = await storage.get_actions(record_id="r1")
        assert len(actions) == 1

    @pytest.mark.asyncio
    async def test_get_actions_no_filter(self):
        storage = InMemoryRetentionStorage()
        for i in range(3):
            await storage.log_action(RetentionAction(
                record_id=f"r{i}",
                action_type=RetentionActionType.CREATED,
            ))
        actions = await storage.get_actions()
        assert len(actions) == 3

    def test_get_policy(self):
        storage = InMemoryRetentionStorage()
        policy = storage.get_policy("default-public")
        assert policy is not None
        assert policy.name == "Public Data - Indefinite"

    def test_get_policy_not_found(self):
        storage = InMemoryRetentionStorage()
        assert storage.get_policy("nonexistent") is None

    def test_add_policy(self):
        storage = InMemoryRetentionStorage()
        policy = RetentionPolicy(
            policy_id="custom",
            name="Custom",
            classification_tier=DataClassificationTier.PUBLIC,
            retention_days=30,
            disposal_method=DisposalMethod.DELETE,
        )
        storage.add_policy(policy)
        assert storage.get_policy("custom") is not None


class TestDisposalHandlers:
    @pytest.mark.asyncio
    async def test_delete_handler_success(self):
        handler = DeleteHandler()
        record = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC),
        )
        result = await handler.dispose(record, data={"key": "val"})
        assert result.success is True
        assert result.method == DisposalMethod.DELETE
        assert result.audit_trail_hash != ""
        assert result.bytes_disposed > 0

    @pytest.mark.asyncio
    async def test_delete_handler_no_data(self):
        handler = DeleteHandler()
        record = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC),
        )
        result = await handler.dispose(record)
        assert result.success is True
        assert result.bytes_disposed == 0

    @pytest.mark.asyncio
    async def test_delete_handler_error(self):
        handler = DeleteHandler()
        record = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC),
        )
        # Non-serializable data
        class Unserializable:
            pass
        result = await handler.dispose(record, data=Unserializable())
        assert result.success is False

    @pytest.mark.asyncio
    async def test_archive_handler_success(self):
        handler = ArchiveHandler()
        record = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC),
        )
        result = await handler.dispose(record, data={"key": "val"})
        assert result.success is True
        assert result.method == DisposalMethod.ARCHIVE

    @pytest.mark.asyncio
    async def test_archive_handler_error(self):
        handler = ArchiveHandler()
        record = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC),
        )
        class Unserializable:
            pass
        result = await handler.dispose(record, data=Unserializable())
        assert result.success is False

    @pytest.mark.asyncio
    async def test_anonymize_handler_success(self):
        handler = AnonymizeHandler()
        record = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC),
        )
        result = await handler.dispose(record)
        assert result.success is True
        assert result.method == DisposalMethod.ANONYMIZE
        assert result.bytes_disposed == 0

    @pytest.mark.asyncio
    async def test_pseudonymize_handler_success(self):
        handler = PseudonymizeHandler()
        record = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC),
        )
        result = await handler.dispose(record)
        assert result.success is True
        assert result.method == DisposalMethod.PSEUDONYMIZE


class TestRetentionPolicyEngine:
    @pytest.mark.asyncio
    async def test_create_retention_record(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        assert record.data_id == "d1"
        assert record.status == RetentionStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_create_retention_record_unknown_policy_fallback(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="nonexistent",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        assert record is not None

    @pytest.mark.asyncio
    async def test_create_retention_record_indefinite(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-public",
            classification_tier=DataClassificationTier.PUBLIC,
        )
        assert record.retention_until.year == datetime.max.year

    @pytest.mark.asyncio
    async def test_extend_retention(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        old_until = record.retention_until
        updated = await engine.extend_retention(record.record_id, 30, "legal requirement")
        assert updated is not None
        assert updated.retention_until > old_until

    @pytest.mark.asyncio
    async def test_extend_retention_not_found(self):
        engine = RetentionPolicyEngine()
        assert await engine.extend_retention("nonexistent", 30, "reason") is None

    @pytest.mark.asyncio
    async def test_apply_legal_hold(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        held = await engine.apply_legal_hold(record.record_id, "litigation")
        assert held is not None
        assert held.legal_hold is True
        assert held.legal_hold_reason == "litigation"

    @pytest.mark.asyncio
    async def test_apply_legal_hold_not_found(self):
        engine = RetentionPolicyEngine()
        assert await engine.apply_legal_hold("nonexistent", "reason") is None

    @pytest.mark.asyncio
    async def test_release_legal_hold(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        await engine.apply_legal_hold(record.record_id, "litigation")
        released = await engine.release_legal_hold(record.record_id)
        assert released is not None
        assert released.legal_hold is False
        assert released.legal_hold_reason is None

    @pytest.mark.asyncio
    async def test_release_legal_hold_not_found(self):
        engine = RetentionPolicyEngine()
        assert await engine.release_legal_hold("nonexistent") is None

    @pytest.mark.asyncio
    async def test_dispose_record_delete(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        result = await engine.dispose_record(record.record_id, method=DisposalMethod.DELETE)
        assert result.success is True
        stored = await engine.storage.get_record(record.record_id)
        assert stored.status == RetentionStatus.DISPOSED

    @pytest.mark.asyncio
    async def test_dispose_record_archive(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        result = await engine.dispose_record(record.record_id, method=DisposalMethod.ARCHIVE)
        assert result.success is True
        stored = await engine.storage.get_record(record.record_id)
        assert stored.status == RetentionStatus.ARCHIVED

    @pytest.mark.asyncio
    async def test_dispose_record_anonymize(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        result = await engine.dispose_record(record.record_id, method=DisposalMethod.ANONYMIZE)
        assert result.success is True
        stored = await engine.storage.get_record(record.record_id)
        assert stored.status == RetentionStatus.ANONYMIZED

    @pytest.mark.asyncio
    async def test_dispose_record_pseudonymize(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        result = await engine.dispose_record(record.record_id, method=DisposalMethod.PSEUDONYMIZE)
        assert result.success is True
        stored = await engine.storage.get_record(record.record_id)
        assert stored.status == RetentionStatus.ANONYMIZED

    @pytest.mark.asyncio
    async def test_dispose_record_not_found(self):
        engine = RetentionPolicyEngine()
        result = await engine.dispose_record("nonexistent")
        assert result.success is False
        assert "not found" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_dispose_record_legal_hold(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        await engine.apply_legal_hold(record.record_id, "litigation")
        result = await engine.dispose_record(record.record_id)
        assert result.success is False
        assert "legal hold" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_dispose_record_no_handler(self):
        # Note: empty dict {} is falsy in Python, so we must set after init
        engine = RetentionPolicyEngine()
        engine.disposal_handlers = {}
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        result = await engine.dispose_record(record.record_id, method=DisposalMethod.DELETE)
        assert result.success is False
        assert "no handler" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_dispose_record_default_method_from_policy(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        result = await engine.dispose_record(record.record_id)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_enforce_retention(self):
        engine = RetentionPolicyEngine()
        # Create expired records
        for i in range(3):
            record = await engine.create_retention_record(
                data_id=f"d{i}",
                data_type="test",
                policy_id="default-internal",
                classification_tier=DataClassificationTier.INTERNAL,
            )
            record.retention_until = datetime.now(UTC) - timedelta(days=1)
            await engine.storage.update_record(record)

        report = await engine.enforce_retention()
        assert report.records_scanned == 3
        assert report.records_expired == 3
        assert report.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_enforce_retention_with_tenant(self):
        engine = RetentionPolicyEngine()
        r1 = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
            tenant_id="t1",
        )
        r1.retention_until = datetime.now(UTC) - timedelta(days=1)
        await engine.storage.update_record(r1)

        r2 = await engine.create_retention_record(
            data_id="d2",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
            tenant_id="t2",
        )
        r2.retention_until = datetime.now(UTC) - timedelta(days=1)
        await engine.storage.update_record(r2)

        report = await engine.enforce_retention(tenant_id="t1")
        assert report.records_scanned == 1

    @pytest.mark.asyncio
    async def test_get_record_history(self):
        engine = RetentionPolicyEngine()
        record = await engine.create_retention_record(
            data_id="d1",
            data_type="test",
            policy_id="default-internal",
            classification_tier=DataClassificationTier.INTERNAL,
        )
        history = await engine.get_record_history(record.record_id)
        assert len(history) == 1
        assert history[0].action_type == RetentionActionType.CREATED


class TestRetentionEngineSingleton:
    def setup_method(self):
        reset_retention_engine()

    def test_get_engine(self):
        engine = get_retention_engine()
        assert engine is not None
        engine2 = get_retention_engine()
        assert engine is engine2

    def test_reset_engine(self):
        engine = get_retention_engine()
        reset_retention_engine()
        engine2 = get_retention_engine()
        assert engine is not engine2


class TestDisposalResultModel:
    def test_defaults(self):
        result = DisposalResult(
            record_id="r1",
            success=True,
            method=DisposalMethod.DELETE,
        )
        assert result.bytes_disposed == 0
        assert result.error_message is None
        assert result.constitutional_hash == "608508a9bd224290"


class TestRetentionRecordModel:
    def test_defaults(self):
        record = RetentionRecord(
            data_id="d1",
            data_type="test",
            policy_id="p1",
            classification_tier=DataClassificationTier.INTERNAL,
            retention_until=datetime.now(UTC),
        )
        assert record.status == RetentionStatus.ACTIVE
        assert record.legal_hold is False
        assert record.constitutional_hash == "608508a9bd224290"
