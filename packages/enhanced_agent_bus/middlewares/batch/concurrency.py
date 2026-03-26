"""
Batch Concurrency Middleware for ACGS-2 Pipeline.

Controls concurrent batch processing.
Extracted from: batch_processor_infra/workers.py

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import time
from typing import cast

from enhanced_agent_bus.validators import ValidationResult

from ...pipeline.context import PipelineContext
from ...pipeline.middleware import BaseMiddleware, MiddlewareConfig
from .context import BatchPipelineContext
from .exceptions import BatchConcurrencyException


class BatchConcurrencyMiddleware(BaseMiddleware):
    """Controls concurrent batch processing.

    Uses asyncio.Semaphore for concurrency control to prevent
    resource exhaustion during batch processing.

    Example:
        middleware = BatchConcurrencyMiddleware(max_concurrency=100)
        context = await middleware.process(batch_context)

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: MiddlewareConfig | None = None,
        max_concurrency: int = 100,
    ):
        """Initialize batch concurrency middleware.

        Args:
            config: Middleware configuration (timeout, fail_closed, etc.)
            max_concurrency: Maximum concurrent operations (default: 100)
        """
        super().__init__(config)
        self._max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._active_count = 0
        self._total_processed = 0

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Process concurrency control setup.

        Sets up the semaphore and concurrency metadata on the context.
        Actual concurrency control happens during item processing.

        Args:
            context: Batch pipeline context

        Returns:
            Context with concurrency settings

        Raises:
            BatchConcurrencyException: If concurrency setup fails
        """
        context = cast(BatchPipelineContext, context)
        start_time = time.perf_counter()

        # Set max concurrency on context
        context.max_concurrency = self._max_concurrency

        # Check if we can acquire the semaphore (quick check)
        if self._semaphore.locked() and self._active_count >= self._max_concurrency:
            error_msg = (
                f"Maximum concurrency ({self._max_concurrency}) reached, batch processing deferred"
            )
            if self.config.fail_closed:
                raise BatchConcurrencyException(
                    message=error_msg,
                    max_concurrency=self._max_concurrency,
                    current_count=self._active_count,
                )
            context.set_early_result(
                ValidationResult(
                    is_valid=False,
                    errors=[error_msg],
                    metadata={
                        "validation_stage": "concurrency",
                        "max_concurrency": self._max_concurrency,
                        "current_count": self._active_count,
                    },
                )
            )
            context = await self._call_next(context)
            return context

        # Record metrics
        duration_ms = (time.perf_counter() - start_time) * 1000
        context.batch_latency_ms += duration_ms

        context = await self._call_next(context)
        return context

    async def acquire(self) -> None:
        """Acquire concurrency semaphore.

        Should be called before processing each item.
        """
        await self._semaphore.acquire()
        self._active_count += 1

    def release(self) -> None:
        """Release concurrency semaphore.

        Should be called after processing each item.
        """
        self._semaphore.release()
        self._active_count -= 1
        self._total_processed += 1

    @property
    def available_slots(self) -> int:
        """Return number of available concurrency slots."""
        return max(0, self._max_concurrency - self._active_count)

    @property
    def is_at_capacity(self) -> bool:
        """Check if concurrency is at capacity."""
        return self._active_count >= self._max_concurrency

    @property
    def utilization_rate(self) -> float:
        """Return current utilization rate (0.0 - 1.0)."""
        if self._max_concurrency == 0:
            return 0.0
        return self._active_count / self._max_concurrency

    def get_stats(self) -> dict:
        """Return concurrency statistics.

        Returns:
            Dictionary with concurrency stats
        """
        return {
            "max_concurrency": self._max_concurrency,
            "active_count": self._active_count,
            "available_slots": self.available_slots,
            "utilization_rate": self.utilization_rate,
            "total_processed": self._total_processed,
            "is_at_capacity": self.is_at_capacity,
        }
