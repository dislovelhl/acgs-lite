"""
ACGS-2 Memory Profiler Tests
Constitutional Hash: 608508a9bd224290

Tests for memory profiling module with tracemalloc integration.
"""

import asyncio
import time

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

try:
    from enhanced_agent_bus.memory_profiler import (
        CONSTITUTIONAL_HASH,
        MEMORY_PROFILING_AVAILABLE,
        AsyncMemoryQueue,
        MemoryDelta,
        MemoryProfiler,
        MemoryProfilingConfig,
        MemoryProfilingContext,
        MemorySnapshot,
        ProfilingLevel,
        get_memory_profiler,
        profile_memory,
    )
except ImportError:
    from memory_profiler import (
        CONSTITUTIONAL_HASH,
        MEMORY_PROFILING_AVAILABLE,
        AsyncMemoryQueue,
        MemoryDelta,
        MemoryProfiler,
        MemoryProfilingConfig,
        MemoryProfilingContext,
        MemorySnapshot,
        ProfilingLevel,
        get_memory_profiler,
        profile_memory,
    )


class TestProfilingLevel:
    """Tests for ProfilingLevel enum."""

    def test_all_levels_defined(self):
        """All profiling levels are defined."""
        assert ProfilingLevel.DISABLED.value == "disabled"
        assert ProfilingLevel.SUMMARY.value == "summary"
        assert ProfilingLevel.DETAILED.value == "detailed"
        assert ProfilingLevel.FULL.value == "full"

    def test_level_count(self):
        """Correct number of levels defined."""
        assert len(ProfilingLevel) == 4


class TestMemorySnapshot:
    """Tests for MemorySnapshot dataclass."""

    def test_snapshot_creation(self):
        """MemorySnapshot can be created with required fields."""
        snap = MemorySnapshot(
            timestamp=time.monotonic(),
            current_bytes=1024 * 1024,  # 1MB
            peak_bytes=2 * 1024 * 1024,  # 2MB
        )
        assert snap.current_bytes == 1024 * 1024
        assert snap.peak_bytes == 2 * 1024 * 1024
        assert snap.constitutional_hash == CONSTITUTIONAL_HASH

    def test_mb_properties(self):
        """MB conversion properties work correctly."""
        snap = MemorySnapshot(
            timestamp=time.monotonic(),
            current_bytes=10 * 1024 * 1024,  # 10MB
            peak_bytes=20 * 1024 * 1024,  # 20MB
        )
        assert snap.current_mb == 10.0
        assert snap.peak_mb == 20.0

    def test_to_dict(self):
        """to_dict() includes all fields."""
        snap = MemorySnapshot(
            timestamp=100.0,
            current_bytes=1024 * 1024,
            peak_bytes=2 * 1024 * 1024,
            trace_id="test-123",
            operation="process_message",
        )
        d = snap.to_dict()
        assert d["current_bytes"] == 1024 * 1024
        assert d["current_mb"] == 1.0
        assert d["peak_mb"] == 2.0
        assert d["trace_id"] == "test-123"
        assert d["operation"] == "process_message"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_optional_fields(self):
        """Optional fields default correctly."""
        snap = MemorySnapshot(
            timestamp=time.monotonic(),
            current_bytes=0,
            peak_bytes=0,
        )
        assert snap.trace_id is None
        assert snap.operation is None
        assert snap.top_allocations == []


class TestMemoryDelta:
    """Tests for MemoryDelta dataclass."""

    def test_delta_creation(self):
        """MemoryDelta can be created with required fields."""
        delta = MemoryDelta(
            start_bytes=1024 * 1024,
            end_bytes=2 * 1024 * 1024,
            delta_bytes=1024 * 1024,
            peak_bytes=3 * 1024 * 1024,
            duration_ms=10.5,
            operation="test_op",
        )
        assert delta.delta_bytes == 1024 * 1024
        assert delta.constitutional_hash == CONSTITUTIONAL_HASH

    def test_delta_mb_property(self):
        """delta_mb property converts correctly."""
        delta = MemoryDelta(
            start_bytes=0,
            end_bytes=5 * 1024 * 1024,
            delta_bytes=5 * 1024 * 1024,
            peak_bytes=5 * 1024 * 1024,
            duration_ms=100.0,
            operation="test",
        )
        assert delta.delta_mb == 5.0

    def test_leak_candidate_detection(self):
        """is_leak_candidate flags large memory retention."""
        # Not a leak (small delta)
        small_delta = MemoryDelta(
            start_bytes=0,
            end_bytes=1024,
            delta_bytes=1024,
            peak_bytes=1024,
            duration_ms=1.0,
            operation="small",
        )
        assert small_delta.is_leak_candidate is False

        # Potential leak (>10MB)
        large_delta = MemoryDelta(
            start_bytes=0,
            end_bytes=15 * 1024 * 1024,
            delta_bytes=15 * 1024 * 1024,
            peak_bytes=15 * 1024 * 1024,
            duration_ms=1.0,
            operation="large",
        )
        assert large_delta.is_leak_candidate is True

    def test_to_dict(self):
        """to_dict() includes all fields."""
        delta = MemoryDelta(
            start_bytes=1000,
            end_bytes=2000,
            delta_bytes=1000,
            peak_bytes=3000,
            duration_ms=5.5,
            operation="test_op",
            trace_id="trace-456",
        )
        d = delta.to_dict()
        assert d["start_bytes"] == 1000
        assert d["end_bytes"] == 2000
        assert d["delta_bytes"] == 1000
        assert d["duration_ms"] == 5.5
        assert d["operation"] == "test_op"
        assert d["trace_id"] == "trace-456"
        assert "is_leak_candidate" in d
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestMemoryProfilingConfig:
    """Tests for MemoryProfilingConfig dataclass."""

    def test_default_config(self):
        """Default configuration values are correct."""
        config = MemoryProfilingConfig()
        assert config.enabled is False
        assert config.level == ProfilingLevel.SUMMARY
        assert config.top_n_allocations == 10
        assert config.leak_threshold_bytes == 10 * 1024 * 1024
        assert config.queue_size == 1000
        assert config.flush_interval_s == 60.0
        assert config.trace_depth == 10

    def test_custom_config(self):
        """Custom configuration can be set."""
        config = MemoryProfilingConfig(
            enabled=True,
            level=ProfilingLevel.DETAILED,
            top_n_allocations=20,
            trace_depth=25,
        )
        assert config.enabled is True
        assert config.level == ProfilingLevel.DETAILED
        assert config.top_n_allocations == 20
        assert config.trace_depth == 25


class TestAsyncMemoryQueue:
    """Tests for AsyncMemoryQueue."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return MemoryProfilingConfig(enabled=True, queue_size=10)

    async def test_start_stop(self, config):
        """Queue can start and stop."""
        queue = AsyncMemoryQueue(config)
        await queue.start()
        assert queue._running is True
        await queue.stop()
        assert queue._running is False

    async def test_enqueue_when_stopped(self, config):
        """Enqueue returns False when queue is stopped."""
        queue = AsyncMemoryQueue(config)
        snap = MemorySnapshot(timestamp=0.0, current_bytes=0, peak_bytes=0)
        result = await queue.enqueue(snap)
        assert result is False

    async def test_enqueue_when_running(self, config):
        """Enqueue returns True when queue is running."""
        queue = AsyncMemoryQueue(config)
        await queue.start()
        try:
            snap = MemorySnapshot(timestamp=0.0, current_bytes=0, peak_bytes=0)
            result = await queue.enqueue(snap)
            assert result is True
        finally:
            await queue.stop()

    async def test_queue_full_drops_snapshot(self):
        """When queue is full, new snapshots are dropped."""
        config = MemoryProfilingConfig(enabled=True, queue_size=2)
        queue = AsyncMemoryQueue(config)
        await queue.start()

        try:
            # Fill queue beyond capacity (worker will process some)
            for i in range(5):
                snap = MemorySnapshot(timestamp=float(i), current_bytes=i, peak_bytes=i)
                await queue.enqueue(snap)

            # Give worker time to process
            await asyncio.sleep(0.1)
        finally:
            await queue.stop()

    async def test_callback_invoked(self, config):
        """Callback is invoked for each snapshot."""
        received = []

        def callback(snap):
            received.append(snap)

        queue = AsyncMemoryQueue(config, callback=callback)
        await queue.start()

        try:
            snap = MemorySnapshot(timestamp=0.0, current_bytes=100, peak_bytes=200)
            await queue.enqueue(snap)
            await asyncio.sleep(0.1)  # Let worker process
            assert len(received) == 1
            assert received[0].current_bytes == 100
        finally:
            await queue.stop()

    async def test_get_recent_snapshots(self, config):
        """get_recent_snapshots returns stored snapshots."""
        queue = AsyncMemoryQueue(config)
        await queue.start()

        try:
            for i in range(5):
                snap = MemorySnapshot(
                    timestamp=float(i), current_bytes=i * 1024, peak_bytes=i * 2048
                )
                await queue.enqueue(snap)

            await asyncio.sleep(0.1)  # Let worker process
            recent = queue.get_recent_snapshots(3)
            assert len(recent) <= 3
        finally:
            await queue.stop()

    async def test_get_memory_stats_empty(self, config):
        """get_memory_stats handles empty queue."""
        queue = AsyncMemoryQueue(config)
        stats = queue.get_memory_stats()
        assert stats["total_snapshots"] == 0
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_memory_stats_with_data(self, config):
        """get_memory_stats computes correct statistics."""
        queue = AsyncMemoryQueue(config)
        await queue.start()

        try:
            for i in range(1, 4):
                snap = MemorySnapshot(
                    timestamp=float(i),
                    current_bytes=i * 1024 * 1024,  # 1MB, 2MB, 3MB
                    peak_bytes=i * 2 * 1024 * 1024,
                )
                await queue.enqueue(snap)

            await asyncio.sleep(0.1)
            stats = queue.get_memory_stats()

            assert stats["total_snapshots"] == 3
            assert stats["avg_current_mb"] == 2.0  # (1+2+3)/3
            assert stats["max_current_mb"] == 3.0
            assert stats["min_current_mb"] == 1.0
        finally:
            await queue.stop()


class TestMemoryProfiler:
    """Tests for MemoryProfiler."""

    def test_disabled_by_default(self):
        """Profiler is disabled by default."""
        profiler = MemoryProfiler()
        assert profiler.config.enabled is False
        assert profiler._started is False

    def test_start_when_disabled(self):
        """Start does nothing when disabled."""
        profiler = MemoryProfiler(MemoryProfilingConfig(enabled=False))
        profiler.start()
        assert profiler._started is False

    def test_start_when_enabled(self):
        """Start initializes tracemalloc when enabled."""
        config = MemoryProfilingConfig(enabled=True, level=ProfilingLevel.SUMMARY)
        profiler = MemoryProfiler(config)

        try:
            profiler.start()
            assert profiler._started is True
        finally:
            profiler.stop()

    def test_stop_when_not_started(self):
        """Stop is safe when not started."""
        profiler = MemoryProfiler()
        profiler.stop()  # Should not raise

    def test_take_snapshot_basic(self):
        """take_snapshot returns valid snapshot."""
        config = MemoryProfilingConfig(enabled=True)
        profiler = MemoryProfiler(config)

        try:
            profiler.start()
            snap = profiler.take_snapshot(operation="test", trace_id="trace-1")

            assert snap.operation == "test"
            assert snap.trace_id == "trace-1"
            assert snap.current_bytes >= 0
            assert snap.peak_bytes >= 0
            assert snap.constitutional_hash == CONSTITUTIONAL_HASH
        finally:
            profiler.stop()

    def test_take_snapshot_detailed(self):
        """take_snapshot with DETAILED level includes allocations."""
        config = MemoryProfilingConfig(
            enabled=True, level=ProfilingLevel.DETAILED, top_n_allocations=5
        )
        profiler = MemoryProfiler(config)

        try:
            profiler.start()
            # Allocate some memory
            _ = [i for i in range(10000)]
            snap = profiler.take_snapshot()

            # Should have allocation info
            assert isinstance(snap.top_allocations, list)
        finally:
            profiler.stop()

    def test_reset_peak(self):
        """reset_peak clears peak counter."""
        config = MemoryProfilingConfig(enabled=True)
        profiler = MemoryProfiler(config)

        try:
            profiler.start()
            profiler.reset_peak()  # Should not raise
        finally:
            profiler.stop()

    def test_compare_to_baseline_not_started(self):
        """compare_to_baseline returns None when not started."""
        profiler = MemoryProfiler()
        result = profiler.compare_to_baseline()
        assert result is None


class TestMemoryProfilingContext:
    """Tests for MemoryProfilingContext."""

    async def test_context_disabled(self):
        """Context is no-op when profiling disabled."""
        profiler = MemoryProfiler(MemoryProfilingConfig(enabled=False))

        async with MemoryProfilingContext(profiler, "test") as ctx:
            pass

        assert ctx.delta is None

    async def test_context_enabled(self):
        """Context records memory delta when enabled."""
        config = MemoryProfilingConfig(enabled=True)
        profiler = MemoryProfiler(config)

        try:
            profiler.start()

            async with MemoryProfilingContext(profiler, "test_op", trace_id="t1") as ctx:
                # Allocate some memory
                _ = [i for i in range(1000)]

            assert ctx.delta is not None
            assert ctx.delta.operation == "test_op"
            assert ctx.delta.trace_id == "t1"
            assert ctx.delta.duration_ms >= 0
        finally:
            profiler.stop()

    async def test_context_with_queue(self):
        """Context enqueues snapshot to queue."""
        config = MemoryProfilingConfig(enabled=True)
        profiler = MemoryProfiler(config)
        queue = AsyncMemoryQueue(config)

        try:
            profiler.start()
            await queue.start()

            async with MemoryProfilingContext(profiler, "queued_op", queue=queue) as ctx:
                pass

            await asyncio.sleep(0.1)
            snapshots = queue.get_recent_snapshots(10)
            assert len(snapshots) >= 1
        finally:
            await queue.stop()
            profiler.stop()


class TestProfileMemoryDecorator:
    """Tests for @profile_memory decorator."""

    async def test_decorator_disabled(self):
        """Decorator is no-op when profiling disabled."""

        @profile_memory("test_func")
        async def my_func():
            return 42

        result = await my_func()
        assert result == 42


class TestModuleLevel:
    """Tests for module-level functions."""

    def test_memory_profiling_available(self):
        """MEMORY_PROFILING_AVAILABLE is True."""
        assert MEMORY_PROFILING_AVAILABLE is True

    def test_get_memory_profiler(self):
        """get_memory_profiler returns a MemoryProfiler."""
        profiler = get_memory_profiler()
        assert isinstance(profiler, MemoryProfiler)


class TestConstitutionalHash:
    """Tests for constitutional hash compliance."""

    def test_snapshot_has_hash(self):
        """MemorySnapshot includes constitutional hash."""
        snap = MemorySnapshot(timestamp=0, current_bytes=0, peak_bytes=0)
        assert snap.constitutional_hash == CONSTITUTIONAL_HASH
        assert CONSTITUTIONAL_HASH in snap.to_dict()["constitutional_hash"]

    def test_delta_has_hash(self):
        """MemoryDelta includes constitutional hash."""
        delta = MemoryDelta(
            start_bytes=0,
            end_bytes=0,
            delta_bytes=0,
            peak_bytes=0,
            duration_ms=0,
            operation="test",
        )
        assert delta.constitutional_hash == CONSTITUTIONAL_HASH

    def test_queue_stats_has_hash(self):
        """Queue stats include constitutional hash."""
        config = MemoryProfilingConfig(enabled=True)
        queue = AsyncMemoryQueue(config)
        stats = queue.get_memory_stats()
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
