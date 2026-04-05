# Constitutional Hash: 608508a9bd224290
"""
Extended coverage tests for performance_monitor.py.

Targets the uncovered lines identified in the 40% baseline run:
- OperationMetrics: add_record, mean_duration_ms, error_rate, get_percentile,
  p50/p95/p99 properties, to_dict (inf min branch)
- TimingRecord.to_dict with metadata
- PerformanceMonitor: async_wrapper (disabled, trace_id kwarg, exception branches),
  sync_wrapper (disabled, trace_id, exception, no-loop path),
  _add_record, _store_record_sync, record_timing (async and sync paths),
  get_metrics (single op, all ops, error path), get_operation_names,
  clear_metrics (single and all), enable, disable, is_enabled
- Global helpers: get_performance_monitor singleton, set_performance_monitor,
  module-level timed() convenience decorator
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

try:
    from enhanced_agent_bus import performance_monitor as _pm_module
    from enhanced_agent_bus.performance_monitor import (
        MetricType,
        OperationMetrics,
        PerformanceMonitor,
        TimingRecord,
        get_performance_monitor,
        set_performance_monitor,
        timed,
    )
except ImportError:
    import performance_monitor as _pm_module
    from performance_monitor import (
        MetricType,
        OperationMetrics,
        PerformanceMonitor,
        TimingRecord,
        get_performance_monitor,
        set_performance_monitor,
        timed,
    )

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# ---------------------------------------------------------------------------
# TimingRecord
# ---------------------------------------------------------------------------


class TestTimingRecordToDict:
    """Cover to_dict rounding and metadata field."""

    def test_to_dict_includes_metadata(self):
        record = TimingRecord(
            operation="op",
            duration_ms=3.14159,
            timestamp=100.0,
            success=True,
            metadata={"tenant": "t1", "priority": "high"},
        )
        d = record.to_dict()
        assert d["metadata"] == {"tenant": "t1", "priority": "high"}

    def test_to_dict_rounds_duration(self):
        record = TimingRecord(
            operation="op",
            duration_ms=1.23456789,
            timestamp=100.0,
            success=True,
        )
        d = record.to_dict()
        assert d["duration_ms"] == 1.235  # rounded to 3 dp

    def test_to_dict_trace_id_none_by_default(self):
        record = TimingRecord(
            operation="op",
            duration_ms=5.0,
            timestamp=200.0,
            success=False,
        )
        d = record.to_dict()
        assert d["trace_id"] is None
        assert d["success"] is False


# ---------------------------------------------------------------------------
# OperationMetrics — all previously-uncovered branches
# ---------------------------------------------------------------------------


class TestOperationMetricsUncovered:
    """Hit the previously-uncovered branches in OperationMetrics."""

    def _make_record(self, duration: float, success: bool = True) -> TimingRecord:
        return TimingRecord(
            operation="op",
            duration_ms=duration,
            timestamp=time.time(),
            success=success,
        )

    def test_add_record_updates_min_max(self):
        m = OperationMetrics(operation="op")
        m.add_record(self._make_record(10.0))
        m.add_record(self._make_record(1.0))
        m.add_record(self._make_record(20.0))
        assert m.min_duration_ms == 1.0
        assert m.max_duration_ms == 20.0

    def test_add_record_increments_error_count(self):
        m = OperationMetrics(operation="op")
        m.add_record(self._make_record(5.0, success=False))
        m.add_record(self._make_record(5.0, success=True))
        assert m.error_count == 1

    def test_mean_duration_zero_when_no_records(self):
        m = OperationMetrics(operation="op")
        assert m.mean_duration_ms == 0.0

    def test_mean_duration_correct(self):
        m = OperationMetrics(operation="op")
        m.add_record(self._make_record(10.0))
        m.add_record(self._make_record(30.0))
        assert m.mean_duration_ms == 20.0

    def test_error_rate_zero_when_no_records(self):
        m = OperationMetrics(operation="op")
        assert m.error_rate == 0.0

    def test_error_rate_all_errors(self):
        m = OperationMetrics(operation="op")
        m.add_record(self._make_record(1.0, False))
        m.add_record(self._make_record(2.0, False))
        assert m.error_rate == 100.0

    def test_error_rate_partial(self):
        m = OperationMetrics(operation="op")
        m.add_record(self._make_record(1.0, True))
        m.add_record(self._make_record(1.0, False))
        assert m.error_rate == 50.0

    def test_get_percentile_empty_returns_zero(self):
        m = OperationMetrics(operation="op")
        assert m.get_percentile(99) == 0.0

    def test_get_percentile_single_value(self):
        m = OperationMetrics(operation="op")
        m.add_record(self._make_record(42.0))
        assert m.get_percentile(50) == 42.0
        assert m.get_percentile(99) == 42.0

    def test_p50_property(self):
        m = OperationMetrics(operation="op")
        for i in range(1, 101):
            m.add_record(self._make_record(float(i)))
        assert m.p50_ms == 50.0

    def test_p95_property(self):
        m = OperationMetrics(operation="op")
        for i in range(1, 101):
            m.add_record(self._make_record(float(i)))
        assert m.p95_ms == 95.0

    def test_p99_property(self):
        m = OperationMetrics(operation="op")
        for i in range(1, 101):
            m.add_record(self._make_record(float(i)))
        assert m.p99_ms == 99.0

    def test_to_dict_when_no_records_min_is_zero(self):
        """When no records exist, min=inf is replaced with 0 in to_dict."""
        m = OperationMetrics(operation="op")
        d = m.to_dict()
        assert d["min_ms"] == 0

    def test_to_dict_after_records(self):
        m = OperationMetrics(operation="op")
        m.add_record(self._make_record(10.0))
        d = m.to_dict()
        assert d["count"] == 1
        assert d["min_ms"] == 10.0
        assert d["max_ms"] == 10.0
        assert d["mean_ms"] == 10.0
        assert "error_rate" in d
        assert "last_updated" in d


# ---------------------------------------------------------------------------
# PerformanceMonitor — async_wrapper paths
# ---------------------------------------------------------------------------


class TestAsyncWrapperPaths:
    """Cover async_wrapper branches: disabled monitor, trace_id, exception."""

    async def test_async_wrapper_disabled_skips_timing(self):
        monitor = PerformanceMonitor()
        monitor.disable()

        @monitor.timed("noop_async")
        async def noop():
            return 42

        result = await noop()
        assert result == 42
        assert monitor.get_metrics()["summary"]["total_operations"] == 0

    async def test_async_wrapper_passes_through_return_value(self):
        monitor = PerformanceMonitor()

        @monitor.timed("passthrough")
        async def fn():
            return "hello"

        result = await fn()
        assert result == "hello"

    async def test_async_wrapper_with_trace_id_kwarg(self):
        monitor = PerformanceMonitor()

        @monitor.timed("traced_async")
        async def fn(**kwargs):
            return kwargs.get("trace_id")

        result = await fn(trace_id="trace-abc")
        assert result == "trace-abc"
        await asyncio.sleep(0.05)
        ops = monitor.get_operation_names()
        assert "traced_async" in ops

    async def test_async_wrapper_records_failure_on_exception(self):
        monitor = PerformanceMonitor()

        @monitor.timed("failing_async")
        async def fn():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await fn()

        await asyncio.sleep(0.05)
        metrics = monitor.get_metrics("failing_async")
        assert "metrics" in metrics
        assert metrics["metrics"]["error_count"] == 1

    async def test_async_wrapper_records_failure_on_runtime_error(self):
        monitor = PerformanceMonitor()

        @monitor.timed("rt_error_async")
        async def fn():
            raise RuntimeError("runtime")

        with pytest.raises(RuntimeError):
            await fn()

        await asyncio.sleep(0.05)
        m = monitor.get_metrics("rt_error_async")
        assert m["metrics"]["error_count"] == 1

    async def test_async_wrapper_records_failure_on_type_error(self):
        monitor = PerformanceMonitor()

        @monitor.timed("type_error_async")
        async def fn():
            raise TypeError("type")

        with pytest.raises(TypeError):
            await fn()

        await asyncio.sleep(0.05)
        m = monitor.get_metrics("type_error_async")
        assert m["metrics"]["error_count"] == 1

    async def test_async_wrapper_records_failure_on_key_error(self):
        monitor = PerformanceMonitor()

        @monitor.timed("key_error_async")
        async def fn():
            raise KeyError("key")

        with pytest.raises(KeyError):
            await fn()

        await asyncio.sleep(0.05)
        m = monitor.get_metrics("key_error_async")
        assert m["metrics"]["error_count"] == 1

    async def test_async_wrapper_records_failure_on_attribute_error(self):
        monitor = PerformanceMonitor()

        @monitor.timed("attr_error_async")
        async def fn():
            raise AttributeError("attr")

        with pytest.raises(AttributeError):
            await fn()

        await asyncio.sleep(0.05)
        m = monitor.get_metrics("attr_error_async")
        assert m["metrics"]["error_count"] == 1

    async def test_async_wrapper_records_failure_on_cancelled_error(self):
        monitor = PerformanceMonitor()

        @monitor.timed("cancel_async")
        async def fn():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await fn()

        await asyncio.sleep(0.05)
        m = monitor.get_metrics("cancel_async")
        assert m["metrics"]["error_count"] == 1


# ---------------------------------------------------------------------------
# PerformanceMonitor — sync_wrapper paths
# ---------------------------------------------------------------------------


class TestSyncWrapperPaths:
    """Cover sync_wrapper branches: disabled, trace_id, exception, no-loop."""

    def test_sync_wrapper_disabled_skips_timing(self):
        monitor = PerformanceMonitor()
        monitor.disable()

        @monitor.timed("noop_sync")
        def fn():
            return 99

        result = fn()
        assert result == 99
        assert monitor.get_metrics()["summary"]["total_operations"] == 0

    def test_sync_wrapper_with_trace_id(self):
        monitor = PerformanceMonitor()

        @monitor.timed("traced_sync")
        def fn(**kwargs):
            return kwargs.get("trace_id")

        result = fn(trace_id="tid-001")
        assert result == "tid-001"
        # Allow async task a moment to schedule
        time.sleep(0.05)

    def test_sync_wrapper_records_failure_on_value_error(self):
        monitor = PerformanceMonitor()

        @monitor.timed("sync_value_err")
        def fn():
            raise ValueError("sync boom")

        with pytest.raises(ValueError, match="sync boom"):
            fn()

        time.sleep(0.05)

    def test_sync_wrapper_records_failure_on_runtime_error(self):
        monitor = PerformanceMonitor()

        @monitor.timed("sync_rt_err")
        def fn():
            raise RuntimeError("rt")

        with pytest.raises(RuntimeError):
            fn()

        time.sleep(0.05)

    def test_sync_wrapper_no_event_loop_stores_directly(self):
        """When called outside any event loop, sync wrapper stores via _store_record_sync."""
        monitor = PerformanceMonitor()

        @monitor.timed("no_loop_sync")
        def fn():
            return "direct"

        # Patch get_running_loop to raise RuntimeError (no loop)
        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            result = fn()

        assert result == "direct"
        # Record stored synchronously — visible immediately
        assert "no_loop_sync" in monitor.get_operation_names()

    def test_sync_wrapper_no_event_loop_exception_path(self):
        """Exception in sync wrapper with no loop still records failure."""
        monitor = PerformanceMonitor()

        @monitor.timed("no_loop_fail")
        def fn():
            raise ValueError("direct fail")

        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            with pytest.raises(ValueError):
                fn()

        m = monitor.get_metrics("no_loop_fail")
        assert m["metrics"]["error_count"] == 1

    async def test_sync_wrapper_within_running_loop_uses_create_task(self):
        """When a sync-wrapped fn is called from inside a running loop,
        asyncio.create_task is used to schedule the record (line 259)."""
        monitor = PerformanceMonitor()

        @monitor.timed("sync_in_loop")
        def sync_fn():
            return "in-loop"

        result = sync_fn()
        assert result == "in-loop"
        # Yield to event loop so the scheduled task runs
        await asyncio.sleep(0.05)
        assert "sync_in_loop" in monitor.get_operation_names()


# ---------------------------------------------------------------------------
# PerformanceMonitor — _add_record / _store_record_sync
# ---------------------------------------------------------------------------


class TestInternalRecordMethods:
    async def test_add_record_populates_metrics(self):
        monitor = PerformanceMonitor()
        record = TimingRecord(
            operation="internal_op",
            duration_ms=7.5,
            timestamp=time.time(),
            success=True,
        )
        await monitor._add_record(record)
        assert "internal_op" in monitor.get_operation_names()

    def test_store_record_sync_creates_operation_first_time(self):
        monitor = PerformanceMonitor()
        record = TimingRecord(
            operation="sync_new_op",
            duration_ms=3.0,
            timestamp=time.time(),
            success=True,
        )
        monitor._store_record_sync(record)
        assert "sync_new_op" in monitor.get_operation_names()

    def test_store_record_sync_appends_to_existing_operation(self):
        monitor = PerformanceMonitor()
        for i in range(3):
            record = TimingRecord(
                operation="existing",
                duration_ms=float(i + 1),
                timestamp=time.time(),
                success=True,
            )
            monitor._store_record_sync(record)
        m = monitor.get_metrics("existing")
        assert m["metrics"]["count"] == 3


# ---------------------------------------------------------------------------
# PerformanceMonitor — record_timing
# ---------------------------------------------------------------------------


class TestRecordTimingMethod:
    """Cover both the async-loop path and the no-loop path of record_timing."""

    async def test_record_timing_with_running_loop(self):
        monitor = PerformanceMonitor()
        monitor.record_timing(
            operation="async_ctx",
            duration_ms=12.0,
            success=True,
            trace_id="t1",
            metadata={"k": "v"},
        )
        await asyncio.sleep(0.05)
        m = monitor.get_metrics("async_ctx")
        assert m["metrics"]["count"] == 1

    async def test_record_timing_disabled_does_nothing(self):
        monitor = PerformanceMonitor()
        monitor.disable()
        monitor.record_timing(operation="ignored", duration_ms=5.0)
        await asyncio.sleep(0.05)
        assert monitor.get_metrics()["summary"]["total_operations"] == 0

    def test_record_timing_no_loop_stores_directly(self):
        monitor = PerformanceMonitor()
        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            monitor.record_timing(
                operation="no_loop_record",
                duration_ms=8.0,
                success=False,
            )
        m = monitor.get_metrics("no_loop_record")
        assert m["metrics"]["count"] == 1
        assert m["metrics"]["error_count"] == 1

    def test_record_timing_no_loop_with_metadata(self):
        monitor = PerformanceMonitor()
        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            monitor.record_timing(
                operation="meta_no_loop",
                duration_ms=4.0,
                metadata={"source": "test"},
            )
        m = monitor.get_metrics("meta_no_loop")
        assert m["metrics"]["count"] == 1


# ---------------------------------------------------------------------------
# PerformanceMonitor — get_metrics
# ---------------------------------------------------------------------------


class TestGetMetrics:
    async def test_get_metrics_empty_all(self):
        monitor = PerformanceMonitor()
        result = monitor.get_metrics()
        assert result["summary"]["total_operations"] == 0
        assert result["summary"]["total_records"] == 0
        assert result["summary"]["global_error_rate"] == 0
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_get_metrics_all_includes_timestamp(self):
        monitor = PerformanceMonitor()
        result = monitor.get_metrics()
        assert "timestamp" in result

    async def test_get_metrics_all_with_errors(self):
        monitor = PerformanceMonitor()
        for _ in range(5):
            record = TimingRecord(
                operation="err_op",
                duration_ms=1.0,
                timestamp=time.time(),
                success=False,
            )
            await monitor._add_record(record)
        result = monitor.get_metrics()
        assert result["summary"]["total_errors"] == 5
        assert result["summary"]["global_error_rate"] == 100.0

    async def test_get_metrics_mixed_operations(self):
        monitor = PerformanceMonitor()
        for op in ["op_a", "op_b", "op_c"]:
            record = TimingRecord(
                operation=op,
                duration_ms=5.0,
                timestamp=time.time(),
                success=True,
            )
            await monitor._add_record(record)
        result = monitor.get_metrics()
        assert result["summary"]["total_operations"] == 3
        assert result["summary"]["total_count"] == 3
        assert "op_a" in result["operations"]
        assert "op_b" in result["operations"]
        assert "op_c" in result["operations"]

    async def test_get_metrics_single_operation_found(self):
        monitor = PerformanceMonitor()
        record = TimingRecord(
            operation="target_op",
            duration_ms=22.5,
            timestamp=time.time(),
            success=True,
        )
        await monitor._add_record(record)
        result = monitor.get_metrics("target_op")
        assert result["operation"] == "target_op"
        assert result["metrics"]["mean_ms"] == 22.5
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_metrics_single_operation_not_found(self):
        monitor = PerformanceMonitor()
        result = monitor.get_metrics("missing_op")
        assert "error" in result
        assert "missing_op" in result["error"]


# ---------------------------------------------------------------------------
# PerformanceMonitor — get_operation_names
# ---------------------------------------------------------------------------


class TestGetOperationNames:
    async def test_empty_initially(self):
        monitor = PerformanceMonitor()
        assert monitor.get_operation_names() == []

    async def test_returns_all_names(self):
        monitor = PerformanceMonitor()
        for name in ["alpha", "beta", "gamma"]:
            record = TimingRecord(
                operation=name,
                duration_ms=1.0,
                timestamp=time.time(),
                success=True,
            )
            await monitor._add_record(record)
        names = monitor.get_operation_names()
        assert set(names) == {"alpha", "beta", "gamma"}


# ---------------------------------------------------------------------------
# PerformanceMonitor — clear_metrics
# ---------------------------------------------------------------------------


class TestClearMetrics:
    async def test_clear_single_operation(self):
        monitor = PerformanceMonitor()
        for op in ["keep_me", "delete_me"]:
            await monitor._add_record(
                TimingRecord(
                    operation=op,
                    duration_ms=1.0,
                    timestamp=time.time(),
                    success=True,
                )
            )
        monitor.clear_metrics("delete_me")
        ops = monitor.get_operation_names()
        assert "delete_me" not in ops
        assert "keep_me" in ops

    async def test_clear_single_operation_also_clears_records(self):
        monitor = PerformanceMonitor()
        await monitor._add_record(
            TimingRecord(
                operation="to_clear",
                duration_ms=1.0,
                timestamp=time.time(),
                success=True,
            )
        )
        monitor.clear_metrics("to_clear")
        # After clear, records deque should have no entries for that op
        assert all(r.operation != "to_clear" for r in monitor._records)

    async def test_clear_nonexistent_operation_is_noop(self):
        monitor = PerformanceMonitor()
        await monitor._add_record(
            TimingRecord(
                operation="stays",
                duration_ms=1.0,
                timestamp=time.time(),
                success=True,
            )
        )
        monitor.clear_metrics("nonexistent")  # should not raise
        assert "stays" in monitor.get_operation_names()

    async def test_clear_all(self):
        monitor = PerformanceMonitor()
        for op in ["x", "y", "z"]:
            await monitor._add_record(
                TimingRecord(
                    operation=op,
                    duration_ms=1.0,
                    timestamp=time.time(),
                    success=True,
                )
            )
        monitor.clear_metrics()
        assert monitor.get_operation_names() == []
        assert len(monitor._records) == 0


# ---------------------------------------------------------------------------
# PerformanceMonitor — enable / disable / is_enabled
# ---------------------------------------------------------------------------


class TestEnableDisable:
    def test_enabled_by_default(self):
        monitor = PerformanceMonitor()
        assert monitor.is_enabled is True

    def test_disable_sets_flag(self):
        monitor = PerformanceMonitor()
        monitor.disable()
        assert monitor.is_enabled is False

    def test_enable_restores_flag(self):
        monitor = PerformanceMonitor()
        monitor.disable()
        monitor.enable()
        assert monitor.is_enabled is True

    def test_enable_logs_message(self, caplog):
        import logging

        monitor = PerformanceMonitor()
        with caplog.at_level(logging.INFO):
            monitor.enable()
        assert any("enabled" in r.message.lower() for r in caplog.records)

    def test_disable_logs_message(self, caplog):
        import logging

        monitor = PerformanceMonitor()
        with caplog.at_level(logging.INFO):
            monitor.disable()
        assert any("disabled" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Global helpers
# ---------------------------------------------------------------------------


class TestGlobalHelpers:
    def test_get_performance_monitor_returns_instance(self):
        monitor = get_performance_monitor()
        assert isinstance(monitor, PerformanceMonitor)

    def test_get_performance_monitor_singleton(self):
        m1 = get_performance_monitor()
        m2 = get_performance_monitor()
        assert m1 is m2

    def test_set_performance_monitor_replaces_global(self):
        new_monitor = PerformanceMonitor()
        set_performance_monitor(new_monitor)
        assert get_performance_monitor() is new_monitor
        # Reset to fresh instance to avoid polluting other tests
        set_performance_monitor(PerformanceMonitor())

    def test_get_performance_monitor_creates_when_none(self):
        # Temporarily set the global to None to exercise the creation branch
        original = _pm_module._global_monitor
        _pm_module._global_monitor = None
        try:
            m = get_performance_monitor()
            assert isinstance(m, PerformanceMonitor)
        finally:
            _pm_module._global_monitor = original

    def test_timed_global_decorator_works_on_sync(self):
        # Ensure the global monitor is a fresh one for this test
        fresh = PerformanceMonitor()
        set_performance_monitor(fresh)

        @timed("global_sync")
        def fn():
            return "done"

        result = fn()
        assert result == "done"
        # Reset
        set_performance_monitor(PerformanceMonitor())

    async def test_timed_global_decorator_works_on_async(self):
        fresh = PerformanceMonitor()
        set_performance_monitor(fresh)

        @timed("global_async")
        async def fn():
            return "async_done"

        result = await fn()
        assert result == "async_done"
        set_performance_monitor(PerformanceMonitor())


# ---------------------------------------------------------------------------
# MetricType enum (ensure all values exercised)
# ---------------------------------------------------------------------------


class TestMetricTypeEnum:
    def test_latency_value(self):
        assert MetricType.LATENCY.value == "latency"

    def test_throughput_value(self):
        assert MetricType.THROUGHPUT.value == "throughput"

    def test_error_rate_value(self):
        assert MetricType.ERROR_RATE.value == "error_rate"

    def test_custom_value(self):
        assert MetricType.CUSTOM.value == "custom"

    def test_enum_len(self):
        assert len(MetricType) == 4


# ---------------------------------------------------------------------------
# Constitutional hash integrity
# ---------------------------------------------------------------------------


@pytest.mark.constitutional
class TestConstitutionalHashIntegrity:
    def test_timing_record_carries_hash(self):
        record = TimingRecord(
            operation="test",
            duration_ms=1.0,
            timestamp=0.0,
            success=True,
        )
        assert record.constitutional_hash == CONSTITUTIONAL_HASH

    def test_operation_metrics_carries_hash(self):
        m = OperationMetrics(operation="test")
        assert m.constitutional_hash == CONSTITUTIONAL_HASH

    def test_performance_monitor_carries_hash(self):
        monitor = PerformanceMonitor()
        assert monitor.constitutional_hash == CONSTITUTIONAL_HASH

    def test_get_metrics_response_carries_hash(self):
        monitor = PerformanceMonitor()
        result = monitor.get_metrics()
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
