"""
ACGS-2 Authentication Handlers
Constitutional Hash: cdd01ef066bc6cf2

This module provides authentication handlers for SSO integration,
supporting both OpenID Connect (OIDC) and SAML 2.0 protocols.

Usage:
    from src.core.shared.auth import OIDCHandler, SAMLHandler, JITProvisioner, RoleMapper
    from src.core.shared.auth.oidc_handler import OIDCConfig
    from src.core.shared.auth.saml_config import SAMLSPConfig, SAMLIdPConfig

    # --- OIDC Authentication ---
    # Create OIDC handler with default settings
    oidc_handler = OIDCHandler()

    # Initialize a login flow
    auth_url, state = await oidc_handler.initiate_login(
        provider_name="google",
        redirect_uri="https://app.example.com/callback"
    )

    # Handle the callback after IdP authentication
    user_info = await oidc_handler.handle_callback(
        provider_name="google",
        code="authorization_code",
        state="state_from_session"
    )

    # --- SAML Authentication ---
    # Create SAML handler with default settings
    saml_handler = SAMLHandler()

    # Register an IdP
    saml_handler.register_idp(
        name="okta",
        metadata_url="https://dev-123.okta.com/app/exk123/sso/saml/metadata"
    )

    # Initiate SAML login
    redirect_url, request_id = await saml_handler.initiate_login("okta")

    # Process ACS callback
    user_info = await saml_handler.process_acs_response(saml_response, request_id)

    # --- JIT Provisioning ---
    # Create provisioner for automatic user creation on SSO login
    provisioner = JITProvisioner()

    # Provision user from SSO login
    result = await provisioner.get_or_create_user(
        email="user@example.com",
        name="John Doe",
        sso_provider="oidc",
        idp_user_id="google-12345",
        roles=["developer"],
    )

    if result.created:

    # --- Role Mapping ---
    # Map IdP groups to ACGS-2 roles
    role_mapper = RoleMapper()

    roles = role_mapper.map_groups(
        groups=["Engineering", "Administrators"],
        provider_name="okta"
    )
"""

from .oidc_handler import OIDCHandler
from .provisioning import JITProvisioner, ProvisioningResult, get_provisioner
from .role_mapper import MappingResult, RoleMapper, get_role_mapper
from .saml_handler import SAMLHandler
from .workos import (
    WORKOS_SIGNATURE_HEADER,
    WorkOSAPIError,
    WorkOSConfigurationError,
    WorkOSWebhookEvent,
    WorkOSWebhookVerificationError,
    generate_workos_admin_portal_link,
    is_workos_enabled,
    list_workos_events,
    parse_and_verify_workos_webhook,
)

__all__ = [
    "WORKOS_SIGNATURE_HEADER",
    "JITProvisioner",
    "MappingResult",
    "OIDCHandler",
    "ProvisioningResult",
    "RoleMapper",
    "SAMLHandler",
    "WorkOSAPIError",
    "WorkOSConfigurationError",
    "WorkOSWebhookEvent",
    "WorkOSWebhookVerificationError",
    "generate_workos_admin_portal_link",
    "get_provisioner",
    "get_role_mapper",
    "is_workos_enabled",
    "list_workos_events",
    "parse_and_verify_workos_webhook",
]
