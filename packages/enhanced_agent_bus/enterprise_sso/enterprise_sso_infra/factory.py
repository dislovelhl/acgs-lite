"""
SSO Protocol handler factory.
Constitutional Hash: 608508a9bd224290
"""

from .oidc import OIDCHandler
from .saml import SAML2Handler


class ProtocolHandlerFactory:
    """Factory for creating protocol handlers."""

    @staticmethod
    def create_saml_handler(
        entity_id: str,
        sso_url: str,
        x509_certificate: str | None = None,
        sp_entity_id: str | None = None,
        sp_acs_url: str | None = None,
        **kwargs,
    ) -> SAML2Handler:
        """Create SAML 2.0 handler."""
        return SAML2Handler(
            entity_id=entity_id,
            sso_url=sso_url,
            x509_certificate=x509_certificate,
            sp_entity_id=sp_entity_id,
            sp_acs_url=sp_acs_url,
            **kwargs,
        )

    @staticmethod
    def create_oidc_handler(
        issuer: str,
        client_id: str,
        client_secret: str | None = None,
        scopes: list[str] | None = None,
        use_pkce: bool = True,
        **kwargs,
    ) -> OIDCHandler:
        """Create OIDC handler."""
        return OIDCHandler(
            issuer=issuer,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
            use_pkce=use_pkce,
            **kwargs,
        )
