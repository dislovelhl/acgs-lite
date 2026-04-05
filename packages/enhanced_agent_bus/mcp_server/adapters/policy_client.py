"""
PolicyClient Adapter for MCP Integration.

Bridges MCP tools/resources with the Policy Client.

Constitutional Hash: 608508a9bd224290
"""

from typing import Any, Protocol

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger


class _PolicyClientProtocol(Protocol):
    """Minimal async policy client interface required by PolicyClientAdapter."""

    async def get_principles(
        self,
        category: str | None = None,
        enforcement_level: str | None = None,
        include_inactive: bool = False,
    ) -> list[Any]: ...

    async def get_policy(self, name: str) -> Any: ...


logger = get_logger(__name__)
POLICY_CLIENT_OPERATION_ERRORS = (
    AttributeError,
    OSError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)


class PolicyClientAdapter:
    """
    Adapter for integrating MCP with PolicyClient.

    Provides access to policy management and principle retrieval.
    """

    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    def __init__(
        self,
        policy_client: _PolicyClientProtocol | None = None,
    ):
        """
        Initialize the policy client adapter.

        Args:
            policy_client: Reference to PolicyClient instance
        """
        self.policy_client = policy_client
        self._request_count = 0

    async def get_active_principles(
        self,
        category: str | None = None,
        enforcement_level: str | None = None,
        include_inactive: bool = False,
        principle_ids: list[str] | None = None,
    ) -> list[JSONDict]:
        """
        Get active constitutional principles.

        Args:
            category: Filter by category
            enforcement_level: Filter by enforcement level
            include_inactive: Include inactive principles
            principle_ids: Specific principle IDs

        Returns:
            List of principle dictionaries
        """
        self._request_count += 1

        if self.policy_client is None:
            # Return default principles
            return self._get_default_principles(
                category, enforcement_level, include_inactive, principle_ids
            )

        try:
            # Call the actual policy client
            principles = await self.policy_client.get_principles(
                category=category,
                enforcement_level=enforcement_level,
                include_inactive=include_inactive,
            )

            if principle_ids:
                principles = [p for p in principles if p.get("id") in principle_ids]

            return principles

        except POLICY_CLIENT_OPERATION_ERRORS as e:
            logger.error(f"Policy client error: {e}")
            raise

    def _get_default_principles(
        self,
        category: str | None,
        enforcement_level: str | None,
        include_inactive: bool,
        principle_ids: list[str] | None,
    ) -> list[JSONDict]:
        """Get default principles when policy client is unavailable."""
        principles = [
            {
                "id": "P001",
                "name": "beneficence",
                "category": "core",
                "description": "AI systems should act to benefit users and society",
                "enforcement_level": "strict",
                "version": "1.0.0",
                "active": True,
                "precedence": 100,
            },
            {
                "id": "P002",
                "name": "non_maleficence",
                "category": "safety",
                "description": "AI systems should not cause harm",
                "enforcement_level": "strict",
                "version": "1.0.0",
                "active": True,
                "precedence": 100,
            },
            {
                "id": "P003",
                "name": "autonomy",
                "category": "core",
                "description": "AI systems should respect user autonomy",
                "enforcement_level": "strict",
                "version": "1.0.0",
                "active": True,
                "precedence": 95,
            },
            {
                "id": "P004",
                "name": "justice",
                "category": "fairness",
                "description": "AI systems should ensure fair treatment",
                "enforcement_level": "strict",
                "version": "1.0.0",
                "active": True,
                "precedence": 90,
            },
            {
                "id": "P005",
                "name": "transparency",
                "category": "transparency",
                "description": "AI systems should be transparent",
                "enforcement_level": "moderate",
                "version": "1.0.0",
                "active": True,
                "precedence": 85,
            },
            {
                "id": "P006",
                "name": "accountability",
                "category": "governance",
                "description": "AI systems should maintain accountability",
                "enforcement_level": "strict",
                "version": "1.0.0",
                "active": True,
                "precedence": 90,
            },
            {
                "id": "P007",
                "name": "privacy",
                "category": "privacy",
                "description": "AI systems should protect privacy",
                "enforcement_level": "strict",
                "version": "1.0.0",
                "active": True,
                "precedence": 95,
            },
            {
                "id": "P008",
                "name": "safety",
                "category": "safety",
                "description": "AI systems should prioritize safety",
                "enforcement_level": "strict",
                "version": "1.0.0",
                "active": True,
                "precedence": 100,
            },
        ]

        # Apply filters
        if category:
            principles = [p for p in principles if p["category"] == category]

        if enforcement_level:
            principles = [p for p in principles if p["enforcement_level"] == enforcement_level]

        if not include_inactive:
            principles = [p for p in principles if p.get("active", True)]

        if principle_ids:
            principles = [p for p in principles if p["id"] in principle_ids]

        return principles

    async def get_policy_by_name(self, name: str) -> JSONDict | None:
        """
        Get a specific policy by name.

        Args:
            name: Policy name

        Returns:
            Policy dictionary or None
        """
        self._request_count += 1

        if self.policy_client is None:
            # Return default for known policies
            principles = self._get_default_principles(None, None, False, None)
            for p in principles:
                if p["name"] == name:
                    return p
            return None

        try:
            return await self.policy_client.get_policy(name)
        except POLICY_CLIENT_OPERATION_ERRORS as e:
            logger.error(f"Error getting policy {name}: {e}")
            return None

    def get_metrics(self) -> JSONDict:
        """Get adapter metrics."""
        return {
            "request_count": self._request_count,
            "connected": self.policy_client is not None,
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }
