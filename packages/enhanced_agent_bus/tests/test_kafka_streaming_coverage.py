"""
Tests for kafka_streaming.py — targets 90%+ coverage.
Constitutional Hash: 608508a9bd224290

All Kafka/aiokafka dependencies are mocked; the module uses a MockProducer
internally so no real Kafka broker is required.
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.enterprise_sso.kafka_streaming import (
    AcknowledgmentMode,
    ConsumerConfig,
    DeadLetterQueue,
    DeliveryGuarantee,
    EventSchema,
    GovernanceEvent,
    GovernanceEventConsumer,
    GovernanceEventProducer,
    KafkaConfig,
    KafkaConnectionError,
    KafkaConnectionPool,
    KafkaEventPublisher,
    MockProducer,
    ProducerConfig,
    PublishResult,
    SchemaFormat,
    SchemaRegistry,
    SchemaRegistryError,
    SerializationError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_kafka_config(**kwargs) -> KafkaConfig:
    defaults = {"bootstrap_servers": "localhost:9092", "client_id": "test-client"}
    defaults.update(kwargs)
    return KafkaConfig(**defaults)


def make_producer_config(**kwargs) -> ProducerConfig:
    return ProducerConfig(**kwargs)


def make_consumer_config(**kwargs) -> ConsumerConfig:
    defaults = {"group_id": "test-group"}
    defaults.update(kwargs)
    return ConsumerConfig(**defaults)


def make_event(**kwargs) -> GovernanceEvent:
    defaults = {
        "event_id": "evt-001",
        "event_type": "sso.login",
        "tenant_id": "tenant-a",
        "payload": {"user": "alice"},
    }
    defaults.update(kwargs)
    return GovernanceEvent(**defaults)


# ===========================================================================
# Exceptions
# ===========================================================================


class TestSerializationError:
    def test_is_exception(self):
        err = SerializationError("bad data")
        assert isinstance(err, SerializationError)
        assert "bad data" in str(err)

    def test_http_status_code(self):
        assert SerializationError.http_status_code == 500

    def test_error_code(self):
        assert SerializationError.error_code == "SERIALIZATION_ERROR"


class TestKafkaConnectionError:
    def test_is_exception(self):
        err = KafkaConnectionError("no broker")
        assert isinstance(err, KafkaConnectionError)

    def test_http_status_code(self):
        assert KafkaConnectionError.http_status_code == 503

    def test_error_code(self):
        assert KafkaConnectionError.error_code == "KAFKA_CONNECTION_ERROR"


class TestSchemaRegistryError:
    def test_is_exception(self):
        err = SchemaRegistryError("bad schema")
        assert isinstance(err, SchemaRegistryError)

    def test_http_status_code(self):
        assert SchemaRegistryError.http_status_code == 500

    def test_error_code(self):
        assert SchemaRegistryError.error_code == "SCHEMA_REGISTRY_ERROR"


# ===========================================================================
# Enums
# ===========================================================================


class TestDeliveryGuarantee:
    def test_values(self):
        assert DeliveryGuarantee.AT_MOST_ONCE.value == "at_most_once"
        assert DeliveryGuarantee.AT_LEAST_ONCE.value == "at_least_once"
        assert DeliveryGuarantee.EXACTLY_ONCE.value == "exactly_once"

    def test_all_members(self):
        assert len(DeliveryGuarantee) == 3


class TestAcknowledgmentMode:
    def test_values(self):
        assert AcknowledgmentMode.AUTO.value == "auto"
        assert AcknowledgmentMode.MANUAL.value == "manual"


class TestSchemaFormat:
    def test_values(self):
        assert SchemaFormat.AVRO.value == "avro"
        assert SchemaFormat.PROTOBUF.value == "protobuf"
        assert SchemaFormat.JSON.value == "json"


# ===========================================================================
# Data classes
# ===========================================================================


class TestKafkaConfig:
    def test_defaults(self):
        cfg = KafkaConfig(bootstrap_servers="broker:9092")
        assert cfg.client_id == "acgs2-governance"
        assert cfg.security_protocol == "PLAINTEXT"
        assert cfg.sasl_mechanism is None
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        cfg = KafkaConfig(
            bootstrap_servers="b:9092",
            client_id="my-client",
            sasl_mechanism="PLAIN",
            sasl_username="user",
            sasl_password="pass",  # pragma: allowlist secret
            ssl_cafile="/ca.pem",
            ssl_certfile="/cert.pem",
            ssl_keyfile="/key.pem",
        )
        assert cfg.sasl_mechanism == "PLAIN"
        assert cfg.sasl_username == "user"
        assert cfg.ssl_cafile == "/ca.pem"


class TestProducerConfig:
    def test_defaults(self):
        cfg = ProducerConfig()
        assert cfg.acks == "all"
        assert cfg.retries == 3
        assert cfg.delivery_guarantee == DeliveryGuarantee.AT_LEAST_ONCE
        assert cfg.enable_idempotence is True
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        cfg = ProducerConfig(retries=5, batch_size=1024, compression_type="gzip")
        assert cfg.retries == 5
        assert cfg.compression_type == "gzip"


class TestConsumerConfig:
    def test_defaults(self):
        cfg = ConsumerConfig(group_id="grp")
        assert cfg.auto_offset_reset == "earliest"
        assert cfg.enable_auto_commit is False
        assert cfg.acknowledgment_mode == AcknowledgmentMode.MANUAL
        assert cfg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_acknowledgment_mode(self):
        cfg = ConsumerConfig(group_id="grp", acknowledgment_mode=AcknowledgmentMode.AUTO)
        assert cfg.acknowledgment_mode == AcknowledgmentMode.AUTO


class TestEventSchema:
    def test_create(self):
        schema = EventSchema(
            name="LoginEvent",
            version="1.0",
            format=SchemaFormat.JSON,
            schema_definition={"type": "object"},
        )
        assert schema.name == "LoginEvent"
        assert schema.schema_id is None
        assert schema.constitutional_hash == CONSTITUTIONAL_HASH

    def test_with_subject_and_id(self):
        schema = EventSchema(
            name="X",
            version="2",
            format=SchemaFormat.AVRO,
            schema_definition='{"type":"record"}',
            subject="x-value",
            schema_id=42,
        )
        assert schema.subject == "x-value"
        assert schema.schema_id == 42


class TestPublishResult:
    def test_success(self):
        result = PublishResult(success=True, event_id="e1", topic="t1", partition=0, offset=5)
        assert result.success is True
        assert result.error is None
        assert result.constitutional_hash == CONSTITUTIONAL_HASH

    def test_failure(self):
        result = PublishResult(success=False, event_id="e2", error="timeout")
        assert result.success is False
        assert result.error == "timeout"


# ===========================================================================
# GovernanceEvent
# ===========================================================================


class TestGovernanceEvent:
    def test_defaults(self):
        evt = make_event()
        assert evt.source is None
        assert evt.correlation_id is None
        assert evt.headers == {}
        assert evt.constitutional_hash == CONSTITUTIONAL_HASH
        assert isinstance(evt.timestamp, datetime)

    def test_to_json_round_trip(self):
        evt = make_event(source="auth-service", correlation_id="corr-123")
        json_str = evt.to_json()
        data = json.loads(json_str)
        assert data["event_id"] == "evt-001"
        assert data["source"] == "auth-service"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_from_json(self):
        evt = make_event()
        json_str = evt.to_json()
        restored = GovernanceEvent.from_json(json_str)
        assert restored.event_id == evt.event_id
        assert restored.event_type == evt.event_type
        assert restored.tenant_id == evt.tenant_id

    def test_from_json_with_z_timestamp(self):
        data = {
            "event_id": "e1",
            "event_type": "t",
            "tenant_id": "ten",
            "timestamp": "2024-01-01T00:00:00Z",
            "payload": {},
            "source": None,
            "correlation_id": None,
            "headers": {},
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        evt = GovernanceEvent.from_json(json.dumps(data))
        assert evt.timestamp.tzinfo is not None

    def test_from_json_no_timestamp(self):
        data = {
            "event_id": "e1",
            "event_type": "t",
            "tenant_id": "ten",
            "payload": {},
            "headers": {},
        }
        evt = GovernanceEvent.from_json(json.dumps(data))
        assert evt.event_id == "e1"

    def test_to_bytes_and_from_bytes(self):
        evt = make_event()
        raw = evt.to_bytes()
        assert isinstance(raw, bytes)
        restored = GovernanceEvent.from_bytes(raw)
        assert restored.event_id == evt.event_id

    def test_to_json_raises_serialization_error_on_bad_payload(self):
        evt = make_event(payload={"obj": object()})
        with pytest.raises(SerializationError):
            evt.to_json()

    def test_serialize_payload_list(self):
        evt = make_event(payload=["a", 1, True, None])
        json_str = evt.to_json()
        data = json.loads(json_str)
        assert data["payload"] == ["a", 1, True, None]

    def test_serialize_payload_nested(self):
        evt = make_event(payload={"nested": {"key": "val"}})
        json_str = evt.to_json()
        data = json.loads(json_str)
        assert data["payload"]["nested"]["key"] == "val"

    def test_serialize_payload_non_serializable_in_dict_raises(self):
        evt = make_event(payload={"bad": object()})
        with pytest.raises(SerializationError, match="Non-serializable value"):
            evt.to_json()

    def test_custom_headers(self):
        evt = make_event(headers={"x-trace": "abc"})
        json_str = evt.to_json()
        data = json.loads(json_str)
        assert data["headers"]["x-trace"] == "abc"

    def test_from_json_uses_default_constitutional_hash_when_missing(self):
        data = {
            "event_id": "e1",
            "event_type": "t",
            "tenant_id": "ten",
            "payload": {},
            "headers": {},
        }
        evt = GovernanceEvent.from_json(json.dumps(data))
        assert evt.constitutional_hash == CONSTITUTIONAL_HASH


# ===========================================================================
# MockProducer
# ===========================================================================


class TestMockProducer:
    async def test_send(self):
        cfg = make_kafka_config()
        pcfg = make_producer_config()
        producer = MockProducer(cfg, pcfg)
        result = await producer.send("topic", b"hello")
        assert result["topic"] == "topic"
        assert result["partition"] == 0

    async def test_close(self):
        cfg = make_kafka_config()
        pcfg = make_producer_config()
        producer = MockProducer(cfg, pcfg)
        await producer.close()  # should not raise


# ===========================================================================
# KafkaConnectionPool
# ===========================================================================


class TestKafkaConnectionPool:
    async def test_start_populates_pool(self):
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=3)
        await pool.start()
        assert pool._started is True
        assert pool._pool.qsize() == 3
        await pool.stop()

    async def test_start_idempotent(self):
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=2)
        await pool.start()
        await pool.start()  # second call should be a no-op
        assert pool._pool.qsize() == 2
        await pool.stop()

    async def test_stop_clears_producers(self):
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=2)
        await pool.start()
        await pool.stop()
        assert pool._started is False
        assert len(pool._producers) == 0

    async def test_stop_when_not_started(self):
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=2)
        await pool.stop()  # should not raise

    async def test_acquire_and_release(self):
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=2)
        await pool.start()
        producer = await pool.acquire()
        assert isinstance(producer, MockProducer)
        assert pool._pool.qsize() == 1
        await pool.release(producer)
        assert pool._pool.qsize() == 2
        await pool.stop()

    async def test_acquire_starts_pool_if_not_started(self):
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=1)
        assert pool._started is False
        producer = await pool.acquire()
        assert pool._started is True
        await pool.release(producer)
        await pool.stop()

    async def test_health_check_started(self):
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=2)
        await pool.start()
        health = await pool.health_check()
        assert health["healthy"] is True
        assert health["pool_size"] == 2
        assert health["available_connections"] == 2
        assert health["constitutional_hash"] == CONSTITUTIONAL_HASH
        await pool.stop()

    async def test_health_check_not_started(self):
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=2)
        health = await pool.health_check()
        assert health["healthy"] is False
        assert health["available_connections"] == 0

    async def test_close_producer_with_async_close(self):
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=1)
        mock_producer = AsyncMock()
        mock_producer.close = AsyncMock()
        await pool._close_producer(mock_producer)
        mock_producer.close.assert_awaited_once()

    async def test_close_producer_with_sync_close(self):
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=1)
        mock_producer = MagicMock()
        mock_producer.close = MagicMock(return_value=None)
        await pool._close_producer(mock_producer)
        mock_producer.close.assert_called_once()

    async def test_stop_swallows_close_errors(self):
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=2)
        await pool.start()

        # Patch _close_producer to raise RuntimeError
        async def bad_close(p):
            raise RuntimeError("fail")

        pool._close_producer = bad_close
        # Should not raise
        await pool.stop()
        assert pool._started is False

    async def test_constitutional_hash(self):
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config())
        assert pool.constitutional_hash == CONSTITUTIONAL_HASH


# ===========================================================================
# KafkaEventPublisher
# ===========================================================================


class TestKafkaEventPublisher:
    async def test_publish_success(self):
        cfg = make_kafka_config()
        publisher = KafkaEventPublisher(cfg)
        evt = make_event()
        result = await publisher.publish("my-topic", evt)
        assert result.success is True
        assert result.event_id == "evt-001"
        assert result.topic == "my-topic"

    async def test_publish_with_key(self):
        publisher = KafkaEventPublisher(make_kafka_config())
        evt = make_event()
        result = await publisher.publish("t", evt, key="k1")
        assert result.success is True

    async def test_publish_with_on_delivery_callback(self):
        publisher = KafkaEventPublisher(make_kafka_config())
        evt = make_event()
        calls = []

        def cb(event_id, success, err):
            calls.append((event_id, success, err))

        result = await publisher.publish("t", evt, on_delivery=cb)
        assert result.success is True
        assert calls[0] == ("evt-001", True, None)

    async def test_publish_handles_error_and_calls_on_delivery(self):
        publisher = KafkaEventPublisher(make_kafka_config())
        evt = make_event()

        async def fail_send(*args, **kwargs):
            raise RuntimeError("Kafka is down")

        publisher._send_to_kafka = fail_send

        calls = []

        def cb(event_id, success, err):
            calls.append((event_id, success, err))

        result = await publisher.publish("t", evt, on_delivery=cb)
        assert result.success is False
        assert "Kafka is down" in result.error
        assert calls[0][1] is False

    async def test_publish_handles_error_without_callback(self):
        publisher = KafkaEventPublisher(make_kafka_config())
        evt = make_event()

        async def fail_send(*args, **kwargs):
            raise ConnectionError("refused")

        publisher._send_to_kafka = fail_send
        result = await publisher.publish("t", evt)
        assert result.success is False
        assert result.error is not None

    async def test_publish_batch(self):
        publisher = KafkaEventPublisher(make_kafka_config())
        events = [make_event(event_id=f"e{i}") for i in range(4)]
        results = await publisher.publish_batch("topic", events)
        assert len(results) == 4
        assert all(r.success for r in results)

    async def test_publish_batch_with_key_extractor(self):
        publisher = KafkaEventPublisher(make_kafka_config())
        events = [make_event(event_id=f"e{i}", tenant_id=f"t{i}") for i in range(3)]
        results = await publisher.publish_batch(
            "topic", events, key_extractor=lambda e: e.tenant_id
        )
        assert len(results) == 3

    async def test_ensure_pool_creates_pool_once(self):
        publisher = KafkaEventPublisher(make_kafka_config())
        assert publisher._pool is None
        await publisher._ensure_pool()
        pool_first = publisher._pool
        await publisher._ensure_pool()
        # Same pool object reused
        assert publisher._pool is pool_first

    async def test_close_with_pool(self):
        publisher = KafkaEventPublisher(make_kafka_config())
        await publisher._ensure_pool()
        await publisher.close()  # should not raise

    async def test_close_without_pool(self):
        publisher = KafkaEventPublisher(make_kafka_config())
        await publisher.close()  # _pool is None, should be a no-op

    async def test_send_batch_returns_true_list(self):
        publisher = KafkaEventPublisher(make_kafka_config())
        events = [make_event(event_id=f"e{i}") for i in range(3)]
        results = await publisher._send_batch("t", events)
        assert results == [True, True, True]

    def test_constitutional_hash(self):
        publisher = KafkaEventPublisher(make_kafka_config())
        assert publisher.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_publish_with_custom_producer_config(self):
        pcfg = make_producer_config(retries=5)
        publisher = KafkaEventPublisher(make_kafka_config(), pcfg)
        evt = make_event()
        result = await publisher.publish("t", evt)
        assert result.success is True


# ===========================================================================
# GovernanceEventProducer
# ===========================================================================


class TestGovernanceEventProducer:
    async def test_publish_success(self):
        producer = GovernanceEventProducer(make_kafka_config())
        evt = make_event()
        result = await producer.publish("topic", evt)
        assert result.success is True
        assert result.event_id == "evt-001"

    async def test_publish_with_key(self):
        producer = GovernanceEventProducer(make_kafka_config())
        evt = make_event()
        result = await producer.publish("topic", evt, key="k1")
        assert result.success is True

    async def test_publish_with_on_delivery_success(self):
        producer = GovernanceEventProducer(make_kafka_config())
        evt = make_event()
        calls = []

        def cb(event_id, success, err):
            calls.append((event_id, success, err))

        result = await producer.publish("topic", evt, on_delivery=cb)
        assert result.success is True
        assert calls[0] == ("evt-001", True, None)

    async def test_publish_retries_on_failure(self):
        pcfg = make_producer_config(retries=2, retry_backoff_ms=1)
        producer = GovernanceEventProducer(make_kafka_config(), pcfg)

        call_count = 0

        async def fail_send(topic, event, key):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("transient error")

        producer._send_to_kafka = fail_send
        evt = make_event()
        result = await producer.publish("t", evt)
        # retries=2 means 3 total attempts
        assert call_count == 3
        assert result.success is False

    async def test_publish_calls_on_delivery_on_failure(self):
        pcfg = make_producer_config(retries=0, retry_backoff_ms=1)
        producer = GovernanceEventProducer(make_kafka_config(), pcfg)

        async def fail_send(topic, event, key):
            raise ValueError("bad")

        producer._send_to_kafka = fail_send

        calls = []

        def cb(event_id, success, err):
            calls.append((event_id, success, err))

        result = await producer.publish("t", make_event(), on_delivery=cb)
        assert result.success is False
        assert calls[0][1] is False
        assert "bad" in calls[0][2]

    async def test_publish_unknown_error_when_no_exception(self):
        """Covers the path where last_error is None (all attempts return False)."""
        pcfg = make_producer_config(retries=0)
        producer = GovernanceEventProducer(make_kafka_config(), pcfg)

        # _send_to_kafka returns False without raising
        async def false_send(topic, event, key):
            return False

        producer._send_to_kafka = false_send
        result = await producer.publish("t", make_event())
        assert result.success is False
        assert result.error == "Unknown error"

    async def test_close(self):
        producer = GovernanceEventProducer(make_kafka_config())
        await producer.close()  # should not raise

    def test_constitutional_hash(self):
        producer = GovernanceEventProducer(make_kafka_config())
        assert producer.constitutional_hash == CONSTITUTIONAL_HASH


# ===========================================================================
# SchemaRegistry
# ===========================================================================


class TestSchemaRegistry:
    async def test_register_schema(self):
        registry = SchemaRegistry(url="http://schema-registry:8081")
        schema = EventSchema(
            name="Test",
            version="1",
            format=SchemaFormat.JSON,
            schema_definition={"type": "object"},
        )
        schema_id = await registry.register_schema("test-value", schema)
        assert schema_id == 1

    async def test_get_schema_caches_result(self):
        registry = SchemaRegistry(url="http://schema-registry:8081")
        schema = await registry.get_schema(42)
        assert schema == {"type": "record", "name": "TestSchema"}
        # Second call should use cache
        schema2 = await registry.get_schema(42)
        assert schema2 == schema
        assert 42 in registry._schema_cache

    async def test_get_schema_cache_hit(self):
        registry = SchemaRegistry(url="http://sr:8081")
        registry._schema_cache[99] = {"cached": True}
        schema = await registry.get_schema(99)
        assert schema == {"cached": True}

    async def test_check_compatibility(self):
        registry = SchemaRegistry(url="http://sr:8081")
        schema = EventSchema(
            name="T",
            version="1",
            format=SchemaFormat.AVRO,
            schema_definition='{"type":"record","name":"T","fields":[]}',
        )
        result = await registry.check_compatibility("t-value", schema)
        assert result is True

    def test_serialize(self):
        registry = SchemaRegistry(url="http://sr:8081")
        schema = EventSchema(
            name="T",
            version="1",
            format=SchemaFormat.JSON,
            schema_definition={},
        )
        raw = registry.serialize(schema, {"key": "value"})
        assert isinstance(raw, bytes)
        assert json.loads(raw) == {"key": "value"}

    def test_deserialize(self):
        registry = SchemaRegistry(url="http://sr:8081")
        schema = EventSchema(
            name="T",
            version="1",
            format=SchemaFormat.JSON,
            schema_definition={},
        )
        data = json.dumps({"foo": "bar"}).encode("utf-8")
        result = registry.deserialize(schema, data)
        assert result == {"foo": "bar"}

    def test_constitutional_hash(self):
        registry = SchemaRegistry(url="http://sr:8081")
        assert registry.constitutional_hash == CONSTITUTIONAL_HASH

    def test_auto_register_default(self):
        registry = SchemaRegistry(url="http://sr:8081")
        assert registry.auto_register is True

    def test_cache_capacity(self):
        registry = SchemaRegistry(url="http://sr:8081", cache_capacity=50)
        assert registry._cache_capacity == 50


# ===========================================================================
# GovernanceEventConsumer
# ===========================================================================


class TestGovernanceEventConsumer:
    async def test_subscribe(self):
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        await consumer.subscribe(["topic-a", "topic-b"])
        assert consumer._subscribed_topics == ["topic-a", "topic-b"]

    async def test_consume_returns_none(self):
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        result = await consumer.consume()
        assert result is None

    async def test_consume_batch_returns_empty(self):
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        events = await consumer.consume_batch()
        assert events == []

    async def test_commit(self):
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        await consumer.commit()  # no-op, should not raise

    async def test_commit_offsets(self):
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        await consumer.commit_offsets({"partition-0": 100})

    async def test_seek_to_beginning(self):
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        await consumer.seek_to_beginning("topic", 0)

    async def test_get_lag(self):
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        lag = await consumer.get_lag()
        assert lag == {}

    async def test_close(self):
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        consumer._running = True
        await consumer.close()
        assert consumer._running is False

    async def test_consume_with_handler_no_events(self):
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        calls = []

        async def handler(evt):
            calls.append(evt)

        processed = await consumer.consume_with_handler(handler)
        assert processed == 0
        assert calls == []

    async def test_consume_with_handler_processes_events(self):
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        events_to_yield = [make_event(event_id=f"e{i}") for i in range(3)]
        events_iter = iter(events_to_yield)

        async def mock_poll(timeout_ms):
            return next(events_iter, None)

        consumer._poll = mock_poll

        collected = []

        async def handler(evt):
            collected.append(evt.event_id)

        processed = await consumer.consume_with_handler(handler, max_events=3)
        assert processed == 3
        assert collected == ["e0", "e1", "e2"]

    async def test_consume_with_handler_manual_ack_commits(self):
        cfg = make_consumer_config(acknowledgment_mode=AcknowledgmentMode.MANUAL)
        consumer = GovernanceEventConsumer(make_kafka_config(), cfg)

        events_iter = iter([make_event(event_id="e0"), None])

        async def mock_poll(timeout_ms):
            return next(events_iter, None)

        consumer._poll = mock_poll

        commit_calls = []

        async def mock_commit():
            commit_calls.append(1)

        consumer._commit = mock_commit

        async def handler(evt):
            pass

        await consumer.consume_with_handler(handler)
        assert len(commit_calls) == 1

    async def test_consume_with_handler_auto_ack_does_not_commit(self):
        cfg = make_consumer_config(acknowledgment_mode=AcknowledgmentMode.AUTO)
        consumer = GovernanceEventConsumer(make_kafka_config(), cfg)

        events_iter = iter([make_event(event_id="e0"), None])

        async def mock_poll(timeout_ms):
            return next(events_iter, None)

        consumer._poll = mock_poll

        commit_calls = []

        async def mock_commit():
            commit_calls.append(1)

        consumer._commit = mock_commit

        async def handler(evt):
            pass

        await consumer.consume_with_handler(handler)
        assert len(commit_calls) == 0

    async def test_consume_with_handler_respects_max_events(self):
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        counter = [0]

        async def infinite_poll(timeout_ms):
            evt = make_event(event_id=f"e{counter[0]}")
            counter[0] += 1
            return evt

        consumer._poll = infinite_poll

        async def handler(evt):
            pass

        processed = await consumer.consume_with_handler(handler, max_events=5)
        assert processed == 5

    def test_constitutional_hash(self):
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        assert consumer.constitutional_hash == CONSTITUTIONAL_HASH


# ===========================================================================
# DeadLetterQueue
# ===========================================================================


class TestDeadLetterQueue:
    async def test_send_to_dlq(self):
        dlq = DeadLetterQueue(topic="events-dlq")
        evt = make_event()
        result = await dlq.send(evt, RuntimeError("fail"), retry_count=2)
        assert result is True

    def test_default_permanent_failure_topic(self):
        dlq = DeadLetterQueue(topic="my-dlq")
        assert dlq.permanent_failure_topic == "my-dlq-permanent"

    def test_custom_permanent_failure_topic(self):
        dlq = DeadLetterQueue(topic="t", permanent_failure_topic="custom-pf")
        assert dlq.permanent_failure_topic == "custom-pf"

    async def test_handle_max_retries_exceeded(self):
        dlq = DeadLetterQueue(topic="dlq")
        evt = make_event()
        result = await dlq.handle_max_retries_exceeded(evt, RuntimeError("too many"))
        assert result is True

    async def test_reprocess_empty_dlq(self):
        dlq = DeadLetterQueue(topic="dlq")
        processed = await dlq.reprocess(handler=AsyncMock(return_value=True))
        assert processed == 0

    async def test_reprocess_calls_handler(self):
        dlq = DeadLetterQueue(topic="dlq")
        events = [make_event(event_id=f"e{i}") for i in range(3)]

        async def mock_consume(max_events):
            return events

        dlq._consume_dlq = mock_consume

        handler_calls = []

        async def handler(evt):
            handler_calls.append(evt.event_id)
            return True

        processed = await dlq.reprocess(handler=handler, max_events=3)
        assert processed == 3
        assert handler_calls == ["e0", "e1", "e2"]

    async def test_reprocess_skips_failed_events(self):
        dlq = DeadLetterQueue(topic="dlq")
        events = [make_event(event_id="good"), make_event(event_id="bad")]

        async def mock_consume(max_events):
            return events

        dlq._consume_dlq = mock_consume

        async def handler(evt):
            if evt.event_id == "bad":
                raise RuntimeError("handler error")
            return True

        processed = await dlq.reprocess(handler=handler)
        assert processed == 1

    async def test_reprocess_counts_only_successful(self):
        dlq = DeadLetterQueue(topic="dlq")
        events = [make_event(event_id=f"e{i}") for i in range(4)]

        async def mock_consume(max_events):
            return events

        dlq._consume_dlq = mock_consume

        async def handler(evt):
            return evt.event_id in ("e0", "e2")

        processed = await dlq.reprocess(handler=handler)
        assert processed == 2

    def test_constitutional_hash(self):
        dlq = DeadLetterQueue(topic="t")
        assert dlq.constitutional_hash == CONSTITUTIONAL_HASH

    async def test_send_includes_error_metadata(self):
        dlq = DeadLetterQueue(topic="dlq")

        captured_metadata = {}

        async def mock_send(event, metadata):
            captured_metadata.update(metadata)
            return True

        dlq._send = mock_send
        evt = make_event()
        await dlq.send(evt, ValueError("oops"), retry_count=1)

        assert captured_metadata["error_type"] == "ValueError"
        assert captured_metadata["error_message"] == "oops"
        assert captured_metadata["retry_count"] == 1
        assert captured_metadata["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_internal_send(self):
        dlq = DeadLetterQueue(topic="dlq")
        evt = make_event()
        result = await dlq._send(event=evt, metadata={"x": 1})
        assert result is True

    async def test_internal_consume_dlq(self):
        dlq = DeadLetterQueue(topic="dlq")
        events = await dlq._consume_dlq(max_events=10)
        assert events == []

    async def test_internal_send_to_permanent_failure(self):
        dlq = DeadLetterQueue(topic="dlq")
        evt = make_event()
        result = await dlq._send_to_permanent_failure(evt, RuntimeError("final"))
        assert result is True


# ===========================================================================
# Additional branch coverage
# ===========================================================================


class TestGovernanceEventAdditionalBranches:
    """Additional tests targeting specific missing lines."""

    def test_to_json_raises_when_json_dumps_fails(self):
        """Line 187: SerializationError from json.dumps TypeError."""
        evt = make_event(payload={})
        # Temporarily patch json.dumps to raise TypeError
        import json as json_mod

        original = json_mod.dumps

        def bad_dumps(obj):
            raise TypeError("not serializable")

        import unittest.mock as um

        with um.patch(
            "enhanced_agent_bus.enterprise_sso.kafka_streaming.json.dumps",
            side_effect=TypeError("not serializable"),
        ):
            with pytest.raises(SerializationError, match="Failed to serialize"):
                evt.to_json()

    def test_serialize_payload_list_with_items(self):
        """Line 199: list comprehension in _serialize_payload."""
        evt = make_event(payload=["a", "b", "c"])
        result = evt._serialize_payload(["a", "b", "c"])
        assert result == ["a", "b", "c"]

    def test_serialize_payload_nested_list(self):
        """Line 199: nested list recursion."""
        evt = make_event()
        result = evt._serialize_payload([{"k": "v"}, [1, 2]])
        assert result == [{"k": "v"}, [1, 2]]

    def test_from_json_timestamp_none(self):
        """Line 207->210: timestamp is None, skip fromisoformat branch."""
        data = {
            "event_id": "e1",
            "event_type": "t",
            "tenant_id": "ten",
            "timestamp": None,
            "payload": {},
            "headers": {},
        }
        evt = GovernanceEvent.from_json(json.dumps(data))
        assert evt.timestamp is None

    def test_from_json_timestamp_not_string(self):
        """Line 207->210: timestamp present but not a string."""
        data = {
            "event_id": "e1",
            "event_type": "t",
            "tenant_id": "ten",
            "timestamp": 12345,  # integer, not string
            "payload": {},
            "headers": {},
        }
        evt = GovernanceEvent.from_json(json.dumps(data))
        assert evt.timestamp == 12345

    def test_from_bytes_direct(self):
        """Line 229: from_bytes method."""
        evt = make_event()
        raw = evt.to_bytes()
        restored = GovernanceEvent.from_bytes(raw)
        assert restored.event_id == evt.event_id


class TestConnectionPoolInternalClose:
    """Tests targeting _close_producer branches."""

    async def test_close_producer_no_close_attr(self):
        """Line 319->exit: producer has no close attribute."""
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=1)

        # Object with no close attribute
        class NoClose:
            pass

        await pool._close_producer(NoClose())  # should not raise

    async def test_close_producer_sync_close_returns_coroutine(self):
        """Line 322: await result when close() returns a coroutine."""
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=1)
        awaited = []

        async def async_close():
            awaited.append(True)

        mock_producer = MagicMock()
        mock_producer.close = async_close
        await pool._close_producer(mock_producer)
        assert awaited == [True]

    async def test_stop_catches_runtime_error(self):
        """Lines 296-297: RuntimeError swallowed in stop."""
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=2)
        await pool.start()

        async def raises_runtime(p):
            raise RuntimeError("oops")

        pool._close_producer = raises_runtime
        await pool.stop()  # should not raise
        assert pool._started is False

    async def test_stop_catches_connection_error(self):
        """Lines 296-297: ConnectionError swallowed in stop."""
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=1)
        await pool.start()

        async def raises_conn(p):
            raise ConnectionError("down")

        pool._close_producer = raises_conn
        await pool.stop()
        assert pool._started is False

    async def test_stop_catches_os_error(self):
        """Lines 296-297: OSError swallowed in stop."""
        pool = KafkaConnectionPool(make_kafka_config(), make_producer_config(), pool_size=1)
        await pool.start()

        async def raises_os(p):
            raise OSError("io error")

        pool._close_producer = raises_os
        await pool.stop()
        assert pool._started is False


class TestMockProducerDirectCalls:
    """Directly call MockProducer.send and close to hit lines 343/347."""

    async def test_mock_producer_send_direct(self):
        cfg = make_kafka_config()
        pcfg = make_producer_config()
        p = MockProducer(cfg, pcfg)
        result = await p.send("mytopic", b"data", key=b"k", headers={"h": "v"})
        assert result == {"topic": "mytopic", "partition": 0, "offset": 1}

    async def test_mock_producer_close_direct(self):
        cfg = make_kafka_config()
        pcfg = make_producer_config()
        p = MockProducer(cfg, pcfg)
        await p.close()  # line 347: pass


class TestKafkaEventPublisherInternalMethods:
    """Direct calls to publisher internal methods."""

    async def test_send_to_kafka_direct(self):
        """Line 422: _send_to_kafka direct call."""
        publisher = KafkaEventPublisher(make_kafka_config())
        evt = make_event()
        result = await publisher._send_to_kafka("t", evt)
        assert result is True

    async def test_send_to_kafka_with_key_and_headers(self):
        publisher = KafkaEventPublisher(make_kafka_config())
        evt = make_event()
        result = await publisher._send_to_kafka("t", evt, key="k", headers={"h": "v"})
        assert result is True

    async def test_send_batch_empty(self):
        """Line 426: _send_batch with empty list."""
        publisher = KafkaEventPublisher(make_kafka_config())
        result = await publisher._send_batch("t", [])
        assert result == []

    async def test_close_calls_pool_stop(self):
        """Lines 430-431: close() when pool exists."""
        publisher = KafkaEventPublisher(make_kafka_config())
        await publisher._ensure_pool()
        assert publisher._pool is not None
        await publisher.close()

    async def test_publish_on_delivery_success_path(self):
        """Line 385: on_delivery called on success path."""
        publisher = KafkaEventPublisher(make_kafka_config())
        evt = make_event()
        recorded = []

        def cb(event_id, success, err):
            recorded.append({"id": event_id, "success": success, "err": err})

        await publisher.publish("t", evt, on_delivery=cb)
        assert recorded[0]["success"] is True
        assert recorded[0]["err"] is None

    async def test_publish_exception_with_on_delivery(self):
        """Lines 393-397: exception path with on_delivery callback."""
        publisher = KafkaEventPublisher(make_kafka_config())
        evt = make_event()

        async def raise_os(*args, **kwargs):
            raise OSError("connection reset")

        publisher._send_to_kafka = raise_os

        recorded = []

        def cb(event_id, success, err):
            recorded.append({"success": success, "err": err})

        result = await publisher.publish("t", evt, on_delivery=cb)
        assert result.success is False
        assert recorded[0]["success"] is False
        assert "connection reset" in recorded[0]["err"]

    async def test_publish_exception_no_callback(self):
        """Lines 393-397: exception path without on_delivery callback."""
        publisher = KafkaEventPublisher(make_kafka_config())
        evt = make_event()

        async def raise_timeout(*args, **kwargs):
            raise TimeoutError("timed out")

        publisher._send_to_kafka = raise_timeout

        result = await publisher.publish("t", evt)
        assert result.success is False
        assert "timed out" in result.error


class TestGovernanceEventProducerInternals:
    """Direct calls to GovernanceEventProducer internal methods."""

    async def test_send_to_kafka_direct(self):
        """Line 486: _send_to_kafka direct call."""
        producer = GovernanceEventProducer(make_kafka_config())
        result = await producer._send_to_kafka("t", make_event(), key=None)
        assert result is True

    async def test_close_direct(self):
        """Line 490: close() direct call."""
        producer = GovernanceEventProducer(make_kafka_config())
        await producer.close()

    async def test_publish_retry_continue_branch(self):
        """Lines 462->459, 469-470: retry loop continues on exception with retries left."""
        pcfg = make_producer_config(retries=2, retry_backoff_ms=1)
        producer = GovernanceEventProducer(make_kafka_config(), pcfg)

        attempts = []

        async def fail_then_succeed(topic, event, key):
            attempts.append(1)
            if len(attempts) < 3:
                raise AttributeError("transient")
            return True

        producer._send_to_kafka = fail_then_succeed
        result = await producer.publish("t", make_event())
        assert result.success is True
        assert len(attempts) == 3

    async def test_publish_break_after_max_retries(self):
        """Lines 471-476: break after max retries exhausted."""
        pcfg = make_producer_config(retries=1, retry_backoff_ms=1)
        producer = GovernanceEventProducer(make_kafka_config(), pcfg)

        async def always_fail(topic, event, key):
            raise TypeError("type mismatch")

        producer._send_to_kafka = always_fail

        calls = []

        def cb(eid, success, err):
            calls.append((success, err))

        result = await producer.publish("t", make_event(), on_delivery=cb)
        assert result.success is False
        assert calls[0][0] is False
        assert "type mismatch" in calls[0][1]


class TestSchemaRegistryInternalMethods:
    """Direct calls to SchemaRegistry internal methods."""

    async def test_register_schema_internal(self):
        """Line 514: _register_schema direct call."""
        registry = SchemaRegistry(url="http://sr:8081")
        schema = EventSchema("T", "1", SchemaFormat.JSON, {})
        result = await registry._register_schema("subject", schema)
        assert result == 1

    async def test_get_schema_internal(self):
        """Line 527: _get_schema direct call."""
        registry = SchemaRegistry(url="http://sr:8081")
        result = await registry._get_schema(99)
        assert result == {"type": "record", "name": "TestSchema"}

    async def test_check_compatibility_internal(self):
        """Line 535: _check_compatibility direct call."""
        registry = SchemaRegistry(url="http://sr:8081")
        schema = EventSchema("T", "1", SchemaFormat.AVRO, {})
        result = await registry._check_compatibility("subject", schema)
        assert result is True

    def test_serialize_internal(self):
        """Line 543: _serialize direct call."""
        registry = SchemaRegistry(url="http://sr:8081")
        schema = EventSchema("T", "1", SchemaFormat.JSON, {})
        result = registry._serialize(schema, {"a": 1})
        assert json.loads(result) == {"a": 1}

    def test_deserialize_internal(self):
        """Line 551: _deserialize direct call."""
        registry = SchemaRegistry(url="http://sr:8081")
        schema = EventSchema("T", "1", SchemaFormat.JSON, {})
        result = registry._deserialize(schema, json.dumps({"b": 2}).encode())
        assert result == {"b": 2}

    async def test_get_schema_no_cache_then_caches(self):
        """Line 519: cache miss path, then cache stores result."""
        registry = SchemaRegistry(url="http://sr:8081")
        # Ensure not in cache
        assert 7 not in registry._schema_cache
        result = await registry.get_schema(7)
        assert result == {"type": "record", "name": "TestSchema"}
        assert 7 in registry._schema_cache


class TestGovernanceEventConsumerInternalMethods:
    """Direct calls to consumer internal methods."""

    async def test_subscribe_internal(self):
        """Line 576: _subscribe direct call."""
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        await consumer._subscribe(["topic-x"])  # pass, should not raise

    async def test_poll_internal(self):
        """Line 584: _poll direct call."""
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        result = await consumer._poll(500)
        assert result is None

    async def test_poll_batch_internal(self):
        """Line 594: _poll_batch direct call."""
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        result = await consumer._poll_batch(10, 1000)
        assert result == []

    async def test_commit_internal(self):
        """Line 602 (pass in _commit): direct call."""
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        await consumer._commit()  # pass statement

    async def test_commit_offsets_internal(self):
        """Line 610 (pass in _commit_offsets): direct call."""
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        await consumer._commit_offsets({"p0": 42})

    async def test_seek_to_beginning_internal(self):
        """Line 639: _seek_to_beginning direct call."""
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        await consumer._seek_to_beginning("topic", 0)

    async def test_get_lag_internal(self):
        """Line 647: _get_lag direct call."""
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        result = await consumer._get_lag()
        assert result == {}

    async def test_close_sets_running_false(self):
        """Line 651: close() sets _running = False."""
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        consumer._running = True
        await consumer.close()
        assert consumer._running is False

    async def test_consume_with_handler_max_events_none_stops_on_none(self):
        """Lines 620/623: max_events=None loop breaks when poll returns None."""
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        # _poll returns None immediately
        result = await consumer.consume_with_handler(AsyncMock(), max_events=None)
        assert result == 0

    async def test_consume_with_handler_processed_increments(self):
        """Line 626: processed += 1 after handler."""
        consumer = GovernanceEventConsumer(make_kafka_config(), make_consumer_config())
        events_iter = iter([make_event(), None])

        async def mock_poll(t):
            return next(events_iter, None)

        consumer._poll = mock_poll
        result = await consumer.consume_with_handler(AsyncMock(), max_events=None)
        assert result == 1
