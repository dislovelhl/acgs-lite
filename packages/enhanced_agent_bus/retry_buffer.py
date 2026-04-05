"""
ACGS-2 Enhanced Agent Bus - Retry Buffer
Constitutional Hash: 608508a9bd224290

Retry buffer for Kafka message delivery with exponential backoff.
Split from circuit_breaker_clients.py for improved maintainability.
"""

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
RETRY_DELIVERY_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)


@dataclass
class BufferedMessage:
    """A message buffered for retry when Kafka is unavailable."""

    id: str
    topic: str
    value: JSONDict
    key: bytes | None
    buffered_at: float
    retry_count: int = 0
    max_retries: int = 5
    tenant_id: str | None = None


class RetryBuffer:
    """
    Thread-safe retry buffer for Kafka messages.

    Implements bounded buffer with exponential backoff retry.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        max_size: int = 10000,
        base_retry_delay: float = 1.0,
        max_retry_delay: float = 60.0,
    ):
        self.max_size = max_size
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay
        self._buffer: deque[BufferedMessage] = deque(maxlen=max_size)
        self._lock = asyncio.Lock()
        self._processing = False
        self._metrics = {
            "buffered_count": 0,
            "delivered_count": 0,
            "failed_count": 0,
            "dropped_count": 0,
        }

    async def add(self, message: BufferedMessage) -> bool:
        """Add a message to the retry buffer."""
        async with self._lock:
            if len(self._buffer) >= self.max_size:
                # Buffer full, drop oldest message
                dropped = self._buffer.popleft()
                self._metrics["dropped_count"] += 1
                logger.warning(
                    f"[{CONSTITUTIONAL_HASH}] Retry buffer full, dropped message {dropped.id}"
                )

            self._buffer.append(message)
            self._metrics["buffered_count"] += 1
            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Buffered message {message.id} for retry "
                f"(buffer_size={len(self._buffer)})"
            )
            return True

    async def process(
        self, producer_func: Callable[[str, JSONDict, bytes | None], object]
    ) -> JSONDict:
        """
        Process all buffered messages using the provided producer function.

        Args:
            producer_func: Async function(topic, value, key) to send messages

        Returns:
            Dictionary with counts of delivered, failed, and remaining messages
        """
        async with self._lock:
            if self._processing:
                return {"status": "already_processing"}
            self._processing = True

        results = {"delivered": 0, "failed": 0, "remaining": 0}

        try:
            messages_to_retry = []

            while self._buffer:
                msg = self._buffer.popleft()

                # Check if max retries exceeded
                if msg.retry_count >= msg.max_retries:
                    logger.error(
                        f"[{CONSTITUTIONAL_HASH}] Message {msg.id} exceeded max retries, discarding"
                    )
                    self._metrics["failed_count"] += 1
                    results["failed"] += 1
                    continue

                # Calculate exponential backoff
                delay = min(
                    self.base_retry_delay * (2**msg.retry_count),
                    self.max_retry_delay,
                )

                # Add jitter to prevent thundering herd
                loop_time_fraction = asyncio.get_running_loop().time() % 1
                delay += delay * 0.1 * (0.5 - loop_time_fraction)

                await asyncio.sleep(delay)

                try:
                    await producer_func(msg.topic, msg.value, msg.key)
                    self._metrics["delivered_count"] += 1
                    results["delivered"] += 1
                    logger.info(
                        f"[{CONSTITUTIONAL_HASH}] Successfully delivered buffered message {msg.id}"
                    )
                except RETRY_DELIVERY_ERRORS as e:
                    msg.retry_count += 1
                    messages_to_retry.append(msg)
                    logger.warning(
                        f"[{CONSTITUTIONAL_HASH}] Retry failed for message {msg.id}: {e}"
                    )

            # Re-add failed messages to buffer or count as failed if exceeded retries
            for msg in messages_to_retry:
                if msg.retry_count >= msg.max_retries:
                    # Message exceeded max retries, count as failed
                    logger.error(
                        f"[{CONSTITUTIONAL_HASH}] Message {msg.id} exceeded max retries, discarding"
                    )
                    self._metrics["failed_count"] += 1
                    results["failed"] += 1
                else:
                    self._buffer.append(msg)
                    results["remaining"] += 1

        finally:
            async with self._lock:
                self._processing = False

        return results

    def get_size(self) -> int:
        """Get current buffer size."""
        return len(self._buffer)

    def get_metrics(self) -> JSONDict:
        """Get buffer metrics."""
        return {
            **self._metrics,
            "current_size": len(self._buffer),
            "max_size": self.max_size,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


__all__ = [
    "BufferedMessage",
    "RetryBuffer",
]
