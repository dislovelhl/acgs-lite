"""
ACGS-2 Exceptions Coverage Tests
Constitutional Hash: 608508a9bd224290

Extended tests to increase exceptions.py coverage.
"""

import pytest

try:
    from enhanced_agent_bus.exceptions import (
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
        MACICrossRoleValidationError,
        MACIError,
        MACIRoleNotAssignedError,
        MACIRoleViolationError,
        MACISelfValidationError,
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
    from enhanced_agent_bus.models import CONSTITUTIONAL_HASH
except ImportError:
    from exceptions import (
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
        MACICrossRoleValidationError,
        MACIError,
        MACIRoleNotAssignedError,
        MACIRoleViolationError,
        MACISelfValidationError,
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
    from models import CONSTITUTIONAL_HASH


class TestAgentBusError:
    """Tests for AgentBusError base class."""

    def test_basic_creation(self):
        """Create error with message only."""
        err = AgentBusError("Test error")
        assert err.message == "Test error"
        assert err.details == {}
        assert err.constitutional_hash == CONSTITUTIONAL_HASH

    def test_with_details(self):
        """Create error with details dict."""
        details = {"key": "value", "count": 42}
        err = AgentBusError("Test error", details=details)
        assert err.details == details

    def test_custom_constitutional_hash(self):
        """Create error with custom hash."""
        err = AgentBusError("Test", constitutional_hash="custom_hash")
        assert err.constitutional_hash == "custom_hash"

    def test_to_dict(self):
        """to_dict returns correct structure."""
        details = {"info": "data"}
        err = AgentBusError("Error msg", details=details)
        d = err.to_dict()
        assert d["error_type"] == "AgentBusError"
        assert d["message"] == "Error msg"
        assert d["details"] == details
        assert d["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_str_representation(self):
        """Exception str includes the message."""
        err = AgentBusError("Test message")
        assert "Test message" in str(err)

    def test_raise_and_catch(self):
        """Can be raised and caught."""
        with pytest.raises(AgentBusError) as exc_info:
            raise AgentBusError("Raised error")
        assert exc_info.value.message == "Raised error"


class TestConstitutionalHashMismatchError:
    """Tests for ConstitutionalHashMismatchError."""

    def test_basic_creation(self):
        """Create mismatch error with hashes."""
        err = ConstitutionalHashMismatchError(
            expected_hash="expected123456789", actual_hash="actual987654321"
        )
        assert err.expected_hash == "expected123456789"
        assert err.actual_hash == "actual987654321"

    def test_sanitize_hash_long(self):
        """Long hashes are sanitized in message."""
        err = ConstitutionalHashMismatchError(
            expected_hash="abcdefghijklmnop", actual_hash="1234567890abcdef"
        )
        assert "..." in err.message

    def test_sanitize_hash_short(self):
        """Short hashes are not truncated."""
        result = ConstitutionalHashMismatchError._sanitize_hash("abc")
        assert result == "abc"

    def test_sanitize_hash_empty(self):
        """Empty hash returns as-is."""
        result = ConstitutionalHashMismatchError._sanitize_hash("")
        assert result == ""

    def test_sanitize_hash_none(self):
        """None hash returns as-is."""
        result = ConstitutionalHashMismatchError._sanitize_hash(None)
        assert result is None

    def test_with_context(self):
        """Error includes context in message."""
        err = ConstitutionalHashMismatchError(
            expected_hash="abc", actual_hash="xyz", context="During message validation"
        )
        assert "During message validation" in err.message
        assert err.details["context"] == "During message validation"

    def test_inheritance(self):
        """Inherits from ConstitutionalError."""
        err = ConstitutionalHashMismatchError("a", "b")
        assert isinstance(err, ConstitutionalError)
        assert isinstance(err, AgentBusError)


class TestConstitutionalValidationError:
    """Tests for ConstitutionalValidationError."""

    def test_basic_creation(self):
        """Create validation error."""
        err = ConstitutionalValidationError(validation_errors=["Rule 1 failed", "Rule 2 failed"])
        assert "Rule 1 failed" in err.message
        assert err.validation_errors == ["Rule 1 failed", "Rule 2 failed"]

    def test_with_agent_and_action(self):
        """Error with agent and action info."""
        err = ConstitutionalValidationError(
            validation_errors=["policy violation"], agent_id="agent123", action_type="send_message"
        )
        assert err.agent_id == "agent123"
        assert err.action_type == "send_message"
        assert err.details["agent_id"] == "agent123"


class TestMessageValidationError:
    """Tests for MessageValidationError."""

    def test_basic_creation(self):
        """Create message validation error."""
        err = MessageValidationError(
            message_id="msg123", errors=["Invalid content", "Missing field"]
        )
        assert "msg123" in err.message
        assert err.message_id == "msg123"
        assert err.errors == ["Invalid content", "Missing field"]

    def test_with_warnings(self):
        """Error with warnings list."""
        err = MessageValidationError(
            message_id="msg456", errors=["error1"], warnings=["warning1", "warning2"]
        )
        assert err.warnings == ["warning1", "warning2"]

    def test_inheritance(self):
        """Inherits from MessageError."""
        err = MessageValidationError(message_id="x", errors=["e"])
        assert isinstance(err, MessageError)
        assert isinstance(err, AgentBusError)


class TestMessageDeliveryError:
    """Tests for MessageDeliveryError."""

    def test_basic_creation(self):
        """Create delivery error."""
        err = MessageDeliveryError(
            message_id="msg123", target_agent="agent456", reason="agent offline"
        )
        assert "msg123" in err.message
        assert "agent456" in err.message
        assert err.target_agent == "agent456"
        assert err.reason == "agent offline"


class TestMessageTimeoutError:
    """Tests for MessageTimeoutError."""

    def test_basic_creation(self):
        """Create timeout error."""
        err = MessageTimeoutError(message_id="msg123", timeout_ms=5000)
        assert "msg123" in err.message
        assert "5000" in err.message
        assert err.timeout_ms == 5000

    def test_with_operation(self):
        """Error with operation info."""
        err = MessageTimeoutError(message_id="msg789", timeout_ms=3000, operation="validation")
        assert "validation" in err.message
        assert err.operation == "validation"


class TestMessageRoutingError:
    """Tests for MessageRoutingError."""

    def test_basic_creation(self):
        """Create routing error."""
        err = MessageRoutingError(
            message_id="msg123",
            source_agent="sender",
            target_agent="receiver",
            reason="no route found",
        )
        assert "msg123" in err.message
        assert err.source_agent == "sender"
        assert err.target_agent == "receiver"
        assert err.reason == "no route found"


class TestAgentNotRegisteredError:
    """Tests for AgentNotRegisteredError."""

    def test_basic_creation(self):
        """Create not registered error."""
        err = AgentNotRegisteredError(agent_id="agent123")
        assert "agent123" in err.message
        assert err.details["agent_id"] == "agent123"

    def test_inheritance(self):
        """Inherits from AgentError."""
        err = AgentNotRegisteredError(agent_id="test")
        assert isinstance(err, AgentError)


class TestAgentAlreadyRegisteredError:
    """Tests for AgentAlreadyRegisteredError."""

    def test_basic_creation(self):
        """Create already registered error."""
        err = AgentAlreadyRegisteredError(agent_id="agent123")
        assert "agent123" in err.message
        assert err.details["agent_id"] == "agent123"


class TestAgentCapabilityError:
    """Tests for AgentCapabilityError."""

    def test_basic_creation(self):
        """Create capability error."""
        err = AgentCapabilityError(
            agent_id="agent123",
            required_capabilities=["translate", "summarize"],
            available_capabilities=["translate"],
        )
        assert "agent123" in err.message
        assert "summarize" in err.message
        assert err.required_capabilities == ["translate", "summarize"]
        assert err.available_capabilities == ["translate"]


class TestPolicyEvaluationError:
    """Tests for PolicyEvaluationError."""

    def test_basic_creation(self):
        """Create policy evaluation error."""
        err = PolicyEvaluationError(policy_path="governance/rate_limit", reason="request denied")
        assert "governance/rate_limit" in err.message
        assert err.policy_path == "governance/rate_limit"
        assert err.reason == "request denied"

    def test_with_input_data(self):
        """Error with input data."""
        err = PolicyEvaluationError(
            policy_path="test/policy", reason="evaluation failed", input_data={"key": "value"}
        )
        assert err.input_data == {"key": "value"}

    def test_inheritance(self):
        """Inherits from PolicyError."""
        err = PolicyEvaluationError(policy_path="x", reason="y")
        assert isinstance(err, PolicyError)


class TestPolicyNotFoundError:
    """Tests for PolicyNotFoundError."""

    def test_basic_creation(self):
        """Create not found error."""
        err = PolicyNotFoundError(policy_path="missing/policy")
        assert "missing/policy" in err.message
        assert err.policy_path == "missing/policy"


class TestOPAConnectionError:
    """Tests for OPAConnectionError."""

    def test_basic_creation(self):
        """Create OPA connection error."""
        err = OPAConnectionError(opa_url="http://opa:8181", reason="Connection refused")
        assert "opa:8181" in err.message
        assert err.opa_url == "http://opa:8181"
        assert err.reason == "Connection refused"


class TestOPANotInitializedError:
    """Tests for OPANotInitializedError."""

    def test_basic_creation(self):
        """Create not initialized error."""
        err = OPANotInitializedError(operation="evaluate_policy")
        assert "evaluate_policy" in err.message
        assert err.operation == "evaluate_policy"


class TestDeliberationTimeoutError:
    """Tests for DeliberationTimeoutError."""

    def test_basic_creation(self):
        """Create deliberation timeout error."""
        err = DeliberationTimeoutError(decision_id="dec123", timeout_seconds=30)
        assert "dec123" in err.message
        assert err.decision_id == "dec123"
        assert err.timeout_seconds == 30

    def test_with_pending_counts(self):
        """Error with pending reviews and signatures."""
        err = DeliberationTimeoutError(
            decision_id="dec456", timeout_seconds=60, pending_reviews=2, pending_signatures=3
        )
        assert err.pending_reviews == 2
        assert err.pending_signatures == 3

    def test_inheritance(self):
        """Inherits from DeliberationError."""
        err = DeliberationTimeoutError(decision_id="x", timeout_seconds=1)
        assert isinstance(err, DeliberationError)


class TestSignatureCollectionError:
    """Tests for SignatureCollectionError."""

    def test_basic_creation(self):
        """Create signature collection error."""
        err = SignatureCollectionError(
            decision_id="dec123",
            required_signers=["agent_a", "agent_b", "agent_c"],
            collected_signers=["agent_a"],
            reason="timeout",
        )
        assert "dec123" in err.message
        assert err.decision_id == "dec123"
        assert err.required_signers == ["agent_a", "agent_b", "agent_c"]
        assert err.collected_signers == ["agent_a"]


class TestReviewConsensusError:
    """Tests for ReviewConsensusError."""

    def test_basic_creation(self):
        """Create consensus error."""
        err = ReviewConsensusError(
            decision_id="dec123", approval_count=2, rejection_count=3, escalation_count=1
        )
        assert "dec123" in err.message
        assert err.approval_count == 2
        assert err.rejection_count == 3
        assert err.escalation_count == 1


class TestBusNotStartedError:
    """Tests for BusNotStartedError."""

    def test_basic_creation(self):
        """Create not started error."""
        err = BusNotStartedError(operation="send_message")
        assert "send_message" in err.message
        assert err.operation == "send_message"

    def test_inheritance(self):
        """Inherits from BusOperationError."""
        err = BusNotStartedError(operation="test")
        assert isinstance(err, BusOperationError)


class TestBusAlreadyStartedError:
    """Tests for BusAlreadyStartedError."""

    def test_basic_creation(self):
        """Create already started error."""
        err = BusAlreadyStartedError()
        assert "already" in err.message.lower() or "running" in err.message.lower()


class TestHandlerExecutionError:
    """Tests for HandlerExecutionError."""

    def test_basic_creation(self):
        """Create handler execution error."""
        original = TypeError("missing arg")
        err = HandlerExecutionError(
            handler_name="MyHandler", message_id="msg123", original_error=original
        )
        assert "MyHandler" in err.message
        assert "msg123" in err.message
        assert err.handler_name == "MyHandler"
        assert err.original_error == original


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_basic_creation(self):
        """Create configuration error."""
        err = ConfigurationError(config_key="REDIS_URL", reason="Missing required configuration")
        assert "REDIS_URL" in err.message
        assert err.config_key == "REDIS_URL"
        assert err.reason == "Missing required configuration"


class TestMACIRoleViolationError:
    """Tests for MACIRoleViolationError."""

    def test_basic_creation(self):
        """Create role violation error."""
        err = MACIRoleViolationError(agent_id="agent123", role="executive", action="validate")
        assert "agent123" in err.message
        assert "executive" in err.message
        assert "validate" in err.message
        assert err.agent_id == "agent123"
        assert err.role == "executive"
        assert err.action == "validate"

    def test_with_allowed_roles(self):
        """Error with allowed roles list."""
        err = MACIRoleViolationError(
            agent_id="agent123", role="executive", action="audit", allowed_roles=["judicial"]
        )
        assert err.allowed_roles == ["judicial"]
        assert "judicial" in err.message

    def test_inheritance(self):
        """Inherits from MACIError."""
        err = MACIRoleViolationError("a", "b", "c")
        assert isinstance(err, MACIError)


class TestMACISelfValidationError:
    """Tests for MACISelfValidationError."""

    def test_basic_creation(self):
        """Create self validation error."""
        err = MACISelfValidationError(agent_id="agent123", action="self-approve")
        assert "agent123" in err.message
        assert "Gödel" in err.message or "godel" in err.message.lower()
        assert err.agent_id == "agent123"
        assert err.action == "self-approve"

    def test_with_output_id(self):
        """Error with output ID."""
        err = MACISelfValidationError(agent_id="agent123", action="validate", output_id="output456")
        assert err.output_id == "output456"
        assert "output456" in err.message


class TestMACICrossRoleValidationError:
    """Tests for MACICrossRoleValidationError."""

    def test_basic_creation(self):
        """Create cross role validation error."""
        err = MACICrossRoleValidationError(
            validator_agent="validator123",
            validator_role="executive",
            target_agent="target456",
            target_role="judicial",
            reason="role conflict",
        )
        assert err.validator_agent == "validator123"
        assert err.validator_role == "executive"
        assert err.target_agent == "target456"
        assert err.target_role == "judicial"
        assert err.reason == "role conflict"


class TestMACIRoleNotAssignedError:
    """Tests for MACIRoleNotAssignedError."""

    def test_basic_creation(self):
        """Create role not assigned error."""
        err = MACIRoleNotAssignedError(agent_id="agent123", operation="validate")
        assert "agent123" in err.message
        assert err.agent_id == "agent123"
        assert err.operation == "validate"


class TestExceptionHierarchy:
    """Tests for exception class hierarchy."""

    def test_constitutional_errors(self):
        """Constitutional errors inherit correctly."""
        assert issubclass(ConstitutionalError, AgentBusError)
        assert issubclass(ConstitutionalHashMismatchError, ConstitutionalError)
        assert issubclass(ConstitutionalValidationError, ConstitutionalError)

    def test_message_errors(self):
        """Message errors inherit correctly."""
        assert issubclass(MessageError, AgentBusError)
        assert issubclass(MessageValidationError, MessageError)
        assert issubclass(MessageDeliveryError, MessageError)
        assert issubclass(MessageTimeoutError, MessageError)
        assert issubclass(MessageRoutingError, MessageError)

    def test_agent_errors(self):
        """Agent errors inherit correctly."""
        assert issubclass(AgentError, AgentBusError)
        assert issubclass(AgentNotRegisteredError, AgentError)
        assert issubclass(AgentAlreadyRegisteredError, AgentError)
        assert issubclass(AgentCapabilityError, AgentError)

    def test_policy_errors(self):
        """Policy errors inherit correctly."""
        assert issubclass(PolicyError, AgentBusError)
        assert issubclass(PolicyEvaluationError, PolicyError)
        assert issubclass(PolicyNotFoundError, PolicyError)
        assert issubclass(OPAConnectionError, PolicyError)
        assert issubclass(OPANotInitializedError, PolicyError)

    def test_deliberation_errors(self):
        """Deliberation errors inherit correctly."""
        assert issubclass(DeliberationError, AgentBusError)
        assert issubclass(DeliberationTimeoutError, DeliberationError)
        assert issubclass(SignatureCollectionError, DeliberationError)
        assert issubclass(ReviewConsensusError, DeliberationError)

    def test_bus_operation_errors(self):
        """Bus operation errors inherit correctly."""
        assert issubclass(BusOperationError, AgentBusError)
        assert issubclass(BusNotStartedError, BusOperationError)
        assert issubclass(BusAlreadyStartedError, BusOperationError)
        assert issubclass(HandlerExecutionError, BusOperationError)

    def test_maci_errors(self):
        """MACI errors inherit correctly."""
        assert issubclass(MACIError, AgentBusError)
        assert issubclass(MACIRoleViolationError, MACIError)
        assert issubclass(MACISelfValidationError, MACIError)
        assert issubclass(MACICrossRoleValidationError, MACIError)
        assert issubclass(MACIRoleNotAssignedError, MACIError)

    def test_configuration_error(self):
        """Configuration error inherits correctly."""
        assert issubclass(ConfigurationError, AgentBusError)
