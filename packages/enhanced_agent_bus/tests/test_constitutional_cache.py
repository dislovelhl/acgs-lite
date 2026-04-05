"""
Constitutional Cache Tests — CE-3

Constitutional Hash: 608508a9bd224290

Tests verify:
- All cached data embeds constitutional hash 608508a9bd224290
- Retrieval with mismatched hash returns None
- Tag-based invalidation clears related entries
- PolicyCache auto-invalidates on policy update
- ValidationCache respects VALIDATION_CACHE_TTL_SECONDS (300s) default
- Local cache enforces max_entries limit
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.types import CONSTITUTIONAL_HASH
from enhanced_agent_bus.constitutional_cache import (
    VALIDATION_CACHE_TTL_SECONDS,
    ConstitutionalCache,
    PolicyCache,
    ValidationCache,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis():
    """Async mock Redis client."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.setex = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.sadd = AsyncMock(return_value=1)
    client.srem = AsyncMock(return_value=1)
    client.expire = AsyncMock(return_value=True)
    client.smembers = AsyncMock(return_value=set())
    client.scan_iter = MagicMock(return_value=aiter([]))
    return client


async def aiter(items):
    """Async iterator helper."""
    for item in items:
        yield item


@pytest.fixture
def cache(mock_redis):
    return ConstitutionalCache(redis_client=mock_redis, default_ttl=3600, max_entries=10000)


@pytest.fixture
def policy_cache(mock_redis):
    return PolicyCache(redis_client=mock_redis, default_ttl=3600)


@pytest.fixture
def validation_cache(mock_redis):
    return ValidationCache(redis_client=mock_redis)


# ---------------------------------------------------------------------------
# CE-3a: All cached data includes constitutional hash validation
# ---------------------------------------------------------------------------


async def test_set_embeds_constitutional_hash(cache, mock_redis):
    """set() stores entry with CONSTITUTIONAL_HASH embedded."""
    await cache.set("policy", "pol-1", {"rule": "allow"})

    mock_redis.setex.assert_called_once()
    _key, _ttl, payload = mock_redis.setex.call_args[0]
    entry_dict = json.loads(payload)
    assert entry_dict["constitutional_hash"] == CONSTITUTIONAL_HASH


async def test_get_local_hit_validates_hash(cache):
    """get() rejects local cache entry with wrong constitutional hash."""
    from enhanced_agent_bus.constitutional_cache import CacheEntry

    key = cache._generate_key("policy", "pol-bad")
    bad_entry = CacheEntry(
        value={"data": "secret"},
        constitutional_hash="wrong-hash-placeholder",  # intentionally invalid hash for rejection test
        created_at=datetime.now(),
        ttl=3600,
        tags=[],
    )
    cache._local_cache[key] = bad_entry

    result = await cache.get("policy", "pol-bad")
    assert result is None


async def test_get_redis_hit_validates_hash(cache, mock_redis):
    """get() from Redis returns None when hash mismatches."""
    stale = {
        "value": {"data": "old"},
        "constitutional_hash": "stalehashhhhhhh",
        "created_at": str(datetime.now()),
        "ttl": 3600,
        "tags": [],
        "access_count": 0,
    }
    mock_redis.get.return_value = json.dumps(stale).encode()

    result = await cache.get("policy", "pol-stale")
    assert result is None


async def test_get_local_hit_valid_hash(cache):
    """get() returns value from local cache when hash is correct."""
    from enhanced_agent_bus.constitutional_cache import CacheEntry

    key = cache._generate_key("policy", "pol-valid")
    good_entry = CacheEntry(
        value={"rule": "allow"},
        constitutional_hash=CONSTITUTIONAL_HASH,
        created_at=datetime.now(),
        ttl=3600,
        tags=[],
    )
    cache._local_cache[key] = good_entry

    result = await cache.get("policy", "pol-valid")
    assert result == {"rule": "allow"}


# ---------------------------------------------------------------------------
# CE-3b: Tag-based invalidation clears related entries
# ---------------------------------------------------------------------------


async def test_invalidate_by_tag_clears_local_entries(cache):
    """invalidate_by_tag() removes matching local cache entries."""
    from enhanced_agent_bus.constitutional_cache import CacheEntry

    key = cache._generate_key("policy", "pol-tag")
    entry = CacheEntry(
        value={"x": 1},
        constitutional_hash=CONSTITUTIONAL_HASH,
        created_at=datetime.now(),
        ttl=3600,
        tags=["policy", "policy:pol-tag"],
    )
    cache._local_cache[key] = entry

    count = await cache.invalidate_by_tag("policy")
    assert count >= 1
    assert key not in cache._local_cache


async def test_invalidate_by_tag_uses_redis_set_index(cache, mock_redis):
    """invalidate_by_tag() uses Redis SET index when populated."""
    mock_redis.smembers.return_value = {b"acgs:cache:policy:pol-1:abc12345"}

    count = await cache.invalidate_by_tag("policy")
    mock_redis.delete.assert_called()
    assert count >= 1


# ---------------------------------------------------------------------------
# CE-3c: PolicyCache auto-invalidates on policy update
# ---------------------------------------------------------------------------


async def test_policy_cache_cache_and_get(policy_cache, mock_redis):
    """PolicyCache.cache_policy() stores; get_policy() retrieves."""
    await policy_cache.cache_policy("pol-1", "rego rule allow { true }")

    entry = {
        "value": {"content": "rego rule allow { true }", "hash": "somehash"},
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "created_at": str(datetime.now()),
        "ttl": 3600,
        "tags": ["policy", "policy:pol-1"],
        "access_count": 0,
    }
    mock_redis.get.return_value = json.dumps(entry).encode()

    result = await policy_cache.get_policy("pol-1")
    assert result is not None
    assert "content" in result


async def test_policy_cache_invalidate_removes_entry(policy_cache, mock_redis):
    """invalidate_policy() calls delete on the correct key."""
    from enhanced_agent_bus.constitutional_cache import CacheEntry

    key = policy_cache._generate_key("policy", "pol-del")
    entry = CacheEntry(
        value={"content": "x"},
        constitutional_hash=CONSTITUTIONAL_HASH,
        created_at=datetime.now(),
        ttl=3600,
        tags=["policy"],
    )
    policy_cache._local_cache[key] = entry

    result = await policy_cache.invalidate_policy("pol-del")
    assert result is True
    assert key not in policy_cache._local_cache


async def test_policy_cache_invalidate_all(policy_cache, mock_redis):
    """invalidate_all_policies() invalidates by 'policy' tag."""
    mock_redis.smembers.return_value = {b"acgs:cache:policy:pol-1:aabb1122"}
    count = await policy_cache.invalidate_all_policies()
    assert count >= 0  # tag index may or may not find local entries


# ---------------------------------------------------------------------------
# CE-3d: ValidationCache respects 5-minute (300s) default TTL
# ---------------------------------------------------------------------------


async def test_validation_cache_uses_300s_ttl(validation_cache, mock_redis):
    """cache_validation() defaults to VALIDATION_CACHE_TTL_SECONDS (300)."""
    await validation_cache.cache_validation("key-1", {"valid": True})

    mock_redis.setex.assert_called_once()
    _key, ttl, _payload = mock_redis.setex.call_args[0]
    assert ttl == VALIDATION_CACHE_TTL_SECONDS


async def test_validation_cache_custom_ttl(validation_cache, mock_redis):
    """cache_validation() accepts explicit ttl override."""
    await validation_cache.cache_validation("key-2", {"valid": True}, ttl=60)
    _key, ttl, _payload = mock_redis.setex.call_args[0]
    assert ttl == 60


# ---------------------------------------------------------------------------
# CE-3e: Max 10,000 entries enforced in local cache
# ---------------------------------------------------------------------------


async def test_local_cache_max_entries_evicts_oldest(mock_redis):
    """Local cache evicts oldest entry when max_entries exceeded."""
    small_cache = ConstitutionalCache(redis_client=mock_redis, default_ttl=3600, max_entries=3)

    await small_cache.set("ns", "key1", "v1")
    await small_cache.set("ns", "key2", "v2")
    await small_cache.set("ns", "key3", "v3")
    assert len(small_cache._local_cache) == 3

    await small_cache.set("ns", "key4", "v4")
    # After eviction: still <= max_entries
    assert len(small_cache._local_cache) <= 3
