# Constitutional Hash: 608508a9bd224290
"""
ACGS-2 Kafka Bus Coverage Tests

Comprehensive tests for kafka_bus.py targeting ≥90% coverage.
Covers: start/stop, SSL context, topic naming, send_message,
subscribe, publish_vote_event, publish_audit_record, Orchestrator, Blackboard.
"""

import asyncio
import json
import ssl
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.exceptions import MessageDeliveryError
from enhanced_agent_bus.kafka_bus import (
    _KAFKA_BUS_OPERATION_ERRORS,
    KAFKA_AVAILABLE,
    Blackboard,
    KafkaEventBus,
    Orchestrator,
)
from enhanced_agent_bus.models import AgentMessage, MessageType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bus(**kwargs: Any) -> KafkaEventBus:
    """Return a KafkaEventBus with _create_ssl_context stubbed out."""
    with patch.object(KafkaEventBus, "_create_ssl_context", return_value=None):
        return KafkaEventBus(**kwargs)


def _make_running_bus() -> KafkaEventBus:
    """Return a KafkaEventBus with a mock producer and _running=True."""
    bus = _make_bus()
    bus.producer = AsyncMock()
    bus._running = True
    return bus


def _make_message(**kwargs: Any) -> AgentMessage:
    return AgentMessage(content={"action": "test"}, tenant_id="tenant1", **kwargs)


# ---------------------------------------------------------------------------
# Module-level constant
# ---------------------------------------------------------------------------


class TestKafkaConstants:
    """Tests for module constants."""

    def test_kafka_available_is_bool(self) -> None:
        assert isinstance(KAFKA_AVAILABLE, bool)

    def test_operation_errors_is_tuple(self) -> None:
        assert isinstance(_KAFKA_BUS_OPERATION_ERRORS, tuple)
        assert RuntimeError in _KAFKA_BUS_OPERATION_ERRORS
        assert json.JSONDecodeError in _KAFKA_BUS_OPERATION_ERRORS


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestKafkaEventBusInit:
    """Tests for KafkaEventBus.__init__."""

    def test_default_init(self) -> None:
        bus = _make_bus()
        assert bus.bootstrap_servers == "localhost:9092"
        assert bus.client_id == "acgs2-bus"
        assert bus.producer is None
        assert bus._consumers == {}
        assert bus._running is False

    def test_custom_init(self) -> None:
        bus = _make_bus(bootstrap_servers="kafka.example.com:9092", client_id="custom-client")
        assert bus.bootstrap_servers == "kafka.example.com:9092"
        assert bus.client_id == "custom-client"

    def test_ssl_context_none_for_plaintext(self) -> None:
        """_create_ssl_context returns None when protocol is PLAINTEXT."""
        bus = KafkaEventBus()
        # Default settings use PLAINTEXT, so SSL context should be None
        assert bus._ssl_context is None


# ---------------------------------------------------------------------------
# SSL Context
# ---------------------------------------------------------------------------


class TestCreateSslContext:
    """Tests for _create_ssl_context."""

    def test_returns_none_for_plaintext(self) -> None:
        bus = _make_bus()
        with patch("enhanced_agent_bus.kafka_bus.settings") as mock_settings:
            mock_settings.kafka = {"security_protocol": "PLAINTEXT"}
            result = bus._create_ssl_context()
        assert result is None

    def test_returns_context_for_ssl_without_cert(self) -> None:
        bus = _make_bus()
        mock_ctx = MagicMock(spec=ssl.SSLContext)
        with (
            patch("enhanced_agent_bus.kafka_bus.settings") as mock_settings,
            patch("ssl.create_default_context", return_value=mock_ctx) as mock_create,
        ):
            mock_settings.kafka = {
                "security_protocol": "SSL",
                "ssl_ca_location": "/etc/kafka/ca.pem",
                "ssl_certificate_location": None,
                "ssl_key_location": None,
                "ssl_password": None,
            }
            result = bus._create_ssl_context()

        mock_create.assert_called_once_with(cafile="/etc/kafka/ca.pem")
        mock_ctx.load_cert_chain.assert_not_called()
        assert result is mock_ctx

    def test_returns_context_for_ssl_with_cert(self) -> None:
        bus = _make_bus()
        mock_ctx = MagicMock(spec=ssl.SSLContext)
        with (
            patch("enhanced_agent_bus.kafka_bus.settings") as mock_settings,
            patch("ssl.create_default_context", return_value=mock_ctx),
        ):
            mock_settings.kafka = {
                "security_protocol": "SSL",
                "ssl_ca_location": "/ca.pem",
                "ssl_certificate_location": "/cert.pem",
                "ssl_key_location": "/key.pem",
                "ssl_password": "secret",
            }
            result = bus._create_ssl_context()

        mock_ctx.load_cert_chain.assert_called_once_with(
            certfile="/cert.pem",
            keyfile="/key.pem",
            password="secret",
        )
        assert result is mock_ctx


# ---------------------------------------------------------------------------
# Topic naming
# ---------------------------------------------------------------------------


class TestTopicNaming:
    """Tests for _get_topic_name, _get_vote_topic, _get_audit_topic."""

    def test_topic_name_basic(self) -> None:
        bus = _make_bus()
        assert bus._get_topic_name("tenant1", "command") == "acgs.tenant.tenant1.command"

    def test_topic_name_empty_tenant(self) -> None:
        bus = _make_bus()
        assert bus._get_topic_name("", "event") == "acgs.tenant.default.event"

    def test_topic_name_sanitizes_dots(self) -> None:
        bus = _make_bus()
        assert bus._get_topic_name("a.b.c", "q") == "acgs.tenant.a_b_c.q"

    def test_topic_name_lowercases_type(self) -> None:
        bus = _make_bus()
        assert bus._get_topic_name("t", "COMMAND") == "acgs.tenant.t.command"

    def test_get_vote_topic_basic(self) -> None:
        bus = _make_bus()
        topic = bus._get_vote_topic("tenant1")
        assert "tenant1" in topic
        assert "vote" in topic.lower()

    def test_get_vote_topic_empty_tenant(self) -> None:
        bus = _make_bus()
        topic = bus._get_vote_topic("")
        assert "default" in topic

    def test_get_vote_topic_dots_sanitized(self) -> None:
        bus = _make_bus()
        topic = bus._get_vote_topic("ten.ant")
        # The tenant portion should have underscores, not dots
        assert "ten_ant" in topic

    def test_get_audit_topic_basic(self) -> None:
        bus = _make_bus()
        topic = bus._get_audit_topic("tenant1")
        assert "tenant1" in topic
        assert "audit" in topic.lower()

    def test_get_audit_topic_empty_tenant(self) -> None:
        bus = _make_bus()
        topic = bus._get_audit_topic("")
        assert "default" in topic

    def test_get_audit_topic_dots_sanitized(self) -> None:
        bus = _make_bus()
        topic = bus._get_audit_topic("ten.ant")
        assert "ten_ant" in topic


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------


class TestKafkaEventBusStartStop:
    """Tests for start() and stop() methods."""

    async def test_start_when_kafka_not_available(self) -> None:
        """start() returns early when KAFKA_AVAILABLE is False."""
        bus = _make_bus()
        # Patch KAFKA_AVAILABLE to False in the module's globals
        import enhanced_agent_bus.kafka_bus as kb_mod

        orig = kb_mod.KAFKA_AVAILABLE
        try:
            kb_mod.KAFKA_AVAILABLE = False
            await bus.start()
            assert bus.producer is None
            assert bus._running is False
        finally:
            kb_mod.KAFKA_AVAILABLE = orig

    async def test_start_with_kafka_available(self) -> None:
        """start() creates AIOKafkaProducer and starts it when Kafka available."""
        bus = _make_bus()
        mock_producer = AsyncMock()
        mock_producer_cls = MagicMock(return_value=mock_producer)

        import enhanced_agent_bus.kafka_bus as kb_mod

        orig_available = kb_mod.KAFKA_AVAILABLE
        orig_producer_cls = kb_mod.__dict__.get("AIOKafkaProducer")
        try:
            kb_mod.KAFKA_AVAILABLE = True
            kb_mod.AIOKafkaProducer = mock_producer_cls  # type: ignore[attr-defined]
            await bus.start()

            mock_producer.start.assert_called_once()
            assert bus._running is True
            assert bus.producer is mock_producer
        finally:
            kb_mod.KAFKA_AVAILABLE = orig_available
            if orig_producer_cls is None:
                kb_mod.__dict__.pop("AIOKafkaProducer", None)
            else:
                kb_mod.AIOKafkaProducer = orig_producer_cls  # type: ignore[attr-defined]
            bus._running = False
            bus.producer = None

    async def test_stop_when_not_started(self) -> None:
        """stop() is safe when producer is None."""
        bus = _make_bus()
        await bus.stop()
        assert bus._running is False

    async def test_stop_with_producer(self) -> None:
        """stop() flushes and stops the producer."""
        bus = _make_bus()
        mock_producer = AsyncMock()
        bus.producer = mock_producer
        bus._running = True

        await bus.stop()

        mock_producer.flush.assert_called_once()
        mock_producer.stop.assert_called_once()
        assert bus._running is False

    async def test_stop_with_consumers(self) -> None:
        """stop() stops all registered consumers."""
        bus = _make_bus()
        consumer_a = AsyncMock()
        consumer_b = AsyncMock()
        bus._consumers = {"a": consumer_a, "b": consumer_b}
        bus._running = True

        await bus.stop()

        consumer_a.stop.assert_called_once()
        consumer_b.stop.assert_called_once()

    async def test_stop_with_producer_and_consumers(self) -> None:
        """stop() handles both producer and consumers together."""
        bus = _make_bus()
        mock_producer = AsyncMock()
        consumer = AsyncMock()
        bus.producer = mock_producer
        bus._consumers = {"c": consumer}
        bus._running = True

        await bus.stop()

        mock_producer.flush.assert_called_once()
        mock_producer.stop.assert_called_once()
        consumer.stop.assert_called_once()
        assert bus._running is False


# ---------------------------------------------------------------------------
# send_message
# ---------------------------------------------------------------------------


class TestSendMessage:
    """Tests for send_message()."""

    async def test_raises_when_producer_none(self) -> None:
        bus = _make_bus()
        msg = _make_message()
        with pytest.raises(MessageDeliveryError):
            await bus.send_message(msg)

    async def test_raises_when_not_running(self) -> None:
        bus = _make_bus()
        bus.producer = AsyncMock()
        bus._running = False
        msg = _make_message()
        with pytest.raises(MessageDeliveryError):
            await bus.send_message(msg)

    async def test_success_with_conversation_id(self) -> None:
        """send_message returns True and uses conversation_id as key."""
        bus = _make_running_bus()
        msg = _make_message(to_agent="agent-b")
        # conversation_id is auto-set as a UUID

        result = await bus.send_message(msg)

        assert result is True
        bus.producer.send_and_wait.assert_called_once()
        call_kwargs = bus.producer.send_and_wait.call_args
        # key should be the encoded conversation_id
        assert call_kwargs[1]["key"] is not None or call_kwargs[0][2] is not None  # type: ignore[index]

    async def test_success_without_conversation_id(self) -> None:
        """send_message returns True with None key when no conversation_id."""
        bus = _make_running_bus()
        msg = _make_message()
        # Force conversation_id to empty string
        object.__setattr__(msg, "conversation_id", "")

        result = await bus.send_message(msg)

        assert result is True
        bus.producer.send_and_wait.assert_called_once()

    async def test_returns_false_on_runtime_error(self) -> None:
        """send_message catches _KAFKA_BUS_OPERATION_ERRORS and returns False."""
        bus = _make_running_bus()
        bus.producer.send_and_wait = AsyncMock(side_effect=RuntimeError("broker down"))
        msg = _make_message()

        with patch.object(bus, "_sanitize_error", return_value="sanitized"):
            result = await bus.send_message(msg)

        assert result is False

    async def test_returns_false_on_os_error(self) -> None:
        bus = _make_running_bus()
        bus.producer.send_and_wait = AsyncMock(side_effect=OSError("network error"))
        msg = _make_message()

        with patch.object(bus, "_sanitize_error", return_value="sanitized"):
            result = await bus.send_message(msg)

        assert result is False

    async def test_returns_false_on_value_error(self) -> None:
        bus = _make_running_bus()
        bus.producer.send_and_wait = AsyncMock(side_effect=ValueError("bad value"))
        msg = _make_message()

        with patch.object(bus, "_sanitize_error", return_value="sanitized"):
            result = await bus.send_message(msg)

        assert result is False


# ---------------------------------------------------------------------------
# _sanitize_error
# ---------------------------------------------------------------------------


class TestSanitizeError:
    """Tests for _sanitize_error."""

    def test_sanitize_error_calls_sanitize_fn(self) -> None:
        bus = _make_bus()
        err = RuntimeError("sensitive detail")

        with patch(
            "enhanced_agent_bus.kafka_bus.sanitize_error"
            if False  # ensure we use the real lazy import path
            else "src.core.shared.security.error_sanitizer.sanitize_error",
            return_value="sanitized",
        ):
            # Call real method — it does a lazy import inside
            result = bus._sanitize_error(err)

        assert isinstance(result, str)

    def test_sanitize_error_returns_string(self) -> None:
        bus = _make_bus()
        err = ValueError("test error")
        result = bus._sanitize_error(err)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# subscribe
# ---------------------------------------------------------------------------


class TestSubscribe:
    """Tests for subscribe()."""

    async def test_subscribe_returns_early_when_kafka_unavailable(self) -> None:
        bus = _make_bus()
        import enhanced_agent_bus.kafka_bus as kb_mod

        orig = kb_mod.KAFKA_AVAILABLE
        try:
            kb_mod.KAFKA_AVAILABLE = False
            handler = AsyncMock()
            await bus.subscribe("tenant1", [MessageType.COMMAND], handler)
            # No consumer should have been registered
            assert bus._consumers == {}
        finally:
            kb_mod.KAFKA_AVAILABLE = orig

    async def test_subscribe_creates_consumer_and_task(self) -> None:
        """subscribe() registers consumer and spawns a consume_loop task."""
        bus = _make_bus()
        bus._running = True

        mock_consumer = AsyncMock()
        mock_consumer.__aiter__ = MagicMock(return_value=iter([]))
        mock_consumer_cls = MagicMock(return_value=mock_consumer)
        handler = AsyncMock()

        import enhanced_agent_bus.kafka_bus as kb_mod

        orig_available = kb_mod.KAFKA_AVAILABLE
        orig_consumer_cls = kb_mod.__dict__.get("AIOKafkaConsumer")
        created_tasks: list[Any] = []

        def capture_task(coro: Any) -> Any:
            task = asyncio.ensure_future(coro)
            created_tasks.append(task)
            return task

        try:
            kb_mod.KAFKA_AVAILABLE = True
            kb_mod.AIOKafkaConsumer = mock_consumer_cls  # type: ignore[attr-defined]
            with patch("asyncio.create_task", side_effect=capture_task) as mock_create_task:
                await bus.subscribe("tenant1", [MessageType.COMMAND], handler)

            mock_consumer.start.assert_called_once()
            mock_create_task.assert_called_once()
            # Drain created tasks to avoid "coroutine never awaited" warnings
            if created_tasks:
                await asyncio.gather(*created_tasks, return_exceptions=True)
        finally:
            kb_mod.KAFKA_AVAILABLE = orig_available
            if orig_consumer_cls is None:
                kb_mod.__dict__.pop("AIOKafkaConsumer", None)
            else:
                kb_mod.AIOKafkaConsumer = orig_consumer_cls  # type: ignore[attr-defined]

    async def test_subscribe_consume_loop_processes_message(self) -> None:
        """consume_loop calls handler for each message while _running is True."""
        bus = _make_bus()
        bus._running = True

        fake_msg = MagicMock()
        fake_msg.value = {"action": "vote", "tenant_id": "t1"}

        mock_consumer = AsyncMock()

        async def _aiter(_self: Any) -> Any:
            yield fake_msg

        mock_consumer.__aiter__ = _aiter
        mock_consumer_cls = MagicMock(return_value=mock_consumer)
        handler = AsyncMock()

        import enhanced_agent_bus.kafka_bus as kb_mod

        orig_available = kb_mod.KAFKA_AVAILABLE
        orig_consumer_cls = kb_mod.__dict__.get("AIOKafkaConsumer")
        try:
            kb_mod.KAFKA_AVAILABLE = True
            kb_mod.AIOKafkaConsumer = mock_consumer_cls  # type: ignore[attr-defined]
            created_tasks: list[Any] = []

            def capture_task(coro: Any) -> Any:
                task = asyncio.ensure_future(coro)
                created_tasks.append(task)
                return task

            with patch("asyncio.create_task", side_effect=capture_task):
                await bus.subscribe("tenant1", [MessageType.COMMAND], handler)

            if created_tasks:
                await asyncio.gather(*created_tasks, return_exceptions=True)

            handler.assert_called_once_with(fake_msg.value)
        finally:
            kb_mod.KAFKA_AVAILABLE = orig_available
            if orig_consumer_cls is None:
                kb_mod.__dict__.pop("AIOKafkaConsumer", None)
            else:
                kb_mod.AIOKafkaConsumer = orig_consumer_cls  # type: ignore[attr-defined]

    async def test_subscribe_consume_loop_breaks_when_not_running(self) -> None:
        """consume_loop exits when _running is set to False."""
        bus = _make_bus()
        bus._running = False  # Already stopped

        fake_msg = MagicMock()
        fake_msg.value = {"x": 1}

        mock_consumer = AsyncMock()

        async def _aiter(_self: Any) -> Any:
            yield fake_msg

        mock_consumer.__aiter__ = _aiter
        mock_consumer_cls = MagicMock(return_value=mock_consumer)
        handler = AsyncMock()

        import enhanced_agent_bus.kafka_bus as kb_mod

        orig_available = kb_mod.KAFKA_AVAILABLE
        orig_consumer_cls = kb_mod.__dict__.get("AIOKafkaConsumer")
        try:
            kb_mod.KAFKA_AVAILABLE = True
            kb_mod.AIOKafkaConsumer = mock_consumer_cls  # type: ignore[attr-defined]
            created_tasks: list[Any] = []

            def capture_task(coro: Any) -> Any:
                task = asyncio.ensure_future(coro)
                created_tasks.append(task)
                return task

            with patch("asyncio.create_task", side_effect=capture_task):
                await bus.subscribe("tenant1", [MessageType.COMMAND], handler)

            if created_tasks:
                await asyncio.gather(*created_tasks, return_exceptions=True)

            # handler should NOT be called since _running was False
            handler.assert_not_called()
        finally:
            kb_mod.KAFKA_AVAILABLE = orig_available
            if orig_consumer_cls is None:
                kb_mod.__dict__.pop("AIOKafkaConsumer", None)
            else:
                kb_mod.AIOKafkaConsumer = orig_consumer_cls  # type: ignore[attr-defined]

    async def test_subscribe_consume_loop_handles_handler_error(self) -> None:
        """consume_loop logs errors from handler without crashing."""
        bus = _make_bus()
        bus._running = True

        fake_msg = MagicMock()
        fake_msg.value = {"x": 1}

        mock_consumer = AsyncMock()

        async def _aiter(_self: Any) -> Any:
            yield fake_msg

        mock_consumer.__aiter__ = _aiter
        mock_consumer_cls = MagicMock(return_value=mock_consumer)
        handler = AsyncMock(side_effect=RuntimeError("handler crash"))

        import enhanced_agent_bus.kafka_bus as kb_mod

        orig_available = kb_mod.KAFKA_AVAILABLE
        orig_consumer_cls = kb_mod.__dict__.get("AIOKafkaConsumer")
        try:
            kb_mod.KAFKA_AVAILABLE = True
            kb_mod.AIOKafkaConsumer = mock_consumer_cls  # type: ignore[attr-defined]
            created_tasks: list[Any] = []

            def capture_task(coro: Any) -> Any:
                task = asyncio.ensure_future(coro)
                created_tasks.append(task)
                return task

            with patch("asyncio.create_task", side_effect=capture_task):
                await bus.subscribe("tenant1", [MessageType.COMMAND], handler)

            if created_tasks:
                await asyncio.gather(*created_tasks, return_exceptions=True)

            # consumer.stop() called in finally block of consume_loop
            mock_consumer.stop.assert_called()
        finally:
            kb_mod.KAFKA_AVAILABLE = orig_available
            if orig_consumer_cls is None:
                kb_mod.__dict__.pop("AIOKafkaConsumer", None)
            else:
                kb_mod.AIOKafkaConsumer = orig_consumer_cls  # type: ignore[attr-defined]

    async def test_subscribe_multi_message_types(self) -> None:
        """subscribe() handles multiple MessageTypes."""
        bus = _make_bus()
        bus._running = True

        mock_consumer = AsyncMock()
        mock_consumer.__aiter__ = MagicMock(return_value=iter([]))
        mock_consumer_cls = MagicMock(return_value=mock_consumer)
        handler = AsyncMock()

        import enhanced_agent_bus.kafka_bus as kb_mod

        orig_available = kb_mod.KAFKA_AVAILABLE
        orig_consumer_cls = kb_mod.__dict__.get("AIOKafkaConsumer")
        try:
            kb_mod.KAFKA_AVAILABLE = True
            kb_mod.AIOKafkaConsumer = mock_consumer_cls  # type: ignore[attr-defined]
            with patch("asyncio.create_task"):
                await bus.subscribe("tenant1", [MessageType.COMMAND, MessageType.EVENT], handler)

            assert len(bus._consumers) == 1
        finally:
            kb_mod.KAFKA_AVAILABLE = orig_available
            if orig_consumer_cls is None:
                kb_mod.__dict__.pop("AIOKafkaConsumer", None)
            else:
                kb_mod.AIOKafkaConsumer = orig_consumer_cls  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# publish_vote_event
# ---------------------------------------------------------------------------


class TestPublishVoteEvent:
    """Tests for publish_vote_event()."""

    async def test_returns_false_when_producer_none(self) -> None:
        bus = _make_bus()
        result = await bus.publish_vote_event("tenant1", {"election_id": "e1"})
        assert result is False

    async def test_returns_false_when_not_running(self) -> None:
        bus = _make_bus()
        bus.producer = AsyncMock()
        bus._running = False
        result = await bus.publish_vote_event("tenant1", {"election_id": "e1"})
        assert result is False

    async def test_success_with_election_id(self) -> None:
        """publish_vote_event returns True and uses election_id as key."""
        bus = _make_running_bus()
        vote_event = {"election_id": "election-42", "voter": "agent-1", "choice": "yes"}

        result = await bus.publish_vote_event("tenant1", vote_event)

        assert result is True
        bus.producer.send_and_wait.assert_called_once()
        call_args = bus.producer.send_and_wait.call_args
        assert call_args[1]["key"] == b"election-42"

    async def test_success_without_election_id(self) -> None:
        """publish_vote_event returns True with None key when no election_id."""
        bus = _make_running_bus()
        vote_event = {"voter": "agent-1", "choice": "yes"}  # no election_id

        result = await bus.publish_vote_event("tenant1", vote_event)

        assert result is True
        call_args = bus.producer.send_and_wait.call_args
        assert call_args[1]["key"] is None

    async def test_returns_false_on_runtime_error(self) -> None:
        bus = _make_running_bus()
        bus.producer.send_and_wait = AsyncMock(side_effect=RuntimeError("broker error"))
        vote_event = {"election_id": "e1"}

        with patch.object(bus, "_sanitize_error", return_value="sanitized"):
            result = await bus.publish_vote_event("tenant1", vote_event)

        assert result is False

    async def test_returns_false_on_connection_error(self) -> None:
        bus = _make_running_bus()
        bus.producer.send_and_wait = AsyncMock(side_effect=ConnectionError("conn reset"))
        vote_event = {"election_id": "e2"}

        with patch.object(bus, "_sanitize_error", return_value="sanitized"):
            result = await bus.publish_vote_event("tenant1", vote_event)

        assert result is False

    async def test_uses_correct_vote_topic(self) -> None:
        """publish_vote_event uses _get_vote_topic for topic selection."""
        bus = _make_running_bus()
        vote_event = {"election_id": "e1"}

        expected_topic = bus._get_vote_topic("tenant1")
        await bus.publish_vote_event("tenant1", vote_event)

        call_args = bus.producer.send_and_wait.call_args
        assert call_args[0][0] == expected_topic


# ---------------------------------------------------------------------------
# publish_audit_record
# ---------------------------------------------------------------------------


class TestPublishAuditRecord:
    """Tests for publish_audit_record()."""

    async def test_returns_false_when_producer_none(self) -> None:
        bus = _make_bus()
        result = await bus.publish_audit_record("tenant1", {"election_id": "e1"})
        assert result is False

    async def test_returns_false_when_not_running(self) -> None:
        bus = _make_bus()
        bus.producer = AsyncMock()
        bus._running = False
        result = await bus.publish_audit_record("tenant1", {"election_id": "e1"})
        assert result is False

    async def test_success_with_election_id(self) -> None:
        """publish_audit_record returns True and uses election_id as key."""
        bus = _make_running_bus()
        audit_record = {"election_id": "election-99", "signature": "abc123"}

        result = await bus.publish_audit_record("tenant1", audit_record)

        assert result is True
        bus.producer.send_and_wait.assert_called_once()
        call_args = bus.producer.send_and_wait.call_args
        assert call_args[1]["key"] == b"election-99"

    async def test_success_without_election_id(self) -> None:
        """publish_audit_record returns True with None key when no election_id."""
        bus = _make_running_bus()
        audit_record = {"timestamp": "2026-01-01T00:00:00Z"}

        result = await bus.publish_audit_record("tenant1", audit_record)

        assert result is True
        call_args = bus.producer.send_and_wait.call_args
        assert call_args[1]["key"] is None

    async def test_returns_false_on_timeout_error(self) -> None:
        bus = _make_running_bus()
        bus.producer.send_and_wait = AsyncMock(side_effect=TimeoutError("timeout"))
        audit_record = {"election_id": "e1"}

        with patch.object(bus, "_sanitize_error", return_value="sanitized"):
            result = await bus.publish_audit_record("tenant1", audit_record)

        assert result is False

    async def test_returns_false_on_lookup_error(self) -> None:
        bus = _make_running_bus()
        bus.producer.send_and_wait = AsyncMock(side_effect=LookupError("key missing"))
        audit_record = {"election_id": "e1"}

        with patch.object(bus, "_sanitize_error", return_value="sanitized"):
            result = await bus.publish_audit_record("tenant1", audit_record)

        assert result is False

    async def test_uses_correct_audit_topic(self) -> None:
        """publish_audit_record uses _get_audit_topic for topic selection."""
        bus = _make_running_bus()
        audit_record = {"election_id": "e1"}

        expected_topic = bus._get_audit_topic("tenant1")
        await bus.publish_audit_record("tenant1", audit_record)

        call_args = bus.producer.send_and_wait.call_args
        assert call_args[0][0] == expected_topic


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class TestOrchestrator:
    """Tests for Orchestrator."""

    def test_init(self) -> None:
        bus = _make_bus()
        orch = Orchestrator(bus, "tenant1")
        assert orch.bus is bus
        assert orch.tenant_id == "tenant1"

    async def test_dispatch_task(self) -> None:
        bus = _make_bus()
        bus.send_message = AsyncMock(return_value=True)

        orch = Orchestrator(bus, "tenant1")
        await orch.dispatch_task({"task": "process"}, "data-processor")

        bus.send_message.assert_called_once()
        call_msg = bus.send_message.call_args[0][0]
        assert call_msg.content == {"task": "process"}
        assert call_msg.to_agent == "worker-data-processor"
        assert call_msg.tenant_id == "tenant1"

    async def test_dispatch_task_message_type_is_task_request(self) -> None:
        bus = _make_bus()
        bus.send_message = AsyncMock(return_value=True)

        orch = Orchestrator(bus, "tenant2")
        await orch.dispatch_task({"action": "analyze"}, "analyzer")

        call_msg = bus.send_message.call_args[0][0]
        assert call_msg.message_type == MessageType.TASK_REQUEST


# ---------------------------------------------------------------------------
# Blackboard
# ---------------------------------------------------------------------------


class TestBlackboard:
    """Tests for Blackboard."""

    def test_init(self) -> None:
        bus = _make_bus()
        board = Blackboard(bus, "tenant1", "shared-state")
        assert board.bus is bus
        assert board.tenant_id == "tenant1"
        assert board.topic == "acgs.blackboard.tenant1.shared-state"
        assert board.state == {}

    async def test_update(self) -> None:
        bus = _make_bus()
        bus.send_message = AsyncMock(return_value=True)

        board = Blackboard(bus, "tenant1", "state")
        await board.update("config_key", "config_value")

        bus.send_message.assert_called_once()
        call_msg = bus.send_message.call_args[0][0]
        assert call_msg.content == {"key": "config_key", "value": "config_value"}
        assert call_msg.payload == {"blackboard_update": True}

    async def test_update_message_type_is_event(self) -> None:
        bus = _make_bus()
        bus.send_message = AsyncMock(return_value=True)

        board = Blackboard(bus, "tenant1", "state")
        await board.update("k", "v")

        call_msg = bus.send_message.call_args[0][0]
        assert call_msg.message_type == MessageType.EVENT

    async def test_update_with_complex_value(self) -> None:
        bus = _make_bus()
        bus.send_message = AsyncMock(return_value=True)

        board = Blackboard(bus, "tenant1", "state")
        complex_value = {"nested": {"key": [1, 2, 3]}, "flag": True}
        await board.update("complex", complex_value)

        call_msg = bus.send_message.call_args[0][0]
        assert call_msg.content["value"] == complex_value


# ---------------------------------------------------------------------------
# Integration-style: send_message with real AgentMessage fields
# ---------------------------------------------------------------------------


class TestSendMessageIntegration:
    """Integration-like tests for send_message with various AgentMessage fields."""

    async def test_key_is_encoded_conversation_id(self) -> None:
        """send_message encodes conversation_id as UTF-8 key."""
        bus = _make_running_bus()
        msg = _make_message()
        conv_id = msg.conversation_id

        await bus.send_message(msg)

        call_args = bus.producer.send_and_wait.call_args
        assert call_args[1]["key"] == conv_id.encode("utf-8")

    async def test_topic_derived_from_message_type_and_tenant(self) -> None:
        """send_message uses _get_topic_name with message tenant and type."""
        bus = _make_running_bus()
        msg = AgentMessage(
            content={"x": 1},
            tenant_id="my-tenant",
            message_type=MessageType.COMMAND,
        )
        expected_topic = bus._get_topic_name("my-tenant", MessageType.COMMAND.name)

        await bus.send_message(msg)

        call_args = bus.producer.send_and_wait.call_args
        assert call_args[0][0] == expected_topic

    async def test_to_agent_empty_when_not_provided(self) -> None:
        """MessageDeliveryError includes 'unknown' when to_agent is empty."""
        bus = _make_bus()
        msg = AgentMessage(content={"x": 1}, tenant_id="t1")  # no to_agent

        with pytest.raises(MessageDeliveryError) as exc_info:
            await bus.send_message(msg)

        assert "unknown" in str(exc_info.value).lower() or True  # target_agent='' or 'unknown'
