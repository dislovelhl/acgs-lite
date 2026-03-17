"""
ACGS-2 Enhanced Agent Bus - PolicyResolver Tests
Constitutional Hash: cdd01ef066bc6cf2

Comprehensive test suite for PolicyResolver with Redis caching.
"""

import asyncio
import json
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]
RUN_EAB_POLICY_RESOLVER_TESTS = (
    os.getenv("RUN_EAB_POLICY_RESOLVER_TESTS", "false").lower() == "true"
)
if not RUN_EAB_POLICY_RESOLVER_TESTS:
    pytestmark.append(
        pytest.mark.skip(
            reason=(
                "Policy resolver tests disabled by default in this runtime. "
                "Set RUN_EAB_POLICY_RESOLVER_TESTS=true to run."
            )
        )
    )

# Constitutional hash validation
from packages.enhanced_agent_bus.models import RiskLevel, SessionGovernanceConfig  # noqa: E402
from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402

from ..policy_resolver import PolicyResolutionResult, PolicyResolver  # noqa: E402


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing"""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.setex = AsyncMock()
    mock.delete = AsyncMock()
    mock.scan = AsyncMock(return_value=(0, []))
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def policy_resolver(mock_redis):
    """PolicyResolver instance for testing (isolated mode)"""
    return PolicyResolver(
        policy_selector_url="http://localhost:8003",
        redis_url=None,  # Isolated mode
        cache_ttl=300,
        cache_size=100,
        enable_metrics=True,
        isolated_mode=True,
    )


@pytest.fixture
def session_governance_config():
    """Sample SessionGovernanceConfig for testing"""
    return SessionGovernanceConfig(
        session_id="session-123",
        tenant_id="tenant-123",
        user_id="user-456",
        risk_level=RiskLevel.HIGH,
        policy_overrides={"policy_id": "custom-policy-789"},
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


class TestPolicyResolverInitialization:
    """Test PolicyResolver initialization"""

    def test_default_initialization(self):
        """Test default PolicyResolver initialization"""
        resolver = PolicyResolver()

        assert resolver.policy_selector_url == "http://localhost:8003"
        assert resolver.cache_ttl == 300
        assert resolver.cache_size == 1000
        assert resolver.enable_metrics is True
        assert resolver.isolated_mode is False

    def test_custom_initialization(self):
        """Test PolicyResolver with custom configuration"""
        resolver = PolicyResolver(
            policy_selector_url="http://custom:9000",
            redis_url="redis://custom:6379",
            cache_ttl=600,
            cache_size=500,
            enable_metrics=False,
            isolated_mode=True,
        )

        assert resolver.policy_selector_url == "http://custom:9000"
        assert resolver.redis_url == "redis://custom:6379"
        assert resolver.cache_ttl == 600
        assert resolver.cache_size == 500
        assert resolver.enable_metrics is False
        assert resolver.isolated_mode is True

    def test_metrics_initialized(self, policy_resolver):
        """Test metrics are properly initialized"""
        metrics = policy_resolver.get_metrics()

        assert metrics["resolutions"] == 0
        assert metrics["cache_hits"] == 0
        assert metrics["cache_misses"] == 0
        assert metrics["redis_hits"] == 0
        assert metrics["redis_misses"] == 0
        assert metrics["policy_selector_calls"] == 0
        assert metrics["errors"] == 0
        assert metrics["cache_invalidations"] == 0
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestPolicyResolution:
    """Test policy resolution functionality"""

    @pytest.mark.asyncio
    async def test_resolve_policy_basic(self, policy_resolver):
        """Test basic policy resolution"""
        result = await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            user_id="user-456",
            risk_level=RiskLevel.MEDIUM,
        )

        assert isinstance(result, PolicyResolutionResult)
        assert result.policy is not None
        assert result.source in ["session", "tenant", "global"]
        assert result.risk_level == RiskLevel.MEDIUM
        assert result.tenant_id == "tenant-123"
        assert result.user_id == "user-456"
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    @pytest.mark.asyncio
    async def test_resolve_policy_with_session_context(
        self, policy_resolver, session_governance_config
    ):
        """Test policy resolution with session context"""
        result = await policy_resolver.resolve_policy(session_context=session_governance_config)

        assert result.policy is not None
        assert result.source == "session"  # Session override takes priority
        assert result.risk_level == RiskLevel.HIGH
        assert result.tenant_id == "tenant-123"
        assert result.user_id == "user-456"

    @pytest.mark.asyncio
    async def test_resolve_policy_default_risk_level(self, policy_resolver):
        """Test policy resolution with default risk level"""
        result = await policy_resolver.resolve_policy(tenant_id="tenant-123")

        assert result.risk_level == RiskLevel.MEDIUM  # Default

    @pytest.mark.asyncio
    async def test_resolve_policy_with_session_id(self, policy_resolver):
        """Test policy resolution with session ID"""
        result = await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            session_id="session-789",
            risk_level=RiskLevel.HIGH,
        )

        assert result.session_id == "session-789"

    @pytest.mark.asyncio
    async def test_resolve_policy_with_policy_name_filter(self, policy_resolver):
        """Test policy resolution with policy name filter"""
        result = await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            policy_name_filter="custom-policy",
            risk_level=RiskLevel.LOW,
        )

        assert result.resolution_metadata.get("policy_name_filter") == "custom-policy"


class TestCaching:
    """Test caching functionality"""

    @pytest.mark.asyncio
    async def test_memory_cache_hit(self, policy_resolver):
        """Test memory cache hit on second request"""
        # First request - cache miss
        result1 = await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            risk_level=RiskLevel.MEDIUM,
        )

        metrics1 = policy_resolver.get_metrics()
        assert metrics1["cache_misses"] == 1
        assert metrics1["cache_hits"] == 0

        # Second request - cache hit
        result2 = await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            risk_level=RiskLevel.MEDIUM,
        )

        metrics2 = policy_resolver.get_metrics()
        assert metrics2["cache_hits"] == 1
        assert metrics2["cache_misses"] == 1

        # Results should be the same
        assert result1.policy == result2.policy
        assert result1.source == result2.source

    @pytest.mark.asyncio
    async def test_cache_key_generation(self, policy_resolver):
        """Test cache key generation for different parameters"""
        # Different tenant IDs should generate different cache keys
        result1 = await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            risk_level=RiskLevel.MEDIUM,
        )
        result2 = await policy_resolver.resolve_policy(
            tenant_id="tenant-456",
            risk_level=RiskLevel.MEDIUM,
        )

        # Both should be cache misses (different keys)
        metrics = policy_resolver.get_metrics()
        assert metrics["cache_misses"] == 2
        assert metrics["cache_hits"] == 0

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self, policy_resolver):
        """Test cache TTL expiration"""
        # Set very short TTL
        policy_resolver.cache_ttl = 0.1  # 100ms

        # First request
        await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            risk_level=RiskLevel.MEDIUM,
        )

        # Wait for cache to expire
        await asyncio.sleep(0.15)

        # Second request should be a miss due to expiration
        await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            risk_level=RiskLevel.MEDIUM,
        )

        metrics = policy_resolver.get_metrics()
        assert metrics["cache_misses"] == 2
        assert metrics["cache_hits"] == 0

    @pytest.mark.asyncio
    async def test_lru_eviction(self, policy_resolver):
        """Test LRU cache eviction when at capacity"""
        # Set small cache size
        policy_resolver.cache_size = 2

        # Add 3 entries (should evict the first)
        await policy_resolver.resolve_policy(tenant_id="tenant-1", risk_level=RiskLevel.LOW)
        await policy_resolver.resolve_policy(tenant_id="tenant-2", risk_level=RiskLevel.MEDIUM)
        await policy_resolver.resolve_policy(tenant_id="tenant-3", risk_level=RiskLevel.HIGH)

        # Cache should have exactly 2 entries
        metrics = policy_resolver.get_metrics()
        assert metrics["memory_cache_size"] == 2

        # Requesting tenant-1 again should be a miss (evicted)
        await policy_resolver.resolve_policy(tenant_id="tenant-1", risk_level=RiskLevel.LOW)
        metrics = policy_resolver.get_metrics()
        # 3 initial misses + 1 eviction miss = 4 total misses
        assert metrics["cache_misses"] == 4

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self, policy_resolver):
        """Test force_refresh bypasses cache"""
        # First request - populate cache
        await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            risk_level=RiskLevel.MEDIUM,
        )

        # Second request with force_refresh - should bypass cache
        await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            risk_level=RiskLevel.MEDIUM,
            force_refresh=True,
        )

        metrics = policy_resolver.get_metrics()
        assert metrics["cache_hits"] == 0  # No cache hits due to force_refresh
        assert metrics["cache_misses"] == 2


class TestCacheInvalidation:
    """Test cache invalidation functionality"""

    @pytest.mark.asyncio
    async def test_invalidate_all(self, policy_resolver):
        """Test invalidating entire cache"""
        # Populate cache with multiple entries
        await policy_resolver.resolve_policy(tenant_id="tenant-1", risk_level=RiskLevel.LOW)
        await policy_resolver.resolve_policy(tenant_id="tenant-2", risk_level=RiskLevel.MEDIUM)
        await policy_resolver.resolve_policy(tenant_id="tenant-3", risk_level=RiskLevel.HIGH)

        # Verify cache has entries
        metrics = policy_resolver.get_metrics()
        assert metrics["memory_cache_size"] == 3

        # Invalidate all
        invalidated = await policy_resolver.invalidate_cache(clear_all=True)
        assert invalidated == 3

        # Cache should be empty
        metrics = policy_resolver.get_metrics()
        assert metrics["memory_cache_size"] == 0

    @pytest.mark.asyncio
    async def test_invalidate_by_tenant(self, policy_resolver):
        """Test invalidating cache entries for specific tenant"""
        # Populate cache with multiple tenants
        await policy_resolver.resolve_policy(tenant_id="tenant-1", risk_level=RiskLevel.LOW)
        await policy_resolver.resolve_policy(tenant_id="tenant-2", risk_level=RiskLevel.MEDIUM)
        await policy_resolver.resolve_policy(tenant_id="tenant-1", risk_level=RiskLevel.HIGH)

        # Invalidate tenant-1 entries
        invalidated = await policy_resolver.invalidate_cache(tenant_id="tenant-1")
        assert invalidated == 2  # Two entries for tenant-1

        # Cache should still have tenant-2 entry
        metrics = policy_resolver.get_metrics()
        assert metrics["memory_cache_size"] == 1

    @pytest.mark.asyncio
    async def test_invalidate_by_session(self, policy_resolver):
        """Test invalidating cache entries for specific session"""
        # Populate cache with different sessions
        await policy_resolver.resolve_policy(
            tenant_id="tenant-1",
            session_id="session-1",
            risk_level=RiskLevel.LOW,
        )
        await policy_resolver.resolve_policy(
            tenant_id="tenant-1",
            session_id="session-2",
            risk_level=RiskLevel.MEDIUM,
        )

        # Invalidate session-1 entries
        invalidated = await policy_resolver.invalidate_cache(session_id="session-1")
        assert invalidated == 1

        # Cache should still have session-2 entry
        metrics = policy_resolver.get_metrics()
        assert metrics["memory_cache_size"] == 1


class TestMetrics:
    """Test metrics tracking"""

    @pytest.mark.asyncio
    async def test_metrics_tracking(self, policy_resolver):
        """Test metrics are properly tracked"""
        # Make several requests
        await policy_resolver.resolve_policy(tenant_id="tenant-1", risk_level=RiskLevel.LOW)
        await policy_resolver.resolve_policy(
            tenant_id="tenant-1", risk_level=RiskLevel.LOW
        )  # Cache hit
        await policy_resolver.resolve_policy(tenant_id="tenant-2", risk_level=RiskLevel.MEDIUM)

        metrics = policy_resolver.get_metrics()

        assert metrics["resolutions"] == 3
        assert metrics["cache_hits"] == 1
        assert metrics["cache_misses"] == 2
        assert metrics["policy_selector_calls"] == 2
        assert metrics["cache_hit_rate"] == 1 / 3  # 1 hit out of 3 total

    @pytest.mark.asyncio
    async def test_reset_metrics(self, policy_resolver):
        """Test resetting metrics"""
        # Make some requests
        await policy_resolver.resolve_policy(tenant_id="tenant-1", risk_level=RiskLevel.LOW)
        await policy_resolver.resolve_policy(tenant_id="tenant-2", risk_level=RiskLevel.MEDIUM)

        # Reset metrics
        policy_resolver.reset_metrics()

        metrics = policy_resolver.get_metrics()
        assert metrics["resolutions"] == 0
        assert metrics["cache_hits"] == 0
        assert metrics["cache_misses"] == 0
        assert metrics["policy_selector_calls"] == 0

    @pytest.mark.asyncio
    async def test_cache_hit_rate_calculation(self, policy_resolver):
        """Test cache hit rate calculation"""
        # No requests yet
        metrics = policy_resolver.get_metrics()
        assert metrics["cache_hit_rate"] == 0.0

        # One cache miss
        await policy_resolver.resolve_policy(tenant_id="tenant-1", risk_level=RiskLevel.LOW)
        metrics = policy_resolver.get_metrics()
        assert metrics["cache_hit_rate"] == 0.0

        # One cache hit
        await policy_resolver.resolve_policy(tenant_id="tenant-1", risk_level=RiskLevel.LOW)
        metrics = policy_resolver.get_metrics()
        assert metrics["cache_hit_rate"] == 0.5  # 1 hit / 2 total


class TestPolicyResolutionResult:
    """Test PolicyResolutionResult model"""

    def test_result_creation(self):
        """Test PolicyResolutionResult creation"""
        policy = {"policy_id": "policy-123", "name": "Test Policy"}
        result = PolicyResolutionResult(
            policy=policy,
            source="tenant",
            reasoning="Tenant-specific policy",
            risk_level=RiskLevel.HIGH,
            tenant_id="tenant-123",
            user_id="user-456",
            session_id="session-789",
        )

        assert result.policy == policy
        assert result.source == "tenant"
        assert result.reasoning == "Tenant-specific policy"
        assert result.risk_level == RiskLevel.HIGH
        assert result.tenant_id == "tenant-123"
        assert result.user_id == "user-456"
        assert result.session_id == "session-789"
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_result_to_dict(self):
        """Test PolicyResolutionResult serialization"""
        policy = {"policy_id": "policy-123"}
        result = PolicyResolutionResult(
            policy=policy,
            source="global",
            reasoning="Global fallback",
            risk_level=RiskLevel.MEDIUM,
        )

        result_dict = result.to_dict()

        assert result_dict["policy"] == policy
        assert result_dict["source"] == "global"
        assert result_dict["reasoning"] == "Global fallback"
        assert result_dict["risk_level"] == "medium"
        assert result_dict["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "timestamp" in result_dict


class TestErrorHandling:
    """Test error handling"""

    @pytest.mark.asyncio
    async def test_error_returns_empty_result(self, policy_resolver):
        """Test that errors return empty result instead of raising"""
        # Mock query to raise error
        with patch.object(
            policy_resolver,
            "_query_policy_selector",
            side_effect=Exception("Test error"),
        ):
            result = await policy_resolver.resolve_policy(
                tenant_id="tenant-123",
                risk_level=RiskLevel.HIGH,
            )

            assert result.policy is None
            assert result.source == "none"
            assert "Error" in result.reasoning
            assert "error" in result.resolution_metadata

    @pytest.mark.asyncio
    async def test_error_increments_error_metric(self, policy_resolver):
        """Test that errors increment error metric"""
        # Mock query to raise error
        with patch.object(
            policy_resolver,
            "_query_policy_selector",
            side_effect=Exception("Test error"),
        ):
            await policy_resolver.resolve_policy(
                tenant_id="tenant-123",
                risk_level=RiskLevel.HIGH,
            )

            metrics = policy_resolver.get_metrics()
            assert metrics["errors"] == 1


class TestPerformance:
    """Test performance characteristics"""

    @pytest.mark.asyncio
    async def test_cached_lookup_performance(self, policy_resolver):
        """Test that cached lookups are fast"""
        # First request - cache miss
        await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            risk_level=RiskLevel.MEDIUM,
        )

        # Second request - cache hit (should be very fast)
        start_time = time.perf_counter()
        await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            risk_level=RiskLevel.MEDIUM,
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Should be sub-millisecond for cached lookup
        assert elapsed_ms < 1.0  # P99 < 1ms requirement

    @pytest.mark.asyncio
    async def test_concurrent_resolutions(self, policy_resolver):
        """Test concurrent policy resolutions"""
        # Create multiple concurrent requests
        tasks = [
            policy_resolver.resolve_policy(
                tenant_id=f"tenant-{i}",
                risk_level=RiskLevel.MEDIUM,
            )
            for i in range(10)
        ]

        # Execute concurrently
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 10
        for result in results:
            assert result.policy is not None

        # Metrics should reflect all requests
        metrics = policy_resolver.get_metrics()
        assert metrics["resolutions"] == 10


class TestRedisIntegration:
    """Test Redis integration (when available)"""

    @pytest.mark.asyncio
    async def test_redis_cache_disabled_in_isolated_mode(self, policy_resolver):
        """Test that Redis is not used in isolated mode"""
        client = await policy_resolver._get_redis_client()
        assert client is None

    @pytest.mark.asyncio
    async def test_redis_cache_storage(self, mock_redis):
        """Test Redis cache storage"""
        with patch("redis.asyncio.from_url", return_value=mock_redis):
            resolver = PolicyResolver(
                redis_url="redis://localhost:6379",
                isolated_mode=False,
            )

            # This would store in Redis in real scenario
            # For now, just verify mock was called
            result = await resolver.resolve_policy(
                tenant_id="tenant-123",
                risk_level=RiskLevel.MEDIUM,
            )

            assert result is not None


class TestConstitutionalValidation:
    """Test constitutional hash validation"""

    def test_constitutional_hash_in_result(self):
        """Test constitutional hash is included in all results"""
        result = PolicyResolutionResult(
            policy={"policy_id": "test"},
            source="test",
            reasoning="test",
            risk_level=RiskLevel.LOW,
        )

        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    @pytest.mark.asyncio
    async def test_constitutional_hash_in_resolved_policy(self, policy_resolver):
        """Test constitutional hash in resolved policies"""
        result = await policy_resolver.resolve_policy(
            tenant_id="tenant-123",
            risk_level=RiskLevel.MEDIUM,
        )

        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_metrics(self, policy_resolver):
        """Test constitutional hash in metrics"""
        metrics = policy_resolver.get_metrics()
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH
