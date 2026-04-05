from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus import interfaces as ifaces
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus.core_models import AgentMessage
from enhanced_agent_bus.interfaces import (
    AgentRegistry,
    CircuitBreakerProtocol,
    ConstitutionalVerificationResultProtocol,
    ConstitutionalVerifierProtocol,
    MACIEnforcerProtocol,
    MACIRegistryProtocol,
    MessageHandler,
    MessageProcessorProtocol,
    MessageRouter,
    MetricsCollector,
    OPAClientProtocol,
    OrchestratorProtocol,
    PolicyClientProtocol,
    PolicyValidationResultProtocol,
    PQCValidatorProtocol,
    ProcessingStrategy,
    RustProcessorProtocol,
    TransportProtocol,
    ValidationResultProtocol,
    ValidationStrategy,
)
from enhanced_agent_bus.validators import ValidationResult


class ConcreteAgentRegistry:
    """Minimal concrete implementation satisfying AgentRegistry."""

    def __init__(self):
        self._agents = {}

    async def register(self, agent_id, capabilities=None, metadata=None):
        if agent_id in self._agents:
            return False
        self._agents[agent_id] = {"capabilities": capabilities or [], "metadata": metadata or {}}
        return True

    async def unregister(self, agent_id):
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        return True

    async def get(self, agent_id):
        return self._agents.get(agent_id)

    async def list_agents(self):
        return list(self._agents.keys())

    async def exists(self, agent_id):
        return agent_id in self._agents

    async def update_metadata(self, agent_id, metadata):
        if agent_id not in self._agents:
            return False
        self._agents[agent_id]["metadata"].update(metadata)
        return True


class ConcreteMessageRouter:
    """Minimal concrete implementation satisfying MessageRouter."""

    async def route(self, message, registry):
        return message.to_agent or None

    async def broadcast(self, message, registry, exclude=None):
        agents = await registry.list_agents()
        if exclude:
            agents = [a for a in agents if a not in exclude]
        return agents


class ConcreteValidationStrategy:
    """Minimal concrete implementation satisfying ValidationStrategy."""

    async def validate(self, message):
        if not message.from_agent:
            return (False, "from_agent is required")
        return (True, None)


class ConcreteProcessingStrategy:
    """Minimal concrete implementation satisfying ProcessingStrategy."""

    async def process(self, message, handlers):
        return ValidationResult(is_valid=True)

    def is_available(self):
        return True

    def get_name(self):
        return "ConcreteProcessingStrategy"


class ConcreteMessageHandler:
    """Minimal concrete implementation satisfying MessageHandler."""

    async def handle(self, message):
        return None

    def can_handle(self, message):
        return True


class ConcreteMetricsCollector:
    """Minimal concrete implementation satisfying MetricsCollector."""

    def __init__(self):
        self._data = {}

    def record_message_processed(self, message_type, duration_ms, success):
        self._data[message_type] = {"duration_ms": duration_ms, "success": success}

    def record_agent_registered(self, agent_id):
        self._data[f"registered:{agent_id}"] = True

    def record_agent_unregistered(self, agent_id):
        self._data[f"unregistered:{agent_id}"] = True

    def get_metrics(self):
        return dict(self._data)


class ConcreteMessageProcessorProtocol:
    """Minimal concrete implementation satisfying MessageProcessorProtocol."""

    async def process(self, message):
        return ValidationResult(is_valid=True)


class ConcreteMACIRegistry:
    """Minimal concrete implementation satisfying MACIRegistryProtocol."""

    def __init__(self):
        self._roles = {}

    def register_agent(self, agent_id, role):
        self._roles[agent_id] = role
        return True

    def get_role(self, agent_id):
        return self._roles.get(agent_id)

    def unregister_agent(self, agent_id):
        if agent_id not in self._roles:
            return False
        del self._roles[agent_id]
        return True


class ConcreteMACIEnforcer:
    """Minimal concrete implementation satisfying MACIEnforcerProtocol."""

    async def validate_action(self, agent_id, action, target_output_id=None):
        return {"allowed": True, "agent_id": agent_id, "action": action}


class ConcreteTransport:
    """Minimal concrete implementation satisfying TransportProtocol."""

    def __init__(self):
        self._running = False
        self._subscriptions = {}

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    async def send(self, message, topic=None):
        return True

    async def subscribe(self, topic, handler):
        self._subscriptions[topic] = handler


class ConcreteOrchestrator:
    """Minimal concrete implementation satisfying OrchestratorProtocol."""

    def __init__(self):
        self._running = False

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    def get_status(self):
        return {
            "status": "running" if self._running else "stopped",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


class ConcreteCircuitBreaker:
    """Minimal concrete implementation satisfying CircuitBreakerProtocol."""

    def __init__(self):
        self._failures = 0
        self._open = False

    async def record_success(self):
        self._failures = 0
        self._open = False

    async def record_failure(self, error=None, error_type="unknown"):
        self._failures += 1
        if self._failures >= 3:
            self._open = True

    async def can_execute(self):
        return not self._open

    async def reset(self):
        self._failures = 0
        self._open = False


class ConcretePolicyValidationResult:
    """Minimal concrete implementation satisfying PolicyValidationResultProtocol."""

    def __init__(self, is_valid, errors=None):
        self._is_valid = is_valid
        self._errors = errors or []

    @property
    def is_valid(self):
        return self._is_valid

    @property
    def errors(self):
        return self._errors


class ConcretePolicyClient:
    """Minimal concrete implementation satisfying PolicyClientProtocol."""

    async def validate_message_signature(self, message):
        return ConcretePolicyValidationResult(is_valid=True)


class ConcreteOPAClient:
    """Minimal concrete implementation satisfying OPAClientProtocol."""

    async def validate_constitutional(self, message):
        return ConcreteValidationResult(is_valid=True)


class ConcreteValidationResult:
    """Minimal concrete implementation satisfying ValidationResultProtocol."""

    def __init__(self, is_valid, errors=None):
        self._is_valid = is_valid
        self._errors = errors or []

    @property
    def is_valid(self):
        return self._is_valid

    @property
    def errors(self):
        return self._errors


class ConcreteRustProcessor:
    """Minimal concrete implementation satisfying RustProcessorProtocol."""

    def validate(self, message):
        return True


class ConcreteRustProcessorDict:
    """Rust processor returning a dict."""

    def validate(self, message):
        return {"is_valid": True, "errors": []}


class ConcretePQCValidator:
    """Minimal concrete implementation satisfying PQCValidatorProtocol."""

    def verify_governance_decision(self, decision, signature, public_key):
        return True


class ConcreteConstitutionalVerificationResult:
    """Minimal concrete implementation satisfying ConstitutionalVerificationResultProtocol."""

    def __init__(self, is_valid, failure_reason=None):
        self._is_valid = is_valid
        self._failure_reason = failure_reason

    @property
    def is_valid(self):
        return self._is_valid

    @property
    def failure_reason(self):
        return self._failure_reason


class ConcreteConstitutionalVerifier:
    """Minimal concrete implementation satisfying ConstitutionalVerifierProtocol."""

    async def verify_constitutional_compliance(self, action_data, context, session_id=None):
        return ConcreteConstitutionalVerificationResult(is_valid=True)


class ConcreteAgentRegistry:
    """Minimal concrete implementation satisfying AgentRegistry."""

    def __init__(self):
        self._agents = {}

    async def register(self, agent_id, capabilities=None, metadata=None):
        if agent_id in self._agents:
            return False
        self._agents[agent_id] = {"capabilities": capabilities or [], "metadata": metadata or {}}
        return True

    async def unregister(self, agent_id):
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        return True

    async def get(self, agent_id):
        return self._agents.get(agent_id)

    async def list_agents(self):
        return list(self._agents.keys())

    async def exists(self, agent_id):
        return agent_id in self._agents

    async def update_metadata(self, agent_id, metadata):
        if agent_id not in self._agents:
            return False
        self._agents[agent_id]["metadata"].update(metadata)
        return True


class ConcreteMessageRouter:
    """Minimal concrete implementation satisfying MessageRouter."""

    async def route(self, message, registry):
        return message.to_agent or None

    async def broadcast(self, message, registry, exclude=None):
        agents = await registry.list_agents()
        if exclude:
            agents = [a for a in agents if a not in exclude]
        return agents


class ConcreteValidationStrategy:
    """Minimal concrete implementation satisfying ValidationStrategy."""

    async def validate(self, message):
        if not message.from_agent:
            return (False, "from_agent is required")
        return (True, None)


class ConcreteProcessingStrategy:
    """Minimal concrete implementation satisfying ProcessingStrategy."""

    async def process(self, message, handlers):
        return ValidationResult(is_valid=True)

    def is_available(self):
        return True

    def get_name(self):
        return "ConcreteProcessingStrategy"


class ConcreteMessageHandler:
    """Minimal concrete implementation satisfying MessageHandler."""

    async def handle(self, message):
        return None

    def can_handle(self, message):
        return True


class ConcreteMetricsCollector:
    """Minimal concrete implementation satisfying MetricsCollector."""

    def __init__(self):
        self._data = {}

    def record_message_processed(self, message_type, duration_ms, success):
        self._data[message_type] = {"duration_ms": duration_ms, "success": success}

    def record_agent_registered(self, agent_id):
        self._data[f"registered:{agent_id}"] = True

    def record_agent_unregistered(self, agent_id):
        self._data[f"unregistered:{agent_id}"] = True

    def get_metrics(self):
        return dict(self._data)


class ConcreteMessageProcessorProtocol:
    """Minimal concrete implementation satisfying MessageProcessorProtocol."""

    async def process(self, message):
        return ValidationResult(is_valid=True)


class ConcreteMACIRegistry:
    """Minimal concrete implementation satisfying MACIRegistryProtocol."""

    def __init__(self):
        self._roles = {}

    def register_agent(self, agent_id, role):
        self._roles[agent_id] = role
        return True

    def get_role(self, agent_id):
        return self._roles.get(agent_id)

    def unregister_agent(self, agent_id):
        if agent_id not in self._roles:
            return False
        del self._roles[agent_id]
        return True


class ConcreteMACIEnforcer:
    """Minimal concrete implementation satisfying MACIEnforcerProtocol."""

    async def validate_action(self, agent_id, action, target_output_id=None):
        return {"allowed": True, "agent_id": agent_id, "action": action}


class ConcreteTransport:
    """Minimal concrete implementation satisfying TransportProtocol."""

    def __init__(self):
        self._running = False
        self._subscriptions = {}

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    async def send(self, message, topic=None):
        return True

    async def subscribe(self, topic, handler):
        self._subscriptions[topic] = handler


class ConcreteOrchestrator:
    """Minimal concrete implementation satisfying OrchestratorProtocol."""

    def __init__(self):
        self._running = False

    async def start(self):
        self._running = True

    async def stop(self):
        self._running = False

    def get_status(self):
        return {
            "status": "running" if self._running else "stopped",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }


class ConcreteCircuitBreaker:
    """Minimal concrete implementation satisfying CircuitBreakerProtocol."""

    def __init__(self):
        self._failures = 0
        self._open = False

    async def record_success(self):
        self._failures = 0
        self._open = False

    async def record_failure(self, error=None, error_type="unknown"):
        self._failures += 1
        if self._failures >= 3:
            self._open = True

    async def can_execute(self):
        return not self._open

    async def reset(self):
        self._failures = 0
        self._open = False


class ConcretePolicyValidationResult:
    """Minimal concrete implementation satisfying PolicyValidationResultProtocol."""

    def __init__(self, is_valid, errors=None):
        self._is_valid = is_valid
        self._errors = errors or []

    @property
    def is_valid(self):
        return self._is_valid

    @property
    def errors(self):
        return self._errors


class ConcretePolicyClient:
    """Minimal concrete implementation satisfying PolicyClientProtocol."""

    async def validate_message_signature(self, message):
        return ConcretePolicyValidationResult(is_valid=True)


class ConcreteOPAClient:
    """Minimal concrete implementation satisfying OPAClientProtocol."""

    async def validate_constitutional(self, message):
        return ConcreteValidationResult(is_valid=True)


class ConcreteValidationResult:
    """Minimal concrete implementation satisfying ValidationResultProtocol."""

    def __init__(self, is_valid, errors=None):
        self._is_valid = is_valid
        self._errors = errors or []

    @property
    def is_valid(self):
        return self._is_valid

    @property
    def errors(self):
        return self._errors


class ConcreteRustProcessor:
    """Minimal concrete implementation satisfying RustProcessorProtocol."""

    def validate(self, message):
        return True


class ConcreteRustProcessorDict:
    """Rust processor returning a dict."""

    def validate(self, message):
        return {"is_valid": True, "errors": []}


class ConcretePQCValidator:
    """Minimal concrete implementation satisfying PQCValidatorProtocol."""

    def verify_governance_decision(self, decision, signature, public_key):
        return True


class ConcreteConstitutionalVerificationResult:
    """Minimal concrete implementation satisfying ConstitutionalVerificationResultProtocol."""

    def __init__(self, is_valid, failure_reason=None):
        self._is_valid = is_valid
        self._failure_reason = failure_reason

    @property
    def is_valid(self):
        return self._is_valid

    @property
    def failure_reason(self):
        return self._failure_reason


class ConcreteConstitutionalVerifier:
    """Minimal concrete implementation satisfying ConstitutionalVerifierProtocol."""

    async def verify_constitutional_compliance(self, action_data, context, session_id=None):
        return ConcreteConstitutionalVerificationResult(is_valid=True)


@pytest.fixture
def agent_message():
    """Return a basic AgentMessage for testing."""
    return AgentMessage(
        content={"key": "value"},
        from_agent="agent-a",
        to_agent="agent-b",
    )


@pytest.fixture
def registry():
    return ConcreteAgentRegistry()


class TestAgentRegistryProtocol:
    """Tests for AgentRegistry Protocol definition."""

    def test_protocol_is_not_none(self):
        assert AgentRegistry is not None

    def test_protocol_is_runtime_checkable(self):
        # Protocol with @runtime_checkable allows isinstance checks
        reg = ConcreteAgentRegistry()
        assert isinstance(reg, AgentRegistry)

    def test_has_register_method(self):
        assert hasattr(AgentRegistry, "register")

    def test_has_unregister_method(self):
        assert hasattr(AgentRegistry, "unregister")

    def test_has_get_method(self):
        assert hasattr(AgentRegistry, "get")

    def test_has_list_agents_method(self):
        assert hasattr(AgentRegistry, "list_agents")

    def test_has_exists_method(self):
        assert hasattr(AgentRegistry, "exists")

    def test_has_update_metadata_method(self):
        assert hasattr(AgentRegistry, "update_metadata")

    def test_non_conforming_object_fails_isinstance(self):
        class Incomplete:
            pass

        obj = Incomplete()
        assert not isinstance(obj, AgentRegistry)


class TestConcreteAgentRegistry:
    """Tests exercising concrete AgentRegistry implementation logic."""

    async def test_register_new_agent_returns_true(self, registry):
        result = await registry.register("agent-1", capabilities=["read"])
        assert result is True

    async def test_register_duplicate_returns_false(self, registry):
        await registry.register("agent-1")
        result = await registry.register("agent-1")
        assert result is False

    async def test_unregister_existing_agent(self, registry):
        await registry.register("agent-1")
        result = await registry.unregister("agent-1")
        assert result is True

    async def test_unregister_missing_agent_returns_false(self, registry):
        result = await registry.unregister("non-existent")
        assert result is False

    async def test_get_existing_agent(self, registry):
        await registry.register("agent-1", metadata={"tier": "low"})
        info = await registry.get("agent-1")
        assert info is not None
        assert info["metadata"]["tier"] == "low"

    async def test_get_missing_agent_returns_none(self, registry):
        info = await registry.get("unknown")
        assert info is None

    async def test_list_agents_empty(self, registry):
        agents = await registry.list_agents()
        assert agents == []

    async def test_list_agents_populated(self, registry):
        await registry.register("agent-1")
        await registry.register("agent-2")
        agents = await registry.list_agents()
        assert "agent-1" in agents
        assert "agent-2" in agents

    async def test_exists_true(self, registry):
        await registry.register("agent-x")
        assert await registry.exists("agent-x") is True

    async def test_exists_false(self, registry):
        assert await registry.exists("agent-x") is False

    async def test_update_metadata_success(self, registry):
        await registry.register("agent-1")
        result = await registry.update_metadata("agent-1", {"version": "2"})
        assert result is True
        info = await registry.get("agent-1")
        assert info["metadata"]["version"] == "2"

    async def test_update_metadata_missing_agent(self, registry):
        result = await registry.update_metadata("ghost", {"k": "v"})
        assert result is False

    async def test_register_with_no_optional_args(self, registry):
        result = await registry.register("bare-agent")
        assert result is True
        assert await registry.exists("bare-agent") is True


# ===========================================================================
# Tests for MessageRouter Protocol
# ===========================================================================
