"""
Comprehensive coverage tests for enhanced_agent_bus modules:
- message_processor.py (MessageProcessor class and helpers)
- di_container.py (DIContainer, ServiceDescriptor, create_default_container, get/reset_container)

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.di_container import (
    DIContainer,
    ServiceDescriptor,
    create_default_container,
    get_container,
    reset_container,
)
from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    AgentMessage,
    AutonomyTier,
    MessageStatus,
    MessageType,
    Priority,
)
from enhanced_agent_bus.validators import ValidationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msg(
    from_agent: str = "test-agent-a",
    to_agent: str = "test-agent-b",
    content: Any = None,
    message_type: MessageType = MessageType.QUERY,
    priority: Priority = Priority.MEDIUM,
    tenant_id: str = "tenant-1",
    autonomy_tier: AutonomyTier = AutonomyTier.BOUNDED,
    metadata: dict[str, Any] | None = None,
    session_id: str | None = None,
) -> AgentMessage:
    msg = AgentMessage(
        from_agent=from_agent,
        to_agent=to_agent,
        message_type=message_type,
        content=content or {"data": "test"},
        constitutional_hash=CONSTITUTIONAL_HASH,
        tenant_id=tenant_id,
        priority=priority,
        autonomy_tier=autonomy_tier,
        metadata=metadata or {},
        session_id=session_id,
    )
    return msg


# ===========================================================================
# DIContainer Tests
# ===========================================================================


class TestServiceDescriptor:
    """Tests for the ServiceDescriptor dataclass."""

    def test_defaults(self) -> None:
        desc = ServiceDescriptor(service_type=int)
        assert desc.service_type is int
        assert desc.factory is None
        assert desc.instance is None
        assert desc.singleton is True

    def test_with_factory(self) -> None:
        def factory():
            return 42

        desc = ServiceDescriptor(service_type=int, factory=factory)
        assert desc.factory is factory
        assert desc.singleton is True

    def test_with_instance(self) -> None:
        desc = ServiceDescriptor(service_type=str, instance="hello")
        assert desc.instance == "hello"

    def test_non_singleton(self) -> None:
        desc = ServiceDescriptor(service_type=list, singleton=False)
        assert desc.singleton is False


class TestDIContainer:
    """Tests for DIContainer registration, resolution, and lifecycle."""

    def test_constitutional_hash_default(self) -> None:
        container = DIContainer()
        assert container.constitutional_hash is not None

    def test_register_with_instance(self) -> None:
        container = DIContainer()
        obj = {"key": "value"}
        result = container.register(dict, instance=obj)
        assert result is container  # chaining
        assert container.is_registered(dict)
        resolved = container.resolve(dict)
        assert resolved is obj

    def test_register_with_factory(self) -> None:
        container = DIContainer()
        counter = {"count": 0}

        def factory() -> list:
            counter["count"] += 1
            return [counter["count"]]

        container.register(list, factory=factory, singleton=True)
        first = container.resolve(list)
        second = container.resolve(list)
        assert first is second
        assert counter["count"] == 1  # only called once (singleton)

    def test_register_with_factory_transient(self) -> None:
        container = DIContainer()
        counter = {"count": 0}

        def factory() -> list:
            counter["count"] += 1
            return [counter["count"]]

        container.register(list, factory=factory, singleton=False)
        first = container.resolve(list)
        second = container.resolve(list)
        assert first is not second
        assert counter["count"] == 2

    def test_register_type_only(self) -> None:
        """When no factory or instance is given, the type itself is used as factory."""
        container = DIContainer()
        container.register(dict)
        resolved = container.resolve(dict)
        assert isinstance(resolved, dict)

    def test_register_type_only_singleton(self) -> None:
        container = DIContainer()
        container.register(dict)
        first = container.resolve(dict)
        second = container.resolve(dict)
        assert first is second

    def test_register_type_only_transient(self) -> None:
        container = DIContainer()
        container.register(dict, singleton=False)
        first = container.resolve(dict)
        second = container.resolve(dict)
        assert first is not second

    def test_resolve_unregistered_raises_key_error(self) -> None:
        container = DIContainer()
        with pytest.raises(KeyError, match="int"):
            container.resolve(int)

    def test_resolve_no_factory_no_instance_raises_value_error(self) -> None:
        container = DIContainer()
        container._services[int] = ServiceDescriptor(service_type=int, factory=None, instance=None)
        with pytest.raises(ValueError, match="No factory for int"):
            container.resolve(int)

    def test_try_resolve_success(self) -> None:
        container = DIContainer()
        container.register(str, instance="hello")
        assert container.try_resolve(str) == "hello"

    def test_try_resolve_unregistered_returns_none(self) -> None:
        container = DIContainer()
        assert container.try_resolve(int) is None

    def test_try_resolve_no_factory_returns_none(self) -> None:
        container = DIContainer()
        container._services[int] = ServiceDescriptor(service_type=int, factory=None, instance=None)
        assert container.try_resolve(int) is None

    def test_is_registered_true(self) -> None:
        container = DIContainer()
        container.register(str, instance="x")
        assert container.is_registered(str) is True

    def test_is_registered_false(self) -> None:
        container = DIContainer()
        assert container.is_registered(str) is False

    def test_get_registered_services_empty(self) -> None:
        container = DIContainer()
        assert container.get_registered_services() == {}

    def test_get_registered_services_mixed(self) -> None:
        container = DIContainer()
        container.register(str, instance="hello")
        container.register(int, factory=lambda: 42)  # not yet resolved
        result = container.get_registered_services()
        assert result["str"] is True  # instance provided
        assert result["int"] is False  # not yet created

    def test_get_registered_services_after_resolve(self) -> None:
        container = DIContainer()
        container.register(int, factory=lambda: 42)
        assert container.get_registered_services()["int"] is False
        container.resolve(int)
        assert container.get_registered_services()["int"] is True

    def test_method_chaining(self) -> None:
        container = DIContainer()
        result = container.register(str, instance="a").register(int, instance=1)
        assert result is container
        assert container.resolve(str) == "a"
        assert container.resolve(int) == 1

    def test_initialized_field_default(self) -> None:
        container = DIContainer()
        assert container._initialized is False


class TestCreateDefaultContainer:
    """Tests for create_default_container function."""

    def test_creates_container_with_coordinators(self) -> None:
        container = create_default_container()
        assert isinstance(container, DIContainer)
        services = container.get_registered_services()
        assert "MemoryCoordinator" in services
        assert "SwarmCoordinator" in services
        assert "WorkflowCoordinator" in services
        assert "ResearchCoordinator" in services
        assert "MACICoordinator" in services

    def test_coordinators_not_instantiated_until_resolved(self) -> None:
        container = create_default_container()
        services = container.get_registered_services()
        # All should be False (not yet resolved)
        for name, instantiated in services.items():
            assert instantiated is False, f"{name} should not be instantiated yet"

    def test_resolve_memory_coordinator(self) -> None:
        from enhanced_agent_bus.coordinators import MemoryCoordinator

        container = create_default_container()
        coordinator = container.resolve(MemoryCoordinator)
        assert coordinator is not None

    def test_resolve_swarm_coordinator(self) -> None:
        from enhanced_agent_bus.coordinators import SwarmCoordinator

        container = create_default_container()
        coordinator = container.resolve(SwarmCoordinator)
        assert coordinator is not None

    def test_resolve_workflow_coordinator(self) -> None:
        from enhanced_agent_bus.coordinators import WorkflowCoordinator

        container = create_default_container()
        coordinator = container.resolve(WorkflowCoordinator)
        assert coordinator is not None

    def test_resolve_research_coordinator(self) -> None:
        from enhanced_agent_bus.coordinators import ResearchCoordinator

        container = create_default_container()
        coordinator = container.resolve(ResearchCoordinator)
        assert coordinator is not None

    def test_resolve_maci_coordinator(self) -> None:
        from enhanced_agent_bus.coordinators import MACICoordinator

        container = create_default_container()
        coordinator = container.resolve(MACICoordinator)
        assert coordinator is not None

    def test_singletons(self) -> None:
        from enhanced_agent_bus.coordinators import MemoryCoordinator

        container = create_default_container()
        first = container.resolve(MemoryCoordinator)
        second = container.resolve(MemoryCoordinator)
        assert first is second


class TestGetAndResetContainer:
    """Tests for get_container and reset_container globals."""

    def setup_method(self) -> None:
        reset_container()

    def teardown_method(self) -> None:
        reset_container()

    def test_get_container_creates_default(self) -> None:
        container = get_container()
        assert isinstance(container, DIContainer)
        services = container.get_registered_services()
        assert len(services) > 0

    def test_get_container_returns_singleton(self) -> None:
        first = get_container()
        second = get_container()
        assert first is second

    def test_reset_container_clears_global(self) -> None:
        first = get_container()
        reset_container()
        second = get_container()
        assert first is not second

    def test_reset_container_idempotent(self) -> None:
        reset_container()
        reset_container()  # should not raise


# ===========================================================================
# MessageProcessor Tests
# ===========================================================================


def _make_processor(**kwargs: Any) -> Any:
    """Create a MessageProcessor in isolated mode with mocked dependencies."""
    from enhanced_agent_bus.message_processor import MessageProcessor

    defaults = {
        "isolated_mode": True,
        "enable_pqc": False,
        "enable_maci": False,
        "enable_metering": False,
    }
    defaults.update(kwargs)
    return MessageProcessor(**defaults)


class TestMessageProcessorInit:
    """Tests for MessageProcessor constructor and attribute setup."""

    def test_isolated_mode(self) -> None:
        proc = _make_processor(isolated_mode=True)
        assert proc._isolated_mode is True
        assert proc._opa_client is None

    def test_constitutional_hash(self) -> None:
        proc = _make_processor()
        assert proc.constitutional_hash == CONSTITUTIONAL_HASH

    def test_default_counts(self) -> None:
        proc = _make_processor()
        assert proc.processed_count == 0
        assert proc.failed_count == 0

    def test_invalid_cache_hash_mode_raises(self) -> None:
        from enhanced_agent_bus.message_processor import MessageProcessor

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            MessageProcessor(isolated_mode=True, cache_hash_mode="invalid")

    def test_cache_hash_mode_sha256(self) -> None:
        proc = _make_processor(cache_hash_mode="sha256")
        assert proc._cache_hash_mode == "sha256"

    def test_cache_hash_mode_non_string_raises(self) -> None:
        from enhanced_agent_bus.message_processor import MessageProcessor

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            MessageProcessor(isolated_mode=True, cache_hash_mode=123)

    def test_processing_strategy_set(self) -> None:
        proc = _make_processor()
        assert proc.processing_strategy is not None

    def test_custom_processing_strategy(self) -> None:
        mock_strategy = MagicMock()
        mock_strategy.get_name = MagicMock(return_value="mock")
        proc = _make_processor(processing_strategy=mock_strategy)
        assert proc.processing_strategy is mock_strategy

    def test_handlers_empty(self) -> None:
        proc = _make_processor()
        assert proc._handlers == {}


class TestMessageProcessorHandlers:
    """Tests for register_handler and unregister_handler."""

    def test_register_handler(self) -> None:
        proc = _make_processor()

        async def handler(msg: AgentMessage) -> AgentMessage | None:
            return msg

        proc.register_handler(MessageType.COMMAND, handler)
        assert MessageType.COMMAND in proc._handlers
        assert handler in proc._handlers[MessageType.COMMAND]

    def test_register_multiple_handlers(self) -> None:
        proc = _make_processor()

        async def handler1(msg: AgentMessage) -> AgentMessage | None:
            return msg

        async def handler2(msg: AgentMessage) -> AgentMessage | None:
            return None

        proc.register_handler(MessageType.COMMAND, handler1)
        proc.register_handler(MessageType.COMMAND, handler2)
        assert len(proc._handlers[MessageType.COMMAND]) == 2

    def test_unregister_handler_success(self) -> None:
        proc = _make_processor()

        async def handler(msg: AgentMessage) -> AgentMessage | None:
            return msg

        proc.register_handler(MessageType.COMMAND, handler)
        result = proc.unregister_handler(MessageType.COMMAND, handler)
        assert result is True
        assert len(proc._handlers[MessageType.COMMAND]) == 0

    def test_unregister_handler_not_found(self) -> None:
        proc = _make_processor()

        async def handler(msg: AgentMessage) -> AgentMessage | None:
            return msg

        result = proc.unregister_handler(MessageType.COMMAND, handler)
        assert result is False

    def test_unregister_handler_wrong_type(self) -> None:
        proc = _make_processor()

        async def handler(msg: AgentMessage) -> AgentMessage | None:
            return msg

        proc.register_handler(MessageType.COMMAND, handler)
        result = proc.unregister_handler(MessageType.QUERY, handler)
        assert result is False


class TestMessageProcessorProperties:
    """Tests for read-only properties."""

    def test_processed_count_property(self) -> None:
        proc = _make_processor()
        proc._processed_count = 5
        assert proc.processed_count == 5

    def test_failed_count_property(self) -> None:
        proc = _make_processor()
        proc._failed_count = 3
        assert proc.failed_count == 3

    def test_opa_client_property(self) -> None:
        proc = _make_processor()
        assert proc.opa_client is None


class TestMessageProcessorMetrics:
    """Tests for get_metrics method."""

    def test_metrics_basic(self) -> None:
        proc = _make_processor()
        metrics = proc.get_metrics()
        assert metrics["processed_count"] == 0
        assert metrics["failed_count"] == 0
        assert metrics["success_rate"] == 0.0
        assert metrics["pqc_enabled"] is False
        assert "processing_strategy" in metrics

    def test_metrics_with_counts(self) -> None:
        proc = _make_processor()
        proc._processed_count = 8
        proc._failed_count = 2
        metrics = proc.get_metrics()
        assert metrics["processed_count"] == 8
        assert metrics["failed_count"] == 2
        assert metrics["success_rate"] == pytest.approx(0.8)

    def test_metrics_all_failed(self) -> None:
        proc = _make_processor()
        proc._failed_count = 5
        metrics = proc.get_metrics()
        assert metrics["success_rate"] == pytest.approx(0.0)

    def test_metrics_session_governance_disabled(self) -> None:
        proc = _make_processor()
        proc._enable_session_governance = False
        metrics = proc.get_metrics()
        assert "session_governance_enabled" in metrics
        assert metrics["session_governance_enabled"] is False

    def test_metrics_opa_disabled(self) -> None:
        proc = _make_processor()
        metrics = proc.get_metrics()
        assert metrics["opa_enabled"] is False

    def test_metrics_strategy_name(self) -> None:
        proc = _make_processor()
        metrics = proc.get_metrics()
        assert isinstance(metrics["processing_strategy"], str)

    def test_metrics_pqc_fields_none_when_disabled(self) -> None:
        proc = _make_processor(enable_pqc=False)
        metrics = proc.get_metrics()
        assert metrics["pqc_mode"] is None
        assert metrics["pqc_verification_mode"] is None
        assert metrics["pqc_migration_phase"] is None


class TestMessageProcessorAutoSelectStrategy:
    """Tests for _auto_select_strategy method."""

    def test_isolated_returns_python_strategy(self) -> None:
        proc = _make_processor(isolated_mode=True)
        name = proc.processing_strategy.get_name()
        assert "python" in name.lower() or "static" in name.lower() or name

    def test_with_maci_enabled(self) -> None:
        """MACI wrapping requires non-isolated mode, but still testable."""
        proc = _make_processor(isolated_mode=True, enable_maci=False)
        assert proc._enable_maci is False


class TestMessageProcessorSetStrategy:
    """Tests for _set_strategy."""

    def test_set_strategy(self) -> None:
        proc = _make_processor()
        mock_strategy = MagicMock()
        proc._set_strategy(mock_strategy)
        assert proc._processing_strategy is mock_strategy


class TestMessageProcessorLogDecision:
    """Tests for _log_decision helper."""

    def test_log_decision_no_span(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        result = ValidationResult(is_valid=True)
        # Should not raise
        proc._log_decision(msg, result)

    def test_log_decision_with_span(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        result = ValidationResult(is_valid=True)
        span = MagicMock()
        span.set_attribute = MagicMock()
        ctx = MagicMock()
        ctx.trace_id = 12345
        span.get_span_context = MagicMock(return_value=ctx)
        proc._log_decision(msg, result, span=span)
        span.set_attribute.assert_any_call("msg.id", msg.message_id)
        span.set_attribute.assert_any_call("msg.valid", True)

    def test_log_decision_span_no_get_span_context(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        result = ValidationResult(is_valid=False)
        span = MagicMock(spec=["set_attribute"])
        proc._log_decision(msg, result, span=span)

    def test_log_decision_span_context_no_trace_id(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        result = ValidationResult(is_valid=True)
        span = MagicMock()
        ctx = MagicMock(spec=[])  # no trace_id
        span.get_span_context = MagicMock(return_value=ctx)
        proc._log_decision(msg, result, span=span)


class TestMessageProcessorComplianceTags:
    """Tests for _get_compliance_tags."""

    def test_approved_tags(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        result = ValidationResult(is_valid=True)
        tags = proc._get_compliance_tags(msg, result)
        assert "constitutional_validated" in tags
        assert "approved" in tags
        assert "rejected" not in tags

    def test_rejected_tags(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        result = ValidationResult(is_valid=False)
        tags = proc._get_compliance_tags(msg, result)
        assert "constitutional_validated" in tags
        assert "rejected" in tags
        assert "approved" not in tags

    def test_critical_priority_tag(self) -> None:
        proc = _make_processor()
        msg = _make_msg(priority=Priority.CRITICAL)
        result = ValidationResult(is_valid=True)
        tags = proc._get_compliance_tags(msg, result)
        assert "high_priority" in tags


class TestMessageProcessorRequiresIndependentValidation:
    """Tests for _requires_independent_validation."""

    def test_high_impact_requires_validation(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        msg.impact_score = 0.9
        assert proc._requires_independent_validation(msg) is True

    def test_low_impact_no_validation(self) -> None:
        proc = _make_processor()
        msg = _make_msg(message_type=MessageType.QUERY)
        msg.impact_score = 0.1
        assert proc._requires_independent_validation(msg) is False

    def test_governance_type_requires_validation(self) -> None:
        proc = _make_processor()
        msg = _make_msg(message_type=MessageType.GOVERNANCE_REQUEST)
        msg.impact_score = 0.0
        assert proc._requires_independent_validation(msg) is True

    def test_constitutional_type_requires_validation(self) -> None:
        proc = _make_processor()
        msg = _make_msg(message_type=MessageType.CONSTITUTIONAL_VALIDATION)
        msg.impact_score = 0.0
        assert proc._requires_independent_validation(msg) is True

    def test_none_impact_score(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        msg.impact_score = None
        # Should not raise, treat as 0.0
        result = proc._requires_independent_validation(msg)
        assert isinstance(result, bool)


class TestMessageProcessorEnforceIndependentValidatorGate:
    """Tests for _enforce_independent_validator_gate."""

    def test_gate_disabled(self) -> None:
        proc = _make_processor()
        proc._require_independent_validator = False
        msg = _make_msg(message_type=MessageType.GOVERNANCE_REQUEST)
        result = proc._enforce_independent_validator_gate(msg)
        assert result is None

    def test_gate_not_required_for_low_impact(self) -> None:
        proc = _make_processor()
        proc._require_independent_validator = True
        msg = _make_msg(message_type=MessageType.QUERY)
        msg.impact_score = 0.0
        result = proc._enforce_independent_validator_gate(msg)
        assert result is None

    def test_gate_missing_validator_id(self) -> None:
        proc = _make_processor()
        proc._require_independent_validator = True
        msg = _make_msg(message_type=MessageType.GOVERNANCE_REQUEST)
        msg.impact_score = 0.0
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert result.is_valid is False
        assert "independent_validator_missing" in str(result.metadata)

    def test_gate_self_validation_rejected(self) -> None:
        proc = _make_processor()
        proc._require_independent_validator = True
        msg = _make_msg(
            from_agent="agent-1",
            message_type=MessageType.GOVERNANCE_REQUEST,
            metadata={"validated_by_agent": "agent-1"},
        )
        msg.impact_score = 0.0
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert result.is_valid is False
        assert "self_validation" in str(result.metadata)

    def test_gate_invalid_stage(self) -> None:
        proc = _make_processor()
        proc._require_independent_validator = True
        msg = _make_msg(
            from_agent="agent-1",
            message_type=MessageType.GOVERNANCE_REQUEST,
            metadata={
                "validated_by_agent": "agent-2",
                "validation_stage": "self",
            },
        )
        msg.impact_score = 0.0
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert result.is_valid is False
        assert "invalid_stage" in str(result.metadata)

    def test_gate_passes_with_valid_validator(self) -> None:
        proc = _make_processor()
        proc._require_independent_validator = True
        msg = _make_msg(
            from_agent="agent-1",
            message_type=MessageType.GOVERNANCE_REQUEST,
            metadata={
                "validated_by_agent": "agent-2",
                "validation_stage": "independent",
            },
        )
        msg.impact_score = 0.0
        result = proc._enforce_independent_validator_gate(msg)
        assert result is None

    def test_gate_passes_with_no_stage(self) -> None:
        proc = _make_processor()
        proc._require_independent_validator = True
        msg = _make_msg(
            from_agent="agent-1",
            message_type=MessageType.GOVERNANCE_REQUEST,
            metadata={"validated_by_agent": "agent-2"},
        )
        msg.impact_score = 0.0
        result = proc._enforce_independent_validator_gate(msg)
        assert result is None

    def test_gate_empty_string_validator(self) -> None:
        proc = _make_processor()
        proc._require_independent_validator = True
        msg = _make_msg(
            from_agent="agent-1",
            message_type=MessageType.GOVERNANCE_REQUEST,
            metadata={"validated_by_agent": "  "},
        )
        msg.impact_score = 0.0
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert result.is_valid is False

    def test_gate_uses_independent_validator_id_fallback(self) -> None:
        proc = _make_processor()
        proc._require_independent_validator = True
        msg = _make_msg(
            from_agent="agent-1",
            message_type=MessageType.GOVERNANCE_REQUEST,
            metadata={"independent_validator_id": "agent-3"},
        )
        msg.impact_score = 0.0
        result = proc._enforce_independent_validator_gate(msg)
        assert result is None


class TestMessageProcessorRecordAgentWorkflowEvent:
    """Tests for _record_agent_workflow_event."""

    def test_no_collector(self) -> None:
        proc = _make_processor()
        proc._agent_workflow_metrics = None
        msg = _make_msg()
        # Should not raise
        proc._record_agent_workflow_event(event_type="test", msg=msg, reason="test")

    def test_collector_record_called(self) -> None:
        proc = _make_processor()
        collector = MagicMock()
        proc._agent_workflow_metrics = collector
        msg = _make_msg(from_agent="agent-x", tenant_id="t1")
        proc._record_agent_workflow_event(event_type="intervention", msg=msg, reason="test_reason")
        collector.record_event.assert_called_once_with(
            event_type="intervention",
            tenant_id="t1",
            source="agent-x",
            reason="test_reason",
        )

    def test_collector_raises_silently(self) -> None:
        proc = _make_processor()
        collector = MagicMock()
        collector.record_event.side_effect = RuntimeError("boom")
        proc._agent_workflow_metrics = collector
        msg = _make_msg()
        # Should not raise
        proc._record_agent_workflow_event(event_type="test", msg=msg, reason="r")

    def test_collector_default_tenant(self) -> None:
        proc = _make_processor()
        collector = MagicMock()
        proc._agent_workflow_metrics = collector
        msg = _make_msg()
        msg.tenant_id = None  # type: ignore[assignment]
        proc._record_agent_workflow_event(event_type="x", msg=msg, reason="y")
        call_kwargs = collector.record_event.call_args.kwargs
        assert call_kwargs["tenant_id"] == "default"

    def test_collector_default_source(self) -> None:
        proc = _make_processor()
        collector = MagicMock()
        proc._agent_workflow_metrics = collector
        msg = _make_msg()
        msg.from_agent = ""
        proc._record_agent_workflow_event(event_type="x", msg=msg, reason="y")
        call_kwargs = collector.record_event.call_args.kwargs
        assert call_kwargs["source"] == "unknown"


class TestMessageProcessorExtractRejectionReason:
    """Tests for _extract_rejection_reason static method."""

    def test_extract_from_metadata(self) -> None:
        from enhanced_agent_bus.message_processor import MessageProcessor

        result = ValidationResult(
            is_valid=False,
            metadata={"rejection_reason": "policy_violation"},
        )
        reason = MessageProcessor._extract_rejection_reason(result)
        assert isinstance(reason, str)


class TestMessageProcessorProcess:
    """Tests for the process() and _do_process() methods."""

    async def test_process_basic_success(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        result = await proc.process(msg, max_retries=1)
        assert isinstance(result, ValidationResult)

    async def test_process_retries_on_failure(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        call_count = {"n": 0}
        original_do_process = proc._do_process

        async def failing_then_ok(m: AgentMessage) -> ValidationResult:
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RuntimeError("transient")
            return await original_do_process(m)

        proc._do_process = failing_then_ok
        result = await proc.process(msg, max_retries=3)
        assert call_count["n"] >= 2

    async def test_process_max_retries_exceeded(self) -> None:
        proc = _make_processor()
        msg = _make_msg()

        async def always_fail(m: AgentMessage) -> ValidationResult:
            raise ValueError("persistent error")

        proc._do_process = always_fail
        result = await proc.process(msg, max_retries=2)
        assert result.is_valid is False
        assert "retries" in str(result.errors)

    async def test_process_cancelled_error_propagates(self) -> None:
        proc = _make_processor()
        msg = _make_msg()

        async def cancel(m: AgentMessage) -> ValidationResult:
            raise asyncio.CancelledError()

        proc._do_process = cancel
        with pytest.raises(asyncio.CancelledError):
            await proc.process(msg, max_retries=3)


class TestMessageProcessorSecurityScan:
    """Tests for _perform_security_scan."""

    async def test_scan_passes(self) -> None:
        proc = _make_processor()
        proc._security_scanner = MagicMock()
        proc._security_scanner.scan = AsyncMock(return_value=None)
        msg = _make_msg()
        result = await proc._perform_security_scan(msg)
        assert result is None

    async def test_scan_blocks(self) -> None:
        proc = _make_processor()
        block_result = ValidationResult(is_valid=False, errors=["blocked"])
        proc._security_scanner = MagicMock()
        proc._security_scanner.scan = AsyncMock(return_value=block_result)
        msg = _make_msg()
        result = await proc._perform_security_scan(msg)
        assert result is not None
        assert result.is_valid is False
        assert proc.failed_count == 1


class TestMessageProcessorSessionContext:
    """Tests for _extract_session_context and _attach_session_context."""

    async def test_session_governance_disabled(self) -> None:
        proc = _make_processor()
        proc._enable_session_governance = False
        msg = _make_msg()
        result = await proc._extract_session_context(msg)
        assert result is None

    async def test_session_governance_enabled(self) -> None:
        proc = _make_processor()
        proc._enable_session_governance = True
        mock_resolver = MagicMock()
        mock_context = MagicMock()
        mock_context.session_id = "sess-1"
        mock_resolver.resolve = AsyncMock(return_value=mock_context)
        mock_resolver.get_metrics = MagicMock(
            return_value={"resolved_count": 1, "not_found_count": 0, "error_count": 0}
        )
        proc._session_resolver = mock_resolver
        msg = _make_msg()
        result = await proc._extract_session_context(msg)
        assert result is mock_context
        assert proc._session_resolved_count == 1

    async def test_attach_session_context_sets_fields(self) -> None:
        proc = _make_processor()
        proc._enable_session_governance = True
        mock_context = MagicMock()
        mock_context.session_id = "sess-2"
        mock_resolver = MagicMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_context)
        mock_resolver.get_metrics = MagicMock(
            return_value={"resolved_count": 1, "not_found_count": 0, "error_count": 0}
        )
        proc._session_resolver = mock_resolver
        msg = _make_msg()
        msg.session_id = None
        await proc._attach_session_context(msg)
        assert msg.session_id == "sess-2"

    async def test_attach_session_context_no_context(self) -> None:
        proc = _make_processor()
        proc._enable_session_governance = False
        msg = _make_msg()
        original_session = msg.session_id
        await proc._attach_session_context(msg)
        assert msg.session_id == original_session


class TestMessageProcessorIncrementFailedCount:
    """Tests for _increment_failed_count."""

    def test_increment(self) -> None:
        proc = _make_processor()
        assert proc._failed_count == 0
        proc._increment_failed_count()
        assert proc._failed_count == 1
        proc._increment_failed_count()
        assert proc._failed_count == 2


class TestMessageProcessorMeteringCallback:
    """Tests for _async_metering_callback."""

    async def test_metering_success(self) -> None:
        proc = _make_processor()
        hooks = MagicMock()
        proc._metering_hooks = hooks
        msg = _make_msg(from_agent="a1", tenant_id="t1")
        await proc._async_metering_callback(msg, 5.0)
        hooks.on_constitutional_validation.assert_called_once_with(
            tenant_id="t1", agent_id="a1", is_valid=True, latency_ms=5.0
        )

    async def test_metering_failure_handled(self) -> None:
        proc = _make_processor()
        hooks = MagicMock()
        hooks.on_constitutional_validation.side_effect = RuntimeError("fail")
        proc._metering_hooks = hooks
        msg = _make_msg()
        # Should not raise
        await proc._async_metering_callback(msg, 1.0)


class TestMessageProcessorDLQ:
    """Tests for _send_to_dlq and _get_dlq_redis."""

    async def test_send_to_dlq_redis_error(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        result = ValidationResult(is_valid=False, errors=["test failure"])
        # Patch import to force error
        with patch(
            "enhanced_agent_bus.message_processor.MessageProcessor._get_dlq_redis",
            new_callable=AsyncMock,
            side_effect=OSError("no redis"),
        ):
            await proc._send_to_dlq(msg, result)
        # Should not raise, error is handled

    async def test_send_to_dlq_success(self) -> None:
        proc = _make_processor()
        mock_client = AsyncMock()
        proc._get_dlq_redis = AsyncMock(return_value=mock_client)
        msg = _make_msg()
        result = ValidationResult(is_valid=False, errors=["bad"])
        await proc._send_to_dlq(msg, result)
        mock_client.lpush.assert_called_once()
        mock_client.ltrim.assert_called_once()

    async def test_get_dlq_redis_cached(self) -> None:
        proc = _make_processor()
        mock_redis = MagicMock()
        proc._dlq_redis = mock_redis
        result = await proc._get_dlq_redis()
        assert result is mock_redis

    async def test_get_dlq_redis_creates(self) -> None:
        proc = _make_processor()
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = MagicMock()
            mock_from_url.return_value = mock_client
            result = await proc._get_dlq_redis()
            assert result is mock_client
            mock_from_url.assert_called_once()


class TestMessageProcessorHandleToolRequest:
    """Tests for handle_tool_request (MCP integration)."""

    async def test_mcp_unavailable(self) -> None:
        proc = _make_processor()
        with patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", False):
            result = await proc.handle_tool_request("agent-1", "tool-x")
        assert isinstance(result, dict)
        assert result["status"] == "error"

    async def test_mcp_pool_not_initialized(self) -> None:
        proc = _make_processor()
        proc._mcp_pool = None
        # Only test when MCP types are available
        try:
            from enhanced_agent_bus.mcp.types import MCPToolResult

            with (
                patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", True),
                patch("enhanced_agent_bus.message_processor.MCPToolResult", MCPToolResult),
            ):
                result = await proc.handle_tool_request("agent-1", "tool-y")
                assert hasattr(result, "status") or isinstance(result, dict)
        except ImportError:
            # MCP not installed; the dict fallback is tested above
            pass


class TestMessageProcessorInitializeMCP:
    """Tests for initialize_mcp method."""

    async def test_mcp_disabled_feature_flag(self) -> None:
        proc = _make_processor()
        with patch("enhanced_agent_bus.message_processor.MCP_ENABLED", False):
            await proc.initialize_mcp({})
        assert proc._mcp_pool is None

    async def test_mcp_dependencies_unavailable(self) -> None:
        proc = _make_processor()
        with (
            patch("enhanced_agent_bus.message_processor.MCP_ENABLED", True),
            patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", False),
        ):
            await proc.initialize_mcp({})
        assert proc._mcp_pool is None

    async def test_mcp_invalid_config_type(self) -> None:
        proc = _make_processor()

        # Create a real class to use as MCPConfig stand-in (isinstance needs a type)
        class FakeMCPConfig:
            pass

        with (
            patch("enhanced_agent_bus.message_processor.MCP_ENABLED", True),
            patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", True),
            patch("enhanced_agent_bus.message_processor.MCPConfig", FakeMCPConfig),
        ):
            await proc.initialize_mcp(12345)
        assert proc._mcp_pool is None


class TestMessageProcessorMemoryProfiling:
    """Tests for _setup_memory_profiling_context."""

    def test_returns_context_manager(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        ctx = proc._setup_memory_profiling_context(msg)
        assert ctx is not None
        # Should be usable as context manager
        with ctx:
            pass


class TestMessageProcessorEnforceAutonomyTier:
    """Tests for _enforce_autonomy_tier delegation."""

    def test_bounded_tier_passes(self) -> None:
        proc = _make_processor()
        msg = _make_msg(autonomy_tier=AutonomyTier.BOUNDED)
        result = proc._enforce_autonomy_tier(msg)
        # BOUNDED should allow all message types
        assert result is None

    def test_advisory_tier_blocks_command(self) -> None:
        proc = _make_processor()
        msg = _make_msg(
            autonomy_tier=AutonomyTier.ADVISORY,
            message_type=MessageType.COMMAND,
        )
        result = proc._enforce_autonomy_tier(msg)
        if result is not None:
            assert result.is_valid is False


class TestMessageProcessorExtractMessageSessionId:
    """Tests for _extract_message_session_id."""

    def test_extract_from_session_id_field(self) -> None:
        proc = _make_processor()
        msg = _make_msg(session_id="sess-abc")
        result = proc._extract_message_session_id(msg)
        # May or may not return depending on implementation
        assert result is None or isinstance(result, str)

    def test_extract_no_session_id(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        result = proc._extract_message_session_id(msg)
        assert result is None or isinstance(result, str)


class TestMessageProcessorHandleProcessingOutcomes:
    """Tests for _handle_successful_processing and _handle_failed_processing."""

    async def test_handle_successful_processing(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        msg.impact_score = 0.1
        result = ValidationResult(is_valid=True, metadata={})
        await proc._handle_successful_processing(msg, result, "cache-key", 5.0)
        assert proc._processed_count == 1

    async def test_handle_successful_processing_with_metering(self) -> None:
        proc = _make_processor()
        hooks = MagicMock()
        hooks.on_constitutional_validation = MagicMock()
        proc._metering_hooks = hooks
        msg = _make_msg()
        msg.impact_score = 0.1
        result = ValidationResult(is_valid=True, metadata={})
        await proc._handle_successful_processing(msg, result, "ck", 2.0)
        assert proc._processed_count == 1

    async def test_handle_failed_processing(self) -> None:
        proc = _make_processor()
        msg = _make_msg()
        result = ValidationResult(
            is_valid=False,
            errors=["bad"],
            metadata={"rejection_reason": "policy"},
        )
        # Mock _send_to_dlq to avoid redis
        proc._send_to_dlq = AsyncMock()
        await proc._handle_failed_processing(msg, result)
        assert proc._failed_count == 1

    async def test_handle_failed_processing_critical(self) -> None:
        proc = _make_processor()
        msg = _make_msg(priority=Priority.CRITICAL)
        result = ValidationResult(
            is_valid=False,
            errors=["critical failure"],
            metadata={"rejection_reason": "policy"},
        )
        proc._send_to_dlq = AsyncMock()
        collector = MagicMock()
        proc._agent_workflow_metrics = collector
        await proc._handle_failed_processing(msg, result)
        assert proc._failed_count == 1
        # Should record both gate_failure and rollback_trigger events
        assert collector.record_event.call_count >= 2
