"""
ACGS-2 Enhanced Agent Bus - Agent Behavioral Contract Models
Constitutional Hash: 608508a9bd224290

Pydantic v2 models implementing formal agent behavioral contracts C=(P,I,G,R)
per arXiv:2602.22302.  Each component captures a distinct facet of an agent's
governance contract:

- ContractPermissions (P) — allowed actions / resources / impact ceiling
- ContractInstructions (I) — behavioral directives and priority ordering
- ContractGoals (G) — objectives and measurable success criteria
- ContractRestrictions (R) — prohibited actions / resources / autonomy cap
- AgentBehavioralContract — composite C=(P,I,G,R) bound to an agent_id
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"


class ContractPermissions(BaseModel):
    """What the agent is allowed to do.

    Attributes:
        allowed_actions: Explicit list of permitted action identifiers.
        allowed_resources: Resources the agent may access.
        max_impact_score: Ceiling on the agent's impact score (0.0-1.0).
    """

    allowed_actions: list[str] = Field(default_factory=list)
    allowed_resources: list[str] = Field(default_factory=list)
    max_impact_score: float = Field(default=1.0, ge=0.0, le=1.0)


class ContractInstructions(BaseModel):
    """Behavioral directives the agent must follow.

    Attributes:
        directives: Ordered list of behavioral directives.
        priority_order: Explicit ordering of directive priority (highest first).
    """

    directives: list[str] = Field(default_factory=list)
    priority_order: list[str] = Field(default_factory=list)


class ContractGoals(BaseModel):
    """What the agent should achieve.

    Attributes:
        objectives: High-level objectives the agent is tasked with.
        success_criteria: Measurable criteria for objective completion.
    """

    objectives: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class ContractRestrictions(BaseModel):
    """Hard constraints the agent must not violate.

    Attributes:
        prohibited_actions: Actions the agent must never perform.
        prohibited_resources: Resources the agent must never access.
        max_autonomy_level: Cap on the agent's autonomy tier (0-5).
    """

    prohibited_actions: list[str] = Field(default_factory=list)
    prohibited_resources: list[str] = Field(default_factory=list)
    max_autonomy_level: int = Field(default=3, ge=0, le=5)


class AgentBehavioralContract(BaseModel):
    """Formal agent behavioral contract C=(P,I,G,R) per arXiv:2602.22302.

    Binds a contract to a specific ``agent_id`` and anchors it to the
    constitutional hash for governance traceability.

    Attributes:
        agent_id: Unique identifier of the governed agent.
        permissions: The P component — what the agent may do.
        instructions: The I component — behavioral directives.
        goals: The G component — objectives to achieve.
        restrictions: The R component — hard constraints.
        constitutional_hash: Must match the active constitutional hash.
        version: Semantic version of this contract definition.
        effective_from: ISO-8601 timestamp when the contract takes effect.
        created_at: ISO-8601 timestamp when the contract was created.
    """

    agent_id: str
    permissions: ContractPermissions = Field(default_factory=ContractPermissions)
    instructions: ContractInstructions = Field(default_factory=ContractInstructions)
    goals: ContractGoals = Field(default_factory=ContractGoals)
    restrictions: ContractRestrictions = Field(default_factory=ContractRestrictions)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    version: str = "1.0.0"
    effective_from: str | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
