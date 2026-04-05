"""
ACGS-2 Model Profiler - GPU Acceleration Evaluation
Constitutional Hash: 608508a9bd224290

Model profiling for determining GPU acceleration ROI.

This module instruments ML model inference to measure:
1. Actual model execution time (not request overhead)
2. CPU utilization during inference
3. Memory allocation patterns
4. Whether models are compute-bound or I/O-bound

Results inform the GPU vs CPU decision for each model.
"""

from __future__ import annotations

import functools
import inspect
import statistics
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    from prometheus_client import Counter, Gauge, Histogram

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = get_logger(__name__)


class BottleneckType(Enum):
    """Classification of model bottleneck type."""

    COMPUTE_BOUND = "compute_bound"  # High CPU, benefits from GPU
    IO_BOUND = "io_bound"  # Low CPU, GPU won't help
    MEMORY_BOUND = "memory_bound"  # Memory transfer limited
    UNKNOWN = "unknown"


@dataclass
class InferenceMetrics:
    """Metrics for a single inference call."""

    model_name: str
    execution_time_ms: float
    cpu_percent_before: float
    cpu_percent_during: float
    memory_mb_before: float
    memory_mb_after: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def memory_delta_mb(self) -> float:
        return self.memory_mb_after - self.memory_mb_before

    @property
    def cpu_delta(self) -> float:
        return self.cpu_percent_during - self.cpu_percent_before


@dataclass
class ProfilingMetrics:
    """Aggregated profiling metrics for a model."""

    model_name: str
    sample_count: int
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_mean_ms: float
    latency_std_ms: float
    avg_cpu_percent: float
    peak_cpu_percent: float
    avg_memory_mb: float
    peak_memory_mb: float
    bottleneck_type: BottleneckType
    gpu_recommendation: str

    def to_dict(self) -> JSONDict:
        return {
            "model_name": self.model_name,
            "sample_count": self.sample_count,
            "latency": {
                "p50_ms": round(self.latency_p50_ms, 3),
                "p95_ms": round(self.latency_p95_ms, 3),
                "p99_ms": round(self.latency_p99_ms, 3),
                "mean_ms": round(self.latency_mean_ms, 3),
                "std_ms": round(self.latency_std_ms, 3),
            },
            "cpu": {
                "avg_percent": round(self.avg_cpu_percent, 1),
                "peak_percent": round(self.peak_cpu_percent, 1),
            },
            "memory": {
                "avg_mb": round(self.avg_memory_mb, 2),
                "peak_mb": round(self.peak_memory_mb, 2),
            },
            "analysis": {
                "bottleneck_type": self.bottleneck_type.value,
                "gpu_recommendation": self.gpu_recommendation,
            },
        }


class ModelProfiler:
    """
    Profiles ML model inference for GPU acceleration evaluation.

    Usage:
        profiler = ModelProfiler()

        # Context manager for synchronous code
        with profiler.track("impact_scorer"):
            result = model.predict(input)

        # Decorator for functions
        @profiler.profile("compliance_check")
        def check_compliance(data):
            return classifier.predict(data)

        # Get aggregated metrics
        metrics = profiler.get_metrics("impact_scorer")
        logger.info(f"P99 latency: {metrics.latency_p99_ms}ms")
        logger.info(f"GPU recommendation: {metrics.gpu_recommendation}")
    """

    # Thresholds for bottleneck classification
    CPU_COMPUTE_THRESHOLD = 50.0  # >50% CPU = compute-bound
    CPU_IO_THRESHOLD = 20.0  # <20% CPU = I/O-bound
    LATENCY_GPU_THRESHOLD_MS = 1.0  # Only consider GPU if >1ms

    def __init__(
        self,
        enable_prometheus: bool = True,
        max_samples_per_model: int = 1000,
    ):
        self._samples: dict[str, list[InferenceMetrics]] = defaultdict(list)
        self._max_samples = max_samples_per_model
        self._lock = threading.Lock()
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None

        # Prometheus metrics
        self._prometheus_enabled = enable_prometheus and PROMETHEUS_AVAILABLE
        if self._prometheus_enabled:
            self._setup_prometheus_metrics()

    def _setup_prometheus_metrics(self) -> None:
        """Initialize Prometheus metrics collectors."""
        self._inference_latency = Histogram(
            "acgs2_model_inference_latency_seconds",
            "Model inference latency in seconds",
            ["model_name"],
            buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
        )
        self._inference_count = Counter(
            "acgs2_model_inference_total",
            "Total model inference calls",
            ["model_name"],
        )
        self._cpu_usage = Gauge(
            "acgs2_model_cpu_percent",
            "CPU usage during model inference",
            ["model_name"],
        )

    def _get_cpu_percent(self) -> float:
        """Get current CPU percent for this process."""
        if self._process:
            try:
                return float(self._process.cpu_percent(interval=None))
            except (OSError, AttributeError, RuntimeError):
                pass
        return 0.0

    def _get_memory_mb(self) -> float:
        """Get current memory usage in MB."""
        if self._process:
            try:
                return float(self._process.memory_info().rss / (1024 * 1024))
            except (OSError, AttributeError, RuntimeError):
                pass
        return 0.0

    def _record_sample(self, metrics: InferenceMetrics) -> None:
        """Thread-safe sample recording with size limit."""
        with self._lock:
            samples = self._samples[metrics.model_name]
            samples.append(metrics)
            # Trim to max size (keep recent samples)
            if len(samples) > self._max_samples:
                self._samples[metrics.model_name] = samples[-self._max_samples :]

        # Update Prometheus
        if self._prometheus_enabled:
            self._inference_latency.labels(model_name=metrics.model_name).observe(
                metrics.execution_time_ms / 1000
            )
            self._inference_count.labels(model_name=metrics.model_name).inc()
            self._cpu_usage.labels(model_name=metrics.model_name).set(metrics.cpu_percent_during)

    @contextmanager
    def track(self, model_name: str):
        """
        Context manager for tracking model inference.

        Usage:
            with profiler.track("impact_scorer"):
                result = model.predict(input)
        """
        # Pre-inference measurements
        cpu_before = self._get_cpu_percent()
        memory_before = self._get_memory_mb()
        start_time = time.perf_counter()

        try:
            yield
        finally:
            # Post-inference measurements
            end_time = time.perf_counter()
            cpu_during = self._get_cpu_percent()
            memory_after = self._get_memory_mb()

            metrics = InferenceMetrics(
                model_name=model_name,
                execution_time_ms=(end_time - start_time) * 1000,
                cpu_percent_before=cpu_before,
                cpu_percent_during=cpu_during,
                memory_mb_before=memory_before,
                memory_mb_after=memory_after,
            )
            self._record_sample(metrics)

    def profile(self, model_name: str):
        """
        Decorator for profiling a function.

        Usage:
            @profiler.profile("compliance_check")
            def check_compliance(data):
                return classifier.predict(data)
        """

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with self.track(model_name):
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    def profile_async(self, model_name: str):
        """
        Decorator for profiling async functions.

        Usage:
            @profiler.profile_async("impact_scorer")
            async def score_impact(message):
                return await model.predict(message)
        """

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                cpu_before = self._get_cpu_percent()
                memory_before = self._get_memory_mb()
                start_time = time.perf_counter()

                try:
                    return await func(*args, **kwargs)
                finally:
                    end_time = time.perf_counter()
                    cpu_during = self._get_cpu_percent()
                    memory_after = self._get_memory_mb()

                    metrics = InferenceMetrics(
                        model_name=model_name,
                        execution_time_ms=(end_time - start_time) * 1000,
                        cpu_percent_before=cpu_before,
                        cpu_percent_during=cpu_during,
                        memory_mb_before=memory_before,
                        memory_mb_after=memory_after,
                    )
                    self._record_sample(metrics)

            return wrapper

        return decorator

    def _classify_bottleneck(
        self,
        avg_cpu: float,
        avg_latency_ms: float,
    ) -> tuple[BottleneckType, str]:
        """
        Classify bottleneck type and generate GPU recommendation.

        Returns:
            (BottleneckType, recommendation_string)
        """
        # Too fast for GPU to help
        if avg_latency_ms < self.LATENCY_GPU_THRESHOLD_MS:
            return (
                BottleneckType.IO_BOUND,
                f"Latency {avg_latency_ms:.3f}ms is too low for GPU benefit. "
                f"GPU overhead would likely increase latency. Keep on CPU.",
            )

        # High CPU = compute-bound = GPU candidate
        if avg_cpu > self.CPU_COMPUTE_THRESHOLD:
            return (
                BottleneckType.COMPUTE_BOUND,
                f"CPU usage {avg_cpu:.1f}% indicates compute-bound. "
                f"GPU acceleration likely beneficial. Consider RAPIDS/cuML or TensorRT.",
            )

        # Low CPU = I/O-bound = GPU won't help
        if avg_cpu < self.CPU_IO_THRESHOLD:
            return (
                BottleneckType.IO_BOUND,
                f"CPU usage {avg_cpu:.1f}% indicates I/O-bound. "
                f"GPU unlikely to help. Focus on reducing data transfer/serialization.",
            )

        # Medium CPU = needs more analysis
        return (
            BottleneckType.UNKNOWN,
            f"CPU usage {avg_cpu:.1f}% is moderate. "
            f"Run under higher load to determine if GPU would help.",
        )

    def get_metrics(self, model_name: str) -> ProfilingMetrics | None:
        """
        Get aggregated profiling metrics for a model.

        Returns None if no samples collected.
        """
        with self._lock:
            samples = self._samples.get(model_name, [])
            if not samples:
                return None

            latencies = [s.execution_time_ms for s in samples]
            cpu_values = [s.cpu_percent_during for s in samples]
            memory_values = [s.memory_mb_after for s in samples]

            sorted_latencies = sorted(latencies)
            n = len(sorted_latencies)

            avg_latency = statistics.mean(latencies)
            avg_cpu = statistics.mean(cpu_values)

            bottleneck_type, recommendation = self._classify_bottleneck(avg_cpu, avg_latency)

            return ProfilingMetrics(
                model_name=model_name,
                sample_count=n,
                latency_p50_ms=sorted_latencies[int(n * 0.50)],
                latency_p95_ms=sorted_latencies[int(n * 0.95)] if n >= 20 else sorted_latencies[-1],
                latency_p99_ms=(
                    sorted_latencies[int(n * 0.99)] if n >= 100 else sorted_latencies[-1]
                ),
                latency_mean_ms=avg_latency,
                latency_std_ms=statistics.stdev(latencies) if n > 1 else 0.0,
                avg_cpu_percent=avg_cpu,
                peak_cpu_percent=max(cpu_values),
                avg_memory_mb=statistics.mean(memory_values),
                peak_memory_mb=max(memory_values),
                bottleneck_type=bottleneck_type,
                gpu_recommendation=recommendation,
            )

    def get_all_metrics(self) -> dict[str, ProfilingMetrics]:
        """Get metrics for all profiled models."""
        with self._lock:
            model_names = list(self._samples.keys())

        return {
            name: metrics for name in model_names if (metrics := self.get_metrics(name)) is not None
        }

    def generate_report(self) -> str:
        """Generate a human-readable profiling report."""
        all_metrics = self.get_all_metrics()

        if not all_metrics:
            return "No profiling data collected yet."

        lines = [
            "=" * 70,
            "ACGS-2 MODEL PROFILING REPORT",
            f"Generated: {datetime.now(UTC).isoformat()}",
            "=" * 70,
            "",
        ]

        for name, metrics in sorted(all_metrics.items()):
            lines.extend(
                [
                    f"Model: {name}",
                    "-" * 40,
                    f"  Samples: {metrics.sample_count}",
                    f"  Latency P50: {metrics.latency_p50_ms:.3f}ms",
                    f"  Latency P95: {metrics.latency_p95_ms:.3f}ms",
                    f"  Latency P99: {metrics.latency_p99_ms:.3f}ms",
                    f"  CPU Avg: {metrics.avg_cpu_percent:.1f}%",
                    f"  CPU Peak: {metrics.peak_cpu_percent:.1f}%",
                    f"  Memory Avg: {metrics.avg_memory_mb:.1f}MB",
                    f"  Bottleneck: {metrics.bottleneck_type.value}",
                    f"  GPU Recommendation: {metrics.gpu_recommendation}",
                    "",
                ]
            )

        # Summary table
        lines.extend(
            [
                "=" * 70,
                "GPU ACCELERATION DECISION MATRIX",
                "=" * 70,
                f"{'Model':<25} {'Type':<15} {'P99(ms)':<10} {'CPU%':<8} {'GPU?'}",
                "-" * 70,
            ]
        )

        for name, metrics in sorted(all_metrics.items()):
            gpu_decision = (
                "✅ YES" if metrics.bottleneck_type == BottleneckType.COMPUTE_BOUND else "❌ NO"
            )
            lines.append(
                f"{name:<25} {metrics.bottleneck_type.value:<15} "
                f"{metrics.latency_p99_ms:<10.3f} {metrics.avg_cpu_percent:<8.1f} {gpu_decision}"
            )

        lines.append("=" * 70)
        return "\n".join(lines)

    def reset(self, model_name: str | None = None) -> None:
        """Reset collected samples."""
        with self._lock:
            if model_name:
                self._samples.pop(model_name, None)
            else:
                self._samples.clear()


# Global profiler instance
_global_profiler: ModelProfiler | None = None


def get_global_profiler() -> ModelProfiler:
    """Get or create the global profiler instance."""
    global _global_profiler
    if _global_profiler is None:
        _global_profiler = ModelProfiler()
    return _global_profiler


def profile_inference(model_name: str):
    """
    Convenience decorator using the global profiler.

    Usage:
        @profile_inference("impact_scorer")
        def score_message(msg):
            return model.predict(msg)
    """
    return get_global_profiler().profile(model_name)


# Type variable for generic profiling
T = TypeVar("T")


async def profile_async_call(
    model_name: str,
    func: Callable[..., T],
    *args,
    **kwargs,
) -> T:
    """
    Profile an async function call.

    Usage:
        result = await profile_async_call(
            "impact_scorer",
            model.async_predict,
            input_data,
        )
    """
    profiler = get_global_profiler()
    cpu_before = profiler._get_cpu_percent()
    memory_before = profiler._get_memory_mb()
    start_time = time.perf_counter()

    try:
        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)  # type: ignore[no-any-return]
        else:
            return func(*args, **kwargs)  # type: ignore[return-value]
    finally:
        end_time = time.perf_counter()
        cpu_during = profiler._get_cpu_percent()
        memory_after = profiler._get_memory_mb()

        metrics = InferenceMetrics(
            model_name=model_name,
            execution_time_ms=(end_time - start_time) * 1000,
            cpu_percent_before=cpu_before,
            cpu_percent_during=cpu_during,
            memory_mb_before=memory_before,
            memory_mb_after=memory_after,
        )
        profiler._record_sample(metrics)
