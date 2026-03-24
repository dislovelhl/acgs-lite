"""
ACGS-2 Enhanced Agent Bus - Circuit Breaker Kafka Producer
Constitutional Hash: cdd01ef066bc6cf2

Kafka Producer with circuit breaker protection implementing QUEUE_FOR_RETRY strategy.
When the circuit is open, messages are buffered for later retry.
Split from circuit_breaker_clients.py for improved maintainability.
"""

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime

# Import centralized constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

# Import circuit breaker components
from .circuit_breaker import (
    CircuitState,
    FallbackStrategy,
    ServiceCircuitBreaker,
    ServiceCircuitConfig,
    ServiceSeverity,
    get_service_circuit_breaker,
)

# Import retry buffer
from .retry_buffer import BufferedMessage, RetryBuffer

logger = get_logger(__name__)
try:
    from aiokafka.errors import KafkaError
except ImportError:
    KafkaError = RuntimeError

KAFKA_OPERATION_ERRORS = (
    AttributeError,
    ConnectionError,
    KafkaError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


class CircuitBreakerKafkaProducer:
    """
    Kafka Producer with circuit breaker protection and retry buffer.

    Implements QUEUE_FOR_RETRY strategy for guaranteed delivery.
    When the circuit is open, messages are buffered for later retry.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        client_id: str = "acgs2-cb-producer",
        buffer_size: int = 10000,
        base_retry_delay: float = 1.0,
        max_retry_delay: float = 60.0,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self.constitutional_hash = CONSTITUTIONAL_HASH

        self._producer: object | None = None
        self._circuit_breaker: ServiceCircuitBreaker | None = None
        self._retry_buffer = RetryBuffer(
            max_size=buffer_size,
            base_retry_delay=base_retry_delay,
            max_retry_delay=max_retry_delay,
        )
        self._initialized = False
        self._running = False

        # Retry processing task
        self._retry_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """Initialize the Kafka producer with circuit breaker."""
        if self._initialized:
            return

        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=self.client_id,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                acks="all",
                enable_idempotence=True,
                retry_backoff_ms=500,
            )
            await self._producer.start()
        except ImportError:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] aiokafka not available, Kafka producer disabled"
            )
            self._producer = None
        except KAFKA_OPERATION_ERRORS as e:
            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Kafka connection failed, operating with buffer only: {e}"
            )
            self._producer = None

        # Get or create the circuit breaker for Kafka
        # Use blockchain_anchor config which has QUEUE_FOR_RETRY strategy
        config = ServiceCircuitConfig(
            name="kafka_producer",
            failure_threshold=5,
            timeout_seconds=30.0,
            half_open_requests=3,
            fallback_strategy=FallbackStrategy.QUEUE_FOR_RETRY,
            fallback_max_queue_size=10000,
            severity=ServiceSeverity.HIGH,
            description="Kafka Producer - queues messages for retry on failure",
        )
        self._circuit_breaker = await get_service_circuit_breaker("kafka_producer", config)
        self._initialized = True
        self._running = True

        # Start retry processing background task
        self._retry_task = asyncio.create_task(self._retry_loop())

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Circuit-protected Kafka producer initialized "
            f"(servers={self.bootstrap_servers}, buffer_size={self._retry_buffer.max_size})"
        )

    async def close(self) -> None:
        """Close the Kafka producer."""
        self._running = False

        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass

        if self._producer:
            await self._producer.flush()
            await self._producer.stop()
            self._producer = None

        self._initialized = False

    async def __aenter__(self) -> "CircuitBreakerKafkaProducer":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def _retry_loop(self) -> None:
        """Background task to process retry buffer when circuit closes."""
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                if not self._running:
                    break

                # Only process if circuit is closed and buffer has items
                if (
                    self._circuit_breaker
                    and self._circuit_breaker.state == CircuitState.CLOSED
                    and self._retry_buffer.get_size() > 0
                    and self._producer
                ):
                    logger.info(
                        f"[{CONSTITUTIONAL_HASH}] Processing retry buffer "
                        f"(size={self._retry_buffer.get_size()})"
                    )
                    results = await self._retry_buffer.process(self._send_raw)
                    logger.info(f"[{CONSTITUTIONAL_HASH}] Retry processing complete: {results}")

            except asyncio.CancelledError:
                break
            except KAFKA_OPERATION_ERRORS as e:
                logger.error(f"[{CONSTITUTIONAL_HASH}] Retry loop error: {e}")

    async def _send_raw(self, topic: str, value: JSONDict, key: bytes | None) -> None:
        """Internal send without circuit breaker (used for retries)."""
        if self._producer:
            await self._producer.send_and_wait(topic, value=value, key=key)
        else:
            raise RuntimeError("Kafka producer not available")

    async def send(
        self,
        topic: str,
        value: JSONDict,
        key: str | None = None,
        tenant_id: str | None = None,
    ) -> bool:
        """
        Send a message to Kafka with circuit breaker protection.

        QUEUE_FOR_RETRY: If circuit is open or send fails, message is buffered.

        Args:
            topic: Kafka topic
            value: Message value (will be JSON serialized)
            key: Optional partition key
            tenant_id: Optional tenant ID for tracking

        Returns:
            True if sent immediately, False if buffered for retry
        """
        if not self._initialized:
            await self.initialize()

        key_bytes = key.encode("utf-8") if key else None
        message_id = str(uuid.uuid4())

        # Check circuit breaker
        if not await self._circuit_breaker.can_execute():
            # QUEUE_FOR_RETRY: Buffer message for later
            await self._circuit_breaker.record_rejection()

            buffered_msg = BufferedMessage(
                id=message_id,
                topic=topic,
                value=value,
                key=key_bytes,
                buffered_at=time.time(),
                tenant_id=tenant_id,
            )
            await self._retry_buffer.add(buffered_msg)

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] Kafka circuit breaker OPEN - "
                f"message {message_id} buffered for retry"
            )
            return False

        if not self._producer:
            # No producer, buffer the message
            buffered_msg = BufferedMessage(
                id=message_id,
                topic=topic,
                value=value,
                key=key_bytes,
                buffered_at=time.time(),
                tenant_id=tenant_id,
            )
            await self._retry_buffer.add(buffered_msg)
            return False

        try:
            await self._producer.send_and_wait(topic, value=value, key=key_bytes)
            await self._circuit_breaker.record_success()
            return True
        except KAFKA_OPERATION_ERRORS as e:
            await self._circuit_breaker.record_failure(e, type(e).__name__)

            # Buffer for retry
            buffered_msg = BufferedMessage(
                id=message_id,
                topic=topic,
                value=value,
                key=key_bytes,
                buffered_at=time.time(),
                tenant_id=tenant_id,
            )
            await self._retry_buffer.add(buffered_msg)

            logger.warning(
                f"[{CONSTITUTIONAL_HASH}] Kafka send failed, message {message_id} buffered: {e}"
            )
            return False

    async def send_batch(
        self,
        messages: list[tuple[str, JSONDict, str | None]],
        tenant_id: str | None = None,
    ) -> dict[str, int]:
        """
        Send multiple messages to Kafka with circuit breaker protection.

        Args:
            messages: List of (topic, value, key) tuples
            tenant_id: Optional tenant ID for tracking

        Returns:
            Dictionary with counts of sent and buffered messages
        """
        results = {"sent": 0, "buffered": 0}

        for topic, value, key in messages:
            success = await self.send(topic, value, key, tenant_id)
            if success:
                results["sent"] += 1
            else:
                results["buffered"] += 1

        return results

    async def flush_buffer(self) -> JSONDict:
        """
        Manually flush the retry buffer.

        Returns:
            Results of flush operation
        """
        if not self._producer:
            return {"error": "Producer not available"}

        return await self._retry_buffer.process(self._send_raw)

    async def health_check(self) -> JSONDict:
        """Check Kafka service health with circuit breaker status."""
        health = {
            "service": "kafka_producer",
            "healthy": False,
            "circuit_state": "unknown",
            "fallback_strategy": "queue_for_retry",
            "buffer_size": self._retry_buffer.get_size(),
            "constitutional_hash": CONSTITUTIONAL_HASH,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if self._circuit_breaker:
            health["circuit_state"] = self._circuit_breaker.state.value
            health["circuit_metrics"] = self._circuit_breaker.metrics.__dict__

        health["buffer_metrics"] = self._retry_buffer.get_metrics()

        if self._producer:
            health["healthy"] = True
            health["kafka_status"] = "connected"
        else:
            health["kafka_status"] = "not_connected"
            health["healthy"] = self._retry_buffer.get_size() == 0

        return health

    def get_circuit_status(self) -> JSONDict:
        """Get circuit breaker status."""
        if not self._circuit_breaker:
            return {"error": "Circuit breaker not initialized"}

        status = self._circuit_breaker.get_status()
        status["buffer_metrics"] = self._retry_buffer.get_metrics()
        return status


__all__ = [
    "CircuitBreakerKafkaProducer",
]
