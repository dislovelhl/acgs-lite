"""ACGS: Constitutional AI Governance for Any Agent.

Copyright (C) 2024-2026 ACGS Contributors
Licensed under AGPL-3.0-or-later. See LICENSE for details.
Commercial license available at https://acgs.ai for proprietary use.

Constitutional Hash: 608508a9bd224290

Usage::

    from acgs import Constitution, GovernedAgent

    constitution = Constitution.from_yaml("rules.yaml")
    agent = GovernedAgent(my_agent, constitution=constitution)
    result = agent.run("process this request")
"""

from acgs_lite.audit import AuditEntry, AuditLog
from acgs_lite.constitution import (
    AcknowledgedTension,
    Constitution,
    ConstitutionBuilder,
    Rule,
    RuleSnapshot,
    RuleSynthesisProvider,
    Severity,
)
from acgs_lite.engine import BatchValidationResult, GovernanceEngine, ValidationResult
from acgs_lite.errors import (
    ConstitutionalViolationError,
    GovernanceError,
    MACIViolationError,
)
from acgs_lite.governed import GovernedAgent, GovernedCallable
from acgs_lite.licensing import LicenseInfo, LicenseManager, Tier
from acgs_lite.maci import MACIEnforcer, MACIRole
from acgs_lite.openshell import (
    ActionContext,
    ActionEnvelope,
    ActionPayloadSummary,
    ActionRequirements,
    ActionType,
    ActorRef,
    ActorRole,
    ApprovalReviewRequest,
    ApprovalReviewResponse,
    ApprovalSubmission,
    AuditEvent,
    AuditEventType,
    ComplianceResult,
    ComplianceStatus,
    DecisionType,
    ExecutionOutcome,
    ExternalRef,
    GovernanceStateChecksumError,
    GovernanceDecision,
    GovernanceStateBackend,
    GovernanceStateError,
    GovernanceStateMigrationError,
    GovernanceStateObservabilityHook,
    GovernanceStateVersionError,
    InMemoryGovernanceStateBackend,
    JsonFileGovernanceStateBackend,
    OperationType,
    OutcomeStatus,
    RedisGovernanceStateBackend,
    ResourceRef,
    RiskLevel,
    SQLiteGovernanceStateBackend,
    create_openshell_governance_app,
    create_openshell_governance_router,
)

__version__ = "2.0.1"


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


__constitutional_hash__ = "608508a9bd224290"

__all__ = [
    # Core
    "Constitution",
    "ConstitutionBuilder",
    "Rule",
    "RuleSynthesisProvider",
    "AcknowledgedTension",
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
    # OpenShell governance integration
    "ActionContext",
    "ActionEnvelope",
    "ActionPayloadSummary",
    "ActionRequirements",
    "ActionType",
    "ActorRef",
    "ActorRole",
    "ApprovalReviewRequest",
    "ApprovalReviewResponse",
    "ApprovalSubmission",
    "AuditEvent",
    "AuditEventType",
    "ComplianceResult",
    "ComplianceStatus",
    "DecisionType",
    "ExecutionOutcome",
    "ExternalRef",
    "GovernanceStateChecksumError",
    "GovernanceDecision",
    "GovernanceStateBackend",
    "GovernanceStateError",
    "GovernanceStateMigrationError",
    "GovernanceStateObservabilityHook",
    "GovernanceStateVersionError",
    "InMemoryGovernanceStateBackend",
    "JsonFileGovernanceStateBackend",
    "OperationType",
    "OutcomeStatus",
    "RedisGovernanceStateBackend",
    "ResourceRef",
    "RiskLevel",
    "SQLiteGovernanceStateBackend",
    "create_openshell_governance_app",
    "create_openshell_governance_router",
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
