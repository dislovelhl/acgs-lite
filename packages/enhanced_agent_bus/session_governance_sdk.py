"""
ACGS-2 Session Governance SDK
Constitutional Hash: 608508a9bd224290

A Python client SDK for the Enhanced Agent Bus Session Governance API.
Provides a clean interface for managing session governance configurations
with full multi-tenant support and constitutional compliance.

Usage:
    from enhanced_agent_bus.session_governance_sdk import SessionGovernanceClient, RiskLevel

    async with SessionGovernanceClient(base_url="http://localhost:8000") as client:
        # Create a session
        session = await client.create_session(
            tenant_id="my-tenant",
            risk_level=RiskLevel.MEDIUM,
            enabled_policies=["policy-a", "policy-b"],
        )

        # Get session details
        session = await client.get_session(session.session_id)

        # Select applicable policies
        policies = await client.select_policies(session.session_id)

        # Update governance configuration
        updated = await client.update_governance(
            session.session_id,
            risk_level=RiskLevel.HIGH,
        )

        # Extend session TTL
        await client.extend_ttl(session.session_id, ttl_seconds=7200)

        # Delete session
        await client.delete_session(session.session_id)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from enhanced_agent_bus._compat.errors import ACGSBaseError

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

logger = get_logger(__name__)
SESSION_SDK_HEALTHCHECK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    ConnectionError,
    OSError,
    httpx.HTTPError,
)

# Constitutional hash for compliance validation
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"


class RiskLevel(str, Enum):
    """Risk level classification for session governance."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AutomationLevel(str, Enum):
    """Maximum automation level for session governance."""

    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class SessionSDKError(ACGSBaseError):
    """Base exception for Session Governance SDK errors."""

    http_status_code = 500
    error_code = "SESSION_SDK_ERROR"

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: dict | None = None,
    ):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(
            message,
            details={"status_code": status_code, "response_body": response_body},
        )


class SessionNotFoundError(SessionSDKError):
    """Raised when a session is not found."""

    http_status_code = 404
    error_code = "SESSION_NOT_FOUND"


class TenantAccessDeniedError(SessionSDKError):
    """Raised when access is denied due to tenant isolation."""

    http_status_code = 403
    error_code = "TENANT_ACCESS_DENIED"


class SessionValidationError(SessionSDKError):
    """Raised when request validation fails."""

    http_status_code = 400
    error_code = "SDK_VALIDATION_ERROR"


class ServiceUnavailableError(SessionSDKError):
    """Raised when the service is unavailable."""

    http_status_code = 503
    error_code = "SERVICE_UNAVAILABLE"


@dataclass
class SelectedPolicy:
    """Represents a selected policy from the policy selection endpoint."""

    policy_id: str
    name: str
    source: str
    priority: int
    reasoning: str
    version: str | None = None
    metadata: JSONDict = field(default_factory=dict)


@dataclass
class PolicySelectionResult:
    """Result from the policy selection endpoint."""

    session_id: str
    tenant_id: str
    risk_level: str
    selected_policy: SelectedPolicy | None
    candidate_policies: list[SelectedPolicy]
    enabled_policies: list[str]
    disabled_policies: list[str]
    selection_metadata: JSONDict
    timestamp: str
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class GovernanceConfig:
    """Session governance configuration."""

    tenant_id: str
    user_id: str | None = None
    risk_level: RiskLevel = RiskLevel.MEDIUM
    policy_id: str | None = None
    policy_overrides: JSONDict = field(default_factory=dict)
    enabled_policies: list[str] = field(default_factory=list)
    disabled_policies: list[str] = field(default_factory=list)
    require_human_approval: bool = False
    max_automation_level: AutomationLevel | None = None

    def to_dict(self) -> JSONDict:
        """Convert to dictionary for API requests."""
        result: JSONDict = {
            "tenant_id": self.tenant_id,
            "risk_level": (
                self.risk_level.value if isinstance(self.risk_level, RiskLevel) else self.risk_level
            ),
        }
        if self.user_id:
            result["user_id"] = self.user_id
        if self.policy_id:
            result["policy_id"] = self.policy_id
        if self.policy_overrides:
            result["policy_overrides"] = self.policy_overrides
        if self.enabled_policies:
            result["enabled_policies"] = self.enabled_policies
        if self.disabled_policies:
            result["disabled_policies"] = self.disabled_policies
        if self.require_human_approval:
            result["require_human_approval"] = self.require_human_approval
        if self.max_automation_level:
            result["max_automation_level"] = (
                self.max_automation_level.value
                if isinstance(self.max_automation_level, AutomationLevel)
                else self.max_automation_level
            )
        return result


@dataclass
class Session:
    """Represents a session with governance configuration."""

    session_id: str
    tenant_id: str
    risk_level: str
    policy_id: str | None = None
    policy_overrides: JSONDict = field(default_factory=dict)
    enabled_policies: list[str] = field(default_factory=list)
    disabled_policies: list[str] = field(default_factory=list)
    require_human_approval: bool = False
    max_automation_level: str | None = None
    metadata: JSONDict = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None
    expires_at: str | None = None
    ttl_remaining: int | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @classmethod
    def from_dict(cls, data: JSONDict) -> Session:
        """Create Session from API response dictionary."""
        return cls(
            session_id=data["session_id"],
            tenant_id=data["tenant_id"],
            risk_level=data.get("risk_level", "medium"),
            policy_id=data.get("policy_id"),
            policy_overrides=data.get("policy_overrides", {}),
            enabled_policies=data.get("enabled_policies", []),
            disabled_policies=data.get("disabled_policies", []),
            require_human_approval=data.get("require_human_approval", False),
            max_automation_level=data.get("max_automation_level"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
            expires_at=data.get("expires_at"),
            ttl_remaining=data.get("ttl_remaining"),
            constitutional_hash=data.get("constitutional_hash", CONSTITUTIONAL_HASH),
        )


@dataclass
class SessionMetrics:
    """Session manager metrics."""

    cache_hits: int
    cache_misses: int
    creates: int
    reads: int
    updates: int
    deletes: int
    errors: int
    cache_hit_rate: float
    cache_size: int
    cache_capacity: int
    constitutional_hash: str = CONSTITUTIONAL_HASH

    @classmethod
    def from_dict(cls, data: JSONDict) -> SessionMetrics:
        """Create SessionMetrics from API response dictionary."""
        return cls(
            cache_hits=data.get("cache_hits", 0),
            cache_misses=data.get("cache_misses", 0),
            creates=data.get("creates", 0),
            reads=data.get("reads", 0),
            updates=data.get("updates", 0),
            deletes=data.get("deletes", 0),
            errors=data.get("errors", 0),
            cache_hit_rate=data.get("cache_hit_rate", 0.0),
            cache_size=data.get("cache_size", 0),
            cache_capacity=data.get("cache_capacity", 1000),
            constitutional_hash=data.get("constitutional_hash", CONSTITUTIONAL_HASH),
        )


class SessionGovernanceClient:
    """
    Client SDK for Session Governance API.

    Constitutional Hash: 608508a9bd224290

    Provides a clean interface for managing session governance configurations
    with full multi-tenant support and constitutional compliance.

    Example:
        async with SessionGovernanceClient(base_url="http://localhost:8000") as client:
            session = await client.create_session(
                tenant_id="my-tenant",
                risk_level=RiskLevel.MEDIUM,
            )
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
        verify_ssl: bool = True,
        default_tenant_id: str | None = None,
    ):
        """
        Initialize the Session Governance Client.

        Args:
            base_url: Base URL of the Enhanced Agent Bus API.
            timeout: Request timeout in seconds.
            verify_ssl: Whether to verify SSL certificates.
            default_tenant_id: Default tenant ID for requests.
        """
        if httpx is None:
            raise ImportError(
                "httpx is required for SessionGovernanceClient. Install it with: pip install httpx"
            )

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.default_tenant_id = default_tenant_id
        self._client: httpx.AsyncClient | None = None
        self.constitutional_hash = CONSTITUTIONAL_HASH

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] SessionGovernanceClient initialized (base_url={base_url})"
        )

    async def __aenter__(self) -> SessionGovernanceClient:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """Initialize the HTTP client connection."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                verify=self.verify_ssl,
            )
            logger.debug(f"[{CONSTITUTIONAL_HASH}] HTTP client connected")

    async def close(self) -> None:
        """Close the HTTP client connection."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.debug(f"[{CONSTITUTIONAL_HASH}] HTTP client closed")

    def _get_headers(self, tenant_id: str | None = None) -> dict[str, str]:
        """Get request headers with tenant ID."""
        tenant = tenant_id or self.default_tenant_id
        if not tenant:
            raise ValueError(
                "tenant_id is required. Provide it in the method call or "
                "set default_tenant_id when initializing the client."
            )
        return {"X-Tenant-ID": tenant, "Content-Type": "application/json"}

    def _handle_error(self, response: httpx.Response) -> None:
        """Handle error responses from the API."""
        try:
            error_body = response.json()
        except (ValueError, TypeError, AttributeError):
            error_body = {"detail": response.text}

        detail = error_body.get("detail", "Unknown error")

        if response.status_code == 404:
            raise SessionNotFoundError(detail, response.status_code, error_body)
        elif response.status_code == 403:
            raise TenantAccessDeniedError(detail, response.status_code, error_body)
        elif response.status_code == 400 or response.status_code == 422:
            raise SessionValidationError(detail, response.status_code, error_body)
        elif response.status_code == 503:
            raise ServiceUnavailableError(detail, response.status_code, error_body)
        else:
            raise SessionSDKError(detail, response.status_code, error_body)

    async def create_session(
        self,
        tenant_id: str | None = None,
        risk_level: RiskLevel | str = RiskLevel.MEDIUM,
        user_id: str | None = None,
        policy_id: str | None = None,
        policy_overrides: JSONDict | None = None,
        enabled_policies: list[str] | None = None,
        disabled_policies: list[str] | None = None,
        require_human_approval: bool = False,
        max_automation_level: AutomationLevel | str | None = None,
        metadata: JSONDict | None = None,
        session_id: str | None = None,
        ttl: int | None = None,
    ) -> Session:
        """
        Create a new session with governance configuration.

        Args:
            tenant_id: Tenant identifier (uses default if not provided).
            risk_level: Risk level for the session.
            user_id: Optional user identifier.
            policy_id: Optional specific policy ID to use.
            policy_overrides: Optional policy override parameters.
            enabled_policies: Optional list of enabled policy IDs.
            disabled_policies: Optional list of disabled policy IDs.
            require_human_approval: Whether to require human approval.
            max_automation_level: Maximum automation level allowed.
            metadata: Optional session metadata.
            session_id: Optional explicit session ID.
            ttl: Optional TTL in seconds.

        Returns:
            Created Session object.

        Raises:
            ValidationError: If request validation fails.
            ServiceUnavailableError: If the service is unavailable.
        """
        if self._client is None:
            await self.connect()

        tenant = tenant_id or self.default_tenant_id
        if not tenant:
            raise ValueError("tenant_id is required")

        # Build request payload
        payload: JSONDict = {
            "risk_level": risk_level.value if isinstance(risk_level, RiskLevel) else risk_level,
        }

        if user_id:
            payload["user_id"] = user_id
        if policy_id:
            payload["policy_id"] = policy_id
        if policy_overrides:
            payload["policy_overrides"] = policy_overrides
        if enabled_policies:
            payload["enabled_policies"] = enabled_policies
        if disabled_policies:
            payload["disabled_policies"] = disabled_policies
        if require_human_approval:
            payload["require_human_approval"] = require_human_approval
        if max_automation_level:
            payload["max_automation_level"] = (
                max_automation_level.value
                if isinstance(max_automation_level, AutomationLevel)
                else max_automation_level
            )
        if metadata:
            payload["metadata"] = metadata
        if session_id:
            payload["session_id"] = session_id
        if ttl:
            payload["ttl"] = ttl

        response = await self._client.post(
            "/api/v1/sessions",
            json=payload,
            headers=self._get_headers(tenant),
        )

        if response.status_code != 201:
            self._handle_error(response)

        session = Session.from_dict(response.json())
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Created session {session.session_id} for tenant {tenant}"
        )
        return session

    async def get_session(
        self,
        session_id: str,
        tenant_id: str | None = None,
    ) -> Session:
        """
        Get session details by ID.

        Args:
            session_id: The session identifier.
            tenant_id: Tenant identifier (uses default if not provided).

        Returns:
            Session object.

        Raises:
            SessionNotFoundError: If the session is not found.
            TenantAccessDeniedError: If access is denied.
        """
        if self._client is None:
            await self.connect()

        response = await self._client.get(
            f"/api/v1/sessions/{session_id}",
            headers=self._get_headers(tenant_id),
        )

        if response.status_code != 200:
            self._handle_error(response)

        return Session.from_dict(response.json())

    async def update_governance(
        self,
        session_id: str,
        tenant_id: str | None = None,
        risk_level: RiskLevel | str | None = None,
        user_id: str | None = None,
        policy_id: str | None = None,
        policy_overrides: JSONDict | None = None,
        enabled_policies: list[str] | None = None,
        disabled_policies: list[str] | None = None,
        require_human_approval: bool | None = None,
        max_automation_level: AutomationLevel | str | None = None,
        metadata: JSONDict | None = None,
    ) -> Session:
        """
        Update session governance configuration.

        Args:
            session_id: The session identifier.
            tenant_id: Tenant identifier (uses default if not provided).
            risk_level: New risk level.
            user_id: New user identifier.
            policy_id: New policy ID.
            policy_overrides: New policy overrides.
            enabled_policies: New enabled policies list.
            disabled_policies: New disabled policies list.
            require_human_approval: New human approval requirement.
            max_automation_level: New max automation level.
            metadata: New metadata.

        Returns:
            Updated Session object.

        Raises:
            SessionNotFoundError: If the session is not found.
            TenantAccessDeniedError: If access is denied.
            ValidationError: If request validation fails.
        """
        if self._client is None:
            await self.connect()

        # Build request payload with only provided fields
        payload: JSONDict = {}

        if risk_level is not None:
            payload["risk_level"] = (
                risk_level.value if isinstance(risk_level, RiskLevel) else risk_level
            )
        if user_id is not None:
            payload["user_id"] = user_id
        if policy_id is not None:
            payload["policy_id"] = policy_id
        if policy_overrides is not None:
            payload["policy_overrides"] = policy_overrides
        if enabled_policies is not None:
            payload["enabled_policies"] = enabled_policies
        if disabled_policies is not None:
            payload["disabled_policies"] = disabled_policies
        if require_human_approval is not None:
            payload["require_human_approval"] = require_human_approval
        if max_automation_level is not None:
            payload["max_automation_level"] = (
                max_automation_level.value
                if isinstance(max_automation_level, AutomationLevel)
                else max_automation_level
            )
        if metadata is not None:
            payload["metadata"] = metadata

        response = await self._client.put(
            f"/api/v1/sessions/{session_id}/governance",
            json=payload,
            headers=self._get_headers(tenant_id),
        )

        if response.status_code != 200:
            self._handle_error(response)

        session = Session.from_dict(response.json())
        logger.info(f"[{CONSTITUTIONAL_HASH}] Updated governance for session {session_id}")
        return session

    async def delete_session(
        self,
        session_id: str,
        tenant_id: str | None = None,
    ) -> bool:
        """
        Delete a session.

        Args:
            session_id: The session identifier.
            tenant_id: Tenant identifier (uses default if not provided).

        Returns:
            True if session was deleted successfully.

        Raises:
            SessionNotFoundError: If the session is not found.
            TenantAccessDeniedError: If access is denied.
        """
        if self._client is None:
            await self.connect()

        response = await self._client.delete(
            f"/api/v1/sessions/{session_id}",
            headers=self._get_headers(tenant_id),
        )

        if response.status_code == 204:
            logger.info(f"[{CONSTITUTIONAL_HASH}] Deleted session {session_id}")
            return True

        self._handle_error(response)
        return False

    async def extend_ttl(
        self,
        session_id: str,
        ttl_seconds: int,
        tenant_id: str | None = None,
    ) -> Session:
        """
        Extend session TTL.

        Args:
            session_id: The session identifier.
            ttl_seconds: New TTL in seconds.
            tenant_id: Tenant identifier (uses default if not provided).

        Returns:
            Updated Session object.

        Raises:
            SessionNotFoundError: If the session is not found.
            TenantAccessDeniedError: If access is denied.
            ValidationError: If TTL value is invalid.
        """
        if self._client is None:
            await self.connect()

        response = await self._client.post(
            f"/api/v1/sessions/{session_id}/extend",
            params={"ttl_seconds": ttl_seconds},
            headers=self._get_headers(tenant_id),
        )

        if response.status_code != 200:
            self._handle_error(response)

        session = Session.from_dict(response.json())
        logger.info(
            f"[{CONSTITUTIONAL_HASH}] Extended TTL for session {session_id} to {ttl_seconds}s"
        )
        return session

    async def select_policies(
        self,
        session_id: str,
        tenant_id: str | None = None,
        policy_name_filter: str | None = None,
        include_disabled: bool = False,
        include_all_candidates: bool = False,
        risk_level_override: RiskLevel | str | None = None,
    ) -> PolicySelectionResult:
        """
        Select applicable policies for a session.

        Args:
            session_id: The session identifier.
            tenant_id: Tenant identifier (uses default if not provided).
            policy_name_filter: Optional filter by policy name.
            include_disabled: Whether to include disabled policies.
            include_all_candidates: Whether to include all candidate policies.
            risk_level_override: Optional risk level override.

        Returns:
            PolicySelectionResult with selected and candidate policies.

        Raises:
            SessionNotFoundError: If the session is not found.
            TenantAccessDeniedError: If access is denied.
        """
        if self._client is None:
            await self.connect()

        # Build request payload
        payload: JSONDict = {}

        if policy_name_filter:
            payload["policy_name_filter"] = policy_name_filter
        if include_disabled:
            payload["include_disabled"] = include_disabled
        if include_all_candidates:
            payload["include_all_candidates"] = include_all_candidates
        if risk_level_override:
            payload["risk_level_override"] = (
                risk_level_override.value
                if isinstance(risk_level_override, RiskLevel)
                else risk_level_override
            )

        response = await self._client.post(
            f"/api/v1/sessions/{session_id}/policies/select",
            json=payload if payload else None,
            headers=self._get_headers(tenant_id),
        )

        if response.status_code != 200:
            self._handle_error(response)

        data = response.json()

        # Parse selected policy
        selected_policy = None
        if data.get("selected_policy"):
            sp = data["selected_policy"]
            selected_policy = SelectedPolicy(
                policy_id=sp["policy_id"],
                name=sp["name"],
                source=sp["source"],
                priority=sp["priority"],
                reasoning=sp["reasoning"],
                version=sp.get("version"),
                metadata=sp.get("metadata", {}),
            )

        # Parse candidate policies
        candidate_policies = []
        for cp in data.get("candidate_policies", []):
            candidate_policies.append(
                SelectedPolicy(
                    policy_id=cp["policy_id"],
                    name=cp["name"],
                    source=cp["source"],
                    priority=cp["priority"],
                    reasoning=cp["reasoning"],
                    version=cp.get("version"),
                    metadata=cp.get("metadata", {}),
                )
            )

        return PolicySelectionResult(
            session_id=data["session_id"],
            tenant_id=data["tenant_id"],
            risk_level=data["risk_level"],
            selected_policy=selected_policy,
            candidate_policies=candidate_policies,
            enabled_policies=data.get("enabled_policies", []),
            disabled_policies=data.get("disabled_policies", []),
            selection_metadata=data.get("selection_metadata", {}),
            timestamp=data["timestamp"],
            constitutional_hash=data.get("constitutional_hash", CONSTITUTIONAL_HASH),
        )

    async def get_metrics(self) -> SessionMetrics:
        """
        Get session manager metrics.

        Returns:
            SessionMetrics object.

        Raises:
            ServiceUnavailableError: If the service is unavailable.
        """
        if self._client is None:
            await self.connect()

        # Metrics endpoint doesn't require tenant header
        response = await self._client.get("/api/v1/sessions")

        if response.status_code != 200:
            self._handle_error(response)

        return SessionMetrics.from_dict(response.json())

    async def health_check(self) -> bool:
        """
        Check if the API is healthy.

        Returns:
            True if API is healthy.
        """
        if self._client is None:
            await self.connect()

        try:
            response = await self._client.get("/api/v1/sessions")  # type: ignore[union-attr]
            return bool(response.status_code == 200)
        except SESSION_SDK_HEALTHCHECK_ERRORS as e:
            logger.warning(f"Health check failed: {e}")
            return False


# Convenience function for creating client
def create_client(
    base_url: str = "http://localhost:8000",
    tenant_id: str | None = None,
    **kwargs,
) -> SessionGovernanceClient:
    """
    Create a SessionGovernanceClient instance.

    Args:
        base_url: Base URL of the Enhanced Agent Bus API.
        tenant_id: Default tenant ID for requests.
        **kwargs: Additional arguments passed to SessionGovernanceClient.

    Returns:
        SessionGovernanceClient instance.
    """
    return SessionGovernanceClient(
        base_url=base_url,
        default_tenant_id=tenant_id,
        **kwargs,
    )


__all__ = [
    "CONSTITUTIONAL_HASH",
    "AutomationLevel",
    "GovernanceConfig",
    "PolicySelectionResult",
    "RiskLevel",
    "SelectedPolicy",
    "ServiceUnavailableError",
    "Session",
    "SessionGovernanceClient",
    "SessionMetrics",
    "SessionNotFoundError",
    "SessionSDKError",
    "SessionValidationError",
    "TenantAccessDeniedError",
    "create_client",
]
