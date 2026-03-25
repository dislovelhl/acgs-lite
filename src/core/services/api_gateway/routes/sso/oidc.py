"""
OIDC Authentication Routes
Constitutional Hash: 608508a9bd224290
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from starlette.requests import Request as StarletteRequest

from src.core.shared.auth.oidc_handler import (
    OIDCAuthenticationError,
    OIDCConfigurationError,
    OIDCProviderError,
    OIDCTokenError,
    OIDCUserInfo,
)
from src.core.shared.auth.provisioning import ProvisioningResult, get_provisioner
from src.core.shared.config import settings
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

from .common import (
    SSOLogoutResponse,
    SSOProviderInfo,
    SSOUserInfoResponse,
    get_oidc_handler,
)

logger = get_logger(__name__)
router = APIRouter()


@router.get("/providers", response_model=list[SSOProviderInfo])
async def list_oidc_providers(
    handler=Depends(get_oidc_handler),
) -> list[SSOProviderInfo]:
    """List available OIDC providers (public endpoint)."""
    providers = handler.list_providers()
    return [SSOProviderInfo(name=name, type="oidc", enabled=True) for name in providers]


# Configured redirect URI allowlist from settings
# SECURITY: Strict allowlist of valid redirect URIs
ALLOWED_REDIRECT_URIS: frozenset[str] = frozenset()


def _validate_redirect_uri(redirect_uri: str, base_url: str | None = None) -> bool:
    """Validate redirect URI against strict allowlist.

    SECURITY: Prevents open redirect attacks by only allowing:
    1. Exact matches from configured allowlist
    2. URLs under the application's base URL
    """
    global ALLOWED_REDIRECT_URIS
    if not ALLOWED_REDIRECT_URIS:
        # Load from settings - in production, this should come from database/config
        from src.core.shared.config import settings

        allowed = set()
        # Add configured SSO callback URLs
        configured_callback_urls = getattr(settings.sso, "oidc_callback_urls", None)
        if configured_callback_urls:
            allowed.update(configured_callback_urls)
        # Add default callback URL
        allowed.add("/sso/oidc/callback")
        allowed.add("/api/v1/sso/oidc/callback")
        ALLOWED_REDIRECT_URIS = frozenset(allowed)

        # SECURITY: Fail closed if no OIDC callback URLs are configured
        if not ALLOWED_REDIRECT_URIS:
            raise ValueError("No OIDC callback URLs configured — cannot validate redirect URI")

    # Reject absolute URLs that don't match allowed patterns
    if "://" in redirect_uri:
        # Must exactly match an allowed URL
        return redirect_uri in ALLOWED_REDIRECT_URIS

    # Relative paths must start with / and not contain path traversal
    if not redirect_uri.startswith("/"):
        return False

    # Block path traversal attempts
    if ".." in redirect_uri or "//" in redirect_uri:
        return False

    # Only allow specific safe paths
    allowed_paths = {"/sso/oidc/callback", "/api/v1/sso/oidc/callback"}
    return redirect_uri in allowed_paths


@router.get("/login")
async def oidc_login(
    req: StarletteRequest,
    provider: str = Query(...),
    redirect_uri: str | None = Query(None),
    handler=Depends(get_oidc_handler),
) -> RedirectResponse:
    if not settings.sso.enabled and not settings.sso.oidc_enabled:
        raise HTTPException(status_code=503, detail="SSO disabled")

    callback_url = redirect_uri or str(req.url_for("oidc_callback"))
    # Validate redirect URI to prevent open redirect
    if redirect_uri and not _validate_redirect_uri(redirect_uri):
        raise HTTPException(status_code=400, detail="Invalid redirect URI")
    try:
        auth_url, state = await handler.initiate_login(
            provider_name=provider, redirect_uri=callback_url
        )
        req.session["oidc_state"] = state
        req.session["oidc_provider"] = provider
        req.session["oidc_callback_url"] = callback_url
        return RedirectResponse(url=auth_url, status_code=302)
    except OIDCConfigurationError as e:
        logger.warning(f"OIDC login failed: {e}")
        raise HTTPException(status_code=404, detail="OIDC provider not found.") from e
    except (OIDCProviderError, OIDCAuthenticationError, OIDCTokenError, ValueError, TypeError) as e:
        logger.error(f"OIDC login failed: {e}")
        raise HTTPException(status_code=500, detail="Login initiation failed") from e


@router.get("/callback", response_model=SSOUserInfoResponse)
async def oidc_callback(
    req: StarletteRequest,
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    handler=Depends(get_oidc_handler),
) -> JSONDict:
    if error:
        raise HTTPException(status_code=401, detail=error_description or error)

    stored_state = req.session.get("oidc_state")
    stored_provider = req.session.get("oidc_provider")
    stored_callback_url = req.session.get("oidc_callback_url")

    if not stored_state or stored_state != state:
        raise HTTPException(status_code=401, detail="Invalid state")

    try:
        user_info: OIDCUserInfo = await handler.handle_callback(
            stored_provider, code, state, stored_callback_url
        )

        # JIT Provisioning
        provisioner = get_provisioner(
            auto_provision_enabled=settings.sso.auto_provision_users,
            default_roles=(
                [settings.sso.default_role_on_provision]
                if settings.sso.default_role_on_provision
                else None
            ),
            allowed_domains=settings.sso.allowed_domains,
        )

        provisioning_result: ProvisioningResult = await provisioner.get_or_create_user(
            email=user_info.email,
            name=user_info.name,
            sso_provider="oidc",
            idp_user_id=user_info.sub,
            provider_id=stored_provider,
            roles=user_info.groups,
        )

        req.session["user"] = {
            "id": provisioning_result.user.get("id"),
            "sub": user_info.sub,
            "email": provisioning_result.user.get("email"),
            "name": provisioning_result.user.get("name"),
            "roles": provisioning_result.user.get("roles", []),
            "provider": stored_provider,
            "auth_type": "oidc",
        }

        return user_info.__dict__  # Simplified for now
    except (
        OIDCConfigurationError,
        OIDCAuthenticationError,
        OIDCTokenError,
        OIDCProviderError,
        ValueError,
        TypeError,
        LookupError,
    ) as e:
        logger.error(f"OIDC callback error: {e}")
        raise HTTPException(status_code=500, detail="Authentication processing failed") from e


@router.post("/logout", response_model=SSOLogoutResponse)
async def oidc_logout(
    req: StarletteRequest,
    handler=Depends(get_oidc_handler),
) -> SSOLogoutResponse:
    user = req.session.get("user")
    provider_name = user.get("provider") if user else None
    redirect_url = None

    if provider_name:
        try:
            redirect_url = await handler.logout(provider_name, str(req.base_url))
        except (
            OIDCConfigurationError,
            OIDCAuthenticationError,
            OIDCTokenError,
            OIDCProviderError,
            ValueError,
            TypeError,
            LookupError,
        ) as e:
            logger.warning(f"IdP logout failed: {e}")

    req.session.clear()
    return SSOLogoutResponse(success=True, message="Logged out", redirect_url=redirect_url)
