# Constitutional Hash: 608508a9bd224290
# Sprint 54 — middlewares/batch/concurrency.py coverage
"""
Comprehensive tests for BatchConcurrencyMiddleware.

Targets >=95% coverage of:
    src/core/enhanced_agent_bus/middlewares/batch/concurrency.py
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.middlewares.batch.concurrency import (
    BatchConcurrencyMiddleware,
)
from enhanced_agent_bus.middlewares.batch.context import BatchPipelineContext
from enhanced_agent_bus.middlewares.batch.exceptions import (
    BatchConcurrencyException,
)
from enhanced_agent_bus.pipeline.middleware import MiddlewareConfig
from enhanced_agent_bus.validators import ValidationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(**kwargs) -> BatchPipelineContext:
    """Create a minimal BatchPipelineContext."""
    return BatchPipelineContext(**kwargs)


def _make_middleware(
    max_concurrency: int = 10,
    fail_closed: bool = True,
    **config_kwargs,
) -> BatchConcurrencyMiddleware:
    config = MiddlewareConfig(fail_closed=fail_closed, **config_kwargs)
    return BatchConcurrencyMiddleware(config=config, max_concurrency=max_concurrency)


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


class TestInit:
    """BatchConcurrencyMiddleware.__init__ coverage."""

    def test_default_max_concurrency(self):
        mw = BatchConcurrencyMiddleware()
        assert mw._max_concurrency == 100

    def test_custom_max_concurrency(self):
        mw = BatchConcurrencyMiddleware(max_concurrency=5)
        assert mw._max_concurrency == 5

    def test_initial_active_count(self):
        mw = BatchConcurrencyMiddleware()
        assert mw._active_count == 0

    def test_initial_total_processed(self):
        mw = BatchConcurrencyMiddleware()
        assert mw._total_processed == 0

    def test_semaphore_created(self):
        mw = BatchConcurrencyMiddleware(max_concurrency=7)
        assert isinstance(mw._semaphore, asyncio.Semaphore)

    def test_config_defaults_when_none(self):
        mw = BatchConcurrencyMiddleware(config=None)
        assert mw.config is not None
        assert mw.config.fail_closed is True

    def test_config_respected(self):
        cfg = MiddlewareConfig(fail_closed=False, timeout_ms=500)
        mw = BatchConcurrencyMiddleware(config=cfg)
        assert mw.config.fail_closed is False
        assert mw.config.timeout_ms == 500


# ---------------------------------------------------------------------------
# process() — happy path (semaphore not locked / under capacity)
# ---------------------------------------------------------------------------


class TestProcessHappyPath:
    """process() when concurrency is available."""

    async def test_process_sets_max_concurrency_on_context(self):
        mw = _make_middleware(max_concurrency=42)
        ctx = _make_context()
        # No next middleware — _call_next returns ctx unchanged
        result = await mw.process(ctx)
        assert result.max_concurrency == 42

    async def test_process_increments_batch_latency(self):
        mw = _make_middleware(max_concurrency=10)
        ctx = _make_context()
        initial_latency = ctx.batch_latency_ms
        await mw.process(ctx)
        assert ctx.batch_latency_ms >= initial_latency

    async def test_process_calls_next_middleware(self):
        mw = _make_middleware(max_concurrency=10)
        ctx = _make_context()
        sentinel = object()
        next_ctx = _make_context()

        async def fake_next(c):
            return next_ctx

        mw._next = MagicMock()
        mw._next.config = MiddlewareConfig(enabled=True)
        mw._next.process = AsyncMock(return_value=next_ctx)
        result = await mw.process(ctx)
        assert result is next_ctx

    async def test_process_no_early_result_when_under_capacity(self):
        mw = _make_middleware(max_concurrency=10)
        ctx = _make_context()
        await mw.process(ctx)
        assert ctx.early_result is None

    async def test_process_returns_pipeline_context(self):
        mw = _make_middleware(max_concurrency=5)
        ctx = _make_context()
        result = await mw.process(ctx)
        assert result is not None


# ---------------------------------------------------------------------------
# process() — at capacity, fail_closed=True
# ---------------------------------------------------------------------------


class TestProcessAtCapacityFailClosed:
    """process() raises BatchConcurrencyException when at capacity and fail_closed=True."""

    async def test_raises_when_at_capacity_and_fail_closed(self):
        mw = _make_middleware(max_concurrency=1, fail_closed=True)
        ctx = _make_context()

        # Make semaphore appear locked and active_count at max
        mw._active_count = 1
        with patch.object(mw._semaphore, "locked", return_value=True):
            with pytest.raises(BatchConcurrencyException) as exc_info:
                await mw.process(ctx)

        exc = exc_info.value
        assert exc.max_concurrency == 1
        assert exc.current_count == 1

    async def test_exception_message_contains_max_concurrency(self):
        mw = _make_middleware(max_concurrency=3, fail_closed=True)
        ctx = _make_context()
        mw._active_count = 3
        with patch.object(mw._semaphore, "locked", return_value=True):
            with pytest.raises(BatchConcurrencyException) as exc_info:
                await mw.process(ctx)
        assert "3" in exc_info.value.args[0]


# ---------------------------------------------------------------------------
# process() — at capacity, fail_closed=False (early result path)
# ---------------------------------------------------------------------------


class TestProcessAtCapacityFailOpen:
    """process() sets early_result and continues chain when fail_closed=False."""

    async def test_sets_early_result_when_not_fail_closed(self):
        mw = _make_middleware(max_concurrency=2, fail_closed=False)
        ctx = _make_context()
        mw._active_count = 2
        with patch.object(mw._semaphore, "locked", return_value=True):
            await mw.process(ctx)

        assert ctx.early_result is not None
        assert ctx.early_result.is_valid is False

    async def test_early_result_contains_error_message(self):
        mw = _make_middleware(max_concurrency=2, fail_closed=False)
        ctx = _make_context()
        mw._active_count = 2
        with patch.object(mw._semaphore, "locked", return_value=True):
            await mw.process(ctx)

        assert len(ctx.early_result.errors) > 0
        assert "Maximum concurrency" in ctx.early_result.errors[0]

    async def test_early_result_metadata_has_validation_stage(self):
        mw = _make_middleware(max_concurrency=2, fail_closed=False)
        ctx = _make_context()
        mw._active_count = 2
        with patch.object(mw._semaphore, "locked", return_value=True):
            await mw.process(ctx)

        assert ctx.early_result.metadata["validation_stage"] == "concurrency"

    async def test_early_result_metadata_has_max_concurrency(self):
        mw = _make_middleware(max_concurrency=2, fail_closed=False)
        ctx = _make_context()
        mw._active_count = 2
        with patch.object(mw._semaphore, "locked", return_value=True):
            await mw.process(ctx)

        assert ctx.early_result.metadata["max_concurrency"] == 2

    async def test_early_result_metadata_has_current_count(self):
        mw = _make_middleware(max_concurrency=2, fail_closed=False)
        ctx = _make_context()
        mw._active_count = 2
        with patch.object(mw._semaphore, "locked", return_value=True):
            await mw.process(ctx)

        assert ctx.early_result.metadata["current_count"] == 2

    async def test_calls_next_even_after_early_result(self):
        mw = _make_middleware(max_concurrency=2, fail_closed=False)
        ctx = _make_context()
        next_ctx = _make_context()
        mw._next = MagicMock()
        mw._next.config = MiddlewareConfig(enabled=True)
        mw._next.process = AsyncMock(return_value=next_ctx)
        mw._active_count = 2

        with patch.object(mw._semaphore, "locked", return_value=True):
            result = await mw.process(ctx)

        # _call_next was invoked so result is next_ctx
        assert result is next_ctx

    async def test_no_exception_when_not_fail_closed(self):
        mw = _make_middleware(max_concurrency=1, fail_closed=False)
        ctx = _make_context()
        mw._active_count = 1
        with patch.object(mw._semaphore, "locked", return_value=True):
            # Should not raise
            result = await mw.process(ctx)
        assert result is not None


# ---------------------------------------------------------------------------
# process() — semaphore locked but count < max (edge: locked but not at max)
# ---------------------------------------------------------------------------


class TestProcessSemaphoreLockedNotAtMax:
    """When semaphore is locked but active_count < max, should proceed normally."""

    async def test_proceeds_when_locked_but_under_capacity(self):
        mw = _make_middleware(max_concurrency=5, fail_closed=True)
        ctx = _make_context()
        # locked() = True but active_count (0) < max_concurrency (5)
        with patch.object(mw._semaphore, "locked", return_value=True):
            # Should NOT raise, should proceed normally
            result = await mw.process(ctx)
        assert result is not None
        assert ctx.early_result is None


# ---------------------------------------------------------------------------
# acquire() and release() tests
# ---------------------------------------------------------------------------


class TestAcquireRelease:
    """acquire() and release() manage semaphore and counters correctly."""

    async def test_acquire_increments_active_count(self):
        mw = _make_middleware(max_concurrency=5)
        await mw.acquire()
        assert mw._active_count == 1

    async def test_acquire_multiple_times(self):
        mw = _make_middleware(max_concurrency=5)
        await mw.acquire()
        await mw.acquire()
        assert mw._active_count == 2

    def test_release_decrements_active_count(self):
        mw = _make_middleware(max_concurrency=5)
        mw._active_count = 2
        # Need to have the semaphore acquired first
        # Manually set internal value for release test
        mw._semaphore._value = 3  # semaphore tracks releases
        mw.release()
        assert mw._active_count == 1

    def test_release_increments_total_processed(self):
        mw = _make_middleware(max_concurrency=5)
        mw._active_count = 1
        mw._semaphore._value = 4
        mw.release()
        assert mw._total_processed == 1

    async def test_acquire_then_release_restores_active_count(self):
        mw = _make_middleware(max_concurrency=5)
        await mw.acquire()
        assert mw._active_count == 1
        mw.release()
        assert mw._active_count == 0

    async def test_multiple_acquire_release_cycles(self):
        mw = _make_middleware(max_concurrency=5)
        for _ in range(3):
            await mw.acquire()
            mw.release()
        assert mw._active_count == 0
        assert mw._total_processed == 3


# ---------------------------------------------------------------------------
# available_slots property
# ---------------------------------------------------------------------------


class TestAvailableSlots:
    """available_slots returns correct count."""

    def test_available_slots_all_free(self):
        mw = _make_middleware(max_concurrency=10)
        assert mw.available_slots == 10

    def test_available_slots_some_used(self):
        mw = _make_middleware(max_concurrency=10)
        mw._active_count = 3
        assert mw.available_slots == 7

    def test_available_slots_at_capacity(self):
        mw = _make_middleware(max_concurrency=5)
        mw._active_count = 5
        assert mw.available_slots == 0

    def test_available_slots_over_capacity_clamped_to_zero(self):
        """max(0, ...) clamp applies when active_count > max."""
        mw = _make_middleware(max_concurrency=3)
        mw._active_count = 5  # abnormal but should not go negative
        assert mw.available_slots == 0


# ---------------------------------------------------------------------------
# is_at_capacity property
# ---------------------------------------------------------------------------


class TestIsAtCapacity:
    """is_at_capacity returns True only when active_count >= max_concurrency."""

    def test_not_at_capacity_initially(self):
        mw = _make_middleware(max_concurrency=5)
        assert mw.is_at_capacity is False

    def test_at_capacity_when_equal(self):
        mw = _make_middleware(max_concurrency=5)
        mw._active_count = 5
        assert mw.is_at_capacity is True

    def test_at_capacity_when_over(self):
        mw = _make_middleware(max_concurrency=3)
        mw._active_count = 4
        assert mw.is_at_capacity is True

    def test_not_at_capacity_one_below(self):
        mw = _make_middleware(max_concurrency=5)
        mw._active_count = 4
        assert mw.is_at_capacity is False


# ---------------------------------------------------------------------------
# utilization_rate property
# ---------------------------------------------------------------------------


class TestUtilizationRate:
    """utilization_rate returns correct float between 0.0 and 1.0."""

    def test_utilization_zero_initially(self):
        mw = _make_middleware(max_concurrency=10)
        assert mw.utilization_rate == 0.0

    def test_utilization_half(self):
        mw = _make_middleware(max_concurrency=10)
        mw._active_count = 5
        assert mw.utilization_rate == 0.5

    def test_utilization_full(self):
        mw = _make_middleware(max_concurrency=4)
        mw._active_count = 4
        assert mw.utilization_rate == 1.0

    def test_utilization_zero_when_max_concurrency_is_zero(self):
        """Guards against division by zero when max_concurrency == 0."""
        mw = BatchConcurrencyMiddleware(max_concurrency=0)
        assert mw.utilization_rate == 0.0

    def test_utilization_partial(self):
        mw = _make_middleware(max_concurrency=100)
        mw._active_count = 25
        assert mw.utilization_rate == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# get_stats() method
# ---------------------------------------------------------------------------


class TestGetStats:
    """get_stats() returns correct dictionary."""

    def test_get_stats_keys(self):
        mw = _make_middleware(max_concurrency=10)
        stats = mw.get_stats()
        expected_keys = {
            "max_concurrency",
            "active_count",
            "available_slots",
            "utilization_rate",
            "total_processed",
            "is_at_capacity",
        }
        assert set(stats.keys()) == expected_keys

    def test_get_stats_max_concurrency(self):
        mw = _make_middleware(max_concurrency=20)
        assert mw.get_stats()["max_concurrency"] == 20

    def test_get_stats_active_count(self):
        mw = _make_middleware(max_concurrency=10)
        mw._active_count = 3
        assert mw.get_stats()["active_count"] == 3

    def test_get_stats_available_slots(self):
        mw = _make_middleware(max_concurrency=10)
        mw._active_count = 3
        assert mw.get_stats()["available_slots"] == 7

    def test_get_stats_utilization_rate(self):
        mw = _make_middleware(max_concurrency=10)
        mw._active_count = 5
        assert mw.get_stats()["utilization_rate"] == 0.5

    def test_get_stats_total_processed(self):
        mw = _make_middleware(max_concurrency=10)
        mw._total_processed = 42
        assert mw.get_stats()["total_processed"] == 42

    def test_get_stats_is_at_capacity_false(self):
        mw = _make_middleware(max_concurrency=10)
        assert mw.get_stats()["is_at_capacity"] is False

    def test_get_stats_is_at_capacity_true(self):
        mw = _make_middleware(max_concurrency=5)
        mw._active_count = 5
        assert mw.get_stats()["is_at_capacity"] is True

    def test_get_stats_reflects_release(self):
        mw = _make_middleware(max_concurrency=5)
        mw._active_count = 1
        mw._semaphore._value = 4
        mw.release()
        stats = mw.get_stats()
        assert stats["active_count"] == 0
        assert stats["total_processed"] == 1

    def test_get_stats_zero_when_fresh(self):
        mw = BatchConcurrencyMiddleware()
        stats = mw.get_stats()
        assert stats["active_count"] == 0
        assert stats["total_processed"] == 0
        assert stats["is_at_capacity"] is False


# ---------------------------------------------------------------------------
# Integration: acquire/release + process together
# ---------------------------------------------------------------------------


class TestIntegration:
    """Integration-style tests combining process + acquire/release."""

    async def test_process_then_acquire_release_cycle(self):
        mw = _make_middleware(max_concurrency=3)
        ctx = _make_context()
        # process() sets up context
        await mw.process(ctx)
        assert ctx.max_concurrency == 3

        # acquire/release cycle
        await mw.acquire()
        assert mw._active_count == 1
        mw.release()
        assert mw._active_count == 0
        assert mw._total_processed == 1

    async def test_concurrent_acquires_up_to_limit(self):
        mw = _make_middleware(max_concurrency=3)
        # Acquire up to max
        await mw.acquire()
        await mw.acquire()
        await mw.acquire()
        assert mw._active_count == 3
        assert mw.is_at_capacity is True

        # Release all
        mw.release()
        mw.release()
        mw.release()
        assert mw._active_count == 0
        assert mw._total_processed == 3

    async def test_process_with_no_config_uses_defaults(self):
        mw = BatchConcurrencyMiddleware(max_concurrency=10)
        ctx = _make_context()
        result = await mw.process(ctx)
        assert result.max_concurrency == 10

    async def test_process_updates_batch_latency_ms(self):
        mw = _make_middleware(max_concurrency=5)
        ctx = _make_context()
        ctx.batch_latency_ms = 0.0
        await mw.process(ctx)
        # Even near-zero execution increments latency
        assert ctx.batch_latency_ms >= 0.0

    async def test_capacity_check_uses_both_locked_and_count(self):
        """Capacity check requires BOTH locked() AND active_count >= max."""
        mw = _make_middleware(max_concurrency=5, fail_closed=True)
        ctx = _make_context()

        # locked=True but count < max — should NOT raise
        mw._active_count = 3
        with patch.object(mw._semaphore, "locked", return_value=True):
            result = await mw.process(ctx)
        assert result is not None

        # locked=False and count at max — should NOT raise (locked() is False)
        mw._active_count = 5
        with patch.object(mw._semaphore, "locked", return_value=False):
            result = await mw.process(ctx)
        assert result is not None
