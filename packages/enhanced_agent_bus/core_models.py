"""
ACGS-2 Enhanced Agent Bus - Core Models
Constitutional Hash: 608508a9bd224290

Core message and routing models for agent communication.
Split from models.py for improved maintainability.
"""

from __future__ import annotations

import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, TypeAlias

from pydantic import BaseModel, Field

from .enums import AutonomyTier, MessageStatus, MessageType, Priority
from .ifc.labels import IFCLabel

if TYPE_CHECKING:
    from .session_models import SessionContext

# Import type aliases
try:
    from src.core.shared.types import (
        JSONDict,
        JSONValue,
        MetadataDict,
        PerformanceMetrics,
        SecurityContext,
    )
except ImportError:
    # Fallback for standalone usage
    JSONValue: TypeAlias = object  # type: ignore[misc, no-redef]
    JSONDict: TypeAlias = dict[str, object]
    SecurityContext: TypeAlias = dict[str, object]
    MetadataDict: TypeAlias = dict[str, object]
    PerformanceMetrics: TypeAlias = dict[str, int | float | str | None]  # type: ignore[misc, no-redef]

# Import constitutional hash
try:
    from src.core.shared.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

_module = sys.modules[__name__]
sys.modules.setdefault("enhanced_agent_bus.core_models", _module)
sys.modules.setdefault("packages.enhanced_agent_bus.core_models", _module)

# Type aliases
MessageContent = JSONDict
EnumOrString = Enum | str


def get_enum_value(enum_or_str: EnumOrString) -> str:
    """
    Safely extract enum value, handling cross-module enum identity issues.

    When modules are loaded via different import paths (e.g., during testing),
    enum instances from different module loads have different class identities.
    This function extracts the underlying string value regardless of class identity.

    Args:
        enum_or_str: An enum instance or string value

    Returns:
        The string value of the enum or the stringified input
    """
    if isinstance(enum_or_str, Enum):
        return str(enum_or_str.value)
    return str(enum_or_str)


@dataclass
class RoutingContext:
    """Context for message routing in the agent bus."""

    source_agent_id: str
    target_agent_id: str
    routing_key: str = ""
    routing_tags: list[str] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    timeout_ms: int = 5000
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def __post_init__(self) -> None:
        """Validate routing context."""
        if not self.source_agent_id:
            raise ValueError("source_agent_id is required")
        if not self.target_agent_id:
            raise ValueError("target_agent_id is required")


@dataclass
class AgentMessage:
    """Agent message with constitutional compliance."""

    # Message identification
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Content and routing
    content: MessageContent = field(default_factory=dict)
    payload: MessageContent = field(default_factory=dict)
    from_agent: str = ""
    to_agent: str = ""
    sender_id: str = ""
    message_type: MessageType = MessageType.COMMAND
    routing: "RoutingContext" | None = None
    headers: dict[str, str] = field(default_factory=dict)

    # Multi-tenant security
    tenant_id: str = "default"  # Valid default for backward compatibility with TenantValidator
    security_context: SecurityContext = field(default_factory=dict)

    # Priority and lifecycle
    priority: Priority = Priority.MEDIUM
    status: MessageStatus = MessageStatus.PENDING

    # Autonomy tier (ACGS-AI-007: Safe Autonomy Tiers)
    autonomy_tier: AutonomyTier = AutonomyTier.BOUNDED

    # Constitutional compliance
    constitutional_hash: str = CONSTITUTIONAL_HASH
    constitutional_validated: bool = False

    # Metadata and extra data
    metadata: JSONDict = field(default_factory=dict)

    # Session governance (Dynamic Per-Session Governance Configuration)
    session_id: str | None = None  # Session identifier for governance routing
    session_context: "SessionContext" | None = None  # Full session context

    # Post-Quantum Cryptography support (NIST FIPS 203/204)
    pqc_signature: str | None = None  # CRYSTALS-Dilithium signature (base64)
    pqc_public_key: str | None = None  # CRYSTALS-Kyber public key (base64)
    pqc_algorithm: str | None = None  # "dilithium-3", "kyber-768", etc.

    # Payload integrity (OWASP AA05: Memory Poisoning prevention)
    # HMAC-SHA256 hex digest of the canonical payload, optional for backwards compat
    payload_hmac: str | None = None

    # MCP tool access control (AA03: privilege escalation closure).
    # Formalized from getattr() pattern per consensus C-5.
    requested_tool: str | None = None

    # Schema Evolution (T012: Event Schema Evolution)
    schema_version: str = "1.3.0"  # Current AgentMessage schema version

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None

    # Impact assessment for deliberation layer
    impact_score: float | None = None

    # Fides-inspired Information Flow Control label (Sprint 3).
    # Carries confidentiality + integrity levels for taint tracking.
    # Defaults to None (PUBLIC/MEDIUM applied at processing time when set).
    # Read by IFCMiddleware to gate message delivery.
    ifc_label: IFCLabel | None = None

    # Performance tracking
    performance_metrics: PerformanceMetrics = field(default_factory=dict)
    _cached_dict: JSONDict | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Post-initialization validation."""

    def _invalidate_cache(self) -> None:
        """Clear the cached dict when mutable fields change."""
        self._cached_dict = None

    def to_dict(self) -> JSONDict:
        """Convert message to dictionary.

        Uses a single-shot cache to avoid repeated serialization on the hot
        path (10K+ RPS).  The cache is invalidated when ``_invalidate_cache``
        is called — callers that mutate ``status``, ``constitutional_validated``,
        or ``metadata`` after construction should call it explicitly.
        """
        if self._cached_dict is not None:
            return {**self._cached_dict}
        result: JSONDict = {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "content": self.content,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": self.message_type.value,
            "tenant_id": self.tenant_id,
            "priority": self.priority.value,
            "status": self.status.value,
            "autonomy_tier": self.autonomy_tier.value,
            "constitutional_hash": self.constitutional_hash,
            "constitutional_validated": self.constitutional_validated,
            "metadata": self.metadata,
            "session_id": self.session_id,
            "session_context": self.session_context.model_dump() if self.session_context else None,
            "pqc_signature": self.pqc_signature,
            "pqc_public_key": self.pqc_public_key,
            "pqc_algorithm": self.pqc_algorithm,
            "schema_version": self.schema_version,
            "payload_hmac": self.payload_hmac,
            "requested_tool": self.requested_tool,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "ifc_label": self.ifc_label.to_dict() if self.ifc_label is not None else None,
        }
        self._cached_dict = result
        return {**self._cached_dict}

    def to_dict_raw(self) -> JSONDict:
        """Convert message to dictionary with all fields for serialization."""
        data = self.to_dict()
        data.update(
            {
                "payload": self.payload,
                "sender_id": self.sender_id,
                "security_context": self.security_context,
                "metadata": self.metadata,
                "expires_at": self.expires_at.isoformat() if self.expires_at else None,
                "impact_score": self.impact_score,
                "performance_metrics": self.performance_metrics,
                "pqc_signature": self.pqc_signature,
                "pqc_public_key": self.pqc_public_key,
                "pqc_algorithm": self.pqc_algorithm,
                "schema_version": self.schema_version,
            }
        )
        return data

    @staticmethod
    def _parse_autonomy_tier(raw: object) -> "AutonomyTier | None":
        """Parse autonomy_tier from raw value, raising ValueError on invalid input."""
        if raw is None or raw == "":
            return None
        try:
            return AutonomyTier(raw)
        except ValueError as err:
            raise ValueError(f"Invalid autonomy_tier: {raw!r}") from err

    @classmethod
    def from_dict(cls, data: JSONDict) -> "AgentMessage":
        """Create message from dictionary."""
        # Import SessionContext here to avoid circular imports
        session_context = None
        if data.get("session_context"):
            try:
                from .session_models import SessionContext

                session_context = SessionContext.model_validate(data["session_context"])
            except (ImportError, KeyError, ValueError):
                # If SessionContext is not available or parsing fails, set to None
                session_context = None

        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            conversation_id=data.get("conversation_id", str(uuid.uuid4())),
            content=data.get("content", {}),
            from_agent=data.get("from_agent", ""),
            to_agent=data.get("to_agent", ""),
            message_type=MessageType(data.get("message_type", "command")),
            tenant_id=data.get("tenant_id", "default"),  # Match model's Field default
            priority=Priority(data.get("priority", 1)),  # Default to MEDIUM/NORMAL
            status=MessageStatus(data.get("status", "pending")),
            metadata=data.get("metadata", {}),
            session_id=data.get("session_id"),
            session_context=session_context,
            pqc_signature=data.get("pqc_signature"),
            pqc_public_key=data.get("pqc_public_key"),
            pqc_algorithm=data.get("pqc_algorithm"),
            schema_version=data.get("schema_version", "1.3.0"),  # T012: Schema versioning
            requested_tool=data.get("requested_tool"),
            payload_hmac=data.get("payload_hmac"),
            autonomy_tier=cls._parse_autonomy_tier(data.get("autonomy_tier")),
            ifc_label=(
                IFCLabel.from_dict(data["ifc_label"]) if data.get("ifc_label") is not None else None
            ),
        )


@dataclass
class PQCMetadata:
    """Metadata for Post-Quantum Cryptography validation results.

    This dataclass tracks the PQC verification status and algorithm details
    for constitutional hash validation and MACI enforcement.

    Constitutional Hash: 608508a9bd224290
    """

    pqc_enabled: bool
    pqc_algorithm: str | None  # e.g., "dilithium3", "kyber768"
    classical_verified: bool
    pqc_verified: bool
    verification_mode: str  # "strict", "classical_only", "pqc_only"
    verified_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    verifier_version: str = "1.0.0"

    def to_dict(self) -> JSONDict:
        """Serialize for storage/transmission."""
        return {
            "pqc_enabled": self.pqc_enabled,
            "pqc_algorithm": self.pqc_algorithm,
            "classical_verified": self.classical_verified,
            "pqc_verified": self.pqc_verified,
            "verification_mode": self.verification_mode,
            "verified_at": self.verified_at.isoformat(),
            "verifier_version": self.verifier_version,
        }


@dataclass
class DecisionLog:
    """Structured decision log for compliance and observability."""

    trace_id: str
    span_id: str
    agent_id: str
    tenant_id: str
    policy_version: str
    risk_score: float
    decision: str
    constitutional_hash: str = CONSTITUTIONAL_HASH
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    compliance_tags: list[str] = field(default_factory=list)
    metadata: MetadataDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        """Convert log to dictionary."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "policy_version": self.policy_version,
            "risk_score": self.risk_score,
            "decision": self.decision,
            "constitutional_hash": self.constitutional_hash,
            "timestamp": self.timestamp.isoformat(),
            "compliance_tags": self.compliance_tags,
            "metadata": self.metadata,
        }


class ConversationMessage(BaseModel):
    """Single message in a multi-turn conversation.

    Used by PACAR verifier to track conversation history for
    governance policy enforcement across conversation threads.

    Constitutional Hash: 608508a9bd224290
    """

    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content text")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the message was created",
    )
    intent: str | None = Field(default=None, description="Detected intent of the message")
    verification_result: JSONDict | None = Field(
        default=None,
        description="PACAR verification result including is_valid, confidence, critique",
    )

    model_config = {"from_attributes": True}


class ConversationState(BaseModel):
    """Conversation state for multi-turn context tracking.

    Stores the full conversation history and metadata for a session,
    enabling PACAR verifier to enforce governance policies across
    multiple turns of a conversation.

    Constitutional Hash: 608508a9bd224290
    """

    session_id: str = Field(..., description="Unique session identifier")
    tenant_id: str = Field(..., description="Tenant identifier for multi-tenant isolation")
    messages: list[ConversationMessage] = Field(
        default_factory=list, description="Ordered list of conversation messages"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the conversation was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the conversation was last updated",
    )
    constitutional_hash: str = Field(
        default=CONSTITUTIONAL_HASH,
        description="Constitutional hash for compliance verification",
    )

    model_config = {"from_attributes": True}


__all__ = [
    "AgentMessage",
    "ConversationMessage",
    "ConversationState",
    "DecisionLog",
    "EnumOrString",
    # Type aliases
    "MessageContent",
    "PQCMetadata",
    # Core models
    "RoutingContext",
    # Utility functions
    "get_enum_value",
]
