"""
ACGS-2 Enhanced Agent Bus - PQC Enforcement Config Service Tests
Constitutional Hash: 608508a9bd224290

Tests for EnforcementModeConfigService covering:
- Default permissive mode when Redis has no config
- Redis read path
- PostgreSQL fallback when Redis is unavailable
- Strict fail-safe when both backends unavailable
- set_mode() persistence and pub/sub publication
- Local cache invalidation via pub/sub
- Local cache TTL expiry
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-under-test: import with fallback for test-runner path variants
# ---------------------------------------------------------------------------
try:
    from enhanced_agent_bus.pqc_enforcement_config import (
        EnforcementModeConfigService,
        StorageUnavailableError,
    )
except ImportError:
    from pqc_enforcement_config import (  # type: ignore[no-redef]
        EnforcementModeConfigService,
        StorageUnavailableError,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_redis_mock(hget_return=None, hget_raises=None, publish_raises=None):
    """Build an async Redis mock with configurable behaviour."""
    redis = AsyncMock()
    if hget_raises is not None:
        redis.hget.side_effect = hget_raises
    else:
        redis.hget.return_value = hget_return
    redis.hset = AsyncMock(return_value=1)
    if publish_raises is not None:
        redis.publish.side_effect = publish_raises
    else:
        redis.publish = AsyncMock(return_value=1)
    return redis


def _make_pg_mock(fetchrow_return=None, fetchrow_raises=None):
    """Build an async PostgreSQL connection mock."""
    pg = AsyncMock()
    if fetchrow_raises is not None:
        pg.fetchrow.side_effect = fetchrow_raises
        pg.execute.side_effect = fetchrow_raises
    else:
        pg.fetchrow.return_value = fetchrow_return
        pg.execute = AsyncMock(return_value=None)
    return pg


@pytest.fixture
def redis_no_config():
    """Redis that returns None for any hget (no stored config)."""
    return _make_redis_mock(hget_return=None)


@pytest.fixture
def redis_strict():
    """Redis that returns b'strict' for any hget."""
    return _make_redis_mock(hget_return=b"strict")


@pytest.fixture
def redis_permissive():
    """Redis that returns b'permissive' for any hget."""
    return _make_redis_mock(hget_return=b"permissive")


@pytest.fixture
def redis_unavailable():
    """Redis that raises ConnectionError on every call."""
    return _make_redis_mock(hget_raises=ConnectionError("Redis down"))


@pytest.fixture
def pg_strict():
    """PostgreSQL that returns a row with mode='strict'."""
    return _make_pg_mock(fetchrow_return={"mode": "strict"})


@pytest.fixture
def pg_unavailable():
    """PostgreSQL that raises an exception on every call."""
    return _make_pg_mock(fetchrow_raises=OSError("PG down"))


# ---------------------------------------------------------------------------
# get_mode() tests
# ---------------------------------------------------------------------------


async def test_get_mode_returns_permissive_when_redis_has_no_config(redis_no_config):
    """Default mode is 'permissive' when no entry exists in Redis."""
    svc = EnforcementModeConfigService(redis_client=redis_no_config)
    mode = await svc.get_mode()
    assert mode == "permissive"
    redis_no_config.hget.assert_awaited_once()


async def test_get_mode_reads_strict_from_redis(redis_strict):
    """get_mode() returns the value stored in Redis when key exists."""
    svc = EnforcementModeConfigService(redis_client=redis_strict)
    mode = await svc.get_mode()
    assert mode == "strict"


async def test_get_mode_reads_permissive_from_redis(redis_permissive):
    """get_mode() returns 'permissive' when that is what Redis has stored."""
    svc = EnforcementModeConfigService(redis_client=redis_permissive)
    mode = await svc.get_mode()
    assert mode == "permissive"


async def test_get_mode_falls_back_to_postgres_when_redis_unavailable(redis_unavailable, pg_strict):
    """get_mode() falls back to PostgreSQL when Redis raises ConnectionError."""
    svc = EnforcementModeConfigService(redis_client=redis_unavailable, pg_conn=pg_strict)
    mode = await svc.get_mode()
    assert mode == "strict"
    pg_strict.fetchrow.assert_awaited_once()


async def test_get_mode_returns_strict_failsafe_when_both_unavailable(
    redis_unavailable, pg_unavailable
):
    """Fail-safe: returns 'strict' when both Redis and PostgreSQL are unavailable."""
    svc = EnforcementModeConfigService(redis_client=redis_unavailable, pg_conn=pg_unavailable)
    mode = await svc.get_mode()
    assert mode == "strict"


# ---------------------------------------------------------------------------
# set_mode() tests
# ---------------------------------------------------------------------------


async def test_set_mode_persists_to_redis_and_postgres_and_publishes(
    redis_no_config,
):
    """set_mode() writes to Redis hash, PostgreSQL, and publishes pub/sub event."""
    pg = _make_pg_mock()
    svc = EnforcementModeConfigService(redis_client=redis_no_config, pg_conn=pg)

    await svc.set_mode(mode="strict", scope="global", activated_by="operator-1")

    # Redis persistence
    redis_no_config.hset.assert_awaited_once()
    hset_kwargs = redis_no_config.hset.await_args
    assert hset_kwargs is not None

    # PostgreSQL persistence
    pg.execute.assert_awaited()

    # Pub/sub publication on pqc:enforcement_mode channel
    redis_no_config.publish.assert_awaited_once()
    channel_arg = redis_no_config.publish.await_args.args[0]
    assert channel_arg == "pqc:enforcement_mode"


async def test_set_mode_updates_local_cache(redis_no_config):
    """set_mode() updates the local in-process cache so the next get_mode() is a cache hit."""
    pg = _make_pg_mock()
    svc = EnforcementModeConfigService(redis_client=redis_no_config, pg_conn=pg)

    await svc.set_mode(mode="strict", scope="global", activated_by="op")

    # Now get_mode() should return "strict" from cache WITHOUT hitting Redis again
    redis_no_config.hget.reset_mock()
    mode = await svc.get_mode(scope="global")
    assert mode == "strict"
    redis_no_config.hget.assert_not_awaited()


# ---------------------------------------------------------------------------
# Local cache tests
# ---------------------------------------------------------------------------


async def test_local_cache_is_invalidated_on_pubsub_message(redis_strict):
    """Cache is cleared when a pub/sub invalidation message is received."""
    svc = EnforcementModeConfigService(redis_client=redis_strict)

    # Prime the cache with "strict"
    mode = await svc.get_mode(scope="global")
    assert mode == "strict"

    # Manually invoke the invalidation handler (simulates pub/sub delivery)
    svc._invalidate_cache(scope="global")

    # After invalidation, a fresh Redis read is performed
    redis_strict.hget.reset_mock()
    await svc.get_mode(scope="global")
    redis_strict.hget.assert_awaited_once()


async def test_local_cache_ttl_expires_and_triggers_redis_reread():
    """After TTL expiry, get_mode() re-reads from Redis instead of using stale cache."""
    redis = _make_redis_mock(hget_return=b"permissive")
    svc = EnforcementModeConfigService(redis_client=redis, cache_ttl_seconds=30)

    # Prime cache
    mode = await svc.get_mode(scope="global")
    assert mode == "permissive"
    redis.hget.assert_awaited_once()

    # Simulate TTL expiry by backdating the cache timestamp
    svc._cache["global"] = ("permissive", time.monotonic() - 31)

    redis.hget.reset_mock()
    mode = await svc.get_mode(scope="global")
    assert mode == "permissive"
    # Must have re-read from Redis
    redis.hget.assert_awaited_once()


async def test_local_cache_hit_avoids_redis_call(redis_permissive):
    """Within TTL, repeated get_mode() calls hit the local cache only."""
    svc = EnforcementModeConfigService(redis_client=redis_permissive, cache_ttl_seconds=30)

    await svc.get_mode(scope="global")
    redis_permissive.hget.assert_awaited_once()

    redis_permissive.hget.reset_mock()
    # Second call should hit cache, not Redis
    await svc.get_mode(scope="global")
    redis_permissive.hget.assert_not_awaited()
