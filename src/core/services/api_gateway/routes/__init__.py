"""
ACGS-2 API Gateway Routes
Constitutional Hash: 608508a9bd224290

This module contains route handlers for the API Gateway service,
including SSO authentication endpoints for OIDC and SAML protocols,
admin APIs for SSO provider configuration, decision explanation APIs,
data subject rights APIs (GDPR/CCPA), feedback endpoints, and the
reverse-proxy catch-all.
"""

from ._x402_bundles import router as x402_bundles_router
from ._x402_facilitator import router as x402_facilitator_router
from ._x402_revenue import router as x402_revenue_router
from .admin_sso import router as admin_sso_router
from .admin_workos import router as admin_workos_router
from .autonomy_tiers import autonomy_tiers_router
from .compliance import compliance_router
from .data_subject import data_subject_v1_router
from .decisions import decisions_v1_router
from .evolution_control import router as evolution_control_router
from .feedback import gateway_v1_router
from .proxy import proxy_router
from .sso import router as sso_router
from .x402_governance import router as x402_governance_router
from .x402_marketplace import router as x402_marketplace_router

__all__ = [
    "admin_sso_router",
    "admin_workos_router",
    "autonomy_tiers_router",
    "compliance_router",
    "data_subject_v1_router",
    "decisions_v1_router",
    "evolution_control_router",
    "gateway_v1_router",
    "proxy_router",
    "sso_router",
    "x402_bundles_router",
    "x402_facilitator_router",
    "x402_governance_router",
    "x402_marketplace_router",
    "x402_revenue_router",
]
