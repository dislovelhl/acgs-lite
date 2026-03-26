"""
ACGS-2 Agent Message Event Schemas
Constitutional Hash: 608508a9bd224290

Versioned schemas for agent-to-agent communication messages.
Supports evolution from V1 (basic messaging) to V2 (enhanced with
session governance and PQC support).

Version History:
- V1 (1.0.0): Basic agent message with content and routing
- V2 (2.0.0): Added session governance, PQC fields, impact scoring
"""

from datetime import datetime
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


class MessageTypeEnum(StrEnum):
    """Types of messages in the agent bus."""

    COMMAND = "command"
    QUERY = "query"
    RESPONSE = "response"
    EVENT = "event"
    NOTIFICATION = "notification"
    HEARTBEAT = "heartbeat"
    GOVERNANCE_REQUEST = "governance_request"
    GOVERNANCE_RESPONSE = "governance_response"
    CONSTITUTIONAL_VALIDATION = "constitutional_validation"


class PriorityEnum(StrEnum):
    """Message priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class MessageStatusEnum(StrEnum):
    """Message processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"
    VALIDATED = "validated"


# =============================================================================
# V1: Basic Agent Message (1.0.0)
# =============================================================================


class AgentMessageV1(EventSchemaBase):
    """
    Agent Message Schema V1 - Basic agent-to-agent communication.

    Constitutional Hash: 608508a9bd224290

    This is the foundational message format for the ACGS-2 enhanced agent bus.
    Supports basic routing, content, and constitutional validation.
    """

    SCHEMA_NAME: ClassVar[str] = "AgentMessage"
    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion(1, 0, 0)

    # Routing
    from_agent: str = Field(..., description="Source agent identifier")
    to_agent: str = Field(default="", description="Target agent identifier")

    # Content
    content: JSONDict = Field(default_factory=dict, description="Message content payload")
    message_type: MessageTypeEnum = Field(
        default=MessageTypeEnum.COMMAND,
        description="Type of message",
    )

    # Multi-tenant
    tenant_id: str = Field(default="default", description="Tenant identifier")

    # Priority and status
    priority: PriorityEnum = Field(
        default=PriorityEnum.NORMAL,
        description="Message priority",
    )
    status: MessageStatusEnum = Field(
        default=MessageStatusEnum.PENDING,
        description="Processing status",
    )

    # Metadata
    metadata: JSONDict = Field(
        default_factory=dict,
        description="Additional message metadata",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Message headers for routing",
    )

    model_config: ClassVar[dict[str, Any]] = {"from_attributes": True}


# =============================================================================
# V2: Enhanced Agent Message (2.0.0)
# =============================================================================


class AgentMessageV2(EventSchemaBase):
    """
    Agent Message Schema V2 - Enhanced with session governance and PQC.

    Constitutional Hash: 608508a9bd224290

    V2 adds:
    - Session governance support for dynamic per-session policies
    - Post-Quantum Cryptography (PQC) signature fields
    - Impact scoring for deliberation layer integration
    - Conversation tracking for multi-turn interactions
    - Performance metrics

    Migration from V1:
    - All V1 fields are preserved
    - New fields have defaults for backward compatibility
    """

    SCHEMA_NAME: ClassVar[str] = "AgentMessage"
    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion(2, 0, 0)

    # === V1 Fields (preserved) ===

    # Routing
    from_agent: str = Field(..., description="Source agent identifier")
    to_agent: str = Field(default="", description="Target agent identifier")

    # Content
    content: JSONDict = Field(default_factory=dict, description="Message content payload")
    message_type: MessageTypeEnum = Field(
        default=MessageTypeEnum.COMMAND,
        description="Type of message",
    )

    # Multi-tenant
    tenant_id: str = Field(default="default", description="Tenant identifier")

    # Priority and status
    priority: PriorityEnum = Field(
        default=PriorityEnum.NORMAL,
        description="Message priority",
    )
    status: MessageStatusEnum = Field(
        default=MessageStatusEnum.PENDING,
        description="Processing status",
    )

    # Metadata
    metadata: JSONDict = Field(
        default_factory=dict,
        description="Additional message metadata",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Message headers for routing",
    )

    # === V2 New Fields ===

    # Conversation tracking
    conversation_id: str | None = Field(
        default=None,
        description="Identifier for multi-turn conversation tracking",
    )
    reply_to_message_id: str | None = Field(
        default=None,
        description="ID of message this is replying to",
    )

    # Session governance (Dynamic Per-Session Governance)
    session_id: str | None = Field(
        default=None,
        description="Session identifier for governance routing",
    )
    session_governance_config: JSONDict | None = Field(
        default=None,
        description="Session-specific governance configuration",
    )

    # Post-Quantum Cryptography support (NIST FIPS 203/204)
    pqc_signature: str | None = Field(
        default=None,
        description="CRYSTALS-Dilithium signature (base64)",
    )
    pqc_public_key: str | None = Field(
        default=None,
        description="CRYSTALS-Kyber public key (base64)",
    )
    pqc_algorithm: str | None = Field(
        default=None,
        description="PQC algorithm identifier (e.g., 'dilithium-3', 'kyber-768')",
    )

    # Impact assessment for deliberation layer
    impact_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Impact score for routing to deliberation layer (0.0-1.0)",
    )
    requires_deliberation: bool = Field(
        default=False,
        description="Flag indicating if message requires deliberation",
    )

    # Performance tracking
    performance_metrics: JSONDict = Field(
        default_factory=dict,
        description="Performance metrics for observability",
    )

    # Expiration
    expires_at: datetime | None = Field(
        default=None,
        description="Message expiration timestamp",
    )

    model_config: ClassVar[dict[str, Any]] = {"from_attributes": True}


# =============================================================================
# Migration Functions
# =============================================================================


def migrate_v1_to_v2(data: JSONDict) -> JSONDict:
    """
    Migrate AgentMessage from V1 to V2 format.

    Adds default values for all new V2 fields while preserving
    existing V1 data.

    Constitutional Hash: 608508a9bd224290
    """
    result = data.copy()

    # Add V2 fields with defaults
    result.setdefault("conversation_id", None)
    result.setdefault("reply_to_message_id", None)
    result.setdefault("session_id", None)
    result.setdefault("session_governance_config", None)
    result.setdefault("pqc_signature", None)
    result.setdefault("pqc_public_key", None)
    result.setdefault("pqc_algorithm", None)
    result.setdefault("impact_score", None)
    result.setdefault("requires_deliberation", False)
    result.setdefault("performance_metrics", {})
    result.setdefault("expires_at", None)

    # Update schema version
    result["schema_version"] = "v2.0.0"

    return result


# =============================================================================
# Registration
# =============================================================================


def register_agent_message_schemas() -> None:
    """Register all AgentMessage schema versions with the registry."""
    registry = get_schema_registry()

    # Register V1 (baseline)
    registry.register(
        AgentMessageV1,
        status=SchemaStatus.DEPRECATED,
        compatibility_mode=SchemaCompatibility.BACKWARD,
        description="Basic agent message format - baseline version",
    )

    # Register V2 (current)
    registry.register(
        AgentMessageV2,
        status=SchemaStatus.ACTIVE,
        compatibility_mode=SchemaCompatibility.BACKWARD,
        migration_from=SchemaVersion(1, 0, 0),
        description="Enhanced agent message with session governance and PQC support",
    )

    # Register migration
    registry.register_migration(
        "AgentMessage",
        SchemaVersion(1, 0, 0),
        SchemaVersion(2, 0, 0),
        migrate_v1_to_v2,
    )


__all__ = [
    "AgentMessageV1",
    "AgentMessageV2",
    "MessageStatusEnum",
    "MessageTypeEnum",
    "PriorityEnum",
    "migrate_v1_to_v2",
    "register_agent_message_schemas",
]
