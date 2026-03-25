"""
Session Governance SDK
Constitutional Hash: 608508a9bd224290

Phase 10 Task 13: Session Governance SDK

Provides:
- Session lifecycle management (create, validate, extend, revoke)
- Session governance policies (max duration, idle timeout, concurrent sessions)
- Session monitoring and analytics
- Cross-tenant session isolation
- Token management with refresh
- SDK client for session governance API
"""

import asyncio
import os
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from typing import Any

import jwt

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from src.core.shared.errors.exceptions import ACGSBaseError

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

# JWT configuration -- override via environment variables
_ALLOWED_JWT_ALGORITHMS = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "EdDSA"})
SESSION_JWT_ALGORITHM = os.environ.get("SESSION_JWT_ALGORITHM", "RS256")
if SESSION_JWT_ALGORITHM not in _ALLOWED_JWT_ALGORITHMS:
    raise ValueError(
        f"Unsupported JWT_ALGORITHM={SESSION_JWT_ALGORITHM!r}. "
        f"Allowed: {sorted(_ALLOWED_JWT_ALGORITHMS)}"
    )
SESSION_JWT_ISSUER = os.environ.get("SESSION_JWT_ISSUER", "acgs2-session-governance")
SESSION_JWT_AUDIENCE = os.environ.get("SESSION_JWT_AUDIENCE", "acgs2-services")
# Maximum cumulative session duration across all extensions (default: 24 h)
SESSION_MAX_TOTAL_DURATION_MINUTES = int(
    os.environ.get("SESSION_MAX_TOTAL_DURATION_MINUTES", "1440")
)


def _uses_asymmetric_jwt_algorithm(algorithm: str) -> bool:
    """Return True when the JWT algorithm requires an asymmetric key pair."""
    return algorithm.startswith(("RS", "ES")) or algorithm == "EdDSA"


# ============================================================================
# Exceptions
# ============================================================================


class SessionGovernanceError(ACGSBaseError):
    """Base exception for session governance errors.

    Inherits from ACGSBaseError to gain constitutional hash tracking,
    correlation IDs, and structured error logging.
    """

    http_status_code = 500
    error_code = "SESSION_GOVERNANCE_ERROR"


class SessionNotFoundError(SessionGovernanceError):
    """Session not found."""

    pass


class SessionExpiredError(SessionGovernanceError):
    """Session has expired."""

    pass


class TokenValidationError(SessionGovernanceError):
    """Token validation failed."""

    pass


# ============================================================================
# Enums
# ============================================================================


class SessionState(Enum):
    """Session state."""

    PENDING = "pending"
    ACTIVE = "active"
    IDLE = "idle"
    EXPIRED = "expired"
    REVOKED = "revoked"


class SessionEventType(Enum):
    """Session event type."""

    CREATED = "created"
    VALIDATED = "validated"
    EXTENDED = "extended"
    ACTIVITY = "activity"
    IDLE = "idle"
    EXPIRED = "expired"
    REVOKED = "revoked"


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class SessionConfig:
    """Session configuration."""

    tenant_id: str
    user_id: str
    max_duration_minutes: int = 60
    idle_timeout_minutes: int = 15
    refresh_threshold_minutes: int = 5
    metadata: dict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class Session:
    """Session data."""

    session_id: str
    tenant_id: str
    user_id: str
    state: SessionState
    created_at: datetime
    expires_at: datetime
    last_activity: datetime
    max_duration_minutes: int = 60
    extension_count: int = 0
    revocation_reason: str | None = None
    metadata: dict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class SessionValidationResult:
    """Session validation result."""

    is_valid: bool
    session_id: str | None = None
    state: SessionState | None = None
    tenant_id: str | None = None
    user_id: str | None = None
    reason: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class SessionGovernancePolicy:
    """Session governance policy."""

    tenant_id: str
    max_session_duration_minutes: int = 480
    idle_timeout_minutes: int = 30
    max_concurrent_sessions: int = 3
    require_mfa: bool = False
    allowed_ip_ranges: list = field(default_factory=list)
    session_refresh_enabled: bool = True
    enforce_concurrent_limit: bool = True
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def is_valid(self) -> bool:
        """Check if policy is valid."""
        return (
            self.max_session_duration_minutes > 0
            and self.idle_timeout_minutes >= 0
            and self.max_concurrent_sessions > 0
        )


@dataclass
class ConcurrencyCheckResult:
    """Result of concurrency check."""

    allowed: bool
    current_count: int
    max_allowed: int = 0
    sessions_to_evict: list = field(default_factory=list)
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ConcurrencyPolicy:
    """Concurrency policy for sessions."""

    tenant_id: str
    max_sessions_per_user: int = 3
    enforcement_mode: str = "strict"  # strict, soft, warn
    eviction_strategy: str = "oldest_first"  # oldest_first, lru, none
    constitutional_hash: str = CONSTITUTIONAL_HASH

    async def check_concurrency(
        self, user_id: str, session_store: "TenantSessionStore"
    ) -> ConcurrencyCheckResult:
        """Check if user can create new session."""
        sessions = await session_store.list_user_sessions(user_id)
        current_count = len(sessions)

        return ConcurrencyCheckResult(
            allowed=current_count < self.max_sessions_per_user,
            current_count=current_count,
            max_allowed=self.max_sessions_per_user,
            constitutional_hash=self.constitutional_hash,
        )

    async def evict_session(
        self, user_id: str, session_store: "TenantSessionStore"
    ) -> "StoredSession":
        """Evict a session based on strategy."""
        sessions = await session_store.list_user_sessions(user_id)
        if not sessions:
            raise SessionGovernanceError("No sessions to evict")

        if self.eviction_strategy == "oldest_first":
            # Sort by created_at and evict oldest
            sessions.sort(key=lambda s: s.created_at)
            oldest = sessions[0]
            await session_store.remove_session(oldest.session_id)
            return oldest

        raise SessionGovernanceError(f"Unknown eviction strategy: {self.eviction_strategy}")

    async def enforce(self, user_id: str, session_store: "TenantSessionStore") -> None:
        """Enforce concurrency policy."""
        result = await self.check_concurrency(user_id, session_store)
        if not result.allowed:
            if self.enforcement_mode == "strict":
                raise SessionGovernanceError(
                    f"Concurrent session limit exceeded: "
                    f"{result.current_count}/{self.max_sessions_per_user}"
                )


@dataclass
class SessionToken:
    """Session token."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: str | None = None
    scope: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class TokenValidationResult:
    """Token validation result."""

    is_valid: bool
    session_id: str | None = None
    tenant_id: str | None = None
    user_id: str | None = None
    roles: list = field(default_factory=list)
    reason: str | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class SessionEvent:
    """Session event."""

    event_type: SessionEventType
    session_id: str
    user_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class SessionAnalytics:
    """Session analytics."""

    tenant_id: str
    total_sessions: int = 0
    active_sessions: int = 0
    expired_sessions: int = 0
    revoked_sessions: int = 0
    average_duration_minutes: float = 0.0
    peak_concurrent_sessions: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class StoredSession:
    """Stored session in session store."""

    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime | None = None
    last_activity: datetime | None = None
    metadata: dict = field(default_factory=dict)


# ============================================================================
# Implementation Classes
# ============================================================================


class TenantSessionStore:
    """Tenant-isolated session store."""

    def __init__(self, tenant_id: str, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.tenant_id = tenant_id
        self.constitutional_hash = constitutional_hash
        self._sessions: dict[str, StoredSession] = {}

    async def add_session(
        self,
        session_id: str,
        user_id: str,
        created_at: datetime,
        expires_at: datetime | None = None,
        metadata: dict | None = None,
    ) -> StoredSession:
        """Add a session to the store."""
        session = StoredSession(
            session_id=session_id,
            user_id=user_id,
            created_at=created_at,
            expires_at=expires_at,
            last_activity=created_at,
            metadata=metadata or {},
        )
        self._sessions[session_id] = session
        return session

    async def get_session(self, session_id: str) -> StoredSession | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    async def remove_session(self, session_id: str) -> None:
        """Remove a session."""
        self._sessions.pop(session_id, None)

    async def list_user_sessions(self, user_id: str) -> list[StoredSession]:
        """List all sessions for a user."""
        return [s for s in self._sessions.values() if s.user_id == user_id]

    async def cleanup_expired(self) -> int:
        """Remove expired sessions."""
        now = datetime.now(UTC)
        expired_ids = [
            sid for sid, s in self._sessions.items() if s.expires_at and s.expires_at < now
        ]
        for sid in expired_ids:
            del self._sessions[sid]
        return len(expired_ids)


class SessionLifecycleManager:
    """Manages session lifecycle."""

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash
        self._sessions: dict[str, Session] = {}
        self._stores: dict[str, TenantSessionStore] = {}

    def _get_store(self, tenant_id: str) -> TenantSessionStore:
        """Get or create session store for tenant."""
        if tenant_id not in self._stores:
            self._stores[tenant_id] = TenantSessionStore(tenant_id)
        return self._stores[tenant_id]

    async def create_session(self, config: SessionConfig) -> Session:
        """Create a new session."""
        session_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=config.max_duration_minutes)

        # Store idle_timeout_minutes in metadata for validation
        metadata = dict(config.metadata) if config.metadata else {}
        metadata["idle_timeout_minutes"] = config.idle_timeout_minutes

        session = Session(
            session_id=session_id,
            tenant_id=config.tenant_id,
            user_id=config.user_id,
            state=SessionState.ACTIVE,
            created_at=now,
            expires_at=expires_at,
            last_activity=now,
            max_duration_minutes=config.max_duration_minutes,
            metadata=metadata,
            constitutional_hash=self.constitutional_hash,
        )

        self._sessions[session_id] = session

        # Also add to tenant store
        store = self._get_store(config.tenant_id)
        await store.add_session(
            session_id=session_id, user_id=config.user_id, created_at=now, expires_at=expires_at
        )

        return session

    async def validate_session(self, session_id: str) -> SessionValidationResult:
        """Validate a session."""
        session = self._sessions.get(session_id)
        if not session:
            return SessionValidationResult(
                is_valid=False,
                reason="session_not_found",
                constitutional_hash=self.constitutional_hash,
            )

        now = datetime.now(UTC)

        # Check if expired
        if session.expires_at < now:
            session.state = SessionState.EXPIRED
            return SessionValidationResult(
                is_valid=False,
                session_id=session_id,
                state=SessionState.EXPIRED,
                reason="session_expired",
                constitutional_hash=self.constitutional_hash,
            )

        # Check idle timeout (using metadata for config)
        idle_timeout = session.metadata.get("idle_timeout_minutes", 15)
        idle_threshold = now - timedelta(minutes=idle_timeout)
        if session.last_activity < idle_threshold:
            session.state = SessionState.IDLE
            return SessionValidationResult(
                is_valid=False,
                session_id=session_id,
                state=SessionState.IDLE,
                reason="idle_timeout",
                constitutional_hash=self.constitutional_hash,
            )

        # Check if revoked
        if session.state == SessionState.REVOKED:
            return SessionValidationResult(
                is_valid=False,
                session_id=session_id,
                state=SessionState.REVOKED,
                reason="session_revoked",
                constitutional_hash=self.constitutional_hash,
            )

        return SessionValidationResult(
            is_valid=True,
            session_id=session_id,
            state=session.state,
            tenant_id=session.tenant_id,
            user_id=session.user_id,
            constitutional_hash=self.constitutional_hash,
        )

    async def extend_session(self, session_id: str, extension_minutes: int = 30) -> Session:
        """Extend a session.

        Raises:
            SessionNotFoundError: If session does not exist.
            SessionGovernanceError: If extension would exceed the configured max total duration.
        """
        session = self._sessions.get(session_id)
        if not session:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        # M3: Cap total session lifetime at SESSION_MAX_TOTAL_DURATION_MINUTES
        cap_minutes = min(
            SESSION_MAX_TOTAL_DURATION_MINUTES,
            session.max_duration_minutes * 4,  # never more than 4x original max
        )
        proposed_expires = session.expires_at + timedelta(minutes=extension_minutes)
        total_minutes = (proposed_expires - session.created_at).total_seconds() / 60
        if total_minutes > cap_minutes:
            raise SessionGovernanceError(
                f"Extension would exceed maximum allowed session duration of {cap_minutes} minutes"
            )

        session.expires_at = proposed_expires
        session.extension_count += 1
        session.last_activity = datetime.now(UTC)

        return session

    async def revoke_session(self, session_id: str, reason: str = "user_logout") -> Session:
        """Revoke a session."""
        session = self._sessions.get(session_id)
        if not session:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        session.state = SessionState.REVOKED
        session.revocation_reason = reason

        # Remove from tenant store
        store = self._get_store(session.tenant_id)
        await store.remove_session(session_id)

        return session

    async def refresh_activity(self, session_id: str) -> Session:
        """Refresh session activity timestamp."""
        session = self._sessions.get(session_id)
        if not session:
            raise SessionNotFoundError(f"Session not found: {session_id}")

        session.last_activity = datetime.now(UTC)
        return session

    async def _update_session(self, session: Session) -> None:
        """Update session in store."""
        self._sessions[session.session_id] = session


class SessionTokenManager:
    """Manages session tokens using PyJWT with iss/aud/jti claims.

    Security properties:
    - Asymmetric JWTs (RS*/ES*/EdDSA) signed with a PEM-encoded private key
      and verified with the derived public key
    - Per-token JTI (JWT ID) enables precise single-token revocation
    - Revoked JTIs stored in-memory; pass ``redis_client`` for restart-durable
      persistence (must expose async ``sadd``, ``sismember``, and ``expire``).
    """

    def __init__(
        self,
        private_key: str,
        token_ttl_minutes: int = 60,
        refresh_token_ttl_days: int = 7,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
        algorithm: str = SESSION_JWT_ALGORITHM,
        issuer: str = SESSION_JWT_ISSUER,
        audience: str = SESSION_JWT_AUDIENCE,
        redis_client: Any | None = None,
    ):
        self._private_key = private_key
        self.token_ttl_minutes = token_ttl_minutes
        self.refresh_token_ttl_days = refresh_token_ttl_days
        self.constitutional_hash = constitutional_hash
        self._algorithm = algorithm
        self._issuer = issuer
        self._audience = audience
        self._redis = redis_client
        if _uses_asymmetric_jwt_algorithm(self._algorithm):
            if "-----BEGIN" not in private_key:
                raise ValueError(
                    f"private_key must be a PEM-encoded private key for {self._algorithm}"
                )

            from cryptography.hazmat.primitives.serialization import load_pem_private_key

            try:
                private_key_obj = load_pem_private_key(private_key.encode(), password=None)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"private_key must be a PEM-encoded private key for {self._algorithm}"
                ) from e
            self._public_key = private_key_obj.public_key()
        else:
            self._public_key = private_key
        # In-memory fallback; also acts as local cache when Redis is available
        self._revoked_jtis: set[str] = set()
        self._refresh_tokens: dict[str, dict] = {}

    async def _is_jti_revoked(self, jti: str) -> bool:
        """Return True if the JTI has been revoked (checks Redis then local set)."""
        if jti in self._revoked_jtis:
            return True
        if self._redis is not None:
            try:
                return bool(await self._redis.sismember("session_revoked_jtis", jti))
            except Exception:
                pass
        return False

    async def _persist_revoked_jti(self, jti: str, ttl_seconds: int) -> None:
        """Persist a revoked JTI to Redis (best-effort)."""
        self._revoked_jtis.add(jti)
        if self._redis is not None:
            try:
                await self._redis.sadd("session_revoked_jtis", jti)
                # Expire the whole set when the last added token would have expired
                await self._redis.expire("session_revoked_jtis", ttl_seconds)
            except Exception:
                pass

    async def generate_access_token(
        self, session_id: str, tenant_id: str, user_id: str, roles: list[str] | None = None
    ) -> "SessionToken":
        """Generate a signed JWT access token with iss/aud/jti claims."""
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self.token_ttl_minutes)

        payload = {
            "jti": str(uuid.uuid4()),
            "sub": user_id,
            "iss": self._issuer,
            "aud": self._audience,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "session_id": session_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "roles": roles or [],
            "constitutional_hash": self.constitutional_hash,
        }

        token = jwt.encode(payload, self._private_key, algorithm=self._algorithm)

        return SessionToken(
            access_token=token,
            token_type="Bearer",
            expires_in=self.token_ttl_minutes * 60,
            constitutional_hash=self.constitutional_hash,
        )

    async def generate_refresh_token(
        self, session_id: str, tenant_id: str, user_id: str
    ) -> "SessionToken":
        """Generate an opaque refresh token (not a JWT -- long-lived, not decoded by clients)."""
        refresh_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=self.refresh_token_ttl_days)

        self._refresh_tokens[refresh_token] = {
            "session_id": session_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "exp": int(expires_at.timestamp()),
        }

        return SessionToken(
            access_token="",
            refresh_token=refresh_token,
            expires_in=self.refresh_token_ttl_days * 24 * 3600,
            constitutional_hash=self.constitutional_hash,
        )

    async def validate_token(self, token: str) -> "TokenValidationResult":
        """Validate a JWT access token, enforcing iss, aud, exp, and revocation."""
        try:
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["jti", "sub", "iss", "aud", "exp", "iat"]},
            )
        except jwt.ExpiredSignatureError:
            return TokenValidationResult(
                is_valid=False,
                reason="token_expired",
                constitutional_hash=self.constitutional_hash,
            )
        except jwt.PyJWTError:
            return TokenValidationResult(
                is_valid=False,
                reason="invalid_token",
                constitutional_hash=self.constitutional_hash,
            )

        jti = payload.get("jti", "")
        if await self._is_jti_revoked(jti):
            return TokenValidationResult(
                is_valid=False,
                reason="token_revoked",
                constitutional_hash=self.constitutional_hash,
            )

        return TokenValidationResult(
            is_valid=True,
            session_id=payload.get("session_id"),
            tenant_id=payload.get("tenant_id"),
            user_id=payload.get("user_id"),
            roles=payload.get("roles", []),
            constitutional_hash=self.constitutional_hash,
        )

    async def refresh_access_token(self, refresh_token: str) -> "SessionToken":
        """Exchange a valid refresh token for a new access token."""
        token_data = self._refresh_tokens.get(refresh_token)
        if not token_data:
            raise TokenValidationError("Invalid refresh token")

        if int(datetime.now(UTC).timestamp()) > token_data["exp"]:
            raise TokenValidationError("Refresh token expired")

        return await self.generate_access_token(
            session_id=token_data["session_id"],
            tenant_id=token_data["tenant_id"],
            user_id=token_data["user_id"],
        )

    async def revoke_token(self, token: str) -> None:
        """Revoke a token by its JTI (durable across restarts when Redis is configured)."""
        try:
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer,
                options={"verify_exp": False},
            )
            jti = payload.get("jti", "")
            exp = payload.get("exp", 0)
            ttl = max(0, exp - int(datetime.now(UTC).timestamp()))
        except jwt.PyJWTError:
            # Malformed tokens: add raw token as fallback key so validate_token
            # still returns token_revoked (via in-memory set) rather than invalid_token.
            self._revoked_jtis.add(token)
            return

        await self._persist_revoked_jti(jti, ttl or self.token_ttl_minutes * 60)


class SessionMonitor:
    """Monitors session events and analytics."""

    def __init__(self, tenant_id: str, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.tenant_id = tenant_id
        self.constitutional_hash = constitutional_hash
        self._events: list[SessionEvent] = []
        self._active_sessions: set[str] = set()

    async def record_event(self, event: SessionEvent) -> None:
        """Record a session event."""
        self._events.append(event)

        if event.event_type == SessionEventType.CREATED:
            self._active_sessions.add(event.session_id)
        elif event.event_type in (SessionEventType.EXPIRED, SessionEventType.REVOKED):
            self._active_sessions.discard(event.session_id)

    async def get_events(
        self,
        session_id: str | None = None,
        event_type: SessionEventType | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[SessionEvent]:
        """Get events with optional filters."""
        events = self._events

        if session_id:
            events = [e for e in events if e.session_id == session_id]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]

        return events

    async def get_active_session_count(self) -> int:
        """Get count of active sessions."""
        return len(self._active_sessions)

    async def get_analytics(self, start_time: datetime, end_time: datetime) -> SessionAnalytics:
        """Get session analytics for period."""
        events = await self.get_events(start_time=start_time, end_time=end_time)

        created = len([e for e in events if e.event_type == SessionEventType.CREATED])
        expired = len([e for e in events if e.event_type == SessionEventType.EXPIRED])
        revoked = len([e for e in events if e.event_type == SessionEventType.REVOKED])

        return SessionAnalytics(
            tenant_id=self.tenant_id,
            total_sessions=created,
            active_sessions=len(self._active_sessions),
            expired_sessions=expired,
            revoked_sessions=revoked,
            period_start=start_time,
            period_end=end_time,
            constitutional_hash=self.constitutional_hash,
        )

    async def get_user_session_history(self, user_id: str) -> list[SessionEvent]:
        """Get session history for a user."""
        return [e for e in self._events if e.user_id == user_id]


class SessionGovernanceClient:
    """SDK client for session governance API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        tenant_id: str,
        max_retries: int = 3,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.max_retries = max_retries
        self.constitutional_hash = constitutional_hash

    async def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        """Make API request with retries."""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return await self._make_request(method, path, data)
            except (ConnectionError, SessionGovernanceError) as e:
                last_error = e
                await asyncio.sleep(0.1 * (attempt + 1))

        raise last_error

    async def _make_request(self, method: str, path: str, data: dict | None = None) -> dict:
        """Make single API request (to be mocked in tests)."""
        # In real implementation, this would use aiohttp or httpx
        raise NotImplementedError("HTTP client not implemented")

    async def create_session(self, user_id: str, metadata: dict | None = None) -> dict:
        """Create a new session."""
        return await self._request(
            "POST",
            f"/tenants/{self.tenant_id}/sessions",
            {"user_id": user_id, "metadata": metadata or {}},
        )

    async def validate_session(self, session_id: str) -> dict:
        """Validate a session."""
        return await self._request(
            "GET", f"/tenants/{self.tenant_id}/sessions/{session_id}/validate"
        )

    async def revoke_session(self, session_id: str, reason: str = "user_logout") -> dict:
        """Revoke a session."""
        return await self._request(
            "DELETE", f"/tenants/{self.tenant_id}/sessions/{session_id}", {"reason": reason}
        )

    async def extend_session(self, session_id: str, extension_minutes: int = 30) -> dict:
        """Extend a session."""
        return await self._request(
            "POST",
            f"/tenants/{self.tenant_id}/sessions/{session_id}/extend",
            {"extension_minutes": extension_minutes},
        )

    async def get_analytics(self, start_time: datetime, end_time: datetime) -> dict:
        """Get session analytics."""
        return await self._request(
            "GET",
            f"/tenants/{self.tenant_id}/sessions/analytics",
            {"start_time": start_time.isoformat(), "end_time": end_time.isoformat()},
        )
