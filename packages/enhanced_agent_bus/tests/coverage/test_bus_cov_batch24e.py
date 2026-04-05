"""
Coverage tests for:
- message_processor.py
- decision_store.py
- interfaces.py
- registry.py

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from enhanced_agent_bus.models import (
    CONSTITUTIONAL_HASH,
    AgentMessage,
    AutonomyTier,
    MessageStatus,
    MessageType,
    Priority,
)
from enhanced_agent_bus.validators import ValidationResult

# ============================================================================
# Helpers
# ============================================================================


def _msg(
    *,
    from_agent: str = "agent-a",
    to_agent: str = "agent-b",
    message_type: MessageType = MessageType.QUERY,
    content: object = "test content",
    priority: Priority = Priority.NORMAL,
    tenant_id: str | None = None,
    autonomy_tier: AutonomyTier | None = None,
    metadata: dict | None = None,
    impact_score: float | None = None,
) -> AgentMessage:
    kwargs: dict = {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "message_type": message_type,
        "content": content,
        "priority": priority,
    }
    if tenant_id is not None:
        kwargs["tenant_id"] = tenant_id
    if autonomy_tier is not None:
        kwargs["autonomy_tier"] = autonomy_tier
    if metadata is not None:
        kwargs["metadata"] = metadata
    msg = AgentMessage(**kwargs)
    if impact_score is not None:
        msg.impact_score = impact_score
    return msg


# ============================================================================
# interfaces.py — Protocol isinstance checks and concrete impls
# ============================================================================


class TestInterfaceProtocols:
    """Test runtime_checkable protocol behaviour from interfaces.py."""

    def test_agent_registry_protocol_isinstance(self):
        from enhanced_agent_bus.interfaces import AgentRegistry

        class _Impl:
            async def register(self, agent_id, capabilities=None, metadata=None):
                return True

            async def unregister(self, agent_id):
                return True

            async def get(self, agent_id):
                return None

            async def list_agents(self):
                return []

            async def exists(self, agent_id):
                return False

            async def update_metadata(self, agent_id, metadata):
                return False

        assert isinstance(_Impl(), AgentRegistry)

    def test_message_router_protocol_isinstance(self):
        from enhanced_agent_bus.interfaces import MessageRouter

        class _Impl:
            async def route(self, message, registry):
                return None

            async def broadcast(self, message, registry, exclude=None):
                return []

        assert isinstance(_Impl(), MessageRouter)

    def test_validation_strategy_protocol_isinstance(self):
        from enhanced_agent_bus.interfaces import ValidationStrategy

        class _Impl:
            async def validate(self, message):
                return (True, None)

        assert isinstance(_Impl(), ValidationStrategy)

    def test_processing_strategy_protocol_isinstance(self):
        from enhanced_agent_bus.interfaces import ProcessingStrategy

        class _Impl:
            async def process(self, message, handlers):
                return None

            def is_available(self):
                return True

            def get_name(self):
                return "test"

        assert isinstance(_Impl(), ProcessingStrategy)

    def test_message_handler_protocol_isinstance(self):
        from enhanced_agent_bus.interfaces import MessageHandler

        class _Impl:
            async def handle(self, message):
                return None

            def can_handle(self, message):
                return True

        assert isinstance(_Impl(), MessageHandler)

    def test_metrics_collector_protocol_isinstance(self):
        from enhanced_agent_bus.interfaces import MetricsCollector

        class _Impl:
            def record_message_processed(self, message_type, duration_ms, success):
                pass

            def record_agent_registered(self, agent_id):
                pass

            def record_agent_unregistered(self, agent_id):
                pass

            def get_metrics(self):
                return {}

        assert isinstance(_Impl(), MetricsCollector)

    def test_message_processor_protocol_isinstance(self):
        from enhanced_agent_bus.interfaces import MessageProcessorProtocol

        class _Impl:
            async def process(self, message):
                return None

        assert isinstance(_Impl(), MessageProcessorProtocol)

    def test_maci_registry_protocol_isinstance(self):
        from enhanced_agent_bus.interfaces import MACIRegistryProtocol

        class _Impl:
            def register_agent(self, agent_id, role):
                return True

            def get_role(self, agent_id):
                return None

            def unregister_agent(self, agent_id):
                return True

        assert isinstance(_Impl(), MACIRegistryProtocol)

    def test_maci_enforcer_protocol_isinstance(self):
        from enhanced_agent_bus.interfaces import MACIEnforcerProtocol

        class _Impl:
            async def validate_action(self, agent_id, action, target_output_id=None):
                return {}

        assert isinstance(_Impl(), MACIEnforcerProtocol)

    def test_transport_protocol_isinstance(self):
        from enhanced_agent_bus.interfaces import TransportProtocol

        class _Impl:
            async def start(self):
                pass

            async def stop(self):
                pass

            async def send(self, message, topic=None):
                return True

            async def subscribe(self, topic, handler):
                pass

        assert isinstance(_Impl(), TransportProtocol)

    def test_orchestrator_protocol_isinstance(self):
        from enhanced_agent_bus.interfaces import OrchestratorProtocol

        class _Impl:
            async def start(self):
                pass

            async def stop(self):
                pass

            def get_status(self):
                return {}

        assert isinstance(_Impl(), OrchestratorProtocol)

    def test_circuit_breaker_protocol_isinstance(self):
        from enhanced_agent_bus.interfaces import CircuitBreakerProtocol

        class _Impl:
            async def record_success(self):
                pass

            async def record_failure(self, error=None, error_type="unknown"):
                pass

            async def can_execute(self):
                return True

            async def reset(self):
                pass

        assert isinstance(_Impl(), CircuitBreakerProtocol)

    def test_policy_validation_result_protocol(self):
        from enhanced_agent_bus.interfaces import PolicyValidationResultProtocol

        class _Impl:
            @property
            def is_valid(self):
                return True

            @property
            def errors(self):
                return []

        assert isinstance(_Impl(), PolicyValidationResultProtocol)

    def test_policy_client_protocol(self):
        from enhanced_agent_bus.interfaces import PolicyClientProtocol

        class _Impl:
            async def validate_message_signature(self, message):
                return MagicMock(is_valid=True, errors=[])

        assert isinstance(_Impl(), PolicyClientProtocol)

    def test_opa_client_protocol(self):
        from enhanced_agent_bus.interfaces import OPAClientProtocol

        class _Impl:
            async def validate_constitutional(self, message):
                return MagicMock(is_valid=True, errors=[])

        assert isinstance(_Impl(), OPAClientProtocol)

    def test_validation_result_protocol(self):
        from enhanced_agent_bus.interfaces import ValidationResultProtocol

        class _Impl:
            @property
            def is_valid(self):
                return False

            @property
            def errors(self):
                return ["err"]

        assert isinstance(_Impl(), ValidationResultProtocol)

    def test_rust_processor_protocol(self):
        from enhanced_agent_bus.interfaces import RustProcessorProtocol

        class _Impl:
            def validate(self, message):
                return True

        assert isinstance(_Impl(), RustProcessorProtocol)

    def test_pqc_validator_protocol(self):
        from enhanced_agent_bus.interfaces import PQCValidatorProtocol

        class _Impl:
            def verify_governance_decision(self, decision, signature, public_key):
                return True

        assert isinstance(_Impl(), PQCValidatorProtocol)

    def test_constitutional_verifier_protocol(self):
        from enhanced_agent_bus.interfaces import ConstitutionalVerifierProtocol

        class _Impl:
            async def verify_constitutional_compliance(self, action_data, context, session_id=None):
                return MagicMock(is_valid=True, failure_reason=None)

        assert isinstance(_Impl(), ConstitutionalVerifierProtocol)

    def test_constitutional_verification_result_protocol(self):
        from enhanced_agent_bus.interfaces import ConstitutionalVerificationResultProtocol

        class _Impl:
            @property
            def is_valid(self):
                return True

            @property
            def failure_reason(self):
                return None

        assert isinstance(_Impl(), ConstitutionalVerificationResultProtocol)

    def test_constitutional_hash_validator_protocol(self):
        from enhanced_agent_bus.interfaces import ConstitutionalHashValidatorProtocol

        class _Impl:
            async def validate_hash(self, *, provided_hash, expected_hash, context=None):
                return (True, "")

        assert isinstance(_Impl(), ConstitutionalHashValidatorProtocol)

    def test_governance_decision_validator_protocol(self):
        from enhanced_agent_bus.interfaces import GovernanceDecisionValidatorProtocol

        class _Impl:
            async def validate_decision(self, *, decision, context):
                return (True, [])

        assert isinstance(_Impl(), GovernanceDecisionValidatorProtocol)

    def test_approvals_validator_protocol(self):
        from enhanced_agent_bus.interfaces import ApprovalsValidatorProtocol

        class _Impl:
            def validate_approvals(self, *, policy, decisions, approvers, requester_id):
                return (True, "ok")

        assert isinstance(_Impl(), ApprovalsValidatorProtocol)

    def test_recommendation_planner_protocol(self):
        from enhanced_agent_bus.interfaces import RecommendationPlannerProtocol

        class _Impl:
            def generate_recommendations(self, *, judgment, decision):
                return []

        assert isinstance(_Impl(), RecommendationPlannerProtocol)

    def test_role_matrix_validator_protocol(self):
        from enhanced_agent_bus.interfaces import RoleMatrixValidatorProtocol

        class _Impl:
            def validate(self, *, violations, strict_mode):
                pass

        assert isinstance(_Impl(), RoleMatrixValidatorProtocol)

    def test_all_exports_exist(self):
        """Verify __all__ exports are importable."""
        import enhanced_agent_bus.interfaces as ifaces

        for name in ifaces.__all__:
            assert hasattr(ifaces, name), f"Missing export: {name}"


# ============================================================================
# registry.py — InMemoryAgentRegistry
# ============================================================================


class TestInMemoryAgentRegistry:
    """Tests for InMemoryAgentRegistry."""

    async def test_register_and_get(self):
        from enhanced_agent_bus.registry import InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        assert await reg.register("a1", capabilities=["cap1"], metadata={"k": "v"})
        info = await reg.get("a1")
        assert info is not None
        assert info["agent_id"] == "a1"
        assert "cap1" in info["capabilities"]
        assert info["metadata"]["k"] == "v"
        assert info["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_register_duplicate_returns_false(self):
        from enhanced_agent_bus.registry import InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        assert await reg.register("a1")
        assert not await reg.register("a1")

    async def test_unregister(self):
        from enhanced_agent_bus.registry import InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        assert await reg.unregister("a1")
        assert not await reg.unregister("a1")
        assert await reg.get("a1") is None

    async def test_list_agents(self):
        from enhanced_agent_bus.registry import InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        await reg.register("a2")
        agents = await reg.list_agents()
        assert set(agents) == {"a1", "a2"}

    async def test_exists(self):
        from enhanced_agent_bus.registry import InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        assert await reg.exists("a1")
        assert not await reg.exists("nonexistent")

    async def test_update_metadata(self):
        from enhanced_agent_bus.registry import InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("a1", metadata={"old": True})
        assert await reg.update_metadata("a1", {"new_key": "val"})
        info = await reg.get("a1")
        assert info["metadata"]["new_key"] == "val"
        assert info["metadata"]["old"] is True
        assert "updated_at" in info

    async def test_update_metadata_nonexistent_returns_false(self):
        from enhanced_agent_bus.registry import InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        assert not await reg.update_metadata("ghost", {"k": "v"})

    async def test_clear(self):
        from enhanced_agent_bus.registry import InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        await reg.clear()
        assert reg.agent_count == 0

    async def test_agent_count_property(self):
        from enhanced_agent_bus.registry import InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        assert reg.agent_count == 0
        await reg.register("a1")
        assert reg.agent_count == 1

    async def test_register_with_defaults(self):
        from enhanced_agent_bus.registry import InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        assert await reg.register("a1")
        info = await reg.get("a1")
        assert info["capabilities"] == []
        assert info["metadata"] == {}


# ============================================================================
# registry.py — DirectMessageRouter
# ============================================================================


class TestDirectMessageRouter:
    """Tests for DirectMessageRouter."""

    async def test_route_to_registered_agent(self):
        from enhanced_agent_bus.registry import DirectMessageRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        # Register with matching tenant_id metadata so router tenant check passes
        await reg.register("target-1", metadata={"tenant_id": "default"})
        router = DirectMessageRouter()
        msg = _msg(from_agent="sender", to_agent="target-1")
        result = await router.route(msg, reg)
        assert result == "target-1"

    async def test_route_no_target(self):
        from enhanced_agent_bus.registry import DirectMessageRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        router = DirectMessageRouter()
        msg = _msg(to_agent="")
        result = await router.route(msg, reg)
        assert result is None

    async def test_route_target_not_registered(self):
        from enhanced_agent_bus.registry import DirectMessageRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        router = DirectMessageRouter()
        msg = _msg(to_agent="ghost")
        result = await router.route(msg, reg)
        assert result is None

    async def test_route_tenant_mismatch(self):
        from enhanced_agent_bus.registry import DirectMessageRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("target-1", metadata={"tenant_id": "tenant-A"})
        router = DirectMessageRouter()
        msg = _msg(to_agent="target-1", tenant_id="tenant-B")
        result = await router.route(msg, reg)
        assert result is None

    async def test_broadcast_excludes_sender(self):
        from enhanced_agent_bus.registry import DirectMessageRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        await reg.register("a2")
        await reg.register("sender")
        router = DirectMessageRouter()
        msg = _msg(from_agent="sender")
        result = await router.broadcast(msg, reg)
        assert "sender" not in result
        assert set(result) == {"a1", "a2"}

    async def test_broadcast_with_exclude_list(self):
        from enhanced_agent_bus.registry import DirectMessageRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        await reg.register("a2")
        await reg.register("a3")
        router = DirectMessageRouter()
        msg = _msg(from_agent="external")
        result = await router.broadcast(msg, reg, exclude=["a2"])
        assert "a2" not in result


# ============================================================================
# registry.py — CapabilityBasedRouter
# ============================================================================


class TestCapabilityBasedRouter:
    """Tests for CapabilityBasedRouter."""

    async def test_route_direct_target(self):
        from enhanced_agent_bus.registry import CapabilityBasedRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("target-1")
        router = CapabilityBasedRouter()
        msg = _msg(to_agent="target-1")
        result = await router.route(msg, reg)
        assert result == "target-1"

    async def test_route_by_capability(self):
        from enhanced_agent_bus.registry import CapabilityBasedRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("a1", capabilities=["analyze", "report"])
        await reg.register("a2", capabilities=["report"])
        router = CapabilityBasedRouter()
        msg = _msg(content={"required_capabilities": ["analyze"]})
        result = await router.route(msg, reg)
        assert result == "a1"

    async def test_route_no_capability_match(self):
        from enhanced_agent_bus.registry import CapabilityBasedRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("a1", capabilities=["report"])
        router = CapabilityBasedRouter()
        msg = _msg(content={"required_capabilities": ["unavailable_cap"]})
        result = await router.route(msg, reg)
        assert result is None

    async def test_route_no_required_caps(self):
        from enhanced_agent_bus.registry import CapabilityBasedRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        router = CapabilityBasedRouter()
        msg = _msg(content="plain string")
        result = await router.route(msg, reg)
        assert result is None

    async def test_broadcast_filters_by_capability(self):
        from enhanced_agent_bus.registry import CapabilityBasedRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("a1", capabilities=["cap_x"])
        await reg.register("a2", capabilities=["cap_y"])
        router = CapabilityBasedRouter()
        msg = _msg(
            from_agent="external",
            content={"required_capabilities": ["cap_x"]},
        )
        result = await router.broadcast(msg, reg)
        assert "a1" in result
        assert "a2" not in result

    async def test_broadcast_no_caps_returns_all(self):
        from enhanced_agent_bus.registry import CapabilityBasedRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("a1", capabilities=["c1"])
        await reg.register("a2", capabilities=["c2"])
        router = CapabilityBasedRouter()
        msg = _msg(from_agent="external", content="no caps")
        result = await router.broadcast(msg, reg)
        assert set(result) == {"a1", "a2"}

    async def test_broadcast_excludes(self):
        from enhanced_agent_bus.registry import CapabilityBasedRouter, InMemoryAgentRegistry

        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        await reg.register("a2")
        router = CapabilityBasedRouter()
        msg = _msg(from_agent="external", content="no caps")
        result = await router.broadcast(msg, reg, exclude=["a1"])
        assert "a1" not in result


# ============================================================================
# registry.py — RedisAgentRegistry
# ============================================================================


class TestRedisAgentRegistry:
    """Tests for RedisAgentRegistry using mocked redis."""

    async def test_get_client_creates_pool(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        mock_redis_cls = MagicMock()
        mock_pool_cls = MagicMock()
        mock_pool_cls.from_url.return_value = MagicMock()
        mock_redis_instance = MagicMock()
        mock_redis_cls.return_value = mock_redis_instance

        reg = RedisAgentRegistry(redis_url="redis://test:6379")

        with patch.dict(
            "sys.modules",
            {
                "redis": MagicMock(),
                "redis.asyncio": MagicMock(
                    ConnectionPool=mock_pool_cls,
                    Redis=mock_redis_cls,
                ),
            },
        ):
            client = await reg._get_client()
            assert client is not None

    async def test_register_calls_hsetnx(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        reg = RedisAgentRegistry(redis_url="redis://test:6379")
        mock_client = AsyncMock()
        mock_client.hsetnx = AsyncMock(return_value=1)
        reg._redis = mock_client

        result = await reg.register("agent-1", caps=["c1"], meta={"k": "v"})
        assert result is True
        mock_client.hsetnx.assert_awaited_once()

    async def test_unregister_calls_hdel(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        reg = RedisAgentRegistry(redis_url="redis://test:6379")
        mock_client = AsyncMock()
        mock_client.hdel = AsyncMock(return_value=1)
        reg._redis = mock_client

        result = await reg.unregister("agent-1")
        assert result is True

    async def test_get_returns_parsed_json(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        reg = RedisAgentRegistry(redis_url="redis://test:6379")
        mock_client = AsyncMock()
        mock_client.hget = AsyncMock(
            return_value=json.dumps({"agent_id": "a1", "capabilities": []})
        )
        reg._redis = mock_client

        result = await reg.get("a1")
        assert result["agent_id"] == "a1"

    async def test_get_returns_none_for_missing(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        reg = RedisAgentRegistry(redis_url="redis://test:6379")
        mock_client = AsyncMock()
        mock_client.hget = AsyncMock(return_value=None)
        reg._redis = mock_client

        result = await reg.get("nonexistent")
        assert result is None

    async def test_list_agents(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        reg = RedisAgentRegistry(redis_url="redis://test:6379")
        mock_client = AsyncMock()
        mock_client.hkeys = AsyncMock(return_value=["a1", "a2"])
        reg._redis = mock_client

        result = await reg.list_agents()
        assert result == ["a1", "a2"]

    async def test_exists(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        reg = RedisAgentRegistry(redis_url="redis://test:6379")
        mock_client = AsyncMock()
        mock_client.hexists = AsyncMock(return_value=True)
        reg._redis = mock_client

        assert await reg.exists("a1")

    async def test_update_metadata_existing(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        reg = RedisAgentRegistry(redis_url="redis://test:6379")
        mock_client = AsyncMock()
        existing = json.dumps({"agent_id": "a1", "metadata": {"old": True}})
        mock_client.hget = AsyncMock(return_value=existing)
        mock_client.hset = AsyncMock()
        reg._redis = mock_client

        assert await reg.update_metadata("a1", {"new_key": "val"})
        mock_client.hset.assert_awaited_once()

    async def test_update_metadata_nonexistent(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        reg = RedisAgentRegistry(redis_url="redis://test:6379")
        mock_client = AsyncMock()
        mock_client.hget = AsyncMock(return_value=None)
        reg._redis = mock_client

        assert not await reg.update_metadata("ghost", {"k": "v"})

    async def test_clear(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        reg = RedisAgentRegistry(redis_url="redis://test:6379")
        mock_client = AsyncMock()
        mock_client.delete = AsyncMock()
        reg._redis = mock_client

        await reg.clear()
        mock_client.delete.assert_awaited_once()

    async def test_close(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        reg = RedisAgentRegistry(redis_url="redis://test:6379")
        mock_client = AsyncMock()
        mock_pool = AsyncMock()
        reg._redis = mock_client
        reg._pool = mock_pool

        await reg.close()
        mock_client.close.assert_awaited_once()
        mock_pool.disconnect.assert_awaited_once()
        assert reg._redis is None
        assert reg._pool is None

    async def test_close_when_not_connected(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        reg = RedisAgentRegistry(redis_url="redis://test:6379")
        await reg.close()  # Should not raise

    def test_agent_count_returns_negative_one(self):
        from enhanced_agent_bus.registry import RedisAgentRegistry

        reg = RedisAgentRegistry(redis_url="redis://test:6379")
        assert reg.agent_count == -1


# ============================================================================
# decision_store.py — DecisionStore (memory fallback)
# ============================================================================


class TestDecisionStoreMemoryFallback:
    """Tests for DecisionStore in-memory fallback mode."""

    def _make_store(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        store = DecisionStore(ttl_seconds=300, enable_metrics=True)
        store._initialized = True
        store._use_memory_fallback = True
        return store

    def _mock_explanation(self, decision_id="d1", tenant_id="t1", message_id="m1"):
        expl = MagicMock()
        expl.decision_id = decision_id
        expl.tenant_id = tenant_id
        expl.message_id = message_id
        expl.model_dump_json.return_value = json.dumps(
            {
                "decision_id": decision_id,
                "tenant_id": tenant_id,
                "message_id": message_id,
            }
        )
        return expl

    async def test_store_and_get_memory_fallback(self):
        store = self._make_store()
        expl = self._mock_explanation()
        assert await store.store(expl)
        assert store._metrics["total_stores"] == 1

    async def test_store_creates_message_index(self):
        store = self._make_store()
        expl = self._mock_explanation(message_id="msg-99")
        await store.store(expl)
        assert len(store._memory_indexes) == 1

    async def test_store_no_message_id(self):
        store = self._make_store()
        expl = self._mock_explanation()
        expl.message_id = None
        assert await store.store(expl)
        assert len(store._memory_indexes) == 0

    async def test_get_cache_hit(self):
        store = self._make_store()
        key = store._make_key("t1", "d1")
        store._memory_store[key] = json.dumps({"decision_id": "d1"})
        with patch("enhanced_agent_bus.decision_store.DecisionExplanationV1", None):
            result = await store.get("d1", "t1")
        assert result is not None
        assert store._metrics["cache_hits"] == 1

    async def test_get_cache_miss(self):
        store = self._make_store()
        result = await store.get("nonexistent", "t1")
        assert result is None
        assert store._metrics["cache_misses"] == 1

    async def test_get_by_message_id_found(self):
        store = self._make_store()
        expl = self._mock_explanation(decision_id="d1", tenant_id="t1", message_id="m1")
        await store.store(expl)

        with patch("enhanced_agent_bus.decision_store.DecisionExplanationV1", None):
            result = await store.get_by_message_id("m1", "t1")
        assert result is not None

    async def test_get_by_message_id_not_found(self):
        store = self._make_store()
        result = await store.get_by_message_id("missing", "t1")
        assert result is None

    async def test_delete_existing(self):
        store = self._make_store()
        expl = self._mock_explanation()
        await store.store(expl)
        assert await store.delete("d1", "t1")
        assert store._metrics["total_deletes"] == 1

    async def test_delete_nonexistent(self):
        store = self._make_store()
        assert not await store.delete("ghost", "t1")

    async def test_delete_cleans_message_indexes(self):
        store = self._make_store()
        expl = self._mock_explanation()
        await store.store(expl)
        await store.delete("d1", "t1")
        assert len(store._memory_indexes) == 0

    async def test_list_decisions_memory(self):
        store = self._make_store()
        for i in range(5):
            expl = self._mock_explanation(decision_id=f"d{i}")
            await store.store(expl)
        result = await store.list_decisions("t1")
        assert len(result) == 5

    async def test_list_decisions_with_offset_and_limit(self):
        store = self._make_store()
        for i in range(10):
            expl = self._mock_explanation(decision_id=f"d{i}")
            await store.store(expl)
        result = await store.list_decisions("t1", limit=3, offset=2)
        assert len(result) <= 3

    async def test_exists_memory(self):
        store = self._make_store()
        expl = self._mock_explanation()
        await store.store(expl)
        assert await store.exists("d1", "t1")
        assert not await store.exists("ghost", "t1")

    async def test_get_ttl_memory_existing(self):
        store = self._make_store()
        expl = self._mock_explanation()
        await store.store(expl)
        ttl = await store.get_ttl("d1", "t1")
        assert ttl == 300

    async def test_get_ttl_memory_nonexistent(self):
        store = self._make_store()
        ttl = await store.get_ttl("ghost", "t1")
        assert ttl == -2

    async def test_extend_ttl_memory(self):
        store = self._make_store()
        expl = self._mock_explanation()
        await store.store(expl)
        assert await store.extend_ttl("d1", "t1")
        assert not await store.extend_ttl("ghost", "t1")

    def test_get_metrics(self):
        store = self._make_store()
        metrics = store.get_metrics()
        assert metrics["cache_hit_rate"] == 0.0
        assert metrics["avg_latency_ms"] == 0.0
        assert metrics["constitutional_hash"] == store.constitutional_hash

    def test_get_metrics_with_data(self):
        store = self._make_store()
        store._metrics["total_stores"] = 5
        store._metrics["total_retrievals"] = 10
        store._metrics["cache_hits"] = 7
        store._metrics["total_latency_ms"] = 50.0
        metrics = store.get_metrics()
        assert metrics["cache_hit_rate"] == 70.0
        assert metrics["avg_latency_ms"] > 0

    async def test_health_check_memory_fallback(self):
        store = self._make_store()
        health = await store.health_check()
        assert health["healthy"] is True
        assert health["using_memory_fallback"] is True

    async def test_close_clears_state(self):
        store = self._make_store()
        expl = self._mock_explanation()
        await store.store(expl)
        await store.close()
        assert not store._initialized
        assert len(store._memory_store) == 0
        assert len(store._memory_indexes) == 0

    def test_make_key(self):
        store = self._make_store()
        key = store._make_key("tenant:1", "decision-1")
        assert "tenant_1" in key
        assert "decision-1" in key

    def test_make_key_default_tenant(self):
        store = self._make_store()
        key = store._make_key("", "d1")
        assert "default" in key

    def test_make_message_index_key(self):
        store = self._make_store()
        key = store._make_message_index_key("t1", "msg-1")
        assert "msg" in key
        assert "t1" in key

    def test_make_time_index_key(self):
        store = self._make_store()
        key = store._make_time_index_key("t1", "2024-01-01")
        assert "time" in key


# ============================================================================
# decision_store.py — Initialize and singleton
# ============================================================================


class TestDecisionStoreInit:
    """Tests for DecisionStore initialization paths."""

    async def test_initialize_already_initialized(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        store = DecisionStore()
        store._initialized = True
        assert await store.initialize()

    async def test_initialize_no_redis_available(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        store = DecisionStore()
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
            assert await store.initialize()
            assert store._use_memory_fallback is True

    async def test_initialize_redis_unhealthy(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        mock_pool = AsyncMock()
        mock_pool.health_check = AsyncMock(return_value={"healthy": False, "error": "timeout"})
        store = DecisionStore(redis_pool=mock_pool)
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", True):
            assert await store.initialize()
            assert store._use_memory_fallback is True

    async def test_initialize_redis_healthy(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        mock_pool = AsyncMock()
        mock_pool.health_check = AsyncMock(return_value={"healthy": True})
        store = DecisionStore(redis_pool=mock_pool)
        with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", True):
            assert await store.initialize()
            assert store._use_memory_fallback is False

    async def test_initialize_redis_raises(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        store = DecisionStore()
        with (
            patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", True),
            patch("enhanced_agent_bus.decision_store.get_shared_pool", side_effect=OSError("fail")),
        ):
            assert await store.initialize()
            assert store._use_memory_fallback is True

    async def test_health_check_with_redis_pool(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        mock_pool = AsyncMock()
        mock_pool.health_check = AsyncMock(return_value={"healthy": True})
        store = DecisionStore(redis_pool=mock_pool)
        store._initialized = True
        store._use_memory_fallback = False
        health = await store.health_check()
        assert health["redis_healthy"] is True

    async def test_health_check_with_unhealthy_redis(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        mock_pool = AsyncMock()
        mock_pool.health_check = AsyncMock(return_value={"healthy": False, "error": "conn refused"})
        store = DecisionStore(redis_pool=mock_pool)
        store._initialized = True
        store._use_memory_fallback = False
        health = await store.health_check()
        assert health["redis_healthy"] is False
        assert "redis_error" in health

    async def test_store_error_handling(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        store = DecisionStore()
        store._initialized = True
        store._use_memory_fallback = True
        expl = MagicMock()
        expl.model_dump_json.side_effect = TypeError("serialize error")
        assert not await store.store(expl)
        assert store._metrics["failed_operations"] == 1

    async def test_get_error_handling(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        store = DecisionStore()
        store._initialized = True
        store._use_memory_fallback = False
        store._pool = MagicMock()
        store._pool.acquire = MagicMock(side_effect=OSError("conn error"))
        result = await store.get("d1", "t1")
        assert result is None
        assert store._metrics["failed_operations"] == 1

    async def test_get_by_message_id_error_handling(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        store = DecisionStore()
        store._initialized = True
        store._use_memory_fallback = False
        store._pool = MagicMock()
        store._pool.acquire = MagicMock(side_effect=RuntimeError("fail"))
        result = await store.get_by_message_id("m1", "t1")
        assert result is None
        assert store._metrics["failed_operations"] == 1

    async def test_delete_error_handling(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        store = DecisionStore()
        store._initialized = True
        store._use_memory_fallback = False
        store._pool = MagicMock()
        store._pool.acquire = MagicMock(side_effect=ConnectionError("fail"))
        assert not await store.delete("d1", "t1")
        assert store._metrics["failed_operations"] == 1

    async def test_list_decisions_error_handling(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        store = DecisionStore()
        store._initialized = True
        store._use_memory_fallback = False
        store._pool = MagicMock()
        store._pool.acquire = MagicMock(side_effect=ValueError("fail"))
        result = await store.list_decisions("t1")
        assert result == []

    async def test_exists_error_handling(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        store = DecisionStore()
        store._initialized = True
        store._use_memory_fallback = False
        store._pool = MagicMock()
        store._pool.acquire = MagicMock(side_effect=TypeError("fail"))
        assert not await store.exists("d1", "t1")

    async def test_get_ttl_error_handling(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        store = DecisionStore()
        store._initialized = True
        store._use_memory_fallback = False
        store._pool = MagicMock()
        store._pool.acquire = MagicMock(side_effect=RuntimeError("fail"))
        assert await store.get_ttl("d1", "t1") == -2

    async def test_extend_ttl_error_handling(self):
        from enhanced_agent_bus.decision_store import DecisionStore

        store = DecisionStore()
        store._initialized = True
        store._use_memory_fallback = False
        store._pool = MagicMock()
        store._pool.acquire = MagicMock(side_effect=OSError("fail"))
        assert not await store.extend_ttl("d1", "t1")


class TestDecisionStoreSingleton:
    """Tests for get_decision_store / reset_decision_store."""

    async def test_get_and_reset(self):
        import enhanced_agent_bus.decision_store as ds_mod

        original = ds_mod._decision_store
        try:
            ds_mod._decision_store = None
            with patch("enhanced_agent_bus.decision_store.REDIS_AVAILABLE", False):
                store = await ds_mod.get_decision_store()
                assert store._initialized
                same_store = await ds_mod.get_decision_store()
                assert same_store is store
                await ds_mod.reset_decision_store()
                assert ds_mod._decision_store is None
        finally:
            ds_mod._decision_store = original

    async def test_reset_when_none(self):
        import enhanced_agent_bus.decision_store as ds_mod

        original = ds_mod._decision_store
        try:
            ds_mod._decision_store = None
            await ds_mod.reset_decision_store()  # Should not raise
        finally:
            ds_mod._decision_store = original


# ============================================================================
# message_processor.py — MessageProcessor
# ============================================================================


class TestMessageProcessor:
    """Tests for MessageProcessor."""

    def _make_processor(self, **kwargs):
        defaults = {
            "isolated_mode": True,
        }
        defaults.update(kwargs)
        from enhanced_agent_bus.message_processor import MessageProcessor

        return MessageProcessor(**defaults)

    def test_constructor_isolated_mode(self):
        proc = self._make_processor()
        assert proc._isolated_mode is True
        assert proc.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constructor_invalid_cache_hash_mode(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        with pytest.raises(ValueError, match="Invalid cache_hash_mode"):
            MessageProcessor(isolated_mode=True, cache_hash_mode="bogus")

    def test_register_and_unregister_handler(self):
        proc = self._make_processor()

        async def handler(msg):
            return None

        proc.register_handler(MessageType.QUERY, handler)
        assert MessageType.QUERY in proc._handlers
        assert handler in proc._handlers[MessageType.QUERY]

        assert proc.unregister_handler(MessageType.QUERY, handler)
        assert handler not in proc._handlers[MessageType.QUERY]

    def test_unregister_handler_not_found(self):
        proc = self._make_processor()

        async def handler(msg):
            return None

        assert not proc.unregister_handler(MessageType.QUERY, handler)

    def test_processed_and_failed_count(self):
        proc = self._make_processor()
        assert proc.processed_count == 0
        assert proc.failed_count == 0

    def test_processing_strategy_property(self):
        proc = self._make_processor()
        assert proc.processing_strategy is not None

    def test_opa_client_property_isolated(self):
        proc = self._make_processor()
        assert proc.opa_client is None

    def test_get_metrics(self):
        proc = self._make_processor()
        metrics = proc.get_metrics()
        assert "processed_count" in metrics
        assert "failed_count" in metrics
        assert "success_rate" in metrics
        assert metrics["processed_count"] == 0
        assert metrics["pqc_enabled"] is not None

    def test_set_strategy(self):
        proc = self._make_processor()
        mock_strategy = MagicMock()
        proc._set_strategy(mock_strategy)
        assert proc.processing_strategy is mock_strategy

    def test_get_compliance_tags_approved(self):
        proc = self._make_processor()
        msg = _msg()
        result = ValidationResult(is_valid=True)
        tags = proc._get_compliance_tags(msg, result)
        assert "constitutional_validated" in tags
        assert "approved" in tags

    def test_get_compliance_tags_rejected(self):
        proc = self._make_processor()
        msg = _msg()
        result = ValidationResult(is_valid=False)
        tags = proc._get_compliance_tags(msg, result)
        assert "rejected" in tags

    def test_get_compliance_tags_high_priority(self):
        proc = self._make_processor()
        msg = _msg(priority=Priority.CRITICAL)
        result = ValidationResult(is_valid=True)
        tags = proc._get_compliance_tags(msg, result)
        assert "high_priority" in tags

    def test_log_decision_with_span(self):
        proc = self._make_processor()
        msg = _msg()
        result = ValidationResult(is_valid=True)
        mock_span = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.trace_id = 12345
        mock_span.get_span_context.return_value = mock_ctx
        proc._log_decision(msg, result, span=mock_span)
        mock_span.set_attribute.assert_called()

    def test_log_decision_no_span(self):
        proc = self._make_processor()
        msg = _msg()
        result = ValidationResult(is_valid=True)
        proc._log_decision(msg, result)  # Should not raise

    def test_requires_independent_validation_high_impact(self):
        proc = self._make_processor()
        msg = _msg(impact_score=0.95)
        assert proc._requires_independent_validation(msg)

    def test_requires_independent_validation_governance_type(self):
        proc = self._make_processor()
        msg = _msg(message_type=MessageType.GOVERNANCE_REQUEST)
        assert proc._requires_independent_validation(msg)

    def test_requires_independent_validation_low_impact_query(self):
        proc = self._make_processor()
        msg = _msg(message_type=MessageType.QUERY, impact_score=0.1)
        assert not proc._requires_independent_validation(msg)

    def test_requires_independent_validation_none_impact(self):
        proc = self._make_processor()
        msg = _msg(message_type=MessageType.QUERY)
        msg.impact_score = None
        assert not proc._requires_independent_validation(msg)

    def test_enforce_independent_validator_gate_disabled(self):
        proc = self._make_processor()
        proc._require_independent_validator = False
        msg = _msg(message_type=MessageType.GOVERNANCE_REQUEST)
        assert proc._enforce_independent_validator_gate(msg) is None

    def test_enforce_independent_validator_gate_not_required(self):
        proc = self._make_processor()
        proc._require_independent_validator = True
        msg = _msg(message_type=MessageType.QUERY, impact_score=0.1)
        assert proc._enforce_independent_validator_gate(msg) is None

    def test_enforce_independent_validator_gate_missing_validator(self):
        proc = self._make_processor()
        proc._require_independent_validator = True
        msg = _msg(message_type=MessageType.GOVERNANCE_REQUEST, metadata={})
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert not result.is_valid
        assert "independent_validator_missing" in str(result.metadata)

    def test_enforce_independent_validator_gate_self_validation(self):
        proc = self._make_processor()
        proc._require_independent_validator = True
        msg = _msg(
            from_agent="agent-x",
            message_type=MessageType.GOVERNANCE_REQUEST,
            metadata={"validated_by_agent": "agent-x"},
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert not result.is_valid
        assert "self_validation" in str(result.metadata)

    def test_enforce_independent_validator_gate_invalid_stage(self):
        proc = self._make_processor()
        proc._require_independent_validator = True
        msg = _msg(
            from_agent="agent-x",
            message_type=MessageType.GOVERNANCE_REQUEST,
            metadata={
                "validated_by_agent": "agent-y",
                "validation_stage": "self",
            },
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is not None
        assert "invalid_stage" in str(result.metadata)

    def test_enforce_independent_validator_gate_passes(self):
        proc = self._make_processor()
        proc._require_independent_validator = True
        msg = _msg(
            from_agent="agent-x",
            message_type=MessageType.GOVERNANCE_REQUEST,
            metadata={
                "validated_by_agent": "agent-y",
                "validation_stage": "independent",
            },
        )
        result = proc._enforce_independent_validator_gate(msg)
        assert result is None

    def test_record_agent_workflow_event_no_collector(self):
        proc = self._make_processor()
        proc._agent_workflow_metrics = None
        msg = _msg()
        proc._record_agent_workflow_event(event_type="test", msg=msg, reason="r")

    def test_record_agent_workflow_event_with_collector(self):
        proc = self._make_processor()
        mock_collector = MagicMock()
        proc._agent_workflow_metrics = mock_collector
        msg = _msg()
        proc._record_agent_workflow_event(event_type="test", msg=msg, reason="r")
        mock_collector.record_event.assert_called_once()

    def test_record_agent_workflow_event_collector_raises(self):
        proc = self._make_processor()
        mock_collector = MagicMock()
        mock_collector.record_event.side_effect = RuntimeError("fail")
        proc._agent_workflow_metrics = mock_collector
        msg = _msg()
        proc._record_agent_workflow_event(event_type="test", msg=msg, reason="r")

    async def test_process_isolated_valid_message(self):
        proc = self._make_processor()
        msg = _msg()
        result = await proc.process(msg)
        assert isinstance(result, ValidationResult)

    async def test_process_retries_on_transient_error(self):
        proc = self._make_processor()
        call_count = 0
        original_do_process = proc._do_process

        async def failing_do_process(msg):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient")
            return await original_do_process(msg)

        proc._do_process = failing_do_process
        msg = _msg()
        result = await proc.process(msg, max_retries=3)
        assert call_count == 3

    async def test_process_max_retries_exceeded(self):
        proc = self._make_processor()

        async def always_fail(msg):
            raise ValueError("permanent error")

        proc._do_process = always_fail
        msg = _msg()
        result = await proc.process(msg, max_retries=2)
        assert not result.is_valid
        assert "max_retries_exceeded" in str(result.metadata)

    async def test_extract_session_context_disabled(self):
        proc = self._make_processor()
        proc._enable_session_governance = False
        msg = _msg()
        result = await proc._extract_session_context(msg)
        assert result is None

    async def test_perform_security_scan_clean(self):
        proc = self._make_processor()
        proc._security_scanner = MagicMock()
        proc._security_scanner.scan = AsyncMock(return_value=None)
        msg = _msg()
        result = await proc._perform_security_scan(msg)
        assert result is None

    async def test_perform_security_scan_blocked(self):
        proc = self._make_processor()
        rejection = ValidationResult(is_valid=False, errors=["injection detected"])
        proc._security_scanner = MagicMock()
        proc._security_scanner.scan = AsyncMock(return_value=rejection)
        msg = _msg()
        result = await proc._perform_security_scan(msg)
        assert result is not None
        assert not result.is_valid
        assert proc.failed_count == 1

    async def test_handle_tool_request_mcp_unavailable(self):
        proc = self._make_processor()
        with (
            patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", False),
            patch("enhanced_agent_bus.message_processor.MCPToolResult", None),
        ):
            result = await proc.handle_tool_request("agent-1", "tool-x")
            assert isinstance(result, dict)
            assert result["status"] == "error"

    async def test_send_to_dlq_import_error(self):
        proc = self._make_processor()
        msg = _msg()
        result = ValidationResult(is_valid=False, errors=["test"])
        with patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}):
            proc._dlq_redis = None
            await proc._send_to_dlq(msg, result)

    async def test_async_metering_callback_success(self):
        proc = self._make_processor()
        proc._metering_hooks = MagicMock()
        msg = _msg()
        await proc._async_metering_callback(msg, 5.0)
        proc._metering_hooks.on_constitutional_validation.assert_called_once()

    async def test_async_metering_callback_error(self):
        proc = self._make_processor()
        proc._metering_hooks = MagicMock()
        proc._metering_hooks.on_constitutional_validation.side_effect = RuntimeError("fail")
        msg = _msg()
        await proc._async_metering_callback(msg, 5.0)  # Should not raise

    def test_extract_rejection_reason(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        result = ValidationResult(is_valid=False, metadata={"rejection_reason": "test_reason"})
        assert MessageProcessor._extract_rejection_reason(result) == "test_reason"

    def test_detect_prompt_injection(self):
        proc = self._make_processor()
        proc._security_scanner = MagicMock()
        proc._security_scanner.detect_prompt_injection.return_value = None
        msg = _msg()
        assert proc._detect_prompt_injection(msg) is None

    async def test_handle_failed_processing_critical(self):
        proc = self._make_processor()
        proc._dlq_redis = None
        msg = _msg(priority=Priority.CRITICAL)
        result = ValidationResult(is_valid=False, errors=["fail"])
        with patch(
            "enhanced_agent_bus.message_processor.schedule_background_task",
            side_effect=lambda coroutine, _: coroutine.close(),
        ):
            await proc._handle_failed_processing(msg, result)
        assert proc.failed_count == 1

    async def test_handle_successful_processing(self):
        proc = self._make_processor()
        msg = _msg()
        result = ValidationResult(is_valid=True)
        with patch(
            "enhanced_agent_bus.message_processor.schedule_background_task",
            side_effect=lambda coroutine, _: coroutine.close(),
        ):
            await proc._handle_successful_processing(msg, result, "cache_key", 1.0)
        assert proc.processed_count == 1

    def test_auto_select_strategy_isolated(self):
        proc = self._make_processor(isolated_mode=True)
        strategy = proc._auto_select_strategy()
        assert strategy.get_name() == "python"

    def test_get_metrics_session_governance(self):
        proc = self._make_processor()
        proc._enable_session_governance = True
        proc._session_resolved_count = 5
        proc._session_not_found_count = 2
        proc._session_error_count = 1
        metrics = proc.get_metrics()
        assert "session_governance_enabled" in metrics
        assert metrics["session_governance_enabled"] is True

    def test_increment_failed_count(self):
        proc = self._make_processor()
        proc._increment_failed_count()
        assert proc.failed_count == 1


# ============================================================================
# message_processor.py — MCP integration paths
# ============================================================================


class TestMessageProcessorMCP:
    """Tests for MCP-related MessageProcessor methods."""

    def _make_processor(self):
        from enhanced_agent_bus.message_processor import MessageProcessor

        return MessageProcessor(isolated_mode=True)

    async def test_initialize_mcp_feature_disabled(self):
        proc = self._make_processor()
        with patch("enhanced_agent_bus.message_processor.MCP_ENABLED", False):
            await proc.initialize_mcp({})
        assert proc._mcp_pool is None

    async def test_initialize_mcp_deps_unavailable(self):
        proc = self._make_processor()
        with (
            patch("enhanced_agent_bus.message_processor.MCP_ENABLED", True),
            patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", False),
        ):
            await proc.initialize_mcp({})
        assert proc._mcp_pool is None

    async def test_handle_tool_request_pool_not_initialized(self):
        proc = self._make_processor()
        mock_tool_result = MagicMock()
        mock_tool_result.error_result = MagicMock(return_value="error")
        with (
            patch("enhanced_agent_bus.message_processor._MCP_AVAILABLE", True),
            patch("enhanced_agent_bus.message_processor.MCPToolResult", mock_tool_result),
        ):
            proc._mcp_pool = None
            result = await proc.handle_tool_request("agent-1", "tool-x")
            assert result == "error"
