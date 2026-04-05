# Constitutional Hash: 608508a9bd224290
"""
Tests for src/core/enhanced_agent_bus/constitutional/storage_infra/cache.py

Covers all cache operations, TTL, invalidation, error paths, and fallbacks
to reach ≥90% line coverage on CacheManager.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from enhanced_agent_bus.constitutional.storage_infra.cache import (
    REDIS_AVAILABLE,
    CacheManager,
)
from enhanced_agent_bus.constitutional.storage_infra.config import StorageConfig
from enhanced_agent_bus.constitutional.version_model import (
    ConstitutionalStatus,
    ConstitutionalVersion,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**kwargs) -> StorageConfig:
    """Return a StorageConfig, allowing field overrides."""
    defaults = {
        "redis_url": "redis://localhost:6379",
        "cache_ttl": 300,
        "version_prefix": "constitutional:version:",
        "active_version_key": "constitutional:active_version",
    }
    defaults.update(kwargs)
    return StorageConfig(**defaults)


def _make_version(version_id: str = "ver-001") -> ConstitutionalVersion:
    """Return a minimal ConstitutionalVersion instance."""
    return ConstitutionalVersion(
        version_id=version_id,
        version="1.0.0",
        content={"rules": ["allow"]},
    )


def _make_mock_redis() -> AsyncMock:
    """Return a fully-mocked async Redis client."""
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.setex = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.close = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# __init__ and _get_tenant_key
# ---------------------------------------------------------------------------


def test_init_stores_config_and_no_client():
    """CacheManager initialises with config and no Redis client."""
    config = _make_config()
    mgr = CacheManager(config)
    assert mgr.config is config
    assert mgr.redis_client is None


def test_get_tenant_key_format():
    """_get_tenant_key scopes key under 'tenant:<id>:<base_key>'."""
    mgr = CacheManager(_make_config())
    key = mgr._get_tenant_key("constitutional:version:v1", "acme")
    assert key == "tenant:acme:constitutional:version:v1"


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


async def test_connect_returns_false_when_redis_unavailable():
    """connect() returns False when the redis library is not installed."""
    mgr = CacheManager(_make_config())
    # Patch REDIS_AVAILABLE inside the module
    import enhanced_agent_bus.constitutional.storage_infra.cache as cache_mod

    with patch.object(cache_mod, "REDIS_AVAILABLE", False):
        result = await mgr.connect()
    assert result is False
    assert mgr.redis_client is None


async def test_connect_success():
    """connect() sets redis_client and returns True on successful ping."""
    import enhanced_agent_bus.constitutional.storage_infra.cache as cache_mod

    mock_redis = _make_mock_redis()
    with (
        patch.object(cache_mod, "aioredis") as mock_aioredis,
        patch.object(cache_mod, "REDIS_AVAILABLE", True),
    ):
        mock_aioredis.from_url.return_value = mock_redis
        mgr = CacheManager(_make_config())
        result = await mgr.connect()

    assert result is True
    assert mgr.redis_client is mock_redis


async def test_connect_connection_error_returns_false():
    """connect() returns False and leaves redis_client None on ConnectionError."""
    import enhanced_agent_bus.constitutional.storage_infra.cache as cache_mod

    mock_redis = _make_mock_redis()
    mock_redis.ping.side_effect = ConnectionError("refused")

    with (
        patch.object(cache_mod, "aioredis") as mock_aioredis,
        patch.object(cache_mod, "REDIS_AVAILABLE", True),
    ):
        mock_aioredis.from_url.return_value = mock_redis
        mgr = CacheManager(_make_config())
        result = await mgr.connect()

    assert result is False
    assert mgr.redis_client is None


async def test_connect_os_error_returns_false():
    """connect() returns False and leaves redis_client None on OSError."""
    import enhanced_agent_bus.constitutional.storage_infra.cache as cache_mod

    mock_redis = _make_mock_redis()
    mock_redis.ping.side_effect = OSError("network error")

    with (
        patch.object(cache_mod, "aioredis") as mock_aioredis,
        patch.object(cache_mod, "REDIS_AVAILABLE", True),
    ):
        mock_aioredis.from_url.return_value = mock_redis
        mgr = CacheManager(_make_config())
        result = await mgr.connect()

    assert result is False
    assert mgr.redis_client is None


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


async def test_disconnect_closes_client():
    """disconnect() closes the Redis client and sets it to None."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mgr.redis_client = mock_redis

    await mgr.disconnect()

    mock_redis.close.assert_called_once()
    assert mgr.redis_client is None


async def test_disconnect_noop_when_no_client():
    """disconnect() is a no-op when redis_client is already None."""
    mgr = CacheManager(_make_config())
    # Should not raise
    await mgr.disconnect()
    assert mgr.redis_client is None


# ---------------------------------------------------------------------------
# get_version()
# ---------------------------------------------------------------------------


async def test_get_version_no_client_returns_none():
    """get_version() returns None when redis_client is None."""
    mgr = CacheManager(_make_config())
    result = await mgr.get_version("ver-001", "tenant-a")
    assert result is None


async def test_get_version_cache_miss_returns_none():
    """get_version() returns None on a Redis cache miss (get → None)."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.get.return_value = None
    mgr.redis_client = mock_redis

    result = await mgr.get_version("ver-001", "tenant-a")
    assert result is None


async def test_get_version_cache_hit_returns_version():
    """get_version() deserialises and returns ConstitutionalVersion on hit."""
    version = _make_version()
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.get.return_value = json.dumps(version.to_dict())
    mgr.redis_client = mock_redis

    result = await mgr.get_version(version.version_id, "tenant-a")
    assert result is not None
    assert result.version_id == version.version_id
    assert result.version == "1.0.0"


async def test_get_version_uses_tenant_scoped_key():
    """get_version() looks up the key with the tenant prefix."""
    config = _make_config()
    mgr = CacheManager(config)
    mock_redis = _make_mock_redis()
    mock_redis.get.return_value = None
    mgr.redis_client = mock_redis

    await mgr.get_version("ver-42", "my-tenant")

    expected_key = f"tenant:my-tenant:{config.version_prefix}ver-42"
    mock_redis.get.assert_called_once_with(expected_key)


async def test_get_version_json_decode_error_returns_none():
    """get_version() returns None when cached value is invalid JSON."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.get.return_value = "this is not json {"
    mgr.redis_client = mock_redis

    result = await mgr.get_version("ver-001", "tenant-a")
    assert result is None


async def test_get_version_validation_error_returns_none():
    """get_version() returns None when JSON does not match version schema."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    # Missing required fields → ValidationError inside CacheManager
    mock_redis.get.return_value = json.dumps({"bad": "data"})
    mgr.redis_client = mock_redis

    result = await mgr.get_version("ver-001", "tenant-a")
    assert result is None


async def test_get_version_connection_error_returns_none():
    """get_version() returns None when Redis raises ConnectionError."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.get.side_effect = ConnectionError("lost connection")
    mgr.redis_client = mock_redis

    result = await mgr.get_version("ver-001", "tenant-a")
    assert result is None


async def test_get_version_os_error_returns_none():
    """get_version() returns None when Redis raises OSError."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.get.side_effect = OSError("io error")
    mgr.redis_client = mock_redis

    result = await mgr.get_version("ver-001", "tenant-a")
    assert result is None


# ---------------------------------------------------------------------------
# set_version()
# ---------------------------------------------------------------------------


async def test_set_version_no_client_returns_false():
    """set_version() returns False when redis_client is None."""
    mgr = CacheManager(_make_config())
    version = _make_version()
    result = await mgr.set_version(version, "tenant-a")
    assert result is False


async def test_set_version_success():
    """set_version() calls setex with tenant-scoped key and configured TTL."""
    config = _make_config(cache_ttl=600)
    mgr = CacheManager(config)
    mock_redis = _make_mock_redis()
    mgr.redis_client = mock_redis

    version = _make_version("v-abc")
    result = await mgr.set_version(version, "t1")

    assert result is True
    mock_redis.setex.assert_called_once()
    key, ttl, payload = mock_redis.setex.call_args[0]
    assert key == f"tenant:t1:{config.version_prefix}v-abc"
    assert ttl == 600
    stored = json.loads(payload)
    assert stored["version_id"] == "v-abc"


async def test_set_version_connection_error_returns_false():
    """set_version() returns False when Redis raises ConnectionError."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.setex.side_effect = ConnectionError("refused")
    mgr.redis_client = mock_redis

    result = await mgr.set_version(_make_version(), "tenant-a")
    assert result is False


async def test_set_version_os_error_returns_false():
    """set_version() returns False when Redis raises OSError."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.setex.side_effect = OSError("broken pipe")
    mgr.redis_client = mock_redis

    result = await mgr.set_version(_make_version(), "tenant-a")
    assert result is False


async def test_set_version_type_error_returns_false():
    """set_version() returns False when serialisation raises TypeError."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.setex.side_effect = TypeError("unserializable")
    mgr.redis_client = mock_redis

    result = await mgr.set_version(_make_version(), "tenant-a")
    assert result is False


async def test_set_version_value_error_returns_false():
    """set_version() returns False when setex raises ValueError."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.setex.side_effect = ValueError("bad value")
    mgr.redis_client = mock_redis

    result = await mgr.set_version(_make_version(), "tenant-a")
    assert result is False


# ---------------------------------------------------------------------------
# invalidate_version()
# ---------------------------------------------------------------------------


async def test_invalidate_version_no_client_returns_false():
    """invalidate_version() returns False when redis_client is None."""
    mgr = CacheManager(_make_config())
    result = await mgr.invalidate_version("ver-001", "tenant-a")
    assert result is False


async def test_invalidate_version_success():
    """invalidate_version() calls delete with the correct tenant-scoped key."""
    config = _make_config()
    mgr = CacheManager(config)
    mock_redis = _make_mock_redis()
    mgr.redis_client = mock_redis

    result = await mgr.invalidate_version("ver-007", "acme")

    assert result is True
    expected_key = f"tenant:acme:{config.version_prefix}ver-007"
    mock_redis.delete.assert_called_once_with(expected_key)


async def test_invalidate_version_connection_error_returns_false():
    """invalidate_version() returns False when Redis raises ConnectionError."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.delete.side_effect = ConnectionError("gone")
    mgr.redis_client = mock_redis

    result = await mgr.invalidate_version("ver-001", "tenant-a")
    assert result is False


async def test_invalidate_version_os_error_returns_false():
    """invalidate_version() returns False when Redis raises OSError."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.delete.side_effect = OSError("io error")
    mgr.redis_client = mock_redis

    result = await mgr.invalidate_version("ver-001", "tenant-a")
    assert result is False


# ---------------------------------------------------------------------------
# set_active_version()
# ---------------------------------------------------------------------------


async def test_set_active_version_no_client_returns_false():
    """set_active_version() returns False when redis_client is None."""
    mgr = CacheManager(_make_config())
    result = await mgr.set_active_version("ver-001", "tenant-a")
    assert result is False


async def test_set_active_version_success():
    """set_active_version() writes version_id under tenant-scoped active key."""
    config = _make_config(cache_ttl=900)
    mgr = CacheManager(config)
    mock_redis = _make_mock_redis()
    mgr.redis_client = mock_redis

    result = await mgr.set_active_version("ver-current", "org-x")

    assert result is True
    mock_redis.setex.assert_called_once()
    key, ttl, value = mock_redis.setex.call_args[0]
    assert key == f"tenant:org-x:{config.active_version_key}"
    assert ttl == 900
    assert value == "ver-current"


async def test_set_active_version_connection_error_returns_false():
    """set_active_version() returns False when Redis raises ConnectionError."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.setex.side_effect = ConnectionError("refused")
    mgr.redis_client = mock_redis

    result = await mgr.set_active_version("ver-001", "tenant-a")
    assert result is False


async def test_set_active_version_os_error_returns_false():
    """set_active_version() returns False when Redis raises OSError."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.setex.side_effect = OSError("pipe broken")
    mgr.redis_client = mock_redis

    result = await mgr.set_active_version("ver-001", "tenant-a")
    assert result is False


# ---------------------------------------------------------------------------
# get_active_version_id()
# ---------------------------------------------------------------------------


async def test_get_active_version_id_no_client_returns_none():
    """get_active_version_id() returns None when redis_client is None."""
    mgr = CacheManager(_make_config())
    result = await mgr.get_active_version_id("tenant-a")
    assert result is None


async def test_get_active_version_id_cache_miss_returns_none():
    """get_active_version_id() returns None when no active version is cached."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.get.return_value = None
    mgr.redis_client = mock_redis

    result = await mgr.get_active_version_id("tenant-a")
    assert result is None


async def test_get_active_version_id_cache_hit():
    """get_active_version_id() returns the stored version ID string."""
    config = _make_config()
    mgr = CacheManager(config)
    mock_redis = _make_mock_redis()
    mock_redis.get.return_value = "ver-active-99"
    mgr.redis_client = mock_redis

    result = await mgr.get_active_version_id("my-org")

    assert result == "ver-active-99"
    expected_key = f"tenant:my-org:{config.active_version_key}"
    mock_redis.get.assert_called_once_with(expected_key)


async def test_get_active_version_id_connection_error_returns_none():
    """get_active_version_id() returns None when Redis raises ConnectionError."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.get.side_effect = ConnectionError("lost")
    mgr.redis_client = mock_redis

    result = await mgr.get_active_version_id("tenant-a")
    assert result is None


async def test_get_active_version_id_os_error_returns_none():
    """get_active_version_id() returns None when Redis raises OSError."""
    mgr = CacheManager(_make_config())
    mock_redis = _make_mock_redis()
    mock_redis.get.side_effect = OSError("timeout")
    mgr.redis_client = mock_redis

    result = await mgr.get_active_version_id("tenant-a")
    assert result is None


# ---------------------------------------------------------------------------
# Full round-trip: set_version → get_version
# ---------------------------------------------------------------------------


async def test_round_trip_set_then_get():
    """set_version() followed by get_version() returns the same version."""
    config = _make_config()
    mgr = CacheManager(config)
    mock_redis = _make_mock_redis()
    mgr.redis_client = mock_redis

    version = _make_version("rt-v1")
    stored_payload: list[str] = []

    async def capture_setex(key, ttl, payload):
        stored_payload.append(payload)
        return True

    async def return_stored(key):
        return stored_payload[0] if stored_payload else None

    mock_redis.setex.side_effect = capture_setex
    mock_redis.get.side_effect = return_stored

    set_ok = await mgr.set_version(version, "rt-tenant")
    assert set_ok is True

    retrieved = await mgr.get_version("rt-v1", "rt-tenant")
    assert retrieved is not None
    assert retrieved.version_id == "rt-v1"


# ---------------------------------------------------------------------------
# Full round-trip: set_active_version → get_active_version_id
# ---------------------------------------------------------------------------


async def test_round_trip_set_then_get_active():
    """set_active_version() followed by get_active_version_id() returns the same ID."""
    config = _make_config()
    mgr = CacheManager(config)
    mock_redis = _make_mock_redis()
    mgr.redis_client = mock_redis

    stored: list[str] = []

    async def capture_setex(key, ttl, value):
        stored.append(value)
        return True

    async def return_stored(key):
        return stored[0] if stored else None

    mock_redis.setex.side_effect = capture_setex
    mock_redis.get.side_effect = return_stored

    await mgr.set_active_version("ver-roundtrip", "rt-tenant")
    result = await mgr.get_active_version_id("rt-tenant")
    assert result == "ver-roundtrip"


# ---------------------------------------------------------------------------
# Module-level REDIS_AVAILABLE flag
# ---------------------------------------------------------------------------


def test_redis_available_is_bool():
    """REDIS_AVAILABLE is a boolean (True if redis installed, False otherwise)."""
    assert isinstance(REDIS_AVAILABLE, bool)
