"""ACGS-Lite: Constitutional AI Governance for Any Agent.

Constitutional Hash: cdd01ef066bc6cf2

Usage::

    from acgs_lite import Constitution, GovernedAgent

    constitution = Constitution.from_yaml("rules.yaml")
    agent = GovernedAgent(my_agent, constitution=constitution)
    result = agent.run("process this request")
"""

from acgs_lite.audit import AuditEntry, AuditLog
from acgs_lite.constitution import Constitution, ConstitutionBuilder, Rule, RuleSnapshot, Severity
from acgs_lite.engine import BatchValidationResult, GovernanceEngine, ValidationResult
from acgs_lite.errors import (
    ConstitutionalViolationError,
    GovernanceError,
    MACIViolationError,
)
from acgs_lite.governed import GovernedAgent, GovernedCallable
from acgs_lite.licensing import LicenseInfo, LicenseManager, Tier
from acgs_lite.maci import MACIEnforcer, MACIRole

__version__ = "0.2.0"


def set_license(key: str) -> LicenseInfo:
    """Activate a license key for this process.

    Args:
        key: License key in ACGS-{TIER}-{data} format.

    Returns:
        LicenseInfo with tier and expiry details.

    Example::

        import acgs_lite
        acgs_lite.set_license("ACGS-PRO-...")
    """
    return LicenseManager().set_license(key)


__constitutional_hash__ = "cdd01ef066bc6cf2"

__all__ = [
    # Core
    "Constitution",
    "ConstitutionBuilder",
    "Rule",
    "RuleSnapshot",
    "Severity",
    # Engine
    "GovernanceEngine",
    "ValidationResult",
    "BatchValidationResult",
    # Wrappers
    "GovernedAgent",
    "GovernedCallable",
    # Audit
    "AuditLog",
    "AuditEntry",
    # MACI
    "MACIRole",
    "MACIEnforcer",
    # Errors
    "ConstitutionalViolationError",
    "GovernanceError",
    "MACIViolationError",
    # Licensing
    "set_license",
    "LicenseInfo",
    "LicenseManager",
    "Tier",
]
