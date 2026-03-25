"""
MCP Authentication Provider Package.

Constitutional Hash: 608508a9bd224290
MACI Role: JUDICIAL

Provides unified authentication for MCP tool access:
- OAuth2 token acquisition and injection
- OIDC discovery and authentication
- Multi-provider support (Generic, Azure AD, Okta)
- Automatic token refresh with renewal before expiry
- Per-tool credential management
- Comprehensive audit logging

This package consolidates OAuth2/OIDC authentication for the MCP integration,
providing a single entry point for all authentication operations.

Module Structure:
- enums.py: ProviderType, TokenState enumerations
- models.py: ProviderConfig, ManagedProviderToken, MCPAuthProviderConfig, AuthResult
- provider.py: MCPAuthProvider main class
- factories.py: Factory functions for common provider configurations
"""

from .enums import ProviderType, TokenState
from .factories import (
    create_azure_ad_provider_config,
    create_generic_oauth2_config,
    create_okta_provider_config,
)
from .models import (
    AuthResult,
    ManagedProviderToken,
    MCPAuthProviderConfig,
    ProviderConfig,
)
from .provider import MCPAuthProvider

__all__ = [
    "AuthResult",
    # Main provider class
    "MCPAuthProvider",
    # Configuration classes
    "MCPAuthProviderConfig",
    # Data models
    "ManagedProviderToken",
    "ProviderConfig",
    # Enums
    "ProviderType",
    "TokenState",
    # Factory functions
    "create_azure_ad_provider_config",
    "create_generic_oauth2_config",
    "create_okta_provider_config",
]
