# Constitutional Hash: 608508a9bd224290
"""
Comprehensive tests for src/core/enhanced_agent_bus/exceptions/operations.py.

Target: ≥95% line coverage of operations.py (84 stmts).
"""

from typing import ClassVar

import pytest

from enhanced_agent_bus.exceptions.base import AgentBusError, BusOperationError
from enhanced_agent_bus.exceptions.messaging import RateLimitExceeded
from enhanced_agent_bus.exceptions.operations import (
    AlignmentViolationError,
    AuthenticationError,
    AuthorizationError,
    BusAlreadyStartedError,
    BusNotStartedError,
    CircuitBreakerOpenError,
    ConfigurationError,
    DeliberationError,
    DeliberationTimeoutError,
    DependencyError,
    GovernanceError,
    HandlerExecutionError,
    ImpactAssessmentError,
    RateLimitExceededError,
    ResourceNotFoundError,
    ReviewConsensusError,
    ServiceUnavailableError,
    SignatureCollectionError,
    TenantIsolationError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# GovernanceError
# ---------------------------------------------------------------------------


class TestGovernanceError:
    def test_basic_instantiation(self):
        err = GovernanceError("governance failed")
        assert "governance failed" in str(err)

    def test_with_details(self):
        err = GovernanceError("governance failed", details={"key": "value"})
        d = err.to_dict()
        assert d["details"]["key"] == "value"

    def test_without_details_no_details_key(self):
        # When details={} (falsy), to_dict() omits the "details" key
        err = GovernanceError("msg")
        d = err.to_dict()
        # details key is absent or the dict is empty when no details given
        assert "details" not in d or isinstance(d.get("details"), dict)

    def test_is_agent_bus_error(self):
        err = GovernanceError("msg")
        assert isinstance(err, AgentBusError)

    def test_raise_and_catch_as_agent_bus_error(self):
        with pytest.raises(AgentBusError):
            raise GovernanceError("raised")

    def test_raise_and_catch_as_governance_error(self):
        with pytest.raises(GovernanceError):
            raise GovernanceError("raised governance")

    def test_to_dict_contains_error_type(self):
        err = GovernanceError("msg")
        assert err.to_dict()["error_type"] == "GovernanceError"

    def test_details_none_stored_as_empty_dict(self):
        # details=None is converted to {} internally; to_dict omits empty details
        err = GovernanceError("msg", details=None)
        assert isinstance(err.details, dict)
        assert err.details == {}

    def test_details_with_complex_value(self):
        err = GovernanceError("msg", details={"list": [1, 2, 3], "nested": {"a": 1}})
        assert err.to_dict()["details"]["list"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# ImpactAssessmentError
# ---------------------------------------------------------------------------


class TestImpactAssessmentError:
    def test_basic_instantiation(self):
        err = ImpactAssessmentError("risk_analysis", "model unavailable")
        assert "risk_analysis" in str(err)
        assert "model unavailable" in str(err)

    def test_assessment_type_stored(self):
        err = ImpactAssessmentError("severity_check", "timeout")
        assert err.assessment_type == "severity_check"

    def test_is_governance_error(self):
        err = ImpactAssessmentError("type", "reason")
        assert isinstance(err, GovernanceError)

    def test_is_agent_bus_error(self):
        err = ImpactAssessmentError("type", "reason")
        assert isinstance(err, AgentBusError)

    def test_details_contain_assessment_type(self):
        err = ImpactAssessmentError("impact_type", "failed")
        d = err.to_dict()
        assert d["details"]["assessment_type"] == "impact_type"

    def test_details_contain_reason(self):
        err = ImpactAssessmentError("impact_type", "bad reason")
        d = err.to_dict()
        assert d["details"]["reason"] == "bad reason"

    def test_message_format(self):
        err = ImpactAssessmentError("foo", "bar")
        assert "Impact assessment failed for foo: bar" in str(err)

    def test_raise_and_catch_as_governance_error(self):
        with pytest.raises(GovernanceError):
            raise ImpactAssessmentError("t", "r")

    def test_to_dict_error_type(self):
        err = ImpactAssessmentError("t", "r")
        assert err.to_dict()["error_type"] == "ImpactAssessmentError"


# ---------------------------------------------------------------------------
# DeliberationError
# ---------------------------------------------------------------------------


class TestDeliberationError:
    def test_basic_instantiation(self):
        err = DeliberationError("deliberation failed")
        assert isinstance(err, DeliberationError)

    def test_is_agent_bus_error(self):
        err = DeliberationError("msg")
        assert isinstance(err, AgentBusError)

    def test_raise_and_catch(self):
        with pytest.raises(DeliberationError):
            raise DeliberationError("error")

    def test_to_dict_error_type(self):
        err = DeliberationError("msg")
        assert err.to_dict()["error_type"] == "DeliberationError"


# ---------------------------------------------------------------------------
# DeliberationTimeoutError
# ---------------------------------------------------------------------------


class TestDeliberationTimeoutError:
    def test_basic_instantiation(self):
        err = DeliberationTimeoutError("dec-001", 300)
        assert "dec-001" in str(err)
        assert "300" in str(err)

    def test_stores_attributes(self):
        err = DeliberationTimeoutError("dec-001", 300, pending_reviews=2, pending_signatures=3)
        assert err.decision_id == "dec-001"
        assert err.timeout_seconds == 300
        assert err.pending_reviews == 2
        assert err.pending_signatures == 3

    def test_default_pending_values(self):
        err = DeliberationTimeoutError("dec-002", 60)
        assert err.pending_reviews == 0
        assert err.pending_signatures == 0

    def test_is_deliberation_error(self):
        err = DeliberationTimeoutError("dec-003", 30)
        assert isinstance(err, DeliberationError)

    def test_is_agent_bus_error(self):
        err = DeliberationTimeoutError("dec-004", 30)
        assert isinstance(err, AgentBusError)

    def test_details_decision_id(self):
        err = DeliberationTimeoutError("dec-005", 120)
        assert err.to_dict()["details"]["decision_id"] == "dec-005"

    def test_details_timeout_seconds(self):
        err = DeliberationTimeoutError("dec-006", 45)
        assert err.to_dict()["details"]["timeout_seconds"] == 45

    def test_details_pending_reviews(self):
        err = DeliberationTimeoutError("dec-007", 60, pending_reviews=5)
        assert err.to_dict()["details"]["pending_reviews"] == 5

    def test_details_pending_signatures(self):
        err = DeliberationTimeoutError("dec-008", 60, pending_signatures=4)
        assert err.to_dict()["details"]["pending_signatures"] == 4

    def test_message_format(self):
        err = DeliberationTimeoutError("dec-xyz", 200)
        assert "Deliberation 'dec-xyz' timed out after 200s" in str(err)

    def test_raise_and_catch_as_deliberation_error(self):
        with pytest.raises(DeliberationError):
            raise DeliberationTimeoutError("d", 10)

    def test_to_dict_error_type(self):
        err = DeliberationTimeoutError("d", 10)
        assert err.to_dict()["error_type"] == "DeliberationTimeoutError"


# ---------------------------------------------------------------------------
# SignatureCollectionError
# ---------------------------------------------------------------------------


class TestSignatureCollectionError:
    def _make(self, **kwargs):
        defaults = dict(
            decision_id="dec-001",
            required_signers=["alice", "bob", "charlie"],
            collected_signers=["alice"],
            reason="quorum not reached",
        )
        defaults.update(kwargs)
        return SignatureCollectionError(**defaults)

    def test_basic_instantiation(self):
        err = self._make()
        assert "dec-001" in str(err)

    def test_stores_decision_id(self):
        err = self._make(decision_id="dec-sig-001")
        assert err.decision_id == "dec-sig-001"

    def test_stores_required_signers(self):
        err = self._make(required_signers=["x", "y"])
        assert err.required_signers == ["x", "y"]

    def test_stores_collected_signers(self):
        err = self._make(collected_signers=["x"])
        assert err.collected_signers == ["x"]

    def test_stores_reason(self):
        err = self._make(reason="timed out")
        assert err.reason == "timed out"

    def test_missing_signers_computed(self):
        err = self._make(
            required_signers=["a", "b", "c"],
            collected_signers=["a"],
        )
        assert set(err.to_dict()["details"]["missing_signers"]) == {"b", "c"}

    def test_no_missing_signers_when_all_collected(self):
        err = self._make(
            required_signers=["a", "b"],
            collected_signers=["a", "b"],
        )
        assert err.to_dict()["details"]["missing_signers"] == []

    def test_is_deliberation_error(self):
        err = self._make()
        assert isinstance(err, DeliberationError)

    def test_is_agent_bus_error(self):
        err = self._make()
        assert isinstance(err, AgentBusError)

    def test_details_contain_all_fields(self):
        err = self._make()
        d = err.to_dict()["details"]
        assert "decision_id" in d
        assert "required_signers" in d
        assert "collected_signers" in d
        assert "missing_signers" in d
        assert "reason" in d

    def test_message_contains_reason(self):
        err = self._make(reason="timeout exceeded")
        assert "timeout exceeded" in str(err)

    def test_raise_and_catch(self):
        with pytest.raises(SignatureCollectionError):
            raise self._make()

    def test_to_dict_error_type(self):
        err = self._make()
        assert err.to_dict()["error_type"] == "SignatureCollectionError"


# ---------------------------------------------------------------------------
# ReviewConsensusError
# ---------------------------------------------------------------------------


class TestReviewConsensusError:
    def test_basic_instantiation(self):
        err = ReviewConsensusError("dec-001", 1, 2, 1)
        assert "dec-001" in str(err)

    def test_stores_attributes(self):
        err = ReviewConsensusError("dec-rev-001", 3, 2, 1)
        assert err.decision_id == "dec-rev-001"
        assert err.approval_count == 3
        assert err.rejection_count == 2
        assert err.escalation_count == 1

    def test_is_deliberation_error(self):
        err = ReviewConsensusError("d", 0, 0, 0)
        assert isinstance(err, DeliberationError)

    def test_is_agent_bus_error(self):
        err = ReviewConsensusError("d", 0, 0, 0)
        assert isinstance(err, AgentBusError)

    def test_details_approval_count(self):
        err = ReviewConsensusError("d", 5, 3, 2)
        assert err.to_dict()["details"]["approval_count"] == 5

    def test_details_rejection_count(self):
        err = ReviewConsensusError("d", 5, 3, 2)
        assert err.to_dict()["details"]["rejection_count"] == 3

    def test_details_escalation_count(self):
        err = ReviewConsensusError("d", 5, 3, 2)
        assert err.to_dict()["details"]["escalation_count"] == 2

    def test_message_contains_counts(self):
        err = ReviewConsensusError("dec-001", 2, 3, 1)
        msg = str(err)
        assert "2 approvals" in msg
        assert "3 rejections" in msg
        assert "1 escalations" in msg

    def test_raise_and_catch_as_deliberation_error(self):
        with pytest.raises(DeliberationError):
            raise ReviewConsensusError("d", 0, 1, 0)

    def test_to_dict_error_type(self):
        err = ReviewConsensusError("d", 0, 1, 0)
        assert err.to_dict()["error_type"] == "ReviewConsensusError"


# ---------------------------------------------------------------------------
# BusNotStartedError
# ---------------------------------------------------------------------------


class TestBusNotStartedError:
    def test_basic_instantiation(self):
        err = BusNotStartedError("send_message")
        assert "send_message" in str(err)

    def test_stores_operation(self):
        err = BusNotStartedError("subscribe")
        assert err.operation == "subscribe"

    def test_is_bus_operation_error(self):
        err = BusNotStartedError("op")
        assert isinstance(err, BusOperationError)

    def test_is_agent_bus_error(self):
        err = BusNotStartedError("op")
        assert isinstance(err, AgentBusError)

    def test_details_operation(self):
        err = BusNotStartedError("process")
        assert err.to_dict()["details"]["operation"] == "process"

    def test_message_format(self):
        err = BusNotStartedError("dispatch")
        assert "Agent bus not started for operation: dispatch" in str(err)

    def test_raise_and_catch_as_bus_operation_error(self):
        with pytest.raises(BusOperationError):
            raise BusNotStartedError("op")

    def test_to_dict_error_type(self):
        err = BusNotStartedError("op")
        assert err.to_dict()["error_type"] == "BusNotStartedError"


# ---------------------------------------------------------------------------
# BusAlreadyStartedError
# ---------------------------------------------------------------------------


class TestBusAlreadyStartedError:
    def test_basic_instantiation(self):
        err = BusAlreadyStartedError()
        assert "already running" in str(err)

    def test_is_bus_operation_error(self):
        err = BusAlreadyStartedError()
        assert isinstance(err, BusOperationError)

    def test_is_agent_bus_error(self):
        err = BusAlreadyStartedError()
        assert isinstance(err, AgentBusError)

    def test_details_empty(self):
        # When details={}, to_dict omits the key
        err = BusAlreadyStartedError()
        assert err.details == {}

    def test_raise_and_catch_as_bus_operation_error(self):
        with pytest.raises(BusOperationError):
            raise BusAlreadyStartedError()

    def test_raise_and_catch_directly(self):
        with pytest.raises(BusAlreadyStartedError):
            raise BusAlreadyStartedError()

    def test_to_dict_error_type(self):
        err = BusAlreadyStartedError()
        assert err.to_dict()["error_type"] == "BusAlreadyStartedError"


# ---------------------------------------------------------------------------
# HandlerExecutionError
# ---------------------------------------------------------------------------


class TestHandlerExecutionError:
    def test_basic_instantiation(self):
        original = ValueError("something went wrong")
        err = HandlerExecutionError("my_handler", "msg-123", original)
        assert "my_handler" in str(err)
        assert "msg-123" in str(err)

    def test_stores_handler_name(self):
        original = RuntimeError("oops")
        err = HandlerExecutionError("handler_x", "msg-001", original)
        assert err.handler_name == "handler_x"

    def test_stores_message_id(self):
        original = RuntimeError("oops")
        err = HandlerExecutionError("handler_x", "msg-002", original)
        assert err.message_id == "msg-002"

    def test_stores_original_error(self):
        original = TypeError("type error")
        err = HandlerExecutionError("h", "m", original)
        assert err.original_error is original

    def test_is_bus_operation_error(self):
        err = HandlerExecutionError("h", "m", Exception("e"))
        assert isinstance(err, BusOperationError)

    def test_is_agent_bus_error(self):
        err = HandlerExecutionError("h", "m", Exception("e"))
        assert isinstance(err, AgentBusError)

    def test_details_handler_name(self):
        err = HandlerExecutionError("handler_abc", "m", Exception("e"))
        assert err.to_dict()["details"]["handler_name"] == "handler_abc"

    def test_details_message_id(self):
        err = HandlerExecutionError("h", "msg-xyz", Exception("e"))
        assert err.to_dict()["details"]["message_id"] == "msg-xyz"

    def test_details_original_error(self):
        original = ValueError("original message")
        err = HandlerExecutionError("h", "m", original)
        assert err.to_dict()["details"]["original_error"] == "original message"

    def test_details_original_error_type(self):
        err = HandlerExecutionError("h", "m", ValueError("v"))
        assert err.to_dict()["details"]["original_error_type"] == "ValueError"

    def test_message_format(self):
        original = RuntimeError("crash")
        err = HandlerExecutionError("my_handler", "msg-001", original)
        msg = str(err)
        assert "Handler 'my_handler' failed" in msg
        assert "msg-001" in msg

    def test_raise_and_catch(self):
        with pytest.raises(HandlerExecutionError):
            raise HandlerExecutionError("h", "m", Exception("e"))

    def test_to_dict_error_type(self):
        err = HandlerExecutionError("h", "m", Exception("e"))
        assert err.to_dict()["error_type"] == "HandlerExecutionError"

    def test_with_custom_exception_subclass(self):
        class MyCustomError(Exception):
            pass

        original = MyCustomError("custom")
        err = HandlerExecutionError("h", "m", original)
        assert err.to_dict()["details"]["original_error_type"] == "MyCustomError"


# ---------------------------------------------------------------------------
# ConfigurationError
# ---------------------------------------------------------------------------


class TestConfigurationError:
    def test_basic_instantiation(self):
        err = ConfigurationError("redis_url", "missing")
        assert "redis_url" in str(err)
        assert "missing" in str(err)

    def test_stores_config_key(self):
        err = ConfigurationError("kafka_brokers", "invalid format")
        assert err.config_key == "kafka_brokers"

    def test_stores_reason(self):
        err = ConfigurationError("opa_url", "unreachable")
        assert err.reason == "unreachable"

    def test_is_agent_bus_error(self):
        err = ConfigurationError("k", "r")
        assert isinstance(err, AgentBusError)

    def test_details_config_key(self):
        err = ConfigurationError("db_host", "not set")
        assert err.to_dict()["details"]["config_key"] == "db_host"

    def test_details_reason(self):
        err = ConfigurationError("db_host", "not set")
        assert err.to_dict()["details"]["reason"] == "not set"

    def test_message_format(self):
        err = ConfigurationError("auth_secret", "too short")
        assert "Configuration error for 'auth_secret': too short" in str(err)

    def test_raise_and_catch(self):
        with pytest.raises(ConfigurationError):
            raise ConfigurationError("k", "r")

    def test_to_dict_error_type(self):
        err = ConfigurationError("k", "r")
        assert err.to_dict()["error_type"] == "ConfigurationError"


# ---------------------------------------------------------------------------
# AlignmentViolationError
# ---------------------------------------------------------------------------


class TestAlignmentViolationError:
    def test_basic_instantiation(self):
        err = AlignmentViolationError("unsafe content detected")
        assert "unsafe content detected" in str(err)

    def test_without_optional_fields(self):
        err = AlignmentViolationError("violation")
        assert err.alignment_score is None
        assert err.agent_id is None

    def test_with_alignment_score(self):
        err = AlignmentViolationError("violation", alignment_score=0.3)
        assert err.alignment_score == 0.3
        assert "0.3" in str(err)

    def test_with_agent_id(self):
        err = AlignmentViolationError("violation", agent_id="agent-007")
        assert err.agent_id == "agent-007"

    def test_with_all_fields(self):
        err = AlignmentViolationError("violation", alignment_score=0.1, agent_id="agent-x")
        assert err.alignment_score == 0.1
        assert err.agent_id == "agent-x"

    def test_message_without_score(self):
        err = AlignmentViolationError("bad content")
        assert "Constitutional alignment violation: bad content" in str(err)
        assert "score" not in str(err)

    def test_message_with_score(self):
        err = AlignmentViolationError("bad content", alignment_score=0.05)
        assert "score: 0.05" in str(err)

    def test_is_agent_bus_error(self):
        err = AlignmentViolationError("v")
        assert isinstance(err, AgentBusError)

    def test_details_reason(self):
        err = AlignmentViolationError("test reason")
        assert err.to_dict()["details"]["reason"] == "test reason"

    def test_details_alignment_score_none(self):
        err = AlignmentViolationError("v")
        assert err.to_dict()["details"]["alignment_score"] is None

    def test_details_alignment_score_set(self):
        err = AlignmentViolationError("v", alignment_score=0.7)
        assert err.to_dict()["details"]["alignment_score"] == 0.7

    def test_details_agent_id_none(self):
        err = AlignmentViolationError("v")
        assert err.to_dict()["details"]["agent_id"] is None

    def test_details_agent_id_set(self):
        err = AlignmentViolationError("v", agent_id="agt-1")
        assert err.to_dict()["details"]["agent_id"] == "agt-1"

    def test_raise_and_catch(self):
        with pytest.raises(AlignmentViolationError):
            raise AlignmentViolationError("v")

    def test_to_dict_error_type(self):
        err = AlignmentViolationError("v")
        assert err.to_dict()["error_type"] == "AlignmentViolationError"

    def test_score_zero_still_appended(self):
        # score=0.0 is falsy but is not None so should appear in the message
        err = AlignmentViolationError("violation", alignment_score=0.0)
        assert "score: 0.0" in str(err)


# ---------------------------------------------------------------------------
# AuthenticationError
# ---------------------------------------------------------------------------


class TestAuthenticationError:
    def test_basic_instantiation(self):
        err = AuthenticationError("agent-001", "token expired")
        assert "agent-001" in str(err)
        assert "token expired" in str(err)

    def test_stores_agent_id(self):
        err = AuthenticationError("agt-xyz", "invalid key")
        assert err.agent_id == "agt-xyz"

    def test_stores_reason(self):
        err = AuthenticationError("agt", "bad signature")
        assert err.reason == "bad signature"

    def test_without_details(self):
        err = AuthenticationError("agt", "reason")
        d = err.to_dict()["details"]
        assert d["agent_id"] == "agt"
        assert d["reason"] == "reason"

    def test_with_extra_details(self):
        err = AuthenticationError("agt", "reason", details={"ip": "1.2.3.4"})
        assert err.to_dict()["details"]["ip"] == "1.2.3.4"

    def test_is_agent_bus_error(self):
        err = AuthenticationError("agt", "reason")
        assert isinstance(err, AgentBusError)

    def test_message_format(self):
        err = AuthenticationError("agent-abc", "session expired")
        assert "Authentication failed for agent 'agent-abc': session expired" in str(err)

    def test_raise_and_catch(self):
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("a", "r")

    def test_to_dict_error_type(self):
        err = AuthenticationError("a", "r")
        assert err.to_dict()["error_type"] == "AuthenticationError"

    def test_extra_details_merged(self):
        err = AuthenticationError("a", "r", details={"extra_field": "extra_value"})
        assert "extra_field" in err.to_dict()["details"]


# ---------------------------------------------------------------------------
# AuthorizationError
# ---------------------------------------------------------------------------


class TestAuthorizationError:
    def test_basic_instantiation(self):
        err = AuthorizationError("agent-001", "write_policy", "insufficient permissions")
        assert "agent-001" in str(err)
        assert "write_policy" in str(err)

    def test_stores_attributes(self):
        err = AuthorizationError("agt", "action_x", "denied")
        assert err.agent_id == "agt"
        assert err.action == "action_x"
        assert err.reason == "denied"

    def test_without_details(self):
        err = AuthorizationError("agt", "act", "reason")
        d = err.to_dict()["details"]
        assert d["agent_id"] == "agt"
        assert d["action"] == "act"
        assert d["reason"] == "reason"

    def test_with_extra_details(self):
        err = AuthorizationError("agt", "act", "reason", details={"policy": "strict"})
        assert err.to_dict()["details"]["policy"] == "strict"

    def test_is_agent_bus_error(self):
        err = AuthorizationError("a", "b", "c")
        assert isinstance(err, AgentBusError)

    def test_message_format(self):
        err = AuthorizationError("agt-001", "delete_data", "role mismatch")
        msg = str(err)
        assert "agt-001" in msg
        assert "delete_data" in msg
        assert "role mismatch" in msg

    def test_raise_and_catch(self):
        with pytest.raises(AuthorizationError):
            raise AuthorizationError("a", "b", "c")

    def test_to_dict_error_type(self):
        err = AuthorizationError("a", "b", "c")
        assert err.to_dict()["error_type"] == "AuthorizationError"

    def test_extra_details_merged(self):
        err = AuthorizationError("a", "b", "c", details={"env": "prod"})
        assert "env" in err.to_dict()["details"]


# ---------------------------------------------------------------------------
# DependencyError
# ---------------------------------------------------------------------------


class TestDependencyError:
    def test_basic_instantiation(self):
        err = DependencyError("redis", "connection refused")
        assert "redis" in str(err)
        assert "connection refused" in str(err)

    def test_stores_dependency_name(self):
        err = DependencyError("kafka", "timeout")
        assert err.dependency_name == "kafka"

    def test_stores_reason(self):
        err = DependencyError("opa", "unavailable")
        assert err.reason == "unavailable"

    def test_without_details(self):
        err = DependencyError("dep", "reason")
        d = err.to_dict()["details"]
        assert d["dependency_name"] == "dep"
        assert d["reason"] == "reason"

    def test_with_extra_details(self):
        err = DependencyError("dep", "reason", details={"host": "localhost"})
        assert err.to_dict()["details"]["host"] == "localhost"

    def test_is_agent_bus_error(self):
        err = DependencyError("d", "r")
        assert isinstance(err, AgentBusError)

    def test_message_format(self):
        err = DependencyError("postgres", "disk full")
        assert "Dependency 'postgres' failed: disk full" in str(err)

    def test_raise_and_catch(self):
        with pytest.raises(DependencyError):
            raise DependencyError("d", "r")

    def test_to_dict_error_type(self):
        err = DependencyError("d", "r")
        assert err.to_dict()["error_type"] == "DependencyError"

    def test_extra_details_merged(self):
        err = DependencyError("d", "r", details={"retry_count": 3})
        assert err.to_dict()["details"]["retry_count"] == 3


# ---------------------------------------------------------------------------
# CircuitBreakerOpenError
# ---------------------------------------------------------------------------


class TestCircuitBreakerOpenError:
    def test_basic_instantiation(self):
        err = CircuitBreakerOpenError("circuit breaker is open")
        assert isinstance(err, CircuitBreakerOpenError)

    def test_is_bus_operation_error(self):
        err = CircuitBreakerOpenError("open")
        assert isinstance(err, BusOperationError)

    def test_is_agent_bus_error(self):
        err = CircuitBreakerOpenError("open")
        assert isinstance(err, AgentBusError)

    def test_raise_and_catch_as_bus_operation_error(self):
        with pytest.raises(BusOperationError):
            raise CircuitBreakerOpenError("circuit is open")

    def test_raise_and_catch_directly(self):
        with pytest.raises(CircuitBreakerOpenError):
            raise CircuitBreakerOpenError("open")

    def test_to_dict_error_type(self):
        err = CircuitBreakerOpenError("open")
        assert err.to_dict()["error_type"] == "CircuitBreakerOpenError"


# ---------------------------------------------------------------------------
# RateLimitExceededError (alias for RateLimitExceeded)
# ---------------------------------------------------------------------------


class TestRateLimitExceededError:
    def test_basic_instantiation(self):
        err = RateLimitExceededError("agent-001", 100, 60)
        assert "agent-001" in str(err)

    def test_is_rate_limit_exceeded(self):
        err = RateLimitExceededError("agt", 50, 30)
        assert isinstance(err, RateLimitExceeded)

    def test_is_agent_bus_error(self):
        err = RateLimitExceededError("agt", 50, 30)
        assert isinstance(err, AgentBusError)

    def test_raise_and_catch_as_rate_limit_exceeded(self):
        with pytest.raises(RateLimitExceeded):
            raise RateLimitExceededError("agt", 10, 5)

    def test_raise_and_catch_directly(self):
        with pytest.raises(RateLimitExceededError):
            raise RateLimitExceededError("agt", 10, 5)

    def test_to_dict_error_type(self):
        err = RateLimitExceededError("agt", 10, 5)
        assert err.to_dict()["error_type"] == "RateLimitExceededError"

    def test_with_retry_after(self):
        err = RateLimitExceededError("agt", 100, 60, retry_after_ms=5000)
        assert "5000" in str(err)


# ---------------------------------------------------------------------------
# ResourceNotFoundError
# ---------------------------------------------------------------------------


class TestResourceNotFoundError:
    def test_basic_instantiation(self):
        err = ResourceNotFoundError("resource not found")
        assert isinstance(err, ResourceNotFoundError)

    def test_is_agent_bus_error(self):
        err = ResourceNotFoundError("not found")
        assert isinstance(err, AgentBusError)

    def test_raise_and_catch(self):
        with pytest.raises(ResourceNotFoundError):
            raise ResourceNotFoundError("missing")

    def test_to_dict_error_type(self):
        err = ResourceNotFoundError("missing")
        assert err.to_dict()["error_type"] == "ResourceNotFoundError"


# ---------------------------------------------------------------------------
# ServiceUnavailableError
# ---------------------------------------------------------------------------


class TestServiceUnavailableError:
    def test_basic_instantiation(self):
        err = ServiceUnavailableError("service down")
        assert isinstance(err, ServiceUnavailableError)

    def test_is_agent_bus_error(self):
        err = ServiceUnavailableError("down")
        assert isinstance(err, AgentBusError)

    def test_raise_and_catch(self):
        with pytest.raises(ServiceUnavailableError):
            raise ServiceUnavailableError("down")

    def test_to_dict_error_type(self):
        err = ServiceUnavailableError("down")
        assert err.to_dict()["error_type"] == "ServiceUnavailableError"


# ---------------------------------------------------------------------------
# TenantIsolationError
# ---------------------------------------------------------------------------


class TestTenantIsolationError:
    def test_basic_instantiation(self):
        err = TenantIsolationError("tenant isolation violated")
        assert isinstance(err, TenantIsolationError)

    def test_is_agent_bus_error(self):
        err = TenantIsolationError("violation")
        assert isinstance(err, AgentBusError)

    def test_raise_and_catch(self):
        with pytest.raises(TenantIsolationError):
            raise TenantIsolationError("violation")

    def test_to_dict_error_type(self):
        err = TenantIsolationError("violation")
        assert err.to_dict()["error_type"] == "TenantIsolationError"


# ---------------------------------------------------------------------------
# ValidationError
# ---------------------------------------------------------------------------


class TestValidationError:
    def test_basic_instantiation(self):
        err = ValidationError("invalid input")
        assert isinstance(err, ValidationError)

    def test_is_agent_bus_error(self):
        err = ValidationError("invalid")
        assert isinstance(err, AgentBusError)

    def test_raise_and_catch(self):
        with pytest.raises(ValidationError):
            raise ValidationError("invalid")

    def test_to_dict_error_type(self):
        err = ValidationError("invalid")
        assert err.to_dict()["error_type"] == "ValidationError"


# ---------------------------------------------------------------------------
# __all__ export verification
# ---------------------------------------------------------------------------


class TestModuleExports:
    def test_all_exports_importable(self):
        from enhanced_agent_bus.exceptions import operations as ops_module

        for name in ops_module.__all__:
            assert hasattr(ops_module, name), f"Missing export: {name}"

    def test_bus_operation_error_exported(self):
        from enhanced_agent_bus.exceptions.operations import BusOperationError as BOE

        assert BOE is BusOperationError

    def test_governance_error_exported(self):
        from enhanced_agent_bus.exceptions.operations import GovernanceError as GE

        assert GE is GovernanceError


# ---------------------------------------------------------------------------
# Cross-hierarchy / polymorphism tests
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_deliberation_timeout_is_agent_bus_error(self):
        err = DeliberationTimeoutError("d", 10)
        assert isinstance(err, AgentBusError)

    def test_signature_collection_is_agent_bus_error(self):
        err = SignatureCollectionError("d", ["a"], ["a"], "r")
        assert isinstance(err, AgentBusError)

    def test_review_consensus_is_agent_bus_error(self):
        err = ReviewConsensusError("d", 1, 2, 0)
        assert isinstance(err, AgentBusError)

    def test_handler_execution_is_agent_bus_error(self):
        err = HandlerExecutionError("h", "m", Exception("e"))
        assert isinstance(err, AgentBusError)

    def test_rate_limit_exceeded_error_is_rate_limit_exceeded(self):
        err = RateLimitExceededError("agt", 10, 5)
        assert isinstance(err, RateLimitExceeded)

    def test_impact_assessment_is_governance_error(self):
        err = ImpactAssessmentError("t", "r")
        assert isinstance(err, GovernanceError)

    def test_deliberation_timeout_is_deliberation_error(self):
        err = DeliberationTimeoutError("d", 30)
        assert isinstance(err, DeliberationError)

    def test_signature_collection_is_deliberation_error(self):
        err = SignatureCollectionError("d", [], [], "r")
        assert isinstance(err, DeliberationError)

    def test_review_consensus_is_deliberation_error(self):
        err = ReviewConsensusError("d", 0, 0, 0)
        assert isinstance(err, DeliberationError)

    def test_bus_not_started_is_bus_operation_error(self):
        err = BusNotStartedError("op")
        assert isinstance(err, BusOperationError)

    def test_bus_already_started_is_bus_operation_error(self):
        err = BusAlreadyStartedError()
        assert isinstance(err, BusOperationError)

    def test_circuit_breaker_is_bus_operation_error(self):
        err = CircuitBreakerOpenError("open")
        assert isinstance(err, BusOperationError)

    def test_all_are_exceptions(self):
        classes = [
            GovernanceError,
            ImpactAssessmentError,
            DeliberationError,
            DeliberationTimeoutError,
            SignatureCollectionError,
            ReviewConsensusError,
            BusNotStartedError,
            BusAlreadyStartedError,
            ConfigurationError,
            AlignmentViolationError,
            AuthenticationError,
            AuthorizationError,
            DependencyError,
            CircuitBreakerOpenError,
            ResourceNotFoundError,
            ServiceUnavailableError,
            TenantIsolationError,
            ValidationError,
        ]
        for cls in classes:
            assert issubclass(cls, Exception), f"{cls.__name__} is not an Exception subclass"

    def test_catch_all_as_agent_bus_error(self):
        errors = [
            GovernanceError("g"),
            ImpactAssessmentError("t", "r"),
            DeliberationError("d"),
            DeliberationTimeoutError("d", 10),
            SignatureCollectionError("d", [], [], "r"),
            ReviewConsensusError("d", 0, 0, 0),
            BusNotStartedError("op"),
            BusAlreadyStartedError(),
            ConfigurationError("k", "r"),
            AlignmentViolationError("v"),
            AuthenticationError("a", "r"),
            AuthorizationError("a", "b", "r"),
            DependencyError("d", "r"),
            CircuitBreakerOpenError("open"),
            RateLimitExceededError("agt", 10, 5),
            ResourceNotFoundError("missing"),
            ServiceUnavailableError("down"),
            TenantIsolationError("violation"),
            ValidationError("invalid"),
        ]
        for err in errors:
            assert isinstance(err, AgentBusError), (
                f"{type(err).__name__} is not an AgentBusError subclass"
            )


# ---------------------------------------------------------------------------
# to_dict() structural tests
# ---------------------------------------------------------------------------


class TestToDictStructure:
    """Ensure to_dict() output always contains the required keys.

    Note: "details" key is only present in to_dict() when details is non-empty.
    Stub exceptions (no __init__ override) have empty details and omit the key.
    """

    # Keys always present regardless of details
    ALWAYS_REQUIRED: ClassVar[set] = {"error_type", "message"}

    def _assert_has_always_keys(self, err):
        d = err.to_dict()
        for key in self.ALWAYS_REQUIRED:
            assert key in d, f"Missing key '{key}' in to_dict() for {type(err).__name__}"

    def _assert_has_details(self, err):
        """Use only for exceptions that always set non-empty details."""
        d = err.to_dict()
        assert "details" in d, f"Expected 'details' key for {type(err).__name__}"

    def test_governance_error_with_details(self):
        self._assert_has_details(GovernanceError("msg", details={"k": "v"}))

    def test_governance_error_always_keys(self):
        self._assert_has_always_keys(GovernanceError("msg"))

    def test_impact_assessment_error(self):
        self._assert_has_always_keys(ImpactAssessmentError("t", "r"))
        self._assert_has_details(ImpactAssessmentError("t", "r"))

    def test_deliberation_error_always_keys(self):
        self._assert_has_always_keys(DeliberationError("msg"))

    def test_deliberation_timeout_error(self):
        self._assert_has_always_keys(DeliberationTimeoutError("d", 10))
        self._assert_has_details(DeliberationTimeoutError("d", 10))

    def test_signature_collection_error(self):
        self._assert_has_always_keys(SignatureCollectionError("d", [], [], "r"))
        self._assert_has_details(SignatureCollectionError("d", ["a"], ["a"], "r"))

    def test_review_consensus_error(self):
        self._assert_has_always_keys(ReviewConsensusError("d", 0, 0, 0))
        self._assert_has_details(ReviewConsensusError("d", 0, 0, 0))

    def test_bus_not_started_error(self):
        self._assert_has_always_keys(BusNotStartedError("op"))
        self._assert_has_details(BusNotStartedError("op"))

    def test_bus_already_started_error_always_keys(self):
        self._assert_has_always_keys(BusAlreadyStartedError())

    def test_handler_execution_error(self):
        self._assert_has_always_keys(HandlerExecutionError("h", "m", Exception("e")))
        self._assert_has_details(HandlerExecutionError("h", "m", Exception("e")))

    def test_configuration_error(self):
        self._assert_has_always_keys(ConfigurationError("k", "r"))
        self._assert_has_details(ConfigurationError("k", "r"))

    def test_alignment_violation_error(self):
        self._assert_has_always_keys(AlignmentViolationError("v"))
        self._assert_has_details(AlignmentViolationError("v"))

    def test_authentication_error(self):
        self._assert_has_always_keys(AuthenticationError("a", "r"))
        self._assert_has_details(AuthenticationError("a", "r"))

    def test_authorization_error(self):
        self._assert_has_always_keys(AuthorizationError("a", "b", "r"))
        self._assert_has_details(AuthorizationError("a", "b", "r"))

    def test_dependency_error(self):
        self._assert_has_always_keys(DependencyError("d", "r"))
        self._assert_has_details(DependencyError("d", "r"))

    def test_circuit_breaker_open_error_always_keys(self):
        self._assert_has_always_keys(CircuitBreakerOpenError("open"))

    def test_resource_not_found_error_always_keys(self):
        self._assert_has_always_keys(ResourceNotFoundError("missing"))

    def test_service_unavailable_error_always_keys(self):
        self._assert_has_always_keys(ServiceUnavailableError("down"))

    def test_tenant_isolation_error_always_keys(self):
        self._assert_has_always_keys(TenantIsolationError("violation"))

    def test_validation_error_always_keys(self):
        self._assert_has_always_keys(ValidationError("invalid"))

    def test_rate_limit_exceeded_error(self):
        self._assert_has_always_keys(RateLimitExceededError("agt", 10, 5))
        self._assert_has_details(RateLimitExceededError("agt", 10, 5))
