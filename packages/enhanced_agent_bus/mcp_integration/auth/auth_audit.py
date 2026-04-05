"""
Auth Audit Logger for MCP Authentication.

Constitutional Hash: 608508a9bd224290
MACI Role: AUDITOR

Provides comprehensive authentication audit logging:
- Authentication event tracking
- Security incident detection
- Compliance reporting
- Anomaly detection
"""

import asyncio
import json
import secrets
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
_system_random = secrets.SystemRandom()
_AUTH_AUDIT_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class AuthAuditEventType(str, Enum):
    """Type of authentication audit event."""

    # Token events
    TOKEN_ACQUIRED = "token_acquired"
    TOKEN_REFRESHED = "token_refreshed"
    TOKEN_REVOKED = "token_revoked"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_VALIDATION_SUCCESS = "token_validation_success"
    TOKEN_VALIDATION_FAILED = "token_validation_failed"

    # Credential events
    CREDENTIAL_CREATED = "credential_created"
    CREDENTIAL_ACCESSED = "credential_accessed"
    CREDENTIAL_ROTATED = "credential_rotated"
    CREDENTIAL_REVOKED = "credential_revoked"
    CREDENTIAL_DELETED = "credential_deleted"
    CREDENTIAL_INJECTION = "credential_injection"

    # Authentication events
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    AUTH_ATTEMPT = "auth_attempt"

    # Security events
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    INVALID_REQUEST = "invalid_request"
    PERMISSION_DENIED = "permission_denied"

    # OIDC events
    OIDC_DISCOVERY = "oidc_discovery"
    OIDC_LOGIN = "oidc_login"
    OIDC_LOGOUT = "oidc_logout"
    OIDC_CALLBACK = "oidc_callback"

    # System events
    CONFIG_CHANGE = "config_change"
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"


class AuditSeverity(str, Enum):
    """Severity level of audit event."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuthAuditEntry:
    """An authentication audit log entry."""

    entry_id: str
    event_type: AuthAuditEventType
    timestamp: datetime
    severity: AuditSeverity = AuditSeverity.INFO

    # Context
    agent_id: str | None = None
    tool_name: str | None = None
    tenant_id: str | None = None
    session_id: str | None = None
    request_id: str | None = None

    # Details
    success: bool = True
    message: str = ""
    details: JSONDict = field(default_factory=dict)

    # Source
    source_ip: str | None = None
    user_agent: str | None = None
    method: str | None = None
    path: str | None = None

    # Constitutional
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "entry_id": self.entry_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "success": self.success,
            "message": self.message,
            "details": self.details,
            "source_ip": self.source_ip,
            "user_agent": self.user_agent,
            "method": self.method,
            "path": self.path,
            "constitutional_hash": self.constitutional_hash,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class AuthAuditStats:
    """Statistics for auth audit."""

    total_events: int = 0
    events_by_type: dict[str, int] = field(default_factory=dict)
    events_by_severity: dict[str, int] = field(default_factory=dict)
    success_rate: float = 0.0
    failures: int = 0
    warnings: int = 0
    unique_agents: int = 0
    unique_tools: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "total_events": self.total_events,
            "events_by_type": self.events_by_type,
            "events_by_severity": self.events_by_severity,
            "success_rate": self.success_rate,
            "failures": self.failures,
            "warnings": self.warnings,
            "unique_agents": self.unique_agents,
            "unique_tools": self.unique_tools,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class AuditLoggerConfig:
    """Configuration for auth audit logger."""

    # Storage
    storage_path: str = "/var/lib/agent-runtime/auth-audit"
    max_entries_in_memory: int = 10000
    persist_to_disk: bool = True
    rotation_size_mb: int = 100
    retention_days: int = 90

    # Redis for distributed logging
    redis_url: str | None = None
    redis_channel: str = "auth:audit"

    # Alerting
    alert_on_failure: bool = True
    alert_threshold_failures: int = 5  # Failures in window
    alert_window_seconds: int = 60

    # Sampling
    sample_rate: float = 1.0  # 1.0 = 100% of events

    # Rate limiting detection
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 100


class AuthAuditLogger:
    """
    Authentication audit logger.

    Features:
    - Comprehensive event logging
    - Anomaly and pattern detection
    - Alert triggering
    - Compliance reporting

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: AuditLoggerConfig | None = None):
        self.config = config or AuditLoggerConfig()
        self._storage_path = Path(self.config.storage_path)

        # In-memory log
        self._entries: list[AuthAuditEntry] = []
        self._entry_count = 0

        # Tracking for alerting
        self._recent_failures: list[datetime] = []
        self._agent_request_counts: dict[str, list[datetime]] = defaultdict(list)

        # Lock
        self._lock = asyncio.Lock()

        # Redis
        self._redis: object | None = None

        # Current file handle
        self._current_log_file: Path | None = None
        self._current_log_size = 0

        # Alert callback
        self._alert_callback: object | None = None

    async def log_event(
        self,
        event_type: AuthAuditEventType,
        message: str = "",
        severity: AuditSeverity = AuditSeverity.INFO,
        success: bool = True,
        agent_id: str | None = None,
        tool_name: str | None = None,
        tenant_id: str | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
        source_ip: str | None = None,
        user_agent: str | None = None,
        method: str | None = None,
        path: str | None = None,
        details: JSONDict | None = None,
    ) -> AuthAuditEntry:
        """
        Log an authentication audit event.

        Args:
            event_type: Type of event
            message: Event message
            severity: Event severity
            success: Whether operation was successful
            agent_id: Agent ID if applicable
            tool_name: Tool name if applicable
            tenant_id: Tenant ID if applicable
            session_id: Session ID if applicable
            request_id: Request ID if applicable
            source_ip: Source IP address
            user_agent: User agent string
            method: HTTP method
            path: Request path
            details: Additional details

        Returns:
            Created AuthAuditEntry
        """
        entry = AuthAuditEntry(
            entry_id=secrets.token_hex(16),
            event_type=event_type,
            timestamp=datetime.now(UTC),
            severity=severity,
            success=success,
            message=message,
            agent_id=agent_id,
            tool_name=tool_name,
            tenant_id=tenant_id,
            session_id=session_id,
            request_id=request_id,
            source_ip=source_ip,
            user_agent=user_agent,
            method=method,
            path=path,
            details=details or {},
        )

        # Apply sampling
        if _system_random.random() > self.config.sample_rate:
            return entry

        async with self._lock:
            self._entries.append(entry)
            self._entry_count += 1

            # Trim if needed
            if len(self._entries) > self.config.max_entries_in_memory:
                self._entries = self._entries[-self.config.max_entries_in_memory :]

        # Track failures for alerting
        if not success:
            await self._track_failure(entry)

        # Track for rate limiting
        if agent_id:
            await self._track_request(agent_id)

        # Persist to disk
        if self.config.persist_to_disk:
            await self._persist_entry(entry)

        # Publish to Redis
        await self._publish_to_redis(entry)

        # Log
        log_method = logger.info if success else logger.warning
        log_method(
            f"Auth audit: {event_type.value} - {message}"
            f" (agent={agent_id}, tool={tool_name}, success={success})"
        )

        return entry

    async def _track_failure(self, entry: AuthAuditEntry) -> None:
        """Track failure for alerting."""
        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=self.config.alert_window_seconds)

        # Add failure
        self._recent_failures.append(now)

        # Clean old failures
        self._recent_failures = [f for f in self._recent_failures if f > window_start]

        # Check threshold
        if (
            self.config.alert_on_failure
            and len(self._recent_failures) >= self.config.alert_threshold_failures
        ):
            await self._trigger_alert(
                f"Auth failure threshold exceeded: "
                f"{len(self._recent_failures)} failures in "
                f"{self.config.alert_window_seconds}s",
                entry,
            )

    async def _track_request(self, agent_id: str) -> None:
        """Track request for rate limiting detection."""
        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=self.config.rate_limit_window_seconds)

        # Add request
        self._agent_request_counts[agent_id].append(now)

        # Clean old requests
        self._agent_request_counts[agent_id] = [
            r for r in self._agent_request_counts[agent_id] if r > window_start
        ]

        # Check rate limit
        if len(self._agent_request_counts[agent_id]) > self.config.rate_limit_max_requests:
            await self.log_event(
                event_type=AuthAuditEventType.RATE_LIMIT_EXCEEDED,
                message=f"Rate limit exceeded for agent: {agent_id}",
                severity=AuditSeverity.WARNING,
                success=False,
                agent_id=agent_id,
                details={
                    "request_count": len(self._agent_request_counts[agent_id]),
                    "window_seconds": self.config.rate_limit_window_seconds,
                    "limit": self.config.rate_limit_max_requests,
                },
            )

    async def _trigger_alert(
        self,
        message: str,
        entry: AuthAuditEntry | None = None,
    ) -> None:
        """Trigger an alert."""
        logger.error(f"Auth audit ALERT: {message}")

        if self._alert_callback:
            try:
                await self._alert_callback(message, entry)
            except _AUTH_AUDIT_OPERATION_ERRORS as e:
                logger.error(f"Alert callback failed: {e}")

    async def _persist_entry(self, entry: AuthAuditEntry) -> None:
        """Persist entry to disk."""
        self._storage_path.mkdir(parents=True, exist_ok=True)

        # Get or create log file
        if (
            self._current_log_file is None
            or self._current_log_size > self.config.rotation_size_mb * 1024 * 1024
        ):
            # Rotate log file
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            self._current_log_file = self._storage_path / f"auth_audit_{timestamp}.jsonl"
            self._current_log_size = 0

        # Append entry
        try:
            line = entry.to_json() + "\n"
            with open(self._current_log_file, "a") as f:
                f.write(line)
            self._current_log_size += len(line)
        except _AUTH_AUDIT_OPERATION_ERRORS as e:
            logger.error(f"Failed to persist audit entry: {e}")

    async def _publish_to_redis(self, entry: AuthAuditEntry) -> None:
        """Publish entry to Redis channel."""
        if not self.config.redis_url:
            return

        if self._redis is None:
            try:
                import redis.asyncio as redis

                self._redis = redis.from_url(self.config.redis_url)
            except ImportError:
                return

        try:
            await self._redis.publish(
                self.config.redis_channel,
                entry.to_json(),
            )
        except _AUTH_AUDIT_OPERATION_ERRORS as e:
            logger.warning(f"Redis publish failed: {e}")

    def set_alert_callback(
        self,
        callback: object,
    ) -> None:
        """Set callback for alerts."""
        self._alert_callback = callback

    async def get_entries(
        self,
        event_type: AuthAuditEventType | None = None,
        agent_id: str | None = None,
        tool_name: str | None = None,
        success: bool | None = None,
        severity: AuditSeverity | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[AuthAuditEntry]:
        """
        Get audit entries with filters.

        Args:
            event_type: Filter by event type
            agent_id: Filter by agent ID
            tool_name: Filter by tool name
            success: Filter by success
            severity: Filter by severity
            since: Start time
            until: End time
            limit: Maximum entries to return

        Returns:
            List of matching AuthAuditEntry
        """
        result = []

        async with self._lock:
            for entry in reversed(self._entries):
                # Apply filters
                if event_type and entry.event_type != event_type:
                    continue
                if agent_id and entry.agent_id != agent_id:
                    continue
                if tool_name and entry.tool_name != tool_name:
                    continue
                if success is not None and entry.success != success:
                    continue
                if severity and entry.severity != severity:
                    continue
                if since and entry.timestamp < since:
                    continue
                if until and entry.timestamp > until:
                    continue

                result.append(entry)

                if len(result) >= limit:
                    break

        return result

    async def get_stats(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> AuthAuditStats:
        """
        Get audit statistics.

        Args:
            since: Start time for stats
            until: End time for stats

        Returns:
            AuthAuditStats
        """
        since = since or datetime.now(UTC) - timedelta(hours=24)
        until = until or datetime.now(UTC)

        async with self._lock:
            entries = list(self._entries)

        return self._build_stats(entries, since, until)

    def get_stats_snapshot(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> AuthAuditStats:
        """Return a synchronous in-memory stats snapshot for diagnostics."""
        since = since or datetime.now(UTC) - timedelta(hours=24)
        until = until or datetime.now(UTC)
        return self._build_stats(list(self._entries), since, until)

    def _build_stats(
        self,
        entries: list[AuthAuditEntry],
        since: datetime,
        until: datetime,
    ) -> AuthAuditStats:
        events_by_type: dict[str, int] = defaultdict(int)
        events_by_severity: dict[str, int] = defaultdict(int)
        agents: set[str] = set()
        tools: set[str] = set()
        successes = 0
        failures = 0
        total = 0

        for entry in entries:
            if entry.timestamp < since or entry.timestamp > until:
                continue

            total += 1
            events_by_type[entry.event_type.value] += 1
            events_by_severity[entry.severity.value] += 1

            if entry.success:
                successes += 1
            else:
                failures += 1

            if entry.agent_id:
                agents.add(entry.agent_id)
            if entry.tool_name:
                tools.add(entry.tool_name)

        return AuthAuditStats(
            total_events=total,
            events_by_type=dict(events_by_type),
            events_by_severity=dict(events_by_severity),
            success_rate=successes / total if total > 0 else 0.0,
            failures=failures,
            warnings=events_by_severity.get("warning", 0),
            unique_agents=len(agents),
            unique_tools=len(tools),
            period_start=since,
            period_end=until,
        )

    async def cleanup_old_entries(self, retention_days: int | None = None) -> int:
        """
        Clean up old audit entries.

        Args:
            retention_days: Days to retain (uses config if not specified)

        Returns:
            Number of entries removed
        """
        retention = retention_days or self.config.retention_days
        cutoff = datetime.now(UTC) - timedelta(days=retention)

        # Clean memory
        async with self._lock:
            before = len(self._entries)
            self._entries = [e for e in self._entries if e.timestamp > cutoff]
            memory_removed = before - len(self._entries)

        # Clean disk
        disk_removed = 0
        if self._storage_path.exists():
            for log_file in self._storage_path.glob("auth_audit_*.jsonl"):
                try:
                    # Extract date from filename
                    date_str = log_file.stem.split("_")[2]  # auth_audit_YYYYMMDD_HHMMSS
                    file_date = datetime.strptime(date_str, "%Y%m%d")
                    if file_date < cutoff.replace(tzinfo=None):
                        log_file.unlink()
                        disk_removed += 1
                except (ValueError, IndexError):
                    continue

        logger.info(f"Cleaned up {memory_removed} memory entries, {disk_removed} log files")
        return memory_removed + disk_removed

    # Convenience methods for common events

    async def log_token_acquired(
        self,
        agent_id: str,
        token_type: str,
        scopes: list[str] | None = None,
        **kwargs: object,
    ) -> AuthAuditEntry:
        """Log token acquisition."""
        return await self.log_event(
            event_type=AuthAuditEventType.TOKEN_ACQUIRED,
            message=f"Token acquired: {token_type}",
            agent_id=agent_id,
            details={"token_type": token_type, "scopes": scopes or []},
            **kwargs,
        )

    async def log_auth_success(
        self,
        agent_id: str,
        method: str = "unknown",
        **kwargs: object,
    ) -> AuthAuditEntry:
        """Log successful authentication."""
        return await self.log_event(
            event_type=AuthAuditEventType.AUTH_SUCCESS,
            message=f"Authentication successful: {method}",
            agent_id=agent_id,
            success=True,
            details={"auth_method": method},
            **kwargs,
        )

    async def log_auth_failure(
        self,
        agent_id: str | None,
        reason: str,
        **kwargs: object,
    ) -> AuthAuditEntry:
        """Log authentication failure."""
        return await self.log_event(
            event_type=AuthAuditEventType.AUTH_FAILURE,
            message=f"Authentication failed: {reason}",
            severity=AuditSeverity.WARNING,
            agent_id=agent_id,
            success=False,
            details={"reason": reason},
            **kwargs,
        )

    async def log_credential_access(
        self,
        agent_id: str,
        credential_id: str,
        tool_name: str | None = None,
        **kwargs: object,
    ) -> AuthAuditEntry:
        """Log credential access."""
        return await self.log_event(
            event_type=AuthAuditEventType.CREDENTIAL_ACCESSED,
            message=f"Credential accessed: {credential_id}",
            agent_id=agent_id,
            tool_name=tool_name,
            details={"credential_id": credential_id},
            **kwargs,
        )

    async def log_suspicious_activity(
        self,
        description: str,
        agent_id: str | None = None,
        **kwargs: object,
    ) -> AuthAuditEntry:
        """Log suspicious activity."""
        return await self.log_event(
            event_type=AuthAuditEventType.SUSPICIOUS_ACTIVITY,
            message=description,
            severity=AuditSeverity.ERROR,
            agent_id=agent_id,
            success=False,
            **kwargs,
        )
