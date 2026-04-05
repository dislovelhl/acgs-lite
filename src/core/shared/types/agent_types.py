# Constitutional Hash: 608508a9bd224290
"""Agent, workflow, message, and event type aliases for ACGS-2."""

from typing import TypedDict

from .json_types import JSONDict, JSONValue

# Agent data structures
AgentID = str  # Agent identifier
AgentContext = dict[str, JSONValue]  # Agent execution context
AgentState = dict[str, JSONValue]  # Agent state data
AgentMetadata = dict[str, JSONValue]  # Agent metadata


class AgentInfo(TypedDict, total=False):
    """Standardized agent information structure."""

    agent_id: str
    agent_type: str
    capabilities: list[str]
    tenant_id: str
    maci_role: str | None
    registered_at: str
    updated_at: str
    constitutional_hash: str
    identity: "AgentIdentity"
    metadata: "MessageMetadata"


class AgentIdentity(TypedDict, total=False):
    """Normalized runtime identity attached to registered agents."""

    principal_id: str
    principal_type: str
    tenant_id: str
    auth_method: str
    scopes: list[str]
    trust_level: str
    issued_at: str
    expires_at: str | None
    constitutional_hash: str
    metadata: "MessageMetadata"


# Workflow data structures
WorkflowID = str  # Workflow identifier
WorkflowContext = dict[str, JSONValue]  # Workflow execution context
WorkflowState = dict[str, JSONValue]  # Workflow state data
StepResult = dict[str, JSONValue]  # Workflow step result
StepParameters = dict[str, JSONValue]  # Workflow step parameters

# Context and memory
ContextData = dict[str, JSONValue]  # Generic context data
MemoryData = dict[str, JSONValue]  # Memory system data
SessionData = dict[str, JSONValue]  # Session data

# Message bus types
MessageID = str  # Message identifier
MessagePayload = dict[str, JSONValue]  # Message payload
MessageHeaders = dict[str, str]  # Message headers
MessageMetadata = dict[str, JSONValue]  # Message metadata

# Event types
EventID = str  # Event identifier
EventData = dict[str, JSONValue]  # Event payload data
EventContext = dict[str, JSONValue]  # Event context
EventMetadata = dict[str, JSONValue]  # Event metadata

# Kafka/messaging
KafkaMessage = JSONDict  # Kafka consumer message object (typically dict-like)
TopicName = str  # Kafka topic name

__all__ = [
    "AgentContext",
    "AgentID",
    "AgentIdentity",
    "AgentInfo",
    "AgentMetadata",
    "AgentState",
    "ContextData",
    "EventContext",
    "EventData",
    "EventID",
    "EventMetadata",
    "KafkaMessage",
    "MemoryData",
    "MessageHeaders",
    "MessageID",
    "MessageMetadata",
    "MessagePayload",
    "SessionData",
    "StepParameters",
    "StepResult",
    "TopicName",
    "WorkflowContext",
    "WorkflowID",
    "WorkflowState",
]
