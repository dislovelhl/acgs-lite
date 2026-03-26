"""
Swarm Intelligence - Capability Matcher

Matches agents to tasks based on capabilities.

Constitutional Hash: 608508a9bd224290
"""

from enhanced_agent_bus.observability.structured_logging import get_logger

from .enums import AgentState
from .models import SwarmAgent, SwarmTask

logger = get_logger(__name__)


class CapabilityMatcher:
    """
    Matches agents to tasks based on capabilities.

    Implements intelligent routing for optimal task assignment.
    """

    def find_best_agent(
        self,
        task: SwarmTask,
        agents: list[SwarmAgent],
    ) -> SwarmAgent | None:
        """Find the best available agent for a task."""
        available = [a for a in agents if a.state == AgentState.READY]
        if not available:
            return None

        # Score each agent
        scored_agents = []
        for agent in available:
            score = self._calculate_match_score(task, agent)
            if score > 0:
                scored_agents.append((agent, score))

        if not scored_agents:
            return None

        # Sort by score (highest first)
        scored_agents.sort(key=lambda x: x[1], reverse=True)
        return scored_agents[0][0]

    def _calculate_match_score(self, task: SwarmTask, agent: SwarmAgent) -> float:
        """Calculate capability match score."""
        if not task.required_capabilities:
            return 1.0  # object agent can handle

        agent_caps = {c.name: c for c in agent.capabilities}
        total_score = 0.0
        matched_caps = 0

        for req_cap in task.required_capabilities:
            if req_cap in agent_caps:
                cap = agent_caps[req_cap]
                total_score += cap.proficiency
                matched_caps += 1

        if matched_caps == 0:
            return 0.0

        # Coverage ratio * average proficiency
        coverage = matched_caps / len(task.required_capabilities)
        avg_proficiency = total_score / matched_caps
        return coverage * avg_proficiency

    def find_agents_for_capability(
        self,
        capability: str,
        agents: list[SwarmAgent],
        min_proficiency: float = 0.0,
    ) -> list[SwarmAgent]:
        """Find all agents with a specific capability."""
        result = []
        for agent in agents:
            for cap in agent.capabilities:
                if cap.name == capability and cap.proficiency >= min_proficiency:
                    result.append(agent)
                    break
        return result


__all__ = [
    "CapabilityMatcher",
]
