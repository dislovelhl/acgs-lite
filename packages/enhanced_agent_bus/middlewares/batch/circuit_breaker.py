"""
Batch Circuit Breaker Middleware for ACGS-2 Pipeline.

Provides circuit breaker protection for batch processing to prevent
cascading failures and allow auto-recovery.

Constitutional Hash: 608508a9bd224290
"""

import time
from typing import cast

from enhanced_agent_bus.validators import ValidationResult

from ...batch_models import BatchResponse, BatchResponseItem
from ...circuit_breaker.batch import CircuitBreaker, CircuitBreakerConfig
from ...pipeline.context import PipelineContext
from ...pipeline.middleware import BaseMiddleware, MiddlewareConfig
from .context import BatchPipelineContext
from .exceptions import BatchProcessingException

BATCH_CIRCUIT_BREAKER_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class BatchCircuitBreakerMiddleware(BaseMiddleware):
    """Circuit breaker middleware for batch processing.

    Prevents cascading failures by:
    - Tracking batch processing success/failure rates
    - Opening circuit when failure threshold exceeded
    - Auto-resetting after cooldown period (HALF_OPEN -> CLOSED)
    - Blocking requests when circuit is open

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit tripped, requests blocked with fallback
    - HALF_OPEN: Testing recovery with limited requests

    Auto-reset behavior:
    - After cooldown period, circuit moves to HALF_OPEN
    - If success rate >= threshold, circuit closes
    - If any failure in HALF_OPEN, circuit reopens

    Example:
        middleware = BatchCircuitBreakerMiddleware(
            failure_threshold=0.5,
            cooldown_period=30.0,
            minimum_requests=10,
        )
        context = await middleware.process(batch_context)

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        config: MiddlewareConfig | None = None,
        failure_threshold: float = 0.5,
        cooldown_period: float = 30.0,
        minimum_requests: int = 10,
        success_threshold: float = 0.5,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        """Initialize circuit breaker middleware.

        Args:
            config: Middleware configuration
            failure_threshold: Failure rate to trip circuit (0.0-1.0)
            cooldown_period: Seconds before auto-reset attempt
            minimum_requests: Min requests before evaluating
            success_threshold: Success rate needed to close circuit from half-open
            circuit_breaker: Optional pre-configured circuit breaker
        """
        super().__init__(config)

        if circuit_breaker:
            self._circuit_breaker = circuit_breaker
        else:
            cb_config = CircuitBreakerConfig(
                failure_threshold=failure_threshold,
                cooldown_period=cooldown_period,
                minimum_requests=minimum_requests,
                success_threshold=success_threshold,
            )
            self._circuit_breaker = CircuitBreaker(cb_config)

        self._fallback_response: BatchResponseItem | None = None

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Process batch with circuit breaker protection.

        Args:
            context: Batch pipeline context

        Returns:
            Context with processed or fallback response

        Raises:
            BatchProcessingException: If circuit open and fail_closed
        """
        context = cast(BatchPipelineContext, context)
        start_time = time.perf_counter()

        # Check if circuit allows request
        circuit_open = not await self._circuit_breaker.allow_request()

        if circuit_open:
            # Circuit is open - record rejection metric
            if "circuit_rejections" not in context.metadata:
                context.metadata["circuit_rejections"] = 0
            context.metadata["circuit_rejections"] += 1

            error_msg = (
                f"Circuit breaker is OPEN - batch rejected. "
                f"Auto-reset after {self._circuit_breaker.config.cooldown_period}s cooldown."
            )

            if self.config.fail_closed:
                raise BatchProcessingException(
                    message=error_msg,
                    error_code="CIRCUIT_OPEN",
                )

            # Return fallback response
            fallback = self._create_fallback_response(context)
            context.batch_response = fallback
            context.warnings.append(error_msg)
            context.metadata["circuit_state"] = "OPEN"
            context.metadata["circuit_auto_reset_pending"] = True

            # Continue to next middleware with fallback
            duration_ms = (time.perf_counter() - start_time) * 1000
            context.batch_latency_ms += duration_ms
            context = await self._call_next(context)
            return context

        # Circuit allows request - record state
        context.metadata["circuit_state"] = self._circuit_breaker.state.value

        try:
            # Process through next middleware
            context = await self._call_next(context)

            # Record success or failure based on result
            await self._record_result(cast(BatchPipelineContext, context))

        except BATCH_CIRCUIT_BREAKER_ERRORS as e:
            # Record failure
            await self._circuit_breaker.record_failure()

            # Re-raise if fail_closed
            if self.config.fail_closed:
                raise

            # Otherwise, set early result with error
            batch_ctx = cast(BatchPipelineContext, context)
            batch_ctx.set_early_result(
                ValidationResult(
                    is_valid=False,
                    errors=[f"Circuit breaker recorded failure: {e}"],
                )
            )

        # Update circuit state in metadata
        cast(BatchPipelineContext, context).metadata["circuit_state"] = (
            self._circuit_breaker.state.value
        )
        cast(BatchPipelineContext, context).metadata["circuit_failure_count"] = (
            self._circuit_breaker.failure_count
        )
        cast(BatchPipelineContext, context).metadata["circuit_success_count"] = (
            self._circuit_breaker.success_count
        )

        duration_ms = (time.perf_counter() - start_time) * 1000
        cast(BatchPipelineContext, context).batch_latency_ms += duration_ms

        return context

    async def _record_result(self, context: BatchPipelineContext) -> None:
        """Record success or failure based on batch response.

        Args:
            context: Pipeline context with response
        """
        if not context.batch_response:
            # No response - treat as failure
            await self._circuit_breaker.record_failure()
            return

        # Calculate success rate from response
        total = len(context.batch_response.items)
        if total == 0:
            # Empty batch - treat as neutral/success
            await self._circuit_breaker.record_success()
            return

        successful = sum(1 for item in context.batch_response.items if item.success)
        success_rate = successful / total

        # Record based on majority success
        if success_rate >= 0.5:
            await self._circuit_breaker.record_success()
        else:
            await self._circuit_breaker.record_failure()

    def _create_fallback_response(self, context: BatchPipelineContext) -> BatchResponse:
        """Create fallback response when circuit is open.

        Args:
            context: Pipeline context

        Returns:
            Fallback batch response
        """
        batch_id = context.batch_request.batch_id if context.batch_request else "circuit_open"

        # Create error response items for all pending items
        fallback_items = []
        for item in context.batch_items:
            fallback_items.append(
                BatchResponseItem.create_error(
                    request_id=item.request_id,
                    error_code="CIRCUIT_OPEN",
                    error_message=(
                        "Request blocked - circuit breaker is OPEN. "
                        "Auto-reset scheduled after cooldown."
                    ),
                )
            )

        return BatchResponse(
            batch_id=batch_id,
            success=False,
            items=fallback_items,
            errors=["Circuit breaker is OPEN - using fallback response"],
        )

    def get_circuit_state(self) -> str:
        """Get current circuit breaker state.

        Returns:
            Circuit state string (CLOSED, OPEN, HALF_OPEN)
        """
        return self._circuit_breaker.state.value

    def get_metrics(self) -> dict:
        """Get circuit breaker metrics.

        Returns:
            Dictionary with circuit breaker metrics
        """
        return {
            "state": self._circuit_breaker.state.value,
            "failure_count": self._circuit_breaker.failure_count,
            "success_count": self._circuit_breaker.success_count,
            "total_requests": self._circuit_breaker.total_requests,
            "failure_threshold": self._circuit_breaker.config.failure_threshold,
            "cooldown_period": self._circuit_breaker.config.cooldown_period,
        }

    async def manual_reset(self) -> None:
        """Manually reset the circuit breaker.

        Use for operational recovery when auto-reset is insufficient.
        """
        from ...circuit_breaker.enums import CircuitState

        self._circuit_breaker.state = CircuitState.CLOSED
        self._circuit_breaker.failure_count = 0
        self._circuit_breaker.success_count = 0
        self._circuit_breaker.total_requests = 0
        self._circuit_breaker.half_open_success_count = 0
