"""
MCP Authentication Provider Models.

Constitutional Hash: 608508a9bd224290
MACI Role: JUDICIAL

Defines data models for the MCP authentication provider:
- ProviderConfig: Configuration for OAuth2/OIDC providers
- ManagedProviderToken: Token managed by MCPAuthProvider
- MCPAuthProviderConfig: Main configuration for MCP Auth Provider
- AuthResult: Result of authentication operations
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone

# Import centralized constitutional hash
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
from enhanced_agent_bus._compat.errors import ValidationError as ACGSValidationError

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ..oauth2_provider import OAuth2Config, OAuth2Token
from ..oidc_provider import OIDCConfig, OIDCTokens
from .enums import ProviderType, TokenState


@dataclass
class ProviderConfig:
    """Configuration for an OAuth2/OIDC provider."""

    provider_type: ProviderType
    name: str

    # Common OAuth2 settings
    client_id: str = ""
    client_secret: str = ""
    default_scopes: list[str] = field(default_factory=list)

    # OIDC discovery (for OIDC providers)
    issuer_url: str | None = None
    discovery_enabled: bool = True

    # Manual endpoints (for non-OIDC or custom providers)
    token_endpoint: str | None = None
    authorization_endpoint: str | None = None
    revocation_endpoint: str | None = None
    introspection_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None

    # Provider-specific settings
    tenant_id: str | None = None  # For Azure AD
    okta_domain: str | None = None  # For Okta

    # Options
    timeout_seconds: int = 30
    verify_ssl: bool = True
    use_pkce: bool = True

    # Token handling
    token_cache_enabled: bool = True
    token_refresh_threshold_seconds: int = 300  # 5 minutes before expiry

    # Additional metadata
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_oauth2_config(self) -> OAuth2Config:
        """Convert to OAuth2Config."""
        return OAuth2Config(
            token_endpoint=self._get_token_endpoint(),
            authorization_endpoint=self._get_authorization_endpoint(),
            revocation_endpoint=self.revocation_endpoint,
            introspection_endpoint=self.introspection_endpoint,
            client_id=self.client_id,
            client_secret=self.client_secret,
            default_scopes=self.default_scopes,
            timeout_seconds=self.timeout_seconds,
            verify_ssl=self.verify_ssl,
            token_cache_enabled=self.token_cache_enabled,
            token_refresh_threshold_seconds=self.token_refresh_threshold_seconds,
            use_pkce=self.use_pkce,
        )

    def to_oidc_config(self) -> OIDCConfig:
        """Convert to OIDCConfig."""
        return OIDCConfig(
            issuer_url=self._get_issuer_url(),
            client_id=self.client_id,
            client_secret=self.client_secret,
            default_scopes=self.default_scopes or ["openid", "profile", "email"],
            timeout_seconds=self.timeout_seconds,
            verify_ssl=self.verify_ssl,
            use_pkce=self.use_pkce,
            cache_discovery=True,
        )

    def _get_issuer_url(self) -> str:
        """Get issuer URL based on provider type."""
        if self.issuer_url:
            return self.issuer_url

        if self.provider_type == ProviderType.AZURE_AD:
            tenant = self.tenant_id or "common"
            return f"https://login.microsoftonline.com/{tenant}/v2.0"

        if self.provider_type == ProviderType.OKTA:
            if self.okta_domain:
                return f"https://{self.okta_domain}"
            raise ACGSValidationError(
                "Okta domain required for Okta provider",
                error_code="MCP_AUTH_OKTA_DOMAIN_MISSING",
            )

        if self.provider_type == ProviderType.GOOGLE:
            return "https://accounts.google.com"

        if self.provider_type == ProviderType.AUTH0:
            if domain := self.metadata.get("auth0_domain"):
                return f"https://{domain}"
            raise ACGSValidationError(
                "Auth0 domain required",
                error_code="MCP_AUTH_AUTH0_DOMAIN_MISSING",
            )

        if self.provider_type == ProviderType.KEYCLOAK:
            if realm := self.metadata.get("keycloak_realm"):
                base_url = self.metadata.get("keycloak_url", "http://localhost:8080")
                return f"{base_url}/realms/{realm}"
            raise ACGSValidationError(
                "Keycloak realm required",
                error_code="MCP_AUTH_KEYCLOAK_REALM_MISSING",
            )

        raise ACGSValidationError(
            f"Cannot determine issuer URL for {self.provider_type}",
            error_code="MCP_AUTH_ISSUER_UNKNOWN",
        )

    def _get_token_endpoint(self) -> str:
        """Get token endpoint based on provider type."""
        if self.token_endpoint:
            return self.token_endpoint

        if self.provider_type == ProviderType.AZURE_AD:
            tenant = self.tenant_id or "common"
            return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

        if self.provider_type == ProviderType.OKTA:
            if self.okta_domain:
                return f"https://{self.okta_domain}/oauth2/v1/token"
            raise ACGSValidationError(
                "Okta domain required",
                error_code="MCP_AUTH_OKTA_DOMAIN_MISSING",
            )

        if self.provider_type == ProviderType.GOOGLE:
            return "https://oauth2.googleapis.com/token"

        if self.provider_type == ProviderType.GITHUB:
            return "https://github.com/login/oauth/access_token"

        raise ACGSValidationError(
            f"Token endpoint required for {self.provider_type}",
            error_code="MCP_AUTH_TOKEN_ENDPOINT_MISSING",
        )

    def _get_authorization_endpoint(self) -> str | None:
        """Get authorization endpoint based on provider type."""
        if self.authorization_endpoint:
            return self.authorization_endpoint

        if self.provider_type == ProviderType.AZURE_AD:
            tenant = self.tenant_id or "common"
            return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"

        if self.provider_type == ProviderType.OKTA:
            if self.okta_domain:
                return f"https://{self.okta_domain}/oauth2/v1/authorize"

        if self.provider_type == ProviderType.GOOGLE:
            return "https://accounts.google.com/o/oauth2/v2/auth"

        if self.provider_type == ProviderType.GITHUB:
            return "https://github.com/login/oauth/authorize"

        return None


@dataclass
class ManagedProviderToken:
    """A token managed by MCPAuthProvider."""

    token_id: str
    provider_name: str
    tool_name: str | None
    tenant_id: str | None
    token: OAuth2Token
    oidc_tokens: OIDCTokens | None = None
    state: TokenState = TokenState.VALID
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used: datetime | None = None
    refresh_count: int = 0
    error_count: int = 0
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def update_state(self, threshold_seconds: int = 300) -> TokenState:
        """Update and return current state."""
        if self.state == TokenState.REVOKED:
            return self.state

        if self.token.is_expired():
            self.state = TokenState.EXPIRED
        elif self.token.needs_refresh(threshold_seconds):
            self.state = TokenState.EXPIRING_SOON
        else:
            self.state = TokenState.VALID

        return self.state

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "token_id": self.token_id,
            "provider_name": self.provider_name,
            "tool_name": self.tool_name,
            "tenant_id": self.tenant_id,
            "state": self.state.value,
            "token": self.token.to_dict(),
            "has_oidc_tokens": self.oidc_tokens is not None,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "refresh_count": self.refresh_count,
            "error_count": self.error_count,
            "constitutional_hash": self.constitutional_hash,
        }


# Import these here to avoid circular imports in MCPAuthProviderConfig
from ..auth_audit import AuditLoggerConfig
from ..credential_manager import CredentialManagerConfig
from ..token_refresh import RefreshConfig


@dataclass
class MCPAuthProviderConfig:
    """Configuration for MCP Auth Provider."""

    # Providers
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    default_provider: str | None = None

    # Credential management
    credential_config: CredentialManagerConfig | None = None

    # Token refresh
    refresh_config: RefreshConfig | None = None
    auto_refresh_enabled: bool = True

    # Audit logging
    audit_config: AuditLoggerConfig | None = None
    enable_audit: bool = True

    # Behavior
    fail_on_auth_error: bool = True
    retry_on_401: bool = True
    max_retries: int = 3

    # Caching
    token_cache_ttl_seconds: int = 3600

    # Constitutional
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class AuthResult:
    """Result of an authentication operation."""

    success: bool
    token: OAuth2Token | None = None
    oidc_tokens: OIDCTokens | None = None
    error: str | None = None
    provider_name: str | None = None
    token_id: str | None = None
    duration_ms: float = 0.0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "has_token": self.token is not None,
            "has_oidc_tokens": self.oidc_tokens is not None,
            "error": self.error,
            "provider_name": self.provider_name,
            "token_id": self.token_id,
            "duration_ms": self.duration_ms,
            "constitutional_hash": self.constitutional_hash,
        }


__all__ = [
    "AuthResult",
    "MCPAuthProviderConfig",
    "ManagedProviderToken",
    "ProviderConfig",
]
