"""
ACGS-2 LDAP Integration Module
Constitutional Hash: 608508a9bd224290

LDAP integration for enterprise authentication with connection pooling,
circuit breaker pattern, and MACI role mapping.

Phase 10 Task 3: LDAP Integration
"""

import secrets
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from queue import Empty, Queue

from enhanced_agent_bus.observability.structured_logging import get_logger

# LDAP module - optional import for environments without python-ldap
try:
    import ldap

    LDAP_AVAILABLE = True
except ImportError:
    LDAP_AVAILABLE = False
    ldap = None  # type: ignore[assignment]

from pydantic import BaseModel, ConfigDict, Field

# Constitutional Hash for ACGS-2
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import ACGSBaseError

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

logger = get_logger(__name__)
LDAP_OPERATION_ERRORS = (
    AttributeError,
    ConnectionError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)

# ============================================================================
# Exception Classes
# ============================================================================


class LDAPIntegrationError(ACGSBaseError):
    """Base exception for LDAP integration errors.

    Inherits from ACGSBaseError to gain constitutional hash tracking,
    correlation IDs, and structured error logging.
    """

    http_status_code = 500
    error_code = "LDAP_INTEGRATION_ERROR"

    def __init__(self, message: str, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash
        super().__init__(message, details={})


class LDAPConnectionError(LDAPIntegrationError):
    """Exception for LDAP connection failures."""

    http_status_code = 503  # Service Unavailable
    error_code = "LDAP_CONNECTION_ERROR"


class LDAPBindError(LDAPIntegrationError):
    """Exception for LDAP bind failures."""

    http_status_code = 401  # Unauthorized
    error_code = "LDAP_BIND_ERROR"


class LDAPSearchError(LDAPIntegrationError):
    """Exception for LDAP search failures."""


class LDAPCircuitOpenError(LDAPIntegrationError):
    """Exception when circuit breaker is open."""


# ============================================================================
# Configuration Models
# ============================================================================


class LDAPConfig(BaseModel):
    """LDAP connection and integration configuration."""

    # Connection settings
    server_uri: str = Field(..., description="LDAP server URI (ldap:// or ldaps://)")
    base_dn: str = Field(..., description="Base DN for searches")
    bind_dn: str | None = Field(None, description="Bind DN for authentication")
    bind_password: str | None = Field(None, description="Bind password")

    # TLS settings
    use_tls: bool = Field(default=True, description="Use TLS for connection")
    start_tls: bool = Field(default=False, description="Use STARTTLS")
    verify_cert: bool = Field(default=True, description="Verify server certificate")
    ca_cert_path: str | None = Field(None, description="Path to CA certificate")

    # Connection pool settings
    pool_size: int = Field(default=5, description="Connection pool size")
    pool_timeout: float = Field(default=30.0, description="Pool acquire timeout")
    connection_timeout: float = Field(default=10.0, description="Connection timeout")

    # User search settings
    user_search_base: str | None = Field(None, description="Base DN for user search")
    user_search_filter: str = Field(
        default="(uid={username})", description="LDAP filter for user search"
    )
    user_dn_pattern: str | None = Field(None, description="Pattern for building user DN")
    user_attributes: list[str] = Field(
        default=["cn", "mail", "displayName", "memberOf", "uid"],
        description="Attributes to fetch for users",
    )

    # Group search settings
    group_search_base: str | None = Field(None, description="Base DN for group search")
    group_search_filter: str = Field(
        default="(member={user_dn})", description="LDAP filter for group search"
    )
    group_name_attribute: str = Field(default="cn", description="Attribute containing group name")

    # MACI role mapping
    group_to_maci_role_mapping: dict[str, str] = Field(
        default_factory=dict, description="Mapping of LDAP groups to MACI roles"
    )

    # Circuit breaker settings
    circuit_breaker_enabled: bool = Field(default=True)
    circuit_breaker_failure_threshold: int = Field(default=5)
    circuit_breaker_recovery_timeout: float = Field(default=30.0)

    # Multi-tenancy
    tenant_id: str | None = Field(None, description="Tenant ID for multi-tenant mode")

    # Constitutional compliance
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH, description="Constitutional hash for validation"
    )

    model_config = ConfigDict(extra="allow")

    @classmethod
    def from_tenant_config(
        cls,
        tenant_id: str,
        server_uri: str,
        base_dn: str,
        bind_dn: str | None = None,
        bind_password: str | None = None,
        **kwargs,
    ) -> "LDAPConfig":
        """Create LDAP config from tenant configuration."""
        return cls(
            tenant_id=tenant_id,
            server_uri=server_uri,
            base_dn=base_dn,
            bind_dn=bind_dn,
            bind_password=bind_password,
            **kwargs,
        )


class LDAPAuthenticationResult(BaseModel):
    """Result of LDAP authentication attempt."""

    success: bool = Field(..., description="Whether authentication succeeded")
    user_dn: str | None = Field(None, description="User's distinguished name")
    email: str | None = Field(None, description="User's email address")
    display_name: str | None = Field(None, description="User's display name")
    groups: list[str] = Field(default_factory=list, description="User's group memberships")
    maci_roles: list[str] = Field(default_factory=list, description="Mapped MACI roles")
    attributes: JSONDict = Field(default_factory=dict, description="User attributes")

    # Error information
    error: str | None = Field(None, description="Error message if failed")
    error_code: str | None = Field(None, description="Error code if failed")

    # Session information
    session_token: str | None = Field(None, description="Session token")
    expires_at: datetime | None = Field(None, description="Session expiration")
    tenant_id: str | None = Field(None, description="Tenant ID")

    # Constitutional compliance
    constitutional_hash: str = Field(default=CONSTITUTIONAL_HASH, description="Constitutional hash")


# ============================================================================
# Circuit Breaker Implementation
# ============================================================================


class CircuitBreakerState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class LDAPCircuitBreaker:
    """Circuit breaker for LDAP connection failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        """Initialize circuit breaker."""
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        """Get current circuit breaker state."""
        with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                # Check if we should transition to half-open
                if self._last_failure_time is not None:
                    elapsed = time.time() - self._last_failure_time
                    if elapsed >= self.recovery_timeout:
                        self._state = CircuitBreakerState.HALF_OPEN
            return self._state.value

    @property
    def is_available(self) -> bool:
        """Check if circuit is available for requests."""
        return self.state in [
            CircuitBreakerState.CLOSED.value,
            CircuitBreakerState.HALF_OPEN.value,
        ]

    @property
    def consecutive_failures(self) -> int:
        """Get consecutive failure count."""
        with self._lock:
            return self._consecutive_failures

    def record_failure(self) -> None:
        """Record a failure."""
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_time = time.time()

            if self._consecutive_failures >= self.failure_threshold:
                self._state = CircuitBreakerState.OPEN
                logger.warning(
                    f"Circuit breaker opened after {self._consecutive_failures} failures"
                )

    def record_success(self) -> None:
        """Record a successful operation."""
        with self._lock:
            self._consecutive_failures = 0
            if self._state in [
                CircuitBreakerState.HALF_OPEN,
                CircuitBreakerState.OPEN,
            ]:
                self._state = CircuitBreakerState.CLOSED
                logger.info("Circuit breaker closed after successful operation")


# ============================================================================
# LDAP Connection Management
# ============================================================================


class LDAPConnection:
    """LDAP connection wrapper with lifecycle management."""

    def __init__(self, config: LDAPConfig):
        """Initialize LDAP connection."""
        if not LDAP_AVAILABLE:
            raise LDAPIntegrationError(
                "python-ldap package is not installed. Install with: pip install python-ldap"
            )

        self.config = config
        self._conn: object | None = None
        self._is_connected = False
        self._is_bound = False

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._is_connected

    def connect(self) -> bool:
        """Establish LDAP connection."""
        try:
            self._conn = ldap.initialize(self.config.server_uri)
            self._conn.set_option(ldap.OPT_REFERRALS, 0)
            self._conn.set_option(ldap.OPT_PROTOCOL_VERSION, ldap.VERSION3)

            # TLS configuration
            if self.config.verify_cert:
                self._conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
            if self.config.ca_cert_path:
                self._conn.set_option(ldap.OPT_X_TLS_CACERTFILE, self.config.ca_cert_path)

            # STARTTLS if configured
            if self.config.start_tls:
                self._conn.start_tls_s()

            self._is_connected = True
            return True

        except LDAP_OPERATION_ERRORS as e:
            self._is_connected = False
            raise LDAPConnectionError(f"Failed to connect: {e}") from e

    def bind(self, bind_dn: str | None = None, password: str | None = None) -> bool:
        """Bind to LDAP server."""
        if not self._is_connected:
            raise LDAPConnectionError("Not connected")

        try:
            dn = bind_dn or self.config.bind_dn
            pwd = password or self.config.bind_password

            if dn and pwd:
                self._conn.simple_bind_s(dn, pwd)
            else:
                # Anonymous bind
                self._conn.simple_bind_s("", "")

            self._is_bound = True
            return True

        except LDAP_OPERATION_ERRORS as e:
            raise LDAPBindError(f"Bind failed: {e}") from e

    def disconnect(self) -> None:
        """Disconnect from LDAP server."""
        if self._conn:
            try:
                self._conn.unbind_s()
            except LDAP_OPERATION_ERRORS as e:
                logger.debug("LDAP unbind cleanup: %s", e)
            finally:
                self._conn = None
                self._is_connected = False
                self._is_bound = False

    def whoami(self) -> str:
        """Get current bind identity."""
        if not self._is_bound:
            raise LDAPConnectionError("Not bound")
        return self._conn.whoami_s()  # type: ignore[no-any-return]

    def search(
        self,
        base_dn: str,
        search_filter: str,
        scope: int = 2,  # SCOPE_SUBTREE
        attributes: list[str] | None = None,
    ) -> list[tuple[str, JSONDict]]:
        """Execute LDAP search."""
        if not self._is_bound:
            raise LDAPConnectionError("Not bound")

        try:
            return self._conn.search_s(  # type: ignore[no-any-return]
                base_dn,
                scope,
                search_filter,
                attributes,
            )
        except (RuntimeError, ValueError, TypeError, OSError) as e:
            raise LDAPSearchError(f"Search failed: {e}") from e

    def __enter__(self) -> "LDAPConnection":
        """Context manager entry."""
        self.connect()
        self.bind()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()


# ============================================================================
# Connection Pool
# ============================================================================


class LDAPConnectionPool:
    """Connection pool for LDAP connections."""

    def __init__(self, config: LDAPConfig):
        """Initialize connection pool."""
        self.config = config
        self.max_size = config.pool_size
        self._pool: Queue = Queue(maxsize=config.pool_size)
        self._active_count = 0
        self._lock = threading.Lock()

    @property
    def available_connections(self) -> int:
        """Get number of available connections."""
        return self._pool.qsize()

    @property
    def active_connections(self) -> int:
        """Get number of active connections."""
        with self._lock:
            return self._active_count

    def _create_connection(self) -> LDAPConnection:
        """Create a new connection."""
        conn = LDAPConnection(self.config)
        conn.connect()
        conn.bind()
        with self._lock:
            self._active_count += 1
        return conn

    @contextmanager
    def acquire(self):
        """Acquire a connection from the pool."""
        conn: LDAPConnection | None = None

        try:
            # Try to get from pool first
            try:
                conn = self._pool.get_nowait()
            except Empty:
                # Create new connection if pool is empty
                conn = self._create_connection()

            yield conn

        finally:
            # Return to pool
            if conn and conn.is_connected:
                try:
                    self._pool.put_nowait(conn)
                except LDAP_OPERATION_ERRORS as e:
                    logger.debug("Failed to return connection to pool: %s", e)
                    conn.disconnect()
                    with self._lock:
                        self._active_count -= 1

    def shutdown(self) -> None:
        """Shutdown pool and close all connections."""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.disconnect()
            except Empty:
                break

        with self._lock:
            self._active_count = 0

    def health_check(self) -> JSONDict:
        """Get pool health status."""
        return {
            "healthy": True,
            "available_connections": self.available_connections,
            "active_connections": self.active_connections,
            "max_size": self.max_size,
        }


# ============================================================================
# Main LDAP Integration Class
# ============================================================================


class LDAPIntegration:
    """
    LDAP integration for enterprise authentication.

    Features:
    - Connection pooling for performance
    - Circuit breaker for fault tolerance
    - User authentication and attribute retrieval
    - Group membership queries
    - MACI role mapping
    - Multi-tenant support
    """

    def __init__(self, config: LDAPConfig):
        """Initialize LDAP integration."""
        self.config = config

        # Connection pool
        if LDAP_AVAILABLE:
            self._pool = LDAPConnectionPool(config)
        else:
            self._pool = None

        # Circuit breaker
        if config.circuit_breaker_enabled:
            self.circuit_breaker = LDAPCircuitBreaker(
                failure_threshold=config.circuit_breaker_failure_threshold,
                recovery_timeout=config.circuit_breaker_recovery_timeout,
            )
        else:
            self.circuit_breaker = None

    def _check_circuit_breaker(self) -> None:
        """Check circuit breaker before operation."""
        if self.circuit_breaker and not self.circuit_breaker.is_available:
            raise LDAPCircuitOpenError("LDAP circuit breaker is open. Service unavailable.")

    def search_user(self, username: str) -> JSONDict | None:
        """Search for a user by username."""
        self._check_circuit_breaker()

        try:
            search_base = self.config.user_search_base or self.config.base_dn
            search_filter = build_search_filter(
                self.config.user_search_filter,
                username=username,
            )

            with self._pool.acquire() as conn:
                results = conn.search(
                    search_base,
                    search_filter,
                    attributes=self.config.user_attributes,
                )

                if results:
                    entry = results[0]
                    if self.circuit_breaker:
                        self.circuit_breaker.record_success()
                    return parse_ldap_entry(entry)

            return None

        except (RuntimeError, ValueError, TypeError) as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            logger.error(f"User search failed: {e}")
            raise LDAPSearchError(f"User search failed: {e}") from e

    def resolve_user_dn(self, username: str) -> str | None:
        """Resolve user DN from username."""
        user = self.search_user(username)
        return user["dn"] if user else None  # type: ignore[no-any-return]

    def build_user_dn(self, username: str) -> str:
        """Build user DN from pattern."""
        if self.config.user_dn_pattern:
            return self.config.user_dn_pattern.format(username=username)
        return f"uid={username},{self.config.base_dn}"

    def authenticate(
        self,
        username: str,
        password: str,
    ) -> LDAPAuthenticationResult:
        """Authenticate a user against LDAP."""
        self._check_circuit_breaker()

        try:
            # First, search for the user
            user = self.search_user(username)

            if not user:
                return LDAPAuthenticationResult(
                    success=False,
                    user_dn=None,
                    email=None,
                    display_name=None,
                    session_token=None,
                    expires_at=None,
                    tenant_id=None,
                    error="User not found",
                    error_code="USER_NOT_FOUND",
                )

            user_dn = user["dn"]

            # Try to bind as the user
            try:
                conn = LDAPConnection(self.config)
                conn.connect()
                conn.bind(user_dn, password)
                conn.disconnect()
            except LDAPBindError:
                return LDAPAuthenticationResult(
                    success=False,
                    user_dn=None,
                    email=None,
                    display_name=None,
                    session_token=None,
                    expires_at=None,
                    tenant_id=None,
                    error="Invalid credentials",
                    error_code="INVALID_CREDENTIALS",
                )

            # Get user groups
            groups = self.get_user_groups(username)

            # Map groups to MACI roles
            maci_roles = self._map_groups_to_maci_roles(groups)

            # Generate session token
            session_token = secrets.token_urlsafe(32)
            expires_at = datetime.now(UTC) + timedelta(hours=8)

            # Log authentication attempt
            self._log_authentication_attempt(
                username=username,
                success=True,
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            if self.circuit_breaker:
                self.circuit_breaker.record_success()

            return LDAPAuthenticationResult(
                success=True,
                user_dn=user_dn,
                email=user.get("mail"),
                display_name=user.get("displayName"),
                groups=groups,
                maci_roles=maci_roles,
                attributes=user,
                error=None,
                error_code=None,
                session_token=session_token,
                expires_at=expires_at,
                tenant_id=self.config.tenant_id,
            )

        except (RuntimeError, ValueError, TypeError) as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()

            logger.debug("[%s] LDAP authentication error detail: %s", CONSTITUTIONAL_HASH, e)
            self._log_authentication_attempt(
                username=username,
                success=False,
                error="Authentication failed",
                constitutional_hash=CONSTITUTIONAL_HASH,
            )

            return LDAPAuthenticationResult(
                success=False,
                user_dn=None,
                email=None,
                display_name=None,
                session_token=None,
                expires_at=None,
                tenant_id=None,
                error="Authentication failed",
                error_code="AUTHENTICATION_ERROR",
            )

    def get_user_attributes(self, username: str) -> JSONDict | None:
        """Get user attributes."""
        user = self.search_user(username)
        return user if user else None

    def get_user_groups(
        self,
        username: str,
        resolve_nested: bool = False,
    ) -> list[str]:
        """Get user's group memberships."""
        _ = resolve_nested
        self._check_circuit_breaker()

        try:
            user = self.search_user(username)
            if not user:
                return []

            groups = []

            # Get groups from memberOf attribute
            member_of = user.get("memberOf", [])
            if isinstance(member_of, str):
                member_of = [member_of]

            for group_dn in member_of:
                # Extract group name from DN
                group_name = extract_cn_from_dn(group_dn)
                if group_name:
                    groups.append(group_name)

            if self.circuit_breaker:
                self.circuit_breaker.record_success()

            return groups

        except (RuntimeError, ValueError, TypeError) as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            logger.error(f"Failed to get user groups: {e}")
            return []

    def search_groups_for_user(self, user_dn: str) -> list[JSONDict]:
        """Search for groups containing a user."""
        self._check_circuit_breaker()

        try:
            search_base = self.config.group_search_base or self.config.base_dn
            search_filter = build_search_filter(
                self.config.group_search_filter,
                user_dn=user_dn,
            )

            with self._pool.acquire() as conn:
                results = conn.search(
                    search_base,
                    search_filter,
                    attributes=[self.config.group_name_attribute],
                )

                groups = []
                for entry in results:
                    if entry[0]:  # Skip referrals
                        groups.append(parse_ldap_entry(entry))

                if self.circuit_breaker:
                    self.circuit_breaker.record_success()

                return groups

        except (RuntimeError, ValueError, TypeError) as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            logger.error(f"Group search failed: {e}")
            return []

    def is_member_of(self, username: str, group_name: str) -> bool:
        """Check if user is member of a group."""
        groups = self.get_user_groups(username)
        return group_name.lower() in [g.lower() for g in groups]

    def search_group(self, group_name: str) -> JSONDict | None:
        """Search for a group by name."""
        self._check_circuit_breaker()

        try:
            search_base = self.config.group_search_base or self.config.base_dn
            search_filter = (
                f"({self.config.group_name_attribute}={escape_filter_chars(group_name)})"
            )

            with self._pool.acquire() as conn:
                results = conn.search(
                    search_base,
                    search_filter,
                    attributes=["cn", "description", "member"],
                )

                if results and results[0][0]:
                    if self.circuit_breaker:
                        self.circuit_breaker.record_success()
                    return parse_ldap_entry(results[0])

            return None

        except (RuntimeError, ValueError, TypeError) as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            logger.error(f"Group search failed: {e}")
            return None

    def get_group_members(self, group_name: str) -> list[str]:
        """Get members of a group."""
        group = self.search_group(group_name)
        if group:
            members = group.get("member", [])
            if isinstance(members, str):
                return [members]
            return members  # type: ignore[no-any-return]
        return []

    def list_groups(self) -> list[JSONDict]:
        """List all groups."""
        self._check_circuit_breaker()

        try:
            search_base = self.config.group_search_base or self.config.base_dn
            search_filter = "(objectClass=groupOfNames)"

            with self._pool.acquire() as conn:
                results = conn.search(
                    search_base,
                    search_filter,
                    attributes=[self.config.group_name_attribute],
                )

                groups = []
                for entry in results:
                    if entry[0]:
                        groups.append(parse_ldap_entry(entry))

                if self.circuit_breaker:
                    self.circuit_breaker.record_success()

                return groups

        except (RuntimeError, ValueError, TypeError) as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            logger.error(f"List groups failed: {e}")
            return []

    def _map_groups_to_maci_roles(self, groups: list[str]) -> list[str]:
        """Map LDAP groups to MACI roles."""
        maci_roles = []
        mapping = self.config.group_to_maci_role_mapping

        for group in groups:
            if group.lower() in [k.lower() for k in mapping.keys()]:
                # Find matching key (case-insensitive)
                for key, role in mapping.items():
                    if key.lower() == group.lower():
                        if role not in maci_roles:
                            maci_roles.append(role)

        return maci_roles

    def _log_authentication_attempt(
        self,
        username: str,
        success: bool,
        error: str | None = None,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        """Log authentication attempt for audit."""
        log_data = {
            "username": username,
            "success": success,
            "timestamp": datetime.now(UTC).isoformat(),
            "tenant_id": self.config.tenant_id,
            "constitutional_hash": constitutional_hash,
        }

        if error:
            log_data["error"] = error

        if success:
            logger.info(f"LDAP authentication successful: {username}")
        else:
            logger.warning(f"LDAP authentication failed: {username} - {error}")

    def health_check(self) -> JSONDict:
        """Perform health check."""
        health: JSONDict = {
            "status": "healthy",
            "server_uri": self.config.server_uri,
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }

        try:
            start_time = time.time()

            with self._pool.acquire() as conn:
                # Try a simple search on the root DSE
                conn.search(
                    "",
                    "(objectClass=*)",
                    scope=0,  # SCOPE_BASE
                    attributes=["namingContexts"],
                )

            latency_ms = (time.time() - start_time) * 1000
            health["latency_ms"] = latency_ms

        except (RuntimeError, ValueError, TypeError, OSError, LDAPIntegrationError) as e:
            health["status"] = "unhealthy"
            logger.debug("[%s] LDAP health check error detail: %s", CONSTITUTIONAL_HASH, e)
            health["error"] = "Health check failed"

        # Circuit breaker status
        if self.circuit_breaker:
            health["circuit_breaker"] = {
                "state": self.circuit_breaker.state,
                "consecutive_failures": self.circuit_breaker.consecutive_failures,
            }

        # Connection pool stats
        if self._pool:
            health["connection_pool"] = self._pool.health_check()

        return health


# ============================================================================
# Utility Functions
# ============================================================================


def escape_dn_chars(value: str) -> str:
    """Escape special characters in DN values."""
    # Characters to escape: , + " \ < > ; = /
    escape_chars = {
        ",": "\\,",
        "+": "\\+",
        '"': '\\"',
        "\\": "\\\\",
        "<": "\\<",
        ">": "\\>",
        ";": "\\;",
        "=": "\\=",
    }

    result = value
    for char, escaped in escape_chars.items():
        result = result.replace(char, escaped)
    return result


def escape_filter_chars(value: str) -> str:
    """Escape special characters in LDAP filter values."""
    # Escape backslash FIRST to avoid double-escaping other escape sequences
    result = value.replace("\\", "\\5c")

    # Then escape other special characters: * ( ) NUL
    escape_chars = [
        ("*", "\\2a"),
        ("(", "\\28"),
        (")", "\\29"),
        ("\x00", "\\00"),
    ]

    for char, escaped in escape_chars:
        result = result.replace(char, escaped)
    return result


def build_search_filter(
    template: str,
    **kwargs,
) -> str:
    """Build LDAP search filter from template."""
    # Escape values before substitution
    escaped_kwargs = {key: escape_filter_chars(str(value)) for key, value in kwargs.items()}
    return template.format(**escaped_kwargs)


def parse_dn(dn: str) -> dict[str, str]:
    """Parse DN into components."""
    result = {}
    parts = dn.split(",")

    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            result[key.strip()] = value.strip()

    return result


def extract_cn_from_dn(dn: str) -> str | None:
    """Extract CN value from DN."""
    parsed = parse_dn(dn)
    return parsed.get("cn")


def parse_ldap_entry(
    entry: tuple[str, dict[str, list[bytes]]],
) -> JSONDict:
    """Parse LDAP entry to dictionary."""
    dn, attributes = entry

    result: JSONDict = {"dn": dn}

    for key, values in attributes.items():
        decoded = decode_ldap_value(values)
        result[key] = decoded

    return result


def decode_ldap_value(
    values: list[bytes],
) -> str | list[str]:
    """Decode LDAP binary values to strings."""
    decoded = []

    for value in values:
        if isinstance(value, bytes):
            decoded.append(value.decode("utf-8", errors="replace"))
        else:
            decoded.append(str(value))

    if len(decoded) == 1:
        return decoded[0]
    return decoded


# ============================================================================
# Export all public classes and functions
# ============================================================================

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "LDAP_AVAILABLE",
    "LDAPAuthenticationResult",
    "LDAPBindError",
    "LDAPCircuitBreaker",
    "LDAPCircuitOpenError",
    # Configuration
    "LDAPConfig",
    # Classes
    "LDAPConnection",
    "LDAPConnectionError",
    "LDAPConnectionPool",
    "LDAPIntegration",
    # Exceptions
    "LDAPIntegrationError",
    "LDAPSearchError",
    "build_search_filter",
    "decode_ldap_value",
    # Utilities
    "escape_dn_chars",
    "escape_filter_chars",
    "parse_dn",
    "parse_ldap_entry",
]
