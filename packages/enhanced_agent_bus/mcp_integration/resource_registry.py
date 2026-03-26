"""Resource registry for MCP integration.

Constitutional Hash: 608508a9bd224290
"""

from collections.abc import Callable
from datetime import UTC, datetime
from logging import Logger
from typing import Protocol

from enhanced_agent_bus.bus_types import JSONDict


class _InternalResourceProtocol(Protocol):
    uri: str

    def to_mcp_definition(self) -> JSONDict: ...


class _InternalMetricsProtocol(Protocol):
    resources_registered: int

    def to_dict(self) -> JSONDict: ...


class MCPResourceRegistry:
    def __init__(
        self,
        resources: dict[str, _InternalResourceProtocol],
        metrics: _InternalMetricsProtocol,
        audit_log: list[JSONDict],
        constitutional_hash: str,
        resource_factory: Callable[..., _InternalResourceProtocol],
        logger_instance: Logger,
    ) -> None:
        self._resources = resources
        self._metrics = metrics
        self._audit_log = audit_log
        self._constitutional_hash = constitutional_hash
        self._resource_factory = resource_factory
        self._logger = logger_instance

    def register_resource(self, resource: _InternalResourceProtocol) -> bool:
        if resource.uri in self._resources:
            self._logger.warning(f"Resource '{resource.uri}' already registered, updating")

        self._resources[resource.uri] = resource
        self._metrics.resources_registered = len(self._resources)
        self._logger.info(f"Registered resource: {resource.uri}")
        return True

    def unregister_resource(self, uri: str) -> bool:
        if uri in self._resources:
            del self._resources[uri]
            self._metrics.resources_registered = len(self._resources)
            self._logger.info(f"Unregistered resource: {uri}")
            return True
        return False

    def _initialize_builtin_resources(self) -> None:
        self.register_resource(
            self._resource_factory(
                uri="acgs2://constitutional/principles",
                name="Constitutional Principles",
                description="Active constitutional principles and governance rules",
                handler=self._resource_principles,
            )
        )

        self.register_resource(
            self._resource_factory(
                uri="acgs2://governance/metrics",
                name="Governance Metrics",
                description="Real-time governance and server metrics",
                handler=self._resource_metrics,
            )
        )

        self.register_resource(
            self._resource_factory(
                uri="acgs2://governance/audit",
                name="Audit Trail",
                description="Recent audit trail entries",
                handler=self._resource_audit,
            )
        )

    async def _resource_principles(self, params: JSONDict) -> JSONDict:
        return {
            "principles": {
                "beneficence": "Actions should benefit users and society",
                "non_maleficence": "Actions should not cause harm",
                "autonomy": "Respect user autonomy and informed consent",
                "justice": "Ensure fair and equitable treatment",
                "transparency": "Be transparent about AI decision-making",
                "accountability": "Maintain accountability for AI actions",
                "privacy": "Protect user privacy and data",
                "safety": "Prioritize safety in all operations",
            },
            "constitutional_hash": self._constitutional_hash,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    async def _resource_metrics(self, params: JSONDict) -> JSONDict:
        return self._metrics.to_dict()

    async def _resource_audit(self, params: JSONDict) -> JSONDict:
        return {
            "entries": self._audit_log[-100:],
            "total_entries": len(self._audit_log),
            "constitutional_hash": self._constitutional_hash,
        }

    def get_resources(self) -> list[JSONDict]:
        return [resource.to_mcp_definition() for resource in self._resources.values()]


__all__ = ["MCPResourceRegistry"]
