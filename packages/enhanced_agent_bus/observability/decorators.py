"""
ACGS-2 Observability Decorators
Constitutional Hash: 608508a9bd224290

Function decorators for automatic tracing and metrics collection.
"""

import asyncio
import functools
import inspect
import time
from collections.abc import Callable
from typing import TypeVar, cast

from enhanced_agent_bus.bus_types import JSONDict, JSONValue

from .structured_logging import get_logger
from .telemetry import (
    CONSTITUTIONAL_HASH,
    OTEL_AVAILABLE,
    TracingContext,
    get_meter,
    get_tracer,
)

logger = get_logger(__name__)
F = TypeVar("F", bound=Callable[..., object])
TRACED_DECORATOR_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    asyncio.CancelledError,
)


def _set_span_args(span: object, args: tuple, kwargs: dict) -> None:
    """Set span attributes for function arguments."""
    if args:
        span.set_attribute("args.count", len(args))
    if kwargs:
        for key, value in kwargs.items():
            if isinstance(value, (str, int, float, bool)):
                span.set_attribute(f"arg.{key}", value)


def _handle_span_error(span: object, error: BaseException) -> None:
    """Handle error in span context."""
    span.set_attribute("success", False)
    span.set_attribute("error.type", type(error).__name__)
    span.set_attribute("error.message", str(error))


def _create_async_traced_wrapper(
    func: F,
    span_name: str,
    service_name: str | None,
    attributes: JSONDict | None,
    record_args: bool,
) -> Callable[..., object]:
    """Create async wrapper for traced function."""

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs) -> object:
        with TracingContext(span_name, service_name, attributes) as span:
            if record_args:
                _set_span_args(span, args, kwargs)

            try:
                result = await func(*args, **kwargs)
                span.set_attribute("success", True)
                return result
            except TRACED_DECORATOR_ERRORS as e:
                _handle_span_error(span, e)
                raise

    return async_wrapper


def _create_sync_traced_wrapper(
    func: F,
    span_name: str,
    service_name: str | None,
    attributes: JSONDict | None,
    record_args: bool,
) -> Callable[..., object]:
    """Create sync wrapper for traced function."""

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> object:
        with TracingContext(span_name, service_name, attributes) as span:
            if record_args:
                _set_span_args(span, args, kwargs)

            try:
                result = func(*args, **kwargs)
                span.set_attribute("success", True)
                return result
            except TRACED_DECORATOR_ERRORS as e:
                _handle_span_error(span, e)
                raise

    return sync_wrapper


def traced(
    name: str | None = None,
    service_name: str | None = None,
    attributes: JSONDict | None = None,
    record_args: bool = False,
) -> Callable[[F], F]:
    """
    Decorator to trace function execution with OpenTelemetry.

    Args:
        name: Span name (defaults to function name)
        service_name: Service name for tracer
        attributes: Additional span attributes
        record_args: Whether to record function arguments as attributes

    Example:
        @traced(name="process_message", record_args=True)
        async def process(message: Message) -> Result:
            ...
    """

    def decorator(func: F) -> F:
        span_name = name or func.__name__
        _tracer = get_tracer(service_name)

        if inspect.iscoroutinefunction(func):
            wrapper = _create_async_traced_wrapper(
                func, span_name, service_name, attributes, record_args
            )
        else:
            wrapper = _create_sync_traced_wrapper(
                func, span_name, service_name, attributes, record_args
            )

        return cast(F, wrapper)

    return decorator


def metered(
    counter_name: str | None = None,
    histogram_name: str | None = None,
    service_name: str | None = None,
) -> Callable[[F], F]:
    """
    Decorator to collect metrics for function execution.

    Args:
        counter_name: Name for call counter (defaults to {func}_calls)
        histogram_name: Name for latency histogram (defaults to {func}_latency_ms)
        service_name: Service name for meter

    Example:
        @metered(counter_name="messages_processed")
        async def process(message: Message) -> Result:
            ...
    """

    def decorator(func: F) -> F:
        meter = get_meter(service_name)
        func_name = func.__name__

        c_name = counter_name or f"{func_name}_calls"
        h_name = histogram_name or f"{func_name}_latency_ms"

        counter = meter.create_counter(
            name=f"acgs2.{c_name}",
            description=f"Number of {func_name} calls",
        )

        histogram = meter.create_histogram(
            name=f"acgs2.{h_name}",
            unit="ms",
            description=f"Latency of {func_name}",
        )

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> object:
            start_time = time.perf_counter()
            success = True

            try:
                result = await func(*args, **kwargs)
                return result
            except (OSError, RuntimeError, ValueError, TypeError) as e:
                success = False
                raise e
            finally:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                attrs = {
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "success": str(success),
                }
                counter.add(1, attrs)
                histogram.record(elapsed_ms, attrs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> object:
            start_time = time.perf_counter()
            success = True

            try:
                result = func(*args, **kwargs)
                return result
            except (OSError, RuntimeError, ValueError, TypeError) as e:
                success = False
                raise e
            finally:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                attrs = {
                    "constitutional_hash": CONSTITUTIONAL_HASH,
                    "success": str(success),
                }
                counter.add(1, attrs)
                histogram.record(elapsed_ms, attrs)

        if inspect.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        return cast(F, sync_wrapper)

    return decorator


def timed(
    histogram_name: str | None = None,
    service_name: str | None = None,
    unit: str = "ms",
) -> Callable[[F], F]:
    """
    Lightweight decorator to record execution time only.

    Args:
        histogram_name: Name for latency histogram
        service_name: Service name for meter
        unit: Time unit (ms or s)

    Example:
        @timed(histogram_name="z3_solve_time")
        async def solve(formula: str) -> Result:
            ...
    """

    def decorator(func: F) -> F:
        meter = get_meter(service_name)
        func_name = func.__name__
        h_name = histogram_name or f"{func_name}_duration_{unit}"

        histogram = meter.create_histogram(
            name=f"acgs2.{h_name}",
            unit=unit,
            description=f"Duration of {func_name}",
        )

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> object:
            start_time = time.perf_counter()

            try:
                return await func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start_time
                if unit == "ms":
                    elapsed *= 1000
                histogram.record(elapsed, {"constitutional_hash": CONSTITUTIONAL_HASH})

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> object:
            start_time = time.perf_counter()

            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start_time
                if unit == "ms":
                    elapsed *= 1000
                histogram.record(elapsed, {"constitutional_hash": CONSTITUTIONAL_HASH})

        if inspect.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        return cast(F, sync_wrapper)

    return decorator


class SpanContext:
    """
    Context manager for creating child spans within traced functions.

    Example:
        @traced("parent_operation")
        async def parent():
            with SpanContext("child_step") as span:
                span.set_attribute("step.id", 1)
                await child_operation()
    """

    def __init__(
        self,
        name: str,
        service_name: str | None = None,
        attributes: JSONDict | None = None,
    ):
        self.name = name
        self.service_name = service_name
        self.attributes = attributes or {}
        self._tracer = get_tracer(service_name)
        self._span = None
        self._context = None

    def __enter__(self) -> object:
        self._context = self._tracer.start_as_current_span(self.name)
        self._span = self._context.__enter__()

        # Add constitutional hash
        self._span.set_attribute("constitutional.hash", CONSTITUTIONAL_HASH)

        for key, value in self.attributes.items():
            self._span.set_attribute(key, value)

        return self._span

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool | None:
        if exc_type is not None and self._span:
            self._span.record_exception(exc_val)
            if OTEL_AVAILABLE:
                from opentelemetry.trace import Status, StatusCode

                self._span.set_status(Status(StatusCode.ERROR, str(exc_val)))

        if self._context:
            return self._context.__exit__(exc_type, exc_val, exc_tb)
        return False

    async def __aenter__(self) -> object:
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool | None:
        return self.__exit__(exc_type, exc_val, exc_tb)
