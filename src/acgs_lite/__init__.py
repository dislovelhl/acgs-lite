"""ACGS: Constitutional AI Governance for Any Agent.

Copyright (C) 2024-2026 ACGS Contributors
Licensed under Apache-2.0. See LICENSE for details.
Commercial license available at https://acgs.ai for proprietary use.

Constitutional Hash: 608508a9bd224290

Usage::

    from acgs import Constitution, GovernedAgent, MACIRole

    constitution = Constitution.from_yaml("rules.yaml")
    agent = GovernedAgent(my_agent, constitution=constitution)
    result = agent.run("process this request")
    # Optional MACI enforcement:
    # agent = GovernedAgent(my_agent, constitution=constitution, maci_role=MACIRole.PROPOSER, enforce_maci=True)
    # result = agent.run("draft change", governance_action="propose")
"""

from acgs_lite._meta import CONSTITUTIONAL_HASH, VERSION
from acgs_lite.audit import (
    AuditBackend,
    AuditEntry,
    AuditLog,
    InMemoryAuditBackend,
    JSONLAuditBackend,
)
from acgs_lite.circuit_breaker import GovernanceCircuitBreaker, GovernanceHaltError
from acgs_lite.constitution import (
    AcknowledgedTension,
    ActivationRecord,
    BundleStatus,
    BundleStore,
    ConcurrentLifecycleError,
    Constitution,
    ConstitutionBuilder,
    ConstitutionBundle,
    ConstitutionLifecycle,
    GovernanceMemoryPrecedentHit,
    GovernanceMemoryReport,
    GovernanceMemoryRetriever,
    GovernanceMemorySummary,
    InMemoryBundleStore,
    InMemoryLifecycleAuditSink,
    LifecycleAuditSink,
    LifecycleError,
    LifecycleEvidenceError,
    LifecycleEvidenceRecord,
    Rule,
    RuleSnapshot,
    RuleSynthesisProvider,
    Severity,
    StatusTransition,
)
from acgs_lite.constitution.claim_lifecycle import (
    CaseConfig,
    CaseManager,
    CaseRecord,
    CaseState,
    TransitionRecord,
)
from acgs_lite.constitution.rule import ViolationAction
from acgs_lite.constitution.spot_check import (
    AuditPolicy,
    CompletedCase,
    SpotCheckAuditor,
    SpotCheckResult,
    TrustAdjustment,
    ValidatorAssessment,
    ValidatorProfile,
)
from acgs_lite.constitution.trust_score import (
    TrustConfig,
    TrustEvent,
    TrustScoreManager,
    TrustTier,
)
from acgs_lite.constitution.validator_selection import (
    SelectionPolicy,
    SelectionResult,
    ValidatorPool,
    ValidatorSelector,
)
from acgs_lite.engine import BatchValidationResult, GovernanceEngine, ValidationResult
from acgs_lite.errors import (
    ConstitutionalViolationError,
    GovernanceError,
    MACIViolationError,
)
from acgs_lite.events import EventBus, GovernanceEvent, get_event_bus
from acgs_lite.fail_closed import fail_closed as fail_closed
from acgs_lite.formal.smt_gate import NullVerificationGate, VerificationResult, Z3VerificationGate
from acgs_lite.governed import GovernedAgent, GovernedCallable
from acgs_lite.lean_verify import (
    LEAN_AVAILABLE,
    MISTRAL_AVAILABLE,
    LeanstralVerifier,
    LeanVerifyResult,
    ProofCertificate,
)
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
    GovernanceDecision,
    GovernanceStateBackend,
    GovernanceStateChecksumError,
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
from acgs_lite.provenance import ProvenanceNode, ProvenanceRecord
from acgs_lite.scoring import ConstitutionalImpactScorer, RuleBasedScorer, score_impact
from acgs_lite.trajectory import (
    CumulativeValueRule,
    FrequencyThresholdRule,
    InMemoryTrajectoryStore,
    SensitiveToolSequenceRule,
    TrajectoryMonitor,
    TrajectorySession,
    TrajectoryViolation,
)
from acgs_lite.z3_verify import (
    Z3_AVAILABLE,
    Z3_RISK_THRESHOLD,
    Z3ConstraintVerifier,
    Z3VerifyResult,
)

__version__ = VERSION


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


__constitutional_hash__ = CONSTITUTIONAL_HASH

__all__ = [
    # Core
    "Constitution",
    "ConstitutionBuilder",
    "ConstitutionBundle",
    "Rule",
    "RuleSynthesisProvider",
    "AcknowledgedTension",
    "ActivationRecord",
    "GovernanceMemoryPrecedentHit",
    "GovernanceMemoryReport",
    "GovernanceMemoryRetriever",
    "GovernanceMemorySummary",
    "BundleStatus",
    "BundleStore",
    "InMemoryBundleStore",
    "RuleSnapshot",
    "Severity",
    "StatusTransition",
    "ViolationAction",
    # Spot-check audit / governance lifecycle
    "AuditPolicy",
    "CompletedCase",
    "SpotCheckAuditor",
    "SpotCheckResult",
    "TrustAdjustment",
    "ValidatorAssessment",
    "ValidatorProfile",
    "CaseConfig",
    "CaseManager",
    "CaseRecord",
    "CaseState",
    "TransitionRecord",
    "TrustConfig",
    "TrustEvent",
    "TrustScoreManager",
    "TrustTier",
    "SelectionPolicy",
    "SelectionResult",
    "ValidatorPool",
    "ValidatorSelector",
    # Engine
    "GovernanceEngine",
    "ValidationResult",
    "BatchValidationResult",
    # Wrappers
    "GovernedAgent",
    "GovernedCallable",
    "VerificationResult",
    "Z3VerificationGate",
    "NullVerificationGate",
    "ProvenanceRecord",
    "ProvenanceNode",
    "EventBus",
    "GovernanceEvent",
    "get_event_bus",
    # Audit
    "AuditLog",
    "AuditEntry",
    "AuditBackend",
    "InMemoryAuditBackend",
    "JSONLAuditBackend",
    # Circuit breaker (Article 14 kill-switch)
    "GovernanceCircuitBreaker",
    "GovernanceHaltError",
    # MACI
    "MACIRole",
    "MACIEnforcer",
    # Scoring
    "ConstitutionalImpactScorer",
    "RuleBasedScorer",
    "score_impact",
    # Runtime trajectory monitoring
    "TrajectoryMonitor",
    "TrajectorySession",
    "TrajectoryViolation",
    "InMemoryTrajectoryStore",
    "FrequencyThresholdRule",
    "CumulativeValueRule",
    "SensitiveToolSequenceRule",
    # Z3 formal verification
    "Z3ConstraintVerifier",
    "Z3VerifyResult",
    "Z3_AVAILABLE",
    "Z3_RISK_THRESHOLD",
    # Leanstral formal verification (Lean 4 proof certificates)
    "LeanstralVerifier",
    "LeanVerifyResult",
    "ProofCertificate",
    "MISTRAL_AVAILABLE",
    "LEAN_AVAILABLE",
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
