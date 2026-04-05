"""
Meta-Orchestrator Models Module
================================

Data models for the Meta-Orchestrator system including task results,
agent definitions, and memory tier structures.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

# Re-export from models.py for consistency
from enhanced_agent_bus.models import AgentCapability, TaskComplexity, TaskType

__all__ = [
    "AgentCapability",
    "MemoryEntry",
    "MemoryTier",
    "SwarmAgent",
    # Re-exports from models.py
    "TaskComplexity",
    "TaskResult",
    "TaskType",
]


from ..coordinators.task_coordinator import TaskResult


@dataclass
class SwarmAgent:
    """Represents a spawned swarm agent."""

    agent_id: str
    agent_type: str
    capabilities: list[AgentCapability]
    status: str = "idle"
    current_task: str | None = None
    performance_score: float = 1.0

    def can_handle(self, task_type: TaskType) -> bool:
        """Check if agent can handle given task type."""
        capability_mapping = {
            TaskType.CODE_GENERATION: [
                AgentCapability.PYTHON_EXPERT,
                AgentCapability.TYPESCRIPT_EXPERT,
                AgentCapability.RUST_EXPERT,
            ],
            TaskType.SECURITY_AUDIT: [
                AgentCapability.SECURITY_SPECIALIST,
                AgentCapability.CONSTITUTIONAL_VALIDATOR,
            ],
            TaskType.RESEARCH: [AgentCapability.RESEARCH_SPECIALIST],
            TaskType.ARCHITECTURE: [AgentCapability.ARCHITECTURE_DESIGNER],
            TaskType.TESTING: [AgentCapability.TEST_AUTOMATION],
            TaskType.OPTIMIZATION: [AgentCapability.PERFORMANCE_OPTIMIZER],
            TaskType.CONSTITUTIONAL_VALIDATION: [AgentCapability.CONSTITUTIONAL_VALIDATOR],
        }
        required = capability_mapping.get(task_type, [])
        return any(cap in self.capabilities for cap in required) if required else True


class MemoryTier(Enum):
    """SAFLA Neural Memory Tiers."""

    VECTOR = "vector"  # Semantic understanding
    EPISODIC = "episodic"  # Experience storage
    SEMANTIC = "semantic"  # Knowledge base
    WORKING = "working"  # Active context


@dataclass
class MemoryEntry:
    """Entry in the neural memory system."""

    tier: MemoryTier
    key: str
    value: object
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    confidence: float = 1.0
    access_count: int = 0
    ttl_seconds: int | None = None
