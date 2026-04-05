"""
AuditClient Adapter for MCP Integration.

Bridges MCP tools/resources with the Audit Client.

Constitutional Hash: 608508a9bd224290
"""

from datetime import UTC, datetime

from typing_extensions import TypedDict

from enhanced_agent_bus.observability.structured_logging import get_logger


class _Precedent(TypedDict):
    """Type definition for precedent record."""

    id: str
    action_type: str
    context_summary: str
    outcome: str
    principles_applied: list[str]
    reasoning: str
    timestamp: str
    confidence_score: float
    appeal_count: int
    overruled: bool


try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

logger = get_logger(__name__)
_MCP_AUDIT_CLIENT_OPERATION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    LookupError,
    OSError,
    TimeoutError,
    ConnectionError,
)


class AuditClientAdapter:
    """
    Adapter for integrating MCP with AuditClient.

    Provides access to audit trail and precedent queries.
    """

    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    def __init__(
        self,
        audit_client: object | None = None,
    ):
        """
        Initialize the audit client adapter.

        Args:
            audit_client: Reference to AuditClient instance
        """
        self.audit_client = audit_client
        self._request_count = 0

    async def query_precedents(
        self,
        action_type: str | None = None,
        outcome: str | None = None,
        principles: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        min_confidence: float = 0.0,
        include_overruled: bool = False,
        limit: int = 10,
        semantic_query: str | None = None,
    ) -> list[JSONDict]:
        """
        Query governance precedents.

        Args:
            action_type: Filter by action type
            outcome: Filter by outcome
            principles: Filter by principles applied
            start_date: Start of date range
            end_date: End of date range
            min_confidence: Minimum confidence threshold
            include_overruled: Include overruled precedents
            limit: Maximum results
            semantic_query: Natural language query

        Returns:
            List of precedent dictionaries
        """
        self._request_count += 1

        if self.audit_client is None:
            return self._get_sample_precedents(action_type, outcome, principles, limit)

        try:
            precedents = await self.audit_client.query_precedents(
                action_type=action_type,
                outcome=outcome,
                principles=principles,
                start_date=start_date,
                end_date=end_date,
                min_confidence=min_confidence,
                include_overruled=include_overruled,
                limit=limit,
            )

            if semantic_query:
                # Apply semantic filtering
                query_lower = semantic_query.lower()
                precedents = [
                    p
                    for p in precedents
                    if query_lower in p.get("context_summary", "").lower()
                    or query_lower in p.get("reasoning", "").lower()
                ]

            return precedents  # type: ignore[no-any-return]

        except _MCP_AUDIT_CLIENT_OPERATION_ERRORS as e:
            logger.error(f"Audit client error: {e}")
            raise

    def _get_sample_precedents(
        self,
        action_type: str | None,
        outcome: str | None,
        principles: list[str] | None,
        limit: int,
    ) -> list[JSONDict]:
        """Get sample precedents when audit client is unavailable."""
        precedents: list[_Precedent] = [
            {
                "id": "PREC-001",
                "action_type": "data_access",
                "context_summary": "Agent requested PII without consent",
                "outcome": "denied",
                "principles_applied": ["P007", "P003"],
                "reasoning": "PII access requires explicit consent",
                "timestamp": "2024-12-01T10:30:00Z",
                "confidence_score": 0.95,
                "appeal_count": 0,
                "overruled": False,
            },
            {
                "id": "PREC-002",
                "action_type": "automated_decision",
                "context_summary": "Automated approval without explanation",
                "outcome": "conditional",
                "principles_applied": ["P005", "P004"],
                "reasoning": "Approved with condition to add explanations",
                "timestamp": "2024-12-05T14:20:00Z",
                "confidence_score": 0.88,
                "appeal_count": 0,
                "overruled": False,
            },
            {
                "id": "PREC-003",
                "action_type": "resource_modification",
                "context_summary": "High-risk config change during peak hours",
                "outcome": "deferred",
                "principles_applied": ["P008", "P006"],
                "reasoning": "Deferred to off-peak hours",
                "timestamp": "2024-12-10T09:15:00Z",
                "confidence_score": 0.92,
                "appeal_count": 0,
                "overruled": False,
            },
        ]

        # Apply filters
        if action_type:
            precedents = [p for p in precedents if action_type.lower() in p["action_type"].lower()]

        if outcome:
            precedents = [p for p in precedents if p["outcome"] == outcome]

        if principles:
            precedents = [
                p for p in precedents if any(pr in p["principles_applied"] for pr in principles)
            ]

        return [dict(p) for p in precedents[:limit]]  # type: ignore[misc]

    async def get_audit_trail(
        self,
        event_type: str | None = None,
        actor_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 50,
    ) -> list[JSONDict]:
        """
        Get audit trail entries.

        Args:
            event_type: Filter by event type
            actor_id: Filter by actor
            start_date: Start of date range
            end_date: End of date range
            limit: Maximum results

        Returns:
            List of audit entry dictionaries
        """
        self._request_count += 1

        if self.audit_client is None:
            return self._get_sample_audit_entries(event_type, actor_id, limit)

        try:
            return await self.audit_client.get_audit_trail(  # type: ignore[no-any-return]
                event_type=event_type,
                actor_id=actor_id,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            )
        except _MCP_AUDIT_CLIENT_OPERATION_ERRORS as e:
            logger.error(f"Audit trail error: {e}")
            raise

    def _get_sample_audit_entries(
        self,
        event_type: str | None,
        actor_id: str | None,
        limit: int,
    ) -> list[JSONDict]:
        """Get sample audit entries when audit client is unavailable."""
        entries = [
            {
                "id": "AUDIT-00000001",
                "event_type": "validation",
                "timestamp": datetime.now(UTC).isoformat(),
                "actor_id": "mcp-server",
                "action": "Constitutional compliance validation",
                "details": {"action": "data_access", "result": "compliant"},
                "outcome": "success",
                "constitutional_hash": self.CONSTITUTIONAL_HASH,
            },
            {
                "id": "AUDIT-00000002",
                "event_type": "decision",
                "timestamp": datetime.now(UTC).isoformat(),
                "actor_id": "governance-engine",
                "action": "Governance decision rendered",
                "details": {"request_id": "GOV-12345", "status": "approved"},
                "outcome": "approved",
                "constitutional_hash": self.CONSTITUTIONAL_HASH,
            },
        ]

        if event_type:
            entries = [e for e in entries if e["event_type"] == event_type]

        if actor_id:
            entries = [e for e in entries if e["actor_id"] == actor_id]

        return entries[:limit]

    async def log_audit_event(
        self,
        event_type: str,
        actor_id: str,
        action: str,
        details: JSONDict,
        outcome: str,
    ) -> JSONDict:
        """
        Log an audit event.

        Args:
            event_type: Type of event
            actor_id: Actor performing the action
            action: Description of action
            details: Event details
            outcome: Event outcome

        Returns:
            Created audit entry
        """
        self._request_count += 1

        if self.audit_client is None:
            # Return simulated entry
            return {
                "id": f"AUDIT-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
                "event_type": event_type,
                "timestamp": datetime.now(UTC).isoformat(),
                "actor_id": actor_id,
                "action": action,
                "details": details,
                "outcome": outcome,
                "constitutional_hash": self.CONSTITUTIONAL_HASH,
            }

        try:
            return await self.audit_client.log_event(
                event_type=event_type,
                actor_id=actor_id,
                action=action,
                details=details,
                outcome=outcome,
            )
        except _MCP_AUDIT_CLIENT_OPERATION_ERRORS as e:
            logger.error(f"Audit log error: {e}")
            raise

    def get_metrics(self) -> JSONDict:
        """Get adapter metrics."""
        return {
            "request_count": self._request_count,
            "connected": self.audit_client is not None,
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }
