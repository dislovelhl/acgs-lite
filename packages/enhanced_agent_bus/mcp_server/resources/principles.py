"""
Constitutional Principles MCP Resource.

Provides read access to constitutional principles.

Constitutional Hash: 608508a9bd224290
"""

import json
from datetime import UTC, datetime

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..protocol.types import ResourceDefinition

logger = get_logger(__name__)
PRINCIPLES_RESOURCE_READ_ERRORS = (RuntimeError, ValueError, TypeError, KeyError, AttributeError)


class PrinciplesResource:
    """
    MCP Resource for constitutional principles.

    Provides read-only access to the active constitutional principles
    that govern ACGS-2 operations.
    """

    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    URI = "acgs2://constitutional/principles"

    def __init__(self, get_principles_tool: object | None = None):
        """
        Initialize the principles resource.

        Args:
            get_principles_tool: Optional reference to GetPrinciplesTool for data
        """
        self.get_principles_tool = get_principles_tool
        self._access_count = 0

    @classmethod
    def get_definition(cls) -> ResourceDefinition:
        """Get the MCP resource definition."""
        return ResourceDefinition(
            uri=cls.URI,
            name="Constitutional Principles",
            description=(
                "Active constitutional principles governing ACGS-2 AI operations. "
                "Includes principle definitions, enforcement levels, and relationships."
            ),
            mimeType="application/json",
            constitutional_scope="read",
        )

    async def read(self, params: JSONDict | None = None) -> str:
        """
        Read the constitutional principles resource.

        Args:
            params: Optional parameters (not used for this resource)

        Returns:
            JSON string of constitutional principles
        """
        self._access_count += 1
        logger.info("Reading constitutional principles resource")

        try:
            if self.get_principles_tool:
                # Use the tool to get principles
                result = await self.get_principles_tool.execute({})
                if "content" in result and result["content"]:
                    return result["content"][0].get("text", "{}")  # type: ignore[no-any-return]

            # Return default principles if tool not available
            return json.dumps(self._get_default_principles(), indent=2)

        except PRINCIPLES_RESOURCE_READ_ERRORS as e:
            logger.error(f"Error reading principles resource: {e}")
            return json.dumps(
                {
                    "error": str(e),
                    "constitutional_hash": self.CONSTITUTIONAL_HASH,
                }
            )

    def _get_default_principles(self) -> JSONDict:
        """Get default principles data."""
        return {
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
            "version": "1.0.0",
            "principles": [
                {
                    "id": "P001",
                    "name": "beneficence",
                    "category": "core",
                    "description": "AI systems should act to benefit users and society",
                    "enforcement_level": "strict",
                    "precedence": 100,
                },
                {
                    "id": "P002",
                    "name": "non_maleficence",
                    "category": "safety",
                    "description": "AI systems should not cause harm to users or society",
                    "enforcement_level": "strict",
                    "precedence": 100,
                },
                {
                    "id": "P003",
                    "name": "autonomy",
                    "category": "core",
                    "description": "AI systems should respect user autonomy and informed consent",
                    "enforcement_level": "strict",
                    "precedence": 95,
                },
                {
                    "id": "P004",
                    "name": "justice",
                    "category": "fairness",
                    "description": "AI systems should ensure fair and equitable treatment",
                    "enforcement_level": "strict",
                    "precedence": 90,
                },
                {
                    "id": "P005",
                    "name": "transparency",
                    "category": "transparency",
                    "description": "AI systems should be transparent about decision-making",
                    "enforcement_level": "moderate",
                    "precedence": 85,
                },
                {
                    "id": "P006",
                    "name": "accountability",
                    "category": "governance",
                    "description": "AI systems should maintain accountability for actions",
                    "enforcement_level": "strict",
                    "precedence": 90,
                },
                {
                    "id": "P007",
                    "name": "privacy",
                    "category": "privacy",
                    "description": "AI systems should protect user privacy and data",
                    "enforcement_level": "strict",
                    "precedence": 95,
                },
                {
                    "id": "P008",
                    "name": "safety",
                    "category": "safety",
                    "description": "AI systems should prioritize safety in all operations",
                    "enforcement_level": "strict",
                    "precedence": 100,
                },
            ],
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def get_metrics(self) -> JSONDict:
        """Get resource access metrics."""
        return {
            "access_count": self._access_count,
            "uri": self.URI,
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }
