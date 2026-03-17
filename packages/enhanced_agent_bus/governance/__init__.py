"""
ACGS-2 CCAI Democratic Framework - Governance Package
Constitutional Hash: cdd01ef066bc6cf2

This package provides the CCAI (Collective Constitutional AI) democratic governance
framework for constitutional AI governance with democratic deliberation.

Re-exports all public APIs from submodules for backward compatibility.

Modules:
    - models: Data models (Enums, dataclasses)
    - polis_engine: Polis-style deliberation engine
    - democratic_governance: Democratic constitutional governance framework

Constitutional Hash: cdd01ef066bc6cf2
"""

from .democratic_governance import (
    DemocraticConstitutionalGovernance,
    ccai_governance,
    deliberate_on_proposal,
    get_ccai_governance,
)
from .models import (
    CONSTITUTIONAL_HASH,
    ConstitutionalProposal,
    DeliberationPhase,
    DeliberationResult,
    DeliberationStatement,
    OpinionCluster,
    Stakeholder,
    StakeholderGroup,
)
from .polis_engine import PolisDeliberationEngine

__all__ = [
    "CONSTITUTIONAL_HASH",
    "ConstitutionalProposal",
    "DeliberationPhase",
    "DeliberationResult",
    "DeliberationStatement",
    "DemocraticConstitutionalGovernance",
    "OpinionCluster",
    "PolisDeliberationEngine",
    "Stakeholder",
    "StakeholderGroup",
    "ccai_governance",
    "deliberate_on_proposal",
    "get_ccai_governance",
]
