"""Capability Registry — O(1) expertise routing for swarm agents.

Each agent registers structured capabilities. Task routing matches
requirements to capabilities without broadcasting to all agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Capability:
    """A declared agent capability."""

    name: str
    domain: str
    description: str = ""
    model_tier: str = "sonnet"
    avg_latency_ms: float = 0.0
    cost_per_task: float = 0.0
    tags: tuple[str, ...] = ()

    def matches(self, requirement: str) -> bool:
        """Check if this capability matches a requirement string."""
        req_lower = requirement.lower()
        return (
            req_lower in self.name.lower()
            or req_lower in self.domain.lower()
            or req_lower in self.description.lower()
            or any(req_lower in t.lower() for t in self.tags)
        )


class CapabilityRegistry:
    """Registry for agent capabilities with O(1) lookup by domain.

    Agents register capabilities. Tasks are routed to the best-matching
    agent without broadcasting to all N agents.
    """

    def __init__(self) -> None:
        self._by_agent: dict[str, list[Capability]] = {}
        self._by_domain: dict[str, list[tuple[str, Capability]]] = {}
        self._by_name: dict[str, list[tuple[str, Capability]]] = {}

    def register(self, agent_id: str, capabilities: list[Capability]) -> None:
        """Register an agent's capabilities."""
        if agent_id in self._by_agent:
            self.unregister(agent_id)
        self._by_agent[agent_id] = list(capabilities)
        for cap in capabilities:
            domain_list = self._by_domain.setdefault(cap.domain, [])
            domain_list.append((agent_id, cap))
            name_list = self._by_name.setdefault(cap.name.lower(), [])
            name_list.append((agent_id, cap))

    def unregister(self, agent_id: str) -> None:
        """Remove an agent's capabilities."""
        caps = self._by_agent.pop(agent_id, [])
        for cap in caps:
            domain_list = self._by_domain.get(cap.domain, [])
            self._by_domain[cap.domain] = [
                (aid, c) for aid, c in domain_list if aid != agent_id
            ]
            name_list = self._by_name.get(cap.name.lower(), [])
            self._by_name[cap.name.lower()] = [
                (aid, c) for aid, c in name_list if aid != agent_id
            ]

    def find_by_domain(self, domain: str) -> list[tuple[str, Capability]]:
        """Find all agents with capabilities in a domain. O(1) lookup."""
        return list(self._by_domain.get(domain, []))

    def find_by_name(self, name: str) -> list[tuple[str, Capability]]:
        """Find agents offering a specific capability. O(1) lookup."""
        return list(self._by_name.get(name.lower(), []))

    def find_best(
        self,
        requirement: str,
        *,
        domain: str | None = None,
        prefer_cheap: bool = False,
        prefer_fast: bool = False,
    ) -> tuple[str, Capability] | None:
        """Find the best agent for a requirement.

        Searches by domain first (O(1)), then scores by match quality,
        cost, and latency.
        """
        candidates: list[tuple[str, Capability]]
        if domain:
            candidates = self.find_by_domain(domain)
        else:
            candidates = [
                (aid, cap)
                for aid, caps in self._by_agent.items()
                for cap in caps
                if cap.matches(requirement)
            ]

        if not candidates:
            return None

        def _score(entry: tuple[str, Capability]) -> float:
            _, cap = entry
            score = 1.0 if cap.matches(requirement) else 0.0
            if prefer_cheap and cap.cost_per_task > 0:
                score += 1.0 / cap.cost_per_task
            if prefer_fast and cap.avg_latency_ms > 0:
                score += 1.0 / cap.avg_latency_ms
            return score

        return max(candidates, key=_score)

    def get_agent_capabilities(self, agent_id: str) -> list[Capability]:
        """Get all capabilities registered for an agent."""
        return list(self._by_agent.get(agent_id, []))

    @property
    def agents(self) -> list[str]:
        """List all registered agent IDs."""
        return list(self._by_agent)

    @property
    def domains(self) -> list[str]:
        """List all registered domains."""
        return list(self._by_domain)

    def summary(self) -> dict[str, Any]:
        """Registry summary statistics."""
        return {
            "agents": len(self._by_agent),
            "domains": len(self._by_domain),
            "capabilities": sum(len(caps) for caps in self._by_agent.values()),
            "domain_distribution": {
                d: len(entries) for d, entries in self._by_domain.items()
            },
        }
