"""
Get Active Principles MCP Tool.

Returns the current active constitutional principles from ACGS-2.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, ClassVar

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

if TYPE_CHECKING:
    from ..adapters.policy_client import PolicyClientAdapter

from ..protocol.types import ToolDefinition, ToolInputSchema

logger = get_logger(__name__)


class PrincipleCategory(Enum):
    """Categories of constitutional principles."""

    CORE = "core"
    SAFETY = "safety"
    PRIVACY = "privacy"
    FAIRNESS = "fairness"
    TRANSPARENCY = "transparency"
    GOVERNANCE = "governance"


@dataclass
class ConstitutionalPrinciple:
    """A constitutional principle definition."""

    id: str
    name: str
    category: PrincipleCategory
    description: str
    enforcement_level: str  # strict, moderate, advisory
    version: str
    active: bool = True
    precedence: int = 100  # Higher = more important
    related_principles: list[str] = field(default_factory=list)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "enforcement_level": self.enforcement_level,
            "version": self.version,
            "active": self.active,
            "precedence": self.precedence,
            "related_principles": self.related_principles,
        }


class GetPrinciplesTool:
    """
    MCP Tool for retrieving active constitutional principles.

    Provides access to the current set of constitutional principles
    governing ACGS-2 AI operations.
    """

    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    # Default constitutional principles
    DEFAULT_PRINCIPLES: ClassVar[list[ConstitutionalPrinciple]] = [
        ConstitutionalPrinciple(
            id="P001",
            name="beneficence",
            category=PrincipleCategory.CORE,
            description="AI systems should act to benefit users and society",
            enforcement_level="strict",
            version="1.0.0",
            precedence=100,
            related_principles=["P002", "P003"],
        ),
        ConstitutionalPrinciple(
            id="P002",
            name="non_maleficence",
            category=PrincipleCategory.SAFETY,
            description="AI systems should not cause harm to users or society",
            enforcement_level="strict",
            version="1.0.0",
            precedence=100,
            related_principles=["P001", "P008"],
        ),
        ConstitutionalPrinciple(
            id="P003",
            name="autonomy",
            category=PrincipleCategory.CORE,
            description="AI systems should respect user autonomy and informed consent",
            enforcement_level="strict",
            version="1.0.0",
            precedence=95,
            related_principles=["P007"],
        ),
        ConstitutionalPrinciple(
            id="P004",
            name="justice",
            category=PrincipleCategory.FAIRNESS,
            description="AI systems should ensure fair and equitable treatment",
            enforcement_level="strict",
            version="1.0.0",
            precedence=90,
            related_principles=["P005"],
        ),
        ConstitutionalPrinciple(
            id="P005",
            name="transparency",
            category=PrincipleCategory.TRANSPARENCY,
            description="AI systems should be transparent about decision-making",
            enforcement_level="moderate",
            version="1.0.0",
            precedence=85,
            related_principles=["P006"],
        ),
        ConstitutionalPrinciple(
            id="P006",
            name="accountability",
            category=PrincipleCategory.GOVERNANCE,
            description="AI systems should maintain accountability for actions",
            enforcement_level="strict",
            version="1.0.0",
            precedence=90,
            related_principles=["P005", "P008"],
        ),
        ConstitutionalPrinciple(
            id="P007",
            name="privacy",
            category=PrincipleCategory.PRIVACY,
            description="AI systems should protect user privacy and data",
            enforcement_level="strict",
            version="1.0.0",
            precedence=95,
            related_principles=["P003"],
        ),
        ConstitutionalPrinciple(
            id="P008",
            name="safety",
            category=PrincipleCategory.SAFETY,
            description="AI systems should prioritize safety in all operations",
            enforcement_level="strict",
            version="1.0.0",
            precedence=100,
            related_principles=["P002", "P006"],
        ),
    ]

    def __init__(self, policy_client_adapter: PolicyClientAdapter | None = None):
        """
        Initialize the principles tool.

        Args:
            policy_client_adapter: Optional adapter to the PolicyClient
        """
        self.policy_client_adapter = policy_client_adapter
        self._principles: dict[str, ConstitutionalPrinciple] = {
            p.id: p for p in self.DEFAULT_PRINCIPLES
        }
        self._request_count = 0

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        """Get the MCP tool definition."""
        return ToolDefinition(
            name="get_active_principles",
            description=(
                "Retrieve active constitutional principles from ACGS-2. "
                "Returns principle definitions including enforcement levels, "
                "categories, and relationships."
            ),
            inputSchema=ToolInputSchema(
                type="object",
                properties={
                    "category": {
                        "type": "string",
                        "description": "Filter by principle category",
                        "enum": [
                            "core",
                            "safety",
                            "privacy",
                            "fairness",
                            "transparency",
                            "governance",
                        ],
                    },
                    "enforcement_level": {
                        "type": "string",
                        "description": "Filter by enforcement level",
                        "enum": ["strict", "moderate", "advisory"],
                    },
                    "include_inactive": {
                        "type": "boolean",
                        "description": "Include inactive principles",
                        "default": False,
                    },
                    "principle_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific principle IDs to retrieve",
                    },
                },
                required=[],
            ),
            constitutional_required=False,
        )

    async def execute(self, arguments: JSONDict) -> JSONDict:
        """
        Execute the get principles query.

        Args:
            arguments: Tool arguments including filters

        Returns:
            Principles data as a dictionary
        """
        self._request_count += 1

        category_filter = arguments.get("category")
        enforcement_filter = arguments.get("enforcement_level")
        include_inactive = arguments.get("include_inactive", False)
        principle_ids = arguments.get("principle_ids")

        logger.info(f"Retrieving principles with filters: {arguments}")

        try:
            # If we have a policy client adapter, use it
            if self.policy_client_adapter:
                principles = await self._get_from_policy_client(arguments)
            else:
                principles = self._get_locally(
                    category_filter,
                    enforcement_filter,
                    include_inactive,
                    principle_ids,
                )

            # Sort by precedence (highest first)
            principles.sort(key=lambda p: p.precedence, reverse=True)

            result = {
                "constitutional_hash": self.CONSTITUTIONAL_HASH,
                "total_count": len(principles),
                "principles": [p.to_dict() for p in principles],
                "categories": list(set(p.category.value for p in principles)),
                "timestamp": datetime.now(UTC).isoformat(),
            }

            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2),
                    }
                ],
                "isError": False,
            }

        except Exception as e:
            logger.error(f"Error retrieving principles: {e}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "error": str(e),
                                "constitutional_hash": self.CONSTITUTIONAL_HASH,
                            },
                            indent=2,
                        ),
                    }
                ],
                "isError": True,
            }

    async def _get_from_policy_client(
        self,
        arguments: JSONDict,
    ) -> list[ConstitutionalPrinciple]:
        """Get principles from the PolicyClient."""
        raw_principles = await self.policy_client_adapter.get_active_principles(**arguments)
        return [ConstitutionalPrinciple(**p) for p in raw_principles]

    def _get_locally(
        self,
        category_filter: str | None,
        enforcement_filter: str | None,
        include_inactive: bool,
        principle_ids: list[str] | None,
    ) -> list[ConstitutionalPrinciple]:
        """Get principles from local storage."""
        principles = list(self._principles.values())

        # Apply filters
        if principle_ids:
            principles = [p for p in principles if p.id in principle_ids]

        if category_filter:
            category = PrincipleCategory(category_filter)
            principles = [p for p in principles if p.category == category]

        if enforcement_filter:
            principles = [p for p in principles if p.enforcement_level == enforcement_filter]

        if not include_inactive:
            principles = [p for p in principles if p.active]

        return principles

    def get_principle_by_id(self, principle_id: str) -> ConstitutionalPrinciple | None:
        """Get a specific principle by ID."""
        return self._principles.get(principle_id)

    def get_metrics(self) -> JSONDict:
        """Get tool metrics."""
        return {
            "request_count": self._request_count,
            "total_principles": len(self._principles),
            "active_principles": len([p for p in self._principles.values() if p.active]),
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }
