from __future__ import annotations

from typing import ClassVar
from uuid import uuid4

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import AgentCapability, SwarmAgent, TaskComplexity, TaskType

logger = get_logger(__name__)


class RoutingEngine:
    """
    Decoupled routing engine for MetaOrchestrator.
    Handles task analysis, agent selection, and swarm coordination.

    Constitutional Hash: 608508a9bd224290
    """

    # Mapping of TaskComplexity value to number of agents needed
    COMPLEXITY_TO_AGENTS: ClassVar[dict[str, int]] = {
        "trivial": 1,
        "simple": 1,
        "moderate": 2,
        "complex": 3,
        "visionary": 5,
    }

    def __init__(self, max_swarm_agents: int = 8, constitutional_hash: str = ""):
        self.max_swarm_agents = max_swarm_agents
        self.constitutional_hash = constitutional_hash
        self._active_agents: dict[str, SwarmAgent] = {}

    def _get_agents_for_complexity(self, complexity: TaskComplexity) -> int:
        """Get the number of agents needed for a given complexity level."""
        return self.COMPLEXITY_TO_AGENTS.get(complexity.value, 1)

    async def analyze_complexity(self, task: str) -> TaskComplexity:
        """Analyze task complexity based on keywords and heuristics."""
        task_lower = task.lower()

        visionary_keywords = [
            "architecture",
            "redesign",
            "system",
            "ultimate",
            "comprehensive",
            "refactor entire",
            "build from scratch",
        ]
        if any(kw in task_lower for kw in visionary_keywords):
            return TaskComplexity.VISIONARY

        complex_keywords = [
            "implement",
            "create",
            "develop",
            "build",
            "integrate",
            "migrate",
            "multiple",
        ]
        if any(kw in task_lower for kw in complex_keywords):
            return TaskComplexity.COMPLEX

        moderate_keywords = ["update", "add", "modify", "fix bug", "refactor", "optimize"]
        if any(kw in task_lower for kw in moderate_keywords):
            return TaskComplexity.MODERATE

        simple_keywords = ["read", "check", "list", "show", "find"]
        if any(kw in task_lower for kw in simple_keywords):
            return TaskComplexity.SIMPLE

        return TaskComplexity.TRIVIAL

    async def identify_task_type(self, task: str) -> TaskType:
        """Identify task type for capability matching."""
        task_lower = task.lower()
        type_patterns = {
            TaskType.CODE_GENERATION: ["write", "create", "generate", "implement"],
            TaskType.CODE_REVIEW: ["review", "audit", "check code"],
            TaskType.DEBUGGING: ["debug", "fix", "error", "bug", "issue"],
            TaskType.ARCHITECTURE: ["architect", "design", "structure", "system"],
            TaskType.RESEARCH: ["research", "find", "investigate", "explore"],
            TaskType.DOCUMENTATION: ["document", "readme", "docs", "explain"],
            TaskType.TESTING: ["test", "coverage", "unittest", "pytest"],
            TaskType.DEPLOYMENT: ["deploy", "release", "ci/cd", "docker"],
            TaskType.OPTIMIZATION: ["optimize", "performance", "speed", "improve"],
            TaskType.SECURITY_AUDIT: ["security", "vulnerability", "audit", "scan"],
            TaskType.CONSTITUTIONAL_VALIDATION: ["constitutional", "compliance", "validate"],
            TaskType.WORKFLOW_AUTOMATION: ["automate", "workflow", "pipeline"],
        }

        for task_type, patterns in type_patterns.items():
            if any(p in task_lower for p in patterns):
                return task_type

        return TaskType.CODE_GENERATION

    async def spawn_agent(
        self, agent_type: str, capabilities: list[AgentCapability]
    ) -> SwarmAgent | None:
        """Spawn a new swarm agent if capacity allows."""
        if len(self._active_agents) >= self.max_swarm_agents:
            logger.warning(f"Swarm at capacity ({self.max_swarm_agents}).")
            return None

        agent = SwarmAgent(
            agent_id=f"agent_{uuid4().hex[:8]}",
            agent_type=agent_type,
            capabilities=capabilities,
        )
        self._active_agents[agent.agent_id] = agent
        logger.info(f"Spawned agent: {agent.agent_id} ({agent_type})")
        return agent

    async def route_task(
        self, task: str, complexity: TaskComplexity, task_type: TaskType
    ) -> list[SwarmAgent]:
        """Route task to appropriate agents."""
        agents_needed = []
        agents_count = self._get_agents_for_complexity(complexity)

        for agent in self._active_agents.values():
            if agent.status == "idle" and agent.can_handle(task_type):
                agents_needed.append(agent)
                agent.status = "assigned"
                if len(agents_needed) >= agents_count:
                    break

        while len(agents_needed) < min(agents_count, self.max_swarm_agents):
            capability_map = {
                TaskType.CODE_GENERATION: [AgentCapability.PYTHON_EXPERT],
                TaskType.SECURITY_AUDIT: [AgentCapability.SECURITY_SPECIALIST],
                TaskType.RESEARCH: [AgentCapability.RESEARCH_SPECIALIST],
                TaskType.ARCHITECTURE: [AgentCapability.ARCHITECTURE_DESIGNER],
                TaskType.TESTING: [AgentCapability.TEST_AUTOMATION],
            }
            caps = capability_map.get(task_type, [AgentCapability.PYTHON_EXPERT])
            agent = await self.spawn_agent(task_type.name.lower(), caps)
            if agent:
                agent.status = "assigned"
                agents_needed.append(agent)
            else:
                break

        return agents_needed

    def get_active_agents(self) -> dict[str, SwarmAgent]:
        return self._active_agents

    def clear_agents(self):
        for agent in self._active_agents.values():
            agent.status = "terminated"
        self._active_agents.clear()

    async def delegate_to_swarm_impl(
        self, task: str, agent_types: list[str] | None, parallel: bool, memory: object
    ) -> JSONDict:
        """Internal implementation for swarm delegation."""
        complexity = await self.analyze_complexity(task)
        task_type = await self.identify_task_type(task)

        # Route to appropriate agents
        agents = await self.route_task(task, complexity, task_type)

        if not agents:
            return {
                "success": False,
                "error": "No agents available for task",
                "task": task,
                "constitutional_hash": self.constitutional_hash,
            }

        # Track swarm delegation
        from .meta_orchestrator import MemoryTier

        delegation_id = f"swarm_{uuid4().hex[:8]}"
        await memory.store(
            MemoryTier.WORKING,
            delegation_id,
            {
                "task": task,
                "agents": [a.agent_id for a in agents],
                "parallel": parallel,
                "complexity": complexity.name,
            },
        )

        return {
            "delegation_id": delegation_id,
            "success": True,
            "agents_assigned": [a.agent_id for a in agents],
            "complexity": complexity.name,
            "task_type": task_type.name,
            "parallel": parallel,
            "constitutional_hash": self.constitutional_hash,
        }
