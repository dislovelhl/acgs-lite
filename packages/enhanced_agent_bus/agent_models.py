"""
ACGS-2 Enhanced Agent Bus - Agent Models
Constitutional Hash: cdd01ef066bc6cf2

Data models for swarm agents and agent coordination.
Split from models.py for improved maintainability.
"""

from dataclasses import dataclass, field

# Import constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH  # noqa: E402
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.bus_types import JSONDict

from .enums import AgentCapability, TaskType

# Type alias


@dataclass
class SwarmAgent:
    """Agent representation for swarm coordination.

    Constitutional Hash: cdd01ef066bc6cf2
    """

    agent_id: str
    name: str = ""
    agent_type: str = ""
    capabilities: list[AgentCapability] = field(default_factory=list)
    is_active: bool = True
    status: str = "idle"  # idle, assigned, busy, terminated
    current_task: str | None = None
    performance_score: float = 1.0
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def has_capability(self, capability: AgentCapability) -> bool:
        """Check if agent has a specific capability."""
        return capability in self.capabilities

    def can_handle(self, task_type: TaskType) -> bool:
        """Check if agent can handle a specific task type.

        Maps task types to required capabilities and checks if agent has them.
        """
        # Mapping of task types to required capabilities
        capability_map: dict[TaskType, list[AgentCapability]] = {
            TaskType.CODE_GENERATION: [
                AgentCapability.CODE_GENERATION,
                AgentCapability.PYTHON_EXPERT,
                AgentCapability.TYPESCRIPT_EXPERT,
                AgentCapability.RUST_EXPERT,
            ],
            TaskType.CODE_REVIEW: [AgentCapability.CODE_REVIEW],
            TaskType.DEBUGGING: [AgentCapability.CODE_GENERATION, AgentCapability.ANALYSIS],
            TaskType.ARCHITECTURE: [AgentCapability.ARCHITECTURE_DESIGNER],
            TaskType.RESEARCH: [AgentCapability.RESEARCH, AgentCapability.RESEARCH_SPECIALIST],
            TaskType.DOCUMENTATION: [AgentCapability.CREATIVE],
            TaskType.TESTING: [AgentCapability.TEST_AUTOMATION],
            TaskType.DEPLOYMENT: [AgentCapability.INTEGRATION],
            TaskType.OPTIMIZATION: [AgentCapability.PERFORMANCE_OPTIMIZER],
            TaskType.SECURITY_AUDIT: [AgentCapability.SECURITY_SPECIALIST],
            TaskType.CONSTITUTIONAL_VALIDATION: [AgentCapability.CONSTITUTIONAL_VALIDATOR],
            TaskType.WORKFLOW_AUTOMATION: [AgentCapability.ORCHESTRATION],
            TaskType.CODING: [AgentCapability.CODE_GENERATION],
            TaskType.ANALYSIS: [AgentCapability.ANALYSIS],
            TaskType.CREATIVE: [AgentCapability.CREATIVE],
            TaskType.INTEGRATION: [AgentCapability.INTEGRATION],
            TaskType.GOVERNANCE: [AgentCapability.GOVERNANCE],
        }

        required_capabilities = capability_map.get(task_type, [])
        if not required_capabilities:
            return True  # Unknown task types can be handled by any agent

        return any(cap in self.capabilities for cap in required_capabilities)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "agent_type": self.agent_type,
            "capabilities": [c.value for c in self.capabilities],
            "is_active": self.is_active,
            "status": self.status,
            "current_task": self.current_task,
            "performance_score": self.performance_score,
            "constitutional_hash": self.constitutional_hash,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "SwarmAgent":
        """Create from dictionary."""
        capabilities = []
        for cap in list(data.get("capabilities", [])):  # type: ignore[arg-type]
            try:
                if isinstance(cap, AgentCapability):
                    capabilities.append(cap)
                else:
                    capabilities.append(AgentCapability(cap))
            except ValueError:
                pass  # Skip unknown capabilities

        return cls(
            agent_id=str(data["agent_id"]),
            name=str(data.get("name", "")),
            agent_type=str(data.get("agent_type", "")),
            capabilities=capabilities,
            is_active=bool(data.get("is_active", True)),
            status=str(data.get("status", "idle")),
            current_task=str(data["current_task"])
            if data.get("current_task") is not None
            else None,
            performance_score=float(data.get("performance_score", 1.0)),  # type: ignore[arg-type]
            constitutional_hash=str(data.get("constitutional_hash", CONSTITUTIONAL_HASH)),
        )


__all__ = [
    "SwarmAgent",
]
