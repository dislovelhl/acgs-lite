"""
ACGS-2 Audit Event Schemas
Constitutional Hash: cdd01ef066bc6cf2

Versioned schemas for audit trail events.
Records all significant system events for compliance and forensics.

Version History:
- V1 (1.0.0): Comprehensive audit event with categorization and blockchain anchoring
"""

from enum import StrEnum
from typing import Any, ClassVar

from pydantic import Field

from src.core.shared.schema_registry import (
    EventSchemaBase,
    SchemaCompatibility,
    SchemaStatus,
    SchemaVersion,
    get_schema_registry,
)
from src.core.shared.types import JSONDict

# =============================================================================
# Enums
# =============================================================================


class AuditEventCategory(StrEnum):
    """Categories of audit events."""

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    CONFIGURATION_CHANGE = "configuration_change"
    POLICY_CHANGE = "policy_change"
    SYSTEM_EVENT = "system_event"
    SECURITY_EVENT = "security_event"
    GOVERNANCE_EVENT = "governance_event"
    COMPLIANCE_EVENT = "compliance_event"
    ERROR = "error"


class AuditEventSeverity(StrEnum):
    """Severity levels for audit events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditOutcome(StrEnum):
    """Outcome of the audited action."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    DENIED = "denied"
    PENDING = "pending"


class BlockchainAnchorStatus(StrEnum):
    """Status of blockchain anchoring."""

    NOT_ANCHORED = "not_anchored"
    PENDING = "pending"
    ANCHORED = "anchored"
    FAILED = "failed"


# =============================================================================
# V1: Audit Event (1.0.0)
# =============================================================================


class AuditEventV1(EventSchemaBase):
    """
    Audit Event Schema V1 - Comprehensive audit trail event.

    Constitutional Hash: cdd01ef066bc6cf2

    Records all significant system events with:
    - Event categorization and severity
    - Actor and resource identification
    - Outcome and impact assessment
    - Blockchain anchoring for immutability
    - Compliance tagging
    """

    SCHEMA_NAME: ClassVar[str] = "AuditEvent"
    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion(1, 0, 0)

    # Event identification
    audit_id: str | None = Field(
        default=None,
        description="Unique identifier for this audit entry",
    )
    sequence_number: int | None = Field(
        default=None,
        description="Sequence number for ordering",
    )

    # Event classification
    category: AuditEventCategory = Field(
        ...,
        description="Category of the audit event",
    )
    severity: AuditEventSeverity = Field(
        default=AuditEventSeverity.INFO,
        description="Severity level of the event",
    )
    action: str = Field(..., description="Action that was performed")
    outcome: AuditOutcome = Field(
        default=AuditOutcome.SUCCESS,
        description="Outcome of the action",
    )

    # Actor information
    actor_id: str = Field(..., description="Identifier of the actor performing the action")
    actor_type: str = Field(
        default="user",
        description="Type of actor (user, agent, service, system)",
    )
    actor_ip: str | None = Field(
        default=None,
        description="IP address of the actor",
    )
    actor_user_agent: str | None = Field(
        default=None,
        description="User agent string",
    )

    # Resource information
    resource_type: str | None = Field(
        default=None,
        description="Type of resource affected",
    )
    resource_id: str | None = Field(
        default=None,
        description="Identifier of the resource",
    )
    resource_name: str | None = Field(
        default=None,
        description="Human-readable resource name",
    )

    # Multi-tenant
    tenant_id: str = Field(
        default="default",
        description="Tenant identifier",
    )

    # Event details
    description: str = Field(
        default="",
        description="Human-readable description of the event",
    )
    details: JSONDict = Field(
        default_factory=dict,
        description="Additional event details",
    )

    # Changes (for modification events)
    old_value: str | int | float | bool | dict[str, object] | list[object] | None = Field(
        default=None,
        description="Previous value (for changes)",
    )
    new_value: str | int | float | bool | dict[str, object] | list[object] | None = Field(
        default=None,
        description="New value (for changes)",
    )
    changes: list[JSONDict] = Field(
        default_factory=list,
        description="List of changes made",
    )

    # Request context
    request_id: str | None = Field(
        default=None,
        description="Request ID for correlation",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation ID for distributed tracing",
    )
    session_id: str | None = Field(
        default=None,
        description="Session identifier",
    )

    # Compliance and governance
    compliance_tags: list[str] = Field(
        default_factory=list,
        description="Compliance framework tags (GDPR, SOC2, etc.)",
    )
    policy_ids: list[str] = Field(
        default_factory=list,
        description="Related policy identifiers",
    )
    requires_review: bool = Field(
        default=False,
        description="Flag indicating if event requires human review",
    )

    # Blockchain anchoring
    anchor_status: BlockchainAnchorStatus = Field(
        default=BlockchainAnchorStatus.NOT_ANCHORED,
        description="Status of blockchain anchoring",
    )
    merkle_root: str | None = Field(
        default=None,
        description="Merkle tree root hash",
    )
    merkle_proof: list[str] | None = Field(
        default=None,
        description="Merkle proof for verification",
    )
    blockchain_tx_id: str | None = Field(
        default=None,
        description="Blockchain transaction ID",
    )
    blockchain_network: str | None = Field(
        default=None,
        description="Blockchain network (ethereum, solana, etc.)",
    )

    # Impact assessment
    impact_level: str | None = Field(
        default=None,
        description="Impact level (low, medium, high, critical)",
    )
    affected_users_count: int | None = Field(
        default=None,
        description="Number of users affected",
    )
    data_classification: str | None = Field(
        default=None,
        description="Classification of data involved",
    )

    # Error information (for failure outcomes)
    error_code: str | None = Field(
        default=None,
        description="Error code if action failed",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if action failed",
    )
    stack_trace: str | None = Field(
        default=None,
        description="Stack trace for errors (redacted for security)",
    )

    # Retention
    retention_days: int = Field(
        default=90,
        description="Number of days to retain this audit entry",
    )
    is_immutable: bool = Field(
        default=True,
        description="Whether this entry is immutable",
    )

    model_config: ClassVar[dict[str, Any]] = {"from_attributes": True}


# =============================================================================
# Registration
# =============================================================================


def register_audit_event_schemas() -> None:
    """Register all AuditEvent schema versions with the registry."""
    registry = get_schema_registry()

    # Register V1
    registry.register(
        AuditEventV1,
        status=SchemaStatus.ACTIVE,
        compatibility_mode=SchemaCompatibility.BACKWARD,
        description="Comprehensive audit event with blockchain anchoring support",
    )


__all__ = [
    "AuditEventCategory",
    "AuditEventSeverity",
    "AuditEventV1",
    "AuditOutcome",
    "BlockchainAnchorStatus",
    "register_audit_event_schemas",
]
