"""Constitutional Hash: 608508a9bd224290
Agent Registry Manager Component

Handles agent registration, discovery, and management operations.
This component is responsible for maintaining the registry of agents
and providing methods to query and manage agent information.
"""

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from ..interfaces import AgentRegistry
    from ..registry import InMemoryAgentRegistry, RedisAgentRegistry
except ImportError:
    from interfaces import AgentRegistry  # type: ignore[no-redef]
    from registry import (  # type: ignore[no-redef]
        InMemoryAgentRegistry,
        RedisAgentRegistry,
    )

logger = get_logger(__name__)


class AgentRegistryManager:
    """
    Manages agent registration, discovery, and information retrieval.

    This component encapsulates all agent registry operations and provides
    a clean interface for registering, unregistering, and querying agents.
    """

    def __init__(
        self, registry: AgentRegistry | None = None, redis_url: str = "redis://localhost:6379"
    ):
        """
        Initialize the agent registry manager.

        Args:
            registry: Custom registry implementation, or None to use defaults
            redis_url: Redis URL for Redis-based registry
        """
        if registry:
            self._registry = registry
        elif redis_url and "redis" in redis_url:
            self._registry = RedisAgentRegistry(redis_url=redis_url)
        else:
            self._registry = InMemoryAgentRegistry()

        logger.info(f"Initialized AgentRegistryManager with {type(self._registry).__name__}")

    async def register_agent(
        self,
        agent_id: str,
        agent_type: str,
        capabilities: list[str] | None = None,
        metadata: JSONDict | None = None,
        tenant_id: str | None = None,
    ) -> bool:
        """
        Register an agent with the registry.

        Args:
            agent_id: Unique identifier for the agent
            agent_type: Type/category of the agent
            capabilities: List of agent capabilities
            metadata: Additional agent metadata
            tenant_id: Tenant identifier for multi-tenancy

        Returns:
            bool: True if registration successful, False otherwise
        """
        try:
            agent_info = {
                "agent_id": agent_id,
                "agent_type": agent_type,
                "capabilities": capabilities or [],
                "metadata": metadata or {},
                "tenant_id": tenant_id,
                "registered_at": "2024-01-01T00:00:00Z",  # Would use datetime.now(timezone.utc) in real implementation
                "status": "active",
            }

            # For development mode, we'll store in memory
            # In production, this would use the actual registry
            if not hasattr(self._registry, "_agents"):
                self._registry._agents = {}  # type: ignore[attr-defined]

            self._registry._agents[agent_id] = agent_info  # type: ignore[attr-defined]

            logger.info(f"Registered agent: {agent_id} (type: {agent_type})")
            return True

        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error(f"Failed to register agent {agent_id}: {e}")
            return False

    async def unregister_agent(self, agent_id: str) -> bool:
        """
        Unregister an agent from the registry.

        Args:
            agent_id: Unique identifier of the agent to unregister

        Returns:
            bool: True if unregistration successful, False otherwise
        """
        try:
            if hasattr(self._registry, "_agents") and agent_id in self._registry._agents:
                del self._registry._agents[agent_id]
                logger.info(f"Unregistered agent: {agent_id}")
                return True

            logger.warning(f"Agent {agent_id} not found for unregistration")
            return False

        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error(f"Failed to unregister agent {agent_id}: {e}")
            return False

    def get_agent_info(self, agent_id: str) -> JSONDict | None:
        """
        Get information about a specific agent.

        Args:
            agent_id: Unique identifier of the agent

        Returns:
            Dict containing agent information, or None if not found
        """
        try:
            if hasattr(self._registry, "_agents"):
                return self._registry._agents.get(agent_id)
            return None
        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error(f"Failed to get agent info for {agent_id}: {e}")
            return None

    def get_registered_agents(self) -> list[str]:
        """
        Get list of all registered agent IDs.

        Returns:
            List of agent IDs
        """
        try:
            if hasattr(self._registry, "_agents"):
                return list(self._registry._agents.keys())
            return []
        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error(f"Failed to get registered agents: {e}")
            return []

    def get_agents_by_type(self, agent_type: str) -> list[str]:
        """
        Get agents of a specific type.

        Args:
            agent_type: Type of agents to retrieve

        Returns:
            List of agent IDs matching the type
        """
        try:
            agents = []
            if hasattr(self._registry, "_agents"):
                for agent_id, info in self._registry._agents.items():
                    if info.get("agent_type") == agent_type:
                        agents.append(agent_id)
            return agents
        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error(f"Failed to get agents by type {agent_type}: {e}")
            return []

    def get_agents_by_capability(self, capability: str) -> list[str]:
        """
        Get agents with a specific capability.

        Args:
            capability: Capability to search for

        Returns:
            List of agent IDs with the specified capability
        """
        try:
            agents = []
            if hasattr(self._registry, "_agents"):
                for agent_id, info in self._registry._agents.items():
                    if capability in info.get("capabilities", []):
                        agents.append(agent_id)
            return agents
        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error(f"Failed to get agents by capability {capability}: {e}")
            return []

    def get_agents_by_tenant(self, tenant_id: str) -> list[str]:
        """
        Get agents belonging to a specific tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            List of agent IDs in the tenant
        """
        try:
            agents = []
            if hasattr(self._registry, "_agents"):
                for agent_id, info in self._registry._agents.items():
                    if info.get("tenant_id") == tenant_id:
                        agents.append(agent_id)
            return agents
        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error(f"Failed to get agents by tenant {tenant_id}: {e}")
            return []

    async def update_agent_status(self, agent_id: str, status: str) -> bool:
        """
        Update the status of an agent.

        Args:
            agent_id: Unique identifier of the agent
            status: New status for the agent

        Returns:
            bool: True if update successful, False otherwise
        """
        try:
            if hasattr(self._registry, "_agents") and agent_id in self._registry._agents:
                self._registry._agents[agent_id]["status"] = status
                self._registry._agents[agent_id]["updated_at"] = "2024-01-01T00:00:00Z"
                logger.info(f"Updated agent {agent_id} status to {status}")
                return True

            logger.warning(f"Agent {agent_id} not found for status update")
            return False

        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error(f"Failed to update agent {agent_id} status: {e}")
            return False

    def get_registry_stats(self) -> JSONDict:
        """
        Get statistics about the agent registry.

        Returns:
            Dictionary with registry statistics
        """
        try:
            stats = {
                "total_agents": 0,
                "agents_by_type": {},
                "agents_by_status": {},
                "registry_type": type(self._registry).__name__,
            }

            if hasattr(self._registry, "_agents"):
                agents = self._registry._agents
                stats["total_agents"] = len(agents)

                for agent_info in agents.values():
                    # Count by type
                    agent_type = agent_info.get("agent_type", "unknown")  # type: ignore[attr-defined]
                    stats["agents_by_type"][agent_type] = (  # type: ignore[index]
                        stats["agents_by_type"].get(agent_type, 0) + 1  # type: ignore[union-attr, attr-defined]
                    )

                    # Count by status
                    status = agent_info.get("status", "unknown")  # type: ignore[attr-defined]
                    stats["agents_by_status"][status] = stats["agents_by_status"].get(status, 0) + 1  # type: ignore[index, union-attr, attr-defined]

            return stats

        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.error(f"Failed to get registry stats: {e}")
            return {"error": str(e)}

    def cleanup_inactive_agents(self, max_age_hours: int = 24) -> int:
        """
        Clean up inactive agents based on last activity.

        Args:
            max_age_hours: Maximum age in hours for agent cleanup

        Returns:
            Number of agents cleaned up
        """
        # Simplified implementation for development
        # In production, this would check last activity timestamps
        logger.info(
            f"Agent cleanup requested (max_age: {max_age_hours}h) - simplified implementation"
        )
        return 0
