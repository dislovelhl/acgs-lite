"""
ACGS-2 Deliberation Layer - Vote Event Models
Constitutional Hash: cdd01ef066bc6cf2

Pydantic models for Kafka vote events, audit records, and weighted voting.
"""

from datetime import UTC, datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]


class VoteDecision(str, Enum):  # noqa: UP042
    """Vote decision types."""

    APPROVE = "APPROVE"
    DENY = "DENY"
    ABSTAIN = "ABSTAIN"


class VoteEventType(str, Enum):  # noqa: UP042
    """Types of vote events for audit trail."""

    ELECTION_CREATED = "election_created"
    VOTE_CAST = "vote_cast"
    ELECTION_RESOLVED = "election_resolved"
    ELECTION_EXPIRED = "election_expired"
    ESCALATION_TRIGGERED = "escalation_triggered"


class VoteEvent(BaseModel):
    """
    Vote event published to Kafka vote topic.

    This event represents a single vote cast by an agent in an election.
    """

    election_id: str = Field(..., description="Unique election identifier")
    agent_id: str = Field(..., description="Agent casting the vote")
    decision: VoteDecision = Field(..., description="Vote decision: APPROVE, DENY, or ABSTAIN")
    weight: float = Field(
        1.0, ge=0.0, description="Vote weight (default 1.0, compliance officers may have 2.0)"
    )
    reasoning: str | None = Field(None, description="Optional reasoning for the vote")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence level (0.0 to 1.0)")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Vote timestamp"
    )
    signature: str | None = Field(None, description="HMAC-SHA256 signature for vote integrity")

    model_config = ConfigDict(use_enum_values=True)


class AuditRecord(BaseModel):
    """
    Immutable audit record published to compacted Kafka audit topic.

    All voting events are recorded here with cryptographic signatures
    for immutability verification.
    """

    event_type: VoteEventType = Field(..., description="type of voting event")
    election_id: str = Field(..., description="Election identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Event timestamp"
    )
    signature: str = Field(..., description="HMAC-SHA256 signature for audit record integrity")
    payload: JSONDict = Field(..., description="Event-specific payload data")
    agent_id: str | None = Field(
        None, description="Agent ID if applicable (e.g., for vote_cast events)"
    )

    model_config = ConfigDict(use_enum_values=True)


class WeightedParticipant(BaseModel):
    """
    Participant in an election with configurable vote weight.

    Compliance officers and senior roles may have higher weights
    to reflect their expertise and authority.
    """

    agent_id: str = Field(..., description="Agent identifier")
    weight: float = Field(1.0, ge=0.0, description="Vote weight (default 1.0)")
    role: str | None = Field(
        None, description="Agent role (e.g., 'compliance_officer', 'engineer')"
    )

    model_config = ConfigDict(use_enum_values=True)


class ElectionCreatedEvent(BaseModel):
    """Event published when an election is created."""

    election_id: str
    message_id: str
    strategy: str  # VotingStrategy enum value
    participants: list[WeightedParticipant]
    timeout_seconds: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ElectionResolvedEvent(BaseModel):
    """Event published when an election is resolved."""

    election_id: str
    decision: str  # "APPROVE" or "DENY"
    resolution_reason: str
    votes_count: int
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EscalationEvent(BaseModel):
    """Event published when an election times out and escalates."""

    election_id: str
    message_id: str
    timeout_seconds: int
    escalation_reason: str = "election_timeout"
    escalated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
