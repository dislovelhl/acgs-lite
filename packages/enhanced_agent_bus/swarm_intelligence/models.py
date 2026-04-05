"""
Swarm Intelligence Models

All dataclasses for swarm operations.

Constitutional Hash: 608508a9bd224290
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from .enums import AgentState, ConsensusType, TaskPriority


@dataclass
class AgentCapability:
    """Capability definition for agents."""

    name: str
    description: str
    proficiency: float = 1.0  # 0.0 to 1.0
    cost_factor: float = 1.0  # Resource cost multiplier
    max_concurrent: int = 1  # Max concurrent tasks with this capability


@dataclass
class SwarmTask:
    """Task to be executed by the swarm."""

    id: str
    description: str
    required_capabilities: list[str]
    priority: TaskPriority = TaskPriority.NORMAL
    dependencies: list[str] = field(default_factory=list)
    timeout_seconds: int = 300
    retry_count: int = 0
    max_retries: int = 3
    constitutional_hash: str = CONSTITUTIONAL_HASH
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    assigned_agent: str | None = None
    result: object | None = None
    error: str | None = None


@dataclass
class SwarmAgent:
    """Agent in the swarm."""

    id: str
    name: str
    capabilities: list[AgentCapability]
    state: AgentState = AgentState.INITIALIZING
    current_task: str | None = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_execution_time: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_active: datetime = field(default_factory=lambda: datetime.now(UTC))
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class ConsensusProposal:
    """Proposal for consensus voting."""

    id: str
    proposer_id: str
    action: str
    context: JSONDict
    votes: dict[str, bool] = field(default_factory=dict)
    required_type: ConsensusType = ConsensusType.MAJORITY
    deadline: datetime = field(default_factory=lambda: datetime.now(UTC))
    result: bool | None = None
    completed_at: datetime | None = None
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class AgentMessage:
    """Message for inter-agent communication."""

    id: str
    sender_id: str
    recipient_id: str | None  # None for broadcast
    message_type: str
    payload: JSONDict
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class DecompositionPattern:
    """Historical pattern for predictive decomposition."""

    pattern_name: str
    keywords: list[str]
    avg_completion_time: float
    avg_subtasks: int
    success_rate: float
    complexity_score: float  # 1.0-10.0


@dataclass
class MessageEnvelope:
    """Enhanced message envelope with metadata for advanced routing."""

    message: AgentMessage
    priority: int = 5  # 1-10, lower is higher priority
    ttl_seconds: int = 300  # Time-to-live
    persistent: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    delivered_at: datetime | None = None
    expires_at: datetime | None = None

    def __post_init__(self):
        if self.expires_at is None and self.ttl_seconds > 0:
            self.expires_at = self.created_at + timedelta(seconds=self.ttl_seconds)

    def is_expired(self) -> bool:
        """Check if message has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at


__all__ = [
    "AgentCapability",
    "AgentMessage",
    "ConsensusProposal",
    "DecompositionPattern",
    "MessageEnvelope",
    "SwarmAgent",
    "SwarmTask",
]
