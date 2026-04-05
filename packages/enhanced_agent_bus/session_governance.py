"""
Backward-compatibility shims for legacy session governance exceptions.
Constitutional Hash: 608508a9bd224290

This module was previously the home for session governance implementation.
The implementation moved, but these exception symbols are kept for import
compatibility with existing consumers.
"""

from enhanced_agent_bus._compat.errors import ACGSBaseError


class SessionGovernanceError(ACGSBaseError):
    """Base exception for legacy session governance errors."""

    http_status_code = 500
    error_code = "SESSION_GOVERNANCE_ERROR"


class SessionNotFoundError(SessionGovernanceError):
    """Raised when a legacy session governance session cannot be found."""

    http_status_code = 404
    error_code = "SESSION_NOT_FOUND"


class PolicyResolutionError(SessionGovernanceError):
    """Raised when policy resolution fails in legacy session governance flows."""

    http_status_code = 500
    error_code = "POLICY_RESOLUTION_ERROR"


__all__ = [
    "PolicyResolutionError",
    "SessionGovernanceError",
    "SessionNotFoundError",
]
