"""Thin public ACGS namespace backed by ``acgs_lite``."""

from __future__ import annotations

from ._version import VERSION as __version__
from acgs_lite.audit import AuditEntry, AuditLog
from acgs_lite.constitution import Constitution, Rule, Severity
from acgs_lite.engine import GovernanceEngine, ValidationResult, Violation
from acgs_lite.errors import ConstitutionalViolationError
from acgs_lite.fail_closed import fail_closed
from acgs_lite.maci import MACIEnforcer, MACIRole

__all__ = [
    "AuditEntry",
    "AuditLog",
    "Constitution",
    "ConstitutionalViolationError",
    "GovernanceEngine",
    "MACIEnforcer",
    "MACIRole",
    "Rule",
    "Severity",
    "ValidationResult",
    "Violation",
    "fail_closed",
    "__version__",
]


def __getattr__(name: str) -> object:
    """Preserve legacy optional OpenShell access for existing acgs-lite tests."""
    if name == "create_openshell_governance_app":
        from acgs_lite import create_openshell_governance_app

        return create_openshell_governance_app
    if name == "create_openshell_governance_router":
        from acgs_lite import create_openshell_governance_router

        return create_openshell_governance_router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
