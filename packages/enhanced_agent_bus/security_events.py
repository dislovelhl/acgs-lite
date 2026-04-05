"""
Security Event Logging Stream for ACGS-2.

Constitutional Hash: 608508a9bd224290

This module provides a unified security event logging interface for the Enhanced Agent Bus,
enabling structured JSON logging suitable for SIEM integration.

Features:
- MACI permission violation logging
- Constitutional hash mismatch detection
- Cross-tenant access attempt tracking
- Rate limit exhaustion logging
- Policy version conflict detection
- Authentication failure logging
- Authorization denial tracking
- Non-blocking async logging
- Structured JSON output for SIEM integration
"""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

# Constitutional hash - all events must include this
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import (
        CorrelationID,
        JSONDict,
        TenantID,
    )
except ImportError:
    CorrelationID = object  # type: ignore[misc,assignment]
    JSONDict = dict  # type: ignore[misc,assignment]
    TenantID = object  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_SECURITY_EVENT_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class SecurityEventType(Enum):
    """Types of security events for logging and alerting."""

    # MACI-related events
    MACI_PERMISSION_VIOLATION = "maci_permission_violation"

    # Constitutional events
    CONSTITUTIONAL_HASH_MISMATCH = "constitutional_hash_mismatch"

    # Tenant isolation events
    CROSS_TENANT_ACCESS_ATTEMPT = "cross_tenant_access_attempt"

    # Rate limiting events
    RATE_LIMIT_EXHAUSTION = "rate_limit_exhaustion"

    # Policy events
    POLICY_VERSION_CONFLICT = "policy_version_conflict"

    # Authentication events
    AUTHENTICATION_FAILURE = "authentication_failure"

    # Authorization events
    AUTHORIZATION_DENIAL = "authorization_denial"


class SecuritySeverity(Enum):
    """Severity levels for security events."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class SecurityEventData:
    """
    Base security event structure with required fields.

    All security events must include:
    - timestamp (ISO 8601)
    - event_type (enum)
    - severity (INFO, WARNING, ERROR, CRITICAL)
    - constitutional_hash
    - correlation_id
    - tenant_id
    """

    event_type: SecurityEventType
    severity: SecuritySeverity
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: TenantID | None = None
    metadata: JSONDict = field(default_factory=dict)

    def to_json(self) -> str:
        """Convert event to structured JSON for SIEM integration."""
        return json.dumps(self.to_dict(), default=str)

    def to_dict(self) -> JSONDict:
        """Convert event to dictionary format."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "constitutional_hash": self.constitutional_hash,
            "correlation_id": self.correlation_id,
            "tenant_id": self.tenant_id,
            "metadata": self.metadata,
        }


@dataclass
class MACIViolationEvent(SecurityEventData):
    """MACI permission violation event details."""

    agent_id: str | None = None
    attempted_action: str | None = None
    required_role: str | None = None
    actual_role: str | None = None

    def __post_init__(self) -> None:
        self.event_type = SecurityEventType.MACI_PERMISSION_VIOLATION
        if not self.message:
            self.message = (
                f"MACI permission violation: agent={self.agent_id}, "
                f"action={self.attempted_action}, required_role={self.required_role}, "
                f"actual_role={self.actual_role}"
            )

    def to_dict(self) -> JSONDict:
        """Override to include MACI-specific fields."""
        base = super().to_dict()
        base["maci_details"] = {
            "agent_id": self.agent_id,
            "attempted_action": self.attempted_action,
            "required_role": self.required_role,
            "actual_role": self.actual_role,
        }
        return base


@dataclass
class ConstitutionalHashMismatchEvent(SecurityEventData):
    """Constitutional hash mismatch event details."""

    expected_hash: str | None = None
    received_hash: str | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        self.event_type = SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH
        self.severity = SecuritySeverity.CRITICAL
        if not self.message:
            self.message = (
                f"Constitutional hash mismatch: expected={self.expected_hash}, "
                f"received={self.received_hash}, source={self.source}"
            )

    def to_dict(self) -> JSONDict:
        """Override to include hash mismatch details."""
        base = super().to_dict()
        base["hash_details"] = {
            "expected_hash": self.expected_hash,
            "received_hash": self.received_hash,
            "source": self.source,
        }
        return base


@dataclass
class CrossTenantAccessEvent(SecurityEventData):
    """Cross-tenant access attempt event details."""

    source_tenant: TenantID | None = None
    target_tenant: TenantID | None = None
    resource_type: str | None = None

    def __post_init__(self) -> None:
        self.event_type = SecurityEventType.CROSS_TENANT_ACCESS_ATTEMPT
        self.severity = SecuritySeverity.ERROR
        if not self.message:
            self.message = (
                f"Cross-tenant access attempt: source_tenant={self.source_tenant}, "
                f"target_tenant={self.target_tenant}, resource_type={self.resource_type}"
            )

    def to_dict(self) -> JSONDict:
        """Override to include cross-tenant details."""
        base = super().to_dict()
        base["tenant_details"] = {
            "source_tenant": self.source_tenant,
            "target_tenant": self.target_tenant,
            "resource_type": self.resource_type,
        }
        return base


@dataclass
class RateLimitExhaustionEvent(SecurityEventData):
    """Rate limit exhaustion event details."""

    client_id: str | None = None
    endpoint: str | None = None
    limit: int | None = None
    current_count: int | None = None

    def __post_init__(self) -> None:
        self.event_type = SecurityEventType.RATE_LIMIT_EXHAUSTION
        if not self.message:
            self.message = (
                f"Rate limit exhausted: client_id={self.client_id}, "
                f"endpoint={self.endpoint}, limit={self.limit}, current={self.current_count}"
            )

    def to_dict(self) -> JSONDict:
        """Override to include rate limit details."""
        base = super().to_dict()
        base["rate_limit_details"] = {
            "client_id": self.client_id,
            "endpoint": self.endpoint,
            "limit": self.limit,
            "current_count": self.current_count,
        }
        return base


@dataclass
class PolicyVersionConflictEvent(SecurityEventData):
    """Policy version conflict event details."""

    policy_id: str | None = None
    expected_version: str | None = None
    actual_version: str | None = None

    def __post_init__(self) -> None:
        self.event_type = SecurityEventType.POLICY_VERSION_CONFLICT
        if not self.message:
            self.message = (
                f"Policy version conflict: policy_id={self.policy_id}, "
                f"expected={self.expected_version}, actual={self.actual_version}"
            )

    def to_dict(self) -> JSONDict:
        """Override to include policy conflict details."""
        base = super().to_dict()
        base["policy_details"] = {
            "policy_id": self.policy_id,
            "expected_version": self.expected_version,
            "actual_version": self.actual_version,
        }
        return base


@dataclass
class AuthenticationFailureEvent(SecurityEventData):
    """Authentication failure event details."""

    user_id: str | None = None
    failure_reason: str | None = None
    ip_address: str | None = None

    def __post_init__(self) -> None:
        self.event_type = SecurityEventType.AUTHENTICATION_FAILURE
        self.severity = SecuritySeverity.WARNING
        if not self.message:
            self.message = (
                f"Authentication failure: user_id={self.user_id}, "
                f"reason={self.failure_reason}, ip={self.ip_address}"
            )

    def to_dict(self) -> JSONDict:
        """Override to include authentication details."""
        base = super().to_dict()
        base["auth_details"] = {
            "user_id": self.user_id,
            "failure_reason": self.failure_reason,
            "ip_address": self.ip_address,
        }
        return base


@dataclass
class AuthorizationDenialEvent(SecurityEventData):
    """Authorization denial event details."""

    user_id: str | None = None
    resource: str | None = None
    action: str | None = None
    denial_reason: str | None = None

    def __post_init__(self) -> None:
        self.event_type = SecurityEventType.AUTHORIZATION_DENIAL
        if not self.message:
            self.message = (
                f"Authorization denied: user_id={self.user_id}, "
                f"resource={self.resource}, action={self.action}, reason={self.denial_reason}"
            )

    def to_dict(self) -> JSONDict:
        """Override to include authorization details."""
        base = super().to_dict()
        base["authz_details"] = {
            "user_id": self.user_id,
            "resource": self.resource,
            "action": self.action,
            "denial_reason": self.denial_reason,
        }
        return base


class SecurityEventLogger:
    """
    Security event logger with async, non-blocking logging capabilities.

    Provides structured JSON logging suitable for SIEM integration with
    fire-and-forget async methods for minimal latency impact.

    Usage:
        logger = SecurityEventLogger()
        await logger.start()

        # Log MACI violation
        await logger.log_maci_violation(
            agent_id="agent-001",
            attempted_action="validate",
            required_role="judicial",
            actual_role="executive",
            tenant_id="tenant-123",
        )

        await logger.stop()

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        max_queue_size: int = 10000,
        flush_interval_seconds: float = 1.0,
        event_handler: Callable[[SecurityEventData], None] | None = None,
        drop_on_overflow: bool = True,
    ):
        """
        Initialize the security event logger.

        Args:
            max_queue_size: Maximum number of events to queue before dropping/blocking
            flush_interval_seconds: How often to flush events to handlers
            event_handler: Optional custom handler for events (receives SecurityEventData)
            drop_on_overflow: If True, drop events when queue is full; if False, block
        """
        self._queue: asyncio.Queue[SecurityEventData] = asyncio.Queue(maxsize=max_queue_size)
        self._flush_interval = flush_interval_seconds
        self._event_handler = event_handler
        self._drop_on_overflow = drop_on_overflow
        self._running = False
        self._flush_task: asyncio.Task | None = None
        self._events: list[SecurityEventData] = []
        self._metrics = {
            "events_logged": 0,
            "events_dropped": 0,
            "events_processed": 0,
            "flush_count": 0,
        }
        self.constitutional_hash = CONSTITUTIONAL_HASH

    async def start(self) -> None:
        """Start the background event processing loop."""
        if self._running:
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info(f"SecurityEventLogger started (constitutional_hash={self.constitutional_hash})")

    async def stop(self) -> None:
        """Stop the event processing loop and flush remaining events."""
        if not self._running:
            return

        self._running = False

        # Flush remaining events
        await self._flush_events()

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        logger.info("SecurityEventLogger stopped")

    async def _flush_loop(self) -> None:
        """Background loop for processing and flushing events."""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush_events()
            except asyncio.CancelledError:
                break
            except _SECURITY_EVENT_OPERATION_ERRORS as e:
                logger.error(f"Error in SecurityEventLogger flush loop: {e}")

    async def _flush_events(self) -> None:
        """Flush queued events to handlers."""
        events_to_process: list[SecurityEventData] = []

        # Drain queue
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                events_to_process.append(event)
            except asyncio.QueueEmpty:
                break

        if not events_to_process:
            return

        # Process events
        for event in events_to_process:
            try:
                # Log as structured JSON
                logger.info(f"SECURITY_EVENT: {event.to_json()}")

                # Call custom handler if provided
                if self._event_handler:
                    if inspect.iscoroutinefunction(self._event_handler):
                        await self._event_handler(event)  # type: ignore[attr-defined]
                    else:
                        self._event_handler(event)

                self._metrics["events_processed"] += 1
                self._events.append(event)

            except _SECURITY_EVENT_OPERATION_ERRORS as e:
                logger.error(f"Error processing security event: {e}")

        self._metrics["flush_count"] += 1

    async def _enqueue_event(self, event: SecurityEventData) -> None:
        """Enqueue an event for async processing (fire-and-forget)."""
        try:
            if self._drop_on_overflow:
                try:
                    self._queue.put_nowait(event)
                    self._metrics["events_logged"] += 1
                except asyncio.QueueFull:
                    self._metrics["events_dropped"] += 1
                    logger.warning("Security event queue full, dropping event")
            else:
                await self._queue.put(event)
                self._metrics["events_logged"] += 1
        except _SECURITY_EVENT_OPERATION_ERRORS as e:
            logger.error(f"Failed to enqueue security event: {e}")

    # --- Async logging methods (fire-and-forget) ---

    async def log_maci_violation(
        self,
        agent_id: str,
        attempted_action: str,
        required_role: str,
        actual_role: str,
        tenant_id: TenantID | None = None,
        correlation_id: CorrelationID | None = None,
        severity: SecuritySeverity = SecuritySeverity.ERROR,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Log a MACI permission violation event.

        Args:
            agent_id: ID of the agent that violated permissions
            attempted_action: The action that was attempted
            required_role: The role required for the action
            actual_role: The agent's actual role
            tenant_id: Optional tenant identifier
            correlation_id: Optional correlation ID for request tracing
            severity: Event severity level
            metadata: Additional metadata
        """
        event = MACIViolationEvent(
            event_type=SecurityEventType.MACI_PERMISSION_VIOLATION,
            severity=severity,
            message="",
            tenant_id=tenant_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            metadata=metadata or {},
            agent_id=agent_id,
            attempted_action=attempted_action,
            required_role=required_role,
            actual_role=actual_role,
        )
        await self._enqueue_event(event)

    async def log_constitutional_hash_mismatch(
        self,
        expected_hash: str,
        received_hash: str,
        source: str,
        tenant_id: TenantID | None = None,
        correlation_id: CorrelationID | None = None,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Log a constitutional hash mismatch event.

        Args:
            expected_hash: The expected constitutional hash
            received_hash: The hash that was actually received
            source: The source/origin of the mismatched hash
            tenant_id: Optional tenant identifier
            correlation_id: Optional correlation ID for request tracing
            metadata: Additional metadata
        """
        event = ConstitutionalHashMismatchEvent(
            event_type=SecurityEventType.CONSTITUTIONAL_HASH_MISMATCH,
            severity=SecuritySeverity.CRITICAL,
            message="",
            tenant_id=tenant_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            metadata=metadata or {},
            expected_hash=expected_hash,
            received_hash=received_hash,
            source=source,
        )
        await self._enqueue_event(event)

    async def log_cross_tenant_access(
        self,
        source_tenant: TenantID,
        target_tenant: TenantID,
        resource_type: str,
        tenant_id: TenantID | None = None,
        correlation_id: CorrelationID | None = None,
        severity: SecuritySeverity = SecuritySeverity.ERROR,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Log a cross-tenant access attempt event.

        Args:
            source_tenant: The tenant making the access attempt
            target_tenant: The tenant being accessed
            resource_type: Type of resource being accessed
            tenant_id: Optional tenant identifier (usually source_tenant)
            correlation_id: Optional correlation ID for request tracing
            severity: Event severity level
            metadata: Additional metadata
        """
        event = CrossTenantAccessEvent(
            event_type=SecurityEventType.CROSS_TENANT_ACCESS_ATTEMPT,
            severity=severity,
            message="",
            tenant_id=tenant_id or source_tenant,
            correlation_id=correlation_id or str(uuid.uuid4()),
            metadata=metadata or {},
            source_tenant=source_tenant,
            target_tenant=target_tenant,
            resource_type=resource_type,
        )
        await self._enqueue_event(event)

    async def log_rate_limit_exhaustion(
        self,
        client_id: str,
        endpoint: str,
        limit: int,
        current_count: int,
        tenant_id: TenantID | None = None,
        correlation_id: CorrelationID | None = None,
        severity: SecuritySeverity = SecuritySeverity.WARNING,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Log a rate limit exhaustion event.

        Args:
            client_id: ID of the client that exhausted the rate limit
            endpoint: The endpoint that was rate limited
            limit: The rate limit threshold
            current_count: Current request count
            tenant_id: Optional tenant identifier
            correlation_id: Optional correlation ID for request tracing
            severity: Event severity level
            metadata: Additional metadata
        """
        event = RateLimitExhaustionEvent(
            event_type=SecurityEventType.RATE_LIMIT_EXHAUSTION,
            severity=severity,
            message="",
            tenant_id=tenant_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            metadata=metadata or {},
            client_id=client_id,
            endpoint=endpoint,
            limit=limit,
            current_count=current_count,
        )
        await self._enqueue_event(event)

    async def log_policy_version_conflict(
        self,
        policy_id: str,
        expected_version: str,
        actual_version: str,
        tenant_id: TenantID | None = None,
        correlation_id: CorrelationID | None = None,
        severity: SecuritySeverity = SecuritySeverity.WARNING,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Log a policy version conflict event.

        Args:
            policy_id: ID of the policy with version conflict
            expected_version: The expected policy version
            actual_version: The actual policy version
            tenant_id: Optional tenant identifier
            correlation_id: Optional correlation ID for request tracing
            severity: Event severity level
            metadata: Additional metadata
        """
        event = PolicyVersionConflictEvent(
            event_type=SecurityEventType.POLICY_VERSION_CONFLICT,
            severity=severity,
            message="",
            tenant_id=tenant_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            metadata=metadata or {},
            policy_id=policy_id,
            expected_version=expected_version,
            actual_version=actual_version,
        )
        await self._enqueue_event(event)

    async def log_authentication_failure(
        self,
        user_id: str,
        failure_reason: str,
        ip_address: str,
        tenant_id: TenantID | None = None,
        correlation_id: CorrelationID | None = None,
        severity: SecuritySeverity = SecuritySeverity.WARNING,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Log an authentication failure event.

        Args:
            user_id: ID of the user who failed authentication
            failure_reason: Reason for the authentication failure
            ip_address: IP address of the failed authentication attempt
            tenant_id: Optional tenant identifier
            correlation_id: Optional correlation ID for request tracing
            severity: Event severity level
            metadata: Additional metadata
        """
        event = AuthenticationFailureEvent(
            event_type=SecurityEventType.AUTHENTICATION_FAILURE,
            severity=severity,
            message="",
            tenant_id=tenant_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            metadata=metadata or {},
            user_id=user_id,
            failure_reason=failure_reason,
            ip_address=ip_address,
        )
        await self._enqueue_event(event)

    async def log_authorization_denial(
        self,
        user_id: str,
        resource: str,
        action: str,
        denial_reason: str,
        tenant_id: TenantID | None = None,
        correlation_id: CorrelationID | None = None,
        severity: SecuritySeverity = SecuritySeverity.WARNING,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Log an authorization denial event.

        Args:
            user_id: ID of the user who was denied authorization
            resource: The resource being accessed
            action: The action being attempted
            denial_reason: Reason for the authorization denial
            tenant_id: Optional tenant identifier
            correlation_id: Optional correlation ID for request tracing
            severity: Event severity level
            metadata: Additional metadata
        """
        event = AuthorizationDenialEvent(
            event_type=SecurityEventType.AUTHORIZATION_DENIAL,
            severity=severity,
            message="",
            tenant_id=tenant_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            metadata=metadata or {},
            user_id=user_id,
            resource=resource,
            action=action,
            denial_reason=denial_reason,
        )
        await self._enqueue_event(event)

    async def log_generic_event(
        self,
        event_type: SecurityEventType,
        severity: SecuritySeverity,
        message: str,
        tenant_id: TenantID | None = None,
        correlation_id: CorrelationID | None = None,
        metadata: JSONDict | None = None,
    ) -> None:
        """
        Log a generic security event.

        Args:
            event_type: Type of the security event
            severity: Event severity level
            message: Event message
            tenant_id: Optional tenant identifier
            correlation_id: Optional correlation ID for request tracing
            metadata: Additional metadata
        """
        event = SecurityEventData(
            event_type=event_type,
            severity=severity,
            message=message,
            tenant_id=tenant_id,
            correlation_id=correlation_id or str(uuid.uuid4()),
            metadata=metadata or {},
        )
        await self._enqueue_event(event)

    def get_metrics(self) -> JSONDict:
        """Get logger metrics."""
        return {
            **self._metrics,
            "queue_size": self._queue.qsize(),
            "running": self._running,
            "constitutional_hash": self.constitutional_hash,
        }

    def get_recent_events(self, limit: int = 100) -> list[JSONDict]:
        """
        Get recent events for debugging/monitoring.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of event dictionaries
        """
        return [e.to_dict() for e in self._events[-limit:]]


# --- Global singleton instance ---

_security_event_logger: SecurityEventLogger | None = None


def get_security_event_logger() -> SecurityEventLogger | None:
    """Get the global SecurityEventLogger instance."""
    return _security_event_logger


async def initialize_security_event_logger(
    max_queue_size: int = 10000,
    flush_interval_seconds: float = 1.0,
    event_handler: Callable[[SecurityEventData], None] | None = None,
) -> SecurityEventLogger:
    """
    Initialize and start the global SecurityEventLogger.

    Args:
        max_queue_size: Maximum event queue size
        flush_interval_seconds: Flush interval in seconds
        event_handler: Optional custom event handler

    Returns:
        The initialized SecurityEventLogger instance
    """
    global _security_event_logger
    if _security_event_logger is None:
        _security_event_logger = SecurityEventLogger(
            max_queue_size=max_queue_size,
            flush_interval_seconds=flush_interval_seconds,
            event_handler=event_handler,
        )
        await _security_event_logger.start()
    return _security_event_logger


async def close_security_event_logger() -> None:
    """Stop and close the global SecurityEventLogger."""
    global _security_event_logger
    if _security_event_logger:
        await _security_event_logger.stop()
        _security_event_logger = None


__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "AuthenticationFailureEvent",
    "AuthorizationDenialEvent",
    "ConstitutionalHashMismatchEvent",
    "CrossTenantAccessEvent",
    "MACIViolationEvent",
    "PolicyVersionConflictEvent",
    "RateLimitExhaustionEvent",
    # Event Data Classes
    "SecurityEventData",
    # Logger
    "SecurityEventLogger",
    # Enums
    "SecurityEventType",
    "SecuritySeverity",
    "close_security_event_logger",
    # Global functions
    "get_security_event_logger",
    "initialize_security_event_logger",
]
