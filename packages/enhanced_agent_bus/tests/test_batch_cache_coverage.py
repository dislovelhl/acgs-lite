"""
ACGS-2 Enhanced Agent Bus - Batch Cache Coverage Tests
Constitutional Hash: 608508a9bd224290

Additional tests to bring batch_cache.py coverage from ~58% to >=90%.
Targets uncovered lines: 69, 84, 87-89, 157, 217-219, 245, 328, 331-332,
336, 355-357, 361-370, 397-411, 423-443, 457, 460, 468-470, 482-495,
499-519, 532, 535, 538, 559-561, 574, 577, 580, 592-594, 641.
"""

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import enhanced_agent_bus.batch_cache as batch_cache_module
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_batch_cache():
    from enhanced_agent_bus import batch_cache as bc

    return bc


# ---------------------------------------------------------------------------
# Serialization fallback paths (lines 69, 84, 87-89)
# ---------------------------------------------------------------------------


class TestSerializationFallbacks:
    """Cover JSON-fallback and msgpack string-input branches."""

    def test_serialize_value_json_fallback(self):
        """Line 69: _serialize_value uses JSON when MSGPACK_AVAILABLE=False."""
        bc = _import_batch_cache()
        test_data = {"key": "value", "num": 42}

        with patch.dict(bc.__dict__, {"MSGPACK_AVAILABLE": False}):
            # Re-invoke through module globals patch
            original = bc.MSGPACK_AVAILABLE
            try:
                bc.MSGPACK_AVAILABLE = False
                result = bc._serialize_value(test_data)
                assert isinstance(result, bytes)
                assert json.loads(result.decode("utf-8")) == test_data
            finally:
                bc.MSGPACK_AVAILABLE = original

    def test_deserialize_value_json_bytes_fallback(self):
        """Lines 87-89: _deserialize_value JSON path with bytes input."""
        bc = _import_batch_cache()
        test_data = {"key": "value"}

        original = bc.MSGPACK_AVAILABLE
        try:
            bc.MSGPACK_AVAILABLE = False
            serialized = json.dumps(test_data).encode("utf-8")
            result = bc._deserialize_value(serialized)
            assert result == test_data
        finally:
            bc.MSGPACK_AVAILABLE = original

    def test_deserialize_value_json_str_input(self):
        """Line 87-89 (str input): _deserialize_value JSON path with string input."""
        bc = _import_batch_cache()
        test_data = {"is_valid": True, "score": 0.9}

        original = bc.MSGPACK_AVAILABLE
        try:
            bc.MSGPACK_AVAILABLE = False
            serialized = json.dumps(test_data)  # str, not bytes
            result = bc._deserialize_value(serialized)
            assert result == test_data
        finally:
            bc.MSGPACK_AVAILABLE = original

    def test_deserialize_value_msgpack_str_input(self):
        """Line 84: _deserialize_value msgpack path when data is a str.

        The code converts the str to bytes via .encode("utf-8") before
        passing to msgpack.unpackb.  We construct a string whose utf-8
        encoding is valid msgpack by encoding a simple value with only
        ASCII characters (so latin-1 == utf-8 for those bytes).
        """
        bc = _import_batch_cache()
        if not bc.MSGPACK_AVAILABLE:
            pytest.skip("msgpack not installed")

        import msgpack

        # msgpack encoding of the integer 42 is a single byte: b'\x2a'
        # That is valid ASCII/UTF-8.  Encode it to a str via latin-1
        # (latin-1 is a 1-to-1 byte<->char mapping), then let the code
        # re-encode it to UTF-8 bytes.  Since 0x2a < 0x80 the bytes are
        # identical in both encodings.
        test_value = 42
        packed_bytes = msgpack.packb(test_value, use_bin_type=True)
        # All bytes must be < 128 so latin-1 → utf-8 is lossless
        assert all(b < 128 for b in packed_bytes), "bytes not ASCII-safe"
        as_str = packed_bytes.decode("latin-1")

        result = bc._deserialize_value(as_str)
        assert result == test_value


# ---------------------------------------------------------------------------
# BatchValidationCache additional paths
# ---------------------------------------------------------------------------


class TestBatchValidationCacheAdditional:
    """Cover BatchValidationCache branches missed by existing tests."""

    def test_batch_validation_cache_rejects_invalid_cache_hash_mode(self):
        """Invalid hash mode should raise ValueError."""
        bc = _import_batch_cache()
        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            bc.BatchValidationCache(cache_hash_mode="invalid")  # type: ignore[arg-type]

    async def test_generate_cache_key_non_dict_content(self):
        """Line 157: generate_cache_key with non-dict content (string)."""
        bc = _import_batch_cache()
        cache = bc.BatchValidationCache()

        key = cache.generate_cache_key(
            content="plain string content",
            from_agent="agent-A",
            to_agent="agent-B",
            message_type="event",
        )
        assert len(key) == 64

    async def test_generate_cache_key_integer_content(self):
        """Line 157: generate_cache_key with integer content."""
        bc = _import_batch_cache()
        cache = bc.BatchValidationCache()

        key = cache.generate_cache_key(
            content=12345,
            from_agent="agent-A",
            to_agent="agent-B",
            message_type="event",
        )
        assert len(key) == 64

    async def test_generate_cache_key_fast_mode_uses_kernel(self, monkeypatch):
        """Fast mode uses Rust kernel when available."""
        bc = _import_batch_cache()
        called = {"value": False}

        def _fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0xBEEF

        monkeypatch.setattr(batch_cache_module, "FAST_HASH_AVAILABLE", True)
        monkeypatch.setattr(batch_cache_module, "fast_hash", _fake_fast_hash, raising=False)

        cache = bc.BatchValidationCache(cache_hash_mode="fast")
        key = cache.generate_cache_key(
            content={"a": 1},
            from_agent="a",
            to_agent="b",
            message_type="m",
        )
        assert called["value"] is True
        assert key == "fast:000000000000beef"

    async def test_generate_cache_key_fast_mode_falls_back_to_sha256(self, monkeypatch):
        """Fast mode falls back to SHA-256 when kernel unavailable."""
        bc = _import_batch_cache()
        monkeypatch.setattr(batch_cache_module, "FAST_HASH_AVAILABLE", False)

        cache = bc.BatchValidationCache(cache_hash_mode="fast")
        key = cache.generate_cache_key(
            content={"a": 1},
            from_agent="a",
            to_agent="b",
            message_type="m",
        )
        expected = hashlib.sha256(b'{"a": 1}|a|b|m|').hexdigest()
        assert key == expected

    async def test_set_updates_existing_key(self):
        """Lines 217-219: set() when key already exists — update and move_to_end."""
        bc = _import_batch_cache()
        cache = bc.BatchValidationCache()

        key = "existing-key"
        await cache.set(key, {"version": 1})
        result1 = await cache.get(key)
        assert result1["version"] == 1

        # Update the same key
        ok = await cache.set(key, {"version": 2})
        assert ok is True

        result2 = await cache.get(key)
        assert result2["version"] == 2

    async def test_set_existing_key_does_not_grow_cache(self):
        """Lines 217-219: updating existing key must not increase cache size."""
        bc = _import_batch_cache()
        cache = bc.BatchValidationCache(max_size=5)

        for i in range(5):
            await cache.set(f"key-{i}", {"i": i})

        size_before = cache.get_stats()["current_size"]
        await cache.set("key-0", {"i": 99})  # update existing
        size_after = cache.get_stats()["current_size"]

        assert size_before == size_after

    async def test_delete_missing_key_returns_false(self):
        """Line 245: delete() returns False when key does not exist."""
        bc = _import_batch_cache()
        cache = bc.BatchValidationCache()

        result = await cache.delete("this-key-does-not-exist")
        assert result is False

    async def test_evictions_counter_increments(self):
        """Lines 222-225: evictions counter increments on LRU eviction."""
        bc = _import_batch_cache()
        cache = bc.BatchValidationCache(max_size=2)

        await cache.set("k1", {"v": 1})
        await cache.set("k2", {"v": 2})
        await cache.set("k3", {"v": 3})  # triggers eviction

        stats = cache.get_stats()
        assert stats["evictions"] >= 1

    async def test_get_stats_zero_requests(self):
        """get_stats returns 0 hit_rate when no requests made."""
        bc = _import_batch_cache()
        cache = bc.BatchValidationCache()

        stats = cache.get_stats()
        assert stats["hit_rate"] == 0.0
        assert stats["hits"] == 0
        assert stats["misses"] == 0


# ---------------------------------------------------------------------------
# RedisBatchCache initialization edge cases (lines 328, 331-332, 336, 355-357)
# ---------------------------------------------------------------------------


class TestRedisBatchCacheInit:
    """Cover RedisBatchCache.initialize() edge-case branches."""

    async def test_initialize_already_initialized(self):
        """Line 328: initialize() returns True immediately if already initialized."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")
        cache._initialized = True  # simulate already initialized

        result = await cache.initialize()
        assert result is True

    async def test_initialize_redis_not_available(self):
        """Lines 331-332: initialize() returns False when aioredis unavailable."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        original = bc.REDIS_AVAILABLE
        try:
            bc.REDIS_AVAILABLE = False
            result = await cache.initialize()
            assert result is False
        finally:
            bc.REDIS_AVAILABLE = original

    async def test_initialize_double_check_inside_lock(self):
        """Line 336: second _initialized check inside the lock."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        # Simulate race: flag set to True just before lock is acquired
        async def _set_initialized(*args, **kwargs):
            cache._initialized = True

        original_acquire = cache._lock.acquire
        called = []

        async def patched_acquire():
            called.append(1)
            cache._initialized = True  # simulate another coroutine winning the race
            return await original_acquire()

        cache._lock.acquire = patched_acquire  # type: ignore[method-assign]

        result = await cache.initialize()
        assert result is True

    async def test_initialize_connection_error(self):
        """Lines 355-357: initialize() returns False on connection error."""
        bc = _import_batch_cache()

        # Only run if redis package is present
        if not bc.REDIS_AVAILABLE:
            pytest.skip("redis package not installed")

        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        with patch.object(bc.aioredis.ConnectionPool, "from_url", side_effect=OSError("refused")):
            result = await cache.initialize()
            assert result is False

    async def test_initialize_ping_raises_connection_error(self):
        """Lines 355-357: initialize() returns False when ping raises."""
        bc = _import_batch_cache()
        if not bc.REDIS_AVAILABLE:
            pytest.skip("redis package not installed")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("no redis"))

        with patch.object(bc.aioredis.ConnectionPool, "from_url", return_value=MagicMock()):
            with patch.object(bc.aioredis, "Redis", return_value=mock_redis):
                cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")
                result = await cache.initialize()
                assert result is False


# ---------------------------------------------------------------------------
# RedisBatchCache.close() (lines 361-370)
# ---------------------------------------------------------------------------


class TestRedisBatchCacheClose:
    """Cover RedisBatchCache.close()."""

    async def test_close_when_not_initialized(self):
        """close() is safe to call when never initialized."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")
        await cache.close()  # should not raise
        assert cache._initialized is False

    async def test_close_clears_redis_and_pool(self):
        """Lines 361-370: close() calls close()/disconnect() and resets state."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        mock_pool = AsyncMock()
        cache._redis = mock_redis
        cache._pool = mock_pool
        cache._initialized = True

        await cache.close()

        mock_redis.close.assert_awaited_once()
        mock_pool.disconnect.assert_awaited_once()
        assert cache._redis is None
        assert cache._pool is None
        assert cache._initialized is False

    async def test_close_only_redis_no_pool(self):
        """close() handles redis present but pool is None."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        cache._redis = mock_redis
        cache._pool = None
        cache._initialized = True

        await cache.close()

        mock_redis.close.assert_awaited_once()
        assert cache._redis is None
        assert cache._initialized is False


# ---------------------------------------------------------------------------
# RedisBatchCache.generate_cache_key() (lines 397-411)
# ---------------------------------------------------------------------------


class TestRedisBatchCacheKeyGeneration:
    """Cover RedisBatchCache.generate_cache_key branches."""

    def test_redis_batch_cache_rejects_invalid_cache_hash_mode(self):
        """Invalid hash mode should raise ValueError."""
        bc = _import_batch_cache()
        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            bc.RedisBatchCache(cache_hash_mode="invalid")  # type: ignore[arg-type]

    def test_generate_cache_key_non_dict_content(self):
        """Line 400: non-dict content uses str()."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache()

        key = cache.generate_cache_key(
            content="a plain string",
            from_agent="a1",
            to_agent="a2",
            message_type="msg",
        )
        assert len(key) == 64

    def test_generate_cache_key_with_tenant_id(self):
        """Line 407 (tenant_id): tenant_id influences key."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache()

        key_no_tenant = cache.generate_cache_key(
            content={"x": 1},
            from_agent="a1",
            to_agent="a2",
            message_type="m",
            tenant_id=None,
        )
        key_with_tenant = cache.generate_cache_key(
            content={"x": 1},
            from_agent="a1",
            to_agent="a2",
            message_type="m",
            tenant_id="t-001",
        )
        assert key_no_tenant != key_with_tenant

    def test_generate_cache_key_dict_content(self):
        """Line 398: dict content is JSON-sorted."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache()

        key1 = cache.generate_cache_key(
            content={"b": 2, "a": 1},
            from_agent="a1",
            to_agent="a2",
            message_type="m",
        )
        key2 = cache.generate_cache_key(
            content={"a": 1, "b": 2},
            from_agent="a1",
            to_agent="a2",
            message_type="m",
        )
        assert key1 == key2

    def test_generate_cache_key_fast_mode_uses_kernel(self, monkeypatch):
        """Fast mode uses Rust kernel when available."""
        bc = _import_batch_cache()
        called = {"value": False}

        def _fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0x1234

        monkeypatch.setattr(batch_cache_module, "FAST_HASH_AVAILABLE", True)
        monkeypatch.setattr(batch_cache_module, "fast_hash", _fake_fast_hash, raising=False)

        cache = bc.RedisBatchCache(cache_hash_mode="fast")
        key = cache.generate_cache_key(
            content={"a": 1},
            from_agent="a",
            to_agent="b",
            message_type="m",
        )
        assert called["value"] is True
        assert key == "fast:0000000000001234"

    def test_generate_cache_key_fast_mode_falls_back_to_sha256(self, monkeypatch):
        """Fast mode falls back to SHA-256 when kernel unavailable."""
        bc = _import_batch_cache()
        monkeypatch.setattr(batch_cache_module, "FAST_HASH_AVAILABLE", False)

        cache = bc.RedisBatchCache(cache_hash_mode="fast")
        key = cache.generate_cache_key(
            content={"a": 1},
            from_agent="a",
            to_agent="b",
            message_type="m",
        )
        expected = hashlib.sha256(b'{"a": 1}|a|b|m|').hexdigest()
        assert key == expected


# ---------------------------------------------------------------------------
# RedisBatchCache.get() edge cases (lines 423-443)
# ---------------------------------------------------------------------------


class TestRedisBatchCacheGet:
    """Cover RedisBatchCache.get() branches."""

    async def test_get_triggers_initialize_when_not_initialized(self):
        """Line 424: get() calls initialize() if not yet initialized."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        # initialize will be called and will fail (no real Redis) → _redis stays None
        # which then returns None from get().
        original = bc.REDIS_AVAILABLE
        try:
            bc.REDIS_AVAILABLE = False
            result = await cache.get("some-key")
            assert result is None
        finally:
            bc.REDIS_AVAILABLE = original

    async def test_get_returns_none_when_redis_none(self):
        """Line 427: returns None when _redis is None after initialize."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")
        cache._initialized = True  # pretend initialized but _redis is None

        result = await cache.get("any-key")
        assert result is None

    async def test_get_returns_value_on_hit(self):
        """Lines 437-438: hit path increments counter and deserializes."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        stored = {"valid": True}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=bc._serialize_value(stored))
        cache._redis = mock_redis
        cache._initialized = True

        result = await cache.get("hit-key")
        assert result == stored
        assert cache._hits == 1

    async def test_get_returns_none_on_redis_exception(self):
        """Lines 440-443: exception path increments misses and returns None."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=OSError("connection lost"))
        cache._redis = mock_redis
        cache._initialized = True

        result = await cache.get("error-key")
        assert result is None
        assert cache._misses == 1


# ---------------------------------------------------------------------------
# RedisBatchCache.set() edge cases (lines 457, 460, 468-470)
# ---------------------------------------------------------------------------


class TestRedisBatchCacheSet:
    """Cover RedisBatchCache.set() branches."""

    async def test_set_triggers_initialize_when_not_initialized(self):
        """Line 457: set() calls initialize() if not yet initialized."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        original = bc.REDIS_AVAILABLE
        try:
            bc.REDIS_AVAILABLE = False
            result = await cache.set("k", {"v": 1})
            assert result is False
        finally:
            bc.REDIS_AVAILABLE = original

    async def test_set_returns_false_when_redis_none(self):
        """Line 460: returns False when _redis is None."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")
        cache._initialized = True

        result = await cache.set("k", {"v": 1})
        assert result is False

    async def test_set_returns_false_on_exception(self):
        """Lines 468-470: exception path returns False."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(side_effect=ConnectionError("broken"))
        cache._redis = mock_redis
        cache._initialized = True

        result = await cache.set("k", {"v": 1})
        assert result is False


# ---------------------------------------------------------------------------
# RedisBatchCache.delete() edge cases (lines 482-495)
# ---------------------------------------------------------------------------


class TestRedisBatchCacheDelete:
    """Cover RedisBatchCache.delete() branches."""

    async def test_delete_triggers_initialize(self):
        """Line 483: delete() calls initialize() if not yet initialized."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        original = bc.REDIS_AVAILABLE
        try:
            bc.REDIS_AVAILABLE = False
            result = await cache.delete("k")
            assert result is False
        finally:
            bc.REDIS_AVAILABLE = original

    async def test_delete_returns_false_when_redis_none(self):
        """Line 486: returns False when _redis is None."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")
        cache._initialized = True

        result = await cache.delete("k")
        assert result is False

    async def test_delete_returns_false_when_key_missing(self):
        """Line 491: result == 0 → returns False."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=0)
        cache._redis = mock_redis
        cache._initialized = True

        result = await cache.delete("missing-key")
        assert result is False

    async def test_delete_returns_true_when_key_deleted(self):
        """Line 491: result > 0 → returns True."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)
        cache._redis = mock_redis
        cache._initialized = True

        result = await cache.delete("existing-key")
        assert result is True

    async def test_delete_returns_false_on_exception(self):
        """Lines 493-495: exception returns False."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock(side_effect=OSError("broken"))
        cache._redis = mock_redis
        cache._initialized = True

        result = await cache.delete("k")
        assert result is False


# ---------------------------------------------------------------------------
# RedisBatchCache.clear() (lines 499-519)
# ---------------------------------------------------------------------------


class TestRedisBatchCacheClear:
    """Cover RedisBatchCache.clear() branches."""

    async def test_clear_triggers_initialize(self):
        """Line 500: clear() calls initialize() if not initialized."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        original = bc.REDIS_AVAILABLE
        try:
            bc.REDIS_AVAILABLE = False
            await cache.clear()  # should not raise
        finally:
            bc.REDIS_AVAILABLE = original

    async def test_clear_returns_when_redis_none(self):
        """Line 503: returns early when _redis is None."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")
        cache._initialized = True

        await cache.clear()  # should not raise

    async def test_clear_scans_and_deletes_keys(self):
        """Lines 506-516: scan loop deletes keys."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        # First scan returns keys; second scan returns cursor=0 (done)
        mock_redis.scan = AsyncMock(
            side_effect=[
                (1, [b"acgs2:batch_cache:key1", b"acgs2:batch_cache:key2"]),
                (0, []),
            ]
        )
        mock_redis.delete = AsyncMock(return_value=2)
        cache._redis = mock_redis
        cache._initialized = True

        await cache.clear()

        assert mock_redis.delete.call_count >= 1

    async def test_clear_handles_empty_scan(self):
        """Lines 513-516: scan returns cursor=0 immediately (no keys)."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, []))
        mock_redis.delete = AsyncMock()
        cache._redis = mock_redis
        cache._initialized = True

        await cache.clear()
        mock_redis.delete.assert_not_called()

    async def test_clear_handles_exception(self):
        """Lines 518-519: exception is logged and swallowed."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(side_effect=ConnectionError("broken"))
        cache._redis = mock_redis
        cache._initialized = True

        await cache.clear()  # should not raise


# ---------------------------------------------------------------------------
# RedisBatchCache.batch_get() (lines 532, 535, 538, 559-561)
# ---------------------------------------------------------------------------


class TestRedisBatchCacheBatchGet:
    """Cover RedisBatchCache.batch_get() edge-case branches."""

    async def test_batch_get_empty_keys_returns_empty(self):
        """Line 532: empty keys list returns []."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        result = await cache.batch_get([])
        assert result == []

    async def test_batch_get_triggers_initialize(self):
        """Line 535: batch_get calls initialize when not initialized."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        original = bc.REDIS_AVAILABLE
        try:
            bc.REDIS_AVAILABLE = False
            result = await cache.batch_get(["k1", "k2"])
            assert result == [None, None]
        finally:
            bc.REDIS_AVAILABLE = original

    async def test_batch_get_returns_nones_when_redis_none(self):
        """Line 538: returns [None]*len(keys) when _redis is None."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")
        cache._initialized = True

        result = await cache.batch_get(["k1", "k2", "k3"])
        assert result == [None, None, None]

    async def test_batch_get_returns_nones_on_exception(self):
        """Lines 559-561: pipeline exception returns [None]*len(keys)."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        mock_pipeline = AsyncMock()
        mock_pipeline.get = MagicMock(return_value=mock_pipeline)
        mock_pipeline.execute = AsyncMock(side_effect=OSError("pipe broken"))

        mock_redis = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
        cache._redis = mock_redis
        cache._initialized = True

        result = await cache.batch_get(["k1", "k2"])
        assert result == [None, None]


# ---------------------------------------------------------------------------
# RedisBatchCache.batch_set() (lines 574, 577, 580, 592-594)
# ---------------------------------------------------------------------------


class TestRedisBatchCacheBatchSet:
    """Cover RedisBatchCache.batch_set() edge-case branches."""

    async def test_batch_set_empty_items_returns_empty(self):
        """Line 574: empty items list returns []."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        result = await cache.batch_set([])
        assert result == []

    async def test_batch_set_triggers_initialize(self):
        """Line 577: batch_set calls initialize when not initialized."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        original = bc.REDIS_AVAILABLE
        try:
            bc.REDIS_AVAILABLE = False
            result = await cache.batch_set([("k1", {"v": 1}), ("k2", {"v": 2})])
            assert result == [False, False]
        finally:
            bc.REDIS_AVAILABLE = original

    async def test_batch_set_returns_falses_when_redis_none(self):
        """Line 580: returns [False]*len(items) when _redis is None."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")
        cache._initialized = True

        result = await cache.batch_set([("k1", {"v": 1}), ("k2", {"v": 2})])
        assert result == [False, False]

    async def test_batch_set_returns_falses_on_exception(self):
        """Lines 592-594: pipeline exception returns [False]*len(items)."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        mock_pipeline = AsyncMock()
        mock_pipeline.setex = MagicMock(return_value=mock_pipeline)
        mock_pipeline.execute = AsyncMock(side_effect=OSError("pipe broken"))

        mock_redis = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
        cache._redis = mock_redis
        cache._initialized = True

        result = await cache.batch_set([("k1", {"v": 1}), ("k2", {"v": 2})])
        assert result == [False, False]


# ---------------------------------------------------------------------------
# RedisBatchCache.get_stats() additional path
# ---------------------------------------------------------------------------


class TestRedisBatchCacheStats:
    """Cover RedisBatchCache.get_stats() paths."""

    def test_get_stats_no_requests(self):
        """get_stats returns 0.0 hit_rate when no requests made."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")

        stats = cache.get_stats()
        assert stats["hit_rate"] == 0.0
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert stats["backend"] == "redis"
        assert stats["initialized"] is False

    async def test_get_stats_after_hits_and_misses(self):
        """get_stats computes correct hit_rate with mixed requests."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(redis_url="redis://localhost:6379")
        cache._hits = 3
        cache._misses = 1

        stats = cache.get_stats()
        assert stats["hit_rate"] == 75.0


# ---------------------------------------------------------------------------
# create_batch_cache factory (line 641)
# ---------------------------------------------------------------------------


class TestCreateBatchCacheFactory:
    """Cover create_batch_cache factory edge cases."""

    def test_create_redis_cache_without_redis_url_uses_default(self):
        """Line 641: redis backend with redis_url=None uses default URL."""
        bc = _import_batch_cache()
        cache = bc.create_batch_cache(backend="redis", redis_url=None, ttl_seconds=120)

        assert isinstance(cache, bc.RedisBatchCache)
        assert cache.redis_url == "redis://localhost:6379"
        assert cache.ttl_seconds == 120

    def test_create_redis_cache_with_explicit_redis_url(self):
        """redis backend with explicit URL stores it correctly."""
        bc = _import_batch_cache()
        cache = bc.create_batch_cache(
            backend="redis",
            redis_url="redis://myhost:6380",
            key_prefix="custom:",
        )
        assert cache.redis_url == "redis://myhost:6380"
        assert cache.key_prefix == "custom:"

    def test_create_memory_cache_with_custom_params(self):
        """memory backend passes ttl_seconds and max_size."""
        bc = _import_batch_cache()
        cache = bc.create_batch_cache(backend="memory", ttl_seconds=60, max_size=500)

        assert isinstance(cache, bc.BatchValidationCache)
        assert cache.ttl_seconds == 60
        assert cache.max_size == 500

    def test_create_default_backend_is_memory(self):
        """Default backend is memory."""
        bc = _import_batch_cache()
        cache = bc.create_batch_cache()
        assert isinstance(cache, bc.BatchValidationCache)

    def test_make_key_uses_prefix(self):
        """_make_key prepends the configured prefix."""
        bc = _import_batch_cache()
        cache = bc.RedisBatchCache(key_prefix="myprefix:")
        assert cache._make_key("abc") == "myprefix:abc"
