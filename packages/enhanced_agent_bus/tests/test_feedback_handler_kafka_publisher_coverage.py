# Constitutional Hash: 608508a9bd224290
# Sprint 57 -- feedback_handler/kafka_publisher.py coverage
"""
Comprehensive tests for FeedbackKafkaPublisher to achieve ≥95% coverage.

Covers:
- FeedbackKafkaPublisher.__init__
- FeedbackKafkaPublisher.start  (KAFKA_AVAILABLE=True/False, already running, error paths)
- FeedbackKafkaPublisher.stop   (running, not running, error during stop)
- FeedbackKafkaPublisher.publish (running, not running, error)
- FeedbackKafkaPublisher.publish_batch
- FeedbackKafkaPublisher._serialize_event (enum + non-enum branches, datetime + string)
- FeedbackKafkaPublisher._sanitize_error
- FeedbackKafkaPublisher._sanitize_bootstrap
- FeedbackKafkaPublisher.is_running (property)
- FeedbackKafkaPublisher.publish_sync (running loop branch, no loop branch)
- get_feedback_kafka_publisher (first call, second call)
- publish_feedback_event
- Module-level constants
"""

from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from enhanced_agent_bus.feedback_handler.enums import FeedbackType, OutcomeStatus
from enhanced_agent_bus.feedback_handler.models import StoredFeedbackEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(
    *,
    id: str = "evt-001",
    decision_id: str = "dec-abc",
    feedback_type: Any = FeedbackType.POSITIVE,
    outcome: Any = OutcomeStatus.SUCCESS,
    user_id: str | None = "user-1",
    tenant_id: str | None = "tenant-1",
    comment: str | None = "looks good",
    correction_data: dict | None = None,
    features: dict | None = None,
    actual_impact: float | None = 0.9,
    metadata: dict | None = None,
    created_at: Any = None,
    processed: bool = False,
) -> StoredFeedbackEvent:
    if created_at is None:
        created_at = datetime(2026, 1, 1, 12, 0, 0)
    return StoredFeedbackEvent(
        id=id,
        decision_id=decision_id,
        feedback_type=feedback_type,
        outcome=outcome,
        user_id=user_id,
        tenant_id=tenant_id,
        comment=comment,
        correction_data=correction_data,
        features=features,
        actual_impact=actual_impact,
        metadata=metadata,
        created_at=created_at,
        processed=processed,
    )


# ---------------------------------------------------------------------------
# Build a fake aiokafka module so we can toggle KAFKA_AVAILABLE=True
# ---------------------------------------------------------------------------


def _make_mock_aiokafka() -> types.ModuleType:
    """Return a mock aiokafka module with AIOKafkaProducer."""
    mod = types.ModuleType("aiokafka")
    producer_cls = MagicMock(name="AIOKafkaProducer")
    mod.AIOKafkaProducer = producer_cls
    return mod


# ---------------------------------------------------------------------------
# Tests - module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_kafka_available_is_bool(self):
        from enhanced_agent_bus.feedback_handler import kafka_publisher as kp

        assert isinstance(kp.KAFKA_AVAILABLE, bool)

    def test_kafka_bootstrap_default(self):
        from enhanced_agent_bus.feedback_handler import kafka_publisher as kp

        assert isinstance(kp.KAFKA_BOOTSTRAP, str)
        assert ":" in kp.KAFKA_BOOTSTRAP or kp.KAFKA_BOOTSTRAP  # non-empty

    def test_kafka_topic_feedback_default(self):
        from enhanced_agent_bus.feedback_handler import kafka_publisher as kp

        assert kp.KAFKA_TOPIC_FEEDBACK


# ---------------------------------------------------------------------------
# Tests - __init__
# ---------------------------------------------------------------------------


class TestFeedbackKafkaPublisherInit:
    def test_defaults(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            KAFKA_BOOTSTRAP,
            KAFKA_TOPIC_FEEDBACK,
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher()
        assert pub.bootstrap_servers == KAFKA_BOOTSTRAP
        assert pub.topic == KAFKA_TOPIC_FEEDBACK
        assert pub.client_id == "acgs2-feedback-publisher"
        assert pub._producer is None
        assert pub._running is False

    def test_custom_args(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher(
            bootstrap_servers="broker1:9092,broker2:9092",
            topic="my.topic",
            client_id="custom-client",
        )
        assert pub.bootstrap_servers == "broker1:9092,broker2:9092"
        assert pub.topic == "my.topic"
        assert pub.client_id == "custom-client"

    def test_bootstrap_none_uses_env(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            KAFKA_BOOTSTRAP,
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher(bootstrap_servers=None)
        assert pub.bootstrap_servers == KAFKA_BOOTSTRAP

    def test_topic_none_uses_env(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            KAFKA_TOPIC_FEEDBACK,
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher(topic=None)
        assert pub.topic == KAFKA_TOPIC_FEEDBACK


# ---------------------------------------------------------------------------
# Tests - start()
# ---------------------------------------------------------------------------


class TestFeedbackKafkaPublisherStart:
    async def test_start_kafka_unavailable(self):
        """When KAFKA_AVAILABLE is False, start() returns False."""
        import enhanced_agent_bus.feedback_handler.kafka_publisher as kp

        pub = kp.FeedbackKafkaPublisher()
        with patch.object(kp, "KAFKA_AVAILABLE", False):
            result = await pub.start()
        assert result is False
        assert pub._running is False

    async def test_start_already_running(self):
        """If already running, start() returns True immediately."""
        import enhanced_agent_bus.feedback_handler.kafka_publisher as kp

        pub = kp.FeedbackKafkaPublisher()
        pub._running = True
        with patch.object(kp, "KAFKA_AVAILABLE", True):
            result = await pub.start()
        assert result is True

    async def test_start_success(self):
        """Happy-path start with mocked AIOKafkaProducer."""
        import enhanced_agent_bus.feedback_handler.kafka_publisher as kp

        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock()
        producer_cls = MagicMock(return_value=mock_producer)

        with (
            patch.object(kp, "KAFKA_AVAILABLE", True),
            patch.object(kp, "AIOKafkaProducer", producer_cls, create=True),
        ):
            pub = kp.FeedbackKafkaPublisher()
            result = await pub.start()

        assert result is True
        assert pub._running is True
        mock_producer.start.assert_awaited_once()

    async def test_start_producer_raises_runtime_error(self):
        """RuntimeError during producer.start() → returns False."""
        import enhanced_agent_bus.feedback_handler.kafka_publisher as kp

        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock(side_effect=RuntimeError("connection refused"))
        producer_cls = MagicMock(return_value=mock_producer)

        with (
            patch.object(kp, "KAFKA_AVAILABLE", True),
            patch.object(kp, "AIOKafkaProducer", producer_cls, create=True),
        ):
            pub = kp.FeedbackKafkaPublisher()
            result = await pub.start()

        assert result is False
        assert pub._running is False
        assert pub._producer is None

    async def test_start_producer_raises_value_error(self):
        """ValueError during init → returns False."""
        import enhanced_agent_bus.feedback_handler.kafka_publisher as kp

        producer_cls = MagicMock(side_effect=ValueError("bad config"))

        with (
            patch.object(kp, "KAFKA_AVAILABLE", True),
            patch.object(kp, "AIOKafkaProducer", producer_cls, create=True),
        ):
            pub = kp.FeedbackKafkaPublisher()
            result = await pub.start()

        assert result is False

    async def test_start_producer_raises_type_error(self):
        """TypeError during init → returns False."""
        import enhanced_agent_bus.feedback_handler.kafka_publisher as kp

        producer_cls = MagicMock(side_effect=TypeError("type err"))

        with (
            patch.object(kp, "KAFKA_AVAILABLE", True),
            patch.object(kp, "AIOKafkaProducer", producer_cls, create=True),
        ):
            pub = kp.FeedbackKafkaPublisher()
            result = await pub.start()

        assert result is False


# ---------------------------------------------------------------------------
# Tests - stop()
# ---------------------------------------------------------------------------


class TestFeedbackKafkaPublisherStop:
    async def test_stop_not_running(self):
        """Stop when not running is a no-op."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher()
        assert pub._running is False
        await pub.stop()  # must not raise

    async def test_stop_running_success(self):
        """Happy-path stop flushes and stops the producer."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        mock_producer = AsyncMock()
        mock_producer.flush = AsyncMock()
        mock_producer.stop = AsyncMock()

        pub = FeedbackKafkaPublisher()
        pub._running = True
        pub._producer = mock_producer

        await pub.stop()

        assert pub._running is False
        assert pub._producer is None
        mock_producer.flush.assert_awaited_once()
        mock_producer.stop.assert_awaited_once()

    async def test_stop_producer_raises_on_flush(self):
        """Exception during flush is caught; producer is still cleaned up."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        mock_producer = AsyncMock()
        mock_producer.flush = AsyncMock(side_effect=RuntimeError("flush failed"))
        mock_producer.stop = AsyncMock()

        pub = FeedbackKafkaPublisher()
        pub._running = True
        pub._producer = mock_producer

        await pub.stop()  # must not propagate

        assert pub._running is False
        assert pub._producer is None

    async def test_stop_producer_raises_value_error(self):
        """ValueError during stop is caught."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        mock_producer = AsyncMock()
        mock_producer.flush = AsyncMock()
        mock_producer.stop = AsyncMock(side_effect=ValueError("stop failed"))

        pub = FeedbackKafkaPublisher()
        pub._running = True
        pub._producer = mock_producer

        await pub.stop()

        assert pub._producer is None

    async def test_stop_producer_raises_type_error(self):
        """TypeError during stop is caught."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        mock_producer = AsyncMock()
        mock_producer.flush = AsyncMock(side_effect=TypeError("type err"))
        mock_producer.stop = AsyncMock()

        pub = FeedbackKafkaPublisher()
        pub._running = True
        pub._producer = mock_producer

        await pub.stop()
        assert pub._producer is None

    async def test_stop_running_no_producer(self):
        """Running flag True but producer is None -- still marks not running."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher()
        pub._running = True
        pub._producer = None

        await pub.stop()

        assert pub._running is False


# ---------------------------------------------------------------------------
# Tests - publish()
# ---------------------------------------------------------------------------


class TestFeedbackKafkaPublisherPublish:
    async def test_publish_not_running(self):
        """Returns False when publisher is not running."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher()
        event = _make_event()
        result = await pub.publish(event)
        assert result is False

    async def test_publish_no_producer(self):
        """Returns False when _producer is None even if _running is True."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher()
        pub._running = True
        pub._producer = None
        event = _make_event()
        result = await pub.publish(event)
        assert result is False

    async def test_publish_success(self):
        """Happy-path publish sends event to Kafka."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        mock_producer = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(return_value=None)

        pub = FeedbackKafkaPublisher()
        pub._running = True
        pub._producer = mock_producer

        event = _make_event()
        result = await pub.publish(event)

        assert result is True
        mock_producer.send_and_wait.assert_awaited_once()
        call_kwargs = mock_producer.send_and_wait.call_args
        assert call_kwargs[0][0] == pub.topic  # positional: topic
        assert call_kwargs[1]["key"] == event.decision_id

    async def test_publish_raises_runtime_error(self):
        """RuntimeError during send → returns False."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        mock_producer = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(side_effect=RuntimeError("broker down"))

        pub = FeedbackKafkaPublisher()
        pub._running = True
        pub._producer = mock_producer

        result = await pub.publish(_make_event())
        assert result is False

    async def test_publish_raises_value_error(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        mock_producer = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(side_effect=ValueError("bad value"))

        pub = FeedbackKafkaPublisher()
        pub._running = True
        pub._producer = mock_producer

        result = await pub.publish(_make_event())
        assert result is False

    async def test_publish_raises_type_error(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        mock_producer = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(side_effect=TypeError("type err"))

        pub = FeedbackKafkaPublisher()
        pub._running = True
        pub._producer = mock_producer

        result = await pub.publish(_make_event())
        assert result is False


# ---------------------------------------------------------------------------
# Tests - publish_batch()
# ---------------------------------------------------------------------------


class TestFeedbackKafkaPublisherPublishBatch:
    async def test_publish_batch_empty(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher()
        results = await pub.publish_batch([])
        assert results == {}

    async def test_publish_batch_all_success(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        mock_producer = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(return_value=None)

        pub = FeedbackKafkaPublisher()
        pub._running = True
        pub._producer = mock_producer

        events = [_make_event(id=f"evt-{i}", decision_id=f"dec-{i}") for i in range(3)]
        results = await pub.publish_batch(events)

        assert len(results) == 3
        assert all(results[f"evt-{i}"] is True for i in range(3))

    async def test_publish_batch_mixed_results(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        call_count = [0]

        async def _send_and_wait(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("broker error")

        mock_producer = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(side_effect=_send_and_wait)

        pub = FeedbackKafkaPublisher()
        pub._running = True
        pub._producer = mock_producer

        events = [_make_event(id=f"evt-{i}", decision_id=f"dec-{i}") for i in range(3)]
        results = await pub.publish_batch(events)

        assert results["evt-0"] is True
        assert results["evt-1"] is False
        assert results["evt-2"] is True

    async def test_publish_batch_all_fail_not_running(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher()  # not running
        events = [_make_event(id=f"evt-{i}") for i in range(2)]
        results = await pub.publish_batch(events)
        assert all(v is False for v in results.values())


# ---------------------------------------------------------------------------
# Tests - _serialize_event()
# ---------------------------------------------------------------------------


class TestSerializeEvent:
    def _get_publisher(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        return FeedbackKafkaPublisher()

    def test_serialize_enum_types(self):
        """feedback_type and outcome are Enum instances → .value is used."""
        pub = self._get_publisher()
        event = _make_event(
            feedback_type=FeedbackType.NEGATIVE,
            outcome=OutcomeStatus.FAILURE,
            created_at=datetime(2026, 3, 1, 10, 30, 0),
        )
        result = pub._serialize_event(event)
        assert result["feedback_type"] == "negative"
        assert result["outcome"] == "failure"
        assert result["created_at"] == "2026-03-01T10:30:00"
        assert result["published_to_kafka"] is True
        assert result["schema_version"] == "v1"

    def test_serialize_string_feedback_type_and_outcome(self):
        """Non-Enum feedback_type/outcome pass through as-is."""
        pub = self._get_publisher()
        event = _make_event(feedback_type="positive", outcome="success")  # plain strings
        result = pub._serialize_event(event)
        assert result["feedback_type"] == "positive"
        assert result["outcome"] == "success"

    def test_serialize_string_created_at(self):
        """Non-datetime created_at passes through as-is."""
        pub = self._get_publisher()
        event = _make_event(created_at="2026-01-01T00:00:00")
        result = pub._serialize_event(event)
        assert result["created_at"] == "2026-01-01T00:00:00"

    def test_serialize_all_optional_none(self):
        """None optional fields are preserved."""
        pub = self._get_publisher()
        event = _make_event(
            user_id=None,
            tenant_id=None,
            comment=None,
            correction_data=None,
            features=None,
            actual_impact=None,
            metadata=None,
        )
        result = pub._serialize_event(event)
        assert result["user_id"] is None
        assert result["tenant_id"] is None
        assert result["comment"] is None
        assert result["correction_data"] is None
        assert result["features"] is None
        assert result["actual_impact"] is None
        assert result["metadata"] is None

    def test_serialize_with_rich_metadata(self):
        pub = self._get_publisher()
        event = _make_event(
            correction_data={"key": "val"},
            features={"f1": 0.5, "f2": 1.0},
            metadata={"source": "ui"},
        )
        result = pub._serialize_event(event)
        assert result["correction_data"] == {"key": "val"}
        assert result["features"]["f1"] == 0.5
        assert result["metadata"]["source"] == "ui"

    def test_serialize_id_and_decision_id_present(self):
        pub = self._get_publisher()
        event = _make_event(id="ev-xyz", decision_id="dec-999")
        result = pub._serialize_event(event)
        assert result["id"] == "ev-xyz"
        assert result["decision_id"] == "dec-999"

    def test_serialize_processed_flag(self):
        pub = self._get_publisher()
        event = _make_event(processed=True)
        result = pub._serialize_event(event)
        assert result["processed"] is True

    def test_serialize_neutral_outcome_unknown(self):
        pub = self._get_publisher()
        event = _make_event(feedback_type=FeedbackType.NEUTRAL, outcome=OutcomeStatus.UNKNOWN)
        result = pub._serialize_event(event)
        assert result["feedback_type"] == "neutral"
        assert result["outcome"] == "unknown"

    def test_serialize_correction_partial(self):
        pub = self._get_publisher()
        event = _make_event(feedback_type=FeedbackType.CORRECTION, outcome=OutcomeStatus.PARTIAL)
        result = pub._serialize_event(event)
        assert result["feedback_type"] == "correction"
        assert result["outcome"] == "partial"


# ---------------------------------------------------------------------------
# Tests - _sanitize_error()
# ---------------------------------------------------------------------------


class TestSanitizeError:
    def _get_publisher(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        return FeedbackKafkaPublisher()

    def test_sanitize_bootstrap_servers_in_error(self):
        pub = self._get_publisher()
        err = RuntimeError("bootstrap_servers='secret-host:9092'")
        result = pub._sanitize_error(err)
        assert "secret-host" not in result
        assert "bootstrap_servers='REDACTED'" in result

    def test_sanitize_password_in_error(self):
        pub = self._get_publisher()
        err = ValueError("password='my-secret-password'")
        result = pub._sanitize_error(err)
        assert "my-secret-password" not in result
        assert "password='REDACTED'" in result

    def test_sanitize_plain_error(self):
        pub = self._get_publisher()
        err = RuntimeError("plain connection error")
        result = pub._sanitize_error(err)
        assert result == "plain connection error"

    def test_sanitize_error_both_patterns(self):
        pub = self._get_publisher()
        err = TypeError("bootstrap_servers='host:9092' password='p4ss'")
        result = pub._sanitize_error(err)
        assert "host:9092" not in result
        assert "p4ss" not in result
        assert "REDACTED" in result


# ---------------------------------------------------------------------------
# Tests - _sanitize_bootstrap()
# ---------------------------------------------------------------------------


class TestSanitizeBootstrap:
    def _get_publisher(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        return FeedbackKafkaPublisher()

    def test_single_server_with_port(self):
        pub = self._get_publisher()
        result = pub._sanitize_bootstrap("kafka.example.com:9092")
        assert result == "kafka.example.com:****"

    def test_multiple_servers(self):
        pub = self._get_publisher()
        result = pub._sanitize_bootstrap("broker1:9092,broker2:9093")
        parts = result.split(",")
        assert len(parts) == 2
        assert all(p.endswith(":****") for p in parts)
        assert "broker1" in parts[0]
        assert "broker2" in parts[1]

    def test_server_without_port(self):
        """If no ':' in a part, still appends :****."""
        pub = self._get_publisher()
        result = pub._sanitize_bootstrap("kafka-broker")
        assert result == "kafka-broker:****"

    def test_multiple_servers_no_port(self):
        pub = self._get_publisher()
        result = pub._sanitize_bootstrap("host1,host2")
        assert result == "host1:****,host2:****"


# ---------------------------------------------------------------------------
# Tests - is_running property
# ---------------------------------------------------------------------------


class TestIsRunning:
    def test_is_running_false_by_default(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher()
        assert pub.is_running is False

    def test_is_running_true_after_set(self):
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher()
        pub._running = True
        assert pub.is_running is True


# ---------------------------------------------------------------------------
# Tests - publish_sync()
# ---------------------------------------------------------------------------


class TestPublishSync:
    def test_publish_sync_no_running_loop(self):
        """Without a running event loop, asyncio.run() is used (returns False -- not running)."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher()
        event = _make_event()
        # pub._running is False, so publish() returns False
        result = pub.publish_sync(event)
        assert result is False

    def test_publish_sync_with_running_loop(self):
        """When a running loop exists, create_task is called and False is returned."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher()
        pub._running = True

        mock_producer = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(return_value=None)
        pub._producer = mock_producer

        event = _make_event()

        # Patch get_running_loop to succeed (simulate a running loop) and
        # create_task to record the call without actually scheduling anything.
        mock_task = MagicMock()
        mock_task.add_done_callback = MagicMock()

        with (
            patch("asyncio.get_running_loop"),
            patch("asyncio.create_task", return_value=mock_task) as mock_create_task,
        ):
            result = pub.publish_sync(event)

        assert result is False  # Cannot await result from running loop
        mock_create_task.assert_called_once()

    def test_publish_sync_no_loop_publish_succeeds(self):
        """asyncio.run() path with a producer that actually sends."""
        from enhanced_agent_bus.feedback_handler.kafka_publisher import (
            FeedbackKafkaPublisher,
        )

        pub = FeedbackKafkaPublisher()
        pub._running = True
        mock_producer = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(return_value=None)
        pub._producer = mock_producer

        event = _make_event()

        # Force RuntimeError for get_running_loop to hit the asyncio.run() path
        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            result = pub.publish_sync(event)

        assert result is True


# ---------------------------------------------------------------------------
# Tests - get_feedback_kafka_publisher()
# ---------------------------------------------------------------------------


class TestGetFeedbackKafkaPublisher:
    async def test_creates_and_returns_publisher(self):
        import enhanced_agent_bus.feedback_handler.kafka_publisher as kp

        # Reset global
        kp._feedback_kafka_publisher = None

        with patch.object(kp, "KAFKA_AVAILABLE", False):
            publisher = await kp.get_feedback_kafka_publisher()

        assert publisher is not None
        assert isinstance(publisher, kp.FeedbackKafkaPublisher)
        # Cleanup
        kp._feedback_kafka_publisher = None

    async def test_returns_existing_publisher(self):
        """Second call returns the same instance."""
        import enhanced_agent_bus.feedback_handler.kafka_publisher as kp

        kp._feedback_kafka_publisher = None

        with patch.object(kp, "KAFKA_AVAILABLE", False):
            pub1 = await kp.get_feedback_kafka_publisher()
            pub2 = await kp.get_feedback_kafka_publisher()

        assert pub1 is pub2
        kp._feedback_kafka_publisher = None

    async def test_creates_publisher_with_kafka_available(self):
        """When KAFKA_AVAILABLE=True, producer creation is attempted."""
        import enhanced_agent_bus.feedback_handler.kafka_publisher as kp

        kp._feedback_kafka_publisher = None

        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock()
        producer_cls = MagicMock(return_value=mock_producer)

        with (
            patch.object(kp, "KAFKA_AVAILABLE", True),
            patch.object(kp, "AIOKafkaProducer", producer_cls, create=True),
        ):
            publisher = await kp.get_feedback_kafka_publisher()

        assert publisher._running is True
        kp._feedback_kafka_publisher = None


# ---------------------------------------------------------------------------
# Tests - publish_feedback_event()
# ---------------------------------------------------------------------------


class TestPublishFeedbackEvent:
    async def test_publish_feedback_event_not_running(self):
        import enhanced_agent_bus.feedback_handler.kafka_publisher as kp

        kp._feedback_kafka_publisher = None

        with patch.object(kp, "KAFKA_AVAILABLE", False):
            result = await kp.publish_feedback_event(_make_event())

        assert result is False
        kp._feedback_kafka_publisher = None

    async def test_publish_feedback_event_success(self):
        import enhanced_agent_bus.feedback_handler.kafka_publisher as kp

        kp._feedback_kafka_publisher = None

        mock_producer = AsyncMock()
        mock_producer.start = AsyncMock()
        mock_producer.send_and_wait = AsyncMock(return_value=None)
        producer_cls = MagicMock(return_value=mock_producer)

        with (
            patch.object(kp, "KAFKA_AVAILABLE", True),
            patch.object(kp, "AIOKafkaProducer", producer_cls, create=True),
        ):
            result = await kp.publish_feedback_event(_make_event())

        assert result is True
        kp._feedback_kafka_publisher = None


# ---------------------------------------------------------------------------
# Tests - __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports_present(self):
        import enhanced_agent_bus.feedback_handler.kafka_publisher as kp

        for name in kp.__all__:
            assert hasattr(kp, name), f"Missing export: {name}"
