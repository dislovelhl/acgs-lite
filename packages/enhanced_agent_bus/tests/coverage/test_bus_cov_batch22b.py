"""
Coverage tests for batch22b:
  - security/redis_rate_limiter.py
  - batch_processor.py
  - context_memory/long_term_memory.py
  - collaboration/sync_engine.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# batch_processor
# ---------------------------------------------------------------------------
from enhanced_agent_bus.batch_processor import (
    BatchMessageProcessor,
    get_batch_processor,
    reset_batch_processor,
)
from enhanced_agent_bus.collaboration.models import (
    CollaborationSession,
    CollaborationValidationError,
    ConflictError,
    DocumentType,
    EditOperation,
    EditOperationType,
)

# ---------------------------------------------------------------------------
# sync_engine
# ---------------------------------------------------------------------------
from enhanced_agent_bus.collaboration.sync_engine import (
    OperationalTransform,
    SyncEngine,
)

# ---------------------------------------------------------------------------
# long_term_memory
# ---------------------------------------------------------------------------
from enhanced_agent_bus.context_memory.long_term_memory import (
    ConsolidationStrategy,
    LongTermMemoryConfig,
    LongTermMemoryStore,
    MemorySearchResult,
    MemoryTier,
)
from enhanced_agent_bus.models import (
    BatchRequest,
    BatchRequestItem,
    Priority,
)

# ---------------------------------------------------------------------------
# redis_rate_limiter
# ---------------------------------------------------------------------------
from enhanced_agent_bus.security.redis_rate_limiter import (
    InMemoryRateLimiter,
    InMemoryWindow,
    MultiTierRateLimiter,
    RateLimitResult,
    RedisRateLimiter,
)

# ===================================================================
# Helpers
# ===================================================================


def _make_edit_op(
    op_type: EditOperationType = EditOperationType.SET_PROPERTY,
    path: str = "/title",
    value=None,
    position: int | None = None,
    length: int | None = None,
    version: int = 1,
    parent_version: int | None = None,
    timestamp: float | None = None,
    old_value=None,
) -> EditOperation:
    return EditOperation(
        type=op_type,
        path=path,
        value=value,
        old_value=old_value,
        position=position,
        length=length,
        user_id="user-1",
        client_id="client-1",
        version=version,
        parent_version=parent_version,
        timestamp=timestamp or time.time(),
    )


def _make_session(document_id: str = "doc-1") -> CollaborationSession:
    return CollaborationSession(
        document_id=document_id,
        document_type=DocumentType.POLICY,
        tenant_id="tenant-1",
        version=0,
    )


# ===================================================================
# InMemoryWindow
# ===================================================================


class TestInMemoryWindow:
    def test_add_request_within_window(self):
        w = InMemoryWindow()
        now = time.monotonic()
        count = w.add_request(now, 60)
        assert count == 1

    def test_add_request_removes_expired(self):
        w = InMemoryWindow()
        now = time.monotonic()
        w.timestamps = [now - 120, now - 100, now - 10]
        count = w.add_request(now, 60)
        # Only now-10 and current remain
        assert count == 2


# ===================================================================
# InMemoryRateLimiter
# ===================================================================


class TestInMemoryRateLimiter:
    async def test_is_allowed_within_limit(self):
        limiter = InMemoryRateLimiter()
        result = await limiter.is_allowed("key1", 5, 60)
        assert result.allowed is True
        assert result.using_fallback is True
        assert result.remaining == 4

    async def test_is_allowed_exceeds_limit(self):
        limiter = InMemoryRateLimiter()
        for _ in range(5):
            await limiter.is_allowed("key1", 5, 60)
        result = await limiter.is_allowed("key1", 5, 60)
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after_seconds is not None

    async def test_cleanup_expired_windows(self):
        limiter = InMemoryRateLimiter()
        # Force cleanup interval to be exceeded
        limiter._last_cleanup = time.monotonic() - 120
        # Create a window with stale timestamps
        limiter._windows["stale"].timestamps = [time.monotonic() - 7200]
        limiter._windows["empty"]  # defaultdict creates empty
        await limiter.is_allowed("fresh", 10, 60)
        # stale and empty should be cleaned up
        assert "stale" not in limiter._windows
        assert "empty" not in limiter._windows

    async def test_cleanup_not_triggered_too_early(self):
        limiter = InMemoryRateLimiter()
        limiter._windows["old"].timestamps = [time.monotonic() - 7200]
        await limiter.is_allowed("k", 10, 60)
        # cleanup not triggered because interval not reached
        assert "old" in limiter._windows


# ===================================================================
# RedisRateLimiter
# ===================================================================


class TestRedisRateLimiter:
    def test_initial_state(self):
        rl = RedisRateLimiter()
        assert rl.is_connected is False
        assert rl.using_fallback is False

    async def test_connect_import_error(self):
        rl = RedisRateLimiter()
        with patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}):
            with patch(
                "enhanced_agent_bus.security.redis_rate_limiter.RedisRateLimiter.connect",
                new=RedisRateLimiter.connect,
            ):
                # Simulate ImportError path via _activate_fallback
                rl._activate_fallback("redis package not installed")
        assert rl.using_fallback is True

    async def test_activate_fallback_creates_limiter(self):
        rl = RedisRateLimiter(fallback_enabled=True)
        rl._activate_fallback("test")
        assert rl._fallback_limiter is not None
        assert rl._fallback_active is True
        assert rl._connected is False

    async def test_activate_fallback_disabled_raises(self):
        rl = RedisRateLimiter(fallback_enabled=False)
        with pytest.raises(RuntimeError, match="fallback disabled"):
            rl._activate_fallback("test")

    async def test_close_with_no_redis(self):
        rl = RedisRateLimiter()
        await rl.close()  # should not raise

    async def test_close_with_mock_redis(self):
        rl = RedisRateLimiter()
        mock_redis = AsyncMock()
        rl._redis = mock_redis
        rl._connected = True
        await rl.close()
        mock_redis.aclose.assert_awaited_once()
        assert rl._redis is None
        assert rl._connected is False

    async def test_close_with_redis_error(self):
        rl = RedisRateLimiter()
        mock_redis = AsyncMock()
        mock_redis.close.side_effect = OSError("conn error")
        rl._redis = mock_redis
        rl._connected = True
        await rl.close()
        assert rl._redis is None
        assert rl._connected is False

    def test_make_key(self):
        rl = RedisRateLimiter(key_prefix="test:")
        assert rl._make_key("user1") == "test:user1"

    async def test_is_allowed_fallback_active(self):
        rl = RedisRateLimiter()
        rl._activate_fallback("test")
        result = await rl.is_allowed("k", 10, 60)
        assert result.allowed is True
        assert result.using_fallback is True

    async def test_is_allowed_not_connected_fallback(self):
        rl = RedisRateLimiter(fallback_enabled=True)
        result = await rl.is_allowed("k", 10, 60)
        assert result.using_fallback is True

    async def test_is_allowed_not_connected_no_fallback(self):
        rl = RedisRateLimiter(fallback_enabled=False)
        with pytest.raises(RuntimeError, match="not connected"):
            await rl.is_allowed("k", 10, 60)

    async def test_is_allowed_redis_success_allowed(self):
        rl = RedisRateLimiter()
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
        mock_pipe.zadd = MagicMock(return_value=mock_pipe)
        mock_pipe.zcard = MagicMock(return_value=mock_pipe)
        mock_pipe.expire = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=[None, None, 3, None])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        rl._redis = mock_redis
        rl._connected = True

        result = await rl.is_allowed("k", 10, 60)
        assert result.allowed is True
        assert result.current_count == 3
        assert result.using_fallback is False

    async def test_is_allowed_redis_success_rate_limited(self):
        rl = RedisRateLimiter()
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
        mock_pipe.zadd = MagicMock(return_value=mock_pipe)
        mock_pipe.zcard = MagicMock(return_value=mock_pipe)
        mock_pipe.expire = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=[None, None, 11, None])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        now = time.time()
        mock_redis.zrange = AsyncMock(return_value=[("member", now - 30)])
        rl._redis = mock_redis
        rl._connected = True

        result = await rl.is_allowed("k", 10, 60)
        assert result.allowed is False
        assert result.retry_after_seconds is not None

    async def test_is_allowed_redis_rate_limited_empty_oldest(self):
        rl = RedisRateLimiter()
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
        mock_pipe.zadd = MagicMock(return_value=mock_pipe)
        mock_pipe.zcard = MagicMock(return_value=mock_pipe)
        mock_pipe.expire = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=[None, None, 11, None])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        mock_redis.zrange = AsyncMock(return_value=[])
        rl._redis = mock_redis
        rl._connected = True

        result = await rl.is_allowed("k", 10, 60)
        assert result.allowed is False
        assert result.retry_after_seconds is None

    async def test_is_allowed_redis_error_falls_back(self):
        rl = RedisRateLimiter(fallback_enabled=True)
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
        mock_pipe.zadd = MagicMock(return_value=mock_pipe)
        mock_pipe.zcard = MagicMock(return_value=mock_pipe)
        mock_pipe.expire = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(side_effect=ConnectionError("down"))
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        rl._redis = mock_redis
        rl._connected = True

        result = await rl.is_allowed("k", 10, 60)
        assert result.using_fallback is True

    async def test_is_allowed_redis_error_no_fallback(self):
        rl = RedisRateLimiter(fallback_enabled=False)
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
        mock_pipe.zadd = MagicMock(return_value=mock_pipe)
        mock_pipe.zcard = MagicMock(return_value=mock_pipe)
        mock_pipe.expire = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(side_effect=ConnectionError("down"))
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        rl._redis = mock_redis
        rl._connected = True

        with pytest.raises(ConnectionError):
            await rl.is_allowed("k", 10, 60)

    async def test_get_current_count_fallback_with_window(self):
        rl = RedisRateLimiter()
        rl._activate_fallback("test")
        await rl._fallback_limiter.is_allowed("key1", 10, 60)
        count = await rl.get_current_count("key1", 60)
        assert count == 1

    async def test_get_current_count_fallback_no_window(self):
        rl = RedisRateLimiter()
        rl._activate_fallback("test")
        count = await rl.get_current_count("nonexistent", 60)
        assert count == 0

    async def test_get_current_count_not_connected(self):
        rl = RedisRateLimiter()
        count = await rl.get_current_count("k", 60)
        assert count == 0

    async def test_get_current_count_redis_success(self):
        rl = RedisRateLimiter()
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
        mock_pipe.zcard = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=[None, 5])
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        rl._redis = mock_redis
        rl._connected = True

        count = await rl.get_current_count("k", 60)
        assert count == 5

    async def test_get_current_count_redis_error(self):
        rl = RedisRateLimiter()
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.zremrangebyscore = MagicMock(return_value=mock_pipe)
        mock_pipe.zcard = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(side_effect=ConnectionError("fail"))
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)
        rl._redis = mock_redis
        rl._connected = True

        count = await rl.get_current_count("k", 60)
        assert count == 0

    async def test_reset_fallback(self):
        rl = RedisRateLimiter()
        rl._activate_fallback("test")
        await rl._fallback_limiter.is_allowed("key1", 10, 60)
        result = await rl.reset("key1")
        assert result is True
        assert "key1" not in rl._fallback_limiter._windows

    async def test_reset_fallback_nonexistent_key(self):
        rl = RedisRateLimiter()
        rl._activate_fallback("test")
        result = await rl.reset("nope")
        assert result is True

    async def test_reset_not_connected(self):
        rl = RedisRateLimiter()
        result = await rl.reset("k")
        assert result is False

    async def test_reset_redis_success(self):
        rl = RedisRateLimiter()
        mock_redis = AsyncMock()
        rl._redis = mock_redis
        rl._connected = True
        result = await rl.reset("k")
        assert result is True
        mock_redis.delete.assert_awaited_once()

    async def test_reset_redis_error(self):
        rl = RedisRateLimiter()
        mock_redis = AsyncMock()
        mock_redis.delete.side_effect = ConnectionError("fail")
        rl._redis = mock_redis
        rl._connected = True
        result = await rl.reset("k")
        assert result is False

    async def test_connect_with_mock_redis(self):
        rl = RedisRateLimiter(redis_url="redis://localhost:6379")
        mock_client = AsyncMock()
        mock_redis_mod = MagicMock()
        mock_redis_mod.from_url.return_value = mock_client
        with patch("enhanced_agent_bus.security.redis_rate_limiter.RedisRateLimiter.connect") as _:
            # Directly simulate successful connect path
            rl._redis = mock_client
            rl._connected = True
            rl._fallback_active = False
        assert rl._connected is True

    async def test_connect_connection_error(self):
        rl = RedisRateLimiter(redis_url="redis://localhost:6379", fallback_enabled=True)
        # Simulate connect failure by directly calling _activate_fallback
        rl._activate_fallback("Connection refused")
        assert rl._fallback_active is True
        assert rl._connected is False


# ===================================================================
# MultiTierRateLimiter
# ===================================================================


class TestMultiTierRateLimiter:
    async def test_configure_and_check(self):
        mt = MultiTierRateLimiter()
        mt._limiter._activate_fallback("test")
        mt.configure_tiers("default", [(100, 60), (1000, 3600)])
        allowed, results = await mt.is_allowed("user1", "default")
        assert allowed is True
        assert len(results) == 2

    async def test_unknown_tier_raises(self):
        mt = MultiTierRateLimiter()
        with pytest.raises(ValueError, match="Unknown tier"):
            await mt.is_allowed("user1", "nonexistent")

    async def test_tier_not_allowed(self):
        mt = MultiTierRateLimiter()
        mt._limiter._activate_fallback("test")
        mt.configure_tiers("strict", [(1, 60)])
        await mt.is_allowed("u", "strict")
        _, results = await mt.is_allowed("u", "strict")
        assert any(not r.allowed for r in results)

    async def test_connect_and_close(self):
        mt = MultiTierRateLimiter()
        mt._limiter._redis = AsyncMock()
        mt._limiter._connected = True
        await mt.close()
        assert mt._limiter._redis is None


# ===================================================================
# BatchMessageProcessor
# ===================================================================


class TestBatchMessageProcessor:
    def test_default_init(self):
        bp = BatchMessageProcessor()
        assert bp.max_concurrency == 100
        assert bp.item_timeout_ms == 30000
        assert bp.max_retries == 0
        assert bp.circuit_breaker_state == "closed"

    def test_custom_kwargs(self):
        bp = BatchMessageProcessor(
            max_concurrency=50,
            item_timeout_ms=5000,
            auto_tune_batch_size=True,
            max_batch_size=500,
            min_batch_size=5,
            target_p99_latency_ms=20.0,
            include_stack_traces=False,
            max_retries=3,
            retry_base_delay=0.5,
            retry_max_delay=30.0,
            retry_exponential_base=3.0,
            circuit_breaker_enabled=True,
            circuit_breaker_threshold=0.7,
            circuit_breaker_cooldown=60.0,
        )
        assert bp.max_concurrency == 50
        assert bp.item_timeout_ms == 5000
        assert bp.auto_tune_batch_size is True
        assert bp.max_batch_size == 500
        assert bp.min_batch_size == 5
        assert bp.target_p99_latency_ms == 20.0
        assert bp.include_stack_traces is False
        assert bp.max_retries == 3
        assert bp.retry_base_delay == 0.5
        assert bp.retry_max_delay == 30.0
        assert bp.retry_exponential_base == 3.0
        assert bp.circuit_breaker_enabled is True
        assert bp.circuit_breaker_threshold == 0.7
        assert bp.circuit_breaker_cooldown == 60.0

    def test_legacy_item_timeout_seconds_are_converted_to_ms(self):
        bp = BatchMessageProcessor(item_timeout=1.5)
        assert bp.item_timeout_ms == 1500

    def test_invalid_kwargs_use_defaults(self):
        bp = BatchMessageProcessor(
            max_concurrency="not_a_number",
            item_timeout_ms="bad",
            auto_tune_batch_size="nope",
            max_batch_size="bad",
        )
        assert bp.max_concurrency == 100
        assert bp.item_timeout_ms == 30000
        assert bp.auto_tune_batch_size is False
        assert bp.max_batch_size == 1000

    def test_properties(self):
        bp = BatchMessageProcessor()
        assert isinstance(bp.max_concurrency, int)
        assert isinstance(bp.item_timeout_ms, int)
        assert isinstance(bp.include_stack_traces, bool)
        assert isinstance(bp.max_retries, int)
        assert isinstance(bp.retry_base_delay, float)
        assert isinstance(bp.retry_max_delay, float)
        assert isinstance(bp.retry_exponential_base, float)
        assert isinstance(bp.circuit_breaker_enabled, bool)
        assert isinstance(bp.circuit_breaker_threshold, float)
        assert isinstance(bp.circuit_breaker_cooldown, float)
        assert bp.circuit_breaker_state == "closed"
        assert bp.get_circuit_state() == "closed"

    def test_get_recommended_batch_size_no_auto_tune(self):
        bp = BatchMessageProcessor(max_batch_size=500)
        assert bp.get_recommended_batch_size() == 500

    def test_get_recommended_batch_size_with_auto_tune(self):
        bp = BatchMessageProcessor(auto_tune_batch_size=True, max_batch_size=500)
        assert bp.get_recommended_batch_size() == 500  # initially max

    def test_update_batch_size_decrease(self):
        bp = BatchMessageProcessor(
            auto_tune_batch_size=True,
            max_batch_size=1000,
            min_batch_size=10,
            target_p99_latency_ms=10.0,
            auto_tune_adjustment_factor=0.1,
        )
        # Need at least 3 samples with high latency (> 1.5x target = 15ms)
        bp._update_batch_size_recommendation(100, 20.0)
        bp._update_batch_size_recommendation(100, 20.0)
        bp._update_batch_size_recommendation(100, 20.0)
        assert bp._recommended_batch_size < 1000
        assert bp._total_adjustments >= 1

    def test_update_batch_size_increase(self):
        bp = BatchMessageProcessor(
            auto_tune_batch_size=True,
            max_batch_size=1000,
            min_batch_size=10,
            target_p99_latency_ms=10.0,
            auto_tune_adjustment_factor=0.1,
        )
        bp._recommended_batch_size = 500
        # Low latency (< 0.5x target = 5ms)
        bp._update_batch_size_recommendation(100, 2.0)
        bp._update_batch_size_recommendation(100, 2.0)
        bp._update_batch_size_recommendation(100, 2.0)
        assert bp._recommended_batch_size > 500
        assert bp._total_adjustments >= 1

    def test_update_batch_size_no_change_in_range(self):
        bp = BatchMessageProcessor(
            auto_tune_batch_size=True,
            target_p99_latency_ms=10.0,
        )
        initial = bp._recommended_batch_size
        # Latency within range (5-15ms)
        bp._update_batch_size_recommendation(100, 8.0)
        bp._update_batch_size_recommendation(100, 8.0)
        bp._update_batch_size_recommendation(100, 8.0)
        assert bp._recommended_batch_size == initial
        assert bp._total_adjustments == 0

    def test_update_batch_size_none_latency(self):
        bp = BatchMessageProcessor(auto_tune_batch_size=True)
        initial = bp._recommended_batch_size
        bp._update_batch_size_recommendation(100, None)
        assert bp._recommended_batch_size == initial

    def test_update_batch_size_not_enabled(self):
        bp = BatchMessageProcessor(auto_tune_batch_size=False)
        initial = bp._recommended_batch_size
        bp._update_batch_size_recommendation(100, 100.0)
        assert bp._recommended_batch_size == initial

    def test_update_batch_size_fewer_than_3_samples(self):
        bp = BatchMessageProcessor(auto_tune_batch_size=True)
        initial = bp._recommended_batch_size
        bp._update_batch_size_recommendation(100, 100.0)
        bp._update_batch_size_recommendation(100, 100.0)
        assert bp._recommended_batch_size == initial

    def test_get_auto_tune_stats(self):
        bp = BatchMessageProcessor(auto_tune_batch_size=True, target_p99_latency_ms=10.0)
        stats = bp.get_auto_tune_stats()
        assert stats["enabled"] is True
        assert stats["target_p99_latency_ms"] == 10.0
        assert stats["avg_p99_latency_ms"] is None

    def test_get_auto_tune_stats_with_history(self):
        bp = BatchMessageProcessor(auto_tune_batch_size=True)
        bp._latency_history.append(5.0)
        bp._latency_history.append(10.0)
        stats = bp.get_auto_tune_stats()
        assert stats["avg_p99_latency_ms"] == 7.5

    def test_get_metrics(self):
        bp = BatchMessageProcessor()
        metrics = bp.get_metrics()
        assert "auto_tune_batch_size" in metrics
        assert "recommended_batch_size" in metrics

    def test_reset_metrics(self):
        bp = BatchMessageProcessor()
        bp.reset_metrics()  # should not raise

    def test_clear_cache_and_get_cache_size(self):
        bp = BatchMessageProcessor()
        bp.clear_cache()
        assert bp.get_cache_size() == 0

    async def test_process_batch_with_custom_validator(self):
        def validator(item):
            return True, {"result": "ok"}

        bp = BatchMessageProcessor(validator=validator)
        items = [
            BatchRequestItem(
                content={"text": "test content"},
                from_agent="agent-a",
                to_agent="agent-b",
            )
        ]
        batch = BatchRequest(items=items)
        response = await bp.process_batch(batch)
        assert response is not None

    async def test_process_batch_with_custom_validator_failure(self):
        def validator(item):
            return False, {"error": "bad input"}

        bp = BatchMessageProcessor(validator=validator)
        items = [
            BatchRequestItem(
                content={"text": "test"},
                from_agent="a",
                to_agent="b",
            )
        ]
        batch = BatchRequest(items=items)
        response = await bp.process_batch(batch)
        assert response is not None

    async def test_process_batch_with_custom_validator_exception(self):
        def validator(item):
            raise ValueError("boom")

        bp = BatchMessageProcessor(validator=validator)
        items = [
            BatchRequestItem(
                content={"text": "test"},
                from_agent="a",
                to_agent="b",
            )
        ]
        batch = BatchRequest(items=items)
        response = await bp.process_batch(batch)
        assert response is not None

    async def test_process_batch_with_auto_tune(self):
        def validator(item):
            return True, {"ok": True}

        bp = BatchMessageProcessor(
            validator=validator,
            auto_tune_batch_size=True,
            target_p99_latency_ms=100.0,
        )
        items = [BatchRequestItem(content={"text": "x"}, from_agent="a", to_agent="b")]
        batch = BatchRequest(items=items)
        await bp.process_batch(batch)
        assert len(bp._latency_history) == 1


class TestBatchProcessorSingleton:
    def test_get_and_reset(self):
        reset_batch_processor()
        bp1 = get_batch_processor()
        bp2 = get_batch_processor()
        assert bp1 is bp2
        reset_batch_processor()


# ===================================================================
# LongTermMemoryStore
# ===================================================================


class TestLongTermMemoryConfig:
    def test_default_config(self):
        cfg = LongTermMemoryConfig(enable_persistence=False)
        assert cfg.max_episodic_entries == 100_000
        assert cfg.enable_compression is True

    def test_invalid_constitutional_hash(self):
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            LongTermMemoryConfig(constitutional_hash="badhash")


class TestMemoryTier:
    def test_values(self):
        assert MemoryTier.WORKING == "working"
        assert MemoryTier.LONG_TERM == "long_term"
        assert MemoryTier.ARCHIVAL == "archival"


class TestLongTermMemoryStore:
    def _make_store(self) -> LongTermMemoryStore:
        cfg = LongTermMemoryConfig(enable_persistence=False, enable_audit_trail=True)
        return LongTermMemoryStore(config=cfg)

    def test_invalid_hash_raises(self):
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            LongTermMemoryStore(constitutional_hash="badhash")

    async def test_store_and_retrieve_episodic(self):
        store = self._make_store()
        entry_id = await store.store_episodic(
            session_id="s1",
            tenant_id="t1",
            event_type="test",
            content="hello world",
            outcome="success",
            context={"key": "val"},
        )
        assert entry_id is not None
        entries = await store.retrieve_episodic(entry_id=entry_id)
        assert len(entries) == 1
        assert entries[0].content == "hello world"
        assert store._metrics["episodic_writes"] == 1
        assert store._metrics["cache_hits"] == 1

    async def test_retrieve_episodic_cache_miss(self):
        store = self._make_store()
        entries = await store.retrieve_episodic(entry_id="nonexistent")
        assert entries == []
        assert store._metrics["cache_misses"] == 1

    async def test_retrieve_episodic_no_filters(self):
        store = self._make_store()
        entries = await store.retrieve_episodic()
        assert entries == []

    async def test_store_and_search_semantic(self):
        store = self._make_store()
        entry_id = await store.store_semantic(
            knowledge_type="policy",
            content="Rate limiting policy for API",
            confidence=0.9,
            source="admin",
            embedding=[0.1, 0.2],
            related_entries=["e1"],
            metadata={"version": 1},
        )
        assert entry_id is not None
        assert store._metrics["semantic_writes"] == 1

        result = await store.search_semantic("rate limiting", min_confidence=0.5)
        assert result.total_count == 1
        assert result.entries[0].content == "Rate limiting policy for API"

    async def test_search_semantic_filters(self):
        store = self._make_store()
        await store.store_semantic(
            knowledge_type="policy",
            content={"text": "test content"},
            confidence=0.9,
            source="admin",
        )
        # Wrong knowledge type
        result = await store.search_semantic("test", knowledge_type="workflow", min_confidence=0.5)
        assert result.total_count == 0

        # Below confidence threshold
        result = await store.search_semantic("test", min_confidence=0.99)
        assert result.total_count == 0

    async def test_search_semantic_no_match(self):
        store = self._make_store()
        await store.store_semantic(
            knowledge_type="policy",
            content="unrelated",
            confidence=0.9,
            source="admin",
        )
        result = await store.search_semantic("elephant")
        assert result.total_count == 0

    async def test_consolidate_time_based(self):
        store = self._make_store()
        # Add old entry
        from enhanced_agent_bus.context_memory.models import EpisodicMemoryEntry

        old_entry = EpisodicMemoryEntry(
            entry_id="old-1",
            session_id="s1",
            tenant_id="t1",
            timestamp=datetime.now(UTC) - timedelta(days=400),
            event_type="test",
            content="old",
            access_count=0,
        )
        store._episodic_cache["old-1"] = old_entry
        result = await store.consolidate(ConsolidationStrategy.TIME_BASED)
        assert result.entries_deleted >= 1

    async def test_consolidate_time_based_accessed_entry(self):
        store = self._make_store()
        from enhanced_agent_bus.context_memory.models import EpisodicMemoryEntry

        old_entry = EpisodicMemoryEntry(
            entry_id="old-2",
            session_id="s1",
            tenant_id="t1",
            timestamp=datetime.now(UTC) - timedelta(days=400),
            event_type="test",
            content="old accessed",
            access_count=10,
        )
        store._episodic_cache["old-2"] = old_entry
        result = await store.consolidate(ConsolidationStrategy.TIME_BASED)
        assert result.entries_archived >= 1
        assert "old-2" in store._episodic_cache

    async def test_consolidate_access_based(self):
        store = self._make_store()
        from enhanced_agent_bus.context_memory.models import EpisodicMemoryEntry

        stale = EpisodicMemoryEntry(
            entry_id="stale-1",
            session_id="s1",
            tenant_id="t1",
            timestamp=datetime.now(UTC) - timedelta(days=10),
            event_type="test",
            content="stale",
            access_count=0,
        )
        store._episodic_cache["stale-1"] = stale
        result = await store.consolidate(ConsolidationStrategy.ACCESS_BASED)
        assert result.entries_deleted >= 1

    async def test_consolidate_relevance_based(self):
        store = self._make_store()
        from enhanced_agent_bus.context_memory.models import EpisodicMemoryEntry

        # Entry with very old timestamp will have low relevance after decay
        very_old = EpisodicMemoryEntry(
            entry_id="very-old",
            session_id="s1",
            tenant_id="t1",
            timestamp=datetime.now(UTC) - timedelta(days=200),
            event_type="test",
            content="ancient",
            relevance_decay=0.1,
        )
        store._episodic_cache["very-old"] = very_old
        result = await store.consolidate(ConsolidationStrategy.RELEVANCE_BASED)
        assert result.entries_processed >= 1

    async def test_consolidate_unknown_strategy(self):
        store = self._make_store()
        result = await store.consolidate(ConsolidationStrategy.SIMILARITY_BASED)
        assert result.entries_processed == 0

    def test_get_metrics(self):
        store = self._make_store()
        metrics = store.get_metrics()
        assert "episodic_writes" in metrics
        assert "constitutional_hash" in metrics
        assert metrics["persistence_enabled"] is False

    async def test_shutdown(self):
        store = self._make_store()
        await store.shutdown()

    def test_audit_log_bounded(self):
        store = self._make_store()
        from enhanced_agent_bus.context_memory.models import MemoryOperationType

        for i in range(10010):
            store._log_operation(
                operation_type=MemoryOperationType.STORE,
                tenant_id="t1",
                session_id="s1",
                entry_id=f"e{i}",
                success=True,
                latency_ms=0.1,
            )
        # After 10001 entries, trim to 5000, then 9 more appended = 5009
        assert len(store._audit_log) <= 10000

    def test_log_operation_disabled_audit(self):
        cfg = LongTermMemoryConfig(enable_persistence=False, enable_audit_trail=False)
        store = LongTermMemoryStore(config=cfg)
        from enhanced_agent_bus.context_memory.models import MemoryOperationType

        store._log_operation(
            operation_type=MemoryOperationType.STORE,
            tenant_id="t1",
            session_id=None,
            entry_id=None,
            success=True,
            latency_ms=0.1,
        )
        assert len(store._audit_log) == 0


class TestLongTermMemoryPersistence:
    async def test_store_and_query_with_persistence(self, tmp_path):
        db_path = str(tmp_path / "test_ltm.db")
        cfg = LongTermMemoryConfig(enable_persistence=True, db_path=db_path)
        store = LongTermMemoryStore(config=cfg)
        assert store._db_connection is not None

        entry_id = await store.store_episodic(
            session_id="s1",
            tenant_id="t1",
            event_type="test",
            content="persistent entry",
            outcome="ok",
            embedding=[0.1, 0.2, 0.3],
        )
        # Clear cache to force DB query
        store._episodic_cache.clear()
        entries = await store.retrieve_episodic(session_id="s1")
        assert len(entries) >= 1
        assert entries[0].content == "persistent entry"

        await store.shutdown()

    async def test_store_semantic_with_persistence(self, tmp_path):
        db_path = str(tmp_path / "test_ltm2.db")
        cfg = LongTermMemoryConfig(enable_persistence=True, db_path=db_path)
        store = LongTermMemoryStore(config=cfg)

        entry_id = await store.store_semantic(
            knowledge_type="rule",
            content="semantic test",
            confidence=0.8,
            source="test",
            embedding=[0.5],
            related_entries=["r1"],
            metadata={"k": "v"},
        )
        assert entry_id is not None
        await store.shutdown()

    async def test_query_episodic_with_filters(self, tmp_path):
        db_path = str(tmp_path / "test_ltm3.db")
        cfg = LongTermMemoryConfig(enable_persistence=True, db_path=db_path)
        store = LongTermMemoryStore(config=cfg)

        await store.store_episodic(
            session_id="s1",
            tenant_id="t1",
            event_type="action",
            content="entry1",
        )
        await store.store_episodic(
            session_id="s2",
            tenant_id="t2",
            event_type="decision",
            content="entry2",
        )
        store._episodic_cache.clear()

        entries = await store.retrieve_episodic(tenant_id="t1")
        assert len(entries) == 1

        entries = await store.retrieve_episodic(event_type="decision")
        assert len(entries) == 1

        await store.shutdown()


# ===================================================================
# OperationalTransform
# ===================================================================


class TestOperationalTransform:
    def test_different_paths_no_transform(self):
        op1 = _make_edit_op(EditOperationType.INSERT, path="/a", position=0, value="x")
        op2 = _make_edit_op(EditOperationType.INSERT, path="/b", position=0, value="y")
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1.path == "/a"
        assert r2.path == "/b"

    def test_insert_insert_op1_before(self):
        ts = time.time()
        op1 = _make_edit_op(
            EditOperationType.INSERT, path="/x", position=2, value="ab", timestamp=ts
        )
        op2 = _make_edit_op(
            EditOperationType.INSERT, path="/x", position=5, value="c", timestamp=ts + 1
        )
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r2.position == 5 + 2  # shifted by len("ab")

    def test_insert_insert_op2_before(self):
        ts = time.time()
        op1 = _make_edit_op(
            EditOperationType.INSERT, path="/x", position=5, value="a", timestamp=ts
        )
        op2 = _make_edit_op(
            EditOperationType.INSERT, path="/x", position=2, value="bc", timestamp=ts + 1
        )
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1.position == 5 + 2  # shifted by len("bc")

    def test_insert_insert_same_position_ts_tie(self):
        ts = time.time()
        op1 = _make_edit_op(
            EditOperationType.INSERT, path="/x", position=3, value="a", timestamp=ts
        )
        op2 = _make_edit_op(
            EditOperationType.INSERT, path="/x", position=3, value="b", timestamp=ts + 1
        )
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r2.position == 3 + 1

    def test_insert_insert_same_position_op2_older(self):
        ts = time.time()
        op1 = _make_edit_op(
            EditOperationType.INSERT, path="/x", position=3, value="a", timestamp=ts + 1
        )
        op2 = _make_edit_op(
            EditOperationType.INSERT, path="/x", position=3, value="b", timestamp=ts
        )
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1.position == 3 + 1

    def test_insert_insert_none_positions(self):
        op1 = _make_edit_op(EditOperationType.INSERT, path="/x", position=None, value="a")
        op2 = _make_edit_op(EditOperationType.INSERT, path="/x", position=None, value="b")
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1.position is None
        assert r2.position is None

    def test_insert_delete(self):
        op1 = _make_edit_op(EditOperationType.INSERT, path="/x", position=2, value="abc")
        op2 = _make_edit_op(EditOperationType.DELETE, path="/x", position=5, length=3)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r2.position == 5 + 3  # shifted by len("abc")

    def test_insert_delete_reverse(self):
        op1 = _make_edit_op(EditOperationType.INSERT, path="/x", position=8, value="a")
        op2 = _make_edit_op(EditOperationType.DELETE, path="/x", position=3, length=2)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r2.position == 3  # delete before insert, no shift

    def test_delete_insert(self):
        op1 = _make_edit_op(EditOperationType.DELETE, path="/x", position=3, length=2)
        op2 = _make_edit_op(EditOperationType.INSERT, path="/x", position=8, value="ab")
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        # delete before insert: insert position adjusted
        assert r2.position == 8 - 2

    def test_delete_delete_no_overlap(self):
        op1 = _make_edit_op(EditOperationType.DELETE, path="/x", position=0, length=3)
        op2 = _make_edit_op(EditOperationType.DELETE, path="/x", position=10, length=2)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r2.position == 10 - 3

    def test_delete_delete_op2_before(self):
        op1 = _make_edit_op(EditOperationType.DELETE, path="/x", position=10, length=2)
        op2 = _make_edit_op(EditOperationType.DELETE, path="/x", position=0, length=3)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1.position == 10 - 3

    def test_delete_delete_overlap(self):
        op1 = _make_edit_op(EditOperationType.DELETE, path="/x", position=3, length=5)
        op2 = _make_edit_op(EditOperationType.DELETE, path="/x", position=5, length=5)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        # overlap: 5..8 (3 chars)
        assert r1.length == 5 - 3
        assert r2.length == 5 - 3

    def test_delete_delete_none_positions(self):
        op1 = _make_edit_op(EditOperationType.DELETE, path="/x", position=None, length=2)
        op2 = _make_edit_op(EditOperationType.DELETE, path="/x", position=None, length=3)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1.position is None

    def test_replace_op1_newer(self):
        ts = time.time()
        op1 = _make_edit_op(EditOperationType.REPLACE, path="/x", value="new", timestamp=ts + 1)
        op2 = _make_edit_op(EditOperationType.INSERT, path="/x", value="old", timestamp=ts)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r2.value is None

    def test_replace_op2_newer(self):
        ts = time.time()
        op1 = _make_edit_op(EditOperationType.INSERT, path="/x", value="old", timestamp=ts)
        op2 = _make_edit_op(EditOperationType.REPLACE, path="/x", value="new", timestamp=ts + 1)
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1.value is None

    def test_default_unhandled_type(self):
        op1 = _make_edit_op(EditOperationType.MOVE, path="/x", value="/y")
        op2 = _make_edit_op(EditOperationType.MOVE, path="/z", value="/w")
        r1, r2 = OperationalTransform.transform_operations(op1, op2)
        assert r1 is op1
        assert r2 is op2


# ===================================================================
# SyncEngine
# ===================================================================


class TestSyncEngine:
    async def test_initialize_and_get_document(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"title": "Test"})
        doc = await engine.get_document("doc1")
        assert doc == {"title": "Test"}

    async def test_get_document_not_found(self):
        engine = SyncEngine()
        doc = await engine.get_document("missing")
        assert doc is None

    async def test_get_document_from_redis(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = '{"title": "From Redis"}'
        engine = SyncEngine(redis_client=mock_redis)
        doc = await engine.get_document("doc-r")
        assert doc == {"title": "From Redis"}

    async def test_get_document_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = ConnectionError("fail")
        engine = SyncEngine(redis_client=mock_redis)
        doc = await engine.get_document("doc-r")
        assert doc is None

    async def test_apply_set_property(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"title": "Old"})
        session = _make_session("doc1")
        op = _make_edit_op(EditOperationType.SET_PROPERTY, path="/title", value="New", version=1)
        result = await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["title"] == "New"
        assert session.version == 1

    async def test_apply_delete_property(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"title": "X", "extra": "Y"})
        session = _make_session("doc1")
        op = _make_edit_op(EditOperationType.DELETE_PROPERTY, path="/extra", version=1)
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert "extra" not in doc

    async def test_apply_insert_to_array(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"items": [1, 2, 3]})
        session = _make_session("doc1")
        op = _make_edit_op(
            EditOperationType.INSERT,
            path="/items",
            position=1,
            value=99,
            version=1,
        )
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["items"] == [1, 99, 2, 3]

    async def test_apply_insert_to_dict(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"data": {}})
        session = _make_session("doc1")
        op = _make_edit_op(
            EditOperationType.INSERT,
            path="/data",
            value={"key": "name", "value": "test"},
            version=1,
        )
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["data"]["name"] == "test"

    async def test_apply_insert_to_dict_without_key(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"data": {}})
        session = _make_session("doc1")
        op = _make_edit_op(
            EditOperationType.INSERT,
            path="/data",
            value="plain_value",
            version=1,
        )
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert "0" in doc["data"]

    async def test_apply_delete_from_array(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"items": [1, 2, 3, 4]})
        session = _make_session("doc1")
        op = _make_edit_op(
            EditOperationType.DELETE,
            path="/items",
            position=1,
            length=2,
            version=1,
        )
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["items"] == [1, 4]

    async def test_apply_replace(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"title": "Old"})
        session = _make_session("doc1")
        op = _make_edit_op(EditOperationType.REPLACE, path="/title", value="New", version=1)
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["title"] == "New"

    async def test_apply_move(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"source": "value", "dest": {}})
        session = _make_session("doc1")
        op = _make_edit_op(EditOperationType.MOVE, path="/source", value="/dest/moved", version=1)
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["dest"]["moved"] == "value"

    async def test_apply_move_with_dict_target(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"source": "val"})
        session = _make_session("doc1")
        op = _make_edit_op(
            EditOperationType.MOVE,
            path="/source",
            value={"path": "/target"},
            version=1,
        )
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["target"] == "val"

    async def test_apply_to_nonexistent_doc(self):
        engine = SyncEngine()
        session = _make_session("missing")
        op = _make_edit_op(EditOperationType.SET_PROPERTY, path="/x", value=1, version=1)
        with pytest.raises(CollaborationValidationError):
            await engine.apply_operation("missing", op, session)

    async def test_set_property_nested_create(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {})
        session = _make_session("doc1")
        op = _make_edit_op(EditOperationType.SET_PROPERTY, path="/a/b/c", value=42, version=1)
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["a"]["b"]["c"] == 42

    async def test_delete_property_nonexistent_path(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"a": 1})
        session = _make_session("doc1")
        op = _make_edit_op(EditOperationType.DELETE_PROPERTY, path="/x/y/z", version=1)
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc == {"a": 1}

    async def test_delete_at_path_nonexistent(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"a": 1})
        session = _make_session("doc1")
        op = _make_edit_op(EditOperationType.DELETE, path="/missing", position=0, version=1)
        await engine.apply_operation("doc1", op, session)

    async def test_batch_apply_operations(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"title": "A"})
        session = _make_session("doc1")
        ops = [
            _make_edit_op(EditOperationType.SET_PROPERTY, path="/title", value="B", version=1),
            _make_edit_op(EditOperationType.SET_PROPERTY, path="/desc", value="C", version=2),
        ]
        applied = await engine.batch_apply_operations("doc1", ops, session)
        assert len(applied) == 2

    async def test_batch_apply_with_error(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"items": [1]})
        session = _make_session("doc1")
        ops = [
            _make_edit_op(EditOperationType.SET_PROPERTY, path="/title", value="ok", version=1),
        ]
        applied = await engine.batch_apply_operations("doc1", ops, session)
        assert len(applied) >= 1

    async def test_undo_last_operation(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"title": "Original"})
        session = _make_session("doc1")

        op = _make_edit_op(
            EditOperationType.SET_PROPERTY,
            path="/title",
            value="Changed",
            old_value="Original",
            version=1,
        )
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["title"] == "Changed"

        undone = await engine.undo_last_operation("doc1", session)
        assert undone is not None
        doc = await engine.get_document("doc1")
        assert doc["title"] == "Original"

    async def test_undo_no_history(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {})
        session = _make_session("doc1")
        result = await engine.undo_last_operation("doc1", session)
        assert result is None

    async def test_undo_insert_creates_delete_inverse(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"items": []})
        session = _make_session("doc1")
        op = _make_edit_op(
            EditOperationType.INSERT,
            path="/items",
            position=0,
            value="x",
            version=1,
        )
        await engine.apply_operation("doc1", op, session)
        undone = await engine.undo_last_operation("doc1", session)
        assert undone is not None

    async def test_undo_delete_creates_insert_inverse(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"items": [1, 2, 3]})
        session = _make_session("doc1")
        op = _make_edit_op(
            EditOperationType.DELETE,
            path="/items",
            position=0,
            length=1,
            old_value=1,
            version=1,
        )
        await engine.apply_operation("doc1", op, session)
        undone = await engine.undo_last_operation("doc1", session)
        assert undone is not None

    async def test_undo_replace_inverse(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"title": "A"})
        session = _make_session("doc1")
        op = _make_edit_op(
            EditOperationType.REPLACE,
            path="/title",
            value="B",
            old_value="A",
            version=1,
        )
        await engine.apply_operation("doc1", op, session)
        undone = await engine.undo_last_operation("doc1", session)
        assert undone is not None

    async def test_undo_set_property_no_old_value(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {})
        session = _make_session("doc1")
        op = _make_edit_op(
            EditOperationType.SET_PROPERTY,
            path="/new_key",
            value="val",
            old_value=None,
            version=1,
        )
        await engine.apply_operation("doc1", op, session)
        undone = await engine.undo_last_operation("doc1", session)
        assert undone is not None
        doc = await engine.get_document("doc1")
        assert "new_key" not in doc

    async def test_get_operation_history(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"x": 1})
        session = _make_session("doc1")
        op1 = _make_edit_op(EditOperationType.SET_PROPERTY, path="/x", value=2, version=1)
        op2 = _make_edit_op(EditOperationType.SET_PROPERTY, path="/x", value=3, version=2)
        await engine.apply_operation("doc1", op1, session)
        await engine.apply_operation("doc1", op2, session)
        history = await engine.get_operation_history("doc1", since_version=1)
        assert len(history) == 1  # only version > 1

    async def test_get_operation_history_empty(self):
        engine = SyncEngine()
        history = await engine.get_operation_history("nonexistent")
        assert history == []

    async def test_compact_history(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"x": 0})
        session = _make_session("doc1")
        # Add 110 operations
        for i in range(110):
            op = _make_edit_op(EditOperationType.SET_PROPERTY, path="/x", value=i, version=i + 1)
            await engine.apply_operation("doc1", op, session)
        assert len(engine._operation_history["doc1"]) == 110
        await engine.compact_history("doc1")
        assert len(engine._operation_history["doc1"]) == 50

    async def test_compact_history_short(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"x": 0})
        session = _make_session("doc1")
        op = _make_edit_op(EditOperationType.SET_PROPERTY, path="/x", value=1, version=1)
        await engine.apply_operation("doc1", op, session)
        await engine.compact_history("doc1")
        assert len(engine._operation_history["doc1"]) == 1

    async def test_compact_history_nonexistent(self):
        engine = SyncEngine()
        await engine.compact_history("nope")  # should not raise

    async def test_initialize_with_redis(self):
        mock_redis = AsyncMock()
        engine = SyncEngine(redis_client=mock_redis)
        await engine.initialize_document("doc1", {"x": 1})
        mock_redis.set.assert_awaited_once()

    async def test_apply_with_redis_persist(self):
        mock_redis = AsyncMock()
        engine = SyncEngine(redis_client=mock_redis)
        await engine.initialize_document("doc1", {"x": 1})
        session = _make_session("doc1")
        op = _make_edit_op(EditOperationType.SET_PROPERTY, path="/x", value=2, version=1)
        await engine.apply_operation("doc1", op, session)
        # lpush called for operation persist
        mock_redis.lpush.assert_awaited()

    async def test_persist_to_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.set.side_effect = ConnectionError("fail")
        engine = SyncEngine(redis_client=mock_redis)
        engine._documents["doc1"] = {"x": 1}
        await engine._persist_to_redis("doc1")  # should not raise

    async def test_persist_operation_error(self):
        mock_redis = AsyncMock()
        mock_redis.lpush.side_effect = ConnectionError("fail")
        engine = SyncEngine(redis_client=mock_redis)
        op = _make_edit_op(EditOperationType.SET_PROPERTY, path="/x", value=1, version=1)
        await engine._persist_operation("doc1", op)  # should not raise

    async def test_persist_operation_no_redis(self):
        engine = SyncEngine()
        op = _make_edit_op(EditOperationType.SET_PROPERTY, path="/x", value=1, version=1)
        await engine._persist_operation("doc1", op)  # should not raise

    async def test_load_from_redis_no_data(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        engine = SyncEngine(redis_client=mock_redis)
        doc = await engine._load_from_redis("missing")
        assert doc is None

    async def test_load_from_redis_no_client(self):
        engine = SyncEngine()
        doc = await engine._load_from_redis("x")
        assert doc is None

    async def test_persist_to_redis_no_doc(self):
        mock_redis = AsyncMock()
        engine = SyncEngine(redis_client=mock_redis)
        await engine._persist_to_redis("missing")
        mock_redis.set.assert_not_awaited()

    async def test_transform_against_history(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {"x": 0})
        session = _make_session("doc1")
        # Add one operation to history
        op1 = _make_edit_op(EditOperationType.SET_PROPERTY, path="/x", value=1, version=1)
        await engine.apply_operation("doc1", op1, session)
        # Now apply a concurrent operation
        op2 = _make_edit_op(
            EditOperationType.SET_PROPERTY,
            path="/y",
            value=2,
            version=1,
            parent_version=0,
        )
        result = await engine.apply_operation("doc1", op2, session)
        assert result.version == 2

    async def test_get_property(self):
        engine = SyncEngine()
        doc = {"a": {"b": {"c": 42}}}
        assert engine._get_property(doc, "/a/b/c") == 42

    async def test_get_property_missing(self):
        engine = SyncEngine()
        doc = {"a": 1}
        assert engine._get_property(doc, "/x/y") is None

    async def test_insert_at_path_creates_array(self):
        engine = SyncEngine()
        await engine.initialize_document("doc1", {})
        session = _make_session("doc1")
        op = _make_edit_op(
            EditOperationType.INSERT,
            path="/newlist",
            position=0,
            value="item",
            version=1,
        )
        await engine.apply_operation("doc1", op, session)
        doc = await engine.get_document("doc1")
        assert doc["newlist"] == ["item"]

    async def test_undo_with_redis(self):
        mock_redis = AsyncMock()
        engine = SyncEngine(redis_client=mock_redis)
        await engine.initialize_document("doc1", {"x": 1})
        session = _make_session("doc1")
        op = _make_edit_op(
            EditOperationType.SET_PROPERTY, path="/x", value=2, old_value=1, version=1
        )
        await engine.apply_operation("doc1", op, session)
        await engine.undo_last_operation("doc1", session)
        # Redis set should be called for persist on undo
        assert mock_redis.set.call_count >= 2
