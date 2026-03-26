"""
Batch Auto-Tune Middleware for ACGS-2 Pipeline.

Auto-tunes batch size based on P99 latency.
Extracted from: batch_processor_infra/tuning.py

Constitutional Hash: 608508a9bd224290
"""

import time
from typing import cast

from ...pipeline.context import PipelineContext
from ...pipeline.middleware import BaseMiddleware, MiddlewareConfig
from .context import BatchPipelineContext
from .exceptions import BatchAutoTuneException

BATCH_AUTO_TUNE_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class BatchAutoTuneMiddleware(BaseMiddleware):
    """Auto-tunes batch size based on P99 latency.

    Monitors processing latency and dynamically adjusts batch size
    to maintain target P99 latency. Uses additive increase,
    multiplicative decrease (AIMD) algorithm.

    Example:
        middleware = BatchAutoTuneMiddleware(
            target_p99_ms=100.0,
            adjustment_factor=0.1,
        )
        context = await middleware.process(batch_context)

    Constitutional Hash: 608508a9bd224290
    """

    # Batch size limits
    MIN_BATCH_SIZE = 10
    MAX_BATCH_SIZE = 1000
    DEFAULT_BATCH_SIZE = 100

    def __init__(
        self,
        config: MiddlewareConfig | None = None,
        target_p99_ms: float = 100.0,
        adjustment_factor: float = 0.1,
    ):
        """Initialize batch auto-tune middleware.

        Args:
            config: Middleware configuration (timeout, fail_closed, etc.)
            target_p99_ms: Target P99 latency in milliseconds (default: 100.0)
            adjustment_factor: Size adjustment factor (default: 0.1 = 10%)
        """
        super().__init__(config)
        self._target_p99_ms = target_p99_ms
        self._adjustment_factor = max(0.01, min(adjustment_factor, 0.5))

        # Global tuning state (shared across batches)
        self._current_batch_size = self.DEFAULT_BATCH_SIZE
        self._latency_history: list[float] = []
        self._max_history_size = 100
        self._tuning_enabled = True

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Process auto-tuning based on latency history.

        Steps:
        1. Record current latency measurements
        2. Calculate P99 from history
        3. Adjust batch size if needed
        4. Apply new batch size to context

        Args:
            context: Batch pipeline context with latency data

        Returns:
            Context with updated batch size

        Raises:
            BatchAutoTuneException: If tuning fails
        """
        context = cast(BatchPipelineContext, context)
        start_time = time.perf_counter()

        try:
            # Record latencies from processed items
            for item in context.processed_items:
                if item.processing_time_ms is not None:
                    self._record_latency(item.processing_time_ms)

            # Record overall batch latency
            if context.batch_latency_ms > 0:
                self._record_latency(
                    context.batch_latency_ms / max(len(context.processed_items), 1)
                )

            # Update context with current batch size
            context.current_batch_size = self._current_batch_size
            context.target_p99_ms = self._target_p99_ms

            # Adjust batch size if we have enough data
            if self._should_adjust() and self._tuning_enabled:
                p99 = self._calculate_p99()
                new_size = self._update_batch_size(p99)
                self._current_batch_size = new_size
                context.current_batch_size = new_size

        except BATCH_AUTO_TUNE_ERRORS as e:
            error_msg = f"Auto-tuning failed: {e}"
            if self.config.fail_closed:
                raise BatchAutoTuneException(
                    message=error_msg,
                    target_p99_ms=self._target_p99_ms,
                ) from e

            # Non-fatal: just log and continue
            context.warnings = getattr(context, "warnings", []) + [error_msg]

        # Record metrics
        duration_ms = (time.perf_counter() - start_time) * 1000
        context.batch_latency_ms += duration_ms

        context = await self._call_next(context)
        return context

    def _record_latency(self, latency_ms: float) -> None:
        """Record a latency measurement.

        Args:
            latency_ms: Latency in milliseconds
        """
        self._latency_history.append(latency_ms)

        # Keep history bounded
        if len(self._latency_history) > self._max_history_size:
            self._latency_history = self._latency_history[-self._max_history_size :]

    def _should_adjust(self) -> bool:
        """Check if we have enough data to adjust batch size.

        Returns:
            True if adjustment should occur
        """
        # Need at least 10 measurements
        return len(self._latency_history) >= 10

    def _calculate_p99(self) -> float:
        """Calculate P99 latency from history.

        Returns:
            P99 latency in milliseconds
        """
        if not self._latency_history:
            return 0.0

        sorted_latencies = sorted(self._latency_history)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    def _update_batch_size(self, latency_ms: float) -> int:
        """Update batch size based on P99 latency.

        Uses AIMD (Additive Increase, Multiplicative Decrease):
        - If latency > target: decrease batch size (multiplicative)
        - If latency < target: increase batch size (additive)

        Args:
            latency_ms: Current P99 latency

        Returns:
            New batch size
        """
        current = self._current_batch_size

        if latency_ms > self._target_p99_ms:
            # Latency too high - decrease batch size (multiplicative)
            decrease = int(current * self._adjustment_factor)
            new_size = max(self.MIN_BATCH_SIZE, current - max(decrease, 1))
        elif latency_ms < self._target_p99_ms * 0.8:
            # Latency well below target - increase batch size (additive)
            increase = max(1, int(current * self._adjustment_factor))
            new_size = min(self.MAX_BATCH_SIZE, current + increase)
        else:
            # Within acceptable range - no change
            new_size = current

        return new_size

    @property
    def current_batch_size(self) -> int:
        """Return current batch size."""
        return self._current_batch_size

    @property
    def target_p99_ms(self) -> float:
        """Return target P99 latency."""
        return self._target_p99_ms

    @property
    def current_p99_ms(self) -> float:
        """Return current P99 latency."""
        return self._calculate_p99()

    @property
    def latency_history(self) -> list[float]:
        """Return latency history (copy)."""
        return self._latency_history.copy()

    @property
    def tuning_enabled(self) -> bool:
        """Return whether auto-tuning is enabled."""
        return self._tuning_enabled

    def set_tuning_enabled(self, enabled: bool) -> None:
        """Enable or disable auto-tuning.

        Args:
            enabled: Whether tuning should be enabled
        """
        self._tuning_enabled = enabled

    def reset(self) -> None:
        """Reset tuning state to defaults."""
        self._current_batch_size = self.DEFAULT_BATCH_SIZE
        self._latency_history.clear()

    def get_stats(self) -> dict:
        """Return auto-tuning statistics.

        Returns:
            Dictionary with tuning stats
        """
        return {
            "current_batch_size": self._current_batch_size,
            "target_p99_ms": self._target_p99_ms,
            "current_p99_ms": self.current_p99_ms,
            "latency_measurements": len(self._latency_history),
            "tuning_enabled": self._tuning_enabled,
            "min_batch_size": self.MIN_BATCH_SIZE,
            "max_batch_size": self.MAX_BATCH_SIZE,
        }
