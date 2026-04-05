# Constitutional Hash: 608508a9bd224290
# Sprint 59 — middlewares/batch/auto_tune.py coverage
"""
Comprehensive tests for BatchAutoTuneMiddleware.

Targets >=95% coverage of:
    src/core/enhanced_agent_bus/middlewares/batch/auto_tune.py
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.middlewares.batch.auto_tune import (
    BATCH_AUTO_TUNE_ERRORS,
    BatchAutoTuneMiddleware,
)
from enhanced_agent_bus.middlewares.batch.context import BatchPipelineContext
from enhanced_agent_bus.middlewares.batch.exceptions import BatchAutoTuneException
from enhanced_agent_bus.pipeline.middleware import MiddlewareConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(**kwargs) -> BatchPipelineContext:
    """Create a minimal BatchPipelineContext."""
    return BatchPipelineContext(**kwargs)


def _make_middleware(
    target_p99_ms: float = 100.0,
    adjustment_factor: float = 0.1,
    fail_closed: bool = True,
    **config_kwargs,
) -> BatchAutoTuneMiddleware:
    config = MiddlewareConfig(fail_closed=fail_closed, **config_kwargs)
    return BatchAutoTuneMiddleware(
        config=config,
        target_p99_ms=target_p99_ms,
        adjustment_factor=adjustment_factor,
    )


def _make_response_item(processing_time_ms=None, success=True):
    """Create a mock BatchResponseItem."""
    item = MagicMock()
    item.processing_time_ms = processing_time_ms
    item.success = success
    return item


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


class TestInit:
    """BatchAutoTuneMiddleware.__init__ coverage."""

    def test_default_init(self):
        mw = BatchAutoTuneMiddleware()
        assert mw._target_p99_ms == 100.0
        assert mw._adjustment_factor == 0.1
        assert mw._current_batch_size == BatchAutoTuneMiddleware.DEFAULT_BATCH_SIZE
        assert mw._latency_history == []
        assert mw._max_history_size == 100
        assert mw._tuning_enabled is True

    def test_custom_target_p99(self):
        mw = BatchAutoTuneMiddleware(target_p99_ms=200.0)
        assert mw._target_p99_ms == 200.0

    def test_adjustment_factor_clamped_min(self):
        mw = BatchAutoTuneMiddleware(adjustment_factor=0.0)
        assert mw._adjustment_factor == 0.01

    def test_adjustment_factor_clamped_max(self):
        mw = BatchAutoTuneMiddleware(adjustment_factor=1.0)
        assert mw._adjustment_factor == 0.5

    def test_adjustment_factor_mid_range(self):
        mw = BatchAutoTuneMiddleware(adjustment_factor=0.3)
        assert mw._adjustment_factor == 0.3

    def test_custom_config(self):
        config = MiddlewareConfig(fail_closed=False)
        mw = BatchAutoTuneMiddleware(config=config)
        assert mw.config.fail_closed is False

    def test_class_constants(self):
        assert BatchAutoTuneMiddleware.MIN_BATCH_SIZE == 10
        assert BatchAutoTuneMiddleware.MAX_BATCH_SIZE == 1000
        assert BatchAutoTuneMiddleware.DEFAULT_BATCH_SIZE == 100


# ---------------------------------------------------------------------------
# process() — happy path
# ---------------------------------------------------------------------------


class TestProcess:
    """BatchAutoTuneMiddleware.process() core paths."""

    async def test_process_empty_items_no_latency(self):
        mw = _make_middleware()
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        result = await mw.process(ctx)
        assert result.current_batch_size == BatchAutoTuneMiddleware.DEFAULT_BATCH_SIZE

    async def test_process_records_item_latencies(self):
        mw = _make_middleware()
        items = [_make_response_item(processing_time_ms=50.0) for _ in range(3)]
        ctx = _make_context(processed_items=items, batch_latency_ms=0.0)
        await mw.process(ctx)
        assert len(mw._latency_history) == 3

    async def test_process_skips_none_processing_time(self):
        mw = _make_middleware()
        items = [
            _make_response_item(processing_time_ms=None),
            _make_response_item(processing_time_ms=50.0),
        ]
        ctx = _make_context(processed_items=items, batch_latency_ms=0.0)
        await mw.process(ctx)
        assert len(mw._latency_history) == 1

    async def test_process_records_batch_latency(self):
        mw = _make_middleware()
        items = [_make_response_item(processing_time_ms=None)]
        ctx = _make_context(processed_items=items, batch_latency_ms=100.0)
        await mw.process(ctx)
        # batch_latency_ms / max(1, 1) = 100.0 — one measurement recorded
        assert len(mw._latency_history) == 1

    async def test_process_sets_context_current_batch_size(self):
        mw = _make_middleware()
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        await mw.process(ctx)
        assert ctx.current_batch_size == mw._current_batch_size

    async def test_process_sets_context_target_p99(self):
        mw = _make_middleware(target_p99_ms=150.0)
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        await mw.process(ctx)
        assert ctx.target_p99_ms == 150.0

    async def test_process_calls_next_middleware(self):
        mw = _make_middleware()
        next_mw = MagicMock()
        next_mw.config = MiddlewareConfig(enabled=True)
        next_mw.process = AsyncMock(side_effect=lambda ctx: ctx)
        mw._next = next_mw
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        await mw.process(ctx)
        next_mw.process.assert_called_once()

    async def test_process_adds_duration_to_batch_latency(self):
        mw = _make_middleware()
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        await mw.process(ctx)
        # duration_ms is positive
        assert ctx.batch_latency_ms > 0.0

    async def test_process_batch_latency_with_zero_processed_items(self):
        """batch_latency_ms > 0 with empty processed_items: uses max(0, 1) = 1."""
        mw = _make_middleware()
        ctx = _make_context(processed_items=[], batch_latency_ms=200.0)
        await mw.process(ctx)
        # one measurement = 200.0 / 1 = 200.0
        assert 200.0 in mw._latency_history


# ---------------------------------------------------------------------------
# process() — auto-tuning triggered
# ---------------------------------------------------------------------------


class TestProcessAutoTuning:
    """Tests where _should_adjust() returns True and batch size changes."""

    def _fill_history(self, mw: BatchAutoTuneMiddleware, latency_ms: float, count: int = 15):
        for _ in range(count):
            mw._record_latency(latency_ms)

    async def test_tuning_increases_batch_size_when_latency_low(self):
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.1)
        # P99 will be well below target*0.8=80ms
        self._fill_history(mw, latency_ms=30.0, count=15)
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        original = mw._current_batch_size
        await mw.process(ctx)
        assert mw._current_batch_size > original

    async def test_tuning_decreases_batch_size_when_latency_high(self):
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.1)
        # P99 will be above target
        self._fill_history(mw, latency_ms=500.0, count=15)
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        original = mw._current_batch_size
        await mw.process(ctx)
        assert mw._current_batch_size < original

    async def test_tuning_no_change_within_acceptable_range(self):
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.1)
        # P99 = 85ms — between 80ms and 100ms
        self._fill_history(mw, latency_ms=85.0, count=15)
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        original = mw._current_batch_size
        await mw.process(ctx)
        assert mw._current_batch_size == original

    async def test_tuning_disabled_skips_adjustment(self):
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.1)
        self._fill_history(mw, latency_ms=30.0, count=15)
        mw.set_tuning_enabled(False)
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        original = mw._current_batch_size
        await mw.process(ctx)
        assert mw._current_batch_size == original

    async def test_context_gets_updated_batch_size(self):
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.1)
        self._fill_history(mw, latency_ms=30.0, count=15)
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        await mw.process(ctx)
        assert ctx.current_batch_size == mw._current_batch_size


# ---------------------------------------------------------------------------
# process() — error handling
# ---------------------------------------------------------------------------


class TestProcessErrorHandling:
    """Tests for error branches in process()."""

    async def test_fail_closed_raises_batch_auto_tune_exception(self):
        mw = _make_middleware(fail_closed=True)
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)

        with patch.object(mw, "_record_latency", side_effect=RuntimeError("boom")):
            # Trigger RuntimeError on first latency record
            items = [_make_response_item(processing_time_ms=10.0)]
            ctx.processed_items = items
            with pytest.raises(BatchAutoTuneException) as exc_info:
                await mw.process(ctx)
        assert "Auto-tuning failed" in str(exc_info.value)

    async def test_fail_open_adds_warning_on_error(self):
        mw = _make_middleware(fail_closed=False)
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)

        with patch.object(mw, "_record_latency", side_effect=ValueError("bad val")):
            items = [_make_response_item(processing_time_ms=10.0)]
            ctx.processed_items = items
            result = await mw.process(ctx)
        assert any("Auto-tuning failed" in w for w in result.warnings)

    async def test_fail_open_continues_pipeline_on_error(self):
        mw = _make_middleware(fail_closed=False)
        next_mw = MagicMock()
        next_mw.config = MiddlewareConfig(enabled=True)
        next_mw.process = AsyncMock(side_effect=lambda ctx: ctx)
        mw._next = next_mw
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)

        with patch.object(mw, "_record_latency", side_effect=TypeError("type err")):
            items = [_make_response_item(processing_time_ms=10.0)]
            ctx.processed_items = items
            result = await mw.process(ctx)
        next_mw.process.assert_called_once()

    async def test_batch_auto_tune_exception_carries_target_p99(self):
        mw = _make_middleware(target_p99_ms=77.5, fail_closed=True)
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)

        with patch.object(mw, "_record_latency", side_effect=KeyError("k")):
            items = [_make_response_item(processing_time_ms=10.0)]
            ctx.processed_items = items
            with pytest.raises(BatchAutoTuneException) as exc_info:
                await mw.process(ctx)
        assert exc_info.value.target_p99_ms == 77.5

    async def test_attribute_error_caught_in_fail_open(self):
        mw = _make_middleware(fail_closed=False)
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)

        with patch.object(mw, "_record_latency", side_effect=AttributeError("attr")):
            items = [_make_response_item(processing_time_ms=10.0)]
            ctx.processed_items = items
            result = await mw.process(ctx)
        assert any("Auto-tuning failed" in w for w in result.warnings)

    async def test_fail_open_context_warnings_appended(self):
        """Verify that warnings attribute is extended, not replaced."""
        mw = _make_middleware(fail_closed=False)
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        ctx.warnings = ["pre-existing warning"]

        with patch.object(mw, "_record_latency", side_effect=ValueError("oops")):
            items = [_make_response_item(processing_time_ms=10.0)]
            ctx.processed_items = items
            result = await mw.process(ctx)
        assert "pre-existing warning" in result.warnings
        assert len(result.warnings) == 2


# ---------------------------------------------------------------------------
# _record_latency()
# ---------------------------------------------------------------------------


class TestRecordLatency:
    """Tests for _record_latency()."""

    def test_appends_to_history(self):
        mw = _make_middleware()
        mw._record_latency(42.0)
        assert mw._latency_history == [42.0]

    def test_keeps_history_bounded(self):
        mw = _make_middleware()
        mw._max_history_size = 5
        for i in range(10):
            mw._record_latency(float(i))
        assert len(mw._latency_history) == 5
        # Should keep most recent 5
        assert mw._latency_history == [5.0, 6.0, 7.0, 8.0, 9.0]

    def test_bounded_at_exactly_max_size(self):
        mw = _make_middleware()
        mw._max_history_size = 3
        mw._record_latency(1.0)
        mw._record_latency(2.0)
        mw._record_latency(3.0)
        assert len(mw._latency_history) == 3
        mw._record_latency(4.0)
        assert len(mw._latency_history) == 3
        assert mw._latency_history[-1] == 4.0

    def test_100_default_max(self):
        mw = _make_middleware()
        for i in range(105):
            mw._record_latency(float(i))
        assert len(mw._latency_history) == 100


# ---------------------------------------------------------------------------
# _should_adjust()
# ---------------------------------------------------------------------------


class TestShouldAdjust:
    """Tests for _should_adjust()."""

    def test_returns_false_with_no_data(self):
        mw = _make_middleware()
        assert mw._should_adjust() is False

    def test_returns_false_below_threshold(self):
        mw = _make_middleware()
        for _ in range(9):
            mw._record_latency(50.0)
        assert mw._should_adjust() is False

    def test_returns_true_at_threshold(self):
        mw = _make_middleware()
        for _ in range(10):
            mw._record_latency(50.0)
        assert mw._should_adjust() is True

    def test_returns_true_above_threshold(self):
        mw = _make_middleware()
        for _ in range(20):
            mw._record_latency(50.0)
        assert mw._should_adjust() is True


# ---------------------------------------------------------------------------
# _calculate_p99()
# ---------------------------------------------------------------------------


class TestCalculateP99:
    """Tests for _calculate_p99()."""

    def test_empty_history_returns_zero(self):
        mw = _make_middleware()
        assert mw._calculate_p99() == 0.0

    def test_single_value(self):
        mw = _make_middleware()
        mw._record_latency(55.0)
        assert mw._calculate_p99() == 55.0

    def test_hundred_values_p99(self):
        mw = _make_middleware()
        for i in range(1, 101):
            mw._record_latency(float(i))
        p99 = mw._calculate_p99()
        # idx = int(100 * 0.99) = 99, value at index 99 is 100.0
        assert p99 == 100.0

    def test_two_values(self):
        mw = _make_middleware()
        mw._record_latency(10.0)
        mw._record_latency(200.0)
        p99 = mw._calculate_p99()
        # idx = int(2 * 0.99) = 1, sorted[1] = 200.0
        assert p99 == 200.0

    def test_monotone_ascending(self):
        mw = _make_middleware()
        for v in [1.0, 2.0, 3.0, 4.0, 5.0]:
            mw._record_latency(v)
        p99 = mw._calculate_p99()
        assert p99 == 5.0


# ---------------------------------------------------------------------------
# _update_batch_size()
# ---------------------------------------------------------------------------


class TestUpdateBatchSize:
    """Tests for _update_batch_size() — all three AIMD branches."""

    def test_latency_above_target_decreases(self):
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.1)
        mw._current_batch_size = 100
        new_size = mw._update_batch_size(200.0)
        # decrease = int(100 * 0.1) = 10, new = max(10, 100 - max(10, 1)) = 90
        assert new_size == 90

    def test_latency_above_target_clamps_to_min(self):
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.5)
        mw._current_batch_size = 10  # already at MIN
        new_size = mw._update_batch_size(200.0)
        assert new_size == BatchAutoTuneMiddleware.MIN_BATCH_SIZE

    def test_latency_well_below_target_increases(self):
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.1)
        mw._current_batch_size = 100
        # latency < 100 * 0.8 = 80
        new_size = mw._update_batch_size(50.0)
        # increase = max(1, int(100 * 0.1)) = 10, new = min(1000, 110) = 110
        assert new_size == 110

    def test_latency_well_below_target_clamps_to_max(self):
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.1)
        mw._current_batch_size = 1000  # already at MAX
        new_size = mw._update_batch_size(50.0)
        assert new_size == BatchAutoTuneMiddleware.MAX_BATCH_SIZE

    def test_latency_in_acceptable_range_no_change(self):
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.1)
        mw._current_batch_size = 100
        # 80 <= 85 <= 100 → no change
        new_size = mw._update_batch_size(85.0)
        assert new_size == 100

    def test_latency_exactly_at_target_no_change(self):
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.1)
        mw._current_batch_size = 100
        new_size = mw._update_batch_size(100.0)
        # exactly == target, not > and not < 80 → no change
        assert new_size == 100

    def test_latency_at_boundary_80_percent_no_change(self):
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.1)
        mw._current_batch_size = 100
        # exactly 80.0 is NOT < 80 → no change
        new_size = mw._update_batch_size(80.0)
        assert new_size == 100

    def test_decrease_at_least_one(self):
        """When adjustment_factor is tiny and current size is small, decrease by at least 1."""
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.01)
        mw._current_batch_size = 11
        new_size = mw._update_batch_size(200.0)
        # decrease = int(11 * 0.01) = 0, but max(0, 1) = 1, new = max(10, 11-1) = 10
        assert new_size == 10

    def test_increase_at_least_one(self):
        """increase = max(1, int(...)) guarantees minimum +1."""
        mw = _make_middleware(target_p99_ms=100.0, adjustment_factor=0.01)
        mw._current_batch_size = 50
        new_size = mw._update_batch_size(10.0)
        # increase = max(1, int(50 * 0.01)) = max(1, 0) = 1
        assert new_size == 51


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """Tests for all property accessors."""

    def test_current_batch_size_property(self):
        mw = _make_middleware()
        assert mw.current_batch_size == mw._current_batch_size

    def test_target_p99_ms_property(self):
        mw = _make_middleware(target_p99_ms=250.0)
        assert mw.target_p99_ms == 250.0

    def test_current_p99_ms_empty(self):
        mw = _make_middleware()
        assert mw.current_p99_ms == 0.0

    def test_current_p99_ms_with_data(self):
        mw = _make_middleware()
        mw._record_latency(75.0)
        assert mw.current_p99_ms == 75.0

    def test_latency_history_returns_copy(self):
        mw = _make_middleware()
        mw._record_latency(10.0)
        history = mw.latency_history
        history.append(999.0)
        # Original should be unchanged
        assert 999.0 not in mw._latency_history

    def test_tuning_enabled_default_true(self):
        mw = _make_middleware()
        assert mw.tuning_enabled is True

    def test_tuning_enabled_after_disable(self):
        mw = _make_middleware()
        mw.set_tuning_enabled(False)
        assert mw.tuning_enabled is False

    def test_tuning_enabled_after_re_enable(self):
        mw = _make_middleware()
        mw.set_tuning_enabled(False)
        mw.set_tuning_enabled(True)
        assert mw.tuning_enabled is True


# ---------------------------------------------------------------------------
# set_tuning_enabled()
# ---------------------------------------------------------------------------


class TestSetTuningEnabled:
    """Tests for set_tuning_enabled()."""

    def test_disable(self):
        mw = _make_middleware()
        mw.set_tuning_enabled(False)
        assert mw._tuning_enabled is False

    def test_enable(self):
        mw = _make_middleware()
        mw._tuning_enabled = False
        mw.set_tuning_enabled(True)
        assert mw._tuning_enabled is True


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------


class TestReset:
    """Tests for reset()."""

    def test_reset_restores_default_batch_size(self):
        mw = _make_middleware()
        mw._current_batch_size = 500
        mw.reset()
        assert mw._current_batch_size == BatchAutoTuneMiddleware.DEFAULT_BATCH_SIZE

    def test_reset_clears_latency_history(self):
        mw = _make_middleware()
        for _ in range(20):
            mw._record_latency(50.0)
        mw.reset()
        assert mw._latency_history == []

    def test_reset_does_not_change_tuning_enabled(self):
        mw = _make_middleware()
        mw.set_tuning_enabled(False)
        mw.reset()
        # reset() does NOT touch _tuning_enabled
        assert mw._tuning_enabled is False


# ---------------------------------------------------------------------------
# get_stats()
# ---------------------------------------------------------------------------


class TestGetStats:
    """Tests for get_stats()."""

    def test_returns_dict_with_expected_keys(self):
        mw = _make_middleware()
        stats = mw.get_stats()
        expected_keys = {
            "current_batch_size",
            "target_p99_ms",
            "current_p99_ms",
            "latency_measurements",
            "tuning_enabled",
            "min_batch_size",
            "max_batch_size",
        }
        assert set(stats.keys()) == expected_keys

    def test_stats_current_batch_size(self):
        mw = _make_middleware()
        mw._current_batch_size = 200
        stats = mw.get_stats()
        assert stats["current_batch_size"] == 200

    def test_stats_target_p99(self):
        mw = _make_middleware(target_p99_ms=75.0)
        stats = mw.get_stats()
        assert stats["target_p99_ms"] == 75.0

    def test_stats_current_p99_empty(self):
        mw = _make_middleware()
        stats = mw.get_stats()
        assert stats["current_p99_ms"] == 0.0

    def test_stats_latency_measurements_count(self):
        mw = _make_middleware()
        for _ in range(7):
            mw._record_latency(10.0)
        stats = mw.get_stats()
        assert stats["latency_measurements"] == 7

    def test_stats_tuning_enabled(self):
        mw = _make_middleware()
        mw.set_tuning_enabled(False)
        stats = mw.get_stats()
        assert stats["tuning_enabled"] is False

    def test_stats_min_max_batch_size(self):
        mw = _make_middleware()
        stats = mw.get_stats()
        assert stats["min_batch_size"] == BatchAutoTuneMiddleware.MIN_BATCH_SIZE
        assert stats["max_batch_size"] == BatchAutoTuneMiddleware.MAX_BATCH_SIZE


# ---------------------------------------------------------------------------
# BATCH_AUTO_TUNE_ERRORS constant
# ---------------------------------------------------------------------------


class TestBatchAutoTuneErrors:
    """Tests for BATCH_AUTO_TUNE_ERRORS tuple."""

    def test_contains_expected_error_types(self):
        assert RuntimeError in BATCH_AUTO_TUNE_ERRORS
        assert ValueError in BATCH_AUTO_TUNE_ERRORS
        assert TypeError in BATCH_AUTO_TUNE_ERRORS
        assert KeyError in BATCH_AUTO_TUNE_ERRORS
        assert AttributeError in BATCH_AUTO_TUNE_ERRORS

    def test_is_tuple(self):
        assert isinstance(BATCH_AUTO_TUNE_ERRORS, tuple)


# ---------------------------------------------------------------------------
# Integration — full process() round trip with tuning
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end process() tests that combine multiple features."""

    async def test_full_round_trip_increases_batch_size(self):
        """Feed enough low-latency measurements to trigger size increase."""
        mw = BatchAutoTuneMiddleware(target_p99_ms=100.0, adjustment_factor=0.1)
        # Pre-fill history so _should_adjust() triggers
        for _ in range(12):
            mw._record_latency(20.0)  # well below 80 ms threshold

        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        result = await mw.process(ctx)
        assert result.current_batch_size > BatchAutoTuneMiddleware.DEFAULT_BATCH_SIZE

    async def test_full_round_trip_decreases_batch_size(self):
        """Feed enough high-latency measurements to trigger size decrease."""
        mw = BatchAutoTuneMiddleware(target_p99_ms=100.0, adjustment_factor=0.1)
        for _ in range(12):
            mw._record_latency(300.0)  # well above 100 ms threshold

        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        result = await mw.process(ctx)
        assert result.current_batch_size < BatchAutoTuneMiddleware.DEFAULT_BATCH_SIZE

    async def test_repeated_calls_accumulate_history(self):
        mw = _make_middleware()
        for _ in range(5):
            item = _make_response_item(processing_time_ms=30.0)
            ctx = _make_context(processed_items=[item], batch_latency_ms=0.0)
            await mw.process(ctx)
        assert len(mw._latency_history) == 5

    async def test_no_next_middleware_returns_context(self):
        mw = _make_middleware()
        mw._next = None
        ctx = _make_context(processed_items=[], batch_latency_ms=0.0)
        result = await mw.process(ctx)
        assert result is ctx

    async def test_batch_latency_with_multiple_items(self):
        mw = _make_middleware()
        items = [
            _make_response_item(processing_time_ms=None),
            _make_response_item(processing_time_ms=None),
        ]
        ctx = _make_context(processed_items=items, batch_latency_ms=60.0)
        await mw.process(ctx)
        # 60.0 / max(2, 1) = 30.0
        assert 30.0 in mw._latency_history
