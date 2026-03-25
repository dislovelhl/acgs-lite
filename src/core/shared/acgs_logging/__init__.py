"""
ACGS-2 Logging Module
Constitutional Hash: 608508a9bd224290

Centralized logging utilities for the ACGS-2 platform:
- Tenant-scoped audit logging with access controls
- Structured logging for compliance and security
- Audit trail for multi-tenant operations
"""

import contextvars
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timezone

from .agent_workflow_events import (
    AgentWorkflowEvent,
    AgentWorkflowEventType,
    create_agent_workflow_event,
    emit_agent_workflow_event,
    event_to_dict,
    parse_agent_workflow_event_type,
)
from .audit_logger import (
    AUDIT_LOGGER_AVAILABLE,
    AuditAction,
    AuditEntry,
    AuditLogConfig,
    AuditLogStore,
    AuditQueryParams,
    AuditQueryResult,
    AuditSeverity,
    InMemoryAuditStore,
    RedisAuditStore,
    TenantAuditLogger,
    create_tenant_audit_logger,
    get_tenant_audit_logger,
)

# Context variable for correlation ID
_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)


# JSON formatter for structured logging via standard logger
class JSONFormatter(logging.Formatter):
    """JSON log formatter that emits structured JSON with correlation ID support."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string including correlation ID if set."""
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            payload["correlation_id"] = correlation_id
        return json.dumps(payload, default=str)


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name. If None, returns root logger.

    Returns:
        Configured logging.Logger instance
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for the current context."""
    _correlation_id.set(correlation_id)


def get_correlation_id() -> str | None:
    """Get the correlation ID for the current context."""
    return _correlation_id.get()


def clear_correlation_id() -> None:
    """Clear the correlation ID for the current context."""
    _correlation_id.set(None)


class StructuredLogger:
    """Wrapper for structured logging with JSON output."""

    def __init__(self, name: str, service: str, json_format: bool = True):
        self.name = name
        self.service = service
        self.json_format = json_format
        self._logger = logging.getLogger(name)

    def _log(self, level: str, event: str, **kwargs: object) -> None:
        """Log a structured event."""
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": level,
            "service": self.service,
            "event": event,
            **kwargs,
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            record["correlation_id"] = correlation_id

        if self.json_format:
            self._logger.log(getattr(logging, level), json.dumps(record))
        else:
            self._logger.log(getattr(logging, level), str(record))

    def info(self, event: str, **kwargs: object) -> None:
        """Log an INFO-level structured event with optional keyword context."""
        self._log("INFO", event, **kwargs)

    def warning(self, event: str, **kwargs: object) -> None:
        """Log a WARNING-level structured event with optional keyword context."""
        self._log("WARNING", event, **kwargs)

    def error(self, event: str, **kwargs: object) -> None:
        """Log an ERROR-level structured event with optional keyword context."""
        self._log("ERROR", event, **kwargs)

    def debug(self, event: str, **kwargs: object) -> None:
        """Log a DEBUG-level structured event with optional keyword context."""
        self._log("DEBUG", event, **kwargs)


def init_service_logging(
    service_name: str,
    level: str = "INFO",
    json_format: bool = True,
) -> StructuredLogger:
    """
    Initialize structured logging for a service.

    Args:
        service_name: Name of the service for log identification
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        json_format: Whether to output logs in JSON format

    Returns:
        Configured StructuredLogger instance
    """
    logging.basicConfig(level=getattr(logging, level))
    base_logger = logging.getLogger(service_name)
    base_logger.setLevel(getattr(logging, level))
    if json_format:
        for handler in list(base_logger.handlers):
            base_logger.removeHandler(handler)
        handler = logging.StreamHandler()
        # StructuredLogger already emits JSON, so keep formatter minimal.
        handler.setFormatter(logging.Formatter("%(message)s"))
        base_logger.addHandler(handler)
        base_logger.propagate = False
    elif not base_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        base_logger.addHandler(handler)
        base_logger.propagate = False
    return StructuredLogger(service_name, service_name, json_format)


def create_correlation_middleware() -> Callable:
    """
    Create a FastAPI middleware for correlation ID propagation.

    Returns:
        Middleware function for FastAPI
    """

    async def correlation_middleware(request: object, call_next: Callable[..., object]) -> object:
        """Inject and propagate a correlation ID through the request lifecycle."""
        import uuid

        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        set_correlation_id(correlation_id)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            clear_correlation_id()

    return correlation_middleware


__all__ = [
    # Feature flags
    "AUDIT_LOGGER_AVAILABLE",
    "AgentWorkflowEvent",
    # Agent workflow telemetry events
    "AgentWorkflowEventType",
    "AuditAction",
    # Audit entries
    "AuditEntry",
    # Configuration
    "AuditLogConfig",
    # Storage backends
    "AuditLogStore",
    # Query
    "AuditQueryParams",
    "AuditQueryResult",
    "AuditSeverity",
    "InMemoryAuditStore",
    "RedisAuditStore",
    "StructuredLogger",
    # Main logger
    "TenantAuditLogger",
    "clear_correlation_id",
    "create_agent_workflow_event",
    "create_correlation_middleware",
    "create_tenant_audit_logger",
    "emit_agent_workflow_event",
    "event_to_dict",
    "get_correlation_id",
    # Standard logger
    "get_logger",
    "get_tenant_audit_logger",
    # Structured logging
    "init_service_logging",
    "parse_agent_workflow_event_type",
    # Correlation ID
    "set_correlation_id",
]
