"""
ACGS-2 Structured Logging Module  [CANONICAL LOGGING MODULE]
Constitutional Hash: cdd01ef066bc6cf2

Provides standardized structured logging with:
- JSON output for enterprise log aggregation
- Correlation ID propagation across services
- RFC 5424 log level compliance
- Sensitive data redaction
- Integration with Splunk, ELK, Datadog

This is the **canonical** ``get_logger`` source for ACGS-2 (262 consumers as of
2026-02-26).  All new code MUST import from this module.

.. note::
    Logging module landscape (as of 2026-02-26):

    - ``src.core.shared.structured_logging`` — **THIS MODULE** (canonical, 262 consumers).
      Returns ``StructuredLogger`` supporting keyword-args in log calls
      (e.g., ``logger.info("event", key=val)``).  **Use this for all new code.**

    - ``src.core.shared.acgs_logging_config`` — Deprecated (30 consumers in src/core/).
      Backed by structlog + OpenTelemetry.  Returns ``logging.Logger | structlog.BoundLogger``.
      ``get_logger()`` now emits ``DeprecationWarning`` on every call.

    - ``src.core.shared.acgs_logging`` — Audit-logging package (23 consumers).
      Use for tenant-scoped audit entries, ``TenantAuditLogger``,
      ``init_service_logging()``, ``create_correlation_middleware()``.
      This package is NOT deprecated — it serves a distinct audit purpose.

    - ``src.core.shared.errors.logging`` — Deprecated, zero consumers (retained for reference).

Usage:
    from src.core.shared.structured_logging import get_logger, configure_logging

    configure_logging()
    logger = get_logger(__name__)

    logger.info("message_processed", message_id="123", agent_id="agent-1")
"""

import inspect
import json
import logging
import os
import sys
import traceback
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from typing import ClassVar, TypeVar

T = TypeVar("T")  # Generic return type for decorators

try:
    from src.core.shared.types import JSONDict, JSONValue
except ImportError:
    JSONValue = object

# ===== Correlation ID Context =====

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def bind_correlation_id(correlation_id: str, trace_id: str | None = None) -> None:
    """
    Bind correlation ID to the current async context.
    Standardized implementation for ACGS-2.
    """
    correlation_id_var.set(correlation_id)


# ===== Configuration =====

# Sensitive field names to redact
SENSITIVE_FIELDS: set[str] = {
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "credential",
    "private_key",
    "privatekey",
    "access_token",
    "refresh_token",
    "client_secret",
    "redis_password",
    "kafka_password",
    "oidc_client_secret",
}

# Maximum log message size before truncation
MAX_LOG_SIZE = 10000  # 10KB
TRUNCATION_SUFFIX = " [truncated]"

# RFC 5424 log level mapping
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# ===== JSON Formatter =====


class StructuredJSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Outputs logs in JSON format with consistent schema:
    {
        "timestamp": "2025-01-03T12:00:00.000Z",
        "level": "INFO",
        "logger": "module.name",
        "message": "Log message",
        "correlation_id": "abc-123",
        "tenant_id": "tenant-1",
        "extra": {...}
    }
    """

    def __init__(
        self,
        include_stack_trace: bool = True,
        redact_sensitive: bool = True,
    ):
        super().__init__()
        self.include_stack_trace = include_stack_trace
        self.redact_sensitive = redact_sensitive

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Base log structure
        log_data: JSONDict = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context variables
        correlation_id = correlation_id_var.get()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        tenant_id = tenant_id_var.get()
        if tenant_id:
            log_data["tenant_id"] = tenant_id

        request_id = request_id_var.get()
        if request_id:
            log_data["request_id"] = request_id

        # Add extra fields from record
        if hasattr(record, "extra") and record.extra:
            extra = self._process_extra(record.extra)
            log_data["extra"] = extra

        # Add structured data from record args if dict
        if isinstance(record.args, dict):
            extra = self._process_extra(record.args)
            log_data.setdefault("extra", {}).update(extra)

        # Add exception info
        if record.exc_info and self.include_stack_trace:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                "message": str(record.exc_info[1]) if record.exc_info[1] else "",
            }
            if self.include_stack_trace:
                log_data["exception"]["traceback"] = traceback.format_exception(*record.exc_info)

        # Add source location for debugging
        if record.levelno >= logging.WARNING:
            log_data["source"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Serialize to JSON
        json_str = json.dumps(log_data, default=str, ensure_ascii=False)

        # Truncate if too large
        if len(json_str) > MAX_LOG_SIZE:
            json_str = json_str[: MAX_LOG_SIZE - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX

        return json_str

    def _process_extra(self, extra: JSONDict) -> JSONDict:
        """Process extra fields with redaction."""
        if not self.redact_sensitive:
            return extra

        processed = {}
        for key, value in extra.items():
            lower_key = key.lower()

            # Check if field name contains sensitive words
            if any(sensitive in lower_key for sensitive in SENSITIVE_FIELDS):
                processed[key] = "[REDACTED]"
            elif isinstance(value, dict):
                processed[key] = self._process_extra(value)
            elif isinstance(value, str) and len(value) > 1000:
                # Truncate long strings
                processed[key] = value[:1000] + "..."
            else:
                processed[key] = value

        return processed


class TextFormatter(logging.Formatter):
    """
    Text log formatter for development.

    Outputs human-readable logs with color support.
    """

    COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as colored text."""
        color = self.COLORS.get(record.levelname, "")

        # Build message parts
        parts = [
            f"{color}[{record.levelname}]{self.RESET}",
            datetime.now().strftime("%H:%M:%S"),
            f"[{record.name}]",
            record.getMessage(),
        ]

        # Add correlation ID if present
        correlation_id = correlation_id_var.get()
        if correlation_id:
            parts.insert(3, f"[{correlation_id[:8]}]")

        # Add extra data
        if hasattr(record, "extra") and record.extra:
            extra_str = " ".join(f"{k}={v}" for k, v in record.extra.items())
            parts.append(f"| {extra_str}")

        message = " ".join(parts)

        # Add exception info
        if record.exc_info:
            message += "\n" + "".join(traceback.format_exception(*record.exc_info))

        return message


# ===== Structured Logger =====


class StructuredLogger:
    """
    Structured logger wrapper with convenience methods.

    Provides structured logging with automatic context injection
    and support for key-value extra data.

    Usage:
        logger = StructuredLogger("my.module")
        logger.info("User logged in", user_id="123", action="login")
    """

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def _log(
        self,
        level: int,
        message: str,
        *args: JSONValue,
        exc_info: Exception | bool | tuple[object] | None = None,
        **kwargs: JSONValue,
    ) -> None:
        """Internal log method with extra data handling."""
        if not self._logger.isEnabledFor(level):
            return

        if args:
            try:
                message = message % args
            except (TypeError, ValueError):
                message = f"{message} {' '.join(str(arg) for arg in args)}"

        # Resolve exc_info=True to the current exception tuple immediately,
        # before leaving the caller's except-block context.
        if exc_info is True:
            exc_info = sys.exc_info()

        record = self._logger.makeRecord(
            name=self._logger.name,
            level=level,
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=exc_info,
        )

        # Attach extra data
        record.extra = kwargs

        self._logger.handle(record)

    def debug(self, message: str, *args: JSONValue, **kwargs: JSONValue) -> None:
        """Log debug message with extra data."""
        self._log(logging.DEBUG, message, *args, **kwargs)

    def info(self, message: str, *args: JSONValue, **kwargs: JSONValue) -> None:
        """Log info message with extra data."""
        self._log(logging.INFO, message, *args, **kwargs)

    def warning(self, message: str, *args: JSONValue, **kwargs: JSONValue) -> None:
        """Log warning message with extra data."""
        self._log(logging.WARNING, message, *args, **kwargs)

    def error(
        self,
        message: str,
        *args: JSONValue,
        exc_info: Exception | bool | tuple[object] | None = None,
        **kwargs: JSONValue,
    ) -> None:
        """Log error message with optional exception info."""
        if exc_info is True:
            exc_info = sys.exc_info()
        self._log(logging.ERROR, message, *args, exc_info=exc_info, **kwargs)

    def critical(
        self,
        message: str,
        *args: JSONValue,
        exc_info: Exception | bool | tuple[object] | None = None,
        **kwargs: JSONValue,
    ) -> None:
        """Log critical message with optional exception info."""
        if exc_info is True:
            exc_info = sys.exc_info()
        self._log(logging.CRITICAL, message, *args, exc_info=exc_info, **kwargs)

    def exception(self, message: str, **kwargs: JSONValue) -> None:
        """Log exception with full traceback."""
        self._log(logging.ERROR, message, exc_info=sys.exc_info(), **kwargs)

    def bind(self, **kwargs: JSONValue) -> "BoundLogger":
        """Create a bound logger with preset extra fields."""
        return BoundLogger(self, kwargs)


class BoundLogger:
    """Logger with preset extra fields."""

    def __init__(self, logger: StructuredLogger, context: JSONDict):
        self._logger = logger
        self._context = context

    def _merge_context(self, kwargs: JSONDict) -> JSONDict:
        """Merge bound context with call-time kwargs."""
        return {**self._context, **kwargs}

    def debug(self, message: str, **kwargs: JSONValue) -> None:
        """Log a DEBUG message with bound context merged in."""
        self._logger.debug(message, **self._merge_context(kwargs))

    def info(self, message: str, **kwargs: JSONValue) -> None:
        """Log an INFO message with bound context merged in."""
        self._logger.info(message, **self._merge_context(kwargs))

    def warning(self, message: str, **kwargs: JSONValue) -> None:
        """Log a WARNING message with bound context merged in."""
        self._logger.warning(message, **self._merge_context(kwargs))

    def error(self, message: str, **kwargs: JSONValue) -> None:
        """Log an ERROR message with bound context merged in."""
        self._logger.error(message, **self._merge_context(kwargs))

    def critical(self, message: str, **kwargs: JSONValue) -> None:
        """Log a CRITICAL message with bound context merged in."""
        self._logger.critical(message, **self._merge_context(kwargs))

    def exception(self, message: str, **kwargs: JSONValue) -> None:
        """Log an ERROR with exception traceback and bound context merged in."""
        self._logger.exception(message, **self._merge_context(kwargs))


# ===== Configuration Functions =====


def configure_logging(
    level: str | None = None,
    format_type: str | None = None,
    include_stack_trace: bool = True,
    redact_sensitive: bool = True,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Output format ("json" or "text")
        include_stack_trace: Include full stack traces in error logs
        redact_sensitive: Redact sensitive field values
    """
    # Get configuration from environment if not provided
    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    format_type = format_type or os.getenv("LOG_FORMAT", "json").lower()

    # Validate log level
    log_level = LOG_LEVELS.get(level, logging.INFO)

    # Create formatter
    if format_type == "json":
        formatter = StructuredJSONFormatter(
            include_stack_trace=include_stack_trace,
            redact_sensitive=redact_sensitive,
        )
    else:
        formatter = TextFormatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Log configuration
    logger = get_logger("structured_logging")
    logger.info(
        "Logging configured",
        configured_level=level,
        format=format_type,
        redact_sensitive=redact_sensitive,
    )


def get_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name)


# ===== Context Management =====


def set_correlation_id(correlation_id: str | None = None) -> str:
    """
    Set correlation ID for current context.

    Args:
        correlation_id: Optional correlation ID (generated if not provided)

    Returns:
        The correlation ID that was set
    """
    cid = correlation_id or str(uuid.uuid4())
    correlation_id_var.set(cid)
    return cid


def get_correlation_id() -> str:
    """Get current correlation ID."""
    return correlation_id_var.get()


def set_tenant_id(tenant_id: str) -> None:
    """Set tenant ID for current context."""
    tenant_id_var.set(tenant_id)


def get_tenant_id() -> str:
    """Get current tenant ID."""
    return tenant_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set request ID for current context."""
    request_id_var.set(request_id)


# ===== Decorators =====


def log_function_call(logger: StructuredLogger | None = None) -> Callable:
    """
    Decorator to log function entry and exit.

    Usage:
        @log_function_call()
        def my_function(arg1, arg2):
            ...
    """

    def decorator(func: Callable) -> Callable:
        nonlocal logger
        if logger is None:
            logger = get_logger(func.__module__)

        @wraps(func)
        def wrapper(*args: JSONValue, **kwargs: JSONValue) -> T:
            logger.debug(
                f"Entering {func.__name__}",
                function=func.__name__,
                args_count=len(args),
                kwargs_keys=list(kwargs.keys()),
            )
            try:
                result = func(*args, **kwargs)
                logger.debug(
                    f"Exiting {func.__name__}",
                    function=func.__name__,
                    success=True,
                )
                return result
            except Exception as e:
                logger.error(
                    f"Error in {func.__name__}",
                    function=func.__name__,
                    error=str(e),
                    exc_info=True,
                )
                raise

        @wraps(func)
        async def async_wrapper(*args: JSONValue, **kwargs: JSONValue) -> T:
            logger.debug(
                f"Entering {func.__name__}",
                function=func.__name__,
                args_count=len(args),
                kwargs_keys=list(kwargs.keys()),
            )
            try:
                result = await func(*args, **kwargs)
                logger.debug(
                    f"Exiting {func.__name__}",
                    function=func.__name__,
                    success=True,
                )
                return result
            except Exception as e:
                logger.error(
                    f"Error in {func.__name__}",
                    function=func.__name__,
                    error=str(e),
                    exc_info=True,
                )
                raise

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


# ===== OpenTelemetry Integration =====


def setup_opentelemetry(service_name: str = "") -> None:
    """Initialize OpenTelemetry TracerProvider for distributed tracing.

    Thin wrapper that delegates to the OTel SDK when available.
    No-op when ``opentelemetry`` is not installed.

    Args:
        service_name: Service identifier for trace spans.
    """
    try:
        from opentelemetry import trace as _trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        resource = Resource(attributes={"service.name": service_name})
        provider = TracerProvider(resource=resource)
        _trace.set_tracer_provider(provider)
    except ImportError:
        pass


def instrument_fastapi(app: object) -> None:
    """Auto-instrument a FastAPI app with OpenTelemetry spans.

    No-op when ``opentelemetry-instrumentation-fastapi`` is not installed.

    Args:
        app: A ``FastAPI`` application instance.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor().instrument_app(app)  # type: ignore[arg-type]
    except ImportError:
        pass


# ===== Export =====

__all__ = [
    "BoundLogger",
    # Formatters
    "StructuredJSONFormatter",
    # Loggers
    "StructuredLogger",
    "TextFormatter",
    # Configuration
    "configure_logging",
    # Context variables
    "correlation_id_var",
    "get_correlation_id",
    "get_logger",
    "get_tenant_id",
    "instrument_fastapi",
    # Decorators
    "log_function_call",
    "request_id_var",
    # Context management
    "set_correlation_id",
    "set_request_id",
    "set_tenant_id",
    # OpenTelemetry
    "setup_opentelemetry",
    "tenant_id_var",
]
