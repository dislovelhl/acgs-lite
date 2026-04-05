"""
ACGS-2 Enhanced Agent Bus - Batch Message Processor
Constitutional Hash: 608508a9bd224290

Refactored BatchMessageProcessor that delegates to the infra components.
"""

import time
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING

try:
    from enhanced_agent_bus._compat.types import (
        JSONDict,
        JSONValue,
    )
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]
    JSONValue = object  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .batch_processor_infra.orchestrator import BatchProcessorOrchestrator
from .models import (
    AgentMessage,
    BatchRequest,
    BatchRequestItem,
    BatchResponse,
    MessageType,
    Priority,
)
from .validators import ValidationResult

if TYPE_CHECKING:
    from .interfaces import MessageProcessorProtocol

logger = get_logger(__name__)
_batch_processor_instance = None


def get_batch_processor() -> "BatchMessageProcessor":
    """
    Get the global batch processor singleton.
    Constitutional Hash: 608508a9bd224290
    """
    global _batch_processor_instance
    if _batch_processor_instance is None:
        try:
            from .message_processor import MessageProcessor

            _batch_processor_instance = BatchMessageProcessor(message_processor=MessageProcessor())  # type: ignore[arg-type]
        except (ImportError, RuntimeError, ValueError, TypeError) as e:
            logger.warning(f"Failed to initialize default message processor: {e}")
            _batch_processor_instance = BatchMessageProcessor(message_processor=None)

    return _batch_processor_instance


def reset_batch_processor() -> None:
    """
    Reset the global batch processor singleton.
    Constitutional Hash: 608508a9bd224290
    """
    global _batch_processor_instance
    _batch_processor_instance = None


class BatchMessageProcessor:
    """
    Refactored BatchMessageProcessor using modular components.
    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, **kwargs: JSONValue) -> None:
        # Type-safe extraction from kwargs (cast from JSONValue to proper types)
        _message_processor = kwargs.get("message_processor")
        self._message_processor: MessageProcessorProtocol | None = (
            _message_processor
            if _message_processor is not None
            and not isinstance(_message_processor, (str, int, float, dict, list))
            else None  # type: ignore[assignment]
        )
        _validator = kwargs.get("validator")
        self._custom_validator: Callable[[BatchRequestItem], tuple[bool, JSONDict]] | None = (
            _validator if callable(_validator) else None  # type: ignore[assignment]
        )
        _max_concurrency_raw = kwargs.get("max_concurrency", 100)
        _max_concurrency = (
            int(_max_concurrency_raw) if isinstance(_max_concurrency_raw, (int, float)) else 100
        )

        # Auto-tuning configuration (with safe type casts)
        _auto_tune = kwargs.get("auto_tune_batch_size", False)
        self.auto_tune_batch_size: bool = (
            bool(_auto_tune) if isinstance(_auto_tune, (bool, int)) else False
        )
        _max_batch = kwargs.get("max_batch_size", 1000)
        self.max_batch_size: int = int(_max_batch) if isinstance(_max_batch, (int, float)) else 1000
        _min_batch = kwargs.get("min_batch_size", 1)
        self.min_batch_size: int = int(_min_batch) if isinstance(_min_batch, (int, float)) else 1
        _target_p99 = kwargs.get("target_p99_latency_ms", 10.0)
        self.target_p99_latency_ms: float = (
            float(_target_p99) if isinstance(_target_p99, (int, float)) else 10.0
        )
        _adj_factor = kwargs.get("auto_tune_adjustment_factor", 0.1)
        self.auto_tune_adjustment_factor: float = (
            float(_adj_factor) if isinstance(_adj_factor, (int, float)) else 0.1
        )
        _hist_size = kwargs.get("auto_tune_history_size", 10)
        self.auto_tune_history_size: int = (
            int(_hist_size) if isinstance(_hist_size, (int, float)) else 10
        )

        # Internal state for auto-tuning
        self._recommended_batch_size: int = self.max_batch_size
        self._latency_history: deque[float] = deque(maxlen=self.auto_tune_history_size)
        self._total_adjustments: int = 0
        self._total_auto_tune_adjustments: int = 0  # Alias for test compatibility

        # Store config for test compatibility
        self._max_concurrency: int = _max_concurrency
        _item_timeout = kwargs.get("item_timeout_ms")
        if not isinstance(_item_timeout, (int, float)):
            legacy_item_timeout = kwargs.get("item_timeout")
            if isinstance(legacy_item_timeout, (int, float)):
                _item_timeout = float(legacy_item_timeout) * 1000.0
            else:
                _item_timeout = 30000
        self._item_timeout_ms: int = (
            int(_item_timeout) if isinstance(_item_timeout, (int, float)) else 30000
        )

        # Error handling and retry configuration
        _include_traces = kwargs.get("include_stack_traces", True)
        self._include_stack_traces: bool = (
            bool(_include_traces) if isinstance(_include_traces, (bool, int)) else True
        )
        _max_retries = kwargs.get("max_retries", 0)
        self._max_retries: int = int(_max_retries) if isinstance(_max_retries, (int, float)) else 0
        _retry_base = kwargs.get("retry_base_delay", 0.1)
        self._retry_base_delay: float = (
            float(_retry_base) if isinstance(_retry_base, (int, float)) else 0.1
        )
        _retry_max = kwargs.get("retry_max_delay", 10.0)
        self._retry_max_delay: float = (
            float(_retry_max) if isinstance(_retry_max, (int, float)) else 10.0
        )
        _retry_exp = kwargs.get("retry_exponential_base", 2.0)
        self._retry_exponential_base: float = (
            float(_retry_exp) if isinstance(_retry_exp, (int, float)) else 2.0
        )

        self._orchestrator = BatchProcessorOrchestrator(
            max_concurrency=_max_concurrency,
            item_timeout_ms=self._item_timeout_ms,
            max_retries=self._max_retries,
            retry_base_delay=self._retry_base_delay,
            retry_exponential_base=self._retry_exponential_base,
        )

        # Circuit breaker configuration
        _cb_enabled = kwargs.get("circuit_breaker_enabled", False)
        self._circuit_breaker_enabled: bool = (
            bool(_cb_enabled) if isinstance(_cb_enabled, (bool, int)) else False
        )
        _cb_threshold = kwargs.get("circuit_breaker_threshold", 0.5)
        self._circuit_breaker_threshold: float = (
            float(_cb_threshold) if isinstance(_cb_threshold, (int, float)) else 0.5
        )
        _cb_cooldown = kwargs.get("circuit_breaker_cooldown", 30.0)
        self._circuit_breaker_cooldown: float = (
            float(_cb_cooldown) if isinstance(_cb_cooldown, (int, float)) else 30.0
        )
        self._circuit_breaker_state: str = "closed"  # closed, open, half_open

    @property
    def max_concurrency(self) -> int:
        """Get the max concurrency setting."""
        return self._max_concurrency

    @property
    def item_timeout_ms(self) -> int:
        """Get the item timeout in milliseconds."""
        return self._item_timeout_ms

    @property
    def include_stack_traces(self) -> bool:
        """Get whether stack traces are included in error responses."""
        return self._include_stack_traces

    @property
    def max_retries(self) -> int:
        """Get the maximum number of retries for transient errors."""
        return self._max_retries

    @property
    def retry_base_delay(self) -> float:
        """Get the base delay between retries in seconds."""
        return self._retry_base_delay

    @property
    def retry_max_delay(self) -> float:
        """Get the maximum delay between retries in seconds."""
        return self._retry_max_delay

    @property
    def retry_exponential_base(self) -> float:
        """Get the exponential base for retry backoff."""
        return self._retry_exponential_base

    @property
    def circuit_breaker_enabled(self) -> bool:
        """Get whether circuit breaker is enabled."""
        return self._circuit_breaker_enabled

    @property
    def circuit_breaker_threshold(self) -> float:
        """Get the failure rate threshold for opening circuit breaker."""
        return self._circuit_breaker_threshold

    @property
    def circuit_breaker_cooldown(self) -> float:
        """Get the cooldown period in seconds before attempting to reset circuit."""
        return self._circuit_breaker_cooldown

    @property
    def circuit_breaker_state(self) -> str:
        """Get the current circuit breaker state (closed, open, half_open)."""
        return self._circuit_breaker_state

    def get_circuit_state(self) -> str:
        """Get the current circuit breaker state for external queries."""
        return self._circuit_breaker_state

    async def process_batch(self, batch_request: BatchRequest) -> BatchResponse:
        """
        Process a batch of messages.
        """

        async def _process_item(item: BatchRequestItem) -> ValidationResult:
            # Use custom validator if provided
            if self._custom_validator:
                try:
                    is_valid, result_dict = self._custom_validator(item)
                    from .models import MessageStatus

                    return ValidationResult(
                        is_valid=is_valid,
                        status=MessageStatus.VALIDATED if is_valid else MessageStatus.FAILED,
                        decision=str(result_dict) if is_valid else None,  # type: ignore[arg-type]
                        errors=(
                            [result_dict.get("error", "Validation failed")] if not is_valid else []
                        ),
                    )
                except (RuntimeError, ValueError, TypeError, KeyError, AttributeError) as e:
                    logger.warning(f"Custom validator error: {e}")
                    from .models import MessageStatus

                    return ValidationResult(
                        is_valid=False,
                        status=MessageStatus.FAILED,
                        errors=[str(e)],
                    )

            # Use message processor for standard processing
            if not self._message_processor:
                from .message_processor import MessageProcessor

                self._message_processor = MessageProcessor()

            # Convert BatchRequestItem to AgentMessage for processing
            try:
                # Map priority int to Priority enum
                priority_map = {
                    0: Priority.LOW,
                    1: Priority.MEDIUM,
                    2: Priority.HIGH,
                    3: Priority.CRITICAL,
                }
                priority = priority_map.get(item.priority, Priority.MEDIUM)

                # Create AgentMessage from BatchRequestItem
                agent_msg = AgentMessage(
                    content=item.content,
                    from_agent=item.from_agent,
                    to_agent=item.to_agent,
                    message_type=(
                        MessageType.GOVERNANCE_REQUEST
                        if item.message_type == "governance_request"
                        else MessageType.COMMAND
                    ),
                    tenant_id=item.tenant_id,
                    priority=priority,
                    metadata=item.metadata,
                )
                return await self._message_processor.process(agent_msg)
            except (RuntimeError, ValueError, TypeError, KeyError, AttributeError) as e:
                # Return a failed validation result on error
                logger.warning(f"Batch item processing error: {e}")
                from .models import MessageStatus

                return ValidationResult(
                    is_valid=False,
                    status=MessageStatus.FAILED,
                    errors=[str(e)],
                )

        start_time = time.perf_counter()
        response = await self._orchestrator.process_batch(batch_request, _process_item)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Update auto-tuning with observed latency
        if self.auto_tune_batch_size:
            batch_size = len(batch_request.items)
            # Use per-item latency as the P99 approximation
            per_item_latency = elapsed_ms / max(batch_size, 1)
            self._update_batch_size_recommendation(batch_size, per_item_latency)

        return response

    def get_metrics(self) -> JSONDict:
        """Get current metrics including auto-tuning fields."""
        metrics = self._orchestrator.get_metrics()

        # Add auto-tuning metrics as flat fields
        metrics["auto_tune_batch_size"] = self.auto_tune_batch_size
        metrics["recommended_batch_size"] = self._recommended_batch_size
        metrics["target_p99_latency_ms"] = self.target_p99_latency_ms
        metrics["total_adjustments"] = self._total_adjustments
        metrics["latency_history_size"] = len(self._latency_history)

        return metrics

    def reset_metrics(self) -> None:
        """Reset metrics."""
        self._orchestrator.reset_metrics()

    def clear_cache(self) -> None:
        """Clear cache."""
        self._orchestrator.clear_cache()

    def get_cache_size(self) -> int:
        """Get cache size."""
        return self._orchestrator.get_cache_size()

    def get_recommended_batch_size(self) -> int:
        """Get the recommended batch size based on auto-tuning.

        Constitutional Hash: 608508a9bd224290
        """
        if not self.auto_tune_batch_size:
            return self.max_batch_size
        return self._recommended_batch_size

    def _update_batch_size_recommendation(
        self, batch_size: int, p99_latency_ms: float | None
    ) -> None:
        """Update batch size recommendation based on observed latency.

        Constitutional Hash: 608508a9bd224290
        """
        if not self.auto_tune_batch_size or p99_latency_ms is None:
            return

        self._latency_history.append(p99_latency_ms)

        # Need at least 3 samples before adjusting
        if len(self._latency_history) < 3:
            return

        # Calculate average P99 latency
        avg_latency = sum(self._latency_history) / len(self._latency_history)

        # High latency threshold (> 1.5x target)
        high_threshold = self.target_p99_latency_ms * 1.5
        # Low latency threshold (< 0.5x target)
        low_threshold = self.target_p99_latency_ms * 0.5

        if avg_latency > high_threshold:
            # Decrease batch size
            new_size = int(self._recommended_batch_size * (1 - self.auto_tune_adjustment_factor))
            self._recommended_batch_size = max(self.min_batch_size, new_size)
            self._total_adjustments += 1
        elif avg_latency < low_threshold:
            # Increase batch size
            new_size = int(self._recommended_batch_size * (1 + self.auto_tune_adjustment_factor))
            self._recommended_batch_size = min(self.max_batch_size, new_size)
            self._total_adjustments += 1

    def get_auto_tune_stats(self) -> JSONDict:
        """Get auto-tuning statistics.

        Constitutional Hash: 608508a9bd224290
        """
        avg_latency = None
        if self._latency_history:
            avg_latency = sum(self._latency_history) / len(self._latency_history)

        return {
            "enabled": self.auto_tune_batch_size,
            "target_p99_latency_ms": self.target_p99_latency_ms,
            "recommended_batch_size": self._recommended_batch_size,
            "total_adjustments": self._total_adjustments,
            "latency_history_size": len(self._latency_history),
            "avg_p99_latency_ms": avg_latency,
            "min_batch_size": self.min_batch_size,
            "max_batch_size": self.max_batch_size,
        }
