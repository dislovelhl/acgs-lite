# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/retry_buffer.py
Target: ≥95% line coverage (76 stmts).
"""

import asyncio
import os
import sys
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

# Block Rust extension before any imports
_test_with_rust = os.environ.get("TEST_WITH_RUST", "0") == "1"
if not _test_with_rust:
    sys.modules["enhanced_agent_bus_rust"] = None  # type: ignore[assignment]

from enhanced_agent_bus.retry_buffer import (
    RETRY_DELIVERY_ERRORS,
    BufferedMessage,
    RetryBuffer,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_message(
    msg_id: str = "msg-1",
    topic: str = "test-topic",
    value: dict | None = None,
    key: bytes | None = b"key",
    buffered_at: float = 0.0,
    retry_count: int = 0,
    max_retries: int = 5,
    tenant_id: str | None = None,
) -> BufferedMessage:
    return BufferedMessage(
        id=msg_id,
        topic=topic,
        value=value or {"data": "payload"},
        key=key,
        buffered_at=buffered_at,
        retry_count=retry_count,
        max_retries=max_retries,
        tenant_id=tenant_id,
    )


# ---------------------------------------------------------------------------
# RETRY_DELIVERY_ERRORS tuple
# ---------------------------------------------------------------------------


class TestRetryDeliveryErrors:
    def test_contains_runtime_error(self):
        assert RuntimeError in RETRY_DELIVERY_ERRORS

    def test_contains_value_error(self):
        assert ValueError in RETRY_DELIVERY_ERRORS

    def test_contains_type_error(self):
        assert TypeError in RETRY_DELIVERY_ERRORS

    def test_contains_key_error(self):
        assert KeyError in RETRY_DELIVERY_ERRORS

    def test_contains_attribute_error(self):
        assert AttributeError in RETRY_DELIVERY_ERRORS

    def test_contains_connection_error(self):
        assert ConnectionError in RETRY_DELIVERY_ERRORS

    def test_contains_os_error(self):
        assert OSError in RETRY_DELIVERY_ERRORS

    def test_contains_asyncio_timeout_error(self):
        assert asyncio.TimeoutError in RETRY_DELIVERY_ERRORS

    def test_is_tuple(self):
        assert isinstance(RETRY_DELIVERY_ERRORS, tuple)

    def test_length(self):
        assert len(RETRY_DELIVERY_ERRORS) == 8


# ---------------------------------------------------------------------------
# BufferedMessage dataclass
# ---------------------------------------------------------------------------


class TestBufferedMessage:
    def test_basic_creation(self):
        msg = make_message()
        assert msg.id == "msg-1"
        assert msg.topic == "test-topic"
        assert msg.value == {"data": "payload"}
        assert msg.key == b"key"
        assert msg.buffered_at == 0.0
        assert msg.retry_count == 0
        assert msg.max_retries == 5
        assert msg.tenant_id is None

    def test_defaults(self):
        msg = BufferedMessage(id="x", topic="t", value={}, key=None, buffered_at=1.0)
        assert msg.retry_count == 0
        assert msg.max_retries == 5
        assert msg.tenant_id is None

    def test_custom_values(self):
        msg = make_message(
            retry_count=3,
            max_retries=10,
            tenant_id="tenant-abc",
            key=None,
        )
        assert msg.retry_count == 3
        assert msg.max_retries == 10
        assert msg.tenant_id == "tenant-abc"
        assert msg.key is None

    def test_mutable_retry_count(self):
        msg = make_message()
        msg.retry_count += 1
        assert msg.retry_count == 1

    def test_value_is_dict(self):
        msg = make_message(value={"nested": {"a": 1}})
        assert msg.value["nested"]["a"] == 1


# ---------------------------------------------------------------------------
# RetryBuffer.__init__
# ---------------------------------------------------------------------------


class TestRetryBufferInit:
    def test_default_params(self):
        buf = RetryBuffer()
        assert buf.max_size == 10000
        assert buf.base_retry_delay == 1.0
        assert buf.max_retry_delay == 60.0

    def test_custom_params(self):
        buf = RetryBuffer(max_size=50, base_retry_delay=0.5, max_retry_delay=10.0)
        assert buf.max_size == 50
        assert buf.base_retry_delay == 0.5
        assert buf.max_retry_delay == 10.0

    def test_initial_buffer_empty(self):
        buf = RetryBuffer()
        assert buf.get_size() == 0

    def test_initial_metrics(self):
        buf = RetryBuffer()
        m = buf.get_metrics()
        assert m["buffered_count"] == 0
        assert m["delivered_count"] == 0
        assert m["failed_count"] == 0
        assert m["dropped_count"] == 0

    def test_not_processing(self):
        buf = RetryBuffer()
        assert buf._processing is False

    def test_buffer_is_deque_with_maxlen(self):
        buf = RetryBuffer(max_size=42)
        assert isinstance(buf._buffer, deque)
        assert buf._buffer.maxlen == 42


# ---------------------------------------------------------------------------
# RetryBuffer.get_size
# ---------------------------------------------------------------------------


class TestGetSize:
    async def test_empty(self):
        buf = RetryBuffer()
        assert buf.get_size() == 0

    async def test_after_add(self):
        buf = RetryBuffer()
        await buf.add(make_message("m1"))
        assert buf.get_size() == 1

    async def test_after_multiple_adds(self):
        buf = RetryBuffer()
        for i in range(5):
            await buf.add(make_message(f"m{i}"))
        assert buf.get_size() == 5


# ---------------------------------------------------------------------------
# RetryBuffer.get_metrics
# ---------------------------------------------------------------------------


class TestGetMetrics:
    async def test_returns_constitutional_hash(self):
        buf = RetryBuffer()
        m = buf.get_metrics()
        assert m["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_current_size_reflected(self):
        buf = RetryBuffer()
        await buf.add(make_message("m1"))
        m = buf.get_metrics()
        assert m["current_size"] == 1

    async def test_max_size_in_metrics(self):
        buf = RetryBuffer(max_size=99)
        m = buf.get_metrics()
        assert m["max_size"] == 99

    async def test_buffered_count_increments(self):
        buf = RetryBuffer()
        await buf.add(make_message("m1"))
        await buf.add(make_message("m2"))
        m = buf.get_metrics()
        assert m["buffered_count"] == 2

    async def test_dropped_count_increments_on_full_buffer(self):
        buf = RetryBuffer(max_size=2)
        for i in range(3):
            await buf.add(make_message(f"m{i}"))
        m = buf.get_metrics()
        assert m["dropped_count"] == 1


# ---------------------------------------------------------------------------
# RetryBuffer.add — normal and full-buffer paths
# ---------------------------------------------------------------------------


class TestAdd:
    async def test_returns_true(self):
        buf = RetryBuffer()
        result = await buf.add(make_message())
        assert result is True

    async def test_size_increases(self):
        buf = RetryBuffer()
        await buf.add(make_message("m1"))
        assert buf.get_size() == 1

    async def test_buffer_full_drops_oldest(self):
        buf = RetryBuffer(max_size=2)
        await buf.add(make_message("first"))
        await buf.add(make_message("second"))
        # Adding a third should drop "first"
        await buf.add(make_message("third"))
        ids = [m.id for m in buf._buffer]
        assert "first" not in ids
        assert "third" in ids

    async def test_buffer_full_increments_dropped_count(self):
        buf = RetryBuffer(max_size=1)
        await buf.add(make_message("m1"))
        await buf.add(make_message("m2"))
        assert buf.get_metrics()["dropped_count"] == 1

    async def test_buffer_not_actually_over_max_size(self):
        # The deque has maxlen set, so it handles overflow automatically;
        # the manual popleft in add happens when len >= max_size.
        # With maxlen=2 the deque itself enforces the bound.
        buf = RetryBuffer(max_size=3)
        for i in range(5):
            await buf.add(make_message(f"m{i}"))
        # buffer should have 3 items (maxlen=3), dropped_count = 2
        assert buf.get_size() <= 3

    async def test_null_key_accepted(self):
        buf = RetryBuffer()
        msg = make_message(key=None)
        result = await buf.add(msg)
        assert result is True

    async def test_message_logged_on_add(self):
        buf = RetryBuffer()
        with patch("enhanced_agent_bus.retry_buffer.logger") as mock_log:
            await buf.add(make_message("m1"))
            assert mock_log.info.called

    async def test_dropped_message_logged_warning(self):
        buf = RetryBuffer(max_size=1)
        await buf.add(make_message("old"))
        with patch("enhanced_agent_bus.retry_buffer.logger") as mock_log:
            await buf.add(make_message("new"))
            assert mock_log.warning.called


# ---------------------------------------------------------------------------
# RetryBuffer.process — already_processing guard
# ---------------------------------------------------------------------------


class TestProcessAlreadyProcessing:
    async def test_returns_already_processing_status(self):
        buf = RetryBuffer()
        # Manually set _processing to True
        buf._processing = True
        result = await buf.process(AsyncMock())
        assert result == {"status": "already_processing"}

    async def test_does_not_drain_buffer(self):
        buf = RetryBuffer()
        await buf.add(make_message("m1"))
        buf._processing = True
        await buf.process(AsyncMock())
        assert buf.get_size() == 1


# ---------------------------------------------------------------------------
# RetryBuffer.process — empty buffer
# ---------------------------------------------------------------------------


class TestProcessEmptyBuffer:
    async def test_empty_returns_zero_counts(self):
        buf = RetryBuffer()
        producer = AsyncMock()
        result = await buf.process(producer)
        assert result == {"delivered": 0, "failed": 0, "remaining": 0}
        producer.assert_not_called()

    async def test_processing_flag_reset_after_empty(self):
        buf = RetryBuffer()
        await buf.process(AsyncMock())
        assert buf._processing is False


# ---------------------------------------------------------------------------
# RetryBuffer.process — successful delivery
# ---------------------------------------------------------------------------


class TestProcessSuccessfulDelivery:
    async def test_single_message_delivered(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message("m1"))
        producer = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await buf.process(producer)

        assert result["delivered"] == 1
        assert result["failed"] == 0
        assert result["remaining"] == 0
        producer.assert_awaited_once()

    async def test_multiple_messages_all_delivered(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        for i in range(3):
            await buf.add(make_message(f"m{i}"))
        producer = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await buf.process(producer)

        assert result["delivered"] == 3
        assert result["failed"] == 0
        assert result["remaining"] == 0

    async def test_delivered_count_metric_incremented(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message("m1"))
        with patch("asyncio.sleep", new=AsyncMock()):
            await buf.process(AsyncMock())
        assert buf.get_metrics()["delivered_count"] == 1

    async def test_buffer_empty_after_delivery(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message("m1"))
        with patch("asyncio.sleep", new=AsyncMock()):
            await buf.process(AsyncMock())
        assert buf.get_size() == 0

    async def test_producer_called_with_correct_args(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        msg = make_message("m1", topic="my-topic", value={"x": 1}, key=b"k")
        await buf.add(msg)
        producer = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            await buf.process(producer)

        producer.assert_awaited_once_with("my-topic", {"x": 1}, b"k")

    async def test_processing_flag_reset_after_success(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message())
        with patch("asyncio.sleep", new=AsyncMock()):
            await buf.process(AsyncMock())
        assert buf._processing is False


# ---------------------------------------------------------------------------
# RetryBuffer.process — messages already at max retries (skip in main loop)
# ---------------------------------------------------------------------------


class TestProcessMaxRetriesExceededInMainLoop:
    async def test_message_at_max_retries_counted_as_failed(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        msg = make_message("m1", retry_count=5, max_retries=5)
        await buf.add(msg)

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await buf.process(AsyncMock())

        assert result["failed"] == 1
        assert result["delivered"] == 0

    async def test_failed_count_metric_incremented(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        msg = make_message("m1", retry_count=5, max_retries=5)
        await buf.add(msg)
        with patch("asyncio.sleep", new=AsyncMock()):
            await buf.process(AsyncMock())
        assert buf.get_metrics()["failed_count"] == 1

    async def test_message_over_max_retries_also_failed(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        msg = make_message("m1", retry_count=10, max_retries=5)
        await buf.add(msg)
        with patch("asyncio.sleep", new=AsyncMock()):
            result = await buf.process(AsyncMock())
        assert result["failed"] == 1


# ---------------------------------------------------------------------------
# RetryBuffer.process — transient failures (retry logic)
# ---------------------------------------------------------------------------


class TestProcessTransientFailures:
    async def test_failed_message_re_added_to_buffer(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        msg = make_message("m1", retry_count=0, max_retries=5)
        await buf.add(msg)
        producer = AsyncMock(side_effect=RuntimeError("kafka unavailable"))

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await buf.process(producer)

        # retry_count becomes 1, which is < 5, so re-added
        assert result["remaining"] == 1
        assert result["delivered"] == 0
        assert result["failed"] == 0

    async def test_retry_count_incremented_after_failure(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        msg = make_message("m1", retry_count=0, max_retries=5)
        await buf.add(msg)
        producer = AsyncMock(side_effect=ValueError("bad value"))

        with patch("asyncio.sleep", new=AsyncMock()):
            await buf.process(producer)

        # The message should be back in the buffer with retry_count=1
        remaining_msg = buf._buffer[0]
        assert remaining_msg.retry_count == 1

    async def test_all_retry_error_types_caught(self):
        errors = [
            RuntimeError("rt"),
            ValueError("ve"),
            TypeError("te"),
            KeyError("ke"),
            AttributeError("ae"),
            ConnectionError("ce"),
            OSError("oe"),
            TimeoutError(),
        ]
        for err in errors:
            buf = RetryBuffer(base_retry_delay=0.0)
            await buf.add(make_message("m1"))
            producer = AsyncMock(side_effect=err)
            with patch("asyncio.sleep", new=AsyncMock()):
                result = await buf.process(producer)
            assert result["remaining"] == 1, f"Error {type(err)} not caught"

    async def test_failed_message_at_max_retries_in_retry_list_counted_as_failed(self):
        # retry_count starts at 4, fails → becomes 5 == max_retries → counted as failed
        buf = RetryBuffer(base_retry_delay=0.0)
        msg = make_message("m1", retry_count=4, max_retries=5)
        await buf.add(msg)
        producer = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await buf.process(producer)

        assert result["failed"] == 1
        assert result["remaining"] == 0
        assert buf.get_metrics()["failed_count"] == 1

    async def test_failed_message_stays_in_buffer_when_retries_remain(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        msg = make_message("m1", retry_count=1, max_retries=5)
        await buf.add(msg)
        producer = AsyncMock(side_effect=ConnectionError("nope"))

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await buf.process(producer)

        assert result["remaining"] == 1
        assert buf.get_size() == 1

    async def test_processing_flag_reset_after_failure(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message("m1"))
        producer = AsyncMock(side_effect=RuntimeError("err"))

        with patch("asyncio.sleep", new=AsyncMock()):
            await buf.process(producer)

        assert buf._processing is False


# ---------------------------------------------------------------------------
# RetryBuffer.process — mixed success and failure
# ---------------------------------------------------------------------------


class TestProcessMixed:
    async def test_some_delivered_some_failed(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        # m1: will succeed
        # m2: already at max retries → failed immediately
        # m3: will succeed
        await buf.add(make_message("m1", retry_count=0, max_retries=5))
        await buf.add(make_message("m2", retry_count=5, max_retries=5))
        await buf.add(make_message("m3", retry_count=0, max_retries=5))

        producer = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await buf.process(producer)

        assert result["delivered"] == 2
        assert result["failed"] == 1
        assert result["remaining"] == 0

    async def test_metrics_reflect_mixed_results(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message("ok", retry_count=0, max_retries=5))
        await buf.add(make_message("bad", retry_count=5, max_retries=5))
        with patch("asyncio.sleep", new=AsyncMock()):
            await buf.process(AsyncMock())
        m = buf.get_metrics()
        assert m["delivered_count"] == 1
        assert m["failed_count"] == 1


# ---------------------------------------------------------------------------
# RetryBuffer.process — exponential backoff calculation
# ---------------------------------------------------------------------------


class TestExponentialBackoff:
    async def test_sleep_called_per_message(self):
        buf = RetryBuffer(base_retry_delay=1.0, max_retry_delay=60.0)
        await buf.add(make_message("m1", retry_count=0))
        sleep_mock = AsyncMock()

        with patch("asyncio.sleep", new=sleep_mock):
            await buf.process(AsyncMock())

        # sleep must be called at least once for the one message
        assert sleep_mock.call_count >= 1

    async def test_backoff_capped_at_max_retry_delay(self):
        buf = RetryBuffer(base_retry_delay=1.0, max_retry_delay=2.0)
        # retry_count=10 → 1.0 * 2^10 = 1024, should be capped at 2.0 before jitter
        msg = make_message("m1", retry_count=10, max_retries=50)
        await buf.add(msg)

        sleep_calls = []

        async def capturing_sleep(delay):
            sleep_calls.append(delay)

        producer = AsyncMock(side_effect=RuntimeError("fail"))

        with patch("asyncio.sleep", new=capturing_sleep):
            await buf.process(producer)

        # The sleep value should be around max_retry_delay (2.0) ± 10% jitter
        assert sleep_calls[0] <= 2.0 * 1.1 + 0.001  # cap + max jitter

    async def test_jitter_applied(self):
        """Delay should include jitter (may differ from base * 2^n)."""
        buf = RetryBuffer(base_retry_delay=10.0, max_retry_delay=1000.0)
        await buf.add(make_message("m1", retry_count=0))

        sleep_calls = []

        async def capturing_sleep(delay):
            sleep_calls.append(delay)

        producer = AsyncMock()

        with patch("asyncio.sleep", new=capturing_sleep):
            await buf.process(producer)

        # base_delay = 10.0 * 2^0 = 10.0; jitter = ±10% → [9.0, 11.0]
        assert len(sleep_calls) == 1
        assert 9.0 <= sleep_calls[0] <= 11.0


# ---------------------------------------------------------------------------
# RetryBuffer.process — non-retryable errors should propagate
# ---------------------------------------------------------------------------


class TestNonRetryableErrors:
    async def test_unexpected_exception_propagates(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message("m1"))

        # Exception NOT in RETRY_DELIVERY_ERRORS
        producer = AsyncMock(side_effect=Exception("unexpected"))

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(Exception, match="unexpected"):
                await buf.process(producer)

    async def test_processing_flag_reset_on_unexpected_exception(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message("m1"))
        producer = AsyncMock(side_effect=Exception("boom"))

        with patch("asyncio.sleep", new=AsyncMock()):
            try:
                await buf.process(producer)
            except Exception:
                pass

        assert buf._processing is False


# ---------------------------------------------------------------------------
# RetryBuffer.process — concurrent calls
# ---------------------------------------------------------------------------


class TestConcurrentProcess:
    async def test_second_call_while_first_in_progress(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message("m1"))

        results = []
        gate = asyncio.Event()

        async def slow_producer(topic, value, key):
            gate.set()
            await asyncio.sleep(0.05)

        async def first():
            with patch("asyncio.sleep", new=AsyncMock(wraps=asyncio.sleep)):
                r = await buf.process(slow_producer)
                results.append(("first", r))

        async def second():
            # Wait until first has started
            await asyncio.sleep(0.01)
            r = await buf.process(AsyncMock())
            results.append(("second", r))

        # Run both but second should find already_processing or empty buffer
        await asyncio.gather(first(), second(), return_exceptions=True)

        labels = [r[0] for r in results]
        assert "first" in labels or "second" in labels  # at least one ran


# ---------------------------------------------------------------------------
# Full lifecycle integration tests
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_add_then_process_then_empty(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        for i in range(5):
            await buf.add(make_message(f"m{i}"))
        assert buf.get_size() == 5
        with patch("asyncio.sleep", new=AsyncMock()):
            result = await buf.process(AsyncMock())
        assert result["delivered"] == 5
        assert buf.get_size() == 0

    async def test_multiple_process_calls(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message("first"))
        with patch("asyncio.sleep", new=AsyncMock()):
            r1 = await buf.process(AsyncMock())
        assert r1["delivered"] == 1

        await buf.add(make_message("second"))
        with patch("asyncio.sleep", new=AsyncMock()):
            r2 = await buf.process(AsyncMock())
        assert r2["delivered"] == 1

    async def test_metrics_accumulate_across_calls(self):
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message("m1"))
        with patch("asyncio.sleep", new=AsyncMock()):
            await buf.process(AsyncMock())
        await buf.add(make_message("m2"))
        with patch("asyncio.sleep", new=AsyncMock()):
            await buf.process(AsyncMock())
        assert buf.get_metrics()["delivered_count"] == 2
        assert buf.get_metrics()["buffered_count"] == 2

    async def test_retry_message_eventually_delivered(self):
        """Simulate first call fails, second call succeeds."""
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message("m1", retry_count=0, max_retries=5))

        # First process: producer fails → message goes back with retry_count=1
        fail_producer = AsyncMock(side_effect=RuntimeError("down"))
        with patch("asyncio.sleep", new=AsyncMock()):
            r1 = await buf.process(fail_producer)
        assert r1["remaining"] == 1

        # Second process: producer succeeds
        ok_producer = AsyncMock()
        with patch("asyncio.sleep", new=AsyncMock()):
            r2 = await buf.process(ok_producer)
        assert r2["delivered"] == 1
        assert buf.get_size() == 0

    async def test_max_retries_zero_means_fail_immediately(self):
        """max_retries=0: message has retry_count=0 >= 0, so discarded immediately."""
        buf = RetryBuffer(base_retry_delay=0.0)
        await buf.add(make_message("m1", retry_count=0, max_retries=0))
        with patch("asyncio.sleep", new=AsyncMock()):
            result = await buf.process(AsyncMock())
        assert result["failed"] == 1
        assert result["delivered"] == 0


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_buffered_message_exported(self):
        from enhanced_agent_bus.retry_buffer import __all__ as exports

        assert "BufferedMessage" in exports

    def test_retry_buffer_exported(self):
        from enhanced_agent_bus.retry_buffer import __all__ as exports

        assert "RetryBuffer" in exports
