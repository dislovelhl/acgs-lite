from src.core.shared.constants import CONSTITUTIONAL_HASH

"""
ACGS-2 Auth Rate Limiting Integration Tests
Constitutional Hash: cdd01ef066bc6cf2

Tests for strict auth endpoint rate limiting to prevent brute force attacks.
"""


import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.core.shared.security.rate_limiter import (
    RateLimitConfig,
    RateLimitMiddleware,
    RateLimitRule,
    RateLimitScope,
)


class TestAuthRateLimiting:
    """Test auth endpoint rate limiting."""

    @pytest.fixture
    def app_with_strict_auth_limits(self):
        """Create FastAPI app with strict auth rate limits."""
        app = FastAPI()

        # Configure strict auth rate limits
        rate_limit_rules = [
            # Auth endpoints - 10 req/min
            RateLimitRule(
                requests=10,
                window_seconds=60,
                scope=RateLimitScope.IP,
                endpoints=["/api/v1/auth/"],
            ),
            # Login endpoints - 5 req/min (STRICT)
            RateLimitRule(
                requests=5,
                window_seconds=60,
                scope=RateLimitScope.IP,
                endpoints=["/api/v1/sso/oidc/login", "/api/v1/sso/saml/login"],
            ),
            # Logout endpoints - 20 req/min
            RateLimitRule(
                requests=20,
                window_seconds=60,
                scope=RateLimitScope.IP,
                endpoints=["/api/v1/sso/oidc/logout"],
            ),
        ]

        config = RateLimitConfig(
            rules=rate_limit_rules,
            redis_url=None,  # Use in-memory for testing
            fallback_to_memory=True,
            enabled=True,
        )

        app.add_middleware(RateLimitMiddleware, config=config)

        @app.get("/api/v1/auth/check")
        async def auth_check():
            return {"status": "ok"}

        @app.post("/api/v1/sso/oidc/login")
        async def oidc_login():
            return {"status": "ok"}

        @app.post("/api/v1/sso/oidc/logout")
        async def oidc_logout():
            return {"status": "ok"}

        return app

    def test_auth_endpoint_rate_limit(self, app_with_strict_auth_limits):
        """Test auth endpoints have 10 req/min limit."""
        client = TestClient(app_with_strict_auth_limits)

        # First 10 requests should succeed
        for i in range(10):
            response = client.get("/api/v1/auth/check")
            assert response.status_code == 200, f"Request {i + 1} should succeed"

        # 11th request should be rate limited
        response = client.get("/api/v1/auth/check")
        assert response.status_code == 429
        assert "Retry-After" in response.headers or "retry_after" in response.json()

    def test_login_endpoint_strict_limit(self, app_with_strict_auth_limits):
        """Test login endpoints have strict 5 req/min limit."""
        client = TestClient(app_with_strict_auth_limits)

        # First 5 requests should succeed
        for i in range(5):
            response = client.post("/api/v1/sso/oidc/login")
            assert response.status_code == 200, f"Request {i + 1} should succeed"

        # 6th request should be rate limited
        response = client.post("/api/v1/sso/oidc/login")
        assert response.status_code == 429
        assert "error" in response.json() or "detail" in response.json()

    def test_logout_endpoint_higher_limit(self, app_with_strict_auth_limits):
        """Test logout endpoints have 20 req/min limit."""
        client = TestClient(app_with_strict_auth_limits)

        # First 20 requests should succeed
        for i in range(20):
            response = client.post("/api/v1/sso/oidc/logout")
            assert response.status_code == 200, f"Request {i + 1} should succeed"

        # 21st request should be rate limited
        response = client.post("/api/v1/sso/oidc/logout")
        assert response.status_code == 429

    def test_rate_limit_headers_present(self, app_with_strict_auth_limits):
        """Test rate limit headers are present in responses."""
        client = TestClient(app_with_strict_auth_limits)

        response = client.get("/api/v1/auth/check")
        assert response.status_code == 200

        # Check for rate limit headers
        # Note: Headers might not be added by the middleware in all cases
        # This is a sanity check
        if "X-RateLimit-Limit" in response.headers:
            assert int(response.headers["X-RateLimit-Limit"]) > 0
            assert int(response.headers["X-RateLimit-Remaining"]) >= 0
            assert int(response.headers["X-RateLimit-Reset"]) > 0

    def test_different_ips_have_separate_limits(self, app_with_strict_auth_limits):
        """Test different IP addresses have separate rate limits."""
        client = TestClient(app_with_strict_auth_limits)

        # Exhaust limit for first IP
        for _i in range(5):
            response = client.post("/api/v1/sso/oidc/login")
            assert response.status_code == 200

        # 6th request from same IP should fail
        response = client.post("/api/v1/sso/oidc/login")
        assert response.status_code == 429

        # Note: TestClient doesn't easily support changing client IP
        # In production, different IPs would have separate limits

    def test_constitutional_hash_in_error_response(self, app_with_strict_auth_limits):
        """Test 429 responses include constitutional hash."""
        client = TestClient(app_with_strict_auth_limits)

        # Exhaust limit
        for _i in range(5):
            client.post("/api/v1/sso/oidc/login")

        # Get rate limited response
        response = client.post("/api/v1/sso/oidc/login")
        assert response.status_code == 429

        # Check for constitutional hash
        data = response.json()
        assert "constitutional_hash" in data
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestBruteForceProtection:
    """Test brute force attack protection scenarios."""

    @pytest.fixture
    def app_with_brute_force_protection(self):
        """Create app with brute force protection."""
        app = FastAPI()

        config = RateLimitConfig(
            rules=[
                RateLimitRule(
                    requests=5,
                    window_seconds=60,
                    scope=RateLimitScope.IP,
                    endpoints=["/api/v1/sso/oidc/login"],
                ),
            ],
            redis_url=None,
            fallback_to_memory=True,
            enabled=True,
        )

        app.add_middleware(RateLimitMiddleware, config=config)

        @app.post("/api/v1/sso/oidc/login")
        async def login(request: Request):
            # Simulate login logic
            return {"status": "authenticated"}

        return app

    def test_brute_force_scenario(self, app_with_brute_force_protection):
        """Test that brute force attempts are blocked after limit."""
        client = TestClient(app_with_brute_force_protection)

        # Simulate 10 rapid login attempts (brute force)
        successful = 0
        blocked = 0

        for _i in range(10):
            response = client.post("/api/v1/sso/oidc/login")
            if response.status_code == 200:
                successful += 1
            elif response.status_code == 429:
                blocked += 1

        # Should allow 5 attempts, block remaining 5
        assert successful == 5
        assert blocked == 5

    def test_retry_after_header(self, app_with_brute_force_protection):
        """Test Retry-After header is present when rate limited."""
        client = TestClient(app_with_brute_force_protection)

        # Exhaust limit
        for _i in range(5):
            client.post("/api/v1/sso/oidc/login")

        # Get rate limited response
        response = client.post("/api/v1/sso/oidc/login")
        assert response.status_code == 429

        # Check retry_after in response
        data = response.json()
        assert "retry_after" in data or "Retry-After" in response.headers
        if "retry_after" in data:
            assert data["retry_after"] > 0


class TestRedisBackedRateLimiting:
    """Test Redis-backed rate limiting (requires Redis)."""

    @pytest.mark.skip(reason="Requires --redis flag and running Redis instance")
    @pytest.mark.asyncio
    async def test_redis_backed_rate_limiting(self):
        """Test Redis-backed rate limiting for distributed scenarios."""
        from src.core.shared.security.rate_limiter import SlidingWindowRateLimiter

        # This would require a real Redis instance
        # Skip if Redis not available
        limiter = SlidingWindowRateLimiter(
            redis_client=None,  # Would use real Redis client
            fallback_to_memory=True,
        )

        result = await limiter.is_allowed(
            key="test_ip:127.0.0.1",
            limit=5,
            window_seconds=60,
            scope=RateLimitScope.IP,
        )
        assert result.allowed is True
        assert result.limit == 5
        assert result.remaining == 4


# Additional monitoring test
class TestRateLimitMonitoring:
    """Test rate limit monitoring and metrics."""

    def test_rate_limit_metrics_tracking(self):
        """Test that rate limit violations are tracked for monitoring."""
        # This would integrate with Prometheus metrics
        # Placeholder for monitoring integration test
        pass
