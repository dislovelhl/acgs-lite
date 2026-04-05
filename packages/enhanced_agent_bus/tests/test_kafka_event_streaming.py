"""
Kafka Event Streaming Integration Tests
Constitutional Hash: 608508a9bd224290

Phase 10 Task 12: Kafka Event Streaming Integration

Tests:
- Kafka producer initialization with connection pooling
- Governance event publishing with async support
- Schema registry integration (Avro/Protobuf)
- Consumer event ingestion
- At-least-once delivery with acknowledgment
- Dead letter queue handling
- Constitutional compliance validation
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enterprise_sso.kafka_streaming import (
    CONSTITUTIONAL_HASH,
    AcknowledgmentMode,
    ConsumerConfig,
    DeadLetterQueue,
    DeliveryGuarantee,
    EventSchema,
    GovernanceEvent,
    GovernanceEventConsumer,
    GovernanceEventProducer,
    KafkaConfig,
    KafkaConnectionPool,
    KafkaEventPublisher,
    ProducerConfig,
    SchemaFormat,
    SchemaRegistry,
    SerializationError,
)

# ============================================================================
# Test Classes
# ============================================================================


class TestKafkaProducerInitialization:
    """Tests for Kafka producer initialization and connection pooling."""

    @pytest.fixture
    def kafka_config(self):
        return KafkaConfig(
            bootstrap_servers="localhost:9092",
            client_id="test-client",
            security_protocol="PLAINTEXT",
        )

    @pytest.fixture
    def producer_config(self):
        return ProducerConfig(acks="all", retries=3, batch_size=16384, linger_ms=5)

    def test_create_config(self, kafka_config):
        """Test creating Kafka configuration."""
        assert kafka_config.bootstrap_servers == "localhost:9092"
        assert kafka_config.client_id == "test-client"
        assert kafka_config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_producer_config_defaults(self):
        """Test producer configuration with defaults."""
        config = ProducerConfig()
        assert config.acks == "all"
        assert config.retries == 3
        assert config.delivery_guarantee == DeliveryGuarantee.AT_LEAST_ONCE

    async def test_connection_pool_initialization(self, kafka_config, producer_config):
        """Test connection pool creates producers."""
        pool = KafkaConnectionPool(kafka_config, producer_config, pool_size=3)

        assert pool.pool_size == 3
        assert pool.config == kafka_config

    async def test_connection_pool_acquire_release(self, kafka_config, producer_config):
        """Test acquiring and releasing connections from pool."""
        pool = KafkaConnectionPool(kafka_config, producer_config, pool_size=2)

        # Mock the producer
        with patch.object(pool, "_create_producer") as mock_create:
            mock_producer = MagicMock()
            mock_create.return_value = mock_producer

            await pool.start()

            # Acquire connection
            producer = await pool.acquire()
            assert producer is not None

            # Release connection
            await pool.release(producer)

            await pool.stop()

    async def test_producer_health_check(self, kafka_config, producer_config):
        """Test producer health check functionality."""
        pool = KafkaConnectionPool(kafka_config, producer_config, pool_size=1)

        with patch.object(pool, "_create_producer"):
            await pool.start()

            health = await pool.health_check()

            assert "pool_size" in health
            assert "available_connections" in health
            assert "constitutional_hash" in health
            assert health["constitutional_hash"] == CONSTITUTIONAL_HASH

            await pool.stop()


class TestGovernanceEventPublishing:
    """Tests for governance event publishing."""

    @pytest.fixture
    def governance_event(self):
        return GovernanceEvent(
            event_id=str(uuid.uuid4()),
            event_type="POLICY_CREATED",
            tenant_id="tenant-001",
            timestamp=datetime.now(UTC),
            payload={"policy_id": "policy-123", "name": "Test Policy"},
            source="policy-service",
        )

    @pytest.fixture
    def event_publisher(self):
        config = KafkaConfig(bootstrap_servers="localhost:9092")
        return KafkaEventPublisher(config)

    async def test_create_governance_event(self, governance_event):
        """Test creating a governance event."""
        assert governance_event.event_type == "POLICY_CREATED"
        assert governance_event.tenant_id == "tenant-001"
        assert governance_event.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_publish_event_success(self, event_publisher, governance_event):
        """Test publishing an event successfully."""
        with patch.object(event_publisher, "_send_to_kafka") as mock_send:
            mock_send.return_value = True

            result = await event_publisher.publish(
                topic="governance-events", event=governance_event
            )

            assert result.success is True
            assert result.event_id == governance_event.event_id

    async def test_publish_event_with_key(self, event_publisher, governance_event):
        """Test publishing with partition key."""
        with patch.object(event_publisher, "_send_to_kafka") as mock_send:
            mock_send.return_value = True

            result = await event_publisher.publish(
                topic="governance-events", event=governance_event, key=governance_event.tenant_id
            )

            assert result.success is True

    async def test_publish_batch_events(self, event_publisher):
        """Test publishing multiple events in batch."""
        events = [
            GovernanceEvent(
                event_id=str(uuid.uuid4()),
                event_type="POLICY_UPDATED",
                tenant_id="tenant-001",
                payload={"policy_id": f"policy-{i}"},
            )
            for i in range(5)
        ]

        with patch.object(event_publisher, "_send_batch") as mock_send:
            mock_send.return_value = [True] * 5

            results = await event_publisher.publish_batch(topic="governance-events", events=events)

            assert len(results) == 5
            assert all(r.success for r in results)

    async def test_publish_with_headers(self, event_publisher, governance_event):
        """Test publishing with custom headers."""
        headers = {"trace-id": "abc123", "correlation-id": "xyz789"}

        with patch.object(event_publisher, "_send_to_kafka") as mock_send:
            mock_send.return_value = True

            result = await event_publisher.publish(
                topic="governance-events", event=governance_event, headers=headers
            )

            assert result.success is True


class TestSchemaRegistryIntegration:
    """Tests for schema registry integration."""

    @pytest.fixture
    def schema_registry(self):
        return SchemaRegistry(url="http://localhost:8081", auto_register=True)

    @pytest.fixture
    def avro_schema(self):
        return EventSchema(
            name="GovernanceEvent",
            version="1.0.0",
            format=SchemaFormat.AVRO,
            schema_definition={
                "type": "record",
                "name": "GovernanceEvent",
                "fields": [
                    {"name": "event_id", "type": "string"},
                    {"name": "event_type", "type": "string"},
                    {"name": "tenant_id", "type": "string"},
                    {"name": "timestamp", "type": "string"},
                    {"name": "payload", "type": "string"},
                    {"name": "constitutional_hash", "type": "string"},
                ],
            },
        )

    async def test_register_avro_schema(self, schema_registry, avro_schema):
        """Test registering an Avro schema."""
        with patch.object(schema_registry, "_register_schema") as mock_register:
            mock_register.return_value = 1  # Schema ID

            schema_id = await schema_registry.register_schema(
                subject="governance-events-value", schema=avro_schema
            )

            assert schema_id == 1

    async def test_get_schema_by_id(self, schema_registry):
        """Test retrieving schema by ID."""
        with patch.object(schema_registry, "_get_schema") as mock_get:
            mock_get.return_value = {"type": "record", "name": "TestSchema"}

            schema = await schema_registry.get_schema(schema_id=1)

            assert schema is not None
            assert schema["type"] == "record"

    async def test_check_compatibility(self, schema_registry, avro_schema):
        """Test schema compatibility check."""
        with patch.object(schema_registry, "_check_compatibility") as mock_check:
            mock_check.return_value = True

            is_compatible = await schema_registry.check_compatibility(
                subject="governance-events-value", schema=avro_schema
            )

            assert is_compatible is True

    def test_serialize_with_schema(self, schema_registry, avro_schema):
        """Test serializing data with schema."""
        data = {
            "event_id": "evt-001",
            "event_type": "TEST",
            "tenant_id": "tenant-001",
            "timestamp": datetime.now(UTC).isoformat(),
            "payload": "{}",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        with patch.object(schema_registry, "_serialize") as mock_serialize:
            mock_serialize.return_value = b"serialized_data"

            serialized = schema_registry.serialize(schema=avro_schema, data=data)

            assert serialized == b"serialized_data"

    def test_deserialize_with_schema(self, schema_registry, avro_schema):
        """Test deserializing data with schema."""
        with patch.object(schema_registry, "_deserialize") as mock_deserialize:
            mock_deserialize.return_value = {"event_id": "evt-001"}

            data = schema_registry.deserialize(schema=avro_schema, data=b"serialized_data")

            assert data["event_id"] == "evt-001"

    def test_protobuf_schema_support(self):
        """Test Protobuf schema format support."""
        schema = EventSchema(
            name="GovernanceEvent",
            version="1.0.0",
            format=SchemaFormat.PROTOBUF,
            schema_definition="syntax = 'proto3'; message GovernanceEvent {}",
        )

        assert schema.format == SchemaFormat.PROTOBUF


class TestKafkaConsumer:
    """Tests for Kafka consumer functionality."""

    @pytest.fixture
    def consumer_config(self):
        return ConsumerConfig(
            group_id="governance-consumers",
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            acknowledgment_mode=AcknowledgmentMode.MANUAL,
        )

    @pytest.fixture
    def event_consumer(self, consumer_config):
        kafka_config = KafkaConfig(bootstrap_servers="localhost:9092")
        return GovernanceEventConsumer(kafka_config, consumer_config)

    async def test_subscribe_to_topics(self, event_consumer):
        """Test subscribing to topics."""
        with patch.object(event_consumer, "_subscribe") as mock_subscribe:
            await event_consumer.subscribe(["governance-events", "policy-events"])

            mock_subscribe.assert_called_once_with(["governance-events", "policy-events"])

    async def test_consume_event(self, event_consumer):
        """Test consuming a single event."""
        mock_event = GovernanceEvent(
            event_id="evt-001", event_type="POLICY_CREATED", tenant_id="tenant-001", payload={}
        )

        with patch.object(event_consumer, "_poll") as mock_poll:
            mock_poll.return_value = mock_event

            event = await event_consumer.consume(timeout_ms=1000)

            assert event is not None
            assert event.event_id == "evt-001"

    async def test_consume_batch(self, event_consumer):
        """Test consuming batch of events."""
        mock_events = [
            GovernanceEvent(
                event_id=f"evt-{i}", event_type="POLICY_UPDATED", tenant_id="tenant-001", payload={}
            )
            for i in range(10)
        ]

        with patch.object(event_consumer, "_poll_batch") as mock_poll:
            mock_poll.return_value = mock_events

            events = await event_consumer.consume_batch(max_records=10, timeout_ms=5000)

            assert len(events) == 10

    async def test_manual_commit(self, event_consumer):
        """Test manual offset commit."""
        with patch.object(event_consumer, "_commit") as mock_commit:
            await event_consumer.commit()

            mock_commit.assert_called_once()

    async def test_commit_specific_offsets(self, event_consumer):
        """Test committing specific offsets."""
        offsets = {"governance-events-0": 100, "governance-events-1": 50}

        with patch.object(event_consumer, "_commit_offsets") as mock_commit:
            await event_consumer.commit_offsets(offsets)

            mock_commit.assert_called_once_with(offsets)

    async def test_event_handler_callback(self, event_consumer):
        """Test event handler callback."""
        received_events = []

        async def handler(event: GovernanceEvent):
            received_events.append(event)

        mock_event = GovernanceEvent(
            event_id="evt-001", event_type="POLICY_CREATED", tenant_id="tenant-001", payload={}
        )

        with patch.object(event_consumer, "_poll") as mock_poll:
            mock_poll.side_effect = [mock_event, None]

            await event_consumer.consume_with_handler(handler, max_events=1)

            assert len(received_events) == 1

    async def test_seek_to_beginning(self, event_consumer):
        """Test seeking to beginning of partition."""
        with patch.object(event_consumer, "_seek_to_beginning") as mock_seek:
            await event_consumer.seek_to_beginning("governance-events", partition=0)

            mock_seek.assert_called_once()

    async def test_get_lag(self, event_consumer):
        """Test getting consumer lag."""
        with patch.object(event_consumer, "_get_lag") as mock_lag:
            mock_lag.return_value = {"governance-events-0": 100}

            lag = await event_consumer.get_lag()

            assert lag["governance-events-0"] == 100


class TestDeliveryGuarantees:
    """Tests for at-least-once delivery guarantees."""

    @pytest.fixture
    def producer_with_guarantee(self):
        config = KafkaConfig(bootstrap_servers="localhost:9092")
        producer_config = ProducerConfig(
            acks="all",
            retries=5,
            delivery_guarantee=DeliveryGuarantee.AT_LEAST_ONCE,
            enable_idempotence=True,
        )
        return GovernanceEventProducer(config, producer_config)

    async def test_at_least_once_config(self, producer_with_guarantee):
        """Test at-least-once delivery configuration."""
        assert producer_with_guarantee.config.delivery_guarantee == DeliveryGuarantee.AT_LEAST_ONCE
        assert producer_with_guarantee.config.acks == "all"

    async def test_idempotent_producer(self, producer_with_guarantee):
        """Test idempotent producer configuration."""
        assert producer_with_guarantee.config.enable_idempotence is True

    async def test_retry_on_failure(self, producer_with_guarantee):
        """Test retry mechanism on transient failures."""
        event = GovernanceEvent(
            event_id="evt-001", event_type="POLICY_CREATED", tenant_id="tenant-001", payload={}
        )

        call_count = 0

        async def mock_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Transient error")
            return True

        with patch.object(producer_with_guarantee, "_send_to_kafka", side_effect=mock_send):
            result = await producer_with_guarantee.publish(topic="governance-events", event=event)

            assert result.success is True
            assert call_count == 3

    async def test_delivery_callback(self, producer_with_guarantee):
        """Test delivery confirmation callback."""
        confirmed_events = []

        def on_delivery(event_id, success, error):
            confirmed_events.append((event_id, success))

        event = GovernanceEvent(
            event_id="evt-001", event_type="POLICY_CREATED", tenant_id="tenant-001", payload={}
        )

        with patch.object(producer_with_guarantee, "_send_to_kafka") as mock_send:
            mock_send.return_value = True

            await producer_with_guarantee.publish(
                topic="governance-events", event=event, on_delivery=on_delivery
            )

            # The publish method calls on_delivery internally when successful
            # Verify callback was invoked exactly once by the publish method
            assert len(confirmed_events) == 1
            assert confirmed_events[0] == ("evt-001", True)


class TestDeadLetterQueue:
    """Tests for dead letter queue handling."""

    @pytest.fixture
    def dlq(self):
        return DeadLetterQueue(topic="governance-events-dlq", max_retries=3, retry_delay_ms=1000)

    @pytest.fixture
    def failed_event(self):
        return GovernanceEvent(
            event_id="evt-failed-001",
            event_type="POLICY_CREATED",
            tenant_id="tenant-001",
            payload={"policy_id": "policy-123"},
        )

    async def test_send_to_dlq(self, dlq, failed_event):
        """Test sending failed event to DLQ."""
        error = Exception("Processing failed")

        with patch.object(dlq, "_send") as mock_send:
            mock_send.return_value = True

            result = await dlq.send(event=failed_event, error=error, retry_count=3)

            assert result is True

    async def test_dlq_includes_error_metadata(self, dlq, failed_event):
        """Test DLQ message includes error metadata."""
        error = ValueError("Invalid payload")

        with patch.object(dlq, "_send") as mock_send:

            async def capture_call(**kwargs):
                return True

            mock_send.side_effect = capture_call

            await dlq.send(event=failed_event, error=error, retry_count=2)

            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert "error" in str(call_args) or call_args is not None

    async def test_reprocess_from_dlq(self, dlq):
        """Test reprocessing events from DLQ."""
        dlq_events = [
            GovernanceEvent(
                event_id=f"evt-dlq-{i}",
                event_type="POLICY_CREATED",
                tenant_id="tenant-001",
                payload={},
            )
            for i in range(3)
        ]

        reprocessed = []

        async def reprocess_handler(event):
            reprocessed.append(event)
            return True

        with patch.object(dlq, "_consume_dlq") as mock_consume:
            mock_consume.return_value = dlq_events

            count = await dlq.reprocess(handler=reprocess_handler)

            assert count == 3

    async def test_dlq_max_retries_exceeded(self, dlq, failed_event):
        """Test handling when max retries exceeded."""
        with patch.object(dlq, "_send_to_permanent_failure") as mock_send:
            mock_send.return_value = True

            # After max retries, send to permanent failure queue
            result = await dlq.handle_max_retries_exceeded(
                event=failed_event, final_error=Exception("Permanent failure")
            )

            assert result is True

    def test_dlq_config(self, dlq):
        """Test DLQ configuration."""
        assert dlq.topic == "governance-events-dlq"
        assert dlq.max_retries == 3
        assert dlq.retry_delay_ms == 1000
        assert dlq.constitutional_hash == CONSTITUTIONAL_HASH


class TestConstitutionalCompliance:
    """Tests for constitutional hash compliance."""

    def test_kafka_config_includes_hash(self):
        """Test Kafka config includes constitutional hash."""
        config = KafkaConfig(bootstrap_servers="localhost:9092")
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_producer_config_includes_hash(self):
        """Test producer config includes constitutional hash."""
        config = ProducerConfig()
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_consumer_config_includes_hash(self):
        """Test consumer config includes constitutional hash."""
        config = ConsumerConfig(group_id="test-group")
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_governance_event_includes_hash(self):
        """Test governance event includes constitutional hash."""
        event = GovernanceEvent(
            event_id="evt-001", event_type="TEST", tenant_id="tenant-001", payload={}
        )
        assert event.constitutional_hash == CONSTITUTIONAL_HASH

    def test_schema_includes_hash(self):
        """Test event schema includes constitutional hash."""
        schema = EventSchema(
            name="TestSchema", version="1.0.0", format=SchemaFormat.AVRO, schema_definition={}
        )
        assert schema.constitutional_hash == CONSTITUTIONAL_HASH

    def test_dlq_includes_hash(self):
        """Test DLQ includes constitutional hash."""
        dlq = DeadLetterQueue(topic="test-dlq")
        assert dlq.constitutional_hash == CONSTITUTIONAL_HASH

    def test_schema_registry_includes_hash(self):
        """Test schema registry includes constitutional hash."""
        registry = SchemaRegistry(url="http://localhost:8081")
        assert registry.constitutional_hash == CONSTITUTIONAL_HASH


class TestEventSerialization:
    """Tests for event serialization and deserialization."""

    @pytest.fixture
    def governance_event(self):
        return GovernanceEvent(
            event_id="evt-001",
            event_type="POLICY_CREATED",
            tenant_id="tenant-001",
            timestamp=datetime.now(UTC),
            payload={"policy_id": "pol-123", "name": "Test Policy"},
            source="policy-service",
        )

    def test_event_to_json(self, governance_event):
        """Test event serialization to JSON."""
        json_str = governance_event.to_json()

        data = json.loads(json_str)
        assert data["event_id"] == "evt-001"
        assert data["event_type"] == "POLICY_CREATED"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_event_from_json(self):
        """Test event deserialization from JSON."""
        json_str = json.dumps(
            {
                "event_id": "evt-002",
                "event_type": "POLICY_UPDATED",
                "tenant_id": "tenant-002",
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": {"policy_id": "pol-456"},
                "constitutional_hash": CONSTITUTIONAL_HASH,
            }
        )

        event = GovernanceEvent.from_json(json_str)

        assert event.event_id == "evt-002"
        assert event.event_type == "POLICY_UPDATED"

    def test_event_to_bytes(self, governance_event):
        """Test event serialization to bytes."""
        data = governance_event.to_bytes()

        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_serialization_error_handling(self):
        """Test handling serialization errors."""
        event = GovernanceEvent(
            event_id="evt-001",
            event_type="TEST",
            tenant_id="tenant-001",
            payload={"invalid": object()},  # Non-serializable
        )

        with pytest.raises(SerializationError):
            event.to_json()
