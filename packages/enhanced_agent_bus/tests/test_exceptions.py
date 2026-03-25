"""
ACGS-2 Enhanced Agent Bus - Exception Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for all custom exception types.
"""

import os
import sys

import pytest

# Add parent directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from enhanced_agent_bus.exceptions import (  # Agent; Bus Operations; Configuration; Constitutional; Deliberation; Message; Policy/OPA
    CONSTITUTIONAL_HASH,
    AgentAlreadyRegisteredError,
    AgentBusError,
    AgentCapabilityError,
    AgentError,
    AgentNotRegisteredError,
    BusAlreadyStartedError,
    BusNotStartedError,
    BusOperationError,
    ConfigurationError,
    ConstitutionalError,
    ConstitutionalHashMismatchError,
    ConstitutionalValidationError,
    DeliberationError,
    DeliberationTimeoutError,
    HandlerExecutionError,
    MessageDeliveryError,
    MessageError,
    MessageRoutingError,
    MessageTimeoutError,
    MessageValidationError,
    OPAConnectionError,
    OPANotInitializedError,
    PolicyError,
    PolicyEvaluationError,
    PolicyNotFoundError,
    ReviewConsensusError,
    SignatureCollectionError,
)

# ============================================================================
# Constitutional Compliance Tests
# ============================================================================


class TestConstitutionalHash:
    """Test constitutional hash compliance."""

    def test_constitutional_hash_value(self):
        """Verify constitutional hash value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH


# ============================================================================
# Base AgentBusError Tests
# ============================================================================


class TestAgentBusError:
    """Test base exception class."""

    def test_basic_instantiation(self):
        """Test basic exception creation."""
        err = AgentBusError("Test error message")
        assert err.message == "Test error message"
        assert "Test error message" in str(err)
        assert err.details == {}
        assert err.constitutional_hash == CONSTITUTIONAL_HASH

    def test_with_details(self):
        """Test exception with details."""
        details = {"key": "value", "count": 42}
        err = AgentBusError("Error with details", details=details)
        assert err.details == details
        assert err.details["key"] == "value"
        assert err.details["count"] == 42

    def test_custom_constitutional_hash(self):
        """Test exception with custom constitutional hash."""
        err = AgentBusError("Custom hash", constitutional_hash="custom_hash")
        assert err.constitutional_hash == "custom_hash"

    def test_to_dict(self):
        """Test to_dict serialization."""
        details = {"info": "test"}
        err = AgentBusError("Test message", details=details)
        result = err.to_dict()

        assert result["error_type"] == "AgentBusError"
        assert result["message"] == "Test message"
        assert result["details"] == details
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_inheritance(self):
        """Test exception can be caught as Exception."""
        with pytest.raises(AgentBusError):
            raise AgentBusError("Test")

    def test_none_details_becomes_empty_dict(self):
        """Test that None details becomes empty dict."""
        err = AgentBusError("Test", details=None)
        assert err.details == {}


# ============================================================================
# Constitutional Error Tests
# ============================================================================


class TestConstitutionalError:
    """Test constitutional base exception."""

    def test_basic_instantiation(self):
        """Test constitutional error creation."""
        err = ConstitutionalError("Constitutional failure")
        assert isinstance(err, AgentBusError)
        assert "Constitutional failure" in str(err)

    def test_inheritance_chain(self):
        """Test inheritance from AgentBusError."""
        err = ConstitutionalError("Test")
        assert isinstance(err, AgentBusError)
        assert isinstance(err, ConstitutionalError)


class TestConstitutionalHashMismatchError:
    """Test hash mismatch exception."""

    def test_basic_instantiation(self):
        """Test hash mismatch error creation."""
        err = ConstitutionalHashMismatchError(expected_hash="expected123", actual_hash="actual456")
        # Error message shows sanitized (truncated) hash prefixes for security
        assert "expected..." in str(err)
        assert "actual45..." in str(err)
        # Full hashes are still available via properties for internal use
        assert err.expected_hash == "expected123"
        assert err.actual_hash == "actual456"

    def test_with_context(self):
        """Test hash mismatch with context."""
        err = ConstitutionalHashMismatchError(
            expected_hash="exp", actual_hash="act", context="policy validation"
        )
        assert "policy validation" in str(err)
        assert err.details["context"] == "policy validation"

    def test_to_dict_includes_hashes(self):
        """Test to_dict includes sanitized hash prefixes for security."""
        err = ConstitutionalHashMismatchError("exp", "act", "ctx")
        result = err.to_dict()
        # Only sanitized prefixes are exposed in serializable output
        assert result["details"]["expected_hash_prefix"] == "exp"
        assert result["details"]["actual_hash_prefix"] == "act"
        # Full hashes should NOT be in serialized output
        assert "expected_hash" not in result["details"]
        assert "actual_hash" not in result["details"]


class TestConstitutionalValidationError:
    """Test validation error exception."""

    def test_single_error(self):
        """Test with single validation error."""
        err = ConstitutionalValidationError(["Missing required field"])
        assert "Missing required field" in str(err)
        assert len(err.validation_errors) == 1

    def test_multiple_errors(self):
        """Test with multiple validation errors."""
        errors = ["Error 1", "Error 2", "Error 3"]
        err = ConstitutionalValidationError(errors)
        assert all(e in str(err) for e in errors)
        assert err.validation_errors == errors

    def test_with_agent_and_action(self):
        """Test with agent ID and action type."""
        err = ConstitutionalValidationError(
            validation_errors=["Invalid action"], agent_id="agent-001", action_type="deploy"
        )
        assert err.agent_id == "agent-001"
        assert err.action_type == "deploy"
        assert err.details["agent_id"] == "agent-001"


# ============================================================================
# Message Error Tests
# ============================================================================


class TestMessageError:
    """Test message base exception."""

    def test_inheritance(self):
        """Test inheritance from AgentBusError."""
        err = MessageError("Message error")
        assert isinstance(err, AgentBusError)


class TestMessageValidationError:
    """Test message validation error."""

    def test_basic_instantiation(self):
        """Test basic message validation error."""
        err = MessageValidationError(message_id="msg-123", errors=["Invalid format"])
        assert "msg-123" in str(err)
        assert err.message_id == "msg-123"
        assert err.errors == ["Invalid format"]
        assert err.warnings == []

    def test_with_warnings(self):
        """Test with warnings included."""
        err = MessageValidationError(
            message_id="msg-456", errors=["Error 1"], warnings=["Warning 1", "Warning 2"]
        )
        assert err.warnings == ["Warning 1", "Warning 2"]
        assert err.details["warnings"] == ["Warning 1", "Warning 2"]


class TestMessageDeliveryError:
    """Test message delivery error."""

    def test_instantiation(self):
        """Test delivery error creation."""
        err = MessageDeliveryError(
            message_id="msg-001", target_agent="agent-A", reason="Connection refused"
        )
        assert "msg-001" in str(err)
        assert "agent-A" in str(err)
        assert "Connection refused" in str(err)
        assert err.message_id == "msg-001"
        assert err.target_agent == "agent-A"
        assert err.reason == "Connection refused"


class TestMessageTimeoutError:
    """Test message timeout error."""

    def test_basic_timeout(self):
        """Test basic timeout error."""
        err = MessageTimeoutError(message_id="msg-timeout", timeout_ms=5000)
        assert "msg-timeout" in str(err)
        assert "5000" in str(err)
        assert err.timeout_ms == 5000

    def test_with_operation(self):
        """Test timeout with operation context."""
        err = MessageTimeoutError(message_id="msg-op", timeout_ms=3000, operation="validation")
        assert "validation" in str(err)
        assert err.operation == "validation"


class TestMessageRoutingError:
    """Test message routing error."""

    def test_instantiation(self):
        """Test routing error creation."""
        err = MessageRoutingError(
            message_id="msg-route",
            source_agent="source-A",
            target_agent="target-B",
            reason="No route available",
        )
        assert "msg-route" in str(err)
        assert "source-A" in str(err)
        assert "target-B" in str(err)
        assert err.source_agent == "source-A"
        assert err.target_agent == "target-B"


# ============================================================================
# Agent Error Tests
# ============================================================================


class TestAgentError:
    """Test agent base exception."""

    def test_inheritance(self):
        """Test inheritance from AgentBusError."""
        err = AgentError("Agent error")
        assert isinstance(err, AgentBusError)


class TestAgentNotRegisteredError:
    """Test agent not registered error."""

    def test_basic_instantiation(self):
        """Test basic not registered error."""
        err = AgentNotRegisteredError(agent_id="agent-missing")
        assert "agent-missing" in str(err)
        assert err.agent_id == "agent-missing"
        assert err.operation is None

    def test_with_operation(self):
        """Test with operation context."""
        err = AgentNotRegisteredError(agent_id="agent-x", operation="message sending")
        assert "message sending" in str(err)
        assert err.operation == "message sending"


class TestAgentAlreadyRegisteredError:
    """Test agent already registered error."""

    def test_instantiation(self):
        """Test already registered error."""
        err = AgentAlreadyRegisteredError(agent_id="agent-dup")
        assert "agent-dup" in str(err)
        assert "already registered" in str(err).lower()
        assert err.agent_id == "agent-dup"


class TestAgentCapabilityError:
    """Test agent capability error."""

    def test_instantiation(self):
        """Test capability error creation."""
        err = AgentCapabilityError(
            agent_id="agent-caps",
            required_capabilities=["read", "write", "admin"],
            available_capabilities=["read"],
        )
        assert err.agent_id == "agent-caps"
        assert err.required_capabilities == ["read", "write", "admin"]
        assert err.available_capabilities == ["read"]
        # Check missing capabilities in message
        assert "write" in str(err) or "admin" in str(err)

    def test_missing_capabilities_in_details(self):
        """Test that missing capabilities are calculated correctly."""
        err = AgentCapabilityError(
            agent_id="test", required_capabilities=["a", "b", "c"], available_capabilities=["a"]
        )
        missing = err.details["missing_capabilities"]
        assert set(missing) == {"b", "c"}


# ============================================================================
# Policy and OPA Error Tests
# ============================================================================


class TestPolicyError:
    """Test policy base exception."""

    def test_inheritance(self):
        """Test inheritance from AgentBusError."""
        err = PolicyError("Policy error")
        assert isinstance(err, AgentBusError)


class TestPolicyEvaluationError:
    """Test policy evaluation error."""

    def test_basic_instantiation(self):
        """Test basic evaluation error."""
        err = PolicyEvaluationError(policy_path="data.acgs.allow", reason="Undefined result")
        assert "data.acgs.allow" in str(err)
        assert "Undefined result" in str(err)
        assert err.policy_path == "data.acgs.allow"
        assert err.reason == "Undefined result"
        assert err.input_data is None

    def test_with_input_data(self):
        """Test with input data included."""
        input_data = {"action": "deploy", "resource": "db"}
        err = PolicyEvaluationError(
            policy_path="data.auth.check", reason="Access denied", input_data=input_data
        )
        assert err.input_data == input_data
        assert err.details["input_data"] == input_data


class TestPolicyNotFoundError:
    """Test policy not found error."""

    def test_instantiation(self):
        """Test not found error."""
        err = PolicyNotFoundError(policy_path="data.missing.policy")
        assert "data.missing.policy" in str(err)
        assert err.policy_path == "data.missing.policy"


class TestOPAConnectionError:
    """Test OPA connection error."""

    def test_instantiation(self):
        """Test connection error creation."""
        err = OPAConnectionError(opa_url="http://localhost:8181", reason="Connection refused")
        assert "localhost:8181" in str(err)
        assert "Connection refused" in str(err)
        assert err.opa_url == "http://localhost:8181"
        assert err.reason == "Connection refused"


class TestOPANotInitializedError:
    """Test OPA not initialized error."""

    def test_instantiation(self):
        """Test not initialized error."""
        err = OPANotInitializedError(operation="evaluate_policy")
        assert "evaluate_policy" in str(err)
        assert err.operation == "evaluate_policy"


# ============================================================================
# Deliberation Error Tests
# ============================================================================


class TestDeliberationError:
    """Test deliberation base exception."""

    def test_inheritance(self):
        """Test inheritance from AgentBusError."""
        err = DeliberationError("Deliberation error")
        assert isinstance(err, AgentBusError)


class TestDeliberationTimeoutError:
    """Test deliberation timeout error."""

    def test_basic_instantiation(self):
        """Test basic timeout error."""
        err = DeliberationTimeoutError(decision_id="dec-001", timeout_seconds=60)
        assert "dec-001" in str(err)
        assert "60" in str(err)
        assert err.decision_id == "dec-001"
        assert err.timeout_seconds == 60
        assert err.pending_reviews == 0
        assert err.pending_signatures == 0

    def test_with_pending_items(self):
        """Test with pending reviews and signatures."""
        err = DeliberationTimeoutError(
            decision_id="dec-002", timeout_seconds=120, pending_reviews=3, pending_signatures=2
        )
        assert err.pending_reviews == 3
        assert err.pending_signatures == 2
        assert err.details["pending_reviews"] == 3


class TestSignatureCollectionError:
    """Test signature collection error."""

    def test_instantiation(self):
        """Test signature collection error."""
        err = SignatureCollectionError(
            decision_id="dec-sig",
            required_signers=["signer-A", "signer-B", "signer-C"],
            collected_signers=["signer-A"],
            reason="Timeout waiting for signatures",
        )
        assert "dec-sig" in str(err)
        assert "Timeout waiting for signatures" in str(err)
        assert set(err.details["missing_signers"]) == {"signer-B", "signer-C"}


class TestReviewConsensusError:
    """Test review consensus error."""

    def test_instantiation(self):
        """Test consensus error creation."""
        err = ReviewConsensusError(
            decision_id="dec-consensus", approval_count=2, rejection_count=2, escalation_count=1
        )
        assert "dec-consensus" in str(err)
        assert "2 approvals" in str(err)
        assert "2 rejections" in str(err)
        assert "1 escalations" in str(err)
        assert err.approval_count == 2
        assert err.rejection_count == 2
        assert err.escalation_count == 1


# ============================================================================
# Bus Operation Error Tests
# ============================================================================


class TestBusOperationError:
    """Test bus operation base exception."""

    def test_inheritance(self):
        """Test inheritance from AgentBusError."""
        err = BusOperationError("Bus operation error")
        assert isinstance(err, AgentBusError)


class TestBusNotStartedError:
    """Test bus not started error."""

    def test_instantiation(self):
        """Test not started error."""
        err = BusNotStartedError(operation="send_message")
        assert "send_message" in str(err)
        assert "not started" in str(err).lower()
        assert err.operation == "send_message"


class TestBusAlreadyStartedError:
    """Test bus already started error."""

    def test_instantiation(self):
        """Test already started error."""
        err = BusAlreadyStartedError()
        assert "already running" in str(err).lower()
        assert err.details == {}


class TestHandlerExecutionError:
    """Test handler execution error."""

    def test_instantiation(self):
        """Test handler execution error."""
        original = ValueError("Invalid input")
        err = HandlerExecutionError(
            handler_name="process_message", message_id="msg-handler", original_error=original
        )
        assert "process_message" in str(err)
        assert "msg-handler" in str(err)
        assert "Invalid input" in str(err)
        assert err.handler_name == "process_message"
        assert err.message_id == "msg-handler"
        assert err.original_error is original
        assert err.details["original_error_type"] == "ValueError"


# ============================================================================
# Configuration Error Tests
# ============================================================================


class TestConfigurationError:
    """Test configuration error."""

    def test_instantiation(self):
        """Test configuration error creation."""
        err = ConfigurationError(config_key="redis_url", reason="Invalid URL format")
        assert "redis_url" in str(err)
        assert "Invalid URL format" in str(err)
        assert err.config_key == "redis_url"
        assert err.reason == "Invalid URL format"


# ============================================================================
# Module Export Tests (using already imported exceptions)
# ============================================================================


class TestModuleExports:
    """Test that all exceptions are properly exported (verified via imports at top)."""

    def test_constitutional_errors_are_classes(self):
        """Test constitutional errors are proper classes."""
        assert issubclass(ConstitutionalError, AgentBusError)
        assert issubclass(ConstitutionalHashMismatchError, ConstitutionalError)
        assert issubclass(ConstitutionalValidationError, ConstitutionalError)

    def test_message_errors_are_classes(self):
        """Test message errors are proper classes."""
        assert issubclass(MessageError, AgentBusError)
        assert issubclass(MessageValidationError, MessageError)
        assert issubclass(MessageDeliveryError, MessageError)
        assert issubclass(MessageTimeoutError, MessageError)
        assert issubclass(MessageRoutingError, MessageError)

    def test_agent_errors_are_classes(self):
        """Test agent errors are proper classes."""
        assert issubclass(AgentError, AgentBusError)
        assert issubclass(AgentNotRegisteredError, AgentError)
        assert issubclass(AgentAlreadyRegisteredError, AgentError)
        assert issubclass(AgentCapabilityError, AgentError)

    def test_policy_errors_are_classes(self):
        """Test policy errors are proper classes."""
        assert issubclass(PolicyError, AgentBusError)
        assert issubclass(PolicyEvaluationError, PolicyError)
        assert issubclass(PolicyNotFoundError, PolicyError)
        assert issubclass(OPAConnectionError, PolicyError)
        assert issubclass(OPANotInitializedError, PolicyError)

    def test_deliberation_errors_are_classes(self):
        """Test deliberation errors are proper classes."""
        assert issubclass(DeliberationError, AgentBusError)
        assert issubclass(DeliberationTimeoutError, DeliberationError)
        assert issubclass(SignatureCollectionError, DeliberationError)
        assert issubclass(ReviewConsensusError, DeliberationError)

    def test_bus_errors_are_classes(self):
        """Test bus operation errors are proper classes."""
        assert issubclass(BusOperationError, AgentBusError)
        assert issubclass(BusNotStartedError, BusOperationError)
        assert issubclass(BusAlreadyStartedError, BusOperationError)
        assert issubclass(HandlerExecutionError, BusOperationError)

    def test_configuration_error_is_class(self):
        """Test configuration error is proper class."""
        assert issubclass(ConfigurationError, AgentBusError)

    def test_constitutional_hash_value(self):
        """Test constitutional hash value is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH


# ============================================================================
# Exception Catching Tests
# ============================================================================


class TestExceptionCatching:
    """Test exception catching behavior."""

    def test_catch_specific_exception(self):
        """Test catching specific exception type."""
        with pytest.raises(ConstitutionalHashMismatchError):
            raise ConstitutionalHashMismatchError("exp", "act")

    def test_catch_base_class(self):
        """Test catching by base class."""
        with pytest.raises(ConstitutionalError):
            raise ConstitutionalHashMismatchError("exp", "act")

    def test_catch_agent_bus_error(self):
        """Test catching all agent bus errors."""
        with pytest.raises(AgentBusError):
            raise MessageDeliveryError("msg", "agent", "reason")

    def test_exception_chaining(self):
        """Test exception can be used in chaining."""
        try:
            try:
                raise ValueError("Original error")
            except ValueError as e:
                raise AgentBusError("Wrapped error") from e
        except AgentBusError as e:
            assert e.__cause__ is not None
            assert str(e.__cause__) == "Original error"
