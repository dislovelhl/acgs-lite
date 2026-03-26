"""
OpenEvolve Governance Adapter
Constitutional Hash: 608508a9bd224290

Integrates AI evolution systems (OpenEvolve and compatibles) with the ACGS-2
constitutional governance framework.

Public surface::

    from enhanced_agent_bus.openevolve_adapter import (
        EvolutionCandidate,
        MutationRecord,
        VerificationPayload,
        RiskTier,
        RolloutStage,
        ConstitutionalFitness,
        FitnessResult,
        ConstitutionalVerifier,
        GovernedEvolver,
        EvolveResult,
        RolloutController,
        RolloutDecision,
        TierConstraints,
    )
"""

from .candidate import (
    EvolutionCandidate,
    MutationRecord,
    RiskTier,
    RolloutStage,
    VerificationPayload,
)
from .cascade import CascadeEvaluator, CascadeResult, CascadeStage
from .evolver import ConstitutionalVerifier, EvolveResult, GovernedEvolver
from .fitness import ConstitutionalFitness, FitnessResult
from .integration import EvolutionMessageHandler, wire_into_processor
from .rollout import RolloutController, RolloutDecision, TierConstraints

__all__ = [
    # candidate
    "EvolutionCandidate",
    "MutationRecord",
    "RiskTier",
    "RolloutStage",
    "VerificationPayload",
    # fitness
    "ConstitutionalFitness",
    "FitnessResult",
    # evolver
    "ConstitutionalVerifier",
    "EvolveResult",
    "GovernedEvolver",
    # rollout
    "RolloutController",
    "RolloutDecision",
    "TierConstraints",
    # cascade
    "CascadeEvaluator",
    "CascadeResult",
    "CascadeStage",
    # integration
    "EvolutionMessageHandler",
    "wire_into_processor",
]
