"""
Shared SSO models, handlers and exception logic.
Constitutional Hash: cdd01ef066bc6cf2
"""

from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.requests import Request as StarletteRequest

from src.core.shared.auth import OIDCHandler, SAMLHandler
from src.core.shared.auth.oidc_handler import (
    OIDCAuthenticationError,
    OIDCConfigurationError,
    OIDCProviderError,
    OIDCTokenError,
)
from src.core.shared.auth.saml_config import SAMLConfigurationError, SAMLSPConfig
from src.core.shared.config import settings
from src.core.shared.di_container import DIContainer
from src.core.shared.structured_logging import get_logger

logger = get_logger(__name__)


class SSOLoginResponse(BaseModel):
    redirect_url: str
    state: str
    provider: str


class SSOUserInfoResponse(BaseModel):
    sub: str
    email: str | None = None
    email_verified: bool = False
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    groups: list[str] = []


class SSOProviderInfo(BaseModel):
    name: str
    type: str = "oidc"
    enabled: bool = True


class SSOLogoutResponse(BaseModel):
    success: bool
    message: str
    redirect_url: str | None = None


class SAMLUserInfoResponse(BaseModel):
    name_id: str
    email: str | None = None
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    groups: list[str] = []
    session_index: str | None = None


def _register_default_providers(handler: OIDCHandler) -> None:
    """Register default OIDC providers from settings."""
    if settings.sso.oidc_enabled and settings.sso.oidc_client_id:
        try:
            client_secret = (
                settings.sso.oidc_client_secret.get_secret_value()
                if settings.sso.oidc_client_secret
                else ""
            )
            discovery_url = settings.sso.oidc_issuer_url
            if discovery_url and not discovery_url.endswith("/.well-known/openid-configuration"):
                discovery_url = discovery_url.rstrip("/") + "/.well-known/openid-configuration"

            if discovery_url:
                handler.register_provider(
                    name="default",
                    client_id=settings.sso.oidc_client_id,
                    client_secret=client_secret,
                    server_metadata_url=discovery_url,
                    scopes=settings.sso.oidc_scopes,
                    use_pkce=settings.sso.oidc_use_pkce,
                )
        except (OIDCConfigurationError, OIDCProviderError, ValueError, TypeError, LookupError) as e:
            logger.warning(f"Failed to register default OIDC provider: {e}")


def _register_default_saml_providers(handler: SAMLHandler) -> None:
    """Register default SAML IdPs from settings."""
    if not settings.sso.saml_enabled:
        return
    if settings.sso.saml_idp_metadata_url or settings.sso.saml_idp_sso_url:
        try:
            handler.register_idp(
                name="default",
                metadata_url=settings.sso.saml_idp_metadata_url,
                entity_id=settings.sso.saml_entity_id,
                sso_url=settings.sso.saml_idp_sso_url,
                slo_url=settings.sso.saml_idp_slo_url,
                certificate=settings.sso.saml_idp_certificate,
                want_assertions_signed=settings.sso.saml_want_assertions_signed,
            )
        except (SAMLConfigurationError, ValueError, TypeError, LookupError) as e:
            logger.warning(f"Failed to register default SAML IdP: {e}")


# Handlers
def get_oidc_handler() -> OIDCHandler:
    """Get or create the global OIDCHandler instance via DI container."""
    try:
        return DIContainer.get_named("oidc_handler")
    except KeyError:
        handler = OIDCHandler()
        _register_default_providers(handler)
        DIContainer.register_named("oidc_handler", handler)

        # Also register as generic identity_provider if not set
        try:
            DIContainer.get_identity_provider()
        except KeyError:
            DIContainer.register_named("identity_provider", handler)

        return handler


def get_saml_handler(req: StarletteRequest) -> SAMLHandler:
    """Get or create the global SAMLHandler instance via DI container."""
    try:
        return DIContainer.get_named("saml_handler")
    except KeyError:
        base_url = str(req.base_url).rstrip("/")
        sp_config = SAMLSPConfig(
            entity_id=settings.sso.saml_entity_id or f"{base_url}/sso/saml/metadata",
            acs_url=f"{base_url}/sso/saml/acs",
            sls_url=f"{base_url}/sso/saml/sls",
            metadata_url=f"{base_url}/sso/saml/metadata",
            sign_authn_requests=settings.sso.saml_sign_requests,
            want_assertions_signed=settings.sso.saml_want_assertions_signed,
            want_assertions_encrypted=settings.sso.saml_want_assertions_encrypted,
        )
        if settings.sso.saml_sp_certificate:
            sp_config.cert_content = settings.sso.saml_sp_certificate
        if settings.sso.saml_sp_private_key:
            sp_config.key_content = settings.sso.saml_sp_private_key.get_secret_value()

        handler = SAMLHandler(sp_config=sp_config)
        _register_default_saml_providers(handler)
        DIContainer.register_named("saml_handler", handler)

        # Register as generic identity_provider if not set (or override if OIDC was set but SAML is preferred)
        DIContainer.register_named("identity_provider", handler)

        return handler


# Exception Handler
async def handle_sso_error(req: StarletteRequest, exc: Exception) -> JSONResponse:
    """Handle SSO related errors and return appropriate JSON responses."""
    logger.error(f"SSO error: {exc}", extra={"error_type": type(exc).__name__})
    if isinstance(exc, OIDCConfigurationError):
        return JSONResponse(status_code=500, content={"detail": "SSO configuration error"})
    elif isinstance(exc, (OIDCAuthenticationError, OIDCTokenError)):
        return JSONResponse(status_code=401, content={"detail": "Authentication failed"})
    elif isinstance(exc, OIDCProviderError):
        return JSONResponse(status_code=502, content={"detail": "Identity provider error"})
    return JSONResponse(status_code=500, content={"detail": "Unexpected SSO error"})
