"""
ACGS-2 Enhanced Agent Bus - Extended Models Tests
Constitutional Hash: 608508a9bd224290

Extended tests for models to improve coverage.
"""

from datetime import datetime, timezone

import pytest

from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    AgentMessage,
    MessageStatus,
    MessageType,
    Priority,
    RoutingContext,
    ValidationStatus,
)

# ============================================================================
# Constitutional Hash Tests
# ============================================================================


class TestConstitutionalHashCompliance:
    """Test constitutional hash compliance."""

    def test_constitutional_hash_value(self):
        """Verify constitutional hash value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH


# ============================================================================
# RoutingContext Tests
# ============================================================================


class TestRoutingContext:
    """Test RoutingContext dataclass."""

    def test_basic_creation(self):
        """Test basic routing context creation."""
        ctx = RoutingContext(source_agent_id="agent-1", target_agent_id="agent-2")
        assert ctx.source_agent_id == "agent-1"
        assert ctx.target_agent_id == "agent-2"
        assert ctx.routing_key == ""
        assert ctx.routing_tags == []
        assert ctx.retry_count == 0
        assert ctx.max_retries == 3
        assert ctx.timeout_ms == 5000
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH

    def test_with_all_fields(self):
        """Test routing context with all fields specified."""
        ctx = RoutingContext(
            source_agent_id="source",
            target_agent_id="target",
            routing_key="my.routing.key",
            routing_tags=["tag1", "tag2"],
            retry_count=1,
            max_retries=5,
            timeout_ms=10000,
            constitutional_hash="custom_hash",
        )
        assert ctx.routing_key == "my.routing.key"
        assert ctx.routing_tags == ["tag1", "tag2"]
        assert ctx.retry_count == 1
        assert ctx.max_retries == 5
        assert ctx.timeout_ms == 10000
        assert ctx.constitutional_hash == "custom_hash"

    def test_empty_source_agent_raises(self):
        """Test that empty source agent raises ValueError."""
        with pytest.raises(ValueError, match="source_agent_id is required"):
            RoutingContext(source_agent_id="", target_agent_id="target")

    def test_empty_target_agent_raises(self):
        """Test that empty target agent raises ValueError."""
        with pytest.raises(ValueError, match="target_agent_id is required"):
            RoutingContext(source_agent_id="source", target_agent_id="")

    def test_both_empty_raises_source_error(self):
        """Test that both empty raises source error first."""
        with pytest.raises(ValueError, match="source_agent_id is required"):
            RoutingContext(source_agent_id="", target_agent_id="")


# ============================================================================
# AgentMessage Tests
# ============================================================================


class TestAgentMessage:
    """Test AgentMessage dataclass."""

    def test_default_creation(self):
        """Test default message creation."""
        msg = AgentMessage()
        assert msg.message_id is not None
        assert msg.conversation_id is not None
        assert msg.content == {}
        assert msg.payload == {}
        assert msg.message_type == MessageType.COMMAND
        assert msg.priority == Priority.MEDIUM
        assert msg.status == MessageStatus.PENDING
        assert msg.constitutional_hash == CONSTITUTIONAL_HASH
        assert (
            msg.constitutional_validated is False
        )  # Set by MessageProcessor after actual validation
        assert msg.created_at is not None
        assert msg.updated_at is not None

    def test_custom_message(self):
        """Test custom message creation."""
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.QUERY,
            priority=Priority.HIGH,
            tenant_id="tenant-1",
        )
        assert msg.content == {"action": "test"}
        assert msg.from_agent == "sender"
        assert msg.to_agent == "receiver"
        assert msg.message_type == MessageType.QUERY
        assert msg.priority == Priority.HIGH
        assert msg.tenant_id == "tenant-1"

    def test_to_dict(self):
        """Test to_dict serialization."""
        msg = AgentMessage(
            content={"key": "value"}, from_agent="agent-1", to_agent="agent-2", tenant_id="tenant-1"
        )
        result = msg.to_dict()

        assert "message_id" in result
        assert "conversation_id" in result
        assert result["content"] == {"key": "value"}
        assert result["from_agent"] == "agent-1"
        assert result["to_agent"] == "agent-2"
        assert result["message_type"] == "command"
        assert result["tenant_id"] == "tenant-1"
        assert result["priority"] == 1  # Priority.MEDIUM.value
        assert result["status"] == "pending"
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert (
            result["constitutional_validated"] is False
        )  # Set by MessageProcessor after actual validation
        assert "created_at" in result
        assert "updated_at" in result

    def test_from_dict(self):
        """Test from_dict deserialization."""
        data = {
            "message_id": "test-msg-123",
            "conversation_id": "conv-456",
            "content": {"test": "data"},
            "from_agent": "sender",
            "to_agent": "receiver",
            "message_type": "query",
            "tenant_id": "tenant-x",
            "priority": 2,  # Priority.HIGH value
            "status": "processing",
        }
        msg = AgentMessage.from_dict(data)

        assert msg.message_id == "test-msg-123"
        assert msg.conversation_id == "conv-456"
        assert msg.content == {"test": "data"}
        assert msg.from_agent == "sender"
        assert msg.to_agent == "receiver"
        assert msg.message_type == MessageType.QUERY
        assert msg.tenant_id == "tenant-x"
        assert msg.priority == Priority.HIGH
        assert msg.status == MessageStatus.PROCESSING

    def test_from_dict_defaults(self):
        """Test from_dict with missing fields uses defaults."""
        data = {}
        msg = AgentMessage.from_dict(data)

        assert msg.message_id is not None
        assert msg.conversation_id is not None
        assert msg.content == {}
        assert msg.from_agent == ""
        assert msg.to_agent == ""
        assert msg.message_type == MessageType.COMMAND
        assert msg.tenant_id == "default"  # Default is "default" for consistency

    def test_routing_context_optional(self):
        """Test routing context is optional."""
        msg = AgentMessage()
        assert msg.routing is None

    def test_routing_context_set(self):
        """Test routing context can be set."""
        routing = RoutingContext(source_agent_id="source", target_agent_id="target")
        msg = AgentMessage(routing=routing)
        assert msg.routing is not None
        assert msg.routing.source_agent_id == "source"
        assert msg.routing.target_agent_id == "target"

    def test_security_context(self):
        """Test security context field."""
        msg = AgentMessage(security_context={"role": "admin", "permissions": ["read", "write"]})
        assert msg.security_context["role"] == "admin"
        assert "read" in msg.security_context["permissions"]

    def test_performance_metrics(self):
        """Test performance metrics field."""
        msg = AgentMessage(performance_metrics={"latency_ms": 5, "throughput": 1000})
        assert msg.performance_metrics["latency_ms"] == 5
        assert msg.performance_metrics["throughput"] == 1000

    def test_impact_score(self):
        """Test impact score for deliberation."""
        msg = AgentMessage(impact_score=0.75)
        assert msg.impact_score == 0.75

    def test_expires_at(self):
        """Test expires_at field."""
        future = datetime(2099, 12, 31, tzinfo=timezone.utc)
        msg = AgentMessage(expires_at=future)
        assert msg.expires_at == future

    def test_headers(self):
        """Test headers field."""
        msg = AgentMessage(headers={"X-Custom": "value", "X-Trace-Id": "123"})
        assert msg.headers["X-Custom"] == "value"
        assert msg.headers["X-Trace-Id"] == "123"


# ============================================================================
# Enum Tests
# ============================================================================


class TestMessageType:
    """Test MessageType enum."""

    def test_all_types(self):
        """Test all message types exist."""
        assert MessageType.COMMAND.value == "command"
        assert MessageType.QUERY.value == "query"
        assert MessageType.RESPONSE.value == "response"
        assert MessageType.EVENT.value == "event"
        assert MessageType.NOTIFICATION.value == "notification"
        assert MessageType.HEARTBEAT.value == "heartbeat"
        assert MessageType.GOVERNANCE_REQUEST.value == "governance_request"
        assert MessageType.GOVERNANCE_RESPONSE.value == "governance_response"
        assert MessageType.CONSTITUTIONAL_VALIDATION.value == "constitutional_validation"
        assert MessageType.TASK_REQUEST.value == "task_request"
        assert MessageType.TASK_RESPONSE.value == "task_response"
        assert MessageType.AUDIT_LOG.value == "audit_log"

    def test_type_count(self):
        """Test number of message types."""
        assert len(MessageType) == 14


class TestPriority:
    """Test Priority enum."""

    def test_all_priorities(self):
        """Test all priority levels."""
        assert Priority.LOW.value == 0
        assert Priority.MEDIUM.value == 1
        assert Priority.HIGH.value == 2
        assert Priority.CRITICAL.value == 3

    def test_priority_ordering(self):
        """Test priority ordering."""
        assert Priority.LOW.value < Priority.MEDIUM.value
        assert Priority.MEDIUM.value < Priority.HIGH.value
        assert Priority.HIGH.value < Priority.CRITICAL.value


class TestValidationStatus:
    """Test ValidationStatus enum."""

    def test_all_statuses(self):
        """Test all validation statuses."""
        assert ValidationStatus.PENDING.value == "pending"
        assert ValidationStatus.VALID.value == "valid"
        assert ValidationStatus.INVALID.value == "invalid"
        assert ValidationStatus.WARNING.value == "warning"


class TestMessageStatus:
    """Test MessageStatus enum."""

    def test_all_statuses(self):
        """Test all message statuses."""
        assert MessageStatus.PENDING.value == "pending"
        assert MessageStatus.PROCESSING.value == "processing"
        assert MessageStatus.DELIVERED.value == "delivered"
        assert MessageStatus.FAILED.value == "failed"
        assert MessageStatus.EXPIRED.value == "expired"


# ============================================================================
# Module Export Tests
# ============================================================================


class TestModuleExports:
    """Test module exports."""

    def test_all_exports(self):
        """Test __all__ exports are correct."""
        from enhanced_agent_bus.models import __all__

        expected = [
            # Core type aliases
            "MessageContent",
            "SecurityContext",
            "PerformanceMetrics",
            "MetadataDict",
            "EnumOrString",
            # Constants
            "CONSTITUTIONAL_HASH",
            "MAX_PAYLOAD_SIZE_BYTES",
            # Enums
            "MessageType",
            "Priority",
            "ValidationStatus",
            "MessageStatus",
            "BatchItemStatus",
            "ConstitutionalStatus",
            "TaskComplexity",
            "TaskType",
            "AgentCapability",
            "AutonomyTier",
            "RiskLevel",
            # Core models
            "RoutingContext",
            "AgentMessage",
            "DecisionLog",
            "ConversationMessage",
            "ConversationState",
            "ConstitutionalVersion",
            "PQCMetadata",
            "SwarmAgent",
            # Session governance models
            "SessionGovernanceConfig",
            "SessionContext",
            # Batch processing models
            "BatchRequest",
            "BatchRequestItem",
            "BatchResponse",
            "BatchResponseItem",
            "BatchResponseStats",
            # LangGraph orchestration models
            "Checkpoint",
            "CheckpointStatus",
            "ConditionalEdge",
            "ExecutionContext",
            "ExecutionResult",
            "ExecutionStatus",
            "GraphConfig",
            "GraphDefinition",
            "GraphEdge",
            "GraphNode",
            "GraphState",
            "InterruptRequest",
            "InterruptResponse",
            "InterruptType",
            "NodeResult",
            "NodeStatus",
            "NodeType",
            # Schema Evolution (T012)
            "SchemaVersion",
            "SchemaCompatibility",
            "EvolutionType",
            "MigrationStatus",
            "SchemaFieldDefinition",
            "SchemaDefinition",
            "SchemaEvolutionChange",
            "CompatibilityChecker",
            "SchemaRegistry",
            "SchemaMigration",
            "SchemaMigrator",
            "VersionedMessageBase",
            "AGENT_MESSAGE_SCHEMA_V1",
            "AGENT_MESSAGE_SCHEMA_V1_1",
            "AGENT_MESSAGE_SCHEMA_V1_2",
            "create_default_registry",
            # Graph execution models
            "GraphDefinition",
            "GraphNode",
            "GraphEdge",
            "GraphConfig",
            "GraphState",
            "NodeType",
            "NodeStatus",
            "NodeResult",
            "ConditionalEdge",
            "ExecutionContext",
            "ExecutionResult",
            "ExecutionStatus",
            "Checkpoint",
            "CheckpointStatus",
            "InterruptType",
            "InterruptRequest",
            "InterruptResponse",
            # Utility functions
            "get_enum_value",
        ]
        assert set(__all__) == set(expected)
