"""
MCP Authentication Provider Factory Functions.

Constitutional Hash: 608508a9bd224290
MACI Role: JUDICIAL

Provides factory functions for common provider configurations:
- Azure AD
- Okta
- Generic OAuth2
"""

from .enums import ProviderType
from .models import ProviderConfig


def create_azure_ad_provider_config(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    scopes: list[str] | None = None,
) -> ProviderConfig:
    """
    Create Azure AD provider configuration.

    Args:
        tenant_id: Azure AD tenant ID
        client_id: Application (client) ID
        client_secret: Client secret
        scopes: OAuth2 scopes (defaults to MS Graph)

    Returns:
        ProviderConfig for Azure AD
    """
    return ProviderConfig(
        provider_type=ProviderType.AZURE_AD,
        name="azure_ad",
        client_id=client_id,
        client_secret=client_secret,
        tenant_id=tenant_id,
        default_scopes=scopes or ["https://graph.microsoft.com/.default"],
        discovery_enabled=True,
    )


def create_okta_provider_config(
    domain: str,
    client_id: str,
    client_secret: str,
    scopes: list[str] | None = None,
) -> ProviderConfig:
    """
    Create Okta provider configuration.

    Args:
        domain: Okta domain (e.g., 'dev-12345.okta.com')
        client_id: Okta client ID
        client_secret: Client secret
        scopes: OAuth2 scopes (defaults to OIDC standard scopes)

    Returns:
        ProviderConfig for Okta
    """
    return ProviderConfig(
        provider_type=ProviderType.OKTA,
        name="okta",
        client_id=client_id,
        client_secret=client_secret,
        okta_domain=domain,
        default_scopes=scopes or ["openid", "profile", "email"],
        discovery_enabled=True,
    )


def create_generic_oauth2_config(
    name: str,
    token_endpoint: str,
    client_id: str,
    client_secret: str,
    scopes: list[str] | None = None,
    authorization_endpoint: str | None = None,
) -> ProviderConfig:
    """
    Create generic OAuth2 provider configuration.

    Args:
        name: Provider name
        token_endpoint: OAuth2 token endpoint URL
        client_id: Client ID
        client_secret: Client secret
        scopes: OAuth2 scopes
        authorization_endpoint: Optional authorization endpoint

    Returns:
        ProviderConfig for generic OAuth2
    """
    return ProviderConfig(
        provider_type=ProviderType.GENERIC,
        name=name,
        client_id=client_id,
        client_secret=client_secret,
        token_endpoint=token_endpoint,
        authorization_endpoint=authorization_endpoint,
        default_scopes=scopes or [],
        discovery_enabled=False,
    )


__all__ = [
    "create_azure_ad_provider_config",
    "create_generic_oauth2_config",
    "create_okta_provider_config",
]
