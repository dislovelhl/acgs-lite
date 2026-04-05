"""
Enterprise SSO Integration Service
Constitutional Hash: 608508a9bd224290

Integrates Enterprise SSO with Multi-Tenancy and MACI frameworks.
Provides unified authentication flow for the Enhanced Agent Bus.

Phase 10 Task 2: Enterprise SSO & Identity Management Integration
"""

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from uuid import uuid4

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import ACGSBaseError
from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
SSO_AUTHENTICATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
    asyncio.TimeoutError,
)

# Try to import multi-tenancy components
try:
    from ..multi_tenancy import (
        TenantContext,
        get_current_tenant,
        set_current_tenant,
        tenant_context,
    )

    MULTI_TENANCY_AVAILABLE = True
except ImportError:
    MULTI_TENANCY_AVAILABLE = False
    TenantContext = None  # type: ignore[misc, assignment]

# Try to import MACI components
try:
    from ..maci_enforcement import MACIRole

    MACI_AVAILABLE = True
except ImportError:
    MACI_AVAILABLE = False

    class MACIRole:  # type: ignore[no-redef]
        """Fallback MACI role enum."""

        EXECUTIVE = "executive"
        LEGISLATIVE = "legislative"
        JUDICIAL = "judicial"
        MONITOR = "monitor"
        AUDITOR = "auditor"
        CONTROLLER = "controller"
        IMPLEMENTER = "implementer"


try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .tenant_sso_config import (
    TenantIdPConfig,
    TenantSSOConfig,
    TenantSSOConfigManager,
)


class SSOIntegrationError(ACGSBaseError):
    """Exception for SSO integration errors.

    Inherits from ACGSBaseError to gain constitutional hash tracking,
    correlation IDs, and structured error logging.
    """

    http_status_code = 500
    error_code = "SSO_INTEGRATION_ERROR"

    def __init__(
        self,
        message: str,
        error_code: str = "SSO_ERROR",
        details: JSONDict | None = None,
    ):
        self.error_code = error_code  # Instance attribute (SSO-specific error code)
        details_dict = details or {}
        super().__init__(message, details={**details_dict, "sso_error_code": error_code})


@dataclass
class SSOUser:
    """Authenticated SSO user information.

    Constitutional Hash: 608508a9bd224290
    """

    external_id: str
    email: str
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    groups: list[str] = field(default_factory=list)
    raw_attributes: JSONDict = field(default_factory=dict)
    authenticated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> JSONDict:
        """Serialize to dictionary."""
        return {
            "external_id": self.external_id,
            "email": self.email,
            "display_name": self.display_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "groups": self.groups,
            "authenticated_at": self.authenticated_at.isoformat(),
        }


@dataclass
class SSOSession:
    """SSO session with tenant and MACI integration.

    Constitutional Hash: 608508a9bd224290
    """

    session_id: str
    user_id: str
    external_id: str
    tenant_id: str
    idp_id: str
    maci_roles: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def is_expired(self) -> bool:
        """Check if session has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    def has_role(self, role: str) -> bool:
        """Check if session has a specific MACI role."""
        return role.upper() in [r.upper() for r in self.maci_roles]

    def to_dict(self) -> JSONDict:
        """Serialize to dictionary (excluding sensitive data)."""
        return {
            "session_id": self.session_id[:12] + "...",
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "idp_id": self.idp_id,
            "maci_roles": self.maci_roles,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired(),
            "email": self.metadata.get("email"),
            "display_name": self.metadata.get("display_name"),
        }


@dataclass
class SSOAuthenticationResult:
    """Result of SSO authentication.

    Constitutional Hash: 608508a9bd224290
    """

    success: bool
    session: SSOSession | None = None
    user: SSOUser | None = None
    tenant_context: object | None = None  # TenantContext if available
    token: str | None = None
    error: str | None = None
    error_code: str | None = None

    def to_dict(self) -> JSONDict:
        """Serialize to dictionary."""
        result = {
            "success": self.success,
            "error": self.error,
            "error_code": self.error_code,
        }

        if self.session:
            result["session"] = self.session.to_dict()

        if self.user:
            result["user"] = self.user.to_dict()

        return result


class EnterpriseSSOService:
    """Enterprise SSO integration service.

    Constitutional Hash: 608508a9bd224290

    Provides unified SSO authentication with:
    - Multi-tenant support
    - MACI role integration
    - Session management
    - Identity federation

    Usage:
        sso_service = EnterpriseSSOService()

        # Configure tenant SSO
        sso_service.configure_tenant_sso(
            tenant_id="acme-corp",
            sso_enabled=True,
        )

        # Add identity provider
        idp_config = create_okta_idp_config(...)
        sso_service.add_identity_provider("acme-corp", idp_config)

        # Authenticate user
        result = await sso_service.authenticate_sso(
            tenant_id="acme-corp",
            idp_id="okta-acme-123",
            sso_response=saml_response_or_oidc_tokens,
        )
    """

    def __init__(
        self,
        config_manager: TenantSSOConfigManager | None = None,
        jwt_secret: str | None = None,
        default_session_hours: int = 24,
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ) -> None:
        """Initialize the SSO service.

        Args:
            config_manager: Tenant SSO configuration manager.
            jwt_secret: Secret for signing session tokens.
            default_session_hours: Default session duration in hours.
            constitutional_hash: Constitutional hash for validation.
        """
        if constitutional_hash != CONSTITUTIONAL_HASH:
            raise ValueError(
                f"Invalid constitutional hash. Expected {CONSTITUTIONAL_HASH}, "
                f"got {constitutional_hash}"
            )

        self.constitutional_hash = constitutional_hash
        self.config_manager = config_manager or TenantSSOConfigManager()
        self.jwt_secret = jwt_secret or secrets.token_urlsafe(32)
        self.default_session_hours = default_session_hours

        # In-memory session store (for production, use Redis)
        self._sessions: dict[str, SSOSession] = {}
        self._user_sessions: dict[str, list[str]] = {}  # user_id -> [session_ids]

        # User store (for JIT provisioning)
        self._users: dict[str, JSONDict] = {}

        logger.info(f"[{CONSTITUTIONAL_HASH}] Initialized EnterpriseSSOService")

    # =========================================================================
    # Tenant SSO Configuration
    # =========================================================================

    def configure_tenant_sso(
        self,
        tenant_id: str,
        sso_enabled: bool = True,
        sso_enforced: bool = False,
    ) -> TenantSSOConfig:
        """Configure SSO for a tenant.

        Args:
            tenant_id: Tenant identifier.
            sso_enabled: Whether SSO is enabled.
            sso_enforced: Whether SSO is required (no local auth).

        Returns:
            TenantSSOConfig for the tenant.
        """
        existing = self.config_manager.get_config(tenant_id)
        if existing:
            return self.config_manager.update_config(
                tenant_id=tenant_id,
                sso_enabled=sso_enabled,
                sso_enforced=sso_enforced,
            )

        return self.config_manager.create_config(
            tenant_id=tenant_id,
            sso_enabled=sso_enabled,
            sso_enforced=sso_enforced,
        )

    def get_tenant_sso_config(self, tenant_id: str) -> TenantSSOConfig | None:
        """Get SSO configuration for a tenant."""
        return self.config_manager.get_config(tenant_id)

    def add_identity_provider(
        self,
        tenant_id: str,
        idp_config: TenantIdPConfig,
        set_as_default: bool = False,
    ) -> TenantSSOConfig:
        """Add an identity provider to a tenant.

        Args:
            tenant_id: Tenant identifier.
            idp_config: Identity provider configuration.
            set_as_default: Whether to set as default IdP.

        Returns:
            Updated TenantSSOConfig.

        Raises:
            SSOIntegrationError: If tenant not configured.
        """
        # Ensure tenant has SSO config
        config = self.config_manager.get_config(tenant_id)
        if not config:
            config = self.configure_tenant_sso(tenant_id, sso_enabled=True)

        result = self.config_manager.add_identity_provider(
            tenant_id=tenant_id,
            idp_config=idp_config,
            set_as_default=set_as_default,
        )

        if not result:
            raise SSOIntegrationError(
                f"Failed to add IdP to tenant: {tenant_id}",
                error_code="IDP_ADD_FAILED",
            )

        return result

    def remove_identity_provider(self, tenant_id: str, idp_id: str) -> TenantSSOConfig | None:
        """Remove an identity provider from a tenant."""
        return self.config_manager.remove_identity_provider(tenant_id, idp_id)

    # =========================================================================
    # SSO Authentication
    # =========================================================================

    async def authenticate_sso(
        self,
        tenant_id: str,
        idp_id: str,
        sso_user: SSOUser,
        session_hours: int | None = None,
    ) -> SSOAuthenticationResult:
        """Authenticate user via SSO and create session.

        Args:
            tenant_id: Tenant identifier.
            idp_id: Identity provider ID.
            sso_user: Authenticated user from IdP.
            session_hours: Optional custom session duration.

        Returns:
            SSOAuthenticationResult with session and tenant context.
        """
        try:
            # Get tenant SSO config
            config = self.config_manager.get_config(tenant_id)
            if not config:
                return SSOAuthenticationResult(
                    success=False,
                    error="Tenant not configured for SSO",
                    error_code="TENANT_NOT_CONFIGURED",
                )

            if not config.sso_enabled:
                return SSOAuthenticationResult(
                    success=False,
                    error="SSO is disabled for this tenant",
                    error_code="SSO_DISABLED",
                )

            # Get IdP config
            idp_config = config.get_idp(idp_id)
            if not idp_config:
                return SSOAuthenticationResult(
                    success=False,
                    error=f"Identity provider not found: {idp_id}",
                    error_code="IDP_NOT_FOUND",
                )

            if not idp_config.enabled:
                return SSOAuthenticationResult(
                    success=False,
                    error="Identity provider is disabled",
                    error_code="IDP_DISABLED",
                )

            # Validate domain
            if not idp_config.is_domain_allowed(sso_user.email):
                return SSOAuthenticationResult(
                    success=False,
                    error="Email domain not allowed",
                    error_code="DOMAIN_NOT_ALLOWED",
                )

            # JIT provision or update user
            internal_user_id = await self._jit_provision_user(
                tenant_id=tenant_id,
                idp_config=idp_config,
                sso_user=sso_user,
            )

            # Get MACI roles
            maci_roles = idp_config.get_maci_roles(
                sso_user.groups,
                sso_user.raw_attributes,
            )

            # Create session
            session = self._create_session(
                user_id=internal_user_id,
                external_id=sso_user.external_id,
                tenant_id=tenant_id,
                idp_id=idp_id,
                maci_roles=maci_roles,
                email=sso_user.email,
                display_name=sso_user.display_name,
                session_hours=session_hours or config.session_timeout_hours,
            )

            # Create tenant context if multi-tenancy is available
            tenant_ctx = None
            if MULTI_TENANCY_AVAILABLE and TenantContext:
                tenant_ctx = TenantContext(
                    tenant_id=tenant_id,
                    user_id=internal_user_id,
                    session_id=session.session_id,
                    is_admin="EXECUTIVE" in maci_roles or "JUDICIAL" in maci_roles,
                    roles=maci_roles,
                )

            logger.info(
                f"[{CONSTITUTIONAL_HASH}] SSO authentication successful: "
                f"user={internal_user_id}, tenant={tenant_id}, roles={maci_roles}"
            )

            return SSOAuthenticationResult(
                success=True,
                session=session,
                user=sso_user,
                tenant_context=tenant_ctx,
            )

        except SSO_AUTHENTICATION_ERRORS as e:
            logger.exception(f"[{CONSTITUTIONAL_HASH}] SSO authentication failed")
            logger.debug(f"[{CONSTITUTIONAL_HASH}] SSO authentication error detail: {e}")
            return SSOAuthenticationResult(
                success=False,
                error="Authentication failed",
                error_code="AUTH_FAILED",
            )

    async def _jit_provision_user(
        self,
        tenant_id: str,
        idp_config: TenantIdPConfig,
        sso_user: SSOUser,
    ) -> str:
        """Just-In-Time provision or update user.

        Args:
            tenant_id: Tenant identifier.
            idp_config: IdP configuration.
            sso_user: SSO user information.

        Returns:
            Internal user ID.
        """
        # Create composite key for user lookup
        user_key = f"{tenant_id}:{sso_user.external_id}"

        existing_user = self._users.get(user_key)

        if existing_user:
            if idp_config.jit_update_on_login:
                # Update user info on login
                existing_user.update(
                    {
                        "email": sso_user.email,
                        "display_name": sso_user.display_name,
                        "first_name": sso_user.first_name,
                        "last_name": sso_user.last_name,
                        "groups": sso_user.groups,
                        "last_login_at": datetime.now(UTC).isoformat(),
                    }
                )
                logger.debug(f"[{CONSTITUTIONAL_HASH}] Updated JIT user: {user_key}")

            return existing_user["user_id"]  # type: ignore[no-any-return]

        # Create new user
        user_id = str(uuid4())
        self._users[user_key] = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "external_id": sso_user.external_id,
            "idp_id": idp_config.idp_id,
            "email": sso_user.email,
            "display_name": sso_user.display_name,
            "first_name": sso_user.first_name,
            "last_name": sso_user.last_name,
            "groups": sso_user.groups,
            "created_at": datetime.now(UTC).isoformat(),
            "last_login_at": datetime.now(UTC).isoformat(),
            "is_active": True,
        }

        logger.info(
            f"[{CONSTITUTIONAL_HASH}] JIT provisioned new user: "
            f"{user_id} ({sso_user.email}) in tenant {tenant_id}"
        )

        return user_id

    def _create_session(
        self,
        user_id: str,
        external_id: str,
        tenant_id: str,
        idp_id: str,
        maci_roles: list[str],
        email: str,
        display_name: str | None,
        session_hours: int,
    ) -> SSOSession:
        """Create a new SSO session.

        Args:
            user_id: Internal user ID.
            external_id: External IdP user ID.
            tenant_id: Tenant identifier.
            idp_id: Identity provider ID.
            maci_roles: Assigned MACI roles.
            email: User email.
            display_name: User display name.
            session_hours: Session duration in hours.

        Returns:
            Created SSOSession.
        """
        from datetime import timedelta

        now = datetime.now(UTC)
        session_id = secrets.token_urlsafe(32)

        session = SSOSession(
            session_id=session_id,
            user_id=user_id,
            external_id=external_id,
            tenant_id=tenant_id,
            idp_id=idp_id,
            maci_roles=maci_roles,
            created_at=now,
            expires_at=now + timedelta(hours=session_hours),
            metadata={
                "email": email,
                "display_name": display_name,
            },
        )

        # Store session
        self._sessions[session_id] = session

        # Track user sessions
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []
        self._user_sessions[user_id].append(session_id)

        return session

    # =========================================================================
    # Session Management
    # =========================================================================

    def get_session(self, session_id: str) -> SSOSession | None:
        """Get session by ID.

        Args:
            session_id: Session identifier.

        Returns:
            SSOSession if found and valid, None otherwise.
        """
        session = self._sessions.get(session_id)
        if session and not session.is_expired():
            return session
        return None

    def validate_session(self, session_id: str) -> SSOSession | None:
        """Validate session and return if valid.

        Args:
            session_id: Session identifier.

        Returns:
            SSOSession if valid, None otherwise.
        """
        session = self.get_session(session_id)
        if not session:
            return None

        # Validate tenant still has SSO enabled
        config = self.config_manager.get_config(session.tenant_id)
        if not config or not config.sso_enabled:
            self.invalidate_session(session_id)
            return None

        return session

    def invalidate_session(self, session_id: str) -> bool:
        """Invalidate a session.

        Args:
            session_id: Session identifier.

        Returns:
            True if session was invalidated, False if not found.
        """
        session = self._sessions.pop(session_id, None)
        if session:
            # Remove from user sessions list
            if session.user_id in self._user_sessions:
                self._user_sessions[session.user_id] = [
                    sid for sid in self._user_sessions[session.user_id] if sid != session_id
                ]

            logger.info(f"[{CONSTITUTIONAL_HASH}] Invalidated session: {session_id[:12]}...")
            return True

        return False

    def invalidate_user_sessions(self, user_id: str) -> int:
        """Invalidate all sessions for a user.

        Args:
            user_id: User identifier.

        Returns:
            Number of sessions invalidated.
        """
        session_ids = self._user_sessions.pop(user_id, [])
        count = 0

        for session_id in session_ids:
            if session_id in self._sessions:
                del self._sessions[session_id]
                count += 1

        if count > 0:
            logger.info(f"[{CONSTITUTIONAL_HASH}] Invalidated {count} sessions for user: {user_id}")

        return count

    def get_user_sessions(self, user_id: str) -> list[SSOSession]:
        """Get all active sessions for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of active sessions.
        """
        session_ids = self._user_sessions.get(user_id, [])
        sessions = []

        for session_id in session_ids:
            session = self.get_session(session_id)
            if session:
                sessions.append(session)

        return sessions

    def refresh_session(self, session_id: str) -> SSOSession | None:
        """Refresh session expiry.

        Args:
            session_id: Session identifier.

        Returns:
            Refreshed session or None if not found.
        """
        from datetime import timedelta

        session = self.get_session(session_id)
        if not session:
            return None

        # Get tenant config for session duration
        config = self.config_manager.get_config(session.tenant_id)
        hours = config.session_timeout_hours if config else self.default_session_hours

        # Update expiry
        session.expires_at = datetime.now(UTC) + timedelta(hours=hours)

        return session

    # =========================================================================
    # Identity Federation
    # =========================================================================

    def get_user_by_external_id(self, tenant_id: str, external_id: str) -> JSONDict | None:
        """Get user by external IdP ID.

        Args:
            tenant_id: Tenant identifier.
            external_id: External IdP user ID.

        Returns:
            User data if found.
        """
        user_key = f"{tenant_id}:{external_id}"
        return self._users.get(user_key)

    def get_user_by_email(self, tenant_id: str, email: str) -> JSONDict | None:
        """Get user by email within a tenant.

        Args:
            tenant_id: Tenant identifier.
            email: User email.

        Returns:
            User data if found.
        """
        for user_data in self._users.values():
            if user_data.get("tenant_id") == tenant_id and user_data.get("email") == email:
                return user_data
        return None

    def list_tenant_users(self, tenant_id: str, skip: int = 0, limit: int = 100) -> list[JSONDict]:
        """List all SSO users in a tenant.

        Args:
            tenant_id: Tenant identifier.
            skip: Number of records to skip.
            limit: Maximum records to return.

        Returns:
            List of user data.
        """
        users = [
            user_data
            for user_data in self._users.values()
            if user_data.get("tenant_id") == tenant_id
        ]
        return users[skip : skip + limit]

    # =========================================================================
    # MACI Integration
    # =========================================================================

    def get_session_maci_roles(self, session_id: str) -> list[str]:
        """Get MACI roles for a session.

        Args:
            session_id: Session identifier.

        Returns:
            List of MACI role names.
        """
        session = self.get_session(session_id)
        if session:
            return session.maci_roles
        return []

    def session_has_role(self, session_id: str, role: str) -> bool:
        """Check if session has a specific MACI role.

        Args:
            session_id: Session identifier.
            role: MACI role to check.

        Returns:
            True if session has the role.
        """
        session = self.get_session(session_id)
        if session:
            return session.has_role(role)
        return False

    # =========================================================================
    # Tenant Context Integration
    # =========================================================================

    def create_tenant_context(self, session: SSOSession) -> object | None:
        """Create TenantContext from SSO session.

        Args:
            session: SSO session.

        Returns:
            TenantContext if multi-tenancy is available.
        """
        if not MULTI_TENANCY_AVAILABLE or not TenantContext:
            return None

        return TenantContext(
            tenant_id=session.tenant_id,
            user_id=session.user_id,
            session_id=session.session_id,
            is_admin="EXECUTIVE" in session.maci_roles or "JUDICIAL" in session.maci_roles,
            roles=session.maci_roles,
        )

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_statistics(self) -> JSONDict:
        """Get SSO service statistics.

        Returns:
            Statistics dictionary.
        """
        active_sessions = len([s for s in self._sessions.values() if not s.is_expired()])

        return {
            "total_users": len(self._users),
            "total_sessions": len(self._sessions),
            "active_sessions": active_sessions,
            "configured_tenants": len(self.config_manager.list_configs()),
            "sso_enabled_tenants": len(self.config_manager.get_sso_enabled_tenants()),
            "constitutional_hash": self.constitutional_hash,
        }
