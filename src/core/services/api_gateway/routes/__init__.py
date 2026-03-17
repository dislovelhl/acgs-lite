"""
ACGS-2 API Gateway Routes
Constitutional Hash: cdd01ef066bc6cf2

This module contains route handlers for the API Gateway service,
including SSO authentication endpoints for OIDC and SAML protocols,
admin APIs for SSO provider configuration, decision explanation APIs,
and data subject rights APIs (GDPR/CCPA).
"""

from .admin_sso import router as admin_sso_router
from .admin_workos import router as admin_workos_router
from .autonomy_tiers import autonomy_tiers_router
from .compliance import compliance_router
from .data_subject import data_subject_v1_router
from .decisions import decisions_v1_router
from .evolution_control import router as evolution_control_router
from .sso import router as sso_router
from .x402_governance import router as x402_governance_router

__all__ = [
    "admin_sso_router",
    "admin_workos_router",
    "autonomy_tiers_router",
    "compliance_router",
    "data_subject_v1_router",
    "decisions_v1_router",
    "evolution_control_router",
    "sso_router",
    "x402_governance_router",
]
