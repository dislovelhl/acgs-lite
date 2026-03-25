"""
Worker Pool for Parallel Batch Processing in ACGS-2.

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

from enhanced_agent_bus.models import (
    BatchItemStatus,
    BatchRequestItem,
    BatchResponseItem,
)
from enhanced_agent_bus.observability.structured_logging import get_logger
from enhanced_agent_bus.validators import ValidationResult

logger = get_logger(__name__)
BATCH_PROCESSING_RETRY_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    asyncio.TimeoutError,
)
BATCH_WORKER_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    asyncio.TimeoutError,
)


class WorkerPool:
    def __init__(
        self,
        max_concurrency: int = 100,
        item_timeout_ms: int = 30000,
        max_retries: int = 1,
        retry_base_delay: float = 0.1,
        retry_exponential_base: float = 2.0,
        max_failures: int = 50,
    ):
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._item_timeout_ms = max(1, int(item_timeout_ms))
        self._circuit_breaker_tripped = False
        self._failure_count = 0
        self._max_failures = max(1, int(max_failures))
        self._max_retries = max(0, int(max_retries))
        self._retry_base_delay = max(0.0, float(retry_base_delay))
        self._retry_exponential_base = max(1.0, float(retry_exponential_base))

    @staticmethod
    def _build_validation_failure_response(
        item: BatchRequestItem,
        result: ValidationResult,
        latency_ms: float,
    ) -> BatchResponseItem:
        error_message = "; ".join(result.errors) if result.errors else "Validation failed"
        return BatchResponseItem(
            request_id=item.request_id,
            status=BatchItemStatus.FAILED.value,
            valid=False,
            validation_result={"decision": getattr(result, "decision", None)},
            error_code="VALIDATION_FAILED",
            error_message=error_message,
            processing_time_ms=latency_ms,
            constitutional_validated=True,
        )

    @staticmethod
    def _build_exception_response(
        item: BatchRequestItem,
        error: BaseException | None,
        latency_ms: float,
    ) -> BatchResponseItem:
        if isinstance(error, asyncio.TimeoutError):
            return BatchResponseItem.create_error(
                request_id=item.request_id,
                error_code="TIMEOUT_ERROR",
                error_message="Item processing timeout",
                processing_time_ms=latency_ms,
            )

        return BatchResponseItem.create_error(
            request_id=item.request_id,
            error_code="PROCESSING_EXCEPTION",
            error_message=str(error or "Item processing failed"),
            processing_time_ms=latency_ms,
        )

    async def process_item(
        self,
        item: BatchRequestItem,
        process_func: Callable[[BatchRequestItem], Awaitable[ValidationResult]],
    ) -> BatchResponseItem:
        if self._circuit_breaker_tripped:
            return BatchResponseItem(
                request_id=item.request_id,
                status=BatchItemStatus.FAILED.value,
                valid=False,
                error_message="Circuit breaker tripped",
            )

        start_time = time.time()
        async with self._semaphore:
            try:
                max_retries = self._max_retries
                last_error = None

                for attempt in range(max_retries + 1):
                    try:
                        result = await asyncio.wait_for(
                            process_func(item),
                            timeout=self._item_timeout_ms / 1000.0,
                        )
                        self._failure_count = 0

                        latency_ms = (time.time() - start_time) * 1000.0
                        # Map to BatchItemStatus for metrics compatibility
                        if not result.is_valid:
                            return self._build_validation_failure_response(
                                item=item,
                                result=result,
                                latency_ms=latency_ms,
                            )

                        return BatchResponseItem(
                            request_id=item.request_id,
                            status=BatchItemStatus.SUCCESS.value,
                            valid=True,
                            validation_result={"decision": result.decision}
                            if hasattr(result, "decision")
                            else None,
                            processing_time_ms=latency_ms,
                            constitutional_validated=True,
                        )
                    except BATCH_PROCESSING_RETRY_ERRORS as e:
                        last_error = e
                        if attempt < max_retries:
                            await asyncio.sleep(
                                self._retry_base_delay * (self._retry_exponential_base**attempt)
                            )

                self._failure_count += 1
                if self._failure_count >= self._max_failures:
                    self._circuit_breaker_tripped = True
                    logger.critical("Batch processor circuit breaker TRIPPED")

                return self._build_exception_response(
                    item=item,
                    error=last_error,
                    latency_ms=(time.time() - start_time) * 1000.0,
                )
            except BATCH_WORKER_ERRORS as e:
                logger.error(f"Worker failed to process item: {e}")
                return self._build_exception_response(
                    item=item,
                    error=e,
                    latency_ms=(time.time() - start_time) * 1000.0,
                )

    def reset_circuit_breaker(self):
        self._circuit_breaker_tripped = False
        self._failure_count = 0
