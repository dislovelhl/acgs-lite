# Constitutional Hash: 608508a9bd224290
# Sprint 54 -- observability/capacity_metrics/trackers.py coverage
"""
Comprehensive tests for
src/core/enhanced_agent_bus/observability/capacity_metrics/trackers.py

Targets ≥95% line and branch coverage.

Classes under test
------------------
- SlidingWindowCounter  - thread-safe sliding-window rate tracker
- LatencyTracker        - thread-safe latency tracker with percentile output
"""

import threading
import time
from unittest.mock import patch

import pytest

from enhanced_agent_bus.observability.capacity_metrics.models import (
    LatencyPercentiles,
)
from enhanced_agent_bus.observability.capacity_metrics.trackers import (
    LatencyTracker,
    SlidingWindowCounter,
)

# ---------------------------------------------------------------------------
# SlidingWindowCounter - construction
# ---------------------------------------------------------------------------


class TestSlidingWindowCounterInit:
    """Verify constructor stores attributes correctly."""

    def test_default_args(self):
        c = SlidingWindowCounter()
        assert c.window_seconds == 60
        assert c.bucket_count == 60
        assert c.bucket_duration == 1.0
        assert c._total_count == 0
        assert c._current_count == 0
        assert c._current_bucket_start == 0
        assert c._peak_rate == 0.0
        assert len(c._buckets) == 0

    def test_custom_args(self):
        c = SlidingWindowCounter(window_seconds=120, bucket_count=30)
        assert c.window_seconds == 120
        assert c.bucket_count == 30
        assert c.bucket_duration == 4.0

    def test_deque_maxlen(self):
        c = SlidingWindowCounter(window_seconds=10, bucket_count=5)
        assert c._buckets.maxlen == 5


# ---------------------------------------------------------------------------
# SlidingWindowCounter.increment
# ---------------------------------------------------------------------------


class TestSlidingWindowCounterIncrement:
    """Test increment() covers all code paths."""

    def test_increment_default_count(self):
        c = SlidingWindowCounter()
        c.increment()
        assert c._total_count == 1
        assert c._current_count == 1

    def test_increment_custom_count(self):
        c = SlidingWindowCounter()
        c.increment(5)
        assert c._total_count == 5
        assert c._current_count == 5

    def test_multiple_increments_same_bucket(self):
        """Multiple calls within one bucket duration should accumulate."""
        c = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        # Freeze time so bucket_start never changes
        frozen = 1_000_000.0  # time value
        with patch("time.time", return_value=frozen):
            c.increment(3)
            c.increment(7)
        assert c._total_count == 10
        assert c._current_count == 10

    def test_bucket_transition_flushes_old_bucket(self):
        """When bucket changes, the previous bucket is flushed to deque."""
        c = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        # bucket_duration == 1.0
        t1 = 1_000_000.0
        t2 = 1_000_001.0  # next second = new bucket
        with patch("time.time", return_value=t1):
            c.increment(3)
        # At this point _current_bucket_start is set, _current_count == 3
        with patch("time.time", return_value=t2):
            c.increment(2)
        # Old bucket (t1's) should be in _buckets, current is t2's
        assert c._total_count == 5
        assert c._current_count == 2
        assert len(c._buckets) == 1

    def test_first_increment_sets_bucket_start(self):
        """First call (bucket_start == 0) does NOT flush the empty bucket."""
        c = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        frozen = 1_000_000.0
        with patch("time.time", return_value=frozen):
            c.increment(1)
        assert len(c._buckets) == 0  # no flush because _current_bucket_start was 0

    def test_transition_from_zero_bucket_start(self):
        """
        When _current_bucket_start == 0 initially and time changes to a new
        bucket, the branch `if self._current_bucket_start > 0` must NOT append.
        """
        c = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        # First call sets bucket_start but does NOT append (start was 0)
        t1 = 1_000_000.0
        t2 = 1_000_001.5  # definitely a different bucket
        with patch("time.time", return_value=t1):
            c.increment(1)
        assert len(c._buckets) == 0
        with patch("time.time", return_value=t2):
            c.increment(1)
        # Now _current_bucket_start > 0 on second call so the old bucket IS flushed
        assert len(c._buckets) == 1

    def test_many_bucket_transitions_respects_maxlen(self):
        """deque maxlen caps the stored buckets."""
        c = SlidingWindowCounter(window_seconds=5, bucket_count=5)
        # bucket_duration == 1.0
        base = 2_000_000.0
        for i in range(10):
            with patch("time.time", return_value=base + i):
                c.increment(1)
        # maxlen is 5; older buckets are evicted
        assert len(c._buckets) <= 5

    def test_thread_safety_under_concurrent_increments(self):
        """Concurrent increments must not lose counts (thread-safety check)."""
        c = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        n_threads = 10
        increments_per_thread = 100

        def worker():
            for _ in range(increments_per_thread):
                c.increment()

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert c.get_total() == n_threads * increments_per_thread


# ---------------------------------------------------------------------------
# SlidingWindowCounter.get_rate
# ---------------------------------------------------------------------------


class TestSlidingWindowCounterGetRate:
    """Test get_rate() covers all branches."""

    def test_rate_empty(self):
        c = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        rate = c.get_rate()
        assert rate == 0.0

    def test_rate_includes_current_bucket(self):
        c = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        frozen = 1_000_000.0
        with patch("time.time", return_value=frozen):
            c.increment(60)
            rate = c.get_rate()
        assert rate == pytest.approx(1.0)

    def test_rate_includes_buckets_within_window(self):
        """Buckets within the window contribute to rate."""
        c = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        base = 2_000_000.0
        # Put 30 counts in an old bucket that is within the window
        with patch("time.time", return_value=base):
            c.increment(30)
        # Advance 10 seconds (still within 60-s window)
        with patch("time.time", return_value=base + 10):
            c.increment(30)
            rate = c.get_rate()
        # Both the old bucket (flushed at base+10) and current bucket are within window.
        # total in window = 60 over 60 s => rate = 1.0
        assert rate == pytest.approx(1.0)

    def test_rate_excludes_buckets_outside_window(self):
        """Buckets older than window_seconds are excluded from the stored deque."""
        c = SlidingWindowCounter(window_seconds=10, bucket_count=10)
        # bucket_duration == 1.0
        base = 3_000_000.0

        # Step 1: increment at base (sets _current_bucket_start, _current_count=100)
        with patch("time.time", return_value=base):
            c.increment(100)

        # Step 2: increment at base+1 -- triggers flush of the base bucket into deque;
        # now _current_count=1 (new bucket at base+1)
        with patch("time.time", return_value=base + 1):
            c.increment(1)

        # Step 3: advance 20 s -- the flushed bucket (base) is outside the 10-s window.
        # _current_count=1 (base+1 bucket) is also outside. Both the deque entry and
        # the current bucket are beyond cutoff = (base+21) - 10 = base+11.
        # However get_rate() always adds _current_count without a time check, so we
        # need _current_count to be reset.  We advance further and increment 0 to
        # trigger a bucket transition that sets _current_count=0.
        with patch("time.time", return_value=base + 25):
            # A new increment at base+25 triggers bucket transition → old bucket flushed,
            # _current_count reset to 1 (this new increment).
            c.increment(1)
            # Now manually clear _current_count to simulate calling get_rate on a
            # fresh bucket with no new events -- use an additional bucket transition.

        # Advance another bucket to flush and start fresh
        with patch("time.time", return_value=base + 26):
            c.increment(0)  # zero-count increment just triggers bucket housekeeping

        # All increments in the deque are now > 10 s old relative to base+26+10=base+36
        with patch("time.time", return_value=base + 100):
            rate = c.get_rate()

        # _current_count is 0 (last increment was 0); all deque buckets are outside window
        assert rate == pytest.approx(0.0)

    def test_peak_rate_updated(self):
        """get_rate() should update _peak_rate when current rate exceeds it."""
        c = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        frozen = 1_000_000.0
        with patch("time.time", return_value=frozen):
            c.increment(600)
            rate = c.get_rate()
        assert c._peak_rate == rate
        assert c._peak_rate > 0.0

    def test_peak_rate_not_downgraded(self):
        """_peak_rate should remain at the highest value seen."""
        c = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        t1 = 1_000_000.0
        with patch("time.time", return_value=t1):
            c.increment(600)  # high rate
            first_rate = c.get_rate()

        # Now simulate empty window - peak should be preserved
        with patch("time.time", return_value=t1 + 120):  # outside window
            c.get_rate()
        assert c._peak_rate == first_rate

    def test_thread_safety_get_rate(self):
        """Concurrent get_rate() calls must not raise."""
        c = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        c.increment(100)
        errors = []

        def reader():
            try:
                c.get_rate()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []


# ---------------------------------------------------------------------------
# SlidingWindowCounter.get_peak_rate / get_total
# ---------------------------------------------------------------------------


class TestSlidingWindowCounterAccessors:
    def test_get_peak_rate_initial(self):
        c = SlidingWindowCounter()
        assert c.get_peak_rate() == 0.0

    def test_get_peak_rate_after_increment_and_rate(self):
        c = SlidingWindowCounter(window_seconds=60, bucket_count=60)
        frozen = 1_000_000.0
        with patch("time.time", return_value=frozen):
            c.increment(120)
            c.get_rate()
        assert c.get_peak_rate() == pytest.approx(2.0)

    def test_get_total_initial(self):
        c = SlidingWindowCounter()
        assert c.get_total() == 0

    def test_get_total_after_increments(self):
        c = SlidingWindowCounter()
        c.increment(7)
        c.increment(3)
        assert c.get_total() == 10

    def test_get_total_thread_safety(self):
        c = SlidingWindowCounter()
        for _ in range(50):
            c.increment()
        assert c.get_total() == 50


# ---------------------------------------------------------------------------
# LatencyTracker - construction
# ---------------------------------------------------------------------------


class TestLatencyTrackerInit:
    def test_default_args(self):
        t = LatencyTracker()
        assert t.max_samples == 10000
        assert t.window_seconds == 60
        assert len(t._samples) == 0

    def test_custom_args(self):
        t = LatencyTracker(max_samples=500, window_seconds=30)
        assert t.max_samples == 500
        assert t.window_seconds == 30

    def test_deque_maxlen(self):
        t = LatencyTracker(max_samples=256)
        assert t._samples.maxlen == 256


# ---------------------------------------------------------------------------
# LatencyTracker.record
# ---------------------------------------------------------------------------


class TestLatencyTrackerRecord:
    def test_record_single(self):
        t = LatencyTracker()
        t.record(1.5)
        assert len(t._samples) == 1
        _, latency = t._samples[0]
        assert latency == 1.5

    def test_record_stores_timestamp(self):
        t = LatencyTracker()
        before = time.time()
        t.record(2.0)
        after = time.time()
        ts, _ = t._samples[0]
        assert before <= ts <= after

    def test_record_multiple(self):
        t = LatencyTracker()
        for v in [1.0, 2.0, 3.0]:
            t.record(v)
        assert len(t._samples) == 3

    def test_record_respects_maxlen(self):
        t = LatencyTracker(max_samples=3)
        for v in range(10):
            t.record(float(v))
        assert len(t._samples) == 3

    def test_record_thread_safety(self):
        t = LatencyTracker(max_samples=10000)
        errors = []

        def worker():
            try:
                for _ in range(50):
                    t.record(1.0)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert errors == []
        assert len(t._samples) == 500


# ---------------------------------------------------------------------------
# LatencyTracker.get_percentiles - empty window
# ---------------------------------------------------------------------------


class TestLatencyTrackerGetPercentilesEmpty:
    def test_returns_default_when_no_samples(self):
        t = LatencyTracker()
        p = t.get_percentiles()
        assert isinstance(p, LatencyPercentiles)
        assert p.p50_ms == 0.0
        assert p.p99_ms == 0.0
        assert p.sample_count == 0

    def test_returns_default_when_all_samples_expired(self):
        t = LatencyTracker(window_seconds=1)
        t.record(5.0)
        # Advance time past window
        future = time.time() + 5.0
        with patch("time.time", return_value=future):
            p = t.get_percentiles()
        assert p.sample_count == 0


# ---------------------------------------------------------------------------
# LatencyTracker.get_percentiles - single sample
# ---------------------------------------------------------------------------


class TestLatencyTrackerGetPercentilesSingleSample:
    def test_single_sample_all_percentiles_equal(self):
        t = LatencyTracker()
        frozen = 1_000_000.0
        with patch("time.time", return_value=frozen):
            t.record(4.0)
            p = t.get_percentiles()
        assert p.p50_ms == pytest.approx(4.0)
        assert p.p90_ms == pytest.approx(4.0)
        assert p.p95_ms == pytest.approx(4.0)
        assert p.p99_ms == pytest.approx(4.0)
        assert p.min_ms == pytest.approx(4.0)
        assert p.max_ms == pytest.approx(4.0)
        assert p.avg_ms == pytest.approx(4.0)
        assert p.sample_count == 1

    def test_single_sample_percentile_function_f_equals_c(self):
        """For n=1, k=0 so f==c==0, branch `if f != c` is False - covers else."""
        t = LatencyTracker()
        frozen = 1_000_000.0
        with patch("time.time", return_value=frozen):
            t.record(7.5)
            p = t.get_percentiles()
        assert p.p99_ms == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# LatencyTracker.get_percentiles - multiple samples
# ---------------------------------------------------------------------------


class TestLatencyTrackerGetPercentilesMultipleSamples:
    def _tracker_with_values(self, values):
        t = LatencyTracker(window_seconds=60)
        frozen = 1_000_000.0
        with patch("time.time", return_value=frozen):
            for v in values:
                t.record(v)
            return t, frozen

    def test_two_samples(self):
        t, frozen = self._tracker_with_values([1.0, 3.0])
        with patch("time.time", return_value=frozen):
            p = t.get_percentiles()
        assert p.min_ms == pytest.approx(1.0)
        assert p.max_ms == pytest.approx(3.0)
        assert p.avg_ms == pytest.approx(2.0)
        assert p.sample_count == 2

    def test_ten_uniform_samples(self):
        values = [float(i) for i in range(1, 11)]  # 1..10
        t, frozen = self._tracker_with_values(values)
        with patch("time.time", return_value=frozen):
            p = t.get_percentiles()
        assert p.min_ms == pytest.approx(1.0)
        assert p.max_ms == pytest.approx(10.0)
        assert p.sample_count == 10
        # P50 for 10 values (0-indexed sorted [1..10]):
        # k = 9 * 50/100 = 4.5 → f=4, c=5 → 5 + 0.5*(6-5) = 5.5
        assert p.p50_ms == pytest.approx(5.5)

    def test_percentile_interpolation_branch_f_ne_c(self):
        """Explicitly exercise the interpolation path (f != c)."""
        # 2 samples: [1.0, 9.0]  sorted
        t = LatencyTracker(window_seconds=60)
        frozen = 1_000_000.0
        with patch("time.time", return_value=frozen):
            t.record(9.0)
            t.record(1.0)
            p = t.get_percentiles()
        # n=2, P50: k = 1*50/100 = 0.5 → f=0, c=1 → 1.0 + 0.5*(9.0-1.0) = 5.0
        assert p.p50_ms == pytest.approx(5.0)

    def test_percentile_c_equals_n_minus_1_clamp(self):
        """When f+1 >= n, c is clamped to f - covers `c = f + 1 if f + 1 < n else f`."""
        # P99 with n=2: k = 1*99/100 = 0.99 → f=0, c=1 (1 < 2 so no clamp)
        # Use n=2 and P99 where c is NOT clamped; n=1 IS clamped.
        t = LatencyTracker(window_seconds=60)
        frozen = 1_000_000.0
        # Single sample forces f=c=0 (clamped)
        with patch("time.time", return_value=frozen):
            t.record(3.0)
            p = t.get_percentiles()
        assert p.p99_ms == pytest.approx(3.0)

    def test_only_recent_samples_included(self):
        """Samples older than window_seconds are excluded."""
        t = LatencyTracker(window_seconds=10)
        old_time = 1_000_000.0
        new_time = old_time + 20.0  # 20 s later, old samples expired

        with patch("time.time", return_value=old_time):
            t.record(100.0)  # will be expired

        with patch("time.time", return_value=new_time):
            t.record(1.0)  # within window
            p = t.get_percentiles()

        assert p.sample_count == 1
        assert p.p99_ms == pytest.approx(1.0)

    def test_all_samples_within_window(self):
        """All samples in window are included in calculation."""
        t = LatencyTracker(window_seconds=60)
        frozen = 1_000_000.0
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        with patch("time.time", return_value=frozen):
            for v in values:
                t.record(v)
            p = t.get_percentiles()
        assert p.sample_count == 5
        assert p.avg_ms == pytest.approx(3.0)

    def test_large_sample_set(self):
        """1000 samples: percentiles should be sensible."""
        t = LatencyTracker(max_samples=2000, window_seconds=60)
        frozen = 1_000_000.0
        with patch("time.time", return_value=frozen):
            for i in range(1, 1001):
                t.record(float(i))
            p = t.get_percentiles()
        assert p.sample_count == 1000
        assert p.min_ms == pytest.approx(1.0)
        assert p.max_ms == pytest.approx(1000.0)
        assert p.p99_ms >= 990.0  # top 1% of 1..1000

    def test_avg_ms_correct(self):
        t = LatencyTracker(window_seconds=60)
        frozen = 1_000_000.0
        with patch("time.time", return_value=frozen):
            t.record(2.0)
            t.record(4.0)
            p = t.get_percentiles()
        assert p.avg_ms == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# LatencyTracker - thread safety for get_percentiles
# ---------------------------------------------------------------------------


class TestLatencyTrackerThreadSafety:
    def test_concurrent_record_and_get_percentiles(self):
        t = LatencyTracker(max_samples=5000, window_seconds=60)
        errors = []

        def recorder():
            try:
                for _ in range(100):
                    t.record(1.0)
            except Exception as exc:
                errors.append(exc)

        def reader():
            try:
                for _ in range(20):
                    t.get_percentiles()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=recorder) for _ in range(5)] + [
            threading.Thread(target=reader) for _ in range(5)
        ]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert errors == []


# ---------------------------------------------------------------------------
# __all__ export check
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports_present(self):
        import enhanced_agent_bus.observability.capacity_metrics.trackers as mod

        assert "SlidingWindowCounter" in mod.__all__
        assert "LatencyTracker" in mod.__all__

    def test_classes_importable(self):
        from enhanced_agent_bus.observability.capacity_metrics.trackers import (
            LatencyTracker,
            SlidingWindowCounter,
        )

        assert SlidingWindowCounter is not None
        assert LatencyTracker is not None
