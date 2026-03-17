"""
SAML Authentication Routes
Constitutional Hash: cdd01ef066bc6cf2
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from starlette.requests import Request as StarletteRequest

from src.core.shared.auth.provisioning import ProvisioningResult, get_provisioner
from src.core.shared.auth.saml_handler import (
    SAMLAuthenticationError,
    SAMLConfigurationError,
    SAMLError,
    SAMLProviderError,
    SAMLReplayError,
    SAMLUserInfo,
    SAMLValidationError,
)
from src.core.shared.config import settings
from src.core.shared.structured_logging import get_logger
from src.core.shared.types import JSONDict

from .common import (
    SAMLUserInfoResponse,
    SSOLogoutResponse,
    SSOProviderInfo,
    get_saml_handler,
)

logger = get_logger(__name__)
router = APIRouter()


@router.get("/metadata")
async def saml_metadata(
    req: StarletteRequest,
    handler=Depends(get_saml_handler),
) -> Response:
    try:
        metadata_xml = await handler.generate_metadata()
        return Response(
            content=metadata_xml,
            media_type="application/xml",
            headers={"Content-Disposition": 'attachment; filename="sp-metadata.xml"'},
        )
    except (SAMLError, SAMLProviderError, SAMLValidationError, ValueError, TypeError) as e:
        logger.error(f"Failed to generate SAML metadata: {e}")
        raise HTTPException(status_code=500, detail="Metadata generation failed") from e


@router.get("/providers", response_model=list[SSOProviderInfo])
async def list_saml_providers(
    handler=Depends(get_saml_handler),
) -> list[SSOProviderInfo]:
    providers = handler.list_idps()
    return [SSOProviderInfo(name=name, type="saml", enabled=True) for name in providers]


@router.get("/login")
async def saml_login(
    req: StarletteRequest,
    provider: str = Query(...),
    relay_state: str | None = Query(None),
    force_authn: bool = Query(False),
    handler=Depends(get_saml_handler),
) -> RedirectResponse:
    if not settings.sso.enabled and not settings.sso.saml_enabled:
        raise HTTPException(status_code=503, detail="SAML disabled")

    try:
        redirect_url, request_id = await handler.initiate_login(
            idp_name=provider, relay_state=relay_state, force_authn=force_authn
        )
        req.session["saml_request_id"] = request_id
        req.session["saml_provider"] = provider
        req.session["saml_relay_state"] = relay_state
        return RedirectResponse(url=redirect_url, status_code=302)
    except SAMLConfigurationError as e:
        logger.warning(f"SAML login failed: {e}")
        raise HTTPException(status_code=404, detail="SAML provider not found.") from e
    except (SAMLProviderError, SAMLError, SAMLAuthenticationError, ValueError, TypeError) as e:
        logger.error(f"SAML login initiation failed: {e}")
        raise HTTPException(status_code=500, detail="Login initiation failed") from e


@router.post("/acs", response_model=SAMLUserInfoResponse)
async def saml_acs(
    req: StarletteRequest,
    SAMLResponse: str = Form(...),
    RelayState: str | None = Form(None),
    handler=Depends(get_saml_handler),
) -> JSONDict:
    stored_request_id = req.session.get("saml_request_id")
    stored_provider = req.session.get("saml_provider")

    try:
        user_info: SAMLUserInfo = await handler.process_acs_response(
            SAMLResponse, stored_request_id, stored_provider
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
            sso_provider="saml",
            idp_user_id=user_info.name_id,
            provider_id=stored_provider or "saml",
            roles=user_info.groups,
            name_id=user_info.name_id,
            session_index=user_info.session_index,
        )

        req.session["user"] = {
            "id": provisioning_result.user.get("id"),
            "sub": user_info.name_id,
            "email": provisioning_result.user.get("email"),
            "name": provisioning_result.user.get("name"),
            "roles": provisioning_result.user.get("roles", []),
            "provider": stored_provider or "saml",
            "auth_type": "saml",
            "session_index": user_info.session_index,
            "name_id": user_info.name_id,
        }

        return user_info.__dict__
    except (SAMLReplayError, SAMLValidationError, SAMLAuthenticationError) as e:
        logger.warning(f"SAML authentication failed: {e}")
        raise HTTPException(status_code=401, detail="SAML authentication failed.") from e
    except (
        SAMLProviderError,
        SAMLError,
        SAMLConfigurationError,
        ValueError,
        TypeError,
        LookupError,
    ) as e:
        logger.error(f"SAML ACS error: {e}")
        raise HTTPException(status_code=500, detail="Assertion processing failed") from e


@router.get("/sls")
@router.post("/sls")
async def saml_sls(
    req: StarletteRequest,
    SAMLResponse: str | None = Query(None),
    _SAMLRequest: str | None = Query(None),
    RelayState: str | None = Query(None),
    handler=Depends(get_saml_handler),
) -> SSOLogoutResponse:
    user = req.session.get("user")
    provider_name = user.get("provider") if user else None

    if SAMLResponse and provider_name:
        await handler.process_sls_response(SAMLResponse, provider_name)

    req.session.clear()
    # Validate RelayState to prevent open redirect
    validated_redirect = None
    if RelayState:
        if RelayState.startswith("/") and "://" not in RelayState:
            validated_redirect = RelayState
        else:
            logger.warning(f"Ignoring invalid RelayState: {RelayState}")
    return SSOLogoutResponse(success=True, message="Logged out", redirect_url=validated_redirect)


@router.post("/logout", response_model=SSOLogoutResponse)
async def saml_logout(
    req: StarletteRequest,
    handler=Depends(get_saml_handler),
) -> SSOLogoutResponse:
    user = req.session.get("user")
    if not user:
        return SSOLogoutResponse(success=True, message="No active session")

    provider_name = user.get("provider")
    name_id = user.get("name_id")
    session_index = user.get("session_index")
    redirect_url = None

    if provider_name and name_id:
        try:
            redirect_url = await handler.initiate_logout(
                provider_name, name_id, session_index, str(req.base_url)
            )
        except (
            SAMLProviderError,
            SAMLError,
            SAMLConfigurationError,
            SAMLAuthenticationError,
            ValueError,
            TypeError,
            LookupError,
        ) as e:
            logger.warning(f"SAML logout initiation failed: {e}")

    req.session.clear()
    return SSOLogoutResponse(success=True, message="Logged out", redirect_url=redirect_url)
