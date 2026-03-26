"""
ACGS-2 Tenant-Scoped Audit Logger
Constitutional Hash: 608508a9bd224290

Production-grade audit logging with tenant-scoped access controls supporting:
- Tenant-scoped audit entries with strict isolation
- Multiple storage backends (in-memory, Redis)
- Query API with mandatory tenant scoping
- Cross-tenant access prevention
- Configurable retention and cleanup

Security Features:
- All audit entries tagged with tenant_id
- Query operations enforced to requesting tenant only
- No cross-tenant audit log access possible
- Audit trail for compliance requirements
- Sensitive field redaction

Usage:
    from src.core.shared.acgs_logging.audit_logger import TenantAuditLogger, AuditAction

    # Create tenant-scoped logger
    logger = TenantAuditLogger()

    # Log an action
    await logger.log(
        tenant_id="acme-corp",
        action=AuditAction.CREATE,
        resource_type="policy",
        resource_id="policy-123",
        actor_id="user-456",
        details={"policy_name": "example"}
    )

    # Query logs (scoped to tenant)
    entries = await logger.query(
        requesting_tenant_id="acme-corp",
        query=AuditQueryParams(action=AuditAction.CREATE)
    )
"""

# Constitutional hash for validation
import logging
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import lru_cache

from src.core.shared.constants import CONSTITUTIONAL_HASH
from src.core.shared.errors.exceptions import ACGSBaseError
from src.core.shared.types import JSONDict

logger = logging.getLogger(__name__)
# Redis client - optional dependency
try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    try:
        import aioredis

        REDIS_AVAILABLE = True
    except ImportError:
        aioredis = None
        REDIS_AVAILABLE = False

# Tenant context - optional for validation
try:
    from src.core.shared.security.tenant_context import (
        TenantValidationError,
        validate_tenant_id,
    )

    TENANT_CONTEXT_AVAILABLE = True
except ImportError:
    TENANT_CONTEXT_AVAILABLE = False

    class TenantValidationError(ACGSBaseError):
        """Fallback tenant validation error."""

        http_status_code = 400
        error_code = "TENANT_VALIDATION_ERROR"

    def validate_tenant_id(tenant_id: str) -> bool:
        """Fallback validation - basic checks only."""
        if not tenant_id or len(tenant_id) > 64:
            raise TenantValidationError("Invalid tenant ID")
        return True


# Feature flag
AUDIT_LOGGER_AVAILABLE = True

# Sensitive fields to redact
SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "private_key",
        "credential",
        "auth",
    }
)


class AuditAction(StrEnum):
    """Audit action types for logging."""

    # CRUD operations
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"

    # Authentication/Authorization
    LOGIN = "login"
    LOGOUT = "logout"
    AUTH_FAILURE = "auth_failure"
    ACCESS_DENIED = "access_denied"

    # Policy operations
    POLICY_EVALUATE = "policy_evaluate"
    POLICY_APPROVE = "policy_approve"
    POLICY_REJECT = "policy_reject"

    # Tenant operations
    TENANT_CREATE = "tenant_create"
    TENANT_UPDATE = "tenant_update"
    TENANT_DELETE = "tenant_delete"
    TENANT_QUOTA_UPDATE = "tenant_quota_update"

    # System operations
    CONFIG_CHANGE = "config_change"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    VALIDATION_FAILURE = "validation_failure"

    # Agent operations
    AGENT_REGISTER = "agent_register"
    AGENT_MESSAGE = "agent_message"
    AGENT_ACTION = "agent_action"

    # Generic
    CUSTOM = "custom"


class AuditSeverity(StrEnum):
    """Severity levels for audit entries."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEntry:
    """
    A single audit log entry.

    Attributes:
        id: Unique entry identifier
        tenant_id: Tenant this entry belongs to (immutable)
        timestamp: When the action occurred
        action: Type of action performed
        severity: Entry severity level
        resource_type: Type of resource affected
        resource_id: Identifier of affected resource
        actor_id: Who performed the action
        actor_type: Type of actor (user, service, agent)
        client_ip: IP address of the client
        user_agent: Client user agent string
        request_id: Correlation ID for request tracing
        details: Additional action-specific details
        outcome: Whether action succeeded or failed
        error_message: Error message if action failed
        constitutional_hash: Constitutional compliance marker
    """

    id: str
    tenant_id: str
    timestamp: str
    action: str
    severity: str = AuditSeverity.INFO.value
    resource_type: str | None = None
    resource_id: str | None = None
    actor_id: str | None = None
    actor_type: str = "user"
    client_ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    details: JSONDict = field(default_factory=dict)
    outcome: str = "success"
    error_message: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: JSONDict) -> "AuditEntry":
        """Create from dictionary representation."""
        # Handle enum values
        if "action" in data and isinstance(data["action"], AuditAction):
            data["action"] = data["action"].value
        if "severity" in data and isinstance(data["severity"], AuditSeverity):
            data["severity"] = data["severity"].value
        return cls(**data)


@dataclass
class AuditQueryParams:
    """
    Parameters for querying audit logs.

    All queries are automatically scoped to the requesting tenant.
    Cross-tenant queries are not possible.
    """

    # Filters
    action: AuditAction | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    actor_id: str | None = None
    severity: AuditSeverity | None = None
    outcome: str | None = None

    # Time range
    start_time: datetime | None = None
    end_time: datetime | None = None

    # Pagination
    limit: int = 100
    offset: int = 0

    # Sorting
    order_by: str = "timestamp"
    order_desc: bool = True


@dataclass
class AuditQueryResult:
    """
    Result of an audit log query.

    Includes metadata about the query and scoping.
    """

    entries: list[AuditEntry]
    total_count: int
    tenant_id: str  # The tenant scope applied
    query_params: AuditQueryParams
    has_more: bool = False
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class AuditLogConfig:
    """
    Configuration for the audit logger.

    Attributes:
        redis_url: Redis connection URL for persistent storage
        use_redis: Whether to use Redis backend
        max_entries_per_tenant: Maximum entries to retain per tenant
        retention_days: Days to retain audit entries
        enable_redaction: Whether to redact sensitive fields
        enable_compression: Whether to compress stored entries
        audit_enabled: Master switch for audit logging
        fail_open: Continue operation if audit logging fails
    """

    redis_url: str = "redis://localhost:6379/0"
    use_redis: bool = False
    max_entries_per_tenant: int = 100000
    retention_days: int = 90
    enable_redaction: bool = True
    enable_compression: bool = False
    audit_enabled: bool = True
    fail_open: bool = True
    key_prefix: str = "acgs2:audit"

    @classmethod
    def from_env(cls) -> "AuditLogConfig":
        """Create configuration from environment variables."""
        return cls(
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            use_redis=os.environ.get("AUDIT_USE_REDIS", "false").lower() == "true",
            max_entries_per_tenant=int(os.environ.get("AUDIT_MAX_ENTRIES_PER_TENANT", "100000")),
            retention_days=int(os.environ.get("AUDIT_RETENTION_DAYS", "90")),
            enable_redaction=os.environ.get("AUDIT_ENABLE_REDACTION", "true").lower() == "true",
            enable_compression=os.environ.get("AUDIT_ENABLE_COMPRESSION", "false").lower()
            == "true",
            audit_enabled=os.environ.get("AUDIT_ENABLED", "true").lower() == "true",
            fail_open=os.environ.get("AUDIT_FAIL_OPEN", "true").lower() == "true",
            key_prefix=os.environ.get("AUDIT_KEY_PREFIX", "acgs2:audit"),
        )


class AuditLogStore(ABC):
    """
    Abstract base class for audit log storage backends.

    All implementations must ensure tenant-scoped access.
    """

    @abstractmethod
    async def store(self, entry: AuditEntry) -> bool:
        """Store an audit entry. Returns True on success."""
        pass

    @abstractmethod
    async def query(self, tenant_id: str, params: AuditQueryParams) -> AuditQueryResult:
        """Query audit entries for a specific tenant."""
        pass

    @abstractmethod
    async def count(self, tenant_id: str) -> int:
        """Count total entries for a tenant."""
        pass

    @abstractmethod
    async def cleanup(self, tenant_id: str, before: datetime) -> int:
        """Remove entries older than specified time. Returns count removed."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close any connections."""
        pass


class InMemoryAuditStore(AuditLogStore):
    """
    In-memory audit log store for development and testing.

    Entries are stored per-tenant in separate lists to ensure isolation.
    """

    def __init__(self, max_entries_per_tenant: int = 10000):
        self._entries: dict[str, list[AuditEntry]] = {}
        self._max_entries = max_entries_per_tenant
        self._constitutional_hash = CONSTITUTIONAL_HASH

    async def store(self, entry: AuditEntry) -> bool:
        """Store an audit entry in memory."""
        tenant_id = entry.tenant_id

        if tenant_id not in self._entries:
            self._entries[tenant_id] = []

        self._entries[tenant_id].append(entry)

        # Enforce max entries limit
        if len(self._entries[tenant_id]) > self._max_entries:
            # Remove oldest entries
            self._entries[tenant_id] = self._entries[tenant_id][-self._max_entries :]

        return True

    async def query(self, tenant_id: str, params: AuditQueryParams) -> AuditQueryResult:
        """Query audit entries for a specific tenant only."""
        entries = self._entries.get(tenant_id, [])

        # Apply filters
        filtered = self._apply_filters(entries, params)

        # Sort
        reverse = params.order_desc
        if params.order_by == "timestamp":
            filtered.sort(key=lambda e: e.timestamp, reverse=reverse)
        elif params.order_by == "action":
            filtered.sort(key=lambda e: e.action, reverse=reverse)
        elif params.order_by == "severity":
            filtered.sort(key=lambda e: e.severity, reverse=reverse)

        total_count = len(filtered)

        # Apply pagination
        start = params.offset
        end = start + params.limit
        paginated = filtered[start:end]

        return AuditQueryResult(
            entries=paginated,
            total_count=total_count,
            tenant_id=tenant_id,
            query_params=params,
            has_more=end < total_count,
        )

    def _apply_filters(
        self, entries: list[AuditEntry], params: AuditQueryParams
    ) -> list[AuditEntry]:
        """Apply query filters to entries."""
        result = entries.copy()

        if params.action:
            action_value = (
                params.action.value if isinstance(params.action, AuditAction) else params.action
            )
            result = [e for e in result if e.action == action_value]

        if params.resource_type:
            result = [e for e in result if e.resource_type == params.resource_type]

        if params.resource_id:
            result = [e for e in result if e.resource_id == params.resource_id]

        if params.actor_id:
            result = [e for e in result if e.actor_id == params.actor_id]

        if params.severity:
            severity_value = (
                params.severity.value
                if isinstance(params.severity, AuditSeverity)
                else params.severity
            )
            result = [e for e in result if e.severity == severity_value]

        if params.outcome:
            result = [e for e in result if e.outcome == params.outcome]

        if params.start_time:
            start_iso = params.start_time.isoformat()
            result = [e for e in result if e.timestamp >= start_iso]

        if params.end_time:
            end_iso = params.end_time.isoformat()
            result = [e for e in result if e.timestamp <= end_iso]

        return result

    async def count(self, tenant_id: str) -> int:
        """Count entries for a tenant."""
        return len(self._entries.get(tenant_id, []))

    async def cleanup(self, tenant_id: str, before: datetime) -> int:
        """Remove old entries for a tenant."""
        if tenant_id not in self._entries:
            return 0

        before_iso = before.isoformat()
        original_count = len(self._entries[tenant_id])
        self._entries[tenant_id] = [
            e for e in self._entries[tenant_id] if e.timestamp >= before_iso
        ]
        return original_count - len(self._entries[tenant_id])

    async def close(self) -> None:
        """No-op for in-memory store."""
        pass

    def get_all_tenant_ids(self) -> list[str]:
        """Get all tenant IDs with entries (for testing)."""
        return list(self._entries.keys())


class RedisAuditStore(AuditLogStore):
    """
    Redis-backed audit log store for production use.

    Uses sorted sets for time-based queries and hash storage for entries.
    Entries are stored per-tenant to ensure strict isolation.
    """

    def __init__(
        self,
        redis_url: str,
        key_prefix: str = "acgs2:audit",
        max_entries_per_tenant: int = 100000,
    ):
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._max_entries = max_entries_per_tenant
        self._redis: object | None = None
        self._initialized = False
        self._constitutional_hash = CONSTITUTIONAL_HASH

    async def _ensure_initialized(self) -> bool:
        """Lazily initialize Redis connection."""
        if self._initialized:
            return self._redis is not None

        if not REDIS_AVAILABLE:
            logger.warning("Redis not available for audit store")
            self._initialized = True
            return False

        try:
            self._redis = await aioredis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            self._initialized = True
            logger.info(f"Redis audit store initialized: {self._redis_url}")
            return True
        except (OSError, RuntimeError, TypeError, ValueError) as e:
            logger.warning(f"Failed to connect to Redis for audit store: {e}")
            self._initialized = True
            return False

    def _tenant_key(self, tenant_id: str, suffix: str = "") -> str:
        """Generate tenant-scoped Redis key."""
        base = f"{self._key_prefix}:tenant:{tenant_id}"
        if suffix:
            return f"{base}:{suffix}"
        return base

    async def store(self, entry: AuditEntry) -> bool:
        """Store an audit entry in Redis."""
        if not await self._ensure_initialized():
            return False

        if self._redis is None:
            return False

        try:
            tenant_id = entry.tenant_id
            entry_key = f"{self._tenant_key(tenant_id, 'entries')}:{entry.id}"
            index_key = self._tenant_key(tenant_id, "index")

            # Store entry as hash
            import json

            entry_data = json.dumps(entry.to_dict())

            pipe = self._redis.pipeline()

            # Store entry
            pipe.set(entry_key, entry_data)

            # Add to time-based index (sorted set with timestamp score)
            timestamp = datetime.fromisoformat(entry.timestamp).timestamp()
            pipe.zadd(index_key, {entry.id: timestamp})

            # Enforce max entries limit
            pipe.zcard(index_key)

            results = await pipe.execute()

            # Check if we need to trim
            current_count = results[2]
            if current_count > self._max_entries:
                # Remove oldest entries
                to_remove = current_count - self._max_entries
                oldest = await self._redis.zrange(index_key, 0, to_remove - 1)
                if oldest:
                    pipe2 = self._redis.pipeline()
                    for entry_id in oldest:
                        pipe2.delete(f"{self._tenant_key(tenant_id, 'entries')}:{entry_id}")
                    pipe2.zremrangebyrank(index_key, 0, to_remove - 1)
                    await pipe2.execute()

            return True

        except (OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Failed to store audit entry: {e}")
            return False

    async def query(self, tenant_id: str, params: AuditQueryParams) -> AuditQueryResult:
        """Query audit entries for a specific tenant."""
        if not await self._ensure_initialized() or self._redis is None:
            return AuditQueryResult(
                entries=[],
                total_count=0,
                tenant_id=tenant_id,
                query_params=params,
            )

        try:
            import json

            index_key = self._tenant_key(tenant_id, "index")

            # Determine time range
            min_score = "-inf"
            max_score = "+inf"
            if params.start_time:
                min_score = str(params.start_time.timestamp())
            if params.end_time:
                max_score = str(params.end_time.timestamp())

            # Get entry IDs in time range
            if params.order_desc:
                entry_ids = await self._redis.zrevrangebyscore(index_key, max_score, min_score)
            else:
                entry_ids = await self._redis.zrangebyscore(index_key, min_score, max_score)

            # Fetch entries
            entries = []
            entries_prefix = self._tenant_key(tenant_id, "entries")
            for entry_id in entry_ids:
                entry_data = await self._redis.get(f"{entries_prefix}:{entry_id}")
                if entry_data:
                    try:
                        entry = AuditEntry.from_dict(json.loads(entry_data))
                        entries.append(entry)
                    except (TypeError, ValueError) as e:
                        logger.warning(f"Failed to parse audit entry {entry_id}: {e}")

            # Apply filters (after fetch since Redis can't filter all fields)
            filtered = self._apply_filters(entries, params)
            total_count = len(filtered)

            # Apply pagination
            start = params.offset
            end = start + params.limit
            paginated = filtered[start:end]

            return AuditQueryResult(
                entries=paginated,
                total_count=total_count,
                tenant_id=tenant_id,
                query_params=params,
                has_more=end < total_count,
            )

        except (OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Failed to query audit entries: {e}")
            return AuditQueryResult(
                entries=[],
                total_count=0,
                tenant_id=tenant_id,
                query_params=params,
            )

    def _apply_filters(
        self, entries: list[AuditEntry], params: AuditQueryParams
    ) -> list[AuditEntry]:
        """Apply query filters to entries."""
        result = entries

        if params.action:
            action_value = (
                params.action.value if isinstance(params.action, AuditAction) else params.action
            )
            result = [e for e in result if e.action == action_value]

        if params.resource_type:
            result = [e for e in result if e.resource_type == params.resource_type]

        if params.resource_id:
            result = [e for e in result if e.resource_id == params.resource_id]

        if params.actor_id:
            result = [e for e in result if e.actor_id == params.actor_id]

        if params.severity:
            severity_value = (
                params.severity.value
                if isinstance(params.severity, AuditSeverity)
                else params.severity
            )
            result = [e for e in result if e.severity == severity_value]

        if params.outcome:
            result = [e for e in result if e.outcome == params.outcome]

        return result

    async def count(self, tenant_id: str) -> int:
        """Count entries for a tenant."""
        if not await self._ensure_initialized() or self._redis is None:
            return 0

        try:
            index_key = self._tenant_key(tenant_id, "index")
            return await self._redis.zcard(index_key)
        except (OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Failed to count audit entries: {e}")
            return 0

    async def cleanup(self, tenant_id: str, before: datetime) -> int:
        """Remove entries older than specified time."""
        if not await self._ensure_initialized() or self._redis is None:
            return 0

        try:
            index_key = self._tenant_key(tenant_id, "index")
            before_score = before.timestamp()

            # Get old entry IDs
            old_ids = await self._redis.zrangebyscore(index_key, "-inf", before_score)
            if not old_ids:
                return 0

            # Delete entries and index records
            entries_prefix = self._tenant_key(tenant_id, "entries")
            pipe = self._redis.pipeline()
            for entry_id in old_ids:
                pipe.delete(f"{entries_prefix}:{entry_id}")
            pipe.zremrangebyscore(index_key, "-inf", before_score)
            await pipe.execute()

            return len(old_ids)

        except (OSError, RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Failed to cleanup audit entries: {e}")
            return 0

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None


class TenantAuditLogger:
    """
    Tenant-scoped audit logger with strict access controls.

    All audit entries are tagged with tenant_id and all queries
    are enforced to the requesting tenant's scope only.

    Features:
    - Automatic tenant ID validation
    - Sensitive field redaction
    - Multiple storage backends
    - Query with tenant scoping
    - Cross-tenant access prevention

    Example:
        logger = TenantAuditLogger()

        # Log an action
        await logger.log(
            tenant_id="acme-corp",
            action=AuditAction.CREATE,
            resource_type="policy",
            resource_id="policy-123",
        )

        # Query (automatically scoped to tenant)
        result = await logger.query(
            requesting_tenant_id="acme-corp",
            query=AuditQueryParams(action=AuditAction.CREATE)
        )
    """

    def __init__(
        self,
        config: AuditLogConfig | None = None,
        store: AuditLogStore | None = None,
    ):
        """
        Initialize the tenant audit logger.

        Args:
            config: Audit logger configuration
            store: Optional custom storage backend
        """
        self.config = config or AuditLogConfig.from_env()
        self._constitutional_hash = CONSTITUTIONAL_HASH

        # Initialize storage backend
        if store:
            self._store = store
        elif self.config.use_redis and REDIS_AVAILABLE:
            self._store = RedisAuditStore(
                redis_url=self.config.redis_url,
                key_prefix=self.config.key_prefix,
                max_entries_per_tenant=self.config.max_entries_per_tenant,
            )
        else:
            self._store = InMemoryAuditStore(
                max_entries_per_tenant=self.config.max_entries_per_tenant
            )

        logger.debug(
            f"TenantAuditLogger initialized: "
            f"store={type(self._store).__name__}, "
            f"enabled={self.config.audit_enabled}"
        )

    def _validate_tenant_id(self, tenant_id: str) -> None:
        """Validate tenant ID format and security."""
        try:
            validate_tenant_id(tenant_id)
        except TenantValidationError as e:
            raise ValueError(f"Invalid tenant ID: {e}") from e

    def _generate_entry_id(self) -> str:
        """Generate unique entry ID."""
        return str(uuid.uuid4())

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(UTC).isoformat()

    def _redact_sensitive(self, details: JSONDict) -> JSONDict:
        """Redact sensitive fields from details."""
        if not self.config.enable_redaction:
            return details

        redacted = {}
        for key, value in details.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
                redacted[key] = "[REDACTED]"
            elif isinstance(value, dict):
                redacted[key] = self._redact_sensitive(value)
            else:
                redacted[key] = value

        return redacted

    async def log(
        self,
        tenant_id: str,
        action: AuditAction,
        resource_type: str | None = None,
        resource_id: str | None = None,
        actor_id: str | None = None,
        actor_type: str = "user",
        client_ip: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        details: JSONDict | None = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        outcome: str = "success",
        error_message: str | None = None,
    ) -> str | None:
        """
        Log an audit entry scoped to a tenant.

        Args:
            tenant_id: The tenant this entry belongs to (required)
            action: Type of action being logged
            resource_type: Type of resource affected
            resource_id: ID of affected resource
            actor_id: Who performed the action
            actor_type: Type of actor (user, service, agent)
            client_ip: Client IP address
            user_agent: Client user agent
            request_id: Correlation ID for tracing
            details: Additional action details
            severity: Entry severity level
            outcome: Whether action succeeded or failed
            error_message: Error message if action failed

        Returns:
            Entry ID if successful, None otherwise
        """
        if not self.config.audit_enabled:
            return None

        try:
            # Validate tenant ID
            self._validate_tenant_id(tenant_id)

            # Redact sensitive fields
            safe_details = self._redact_sensitive(details or {})

            # Create entry
            entry = AuditEntry(
                id=self._generate_entry_id(),
                tenant_id=tenant_id,
                timestamp=self._get_timestamp(),
                action=action.value if isinstance(action, AuditAction) else action,
                severity=severity.value if isinstance(severity, AuditSeverity) else severity,
                resource_type=resource_type,
                resource_id=resource_id,
                actor_id=actor_id,
                actor_type=actor_type,
                client_ip=client_ip,
                user_agent=user_agent,
                request_id=request_id,
                details=safe_details,
                outcome=outcome,
                error_message=error_message,
                constitutional_hash=self._constitutional_hash,
            )

            # Store entry
            success = await self._store.store(entry)

            if success:
                logger.debug(
                    f"Audit entry logged: {entry.id} for tenant {tenant_id} action={action}"
                )
                return entry.id
            else:
                logger.warning(f"Failed to store audit entry for tenant {tenant_id}")
                if not self.config.fail_open:
                    raise RuntimeError("Audit logging failed")
                return None

        except ValueError as e:
            logger.error(f"Invalid audit log request: {e}")
            if not self.config.fail_open:
                raise
            return None
        except (OSError, RuntimeError, TypeError) as e:
            logger.error(f"Audit logging failed: {e}")
            if not self.config.fail_open:
                raise
            return None

    async def query(
        self,
        requesting_tenant_id: str,
        query: AuditQueryParams | None = None,
    ) -> AuditQueryResult:
        """
        Query audit entries scoped to the requesting tenant.

        SECURITY: This method ONLY returns entries for the requesting tenant.
        Cross-tenant queries are not possible.

        Args:
            requesting_tenant_id: The tenant making the query (enforced scope)
            query: Query parameters (filters, pagination, sorting)

        Returns:
            AuditQueryResult with entries scoped to the requesting tenant
        """
        # Validate tenant ID
        try:
            self._validate_tenant_id(requesting_tenant_id)
        except ValueError as e:
            logger.warning(f"Invalid tenant ID in query: {e}")
            return AuditQueryResult(
                entries=[],
                total_count=0,
                tenant_id=requesting_tenant_id,
                query_params=query or AuditQueryParams(),
            )

        params = query or AuditQueryParams()

        # CRITICAL: Query is ALWAYS scoped to requesting tenant
        # No cross-tenant access is possible
        return await self._store.query(requesting_tenant_id, params)

    async def get_entry(
        self,
        requesting_tenant_id: str,
        entry_id: str,
    ) -> AuditEntry | None:
        """
        Get a specific audit entry by ID.

        SECURITY: Entry is only returned if it belongs to the requesting tenant.

        Args:
            requesting_tenant_id: The tenant making the request
            entry_id: The entry ID to retrieve

        Returns:
            AuditEntry if found and owned by tenant, None otherwise
        """
        # Validate tenant ID
        try:
            self._validate_tenant_id(requesting_tenant_id)
        except ValueError:
            return None

        # Query with specific entry ID (still scoped to tenant)
        result = await self._store.query(
            requesting_tenant_id,
            AuditQueryParams(limit=1),
        )

        # Find the specific entry
        for entry in result.entries:
            if entry.id == entry_id:
                return entry

        return None

    async def count(self, tenant_id: str) -> int:
        """
        Count audit entries for a tenant.

        Args:
            tenant_id: The tenant to count entries for

        Returns:
            Number of entries for the tenant
        """
        try:
            self._validate_tenant_id(tenant_id)
            return await self._store.count(tenant_id)
        except ValueError:
            return 0

    async def cleanup_old_entries(
        self,
        tenant_id: str,
        retention_days: int | None = None,
    ) -> int:
        """
        Remove old audit entries for a tenant.

        Args:
            tenant_id: The tenant to cleanup entries for
            retention_days: Days to retain (defaults to config)

        Returns:
            Number of entries removed
        """
        try:
            self._validate_tenant_id(tenant_id)
        except ValueError:
            return 0

        days = retention_days or self.config.retention_days
        cutoff = datetime.now(UTC) - timedelta(days=days)
        return await self._store.cleanup(tenant_id, cutoff)

    async def close(self) -> None:
        """Close the audit logger and release resources."""
        await self._store.close()

    def get_store(self) -> AuditLogStore:
        """Get the underlying storage backend (for testing)."""
        return self._store


# Global instances and factory functions


@lru_cache
def get_tenant_audit_logger() -> TenantAuditLogger:
    """
    Get the global tenant audit logger instance.

    Uses lru_cache for consistency with FastAPI dependency patterns.
    """
    return TenantAuditLogger()


def create_tenant_audit_logger(
    config: AuditLogConfig | None = None,
    store: AuditLogStore | None = None,
) -> TenantAuditLogger:
    """
    Factory function to create a configured TenantAuditLogger.

    Args:
        config: Optional custom configuration
        store: Optional custom storage backend

    Returns:
        Configured TenantAuditLogger instance
    """
    return TenantAuditLogger(config=config, store=store)


__all__ = [
    "AUDIT_LOGGER_AVAILABLE",
    # Feature flags
    "CONSTITUTIONAL_HASH",
    "REDIS_AVAILABLE",
    "TENANT_CONTEXT_AVAILABLE",
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
    # Main logger
    "TenantAuditLogger",
    # Exceptions
    "TenantValidationError",
    "create_tenant_audit_logger",
    "get_tenant_audit_logger",
]
