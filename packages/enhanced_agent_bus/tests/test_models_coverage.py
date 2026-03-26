"""
ACGS-2 Models Coverage Tests
Constitutional Hash: 608508a9bd224290

Extended tests to increase models.py coverage.
"""

from datetime import datetime, timezone

import pytest

try:
    from enhanced_agent_bus.models import (
        CONSTITUTIONAL_HASH,
        AgentMessage,
        DecisionLog,
        MessageStatus,
        MessageType,
        Priority,
        RoutingContext,
    )
except ImportError:
    from models import (
        CONSTITUTIONAL_HASH,
        AgentMessage,
        DecisionLog,
        MessageStatus,
        MessageType,
        Priority,
        RoutingContext,
    )


class TestAgentMessageExtended:
    """Extended tests for AgentMessage model."""

    def test_create_message_basic(self):
        """Create basic message with minimal args."""
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="agent_a",
            to_agent="agent_b",
        )
        assert msg.from_agent == "agent_a"
        assert msg.to_agent == "agent_b"
        assert msg.constitutional_hash == CONSTITUTIONAL_HASH

    def test_message_default_values(self):
        """Message has correct default values."""
        msg = AgentMessage(
            content={"action": "test"},
            from_agent="sender",
            to_agent="receiver",
        )
        assert msg.message_type == MessageType.COMMAND
        assert msg.priority == Priority.NORMAL
        assert msg.status == MessageStatus.PENDING
        # tenant_id defaults to "default" for consistency
        assert msg.tenant_id == "default"
        assert msg.constitutional_validated is False

    def test_message_to_dict(self):
        """to_dict returns correct structure."""
        msg = AgentMessage(
            content={"data": "value"},
            from_agent="a",
            to_agent="b",
            message_type=MessageType.QUERY,
        )
        d = msg.to_dict()
        assert d["from_agent"] == "a"
        assert d["to_agent"] == "b"
        assert d["message_type"] == "query"
        assert d["content"] == {"data": "value"}
        assert "created_at" in d
        assert "updated_at" in d

    def test_message_to_dict_raw(self):
        """to_dict_raw includes all fields."""
        msg = AgentMessage(
            content={"test": 1},
            from_agent="src",
            to_agent="dst",
            payload={"extra": "data"},
            impact_score=0.75,
        )
        d = msg.to_dict_raw()
        assert d["payload"] == {"extra": "data"}
        assert d["impact_score"] == 0.75
        assert "sender_id" in d
        assert "security_context" in d
        assert "expires_at" in d
        assert "performance_metrics" in d

    def test_message_from_dict(self):
        """from_dict creates message from dict."""
        data = {
            "content": {"key": "val"},
            "from_agent": "from",
            "to_agent": "to",
            "message_type": "event",
            "priority": 2,  # HIGH = 2
            "status": "processing",
        }
        msg = AgentMessage.from_dict(data)
        assert msg.content == {"key": "val"}
        assert msg.from_agent == "from"
        assert msg.to_agent == "to"
        assert msg.message_type == MessageType.EVENT
        assert msg.priority == Priority.HIGH
        assert msg.status == MessageStatus.PROCESSING

    def test_message_from_dict_defaults(self):
        """from_dict uses defaults for missing fields."""
        data = {}
        msg = AgentMessage.from_dict(data)
        assert msg.content == {}
        assert msg.from_agent == ""
        assert msg.to_agent == ""
        assert msg.message_type == MessageType.COMMAND
        assert msg.priority == Priority.NORMAL


class TestDecisionLogExtended:
    """Extended tests for DecisionLog model."""

    def test_decision_log_basic(self):
        """Create basic decision log."""
        log = DecisionLog(
            trace_id="trace-123",
            span_id="span-456",
            agent_id="agent-1",
            tenant_id="tenant-1",
            policy_version="v1.0",
            risk_score=0.3,
            decision="ALLOW",
        )
        assert log.trace_id == "trace-123"
        assert log.decision == "ALLOW"
        assert log.constitutional_hash == CONSTITUTIONAL_HASH

    def test_decision_log_defaults(self):
        """DecisionLog has correct defaults."""
        log = DecisionLog(
            trace_id="t",
            span_id="s",
            agent_id="a",
            tenant_id="t",
            policy_version="v",
            risk_score=0.0,
            decision="DENY",
        )
        assert log.compliance_tags == []
        assert log.metadata == {}
        assert isinstance(log.timestamp, datetime)

    def test_decision_log_to_dict(self):
        """to_dict returns correct structure."""
        log = DecisionLog(
            trace_id="trace",
            span_id="span",
            agent_id="agent",
            tenant_id="tenant",
            policy_version="v1",
            risk_score=0.5,
            decision="ALLOW",
            compliance_tags=["gdpr", "pci"],
            metadata={"key": "value"},
        )
        d = log.to_dict()
        assert d["trace_id"] == "trace"
        assert d["span_id"] == "span"
        assert d["agent_id"] == "agent"
        assert d["tenant_id"] == "tenant"
        assert d["policy_version"] == "v1"
        assert d["risk_score"] == 0.5
        assert d["decision"] == "ALLOW"
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert d["compliance_tags"] == ["gdpr", "pci"]
        assert d["metadata"] == {"key": "value"}
        assert "timestamp" in d

    def test_decision_log_with_custom_timestamp(self):
        """DecisionLog can have custom timestamp."""
        custom_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        log = DecisionLog(
            trace_id="t",
            span_id="s",
            agent_id="a",
            tenant_id="t",
            policy_version="v",
            risk_score=0.0,
            decision="ALLOW",
            timestamp=custom_time,
        )
        assert log.timestamp == custom_time


class TestMessageEnums:
    """Tests for message-related enums."""

    def test_message_type_values(self):
        """MessageType enum has expected values."""
        assert MessageType.COMMAND.value == "command"
        assert MessageType.QUERY.value == "query"
        assert MessageType.EVENT.value == "event"
        assert MessageType.RESPONSE.value == "response"

    def test_priority_values(self):
        """Priority enum has expected values."""
        assert Priority.LOW.value == 0
        assert Priority.NORMAL.value == 1
        assert Priority.HIGH.value == 2
        assert Priority.CRITICAL.value == 3

    def test_message_status_values(self):
        """MessageStatus enum has expected values."""
        assert MessageStatus.PENDING.value == "pending"
        assert MessageStatus.PROCESSING.value == "processing"
        assert MessageStatus.DELIVERED.value == "delivered"
        assert MessageStatus.FAILED.value == "failed"

    def test_enum_iteration(self):
        """Enums can be iterated."""
        types = list(MessageType)
        assert len(types) >= 4

        priorities = list(Priority)
        assert len(priorities) >= 4

        statuses = list(MessageStatus)
        assert len(statuses) >= 4


class TestRoutingContext:
    """Tests for RoutingContext model."""

    def test_routing_context_basic(self):
        """Create routing context with required fields."""
        ctx = RoutingContext(
            source_agent_id="agent_a",
            target_agent_id="agent_b",
        )
        assert ctx.source_agent_id == "agent_a"
        assert ctx.target_agent_id == "agent_b"
        assert ctx.constitutional_hash == CONSTITUTIONAL_HASH
        assert ctx.timeout_ms == 5000

    def test_routing_context_custom_timeout(self):
        """Create routing context with custom timeout."""
        ctx = RoutingContext(
            source_agent_id="sender",
            target_agent_id="receiver",
            timeout_ms=10000,
        )
        assert ctx.timeout_ms == 10000

    def test_routing_context_missing_source(self):
        """Missing source_agent_id raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            RoutingContext(
                source_agent_id="",
                target_agent_id="receiver",
            )
        assert "source_agent_id" in str(exc_info.value)

    def test_routing_context_missing_target(self):
        """Missing target_agent_id raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            RoutingContext(
                source_agent_id="sender",
                target_agent_id="",
            )
        assert "target_agent_id" in str(exc_info.value)
