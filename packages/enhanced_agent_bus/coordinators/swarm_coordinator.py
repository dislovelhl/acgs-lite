"""
Swarm Coordinator - Manages multi-agent spawning and task routing.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)
_SWARM_COORDINATOR_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class SwarmCoordinator:
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __init__(self, max_agents: int = 10, enable_consensus: bool = True):
        self._max_agents = max_agents
        self._enable_consensus = enable_consensus
        self._swarm: object | None = None
        self._initialized = False
        self._agents: JSONDict = {}  # Stores SwarmAgent or fallback dicts

        self._initialize_swarm()

    def _initialize_swarm(self) -> None:
        try:
            from ..swarm_intelligence import create_swarm_coordinator

            self._swarm = create_swarm_coordinator(
                max_agents=self._max_agents,
                constitutional_hash=self.constitutional_hash,
            )
            self._initialized = True
            logger.info(f"SwarmCoordinator initialized with max_agents={self._max_agents}")
        except ImportError:
            logger.info("Swarm intelligence not available, using basic agent management")
        except _SWARM_COORDINATOR_OPERATION_ERRORS as e:
            logger.warning(f"Swarm initialization failed: {e}")

    @property
    def is_available(self) -> bool:
        return self._initialized and self._swarm is not None

    async def spawn_agent(
        self,
        agent_type: str,
        capabilities: list[str],
        name: str | None = None,
    ) -> JSONDict | None:
        agent_id = str(uuid.uuid4())[:8]
        agent_name = name or f"{agent_type}-{agent_id}"

        if self._swarm:
            try:
                from ..swarm_intelligence import AgentCapability

                caps = [
                    AgentCapability(name=c, description=c, proficiency=0.8, cost_factor=1.0)
                    for c in capabilities
                ]
                agent = await self._swarm.spawn_agent(
                    agent_type=agent_type,
                    name=agent_name,
                    capabilities=caps,
                )
                if agent:
                    self._agents[agent.id] = agent
                    return {
                        "id": agent.id,
                        "name": agent.name,
                        "type": agent_type,
                        "capabilities": capabilities,
                        "state": (
                            agent.state.value if hasattr(agent.state, "value") else str(agent.state)
                        ),
                        "constitutional_hash": self.constitutional_hash,
                    }
            except _SWARM_COORDINATOR_OPERATION_ERRORS as e:
                logger.error(f"Failed to spawn agent: {e}")
                return None

        self._agents[agent_id] = {
            "id": agent_id,
            "name": agent_name,
            "type": agent_type,
            "capabilities": capabilities,
            "state": "ready",
        }
        return {
            "id": agent_id,
            "name": agent_name,
            "type": agent_type,
            "capabilities": capabilities,
            "state": "ready",
            "constitutional_hash": self.constitutional_hash,
        }

    async def route_task(
        self,
        task: str,
        required_capabilities: list[str],
        priority: str = "normal",
    ) -> list[JSONDict]:
        if self._swarm:
            try:
                from ..swarm_intelligence import TaskPriority

                priority_map = {
                    "critical": TaskPriority.CRITICAL,
                    "high": TaskPriority.HIGH,
                    "normal": TaskPriority.NORMAL,
                    "low": TaskPriority.LOW,
                    "background": TaskPriority.LOW,  # type: ignore[attr-defined]  # BACKGROUND not defined, use LOW
                }
                agents = await self._swarm.route_task(
                    task=task,
                    required_capabilities=required_capabilities,
                    priority=priority_map.get(priority, TaskPriority.NORMAL),
                )
                return [
                    {
                        "id": a.id,
                        "name": a.name,
                        "match_score": getattr(a, "match_score", 1.0),
                    }
                    for a in agents
                ]
            except _SWARM_COORDINATOR_OPERATION_ERRORS as e:
                logger.error(f"Task routing failed: {e}")

        matching = []
        for agent_id, agent in self._agents.items():
            if isinstance(agent, dict):
                agent_caps = set(agent.get("capabilities", []))
            else:
                agent_caps = {c.name for c in getattr(agent, "capabilities", [])}

            required_set = set(required_capabilities)
            if required_set.intersection(agent_caps):
                matching.append(
                    {
                        "id": agent_id,
                        "name": (
                            agent.get("name", agent_id) if isinstance(agent, dict) else agent.name
                        ),
                        "match_score": len(required_set.intersection(agent_caps))
                        / len(required_set),
                    }
                )

        return sorted(matching, key=lambda x: x["match_score"], reverse=True)

    async def terminate_agent(self, agent_id: str) -> bool:
        if agent_id in self._agents:
            if self._swarm:
                try:
                    await self._swarm.terminate_agent(agent_id)
                except _SWARM_COORDINATOR_OPERATION_ERRORS as e:
                    logger.warning(f"Swarm termination failed: {e}")

            del self._agents[agent_id]
            logger.info(f"Agent {agent_id} terminated")
            return True
        return False

    def get_active_agents(self) -> JSONDict:
        agents_list = []
        for _, agent in self._agents.items():
            if isinstance(agent, dict):
                agents_list.append(agent)  # type: ignore[arg-type]
            else:
                agents_list.append(
                    {  # type: ignore[arg-type]
                        "id": agent.id,
                        "name": agent.name,
                        "state": (
                            agent.state.value if hasattr(agent.state, "value") else str(agent.state)
                        ),
                    }
                )

        return {
            "constitutional_hash": self.constitutional_hash,
            "swarm_available": self.is_available,
            "max_agents": self._max_agents,
            "active_count": len(self._agents),
            "agents": agents_list,
        }
