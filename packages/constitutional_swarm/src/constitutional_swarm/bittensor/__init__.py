"""Bittensor subnet integration layer for constitutional_swarm.

Bridges constitutional_swarm primitives (AgentDNA, ConstitutionalMesh,
GovernanceManifold, SwarmExecutor) to Bittensor's miner/validator protocol.

Phase 1 — Protocol Bridge (complete):
  Synapses, Miner, Validator, SN Owner, Protocol types, ConstitutionSync

Phase 2 — On-Chain + Privacy:
  ChainAnchor, ProofEvidence, AnchorRecord

Phase 3 — Precedent Feedback Loop:
  PrecedentStore, PrecedentRecord, RetrievalResult

Requires: bittensor (optional dependency, lazy-imported at deployment time).
"""

# Phase 1: Protocol Bridge
from constitutional_swarm.bittensor.synapses import (
    DeliberationSynapse,
    JudgmentSynapse,
    ValidationSynapse,
)
from constitutional_swarm.bittensor.protocol import (
    EscalationType,
    MinerConfig,
    MinerTier,
    SubnetMetrics,
    TIER_TAO_MULTIPLIER,
    TIER_REQUIREMENTS,
    ValidatorConfig,
)
from constitutional_swarm.bittensor.miner import (
    ConstitutionalMiner,
    ConstitutionMismatchError,
    DNAPreCheckFailedError,
    MinerStats,
)
from constitutional_swarm.bittensor.validator import (
    ConstitutionalValidator,
    ValidatorStats,
)
from constitutional_swarm.bittensor.subnet_owner import (
    EscalatedCase,
    PrecedentRecord as SubnetPrecedentRecord,
    SubnetOwner,
)
from constitutional_swarm.bittensor.constitution_sync import (
    ConstitutionDistributor,
    ConstitutionReceiver,
    ConstitutionSyncMessage,
    ConstitutionVersionRecord,
    SyncResult,
)

# Phase 2: On-Chain + Privacy
from constitutional_swarm.bittensor.chain_anchor import (
    AnchorRecord,
    ChainAnchor,
    InMemorySubmitter,
    ProofEvidence,
)

# Phase 3: Precedent Feedback Loop
from constitutional_swarm.bittensor.precedent_store import (
    PrecedentMatch,
    PrecedentRecord,
    PrecedentStore,
    RetrievalResult,
)
from constitutional_swarm.bittensor.threshold_updater import (
    BayesianThresholdUpdater,
    DEFAULT_WEIGHTS,
    DimensionEvidence,
    UpdateCycle,
    WeightUpdate,
)
from constitutional_swarm.bittensor.rule_codifier import (
    PrecedentCluster,
    RuleCandidate,
    RuleCandidateStatus,
    RuleCodifier,
)

# Phase 4: Authenticity Detection
from constitutional_swarm.bittensor.authenticity_detector import (
    AuthenticityDetector,
    AuthenticityDimension,
    AuthenticityScore,
    DimensionScore,
)

# Phase 5: Miner Qualification Tiers
from constitutional_swarm.bittensor.tier_manager import (
    MinerPerformance,
    RoutingResult,
    TaskComplexity,
    TierManager,
    TierPromotion,
)

# Phase 2.2: Compliance Certificates
from constitutional_swarm.bittensor.compliance_certificate import (
    AuditPeriod,
    CertificateIssuer,
    CertificateStatus,
    ComplianceCertificate,
    ComplianceSnapshot,
    HMACProver,
    ProofType,
    ZKPStubProver,
)

# Phase 2.3: Arweave Audit Log
from constitutional_swarm.bittensor.arweave_audit_log import (
    AuditBatch,
    AuditDecisionType,
    AuditLogEntry,
    AuditLogReceipt,
    ArweaveAuditLogger,
    InMemoryArweaveClient,
    verify_merkle_path,
)

# Phase 2.4: NMC Multi-Miner Protocol
from constitutional_swarm.bittensor.nmc_protocol import (
    ConsensusJudgment,
    NMCCoordinator,
    NMCSession,
    NMCSessionState,
    SybilFlag,
    SynthesisMethod,
)

# Economic Model: Emission Calculator
from constitutional_swarm.bittensor.emission_calculator import (
    DEFAULT_EMISSION_WEIGHTS,
    EmissionCalculator,
    EmissionCycle,
    EmissionWeights,
    MinerEmissionInput,
)

# Governance Coordinator (acgs-lite ↔ subnet bridge)
from constitutional_swarm.bittensor.governance_coordinator import (
    AuditCycleResult,
    CoordinatorConfig,
    GovernanceCoordinator,
)

# bt.Synapse Adapter Layer (testnet protocol bridge)
from constitutional_swarm.bittensor.synapse_adapter import (
    GovernanceDeliberation,
    HAS_BITTENSOR,
    bt_to_deliberation,
    bt_to_judgment,
    deliberation_to_bt,
    judgment_to_bt,
)
from constitutional_swarm.bittensor.axon_server import MinerAxonServer
from constitutional_swarm.bittensor.dendrite_client import ValidatorDendriteClient

__all__ = [
    # Phase 1 — Protocol Bridge
    "ConstitutionMismatchError",
    "ConstitutionalMiner",
    "ConstitutionalValidator",
    "DeliberationSynapse",
    "DNAPreCheckFailedError",
    "EscalatedCase",
    "EscalationType",
    "JudgmentSynapse",
    "MinerConfig",
    "MinerStats",
    "MinerTier",
    "SubnetMetrics",
    "SubnetOwner",
    "SubnetPrecedentRecord",
    "TIER_TAO_MULTIPLIER",
    "TIER_REQUIREMENTS",
    "ValidatorConfig",
    "ValidatorStats",
    "ValidationSynapse",
    # Phase 1 — Constitution Sync
    "ConstitutionDistributor",
    "ConstitutionReceiver",
    "ConstitutionSyncMessage",
    "ConstitutionVersionRecord",
    "SyncResult",
    # Phase 2 — On-Chain + Privacy
    "AnchorRecord",
    "ChainAnchor",
    "InMemorySubmitter",
    "ProofEvidence",
    # Phase 3 — Precedent Feedback Loop
    "PrecedentMatch",
    "PrecedentRecord",
    "PrecedentStore",
    "RetrievalResult",
    # Phase 3.2 — Bayesian Threshold Updater
    "BayesianThresholdUpdater",
    "DEFAULT_WEIGHTS",
    "DimensionEvidence",
    "UpdateCycle",
    "WeightUpdate",
    # Phase 3.3 — Rule Codifier
    "PrecedentCluster",
    "RuleCandidate",
    "RuleCandidateStatus",
    "RuleCodifier",
    # Phase 4 — Authenticity Detection
    "AuthenticityDetector",
    "AuthenticityDimension",
    "AuthenticityScore",
    "DimensionScore",
    # Phase 5 — Miner Qualification Tiers
    "MinerPerformance",
    "RoutingResult",
    "TaskComplexity",
    "TierManager",
    "TierPromotion",
    # Phase 2.2 — Compliance Certificates
    "AuditPeriod",
    "CertificateIssuer",
    "CertificateStatus",
    "ComplianceCertificate",
    "ComplianceSnapshot",
    "HMACProver",
    "ProofType",
    "ZKPStubProver",
    # Phase 2.3 — Arweave Audit Log
    "AuditBatch",
    "AuditDecisionType",
    "AuditLogEntry",
    "AuditLogReceipt",
    "ArweaveAuditLogger",
    "InMemoryArweaveClient",
    "verify_merkle_path",
    # Phase 2.4 — NMC Multi-Miner Protocol
    "ConsensusJudgment",
    "NMCCoordinator",
    "NMCSession",
    "NMCSessionState",
    "SybilFlag",
    "SynthesisMethod",
    # Economic Model — Emission Calculator
    "DEFAULT_EMISSION_WEIGHTS",
    "EmissionCalculator",
    "EmissionCycle",
    "EmissionWeights",
    "MinerEmissionInput",
    # Governance Coordinator
    "AuditCycleResult",
    "CoordinatorConfig",
    "GovernanceCoordinator",
    # bt.Synapse Adapter Layer
    "GovernanceDeliberation",
    "HAS_BITTENSOR",
    "MinerAxonServer",
    "ValidatorDendriteClient",
    "bt_to_deliberation",
    "bt_to_judgment",
    "deliberation_to_bt",
    "judgment_to_bt",
]
