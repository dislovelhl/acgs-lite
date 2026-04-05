"""
Query Governance Precedents MCP Tool.

Queries historical governance decisions for precedent analysis.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from enhanced_agent_bus.observability.structured_logging import get_logger

if TYPE_CHECKING:
    from ..adapters.audit_client import AuditClientAdapter

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from ..protocol.types import ToolDefinition, ToolInputSchema

logger = get_logger(__name__)


class DecisionOutcome(Enum):
    """Governance decision outcomes."""

    APPROVED = "approved"
    DENIED = "denied"
    CONDITIONAL = "conditional"
    DEFERRED = "deferred"
    ESCALATED = "escalated"


@dataclass
class GovernancePrecedent:
    """A governance decision precedent."""

    id: str
    action_type: str
    context_summary: str
    outcome: DecisionOutcome
    principles_applied: list[str]
    reasoning: str
    timestamp: str
    confidence_score: float
    appeal_count: int = 0
    overruled: bool = False
    related_precedents: list[str] = field(default_factory=list)

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "action_type": self.action_type,
            "context_summary": self.context_summary,
            "outcome": self.outcome.value,
            "principles_applied": self.principles_applied,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp,
            "confidence_score": self.confidence_score,
            "appeal_count": self.appeal_count,
            "overruled": self.overruled,
            "related_precedents": self.related_precedents,
        }


class QueryPrecedentsTool:
    """
    MCP Tool for querying governance precedents.

    Provides access to historical governance decisions for precedent-based
    decision making and consistency enforcement.
    """

    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    def __init__(self, audit_client_adapter: AuditClientAdapter | None = None):
        """
        Initialize the precedents tool.

        Args:
            audit_client_adapter: Optional adapter to the AuditClient
        """
        self.audit_client_adapter = audit_client_adapter
        self._precedent_cache: dict[str, GovernancePrecedent] = {}
        self._request_count = 0

        # Initialize with sample precedents for demonstration
        self._initialize_sample_precedents()

    def _initialize_sample_precedents(self) -> None:
        """Initialize sample precedents for demonstration."""
        sample_precedents = [
            GovernancePrecedent(
                id="PREC-001",
                action_type="data_access",
                context_summary="Agent requested access to user PII without explicit consent",
                outcome=DecisionOutcome.DENIED,
                principles_applied=["P007", "P003"],  # privacy, autonomy
                reasoning="Access to PII requires explicit user consent per privacy principle",
                timestamp="2024-12-01T10:30:00Z",
                confidence_score=0.95,
            ),
            GovernancePrecedent(
                id="PREC-002",
                action_type="automated_decision",
                context_summary="Automated loan approval decision without explanation capability",
                outcome=DecisionOutcome.CONDITIONAL,
                principles_applied=["P005", "P004"],  # transparency, justice
                reasoning="Approved with condition that explanation mechanism is implemented",
                timestamp="2024-12-05T14:20:00Z",
                confidence_score=0.88,
                related_precedents=["PREC-003"],
            ),
            GovernancePrecedent(
                id="PREC-003",
                action_type="resource_modification",
                context_summary="High-risk system configuration change during peak hours",
                outcome=DecisionOutcome.DEFERRED,
                principles_applied=["P008", "P006"],  # safety, accountability
                reasoning="Deferred to off-peak hours to minimize potential impact",
                timestamp="2024-12-10T09:15:00Z",
                confidence_score=0.92,
            ),
            GovernancePrecedent(
                id="PREC-004",
                action_type="external_communication",
                context_summary="AI agent sending promotional content to users",
                outcome=DecisionOutcome.APPROVED,
                principles_applied=["P003", "P001"],  # autonomy, beneficence
                reasoning="Approved as users opted-in to promotional communications",
                timestamp="2024-12-15T11:45:00Z",
                confidence_score=0.97,
            ),
            GovernancePrecedent(
                id="PREC-005",
                action_type="data_processing",
                context_summary="Processing sensitive health data for analytics",
                outcome=DecisionOutcome.DENIED,
                principles_applied=["P007", "P002"],  # privacy, non-maleficence
                reasoning="Denied due to insufficient anonymization and potential re-identification risk",
                timestamp="2024-12-20T16:00:00Z",
                confidence_score=0.94,
                appeal_count=1,
            ),
        ]

        for precedent in sample_precedents:
            self._precedent_cache[precedent.id] = precedent

    @classmethod
    def get_definition(cls) -> ToolDefinition:
        """Get the MCP tool definition."""
        return ToolDefinition(
            name="query_governance_precedents",
            description=(
                "Query historical governance decisions for precedent analysis. "
                "Returns matching precedents with their outcomes, reasoning, and "
                "applied principles for consistency in decision-making."
            ),
            inputSchema=ToolInputSchema(
                type="object",
                properties={
                    "action_type": {
                        "type": "string",
                        "description": "Filter by action type (e.g., 'data_access', 'automated_decision')",
                    },
                    "outcome": {
                        "type": "string",
                        "description": "Filter by decision outcome",
                        "enum": ["approved", "denied", "conditional", "deferred", "escalated"],
                    },
                    "principles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by principles applied (principle IDs)",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start of date range (ISO 8601 date-time, e.g. 2024-12-01T00:00:00Z)",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End of date range (ISO 8601 date-time, e.g. 2024-12-31T23:59:59Z)",
                    },
                    "min_confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Minimum confidence score threshold",
                    },
                    "include_overruled": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include overruled precedents",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 10,
                        "description": "Maximum number of results",
                    },
                    "semantic_query": {
                        "type": "string",
                        "description": "Natural language query for semantic search",
                    },
                },
                required=[],
            ),
            constitutional_required=False,
        )

    async def execute(self, arguments: JSONDict) -> JSONDict:
        """
        Execute the precedent query.

        Args:
            arguments: Tool arguments including filters

        Returns:
            Matching precedents as a dictionary
        """
        self._request_count += 1

        action_type = arguments.get("action_type")
        outcome_filter = arguments.get("outcome")
        principles = arguments.get("principles", [])
        start_date = arguments.get("start_date")
        end_date = arguments.get("end_date")
        min_confidence = arguments.get("min_confidence", 0.0)
        include_overruled = arguments.get("include_overruled", False)
        limit = arguments.get("limit", 10)
        semantic_query = arguments.get("semantic_query")

        logger.info(f"Querying precedents with filters: {arguments}")

        try:
            # If we have an audit client adapter, use it
            if self.audit_client_adapter:
                precedents = await self._query_from_audit_client(arguments)
            else:
                precedents = self._query_locally(
                    action_type=action_type,
                    outcome_filter=outcome_filter,
                    principles=principles,
                    start_date=start_date,
                    end_date=end_date,
                    min_confidence=min_confidence,
                    include_overruled=include_overruled,
                    limit=limit,
                    semantic_query=semantic_query,
                )

            result = {
                "constitutional_hash": self.CONSTITUTIONAL_HASH,
                "total_count": len(precedents),
                "precedents": [p.to_dict() for p in precedents],
                "query_filters": {k: v for k, v in arguments.items() if v is not None},
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
            logger.error(f"Error querying precedents: {e}")
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

    async def _query_from_audit_client(
        self,
        arguments: JSONDict,
    ) -> list[GovernancePrecedent]:
        """Query precedents from the AuditClient."""
        raw_precedents = await self.audit_client_adapter.query_precedents(**arguments)
        return [GovernancePrecedent(**p) for p in raw_precedents]

    def _query_locally(
        self,
        action_type: str | None,
        outcome_filter: str | None,
        principles: list[str],
        start_date: str | None,
        end_date: str | None,
        min_confidence: float,
        include_overruled: bool,
        limit: int,
        semantic_query: str | None,
    ) -> list[GovernancePrecedent]:
        """Query precedents from local cache."""
        precedents = list(self._precedent_cache.values())

        # Apply filters
        if action_type:
            precedents = [p for p in precedents if action_type.lower() in p.action_type.lower()]

        if outcome_filter:
            outcome = DecisionOutcome(outcome_filter)
            precedents = [p for p in precedents if p.outcome == outcome]

        if principles:
            precedents = [
                p for p in precedents if any(pr in p.principles_applied for pr in principles)
            ]

        if min_confidence:
            precedents = [p for p in precedents if p.confidence_score >= min_confidence]

        if not include_overruled:
            precedents = [p for p in precedents if not p.overruled]

        # Simple semantic matching
        if semantic_query:
            query_lower = semantic_query.lower()
            precedents = [
                p
                for p in precedents
                if query_lower in p.context_summary.lower()
                or query_lower in p.reasoning.lower()
                or query_lower in p.action_type.lower()
            ]

        # Sort by timestamp (newest first) and limit
        precedents.sort(key=lambda p: p.timestamp, reverse=True)
        return precedents[:limit]

    def add_precedent(self, precedent: GovernancePrecedent) -> None:
        """Add a new precedent to the cache."""
        self._precedent_cache[precedent.id] = precedent

    def get_metrics(self) -> JSONDict:
        """Get tool metrics."""
        outcomes: dict[str, int] = {}
        for p in self._precedent_cache.values():
            outcome = p.outcome.value
            outcomes[outcome] = outcomes.get(outcome, 0) + 1

        return {
            "request_count": self._request_count,
            "total_precedents": len(self._precedent_cache),
            "outcome_distribution": outcomes,
            "overruled_count": len([p for p in self._precedent_cache.values() if p.overruled]),
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }
