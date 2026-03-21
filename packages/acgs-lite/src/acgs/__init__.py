"""ACGS: Constitutional AI Governance for Any Agent.

This module re-exports the full acgs_lite public API so users can write:

    from acgs import Constitution, GovernedAgent

Constitutional Hash: cdd01ef066bc6cf2
"""

from acgs_lite import (  # noqa: F401
    AcknowledgedTension,
    AuditEntry,
    AuditLog,
    BatchValidationResult,
    Constitution,
    ConstitutionBuilder,
    ConstitutionalViolationError,
    GovernanceEngine,
    GovernanceError,
    GovernedAgent,
    GovernedCallable,
    LicenseInfo,
    LicenseManager,
    MACIEnforcer,
    MACIRole,
    MACIViolationError,
    Rule,
    RuleSnapshot,
    RuleSynthesisProvider,
    Severity,
    Tier,
    ValidationResult,
    __constitutional_hash__,
    __version__,
    set_license,
)

__all__ = [
    "Constitution",
    "ConstitutionBuilder",
    "Rule",
    "RuleSynthesisProvider",
    "AcknowledgedTension",
    "RuleSnapshot",
    "Severity",
    "GovernanceEngine",
    "ValidationResult",
    "BatchValidationResult",
    "GovernedAgent",
    "GovernedCallable",
    "AuditLog",
    "AuditEntry",
    "MACIRole",
    "MACIEnforcer",
    "ConstitutionalViolationError",
    "GovernanceError",
    "MACIViolationError",
    "set_license",
    "LicenseInfo",
    "LicenseManager",
    "Tier",
    "__version__",
    "__constitutional_hash__",
]
