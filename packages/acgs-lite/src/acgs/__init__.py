"""ACGS: Constitutional AI Governance for Any Agent.

Copyright (C) 2024-2026 ACGS Contributors
Licensed under AGPL-3.0-or-later. See LICENSE for details.
Commercial license available at https://acgs.ai for proprietary use.

This module re-exports the full acgs_lite public API so users can write:

    from acgs import Constitution, GovernedAgent

Constitutional Hash: cdd01ef066bc6cf2
"""

from acgs_lite import (
    AcknowledgedTension,
    AuditEntry,
    AuditLog,
    BatchValidationResult,
    Constitution,
    ConstitutionalViolationError,
    ConstitutionBuilder,
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
    "AcknowledgedTension",
    "AuditEntry",
    "AuditLog",
    "BatchValidationResult",
    "Constitution",
    "ConstitutionBuilder",
    "ConstitutionalViolationError",
    "GovernanceEngine",
    "GovernanceError",
    "GovernedAgent",
    "GovernedCallable",
    "LicenseInfo",
    "LicenseManager",
    "MACIEnforcer",
    "MACIRole",
    "MACIViolationError",
    "Rule",
    "RuleSnapshot",
    "RuleSynthesisProvider",
    "Severity",
    "Tier",
    "ValidationResult",
    "__constitutional_hash__",
    "__version__",
    "set_license",
]
