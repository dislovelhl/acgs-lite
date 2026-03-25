"""
ACGS-2 Standardized Error Logging
Constitutional Hash: 608508a9bd224290

.. deprecated::
    This module (``src.core.shared.errors.logging``) has zero active consumers in
    ``src/`` as of 2026-02-17.  It is retained for reference and future use only.

    For structured logging in new code, prefer the canonical module::

        from src.core.shared.structured_logging import get_logger, configure_logging

    For tenant-scoped audit logging, use::

        from src.core.shared.acgs_logging import TenantAuditLogger, AuditAction

Provides standardized error logging utilities with:
- Structured error context with correlation ID propagation
- Severity levels aligned with escalation framework
- Integration with existing ACGS-2 structured logging
- Constitutional hash inclusion in all error logs
- Support for distributed tracing

Usage:
    from src.core.shared.errors.logging import log_error, ErrorContext

    try:
        result = await risky_operation()
    except ServiceUnavailableError as e:
        log_error(
            e,
            context=ErrorContext(
                operation="fetch_policy",
                service="policy_registry",
                tenant_id="acme-corp",
            ),
        )
        raise

    # Or with context builder
    from src.core.shared.errors.logging import build_error_context

    context = build_error_context(
        operation="validate_message",
        agent_id="agent-001",
        message_id="msg-123",
    )
    log_error(exception, context=context)
"""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "src.core.shared.errors.logging is deprecated and has no active consumers. "
    "Use src.core.shared.acgs_logging_config for structured logging, or "
    "src.core.shared.acgs_logging for tenant-scoped audit logging.",
    DeprecationWarning,
    stacklevel=2,
)

import logging
import traceback
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from uuid import uuid4

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.types import CorrelationID, JSONDict

# Context variables for correlation ID propagation
_correlation_id_var: ContextVar[str] = ContextVar("error_correlation_id", default="")
_tenant_id_var: ContextVar[str] = ContextVar("error_tenant_id", default="")
_request_id_var: ContextVar[str] = ContextVar("error_request_id", default="")

logger = logging.getLogger(__name__)


class ErrorSeverity(IntEnum):
    """
    Error severity levels aligned with failure escalation framework.

    Constitutional Hash: 608508a9bd224290
    """

    DEBUG = 10  # Debug-level errors (not typically logged in production)
    INFO = 20  # Informational errors (expected failures)
    WARNING = 30  # Warning-level errors (may need attention)
    ERROR = 40  # Errors requiring investigation
    CRITICAL = 50  # Critical errors requiring immediate attention
    EMERGENCY = 60  # System-wide impact, immediate human intervention


@dataclass
class ErrorContext:
    """
    Structured context for error logging.

    Constitutional Hash: 608508a9bd224290

    Provides comprehensive context for error events including:
    - Operation and service information
    - Correlation IDs for distributed tracing
    - Tenant and agent information for multi-tenant systems
    - Custom metadata for additional context

    Attributes:
        operation: Name of the operation that failed.
        service: Name of the service where error occurred.
        correlation_id: Request correlation ID for tracing.
        tenant_id: Tenant identifier for multi-tenant systems.
        agent_id: Agent identifier for agent-based operations.
        message_id: Message identifier for message processing.
        request_id: HTTP request identifier.
        user_id: User identifier (if applicable).
        metadata: Additional custom context.
        severity: Error severity level.
        constitutional_hash: Constitutional hash for governance.
    """

    operation: str = ""
    service: str = ""
    correlation_id: CorrelationID = ""
    tenant_id: str = ""
    agent_id: str = ""
    message_id: str = ""
    request_id: str = ""
    user_id: str = ""
    metadata: JSONDict = field(default_factory=dict)
    severity: ErrorSeverity = ErrorSeverity.ERROR
    constitutional_hash: str = CONSTITUTIONAL_HASH
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        """Initialize correlation ID from context var if not provided."""
        if not self.correlation_id:
            ctx_correlation_id = _correlation_id_var.get()
            if ctx_correlation_id:
                self.correlation_id = ctx_correlation_id
            else:
                self.correlation_id = str(uuid4())

        if not self.tenant_id:
            self.tenant_id = _tenant_id_var.get()

        if not self.request_id:
            self.request_id = _request_id_var.get()

    def to_dict(self) -> JSONDict:
        """Convert context to dictionary for logging."""
        result: JSONDict = {
            "constitutional_hash": self.constitutional_hash,
            "timestamp": self.timestamp,
            "severity": self.severity.name,
            "severity_value": self.severity.value,
        }

        # Only include non-empty fields
        if self.operation:
            result["operation"] = self.operation
        if self.service:
            result["service"] = self.service
        if self.correlation_id:
            result["correlation_id"] = self.correlation_id
        if self.tenant_id:
            result["tenant_id"] = self.tenant_id
        if self.agent_id:
            result["agent_id"] = self.agent_id
        if self.message_id:
            result["message_id"] = self.message_id
        if self.request_id:
            result["request_id"] = self.request_id
        if self.user_id:
            result["user_id"] = self.user_id
        if self.metadata:
            result["metadata"] = self.metadata

        return result


def get_correlation_id() -> str:
    """Get current correlation ID from context."""
    correlation_id = _correlation_id_var.get()
    if not correlation_id:
        correlation_id = str(uuid4())
        _correlation_id_var.set(correlation_id)
    return correlation_id


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID in context."""
    _correlation_id_var.set(correlation_id)


def set_tenant_id(tenant_id: str) -> None:
    """Set tenant ID in context."""
    _tenant_id_var.set(tenant_id)


def set_request_id(request_id: str) -> None:
    """Set request ID in context."""
    _request_id_var.set(request_id)


def build_error_context(
    operation: str = "",
    service: str = "",
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    **kwargs: object,
) -> ErrorContext:
    """
    Build an ErrorContext with the provided parameters.

    Constitutional Hash: 608508a9bd224290

    This is a convenience function for creating ErrorContext instances
    with common patterns.

    Args:
        operation: Name of the operation that failed.
        service: Name of the service where error occurred.
        severity: Error severity level.
        **kwargs: Additional context fields (tenant_id, agent_id, etc.).

    Returns:
        ErrorContext instance with provided values.

    Example:
        context = build_error_context(
            operation="validate_message",
            service="agent_bus",
            agent_id="agent-001",
            message_id="msg-123",
            severity=ErrorSeverity.WARNING,
        )
    """
    # Extract known fields
    known_fields = {
        "correlation_id",
        "tenant_id",
        "agent_id",
        "message_id",
        "request_id",
        "user_id",
    }

    context_kwargs: JSONDict = {
        "operation": operation,
        "service": service,
        "severity": severity,
    }

    # Add known fields
    for field_name in known_fields:
        if field_name in kwargs:
            context_kwargs[field_name] = kwargs.pop(field_name)

    # Remaining kwargs go to metadata
    if kwargs:
        context_kwargs["metadata"] = kwargs

    return ErrorContext(**context_kwargs)


def log_error(
    error: BaseException,
    *,
    context: ErrorContext | None = None,
    include_traceback: bool = True,
    extra_data: JSONDict | None = None,
) -> None:
    """
    Log an error with structured context.

    Constitutional Hash: 608508a9bd224290

    Args:
        error: The exception to log.
        context: ErrorContext with additional information.
        include_traceback: Whether to include stack trace.
        extra_data: Additional data to include in log.

    Example:
        try:
            await risky_operation()
        except Exception as e:
            log_error(e, context=ErrorContext(
                operation="risky_operation",
                service="my_service",
            ))
    """
    if context is None:
        context = ErrorContext(severity=ErrorSeverity.ERROR)

    # Build log data
    log_data: JSONDict = {
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context.to_dict(),
    }

    # Add ACGS error details if available
    if hasattr(error, "to_log_dict"):
        log_data["error_details"] = error.to_log_dict()
    elif hasattr(error, "to_dict"):
        log_data["error_details"] = error.to_dict()

    # Add traceback if requested
    if include_traceback:
        log_data["traceback"] = traceback.format_exception(type(error), error, error.__traceback__)

    # Add extra data
    if extra_data:
        log_data["extra"] = extra_data

    # Log at appropriate level
    log_level = _severity_to_log_level(context.severity)
    logger.log(
        log_level,
        f"[{CONSTITUTIONAL_HASH}] Error in {context.operation or 'unknown'}: "
        f"{type(error).__name__}: {error}",
        extra={"structured_data": log_data},
    )


def log_warning(
    message: str,
    *,
    context: ErrorContext | None = None,
    extra_data: JSONDict | None = None,
) -> None:
    """
    Log a warning message with structured context.

    Constitutional Hash: 608508a9bd224290

    Args:
        message: Warning message to log.
        context: ErrorContext with additional information.
        extra_data: Additional data to include in log.
    """
    if context is None:
        context = ErrorContext(severity=ErrorSeverity.WARNING)

    log_data: JSONDict = {
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "message": message,
        "context": context.to_dict(),
    }

    if extra_data:
        log_data["extra"] = extra_data

    logger.warning(
        f"[{CONSTITUTIONAL_HASH}] {message}",
        extra={"structured_data": log_data},
    )


def log_critical(
    error: BaseException,
    *,
    context: ErrorContext | None = None,
    include_traceback: bool = True,
    extra_data: JSONDict | None = None,
    alert: bool = True,
) -> None:
    """
    Log a critical error with structured context.

    Constitutional Hash: 608508a9bd224290

    Critical errors may trigger alerts and escalation procedures.

    Args:
        error: The exception to log.
        context: ErrorContext with additional information.
        include_traceback: Whether to include stack trace.
        extra_data: Additional data to include in log.
        alert: Whether this should trigger alerting systems.
    """
    if context is None:
        context = ErrorContext(severity=ErrorSeverity.CRITICAL)
    else:
        # Ensure severity is at least CRITICAL
        if context.severity < ErrorSeverity.CRITICAL:
            context.severity = ErrorSeverity.CRITICAL

    log_data: JSONDict = {
        "constitutional_hash": CONSTITUTIONAL_HASH,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context.to_dict(),
        "alert": alert,
    }

    if hasattr(error, "to_log_dict"):
        log_data["error_details"] = error.to_log_dict()
    elif hasattr(error, "to_dict"):
        log_data["error_details"] = error.to_dict()

    if include_traceback:
        log_data["traceback"] = traceback.format_exception(type(error), error, error.__traceback__)

    if extra_data:
        log_data["extra"] = extra_data

    logger.critical(
        f"[{CONSTITUTIONAL_HASH}] CRITICAL: {context.operation or 'unknown'}: "
        f"{type(error).__name__}: {error}",
        extra={"structured_data": log_data},
    )


def _severity_to_log_level(severity: ErrorSeverity) -> int:
    """Map ErrorSeverity to logging level."""
    mapping = {
        ErrorSeverity.DEBUG: logging.DEBUG,
        ErrorSeverity.INFO: logging.INFO,
        ErrorSeverity.WARNING: logging.WARNING,
        ErrorSeverity.ERROR: logging.ERROR,
        ErrorSeverity.CRITICAL: logging.CRITICAL,
        ErrorSeverity.EMERGENCY: logging.CRITICAL,  # Map EMERGENCY to CRITICAL
    }
    return mapping.get(severity, logging.ERROR)


__all__ = [
    "ErrorContext",
    "ErrorSeverity",
    "build_error_context",
    "get_correlation_id",
    "log_critical",
    "log_error",
    "log_warning",
    "set_correlation_id",
    "set_request_id",
    "set_tenant_id",
]
