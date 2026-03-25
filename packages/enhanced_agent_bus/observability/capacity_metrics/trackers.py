"""
ACGS-2 Capacity Metrics Trackers
Constitutional Hash: 608508a9bd224290

Contains tracking utilities for capacity metrics:
- SlidingWindowCounter: Thread-safe sliding window counter for rate calculations
- LatencyTracker: Thread-safe latency tracker with percentile calculations

These classes maintain sliding windows of data points for accurate
rate and percentile calculations over configurable time windows.

This module is part of the capacity_metrics refactoring to improve maintainability
by splitting the original 1478-line file into focused, cohesive modules.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock

from .models import LatencyPercentiles


class SlidingWindowCounter:
    """
    Thread-safe sliding window counter for rate calculations.

    Maintains a sliding window of timestamps to calculate accurate rates.
    Uses bucket-based aggregation for memory efficiency.

    Args:
        window_seconds: Size of the sliding window in seconds
        bucket_count: Number of buckets to divide the window into

    Example:
        >>> counter = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        >>> counter.increment()
        >>> counter.increment(5)
        >>> rate = counter.get_rate()  # requests per second
    """

    def __init__(self, window_seconds: int = 60, bucket_count: int = 60):
        self.window_seconds = window_seconds
        self.bucket_count = bucket_count
        self.bucket_duration = window_seconds / bucket_count
        self._buckets: deque[tuple[float, int]] = deque(maxlen=bucket_count)
        self._current_bucket_start: float = 0
        self._current_count: int = 0
        self._total_count: int = 0
        self._peak_rate: float = 0.0
        self._lock = Lock()

    def increment(self, count: int = 1) -> None:
        """
        Increment the counter.

        Args:
            count: Amount to increment by (default 1)
        """
        now = time.time()
        with self._lock:
            self._total_count += count
            bucket_start = now - (now % self.bucket_duration)

            if self._current_bucket_start != bucket_start:
                if self._current_bucket_start > 0:
                    self._buckets.append((self._current_bucket_start, self._current_count))
                self._current_bucket_start = bucket_start
                self._current_count = 0

            self._current_count += count

    def get_rate(self) -> float:
        """
        Get the current rate (per second) over the window.

        Returns:
            Current rate in operations per second
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            total = self._current_count
            for bucket_time, bucket_count in self._buckets:
                if bucket_time >= cutoff:
                    total += bucket_count

            rate = total / self.window_seconds
            if rate > self._peak_rate:
                self._peak_rate = rate
            return rate

    def get_peak_rate(self) -> float:
        """
        Get the peak rate observed.

        Returns:
            Peak rate in operations per second
        """
        with self._lock:
            return self._peak_rate

    def get_total(self) -> int:
        """
        Get the total count since creation.

        Returns:
            Total count
        """
        with self._lock:
            return self._total_count


class LatencyTracker:
    """
    Thread-safe latency tracker with percentile calculations.

    Maintains a sliding window of latency samples for percentile calculations.
    Automatically evicts old samples outside the time window.

    Args:
        max_samples: Maximum number of samples to retain
        window_seconds: Time window for percentile calculations

    Example:
        >>> tracker = LatencyTracker(max_samples=10000, window_seconds=60)
        >>> tracker.record(1.5)  # 1.5ms latency
        >>> tracker.record(2.3)
        >>> percentiles = tracker.get_percentiles()
        >>> print(f"P99: {percentiles.p99_ms}ms")
    """

    def __init__(self, max_samples: int = 10000, window_seconds: int = 60):
        self.max_samples = max_samples
        self.window_seconds = window_seconds
        self._samples: deque[tuple[float, float]] = deque(maxlen=max_samples)
        self._lock = Lock()

    def record(self, latency_ms: float) -> None:
        """
        Record a latency sample.

        Args:
            latency_ms: Latency value in milliseconds
        """
        now = time.time()
        with self._lock:
            self._samples.append((now, latency_ms))

    def get_percentiles(self) -> LatencyPercentiles:
        """
        Calculate percentiles from recent samples.

        Returns:
            LatencyPercentiles containing P50, P90, P95, P99, min, max, and avg
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            recent = [lat for ts, lat in self._samples if ts >= cutoff]

        if not recent:
            return LatencyPercentiles()

        recent.sort()
        n = len(recent)

        def percentile(p: float) -> float:
            k = (n - 1) * p / 100
            f = int(k)
            c = f + 1 if f + 1 < n else f
            return recent[f] + (k - f) * (recent[c] - recent[f]) if f != c else recent[f]

        return LatencyPercentiles(
            p50_ms=percentile(50),
            p90_ms=percentile(90),
            p95_ms=percentile(95),
            p99_ms=percentile(99),
            max_ms=max(recent),
            min_ms=min(recent),
            avg_ms=sum(recent) / n,
            sample_count=n,
        )


__all__ = [
    "LatencyTracker",
    "SlidingWindowCounter",
]
