"""
ACGS-2 Layer 2: Verification & Validation
Constitutional Hash: 608508a9bd224290

This module implements the complete Layer 2 verification and validation system
for ACGS-2, combining MACI role separation, SagaLLM transactions, and VeriPlan
(Z3 SMT solver integration) to bypass Godel limitations with formal guarantees.

Key Components:
- MACIVerifier: Role-based verification pipeline (Executive/Legislative/Judicial)
- SagaCoordinator: Compensable operations with LIFO rollback
- Z3PolicyVerifier: Mathematical policy verification with Z3 SMT solver
- ConstitutionalTransition: State transitions with cryptographic proofs

Performance Targets:
- 99.9% transaction consistency
- P99 latency < 5ms for verification operations
- 100% constitutional compliance

References:
- docs/ROADMAP_2025.md Phase 2.1 Layer 2
- MACI role separation prevents Godel bypass attacks
"""

# Constitutional hash for compliance
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from .constitutional_transition import (
    ConstitutionalTransition,
    StateTransitionManager,
    TransitionProof,
    TransitionState,
    create_transition_manager,
)

# Dafny adapter (relocated from verification/ package)
from .dafny_adapter import DafnyVerificationResult
from .maci_verifier import (
    MACIAgentRole,
    MACIVerificationContext,
    MACIVerificationResult,
    MACIVerifier,
    VerificationPhase,
    create_maci_verifier,
)
from .saga_coordinator import (
    SagaCheckpoint,
    SagaCompensation,
    SagaCoordinator,
    SagaState,
    SagaStep,
    create_saga_coordinator,
)
from .verification_pipeline import (
    PipelineConfig,
    PipelineResult,
    VerificationPipeline,
    create_verification_pipeline,
)
from .z3_policy_verifier import (
    PolicyConstraint,
    VerificationProof,
    Z3PolicyVerifier,
    Z3VerificationStatus,
    create_z3_verifier,
)

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    # Constitutional Transition
    "ConstitutionalTransition",
    # Dafny Adapter
    "DafnyVerificationResult",
    "MACIAgentRole",
    "MACIVerificationContext",
    "MACIVerificationResult",
    # MACI Verifier
    "MACIVerifier",
    "PipelineConfig",
    "PipelineResult",
    "PolicyConstraint",
    "SagaCheckpoint",
    "SagaCompensation",
    # Saga Coordinator
    "SagaCoordinator",
    "SagaState",
    "SagaStep",
    "StateTransitionManager",
    "TransitionProof",
    "TransitionState",
    "VerificationPhase",
    # Verification Pipeline
    "VerificationPipeline",
    "VerificationProof",
    # Z3 Policy Verifier
    "Z3PolicyVerifier",
    "Z3VerificationStatus",
    "create_maci_verifier",
    "create_saga_coordinator",
    "create_transition_manager",
    "create_verification_pipeline",
    "create_z3_verifier",
]
