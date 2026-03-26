"""
Swarm Intelligence Enums

Constitutional Hash: 608508a9bd224290
"""

from enum import Enum, auto


class AgentState(Enum):
    """Agent lifecycle states."""

    INITIALIZING = auto()
    READY = auto()
    BUSY = auto()
    WAITING = auto()
    ERROR = auto()
    TERMINATED = auto()


class TaskPriority(Enum):
    """Task priority levels for scheduling."""

    CRITICAL = 1  # Immediate execution
    HIGH = 2  # Next in queue
    NORMAL = 3  # Standard processing
    LOW = 4  # Background processing
    DEFERRED = 5  # When resources available


class ConsensusType(Enum):
    """Consensus mechanism types."""

    MAJORITY = "majority"  # Simple majority (>50%)
    SUPERMAJORITY = "supermajority"  # 2/3 majority
    UNANIMOUS = "unanimous"  # All agents agree
    QUORUM = "quorum"  # Minimum threshold met


__all__ = [
    "AgentState",
    "ConsensusType",
    "TaskPriority",
]
