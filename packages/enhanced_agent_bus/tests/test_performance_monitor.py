"""
ACGS-2 Performance Monitor Tests
Constitutional Hash: 608508a9bd224290

Tests for performance monitoring module with timing decorators.
Coverage target: >= 85%
"""

import asyncio
import sys
import time

import pytest

try:
    from enhanced_agent_bus.performance_monitor import (
        CONSTITUTIONAL_HASH,
        MetricType,
        OperationMetrics,
        PerformanceMonitor,
        TimingRecord,
        get_performance_monitor,
        set_performance_monitor,
        timed,
    )
except ImportError:
    from performance_monitor import (
        CONSTITUTIONAL_HASH,
        MetricType,
        OperationMetrics,
        PerformanceMonitor,
        TimingRecord,
        get_performance_monitor,
        set_performance_monitor,
        timed,
    )


class TestMetricType:
    """Tests for MetricType enum."""

    def test_all_types_defined(self):
        """All metric types are defined."""
        assert MetricType.LATENCY.value == "latency"
        assert MetricType.THROUGHPUT.value == "throughput"
        assert MetricType.ERROR_RATE.value == "error_rate"
        assert MetricType.CUSTOM.value == "custom"

    def test_type_count(self):
        """Correct number of types defined."""
        assert len(MetricType) == 4


class TestTimingRecord:
    """Tests for TimingRecord dataclass."""

    def test_record_creation(self):
        """TimingRecord can be created with required fields."""
        record = TimingRecord(
            operation="test_op",
            duration_ms=10.5,
            timestamp=time.time(),
            success=True,
        )
        assert record.operation == "test_op"
        assert record.duration_ms == 10.5
        assert record.success is True
        assert record.constitutional_hash == CONSTITUTIONAL_HASH

    def test_record_to_dict(self):
        """to_dict() includes all fields."""
        record = TimingRecord(
            operation="test_op",
            duration_ms=10.5,
            timestamp=100.0,
            success=True,
            trace_id="trace-123",
            metadata={"key": "value"},
        )
        d = record.to_dict()
        assert d["operation"] == "test_op"
        assert d["duration_ms"] == 10.5
        assert d["success"] is True
        assert d["trace_id"] == "trace-123"
        assert d["metadata"] == {"key": "value"}


class TestOperationMetrics:
    """Tests for OperationMetrics dataclass."""

    def test_metrics_creation(self):
        """OperationMetrics can be created."""
        metrics = OperationMetrics(operation="test_op")
        assert metrics.operation == "test_op"
        assert metrics.count == 0
        assert metrics.error_count == 0

    def test_add_record(self):
        """Adding records updates metrics correctly."""
        metrics = OperationMetrics(operation="test_op")
        record = TimingRecord(
            operation="test_op",
            duration_ms=10.0,
            timestamp=time.time(),
            success=True,
        )
        metrics.add_record(record)
        assert metrics.count == 1
        assert metrics.total_duration_ms == 10.0
        assert metrics.error_count == 0

    def test_add_error_record(self):
        """Adding error record increments error count."""
        metrics = OperationMetrics(operation="test_op")
        record = TimingRecord(
            operation="test_op",
            duration_ms=10.0,
            timestamp=time.time(),
            success=False,
        )
        metrics.add_record(record)
        assert metrics.count == 1
        assert metrics.error_count == 1
        assert metrics.error_rate == 100.0

    def test_mean_duration(self):
        """Mean duration is calculated correctly."""
        metrics = OperationMetrics(operation="test_op")
        for i in range(3):
            record = TimingRecord(
                operation="test_op",
                duration_ms=float(i + 1) * 10,
                timestamp=time.time(),
                success=True,
            )
            metrics.add_record(record)
        assert metrics.mean_duration_ms == 20.0  # (10 + 20 + 30) / 3

    def test_percentiles(self):
        """Percentile calculations work correctly."""
        metrics = OperationMetrics(operation="test_op")
        for i in range(1, 101):  # 1 to 100
            record = TimingRecord(
                operation="test_op",
                duration_ms=float(i),
                timestamp=time.time(),
                success=True,
            )
            metrics.add_record(record)
        assert metrics.p50_ms == 50.0
        assert metrics.p95_ms == 95.0
        assert metrics.p99_ms == 99.0

    def test_min_max(self):
        """Min and max durations are tracked."""
        metrics = OperationMetrics(operation="test_op")
        durations = [5.0, 15.0, 10.0, 20.0]
        for d in durations:
            record = TimingRecord(
                operation="test_op",
                duration_ms=d,
                timestamp=time.time(),
                success=True,
            )
            metrics.add_record(record)
        assert metrics.min_duration_ms == 5.0
        assert metrics.max_duration_ms == 20.0

    def test_to_dict(self):
        """to_dict() includes all metrics."""
        metrics = OperationMetrics(operation="test_op")
        record = TimingRecord(
            operation="test_op",
            duration_ms=10.0,
            timestamp=time.time(),
            success=True,
        )
        metrics.add_record(record)
        d = metrics.to_dict()
        assert d["operation"] == "test_op"
        assert d["count"] == 1
        assert d["mean_ms"] == 10.0
        assert "p50_ms" in d
        assert "p95_ms" in d
        assert "p99_ms" in d

    def test_percentiles_use_rust_kernel_when_available(self, monkeypatch):
        """Nearest-rank percentiles use Rust kernel when available."""
        metrics = OperationMetrics(operation="rust_percentiles")
        called = {"value": False}
        module = sys.modules[OperationMetrics.__module__]

        def _fake_kernel(values: list[float], percentiles: list[float]) -> list[float]:
            called["value"] = True
            assert values == sorted(values)
            assert percentiles == [50.0, 95.0, 99.0]
            return [50.0, 95.0, 99.0]

        monkeypatch.setattr(module, "PERF_KERNELS_AVAILABLE", True)
        monkeypatch.setattr(
            module,
            "compute_percentiles_nearest_rank",
            _fake_kernel,
            raising=False,
        )

        for i in range(1, 101):
            record = TimingRecord(
                operation="rust_percentiles",
                duration_ms=float(i),
                timestamp=time.time(),
                success=True,
            )
            metrics.add_record(record)

        payload = metrics.to_dict()
        assert called["value"] is True
        assert payload["p50_ms"] == 50.0
        assert payload["p95_ms"] == 95.0
        assert payload["p99_ms"] == 99.0

    def test_percentiles_python_fallback_without_rust(self, monkeypatch):
        """Nearest-rank Python fallback remains behavior-compatible."""
        metrics = OperationMetrics(operation="python_percentiles")
        module = sys.modules[OperationMetrics.__module__]
        monkeypatch.setattr(module, "PERF_KERNELS_AVAILABLE", False)

        for i in range(1, 101):
            record = TimingRecord(
                operation="python_percentiles",
                duration_ms=float(i),
                timestamp=time.time(),
                success=True,
            )
            metrics.add_record(record)

        assert metrics.p50_ms == 50.0
        assert metrics.p95_ms == 95.0
        assert metrics.p99_ms == 99.0


class TestPerformanceMonitor:
    """Tests for PerformanceMonitor class."""

    @pytest.fixture
    def monitor(self):
        """Create a fresh monitor instance."""
        return PerformanceMonitor()

    async def test_timed_async_decorator(self, monitor):
        """@timed decorator works with async functions."""

        @monitor.timed("async_test")
        async def async_func():
            await asyncio.sleep(0.01)
            return "result"

        result = await async_func()
        assert result == "result"

        # Wait for async metric recording
        await asyncio.sleep(0.1)

        metrics = monitor.get_metrics()
        assert metrics["summary"]["total_operations"] >= 1

    def test_timed_sync_decorator(self, monitor):
        """@timed decorator works with sync functions."""

        @monitor.timed("sync_test")
        def sync_func():
            time.sleep(0.01)
            return "result"

        result = sync_func()
        assert result == "result"

        # Allow time for recording
        time.sleep(0.1)

        metrics = monitor.get_metrics()
        assert metrics["summary"]["total_operations"] >= 1

    async def test_timed_with_exception(self, monitor):
        """@timed decorator captures exceptions as failures."""

        @monitor.timed("error_test")
        async def error_func():
            await asyncio.sleep(0.01)
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await error_func()

        # Wait for async metric recording
        await asyncio.sleep(0.1)

        metrics = monitor.get_metrics("error_test")
        assert "metrics" in metrics
        assert metrics["metrics"]["error_count"] >= 1

    def test_manual_record_timing(self, monitor):
        """Manual timing recording works."""
        monitor.record_timing(
            operation="manual_op",
            duration_ms=15.0,
            success=True,
            trace_id="test-trace",
        )

        # Allow time for recording
        time.sleep(0.1)

        metrics = monitor.get_metrics("manual_op")
        assert "metrics" in metrics
        assert metrics["metrics"]["count"] >= 1

    async def test_get_metrics_all(self, monitor):
        """Get all metrics returns correct structure."""
        # Add some records
        for i in range(5):
            record = TimingRecord(
                operation=f"op_{i}",
                duration_ms=10.0,
                timestamp=time.time(),
                success=True,
            )
            await monitor._add_record(record)

        metrics = monitor.get_metrics()
        assert "operations" in metrics
        assert "summary" in metrics
        assert "constitutional_hash" in metrics
        assert metrics["summary"]["total_operations"] == 5

    async def test_get_metrics_single_operation(self, monitor):
        """Get metrics for specific operation."""
        record = TimingRecord(
            operation="specific_op",
            duration_ms=25.0,
            timestamp=time.time(),
            success=True,
        )
        await monitor._add_record(record)

        metrics = monitor.get_metrics("specific_op")
        assert metrics["operation"] == "specific_op"
        assert "metrics" in metrics
        assert metrics["metrics"]["mean_ms"] == 25.0

    def test_get_metrics_not_found(self, monitor):
        """Get metrics for non-existent operation returns error."""
        metrics = monitor.get_metrics("non_existent")
        assert "error" in metrics

    async def test_clear_metrics_single(self, monitor):
        """Clear metrics for single operation."""
        record = TimingRecord(
            operation="to_clear",
            duration_ms=10.0,
            timestamp=time.time(),
            success=True,
        )
        await monitor._add_record(record)

        assert monitor.get_operation_names() == ["to_clear"]

        monitor.clear_metrics("to_clear")
        assert monitor.get_operation_names() == []

    async def test_clear_metrics_all(self, monitor):
        """Clear all metrics."""
        for i in range(3):
            record = TimingRecord(
                operation=f"op_{i}",
                duration_ms=10.0,
                timestamp=time.time(),
                success=True,
            )
            await monitor._add_record(record)

        assert len(monitor.get_operation_names()) == 3

        monitor.clear_metrics()
        assert len(monitor.get_operation_names()) == 0

    def test_enable_disable(self, monitor):
        """Enable and disable monitoring."""
        assert monitor.is_enabled is True

        monitor.disable()
        assert monitor.is_enabled is False

        monitor.enable()
        assert monitor.is_enabled is True

    def test_disabled_monitor_no_records(self, monitor):
        """Disabled monitor doesn't record."""
        monitor.disable()

        @monitor.timed("disabled_test")
        def test_func():
            return "result"

        test_func()

        metrics = monitor.get_metrics()
        assert metrics["summary"]["total_operations"] == 0

    def test_get_operation_names(self, monitor):
        """Get list of operation names."""
        assert monitor.get_operation_names() == []


class TestGlobalFunctions:
    """Tests for global functions."""

    def test_get_performance_monitor_singleton(self):
        """Global monitor is a singleton."""
        monitor1 = get_performance_monitor()
        monitor2 = get_performance_monitor()
        assert monitor1 is monitor2

    def test_set_performance_monitor(self):
        """Set global monitor instance."""
        new_monitor = PerformanceMonitor()
        set_performance_monitor(new_monitor)

        retrieved = get_performance_monitor()
        assert retrieved is new_monitor

        # Reset for other tests
        set_performance_monitor(PerformanceMonitor())

    def test_timed_global_decorator(self):
        """Global timed decorator uses global monitor."""

        @timed("global_test")
        def test_func():
            time.sleep(0.01)
            return "done"

        result = test_func()
        assert result == "done"

        # Allow time for recording
        time.sleep(0.1)

        monitor = get_performance_monitor()
        metrics = monitor.get_metrics()
        assert metrics["summary"]["total_operations"] >= 1


class TestConcurrency:
    """Tests for concurrent access."""

    async def test_concurrent_record_addition(self):
        """Multiple concurrent recordings work correctly."""
        monitor = PerformanceMonitor()

        async def add_records(op_name: str, count: int):
            for i in range(count):
                record = TimingRecord(
                    operation=op_name,
                    duration_ms=float(i + 1),
                    timestamp=time.time(),
                    success=True,
                )
                await monitor._add_record(record)

        # Run multiple concurrent tasks
        await asyncio.gather(
            add_records("op1", 100),
            add_records("op2", 100),
            add_records("op1", 100),  # More op1
        )

        metrics = monitor.get_metrics()
        assert metrics["summary"]["total_count"] == 300

        op1_metrics = monitor.get_metrics("op1")
        assert op1_metrics["metrics"]["count"] == 200

        op2_metrics = monitor.get_metrics("op2")
        assert op2_metrics["metrics"]["count"] == 100


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_metrics(self):
        """Empty metrics return sensible defaults."""
        metrics = OperationMetrics(operation="empty")
        assert metrics.mean_duration_ms == 0.0
        assert metrics.error_rate == 0.0
        assert metrics.p99_ms == 0.0

    def test_single_record_percentiles(self):
        """Percentiles with single record."""
        metrics = OperationMetrics(operation="single")
        record = TimingRecord(
            operation="single",
            duration_ms=50.0,
            timestamp=time.time(),
            success=True,
        )
        metrics.add_record(record)
        assert metrics.p50_ms == 50.0
        assert metrics.p95_ms == 50.0
        assert metrics.p99_ms == 50.0

    async def test_record_with_metadata(self):
        """Records can include metadata."""
        monitor = PerformanceMonitor()
        monitor.record_timing(
            operation="meta_test",
            duration_ms=10.0,
            success=True,
            metadata={"tenant_id": "tenant-1", "priority": "high"},
        )

        # Allow time for recording
        await asyncio.sleep(0.1)

        metrics = monitor.get_metrics("meta_test")
        assert "metrics" in metrics

    def test_deque_maxlen(self):
        """Operation metrics respects maxlen for durations."""
        metrics = OperationMetrics(operation="maxlen_test")
        # Add more than maxlen (10000)
        for i in range(10010):
            record = TimingRecord(
                operation="maxlen_test",
                duration_ms=float(i),
                timestamp=time.time(),
                success=True,
            )
            metrics.add_record(record)

        assert len(metrics.durations) == 10000


@pytest.mark.constitutional
def test_constitutional_hash_present():
    """Constitutional hash is present in all classes."""
    record = TimingRecord(
        operation="test",
        duration_ms=10.0,
        timestamp=time.time(),
        success=True,
    )
    assert record.constitutional_hash == CONSTITUTIONAL_HASH

    metrics = OperationMetrics(operation="test")
    assert metrics.constitutional_hash == CONSTITUTIONAL_HASH

    monitor = PerformanceMonitor()
    assert monitor.constitutional_hash == CONSTITUTIONAL_HASH
