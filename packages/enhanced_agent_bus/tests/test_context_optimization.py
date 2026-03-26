"""Tests for enhanced_agent_bus.context_optimization — coverage boost.

Constitutional Hash: 608508a9bd224290

Tests SpecDeltaCompressor, CachedGovernanceValidator, PartitionBroker,
OptimizedAgentBus, and factory functions.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus.context_optimization import (
    CONTEXT_OPTIMIZATION_AVAILABLE,
    CachedGovernanceValidator,
    CompressionResult,
    CompressionStrategy,
    GovernanceDecision,
    GovernanceValidatorProtocol,
    OptimizedAgentBus,
    PartitionBroker,
    PartitionedMessage,
    SpecBaseline,
    SpecDeltaCompressor,
    TopicConfig,
    TopicPriority,
    ValidationContext,
    create_cached_validator,
    create_optimized_bus,
    create_spec_compressor,
)

# ---------------------------------------------------------------------------
# Module-level checks
# ---------------------------------------------------------------------------


def test_feature_flag():
    assert CONTEXT_OPTIMIZATION_AVAILABLE is True


# ---------------------------------------------------------------------------
# CompressionResult
# ---------------------------------------------------------------------------


class TestCompressionResult:
    def test_bytes_saved(self):
        cr = CompressionResult(
            strategy=CompressionStrategy.DELTA,
            original_size=1000,
            compressed_size=300,
            compression_ratio=0.3,
            payload={},
            checksum="abc123",
        )
        assert cr.bytes_saved == 700


class TestCompressionStrategy:
    def test_enum_values(self):
        assert CompressionStrategy.FULL.value == "full"
        assert CompressionStrategy.DELTA.value == "delta"
        assert CompressionStrategy.INCREMENTAL.value == "incremental"


# ---------------------------------------------------------------------------
# GovernanceDecision
# ---------------------------------------------------------------------------


class TestGovernanceDecision:
    def test_is_expired_false(self):
        d = GovernanceDecision(
            allowed=True,
            reason="ok",
            cached_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
            cache_key="k",
        )
        assert d.is_expired is False

    def test_is_expired_true(self):
        d = GovernanceDecision(
            allowed=True,
            reason="ok",
            cached_at=datetime.now() - timedelta(hours=2),
            expires_at=datetime.now() - timedelta(hours=1),
            cache_key="k",
        )
        assert d.is_expired is True


# ---------------------------------------------------------------------------
# SpecDeltaCompressor
# ---------------------------------------------------------------------------


class TestSpecDeltaCompressor:
    @pytest.mark.asyncio
    async def test_first_compress_is_full(self):
        c = SpecDeltaCompressor()
        result = await c.compress("spec-1", {"key": "value"})
        assert result.strategy == CompressionStrategy.FULL
        assert result.payload["full"] is True
        assert result.compressed_size == result.original_size

    @pytest.mark.asyncio
    async def test_second_compress_no_change_is_delta(self):
        c = SpecDeltaCompressor()
        await c.compress("spec-1", {"key": "value"})
        result = await c.compress("spec-1", {"key": "value"})
        assert result.strategy == CompressionStrategy.DELTA
        assert result.payload["delta"] == {}

    @pytest.mark.asyncio
    async def test_second_compress_with_change(self):
        c = SpecDeltaCompressor()
        # Use a large enough payload so delta is actually smaller
        large_data = {f"key_{i}": f"value_{i}" for i in range(20)}
        await c.compress("spec-1", large_data)
        updated = {**large_data, "key_0": "changed"}
        result = await c.compress("spec-1", updated)
        assert result.strategy == CompressionStrategy.DELTA
        assert result.payload["delta"]["key_0"] == "changed"
        assert result.compressed_size < result.original_size

    @pytest.mark.asyncio
    async def test_compress_detects_removed_keys(self):
        c = SpecDeltaCompressor()
        await c.compress("spec-1", {"a": 1, "b": 2})
        result = await c.compress("spec-1", {"a": 1})
        assert "__removed__b" in result.payload["delta"]

    @pytest.mark.asyncio
    async def test_decompress_full(self):
        c = SpecDeltaCompressor()
        data, ok = await c.decompress("spec-1", {"full": True, "spec": {"x": 42}})
        assert ok is True
        assert data == {"x": 42}

    @pytest.mark.asyncio
    async def test_decompress_delta_no_baseline(self):
        c = SpecDeltaCompressor()
        data, ok = await c.decompress("missing", {"full": False, "delta": {"x": 1}})
        assert ok is False
        assert data == {}

    @pytest.mark.asyncio
    async def test_decompress_delta_checksum_mismatch(self):
        c = SpecDeltaCompressor()
        await c.decompress("spec-1", {"full": True, "spec": {"x": 1}})
        data, ok = await c.decompress(
            "spec-1",
            {"full": False, "delta": {"x": 2}, "baseline_checksum": "wrong"},
        )
        assert ok is False

    @pytest.mark.asyncio
    async def test_decompress_delta_applies_changes(self):
        c = SpecDeltaCompressor()
        await c.decompress("spec-1", {"full": True, "spec": {"a": 1, "b": 2}})
        data, ok = await c.decompress(
            "spec-1",
            {"full": False, "delta": {"a": 10, "__removed__b": None}, "checksum": "new"},
        )
        assert ok is True
        assert data == {"a": 10}

    @pytest.mark.asyncio
    async def test_get_stats(self):
        c = SpecDeltaCompressor()
        stats = c.get_stats()
        assert stats["compressions"] == 0
        assert stats["baselines_cached"] == 0
        assert "constitutional_hash" in stats

    @pytest.mark.asyncio
    async def test_clear(self):
        c = SpecDeltaCompressor()
        await c.compress("spec-1", {"k": "v"})
        assert c.get_stats()["baselines_cached"] == 1
        await c.clear()
        assert c.get_stats()["baselines_cached"] == 0

    @pytest.mark.asyncio
    async def test_evict_stale_baselines_by_ttl(self):
        c = SpecDeltaCompressor(baseline_ttl_seconds=0)
        await c.compress("spec-1", {"k": "v"})
        # TTL is 0 seconds, so next compress should evict the baseline
        result = await c.compress("spec-2", {"k2": "v2"})
        # spec-1 should have been evicted, spec-2 is new
        assert c.get_stats()["baselines_cached"] == 1

    @pytest.mark.asyncio
    async def test_evict_by_max_baselines(self):
        # Eviction runs BEFORE adding the new baseline.
        # Condition: `while len > max_baselines` (strictly greater).
        # With max_baselines=2:
        #   s1 → 1, s2 → 2, s3 → evict_check(2>2=False) then add → 3
        #   s4 → evict_check(3>2=True, evict s1) → 2, then add → 3
        # To trigger eviction we need 4 distinct specs.
        c = SpecDeltaCompressor(max_baselines=2)
        await c.compress("s1", {"a": 1})
        await c.compress("s2", {"b": 2})
        await c.compress("s3", {"c": 3})
        assert c.get_stats()["baselines_cached"] == 3  # no eviction yet
        await c.compress("s4", {"d": 4})
        # Eviction triggered: 3 > 2, evicts s1, then adds s4 → 3 again
        # Actually it keeps evicting in a while loop: 3>2 evict, 2>2 stop, add → 3
        # So final count is 3. Let's just assert it ran eviction and count is bounded.
        cached = c.get_stats()["baselines_cached"]
        assert cached <= 3  # eviction did run
        # s1 should have been evicted (LRU)
        assert "s1" not in c._baselines

    @pytest.mark.asyncio
    async def test_stats_track_delta_sends(self):
        c = SpecDeltaCompressor()
        await c.compress("s1", {"a": 1})
        await c.compress("s1", {"a": 2})
        stats = c.get_stats()
        assert stats["delta_sends"] >= 1
        assert stats["full_sends"] >= 1


# ---------------------------------------------------------------------------
# CachedGovernanceValidator
# ---------------------------------------------------------------------------


class TestCachedGovernanceValidator:
    @pytest.mark.asyncio
    async def test_validate_no_upstream(self):
        v = CachedGovernanceValidator()
        ctx = ValidationContext(action="read", resource="data", agent_id="a1")
        decision = await v.validate(ctx)
        assert decision.allowed is True
        assert "No upstream" in decision.reason

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        v = CachedGovernanceValidator()
        ctx = ValidationContext(action="read", resource="data", agent_id="a1")
        await v.validate(ctx)
        await v.validate(ctx)
        stats = v.get_stats()
        assert stats["hits"] >= 1

    @pytest.mark.asyncio
    async def test_cache_miss_then_hit(self):
        v = CachedGovernanceValidator()
        ctx = ValidationContext(action="read", resource="data", agent_id="a1")
        await v.validate(ctx)
        stats = v.get_stats()
        assert stats["misses"] >= 1

    @pytest.mark.asyncio
    async def test_upstream_validator_called(self):
        upstream = AsyncMock()
        upstream.validate = AsyncMock(
            return_value=GovernanceDecision(
                allowed=True,
                reason="ok",
                cached_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=1),
                cache_key="k",
            )
        )
        v = CachedGovernanceValidator(upstream_validator=upstream)
        ctx = ValidationContext(action="write", resource="data", agent_id="a2")
        decision = await v.validate(ctx)
        assert decision.allowed is True
        upstream.validate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upstream_failure_fail_closed(self):
        upstream = AsyncMock()
        upstream.validate = AsyncMock(side_effect=RuntimeError("upstream down"))
        v = CachedGovernanceValidator(upstream_validator=upstream)
        ctx = ValidationContext(action="write", resource="data", agent_id="a2")
        decision = await v.validate(ctx)
        assert decision.allowed is False
        assert "fail-closed" in decision.reason

    @pytest.mark.asyncio
    async def test_negative_caching_disabled(self):
        upstream = AsyncMock()
        upstream.validate = AsyncMock(side_effect=RuntimeError("fail"))
        v = CachedGovernanceValidator(upstream_validator=upstream, enable_negative_caching=False)
        ctx = ValidationContext(action="write", resource="data", agent_id="a2")
        await v.validate(ctx)
        # Denied decisions should NOT be cached
        stats = v.get_stats()
        assert stats["cache_size"] == 0

    @pytest.mark.asyncio
    async def test_invalidate_all(self):
        v = CachedGovernanceValidator()
        ctx = ValidationContext(action="read", resource="data", agent_id="a1")
        await v.validate(ctx)
        count = await v.invalidate()
        assert count >= 1
        assert v.get_stats()["cache_size"] == 0

    @pytest.mark.asyncio
    async def test_invalidate_pattern(self):
        v = CachedGovernanceValidator()
        ctx = ValidationContext(action="read", resource="data", agent_id="a1")
        await v.validate(ctx)
        count = await v.invalidate(pattern="nonexistent")
        assert count == 0

    @pytest.mark.asyncio
    async def test_eviction_at_max_capacity(self):
        v = CachedGovernanceValidator(max_cache_size=2)
        for i in range(5):
            ctx = ValidationContext(action=f"act-{i}", resource="r", agent_id="a")
            await v.validate(ctx)
        stats = v.get_stats()
        assert stats["cache_size"] <= 2
        assert stats["evictions"] >= 1

    def test_invalid_hash_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            CachedGovernanceValidator(cache_hash_mode="invalid")

    def test_get_stats_structure(self):
        v = CachedGovernanceValidator()
        stats = v.get_stats()
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert "constitutional_hash" in stats

    def test_cache_key_deterministic(self):
        v = CachedGovernanceValidator()
        ctx = ValidationContext(action="read", resource="data", agent_id="a1")
        k1 = v._cache_key(ctx)
        k2 = v._cache_key(ctx)
        assert k1 == k2

    def test_cache_key_varies_by_action(self):
        v = CachedGovernanceValidator()
        ctx1 = ValidationContext(action="read", resource="data", agent_id="a1")
        ctx2 = ValidationContext(action="write", resource="data", agent_id="a1")
        assert v._cache_key(ctx1) != v._cache_key(ctx2)


# ---------------------------------------------------------------------------
# PartitionBroker
# ---------------------------------------------------------------------------


class TestPartitionBroker:
    @pytest.mark.asyncio
    async def test_publish(self):
        broker = PartitionBroker("test-topic", 0)
        msg = PartitionedMessage(
            topic="test-topic",
            partition=0,
            payload={"data": 1},
            partition_key="k",
        )
        ok = await broker.publish(msg)
        assert ok is True
        stats = broker.get_stats()
        assert stats["published"] == 1

    @pytest.mark.asyncio
    async def test_buffer_full_drops(self):
        broker = PartitionBroker("test", 0, max_buffer=1)
        msg1 = PartitionedMessage(topic="test", partition=0, payload={}, partition_key="k")
        msg2 = PartitionedMessage(topic="test", partition=0, payload={}, partition_key="k")
        await broker.publish(msg1)
        ok = await broker.publish(msg2)
        assert ok is False
        assert broker.get_stats()["dropped"] == 1

    @pytest.mark.asyncio
    async def test_subscribe_and_notify(self):
        broker = PartitionBroker("test", 0)
        received = []

        async def handler(msg):
            received.append(msg)

        await broker.subscribe(handler)
        msg = PartitionedMessage(topic="test", partition=0, payload={"x": 1}, partition_key="k")
        await broker.publish(msg)

        assert len(received) == 1
        assert received[0].payload == {"x": 1}

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        broker = PartitionBroker("test", 0)
        received = []

        async def handler(msg):
            received.append(msg)

        await broker.subscribe(handler)
        await broker.unsubscribe(handler)

        msg = PartitionedMessage(topic="test", partition=0, payload={}, partition_key="k")
        await broker.publish(msg)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_handler_error_does_not_break(self):
        broker = PartitionBroker("test", 0)

        async def bad_handler(msg):
            raise RuntimeError("boom")

        await broker.subscribe(bad_handler)
        msg = PartitionedMessage(topic="test", partition=0, payload={}, partition_key="k")
        ok = await broker.publish(msg)
        assert ok is True

    def test_get_stats(self):
        broker = PartitionBroker("topic", 3)
        stats = broker.get_stats()
        assert stats["topic"] == "topic"
        assert stats["partition"] == 3
        assert stats["buffer_size"] == 0
        assert stats["subscribers"] == 0


# ---------------------------------------------------------------------------
# OptimizedAgentBus
# ---------------------------------------------------------------------------


class TestOptimizedAgentBus:
    @pytest.mark.asyncio
    async def test_publish_auto_creates_topic(self):
        bus = OptimizedAgentBus()
        ok = await bus.publish("new-topic", {"data": 1}, partition_key="k")
        assert ok is True
        assert "new-topic" in bus._brokers

    @pytest.mark.asyncio
    async def test_publish_to_existing_topic(self):
        bus = OptimizedAgentBus()
        config = TopicConfig(name="my-topic", partitions=2)
        await bus.create_topic(config)
        ok = await bus.publish("my-topic", {"data": 1}, partition_key="k")
        assert ok is True

    @pytest.mark.asyncio
    async def test_create_topic_duplicate_ignored(self):
        bus = OptimizedAgentBus()
        config = TopicConfig(name="dup", partitions=2)
        await bus.create_topic(config)
        await bus.create_topic(config)  # Should not raise
        assert len(bus._brokers["dup"]) == 2

    @pytest.mark.asyncio
    async def test_subscribe_all_partitions(self):
        bus = OptimizedAgentBus()
        config = TopicConfig(name="sub-test", partitions=3)
        await bus.create_topic(config)

        received = []

        async def handler(msg):
            received.append(msg)

        await bus.subscribe("sub-test", handler)
        # Each partition should have the handler
        for broker in bus._brokers["sub-test"]:
            assert len(broker._subscribers) == 1

    @pytest.mark.asyncio
    async def test_subscribe_specific_partitions(self):
        bus = OptimizedAgentBus()
        config = TopicConfig(name="part-test", partitions=4)
        await bus.create_topic(config)

        async def handler(msg):
            pass

        await bus.subscribe("part-test", handler, partitions=[0, 2])
        assert len(bus._brokers["part-test"][0]._subscribers) == 1
        assert len(bus._brokers["part-test"][1]._subscribers) == 0
        assert len(bus._brokers["part-test"][2]._subscribers) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        bus = OptimizedAgentBus()
        config = TopicConfig(name="unsub-test", partitions=2)
        await bus.create_topic(config)

        async def handler(msg):
            pass

        await bus.subscribe("unsub-test", handler)
        await bus.unsubscribe("unsub-test", handler)
        for broker in bus._brokers["unsub-test"]:
            assert len(broker._subscribers) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_topic(self):
        bus = OptimizedAgentBus()

        async def handler(msg):
            pass

        await bus.unsubscribe("no-such-topic", handler)  # Should not raise

    @pytest.mark.asyncio
    async def test_subscribe_auto_creates_topic(self):
        bus = OptimizedAgentBus()

        async def handler(msg):
            pass

        await bus.subscribe("auto-topic", handler)
        assert "auto-topic" in bus._brokers

    def test_get_stats(self):
        bus = OptimizedAgentBus()
        stats = bus.get_stats()
        assert "topics_created" in stats
        assert "total_published" in stats
        assert "constitutional_hash" in stats

    def test_init_with_configs(self):
        configs = {
            "events": TopicConfig(name="events", partitions=8),
        }
        bus = OptimizedAgentBus(topic_configs=configs)
        assert "events" in bus._brokers
        assert len(bus._brokers["events"]) == 8

    @pytest.mark.asyncio
    async def test_partition_routing_deterministic(self):
        bus = OptimizedAgentBus()
        config = TopicConfig(name="det-test", partitions=4)
        await bus.create_topic(config)
        p1 = bus._get_partition("det-test", "same-key")
        p2 = bus._get_partition("det-test", "same-key")
        assert p1 == p2


# ---------------------------------------------------------------------------
# TopicPriority
# ---------------------------------------------------------------------------


class TestTopicPriority:
    def test_values(self):
        assert TopicPriority.LOW.value == "low"
        assert TopicPriority.NORMAL.value == "normal"
        assert TopicPriority.HIGH.value == "high"
        assert TopicPriority.CRITICAL.value == "critical"


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


class TestFactoryFunctions:
    def test_create_spec_compressor(self):
        c = create_spec_compressor(max_baselines=10, baseline_ttl_seconds=60)
        assert isinstance(c, SpecDeltaCompressor)

    def test_create_cached_validator(self):
        v = create_cached_validator(cache_ttl_seconds=30, max_cache_size=100)
        assert isinstance(v, CachedGovernanceValidator)

    def test_create_optimized_bus(self):
        bus = create_optimized_bus()
        assert isinstance(bus, OptimizedAgentBus)

    def test_create_optimized_bus_with_configs(self):
        configs = {"test": TopicConfig(name="test", partitions=2)}
        bus = create_optimized_bus(topic_configs=configs)
        assert "test" in bus._brokers
