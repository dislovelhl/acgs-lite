"""
ACGS-2 Pytest Fixtures for Executable Specifications
Constitutional Hash: 608508a9bd224290

Provides reusable fixtures for specification-based testing across all
architectural layers.
"""

from .architecture import architecture_context, layer_context
from .constitutional import constitutional_hash, hash_validator
from .governance import consensus_checker, policy_verifier
from .observability import metrics_registry, timeout_budget_manager, tracing_context
from .resilience import chaos_controller, circuit_breaker, saga_manager
from .temporal import causal_validator, timeline
from .verification import maci_framework, z3_solver_context

__all__ = [
    # Architecture
    "architecture_context",
    "causal_validator",
    "chaos_controller",
    # Resilience
    "circuit_breaker",
    # Governance
    "consensus_checker",
    # Constitutional
    "constitutional_hash",
    "hash_validator",
    "layer_context",
    # Verification
    "maci_framework",
    "metrics_registry",
    "policy_verifier",
    "saga_manager",
    # Temporal
    "timeline",
    # Observability
    "timeout_budget_manager",
    "tracing_context",
    "z3_solver_context",
]
