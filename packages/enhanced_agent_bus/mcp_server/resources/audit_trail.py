"""
Audit Trail MCP Resource.

Provides read access to the governance audit trail.

Constitutional Hash: 608508a9bd224290
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from ..protocol.types import ResourceDefinition

logger = get_logger(__name__)
AUDIT_TRAIL_READ_ERRORS = (RuntimeError, ValueError, TypeError, KeyError, AttributeError)


class AuditEventType(Enum):
    """Types of audit events."""

    VALIDATION = "validation"
    DECISION = "decision"
    PRINCIPLE_ACCESS = "principle_access"
    PRECEDENT_QUERY = "precedent_query"
    ESCALATION = "escalation"
    APPEAL = "appeal"
    SYSTEM = "system"


@dataclass
class AuditEntry:
    """An audit trail entry."""

    id: str
    event_type: AuditEventType
    timestamp: str
    actor_id: str
    action: str
    details: JSONDict
    outcome: str
    constitutional_hash: str

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "actor_id": self.actor_id,
            "action": self.action,
            "details": self.details,
            "outcome": self.outcome,
            "constitutional_hash": self.constitutional_hash,
        }


class AuditTrailResource:
    """
    MCP Resource for governance audit trail.

    Provides read-only access to the governance audit trail
    for compliance and accountability purposes.
    """

    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH

    URI = "acgs2://governance/audit-trail"

    def __init__(
        self,
        audit_client_adapter: object | None = None,
        max_entries: int = 1000,
    ):
        """
        Initialize the audit trail resource.

        Args:
            audit_client_adapter: Optional adapter to AuditClient
            max_entries: Maximum number of entries to store
        """
        self.audit_client_adapter = audit_client_adapter
        self.max_entries = max_entries
        self._access_count = 0
        self._entries: list[AuditEntry] = []
        self._entry_counter = 0

    @classmethod
    def get_definition(cls) -> ResourceDefinition:
        """Get the MCP resource definition."""
        return ResourceDefinition(
            uri=cls.URI,
            name="Audit Trail",
            description=(
                "Governance audit trail for compliance and accountability. "
                "Tracks all governance events, decisions, and system actions."
            ),
            mimeType="application/json",
            constitutional_scope="read",
        )

    async def read(self, params: JSONDict | None = None) -> str:
        """
        Read the audit trail.

        Args:
            params: Optional parameters (event_type, start_date, limit, etc.)

        Returns:
            JSON string of audit entries
        """
        self._access_count += 1
        params = params or {}
        event_type_filter = params.get("event_type")
        actor_filter = params.get("actor_id")
        limit = params.get("limit", 50)
        start_date = params.get("start_date")
        end_date = params.get("end_date")

        logger.info(f"Reading audit trail (limit={limit})")

        try:
            if self.audit_client_adapter:
                entries = await self._read_from_adapter(params)
            else:
                entries = self._read_locally(
                    event_type_filter,
                    actor_filter,
                    start_date,
                    end_date,
                    limit,
                )

            return json.dumps(
                {
                    "constitutional_hash": self.CONSTITUTIONAL_HASH,
                    "total_count": len(entries),
                    "entries": [e.to_dict() for e in entries],
                    "filters_applied": {k: v for k, v in params.items() if v is not None},
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )

        except AUDIT_TRAIL_READ_ERRORS as e:
            logger.error(f"Error reading audit trail resource: {e}")
            return json.dumps(
                {
                    "error": str(e),
                    "constitutional_hash": self.CONSTITUTIONAL_HASH,
                }
            )

    async def _read_from_adapter(
        self,
        params: JSONDict,
    ) -> list[AuditEntry]:
        """Read audit entries from the adapter."""
        raw_entries = await self.audit_client_adapter.get_audit_trail(**params)
        return [AuditEntry(**e) for e in raw_entries]

    def _read_locally(
        self,
        event_type_filter: str | None,
        actor_filter: str | None,
        start_date: str | None,
        end_date: str | None,
        limit: int,
    ) -> list[AuditEntry]:
        """Read audit entries from local storage."""
        entries = list(self._entries)

        # Apply filters
        if event_type_filter:
            event_type = AuditEventType(event_type_filter)
            entries = [e for e in entries if e.event_type == event_type]

        if actor_filter:
            entries = [e for e in entries if e.actor_id == actor_filter]

        if start_date:
            entries = [e for e in entries if e.timestamp >= start_date]

        if end_date:
            entries = [e for e in entries if e.timestamp <= end_date]

        # Sort by timestamp (newest first) and limit
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[:limit]

    def log_event(
        self,
        event_type: AuditEventType,
        actor_id: str,
        action: str,
        details: JSONDict,
        outcome: str,
    ) -> AuditEntry:
        """
        Log an audit event.

        Args:
            event_type: Type of audit event
            actor_id: ID of the actor performing the action
            action: Description of the action
            details: Additional event details
            outcome: Outcome of the action

        Returns:
            The created audit entry
        """
        self._entry_counter += 1

        entry = AuditEntry(
            id=f"AUDIT-{self._entry_counter:08d}",
            event_type=event_type,
            timestamp=datetime.now(UTC).isoformat(),
            actor_id=actor_id,
            action=action,
            details=details,
            outcome=outcome,
            constitutional_hash=self.CONSTITUTIONAL_HASH,
        )

        self._entries.append(entry)

        # Maintain max size
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries :]

        logger.info(f"Audit event logged: {entry.id} - {action}")
        return entry

    def get_metrics(self) -> JSONDict:
        """Get resource access metrics."""
        event_counts: dict[str, int] = {}
        for entry in self._entries:
            event_type = entry.event_type.value
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        return {
            "access_count": self._access_count,
            "entry_count": len(self._entries),
            "event_type_distribution": event_counts,
            "uri": self.URI,
            "constitutional_hash": self.CONSTITUTIONAL_HASH,
        }
