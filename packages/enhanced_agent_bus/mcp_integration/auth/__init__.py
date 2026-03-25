"""
MCP Authentication Injection Module.

Constitutional Hash: 608508a9bd224290
MACI Role: JUDICIAL (authentication validation)

Provides comprehensive authentication for MCP tool access:
- OAuth2 token injection
- OIDC discovery and configuration
- Per-tool credential management
- Token refresh and rotation
- Auth audit logging
- Multi-provider support (Azure AD, Okta, generic OAuth2)

Components:
- MCPAuthProvider: Main authentication provider with multi-provider support
- OAuth2Provider: OAuth2 token management
- OIDCProvider: OpenID Connect discovery
- CredentialManager: Per-tool credentials
- TokenRefresher: Automatic token refresh
- AuthAuditLogger: Authentication audit
- AuthInjector: Request authentication injection
"""

from .auth_audit import (
    AuditLoggerConfig,
    AuditSeverity,
    AuthAuditEntry,
    AuthAuditEventType,
    AuthAuditLogger,
    AuthAuditStats,
)
from .auth_injector import (
    AuthContext,
    AuthInjector,
    AuthInjectorConfig,
    AuthMethod,
    InjectionResult,
    InjectionStatus,
)
from .credential_manager import (
    Credential,
    CredentialManager,
    CredentialManagerConfig,
    CredentialScope,
    CredentialType,
    ToolCredential,
)
from .mcp_auth_provider import (
    AuthResult,
    ManagedProviderToken,
    MCPAuthProvider,
    MCPAuthProviderConfig,
    ProviderConfig,
    ProviderType,
    TokenState,
    create_azure_ad_provider_config,
    create_generic_oauth2_config,
    create_okta_provider_config,
)
from .oauth2_provider import (
    OAuth2Config,
    OAuth2GrantType,
    OAuth2Provider,
    OAuth2Token,
)
from .oidc_provider import (
    OIDCConfig,
    OIDCProvider,
    OIDCProviderMetadata,
    OIDCTokens,
)
from .token_refresh import (
    RefreshConfig,
    RefreshResult,
    RefreshStatus,
    TokenRefresher,
)

__all__ = [
    "AuditLoggerConfig",
    "AuditSeverity",
    # Auth Audit
    "AuthAuditEntry",
    "AuthAuditEventType",
    "AuthAuditLogger",
    "AuthAuditStats",
    # Auth Injector
    "AuthContext",
    "AuthInjector",
    "AuthInjectorConfig",
    "AuthMethod",
    "AuthResult",
    # Credential Manager
    "Credential",
    "CredentialManager",
    "CredentialManagerConfig",
    "CredentialScope",
    "CredentialType",
    "InjectionResult",
    "InjectionStatus",
    # MCP Auth Provider (main entry point)
    "MCPAuthProvider",
    "MCPAuthProviderConfig",
    "ManagedProviderToken",
    # OAuth2
    "OAuth2Config",
    "OAuth2GrantType",
    "OAuth2Provider",
    "OAuth2Token",
    # OIDC
    "OIDCConfig",
    "OIDCProvider",
    "OIDCProviderMetadata",
    "OIDCTokens",
    "ProviderConfig",
    "ProviderType",
    # Token Refresh
    "RefreshConfig",
    "RefreshResult",
    "RefreshStatus",
    "TokenRefresher",
    "TokenState",
    "ToolCredential",
    # Factory functions
    "create_azure_ad_provider_config",
    "create_generic_oauth2_config",
    "create_okta_provider_config",
]
