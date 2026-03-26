"""
ACGS-2 Enhanced Agent Bus - API Routes
Constitutional Hash: 608508a9bd224290

This module contains FastAPI router definitions for the Enhanced Agent Bus API.
"""

from .sessions import (
    get_session_manager,
    init_session_manager,
    shutdown_session_manager,
)
from .sessions import (
    router as sessions_router,
)
from .tenants import router as tenants_router

# Import middleware for convenience
try:
    from ..middlewares.session_extraction import (
        SessionContext,
        SessionContextDependency,
        SessionExtractionMiddleware,
        SessionGovernanceDependency,
        get_optional_session_context,
        get_session_context,
        get_session_governance,
    )
except ImportError:
    # Fallback imports when not in package context
    SessionExtractionMiddleware = None
    SessionContext = None
    SessionContextDependency = None
    SessionGovernanceDependency = None
    get_session_context = None
    get_optional_session_context = None
    get_session_governance = None

__all__ = [
    "SessionContext",
    "SessionContextDependency",
    # Session middleware and dependencies
    "SessionExtractionMiddleware",
    "SessionGovernanceDependency",
    "get_optional_session_context",
    "get_session_context",
    "get_session_governance",
    "get_session_manager",
    "init_session_manager",
    # Session router and lifecycle
    "sessions_router",
    "shutdown_session_manager",
    # Tenant router
    "tenants_router",
]
