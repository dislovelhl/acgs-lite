"""Coverage tests for interfaces.py and facades/agent_bus_facade.py.

Constitutional Hash: 608508a9bd224290

Targets:
  - enhanced_agent_bus/interfaces.py (Protocol stub bodies, isinstance checks)
  - enhanced_agent_bus/facades/agent_bus_facade.py (lazy loading, __dir__, __getattr__)
"""

from __future__ import annotations

import importlib
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from enhanced_agent_bus.bus_types import JSONDict, MetadataDict
from enhanced_agent_bus.core_models import AgentMessage
from enhanced_agent_bus.interfaces import (
    AgentRegistry,
    ApprovalsValidatorProtocol,
    CircuitBreakerProtocol,
    ConstitutionalHashValidatorProtocol,
    ConstitutionalVerificationResultProtocol,
    ConstitutionalVerifierProtocol,
    GovernanceDecisionValidatorProtocol,
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
    RecommendationPlannerProtocol,
    RoleMatrixValidatorProtocol,
    RustProcessorProtocol,
    TransportProtocol,
    ValidationResultProtocol,
    ValidationStrategy,
)

# ---------------------------------------------------------------------------
# Helpers: minimal concrete implementations that satisfy each Protocol
# ---------------------------------------------------------------------------


def _make_message() -> AgentMessage:
    return AgentMessage(from_agent="test-sender", to_agent="test-receiver")


class ConcreteAgentRegistry:
    async def register(
        self,
        agent_id: str,
        capabilities: list[str] | None = None,
        metadata: MetadataDict | None = None,
    ) -> bool:
        return True

    async def unregister(self, agent_id: str) -> bool:
        return True

    async def get(self, agent_id: str) -> dict[str, Any] | None:
        return {"agent_id": agent_id}

    async def list_agents(self) -> list[str]:
        return ["agent-1"]

    async def exists(self, agent_id: str) -> bool:
        return True

    async def update_metadata(self, agent_id: str, metadata: MetadataDict) -> bool:
        return True


class ConcreteMessageRouter:
    async def route(self, message: AgentMessage, registry: AgentRegistry) -> str | None:
        return "target-agent"

    async def broadcast(
        self, message: AgentMessage, registry: AgentRegistry, exclude: list[str] | None = None
    ) -> list[str]:
        return ["agent-1", "agent-2"]


class ConcreteValidationStrategy:
    async def validate(self, message: AgentMessage) -> tuple[bool, str | None]:
        return (True, None)


class ConcreteProcessingStrategy:
    async def process(self, message: AgentMessage, handlers: dict[object, list]) -> Any:
        return MagicMock(is_valid=True)

    def is_available(self) -> bool:
        return True

    def get_name(self) -> str:
        return "test-strategy"


class ConcreteMessageHandler:
    async def handle(self, message: AgentMessage) -> AgentMessage | None:
        return None

    def can_handle(self, message: AgentMessage) -> bool:
        return True


class ConcreteMetricsCollector:
    def record_message_processed(
        self, message_type: str, duration_ms: float, success: bool
    ) -> None:
        pass

    def record_agent_registered(self, agent_id: str) -> None:
        pass

    def record_agent_unregistered(self, agent_id: str) -> None:
        pass

    def get_metrics(self) -> JSONDict:
        return {"messages": 0}


class ConcreteMessageProcessor:
    async def process(self, message: AgentMessage) -> Any:
        return MagicMock(is_valid=True)


class ConcreteMACIRegistry:
    def register_agent(self, agent_id: str, role: str) -> bool:
        return True

    def get_role(self, agent_id: str) -> str | None:
        return "executive"

    def unregister_agent(self, agent_id: str) -> bool:
        return True


class ConcreteMACIEnforcer:
    async def validate_action(
        self, agent_id: str, action: str, target_output_id: str | None = None
    ) -> JSONDict:
        return {"valid": True, "violations": []}


class ConcreteTransport:
    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send(self, message: AgentMessage, topic: str | None = None) -> bool:
        return True

    async def subscribe(self, topic: str, handler: Any) -> None:
        pass


class ConcreteOrchestrator:
    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def get_status(self) -> JSONDict:
        return {"status": "healthy", "constitutional_hash": "608508a9bd224290"}


class ConcreteCircuitBreaker:
    async def record_success(self) -> None:
        pass

    async def record_failure(
        self, error: Exception | None = None, error_type: str = "unknown"
    ) -> None:
        pass

    async def can_execute(self) -> bool:
        return True

    async def reset(self) -> None:
        pass


class ConcretePolicyValidationResult:
    @property
    def is_valid(self) -> bool:
        return True

    @property
    def errors(self) -> list[str]:
        return []


class ConcretePolicyClient:
    async def validate_message_signature(self, message: AgentMessage) -> Any:
        return ConcretePolicyValidationResult()


class ConcreteOPAClient:
    async def validate_constitutional(self, message: JSONDict) -> Any:
        return ConcretePolicyValidationResult()


class ConcreteValidationResult:
    @property
    def is_valid(self) -> bool:
        return True

    @property
    def errors(self) -> list[str]:
        return []


class ConcreteRustProcessor:
    def validate(self, message: JSONDict) -> bool | JSONDict:
        return True


class ConcretePQCValidator:
    def verify_governance_decision(
        self, decision: JSONDict, signature: object, public_key: bytes
    ) -> bool:
        return True


class ConcreteConstitutionalVerificationResult:
    @property
    def is_valid(self) -> bool:
        return True

    @property
    def failure_reason(self) -> str | None:
        return None


class ConcreteConstitutionalVerifier:
    async def verify_constitutional_compliance(
        self, action_data: JSONDict, context: JSONDict, session_id: str | None = None
    ) -> Any:
        return ConcreteConstitutionalVerificationResult()


class ConcreteConstitutionalHashValidator:
    async def validate_hash(
        self, *, provided_hash: str, expected_hash: str, context: dict[str, Any] | None = None
    ) -> tuple[bool, str]:
        return (True, "")


class ConcreteGovernanceDecisionValidator:
    async def validate_decision(
        self, *, decision: dict[str, Any], context: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        return (True, [])


class ConcreteApprovalsValidator:
    def validate_approvals(
        self, *, policy: Any, decisions: list[Any], approvers: dict[str, Any], requester_id: str
    ) -> tuple[bool, str]:
        return (True, "approved")


class ConcreteRecommendationPlanner:
    def generate_recommendations(
        self, *, judgment: dict[str, Any], decision: dict[str, Any]
    ) -> list[str]:
        return ["recommendation-1"]


class ConcreteRoleMatrixValidator:
    def validate(self, *, violations: list[str], strict_mode: bool) -> None:
        pass


# A class that conforms to no protocol
class Empty:
    pass


# ============================================================================
# Part 1: interfaces.py - isinstance checks (True path)
# ============================================================================


class TestProtocolIsinstanceTrue:
    """Verify isinstance returns True for conforming implementations."""

    def test_agent_registry_isinstance(self) -> None:
        assert isinstance(ConcreteAgentRegistry(), AgentRegistry)

    def test_message_router_isinstance(self) -> None:
        assert isinstance(ConcreteMessageRouter(), MessageRouter)

    def test_validation_strategy_isinstance(self) -> None:
        assert isinstance(ConcreteValidationStrategy(), ValidationStrategy)

    def test_processing_strategy_isinstance(self) -> None:
        assert isinstance(ConcreteProcessingStrategy(), ProcessingStrategy)

    def test_message_handler_isinstance(self) -> None:
        assert isinstance(ConcreteMessageHandler(), MessageHandler)

    def test_metrics_collector_isinstance(self) -> None:
        assert isinstance(ConcreteMetricsCollector(), MetricsCollector)

    def test_message_processor_isinstance(self) -> None:
        assert isinstance(ConcreteMessageProcessor(), MessageProcessorProtocol)

    def test_maci_registry_isinstance(self) -> None:
        assert isinstance(ConcreteMACIRegistry(), MACIRegistryProtocol)

    def test_maci_enforcer_isinstance(self) -> None:
        assert isinstance(ConcreteMACIEnforcer(), MACIEnforcerProtocol)

    def test_transport_isinstance(self) -> None:
        assert isinstance(ConcreteTransport(), TransportProtocol)

    def test_orchestrator_isinstance(self) -> None:
        assert isinstance(ConcreteOrchestrator(), OrchestratorProtocol)

    def test_circuit_breaker_isinstance(self) -> None:
        assert isinstance(ConcreteCircuitBreaker(), CircuitBreakerProtocol)

    def test_policy_validation_result_isinstance(self) -> None:
        assert isinstance(ConcretePolicyValidationResult(), PolicyValidationResultProtocol)

    def test_policy_client_isinstance(self) -> None:
        assert isinstance(ConcretePolicyClient(), PolicyClientProtocol)

    def test_opa_client_isinstance(self) -> None:
        assert isinstance(ConcreteOPAClient(), OPAClientProtocol)

    def test_validation_result_isinstance(self) -> None:
        assert isinstance(ConcreteValidationResult(), ValidationResultProtocol)

    def test_rust_processor_isinstance(self) -> None:
        assert isinstance(ConcreteRustProcessor(), RustProcessorProtocol)

    def test_pqc_validator_isinstance(self) -> None:
        assert isinstance(ConcretePQCValidator(), PQCValidatorProtocol)

    def test_constitutional_verifier_isinstance(self) -> None:
        assert isinstance(ConcreteConstitutionalVerifier(), ConstitutionalVerifierProtocol)

    def test_constitutional_verification_result_isinstance(self) -> None:
        assert isinstance(
            ConcreteConstitutionalVerificationResult(), ConstitutionalVerificationResultProtocol
        )

    def test_constitutional_hash_validator_isinstance(self) -> None:
        assert isinstance(
            ConcreteConstitutionalHashValidator(), ConstitutionalHashValidatorProtocol
        )

    def test_governance_decision_validator_isinstance(self) -> None:
        assert isinstance(
            ConcreteGovernanceDecisionValidator(), GovernanceDecisionValidatorProtocol
        )

    def test_approvals_validator_isinstance(self) -> None:
        assert isinstance(ConcreteApprovalsValidator(), ApprovalsValidatorProtocol)

    def test_recommendation_planner_isinstance(self) -> None:
        assert isinstance(ConcreteRecommendationPlanner(), RecommendationPlannerProtocol)

    def test_role_matrix_validator_isinstance(self) -> None:
        assert isinstance(ConcreteRoleMatrixValidator(), RoleMatrixValidatorProtocol)


# ============================================================================
# Part 2: interfaces.py - isinstance checks (False path)
# ============================================================================


class TestProtocolIsinstanceFalse:
    """Verify isinstance returns False for non-conforming objects."""

    def test_agent_registry_rejects_empty(self) -> None:
        assert not isinstance(Empty(), AgentRegistry)

    def test_message_router_rejects_empty(self) -> None:
        assert not isinstance(Empty(), MessageRouter)

    def test_validation_strategy_rejects_empty(self) -> None:
        assert not isinstance(Empty(), ValidationStrategy)

    def test_processing_strategy_rejects_empty(self) -> None:
        assert not isinstance(Empty(), ProcessingStrategy)

    def test_message_handler_rejects_empty(self) -> None:
        assert not isinstance(Empty(), MessageHandler)

    def test_metrics_collector_rejects_empty(self) -> None:
        assert not isinstance(Empty(), MetricsCollector)

    def test_message_processor_rejects_empty(self) -> None:
        assert not isinstance(Empty(), MessageProcessorProtocol)

    def test_maci_registry_rejects_empty(self) -> None:
        assert not isinstance(Empty(), MACIRegistryProtocol)

    def test_maci_enforcer_rejects_empty(self) -> None:
        assert not isinstance(Empty(), MACIEnforcerProtocol)

    def test_transport_rejects_empty(self) -> None:
        assert not isinstance(Empty(), TransportProtocol)

    def test_orchestrator_rejects_empty(self) -> None:
        assert not isinstance(Empty(), OrchestratorProtocol)

    def test_circuit_breaker_rejects_empty(self) -> None:
        assert not isinstance(Empty(), CircuitBreakerProtocol)

    def test_policy_client_rejects_empty(self) -> None:
        assert not isinstance(Empty(), PolicyClientProtocol)

    def test_opa_client_rejects_empty(self) -> None:
        assert not isinstance(Empty(), OPAClientProtocol)

    def test_rust_processor_rejects_empty(self) -> None:
        assert not isinstance(Empty(), RustProcessorProtocol)

    def test_pqc_validator_rejects_empty(self) -> None:
        assert not isinstance(Empty(), PQCValidatorProtocol)

    def test_constitutional_verifier_rejects_empty(self) -> None:
        assert not isinstance(Empty(), ConstitutionalVerifierProtocol)

    def test_constitutional_hash_validator_rejects_empty(self) -> None:
        assert not isinstance(Empty(), ConstitutionalHashValidatorProtocol)

    def test_governance_decision_validator_rejects_empty(self) -> None:
        assert not isinstance(Empty(), GovernanceDecisionValidatorProtocol)

    def test_approvals_validator_rejects_empty(self) -> None:
        assert not isinstance(Empty(), ApprovalsValidatorProtocol)

    def test_recommendation_planner_rejects_empty(self) -> None:
        assert not isinstance(Empty(), RecommendationPlannerProtocol)

    def test_role_matrix_validator_rejects_empty(self) -> None:
        assert not isinstance(Empty(), RoleMatrixValidatorProtocol)

    def test_rejects_string(self) -> None:
        assert not isinstance("hello", AgentRegistry)

    def test_rejects_int(self) -> None:
        assert not isinstance(42, MessageRouter)

    def test_rejects_dict(self) -> None:
        assert not isinstance({}, MetricsCollector)


# ============================================================================
# Part 3: interfaces.py - calling protocol method stubs on concrete impls
# ============================================================================


class TestAgentRegistryMethods:
    async def test_register(self) -> None:
        reg = ConcreteAgentRegistry()
        result = await reg.register("agent-1", capabilities=["cap"], metadata={"k": "v"})
        assert result is True

    async def test_register_no_optionals(self) -> None:
        reg = ConcreteAgentRegistry()
        result = await reg.register("agent-1")
        assert result is True

    async def test_unregister(self) -> None:
        reg = ConcreteAgentRegistry()
        assert await reg.unregister("agent-1") is True

    async def test_get(self) -> None:
        reg = ConcreteAgentRegistry()
        info = await reg.get("agent-1")
        assert info is not None
        assert info["agent_id"] == "agent-1"

    async def test_list_agents(self) -> None:
        reg = ConcreteAgentRegistry()
        agents = await reg.list_agents()
        assert "agent-1" in agents

    async def test_exists(self) -> None:
        reg = ConcreteAgentRegistry()
        assert await reg.exists("agent-1") is True

    async def test_update_metadata(self) -> None:
        reg = ConcreteAgentRegistry()
        assert await reg.update_metadata("agent-1", {"key": "val"}) is True


class TestMessageRouterMethods:
    async def test_route(self) -> None:
        router = ConcreteMessageRouter()
        registry = ConcreteAgentRegistry()
        msg = _make_message()
        result = await router.route(msg, registry)
        assert result == "target-agent"

    async def test_broadcast(self) -> None:
        router = ConcreteMessageRouter()
        registry = ConcreteAgentRegistry()
        msg = _make_message()
        targets = await router.broadcast(msg, registry, exclude=["agent-3"])
        assert len(targets) == 2


class TestValidationStrategyMethods:
    async def test_validate_valid(self) -> None:
        strat = ConcreteValidationStrategy()
        is_valid, error = await strat.validate(_make_message())
        assert is_valid is True
        assert error is None


class TestProcessingStrategyMethods:
    async def test_process(self) -> None:
        strat = ConcreteProcessingStrategy()
        result = await strat.process(_make_message(), {})
        assert result.is_valid is True

    def test_is_available(self) -> None:
        strat = ConcreteProcessingStrategy()
        assert strat.is_available() is True

    def test_get_name(self) -> None:
        strat = ConcreteProcessingStrategy()
        assert strat.get_name() == "test-strategy"


class TestMessageHandlerMethods:
    async def test_handle(self) -> None:
        handler = ConcreteMessageHandler()
        result = await handler.handle(_make_message())
        assert result is None

    def test_can_handle(self) -> None:
        handler = ConcreteMessageHandler()
        assert handler.can_handle(_make_message()) is True


class TestMetricsCollectorMethods:
    def test_record_message_processed(self) -> None:
        mc = ConcreteMetricsCollector()
        mc.record_message_processed("command", 1.5, True)

    def test_record_agent_registered(self) -> None:
        mc = ConcreteMetricsCollector()
        mc.record_agent_registered("agent-1")

    def test_record_agent_unregistered(self) -> None:
        mc = ConcreteMetricsCollector()
        mc.record_agent_unregistered("agent-1")

    def test_get_metrics(self) -> None:
        mc = ConcreteMetricsCollector()
        metrics = mc.get_metrics()
        assert "messages" in metrics


class TestMessageProcessorMethods:
    async def test_process(self) -> None:
        proc = ConcreteMessageProcessor()
        result = await proc.process(_make_message())
        assert result.is_valid is True


class TestMACIRegistryMethods:
    def test_register_agent(self) -> None:
        reg = ConcreteMACIRegistry()
        assert reg.register_agent("agent-1", "executive") is True

    def test_get_role(self) -> None:
        reg = ConcreteMACIRegistry()
        assert reg.get_role("agent-1") == "executive"

    def test_unregister_agent(self) -> None:
        reg = ConcreteMACIRegistry()
        assert reg.unregister_agent("agent-1") is True


class TestMACIEnforcerMethods:
    async def test_validate_action(self) -> None:
        enforcer = ConcreteMACIEnforcer()
        result = await enforcer.validate_action("agent-1", "propose", target_output_id="out-1")
        assert result["valid"] is True

    async def test_validate_action_no_target(self) -> None:
        enforcer = ConcreteMACIEnforcer()
        result = await enforcer.validate_action("agent-1", "propose")
        assert "violations" in result


class TestTransportMethods:
    async def test_start_stop(self) -> None:
        transport = ConcreteTransport()
        await transport.start()
        await transport.stop()

    async def test_send(self) -> None:
        transport = ConcreteTransport()
        assert await transport.send(_make_message(), topic="test-topic") is True

    async def test_send_no_topic(self) -> None:
        transport = ConcreteTransport()
        assert await transport.send(_make_message()) is True

    async def test_subscribe(self) -> None:
        transport = ConcreteTransport()
        await transport.subscribe("topic", lambda msg: None)


class TestOrchestratorMethods:
    async def test_start_stop(self) -> None:
        orch = ConcreteOrchestrator()
        await orch.start()
        await orch.stop()

    def test_get_status(self) -> None:
        orch = ConcreteOrchestrator()
        status = orch.get_status()
        assert status["status"] == "healthy"
        assert "constitutional_hash" in status


class TestCircuitBreakerMethods:
    async def test_record_success(self) -> None:
        cb = ConcreteCircuitBreaker()
        await cb.record_success()

    async def test_record_failure(self) -> None:
        cb = ConcreteCircuitBreaker()
        await cb.record_failure(error=ValueError("boom"), error_type="value_error")

    async def test_record_failure_defaults(self) -> None:
        cb = ConcreteCircuitBreaker()
        await cb.record_failure()

    async def test_can_execute(self) -> None:
        cb = ConcreteCircuitBreaker()
        assert await cb.can_execute() is True

    async def test_reset(self) -> None:
        cb = ConcreteCircuitBreaker()
        await cb.reset()


class TestPolicyValidationResultMethods:
    def test_is_valid(self) -> None:
        r = ConcretePolicyValidationResult()
        assert r.is_valid is True

    def test_errors(self) -> None:
        r = ConcretePolicyValidationResult()
        assert r.errors == []


class TestPolicyClientMethods:
    async def test_validate_message_signature(self) -> None:
        client = ConcretePolicyClient()
        result = await client.validate_message_signature(_make_message())
        assert result.is_valid is True


class TestOPAClientMethods:
    async def test_validate_constitutional(self) -> None:
        client = ConcreteOPAClient()
        result = await client.validate_constitutional({"key": "value"})
        assert result.is_valid is True


class TestValidationResultMethods:
    def test_is_valid_and_errors(self) -> None:
        r = ConcreteValidationResult()
        assert r.is_valid is True
        assert r.errors == []


class TestRustProcessorMethods:
    def test_validate_returns_bool(self) -> None:
        proc = ConcreteRustProcessor()
        assert proc.validate({"msg": "data"}) is True


class TestPQCValidatorMethods:
    def test_verify_governance_decision(self) -> None:
        v = ConcretePQCValidator()
        assert v.verify_governance_decision({"d": 1}, object(), b"key") is True


class TestConstitutionalVerifierMethods:
    async def test_verify_compliance(self) -> None:
        v = ConcreteConstitutionalVerifier()
        result = await v.verify_constitutional_compliance({"action": "x"}, {"ctx": "y"})
        assert result.is_valid is True
        assert result.failure_reason is None

    async def test_verify_compliance_with_session(self) -> None:
        v = ConcreteConstitutionalVerifier()
        result = await v.verify_constitutional_compliance(
            {"action": "x"}, {"ctx": "y"}, session_id="sess-1"
        )
        assert result.is_valid is True


class TestConstitutionalHashValidatorMethods:
    async def test_validate_hash(self) -> None:
        v = ConcreteConstitutionalHashValidator()
        is_valid, err = await v.validate_hash(
            provided_hash="608508a9bd224290",
            expected_hash="608508a9bd224290",
            context={"source": "test"},
        )
        assert is_valid is True
        assert err == ""

    async def test_validate_hash_no_context(self) -> None:
        v = ConcreteConstitutionalHashValidator()
        is_valid, _ = await v.validate_hash(provided_hash="abc", expected_hash="abc")
        assert is_valid is True


class TestGovernanceDecisionValidatorMethods:
    async def test_validate_decision(self) -> None:
        v = ConcreteGovernanceDecisionValidator()
        is_valid, errors = await v.validate_decision(
            decision={"action": "approve"}, context={"role": "admin"}
        )
        assert is_valid is True
        assert errors == []


class TestApprovalsValidatorMethods:
    def test_validate_approvals(self) -> None:
        v = ConcreteApprovalsValidator()
        is_valid, reason = v.validate_approvals(
            policy={"min_approvals": 1},
            decisions=[{"approved": True}],
            approvers={"user-1": "admin"},
            requester_id="user-2",
        )
        assert is_valid is True
        assert reason == "approved"


class TestRecommendationPlannerMethods:
    def test_generate_recommendations(self) -> None:
        p = ConcreteRecommendationPlanner()
        recs = p.generate_recommendations(judgment={"result": "fail"}, decision={"action": "retry"})
        assert len(recs) == 1


class TestRoleMatrixValidatorMethods:
    def test_validate_no_violations(self) -> None:
        v = ConcreteRoleMatrixValidator()
        v.validate(violations=[], strict_mode=True)

    def test_validate_with_violations(self) -> None:
        v = ConcreteRoleMatrixValidator()
        v.validate(violations=["self-validation"], strict_mode=False)


# ============================================================================
# Part 4: interfaces.py - __all__ and module-level attributes
# ============================================================================


class TestInterfacesModuleAttributes:
    def test_all_exports_defined(self) -> None:
        from enhanced_agent_bus import interfaces

        for name in interfaces.__all__:
            assert hasattr(interfaces, name), f"{name} in __all__ but not defined"

    def test_runtime_checkable_protocols(self) -> None:
        """All Protocol classes should be @runtime_checkable."""
        import inspect

        from enhanced_agent_bus import interfaces

        for name in interfaces.__all__:
            obj = getattr(interfaces, name, None)
            if obj is None:
                continue
            if inspect.isclass(obj) and issubclass(obj, type) is False:
                # runtime_checkable protocols support isinstance
                try:
                    isinstance(Empty(), obj)
                except TypeError:
                    pytest.fail(f"{name} is not @runtime_checkable")

    def test_constitutional_hash_in_docstring(self) -> None:
        from enhanced_agent_bus import interfaces

        assert "608508a9bd224290" in (interfaces.__doc__ or "")


# ============================================================================
# Part 5: facades/agent_bus_facade.py
# ============================================================================


class TestFacadeConstitutionalHash:
    def test_constitutional_hash_is_string(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        assert isinstance(agent_bus_facade.CONSTITUTIONAL_HASH, str)

    def test_constitutional_hash_value(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        # Either the real hash or standalone fallback
        assert agent_bus_facade.CONSTITUTIONAL_HASH in ("608508a9bd224290", "standalone")

    def test_constitutional_hash_in_all(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        assert "CONSTITUTIONAL_HASH" in agent_bus_facade.__all__


class TestFacadeDir:
    def test_dir_contains_all_symbols(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        d = dir(agent_bus_facade)
        for name in agent_bus_facade._SYMBOL_SOURCES:
            assert name in d, f"{name} missing from dir()"

    def test_dir_contains_constitutional_hash(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        assert "CONSTITUTIONAL_HASH" in dir(agent_bus_facade)

    def test_dir_returns_sorted_list(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        d = dir(agent_bus_facade)
        assert d == sorted(d)

    def test_dir_includes_globals(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        d = dir(agent_bus_facade)
        # Standard module globals should be present
        assert "__name__" in d
        assert "__all__" in d


class TestFacadeGetattr:
    def test_unknown_attribute_raises(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        with pytest.raises(AttributeError, match="has no attribute"):
            agent_bus_facade.__getattr__("nonexistent_symbol_xyz")

    def test_error_message_includes_module_name(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        with pytest.raises(AttributeError, match=r"module .* has no attribute"):
            agent_bus_facade.__getattr__("bogus_name")

    def test_lazy_load_message_type(self) -> None:
        facade = importlib.import_module("enhanced_agent_bus.facades.agent_bus_facade")
        # Ensure MessageType is accessible (lazy import)
        mt = facade.MessageType
        assert mt is not None
        # Verify it was cached into globals
        assert "MessageType" in facade.__dict__

    def test_lazy_load_decision_log(self) -> None:
        facade = importlib.import_module("enhanced_agent_bus.facades.agent_bus_facade")
        dl = facade.DecisionLog
        assert dl is not None
        assert "DecisionLog" in facade.__dict__

    def test_lazy_load_validation_result(self) -> None:
        facade = importlib.import_module("enhanced_agent_bus.facades.agent_bus_facade")
        vr = facade.ValidationResult
        assert vr is not None
        assert "ValidationResult" in facade.__dict__

    def test_lazy_load_caches_on_second_access(self) -> None:
        facade = importlib.import_module("enhanced_agent_bus.facades.agent_bus_facade")
        first = facade.MessageType
        second = facade.MessageType
        assert first is second


class TestFacadeSymbolSources:
    def test_symbol_sources_is_dict(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        assert isinstance(agent_bus_facade._SYMBOL_SOURCES, dict)

    def test_all_symbol_sources_are_tuples(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        for name, source in agent_bus_facade._SYMBOL_SOURCES.items():
            assert isinstance(source, tuple), f"{name} source is not a tuple"
            assert len(source) == 2, f"{name} source tuple wrong length"

    def test_all_entries_have_string_module_and_symbol(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        for name, (mod, sym) in agent_bus_facade._SYMBOL_SOURCES.items():
            assert isinstance(mod, str), f"{name}: module_name is not str"
            assert isinstance(sym, str), f"{name}: symbol_name is not str"

    def test_all_exports_in_all(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        for name in agent_bus_facade._SYMBOL_SOURCES:
            assert name in agent_bus_facade.__all__, f"{name} in _SYMBOL_SOURCES but not __all__"


class TestFacadeAllExports:
    def test_all_is_list(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        assert isinstance(agent_bus_facade.__all__, list)

    def test_all_entries_are_strings(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        for name in agent_bus_facade.__all__:
            assert isinstance(name, str)

    def test_all_entries_are_accessible(self) -> None:
        """Every name in __all__ should be importable via getattr."""
        from enhanced_agent_bus.facades import agent_bus_facade

        for name in agent_bus_facade.__all__:
            val = getattr(agent_bus_facade, name, "MISSING")
            assert val != "MISSING", f"{name} in __all__ but not accessible"


class TestFacadeLazyImportIntegration:
    def test_session_context_accessible(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        sc = agent_bus_facade.SessionContext
        assert sc is not None

    def test_session_context_manager_accessible(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        scm = agent_bus_facade.SessionContextManager
        assert scm is not None

    def test_explanation_service_accessible(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        es = agent_bus_facade.ExplanationService
        assert es is not None

    def test_message_processor_accessible(self) -> None:
        from enhanced_agent_bus.facades import agent_bus_facade

        mp = agent_bus_facade.MessageProcessor
        assert mp is not None
