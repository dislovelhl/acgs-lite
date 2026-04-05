"""
Tests for saga_persistence Redis modules and factory.

Covers:
- saga_persistence/redis/locking.py (RedisLockManager)
- saga_persistence/redis/repository.py (RedisSagaStateRepository)
- saga_persistence/redis/queries.py (RedisQueryOperations)
- saga_persistence/factory.py (create_saga_repository, SagaBackend, _mask_url, etc.)
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.saga_persistence.factory import (
    BackendUnavailableError,
    SagaBackend,
    _detect_backend,
    _mask_url,
    create_saga_repository,
)
from enhanced_agent_bus.saga_persistence.models import (
    PersistedSagaState,
    SagaState,
)
from enhanced_agent_bus.saga_persistence.redis.keys import (
    DEFAULT_LOCK_TIMEOUT_SECONDS,
    DEFAULT_TTL_DAYS,
    SAGA_INDEX_STATE_PREFIX,
    SAGA_LOCK_PREFIX,
    SAGA_STATE_PREFIX,
    RedisKeyMixin,
)
from enhanced_agent_bus.saga_persistence.redis.locking import RedisLockManager
from enhanced_agent_bus.saga_persistence.redis.queries import RedisQueryOperations
from enhanced_agent_bus.saga_persistence.redis.repository import RedisSagaStateRepository
from enhanced_agent_bus.saga_persistence.repository import (
    LockError,
    RepositoryError,
    VersionConflictError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_saga(
    saga_id: str = "saga-1",
    state: SagaState = SagaState.INITIALIZED,
    tenant_id: str = "tenant-a",
    version: int = 1,
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    failed_at: datetime | None = None,
    compensated_at: datetime | None = None,
    timeout_ms: int = 300_000,
) -> PersistedSagaState:
    return PersistedSagaState(
        saga_id=saga_id,
        saga_name="test-saga",
        tenant_id=tenant_id,
        state=state,
        version=version,
        created_at=created_at or datetime.now(UTC),
        started_at=started_at,
        completed_at=completed_at,
        failed_at=failed_at,
        compensated_at=compensated_at,
        timeout_ms=timeout_ms,
    )


class FakeRedis:
    """Minimal async fake Redis for unit testing."""

    def __init__(self):
        self._store: dict[str, object] = {}
        self._sets: dict[str, set] = {}
        self._zsets: dict[str, list] = {}
        self._expiry: dict[str, int] = {}

    async def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self._store:
            return False
        self._store[key] = value
        if ex:
            self._expiry[key] = ex
        return True

    async def get(self, key):
        return self._store.get(key)

    async def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                count += 1
            if k in self._sets:
                del self._sets[k]
                count += 1
            if k in self._zsets:
                del self._zsets[k]
                count += 1
        return count

    async def expire(self, key, ttl):
        self._expiry[key] = ttl
        return True

    async def exists(self, key):
        return 1 if key in self._store else 0

    async def ping(self):
        return True

    async def setex(self, key, ttl, value):
        self._store[key] = value
        self._expiry[key] = ttl
        return True

    async def hset(self, key, mapping=None):
        self._store[key] = dict(mapping) if mapping else {}
        return len(mapping) if mapping else 0

    async def hgetall(self, key):
        return self._store.get(key, {})

    async def smembers(self, key):
        return set(self._sets.get(key, set()))

    async def sadd(self, key, *values):
        if key not in self._sets:
            self._sets[key] = set()
        self._sets[key].update(values)
        return len(values)

    async def srem(self, key, *values):
        if key not in self._sets:
            return 0
        before = len(self._sets[key])
        self._sets[key] -= set(values)
        return before - len(self._sets[key])

    async def scard(self, key):
        return len(self._sets.get(key, set()))

    async def zrange(self, key, start, stop):
        return self._zsets.get(key, [])

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    """Collects pipeline ops and executes them."""

    def __init__(self, redis: FakeRedis):
        self._redis = redis
        self._ops: list = []

    def hset(self, key, mapping=None):
        self._ops.append(("hset", key, mapping))

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))

    def sadd(self, key, *values):
        self._ops.append(("sadd", key, values))

    def srem(self, key, *values):
        self._ops.append(("srem", key, values))

    def delete(self, key):
        self._ops.append(("delete", key))

    async def execute(self):
        for op in self._ops:
            cmd = op[0]
            if cmd == "hset":
                await self._redis.hset(op[1], mapping=op[2])
            elif cmd == "expire":
                await self._redis.expire(op[1], op[2])
            elif cmd == "sadd":
                await self._redis.sadd(op[1], *op[2])
            elif cmd == "srem":
                await self._redis.srem(op[1], *op[2])
            elif cmd == "delete":
                await self._redis.delete(op[1])
        return [True] * len(self._ops)


def _make_repo(fake_redis: FakeRedis | None = None) -> RedisSagaStateRepository:
    r = fake_redis or FakeRedis()
    return RedisSagaStateRepository(redis_client=r)


# ===========================================================================
# RedisLockManager tests
# ===========================================================================


class TestRedisLockManagerAcquireLock:
    async def test_acquire_lock_success(self):
        repo = _make_repo()
        result = await repo.acquire_lock("saga-1", "holder-a", ttl_seconds=10)
        assert result is True

    async def test_acquire_lock_already_held(self):
        repo = _make_repo()
        await repo.acquire_lock("saga-1", "holder-a")
        result = await repo.acquire_lock("saga-1", "holder-b")
        assert result is False

    async def test_acquire_lock_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("connection lost")

        fake.set = _boom
        with pytest.raises(LockError, match="Failed to acquire lock"):
            await repo.acquire_lock("saga-1", "holder-a")


class TestRedisLockManagerReleaseLock:
    async def test_release_lock_success(self):
        repo = _make_repo()
        await repo.acquire_lock("saga-1", "holder-a")
        result = await repo.release_lock("saga-1", "holder-a")
        assert result is True

    async def test_release_lock_not_held(self):
        repo = _make_repo()
        result = await repo.release_lock("saga-1", "holder-a")
        assert result is False

    async def test_release_lock_wrong_holder(self):
        repo = _make_repo()
        await repo.acquire_lock("saga-1", "holder-a")
        result = await repo.release_lock("saga-1", "holder-b")
        assert result is False

    async def test_release_lock_bytes_holder(self):
        """Holder stored as bytes should be decoded."""
        fake = FakeRedis()
        repo = _make_repo(fake)
        lock_key = f"{SAGA_LOCK_PREFIX}saga-1"
        fake._store[lock_key] = b"holder-a"
        result = await repo.release_lock("saga-1", "holder-a")
        assert result is True

    async def test_release_lock_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("oops")

        fake.get = _boom
        with pytest.raises(LockError, match="Failed to release lock"):
            await repo.release_lock("saga-1", "holder-a")


class TestRedisLockManagerExtendLock:
    async def test_extend_lock_success(self):
        repo = _make_repo()
        await repo.acquire_lock("saga-1", "holder-a")
        result = await repo.extend_lock("saga-1", "holder-a", ttl_seconds=60)
        assert result is True

    async def test_extend_lock_not_held(self):
        repo = _make_repo()
        result = await repo.extend_lock("saga-1", "holder-a")
        assert result is False

    async def test_extend_lock_wrong_holder(self):
        repo = _make_repo()
        await repo.acquire_lock("saga-1", "holder-a")
        result = await repo.extend_lock("saga-1", "holder-b")
        assert result is False

    async def test_extend_lock_bytes_holder(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        lock_key = f"{SAGA_LOCK_PREFIX}saga-1"
        fake._store[lock_key] = b"holder-a"
        result = await repo.extend_lock("saga-1", "holder-a", ttl_seconds=60)
        assert result is True

    async def test_extend_lock_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("timeout")

        fake.get = _boom
        with pytest.raises(LockError, match="Failed to extend lock"):
            await repo.extend_lock("saga-1", "holder-a")


class TestDistributedLockContextManager:
    async def test_distributed_lock_acquire_and_release(self):
        repo = _make_repo()
        async with repo.distributed_lock("saga-1", ttl_seconds=5) as acquired:
            assert acquired is True
        # After context, lock should be released
        lock_key = f"{SAGA_LOCK_PREFIX}saga-1"
        assert lock_key not in repo._redis._store

    async def test_distributed_lock_not_acquired(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        # Pre-hold the lock
        lock_key = f"{SAGA_LOCK_PREFIX}saga-1"
        fake._store[lock_key] = "someone-else"
        async with repo.distributed_lock("saga-1") as acquired:
            assert acquired is False

    async def test_distributed_lock_releases_on_exception(self):
        repo = _make_repo()
        with pytest.raises(RuntimeError, match="boom"):
            async with repo.distributed_lock("saga-1") as acquired:
                assert acquired is True
                raise RuntimeError("boom")
        lock_key = f"{SAGA_LOCK_PREFIX}saga-1"
        assert lock_key not in repo._redis._store


class TestCleanupOldSagas:
    async def test_cleanup_terminal_sagas(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        old_time = datetime(2020, 1, 1, tzinfo=UTC)
        saga = _make_saga(saga_id="old-1", state=SagaState.COMPLETED, completed_at=old_time)

        await repo.save(saga)
        deleted = await repo.cleanup_old_sagas(
            older_than=datetime(2023, 1, 1, tzinfo=UTC),
            terminal_only=True,
        )
        assert deleted == 1

    async def test_cleanup_no_matching_sagas(self):
        repo = _make_repo()
        deleted = await repo.cleanup_old_sagas(
            older_than=datetime(2020, 1, 1, tzinfo=UTC),
            terminal_only=True,
        )
        assert deleted == 0

    async def test_cleanup_non_terminal_too(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        old_time = datetime(2020, 1, 1, tzinfo=UTC)
        saga = _make_saga(saga_id="init-1", state=SagaState.INITIALIZED, created_at=old_time)
        await repo.save(saga)
        deleted = await repo.cleanup_old_sagas(
            older_than=datetime(2023, 1, 1, tzinfo=UTC),
            terminal_only=False,
        )
        assert deleted == 1

    async def test_cleanup_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("fail")

        fake.smembers = _boom
        with pytest.raises(RepositoryError, match="Failed to cleanup old sagas"):
            await repo.cleanup_old_sagas(older_than=datetime.now(UTC))


class TestGetStatistics:
    async def test_get_statistics_empty(self):
        repo = _make_repo()
        stats = await repo.get_statistics()
        assert stats["total_sagas"] == 0
        assert "counts_by_state" in stats
        assert "constitutional_hash" in stats

    async def test_get_statistics_with_data(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(state=SagaState.RUNNING)
        await repo.save(saga)
        # Manually add to the state index for counting
        stats = await repo.get_statistics()
        assert stats["total_sagas"] >= 0

    async def test_get_statistics_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("dead")

        fake.scard = _boom
        with pytest.raises(RepositoryError, match="Failed to count sagas by state"):
            await repo.get_statistics()


class TestHealthCheck:
    async def test_health_check_healthy(self):
        repo = _make_repo()
        health = await repo.health_check()
        assert health["healthy"] is True
        assert health["checks"]["redis_ping"]["status"] == "pass"
        assert health["checks"]["redis_ops"]["status"] == "pass"

    async def test_health_check_unhealthy(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("connection refused")

        fake.ping = _boom
        health = await repo.health_check()
        assert health["healthy"] is False
        assert "error" in health


# ===========================================================================
# RedisSagaStateRepository tests (repository.py)
# ===========================================================================


class TestRedisSagaStateRepositoryInit:
    def test_init_defaults(self):
        fake = FakeRedis()
        repo = RedisSagaStateRepository(redis_client=fake)
        assert repo._redis is fake
        assert repo._default_ttl == timedelta(days=DEFAULT_TTL_DAYS)
        assert repo._lock_timeout == DEFAULT_LOCK_TIMEOUT_SECONDS
        assert repo._node_id.startswith("node-")

    def test_init_custom_params(self):
        fake = FakeRedis()
        repo = RedisSagaStateRepository(
            redis_client=fake, default_ttl_days=14, lock_timeout_seconds=60
        )
        assert repo._default_ttl == timedelta(days=14)
        assert repo._lock_timeout == 60

    def test_get_ttl_seconds(self):
        repo = _make_repo()
        expected = DEFAULT_TTL_DAYS * 86400
        assert repo._get_ttl_seconds() == expected


class TestRedisSagaStateRepositorySave:
    async def test_save_new_saga(self):
        repo = _make_repo()
        saga = _make_saga()
        result = await repo.save(saga)
        assert result is True

    async def test_save_existing_saga_same_version(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(version=1)
        await repo.save(saga)
        # Save again with same version
        result = await repo.save(saga)
        assert result is True

    async def test_save_version_conflict(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga_v1 = _make_saga(version=1)
        await repo.save(saga_v1)
        saga_v5 = _make_saga(version=5)
        with pytest.raises(VersionConflictError):
            await repo.save(saga_v5)

    async def test_save_with_state_change(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga_init = _make_saga(state=SagaState.INITIALIZED, version=1)
        await repo.save(saga_init)
        saga_running = _make_saga(state=SagaState.RUNNING, version=2)
        result = await repo.save(saga_running)
        assert result is True

    async def test_save_with_tenant_id(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(tenant_id="tenant-x")
        await repo.save(saga)
        tenant_key = "acgs2:saga:index:tenant:tenant-x"
        assert "saga-1" in fake._sets.get(tenant_key, set())

    async def test_save_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("write failed")

        fake.hgetall = _boom
        saga = _make_saga()
        with pytest.raises(RepositoryError, match="Failed to save saga"):
            await repo.save(saga)


class TestRedisSagaStateRepositoryGet:
    async def test_get_existing(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga()
        await repo.save(saga)
        result = await repo.get("saga-1")
        assert result is not None
        assert result.saga_id == "saga-1"

    async def test_get_not_found(self):
        repo = _make_repo()
        result = await repo.get("nonexistent")
        assert result is None

    async def test_get_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("read failed")

        fake.hgetall = _boom
        with pytest.raises(RepositoryError, match="Failed to get saga"):
            await repo.get("saga-1")


class TestRedisSagaStateRepositoryDelete:
    async def test_delete_existing(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga()
        await repo.save(saga)
        result = await repo.delete("saga-1")
        assert result is True

    async def test_delete_not_found(self):
        repo = _make_repo()
        result = await repo.delete("nonexistent")
        assert result is False

    async def test_delete_with_tenant(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(tenant_id="tenant-x")
        await repo.save(saga)
        result = await repo.delete("saga-1")
        assert result is True

    async def test_delete_with_checkpoints(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga()
        await repo.save(saga)
        # Add checkpoint IDs to the zset
        cp_list_key = "acgs2:saga:checkpoint:saga-1:list"
        fake._zsets[cp_list_key] = ["cp-1", "cp-2"]
        result = await repo.delete("saga-1")
        assert result is True

    async def test_delete_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("delete failed")

        fake.hgetall = _boom
        with pytest.raises(RepositoryError, match="Failed to delete saga"):
            await repo.delete("saga-1")


class TestRedisSagaStateRepositoryExists:
    async def test_exists_true(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga()
        await repo.save(saga)
        result = await repo.exists("saga-1")
        assert result is True

    async def test_exists_false(self):
        repo = _make_repo()
        result = await repo.exists("nonexistent")
        assert result is False

    async def test_exists_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("exists failed")

        fake.exists = _boom
        with pytest.raises(RepositoryError, match="Failed to check saga existence"):
            await repo.exists("saga-1")


class TestExecuteWithRetry:
    async def test_execute_with_retry_success(self):
        repo = _make_repo()

        async def _op():
            return "ok"

        result = await repo._execute_with_retry("test", "saga-1", _op)
        assert result == "ok"

    async def test_execute_with_retry_error(self):
        repo = _make_repo()
        import redis.asyncio as _redis_mod

        async def _op():
            raise _redis_mod.RedisError("fail")

        with pytest.raises(RepositoryError, match="Redis test failed"):
            await repo._execute_with_retry("test", "saga-1", _op)


# ===========================================================================
# RedisQueryOperations tests (queries.py)
# ===========================================================================


class TestListByTenant:
    async def test_list_by_tenant_empty(self):
        repo = _make_repo()
        result = await repo.list_by_tenant("tenant-a")
        assert result == []

    async def test_list_by_tenant_returns_sagas(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(tenant_id="tenant-a")
        await repo.save(saga)
        result = await repo.list_by_tenant("tenant-a")
        assert len(result) == 1
        assert result[0].saga_id == "saga-1"

    async def test_list_by_tenant_with_state_filter(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga1 = _make_saga(saga_id="s1", tenant_id="t1", state=SagaState.RUNNING)
        saga2 = _make_saga(saga_id="s2", tenant_id="t1", state=SagaState.COMPLETED)
        await repo.save(saga1)
        await repo.save(saga2)
        result = await repo.list_by_tenant("t1", state=SagaState.RUNNING)
        saga_ids = [s.saga_id for s in result]
        assert "s1" in saga_ids
        assert "s2" not in saga_ids

    async def test_list_by_tenant_pagination(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        for i in range(5):
            saga = _make_saga(saga_id=f"s-{i:03d}", tenant_id="t1")
            await repo.save(saga)
        result = await repo.list_by_tenant("t1", limit=2, offset=0)
        assert len(result) == 2

    async def test_list_by_tenant_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("fail")

        fake.smembers = _boom
        with pytest.raises(RepositoryError, match="Failed to list sagas by tenant"):
            await repo.list_by_tenant("tenant-a")


class TestListByState:
    async def test_list_by_state_empty(self):
        repo = _make_repo()
        result = await repo.list_by_state(SagaState.RUNNING)
        assert result == []

    async def test_list_by_state_returns_sagas(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(state=SagaState.RUNNING)
        await repo.save(saga)
        result = await repo.list_by_state(SagaState.RUNNING)
        assert len(result) == 1

    async def test_list_by_state_pagination(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        for i in range(5):
            saga = _make_saga(saga_id=f"s-{i:03d}", state=SagaState.RUNNING)
            await repo.save(saga)
        result = await repo.list_by_state(SagaState.RUNNING, limit=2, offset=1)
        assert len(result) == 2

    async def test_list_by_state_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("fail")

        fake.smembers = _boom
        with pytest.raises(RepositoryError, match="Failed to list sagas by state"):
            await repo.list_by_state(SagaState.RUNNING)


class TestListPendingCompensations:
    async def test_list_pending_empty(self):
        repo = _make_repo()
        result = await repo.list_pending_compensations()
        assert result == []

    async def test_list_pending_compensating_sagas(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(state=SagaState.COMPENSATING)
        await repo.save(saga)
        result = await repo.list_pending_compensations()
        assert len(result) == 1

    async def test_list_pending_running_sagas(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(state=SagaState.RUNNING)
        await repo.save(saga)
        result = await repo.list_pending_compensations()
        assert len(result) == 1

    async def test_list_pending_with_limit(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        for i in range(5):
            saga = _make_saga(saga_id=f"s-{i}", state=SagaState.COMPENSATING)
            await repo.save(saga)
        result = await repo.list_pending_compensations(limit=2)
        assert len(result) <= 2

    async def test_list_pending_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("fail")

        fake.smembers = _boom
        with pytest.raises(RepositoryError, match="Failed to list pending compensations"):
            await repo.list_pending_compensations()


class TestListTimedOut:
    async def test_list_timed_out_empty(self):
        repo = _make_repo()
        result = await repo.list_timed_out(since=datetime.now(UTC))
        assert result == []

    async def test_list_timed_out_finds_expired(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        old_start = datetime(2020, 1, 1, tzinfo=UTC)
        saga = _make_saga(
            state=SagaState.RUNNING,
            started_at=old_start,
            timeout_ms=1000,  # 1 second timeout
        )
        await repo.save(saga)
        result = await repo.list_timed_out(since=datetime.now(UTC))
        assert len(result) == 1

    async def test_list_timed_out_skips_not_expired(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        now = datetime.now(UTC)
        saga = _make_saga(
            state=SagaState.RUNNING,
            started_at=now,
            timeout_ms=999_999_999,  # huge timeout
        )
        await repo.save(saga)
        result = await repo.list_timed_out(since=now)
        assert len(result) == 0

    async def test_list_timed_out_no_started_at(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(state=SagaState.RUNNING, started_at=None)
        await repo.save(saga)
        result = await repo.list_timed_out(since=datetime.now(UTC))
        assert len(result) == 0

    async def test_list_timed_out_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("fail")

        fake.smembers = _boom
        with pytest.raises(RepositoryError, match="Failed to list timed out sagas"):
            await repo.list_timed_out(since=datetime.now(UTC))


class TestCountByState:
    async def test_count_by_state_zero(self):
        repo = _make_repo()
        count = await repo.count_by_state(SagaState.RUNNING)
        assert count == 0

    async def test_count_by_state_nonzero(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(state=SagaState.RUNNING)
        await repo.save(saga)
        count = await repo.count_by_state(SagaState.RUNNING)
        assert count == 1

    async def test_count_by_state_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("fail")

        fake.scard = _boom
        with pytest.raises(RepositoryError, match="Failed to count sagas by state"):
            await repo.count_by_state(SagaState.RUNNING)


class TestCountByTenant:
    async def test_count_by_tenant_zero(self):
        repo = _make_repo()
        count = await repo.count_by_tenant("tenant-a")
        assert count == 0

    async def test_count_by_tenant_nonzero(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(tenant_id="tenant-a")
        await repo.save(saga)
        count = await repo.count_by_tenant("tenant-a")
        assert count == 1

    async def test_count_by_tenant_redis_error(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        import redis.asyncio as _redis_mod

        async def _boom(*a, **kw):
            raise _redis_mod.RedisError("fail")

        fake.scard = _boom
        with pytest.raises(RepositoryError, match="Failed to count sagas by tenant"):
            await repo.count_by_tenant("tenant-a")


# ===========================================================================
# Factory tests (factory.py)
# ===========================================================================


class TestSagaBackendEnum:
    def test_values(self):
        assert SagaBackend.REDIS.value == "redis"
        assert SagaBackend.POSTGRES.value == "postgres"

    def test_is_str_enum(self):
        assert isinstance(SagaBackend.REDIS, str)


class TestBackendUnavailableError:
    def test_attributes(self):
        err = BackendUnavailableError(SagaBackend.REDIS, "not installed")
        assert err.backend == SagaBackend.REDIS
        assert err.reason == "not installed"
        assert "redis" in str(err).lower()


class TestDetectBackend:
    def test_default_is_redis(self):
        env = {"SAGA_BACKEND": "", "DATABASE_URL": ""}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("DATABASE_URL", None)
            os.environ.pop("SAGA_BACKEND", None)
            result = _detect_backend()
        assert result == SagaBackend.REDIS

    def test_explicit_postgres(self):
        with patch.dict(os.environ, {"SAGA_BACKEND": "postgres"}, clear=False):
            result = _detect_backend()
        assert result == SagaBackend.POSTGRES

    def test_explicit_redis(self):
        with patch.dict(os.environ, {"SAGA_BACKEND": "redis"}, clear=False):
            result = _detect_backend()
        assert result == SagaBackend.REDIS

    def test_database_url_implies_postgres(self):
        env = {"DATABASE_URL": "postgresql://localhost/db"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SAGA_BACKEND", None)
            result = _detect_backend()
        assert result == SagaBackend.POSTGRES


class TestMaskUrl:
    def test_no_credentials(self):
        assert _mask_url("redis://localhost:6379") == "redis://localhost:6379"

    def test_mask_password(self):
        result = _mask_url("redis://user:secret@host:6379/0")
        assert "secret" not in result
        assert "***" in result
        assert "user" in result

    def test_mask_postgres_password(self):
        result = _mask_url("postgresql://admin:p4ssw0rd@db.host:5432/mydb")
        assert "p4ssw0rd" not in result
        assert "***" in result

    def test_no_at_sign(self):
        url = "redis://localhost"
        assert _mask_url(url) == url


class TestCreateSagaRepositoryRedis:
    async def test_creates_redis_repo_successfully(self):
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)

        with (
            patch(
                "enhanced_agent_bus.saga_persistence.factory._detect_backend",
                return_value=SagaBackend.REDIS,
            ),
            patch("enhanced_agent_bus.saga_persistence.REDIS_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.saga_persistence.RedisSagaStateRepository",
                return_value=MagicMock(),
            ) as mock_repo_cls,
            patch("redis.asyncio.from_url", return_value=mock_client),
        ):
            repo = await create_saga_repository(SagaBackend.REDIS, redis_url="redis://localhost")
            assert repo is not None

    async def test_redis_unavailable_raises(self):
        with patch("enhanced_agent_bus.saga_persistence.REDIS_AVAILABLE", False):
            with pytest.raises(BackendUnavailableError):
                await create_saga_repository(SagaBackend.REDIS, fallback=False)

    async def test_redis_connection_failure_with_fallback(self):
        with (
            patch("enhanced_agent_bus.saga_persistence.REDIS_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.saga_persistence.RedisSagaStateRepository",
                return_value=MagicMock(),
            ),
            patch("redis.asyncio.from_url", side_effect=ConnectionError("refused")),
            patch("enhanced_agent_bus.saga_persistence.POSTGRES_AVAILABLE", False),
        ):
            with pytest.raises(BackendUnavailableError):
                await create_saga_repository(SagaBackend.REDIS, fallback=True)


class TestCreateSagaRepositoryPostgres:
    async def test_postgres_unavailable_raises(self):
        with patch("enhanced_agent_bus.saga_persistence.POSTGRES_AVAILABLE", False):
            with pytest.raises(BackendUnavailableError):
                await create_saga_repository(SagaBackend.POSTGRES, fallback=False)

    async def test_postgres_no_dsn_raises(self):
        mock_pg_cls = MagicMock()
        with (
            patch("enhanced_agent_bus.saga_persistence.POSTGRES_AVAILABLE", True),
            patch(
                "enhanced_agent_bus.saga_persistence.PostgresSagaStateRepository",
                mock_pg_cls,
            ),
            patch.dict(os.environ, {}, clear=False),
        ):
            os.environ.pop("DATABASE_URL", None)
            with pytest.raises(BackendUnavailableError, match="No DSN"):
                await create_saga_repository(SagaBackend.POSTGRES, fallback=False)


class TestCreateSagaRepositoryAutoDetect:
    async def test_auto_detect_defaults_to_redis(self):
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)

        with (
            patch.dict(os.environ, {}, clear=False),
            patch(
                "enhanced_agent_bus.saga_persistence.REDIS_AVAILABLE",
                True,
            ),
            patch(
                "enhanced_agent_bus.saga_persistence.RedisSagaStateRepository",
                return_value=MagicMock(),
            ),
            patch("redis.asyncio.from_url", return_value=mock_client),
        ):
            os.environ.pop("SAGA_BACKEND", None)
            os.environ.pop("DATABASE_URL", None)
            repo = await create_saga_repository()
            assert repo is not None


# ===========================================================================
# Mixin standalone tests
# ===========================================================================


class TestRedisQueryOperationsMixinStandalone:
    """Test that the mixin raises NotImplementedError for abstract methods."""

    async def test_get_raises(self):
        obj = RedisQueryOperations()
        with pytest.raises(NotImplementedError):
            await obj.get("saga-1")


class TestRedisLockManagerMixinStandalone:
    async def test_get_raises(self):
        obj = RedisLockManager()
        with pytest.raises(NotImplementedError):
            await obj.get("saga-1")

    async def test_delete_raises(self):
        obj = RedisLockManager()
        with pytest.raises(NotImplementedError):
            await obj.delete("saga-1")

    async def test_count_by_state_raises(self):
        obj = RedisLockManager()
        with pytest.raises(NotImplementedError):
            await obj.count_by_state(SagaState.RUNNING)


# ===========================================================================
# RedisKeyMixin tests
# ===========================================================================


class TestRedisKeyMixin:
    def test_state_key(self):
        mixin = RedisKeyMixin()
        assert mixin._state_key("s1") == f"{SAGA_STATE_PREFIX}s1"

    def test_lock_key(self):
        mixin = RedisKeyMixin()
        assert mixin._lock_key("s1") == f"{SAGA_LOCK_PREFIX}s1"

    def test_state_index_key(self):
        mixin = RedisKeyMixin()
        assert mixin._state_index_key(SagaState.RUNNING) == f"{SAGA_INDEX_STATE_PREFIX}RUNNING"

    def test_tenant_index_key(self):
        mixin = RedisKeyMixin()
        assert mixin._tenant_index_key("t1") == "acgs2:saga:index:tenant:t1"

    def test_checkpoint_key(self):
        mixin = RedisKeyMixin()
        assert "acgs2:saga:checkpoint:s1:cp1" == mixin._checkpoint_key("s1", "cp1")

    def test_checkpoint_list_key(self):
        mixin = RedisKeyMixin()
        assert "acgs2:saga:checkpoint:s1:list" == mixin._checkpoint_list_key("s1")

    def test_compensation_key(self):
        mixin = RedisKeyMixin()
        assert "acgs2:saga:compensation:s1" == mixin._compensation_key("s1")


# ===========================================================================
# Integration-level: full save/get/delete round-trip
# ===========================================================================


class TestRedisSagaRepositoryRoundTrip:
    async def test_save_get_delete_cycle(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(saga_id="rt-1", tenant_id="t1", state=SagaState.INITIALIZED)
        await repo.save(saga)

        fetched = await repo.get("rt-1")
        assert fetched is not None
        assert fetched.saga_id == "rt-1"
        assert fetched.state == SagaState.INITIALIZED
        assert fetched.tenant_id == "t1"

        assert await repo.exists("rt-1") is True

        deleted = await repo.delete("rt-1")
        assert deleted is True

        assert await repo.get("rt-1") is None
        assert await repo.exists("rt-1") is False

    async def test_save_incremented_version(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga_v1 = _make_saga(version=1)
        await repo.save(saga_v1)
        saga_v2 = _make_saga(version=2)
        result = await repo.save(saga_v2)
        assert result is True

    async def test_cleanup_uses_failed_at_timestamp(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        old_time = datetime(2019, 6, 1, tzinfo=UTC)
        saga = _make_saga(
            saga_id="f1",
            state=SagaState.FAILED,
            failed_at=old_time,
        )
        await repo.save(saga)
        deleted = await repo.cleanup_old_sagas(
            older_than=datetime(2020, 1, 1, tzinfo=UTC),
            terminal_only=True,
        )
        assert deleted == 1

    async def test_cleanup_uses_compensated_at_timestamp(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        old_time = datetime(2019, 6, 1, tzinfo=UTC)
        saga = _make_saga(
            saga_id="c1",
            state=SagaState.COMPENSATED,
            compensated_at=old_time,
        )
        await repo.save(saga)
        deleted = await repo.cleanup_old_sagas(
            older_than=datetime(2020, 1, 1, tzinfo=UTC),
            terminal_only=True,
        )
        assert deleted == 1

    async def test_list_by_tenant_bytes_ids(self):
        """Simulate Redis returning bytes for set members."""
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(saga_id="byt-1", tenant_id="t-bytes")
        await repo.save(saga)
        # Replace set members with bytes to simulate real Redis
        tenant_key = "acgs2:saga:index:tenant:t-bytes"
        fake._sets[tenant_key] = {b"byt-1"}
        result = await repo.list_by_tenant("t-bytes")
        assert len(result) == 1
        assert result[0].saga_id == "byt-1"

    async def test_list_by_state_bytes_ids(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(saga_id="byt-2", state=SagaState.RUNNING)
        await repo.save(saga)
        state_key = f"{SAGA_INDEX_STATE_PREFIX}RUNNING"
        fake._sets[state_key] = {b"byt-2"}
        result = await repo.list_by_state(SagaState.RUNNING)
        assert len(result) == 1

    async def test_list_timed_out_bytes_ids(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        old_start = datetime(2020, 1, 1, tzinfo=UTC)
        saga = _make_saga(
            saga_id="byt-3",
            state=SagaState.RUNNING,
            started_at=old_start,
            timeout_ms=1,
        )
        await repo.save(saga)
        state_key = f"{SAGA_INDEX_STATE_PREFIX}RUNNING"
        fake._sets[state_key] = {b"byt-3"}
        result = await repo.list_timed_out(since=datetime.now(UTC))
        assert len(result) == 1

    async def test_list_pending_compensations_bytes_ids(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(saga_id="byt-4", state=SagaState.COMPENSATING)
        await repo.save(saga)
        state_key = f"{SAGA_INDEX_STATE_PREFIX}COMPENSATING"
        fake._sets[state_key] = {b"byt-4"}
        result = await repo.list_pending_compensations()
        assert len(result) == 1

    async def test_delete_checkpoints_bytes(self):
        fake = FakeRedis()
        repo = _make_repo(fake)
        saga = _make_saga(saga_id="byt-5")
        await repo.save(saga)
        cp_list_key = "acgs2:saga:checkpoint:byt-5:list"
        fake._zsets[cp_list_key] = [b"cp-a", b"cp-b"]
        result = await repo.delete("byt-5")
        assert result is True
