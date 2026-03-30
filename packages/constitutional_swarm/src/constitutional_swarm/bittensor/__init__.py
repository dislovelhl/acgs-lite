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
]
