"""
ACGS-2 Enhanced Agent Bus - Agent Behavioral Contracts
Constitutional Hash: 608508a9bd224290

Implements formal agent behavioral contracts C=(P,I,G,R) per arXiv:2602.22302:
- P: Permissions — what the agent is allowed to do
- I: Instructions — behavioral directives the agent must follow
- G: Goals — what the agent should achieve
- R: Restrictions — hard constraints the agent must not violate

Feature flag: ACGS_ENABLE_ABC_CONTRACTS (advisory mode by default).
"""

from .models import (
    AgentBehavioralContract,
    ContractGoals,
    ContractInstructions,
    ContractPermissions,
    ContractRestrictions,
)
from .validator import ContractRegistry, ContractValidationResult, ContractValidator

__all__ = [
    "AgentBehavioralContract",
    "ContractGoals",
    "ContractInstructions",
    "ContractPermissions",
    "ContractRegistry",
    "ContractRestrictions",
    "ContractValidationResult",
    "ContractValidator",
]
