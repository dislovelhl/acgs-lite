"""
ACGS-2 Executable Specifications Module
Constitutional Hash: 608508a9bd224290

This module provides pytest fixtures and base classes for specification-based
testing following Gojko Adzic's Specification by Example methodology.
"""

from .fixtures import (
    architecture_context,
    chaos_controller,
    circuit_breaker,
    constitutional_hash,
    maci_framework,
    metrics_registry,
    saga_manager,
    timeline,
    timeout_budget_manager,
)

__all__ = [
    "architecture_context",
    "chaos_controller",
    "circuit_breaker",
    "constitutional_hash",
    "maci_framework",
    "metrics_registry",
    "saga_manager",
    "timeline",
    "timeout_budget_manager",
]
