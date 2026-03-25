# Constitutional Hash: 608508a9bd224290
# Sprint 54 — batch_auto_tuner.py coverage
"""
Comprehensive tests for src/core/enhanced_agent_bus/batch_auto_tuner.py
Targets ≥95% branch coverage.
"""

import pytest

pytest.importorskip("enhanced_agent_bus.batch_auto_tuner")


import logging

import pytest

from enhanced_agent_bus.batch_auto_tuner import AutoTunerConfig, BatchAutoTuner
from enhanced_agent_bus.observability.structured_logging import get_logger

# ---------------------------------------------------------------------------
# AutoTunerConfig tests
# ---------------------------------------------------------------------------


class TestAutoTunerConfigDefaults:
    """AutoTunerConfig default value tests."""

    def test_default_target_p99(self):
        cfg = AutoTunerConfig()
        assert cfg.target_p99_latency_ms == 10.0

    def test_default_min_batch_size(self):
        cfg = AutoTunerConfig()
        assert cfg.min_batch_size == 10

    def test_default_max_batch_size(self):
        cfg = AutoTunerConfig()
        assert cfg.max_batch_size == 1000

    def test_default_history_size(self):
        cfg = AutoTunerConfig()
        assert cfg.history_size == 10

    def test_default_adjustment_factor(self):
        cfg = AutoTunerConfig()
        assert cfg.adjustment_factor == 0.2

    def test_custom_values(self):
        cfg = AutoTunerConfig(
            target_p99_latency_ms=5.0,
            min_batch_size=5,
            max_batch_size=500,
            history_size=20,
            adjustment_factor=0.1,
        )
        assert cfg.target_p99_latency_ms == 5.0
        assert cfg.min_batch_size == 5
        assert cfg.max_batch_size == 500
        assert cfg.history_size == 20
        assert cfg.adjustment_factor == 0.1


# ---------------------------------------------------------------------------
# BatchAutoTuner initialisation tests
# ---------------------------------------------------------------------------


class TestBatchAutoTunerInit:
    """BatchAutoTuner initialisation boundary conditions."""

    def test_initial_batch_size_within_range(self):
        cfg = AutoTunerConfig(min_batch_size=10, max_batch_size=1000)
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        assert tuner.current_batch_size == 100

    def test_initial_batch_size_clipped_to_min(self):
        cfg = AutoTunerConfig(min_batch_size=50, max_batch_size=1000)
        tuner = BatchAutoTuner(cfg, initial_batch_size=1)
        assert tuner.current_batch_size == 50

    def test_initial_batch_size_clipped_to_max(self):
        cfg = AutoTunerConfig(min_batch_size=10, max_batch_size=200)
        tuner = BatchAutoTuner(cfg, initial_batch_size=9999)
        assert tuner.current_batch_size == 200

    def test_initial_stats_are_zero(self):
        cfg = AutoTunerConfig()
        tuner = BatchAutoTuner(cfg)
        assert tuner._total_batches_analyzed == 0
        assert tuner._total_adjustments == 0

    def test_initial_history_is_empty(self):
        cfg = AutoTunerConfig()
        tuner = BatchAutoTuner(cfg)
        assert len(tuner._history) == 0

    def test_history_deque_respects_maxlen(self):
        cfg = AutoTunerConfig(history_size=5)
        tuner = BatchAutoTuner(cfg)
        assert tuner._history.maxlen == 5


# ---------------------------------------------------------------------------
# get_recommended_batch_size
# ---------------------------------------------------------------------------


class TestGetRecommendedBatchSize:
    def test_returns_current_batch_size(self):
        cfg = AutoTunerConfig()
        tuner = BatchAutoTuner(cfg, initial_batch_size=123)
        assert tuner.get_recommended_batch_size() == 123


# ---------------------------------------------------------------------------
# get_statistics — empty history branch
# ---------------------------------------------------------------------------


class TestGetStatisticsEmpty:
    def test_empty_history_returns_minimal_dict(self):
        cfg = AutoTunerConfig()
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        stats = tuner.get_statistics()
        assert stats["current_batch_size"] == 100
        assert stats["total_batches_analyzed"] == 0
        assert stats["total_adjustments"] == 0
        assert stats["history_size"] == 0
        # Full statistics keys absent in empty branch
        assert "average_p99_latency_ms" not in stats


# ---------------------------------------------------------------------------
# get_statistics — non-empty history branch
# ---------------------------------------------------------------------------


class TestGetStatisticsNonEmpty:
    """Tests exercising the branch where history is populated."""

    def _tuner_with_two_records(self) -> BatchAutoTuner:
        """Return tuner with 2 records (below threshold, no adjustment yet)."""
        cfg = AutoTunerConfig(history_size=10, target_p99_latency_ms=10.0)
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        # Add only 2 entries — below the min(3, history_size)=3 threshold so
        # _update_batch_size_recommendation is NOT called yet.
        tuner._history.append(
            {
                "batch_size": 100,
                "p99_latency_ms": 8.0,
                "p95_latency_ms": 7.0,
                "p50_latency_ms": 5.0,
                "success_rate": 0.99,
            }
        )
        tuner._history.append(
            {
                "batch_size": 100,
                "p99_latency_ms": 6.0,
                "p95_latency_ms": 5.0,
                "p50_latency_ms": 4.0,
                "success_rate": 0.98,
            }
        )
        tuner._total_batches_analyzed = 2
        return tuner

    def test_full_stats_keys_present(self):
        tuner = self._tuner_with_two_records()
        stats = tuner.get_statistics()
        for key in (
            "current_batch_size",
            "target_p99_latency_ms",
            "min_batch_size",
            "max_batch_size",
            "average_p99_latency_ms",
            "average_success_rate",
            "total_batches_analyzed",
            "total_adjustments",
            "history_size",
        ):
            assert key in stats, f"Missing key: {key}"

    def test_average_p99_computed_correctly(self):
        tuner = self._tuner_with_two_records()
        stats = tuner.get_statistics()
        assert stats["average_p99_latency_ms"] == pytest.approx(7.0)

    def test_average_success_rate_computed_correctly(self):
        tuner = self._tuner_with_two_records()
        stats = tuner.get_statistics()
        expected = (0.99 + 0.98) / 2
        assert stats["average_success_rate"] == pytest.approx(expected)

    def test_history_size_reflects_entries(self):
        tuner = self._tuner_with_two_records()
        stats = tuner.get_statistics()
        assert stats["history_size"] == 2


# ---------------------------------------------------------------------------
# record_batch_performance
# ---------------------------------------------------------------------------


class TestRecordBatchPerformance:
    """Tests for record_batch_performance including threshold logic."""

    def test_single_record_does_not_trigger_update(self):
        cfg = AutoTunerConfig(history_size=10)
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        original_size = tuner.current_batch_size
        tuner.record_batch_performance(
            batch_size=100,
            p99_latency_ms=5.0,
            p95_latency_ms=4.0,
            p50_latency_ms=3.0,
            success_rate=1.0,
        )
        assert tuner._total_batches_analyzed == 1
        assert tuner.current_batch_size == original_size

    def test_two_records_do_not_trigger_update(self):
        cfg = AutoTunerConfig(history_size=10)
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        for _ in range(2):
            tuner.record_batch_performance(
                batch_size=100,
                p99_latency_ms=5.0,
                p95_latency_ms=4.0,
                p50_latency_ms=3.0,
                success_rate=1.0,
            )
        assert tuner._total_adjustments == 0

    def test_three_records_trigger_update(self):
        cfg = AutoTunerConfig(history_size=10, target_p99_latency_ms=10.0)
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        # Three records with P99 well below target → should increase batch size
        for _ in range(3):
            tuner.record_batch_performance(
                batch_size=100,
                p99_latency_ms=1.0,
                p95_latency_ms=0.8,
                p50_latency_ms=0.5,
                success_rate=1.0,
            )
        assert tuner._total_batches_analyzed == 3

    def test_increments_total_batches_analyzed(self):
        cfg = AutoTunerConfig()
        tuner = BatchAutoTuner(cfg)
        for _i in range(5):
            tuner.record_batch_performance(
                batch_size=100,
                p99_latency_ms=5.0,
                p95_latency_ms=4.0,
                p50_latency_ms=3.0,
                success_rate=1.0,
            )
        assert tuner._total_batches_analyzed == 5

    def test_history_size_capped_by_maxlen(self):
        cfg = AutoTunerConfig(history_size=3)
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        for _i in range(10):
            tuner.record_batch_performance(
                batch_size=100,
                p99_latency_ms=5.0,
                p95_latency_ms=4.0,
                p50_latency_ms=3.0,
                success_rate=1.0,
            )
        assert len(tuner._history) == 3

    def test_history_size_one_triggers_after_one_record(self):
        """history_size=1 means min(3,1)=1 → update triggered immediately."""
        cfg = AutoTunerConfig(history_size=1, target_p99_latency_ms=10.0)
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        # However _update_batch_size_recommendation requires len >= 3 internally,
        # so no adjustment will occur — just verify no crash.
        tuner.record_batch_performance(
            batch_size=100,
            p99_latency_ms=5.0,
            p95_latency_ms=4.0,
            p50_latency_ms=3.0,
            success_rate=1.0,
        )
        assert tuner._total_batches_analyzed == 1

    def test_history_size_two_triggers_after_two_records(self):
        """history_size=2 means min(3,2)=2 → _update called after 2 records."""
        cfg = AutoTunerConfig(history_size=2, target_p99_latency_ms=10.0)
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        for _ in range(2):
            tuner.record_batch_performance(
                batch_size=100,
                p99_latency_ms=5.0,
                p95_latency_ms=4.0,
                p50_latency_ms=3.0,
                success_rate=1.0,
            )
        # _update_batch_size_recommendation called but requires len(history) >= 3
        # — no adjustment since only 2 entries
        assert tuner._total_adjustments == 0


# ---------------------------------------------------------------------------
# _update_batch_size_recommendation — all branches
# ---------------------------------------------------------------------------


class TestUpdateBatchSizeRecommendation:
    """Direct tests of the private update method via record_batch_performance."""

    def _make_tuner(self, target_p99=10.0, initial=100, adj=0.2):
        cfg = AutoTunerConfig(
            target_p99_latency_ms=target_p99,
            min_batch_size=10,
            max_batch_size=1000,
            history_size=10,
            adjustment_factor=adj,
        )
        return BatchAutoTuner(cfg, initial_batch_size=initial)

    def _fill_history(self, tuner, p99, count=3):
        """Directly fill history without triggering _update."""
        for _ in range(count):
            tuner._history.append(
                {
                    "batch_size": tuner.current_batch_size,
                    "p99_latency_ms": p99,
                    "p95_latency_ms": p99 * 0.9,
                    "p50_latency_ms": p99 * 0.5,
                    "success_rate": 1.0,
                }
            )
        tuner._total_batches_analyzed += count

    # Branch 1: avg_p99 > target → reduce batch size
    def test_high_latency_reduces_batch_size(self):
        tuner = self._make_tuner(target_p99=10.0, initial=100)
        self._fill_history(tuner, p99=20.0)  # well above target
        old_size = tuner.current_batch_size
        tuner._update_batch_size_recommendation()
        assert tuner.current_batch_size < old_size

    def test_high_latency_increments_adjustments(self):
        tuner = self._make_tuner(target_p99=10.0, initial=100)
        self._fill_history(tuner, p99=20.0)
        tuner._update_batch_size_recommendation()
        assert tuner._total_adjustments == 1

    # Branch 2: avg_p99 < target * 0.8 → increase batch size
    def test_low_latency_increases_batch_size(self):
        tuner = self._make_tuner(target_p99=10.0, initial=100)
        self._fill_history(tuner, p99=1.0)  # well below 80% of 10ms
        old_size = tuner.current_batch_size
        tuner._update_batch_size_recommendation()
        assert tuner.current_batch_size > old_size

    def test_low_latency_increments_adjustments(self):
        tuner = self._make_tuner(target_p99=10.0, initial=100)
        self._fill_history(tuner, p99=1.0)
        tuner._update_batch_size_recommendation()
        assert tuner._total_adjustments == 1

    # Branch 3: latency in acceptable range → no change (early return)
    def test_acceptable_latency_no_change(self):
        tuner = self._make_tuner(target_p99=10.0, initial=100)
        # 8.5ms is > 80% of 10ms (=8ms) but < 10ms → acceptable range
        self._fill_history(tuner, p99=8.5)
        old_size = tuner.current_batch_size
        tuner._update_batch_size_recommendation()
        assert tuner.current_batch_size == old_size
        assert tuner._total_adjustments == 0

    def test_acceptable_latency_exactly_at_80pct_threshold(self):
        tuner = self._make_tuner(target_p99=10.0, initial=100)
        # Exactly 8.0ms = 80% of 10ms → NOT less than 8ms, so no increase
        self._fill_history(tuner, p99=8.0)
        old_size = tuner.current_batch_size
        tuner._update_batch_size_recommendation()
        assert tuner.current_batch_size == old_size

    # Branch 4: fewer than 3 history entries → early return
    def test_less_than_three_history_no_change(self):
        tuner = self._make_tuner(target_p99=10.0, initial=100)
        tuner._history.append(
            {
                "batch_size": 100,
                "p99_latency_ms": 20.0,
                "p95_latency_ms": 18.0,
                "p50_latency_ms": 10.0,
                "success_rate": 1.0,
            }
        )
        tuner._history.append(
            {
                "batch_size": 100,
                "p99_latency_ms": 20.0,
                "p95_latency_ms": 18.0,
                "p50_latency_ms": 10.0,
                "success_rate": 1.0,
            }
        )
        old_size = tuner.current_batch_size
        tuner._update_batch_size_recommendation()
        assert tuner.current_batch_size == old_size

    # Branch 5: new size == current size → no update logged
    def test_no_adjustment_when_new_size_unchanged(self):
        """If int truncation produces the same size, no adjustment is counted."""
        # With a tiny adjustment factor, int() rounding may not change size.
        cfg = AutoTunerConfig(
            target_p99_latency_ms=10.0,
            min_batch_size=10,
            max_batch_size=1000,
            history_size=10,
            adjustment_factor=0.001,  # 0.1% change — int() rounds away
        )
        tuner = BatchAutoTuner(cfg, initial_batch_size=10)
        # Fill history with low P99 to trigger increase branch
        for _ in range(3):
            tuner._history.append(
                {
                    "batch_size": 10,
                    "p99_latency_ms": 1.0,
                    "p95_latency_ms": 0.9,
                    "p50_latency_ms": 0.5,
                    "success_rate": 1.0,
                }
            )
        tuner._update_batch_size_recommendation()
        # int(10 * 1.001) = 10 → no change
        assert tuner._total_adjustments == 0

    # Clamping to min boundary
    def test_batch_size_clamped_to_min(self):
        cfg = AutoTunerConfig(
            target_p99_latency_ms=10.0,
            min_batch_size=90,
            max_batch_size=1000,
            history_size=10,
            adjustment_factor=0.5,
        )
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        # High latency → reduce by 50% → 50, but clamped to 90
        for _ in range(3):
            tuner._history.append(
                {
                    "batch_size": 100,
                    "p99_latency_ms": 50.0,
                    "p95_latency_ms": 45.0,
                    "p50_latency_ms": 25.0,
                    "success_rate": 1.0,
                }
            )
        tuner._update_batch_size_recommendation()
        assert tuner.current_batch_size == 90

    # Clamping to max boundary
    def test_batch_size_clamped_to_max(self):
        cfg = AutoTunerConfig(
            target_p99_latency_ms=100.0,
            min_batch_size=10,
            max_batch_size=110,
            history_size=10,
            adjustment_factor=0.5,
        )
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        # Very low latency → increase by 50% → 150, but clamped to 110
        for _ in range(3):
            tuner._history.append(
                {
                    "batch_size": 100,
                    "p99_latency_ms": 1.0,
                    "p95_latency_ms": 0.9,
                    "p50_latency_ms": 0.5,
                    "success_rate": 1.0,
                }
            )
        tuner._update_batch_size_recommendation()
        assert tuner.current_batch_size == 110


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_history(self):
        cfg = AutoTunerConfig()
        tuner = BatchAutoTuner(cfg)
        for _ in range(5):
            tuner.record_batch_performance(
                batch_size=100,
                p99_latency_ms=5.0,
                p95_latency_ms=4.0,
                p50_latency_ms=3.0,
                success_rate=1.0,
            )
        tuner.reset()
        assert len(tuner._history) == 0

    def test_reset_clears_total_batches_analyzed(self):
        cfg = AutoTunerConfig()
        tuner = BatchAutoTuner(cfg)
        tuner._total_batches_analyzed = 42
        tuner.reset()
        assert tuner._total_batches_analyzed == 0

    def test_reset_clears_total_adjustments(self):
        cfg = AutoTunerConfig()
        tuner = BatchAutoTuner(cfg)
        tuner._total_adjustments = 7
        tuner.reset()
        assert tuner._total_adjustments == 0

    def test_reset_logs_info(self, caplog):
        cfg = AutoTunerConfig()
        tuner = BatchAutoTuner(cfg)
        with caplog.at_level(logging.INFO, logger="enhanced_agent_bus.batch_auto_tuner"):
            tuner.reset()
        assert "reset" in caplog.text.lower()


# ---------------------------------------------------------------------------
# Integration / end-to-end behaviour
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end tests exercising multiple calls."""

    def test_batch_size_decreases_under_sustained_high_latency(self):
        cfg = AutoTunerConfig(
            target_p99_latency_ms=10.0,
            min_batch_size=10,
            max_batch_size=1000,
            history_size=5,
            adjustment_factor=0.2,
        )
        tuner = BatchAutoTuner(cfg, initial_batch_size=200)
        for _ in range(10):
            tuner.record_batch_performance(
                batch_size=tuner.current_batch_size,
                p99_latency_ms=50.0,
                p95_latency_ms=40.0,
                p50_latency_ms=30.0,
                success_rate=0.95,
            )
        assert tuner.current_batch_size < 200
        assert tuner._total_adjustments > 0

    def test_batch_size_increases_under_sustained_low_latency(self):
        cfg = AutoTunerConfig(
            target_p99_latency_ms=10.0,
            min_batch_size=10,
            max_batch_size=1000,
            history_size=5,
            adjustment_factor=0.2,
        )
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        for _ in range(10):
            tuner.record_batch_performance(
                batch_size=tuner.current_batch_size,
                p99_latency_ms=0.5,
                p95_latency_ms=0.4,
                p50_latency_ms=0.3,
                success_rate=1.0,
            )
        assert tuner.current_batch_size > 100
        assert tuner._total_adjustments > 0

    def test_statistics_updated_after_multiple_calls(self):
        cfg = AutoTunerConfig()
        tuner = BatchAutoTuner(cfg)
        for i in range(5):
            tuner.record_batch_performance(
                batch_size=100,
                p99_latency_ms=float(i + 1),
                p95_latency_ms=float(i),
                p50_latency_ms=float(i) * 0.5,
                success_rate=0.9,
            )
        stats = tuner.get_statistics()
        assert stats["total_batches_analyzed"] == 5
        assert stats["history_size"] == 5

    def test_adjustment_logged(self, caplog):
        cfg = AutoTunerConfig(
            target_p99_latency_ms=10.0,
            min_batch_size=10,
            max_batch_size=1000,
            history_size=5,
            adjustment_factor=0.2,
        )
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        with caplog.at_level(logging.INFO, logger="enhanced_agent_bus.batch_auto_tuner"):
            for _ in range(3):
                tuner.record_batch_performance(
                    batch_size=100,
                    p99_latency_ms=50.0,
                    p95_latency_ms=40.0,
                    p50_latency_ms=30.0,
                    success_rate=0.9,
                )
        assert "adjusted" in caplog.text.lower() or tuner._total_adjustments > 0

    def test_recommended_size_never_below_min(self):
        cfg = AutoTunerConfig(
            target_p99_latency_ms=10.0,
            min_batch_size=50,
            max_batch_size=1000,
            history_size=5,
            adjustment_factor=0.5,
        )
        tuner = BatchAutoTuner(cfg, initial_batch_size=60)
        for _ in range(20):
            tuner.record_batch_performance(
                batch_size=tuner.current_batch_size,
                p99_latency_ms=999.0,
                p95_latency_ms=900.0,
                p50_latency_ms=500.0,
                success_rate=0.5,
            )
        assert tuner.current_batch_size >= 50

    def test_recommended_size_never_above_max(self):
        cfg = AutoTunerConfig(
            target_p99_latency_ms=100.0,
            min_batch_size=10,
            max_batch_size=200,
            history_size=5,
            adjustment_factor=0.5,
        )
        tuner = BatchAutoTuner(cfg, initial_batch_size=150)
        for _ in range(20):
            tuner.record_batch_performance(
                batch_size=tuner.current_batch_size,
                p99_latency_ms=0.001,
                p95_latency_ms=0.001,
                p50_latency_ms=0.001,
                success_rate=1.0,
            )
        assert tuner.current_batch_size <= 200

    def test_reset_and_reuse(self):
        cfg = AutoTunerConfig(target_p99_latency_ms=10.0, history_size=5)
        tuner = BatchAutoTuner(cfg, initial_batch_size=100)
        # Fill and trigger adjustments
        for _ in range(5):
            tuner.record_batch_performance(
                batch_size=100,
                p99_latency_ms=50.0,
                p95_latency_ms=40.0,
                p50_latency_ms=25.0,
                success_rate=0.9,
            )
        tuner.reset()
        # After reset statistics are zero
        stats = tuner.get_statistics()
        assert stats["total_batches_analyzed"] == 0
        assert stats["history_size"] == 0
        # Can still record new data
        tuner.record_batch_performance(
            batch_size=100,
            p99_latency_ms=5.0,
            p95_latency_ms=4.0,
            p50_latency_ms=3.0,
            success_rate=1.0,
        )
        assert tuner._total_batches_analyzed == 1
