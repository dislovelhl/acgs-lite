"""exp115: Multi-constitution routing for multi-agent governance.

Routes actions to different constitutions based on agent role, domain,
or custom routing functions. Essential for multi-agent systems where
different agents have different governance requirements.

Constitutional Hash: cdd01ef066bc6cf2
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .core import Constitution


class GovernanceRouter:
    """exp115: Route governance decisions to domain-specific constitutions.

    Multi-agent systems often need different governance rules for different
    contexts: a data-processing agent follows data-protection rules while
    a deployment agent follows infrastructure rules. GovernanceRouter maps
    agents/domains to constitutions and resolves the correct one at
    validation time.

    Usage::

        router = GovernanceRouter(default=general_constitution)
        router.add_route("data-agent", data_constitution)
        router.add_route("deploy-agent", infra_constitution)
        router.add_domain_route("healthcare", healthcare_constitution)

        # At validation time:
        constitution = router.resolve(agent_id="data-agent")
        constitution = router.resolve(domain="healthcare")
    """

    __slots__ = ("_default", "_agent_routes", "_domain_routes", "_custom_routes")

    def __init__(self, default: Constitution) -> None:
        """Initialize with a default constitution for unmatched routes.

        Args:
            default: Fallback constitution when no specific route matches.
        """
        self._default = default
        self._agent_routes: dict[str, Constitution] = {}
        self._domain_routes: dict[str, Constitution] = {}
        self._custom_routes: list[tuple[str, Callable[..., bool], Constitution]] = []

    def add_route(self, agent_id: str, constitution: Constitution) -> GovernanceRouter:
        """Map an agent ID to a specific constitution. Returns self for chaining.

        Args:
            agent_id: The agent identifier to route.
            constitution: The constitution to use for this agent.
        """
        self._agent_routes[agent_id] = constitution
        return self

    def add_domain_route(
        self, domain: str, constitution: Constitution
    ) -> GovernanceRouter:
        """Map a domain name to a specific constitution. Returns self for chaining.

        Args:
            domain: The domain identifier (e.g., "healthcare", "finance").
            constitution: The constitution to use for this domain.
        """
        self._domain_routes[domain] = constitution
        return self

    def add_custom_route(
        self,
        name: str,
        predicate: Callable[..., bool],
        constitution: Constitution,
    ) -> GovernanceRouter:
        """Add a custom routing rule. Returns self for chaining.

        The predicate receives keyword arguments from ``resolve()`` and returns
        True if this route should match. Custom routes are evaluated in
        registration order; first match wins.

        Args:
            name: Human-readable name for this route (for diagnostics).
            predicate: Callable that returns True if this route matches.
            constitution: The constitution to use when predicate matches.

        Example::

            router.add_custom_route(
                "high-risk-prod",
                lambda context=None, **kw: context and context.get("env") == "production",
                strict_constitution,
            )
        """
        self._custom_routes.append((name, predicate, constitution))
        return self

    def resolve(
        self,
        *,
        agent_id: str = "",
        domain: str = "",
        **context: Any,
    ) -> Constitution:
        """Resolve which constitution to use for a given request.

        Resolution order (first match wins):
        1. Agent-specific route
        2. Domain-specific route
        3. Custom routes (in registration order)
        4. Default constitution

        Args:
            agent_id: The requesting agent's ID.
            domain: The governance domain.
            **context: Additional context passed to custom route predicates.

        Returns:
            The resolved Constitution.
        """
        if agent_id and agent_id in self._agent_routes:
            return self._agent_routes[agent_id]

        if domain and domain in self._domain_routes:
            return self._domain_routes[domain]

        for _name, predicate, constitution in self._custom_routes:
            if predicate(agent_id=agent_id, domain=domain, **context):
                return constitution

        return self._default

    def resolve_with_info(
        self,
        *,
        agent_id: str = "",
        domain: str = "",
        **context: Any,
    ) -> dict[str, Any]:
        """Resolve constitution with routing diagnostics.

        Same resolution as ``resolve()`` but returns routing metadata for
        observability and debugging.

        Returns:
            dict with keys:
                - ``constitution``: the resolved Constitution
                - ``route_type``: "agent" | "domain" | "custom" | "default"
                - ``route_key``: the matched agent_id, domain, or custom route name
                - ``available_routes``: summary of configured routes
        """
        if agent_id and agent_id in self._agent_routes:
            return {
                "constitution": self._agent_routes[agent_id],
                "route_type": "agent",
                "route_key": agent_id,
                "available_routes": self.summary(),
            }

        if domain and domain in self._domain_routes:
            return {
                "constitution": self._domain_routes[domain],
                "route_type": "domain",
                "route_key": domain,
                "available_routes": self.summary(),
            }

        for name, predicate, constitution in self._custom_routes:
            if predicate(agent_id=agent_id, domain=domain, **context):
                return {
                    "constitution": constitution,
                    "route_type": "custom",
                    "route_key": name,
                    "available_routes": self.summary(),
                }

        return {
            "constitution": self._default,
            "route_type": "default",
            "route_key": "default",
            "available_routes": self.summary(),
        }

    def summary(self) -> dict[str, Any]:
        """Return routing configuration summary.

        Returns:
            dict with keys:
                - ``default``: default constitution name
                - ``agent_routes``: {agent_id: constitution_name, ...}
                - ``domain_routes``: {domain: constitution_name, ...}
                - ``custom_routes``: list of custom route names
                - ``total_routes``: total number of configured routes
        """
        return {
            "default": self._default.name,
            "agent_routes": {
                k: v.name for k, v in self._agent_routes.items()
            },
            "domain_routes": {
                k: v.name for k, v in self._domain_routes.items()
            },
            "custom_routes": [name for name, _, _ in self._custom_routes],
            "total_routes": (
                len(self._agent_routes)
                + len(self._domain_routes)
                + len(self._custom_routes)
            ),
        }
