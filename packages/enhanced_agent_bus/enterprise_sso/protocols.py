"""
SSO Protocol Handlers (Facade)
Constitutional Hash: 608508a9bd224290

Implements SAML 2.0 and OIDC protocol handlers for Enterprise SSO.
Delegates to specialized modules in .enterprise_sso_infra.
"""

from .enterprise_sso_infra.base import BaseProtocolHandler
from .enterprise_sso_infra.factory import ProtocolHandlerFactory
from .enterprise_sso_infra.models import (
    CONSTITUTIONAL_HASH,
    AuthorizationRequest,
    LogoutRequest,
    LogoutRequestResult,
    LogoutResult,
    ProtocolValidationResult,
)
from .enterprise_sso_infra.oidc import OIDCHandler
from .enterprise_sso_infra.saml import SAML2Handler

__all__ = [
    "CONSTITUTIONAL_HASH",
    "AuthorizationRequest",
    "BaseProtocolHandler",
    "LogoutRequest",
    "LogoutRequestResult",
    "LogoutResult",
    "OIDCHandler",
    "ProtocolHandlerFactory",
    "ProtocolValidationResult",
    "SAML2Handler",
]
