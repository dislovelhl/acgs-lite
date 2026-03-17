"""
ACGS-2 SSO Authentication Router
Constitutional Hash: cdd01ef066bc6cf2

Provides a lean entry point for OIDC and SAML authentication routes.
Delegates implementation to sub-modules in routes/sso/.
"""

from fastapi import APIRouter
from starlette.requests import Request as StarletteRequest

from src.core.shared.structured_logging import get_logger

from .common import get_oidc_handler, get_saml_handler, handle_sso_error
from .oidc import router as oidc_router
from .saml import router as saml_router
from .workos import router as workos_router

# Configure logging
logger = get_logger(__name__)
from src.core.shared.constants import CONSTITUTIONAL_HASH

# Create main SSO router with versioned prefix
# API versioning: URL-path versioning with /api/v1/ prefix
router = APIRouter(prefix="/api/v1/sso", tags=["SSO"])

# Export common handlers for tests
__all__ = ["get_oidc_handler", "get_saml_handler", "handle_sso_error", "router"]

# Include sub-routers
router.include_router(oidc_router, prefix="/oidc")
router.include_router(saml_router, prefix="/saml")
router.include_router(workos_router, prefix="/workos")


@router.get("/session")
async def get_session_info(request: StarletteRequest):
    """Get current session information."""
    user = request.session.get("user")
    return {
        "authenticated": user is not None,
        "user": user,
    }
