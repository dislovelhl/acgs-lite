"""
ACGS-2 Decorators Tests
Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio

import pytest

try:
    from ..decorators import SpanContext, metered, timed, traced
    from ..telemetry import CONSTITUTIONAL_HASH
except ImportError:
    from observability.decorators import (
        SpanContext,
        metered,  # type: ignore
        timed,
        traced,
    )


class TestTracedDecorator:
    """Tests for @traced decorator."""

    @pytest.mark.asyncio
    async def test_traced_async_function(self):
        """@traced works with async functions."""
        call_count = 0

        @traced(name="test_operation")
        async def async_operation(value: int) -> int:
            nonlocal call_count
            call_count += 1
            return value * 2

        result = await async_operation(5)

        assert result == 10
        assert call_count == 1

    def test_traced_sync_function(self):
        """@traced works with sync functions."""
        call_count = 0

        @traced(name="sync_operation")
        def sync_operation(value: int) -> int:
            nonlocal call_count
            call_count += 1
            return value * 2

        result = sync_operation(5)

        assert result == 10
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_traced_with_args_recording(self):
        """@traced records arguments when enabled."""

        @traced(name="with_args", record_args=True)
        async def operation_with_args(a: int, b: str, c: bool = True) -> str:
            return f"{a}-{b}-{c}"

        result = await operation_with_args(1, "test", c=False)

        assert result == "1-test-False"

    @pytest.mark.asyncio
    async def test_traced_exception_handling(self):
        """@traced handles exceptions correctly."""

        @traced(name="failing_op")
        async def failing_operation():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await failing_operation()

    def test_traced_sync_exception_handling(self):
        """@traced handles sync exceptions correctly."""

        @traced(name="sync_failing")
        def sync_failing():
            raise RuntimeError("sync error")

        with pytest.raises(RuntimeError, match="sync error"):
            sync_failing()

    @pytest.mark.asyncio
    async def test_traced_default_name(self):
        """@traced uses function name as default span name."""

        @traced()
        async def my_custom_function():
            return "done"

        result = await my_custom_function()
        assert result == "done"

    @pytest.mark.asyncio
    async def test_traced_with_service_name(self):
        """@traced accepts service name."""

        @traced(service_name="custom-service")
        async def service_operation():
            return "ok"

        result = await service_operation()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_traced_with_attributes(self):
        """@traced accepts custom attributes."""
        attrs = {"operation.type": "test", "priority": "high"}

        @traced(attributes=attrs)
        async def attributed_operation():
            return True

        result = await attributed_operation()
        assert result is True


class TestMeteredDecorator:
    """Tests for @metered decorator."""

    @pytest.mark.asyncio
    async def test_metered_async_function(self):
        """@metered works with async functions."""

        @metered(counter_name="test_calls")
        async def metered_operation(x: int) -> int:
            return x + 1

        result = await metered_operation(10)

        assert result == 11

    def test_metered_sync_function(self):
        """@metered works with sync functions."""

        @metered(counter_name="sync_calls")
        def sync_metered(x: int) -> int:
            return x + 1

        result = sync_metered(10)

        assert result == 11

    @pytest.mark.asyncio
    async def test_metered_tracks_exceptions(self):
        """@metered tracks failed operations."""

        @metered()
        async def failing_metered():
            raise ValueError("expected failure")

        with pytest.raises(ValueError):
            await failing_metered()

    def test_metered_sync_tracks_exceptions(self):
        """@metered tracks sync failed operations."""

        @metered()
        def sync_failing_metered():
            raise RuntimeError("sync failure")

        with pytest.raises(RuntimeError):
            sync_failing_metered()

    @pytest.mark.asyncio
    async def test_metered_custom_histogram_name(self):
        """@metered accepts custom histogram name."""

        @metered(histogram_name="custom_latency")
        async def custom_histogram_op():
            return "done"

        result = await custom_histogram_op()
        assert result == "done"


class TestTimedDecorator:
    """Tests for @timed decorator."""

    @pytest.mark.asyncio
    async def test_timed_async_function(self):
        """@timed works with async functions."""

        @timed(histogram_name="operation_time")
        async def timed_operation():
            await asyncio.sleep(0.01)
            return "complete"

        result = await timed_operation()

        assert result == "complete"

    def test_timed_sync_function(self):
        """@timed works with sync functions."""

        @timed()
        def sync_timed():
            return sum(range(100))

        result = sync_timed()

        assert result == 4950

    @pytest.mark.asyncio
    async def test_timed_seconds_unit(self):
        """@timed supports seconds unit."""

        @timed(unit="s")
        async def seconds_timed():
            return True

        result = await seconds_timed()
        assert result is True

    @pytest.mark.asyncio
    async def test_timed_exception_still_records(self):
        """@timed records time even on exception."""

        @timed()
        async def failing_timed():
            raise ValueError("timed failure")

        with pytest.raises(ValueError):
            await failing_timed()


class TestSpanContext:
    """Tests for SpanContext class."""

    def test_span_context_sync(self):
        """SpanContext works synchronously."""
        with SpanContext("child_operation") as span:
            span.set_attribute("child.attr", "value")

    @pytest.mark.asyncio
    async def test_span_context_async(self):
        """SpanContext works asynchronously."""
        async with SpanContext("async_child") as span:
            span.set_attribute("async.attr", "value")

    def test_span_context_with_attributes(self):
        """SpanContext accepts attributes."""
        attrs = {"step": 1, "status": "running"}

        with SpanContext("step_operation", attributes=attrs) as span:
            span.set_attribute("progress", 50)

    def test_span_context_exception_handling(self):
        """SpanContext handles exceptions."""
        with pytest.raises(RuntimeError):
            with SpanContext("failing_child"):
                raise RuntimeError("child failure")

    @pytest.mark.asyncio
    async def test_span_context_async_exception(self):
        """SpanContext handles async exceptions."""
        with pytest.raises(ValueError):
            async with SpanContext("async_failing"):
                raise ValueError("async child failure")

    def test_span_context_with_service_name(self):
        """SpanContext accepts service name."""
        with SpanContext("service_child", service_name="child-service") as span:
            assert span is not None


class TestDecoratorCombinations:
    """Tests for combining decorators."""

    @pytest.mark.asyncio
    async def test_traced_and_metered(self):
        """@traced and @metered work together."""

        @traced(name="combined_op")
        @metered(counter_name="combined_calls")
        async def combined_operation():
            return "combined"

        result = await combined_operation()

        assert result == "combined"

    @pytest.mark.asyncio
    async def test_traced_and_timed(self):
        """@traced and @timed work together."""

        @traced()
        @timed()
        async def traced_timed():
            return 42

        result = await traced_timed()

        assert result == 42

    def test_all_decorators_sync(self):
        """All decorators work together on sync function."""

        @traced()
        @metered()
        @timed()
        def fully_instrumented():
            return "instrumented"

        result = fully_instrumented()

        assert result == "instrumented"
