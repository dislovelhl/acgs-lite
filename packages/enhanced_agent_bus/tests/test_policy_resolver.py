"""
ACGS-2 Enhanced Agent Bus - PolicyResolver Tests
Constitutional Hash: 608508a9bd224290

Comprehensive test suite for PolicyResolver covering:
- Initialization and configuration
- Policy resolution (isolated + service modes)
- In-memory LRU cache behavior
- Redis cache integration (mocked)
- Cache invalidation
- Metrics tracking
- Error handling and fallback paths
- PolicyResolutionResult serialization
- Cache key hashing
- Resource cleanup
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from enhanced_agent_bus.models import RiskLevel, SessionGovernanceConfig
from enhanced_agent_bus.policy_resolver import (
    DEFAULT_CACHE_HASH_MODE,
    PolicyResolutionResult,
    PolicyResolver,
    _cached_policy_key_hash,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def resolver_isolated():
    """PolicyResolver in isolated mode (no Redis, no HTTP)."""
    return PolicyResolver(
        policy_selector_url="http://test-selector:8003",
        redis_url=None,
        cache_ttl=300,
        cache_size=100,
        enable_metrics=True,
        isolated_mode=True,
    )


@pytest.fixture()
def resolver_connected():
    """PolicyResolver wired to mocked external deps."""
    return PolicyResolver(
        policy_selector_url="http://test-selector:8003",
        redis_url="redis://localhost:6379",
        cache_ttl=60,
        cache_size=50,
        enable_metrics=True,
        isolated_mode=False,
    )


@pytest.fixture()
def mock_redis_client():
    """Async mock for a redis.asyncio.Redis client."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.setex = AsyncMock()
    client.delete = AsyncMock()
    client.scan = AsyncMock(return_value=(0, []))
    client.close = AsyncMock()
    return client


@pytest.fixture()
def session_config():
    """Sample SessionGovernanceConfig."""
    return SessionGovernanceConfig(
        session_id="sess-001",
        tenant_id="tenant-abc",
        user_id="user-xyz",
        risk_level=RiskLevel.HIGH,
        policy_overrides={"override_key": "override_val"},
    )


@pytest.fixture()
def session_config_no_overrides():
    """SessionGovernanceConfig without policy overrides."""
    return SessionGovernanceConfig(
        session_id="sess-002",
        tenant_id="tenant-def",
        user_id="user-uvw",
        risk_level=RiskLevel.LOW,
    )


# ---------------------------------------------------------------------------
# PolicyResolutionResult
# ---------------------------------------------------------------------------


class TestPolicyResolutionResult:
    def test_creation_with_defaults(self):
        result = PolicyResolutionResult(
            policy={"id": "p1"},
            source="global",
            reasoning="fallback",
            risk_level=RiskLevel.MEDIUM,
        )
        assert result.policy == {"id": "p1"}
        assert result.source == "global"
        assert result.reasoning == "fallback"
        assert result.risk_level == RiskLevel.MEDIUM
        assert result.tenant_id is None
        assert result.user_id is None
        assert result.session_id is None
        assert result.resolution_metadata == {}
        assert result.timestamp is not None

    def test_creation_with_all_fields(self):
        meta = {"key": "value"}
        result = PolicyResolutionResult(
            policy={"id": "p2"},
            source="session",
            reasoning="override",
            risk_level=RiskLevel.CRITICAL,
            tenant_id="t1",
            user_id="u1",
            session_id="s1",
            resolution_metadata=meta,
        )
        assert result.tenant_id == "t1"
        assert result.user_id == "u1"
        assert result.session_id == "s1"
        assert result.resolution_metadata is meta

    def test_to_dict_serialization(self):
        result = PolicyResolutionResult(
            policy={"id": "p1"},
            source="tenant",
            reasoning="tenant match",
            risk_level=RiskLevel.HIGH,
            tenant_id="t1",
            user_id="u1",
            session_id="s1",
            resolution_metadata={"fallback": False},
        )
        d = result.to_dict()
        assert d["policy"] == {"id": "p1"}
        assert d["source"] == "tenant"
        assert d["reasoning"] == "tenant match"
        assert d["risk_level"] == "high"
        assert d["tenant_id"] == "t1"
        assert d["user_id"] == "u1"
        assert d["session_id"] == "s1"
        assert d["resolution_metadata"] == {"fallback": False}
        assert "timestamp" in d
        assert "constitutional_hash" in d

    def test_to_dict_with_string_risk_level(self):
        """When risk_level is a plain string, to_dict should use it directly."""
        result = PolicyResolutionResult(
            policy=None,
            source="none",
            reasoning="error",
            risk_level="custom_level",
        )
        d = result.to_dict()
        assert d["risk_level"] == "custom_level"

    def test_none_policy(self):
        result = PolicyResolutionResult(
            policy=None,
            source="none",
            reasoning="no policy found",
            risk_level=RiskLevel.LOW,
        )
        assert result.policy is None
        assert result.to_dict()["policy"] is None


# ---------------------------------------------------------------------------
# PolicyResolver - Initialization
# ---------------------------------------------------------------------------


class TestPolicyResolverInit:
    def test_default_init(self):
        r = PolicyResolver()
        assert r.policy_selector_url == "http://localhost:8003"
        assert r.redis_url is None
        assert r.cache_ttl == 300
        assert r.cache_size == 1000
        assert r.enable_metrics is True
        assert r.isolated_mode is False
        assert r.cache_hash_mode == DEFAULT_CACHE_HASH_MODE

    def test_custom_init(self):
        r = PolicyResolver(
            policy_selector_url="http://custom:9999",
            redis_url="redis://r:6379",
            cache_ttl=10,
            cache_size=5,
            enable_metrics=False,
            isolated_mode=True,
            cache_hash_mode="sha256",
        )
        assert r.policy_selector_url == "http://custom:9999"
        assert r.redis_url == "redis://r:6379"
        assert r.cache_ttl == 10
        assert r.cache_size == 5
        assert r.enable_metrics is False
        assert r.isolated_mode is True

    def test_invalid_cache_hash_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            PolicyResolver(cache_hash_mode="bogus")

    def test_metrics_initialized_to_zero(self, resolver_isolated):
        m = resolver_isolated.get_metrics()
        assert m["resolutions"] == 0
        assert m["cache_hits"] == 0
        assert m["cache_misses"] == 0
        assert m["errors"] == 0


# ---------------------------------------------------------------------------
# Parameter normalization
# ---------------------------------------------------------------------------


class TestNormalizeParameters:
    def test_defaults_risk_to_medium(self, resolver_isolated):
        result = resolver_isolated._normalize_resolution_parameters(
            None, None, None, None, None, None
        )
        assert result[2] == RiskLevel.MEDIUM

    def test_session_context_fills_gaps(self, resolver_isolated, session_config):
        result = resolver_isolated._normalize_resolution_parameters(
            None, None, None, None, session_config, None
        )
        tenant_id, user_id, risk_level, _, _ = result
        assert tenant_id == "tenant-abc"
        assert user_id == "user-xyz"
        assert risk_level == RiskLevel.HIGH

    def test_explicit_params_override_session_context(self, resolver_isolated, session_config):
        result = resolver_isolated._normalize_resolution_parameters(
            "explicit-tenant", "explicit-user", RiskLevel.LOW, "s1", session_config, "filter"
        )
        tenant_id, user_id, risk_level, session_id, name_filter = result
        assert tenant_id == "explicit-tenant"
        assert user_id == "explicit-user"
        assert risk_level == RiskLevel.LOW
        assert session_id == "s1"
        assert name_filter == "filter"


# ---------------------------------------------------------------------------
# Cache key generation
# ---------------------------------------------------------------------------


class TestCacheKeyGeneration:
    def test_deterministic(self, resolver_isolated):
        k1 = resolver_isolated._generate_cache_key("t", "u", RiskLevel.LOW, "s", "f")
        k2 = resolver_isolated._generate_cache_key("t", "u", RiskLevel.LOW, "s", "f")
        assert k1 == k2

    def test_different_inputs_different_keys(self, resolver_isolated):
        k1 = resolver_isolated._generate_cache_key("t1", "u", RiskLevel.LOW, None, None)
        k2 = resolver_isolated._generate_cache_key("t2", "u", RiskLevel.LOW, None, None)
        assert k1 != k2

    def test_key_starts_with_policy_prefix(self, resolver_isolated):
        k = resolver_isolated._generate_cache_key(None, None, RiskLevel.MEDIUM, None, None)
        assert k.startswith("policy:")

    def test_none_values_get_defaults(self, resolver_isolated):
        k = resolver_isolated._generate_cache_key(None, None, RiskLevel.MEDIUM, None, None)
        assert isinstance(k, str)
        assert len(k) > len("policy:")


class TestCachedPolicyKeyHash:
    def test_sha256_mode(self):
        _cached_policy_key_hash.cache_clear()
        result = _cached_policy_key_hash("test:key", "sha256")
        assert result.startswith("policy:")
        assert len(result) == len("policy:") + 16  # 16 hex chars

    def test_same_input_same_output(self):
        _cached_policy_key_hash.cache_clear()
        a = _cached_policy_key_hash("x", "sha256")
        b = _cached_policy_key_hash("x", "sha256")
        assert a == b


# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------


class TestMemoryCache:
    @pytest.mark.asyncio
    async def test_add_and_get(self, resolver_isolated):
        result = PolicyResolutionResult(
            policy={"id": "p1"}, source="tenant", reasoning="r", risk_level=RiskLevel.LOW
        )
        key = "policy:testkey1"
        await resolver_isolated._add_to_memory_cache(key, result)
        fetched = await resolver_isolated._get_from_memory_cache(key)
        assert fetched is not None
        assert fetched.policy == {"id": "p1"}

    @pytest.mark.asyncio
    async def test_miss_returns_none(self, resolver_isolated):
        fetched = await resolver_isolated._get_from_memory_cache("policy:nonexistent")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, resolver_isolated):
        resolver_isolated.cache_ttl = 0.05
        result = PolicyResolutionResult(
            policy={"id": "p1"}, source="global", reasoning="r", risk_level=RiskLevel.LOW
        )
        key = "policy:ttltest"
        await resolver_isolated._add_to_memory_cache(key, result)
        await asyncio.sleep(0.08)
        fetched = await resolver_isolated._get_from_memory_cache(key)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self, resolver_isolated):
        resolver_isolated.cache_size = 2
        r1 = PolicyResolutionResult(
            policy={"id": "1"}, source="a", reasoning="r", risk_level=RiskLevel.LOW
        )
        r2 = PolicyResolutionResult(
            policy={"id": "2"}, source="b", reasoning="r", risk_level=RiskLevel.LOW
        )
        r3 = PolicyResolutionResult(
            policy={"id": "3"}, source="c", reasoning="r", risk_level=RiskLevel.LOW
        )
        await resolver_isolated._add_to_memory_cache("policy:k1", r1)
        await resolver_isolated._add_to_memory_cache("policy:k2", r2)
        await resolver_isolated._add_to_memory_cache("policy:k3", r3)
        # k1 should be evicted
        assert await resolver_isolated._get_from_memory_cache("policy:k1") is None
        assert await resolver_isolated._get_from_memory_cache("policy:k2") is not None
        assert await resolver_isolated._get_from_memory_cache("policy:k3") is not None


# ---------------------------------------------------------------------------
# Redis cache (mocked)
# ---------------------------------------------------------------------------


class TestRedisCache:
    @pytest.mark.asyncio
    async def test_isolated_mode_returns_none(self, resolver_isolated):
        client = await resolver_isolated._get_redis_client()
        assert client is None

    @pytest.mark.asyncio
    async def test_no_redis_url_returns_none(self):
        r = PolicyResolver(redis_url=None, isolated_mode=False)
        client = await r._get_redis_client()
        assert client is None

    @pytest.mark.asyncio
    async def test_get_from_redis_returns_none_when_no_client(self, resolver_isolated):
        result = await resolver_isolated._get_from_redis_cache("policy:k1")
        assert result is None

    @pytest.mark.asyncio
    async def test_add_to_redis_noop_when_no_client(self, resolver_isolated):
        result = PolicyResolutionResult(
            policy={"id": "p"}, source="s", reasoning="r", risk_level=RiskLevel.LOW
        )
        # Should not raise
        await resolver_isolated._add_to_redis_cache("policy:k1", result)

    @pytest.mark.asyncio
    async def test_get_from_redis_deserializes(self, resolver_connected, mock_redis_client):
        cached_data = json.dumps(
            {
                "policy": {"id": "cached"},
                "source": "cache",
                "reasoning": "from redis",
                "risk_level": "medium",
                "tenant_id": "t1",
                "user_id": "u1",
                "session_id": "s1",
                "resolution_metadata": {},
            }
        )
        mock_redis_client.get = AsyncMock(return_value=cached_data)
        resolver_connected._redis_client = mock_redis_client

        result = await resolver_connected._get_from_redis_cache("policy:k1")
        assert result is not None
        assert result.policy == {"id": "cached"}
        assert result.risk_level == RiskLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_get_from_redis_bad_json(self, resolver_connected, mock_redis_client):
        mock_redis_client.get = AsyncMock(return_value="not-json")
        resolver_connected._redis_client = mock_redis_client
        result = await resolver_connected._get_from_redis_cache("policy:k1")
        assert result is None

    @pytest.mark.asyncio
    async def test_add_to_redis_calls_setex(self, resolver_connected, mock_redis_client):
        resolver_connected._redis_client = mock_redis_client
        result = PolicyResolutionResult(
            policy={"id": "p"}, source="s", reasoning="r", risk_level=RiskLevel.LOW
        )
        await resolver_connected._add_to_redis_cache("policy:k1", result)
        mock_redis_client.setex.assert_awaited_once()
        args = mock_redis_client.setex.call_args
        assert args[0][0] == "policy:k1"
        assert args[0][1] == 60  # cache_ttl

    @pytest.mark.asyncio
    async def test_redis_miss_increments_metric(self, resolver_connected, mock_redis_client):
        mock_redis_client.get = AsyncMock(return_value=None)
        resolver_connected._redis_client = mock_redis_client
        await resolver_connected._get_from_redis_cache("policy:missing")
        assert resolver_connected._metrics["redis_misses"] == 1


# ---------------------------------------------------------------------------
# Policy resolution (isolated mode, end-to-end)
# ---------------------------------------------------------------------------


class TestResolvePolicy:
    @pytest.mark.asyncio
    async def test_basic_resolve_isolated(self, resolver_isolated):
        result = await resolver_isolated.resolve_policy(
            tenant_id="t1", user_id="u1", risk_level=RiskLevel.MEDIUM
        )
        assert isinstance(result, PolicyResolutionResult)
        assert result.policy is not None
        assert result.tenant_id == "t1"
        assert result.user_id == "u1"
        assert result.risk_level == RiskLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_resolve_defaults_risk_level(self, resolver_isolated):
        result = await resolver_isolated.resolve_policy(tenant_id="t1")
        assert result.risk_level == RiskLevel.MEDIUM

    @pytest.mark.asyncio
    async def test_resolve_with_session_context_overrides(self, resolver_isolated, session_config):
        result = await resolver_isolated.resolve_policy(session_context=session_config)
        assert result.tenant_id == "tenant-abc"
        assert result.user_id == "user-xyz"
        assert result.risk_level == RiskLevel.HIGH
        assert result.source == "session"

    @pytest.mark.asyncio
    async def test_resolve_with_session_context_no_overrides(
        self, resolver_isolated, session_config_no_overrides
    ):
        result = await resolver_isolated.resolve_policy(session_context=session_config_no_overrides)
        assert result.source == "tenant"  # tenant is set, no overrides

    @pytest.mark.asyncio
    async def test_resolve_global_fallback(self, resolver_isolated):
        result = await resolver_isolated.resolve_policy()
        assert result.source == "global"

    @pytest.mark.asyncio
    async def test_resolve_caches_result(self, resolver_isolated):
        await resolver_isolated.resolve_policy(tenant_id="t1", risk_level=RiskLevel.LOW)
        m1 = resolver_isolated.get_metrics()
        assert m1["cache_misses"] == 1

        await resolver_isolated.resolve_policy(tenant_id="t1", risk_level=RiskLevel.LOW)
        m2 = resolver_isolated.get_metrics()
        assert m2["cache_hits"] == 1
        assert m2["cache_misses"] == 1

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self, resolver_isolated):
        await resolver_isolated.resolve_policy(tenant_id="t1", risk_level=RiskLevel.LOW)
        await resolver_isolated.resolve_policy(
            tenant_id="t1", risk_level=RiskLevel.LOW, force_refresh=True
        )
        m = resolver_isolated.get_metrics()
        assert m["cache_hits"] == 0
        assert m["cache_misses"] == 2

    @pytest.mark.asyncio
    async def test_policy_name_filter_in_metadata(self, resolver_isolated):
        result = await resolver_isolated.resolve_policy(
            tenant_id="t1", policy_name_filter="my-policy", risk_level=RiskLevel.LOW
        )
        assert result.resolution_metadata.get("policy_name_filter") == "my-policy"

    @pytest.mark.asyncio
    async def test_session_id_propagated(self, resolver_isolated):
        result = await resolver_isolated.resolve_policy(
            tenant_id="t1", session_id="sess-99", risk_level=RiskLevel.LOW
        )
        assert result.session_id == "sess-99"


# ---------------------------------------------------------------------------
# Service resolution (non-isolated) with mocked HTTP
# ---------------------------------------------------------------------------


class TestResolveFromService:
    @pytest.mark.asyncio
    async def test_successful_http_resolution(self, resolver_connected):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "policy": {"id": "service-p1", "name": "Service Policy"},
            "source": "service",
            "reasoning": "matched tenant",
            "metadata": {"origin": "registry"},
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        resolver_connected._http_client = mock_client

        result = await resolver_connected.resolve_policy(tenant_id="t1", risk_level=RiskLevel.HIGH)
        assert result.policy == {"id": "service-p1", "name": "Service Policy"}
        assert result.source == "service"

    @pytest.mark.asyncio
    async def test_non_200_falls_back_to_mock(self, resolver_connected):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        resolver_connected._http_client = mock_client

        result = await resolver_connected.resolve_policy(
            tenant_id="t1", risk_level=RiskLevel.MEDIUM
        )
        # Should get fallback policy
        assert result.policy is not None
        assert result.resolution_metadata.get("fallback") is True

    @pytest.mark.asyncio
    async def test_http_error_falls_back_to_mock(self, resolver_connected):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        resolver_connected._http_client = mock_client

        result = await resolver_connected.resolve_policy(tenant_id="t1", risk_level=RiskLevel.LOW)
        assert result.policy is not None
        assert result.resolution_metadata.get("fallback") is True

    @pytest.mark.asyncio
    async def test_resolve_from_service_error_path(self, resolver_isolated):
        """When _query_policy_selector raises a caught exception, error result returned."""
        with patch.object(
            resolver_isolated,
            "_query_policy_selector",
            side_effect=ValueError("bad value"),
        ):
            result = await resolver_isolated.resolve_policy(
                tenant_id="t1", risk_level=RiskLevel.HIGH
            )
        assert result.policy is None
        assert result.source == "none"
        assert "bad value" in result.reasoning
        assert resolver_isolated._metrics["errors"] >= 1


# ---------------------------------------------------------------------------
# Default mock policy
# ---------------------------------------------------------------------------


class TestDefaultMockPolicy:
    def test_session_override_source(self, resolver_isolated, session_config):
        result = resolver_isolated._get_default_mock_policy(
            "t1", "u1", RiskLevel.HIGH, "s1", session_config, None
        )
        assert result.source == "session"

    def test_tenant_source(self, resolver_isolated):
        result = resolver_isolated._get_default_mock_policy(
            "t1", "u1", RiskLevel.MEDIUM, "s1", None, None
        )
        assert result.source == "tenant"
        assert "t1" in result.reasoning

    def test_global_source(self, resolver_isolated):
        result = resolver_isolated._get_default_mock_policy(
            None, None, RiskLevel.LOW, None, None, None
        )
        assert result.source == "global"

    def test_policy_name_filter_in_metadata(self, resolver_isolated):
        result = resolver_isolated._get_default_mock_policy(
            None, None, RiskLevel.LOW, None, None, "my-filter"
        )
        assert result.resolution_metadata["policy_name_filter"] == "my-filter"

    def test_policy_structure(self, resolver_isolated):
        result = resolver_isolated._get_default_mock_policy(
            "t1", None, RiskLevel.HIGH, None, None, None
        )
        p = result.policy
        assert "policy_id" in p
        assert "name" in p
        assert p["risk_level"] == "high"
        assert p["status"] == "active"
        assert "rules" in p


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------


class TestCacheInvalidation:
    @pytest.mark.asyncio
    async def test_clear_all(self, resolver_isolated):
        await resolver_isolated.resolve_policy(tenant_id="t1", risk_level=RiskLevel.LOW)
        await resolver_isolated.resolve_policy(tenant_id="t2", risk_level=RiskLevel.MEDIUM)
        assert resolver_isolated.get_metrics()["memory_cache_size"] == 2

        count = await resolver_isolated.invalidate_cache(clear_all=True)
        assert count == 2
        assert resolver_isolated.get_metrics()["memory_cache_size"] == 0

    @pytest.mark.asyncio
    async def test_invalidate_by_tenant(self, resolver_isolated):
        await resolver_isolated.resolve_policy(tenant_id="t1", risk_level=RiskLevel.LOW)
        await resolver_isolated.resolve_policy(tenant_id="t1", risk_level=RiskLevel.HIGH)
        await resolver_isolated.resolve_policy(tenant_id="t2", risk_level=RiskLevel.MEDIUM)

        count = await resolver_isolated.invalidate_cache(tenant_id="t1")
        assert count == 2
        assert resolver_isolated.get_metrics()["memory_cache_size"] == 1

    @pytest.mark.asyncio
    async def test_invalidate_by_session(self, resolver_isolated):
        await resolver_isolated.resolve_policy(
            tenant_id="t1", session_id="s1", risk_level=RiskLevel.LOW
        )
        await resolver_isolated.resolve_policy(
            tenant_id="t1", session_id="s2", risk_level=RiskLevel.LOW
        )
        count = await resolver_isolated.invalidate_cache(session_id="s1")
        assert count == 1

    @pytest.mark.asyncio
    async def test_invalidation_increments_metric(self, resolver_isolated):
        await resolver_isolated.invalidate_cache(clear_all=True)
        assert resolver_isolated._metrics["cache_invalidations"] == 1

    @pytest.mark.asyncio
    async def test_redis_clear_all(self, resolver_connected, mock_redis_client):
        mock_redis_client.scan = AsyncMock(
            side_effect=[
                (1, ["policy:a", "policy:b"]),
                (0, ["policy:c"]),
            ]
        )
        resolver_connected._redis_client = mock_redis_client
        count = await resolver_connected._clear_all_redis_cache(mock_redis_client)
        assert count == 3
        assert mock_redis_client.delete.await_count == 2

    @pytest.mark.asyncio
    async def test_invalidate_redis_no_client(self, resolver_isolated):
        count = await resolver_isolated._invalidate_redis_cache(None, None, True)
        assert count == 0


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    @pytest.mark.asyncio
    async def test_metrics_tracking(self, resolver_isolated):
        await resolver_isolated.resolve_policy(tenant_id="t1", risk_level=RiskLevel.LOW)
        await resolver_isolated.resolve_policy(tenant_id="t1", risk_level=RiskLevel.LOW)  # hit
        await resolver_isolated.resolve_policy(tenant_id="t2", risk_level=RiskLevel.MEDIUM)
        # Let background tasks complete
        await asyncio.sleep(0.01)

        m = resolver_isolated.get_metrics()
        assert m["resolutions"] == 3
        assert m["cache_hits"] == 1
        assert m["cache_misses"] == 2

    @pytest.mark.asyncio
    async def test_cache_hit_rate(self, resolver_isolated):
        assert resolver_isolated.get_metrics()["cache_hit_rate"] == 0.0
        await resolver_isolated.resolve_policy(tenant_id="t1", risk_level=RiskLevel.LOW)
        await resolver_isolated.resolve_policy(tenant_id="t1", risk_level=RiskLevel.LOW)
        m = resolver_isolated.get_metrics()
        assert m["cache_hit_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_redis_hit_rate_zero_when_no_requests(self, resolver_isolated):
        assert resolver_isolated.get_metrics()["redis_hit_rate"] == 0.0

    def test_reset_metrics(self, resolver_isolated):
        resolver_isolated._metrics["resolutions"] = 42
        resolver_isolated._metrics["errors"] = 5
        resolver_isolated.reset_metrics()
        m = resolver_isolated.get_metrics()
        assert m["resolutions"] == 0
        assert m["errors"] == 0

    def test_metrics_includes_cache_capacity(self, resolver_isolated):
        m = resolver_isolated.get_metrics()
        assert m["memory_cache_capacity"] == 100

    def test_metrics_includes_constitutional_hash(self, resolver_isolated):
        m = resolver_isolated.get_metrics()
        assert "constitutional_hash" in m


# ---------------------------------------------------------------------------
# Concurrent resolution
# ---------------------------------------------------------------------------


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_resolutions(self, resolver_isolated):
        tasks = [
            resolver_isolated.resolve_policy(tenant_id=f"t{i}", risk_level=RiskLevel.MEDIUM)
            for i in range(20)
        ]
        results = await asyncio.gather(*tasks)
        assert len(results) == 20
        for r in results:
            assert r.policy is not None

    @pytest.mark.asyncio
    async def test_concurrent_cache_reads(self, resolver_isolated):
        await resolver_isolated.resolve_policy(tenant_id="t1", risk_level=RiskLevel.LOW)
        tasks = [
            resolver_isolated.resolve_policy(tenant_id="t1", risk_level=RiskLevel.LOW)
            for _ in range(10)
        ]
        results = await asyncio.gather(*tasks)
        assert len(results) == 10
        # All should be cache hits
        await asyncio.sleep(0.01)
        assert resolver_isolated.get_metrics()["cache_hits"] == 10


# ---------------------------------------------------------------------------
# Resource cleanup
# ---------------------------------------------------------------------------


class TestClose:
    @pytest.mark.asyncio
    async def test_close_no_clients(self, resolver_isolated):
        # Should not raise when no clients exist
        await resolver_isolated.close()

    @pytest.mark.asyncio
    async def test_close_with_http_client(self, resolver_isolated):
        mock_http = AsyncMock()
        resolver_isolated._http_client = mock_http
        await resolver_isolated.close()
        mock_http.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_with_redis_client(self, resolver_isolated):
        mock_redis = AsyncMock()
        resolver_isolated._redis_client = mock_redis
        await resolver_isolated.close()
        mock_redis.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_handles_http_error(self, resolver_isolated):
        mock_http = AsyncMock()
        mock_http.aclose = AsyncMock(side_effect=httpx.HTTPError("close failed"))
        resolver_isolated._http_client = mock_http
        # Should not raise
        await resolver_isolated.close()

    @pytest.mark.asyncio
    async def test_close_handles_redis_error(self, resolver_isolated):
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock(side_effect=OSError("connection reset"))
        resolver_isolated._redis_client = mock_redis
        # Should not raise
        await resolver_isolated.close()


# ---------------------------------------------------------------------------
# HTTP client lazy init
# ---------------------------------------------------------------------------


class TestHttpClient:
    @pytest.mark.asyncio
    async def test_get_http_client_creates_once(self, resolver_isolated):
        c1 = await resolver_isolated._get_http_client()
        c2 = await resolver_isolated._get_http_client()
        assert c1 is c2
        assert isinstance(c1, httpx.AsyncClient)
        await c1.aclose()


# ---------------------------------------------------------------------------
# Redis client lazy init
# ---------------------------------------------------------------------------


class TestRedisClientInit:
    @pytest.mark.asyncio
    async def test_redis_unavailable_module(self, resolver_connected):
        with patch("enhanced_agent_bus.policy_resolver.REDIS_AVAILABLE", False):
            client = await resolver_connected._get_redis_client()
            assert client is None

    @pytest.mark.asyncio
    async def test_redis_connection_failure_returns_none(self, resolver_connected):
        with patch(
            "enhanced_agent_bus.policy_resolver.aioredis.from_url",
            AsyncMock(side_effect=OSError("refused")),
        ):
            client = await resolver_connected._get_redis_client()
            assert client is None


# ---------------------------------------------------------------------------
# Try-cache resolution path
# ---------------------------------------------------------------------------


class TestTryCacheResolution:
    @pytest.mark.asyncio
    async def test_memory_hit_returns_result(self, resolver_isolated):
        result = PolicyResolutionResult(
            policy={"id": "cached"}, source="cache", reasoning="r", risk_level=RiskLevel.LOW
        )
        await resolver_isolated._add_to_memory_cache("policy:k1", result)
        cached = await resolver_isolated._try_cache_resolution("policy:k1", time.perf_counter())
        assert cached is not None
        assert cached.policy == {"id": "cached"}

    @pytest.mark.asyncio
    async def test_redis_hit_populates_memory(self, resolver_connected, mock_redis_client):
        cached_data = json.dumps(
            {
                "policy": {"id": "redis-cached"},
                "source": "cache",
                "reasoning": "from redis",
                "risk_level": "low",
            }
        )
        mock_redis_client.get = AsyncMock(return_value=cached_data)
        resolver_connected._redis_client = mock_redis_client

        result = await resolver_connected._try_cache_resolution("policy:k1", time.perf_counter())
        assert result is not None
        assert result.policy == {"id": "redis-cached"}
        # Should also be in memory now
        mem = await resolver_connected._get_from_memory_cache("policy:k1")
        assert mem is not None

    @pytest.mark.asyncio
    async def test_both_miss_returns_none(self, resolver_isolated):
        result = await resolver_isolated._try_cache_resolution("policy:miss", time.perf_counter())
        assert result is None
