"""
ACGS-2 Session Governance - Package Initialization
Constitutional Hash: 608508a9bd224290

Re-exports all public symbols for backward compatibility.
"""

# Re-export endpoint handlers for direct use if needed
from .endpoints import (
    create_session,
    delete_session,
    extend_session_ttl,
    get_session,
    get_session_metrics,
    select_session_policies,
    update_session_governance,
)
from .models import (
    CreateSessionRequest,
    ErrorResponse,
    PolicySelectionRequest,
    PolicySelectionResponse,
    SelectedPolicy,
    SessionListResponse,
    SessionMetricsResponse,
    SessionResponse,
    UpdateGovernanceRequest,
)
from .router import (
    get_session_manager,
    init_session_manager,
    router,
    shutdown_session_manager,
)

__all__ = [
    # Request models
    "CreateSessionRequest",
    "ErrorResponse",
    "PolicySelectionRequest",
    "PolicySelectionResponse",
    "SelectedPolicy",
    "SessionListResponse",
    "SessionMetricsResponse",
    # Response models
    "SessionResponse",
    "UpdateGovernanceRequest",
    # Endpoint handlers (for direct invocation)
    "create_session",
    "delete_session",
    "extend_session_ttl",
    "get_session",
    "get_session_manager",
    "get_session_metrics",
    "init_session_manager",
    # Router and lifecycle
    "router",
    "select_session_policies",
    "shutdown_session_manager",
    "update_session_governance",
]
