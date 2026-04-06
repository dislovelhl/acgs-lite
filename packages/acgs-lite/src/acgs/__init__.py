"""ACGS: Constitutional AI Governance for Any Agent.

Copyright (C) 2024-2026 ACGS Contributors
Licensed under Apache-2.0. See LICENSE for details.
Commercial license available at https://acgs.ai for proprietary use.

This module is the canonical ``acgs`` import namespace. It re-exports the full
``acgs_lite`` public API so users can write::

    from acgs import Constitution, GovernedAgent, MACIRole

    constitution = Constitution.from_yaml("rules.yaml")
    agent = GovernedAgent(my_agent, constitution=constitution)
    result = agent.run("process this request")

``acgs_lite`` remains available as a compatibility import namespace.

Constitutional Hash: 608508a9bd224290
"""

from acgs_lite import (
    AcknowledgedTension,
    ViolationAction,
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
    AuditBackend,
    AuditEntry,
    AuditEvent,
    AuditEventType,
    AuditLog,
    BatchValidationResult,
    ComplianceResult,
    ComplianceStatus,
    Constitution,
    ConstitutionalViolationError,
    ConstitutionBuilder,
    DecisionType,
    ExecutionOutcome,
    ExternalRef,
    GovernanceCircuitBreaker,
    GovernanceDecision,
    GovernanceEngine,
    GovernanceError,
    GovernanceHaltError,
    GovernanceStateBackend,
    GovernanceStateChecksumError,
    GovernanceStateError,
    GovernanceStateMigrationError,
    GovernanceStateObservabilityHook,
    GovernanceStateVersionError,
    GovernedAgent,
    GovernedCallable,
    InMemoryAuditBackend,
    InMemoryGovernanceStateBackend,
    JsonFileGovernanceStateBackend,
    JSONLAuditBackend,
    LicenseInfo,
    LicenseManager,
    MACIEnforcer,
    MACIRole,
    MACIViolationError,
    OperationType,
    OutcomeStatus,
    RedisGovernanceStateBackend,
    ResourceRef,
    RiskLevel,
    Rule,
    RuleSnapshot,
    RuleSynthesisProvider,
    Severity,
    SQLiteGovernanceStateBackend,
    Tier,
    ValidationResult,
    __constitutional_hash__,
    __version__,
    create_openshell_governance_app,
    create_openshell_governance_router,
    set_license,
)

__all__ = [
    # Core
    "Constitution",
    "ConstitutionBuilder",
    "Rule",
    "RuleSynthesisProvider",
    "AcknowledgedTension",
    "RuleSnapshot",
    "Severity",
    "ViolationAction",
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
    "AuditBackend",
    "AuditEvent",
    "AuditEventType",
    "InMemoryAuditBackend",
    "JSONLAuditBackend",
    # Circuit breaker (Article 14 kill-switch)
    "GovernanceCircuitBreaker",
    "GovernanceHaltError",
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
    # Metadata
    "__constitutional_hash__",
    "__version__",
]
