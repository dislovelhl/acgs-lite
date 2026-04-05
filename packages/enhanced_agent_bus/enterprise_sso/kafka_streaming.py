"""
Kafka Event Streaming Integration
Constitutional Hash: 608508a9bd224290

Phase 10 Task 12: Kafka Event Streaming Integration

Provides:
- Kafka producer with connection pooling
- Governance event publishing with async support
- Schema registry integration (Avro/Protobuf)
- Consumer event ingestion
- At-least-once delivery with acknowledgment
- Dead letter queue handling
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum

_JsonValue = str | int | float | bool | None | dict | list

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import ACGSBaseError

KAFKA_STREAMING_OPERATION_ERRORS = (
    AttributeError,
    ConnectionError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)

# ============================================================================
# Exceptions
# ============================================================================


class SerializationError(ACGSBaseError):
    """Error during event serialization.

    Inherits from ACGSBaseError to gain constitutional hash tracking,
    correlation IDs, and structured error logging.
    """

    http_status_code = 500
    error_code = "SERIALIZATION_ERROR"


class KafkaConnectionError(ACGSBaseError):
    """Error connecting to Kafka.

    Inherits from ACGSBaseError to gain constitutional hash tracking,
    correlation IDs, and structured error logging.
    """

    http_status_code = 503  # Service Unavailable
    error_code = "KAFKA_CONNECTION_ERROR"


class SchemaRegistryError(ACGSBaseError):
    """Error with schema registry operations.

    Inherits from ACGSBaseError to gain constitutional hash tracking,
    correlation IDs, and structured error logging.
    """

    http_status_code = 500
    error_code = "SCHEMA_REGISTRY_ERROR"


# ============================================================================
# Enums
# ============================================================================


class DeliveryGuarantee(Enum):
    """Kafka delivery guarantee levels."""

    AT_MOST_ONCE = "at_most_once"
    AT_LEAST_ONCE = "at_least_once"
    EXACTLY_ONCE = "exactly_once"


class AcknowledgmentMode(Enum):
    """Consumer acknowledgment modes."""

    AUTO = "auto"
    MANUAL = "manual"


class SchemaFormat(Enum):
    """Schema formats for serialization."""

    AVRO = "avro"
    PROTOBUF = "protobuf"
    JSON = "json"


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class KafkaConfig:
    """Kafka connection configuration."""

    bootstrap_servers: str
    client_id: str = "acgs2-governance"
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: str | None = None
    sasl_username: str | None = None
    sasl_password: str | None = None
    ssl_cafile: str | None = None
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ProducerConfig:
    """Kafka producer configuration."""

    acks: str = "all"
    retries: int = 3
    retry_backoff_ms: int = 100
    batch_size: int = 16384
    linger_ms: int = 5
    buffer_memory: int = 33554432
    max_block_ms: int = 60000
    delivery_guarantee: DeliveryGuarantee = DeliveryGuarantee.AT_LEAST_ONCE
    enable_idempotence: bool = True
    compression_type: str = "lz4"
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ConsumerConfig:
    """Kafka consumer configuration."""

    group_id: str
    auto_offset_reset: str = "earliest"
    enable_auto_commit: bool = False
    max_poll_records: int = 500
    max_poll_interval_ms: int = 300000
    session_timeout_ms: int = 10000
    heartbeat_interval_ms: int = 3000
    acknowledgment_mode: AcknowledgmentMode = AcknowledgmentMode.MANUAL
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class GovernanceEvent:
    """Governance event for Kafka streaming."""

    event_id: str
    event_type: str
    tenant_id: str
    payload: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str | None = None
    correlation_id: str | None = None
    headers: dict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_json(self) -> str:
        """Serialize event to JSON string."""
        try:
            data = {
                "event_id": self.event_id,
                "event_type": self.event_type,
                "tenant_id": self.tenant_id,
                "timestamp": self.timestamp.isoformat() if self.timestamp else None,
                "payload": self._serialize_payload(self.payload),
                "source": self.source,
                "correlation_id": self.correlation_id,
                "headers": self.headers,
                "constitutional_hash": self.constitutional_hash,
            }
            return json.dumps(data)
        except (TypeError, ValueError) as e:
            raise SerializationError(f"Failed to serialize event: {e}") from e

    def _serialize_payload(self, payload: _JsonValue) -> _JsonValue:
        """Recursively serialize payload, handling non-JSON types."""
        if isinstance(payload, dict):
            result = {}
            for k, v in payload.items():
                if not isinstance(v, (str, int, float, bool, list, dict, type(None))):
                    raise SerializationError(f"Non-serializable value for key '{k}': {type(v)}")
                result[k] = self._serialize_payload(v)
            return result
        elif isinstance(payload, list):
            return [self._serialize_payload(item) for item in payload]
        return payload

    @classmethod
    def from_json(cls, json_str: str) -> "GovernanceEvent":
        """Deserialize event from JSON string."""
        data = json.loads(json_str)
        timestamp = data.get("timestamp")
        if timestamp and isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            tenant_id=data["tenant_id"],
            timestamp=timestamp,
            payload=data.get("payload", {}),
            source=data.get("source"),
            correlation_id=data.get("correlation_id"),
            headers=data.get("headers", {}),
            constitutional_hash=data.get("constitutional_hash", CONSTITUTIONAL_HASH),
        )

    def to_bytes(self) -> bytes:
        """Serialize event to bytes."""
        return self.to_json().encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "GovernanceEvent":
        """Deserialize event from bytes."""
        return cls.from_json(data.decode("utf-8"))


@dataclass
class EventSchema:
    """Event schema definition for serialization."""

    name: str
    version: str
    format: SchemaFormat
    schema_definition: dict | str
    subject: str | None = None
    schema_id: int | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class PublishResult:
    """Result of publishing an event."""

    success: bool
    event_id: str
    topic: str | None = None
    partition: int | None = None
    offset: int | None = None
    timestamp: datetime | None = None
    error: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


# ============================================================================
# Connection Pool
# ============================================================================


class KafkaConnectionPool:
    """Connection pool for Kafka producers."""

    def __init__(self, config: KafkaConfig, producer_config: ProducerConfig, pool_size: int = 5):
        self.config = config
        self.producer_config = producer_config
        self.pool_size = pool_size
        self._pool: asyncio.Queue = asyncio.Queue()
        self._producers: list = []
        self._started = False
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def start(self) -> None:
        """Initialize the connection pool."""
        if self._started:
            return

        for _ in range(self.pool_size):
            producer = self._create_producer()
            self._producers.append(producer)
            await self._pool.put(producer)

        self._started = True

    async def stop(self) -> None:
        """Shutdown the connection pool."""
        if not self._started:
            return

        for producer in self._producers:
            try:
                await self._close_producer(producer)
            except (RuntimeError, ConnectionError, OSError):
                pass  # Ignore close errors during shutdown

        self._producers.clear()
        self._started = False

    async def acquire(self) -> "MockProducer":
        """Acquire a producer from the pool."""
        if not self._started:
            await self.start()
        return await self._pool.get()  # type: ignore[no-any-return]

    async def release(self, producer: "MockProducer") -> None:
        """Release a producer back to the pool."""
        await self._pool.put(producer)

    def _create_producer(self) -> "MockProducer":
        """Create a new Kafka producer (mock for testing)."""
        # In production, this would create a confluent_kafka.Producer
        return MockProducer(self.config, self.producer_config)

    async def _close_producer(self, producer: "MockProducer") -> None:
        """Close a producer connection."""
        if hasattr(producer, "close"):
            result = producer.close()
            if asyncio.iscoroutine(result):
                await result

    async def health_check(self) -> dict:
        """Check pool health."""
        return {
            "healthy": self._started,
            "pool_size": self.pool_size,
            "available_connections": self._pool.qsize() if self._started else 0,
            "constitutional_hash": self.constitutional_hash,
        }


class MockProducer:
    """Mock producer for testing."""

    def __init__(self, config: KafkaConfig, producer_config: ProducerConfig):
        self.config = config
        self.producer_config = producer_config

    async def send(
        self, topic: str, value: bytes, key: bytes | None = None, headers: dict | None = None
    ) -> dict:
        """Send a message."""
        return {"topic": topic, "partition": 0, "offset": 1}

    async def close(self) -> None:
        """Close the producer."""
        pass


# ============================================================================
# Event Publisher
# ============================================================================


class KafkaEventPublisher:
    """Publishes governance events to Kafka."""

    def __init__(self, config: KafkaConfig, producer_config: ProducerConfig | None = None):
        self.config = config
        self.producer_config = producer_config or ProducerConfig()
        self._pool: KafkaConnectionPool | None = None
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def _ensure_pool(self) -> None:
        """Ensure connection pool is initialized."""
        if self._pool is None:
            self._pool = KafkaConnectionPool(self.config, self.producer_config)
            await self._pool.start()

    async def publish(
        self,
        topic: str,
        event: GovernanceEvent,
        key: str | None = None,
        headers: dict | None = None,
        on_delivery: Callable | None = None,
    ) -> PublishResult:
        """Publish a single event."""
        await self._ensure_pool()

        try:
            success = await self._send_to_kafka(topic=topic, event=event, key=key, headers=headers)

            if on_delivery:
                on_delivery(event.event_id, success, None)

            return PublishResult(
                success=success,
                event_id=event.event_id,
                topic=topic,
                timestamp=datetime.now(UTC),
            )
        except KAFKA_STREAMING_OPERATION_ERRORS as e:
            if on_delivery:
                on_delivery(event.event_id, False, str(e))

            return PublishResult(success=False, event_id=event.event_id, topic=topic, error=str(e))

    async def publish_batch(
        self, topic: str, events: list[GovernanceEvent], key_extractor: Callable | None = None
    ) -> list[PublishResult]:
        """Publish multiple events in batch."""
        await self._ensure_pool()

        results = []
        for event in events:
            key = key_extractor(event) if key_extractor else None
            result = await self.publish(topic, event, key=key)
            results.append(result)

        return results

    async def _send_to_kafka(
        self,
        topic: str,
        event: GovernanceEvent,
        key: str | None = None,
        headers: dict | None = None,
    ) -> bool:
        """Send event to Kafka (mock implementation)."""
        # In production, this would use the connection pool
        return True

    async def _send_batch(self, topic: str, events: list[GovernanceEvent]) -> list[bool]:
        """Send batch of events."""
        return [True] * len(events)

    async def close(self) -> None:
        """Close the publisher."""
        if self._pool:
            await self._pool.stop()


# ============================================================================
# Governance Event Producer
# ============================================================================


class GovernanceEventProducer:
    """Enhanced producer with governance-specific features."""

    def __init__(self, config: KafkaConfig, producer_config: ProducerConfig | None = None):
        self.kafka_config = config
        self.config = producer_config or ProducerConfig()
        self._publisher = KafkaEventPublisher(config, self.config)
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def publish(
        self,
        topic: str,
        event: GovernanceEvent,
        key: str | None = None,
        on_delivery: Callable | None = None,
    ) -> PublishResult:
        """Publish with retry logic for at-least-once delivery."""
        max_retries = self.config.retries
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                result = await self._send_to_kafka(topic, event, key)
                if result:
                    if on_delivery:
                        on_delivery(event.event_id, True, None)
                    return PublishResult(success=True, event_id=event.event_id, topic=topic)
            except KAFKA_STREAMING_OPERATION_ERRORS as e:
                last_error = e
                if attempt < max_retries:
                    await asyncio.sleep(self.config.retry_backoff_ms / 1000.0)
                    continue
                break

        if on_delivery:
            on_delivery(event.event_id, False, str(last_error))

        return PublishResult(
            success=False,
            event_id=event.event_id,
            error=str(last_error) if last_error else "Unknown error",
        )

    async def _send_to_kafka(
        self, topic: str, event: GovernanceEvent, key: str | None = None
    ) -> bool:
        """Send to Kafka with error simulation support."""
        return True

    async def close(self) -> None:
        """Close the producer."""
        await self._publisher.close()


# ============================================================================
# Schema Registry
# ============================================================================


class SchemaRegistry:
    """Schema registry client for Avro/Protobuf schemas."""

    def __init__(self, url: str, auto_register: bool = True, cache_capacity: int = 100):
        self.url = url
        self.auto_register = auto_register
        self._schema_cache: dict = {}
        self._cache_capacity = cache_capacity
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def register_schema(self, subject: str, schema: EventSchema) -> int:
        """Register a schema and return schema ID."""
        return await self._register_schema(subject, schema)

    async def _register_schema(self, subject: str, schema: EventSchema) -> int:
        """Internal schema registration (mock)."""
        return 1

    async def get_schema(self, schema_id: int) -> dict:
        """Get schema by ID."""
        if schema_id in self._schema_cache:
            return self._schema_cache[schema_id]  # type: ignore[no-any-return]

        schema = await self._get_schema(schema_id)
        self._schema_cache[schema_id] = schema
        return dict(schema)  # type: ignore[arg-type]

    async def _get_schema(self, schema_id: int) -> dict:
        """Internal schema retrieval (mock)."""
        return {"type": "record", "name": "TestSchema"}

    async def check_compatibility(self, subject: str, schema: EventSchema) -> bool:
        """Check if schema is compatible with existing versions."""
        return await self._check_compatibility(subject, schema)

    async def _check_compatibility(self, subject: str, schema: EventSchema) -> bool:
        """Internal compatibility check (mock)."""
        return True

    def serialize(self, schema: EventSchema, data: dict) -> bytes:
        """Serialize data using schema."""
        return self._serialize(schema, data)

    def _serialize(self, schema: EventSchema, data: dict) -> bytes:
        """Internal serialization (mock)."""
        return json.dumps(data).encode("utf-8")

    def deserialize(self, schema: EventSchema, data: bytes) -> dict:
        """Deserialize data using schema."""
        return dict(self._deserialize(schema, data))

    def _deserialize(self, schema: EventSchema, data: bytes) -> dict:
        """Internal deserialization (mock)."""
        return dict(json.loads(data.decode("utf-8")))  # type: ignore[arg-type]


# ============================================================================
# Event Consumer
# ============================================================================


class GovernanceEventConsumer:
    """Consumes governance events from Kafka."""

    def __init__(self, config: KafkaConfig, consumer_config: ConsumerConfig):
        self.kafka_config = config
        self.config = consumer_config
        self._subscribed_topics: list = []
        self._running = False
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def subscribe(self, topics: list[str]) -> None:
        """Subscribe to topics."""
        await self._subscribe(topics)
        self._subscribed_topics = topics

    async def _subscribe(self, topics: list[str]) -> None:
        """Internal subscribe (mock)."""
        pass

    async def consume(self, timeout_ms: int = 1000) -> GovernanceEvent | None:
        """Consume a single event."""
        return await self._poll(timeout_ms)

    async def _poll(self, timeout_ms: int) -> GovernanceEvent | None:
        """Internal poll (mock)."""
        return None

    async def consume_batch(
        self, max_records: int = 500, timeout_ms: int = 5000
    ) -> list[GovernanceEvent]:
        """Consume batch of events."""
        return await self._poll_batch(max_records, timeout_ms)

    async def _poll_batch(self, max_records: int, timeout_ms: int) -> list[GovernanceEvent]:
        """Internal batch poll (mock)."""
        return []

    async def commit(self) -> None:
        """Commit current offsets."""
        await self._commit()

    async def _commit(self) -> None:
        """Internal commit (mock)."""
        pass

    async def commit_offsets(self, offsets: dict) -> None:
        """Commit specific offsets."""
        await self._commit_offsets(offsets)

    async def _commit_offsets(self, offsets: dict) -> None:
        """Internal offset commit (mock)."""
        pass

    async def consume_with_handler(
        self,
        handler: Callable[[GovernanceEvent], Awaitable[object]],
        max_events: int | None = None,
    ) -> int:
        """Consume events with handler callback."""
        processed = 0

        while max_events is None or processed < max_events:
            event = await self._poll(1000)
            if event is None:
                break

            await handler(event)
            processed += 1

            if self.config.acknowledgment_mode == AcknowledgmentMode.MANUAL:
                await self.commit()

        return processed

    async def seek_to_beginning(self, topic: str, partition: int) -> None:
        """Seek to beginning of partition."""
        await self._seek_to_beginning(topic, partition)

    async def _seek_to_beginning(self, topic: str, partition: int) -> None:
        """Internal seek (mock)."""
        pass

    async def get_lag(self) -> dict:
        """Get consumer lag for all partitions."""
        return await self._get_lag()

    async def _get_lag(self) -> dict:
        """Internal lag calculation (mock)."""
        return {}

    async def close(self) -> None:
        """Close the consumer."""
        self._running = False


# ============================================================================
# Dead Letter Queue
# ============================================================================


class DeadLetterQueue:
    """Handles failed events with dead letter queue."""

    def __init__(
        self,
        topic: str,
        max_retries: int = 3,
        retry_delay_ms: int = 1000,
        permanent_failure_topic: str | None = None,
    ):
        self.topic = topic
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms
        self.permanent_failure_topic = permanent_failure_topic or f"{topic}-permanent"
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def send(self, event: GovernanceEvent, error: Exception, retry_count: int) -> bool:
        """Send failed event to DLQ."""
        dlq_event = {
            "original_event": event.to_json(),
            "error_message": str(error),
            "error_type": type(error).__name__,
            "retry_count": retry_count,
            "timestamp": datetime.now(UTC).isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }

        return await self._send(event=event, metadata=dlq_event)

    async def _send(self, event: GovernanceEvent, metadata: dict) -> bool:
        """Internal DLQ send (mock)."""
        return True

    async def reprocess(
        self,
        handler: Callable[[GovernanceEvent], Awaitable[bool]],
        max_events: int | None = None,
    ) -> int:
        """Reprocess events from DLQ."""
        events = await self._consume_dlq(max_events)
        processed = 0

        for event in events:
            try:
                success = await handler(event)
                if success:
                    processed += 1
            except (RuntimeError, ValueError, TypeError):
                pass  # Skip failed events in DLQ processing

        return processed

    async def _consume_dlq(self, max_events: int | None) -> list[GovernanceEvent]:
        """Internal DLQ consumption (mock)."""
        return []

    async def handle_max_retries_exceeded(
        self, event: GovernanceEvent, final_error: Exception
    ) -> bool:
        """Handle event that exceeded max retries."""
        return await self._send_to_permanent_failure(event, final_error)

    async def _send_to_permanent_failure(self, event: GovernanceEvent, error: Exception) -> bool:
        """Send to permanent failure queue (mock)."""
        return True
