# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/core_models.py

Targets ≥95% line coverage of core_models.py.
"""

import uuid
from datetime import UTC, datetime, timezone
from enum import Enum

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.core_models import (
    AgentMessage,
    ConversationMessage,
    ConversationState,
    DecisionLog,
    EnumOrString,
    MessageContent,
    PQCMetadata,
    RoutingContext,
    get_enum_value,
)
from enhanced_agent_bus.enums import (
    AutonomyTier,
    MessageStatus,
    MessageType,
    Priority,
)
from enhanced_agent_bus.ifc.labels import (
    Confidentiality,
    IFCLabel,
    Integrity,
)

# ---------------------------------------------------------------------------
# get_enum_value
# ---------------------------------------------------------------------------


class TestGetEnumValue:
    def test_returns_value_for_enum(self):
        assert get_enum_value(Priority.HIGH) == "2"

    def test_returns_value_for_string_enum(self):
        assert get_enum_value(MessageType.COMMAND) == "command"

    def test_returns_str_for_plain_string(self):
        assert get_enum_value("hello") == "hello"

    def test_returns_str_for_integer(self):
        assert get_enum_value(42) == "42"  # type: ignore[arg-type]

    def test_autonomy_tier_enum(self):
        assert get_enum_value(AutonomyTier.BOUNDED) == "bounded"

    def test_message_status_enum(self):
        assert get_enum_value(MessageStatus.PENDING) == "pending"

    def test_empty_string(self):
        assert get_enum_value("") == ""

    def test_custom_enum(self):
        class Color(Enum):
            RED = "red"

        assert get_enum_value(Color.RED) == "red"


# ---------------------------------------------------------------------------
# RoutingContext
# ---------------------------------------------------------------------------


class TestRoutingContext:
    def test_basic_creation(self):
        rc = RoutingContext(source_agent_id="agent-a", target_agent_id="agent-b")
        assert rc.source_agent_id == "agent-a"
        assert rc.target_agent_id == "agent-b"

    def test_default_values(self):
        rc = RoutingContext(source_agent_id="a", target_agent_id="b")
        assert rc.routing_key == ""
        assert rc.routing_tags == []
        assert rc.retry_count == 0
        assert rc.max_retries == 3
        assert rc.timeout_ms == 5000
        assert rc.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_values(self):
        rc = RoutingContext(
            source_agent_id="src",
            target_agent_id="tgt",
            routing_key="my-key",
            routing_tags=["tag1", "tag2"],
            retry_count=2,
            max_retries=5,
            timeout_ms=1000,
        )
        assert rc.routing_key == "my-key"
        assert rc.routing_tags == ["tag1", "tag2"]
        assert rc.retry_count == 2
        assert rc.max_retries == 5
        assert rc.timeout_ms == 1000

    def test_raises_when_source_empty(self):
        with pytest.raises(ValueError, match="source_agent_id is required"):
            RoutingContext(source_agent_id="", target_agent_id="b")

    def test_raises_when_target_empty(self):
        with pytest.raises(ValueError, match="target_agent_id is required"):
            RoutingContext(source_agent_id="a", target_agent_id="")

    def test_constitutional_hash_default(self):
        rc = RoutingContext(source_agent_id="x", target_agent_id="y")
        assert rc.constitutional_hash == CONSTITUTIONAL_HASH

    def test_routing_tags_are_independent(self):
        rc1 = RoutingContext(source_agent_id="a", target_agent_id="b")
        rc2 = RoutingContext(source_agent_id="a", target_agent_id="b")
        rc1.routing_tags.append("t")
        assert rc2.routing_tags == []


# ---------------------------------------------------------------------------
# AgentMessage - construction and defaults
# ---------------------------------------------------------------------------


class TestAgentMessageDefaults:
    def test_creates_with_defaults(self):
        msg = AgentMessage()
        assert msg.message_id
        assert msg.conversation_id
        assert msg.content == {}
        assert msg.payload == {}
        assert msg.from_agent == ""
        assert msg.to_agent == ""
        assert msg.sender_id == ""
        assert msg.message_type == MessageType.COMMAND
        assert msg.tenant_id == "default"
        assert msg.priority == Priority.MEDIUM
        assert msg.status == MessageStatus.PENDING
        assert msg.autonomy_tier == AutonomyTier.BOUNDED
        assert msg.constitutional_hash == CONSTITUTIONAL_HASH
        assert msg.constitutional_validated is False
        assert msg.metadata == {}
        assert msg.session_id is None
        assert msg.session_context is None
        assert msg.pqc_signature is None
        assert msg.pqc_public_key is None
        assert msg.pqc_algorithm is None
        assert msg.schema_version == "1.3.0"
        assert msg.expires_at is None
        assert msg.impact_score is None
        assert msg.ifc_label is None
        assert msg.performance_metrics == {}

    def test_message_id_is_uuid(self):
        msg = AgentMessage()
        uuid.UUID(msg.message_id)  # raises if invalid

    def test_unique_message_ids(self):
        ids = {AgentMessage().message_id for _ in range(10)}
        assert len(ids) == 10

    def test_created_at_is_utc(self):
        msg = AgentMessage()
        assert msg.created_at.tzinfo is not None

    def test_custom_fields(self):
        msg = AgentMessage(
            from_agent="agent-1",
            to_agent="agent-2",
            tenant_id="tenant-x",
            message_type=MessageType.EVENT,
            priority=Priority.HIGH,
            status=MessageStatus.DELIVERED,
        )
        assert msg.from_agent == "agent-1"
        assert msg.to_agent == "agent-2"
        assert msg.tenant_id == "tenant-x"
        assert msg.message_type == MessageType.EVENT
        assert msg.priority == Priority.HIGH
        assert msg.status == MessageStatus.DELIVERED

    def test_with_ifc_label(self):
        label = IFCLabel(
            confidentiality=Confidentiality.SECRET,
            integrity=Integrity.HIGH,
        )
        msg = AgentMessage(ifc_label=label)
        assert msg.ifc_label == label

    def test_with_pqc_fields(self):
        msg = AgentMessage(
            pqc_signature="sig123",
            pqc_public_key="key456",
            pqc_algorithm="dilithium-3",
        )
        assert msg.pqc_signature == "sig123"
        assert msg.pqc_public_key == "key456"
        assert msg.pqc_algorithm == "dilithium-3"

    def test_with_routing(self):
        rc = RoutingContext(source_agent_id="a", target_agent_id="b")
        msg = AgentMessage(routing=rc)
        assert msg.routing is rc

    def test_with_headers(self):
        msg = AgentMessage(headers={"X-Custom": "value"})
        assert msg.headers["X-Custom"] == "value"

    def test_with_expires_at(self):
        dt = datetime.now(UTC)
        msg = AgentMessage(expires_at=dt)
        assert msg.expires_at == dt

    def test_with_impact_score(self):
        msg = AgentMessage(impact_score=0.95)
        assert msg.impact_score == 0.95

    def test_post_init_does_nothing_harmful(self):
        # Ensure __post_init__ runs without side effects
        msg = AgentMessage(
            content={"key": "value"},
            metadata={"m": 1},
        )
        assert msg.content == {"key": "value"}


# ---------------------------------------------------------------------------
# AgentMessage.to_dict
# ---------------------------------------------------------------------------


class TestAgentMessageToDict:
    def test_to_dict_keys(self):
        msg = AgentMessage(from_agent="a", to_agent="b")
        d = msg.to_dict()
        expected_keys = {
            "message_id",
            "conversation_id",
            "content",
            "from_agent",
            "to_agent",
            "message_type",
            "tenant_id",
            "priority",
            "status",
            "autonomy_tier",
            "constitutional_hash",
            "constitutional_validated",
            "metadata",
            "session_id",
            "session_context",
            "pqc_signature",
            "pqc_public_key",
            "pqc_algorithm",
            "schema_version",
            "created_at",
            "updated_at",
            "ifc_label",
        }
        assert expected_keys.issubset(d.keys())

    def test_to_dict_enum_values_are_serialized(self):
        msg = AgentMessage(
            message_type=MessageType.QUERY,
            priority=Priority.CRITICAL,
            status=MessageStatus.DELIVERED,
            autonomy_tier=AutonomyTier.ADVISORY,
        )
        d = msg.to_dict()
        assert d["message_type"] == "query"
        assert d["priority"] == 3
        assert d["status"] == "delivered"
        assert d["autonomy_tier"] == "advisory"

    def test_to_dict_ifc_label_none(self):
        msg = AgentMessage()
        assert msg.to_dict()["ifc_label"] is None

    def test_to_dict_ifc_label_serialized(self):
        label = IFCLabel(
            confidentiality=Confidentiality.INTERNAL,
            integrity=Integrity.HIGH,
        )
        msg = AgentMessage(ifc_label=label)
        d = msg.to_dict()
        assert d["ifc_label"] == {"confidentiality": 1, "integrity": 3}

    def test_to_dict_session_context_none(self):
        msg = AgentMessage()
        assert msg.to_dict()["session_context"] is None

    def test_to_dict_timestamps_are_iso(self):
        msg = AgentMessage()
        d = msg.to_dict()
        datetime.fromisoformat(d["created_at"])
        datetime.fromisoformat(d["updated_at"])

    def test_to_dict_pqc_fields(self):
        msg = AgentMessage(pqc_signature="s", pqc_public_key="k", pqc_algorithm="alg")
        d = msg.to_dict()
        assert d["pqc_signature"] == "s"
        assert d["pqc_public_key"] == "k"
        assert d["pqc_algorithm"] == "alg"

    def test_to_dict_constitutional_hash(self):
        msg = AgentMessage()
        assert msg.to_dict()["constitutional_hash"] == CONSTITUTIONAL_HASH


# ---------------------------------------------------------------------------
# AgentMessage.to_dict_raw
# ---------------------------------------------------------------------------


class TestAgentMessageToDictRaw:
    def test_includes_payload(self):
        msg = AgentMessage(payload={"raw": True})
        d = msg.to_dict_raw()
        assert d["payload"] == {"raw": True}

    def test_includes_sender_id(self):
        msg = AgentMessage(sender_id="sender-007")
        d = msg.to_dict_raw()
        assert d["sender_id"] == "sender-007"

    def test_includes_security_context(self):
        msg = AgentMessage(security_context={"level": "high"})
        d = msg.to_dict_raw()
        assert d["security_context"] == {"level": "high"}

    def test_expires_at_none(self):
        msg = AgentMessage()
        d = msg.to_dict_raw()
        assert d["expires_at"] is None

    def test_expires_at_serialized(self):
        dt = datetime(2030, 1, 1, tzinfo=UTC)
        msg = AgentMessage(expires_at=dt)
        d = msg.to_dict_raw()
        assert d["expires_at"] == dt.isoformat()

    def test_impact_score_included(self):
        msg = AgentMessage(impact_score=0.75)
        d = msg.to_dict_raw()
        assert d["impact_score"] == 0.75

    def test_performance_metrics_included(self):
        msg = AgentMessage(performance_metrics={"latency_ms": 1.5})
        d = msg.to_dict_raw()
        assert d["performance_metrics"] == {"latency_ms": 1.5}

    def test_schema_version_included(self):
        msg = AgentMessage()
        assert msg.to_dict_raw()["schema_version"] == "1.3.0"

    def test_all_extra_keys_present(self):
        msg = AgentMessage()
        d = msg.to_dict_raw()
        for k in ("payload", "sender_id", "security_context", "expires_at", "impact_score"):
            assert k in d


# ---------------------------------------------------------------------------
# AgentMessage._parse_autonomy_tier
# ---------------------------------------------------------------------------


class TestParseAutonomyTier:
    def test_none_returns_none(self):
        assert AgentMessage._parse_autonomy_tier(None) is None

    def test_empty_string_returns_none(self):
        assert AgentMessage._parse_autonomy_tier("") is None

    def test_valid_string(self):
        result = AgentMessage._parse_autonomy_tier("advisory")
        assert result == AutonomyTier.ADVISORY

    def test_valid_enum_value(self):
        result = AgentMessage._parse_autonomy_tier("bounded")
        assert result == AutonomyTier.BOUNDED

    def test_unrestricted(self):
        result = AgentMessage._parse_autonomy_tier("unrestricted")
        assert result == AutonomyTier.UNRESTRICTED

    def test_human_approved(self):
        result = AgentMessage._parse_autonomy_tier("human_approved")
        assert result == AutonomyTier.HUMAN_APPROVED

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid autonomy_tier"):
            AgentMessage._parse_autonomy_tier("invalid_tier")

    def test_invalid_integer_raises(self):
        with pytest.raises(ValueError, match="Invalid autonomy_tier"):
            AgentMessage._parse_autonomy_tier(999)


# ---------------------------------------------------------------------------
# AgentMessage.from_dict
# ---------------------------------------------------------------------------


class TestAgentMessageFromDict:
    def test_empty_dict_uses_defaults(self):
        msg = AgentMessage.from_dict({})
        assert msg.tenant_id == "default"
        assert msg.schema_version == "1.3.0"
        assert msg.session_context is None
        assert msg.ifc_label is None

    def test_basic_fields(self):
        d = {
            "message_id": "msg-001",
            "conversation_id": "conv-001",
            "from_agent": "a",
            "to_agent": "b",
            "message_type": "event",
            "tenant_id": "t1",
            "priority": 2,
            "status": "delivered",
        }
        msg = AgentMessage.from_dict(d)
        assert msg.message_id == "msg-001"
        assert msg.conversation_id == "conv-001"
        assert msg.from_agent == "a"
        assert msg.to_agent == "b"
        assert msg.message_type == MessageType.EVENT
        assert msg.tenant_id == "t1"
        assert msg.priority == Priority.HIGH
        assert msg.status == MessageStatus.DELIVERED

    def test_pqc_fields(self):
        d = {
            "pqc_signature": "sig",
            "pqc_public_key": "key",
            "pqc_algorithm": "kyber-768",
        }
        msg = AgentMessage.from_dict(d)
        assert msg.pqc_signature == "sig"
        assert msg.pqc_public_key == "key"
        assert msg.pqc_algorithm == "kyber-768"

    def test_session_id(self):
        msg = AgentMessage.from_dict({"session_id": "sess-123"})
        assert msg.session_id == "sess-123"

    def test_ifc_label_none(self):
        msg = AgentMessage.from_dict({})
        assert msg.ifc_label is None

    def test_ifc_label_deserialized(self):
        d = {"ifc_label": {"confidentiality": 2, "integrity": 3}}
        msg = AgentMessage.from_dict(d)
        assert msg.ifc_label == IFCLabel(
            confidentiality=Confidentiality.CONFIDENTIAL,
            integrity=Integrity.HIGH,
        )

    def test_autonomy_tier_from_dict(self):
        msg = AgentMessage.from_dict({"autonomy_tier": "advisory"})
        assert msg.autonomy_tier == AutonomyTier.ADVISORY

    def test_autonomy_tier_none_in_dict_defaults_to_bounded(self):
        msg = AgentMessage.from_dict({"autonomy_tier": None})
        # None defaults to BOUNDED (safe default)
        assert msg.autonomy_tier == AutonomyTier.BOUNDED

    def test_autonomy_tier_missing_in_dict_defaults_to_bounded(self):
        msg = AgentMessage.from_dict({})
        # Missing key defaults to BOUNDED (safe default)
        assert msg.autonomy_tier == AutonomyTier.BOUNDED

    def test_metadata_preserved(self):
        msg = AgentMessage.from_dict({"metadata": {"k": "v"}})
        assert msg.metadata == {"k": "v"}

    def test_schema_version_preserved(self):
        msg = AgentMessage.from_dict({"schema_version": "2.0.0"})
        assert msg.schema_version == "2.0.0"

    def test_message_id_generated_when_absent(self):
        msg = AgentMessage.from_dict({})
        uuid.UUID(msg.message_id)  # no exception means valid UUID

    def test_session_context_invalid_data_gracefully_sets_none(self):
        d = {"session_context": {"garbage": True}}
        msg = AgentMessage.from_dict(d)
        # SessionContext parsing fails → session_context is None
        assert msg.session_context is None

    def test_roundtrip_to_dict_from_dict(self):
        original = AgentMessage(
            from_agent="x",
            to_agent="y",
            tenant_id="tenant-rt",
            message_type=MessageType.QUERY,
            priority=Priority.LOW,
            status=MessageStatus.PROCESSING,
            metadata={"a": 1},
        )
        d = original.to_dict()
        # Ensure message_type is plain string for from_dict
        restored = AgentMessage.from_dict(d)
        assert restored.from_agent == "x"
        assert restored.tenant_id == "tenant-rt"
        assert restored.message_type == MessageType.QUERY
        assert restored.priority == Priority.LOW
        assert restored.metadata == {"a": 1}


# ---------------------------------------------------------------------------
# PQCMetadata
# ---------------------------------------------------------------------------


class TestPQCMetadata:
    def _make(self, **kwargs):
        defaults = dict(
            pqc_enabled=True,
            pqc_algorithm="dilithium3",
            classical_verified=True,
            pqc_verified=True,
            verification_mode="strict",
        )
        defaults.update(kwargs)
        return PQCMetadata(**defaults)

    def test_basic_creation(self):
        m = self._make()
        assert m.pqc_enabled is True
        assert m.pqc_algorithm == "dilithium3"
        assert m.classical_verified is True
        assert m.pqc_verified is True
        assert m.verification_mode == "strict"
        assert m.verifier_version == "1.0.0"

    def test_verified_at_default_is_utc(self):
        m = self._make()
        assert m.verified_at.tzinfo is not None

    def test_pqc_algorithm_none(self):
        m = self._make(pqc_algorithm=None)
        assert m.pqc_algorithm is None

    def test_verification_modes(self):
        for mode in ("strict", "classical_only", "pqc_only"):
            m = self._make(verification_mode=mode)
            assert m.verification_mode == mode

    def test_to_dict_keys(self):
        m = self._make()
        d = m.to_dict()
        assert set(d.keys()) == {
            "pqc_enabled",
            "pqc_algorithm",
            "classical_verified",
            "pqc_verified",
            "verification_mode",
            "verified_at",
            "verifier_version",
        }

    def test_to_dict_values(self):
        m = self._make(pqc_enabled=False, classical_verified=False, pqc_verified=False)
        d = m.to_dict()
        assert d["pqc_enabled"] is False
        assert d["classical_verified"] is False
        assert d["pqc_verified"] is False

    def test_to_dict_verified_at_is_iso(self):
        m = self._make()
        d = m.to_dict()
        datetime.fromisoformat(d["verified_at"])

    def test_to_dict_algorithm_none(self):
        m = self._make(pqc_algorithm=None)
        assert m.to_dict()["pqc_algorithm"] is None

    def test_custom_verifier_version(self):
        m = self._make(verifier_version="2.5.0")
        assert m.verifier_version == "2.5.0"
        assert m.to_dict()["verifier_version"] == "2.5.0"


# ---------------------------------------------------------------------------
# DecisionLog
# ---------------------------------------------------------------------------


class TestDecisionLog:
    def _make(self, **kwargs):
        defaults = dict(
            trace_id="t1",
            span_id="s1",
            agent_id="agent-007",
            tenant_id="tenant-1",
            policy_version="v1.0",
            risk_score=0.25,
            decision="allow",
        )
        defaults.update(kwargs)
        return DecisionLog(**defaults)

    def test_basic_creation(self):
        log = self._make()
        assert log.trace_id == "t1"
        assert log.span_id == "s1"
        assert log.agent_id == "agent-007"
        assert log.tenant_id == "tenant-1"
        assert log.policy_version == "v1.0"
        assert log.risk_score == 0.25
        assert log.decision == "allow"
        assert log.constitutional_hash == CONSTITUTIONAL_HASH

    def test_default_compliance_tags(self):
        log = self._make()
        assert log.compliance_tags == []

    def test_default_metadata(self):
        log = self._make()
        assert log.metadata == {}

    def test_timestamp_is_utc(self):
        log = self._make()
        assert log.timestamp.tzinfo is not None

    def test_custom_compliance_tags(self):
        log = self._make(compliance_tags=["gdpr", "ccpa"])
        assert log.compliance_tags == ["gdpr", "ccpa"]

    def test_custom_metadata(self):
        log = self._make(metadata={"key": "val"})
        assert log.metadata == {"key": "val"}

    def test_to_dict_keys(self):
        log = self._make()
        d = log.to_dict()
        expected = {
            "trace_id",
            "span_id",
            "agent_id",
            "tenant_id",
            "policy_version",
            "risk_score",
            "decision",
            "constitutional_hash",
            "timestamp",
            "compliance_tags",
            "metadata",
        }
        assert set(d.keys()) == expected

    def test_to_dict_values(self):
        log = self._make(decision="deny", risk_score=0.99)
        d = log.to_dict()
        assert d["decision"] == "deny"
        assert d["risk_score"] == 0.99
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_to_dict_timestamp_is_iso(self):
        log = self._make()
        d = log.to_dict()
        datetime.fromisoformat(d["timestamp"])

    def test_to_dict_compliance_tags(self):
        log = self._make(compliance_tags=["soc2"])
        d = log.to_dict()
        assert d["compliance_tags"] == ["soc2"]

    def test_to_dict_metadata(self):
        log = self._make(metadata={"extra": 42})
        d = log.to_dict()
        assert d["metadata"] == {"extra": 42}

    def test_risk_score_zero(self):
        log = self._make(risk_score=0.0)
        assert log.to_dict()["risk_score"] == 0.0

    def test_risk_score_one(self):
        log = self._make(risk_score=1.0)
        assert log.to_dict()["risk_score"] == 1.0


# ---------------------------------------------------------------------------
# ConversationMessage
# ---------------------------------------------------------------------------


class TestConversationMessage:
    def test_basic_creation(self):
        msg = ConversationMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_assistant_role(self):
        msg = ConversationMessage(role="assistant", content="Hi there")
        assert msg.role == "assistant"

    def test_timestamp_default_is_utc(self):
        msg = ConversationMessage(role="user", content="x")
        assert msg.timestamp.tzinfo is not None

    def test_intent_default_none(self):
        msg = ConversationMessage(role="user", content="x")
        assert msg.intent is None

    def test_verification_result_default_none(self):
        msg = ConversationMessage(role="user", content="x")
        assert msg.verification_result is None

    def test_custom_intent(self):
        msg = ConversationMessage(role="user", content="x", intent="query")
        assert msg.intent == "query"

    def test_custom_verification_result(self):
        vr = {"is_valid": True, "confidence": 0.9}
        msg = ConversationMessage(role="user", content="x", verification_result=vr)
        assert msg.verification_result == vr

    def test_custom_timestamp(self):
        dt = datetime(2025, 6, 1, tzinfo=UTC)
        msg = ConversationMessage(role="user", content="x", timestamp=dt)
        assert msg.timestamp == dt

    def test_from_attributes_config(self):
        assert ConversationMessage.model_config.get("from_attributes") is True

    def test_serialization_roundtrip(self):
        msg = ConversationMessage(role="user", content="Test", intent="info")
        data = msg.model_dump()
        restored = ConversationMessage.model_validate(data)
        assert restored.role == msg.role
        assert restored.content == msg.content
        assert restored.intent == msg.intent


# ---------------------------------------------------------------------------
# ConversationState
# ---------------------------------------------------------------------------


class TestConversationState:
    def test_basic_creation(self):
        cs = ConversationState(session_id="sess-1", tenant_id="tenant-1")
        assert cs.session_id == "sess-1"
        assert cs.tenant_id == "tenant-1"
        assert cs.messages == []

    def test_constitutional_hash_default(self):
        cs = ConversationState(session_id="s", tenant_id="t")
        assert cs.constitutional_hash == CONSTITUTIONAL_HASH

    def test_timestamps_are_utc(self):
        cs = ConversationState(session_id="s", tenant_id="t")
        assert cs.created_at.tzinfo is not None
        assert cs.updated_at.tzinfo is not None

    def test_with_messages(self):
        m1 = ConversationMessage(role="user", content="Hi")
        m2 = ConversationMessage(role="assistant", content="Hello")
        cs = ConversationState(session_id="s", tenant_id="t", messages=[m1, m2])
        assert len(cs.messages) == 2

    def test_messages_default_is_empty_list(self):
        cs = ConversationState(session_id="s", tenant_id="t")
        assert cs.messages == []

    def test_from_attributes_config(self):
        assert ConversationState.model_config.get("from_attributes") is True

    def test_model_dump_round_trip(self):
        cs = ConversationState(session_id="s1", tenant_id="t1")
        data = cs.model_dump()
        restored = ConversationState.model_validate(data)
        assert restored.session_id == "s1"
        assert restored.tenant_id == "t1"
        assert restored.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_constitutional_hash(self):
        cs = ConversationState(
            session_id="s",
            tenant_id="t",
            constitutional_hash="custom-hash",
        )
        assert cs.constitutional_hash == "custom-hash"

    def test_model_dump_has_all_fields(self):
        cs = ConversationState(session_id="s", tenant_id="t")
        data = cs.model_dump()
        assert "session_id" in data
        assert "tenant_id" in data
        assert "messages" in data
        assert "created_at" in data
        assert "updated_at" in data
        assert "constitutional_hash" in data


# ---------------------------------------------------------------------------
# Type alias smoke tests
# ---------------------------------------------------------------------------


class TestTypeAliases:
    def test_message_content_alias(self):
        # MessageContent is just JSONDict; verify it's dict-compatible
        mc: MessageContent = {"key": "value"}
        assert mc["key"] == "value"

    def test_enum_or_string_union(self):
        # EnumOrString should accept Enum or str
        val: EnumOrString = Priority.HIGH
        assert get_enum_value(val) == "2"
        val2: EnumOrString = "plain_string"
        assert get_enum_value(val2) == "plain_string"


# ---------------------------------------------------------------------------
# __all__ exports
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports_present(self):
        from enhanced_agent_bus import core_models

        expected = [
            "MessageContent",
            "EnumOrString",
            "get_enum_value",
            "RoutingContext",
            "AgentMessage",
            "PQCMetadata",
            "DecisionLog",
            "ConversationMessage",
            "ConversationState",
        ]
        for name in expected:
            assert name in core_models.__all__, f"{name} missing from __all__"


# ---------------------------------------------------------------------------
# Edge-case and integration tests
# ---------------------------------------------------------------------------


class TestAgentMessageEdgeCases:
    def test_autonomy_tier_advisory_roundtrip(self):
        msg = AgentMessage(autonomy_tier=AutonomyTier.ADVISORY)
        d = msg.to_dict()
        assert d["autonomy_tier"] == "advisory"

    def test_autonomy_tier_unrestricted(self):
        msg = AgentMessage(autonomy_tier=AutonomyTier.UNRESTRICTED)
        assert msg.to_dict()["autonomy_tier"] == "unrestricted"

    def test_all_message_types_in_to_dict(self):
        for mt in MessageType:
            msg = AgentMessage(message_type=mt)
            d = msg.to_dict()
            assert d["message_type"] == mt.value

    def test_all_priorities_in_to_dict(self):
        for p in (Priority.LOW, Priority.HIGH, Priority.CRITICAL):
            msg = AgentMessage(priority=p)
            d = msg.to_dict()
            assert d["priority"] == p.value

    def test_all_statuses_in_to_dict(self):
        for s in MessageStatus:
            msg = AgentMessage(status=s)
            d = msg.to_dict()
            assert d["status"] == s.value

    def test_content_preserved(self):
        msg = AgentMessage(content={"nested": {"deep": 1}})
        assert msg.to_dict()["content"] == {"nested": {"deep": 1}}

    def test_to_dict_raw_overrides_base(self):
        # to_dict_raw updates the base dict, so payload key appears
        msg = AgentMessage(payload={"p": 1}, impact_score=0.5)
        d = msg.to_dict_raw()
        assert d["payload"] == {"p": 1}
        assert d["impact_score"] == 0.5

    def test_from_dict_generates_uuid_for_missing_conversation_id(self):
        msg = AgentMessage.from_dict({"message_id": "m1"})
        uuid.UUID(msg.conversation_id)

    def test_security_context_default_is_dict(self):
        msg = AgentMessage()
        assert isinstance(msg.security_context, dict)

    def test_performance_metrics_independent_per_instance(self):
        msg1 = AgentMessage()
        msg2 = AgentMessage()
        msg1.performance_metrics["x"] = 1
        assert "x" not in msg2.performance_metrics

    def test_metadata_independent_per_instance(self):
        msg1 = AgentMessage()
        msg2 = AgentMessage()
        msg1.metadata["x"] = 1
        assert "x" not in msg2.metadata
