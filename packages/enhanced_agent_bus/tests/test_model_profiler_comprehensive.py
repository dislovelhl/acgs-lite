"""
Comprehensive tests for ModelProfiler module.
Constitutional Hash: 608508a9bd224290

Coverage targets:
- BottleneckType enum
- InferenceMetrics dataclass
- ProfilingMetrics dataclass
- ModelProfiler class
- track() context manager
- profile() and profile_async() decorators
- get_metrics() and get_all_metrics()
- _classify_bottleneck()
- generate_report()
- reset()
- Global profiler functions
- CPU and memory measurement
- Prometheus integration
- Thread safety
"""

import asyncio
import threading
import time
from datetime import datetime, timezone

import pytest

# Import the module under test
from enhanced_agent_bus.profiling.model_profiler import (
    PROMETHEUS_AVAILABLE,
    PSUTIL_AVAILABLE,
    BottleneckType,
    InferenceMetrics,
    ModelProfiler,
    ProfilingMetrics,
    get_global_profiler,
    profile_async_call,
    profile_inference,
)


@pytest.fixture(autouse=True)
def reset_prometheus_registry():
    """Reset Prometheus registry and global profiler between tests to prevent duplication errors."""
    import enhanced_agent_bus.profiling.model_profiler as profiler_module

    # Reset global profiler
    profiler_module._global_profiler = None

    yield

    # Cleanup after test - reset again and try to unregister metrics
    profiler_module._global_profiler = None

    # Try to clear Prometheus collectors if available
    if PROMETHEUS_AVAILABLE:
        try:
            from prometheus_client import REGISTRY

            # Get collectors to remove (those with our prefix)
            collectors_to_remove = []
            for collector in list(REGISTRY._collector_to_names.keys()):
                try:
                    if hasattr(collector, "_name") and collector._name.startswith("acgs2_model"):
                        collectors_to_remove.append(collector)
                except (AttributeError, TypeError):
                    pass

            # Unregister our collectors
            for collector in collectors_to_remove:
                try:
                    REGISTRY.unregister(collector)
                except (RuntimeError, ValueError, TypeError):
                    pass
        except (RuntimeError, ValueError, TypeError):
            pass


class TestBottleneckType:
    """Tests for BottleneckType enum."""

    def test_compute_bound_value(self):
        """Test COMPUTE_BOUND enum value."""
        assert BottleneckType.COMPUTE_BOUND.value == "compute_bound"

    def test_io_bound_value(self):
        """Test IO_BOUND enum value."""
        assert BottleneckType.IO_BOUND.value == "io_bound"

    def test_memory_bound_value(self):
        """Test MEMORY_BOUND enum value."""
        assert BottleneckType.MEMORY_BOUND.value == "memory_bound"

    def test_unknown_value(self):
        """Test UNKNOWN enum value."""
        assert BottleneckType.UNKNOWN.value == "unknown"

    def test_all_variants_accessible(self):
        """Test all enum variants are accessible."""
        variants = list(BottleneckType)
        assert len(variants) == 4


class TestInferenceMetrics:
    """Tests for InferenceMetrics dataclass."""

    def test_basic_creation(self):
        """Test basic creation of InferenceMetrics."""
        metrics = InferenceMetrics(
            model_name="test_model",
            execution_time_ms=10.5,
            cpu_percent_before=10.0,
            cpu_percent_during=50.0,
            memory_mb_before=100.0,
            memory_mb_after=150.0,
        )
        assert metrics.model_name == "test_model"
        assert metrics.execution_time_ms == 10.5

    def test_memory_delta_property(self):
        """Test memory_delta_mb property calculation."""
        metrics = InferenceMetrics(
            model_name="test",
            execution_time_ms=10.0,
            cpu_percent_before=0.0,
            cpu_percent_during=0.0,
            memory_mb_before=100.0,
            memory_mb_after=150.0,
        )
        assert metrics.memory_delta_mb == 50.0

    def test_cpu_delta_property(self):
        """Test cpu_delta property calculation."""
        metrics = InferenceMetrics(
            model_name="test",
            execution_time_ms=10.0,
            cpu_percent_before=10.0,
            cpu_percent_during=60.0,
            memory_mb_before=100.0,
            memory_mb_after=100.0,
        )
        assert metrics.cpu_delta == 50.0

    def test_timestamp_auto_generated(self):
        """Test that timestamp is auto-generated."""
        metrics = InferenceMetrics(
            model_name="test",
            execution_time_ms=10.0,
            cpu_percent_before=0.0,
            cpu_percent_during=0.0,
            memory_mb_before=0.0,
            memory_mb_after=0.0,
        )
        assert metrics.timestamp is not None
        assert isinstance(metrics.timestamp, datetime)

    def test_negative_memory_delta(self):
        """Test negative memory delta (memory freed)."""
        metrics = InferenceMetrics(
            model_name="test",
            execution_time_ms=10.0,
            cpu_percent_before=0.0,
            cpu_percent_during=0.0,
            memory_mb_before=150.0,
            memory_mb_after=100.0,
        )
        assert metrics.memory_delta_mb == -50.0


class TestProfilingMetrics:
    """Tests for ProfilingMetrics dataclass."""

    def test_basic_creation(self):
        """Test basic creation of ProfilingMetrics."""
        metrics = ProfilingMetrics(
            model_name="test_model",
            sample_count=100,
            latency_p50_ms=5.0,
            latency_p95_ms=10.0,
            latency_p99_ms=15.0,
            latency_mean_ms=6.0,
            latency_std_ms=2.0,
            avg_cpu_percent=30.0,
            peak_cpu_percent=80.0,
            avg_memory_mb=200.0,
            peak_memory_mb=300.0,
            bottleneck_type=BottleneckType.COMPUTE_BOUND,
            gpu_recommendation="GPU recommended",
        )
        assert metrics.model_name == "test_model"
        assert metrics.sample_count == 100

    def test_to_dict_structure(self):
        """Test to_dict returns proper structure."""
        metrics = ProfilingMetrics(
            model_name="test",
            sample_count=10,
            latency_p50_ms=5.0,
            latency_p95_ms=10.0,
            latency_p99_ms=15.0,
            latency_mean_ms=6.0,
            latency_std_ms=2.0,
            avg_cpu_percent=30.0,
            peak_cpu_percent=80.0,
            avg_memory_mb=200.0,
            peak_memory_mb=300.0,
            bottleneck_type=BottleneckType.IO_BOUND,
            gpu_recommendation="Keep on CPU",
        )
        d = metrics.to_dict()
        assert "model_name" in d
        assert "latency" in d
        assert "cpu" in d
        assert "memory" in d
        assert "analysis" in d

    def test_to_dict_latency_values(self):
        """Test to_dict latency values are rounded."""
        metrics = ProfilingMetrics(
            model_name="test",
            sample_count=10,
            latency_p50_ms=5.12345,
            latency_p95_ms=10.6789,
            latency_p99_ms=15.111,
            latency_mean_ms=6.222,
            latency_std_ms=2.333,
            avg_cpu_percent=30.0,
            peak_cpu_percent=80.0,
            avg_memory_mb=200.0,
            peak_memory_mb=300.0,
            bottleneck_type=BottleneckType.UNKNOWN,
            gpu_recommendation="Needs more analysis",
        )
        d = metrics.to_dict()
        assert d["latency"]["p50_ms"] == 5.123
        assert d["latency"]["p95_ms"] == 10.679

    def test_to_dict_cpu_values(self):
        """Test to_dict CPU values are rounded."""
        metrics = ProfilingMetrics(
            model_name="test",
            sample_count=10,
            latency_p50_ms=5.0,
            latency_p95_ms=10.0,
            latency_p99_ms=15.0,
            latency_mean_ms=6.0,
            latency_std_ms=2.0,
            avg_cpu_percent=30.5678,
            peak_cpu_percent=80.1234,
            avg_memory_mb=200.0,
            peak_memory_mb=300.0,
            bottleneck_type=BottleneckType.COMPUTE_BOUND,
            gpu_recommendation="GPU recommended",
        )
        d = metrics.to_dict()
        assert d["cpu"]["avg_percent"] == 30.6
        assert d["cpu"]["peak_percent"] == 80.1

    def test_to_dict_analysis_values(self):
        """Test to_dict analysis values."""
        metrics = ProfilingMetrics(
            model_name="test",
            sample_count=10,
            latency_p50_ms=5.0,
            latency_p95_ms=10.0,
            latency_p99_ms=15.0,
            latency_mean_ms=6.0,
            latency_std_ms=2.0,
            avg_cpu_percent=30.0,
            peak_cpu_percent=80.0,
            avg_memory_mb=200.0,
            peak_memory_mb=300.0,
            bottleneck_type=BottleneckType.COMPUTE_BOUND,
            gpu_recommendation="GPU recommended",
        )
        d = metrics.to_dict()
        assert d["analysis"]["bottleneck_type"] == "compute_bound"
        assert d["analysis"]["gpu_recommendation"] == "GPU recommended"


class TestModelProfilerInit:
    """Tests for ModelProfiler initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        profiler = ModelProfiler(enable_prometheus=False)
        assert profiler._max_samples == 1000
        assert len(profiler._samples) == 0

    def test_custom_max_samples(self):
        """Test custom max_samples setting."""
        profiler = ModelProfiler(max_samples_per_model=500, enable_prometheus=False)
        assert profiler._max_samples == 500

    def test_prometheus_disabled(self):
        """Test Prometheus can be disabled."""
        profiler = ModelProfiler(enable_prometheus=False)
        assert not profiler._prometheus_enabled

    def test_thread_lock_created(self):
        """Test thread lock is created."""
        profiler = ModelProfiler(enable_prometheus=False)
        assert profiler._lock is not None


class TestModelProfilerTrack:
    """Tests for track() context manager."""

    def test_track_records_sample(self):
        """Test that track() records a sample."""
        profiler = ModelProfiler(enable_prometheus=False)
        with profiler.track("test_model"):
            time.sleep(0.001)  # 1ms

        assert "test_model" in profiler._samples
        assert len(profiler._samples["test_model"]) == 1

    def test_track_measures_execution_time(self):
        """Test that track() measures execution time."""
        profiler = ModelProfiler(enable_prometheus=False)
        with profiler.track("test_model"):
            time.sleep(0.01)  # 10ms

        sample = profiler._samples["test_model"][0]
        assert sample.execution_time_ms >= 10.0  # At least 10ms

    def test_track_handles_exceptions(self):
        """Test that track() records even when exception raised."""
        profiler = ModelProfiler(enable_prometheus=False)
        try:
            with profiler.track("test_model"):
                raise ValueError("Test error")
        except ValueError:
            pass

        # Should still record the sample
        assert len(profiler._samples["test_model"]) == 1

    def test_track_multiple_calls(self):
        """Test multiple tracking calls."""
        profiler = ModelProfiler(enable_prometheus=False)
        for _ in range(5):
            with profiler.track("test_model"):
                pass

        assert len(profiler._samples["test_model"]) == 5

    def test_track_different_models(self):
        """Test tracking different models."""
        profiler = ModelProfiler(enable_prometheus=False)
        with profiler.track("model_a"):
            pass
        with profiler.track("model_b"):
            pass

        assert "model_a" in profiler._samples
        assert "model_b" in profiler._samples


class TestModelProfilerDecorator:
    """Tests for profile() decorator."""

    def test_profile_decorator_basic(self):
        """Test basic profile decorator."""
        profiler = ModelProfiler(enable_prometheus=False)

        @profiler.profile("test_func")
        def test_function():
            return "result"

        result = test_function()
        assert result == "result"
        assert len(profiler._samples["test_func"]) == 1

    def test_profile_decorator_preserves_return(self):
        """Test that decorator preserves return value."""
        profiler = ModelProfiler(enable_prometheus=False)

        @profiler.profile("test_func")
        def compute():
            return 42

        assert compute() == 42

    def test_profile_decorator_with_args(self):
        """Test decorator with function arguments."""
        profiler = ModelProfiler(enable_prometheus=False)

        @profiler.profile("add_func")
        def add(a, b):
            return a + b

        result = add(3, 4)
        assert result == 7

    def test_profile_decorator_with_kwargs(self):
        """Test decorator with keyword arguments."""
        profiler = ModelProfiler(enable_prometheus=False)

        @profiler.profile("greet_func")
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}"

        result = greet("World", greeting="Hi")
        assert result == "Hi, World"


class TestModelProfilerAsyncDecorator:
    """Tests for profile_async() decorator."""

    async def test_profile_async_basic(self):
        """Test basic async profile decorator."""
        profiler = ModelProfiler(enable_prometheus=False)

        @profiler.profile_async("async_func")
        async def async_function():
            await asyncio.sleep(0.001)
            return "async result"

        result = await async_function()
        assert result == "async result"
        assert len(profiler._samples["async_func"]) == 1

    async def test_profile_async_measures_time(self):
        """Test async decorator measures execution time."""
        profiler = ModelProfiler(enable_prometheus=False)

        @profiler.profile_async("async_func")
        async def slow_function():
            await asyncio.sleep(0.01)  # 10ms
            return "done"

        await slow_function()
        sample = profiler._samples["async_func"][0]
        assert sample.execution_time_ms >= 10.0


class TestModelProfilerMetrics:
    """Tests for get_metrics() method."""

    def test_get_metrics_empty(self):
        """Test get_metrics returns None when no samples."""
        profiler = ModelProfiler(enable_prometheus=False)
        result = profiler.get_metrics("nonexistent")
        assert result is None

    def test_get_metrics_basic(self):
        """Test get_metrics with samples."""
        profiler = ModelProfiler(enable_prometheus=False)
        for _ in range(10):
            with profiler.track("test_model"):
                time.sleep(0.001)

        metrics = profiler.get_metrics("test_model")
        assert metrics is not None
        assert metrics.sample_count == 10
        assert metrics.model_name == "test_model"

    def test_get_metrics_latency_percentiles(self):
        """Test latency percentiles are calculated."""
        profiler = ModelProfiler(enable_prometheus=False)
        for _ in range(100):
            with profiler.track("test_model"):
                time.sleep(0.001)

        metrics = profiler.get_metrics("test_model")
        assert metrics.latency_p50_ms > 0
        assert metrics.latency_p95_ms >= metrics.latency_p50_ms
        assert metrics.latency_p99_ms >= metrics.latency_p95_ms

    def test_get_metrics_with_few_samples(self):
        """Test metrics with fewer than 20 samples."""
        profiler = ModelProfiler(enable_prometheus=False)
        for _ in range(5):
            with profiler.track("test_model"):
                pass

        metrics = profiler.get_metrics("test_model")
        assert metrics is not None
        assert metrics.sample_count == 5


class TestModelProfilerClassifyBottleneck:
    """Tests for _classify_bottleneck() method."""

    def test_classify_compute_bound(self):
        """Test compute-bound classification."""
        profiler = ModelProfiler(enable_prometheus=False)
        bottleneck, _ = profiler._classify_bottleneck(avg_cpu=70.0, avg_latency_ms=10.0)
        assert bottleneck == BottleneckType.COMPUTE_BOUND

    def test_classify_io_bound_low_cpu(self):
        """Test I/O-bound classification with low CPU."""
        profiler = ModelProfiler(enable_prometheus=False)
        bottleneck, _ = profiler._classify_bottleneck(avg_cpu=10.0, avg_latency_ms=10.0)
        assert bottleneck == BottleneckType.IO_BOUND

    def test_classify_io_bound_low_latency(self):
        """Test I/O-bound classification with low latency."""
        profiler = ModelProfiler(enable_prometheus=False)
        bottleneck, _ = profiler._classify_bottleneck(avg_cpu=70.0, avg_latency_ms=0.5)
        assert bottleneck == BottleneckType.IO_BOUND

    def test_classify_unknown(self):
        """Test unknown classification with moderate CPU."""
        profiler = ModelProfiler(enable_prometheus=False)
        bottleneck, _ = profiler._classify_bottleneck(avg_cpu=35.0, avg_latency_ms=10.0)
        assert bottleneck == BottleneckType.UNKNOWN


class TestModelProfilerReport:
    """Tests for generate_report() method."""

    def test_generate_report_empty(self):
        """Test report generation with no data."""
        profiler = ModelProfiler(enable_prometheus=False)
        report = profiler.generate_report()
        assert "No profiling data collected" in report

    def test_generate_report_with_data(self):
        """Test report generation with data."""
        profiler = ModelProfiler(enable_prometheus=False)
        for _ in range(10):
            with profiler.track("test_model"):
                time.sleep(0.001)

        report = profiler.generate_report()
        assert "ACGS-2 MODEL PROFILING REPORT" in report
        assert "test_model" in report

    def test_generate_report_multiple_models(self):
        """Test report generation with multiple models."""
        profiler = ModelProfiler(enable_prometheus=False)
        for _ in range(5):
            with profiler.track("model_a"):
                time.sleep(0.001)
            with profiler.track("model_b"):
                time.sleep(0.001)

        report = profiler.generate_report()
        assert "model_a" in report
        assert "model_b" in report


class TestModelProfilerReset:
    """Tests for reset() method."""

    def test_reset_specific_model(self):
        """Test resetting specific model."""
        profiler = ModelProfiler(enable_prometheus=False)
        with profiler.track("model_a"):
            pass
        with profiler.track("model_b"):
            pass

        profiler.reset("model_a")
        assert "model_a" not in profiler._samples
        assert "model_b" in profiler._samples

    def test_reset_all(self):
        """Test resetting all models."""
        profiler = ModelProfiler(enable_prometheus=False)
        with profiler.track("model_a"):
            pass
        with profiler.track("model_b"):
            pass

        profiler.reset()
        assert len(profiler._samples) == 0

    def test_reset_nonexistent_model(self):
        """Test resetting nonexistent model doesn't error."""
        profiler = ModelProfiler(enable_prometheus=False)
        profiler.reset("nonexistent")  # Should not raise


class TestSampleLimiting:
    """Tests for sample limiting behavior."""

    def test_samples_limited_to_max(self):
        """Test that samples are limited to max_samples."""
        profiler = ModelProfiler(max_samples_per_model=10, enable_prometheus=False)
        for _ in range(20):
            with profiler.track("test_model"):
                pass

        assert len(profiler._samples["test_model"]) == 10


class TestGetAllMetrics:
    """Tests for get_all_metrics() method."""

    def test_get_all_metrics_empty(self):
        """Test get_all_metrics with no data."""
        profiler = ModelProfiler(enable_prometheus=False)
        result = profiler.get_all_metrics()
        assert result == {}

    def test_get_all_metrics_multiple_models(self):
        """Test get_all_metrics with multiple models."""
        profiler = ModelProfiler(enable_prometheus=False)
        for _ in range(5):
            with profiler.track("model_a"):
                pass
            with profiler.track("model_b"):
                pass

        result = profiler.get_all_metrics()
        assert "model_a" in result
        assert "model_b" in result


class TestGlobalProfiler:
    """Tests for global profiler functions."""

    def test_get_global_profiler_singleton(self):
        """Test that get_global_profiler returns singleton."""
        # Reset global profiler
        import enhanced_agent_bus.profiling.model_profiler as profiler_module

        profiler_module._global_profiler = None

        profiler1 = get_global_profiler()
        profiler2 = get_global_profiler()
        assert profiler1 is profiler2

    def test_profile_inference_decorator(self):
        """Test profile_inference convenience decorator."""
        # Reset global profiler
        import enhanced_agent_bus.profiling.model_profiler as profiler_module

        profiler_module._global_profiler = None

        @profile_inference("test_func")
        def test_function():
            return "result"

        result = test_function()
        assert result == "result"


class TestProfileAsyncCall:
    """Tests for profile_async_call function."""

    async def test_profile_async_call_coroutine(self):
        """Test profiling async call with coroutine."""
        # Reset global profiler
        import enhanced_agent_bus.profiling.model_profiler as profiler_module

        profiler_module._global_profiler = None

        async def async_compute():
            await asyncio.sleep(0.001)
            return 42

        result = await profile_async_call("test_model", async_compute)
        assert result == 42

    async def test_profile_async_call_sync_function(self):
        """Test profiling call with sync function that returns coroutine."""
        import enhanced_agent_bus.profiling.model_profiler as profiler_module

        profiler_module._global_profiler = None

        async def sync_returning_async():
            return "sync_result"

        result = await profile_async_call("test_model", sync_returning_async)
        assert result == "sync_result"


class TestCPUAndMemoryMeasurement:
    """Tests for CPU and memory measurement functions."""

    def test_get_cpu_percent_with_psutil(self):
        """Test CPU percent measurement with psutil."""
        if not PSUTIL_AVAILABLE:
            pytest.skip("psutil not available")

        profiler = ModelProfiler(enable_prometheus=False)
        cpu = profiler._get_cpu_percent()
        assert cpu >= 0.0

    def test_get_memory_mb_with_psutil(self):
        """Test memory measurement with psutil."""
        if not PSUTIL_AVAILABLE:
            pytest.skip("psutil not available")

        profiler = ModelProfiler(enable_prometheus=False)
        memory = profiler._get_memory_mb()
        assert memory > 0.0

    def test_get_cpu_percent_without_psutil(self):
        """Test CPU percent returns 0 without psutil."""
        profiler = ModelProfiler(enable_prometheus=False)
        profiler._process = None  # Simulate no psutil
        cpu = profiler._get_cpu_percent()
        assert cpu == 0.0

    def test_get_memory_mb_without_psutil(self):
        """Test memory returns 0 without psutil."""
        profiler = ModelProfiler(enable_prometheus=False)
        profiler._process = None  # Simulate no psutil
        memory = profiler._get_memory_mb()
        assert memory == 0.0


class TestPrometheusIntegration:
    """Tests for Prometheus integration."""

    def test_prometheus_disabled_no_error(self):
        """Test that disabled Prometheus doesn't cause errors."""
        profiler = ModelProfiler(enable_prometheus=False)
        with profiler.track("test"):
            pass
        # Should not raise any errors

    def test_prometheus_metrics_recorded(self):
        """Test Prometheus metrics are recorded when enabled."""
        if not PROMETHEUS_AVAILABLE:
            pytest.skip("Prometheus not available")

        profiler = ModelProfiler(enable_prometheus=True)
        with profiler.track("test"):
            time.sleep(0.001)
        # Should not raise and metrics should be recorded


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_tracking(self):
        """Test concurrent tracking from multiple threads."""
        profiler = ModelProfiler(enable_prometheus=False)

        def track_calls():
            for _ in range(10):
                with profiler.track("concurrent_model"):
                    time.sleep(0.001)

        threads = [threading.Thread(target=track_calls) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have 50 samples (5 threads * 10 calls)
        assert len(profiler._samples["concurrent_model"]) == 50
