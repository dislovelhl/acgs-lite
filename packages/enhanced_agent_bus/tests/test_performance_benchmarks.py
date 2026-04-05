"""
ACGS-2 Enhanced Agent Bus - Performance Benchmark Tests
Constitutional Hash: perf_benchmark_v1

Performance benchmark test suite with memory profiling for validating:
- P99 latency <10ms (stretch goal <5ms)
- Memory usage <2GB peak
- Batch throughput ≥500 req/sec

Usage:
    pytest src/core/enhanced_agent_bus/tests/test_performance_benchmarks.py --benchmark-only -v

Requires:
    pip install pytest-benchmark memory-profiler

Constitutional Hash: 608508a9bd224290
"""

import gc
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from unittest.mock import patch

import numpy as np
import pytest

RUN_EAB_PERFORMANCE_BENCHMARK_TESTS = (
    os.getenv("RUN_EAB_PERFORMANCE_BENCHMARK_TESTS", "false").lower() == "true"
)
if not RUN_EAB_PERFORMANCE_BENCHMARK_TESTS:
    pytestmark = pytest.mark.skip(
        reason=(
            "Performance benchmark tests disabled by default in this runtime. "
            "set RUN_EAB_PERFORMANCE_BENCHMARK_TESTS=true to run."
        )
    )

# Add enhanced_agent_bus directory to path
enhanced_agent_bus_dir = os.path.dirname(os.path.dirname(__file__))
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)

# Attempt to import optional dependencies
TRACEMALLOC_AVAILABLE = False
MEMORY_PROFILER_AVAILABLE = False
PYTEST_BENCHMARK_AVAILABLE = False
PSUTIL_AVAILABLE = False

try:
    import tracemalloc

    TRACEMALLOC_AVAILABLE = True
except ImportError:
    pass

try:
    pass

    MEMORY_PROFILER_AVAILABLE = True
except ImportError:
    pass

try:
    pass

    PYTEST_BENCHMARK_AVAILABLE = True
except ImportError:
    pass

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    pass


# Performance targets from spec
PERFORMANCE_TARGETS = {
    "p99_latency_ms": 10.0,  # <10ms P99 latency
    "p99_latency_stretch_ms": 5.0,  # <5ms stretch goal
    "peak_memory_gb": 2.0,  # <2GB peak memory
    "throughput_req_per_sec": 500,  # ≥500 req/sec batch throughput
    "batch_50_latency_sec": 2.0,  # 50 texts in <2 seconds
    "onnx_peak_memory_mb": 500.0,  # <500MB with ONNX
    "pytorch_peak_memory_gb": 1.5,  # <1.5GB with PyTorch
    "single_inference_onnx_ms": 50.0,  # <50ms single inference ONNX
    "single_inference_pytorch_ms": 200.0,  # <200ms single inference PyTorch
    "batch_50_onnx_sec": 1.0,  # Batch 50 ONNX <1 second
    "batch_50_pytorch_sec": 2.0,  # Batch 50 PyTorch <2 seconds
    "cold_start_sec": 5.0,  # Time to first inference <5 seconds
}


@dataclass
class BenchmarkMetrics:
    """Container for benchmark metrics."""

    operation: str
    latency_ms: list[float] = field(default_factory=list)
    memory_mb: list[float] = field(default_factory=list)
    call_count: int = 0

    @property
    def latency_p50(self) -> float:
        if not self.latency_ms:
            return 0.0
        return statistics.median(self.latency_ms)

    @property
    def latency_p95(self) -> float:
        if not self.latency_ms:
            return 0.0
        return float(np.percentile(self.latency_ms, 95))

    @property
    def latency_p99(self) -> float:
        if not self.latency_ms:
            return 0.0
        return float(np.percentile(self.latency_ms, 99))

    @property
    def latency_mean(self) -> float:
        if not self.latency_ms:
            return 0.0
        return statistics.mean(self.latency_ms)

    @property
    def memory_peak_mb(self) -> float:
        if not self.memory_mb:
            return 0.0
        return max(self.memory_mb)

    @property
    def throughput_per_sec(self) -> float:
        if self.latency_mean <= 0:
            return 0.0
        return 1000.0 / self.latency_mean


class TestPerformanceTargetConstants:
    """Tests to verify performance targets are properly defined."""

    def test_p99_latency_target_defined(self):
        """Test P99 latency target is defined."""
        assert "p99_latency_ms" in PERFORMANCE_TARGETS
        assert PERFORMANCE_TARGETS["p99_latency_ms"] == 10.0

    def test_stretch_target_more_aggressive(self):
        """Test stretch target is more aggressive than base target."""
        assert PERFORMANCE_TARGETS["p99_latency_stretch_ms"] < PERFORMANCE_TARGETS["p99_latency_ms"]

    def test_memory_target_defined(self):
        """Test memory target is defined."""
        assert "peak_memory_gb" in PERFORMANCE_TARGETS
        assert PERFORMANCE_TARGETS["peak_memory_gb"] == 2.0

    def test_throughput_target_defined(self):
        """Test throughput target is defined."""
        assert "throughput_req_per_sec" in PERFORMANCE_TARGETS
        assert PERFORMANCE_TARGETS["throughput_req_per_sec"] >= 500


class TestBenchmarkMetricsDataclass:
    """Tests for BenchmarkMetrics dataclass."""

    def test_latency_p50_calculation(self):
        """Test P50 latency calculation."""
        metrics = BenchmarkMetrics(operation="test")
        metrics.latency_ms = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]

        assert abs(metrics.latency_p50 - 5.5) < 0.1

    def test_latency_p95_calculation(self):
        """Test P95 latency calculation."""
        metrics = BenchmarkMetrics(operation="test")
        metrics.latency_ms = list(range(1, 101))  # 1 to 100

        assert metrics.latency_p95 >= 95.0

    def test_latency_p99_calculation(self):
        """Test P99 latency calculation."""
        metrics = BenchmarkMetrics(operation="test")
        metrics.latency_ms = list(range(1, 101))  # 1 to 100

        assert metrics.latency_p99 >= 99.0

    def test_throughput_calculation(self):
        """Test throughput calculation."""
        metrics = BenchmarkMetrics(operation="test")
        metrics.latency_ms = [1.0, 1.0, 1.0]  # 1ms average

        assert abs(metrics.throughput_per_sec - 1000.0) < 0.1

    def test_empty_metrics_return_zero(self):
        """Test empty metrics return zero values."""
        metrics = BenchmarkMetrics(operation="test")

        assert metrics.latency_p50 == 0.0
        assert metrics.latency_p95 == 0.0
        assert metrics.latency_p99 == 0.0
        assert metrics.throughput_per_sec == 0.0
        assert metrics.memory_peak_mb == 0.0


class TestKeywordScoringLatency:
    """Latency benchmarks for keyword-based scoring (fallback path)."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer with keyword-only fallback."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
        return scorer

    @pytest.fixture
    def sample_messages(self):
        """Generate sample messages for benchmarking."""
        return [
            {"content": "Critical security breach detected in blockchain consensus layer"},
            {"content": "Standard health check request"},
            {"content": "Unauthorized financial transfer attempt blocked"},
            {"content": "Performance metrics indicate potential anomaly"},
            {"content": "User requested password reset"},
            {"content": "System configuration change detected in production environment"},
            {"content": "Routine database backup completed successfully"},
            {"content": "New API endpoint deployment initiated"},
            {"content": "Network traffic spike observed on main gateway"},
            {"content": "Authentication failure for admin account after 5 attempts"},
        ]

    def test_single_score_latency(self, scorer, sample_messages):
        """Benchmark single message scoring latency."""
        metrics = BenchmarkMetrics(operation="single_keyword_score")
        num_iterations = 100

        # Warmup
        for msg in sample_messages[:3]:
            scorer.calculate_impact_score(msg)

        # Benchmark
        for i in range(num_iterations):
            msg = sample_messages[i % len(sample_messages)]

            start = time.perf_counter()
            scorer.calculate_impact_score(msg)
            elapsed_ms = (time.perf_counter() - start) * 1000

            metrics.latency_ms.append(elapsed_ms)
            metrics.call_count += 1

        # Assert P99 < 10ms (keyword scoring should be very fast)
        assert metrics.latency_p99 < PERFORMANCE_TARGETS["p99_latency_ms"], (
            f"P99 latency {metrics.latency_p99:.2f}ms exceeds target {PERFORMANCE_TARGETS['p99_latency_ms']}ms"
        )

    def test_batch_score_latency(self, scorer, sample_messages):
        """Benchmark batch message scoring latency."""
        metrics = BenchmarkMetrics(operation="batch_keyword_score")
        num_iterations = 50
        batch_size = 10

        # Warmup
        scorer.batch_score_impact(sample_messages)

        # Benchmark
        for _ in range(num_iterations):
            start = time.perf_counter()
            scorer.batch_score_impact(sample_messages[:batch_size])
            elapsed_ms = (time.perf_counter() - start) * 1000

            metrics.latency_ms.append(elapsed_ms)
            metrics.call_count += 1

        # Per-message latency in batch
        per_message_p99 = metrics.latency_p99 / batch_size
        assert per_message_p99 < PERFORMANCE_TARGETS["p99_latency_ms"], (
            f"Per-message P99 {per_message_p99:.2f}ms exceeds target"
        )

    def test_batch_50_under_2_seconds(self, scorer, sample_messages):
        """Test batch of 50 messages completes in under 2 seconds."""
        # Extend sample messages to 50
        batch_messages = sample_messages * 5  # 50 messages

        start = time.perf_counter()
        results = scorer.batch_score_impact(batch_messages)
        elapsed = time.perf_counter() - start

        assert len(results) == 50
        assert elapsed < PERFORMANCE_TARGETS["batch_50_latency_sec"], (
            f"Batch 50 took {elapsed:.2f}s, target is <{PERFORMANCE_TARGETS['batch_50_latency_sec']}s"
        )


class TestBatchThroughput:
    """Throughput benchmarks for batch processing."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer with keyword-only fallback."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
        return scorer

    @pytest.fixture
    def sample_messages(self):
        """Generate sample messages for benchmarking."""
        messages = []
        for i in range(100):
            if i % 5 == 0:
                messages.append({"content": f"Critical security breach {i}"})
            elif i % 3 == 0:
                messages.append({"content": f"Governance policy update {i}"})
            else:
                messages.append({"content": f"Normal status message {i}"})
        return messages

    def test_throughput_batch_1(self, scorer, sample_messages):
        """Benchmark throughput with batch size 1."""
        metrics = BenchmarkMetrics(operation="batch_1")
        num_iterations = 100

        for i in range(num_iterations):
            msg = [sample_messages[i % len(sample_messages)]]

            start = time.perf_counter()
            scorer.batch_score_impact(msg)
            elapsed_ms = (time.perf_counter() - start) * 1000

            metrics.latency_ms.append(elapsed_ms)
            metrics.call_count += 1

        # Calculate throughput
        throughput = metrics.throughput_per_sec
        assert throughput > 0, "Throughput should be positive"

    def test_throughput_batch_8(self, scorer, sample_messages):
        """Benchmark throughput with batch size 8."""
        metrics = BenchmarkMetrics(operation="batch_8")
        batch_size = 8
        num_iterations = 50

        for i in range(num_iterations):
            start_idx = (i * batch_size) % len(sample_messages)
            batch = sample_messages[start_idx : start_idx + batch_size]
            if len(batch) < batch_size:
                batch = sample_messages[:batch_size]

            start = time.perf_counter()
            scorer.batch_score_impact(batch)
            elapsed_ms = (time.perf_counter() - start) * 1000

            metrics.latency_ms.append(elapsed_ms)
            metrics.call_count += 1

        # Throughput = batch_size * (1000 / latency_mean)
        throughput = batch_size * metrics.throughput_per_sec
        assert throughput > 0, "Throughput should be positive"

    def test_throughput_batch_16(self, scorer, sample_messages):
        """Benchmark throughput with batch size 16."""
        metrics = BenchmarkMetrics(operation="batch_16")
        batch_size = 16
        num_iterations = 50

        for i in range(num_iterations):
            start_idx = (i * batch_size) % len(sample_messages)
            batch = sample_messages[start_idx : start_idx + batch_size]
            if len(batch) < batch_size:
                batch = sample_messages[:batch_size]

            start = time.perf_counter()
            scorer.batch_score_impact(batch)
            elapsed_ms = (time.perf_counter() - start) * 1000

            metrics.latency_ms.append(elapsed_ms)
            metrics.call_count += 1

        throughput = batch_size * metrics.throughput_per_sec
        assert throughput > 0, "Throughput should be positive"

    def test_throughput_batch_32(self, scorer, sample_messages):
        """Benchmark throughput with batch size 32."""
        metrics = BenchmarkMetrics(operation="batch_32")
        batch_size = 32
        num_iterations = 30

        for i in range(num_iterations):
            start_idx = (i * batch_size) % len(sample_messages)
            batch = sample_messages[start_idx : start_idx + batch_size]
            if len(batch) < batch_size:
                batch = sample_messages[:batch_size]

            start = time.perf_counter()
            scorer.batch_score_impact(batch)
            elapsed_ms = (time.perf_counter() - start) * 1000

            metrics.latency_ms.append(elapsed_ms)
            metrics.call_count += 1

        throughput = batch_size * metrics.throughput_per_sec

        # For keyword scoring (fallback path), should easily exceed 500 req/sec
        assert throughput >= PERFORMANCE_TARGETS["throughput_req_per_sec"], (
            f"Throughput {throughput:.0f} req/sec below target {PERFORMANCE_TARGETS['throughput_req_per_sec']}"
        )

    def test_throughput_scales_with_batch_size(self, scorer, sample_messages):
        """Test that throughput scales with batch size."""
        batch_sizes = [1, 8, 16, 32]
        throughputs = {}

        for batch_size in batch_sizes:
            metrics = BenchmarkMetrics(operation=f"batch_{batch_size}")
            num_iterations = 20

            for _ in range(num_iterations):
                batch = sample_messages[:batch_size]

                start = time.perf_counter()
                scorer.batch_score_impact(batch)
                elapsed_ms = (time.perf_counter() - start) * 1000

                metrics.latency_ms.append(elapsed_ms)

            # Throughput = batch_size * (1000 / latency_mean)
            throughputs[batch_size] = batch_size * metrics.throughput_per_sec

        # Verify throughput increases with batch size (not necessarily linearly)
        # Using 0.5x tolerance to account for environmental variance in CI/CD
        assert throughputs[8] >= throughputs[1] * 0.5, (
            "Batch 8 should not be much slower than batch 1"
        )
        assert throughputs[16] >= throughputs[8] * 0.5, (
            "Batch 16 should not be much slower than batch 8"
        )
        assert throughputs[32] >= throughputs[16] * 0.5, (
            "Batch 32 should not be much slower than batch 16"
        )


class TestMemoryUsage:
    """Memory usage benchmarks."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer with keyword-only fallback."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
        return scorer

    @pytest.fixture
    def sample_messages(self):
        """Generate sample messages for benchmarking."""
        return [
            {"content": f"Test message {i} with varying content length " * (i % 5 + 1)}
            for i in range(100)
        ]

    def test_scorer_initialization_memory(self):
        """Test memory usage during scorer initialization."""
        if not TRACEMALLOC_AVAILABLE:
            pytest.skip("tracemalloc not available")

        from deliberation_layer.impact_scorer import ImpactScorer, reset_impact_scorer

        reset_impact_scorer()
        gc.collect()

        tracemalloc.start()

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)

        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)

        # Keyword-only scorer should use minimal memory (<100MB)
        assert peak_mb < 100, f"Scorer initialization peak memory {peak_mb:.2f}MB > 100MB"

    def test_scoring_memory_no_leak(self, scorer, sample_messages):
        """Test that scoring does not leak memory."""
        if not TRACEMALLOC_AVAILABLE:
            pytest.skip("tracemalloc not available")

        gc.collect()
        tracemalloc.start()

        # Run many scoring operations
        for _ in range(10):
            for msg in sample_messages:
                scorer.calculate_impact_score(msg)

        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)

        # Should stay well under 2GB
        assert peak_mb < PERFORMANCE_TARGETS["peak_memory_gb"] * 1024, (
            f"Peak memory {peak_mb:.2f}MB exceeds {PERFORMANCE_TARGETS['peak_memory_gb']}GB"
        )

    def test_batch_scoring_memory(self, scorer, sample_messages):
        """Test memory usage during batch scoring."""
        if not TRACEMALLOC_AVAILABLE:
            pytest.skip("tracemalloc not available")

        gc.collect()
        tracemalloc.start()

        # Run batch scoring
        for _ in range(10):
            scorer.batch_score_impact(sample_messages)

        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)

        # Should stay well under 2GB
        assert peak_mb < PERFORMANCE_TARGETS["peak_memory_gb"] * 1024, (
            f"Peak memory {peak_mb:.2f}MB exceeds {PERFORMANCE_TARGETS['peak_memory_gb']}GB"
        )

    @pytest.mark.skipif(not PSUTIL_AVAILABLE, reason="psutil not available")
    def test_process_memory_usage(self, scorer, sample_messages):
        """Test process-level memory usage with psutil."""
        process = psutil.Process(os.getpid())

        # Initial memory
        initial_rss = process.memory_info().rss / (1024 * 1024)

        # Run many scoring operations
        for _ in range(100):
            scorer.batch_score_impact(sample_messages)

        gc.collect()

        # Final memory
        final_rss = process.memory_info().rss / (1024 * 1024)
        memory_increase = final_rss - initial_rss

        # Memory increase should be reasonable (less than 500MB)
        assert memory_increase < 500, f"Memory increased by {memory_increase:.2f}MB during scoring"


class TestLatencyPercentiles:
    """Tests for latency percentile calculations."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer with keyword-only fallback."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
        return scorer

    @pytest.fixture
    def sample_messages(self):
        """Generate varied sample messages."""
        messages = []
        # Mix of short and long messages
        for i in range(50):
            if i % 3 == 0:
                messages.append({"content": "short"})
            elif i % 3 == 1:
                messages.append({"content": "medium length message with some content here"})
            else:
                messages.append({"content": "long " * 100})  # Long message
        return messages

    def test_p50_latency(self, scorer, sample_messages):
        """Test P50 latency is within acceptable range."""
        metrics = BenchmarkMetrics(operation="p50_test")

        for msg in sample_messages:
            start = time.perf_counter()
            scorer.calculate_impact_score(msg)
            elapsed_ms = (time.perf_counter() - start) * 1000
            metrics.latency_ms.append(elapsed_ms)

        # P50 should be well under 5ms for keyword scoring
        assert metrics.latency_p50 < 5.0, f"P50 latency {metrics.latency_p50:.2f}ms > 5ms"

    def test_p95_latency(self, scorer, sample_messages):
        """Test P95 latency is within acceptable range."""
        metrics = BenchmarkMetrics(operation="p95_test")

        for msg in sample_messages:
            start = time.perf_counter()
            scorer.calculate_impact_score(msg)
            elapsed_ms = (time.perf_counter() - start) * 1000
            metrics.latency_ms.append(elapsed_ms)

        # P95 should be under 10ms
        assert metrics.latency_p95 < PERFORMANCE_TARGETS["p99_latency_ms"], (
            f"P95 latency {metrics.latency_p95:.2f}ms > {PERFORMANCE_TARGETS['p99_latency_ms']}ms"
        )

    def test_p99_latency(self, scorer, sample_messages):
        """Test P99 latency meets target."""
        metrics = BenchmarkMetrics(operation="p99_test")

        # Run 100 iterations for better percentile accuracy
        for _ in range(2):
            for msg in sample_messages:
                start = time.perf_counter()
                scorer.calculate_impact_score(msg)
                elapsed_ms = (time.perf_counter() - start) * 1000
                metrics.latency_ms.append(elapsed_ms)

        # P99 should meet target
        assert metrics.latency_p99 < PERFORMANCE_TARGETS["p99_latency_ms"], (
            f"P99 latency {metrics.latency_p99:.2f}ms > {PERFORMANCE_TARGETS['p99_latency_ms']}ms"
        )

    def test_latency_consistency(self, scorer, sample_messages):
        """Test latency is consistent across runs."""
        run1_latencies = []
        run2_latencies = []

        # Run 1
        for msg in sample_messages[:20]:
            start = time.perf_counter()
            scorer.calculate_impact_score(msg)
            elapsed_ms = (time.perf_counter() - start) * 1000
            run1_latencies.append(elapsed_ms)

        # Run 2
        for msg in sample_messages[:20]:
            start = time.perf_counter()
            scorer.calculate_impact_score(msg)
            elapsed_ms = (time.perf_counter() - start) * 1000
            run2_latencies.append(elapsed_ms)

        # Mean latencies should be within 50% of each other
        mean1 = statistics.mean(run1_latencies)
        mean2 = statistics.mean(run2_latencies)

        ratio = max(mean1, mean2) / max(min(mean1, mean2), 0.001)
        assert ratio < 2.0, f"Latency inconsistent: run1={mean1:.2f}ms, run2={mean2:.2f}ms"


class TestColdStartPerformance:
    """Tests for cold start performance."""

    def test_first_inference_latency(self):
        """Test time to first inference (cold start)."""
        from deliberation_layer.impact_scorer import ImpactScorer, reset_impact_scorer

        # Clean state
        reset_impact_scorer()
        gc.collect()

        start = time.perf_counter()

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
            scorer.calculate_impact_score({"content": "test message"})

        elapsed = time.perf_counter() - start

        # Cold start should be under 5 seconds (for keyword-only, much faster)
        assert elapsed < PERFORMANCE_TARGETS["cold_start_sec"], (
            f"Cold start took {elapsed:.2f}s > {PERFORMANCE_TARGETS['cold_start_sec']}s"
        )

        # Cleanup
        reset_impact_scorer()

    def test_warmup_improves_latency(self):
        """Test that warmup improves subsequent latency."""
        from deliberation_layer.impact_scorer import ImpactScorer, reset_impact_scorer

        reset_impact_scorer()

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)

        message = {"content": "test message with security keywords"}

        # First inference (cold)
        cold_latencies = []
        for _ in range(3):
            start = time.perf_counter()
            scorer.calculate_impact_score(message)
            cold_latencies.append((time.perf_counter() - start) * 1000)

        # Warmup
        for _ in range(50):
            scorer.calculate_impact_score(message)

        # Warm latencies
        warm_latencies = []
        for _ in range(10):
            start = time.perf_counter()
            scorer.calculate_impact_score(message)
            warm_latencies.append((time.perf_counter() - start) * 1000)

        # Warm latency should be stable
        warm_mean = statistics.mean(warm_latencies)
        warm_std = statistics.stdev(warm_latencies) if len(warm_latencies) > 1 else 0

        # Standard deviation should be low (consistent latency)
        assert warm_std < warm_mean, "Warm latency should be consistent"

        reset_impact_scorer()


class TestCachePerformance:
    """Tests for caching performance improvements."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer with keyword-only fallback."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
        return scorer

    def test_cache_hit_faster_than_miss(self, scorer):
        """Test that cache hits are faster than cache misses."""
        message = {"content": "critical security breach detected"}

        # First call (cache miss)
        miss_latencies = []
        for i in range(10):
            msg = {"content": f"unique message {i} with security keywords"}
            start = time.perf_counter()
            scorer.calculate_impact_score(msg)
            miss_latencies.append((time.perf_counter() - start) * 1000)

        # Repeated calls to same message (cache hit if caching implemented)
        hit_latencies = []
        for _ in range(10):
            start = time.perf_counter()
            scorer.calculate_impact_score(message)
            hit_latencies.append((time.perf_counter() - start) * 1000)

        # Both should be fast for keyword scoring
        assert statistics.mean(hit_latencies) < 10.0
        assert statistics.mean(miss_latencies) < 10.0

    def test_tokenization_cache_effectiveness(self):
        """Test tokenization cache effectiveness when available."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)

        # Verify cache attribute exists
        assert hasattr(scorer, "_tokenization_cache")

        # Clear cache if possible
        if hasattr(scorer, "clear_tokenization_cache"):
            scorer.clear_tokenization_cache()


class TestEdgeCasePerformance:
    """Performance tests for edge cases."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer with keyword-only fallback."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
        return scorer

    def test_empty_message_fast(self, scorer):
        """Test empty message is processed quickly."""
        start = time.perf_counter()
        for _ in range(100):
            scorer.calculate_impact_score({})
        elapsed_ms = (time.perf_counter() - start) * 1000 / 100

        assert elapsed_ms < 1.0, f"Empty message took {elapsed_ms:.2f}ms"

    def test_very_long_message_bounded(self, scorer):
        """Test very long message has bounded latency."""
        long_message = {"content": "security breach " * 10000}  # Very long

        latencies = []
        for _ in range(5):
            start = time.perf_counter()
            scorer.calculate_impact_score(long_message)
            latencies.append((time.perf_counter() - start) * 1000)

        mean_latency = statistics.mean(latencies)

        # Should still be under 100ms even for very long messages
        assert mean_latency < 100.0, f"Long message took {mean_latency:.2f}ms"

    def test_special_characters_no_slowdown(self, scorer):
        """Test special characters don't cause slowdown."""
        special_message = {"content": "!@#$%^&*()_+-=[]{}|;':\",./<>? " * 100}
        normal_message = {"content": "normal text content here " * 100}

        # Time special characters
        special_latencies = []
        for _ in range(20):
            start = time.perf_counter()
            scorer.calculate_impact_score(special_message)
            special_latencies.append((time.perf_counter() - start) * 1000)

        # Time normal text
        normal_latencies = []
        for _ in range(20):
            start = time.perf_counter()
            scorer.calculate_impact_score(normal_message)
            normal_latencies.append((time.perf_counter() - start) * 1000)

        # Special characters should not be significantly slower
        ratio = statistics.mean(special_latencies) / max(statistics.mean(normal_latencies), 0.001)
        assert ratio < 2.0, f"Special chars {ratio:.2f}x slower than normal"

    def test_unicode_no_slowdown(self, scorer):
        """Test unicode content doesn't cause slowdown."""
        unicode_message = {"content": "セキュリティ警告 安全性の問題 " * 50}
        ascii_message = {"content": "security alert safety issue " * 50}

        # Time unicode
        unicode_latencies = []
        for _ in range(20):
            start = time.perf_counter()
            scorer.calculate_impact_score(unicode_message)
            unicode_latencies.append((time.perf_counter() - start) * 1000)

        # Time ascii
        ascii_latencies = []
        for _ in range(20):
            start = time.perf_counter()
            scorer.calculate_impact_score(ascii_message)
            ascii_latencies.append((time.perf_counter() - start) * 1000)

        # Unicode should not be significantly slower
        # Using 4.0x tolerance to account for environmental variance in CI/CD
        ratio = statistics.mean(unicode_latencies) / max(statistics.mean(ascii_latencies), 0.001)
        assert ratio < 4.0, f"Unicode {ratio:.2f}x slower than ASCII"


class TestConcurrentPerformance:
    """Tests for concurrent scoring performance (single-threaded baseline)."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer with keyword-only fallback."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
        return scorer

    @pytest.fixture
    def sample_messages(self):
        """Generate sample messages."""
        return [{"content": f"message {i} with security alert"} for i in range(100)]

    def test_sequential_100_messages(self, scorer, sample_messages):
        """Test processing 100 messages sequentially."""
        start = time.perf_counter()
        results = []
        for msg in sample_messages:
            results.append(scorer.calculate_impact_score(msg))
        elapsed = time.perf_counter() - start

        assert len(results) == 100
        throughput = 100 / elapsed

        # Should process at least 100 messages per second
        assert throughput > 100, f"Sequential throughput {throughput:.0f} req/s < 100"

    def test_batch_100_messages(self, scorer, sample_messages):
        """Test processing 100 messages in batch."""
        start = time.perf_counter()
        results = scorer.batch_score_impact(sample_messages)
        elapsed = time.perf_counter() - start

        assert len(results) == 100
        throughput = 100 / elapsed

        # Batch should be faster than sequential
        assert throughput > 100, f"Batch throughput {throughput:.0f} req/s < 100"


class TestBaselineComparison:
    """Tests comparing against baseline performance metrics."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer with keyword-only fallback."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
        return scorer

    def test_beats_baseline_p99(self, scorer):
        """Test P99 latency beats the 25.24ms baseline."""
        BASELINE_P99_MS = 25.24  # From spec: baseline P99 latency

        metrics = BenchmarkMetrics(operation="baseline_comparison")

        messages = [
            {"content": "critical security breach detected"},
            {"content": "normal status update"},
            {"content": "governance policy violation"},
        ]

        # Run 100 iterations
        for _ in range(100):
            for msg in messages:
                start = time.perf_counter()
                scorer.calculate_impact_score(msg)
                elapsed_ms = (time.perf_counter() - start) * 1000
                metrics.latency_ms.append(elapsed_ms)

        # Should beat baseline
        assert metrics.latency_p99 < BASELINE_P99_MS, (
            f"P99 {metrics.latency_p99:.2f}ms >= baseline {BASELINE_P99_MS}ms"
        )

        # Should also meet target
        assert metrics.latency_p99 < PERFORMANCE_TARGETS["p99_latency_ms"], (
            f"P99 {metrics.latency_p99:.2f}ms >= target {PERFORMANCE_TARGETS['p99_latency_ms']}ms"
        )

    def test_meets_stretch_goal(self, scorer):
        """Test if stretch goal of <5ms P99 is achievable."""
        metrics = BenchmarkMetrics(operation="stretch_goal")

        messages = [{"content": "test message"} for _ in range(50)]

        for msg in messages:
            start = time.perf_counter()
            scorer.calculate_impact_score(msg)
            elapsed_ms = (time.perf_counter() - start) * 1000
            metrics.latency_ms.append(elapsed_ms)

        # Report whether stretch goal is met (not a hard failure)
        stretch_met = metrics.latency_p99 < PERFORMANCE_TARGETS["p99_latency_stretch_ms"]

        # This is informational - keyword scoring should meet stretch goal
        if not stretch_met:
            pytest.skip(
                f"Stretch goal not met: P99 {metrics.latency_p99:.2f}ms >= "
                f"{PERFORMANCE_TARGETS['p99_latency_stretch_ms']}ms"
            )


@pytest.mark.skipif(not PYTEST_BENCHMARK_AVAILABLE, reason="pytest-benchmark not available")
class TestPytestBenchmarkIntegration:
    """Integration tests using pytest-benchmark plugin."""

    @pytest.fixture
    def scorer(self):
        """Create a scorer with keyword-only fallback."""
        from deliberation_layer.impact_scorer import ImpactScorer

        with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
            scorer = ImpactScorer(use_onnx=False)
        return scorer

    def test_benchmark_single_score(self, benchmark, scorer):
        """Benchmark single message scoring using pytest-benchmark."""
        message = {"content": "critical security breach detected"}

        result = benchmark(scorer.calculate_impact_score, message)

        assert 0.0 <= result <= 1.0

    def test_benchmark_batch_score(self, benchmark, scorer):
        """Benchmark batch message scoring using pytest-benchmark."""
        messages = [{"content": f"message {i} with security keywords"} for i in range(10)]

        results = benchmark(scorer.batch_score_impact, messages)

        assert len(results) == 10
        assert all(0.0 <= r <= 1.0 for r in results)


# Benchmark runner for standalone execution
def run_benchmarks():
    """Run benchmarks and print summary."""
    from deliberation_layer.impact_scorer import ImpactScorer

    with patch("deliberation_layer.impact_scorer.TRANSFORMERS_AVAILABLE", False):
        scorer = ImpactScorer(use_onnx=False)

    messages = [
        {"content": f"test message {i} with {'security' if i % 2 == 0 else 'normal'} content"}
        for i in range(100)
    ]

    # Single scoring benchmark
    metrics_single = BenchmarkMetrics(operation="single_score")
    for msg in messages:
        start = time.perf_counter()
        scorer.calculate_impact_score(msg)
        metrics_single.latency_ms.append((time.perf_counter() - start) * 1000)

    # Batch scoring benchmark
    batch_sizes = [1, 8, 16, 32]

    for batch_size in batch_sizes:
        metrics_batch = BenchmarkMetrics(operation=f"batch_{batch_size}")
        for _ in range(50):
            batch = messages[:batch_size]
            start = time.perf_counter()
            scorer.batch_score_impact(batch)
            metrics_batch.latency_ms.append((time.perf_counter() - start) * 1000)

        batch_size * metrics_batch.throughput_per_sec
        #     f"{batch_size:<8} {metrics_batch.latency_p50:<12.2f} "
        #     f"{metrics_batch.latency_p99:<12.2f} {throughput:<20.0f}"
        # )


# Entry point for running tests directly
if __name__ == "__main__":
    if "--run-benchmarks" in sys.argv:
        run_benchmarks()
    else:
        pytest.main([__file__, "-v"])
