"""
ACGS-2 Structured Logging Configuration
Constitutional Hash: 608508a9bd224290

Implements the required logging from SPEC_ACGS2_ENHANCED.md Section 6.2.
Per Expert Panel Review (Kelsey Hightower - Cloud Native Expert).

Features:
- Structured JSON logging format
- PII/sensitive data redaction
- Distributed tracing support
- Required event logging
"""

import json
import logging
import os
import re
import sys
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from re import Pattern
from typing import IO

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

# Context variables for distributed tracing
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[str | None] = ContextVar("span_id", default=None)

# =============================================================================
# Log Levels per Section 6.2
# =============================================================================


class LogLevel(str, Enum):
    """Log levels per spec."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"


# Environment-based log level configuration
LOG_LEVEL_CONFIG = {
    "production": LogLevel.INFO,
    "staging": LogLevel.DEBUG,
    "development": LogLevel.DEBUG,
}


def get_log_level() -> str:
    """Get log level based on environment."""
    env = os.getenv("ENVIRONMENT", "development").lower()
    level = LOG_LEVEL_CONFIG.get(env, LogLevel.DEBUG)
    return level.value


# =============================================================================
# PII/Sensitive Data Redaction per Section 6.2
# =============================================================================


@dataclass
class RedactionPattern:
    """Pattern for redacting sensitive data."""

    name: str
    pattern: Pattern[str]
    replacement: str


# Sensitive patterns to redact
REDACTION_PATTERNS: list[RedactionPattern] = [
    # Email addresses
    RedactionPattern(
        name="email",
        pattern=re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
        replacement="***@***.***",
    ),
    # JWT tokens
    RedactionPattern(
        name="jwt",
        pattern=re.compile(r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*"),
        replacement="[JWT_REDACTED]",
    ),
    # API keys (common patterns)
    RedactionPattern(
        name="api_key",
        pattern=re.compile(
            r"(?i)(api[_-]?key|apikey|api_secret)[\"']?\s*[:=]\s*[\"']?([a-zA-Z0-9_-]{16,})"
        ),
        replacement=r"\1=[KEY_REDACTED]",
    ),
    # Bearer tokens
    RedactionPattern(
        name="bearer_token",
        pattern=re.compile(r"(?i)bearer\s+[a-zA-Z0-9_-]+"),
        replacement="Bearer [TOKEN_REDACTED]",
    ),
    # Password fields
    RedactionPattern(
        name="password",
        pattern=re.compile(r"(?i)(password|passwd|pwd)[\"']?\s*[:=]\s*[\"']?[^\s,;\"']+"),
        replacement=r"\1=[PASSWORD_REDACTED]",
    ),
    # Credit card numbers
    RedactionPattern(
        name="credit_card",
        pattern=re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"),
        replacement="[CARD_REDACTED]",
    ),
    # SSN
    RedactionPattern(
        name="ssn",
        pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        replacement="[SSN_REDACTED]",
    ),
    # Phone numbers
    RedactionPattern(
        name="phone",
        pattern=re.compile(r"\b(?:\+1[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b"),
        replacement="[PHONE_REDACTED]",
    ),
    # IP addresses (for privacy)
    RedactionPattern(
        name="ip_address",
        pattern=re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        replacement="[IP_REDACTED]",
    ),
    # Authorization headers
    RedactionPattern(
        name="auth_header",
        pattern=re.compile(r"(?i)(authorization)[\"']?\s*[:=]\s*[\"']?[^\s,;\"']+"),
        replacement=r"\1=[AUTH_REDACTED]",
    ),
]


def redact_sensitive_data(text: str) -> str:
    """Redact sensitive data from text using pattern matching."""
    if not isinstance(text, str):
        return text

    result = text
    for pattern in REDACTION_PATTERNS:
        result = pattern.pattern.sub(pattern.replacement, result)

    return result


def redact_dict(data: JSONDict) -> JSONDict:
    """Recursively redact sensitive data from a dictionary."""
    if not isinstance(data, dict):
        return data

    result: JSONDict = {}
    sensitive_keys = {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "auth",
    }

    for key, value in data.items():
        key_lower = key.lower()

        # Check if key is sensitive
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = redact_dict(value)
        elif isinstance(value, list):
            result[key] = [
                (
                    redact_dict(v)
                    if isinstance(v, dict)
                    else redact_sensitive_data(str(v))
                    if isinstance(v, str)
                    else v
                )
                for v in value
            ]
        elif isinstance(value, str):
            result[key] = redact_sensitive_data(value)
        else:
            result[key] = value

    return result


# =============================================================================
# Structured JSON Formatter
# =============================================================================


class StructuredJSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging per Section 6.2.

    Required fields:
    - timestamp: ISO 8601 format
    - level: DEBUG|INFO|WARN|ERROR|FATAL
    - service: service name
    - trace_id: distributed trace identifier
    - span_id: span identifier
    - message: human-readable message
    """

    def __init__(
        self,
        service_name: str = "acgs2-enhanced-agent-bus",
        include_extra: bool = True,
        redact_pii: bool = True,
    ):
        super().__init__()
        self.service_name = service_name
        self.include_extra = include_extra
        self.redact_pii = redact_pii
        self.constitutional_hash = CONSTITUTIONAL_HASH

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        # Base log structure per spec
        log_entry: JSONDict = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "trace_id": trace_id_var.get() or str(uuid.uuid4()),
            "span_id": span_id_var.get() or str(uuid.uuid4())[:16],
            "message": record.getMessage(),
            "constitutional_hash": self.constitutional_hash,
        }

        # Add logger name
        log_entry["logger"] = record.name

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if self.include_extra:
            extra_fields: JSONDict = {}
            for key, value in record.__dict__.items():
                if key not in {
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "stack_info",
                    "exc_info",
                    "exc_text",
                    "thread",
                    "threadName",
                    "message",
                    "asctime",
                }:
                    extra_fields[key] = value

            if extra_fields:
                log_entry["extra"] = extra_fields

        # Redact sensitive data
        if self.redact_pii:
            log_entry = redact_dict(log_entry)

        return json.dumps(log_entry, default=str, ensure_ascii=False)


# =============================================================================
# Required Event Loggers per Section 6.2
# =============================================================================


@dataclass
class StructuredLogger:
    """
    Structured logger for ACGS-2 events.

    Implements required events from Section 6.2:
    - constitutional_validation
    - policy_evaluation
    - security_violation
    """

    service_name: str = "acgs2-enhanced-agent-bus"
    logger: logging.Logger = field(default=None, repr=False)
    redact_pii: bool = True

    def __post_init__(self):
        """Initialize the logger."""
        if self.logger is None:
            self.logger = logging.getLogger(f"acgs2.{self.service_name}")

    def _log_event(
        self,
        event_type: str,
        level: int,
        fields: JSONDict,
        message: str | None = None,
    ) -> None:
        """Log a structured event."""
        event_data = {
            "event_type": event_type,
            "constitutional_hash": CONSTITUTIONAL_HASH,
            **fields,
        }

        if self.redact_pii:
            event_data = redact_dict(event_data)

        msg = message or f"{event_type}: {json.dumps(event_data, default=str)}"
        self.logger.log(level, msg, extra=event_data)

    # -------------------------------------------------------------------------
    # Required Events per Section 6.2
    # -------------------------------------------------------------------------

    def log_constitutional_validation(
        self,
        agent_id: str,
        result: str,
        confidence: float,
        latency_ms: float,
        principles_checked: list[str] | None = None,
        violations: list[dict] | None = None,
    ) -> None:
        """
        Log constitutional validation event.

        Level: INFO
        Required fields: agent_id, result, confidence, latency_ms
        """
        fields = {
            "agent_id": agent_id,
            "result": result,
            "confidence": confidence,
            "latency_ms": latency_ms,
        }

        if principles_checked:
            fields["principles_checked"] = principles_checked

        if violations:
            fields["violations"] = violations

        self._log_event(
            event_type="constitutional_validation",
            level=logging.INFO,
            fields=fields,
            message=f"Constitutional validation for {agent_id}: {result} (confidence={confidence:.2f}, latency={latency_ms:.2f}ms)",
        )

    def log_policy_evaluation(
        self,
        policy_id: str,
        input_hash: str,
        decision: str,
        latency_ms: float | None = None,
    ) -> None:
        """
        Log policy evaluation event.

        Level: INFO
        Required fields: policy_id, input_hash, decision
        """
        fields: JSONDict = {
            "policy_id": policy_id,
            "input_hash": input_hash,
            "decision": decision,
        }

        if latency_ms is not None:
            fields["latency_ms"] = latency_ms

        self._log_event(
            event_type="policy_evaluation",
            level=logging.INFO,
            fields=fields,
            message=f"Policy evaluation {policy_id}: {decision}",
        )

    def log_security_violation(
        self,
        violation_type: str,
        source: str,
        details: JSONDict,
        always_log: bool = True,
    ) -> None:
        """
        Log security violation event.

        Level: ERROR
        Required fields: violation_type, source, details
        always_log: true (per spec)
        """
        fields = {
            "violation_type": violation_type,
            "source": source,
            "details": details,
            "always_log": always_log,
        }

        self._log_event(
            event_type="security_violation",
            level=logging.ERROR,
            fields=fields,
            message=f"SECURITY VIOLATION [{violation_type}] from {source}: {details.get('summary', 'See details')}",
        )

    # -------------------------------------------------------------------------
    # Additional Event Loggers
    # -------------------------------------------------------------------------

    def log_cache_operation(
        self,
        cache_tier: str,
        operation: str,
        hit: bool,
        key_prefix: str | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """Log cache operation event."""
        fields = {
            "cache_tier": cache_tier,
            "operation": operation,
            "hit": hit,
        }

        if key_prefix:
            fields["key_prefix"] = key_prefix
        if latency_ms is not None:
            fields["latency_ms"] = latency_ms

        self._log_event(
            event_type="cache_operation",
            level=logging.DEBUG,
            fields=fields,
        )

    def log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        latency_ms: float,
        user_agent: str | None = None,
    ) -> None:
        """Log HTTP request event."""
        fields = {
            "method": method,
            "path": path,
            "status_code": status_code,
            "latency_ms": latency_ms,
        }

        if user_agent:
            fields["user_agent"] = user_agent

        level = logging.INFO if status_code < 400 else logging.ERROR
        self._log_event(
            event_type="http_request",
            level=level,
            fields=fields,
            message=f"{method} {path} {status_code} ({latency_ms:.2f}ms)",
        )


# =============================================================================
# Logging Configuration
# =============================================================================


def configure_structured_logging(
    service_name: str = "acgs2-enhanced-agent-bus",
    log_level: str | None = None,
    output_stream: IO[str] | None = None,
    redact_pii: bool = True,
) -> logging.Logger:
    """
    Configure structured JSON logging for the application.

    Args:
        service_name: Name of the service for logs
        log_level: Log level (defaults to environment-based)
        output_stream: Output stream (defaults to sys.stdout)
        redact_pii: Whether to redact PII (default True)

    Returns:
        Configured root logger
    """
    if log_level is None:
        log_level = get_log_level()

    if output_stream is None:
        output_stream = sys.stdout

    # Create handler with JSON formatter
    handler = logging.StreamHandler(output_stream)
    handler.setFormatter(
        StructuredJSONFormatter(
            service_name=service_name,
            redact_pii=redact_pii,
        )
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Remove existing handlers and add new one
    root_logger.handlers = []
    root_logger.addHandler(handler)

    # Log configuration
    logger = logging.getLogger(__name__)
    logger.info(
        "Configured structured logging",
        extra={
            "service_name": service_name,
            "log_level": log_level,
            "redact_pii": redact_pii,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        },
    )

    return root_logger


# =============================================================================
# Global Structured Logger Instance
# =============================================================================

_structured_logger: StructuredLogger | None = None


def get_structured_logger() -> StructuredLogger:
    """Get or create the global structured logger instance."""
    global _structured_logger
    if _structured_logger is None:
        _structured_logger = StructuredLogger()
    return _structured_logger


def reset_structured_logger() -> None:
    """Reset the global structured logger (for testing)."""
    global _structured_logger
    _structured_logger = None


# =============================================================================
# Tracing Context Helpers
# =============================================================================


def set_trace_context(trace_id: str, span_id: str | None = None) -> None:
    """set trace context for current async context."""
    trace_id_var.set(trace_id)
    if span_id:
        span_id_var.set(span_id)


def get_trace_context() -> dict[str, str | None]:
    """Get current trace context."""
    return {
        "trace_id": trace_id_var.get(),
        "span_id": span_id_var.get(),
    }


def clear_trace_context() -> None:
    """Clear trace context."""
    trace_id_var.set(None)
    span_id_var.set(None)


# Re-export canonical get_logger so EAB modules import from within the package.
try:
    from enhanced_agent_bus._compat.structured_logging import get_logger
except ImportError:
    import logging

    def get_logger(name: str) -> logging.Logger:
        return logging.getLogger(name)
