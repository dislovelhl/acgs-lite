"""
MCP Authentication Provider Enums.

Constitutional Hash: 608508a9bd224290
MACI Role: JUDICIAL

Defines enumeration types for the MCP authentication provider:
- ProviderType: OAuth2/OIDC provider types
- TokenState: Token lifecycle states
"""

from enum import Enum


class ProviderType(str, Enum):
    """Type of OAuth2/OIDC provider."""

    GENERIC = "generic"
    AZURE_AD = "azure_ad"
    OKTA = "okta"
    KEYCLOAK = "keycloak"
    AUTH0 = "auth0"
    GOOGLE = "google"
    GITHUB = "github"
    CUSTOM = "custom"


class TokenState(str, Enum):
    """State of a managed token."""

    VALID = "valid"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    REFRESHING = "refreshing"
    INVALID = "invalid"
    REVOKED = "revoked"


__all__ = [
    "ProviderType",
    "TokenState",
]
