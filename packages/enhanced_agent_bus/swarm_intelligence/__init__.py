"""
Swarm Intelligence Layer v3.0

Advanced multi-agent coordination with:
- Dynamic capability-based agent spawning
- DAG-based task decomposition
- Inter-agent communication protocols
- Consensus mechanisms (Byzantine fault-tolerant)
- Load balancing and fault tolerance
- Constitutional compliance validation

Constitutional Hash: 608508a9bd224290
"""

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

# Core components
from .capabilities import CapabilityMatcher
from .consensus import ConsensusMechanism
from .coordinator import SwarmCoordinator, create_swarm_coordinator

# Enums
from .enums import AgentState, ConsensusType, TaskPriority
from .message_bus import MessageBus

# Models
from .models import (
    AgentCapability,
    AgentMessage,
    ConsensusProposal,
    DecompositionPattern,
    MessageEnvelope,
    SwarmAgent,
    SwarmTask,
)
from .task_decomposer import TaskDecomposer

__all__ = [
    # Constants
    "CONSTITUTIONAL_HASH",
    "AgentCapability",
    "AgentMessage",
    # Enums
    "AgentState",
    "CapabilityMatcher",
    "ConsensusMechanism",
    # Dataclasses
    "ConsensusProposal",
    "ConsensusType",
    "DecompositionPattern",
    "MessageBus",
    "MessageEnvelope",
    "SwarmAgent",
    # Core classes
    "SwarmCoordinator",
    "SwarmTask",
    # Core components
    "TaskDecomposer",
    "TaskPriority",
    # Factory
    "create_swarm_coordinator",
]
