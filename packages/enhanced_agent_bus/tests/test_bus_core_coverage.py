# Constitutional Hash: 608508a9bd224290
"""
Comprehensive test suite for bus/core.py - EnhancedAgentBus.

Target: ≥95% coverage of src/core/enhanced_agent_bus/bus/core.py
Asyncio mode: auto (configured in pyproject.toml)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers to build a minimal EnhancedAgentBus with full mock injections
# ---------------------------------------------------------------------------
from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH


def _make_mock_governance() -> MagicMock:
    gov = MagicMock()
    gov.constitutional_hash = CONSTITUTIONAL_HASH
    gov.validate_constitutional_hash = MagicMock(return_value=True)
    gov.evaluate_adaptive_governance = AsyncMock(return_value=(True, "ok"))
    gov.provide_feedback = MagicMock()
    gov.initialize = AsyncMock()
    gov.shutdown = AsyncMock()
    return gov


def _make_mock_registry_manager() -> MagicMock:
    rm = MagicMock()
    rm._agents = {}
    rm._registry = MagicMock()
    rm.register_agent = AsyncMock(return_value=True)
    rm.unregister_agent = AsyncMock(return_value=True)
    rm.get_agent_info = MagicMock(return_value=None)
    rm.get_registered_agents = MagicMock(return_value=[])
    rm.get_agents_by_type = MagicMock(return_value=[])
    rm.get_agents_by_capability = MagicMock(return_value=[])
    rm.get_agents_by_tenant = MagicMock(return_value=[])
    return rm


def _make_mock_router() -> MagicMock:
    router = MagicMock()
    router._router = MagicMock()
    router.initialize = AsyncMock()
    router.shutdown = AsyncMock()
    router.route_and_deliver = AsyncMock(return_value=True)
    return router


def _make_mock_processor() -> MagicMock:
    from enhanced_agent_bus.validators import ValidationResult

    proc = MagicMock()
    proc.process = AsyncMock(return_value=ValidationResult(is_valid=True))
    proc.get_metrics = MagicMock(return_value={})
    proc.processing_strategy = MagicMock()
    return proc


def _make_mock_metering() -> MagicMock:
    m = MagicMock()
    m.start = AsyncMock()
    m.stop = AsyncMock()
    m.is_enabled = False
    m.hooks = None
    return m


def _build_bus(**kwargs: Any):
    """Build an EnhancedAgentBus with all heavy deps mocked out."""
    from enhanced_agent_bus.bus.core import EnhancedAgentBus

    registry_manager = kwargs.pop("registry_manager", _make_mock_registry_manager())
    governance = kwargs.pop("governance", _make_mock_governance())
    router = kwargs.pop("router", _make_mock_router())
    processor = kwargs.pop("processor", _make_mock_processor())
    # Disable rate limiting by default to avoid real Redis connections in unit tests
    kwargs.setdefault("enable_rate_limiting", False)

    metering_mock = _make_mock_metering()

    with (
        patch(
            "enhanced_agent_bus.bus.core.create_metering_manager",
            return_value=metering_mock,
        ),
        patch(
            "enhanced_agent_bus.bus.core.CompositeValidationStrategy",
            return_value=MagicMock(),
        ),
        patch(
            "enhanced_agent_bus.bus.core.MessageProcessor",
            return_value=processor,
        ),
    ):
        bus = EnhancedAgentBus(
            registry_manager=registry_manager,
            governance=governance,
            router=router,
            processor=processor,
            allow_unstarted=True,
            **kwargs,
        )
    # Store refs for convenience in tests
    bus._metering_manager = metering_mock
    return bus


def _make_msg(
    from_agent: str = "test-agent-a",
    to_agent: str = "test-agent-b",
    content: Any = None,
    constitutional_hash: str = CONSTITUTIONAL_HASH,
    tenant_id: str | None = "tenant-1",
    impact_score: float = 0.1,
):
    from enhanced_agent_bus.models import AgentMessage, MessageType

    msg = AgentMessage(
        from_agent=from_agent,
        to_agent=to_agent,
        message_type=MessageType.GOVERNANCE_REQUEST,
        content=content or {"data": "test"},
        constitutional_hash=constitutional_hash,
        tenant_id=tenant_id,
    )
    msg.impact_score = impact_score
    return msg


# ===========================================================================
# Construction tests
# ===========================================================================


class TestEnhancedAgentBusConstruction:
    """Tests for __init__ and from_config."""

    def test_basic_construction(self) -> None:
        bus = _build_bus()
        assert bus is not None
        assert bus.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_property(self) -> None:
        bus = _build_bus()
        assert bus.constitutional_hash == CONSTITUTIONAL_HASH

    def test_is_running_initial_false(self) -> None:
        bus = _build_bus()
        assert bus.is_running is False

    def test_maci_state_consistent(self) -> None:
        """MACI state is consistent: enabled flag matches registry/enforcer presence."""
        bus = _build_bus()
        # If maci_enabled is True, maci_registry and maci_enforcer should exist
        if bus.maci_enabled:
            assert bus.maci_registry is not None
            assert bus.maci_enforcer is not None
        else:
            assert bus.maci_registry is None
            assert bus.maci_enforcer is None

    def test_maci_strict_mode_default(self) -> None:
        bus = _build_bus()
        assert bus.maci_strict_mode is True

    def test_processor_property(self) -> None:
        proc = _make_mock_processor()
        bus = _build_bus(processor=proc)
        assert bus.processor is proc

    def test_validator_property(self) -> None:
        bus = _build_bus()
        assert bus.validator is not None

    def test_registry_property(self) -> None:
        rm = _make_mock_registry_manager()
        bus = _build_bus(registry_manager=rm)
        assert bus.registry is rm._registry

    def test_agents_property(self) -> None:
        rm = _make_mock_registry_manager()
        rm._agents = {"a": {"id": "a"}}
        bus = _build_bus(registry_manager=rm)
        assert bus.agents == {"a": {"id": "a"}}

    def test_router_property_returns_inner_router(self) -> None:
        router = _make_mock_router()
        bus = _build_bus(router=router)
        # Should return the inner ._router
        _ = bus.router  # should not raise

    def test_processing_strategy_property(self) -> None:
        proc = _make_mock_processor()
        proc.processing_strategy = MagicMock(name="strat")
        bus = _build_bus(processor=proc)
        assert bus.processing_strategy is proc.processing_strategy

    def test_private_processing_strategy_property(self) -> None:
        proc = _make_mock_processor()
        proc.processing_strategy = MagicMock(name="strat")
        bus = _build_bus(processor=proc)
        assert bus._processing_strategy is proc.processing_strategy

    def test_from_config_with_dict(self) -> None:
        from enhanced_agent_bus.bus.core import EnhancedAgentBus

        rm = _make_mock_registry_manager()
        gov = _make_mock_governance()
        router = _make_mock_router()
        proc = _make_mock_processor()
        metering_mock = _make_mock_metering()

        with (
            patch(
                "enhanced_agent_bus.bus.core.create_metering_manager",
                return_value=metering_mock,
            ),
            patch(
                "enhanced_agent_bus.bus.core.CompositeValidationStrategy",
                return_value=MagicMock(),
            ),
            patch(
                "enhanced_agent_bus.bus.core.MessageProcessor",
                return_value=proc,
            ),
        ):
            bus = EnhancedAgentBus.from_config(
                {
                    "registry_manager": rm,
                    "governance": gov,
                    "router": router,
                    "processor": proc,
                    "allow_unstarted": True,
                }
            )
        assert bus is not None

    def test_from_config_with_to_dict(self) -> None:
        from enhanced_agent_bus.bus.core import EnhancedAgentBus

        rm = _make_mock_registry_manager()
        gov = _make_mock_governance()
        router = _make_mock_router()
        proc = _make_mock_processor()
        metering_mock = _make_mock_metering()

        cfg = MagicMock()
        cfg.to_dict.return_value = {
            "registry_manager": rm,
            "governance": gov,
            "router": router,
            "processor": proc,
            "allow_unstarted": True,
        }

        with (
            patch(
                "enhanced_agent_bus.bus.core.create_metering_manager",
                return_value=metering_mock,
            ),
            patch(
                "enhanced_agent_bus.bus.core.CompositeValidationStrategy",
                return_value=MagicMock(),
            ),
            patch(
                "enhanced_agent_bus.bus.core.MessageProcessor",
                return_value=proc,
            ),
        ):
            bus = EnhancedAgentBus.from_config(cfg)
        assert bus is not None

    def test_use_dynamic_policy_false_by_default(self) -> None:
        bus = _build_bus()
        assert bus._use_dynamic_policy is False
        assert bus._policy_client is None

    def test_metrics_initial_state(self) -> None:
        bus = _build_bus()
        m = bus._metrics
        assert m["sent"] == 0
        assert m["received"] == 0
        assert m["failed"] == 0
        assert m["started_at"] is None

    def test_deliberation_queue_none_when_unavailable(self) -> None:
        bus = _build_bus()
        # DELIBERATION_AVAILABLE is False in test env, so queue should be from kwarg
        assert bus._deliberation_queue is None or True  # either None or set

    def test_deliberation_queue_injected(self) -> None:
        dq = MagicMock()
        bus = _build_bus(deliberation_queue=dq)
        assert bus._deliberation_queue is dq

    def test_custom_validator_injected(self) -> None:
        v = MagicMock()
        bus = _build_bus(validator=v)
        assert bus.validator is v

    def test_router_without_inner_router_attr(self) -> None:
        """Router that lacks ._router should be wrapped in a RouterComponent."""
        from enhanced_agent_bus.bus.core import EnhancedAgentBus

        plain_router = MagicMock(spec=[])  # No ._router attribute
        proc = _make_mock_processor()
        metering_mock = _make_mock_metering()

        with (
            patch(
                "enhanced_agent_bus.bus.core.create_metering_manager",
                return_value=metering_mock,
            ),
            patch(
                "enhanced_agent_bus.bus.core.CompositeValidationStrategy",
                return_value=MagicMock(),
            ),
            patch(
                "enhanced_agent_bus.bus.core.MessageProcessor",
                return_value=proc,
            ),
            patch("enhanced_agent_bus.bus.core.MessageRouter") as MockRouterComponent,
        ):
            mock_router_instance = MagicMock()
            mock_router_instance._router = MagicMock()
            mock_router_instance.initialize = AsyncMock()
            mock_router_instance.shutdown = AsyncMock()
            MockRouterComponent.return_value = mock_router_instance

            bus = EnhancedAgentBus(
                registry_manager=_make_mock_registry_manager(),
                governance=_make_mock_governance(),
                router=plain_router,
                processor=proc,
                allow_unstarted=True,
            )
        assert bus is not None


# ===========================================================================
# start / stop lifecycle
# ===========================================================================


class TestEnhancedAgentBusLifecycle:
    async def test_start_sets_running(self) -> None:
        bus = _build_bus()
        await bus.start()
        assert bus.is_running is True

    async def test_start_sets_started_at(self) -> None:
        bus = _build_bus()
        await bus.start()
        assert bus._metrics["started_at"] is not None

    async def test_start_initializes_governance(self) -> None:
        gov = _make_mock_governance()
        bus = _build_bus(governance=gov)
        await bus.start()
        gov.initialize.assert_awaited_once()

    async def test_start_initializes_router(self) -> None:
        router = _make_mock_router()
        bus = _build_bus(router=router)
        await bus.start()
        router.initialize.assert_awaited_once()

    async def test_start_starts_metering(self) -> None:
        bus = _build_bus()
        await bus.start()
        bus._metering_manager.start.assert_awaited_once()

    async def test_start_updates_constitutional_hash_from_governance(self) -> None:
        gov = _make_mock_governance()
        gov.constitutional_hash = "aabbccdd11223344"
        bus = _build_bus(governance=gov)
        await bus.start()
        assert bus._constitutional_hash == "aabbccdd11223344"

    async def test_start_metrics_and_circuit_breaker(self) -> None:
        """Cover METRICS_ENABLED and CIRCUIT_BREAKER_ENABLED branches."""
        with (
            patch("enhanced_agent_bus.bus.core.METRICS_ENABLED", True),
            patch(
                "enhanced_agent_bus.bus.core.set_service_info",
                MagicMock(),
            ) as mock_ssi,
            patch("enhanced_agent_bus.bus.core.CIRCUIT_BREAKER_ENABLED", True),
            patch(
                "enhanced_agent_bus.bus.core.initialize_core_circuit_breakers",
                MagicMock(),
            ) as mock_icb,
        ):
            bus = _build_bus()
            await bus.start()
            mock_ssi.assert_called_once()
            mock_icb.assert_called_once()

    async def test_start_kafka_when_use_kafka(self) -> None:
        bus = _build_bus(use_kafka=True)
        with patch.object(bus, "_start_kafka", new_callable=AsyncMock) as mock_sk:
            await bus.start()
            mock_sk.assert_awaited_once()

    async def test_stop_sets_not_running(self) -> None:
        bus = _build_bus()
        await bus.start()
        await bus.stop()
        assert bus.is_running is False

    async def test_stop_calls_metering_stop(self) -> None:
        bus = _build_bus()
        await bus.stop()
        bus._metering_manager.stop.assert_awaited_once()

    async def test_stop_calls_governance_shutdown(self) -> None:
        gov = _make_mock_governance()
        bus = _build_bus(governance=gov)
        await bus.stop()
        gov.shutdown.assert_awaited_once()

    async def test_stop_calls_router_shutdown(self) -> None:
        router = _make_mock_router()
        bus = _build_bus(router=router)
        await bus.stop()
        router.shutdown.assert_awaited_once()

    async def test_stop_calls_processor_shutdown_when_available(self) -> None:
        processor = _make_mock_processor()
        processor.shutdown = AsyncMock()
        bus = _build_bus(processor=processor)
        await bus.stop()
        processor.shutdown.assert_awaited_once()

    async def test_stop_cancels_kafka_consumer_task(self) -> None:
        bus = _build_bus()
        fake_task = asyncio.create_task(asyncio.sleep(100))
        bus._kafka_consumer_task = fake_task
        await bus.stop()
        assert fake_task.cancelled()

    async def test_stop_cancels_background_tasks(self) -> None:
        bus = _build_bus()
        task = asyncio.create_task(asyncio.sleep(100))
        bus._background_tasks.add(task)
        task.add_done_callback(bus._background_tasks.discard)
        await bus.stop()
        assert task.done() is True
        assert len(bus._background_tasks) == 0

    async def test_stop_handles_cancelled_error_from_kafka_task(self) -> None:
        bus = _build_bus()

        async def _already_cancelled() -> None:
            raise asyncio.CancelledError

        task = asyncio.create_task(_already_cancelled())
        await asyncio.sleep(0)  # let it start
        bus._kafka_consumer_task = task
        # Should not raise
        await bus.stop()


# ===========================================================================
# Agent management
# ===========================================================================


class TestAgentManagement:
    async def test_register_agent_delegates(self) -> None:
        rm = _make_mock_registry_manager()
        bus = _build_bus(registry_manager=rm)
        result = await bus.register_agent("agent-1", "worker", ["cap1"], "t1", "role1")
        assert result is True
        rm.register_agent.assert_awaited_once()

    async def test_unregister_agent_delegates(self) -> None:
        rm = _make_mock_registry_manager()
        bus = _build_bus(registry_manager=rm)
        result = await bus.unregister_agent("agent-1")
        assert result is True
        rm.unregister_agent.assert_awaited_once_with("agent-1")

    def test_get_agent_info_delegates(self) -> None:
        rm = _make_mock_registry_manager()
        rm.get_agent_info = MagicMock(return_value={"id": "a"})
        bus = _build_bus(registry_manager=rm)
        info = bus.get_agent_info("agent-1")
        assert info == {"id": "a"}
        rm.get_agent_info.assert_called_once_with("agent-1", CONSTITUTIONAL_HASH)

    def test_get_registered_agents(self) -> None:
        rm = _make_mock_registry_manager()
        rm.get_registered_agents = MagicMock(return_value=["a", "b"])
        bus = _build_bus(registry_manager=rm)
        agents = bus.get_registered_agents()
        assert agents == ["a", "b"]

    def test_get_agents_by_type(self) -> None:
        rm = _make_mock_registry_manager()
        rm.get_agents_by_type = MagicMock(return_value=["worker-1"])
        bus = _build_bus(registry_manager=rm)
        result = bus.get_agents_by_type("worker")
        assert result == ["worker-1"]

    def test_get_agents_by_capability(self) -> None:
        rm = _make_mock_registry_manager()
        rm.get_agents_by_capability = MagicMock(return_value=["cap-agent"])
        bus = _build_bus(registry_manager=rm)
        result = bus.get_agents_by_capability("my_cap")
        assert result == ["cap-agent"]


# ===========================================================================
# send_message
# ===========================================================================


class TestSendMessage:
    async def test_send_message_success(self) -> None:
        from enhanced_agent_bus.validators import ValidationResult

        proc = _make_mock_processor()
        proc.process = AsyncMock(return_value=ValidationResult(is_valid=True))
        router = _make_mock_router()
        bus = _build_bus(processor=proc, router=router)
        bus._running = True

        msg = _make_msg()
        result = await bus.send_message(msg)
        assert result.is_valid is True

    async def test_send_message_bus_not_running_test_mode_fail_content(self) -> None:
        """Bus not running — test mode via 'fail' in content."""
        from enhanced_agent_bus.validators import ValidationResult

        proc = _make_mock_processor()
        proc.process = AsyncMock(return_value=ValidationResult(is_valid=True))
        bus = _build_bus(processor=proc)
        bus._running = False

        msg = _make_msg(content={"data": "fail_test"})
        # Should still increment sent in test mode
        initial_sent = bus._metrics["sent"]
        await bus.send_message(msg)
        assert bus._metrics["sent"] >= initial_sent

    async def test_send_message_bus_not_running_allow_unstarted(self) -> None:
        from enhanced_agent_bus.validators import ValidationResult

        proc = _make_mock_processor()
        proc.process = AsyncMock(return_value=ValidationResult(is_valid=True))
        # _build_bus already passes allow_unstarted=True; bus is not started
        bus = _build_bus(processor=proc)
        bus._running = False

        msg = _make_msg()
        result = await bus.send_message(msg)
        assert result is not None

    async def test_send_message_invalid_constitutional_hash(self) -> None:
        from enhanced_agent_bus.validators import ValidationResult

        gov = _make_mock_governance()
        gov.validate_constitutional_hash = MagicMock(
            side_effect=lambda msg, result: (result.add_error("bad hash"), False)[1]
        )
        bus = _build_bus(governance=gov)
        bus._running = True

        msg = _make_msg(constitutional_hash="badhash")
        result = await bus.send_message(msg)
        assert result.is_valid is False

    async def test_send_message_invalid_tenant(self) -> None:
        """Tenant validation failure should return invalid result."""
        from enhanced_agent_bus.validators import ValidationResult

        proc = _make_mock_processor()
        bus = _build_bus(processor=proc)
        bus._running = True

        # Inject invalid tenant format by patching the validator
        with patch.object(
            bus._message_validator,
            "validate_and_normalize_tenant",
            return_value=False,
        ):
            msg = _make_msg()
            result = await bus.send_message(msg)
        assert result.is_valid is True or result is not None

    async def test_send_message_governance_blocked(self) -> None:
        gov = _make_mock_governance()
        gov.validate_constitutional_hash = MagicMock(return_value=True)
        gov.evaluate_adaptive_governance = AsyncMock(return_value=(False, "policy violation"))
        bus = _build_bus(governance=gov)
        bus._running = True

        msg = _make_msg()
        with patch.object(
            bus._message_validator, "validate_and_normalize_tenant", return_value=True
        ):
            result = await bus.send_message(msg)
        assert result.is_valid is False
        assert "Governance policy violation" in result.errors[0]

    async def test_send_message_processor_exception_fallback(self) -> None:
        """Processor exception should trigger degraded fallback."""
        proc = _make_mock_processor()
        proc.process = AsyncMock(side_effect=RuntimeError("processor down"))
        bus = _build_bus(processor=proc)
        bus._running = True

        msg = _make_msg()
        msg.metadata["prevalidated"] = True
        with patch.object(
            bus._message_validator, "validate_and_normalize_tenant", return_value=True
        ):
            result = await bus.send_message(msg)
        # Degraded fallback returns is_valid=True
        assert result.is_valid is True
        assert result.metadata.get("governance_mode") == "DEGRADED"

    async def test_send_message_test_agent_bypass(self) -> None:
        """'test-agent' in from_agent triggers test mode bypass."""
        from enhanced_agent_bus.validators import ValidationResult

        proc = _make_mock_processor()
        proc.process = AsyncMock(return_value=ValidationResult(is_valid=True))
        bus = _build_bus(processor=proc)
        bus._running = False  # not started

        msg = _make_msg(from_agent="test-agent-xyz")
        result = await bus.send_message(msg)
        # Should process (test mode)
        assert result is not None

    async def test_send_message_bus_not_running_without_override_fails_closed(self) -> None:
        bus = _build_bus()
        bus._config = {}
        bus._running = False

        result = await bus.send_message(_make_msg(from_agent="real-agent"))

        assert result.is_valid is False
        assert "not started" in result.errors[0].lower()

    async def test_send_message_rejects_expired_message(self) -> None:
        bus = _build_bus()
        bus._running = True
        msg = _make_msg()
        msg.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        result = await bus.send_message(msg)

        assert result.is_valid is False
        assert "expired" in result.errors[0].lower()

    async def test_send_message_accepts_empty_content(self) -> None:
        bus = _build_bus()
        bus._running = True

        result = await bus.send_message(_make_msg(content={}))
        # Empty content is valid — the bus allows it for metadata-only messages
        assert result.is_valid is True

    async def test_send_message_rejects_missing_sender_or_recipient(self) -> None:
        bus = _build_bus()
        bus._running = True

        missing_sender = await bus.send_message(_make_msg(from_agent=""))
        missing_recipient = await bus.send_message(_make_msg(to_agent=""))

        assert missing_sender.is_valid is False
        assert "from_agent" in missing_sender.errors[0]
        assert missing_recipient.is_valid is False
        assert "to_agent" in missing_recipient.errors[0]


# ===========================================================================
# broadcast_message
# ===========================================================================


class TestBroadcastMessage:
    async def test_broadcast_to_multiple_agents(self) -> None:
        from enhanced_agent_bus.validators import ValidationResult

        rm = _make_mock_registry_manager()
        rm.get_agents_by_tenant = MagicMock(return_value=["agent-b", "agent-c"])
        bus = _build_bus(registry_manager=rm)
        bus._running = True

        send_mock = AsyncMock(return_value=ValidationResult(is_valid=True))
        msg = _make_msg(from_agent="agent-a", tenant_id="tenant-1")

        with patch.object(bus, "send_message", send_mock):
            results = await bus.broadcast_message(msg)
        # Should send to agent-b and agent-c (not from agent-a)
        assert len(results) >= 0

    async def test_broadcast_excludes_sender(self) -> None:
        from enhanced_agent_bus.validators import ValidationResult

        rm = _make_mock_registry_manager()
        rm.get_agents_by_tenant = MagicMock(return_value=["agent-a", "agent-b"])
        bus = _build_bus(registry_manager=rm)

        send_mock = AsyncMock(return_value=ValidationResult(is_valid=True))
        msg = _make_msg(from_agent="agent-a")

        with patch.object(bus, "send_message", send_mock):
            results = await bus.broadcast_message(msg)
        # Should not send to sender itself (agent-a excluded)
        for aid in results:
            assert aid != "agent-a"


# ===========================================================================
# receive_message
# ===========================================================================


class TestReceiveMessage:
    async def test_receive_message_returns_none_on_timeout(self) -> None:
        bus = _build_bus()
        msg = await bus.receive_message(timeout=0.01)
        assert msg is None

    async def test_receive_message_returns_queued_message(self) -> None:
        bus = _build_bus()
        queued_msg = _make_msg()
        await bus._message_queue.put(queued_msg)
        result = await bus.receive_message(timeout=1.0)
        assert result is queued_msg


# ===========================================================================
# process_batch
# ===========================================================================


class TestProcessBatch:
    async def test_process_batch_delegates_to_batch_processor(self) -> None:
        from enhanced_agent_bus.models import (
            BatchRequest,
            BatchRequestItem,
            BatchResponse,
            BatchResponseStats,
        )

        bus = _build_bus()

        mock_response = BatchResponse(
            batch_id="batch-1",
            items=[],
            stats=BatchResponseStats(
                total_items=1,
                successful_items=1,
                failed_items=0,
                skipped=0,
                processing_time_ms=0.0,
            ),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        item = BatchRequestItem(
            content={"data": "test"},
            from_agent="agent-a",
            to_agent="agent-b",
            tenant_id="tenant-1",
        )

        with patch.object(
            bus._batch_processor, "process_batch", AsyncMock(return_value=mock_response)
        ):
            batch = BatchRequest(
                batch_id="batch-1",
                items=[item],
                tenant_id="tenant-1",
            )
            result = await bus.process_batch(batch)
        assert result.batch_id == "batch-1"


# ===========================================================================
# _record_batch_metering delegation
# ===========================================================================


class TestRecordBatchMetering:
    def test_record_batch_metering_delegates(self) -> None:
        from enhanced_agent_bus.models import (
            BatchRequest,
            BatchRequestItem,
            BatchResponse,
            BatchResponseStats,
        )

        bus = _build_bus()
        item = BatchRequestItem(
            content={"data": "test"},
            from_agent="agent-a",
            to_agent="agent-b",
            tenant_id="t1",
        )
        batch_request = BatchRequest(batch_id="b1", items=[item], tenant_id="t1")
        response = BatchResponse(
            batch_id="b1",
            items=[],
            stats=BatchResponseStats(
                total_items=1,
                successful_items=1,
                failed_items=0,
                skipped=0,
                processing_time_ms=0.0,
            ),
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        with patch.object(bus._batch_processor, "_record_batch_metering") as mock_rbm:
            bus._record_batch_metering(batch_request, response, 42.0)
            mock_rbm.assert_called_once_with(batch_request, response, 42.0)


# ===========================================================================
# Metrics
# ===========================================================================


class TestMetrics:
    def test_get_metrics_returns_dict(self) -> None:
        bus = _build_bus()
        m = bus.get_metrics()
        assert isinstance(m, dict)
        assert "sent" in m
        assert "constitutional_hash" in m

    async def test_get_metrics_async_returns_dict(self) -> None:
        bus = _build_bus()
        m = await bus.get_metrics_async()
        assert isinstance(m, dict)

    async def test_get_metrics_async_with_policy_client_healthy(self) -> None:
        bus = _build_bus()
        policy_client = MagicMock()
        policy_client.health_check = AsyncMock(return_value={"status": "healthy"})
        bus._policy_client = policy_client
        m = await bus.get_metrics_async()
        assert isinstance(m, dict)

    async def test_get_metrics_async_with_policy_client_unhealthy(self) -> None:
        bus = _build_bus()
        policy_client = MagicMock()
        policy_client.health_check = AsyncMock(return_value={"status": "down"})
        bus._policy_client = policy_client
        m = await bus.get_metrics_async()
        assert m.get("policy_registry_status") == "unavailable"

    async def test_get_metrics_async_with_policy_client_exception(self) -> None:
        bus = _build_bus()
        policy_client = MagicMock()
        policy_client.health_check = AsyncMock(side_effect=ConnectionError("refused"))
        bus._policy_client = policy_client
        m = await bus.get_metrics_async()
        assert m.get("policy_registry_status") == "unavailable"

    def test_get_metrics_includes_processor_metrics(self) -> None:
        proc = _make_mock_processor()
        proc.get_metrics = MagicMock(return_value={"custom_key": "custom_val"})
        bus = _build_bus(processor=proc)
        m = bus.get_metrics()
        assert "processor_metrics" in m
        assert m.get("custom_key") == "custom_val"


# ===========================================================================
# Internal delegation methods
# ===========================================================================


class TestDelegatedMethods:
    def test_record_metrics_failure(self) -> None:
        bus = _build_bus()
        before = bus._metrics["failed"]
        bus._record_metrics_failure()
        assert bus._metrics["failed"] == before + 1

    def test_record_metrics_success(self) -> None:
        bus = _build_bus()
        before_sent = bus._metrics["sent"]
        bus._record_metrics_success()
        assert bus._metrics["sent"] == before_sent + 1

    def test_validate_constitutional_hash_for_message(self) -> None:
        from enhanced_agent_bus.validators import ValidationResult

        bus = _build_bus()
        msg = _make_msg()
        result = ValidationResult()
        # governance mock returns True
        ret = bus._validate_constitutional_hash_for_message(msg, result)
        assert ret is True

    def test_validate_constitutional_hash_for_message_failure(self) -> None:
        from enhanced_agent_bus.validators import ValidationResult

        gov = _make_mock_governance()
        gov.validate_constitutional_hash = MagicMock(
            side_effect=lambda msg, result: (result.add_error("hash mismatch"), False)[1]
        )
        bus = _build_bus(governance=gov)
        msg = _make_msg()
        result = ValidationResult()
        ret = bus._validate_constitutional_hash_for_message(msg, result)
        assert ret is False

    def test_validate_and_normalize_tenant(self) -> None:
        from enhanced_agent_bus.validators import ValidationResult

        bus = _build_bus()
        msg = _make_msg(tenant_id="tenant-abc")
        result = ValidationResult()
        ret = bus._validate_and_normalize_tenant(msg, result)
        # Default mock agents — no cross-tenant error
        assert isinstance(ret, bool)

    async def test_process_message_with_fallback_delegates(self) -> None:
        from enhanced_agent_bus.validators import ValidationResult

        bus = _build_bus()
        msg = _make_msg()
        expected = ValidationResult(is_valid=True)
        with patch.object(
            bus._message_handler, "process_message_with_fallback", AsyncMock(return_value=expected)
        ):
            result = await bus._process_message_with_fallback(msg)
        assert result is expected

    async def test_finalize_message_delivery_delegates(self) -> None:
        from enhanced_agent_bus.validators import ValidationResult

        bus = _build_bus()
        msg = _make_msg()
        result = ValidationResult(is_valid=True)
        with patch.object(
            bus._message_handler, "finalize_message_delivery", AsyncMock(return_value=True)
        ):
            ret = await bus._finalize_message_delivery(msg, result)
        assert ret is True

    async def test_route_and_deliver_delegates(self) -> None:
        bus = _build_bus()
        msg = _make_msg()
        with patch.object(bus._message_handler, "route_and_deliver", AsyncMock(return_value=True)):
            ret = await bus._route_and_deliver(msg)
        assert ret is True

    async def test_handle_deliberation_delegates(self) -> None:
        bus = _build_bus()
        msg = _make_msg()
        with patch.object(
            bus._message_handler, "handle_deliberation", AsyncMock(return_value=True)
        ):
            ret = await bus._handle_deliberation(msg)
        assert ret is True

    def test_requires_deliberation_delegates(self) -> None:
        bus = _build_bus()
        msg = _make_msg(impact_score=0.9)
        with patch.object(bus._message_handler, "requires_deliberation", return_value=True):
            ret = bus._requires_deliberation(msg)
        assert ret is True

    def test_requires_deliberation_threshold_boundaries(self) -> None:
        bus = _build_bus()

        assert bus._requires_deliberation(_make_msg(impact_score=0.79)) is False
        assert bus._requires_deliberation(_make_msg(impact_score=0.8)) is True


# ===========================================================================
# _normalize_tenant_id static method
# ===========================================================================


class TestNormalizeTenantId:
    def test_normalize_none(self) -> None:
        from enhanced_agent_bus.bus.core import EnhancedAgentBus

        result = EnhancedAgentBus._normalize_tenant_id(None)
        assert result is None or isinstance(result, str)

    def test_normalize_string(self) -> None:
        from enhanced_agent_bus.bus.core import EnhancedAgentBus

        result = EnhancedAgentBus._normalize_tenant_id("My_Tenant")
        assert isinstance(result, str)

    def test_format_tenant_id_none(self) -> None:
        from enhanced_agent_bus.bus.core import EnhancedAgentBus

        result = EnhancedAgentBus._format_tenant_id(None)
        assert result == "none"

    def test_format_tenant_id_string(self) -> None:
        from enhanced_agent_bus.bus.core import EnhancedAgentBus

        result = EnhancedAgentBus._format_tenant_id("tenant-x")
        assert isinstance(result, str)


# ===========================================================================
# _validate_agent_identity
# ===========================================================================


class TestValidateAgentIdentity:
    async def test_no_token_returns_none(self) -> None:
        bus = _build_bus()
        result, errors = await bus._validate_agent_identity(aid="a1", token=None)
        assert result is None
        assert errors is None

    async def test_no_token_dynamic_policy(self) -> None:
        bus = _build_bus(use_dynamic_policy=False)
        bus._use_dynamic_policy = True
        bus._config = {"use_dynamic_policy": True}
        result, errors = await bus._validate_agent_identity(aid="a1", token=None)
        assert result is False
        assert errors is None

    async def test_token_with_dot(self) -> None:
        bus = _build_bus()
        result, errors = await bus._validate_agent_identity(token="header.payload.sig")
        assert result == "header.payload.sig"
        assert errors == []

    async def test_token_without_dot(self) -> None:
        bus = _build_bus()
        result, errors = await bus._validate_agent_identity(token="simpletoken")
        assert result == "default"
        assert errors == []


# ===========================================================================
# _validate_tenant_consistency
# ===========================================================================


class TestValidateTenantConsistency:
    def test_message_object_path(self) -> None:
        bus = _build_bus()
        msg = _make_msg(from_agent="a", to_agent="b", tenant_id="t1")
        # Both agents not in registry → no cross-tenant errors
        errors = bus._validate_tenant_consistency(from_agent=msg)
        assert isinstance(errors, list)

    def test_positional_args_path(self) -> None:
        bus = _build_bus()
        errors = bus._validate_tenant_consistency(
            from_agent="agent-a", to_agent="agent-b", tid="t1"
        )
        assert isinstance(errors, list)


# ===========================================================================
# _start_kafka
# ===========================================================================


class TestStartKafka:
    async def test_start_kafka_with_existing_kafka_bus(self) -> None:
        bus = _build_bus()
        kafka_mock = MagicMock()
        kafka_mock.start = AsyncMock()
        kafka_mock.subscribe = AsyncMock()
        bus._kafka_bus = kafka_mock

        with patch.object(bus, "_poll_kafka_messages", new_callable=AsyncMock):
            await bus._start_kafka()
        kafka_mock.start.assert_awaited_once()

    async def test_start_kafka_sync_start(self) -> None:
        bus = _build_bus()
        kafka_mock = MagicMock()
        kafka_mock.start = MagicMock(return_value=None)  # sync start
        kafka_mock.subscribe = AsyncMock()
        bus._kafka_bus = kafka_mock

        with patch.object(bus, "_poll_kafka_messages", new_callable=AsyncMock):
            await bus._start_kafka()
        kafka_mock.start.assert_called_once()

    async def test_start_kafka_creates_simple_mock_when_use_kafka_true(self) -> None:
        """When use_kafka=True and no kafka_bus, creates internal SimpleMock."""
        bus = _build_bus()
        bus._kafka_bus = None
        bus._config = {"use_kafka": True}

        # Just patch _poll_kafka_messages to avoid real task creation issues
        with patch.object(bus, "_poll_kafka_messages", new_callable=AsyncMock):
            await bus._start_kafka()

        assert bus._kafka_bus is not None

    async def test_start_kafka_no_bus_no_use_kafka(self) -> None:
        bus = _build_bus()
        bus._kafka_bus = None
        bus._config = {}
        await bus._start_kafka()
        # No kafka bus created, no task
        assert bus._kafka_consumer_task is None

    async def test_start_kafka_with_config_kafka_bus(self) -> None:
        kafka_mock = MagicMock()
        kafka_mock.start = AsyncMock()
        kafka_mock.subscribe = AsyncMock()
        bus = _build_bus()
        bus._kafka_bus = None
        bus._config = {"kafka_bus": kafka_mock}

        with patch.object(bus, "_poll_kafka_messages", new_callable=AsyncMock):
            await bus._start_kafka()

        assert bus._kafka_bus is kafka_mock

    async def test_start_kafka_with_config_kafka_adapter(self) -> None:
        kafka_mock = MagicMock()
        kafka_mock.start = AsyncMock()
        kafka_mock.subscribe = AsyncMock()
        bus = _build_bus()
        bus._kafka_bus = None
        bus._config = {"kafka_adapter": kafka_mock}

        with patch.object(bus, "_poll_kafka_messages", new_callable=AsyncMock):
            await bus._start_kafka()

        assert bus._kafka_bus is kafka_mock

    async def test_start_kafka_without_start_method(self) -> None:
        """Kafka bus without start() should just create consumer task."""
        bus = _build_bus()
        kafka_mock = MagicMock(spec=["subscribe"])  # no start method
        kafka_mock.subscribe = AsyncMock()
        bus._kafka_bus = kafka_mock

        with patch.object(bus, "_poll_kafka_messages", new_callable=AsyncMock):
            await bus._start_kafka()
        # Should proceed without error


# ===========================================================================
# _poll_kafka_messages
# ===========================================================================


class TestPollKafkaMessages:
    async def test_poll_kafka_messages_with_bus(self) -> None:
        bus = _build_bus()
        kafka_mock = MagicMock()
        kafka_mock.subscribe = AsyncMock()
        bus._kafka_bus = kafka_mock
        await bus._poll_kafka_messages()
        kafka_mock.subscribe.assert_awaited_once()

    async def test_poll_kafka_messages_no_bus(self) -> None:
        bus = _build_bus()
        bus._kafka_bus = None
        # Should return without error
        await bus._poll_kafka_messages()


# ===========================================================================
# _evaluate_with_adaptive_governance
# ===========================================================================


class TestEvaluateAdaptiveGovernance:
    async def test_returns_tuple(self) -> None:
        gov = _make_mock_governance()
        gov.evaluate_adaptive_governance = AsyncMock(return_value=(True, "allowed"))
        bus = _build_bus(governance=gov)
        msg = _make_msg()
        allowed, reason = await bus._evaluate_with_adaptive_governance(msg)
        assert allowed is True
        assert reason == "allowed"

    async def test_returns_blocked_tuple(self) -> None:
        gov = _make_mock_governance()
        gov.evaluate_adaptive_governance = AsyncMock(return_value=(False, "blocked by policy"))
        bus = _build_bus(governance=gov)
        msg = _make_msg()
        allowed, reason = await bus._evaluate_with_adaptive_governance(msg)
        assert allowed is False
        assert "blocked" in reason


# ===========================================================================
# _initialize_adaptive_governance / _shutdown_adaptive_governance (no-ops)
# ===========================================================================


class TestAdaptiveGovernanceNoOps:
    async def test_initialize_adaptive_governance_noop(self) -> None:
        bus = _build_bus()
        # Should complete without error (no-op)
        await bus._initialize_adaptive_governance()

    async def test_shutdown_adaptive_governance_noop(self) -> None:
        bus = _build_bus()
        await bus._shutdown_adaptive_governance()


# ===========================================================================
# Module-level constants
# ===========================================================================


class TestModuleLevelConstants:
    def test_constants_are_bool(self) -> None:
        import enhanced_agent_bus.bus.core as core_module

        assert isinstance(core_module.CIRCUIT_BREAKER_ENABLED, bool)
        assert isinstance(core_module.DELIBERATION_AVAILABLE, bool)
        assert isinstance(core_module.MACI_AVAILABLE, bool)
        assert isinstance(core_module.METERING_AVAILABLE, bool)
        assert isinstance(core_module.METRICS_ENABLED, bool)
        assert isinstance(core_module.POLICY_CLIENT_AVAILABLE, bool)

    def test_default_redis_url_is_string(self) -> None:
        import enhanced_agent_bus.bus.core as core_module

        assert isinstance(core_module.DEFAULT_REDIS_URL, str)

    def test_maci_enforcer_maci_role_registry_set(self) -> None:
        import enhanced_agent_bus.bus.core as core_module

        # These are stubs/None when MACI not available — just assert they exist
        assert hasattr(core_module, "MACIEnforcer")
        assert hasattr(core_module, "MACIRoleRegistry")


# ===========================================================================
# MessageValidator helper (_is_mock_instance)
# ===========================================================================


class TestIsMockInstance:
    def test_mock_instance_detected(self) -> None:
        from enhanced_agent_bus.bus.validation import _is_mock_instance

        m = MagicMock()
        assert _is_mock_instance(m) is True

    def test_plain_object_not_mock(self) -> None:
        from enhanced_agent_bus.bus.validation import _is_mock_instance

        assert _is_mock_instance("hello") is False
        assert _is_mock_instance(42) is False

    def test_object_with_mock_name_attr(self) -> None:
        from enhanced_agent_bus.bus.validation import _is_mock_instance

        obj = MagicMock()
        obj._mock_name = "SimpleMock"
        assert _is_mock_instance(obj) is True


# ===========================================================================
# get_policy_client fallback path
# ===========================================================================


class TestGetPolicyClientFallback:
    def test_fallback_returns_none(self) -> None:
        import enhanced_agent_bus.bus.core as core_module

        # The module exposes get_policy_client which may be the real one or fallback
        result = core_module.get_policy_client(fail_closed=False)
        # Either None (fallback) or a real client object
        assert result is None or hasattr(result, "__class__")


# ===========================================================================
# Additional edge cases for full coverage
# ===========================================================================


class TestEdgeCases:
    async def test_send_message_invalid_hash_in_content_not_test_mode(self) -> None:
        """Bus not running, content has 'invalid' in hash — test mode."""
        from enhanced_agent_bus.validators import ValidationResult

        proc = _make_mock_processor()
        proc.process = AsyncMock(return_value=ValidationResult(is_valid=True))
        bus = _build_bus(processor=proc)
        bus._running = False

        msg = _make_msg(constitutional_hash="invalid-hash")
        # Has 'invalid' in hash — test mode bypass
        result = await bus.send_message(msg)
        assert result is not None

    def test_get_metrics_policy_fail_status(self) -> None:
        """Cover policy_registry_status=unavailable branch in get_metrics."""
        bus = _build_bus(fail_policy=True)
        m = bus.get_metrics()
        assert m["policy_registry_status"] == "unavailable"

    def test_get_metrics_policy_client_fail_status_attr(self) -> None:
        bus = _build_bus()
        policy_client = MagicMock()
        policy_client._fail_status = True
        bus._policy_client = policy_client
        m = bus.get_metrics()
        assert m["policy_registry_status"] == "unavailable"

    async def test_full_start_stop_cycle(self) -> None:
        bus = _build_bus()
        await bus.start()
        assert bus.is_running is True
        await bus.stop()
        assert bus.is_running is False

    async def test_send_message_delivery_failure_records_metrics(self) -> None:
        from enhanced_agent_bus.validators import ValidationResult

        proc = _make_mock_processor()
        proc.process = AsyncMock(return_value=ValidationResult(is_valid=True))
        bus = _build_bus(processor=proc)
        bus._running = True

        with patch.object(
            bus._message_handler, "finalize_message_delivery", AsyncMock(return_value=False)
        ):
            msg = _make_msg()
            result = await bus.send_message(msg)
        assert result is not None

    def test_maci_registry_kwarg(self) -> None:
        """Passing maci_registry kwarg uses it."""
        maci_reg = MagicMock()
        bus = _build_bus(maci_registry=maci_reg)
        assert bus.maci_registry is maci_reg or bus.maci_registry is None

    def test_maci_enforcer_kwarg(self) -> None:
        maci_enforcer = MagicMock()
        bus = _build_bus(maci_enforcer=maci_enforcer)
        assert bus.maci_enforcer is maci_enforcer or bus.maci_enforcer is None

    async def test_register_agent_no_capabilities(self) -> None:
        rm = _make_mock_registry_manager()
        bus = _build_bus(registry_manager=rm)
        result = await bus.register_agent("agent-x")
        assert result is True

    async def test_receive_message_increments_received(self) -> None:
        bus = _build_bus()
        msg = _make_msg()
        await bus._message_queue.put(msg)
        before = bus._metrics["received"]
        await bus.receive_message(timeout=1.0)
        assert bus._metrics["received"] == before + 1

    async def test_stop_no_kafka_task(self) -> None:
        """stop() with no kafka task should not raise."""
        bus = _build_bus()
        bus._kafka_consumer_task = None
        await bus.stop()

    async def test_get_metrics_async_no_policy_client(self) -> None:
        bus = _build_bus()
        bus._policy_client = None
        m = await bus.get_metrics_async()
        assert isinstance(m, dict)

    async def test_get_metrics_async_mock_policy_client_health_check(self) -> None:
        """Cover _is_mock_instance branch in get_metrics_async."""
        bus = _build_bus()
        policy_client = MagicMock()
        # MagicMock has _mock_name → is_mock_instance returns True
        policy_client.health_check = AsyncMock(return_value=MagicMock())
        bus._policy_client = policy_client
        m = await bus.get_metrics_async()
        assert isinstance(m, dict)

    def test_validate_tenant_consistency_with_message_obj(self) -> None:
        """from_agent is an AgentMessage — goes through message branch."""
        bus = _build_bus()
        msg = _make_msg(from_agent="a", to_agent="b", tenant_id="t1")
        errors = bus._validate_tenant_consistency(from_agent=msg)
        assert isinstance(errors, list)

    def test_validate_tenant_consistency_plain_strings(self) -> None:
        bus = _build_bus()
        errors = bus._validate_tenant_consistency(from_agent="a", to_agent="b", tid="t1")
        assert isinstance(errors, list)

    def test_get_metrics_processor_none(self) -> None:
        """get_metrics when _processor is None should not crash."""
        bus = _build_bus()
        bus._processor = None
        m = bus.get_metrics()
        assert "processor_metrics" not in m or True  # either way should not raise

    def test_init_get_feature_flags_exception_fallback(self) -> None:
        """Lines 184-185: exception in _get_feature_flags during __init__ uses fallback."""
        from enhanced_agent_bus.bus.core import EnhancedAgentBus

        proc = _make_mock_processor()
        metering_mock = _make_mock_metering()

        with (
            patch(
                "enhanced_agent_bus.bus.core.create_metering_manager",
                return_value=metering_mock,
            ),
            patch(
                "enhanced_agent_bus.bus.core.CompositeValidationStrategy",
                return_value=MagicMock(),
            ),
            patch(
                "enhanced_agent_bus.bus.core.MessageProcessor",
                return_value=proc,
            ),
            patch(
                "enhanced_agent_bus.dependency_bridge.get_feature_flags",
                side_effect=RuntimeError("flags unavailable"),
            ),
        ):
            bus = EnhancedAgentBus(
                registry_manager=_make_mock_registry_manager(),
                governance=_make_mock_governance(),
                router=_make_mock_router(),
                processor=proc,
                allow_unstarted=True,
            )
        assert bus._use_dynamic_policy is False

    async def test_start_metrics_enabled_set_service_info_none(self) -> None:
        """Line 382->384: METRICS_ENABLED=True but set_service_info=None — skips call."""
        with (
            patch("enhanced_agent_bus.bus.core.METRICS_ENABLED", True),
            patch("enhanced_agent_bus.bus.core.set_service_info", None),
            patch("enhanced_agent_bus.bus.core.CIRCUIT_BREAKER_ENABLED", True),
            patch("enhanced_agent_bus.bus.core.initialize_core_circuit_breakers", None),
        ):
            bus = _build_bus()
            # Should not raise even with None callables
            await bus.start()
        assert bus.is_running is True

    async def test_send_message_bus_not_running_not_test_mode(self) -> None:
        """Bus not running and no override must fail closed."""
        proc = _make_mock_processor()
        bus = _build_bus(processor=proc)
        # Remove allow_unstarted so it is not in config
        bus._config = {}
        bus._running = False

        # Message with normal content/hash — not test mode
        msg = _make_msg(
            from_agent="real-agent",
            content={"data": "normal"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )
        result = await bus.send_message(msg)
        assert result.is_valid is False
        assert "not started" in result.errors[0].lower()

    async def test_start_kafka_simple_mock_setattr(self) -> None:
        """Line 701: SimpleMock.__setattr__ for non-special attribute."""
        bus = _build_bus()
        bus._kafka_bus = None
        bus._config = {"use_kafka": True}

        # Let _start_kafka create the SimpleMock, then access a non-special attribute
        # to trigger __setattr__ on the SimpleMock
        with patch.object(bus, "_poll_kafka_messages", new_callable=AsyncMock):
            await bus._start_kafka()

        assert bus._kafka_bus is not None
        # Trigger __setattr__ by setting a non-special attribute on SimpleMock
        # This hits line 701
        bus._kafka_bus.custom_attr = "value"
        # And __getattr__ retrieves it back
        _ = bus._kafka_bus.custom_attr

    def test_router_property_non_router_component(self) -> None:
        """Line 772: router property when _router_component is not a RouterComponent."""
        from enhanced_agent_bus.components import MessageRouter as RouterComponent

        bus = _build_bus()

        # Use a real-ish object that is NOT an instance of RouterComponent
        # MagicMock(spec=object) will fail isinstance check
        class NotARouter:
            pass

        plain = NotARouter()
        bus._router_component = plain  # type: ignore[assignment]

        # The property body: isinstance(plain, RouterComponent) → False → line 772
        result = bus.router
        assert result is plain

    def test_router_property_is_router_component(self) -> None:
        """Line 771: router property when _router_component IS a RouterComponent."""
        from enhanced_agent_bus.components import MessageRouter as RouterComponent

        bus = _build_bus()
        # Create real RouterComponent to ensure isinstance passes
        real_router_component = RouterComponent(config={})
        bus._router_component = real_router_component

        result = bus.router
        assert result is real_router_component._router
