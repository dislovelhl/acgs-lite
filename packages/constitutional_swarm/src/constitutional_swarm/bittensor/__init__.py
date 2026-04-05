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
# Phase 2.3: Arweave Audit Log
from constitutional_swarm.bittensor.arweave_audit_log import (
    ArweaveAuditLogger,
    AuditBatch,
    AuditDecisionType,
    AuditLogEntry,
    AuditLogReceipt,
    InMemoryArweaveClient,
    verify_merkle_path,
)

# Phase 4: Authenticity Detection
from constitutional_swarm.bittensor.authenticity_detector import (
    AuthenticityDetector,
    AuthenticityDimension,
    AuthenticityScore,
    DimensionScore,
)
from constitutional_swarm.bittensor.axon_server import MinerAxonServer

# Phase 2: On-Chain + Privacy
from constitutional_swarm.bittensor.chain_anchor import (
    AnchorRecord,
    ChainAnchor,
    InMemorySubmitter,
    ProofEvidence,
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
from constitutional_swarm.bittensor.constitution_sync import (
    ConstitutionDistributor,
    ConstitutionReceiver,
    ConstitutionSyncMessage,
    ConstitutionVersionRecord,
    SyncResult,
)
from constitutional_swarm.bittensor.dendrite_client import ValidatorDendriteClient

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
from constitutional_swarm.bittensor.miner import (
    ConstitutionalMiner,
    ConstitutionMismatchError,
    DNAPreCheckFailedError,
    MinerStats,
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

# Phase 3: Precedent Feedback Loop
from constitutional_swarm.bittensor.precedent_store import (
    PrecedentMatch,
    PrecedentRecord,
    PrecedentStore,
    RetrievalResult,
)
from constitutional_swarm.bittensor.protocol import (
    TIER_REQUIREMENTS,
    TIER_TAO_MULTIPLIER,
    EscalationType,
    MinerConfig,
    MinerTier,
    SubnetMetrics,
    ValidatorConfig,
)
from constitutional_swarm.bittensor.rule_codifier import (
    PrecedentCluster,
    RuleCandidate,
    RuleCandidateStatus,
    RuleCodifier,
)
from constitutional_swarm.bittensor.subnet_owner import (
    EscalatedCase,
    SubnetOwner,
)
from constitutional_swarm.bittensor.subnet_owner import (
    PrecedentRecord as SubnetPrecedentRecord,
)

# bt.Synapse Adapter Layer (testnet protocol bridge)
from constitutional_swarm.bittensor.synapse_adapter import (
    HAS_BITTENSOR,
    GovernanceDeliberation,
    bt_to_deliberation,
    bt_to_judgment,
    deliberation_to_bt,
    judgment_to_bt,
)
from constitutional_swarm.bittensor.synapses import (
    DeliberationSynapse,
    JudgmentSynapse,
    ValidationSynapse,
)
from constitutional_swarm.bittensor.threshold_updater import (
    DEFAULT_WEIGHTS,
    BayesianThresholdUpdater,
    DimensionEvidence,
    UpdateCycle,
    WeightUpdate,
)

# Phase 5: Miner Qualification Tiers
from constitutional_swarm.bittensor.tier_manager import (
    MinerPerformance,
    RoutingResult,
    TaskComplexity,
    TierManager,
    TierPromotion,
)
from constitutional_swarm.bittensor.validator import (
    ConstitutionalValidator,
    ValidatorStats,
)

__all__ = [
    # Economic Model — Emission Calculator
    "DEFAULT_EMISSION_WEIGHTS",
    "DEFAULT_WEIGHTS",
    "HAS_BITTENSOR",
    "TIER_REQUIREMENTS",
    "TIER_TAO_MULTIPLIER",
    # Phase 2 — On-Chain + Privacy
    "AnchorRecord",
    "ArweaveAuditLogger",
    # Phase 2.3 — Arweave Audit Log
    "AuditBatch",
    # Governance Coordinator
    "AuditCycleResult",
    "AuditDecisionType",
    "AuditLogEntry",
    "AuditLogReceipt",
    # Phase 2.2 — Compliance Certificates
    "AuditPeriod",
    # Phase 4 — Authenticity Detection
    "AuthenticityDetector",
    "AuthenticityDimension",
    "AuthenticityScore",
    # Phase 3.2 — Bayesian Threshold Updater
    "BayesianThresholdUpdater",
    "CertificateIssuer",
    "CertificateStatus",
    "ChainAnchor",
    "ComplianceCertificate",
    "ComplianceSnapshot",
    # Phase 2.4 — NMC Multi-Miner Protocol
    "ConsensusJudgment",
    # Phase 1 — Constitution Sync
    "ConstitutionDistributor",
    # Phase 1 — Protocol Bridge
    "ConstitutionMismatchError",
    "ConstitutionReceiver",
    "ConstitutionSyncMessage",
    "ConstitutionVersionRecord",
    "ConstitutionalMiner",
    "ConstitutionalValidator",
    "CoordinatorConfig",
    "DNAPreCheckFailedError",
    "DeliberationSynapse",
    "DimensionEvidence",
    "DimensionScore",
    "EmissionCalculator",
    "EmissionCycle",
    "EmissionWeights",
    "EscalatedCase",
    "EscalationType",
    "GovernanceCoordinator",
    # bt.Synapse Adapter Layer
    "GovernanceDeliberation",
    "HMACProver",
    "InMemoryArweaveClient",
    "InMemorySubmitter",
    "JudgmentSynapse",
    "MinerAxonServer",
    "MinerConfig",
    "MinerEmissionInput",
    # Phase 5 — Miner Qualification Tiers
    "MinerPerformance",
    "MinerStats",
    "MinerTier",
    "NMCCoordinator",
    "NMCSession",
    "NMCSessionState",
    # Phase 3.3 — Rule Codifier
    "PrecedentCluster",
    # Phase 3 — Precedent Feedback Loop
    "PrecedentMatch",
    "PrecedentRecord",
    "PrecedentStore",
    "ProofEvidence",
    "ProofType",
    "RetrievalResult",
    "RoutingResult",
    "RuleCandidate",
    "RuleCandidateStatus",
    "RuleCodifier",
    "SubnetMetrics",
    "SubnetOwner",
    "SubnetPrecedentRecord",
    "SybilFlag",
    "SyncResult",
    "SynthesisMethod",
    "TaskComplexity",
    "TierManager",
    "TierPromotion",
    "UpdateCycle",
    "ValidationSynapse",
    "ValidatorConfig",
    "ValidatorDendriteClient",
    "ValidatorStats",
    "WeightUpdate",
    "ZKPStubProver",
    "bt_to_deliberation",
    "bt_to_judgment",
    "deliberation_to_bt",
    "judgment_to_bt",
    "verify_merkle_path",
]
