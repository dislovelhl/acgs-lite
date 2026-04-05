"""
ACGS-2 Enhanced Agent Bus - Middlewares Package
Constitutional Hash: 608508a9bd224290

Consolidated middleware package. Contains:
- session_extraction: Session context extraction from requests
- security: AI guardrails and security middleware
- batch/: Batch processing pipeline middlewares
"""

# Re-export session extraction components for convenience
from .session_extraction import (
    CONSTITUTIONAL_HASH,
    SESSION_ID_HEADER,
    TENANT_ID_HEADER,
    SessionContext,
    SessionContextDependency,
    SessionExtractionMiddleware,
    SessionGovernanceDependency,
    extract_session_id_from_request,
    extract_tenant_id_from_request,
    get_optional_session_context,
    get_session_context,
    get_session_governance,
)


def __getattr__(name: str):
    """Lazy import security components to avoid circular import issues."""
    _security_names = {"AIGuardrailsConfig", "SecurityMiddleware"}
    if name in _security_names:
        from .security import AIGuardrailsConfig, SecurityMiddleware

        _map = {
            "AIGuardrailsConfig": AIGuardrailsConfig,
            "SecurityMiddleware": SecurityMiddleware,
        }
        return _map[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Session extraction
    "CONSTITUTIONAL_HASH",
    "SESSION_ID_HEADER",
    "TENANT_ID_HEADER",
    # Security (lazy-loaded)
    "AIGuardrailsConfig",
    "SecurityMiddleware",
    "SessionContext",
    "SessionContextDependency",
    "SessionExtractionMiddleware",
    "SessionGovernanceDependency",
    "extract_session_id_from_request",
    "extract_tenant_id_from_request",
    "get_optional_session_context",
    "get_session_context",
    "get_session_governance",
]
